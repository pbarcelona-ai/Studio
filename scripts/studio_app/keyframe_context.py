"""Shared Step 17 context, prompt builder, and turnaround reference resolver.

Ensures Step 17 (Storyboard Keyframes) accurately reflects all upstream steps:
- Step 08: Full character dossiers (`character_tokens.load_character`), cast reference
  photos, per-scene wardrobe states (`wardrobe_states.json`), and `cast_lock.json`.
- Step 09: Active visual style `positives`, `negatives`, `look`, and `hybrid_mode`
  from `global_params.json` and `character_types_registry`.
- Step 10: Character turnaround PNGs (`assets/turnarounds/*_sheet.png`, `*_front.png`,
  etc.) resolved via `character_identity` with outfit & variant awareness.
- Step 11: Set / location descriptions (continuity book + `sets_custom.json`, with
  article-normalized matching so `"the living room"` matches `"INT. LIVING ROOM - DAY"`),
  rendered set establishing images (`assets/sets/<safe>.png`), and continuity props.
- Step 12: Full shot cinematographic details (`type`, `lens_mm`, `height`, `angle`,
  `movement`, `composition`, `blocking`, `action`, `expression`, `lighting`, `props`).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("studio.keyframe_context")

_LEADING_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)
_SLUGLINE_PREFIX_RE = re.compile(r"^(?:int\.?/ext\.?|ext\.?/int\.?|int\.?|ext\.?)\s+", re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_SPACE_BRIDGE_RE = re.compile(r"\b(?:starship\s+bridge|bridge|space|moon|mars|asteroid|saturn|titan|enceladus|mimas|earth\s+orbit|re-?entry|launch|homeward)\b", re.IGNORECASE)


def _norm_key(text: str) -> str:
    """Normalize a location or prop name for fuzzy matching (strips leading articles & punctuation)."""
    s = str(text or "").strip().lower()
    s = _SLUGLINE_PREFIX_RE.sub("", s).strip()
    s = _LEADING_ARTICLE_RE.sub("", s).strip()
    return _NON_ALNUM_RE.sub(" ", s).strip()


def _scene_num(sid: str) -> int:
    digits = "".join(c for c in str(sid or "") if c.isdigit())
    return int(digits) if digits else 0


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log.debug("failed reading %s: %s", path.name, e)
        return {}


def _merge_character_dossier_text(name: str, full_ch: dict[str, Any]) -> str:
    """Build a complete visual description from a full Step 08 character dossier.

    Mirrors `_v2_turnarounds` so bare name-only `visual_token` entries (e.g. `"mom"`)
    never hide the richer `description`, `clothing`, or `consistency_notes`.
    """
    clean_name = str(name or full_ch.get("name") or "").strip()
    vt = str(full_ch.get("visual_token") or full_ch.get("token") or "").strip()
    clothing = str(full_ch.get("clothing") or "").strip()
    desc = str(full_ch.get("description") or "").strip()
    notes = str(full_ch.get("consistency_notes") or "").strip()

    parts: list[str] = []
    # Skip bare name-only visual_token (e.g. "mom") whenever richer fields exist
    if vt and (vt.lower() != clean_name.lower() or not (desc or notes or clothing)):
        parts.append(vt)
    if clothing and clothing.lower() not in " ".join(parts).lower():
        parts.append(f"wearing {clothing}")
    for extra in (desc, notes):
        if not extra:
            continue
        joined_words = set(re.findall(r"[a-z0-9]+", " ".join(parts).lower()))
        extra_words = set(re.findall(r"[a-z0-9]+", extra.lower()))
        overlap = (len(joined_words & extra_words) / max(1, len(extra_words))) if joined_words else 0.0
        if overlap < 0.65:
            parts.append(extra)
    return ". ".join(p.rstrip(". ") for p in parts if p)


def _find_cast_ref_photo(pd: Path, full_ch: dict[str, Any]) -> Path | None:
    """Return the first valid Step 08 uploaded cast reference photo for a character, if any."""
    raw_refs = full_ch.get("ref_photos") or full_ch.get("reference_photos") or []
    if isinstance(raw_refs, str):
        raw_refs = [raw_refs]
    if not isinstance(raw_refs, list):
        return None
    for item in raw_refs:
        if isinstance(item, dict):
            cand = str(item.get("rel_book") or item.get("rel_path") or item.get("path") or "").strip()
        else:
            cand = str(item or "").strip()
        if not cand:
            continue
        p = Path(cand)
        if not p.is_absolute():
            p_book = pd / cand
            if p_book.is_file() and p_book.stat().st_size > 100:
                return p_book
            # Also try stripping leading projects/books/<slug>/
            p_repo = Path(cand)
            if p_repo.is_file() and p_repo.stat().st_size > 100:
                return p_repo
        elif p.is_file() and p.stat().st_size > 100:
            return p
    return None


def load_keyframe_project_context(slug: str, pd: Path) -> dict[str, Any]:
    """Load all upstream Step 08–12 context for Step 17 keyframe prompts & rendering."""
    import character_identity
    import character_tokens
    import character_types_registry as ctr

    # --- Step 09: Style & Global Params ---
    gp = _read_json_dict(pd / "global_params.json")
    look = str(gp.get("look") or "pixar_3d").strip() or "pixar_3d"
    raw_hm = gp.get("hybrid_mode")
    hybrid_mode: dict[str, Any] = raw_hm if isinstance(raw_hm, dict) else {}
    style_rec = ctr.get_style(look) or {}
    # Prefer explicit Step 09 saved positives/negatives from global_params.json
    gp_pos = str(gp.get("positives") or "").strip()
    gp_neg = str(gp.get("negatives") or "").strip()
    style_prefix = gp_pos or str(style_rec.get("positives") or "").strip() or "cinematic 3D animated film still"
    style_negatives = gp_neg or str(style_rec.get("negatives") or "").strip()

    # --- Continuity Book (fallback characters, locations, props) ---
    cb: dict[str, Any] = {}
    for cb_file in (pd / f"{slug}.json", pd / "continuity.json"):
        if cb_file.is_file():
            cb = _read_json_dict(cb_file)
            if cb:
                break

    # --- Step 08: Characters (merge continuity -> cast_lock -> Step 08 full dossiers) ---
    cast_profiles: dict[str, dict[str, Any]] = {}

    def _upsert_char(
        name: str,
        token_text: str = "",
        *,
        prefer: bool = False,
        archetype: str = "",
        style_override: str = "",
        ref_photo: Path | None = None,
    ) -> None:
        clean = str(name or "").strip()
        if not clean:
            return
        k = clean.lower()
        t = str(token_text or "").strip()
        if k not in cast_profiles:
            cast_profiles[k] = {
                "name": clean,
                "token": t,
                "archetype": archetype,
                "style_override": style_override,
                "ref_photo": ref_photo,
            }
        else:
            rec = cast_profiles[k]
            # Never overwrite a richer description with a bare name-only token like "mom"
            is_bare = t.lower() == k
            if t and ((not is_bare and (prefer or not rec["token"] or rec["token"].lower() == k)) or not rec["token"]):
                rec["token"] = t
            if archetype:
                rec["archetype"] = archetype
            if style_override:
                rec["style_override"] = style_override
            if ref_photo and not rec.get("ref_photo"):
                rec["ref_photo"] = ref_photo

    for c in cb.get("characters") or []:
        if isinstance(c, dict) and c.get("name"):
            _upsert_char(str(c["name"]), str(c.get("token") or c.get("description") or ""))

    # Scene-specific cast locks (cast_lock.json)
    cast_lock_scenes: dict[str, dict[str, str]] = {}
    cl_doc = _read_json_dict(pd / "cast_lock.json")
    for sc_k, sc_val in (cl_doc.get("scenes") or {}).items():
        if not isinstance(sc_val, dict):
            continue
        sc_chars = sc_val.get("characters") or {}
        if isinstance(sc_chars, dict):
            cast_lock_scenes[str(sc_k).upper()] = {
                str(cn).lower(): str(cv.get("token") or "").strip()
                for cn, cv in sc_chars.items()
                if isinstance(cv, dict) and str(cv.get("token") or "").strip()
            }

    # Always prefer full Step 08 character dossiers via load_character()
    try:
        for ch in character_tokens.list_characters(slug) or []:
            if not isinstance(ch, dict) or not ch.get("name"):
                continue
            cname = str(ch["name"]).strip()
            full_ch = character_tokens.load_character(slug, cname) or ch
            merged_desc = _merge_character_dossier_text(cname, full_ch)
            _upsert_char(
                cname,
                merged_desc,
                prefer=True,
                archetype=str(full_ch.get("archetype") or ""),
                style_override=str(full_ch.get("style_override") or ""),
                ref_photo=_find_cast_ref_photo(pd, full_ch),
            )
    except Exception as e:
        log.debug("character_tokens read failed in keyframe_context: %s", e)

    # Step 08 wardrobe states per scene/location
    wardrobe_states: dict[str, list[dict[str, Any]]] = {}
    raw_ws = _read_json_dict(pd / "wardrobe_states.json")
    for k, v in raw_ws.items():
        if isinstance(v, list):
            wardrobe_states[str(k).lower()] = [x for x in v if isinstance(x, dict)]

    # --- Step 10: Identity overrides & known cast names ---
    identity_overrides = character_identity.load_identity_overrides(pd)
    known_names = [rec["name"] for rec in cast_profiles.values()]

    # --- Step 11: Locations / Sets (continuity + sets_custom.json + assets/sets/*.png) ---
    locations: dict[str, dict[str, Any]] = {}
    for loc in cb.get("locations") or []:
        if isinstance(loc, dict) and loc.get("name"):
            lname = str(loc["name"]).strip()
            ltok = str(loc.get("token") or loc.get("description") or "").strip()
            nk = _norm_key(lname)
            if nk and ltok:
                locations[nk] = {"name": lname, "token": ltok, "lighting": ""}

    raw_custom_sets = _read_json_dict(pd / "sets_custom.json")
    for k_cs, val in raw_custom_sets.items():
        if not isinstance(val, dict):
            continue
        lname = str(val.get("name") or k_cs).strip()
        desc = str(val.get("description") or val.get("token") or "").strip()
        light = str(val.get("lighting") or "").strip()
        nk = _norm_key(lname)
        if nk and (desc or light):
            prev = locations.get(nk) or {}
            locations[nk] = {
                "name": lname,
                "token": desc or prev.get("token", ""),
                "lighting": light or prev.get("lighting", ""),
            }

    # Index rendered Step 11 set plates (assets/sets/*.png), preferring pinned Baselines from sets_views.json!
    set_images: dict[str, Path] = {}
    sets_dir = pd / "assets" / "sets"
    if sets_dir.is_dir():
        for p in sorted(sets_dir.glob("*.png")):
            if p.stat().st_size <= 100:
                continue
            stem_low = p.stem.lower()
            if "__view_" in stem_low or stem_low.endswith("_baseline"):
                continue
            nk = _norm_key(p.stem.replace("_", " "))
            if nk:
                set_images[nk] = p

    raw_views_doc = _read_json_dict(pd / "sets_views.json")
    raw_vsets = raw_views_doc.get("sets") if isinstance(raw_views_doc.get("sets"), dict) else {}
    if isinstance(raw_vsets, dict):
        for sk, sdata in raw_vsets.items():
            if not isinstance(sdata, dict):
                continue
            nk = _norm_key(str(sdata.get("name") or sk))
            if not nk:
                continue
            b_snap = str(sdata.get("baseline_snapshot") or "").strip()
            if b_snap:
                bp = pd / b_snap
                if bp.is_file() and bp.stat().st_size > 100:
                    # Pinned Baseline ALWAYS takes top priority for Step 17!
                    set_images[nk] = bp
                    continue
            if nk not in set_images:
                for vw in sdata.get("views") or []:
                    if not isinstance(vw, dict):
                        continue
                    crel = str(vw.get("converted_image") or "").strip()
                    if crel and (pd / crel).is_file() and (pd / crel).stat().st_size > 100:
                        set_images[nk] = pd / crel
                        break

    # --- Continuity Props ---
    props_map: dict[str, dict[str, str]] = {}
    for pr in cb.get("props") or []:
        if isinstance(pr, dict) and pr.get("name") and pr.get("token"):
            pname = str(pr["name"]).strip()
            ptok = str(pr["token"]).strip()
            nk = _norm_key(pname)
            if nk:
                props_map[nk] = {"name": pname, "token": ptok}

    return {
        "slug": slug,
        "pd": pd,
        "look": look,
        "hybrid_mode": hybrid_mode,
        "style_prefix": style_prefix,
        "style_negatives": style_negatives,
        "cast_profiles": cast_profiles,
        "cast_lock_scenes": cast_lock_scenes,
        "wardrobe_states": wardrobe_states,
        "identity_overrides": identity_overrides,
        "known_names": known_names,
        "locations": locations,
        "set_images": set_images,
        "set_plates_count": len(set_images),
        "props_map": props_map,
    }


def compute_scene_seed(slug: str, sc_id: str) -> int:
    """Deterministic positive 31-bit seed shared across shots in the same scene to stabilize room/lighting."""
    digest = hashlib.sha256(f"neon_scene_seed:{slug}:{sc_id}".encode()).digest()
    return (int.from_bytes(digest[:4], "big") % 1_999_999_000) + 100


def detect_camera_continuity(
    cur_shot: dict[str, Any] | None,
    ref_shot: dict[str, Any] | None,
    cur_prompt: str,
    ref_prompt: str,
) -> tuple[str, float | None]:
    """Classify shot-to-shot continuity using Step 12 camera metadata + prompt similarity.

    Returns ``(mode, recommended_init_strength)`` where mode is:
    - ``"same_angle"`` -> strong img2img lock (``0.45``) preserving room/camera geometry
    - ``"incremental"`` -> moderate img2img lock (``0.62``) preserving palette & layout
    - ``"scene_cut"`` -> fresh composition using ``-r`` references only (``None``)
    """
    import difflib

    sim = (
        difflib.SequenceMatcher(None, ref_prompt.lower(), cur_prompt.lower()).ratio()
        if (ref_prompt and cur_prompt)
        else 0.5
    )

    if isinstance(cur_shot, dict) and isinstance(ref_shot, dict):
        c_type = str(cur_shot.get("type") or "").strip().upper()
        r_type = str(ref_shot.get("type") or "").strip().upper()
        c_lens = int(cur_shot.get("lens_mm") or 0)
        r_lens = int(ref_shot.get("lens_mm") or 0)
        c_height = str(cur_shot.get("height") or "eye").strip().lower()
        r_height = str(ref_shot.get("height") or "eye").strip().lower()
        c_angle = _norm_key(str(cur_shot.get("angle") or ""))
        r_angle = _norm_key(str(ref_shot.get("angle") or ""))

        # Explicit reverse angle / opposing side cues always count as a camera cut
        combined_angles = f"{c_angle} {r_angle}"
        if "reverse" in c_angle or ("behind" in c_angle) != ("behind" in r_angle):
            return "scene_cut", None

        lens_close = bool(c_lens and r_lens and abs(c_lens - r_lens) <= 10)
        same_type = bool(c_type and r_type and c_type == r_type)
        same_height = c_height == r_height
        angle_similar = (
            (not c_angle and not r_angle)
            or (c_angle == r_angle)
            or (
                bool(c_angle and r_angle)
                and difflib.SequenceMatcher(None, c_angle, r_angle).ratio() >= 0.65
            )
        )
        # Continuing the same camera move (e.g. matching rightward truck/pan) or locked same angle
        if same_type and lens_close and same_height and angle_similar:
            return "same_angle", 0.45
        if (same_type or lens_close) and same_height and (angle_similar or sim >= 0.50):
            return "incremental", 0.62
        if "reverse" in combined_angles:
            return "scene_cut", None

    if sim >= 0.65:
        return "same_angle", 0.45
    if sim >= 0.50:
        return "incremental", 0.62
    return "scene_cut", None


# Exact camera move strings expected by ComfyUI `apps/angles` (Qwen-Image-Edit Multiple Angles LoRA)
ANGLES_CAMERA_MOVES: dict[str, tuple[str, str]] = {
    "rotate_left_45": ("Rotate 45° left", "\u5c06\u955c\u5934\u5411\u5de6\u65cb\u8f6c45\u5ea6 Rotate the camera 45 degrees to the left."),
    "rotate_right_45": ("Rotate 45° right", "\u5c06\u955c\u5934\u5411\u53f3\u65cb\u8f6c45\u5ea6 Rotate the camera 45 degrees to the right."),
    "move_forward": ("Move forward (closer)", "\u5c06\u955c\u5934\u5411\u524d\u79fb\u52a8 Move the camera forward."),
    "move_back": ("Move back (wider)", "\u5c06\u955c\u5934\u5411\u540e\u79fb\u52a8 Move the camera backward."),
    "move_left": ("Move left", "\u5c06\u955c\u5934\u5411\u5de6\u79fb\u52a8 Move the camera left."),
    "move_right": ("Move right", "\u5c06\u955c\u5934\u5411\u53f3\u79fb\u52a8 Move the camera right."),
    "move_up": ("Move up", "\u5c06\u955c\u5934\u5411\u4e0a\u79fb\u52a8 Move the camera up."),
    "move_down": ("Move down", "\u5c06\u955c\u5934\u5411\u4e0b\u79fb\u52a8 Move the camera down."),
    "top_down": ("Top-down view", "\u5c06\u955c\u5934\u8f6c\u4e3a\u4fef\u89c6 Turn the camera to a top-down view."),
    "low_angle": ("Low angle", "\u5c06\u955c\u5934\u8f6c\u4e3a\u4ef0\u89c6 Turn the camera to a low-angle view looking up."),
}


def map_shot_to_angles_move(
    cur_shot: dict[str, Any] | None,
    ref_shot: dict[str, Any] | None = None,
    prompt: str = "",
) -> str:
    """Map Step 12 camera specs to the closest ComfyUI `apps/angles` Qwen-Image-Edit camera move string."""
    angle_txt = (
        f"{(cur_shot or {}).get('height', '')} {(cur_shot or {}).get('angle', '')} "
        f"{(cur_shot or {}).get('movement', '')} {prompt[:160]}"
    ).lower()
    if any(k in angle_txt for k in ("top-down", "top down", "overhead", "bird's-eye", "birds eye", "directly above")):
        return ANGLES_CAMERA_MOVES["top_down"][1]
    if any(k in angle_txt for k in ("low angle", "low-angle", "floor-level", "floor level", "looking up")) or str((cur_shot or {}).get("height") or "").lower() == "low":
        return ANGLES_CAMERA_MOVES["low_angle"][1]
    if any(k in angle_txt for k in ("frame left", "camera-left", "camera left", "from left")):
        return ANGLES_CAMERA_MOVES["rotate_left_45"][1]
    if any(k in angle_txt for k in ("frame right", "camera-right", "camera right", "from right")):
        return ANGLES_CAMERA_MOVES["rotate_right_45"][1]

    c_type = str((cur_shot or {}).get("type") or "").upper()
    r_type = str((ref_shot or {}).get("type") or "").upper()
    tight = {"ECU", "CU", "MCU", "INSERT"}
    wide = {"EWS", "WS", "MLS"}
    if c_type in tight and (not r_type or r_type in wide or r_type == "MS"):
        return ANGLES_CAMERA_MOVES["move_forward"][1]
    if c_type in wide and r_type in tight:
        return ANGLES_CAMERA_MOVES["move_back"][1]
    if "push in" in angle_txt or "dolly in" in angle_txt:
        return ANGLES_CAMERA_MOVES["move_forward"][1]
    if "pull out" in angle_txt or "pull back" in angle_txt:
        return ANGLES_CAMERA_MOVES["move_back"][1]
    return ""


def match_wardrobe_state(
    ctx: dict[str, Any],
    char_name: str,
    sc_id: str,
    heading_text: str,
) -> tuple[str, str]:
    """Return `(wardrobe_text, outfit_id)` matching a character in this scene/location."""
    states = ctx["wardrobe_states"].get(char_name.lower()) or []
    if not states:
        return "", ""
    sn = _scene_num(sc_id)
    low_h = heading_text.lower()
    for idx, st in enumerate(states, start=1):
        w = str(st.get("wardrobe") or "").strip()
        if not w:
            continue
        oid = f"outfit{idx}"
        sc_spec = str(st.get("scenes") or "").strip()
        loc_spec = str(st.get("location") or "").strip().lower()
        if sc_spec and sn > 0:
            matched = False
            for part in sc_spec.replace(" ", "").split(","):
                if "-" in part:
                    a, b = part.split("-", 1)
                    na, nb = _scene_num(a), _scene_num(b)
                    if na and nb and na <= sn <= nb:
                        matched = True
                        break
                elif _scene_num(part) == sn:
                    matched = True
                    break
            if matched:
                loc_lbl = str(st.get("location") or "").strip()
                return (f"{w} (in {loc_lbl})" if loc_lbl else w), oid
        if loc_spec and loc_spec in low_h:
            return w, oid
    return "", ""


def match_location_context(ctx: dict[str, Any], heading_text: str) -> tuple[str, Path | None, list[str]]:
    """Match a scene heading against Step 11 / continuity locations and rendered set images.

    Strips leading `"the "`/`"a "`/`"INT."`/`"EXT."` so `"the living room"` matches
    `"INT. LIVING ROOM - DAY"` and `"the starship bridge"` + `"the Moon flyby"` both
    match `"INT. STARSHIP BRIDGE - MOON FLYBY"`.
    """
    norm_h = _norm_key(heading_text)
    if not norm_h:
        return "", None, []

    locations: dict[str, dict[str, Any]] = ctx["locations"]
    matched_entries: list[tuple[int, str, dict[str, Any]]] = []
    # Match longest keys first; match on word boundaries so "mars" doesn't match "marsh"
    for nk, rec in sorted(locations.items(), key=lambda kv: -len(kv[0])):
        if not nk or len(nk) < 3:
            continue
        if re.search(rf"\b{re.escape(nk)}\b", norm_h):
            # Position in heading preserves primary location before secondary viewscreen location
            pos = norm_h.find(nk)
            matched_entries.append((pos, nk, rec))

    matched_entries.sort(key=lambda t: (t[0], -len(t[1])))

    # Deduplicate overlapping substrings (e.g. if both "starship bridge" and "bridge" matched)
    kept: list[tuple[str, dict[str, Any]]] = []
    for _pos, nk, rec in matched_entries:
        if any(nk in prev_nk for prev_nk, _ in kept):
            continue
        kept.append((nk, rec))

    loc_bits: list[str] = []
    matched_names: list[str] = []
    set_img: Path | None = None
    for nk, rec in kept[:2]:
        tok = str(rec.get("token") or "").strip()
        if tok:
            loc_bits.append(tok)
            matched_names.append(str(rec.get("name") or nk))
        if set_img is None and nk in ctx["set_images"]:
            set_img = ctx["set_images"][nk]

    # Also check set_images directly even if no text token matched
    if set_img is None:
        for nk, img_p in sorted(ctx["set_images"].items(), key=lambda kv: -len(kv[0])):
            if len(nk) >= 3 and re.search(rf"\b{re.escape(nk)}\b", norm_h):
                set_img = img_p
                break

    return "; ".join(loc_bits), set_img, matched_names


def match_props_tokens(ctx: dict[str, Any], shot_props: list[str]) -> list[str]:
    """Resolve shotlist prop names against Step 11 / continuity locked prop tokens."""
    props_map: dict[str, dict[str, str]] = ctx["props_map"]
    if not props_map or not shot_props:
        return []
    matched: list[str] = []
    seen_keys: set[str] = set()
    for raw_p in shot_props:
        np = _norm_key(str(raw_p))
        if not np:
            continue
        # Direct match or substring match on normalized prop name
        best_k = ""
        if np in props_map:
            best_k = np
        else:
            for pk in sorted(props_map.keys(), key=len, reverse=True):
                if len(pk) >= 4 and (pk in np or np in pk):
                    best_k = pk
                    break
        if best_k and best_k not in seen_keys:
            seen_keys.add(best_k)
            matched.append(props_map[best_k]["token"])
        if len(matched) >= 3:
            break
    return matched


def resolve_shot_characters(
    sh: dict[str, Any],
    sc_id: str,
    heading: str,
    ctx: dict[str, Any],
) -> list[str]:
    """Resolve shot characters to the most accurate Step 08/10 cast variant for this scene.

    For example, when a starship bridge shot lists ``TOMMY`` or ``JUDAH`` while
    ``CAPTAIN TOMMY`` / ``FIRST OFFICER JUDAH`` exist in the cast and the shot
    mentions their uniform/rank (or takes place on the starship bridge without
    explicitly wearing their home clothes), promote to the exact uniformed variant
    so both the Step 17 prompt and Step 10 turnaround reference match!
    """
    import character_identity

    raw_chars = [str(c).strip() for c in (sh.get("characters") or []) if str(c).strip()]
    if not raw_chars:
        return []

    cast_profiles: dict[str, dict[str, Any]] = ctx["cast_profiles"]
    known_names: list[str] = ctx["known_names"]
    overrides: dict[str, str] = ctx["identity_overrides"]

    shot_text = " ".join(
        str(sh.get(k) or "") for k in ("composition", "blocking", "action", "expression")
    ).lower()
    is_bridge = bool(_SPACE_BRIDGE_RE.search(heading))

    # Build map of canonical_key -> list of cast profile names (variants)
    canon_variants: dict[str, list[str]] = {}
    for rec in cast_profiles.values():
        cn = rec["name"]
        ck = character_identity.canonical_character_key(cn, known_names=known_names, overrides=overrides)
        canon_variants.setdefault(ck, []).append(cn)

    resolved: list[str] = []
    seen_lower: set[str] = set()
    raw_lowers = {c.lower() for c in raw_chars}

    for c in raw_chars:
        chosen = c
        ck = character_identity.canonical_character_key(c, known_names=known_names, overrides=overrides)
        variants = canon_variants.get(ck) or []

        # Only consider promoting when `c` is the bare/base name (slug == canonical key)
        # and another variant of the same canonical character exists in the cast.
        if character_identity.safe_char_slug(c) == ck and len(variants) > 1:
            # Explicit variant name mentioned in shot text (e.g. "captain tommy", "first officer judah")
            best_var = ""
            for v in variants:
                vl = v.lower()
                if vl == c.lower():
                    continue
                if vl in raw_lowers:
                    # Both base & variant explicitly listed (e.g. transformation shot S007-03); keep as-is
                    best_var = ""
                    break
                if re.search(rf"\b{re.escape(vl)}\b", shot_text):
                    best_var = v
                    break

            if not best_var:
                # Check for crayon-marked / state parenthetical variants explicitly described in shot
                for v in variants:
                    vl = v.lower()
                    if vl == c.lower() or vl in raw_lowers:
                        continue
                    if "crayon" in vl and "crayon" in shot_text and "no crayon" not in shot_text:
                        best_var = v
                        break

            if not best_var and is_bridge:
                # On the starship bridge, promote to uniformed space rank variant (Captain / First Officer)
                # UNLESS the shot explicitly describes their home outfit (e.g. "still in his solid brown t-shirt").
                base_tok = str((cast_profiles.get(c.lower()) or {}).get("token") or "").lower()
                home_cues = ("still in", "brown t-shirt", "t-shirt", "blue jeans", "white socks")
                staying_home = any(hc in shot_text for hc in home_cues)
                if not staying_home:
                    for v in variants:
                        vl = v.lower()
                        if vl == c.lower() or vl in raw_lowers:
                            continue
                        if any(rank in vl for rank in ("captain", "first officer", "commander", "pilot", "astronaut")):
                            # Extra check: if shot mentions variant clothing or we're on bridge, promote
                            v_tok = str((cast_profiles.get(vl) or {}).get("token") or "").lower()
                            if v_tok != base_tok:
                                best_var = v
                                break
            if best_var:
                chosen = best_var

        if chosen.lower() not in seen_lower:
            seen_lower.add(chosen.lower())
            resolved.append(chosen)

    return resolved


def find_character_visual_ref(
    ctx: dict[str, Any],
    char_name: str,
    *,
    prefer_outfit: str = "",
) -> tuple[Path | None, str, str]:
    """Find the best visual reference image for `char_name`: Step 10 turnaround first, then Step 08 cast photo.

    Returns ``(path_or_none, url_or_empty, source_label)``.
    """
    import character_identity

    pd: Path = ctx["pd"]
    slug: str = ctx["slug"]
    t_dir = pd / "assets" / "turnarounds"

    # 1. Check Step 10 turnarounds via canonical identity lookup
    if t_dir.is_dir():
        # Prefer 3-panel sheet if present for exact slug, else front/3-4/profile via canonical lookup
        safe = character_identity.safe_char_slug(char_name)
        sheet_cands = []
        if prefer_outfit and prefer_outfit != "default":
            sheet_cands.append(t_dir / f"{safe}_{prefer_outfit}_sheet.png")
        sheet_cands.append(t_dir / f"{safe}_sheet.png")
        for sp in sheet_cands:
            if sp.is_file() and sp.stat().st_size > 100:
                rel = sp.relative_to(pd).as_posix()
                return sp, f"/file/{slug}/{rel}", "turnaround_sheet"

        refs = character_identity.find_canonical_character_refs(
            t_dir,
            char_name,
            prefer_outfit=prefer_outfit,
            known_names=ctx["known_names"],
            overrides=ctx["identity_overrides"],
            limit=1,
        )
        if refs:
            p, src_name = refs[0]
            rel = p.relative_to(pd).as_posix()
            lbl = "turnaround" if src_name.lower() == char_name.lower() else f"turnaround ({src_name})"
            return p, f"/file/{slug}/{rel}", lbl

    # 2. Fallback to Step 08 uploaded cast reference photo
    rec = ctx["cast_profiles"].get(char_name.lower())
    if rec and isinstance(rec.get("ref_photo"), Path):
        rp: Path = rec["ref_photo"]
        if rp.is_file() and rp.stat().st_size > 100:
            try:
                rel = rp.relative_to(pd).as_posix()
                return rp, f"/file/{slug}/{rel}", "cast_ref_photo"
            except ValueError:
                return rp, "", "cast_ref_photo"

    return None, "", ""


def build_shot_keyframe_info(
    sh: dict[str, Any],
    sc_id: str,
    heading: str,
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Build accurate default prompt, cast tokens, turnaround refs, and set lock for one Step 17 shot."""
    import character_types_registry as ctr

    stype = str(sh.get("type") or "MS")
    lens = sh.get("lens_mm") or 35
    height = str(sh.get("height") or "").strip()
    angle = str(sh.get("angle") or "").strip()
    movement = str(sh.get("movement") or "").strip()
    comp = str(sh.get("composition") or "").strip()
    blocking = str(sh.get("blocking") or "").strip()
    act = str(sh.get("action") or "").strip()
    expr = str(sh.get("expression") or "").strip()
    light = str(sh.get("lighting") or "").strip()
    shot_props = [str(p) for p in (sh.get("props") or []) if p]

    resolved_chars = resolve_shot_characters(sh, sc_id, heading, ctx)
    cast_profiles: dict[str, dict[str, Any]] = ctx["cast_profiles"]
    sc_locks = ctx["cast_lock_scenes"].get(sc_id.upper()) or {}

    toks: list[str] = []
    attention_notes: list[str] = []
    char_refs: list[dict[str, Any]] = []

    for c in resolved_chars:
        rec = cast_profiles.get(c.lower()) or {}
        base_tok = str(rec.get("token") or "").strip()
        # Fallback to scene cast_lock.json if Step 08 profile is missing or bare name
        if not base_tok or base_tok.lower() == c.lower():
            base_tok = sc_locks.get(c.lower(), base_tok)

        # Include per-character visual style override for mixed-media films
        style_ov_id = str(rec.get("style_override") or "").strip()
        style_ov_tag = ""
        if style_ov_id:
            ov_st = ctr.get_style(style_ov_id)
            if ov_st and ov_st.get("positives"):
                style_ov_tag = f" [CHARACTER STYLE: {ov_st['positives']}]"

        sc_wardrobe, prefer_outfit = match_wardrobe_state(ctx, c, sc_id, heading)
        if sc_wardrobe and base_tok:
            toks.append(f"{c}: {base_tok}{style_ov_tag} | SCENE WARDROBE: {sc_wardrobe}")
        elif sc_wardrobe:
            toks.append(f"{c}: {sc_wardrobe}{style_ov_tag}")
        elif base_tok and base_tok.lower() != c.lower():
            toks.append(f"{c}: {base_tok}{style_ov_tag}")
            if "striped" in base_tok.lower() or len(base_tok) < 25:
                attention_notes.append(f"{c}'s wardrobe needs specific solid colors/outfit in Step 08")
        else:
            attention_notes.append(f"{c} has no visual/wardrobe description in Step 08")

        ref_path, ref_url, ref_source = find_character_visual_ref(ctx, c, prefer_outfit=prefer_outfit)
        char_refs.append({
            "name": c,
            "has_ref": bool(ref_path),
            "ref_url": ref_url,
            "ref_path": str(ref_path) if ref_path else "",
            "ref_source": ref_source,
            "has_profile": bool(base_tok and base_tok.lower() != c.lower()),
        })

    loc_tok, set_img_path, matched_loc_names = match_location_context(ctx, heading)
    prop_toks = match_props_tokens(ctx, shot_props)

    # Assemble rich, faithful prompt from Steps 08–12
    cam_specs = [f"{lens}mm lens"]
    if height and height.lower() != "eye":
        cam_specs.append(f"{height} camera height")
    if angle and angle.lower() != "straight":
        cam_specs.append(angle)
    if movement and movement.lower() != "static":
        cam_specs.append(f"{movement} camera movement")

    bits: list[str] = [f"{ctx['style_prefix']}, {stype} shot ({', '.join(cam_specs)})"]
    if loc_tok:
        bits.append(f"LOCKED LOCATION ({heading}): {loc_tok}" if heading else f"LOCKED LOCATION: {loc_tok}")
    elif heading:
        bits.append(f"LOCKED LOCATION: {heading}")
    if comp:
        bits.append(comp)
    if blocking and blocking.lower() not in comp.lower():
        bits.append(f"Blocking: {blocking}")
    if act and act.lower() not in comp.lower() and act.lower() not in blocking.lower():
        bits.append(f"Action: {act}")
    if expr:
        bits.append(f"Expression: {expr}")
    if prop_toks:
        bits.append("LOCKED PROPS: " + "; ".join(prop_toks))
    if light:
        bits.append(f"Lighting: {light}")
    if toks:
        bits.append(
            "LOCKED CHARACTERS & TURNAROUND WARDROBE (match attached turnaround references, exact faces, proportions & clothing): "
            + "; ".join(toks[:5])
        )
    default_prompt = ". ".join(b.rstrip(". ") for b in bits if b)

    set_ref_url = ""
    if set_img_path and set_img_path.is_file():
        try:
            rel_s = set_img_path.relative_to(ctx["pd"]).as_posix()
            set_ref_url = f"/file/{ctx['slug']}/{rel_s}"
        except ValueError:
            set_ref_url = ""

    return {
        "characters": resolved_chars,
        "char_refs": char_refs,
        "matched_locations": matched_loc_names,
        "set_ref_path": str(set_img_path) if set_img_path else "",
        "set_ref_url": set_ref_url,
        "default_prompt": default_prompt,
        "attention_notes": attention_notes,
    }


def is_saved_prompt_broken_or_stale(saved_prompt: str, info: dict[str, Any]) -> bool:
    """Detect legacy broken auto-generated prompts (e.g. `MOM: mom` or missing matched location details)."""
    sp = str(saved_prompt or "").strip()
    if not sp:
        return True
    # 1. Bare name-only character token like "MOM: mom;" or "MOM: mom" at end of prompt
    for cr in info.get("char_refs") or []:
        cname = str(cr.get("name") or "").strip()
        if cname and cr.get("has_profile"):
            pat = re.compile(rf"\b{re.escape(cname)}\s*:\s*{re.escape(cname)}\b(?:\s*[;.]|$)", re.IGNORECASE)
            if pat.search(sp):
                return True
    # 2. Old prompt had bare "LOCKED LOCATION: INT. ..." with no set description even though we now match one
    if info.get("matched_locations") and re.search(r"LOCKED LOCATION:\s*(?:INT|EXT)\.", sp):
        if "LOCKED LOCATION (" not in sp:
            return True
    return False


def collect_render_references(
    ctx: dict[str, Any],
    shot_id: str,
    prompt: str,
    sl_data: dict[str, Any],
    kf_dir: Path,
    saved_prompts_map: dict[str, Any],
    *,
    anchor_shot_id: str = "",
    user_strength: float | None = None,
) -> dict[str, Any]:
    """Collect ordered reference images (anchor + prev shot + character turnarounds + set plate),
    deterministic scene seed, same-angle img2img lock parameters, and reference legend.

    Guarantees character turnarounds for characters in the shot are NEVER dropped by
    previous-shot/anchor refs (up to 4 total refs for FLUX.2-klein-4B / Gemini).
    """
    sc_id = shot_id.split("-")[0] if "-" in shot_id else ""
    sh_num = int(shot_id.split("-")[1]) if ("-" in shot_id and shot_id.split("-")[1].isdigit()) else 0
    scene_seed = compute_scene_seed(ctx["slug"], sc_id or shot_id)

    target_scene: dict[str, Any] | None = None
    target_shot: dict[str, Any] | None = None
    shots_by_id: dict[str, dict[str, Any]] = {}
    if sl_data and sc_id:
        for sc in sl_data.get("scenes") or []:
            if str(sc.get("id") or sc.get("scene") or "") == sc_id:
                target_scene = sc
                for idx, sh in enumerate(sc.get("shots") or [], start=1):
                    if not isinstance(sh, dict):
                        continue
                    n = int(sh.get("n") or idx)
                    shots_by_id[f"{sc_id}-{n:02d}"] = sh
                    if n == sh_num:
                        target_shot = sh
                break

    heading = str((target_scene or {}).get("heading") or "")

    # 1. Resolve characters from shotlist + any cast members explicitly mentioned in the user's edited prompt
    # Strip the auto-generated `LOCKED CHARACTERS & TURNAROUND WARDROBE:` block first so relative
    # height notes like "waist-high to Mom" inside Tommy's own dossier never drag absent characters in!
    resolved_chars: list[str] = []
    if target_shot is not None:
        resolved_chars = resolve_shot_characters(target_shot, sc_id, heading, ctx)
    action_prompt = re.split(r"LOCKED CHARACTERS\b", prompt, maxsplit=1, flags=re.IGNORECASE)[0]
    low_prompt = action_prompt.lower()
    seen_low = {c.lower() for c in resolved_chars}
    for cn in sorted(ctx["known_names"], key=len, reverse=True):
        cnl = cn.lower()
        if cnl in seen_low or len(cnl) < 3 or "offstage" in cnl:
            continue
        if re.search(rf"\b{re.escape(cnl)}\b(?!['’]s\b)", low_prompt):
            import character_identity
            ck = character_identity.canonical_character_key(cn, known_names=ctx["known_names"], overrides=ctx["identity_overrides"])
            already_same = any(
                character_identity.canonical_character_key(ex, known_names=ctx["known_names"], overrides=ctx["identity_overrides"]) == ck
                for ex in resolved_chars
            )
            if not already_same:
                resolved_chars.append(cn)
                seen_low.add(cnl)

    def _shot_text_for(sid_key: str) -> str:
        t = str(saved_prompts_map.get(sid_key) or "").strip()
        if t:
            return t
        sh_obj = shots_by_id.get(sid_key)
        if sh_obj:
            return f"{sh_obj.get('type', '')} {sh_obj.get('composition', '')} {sh_obj.get('action', '')}".strip()
        return ""

    # 2. Check pinned Scene Anchor first (prevents chain drift across long scenes)
    anchor_ref = ""
    anchor_png: Path | None = None
    if anchor_shot_id and anchor_shot_id != shot_id:
        cand_a = kf_dir / f"{anchor_shot_id}.png"
        if cand_a.is_file() and cand_a.stat().st_size > 200:
            anchor_ref = anchor_shot_id
            anchor_png = cand_a

    # 3. Check immediately preceding rendered keyframe in the same scene
    prev_shot_ref = ""
    prev_png: Path | None = None
    if sc_id and sh_num > 1:
        for prev_n in range(sh_num - 1, 0, -1):
            cand_id = f"{sc_id}-{prev_n:02d}"
            cand_png = kf_dir / f"{cand_id}.png"
            if cand_png.is_file() and cand_png.stat().st_size > 200:
                prev_shot_ref = cand_id
                prev_png = cand_png
                break

    # Primary spatial reference for continuity comparison:
    # prefer immediately preceding shot if same angle, else pinned anchor if present, else prev shot.
    primary_ref_id = ""
    primary_ref_png: Path | None = None
    continuity_mode = "none"
    auto_strength: float | None = None

    candidates: list[tuple[str, Path]] = []
    if prev_png is not None:
        candidates.append((prev_shot_ref, prev_png))
    if anchor_png is not None and anchor_ref != prev_shot_ref:
        candidates.append((anchor_ref, anchor_png))

    for cid, cpng in candidates:
        mode, rec_str = detect_camera_continuity(
            target_shot,
            shots_by_id.get(cid),
            prompt,
            _shot_text_for(cid),
        )
        # Prefer a same_angle match over incremental over scene_cut
        rank = {"same_angle": 3, "incremental": 2, "scene_cut": 1, "none": 0}
        if not primary_ref_id or rank.get(mode, 0) > rank.get(continuity_mode, 0):
            primary_ref_id = cid
            primary_ref_png = cpng
            continuity_mode = mode
            auto_strength = rec_str

    # If user pinned an anchor and neither is same_angle, anchor takes lead over sequential prev shot to eliminate chain drift
    if anchor_png is not None and continuity_mode == "scene_cut":
        primary_ref_id = anchor_ref
        primary_ref_png = anchor_png

    # Resolve effective init_image & init_strength (respecting explicit user slider when provided)
    init_image: Path | None = None
    init_strength: float | None = None
    if primary_ref_png is not None:
        if user_strength is not None:
            if user_strength < 0.99:
                init_image = primary_ref_png
                init_strength = max(0.15, min(0.95, float(user_strength)))
        elif auto_strength is not None:
            init_image = primary_ref_png
            init_strength = auto_strength

    continuity_prefix = ""
    if primary_ref_id:
        ref_txt = _shot_text_for(primary_ref_id)
        if continuity_mode == "same_angle":
            continuity_prefix = (
                f"LOCKED CAMERA / IDENTICAL BACKGROUND CONTINUITY (SAME ANGLE as {primary_ref_id}): "
                f"Keep the EXACT SAME camera position, room geometry, wall details, window mullions, furniture positions, props, and lighting pixel-consistent with {primary_ref_id}. "
                f"Do NOT rearrange the room or change lighting. Change ONLY the character pose, expression, or new action described below.\n"
                f"Reference frame ({primary_ref_id}): {ref_txt[:220]}\n"
            )
        elif continuity_mode == "incremental":
            continuity_prefix = (
                f"SHOT-TO-SHOT CONTINUITY (INCREMENTAL CHANGE from {primary_ref_id}): "
                f"Maintain the EXACT SAME room layout, lighting, furniture positions, camera world, character faces, and clothing from {primary_ref_id}. "
                f"Apply ONLY the pose, expression, or slight framing adjustment described below.\n"
                f"Reference frame ({primary_ref_id}): {ref_txt[:220]}\n"
            )
        else:
            continuity_prefix = (
                f"SHOT-TO-SHOT CONTINUITY (NEW CAMERA ANGLE within the SAME scene as {primary_ref_id}): "
                f"Keep the EXACT SAME character identities, clothing colors, room palette, furniture style, props, and lighting from {primary_ref_id}, "
                f"while executing the camera angle or blocking change described below.\n"
                f"Scene reference ({primary_ref_id}): {ref_txt[:220]}\n"
            )

    # 4. Resolve matched Step 11 Set Plate FIRST and ALWAYS reserve a dedicated slot so it is NEVER
    # dropped by character turnarounds.
    set_img_path: Path | None = None
    set_loc_lbl = ""
    set_ref_url = ""
    if heading:
        _loc_tok, cand_set_img, matched_locs = match_location_context(ctx, heading)
        if cand_set_img and cand_set_img.is_file() and cand_set_img.stat().st_size > 100:
            set_img_path = cand_set_img
            set_loc_lbl = matched_locs[0] if matched_locs else heading
            try:
                set_ref_url = f"/file/{ctx['slug']}/{set_img_path.relative_to(ctx['pd']).as_posix()}"
            except ValueError:
                set_ref_url = ""

    # When starting a new scene (no prior rendered keyframe in this scene) and a Step 11 Set Plate exists,
    # explicitly lock the room geometry & furnishings to that Step 11 Set Plate.
    if not primary_ref_id and set_img_path is not None:
        continuity_prefix = (
            f"LOCKED STEP 11 SET PLATE ({set_loc_lbl}): Stage this shot INSIDE THE EXACT ROOM/ENVIRONMENT shown in the attached Step 11 set plate. "
            f"Preserve the exact furniture, couch/sofa, blankets/pillows, rug, walls, windows, wooden dividers/spindles, cabinets, TV stand, lighting, and architectural layout from the Step 11 set plate — do NOT invent a different room or generic furniture.\n"
        )

    # 5. Collect character turnaround references within the remaining budget (preserving Set Plate & Spatial slots)
    import plate_audit

    is_cu = plate_audit.is_closeup_shot(target_shot, prompt)
    max_refs = 4
    char_ref_items: list[tuple[Path, str, str, str, bool]] = []
    seen_paths: set[Path] = set()
    spatial_reserved = 1 if primary_ref_png is not None else 0
    set_reserved = 1 if set_img_path is not None else 0
    char_budget = max(1, max_refs - spatial_reserved - set_reserved) if resolved_chars else 0
    t_dir = ctx["pd"] / "assets" / "turnarounds"
    for c in resolved_chars:
        if len(char_ref_items) >= char_budget:
            break
        _, prefer_outfit = match_wardrobe_state(ctx, c, sc_id, heading)
        rp, rurl, rsrc = find_character_visual_ref(ctx, c, prefer_outfit=prefer_outfit)
        if rp and rp.resolve() not in seen_paths:
            use_crop = False
            if is_cu:
                import character_identity
                c_slug = character_identity.safe_char_slug(c)
                crop_p = plate_audit.ensure_face_closeup_crop(rp, t_dir, c_slug)
                if crop_p and crop_p.is_file() and crop_p.resolve() not in seen_paths:
                    rp = crop_p
                    use_crop = True
                    rsrc = f"{rsrc} (face close-up crop)"
                    try:
                        rurl = f"/file/{ctx['slug']}/{crop_p.relative_to(ctx['pd']).as_posix()}"
                    except ValueError:
                        pass
            seen_paths.add(rp.resolve())
            char_ref_items.append((rp, c, rurl, rsrc, use_crop))

    # 6. Assemble final ordered ref_imgs list + explicit reference legend.
    # Ordering rules tuned for FLUX.2 / Kontext / Gemini multi-ref conditioning:
    # - On tight Close-Ups (CU/MCU/ECU): Image 1 = lead character FACE CLOSE-UP CROP (prevents face drift).
    # - On all other shots: Image 1 = Scene Anchor / previous shot (if present), OR Step 11 Set Plate (anchors room!).
    # - Whenever a Step 11 Set Plate exists, it is ALWAYS placed in Slot 1 or Slot 2 (never evicted or buried last).
    ref_imgs: list[Path] = []
    legend_parts: list[str] = []
    char_refs_used: list[dict[str, str]] = []
    set_ref_used: dict[str, str] | None = None

    def _attach_set_plate() -> None:
        nonlocal set_ref_used
        if set_img_path is None or set_ref_used is not None:
            return
        if len(ref_imgs) < max_refs and set_img_path.resolve() not in seen_paths:
            ref_imgs.append(set_img_path)
            seen_paths.add(set_img_path.resolve())
            legend_parts.append(
                f"Image {len(ref_imgs)} = LOCKED STEP 11 SET PLATE ({set_loc_lbl}) — match EXACT room architecture, walls, windows, couch, rug, furniture, props & colors from Image {len(ref_imgs)}"
            )
            set_ref_used = {"name": set_loc_lbl, "url": set_ref_url, "file": set_img_path.name}

    if is_cu and char_ref_items and char_ref_items[0][4]:
        rp0, cname0, rurl0, rsrc0, _ = char_ref_items[0]
        ref_imgs.append(rp0)
        legend_parts.append(
            f"Image {len(ref_imgs)} = {cname0} FACE CLOSE-UP CROP (match EXACT eyes, nose, facial structure, hair & expression)"
        )
        char_refs_used.append({"name": cname0, "url": rurl0, "source": rsrc0})
        remaining_chars = char_ref_items[1:]
    else:
        remaining_chars = char_ref_items

    if primary_ref_png is not None:
        ref_imgs.append(primary_ref_png)
        seen_paths.add(primary_ref_png.resolve())
        role_lbl = "pinned Scene Anchor" if primary_ref_id == anchor_ref else "previous shot"
        legend_parts.append(
            f"Image {len(ref_imgs)} = {role_lbl} {primary_ref_id} (match room geometry, furniture, lighting & continuity)"
        )
        # Put Step 11 Set Plate right behind the anchor/prev shot (Slot 2) so the room stays locked!
        _attach_set_plate()
    else:
        # First shot of a scene (no prev shot): put Step 11 Set Plate FIRST (Slot 1 on wide/medium, Slot 2 on CU)!
        _attach_set_plate()

    for rp, cname, rurl, rsrc, is_crop in remaining_chars:
        if len(ref_imgs) >= max_refs:
            break
        ref_imgs.append(rp)
        role_desc = "FACE CLOSE-UP CROP (match EXACT face, eyes & hair)" if is_crop else "character turnaround (match EXACT face, hair, eyes, proportions, and outfit)"
        legend_parts.append(f"Image {len(ref_imgs)} = {cname} {role_desc}")
        char_refs_used.append({"name": cname, "url": rurl, "source": rsrc})

    # If both a pinned anchor AND a separate previous shot exist and a slot remains, attach the secondary frame too
    secondary_png = anchor_png if primary_ref_png == prev_png else prev_png
    secondary_id = anchor_ref if primary_ref_id == prev_shot_ref else prev_shot_ref
    if len(ref_imgs) < max_refs and secondary_png is not None and secondary_png.resolve() not in seen_paths:
        ref_imgs.append(secondary_png)
        seen_paths.add(secondary_png.resolve())
        sec_lbl = "pinned Scene Anchor" if secondary_id == anchor_ref else "previous shot"
        legend_parts.append(f"Image {len(ref_imgs)} = {sec_lbl} {secondary_id}")

    ref_legend = ""
    if legend_parts:
        ref_legend = "ATTACHED VISUAL REFERENCES (STRICT IDENTITY & CONTINUITY LOCK): " + "; ".join(legend_parts) + ".\n"

    suggested_angle_move = ""
    if continuity_mode == "scene_cut" and primary_ref_png is not None:
        suggested_angle_move = map_shot_to_angles_move(target_shot, shots_by_id.get(primary_ref_id), prompt)

    return {
        "ref_imgs": ref_imgs,
        "init_image": init_image,
        "init_strength": init_strength,
        "auto_strength": auto_strength,
        "scene_seed": scene_seed,
        "ref_legend": ref_legend,
        "continuity_prefix": continuity_prefix,
        "continuity_mode": continuity_mode,
        "suggested_angle_move": suggested_angle_move,
        "prev_shot_ref": prev_shot_ref,
        "anchor_shot_ref": anchor_ref,
        "primary_ref_id": primary_ref_id,
        "char_refs_used": char_refs_used,
        "set_ref_used": set_ref_used,
        "resolved_characters": resolved_chars,
        "style_negatives": ctx["style_negatives"],
    }
