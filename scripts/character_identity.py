"""Character identity control for turnarounds, costume changes, and cast distinctness.

Enforces three core rules across Step 10 (Turnarounds) and Step 17 (Keyframes):
1. Same canonical character = same face/body regardless of outfit, title, or scene state
   (e.g. ``TOMMY``, ``CAPTAIN TOMMY``, ``TOMMY (CRAYON-MARKED)`` all share identity ``tommy``;
   ``JUDAH`` and ``FIRST OFFICER JUDAH`` share identity ``judah``).
2. Whenever a generated picture already exists for a character (any outfit or variant),
   use it as the visual reference for subsequent costume/scene changes.
3. Two characters with different canonical names must look visibly distinct UNLESS
   their description explicitly states they are twins.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

# Parenthetical / bracketed scene or state modifiers: "TOMMY (CRAYON-MARKED)", "DAD [OFFSTAGE]"
_PAREN_MOD_RE = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]\s*")
# Trailing dash / colon state suffix: "TOMMY - SPACESUIT", "ALICE: BATTLE ARMOR"
_SUFFIX_STATE_RE = re.compile(r"\s+(?:[-–—]|::?)\s+.+$")
# Explicit twin mention in character descriptions
_TWIN_WORD_RE = re.compile(r"\b(?:identical\s+|fraternal\s+)?twins?\b", re.IGNORECASE)

# Role, rank, costume, or age prefixes that describe a state/outfit of the same character
# (intentionally excludes gendered family/royalty nouns like mr/mrs/king/queen/prince/princess/mom/dad)
_MULTI_WORD_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("first", "officer"),
    ("second", "officer"),
    ("chief", "officer"),
    ("chief", "engineer"),
    ("science", "officer"),
    ("special", "agent"),
    ("secret", "agent"),
    ("space", "captain"),
    ("starship", "captain"),
    ("vice", "president"),
    ("grand", "wizard"),
    ("high", "priest"),
    ("little", "captain"),
)

_SINGLE_WORD_PREFIXES: frozenset[str] = frozenset({
    "captain", "capt", "commander", "cmdr", "officer", "lieutenant", "lt",
    "major", "general", "gen", "admiral", "sergeant", "sgt", "corporal", "cpl",
    "private", "pvt", "colonel", "col", "chief", "pilot", "astronaut",
    "doctor", "dr", "professor", "prof", "chef", "coach", "detective", "agent",
    "inspector", "sheriff", "deputy", "mayor", "judge", "senator", "president",
    "pirate", "wizard", "knight", "ninja", "super", "space", "cyber", "mecha",
    "young", "older", "old", "elder", "little", "baby", "teen", "teenage", "adult",
    "future", "past", "evil", "dark", "shadow", "ghost", "robot", "royal",
})

# Nouns indicating a distinct person rather than a costume/rank of another named person
_DISTINCT_RELATION_WORDS: frozenset[str] = frozenset({
    "mom", "mother", "dad", "father", "brother", "sister", "son", "daughter",
    "uncle", "aunt", "grandpa", "grandfather", "grandma", "grandmother",
    "cousin", "wife", "husband", "mr", "mrs", "ms", "miss", "king", "queen",
    "prince", "princess", "lord", "lady", "jr", "junior", "sr", "senior", "ii", "iii",
})


def safe_char_slug(name: str) -> str:
    """Filesystem-safe lowercase slug matching Studio's turnaround filenames."""
    return "".join(c if c.isalnum() else "_" for c in str(name or "").lower()).strip("_") or "char"


def _clean_tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t]


def load_identity_overrides(project_dir: Path) -> dict[str, str]:
    """Load optional manual character identity links from `<project>/character_identity.json`."""
    p = project_dir / "character_identity.json"
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8")) or {}
        links = data.get("links") if isinstance(data, dict) else {}
        if isinstance(links, dict):
            return {str(k).strip().lower(): str(v).strip() for k, v in links.items() if str(k).strip() and str(v).strip()}
    except Exception:
        return {}
    return {}


def save_identity_override(project_dir: Path, char_name: str, target_base: str) -> dict[str, str]:
    """Persist a manual identity link (`""` resets to Auto, `"__self__"` forces independent)."""
    p = project_dir / "character_identity.json"
    links = load_identity_overrides(project_dir)
    key = str(char_name or "").strip().lower()
    val = str(target_base or "").strip()
    if key:
        if not val or val.lower() == "auto":
            links.pop(key, None)
        else:
            links[key] = val
    project_dir.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"links": links}, indent=2, ensure_ascii=False), encoding="utf-8")
    return links


def canonical_character_key(
    name: str,
    *,
    known_names: list[str] | tuple[str, ...] | None = None,
    overrides: dict[str, str] | None = None,
) -> str:
    """Resolve a character name to its canonical identity key.

    Examples:
        ``"TOMMY"``, ``"CAPTAIN TOMMY"``, ``"TOMMY (CRAYON-MARKED)"`` -> ``"tommy"``
        ``"JUDAH"``, ``"FIRST OFFICER JUDAH"`` -> ``"judah"``
        ``"Tommy's Mom"`` -> ``"tommy_s_mom"`` (does NOT collapse into ``"tommy"``)
    """
    raw = str(name or "").strip()
    if not raw:
        return "char"

    low = raw.lower()
    if overrides and low in overrides:
        ov = overrides[low].strip()
        if ov == "__self__":
            return safe_char_slug(raw)
        if ov and ov.lower() != low:
            # Resolve one hop without risking cycles
            next_ov = {k: v for k, v in overrides.items() if k != low}
            return canonical_character_key(ov, known_names=known_names, overrides=next_ov)

    # Possessives like "Tommy's Mom" or "Judah's Toy" refer to a distinct entity
    if "'s " in low or "\u2019s " in low:
        return safe_char_slug(raw)

    # Strip parenthetical/bracketed scene modifiers and trailing dash/colon state labels
    stripped = _PAREN_MOD_RE.sub(" ", raw).strip()
    stripped = _SUFFIX_STATE_RE.sub("", stripped).strip()
    tokens = _clean_tokens(stripped)
    if not tokens:
        return safe_char_slug(raw)

    # Keep relational / generational names distinct (e.g. "Mr. Smith" vs "Mrs. Smith", "Tommy Jr")
    if tokens[0] in _DISTINCT_RELATION_WORDS or (len(tokens) > 1 and tokens[-1] in _DISTINCT_RELATION_WORDS):
        return "_".join(tokens)

    # Strip leading multi-word and single-word role/costume/rank prefixes while preserving >=1 name token
    changed = True
    while changed and len(tokens) > 1:
        changed = False
        for mp in _MULTI_WORD_PREFIXES:
            n = len(mp)
            if len(tokens) > n and tuple(tokens[:n]) == mp:
                tokens = tokens[n:]
                changed = True
                break
        if changed:
            continue
        if len(tokens) > 1 and tokens[0] in _SINGLE_WORD_PREFIXES:
            tokens = tokens[1:]
            changed = True

    # If the remaining phrase ends with a known standalone cast member's base name and all
    # leading words are non-relational modifiers (e.g. "STARSHIP CAPTAIN TOMMY" with "TOMMY" in cast),
    # collapse to that known base name.
    if known_names and len(tokens) > 1:
        known_bases: set[str] = set()
        for kn in known_names:
            k_raw = str(kn or "").strip()
            if not k_raw or k_raw.lower() == low:
                continue
            if "'s " in k_raw.lower() or "\u2019s " in k_raw.lower():
                continue
            k_toks = _clean_tokens(_SUFFIX_STATE_RE.sub("", _PAREN_MOD_RE.sub(" ", k_raw)).strip())
            if len(k_toks) == 1 and k_toks[0] not in _DISTINCT_RELATION_WORDS and k_toks[0] not in _SINGLE_WORD_PREFIXES:
                known_bases.add(k_toks[0])
        if tokens[-1] in known_bases and not any(t in _DISTINCT_RELATION_WORDS for t in tokens[:-1]):
            tokens = [tokens[-1]]

    return "_".join(tokens) or safe_char_slug(raw)


def same_character(
    name_a: str,
    name_b: str,
    *,
    known_names: list[str] | tuple[str, ...] | None = None,
    overrides: dict[str, str] | None = None,
) -> bool:
    """Return True if two cast entries represent the exact same character."""
    ka = canonical_character_key(name_a, known_names=known_names, overrides=overrides)
    kb = canonical_character_key(name_b, known_names=known_names, overrides=overrides)
    return bool(ka and kb and ka == kb)


def explicit_twin_relationship(
    name_a: str,
    desc_a: str,
    name_b: str,
    desc_b: str,
) -> bool:
    """Return True ONLY when character descriptions explicitly declare these two characters are twins."""
    da = str(desc_a or "").strip()
    db = str(desc_b or "").strip()
    a_has_twin = bool(_TWIN_WORD_RE.search(da))
    b_has_twin = bool(_TWIN_WORD_RE.search(db))
    if not (a_has_twin or b_has_twin):
        return False

    # Base name tokens for cross-reference matching ("twin brother of Alex", "Maya's identical twin")
    a_key = canonical_character_key(name_a).replace("_", " ").strip()
    b_key = canonical_character_key(name_b).replace("_", " ").strip()
    da_low = da.lower()
    db_low = db.lower()

    if a_has_twin and b_key and re.search(rf"\b{re.escape(b_key)}\b", da_low):
        return True
    if b_has_twin and a_key and re.search(rf"\b{re.escape(a_key)}\b", db_low):
        return True
    # Both characters explicitly state they are twins in their own descriptions
    return bool(a_has_twin and b_has_twin)


def _iter_turnaround_candidates_for_slug(t_dir: Path, slug: str, prefer_outfit: str = "") -> list[Path]:
    """Yield turnaround PNGs for one filename slug, prioritizing Front Views first."""
    ordered: list[Path] = []
    if prefer_outfit and prefer_outfit != "default":
        for v in ("front", "three_quarter", "profile"):
            ordered.append(t_dir / f"{slug}_{prefer_outfit}_{v}.png")
    for cand in (
        f"{slug}_front.png",
        f"{slug}_outfit1_front.png",
        f"{slug}_three_quarter.png",
        f"{slug}_outfit1_three_quarter.png",
        f"{slug}_profile.png",
        f"{slug}_outfit1_profile.png",
    ):
        ordered.append(t_dir / cand)
    if t_dir.is_dir():
        # Prefer any other outfit's front views before 3/4 or profile
        all_matches = sorted(t_dir.glob(f"{slug}_*.png"))
        ordered.extend(p for p in all_matches if p.name.endswith("_front.png"))
        ordered.extend(p for p in all_matches if not p.name.endswith("_front.png"))
    return ordered


def find_canonical_character_refs(
    t_dir: Path,
    char_name: str,
    *,
    prefer_outfit: str = "",
    exclude_path: Path | None = None,
    known_names: list[str] | tuple[str, ...] | None = None,
    overrides: dict[str, str] | None = None,
    limit: int = 3,
) -> list[tuple[Path, str]]:
    """Find existing generated turnaround PNGs for `char_name` and all same-identity variants.

    Returns ``[(path, source_character_name), ...]`` prioritized as:
    1. Preferred outfit of `char_name` (front first)
    2. Other outfits of `char_name` (front first)
    3. Canonical base character's front view (e.g. ``TOMMY`` for ``CAPTAIN TOMMY``)
    4. Any same-canonical-identity variant's front view (e.g. ``CAPTAIN TOMMY`` for ``TOMMY``)
    5. Any remaining turnaround views for the same canonical identity.
    """
    if not t_dir.is_dir():
        return []
    names = list(known_names or [])
    if char_name and char_name not in names:
        names.append(char_name)

    canon = canonical_character_key(char_name, known_names=names, overrides=overrides)
    self_slug = safe_char_slug(char_name)
    ex_res = exclude_path.resolve() if exclude_path else None

    found: list[tuple[Path, str]] = []
    seen: set[Path] = set()

    def _try(p: Path, label: str) -> None:
        if len(found) >= limit or not p.is_file():
            return
        try:
            rp = p.resolve()
            if (ex_res and rp == ex_res) or rp in seen or p.stat().st_size <= 100:
                return
            seen.add(rp)
            found.append((p, label))
        except OSError:
            pass

    # 1 & 2. Exact character name (preferred outfit then base/other outfits)
    for p in _iter_turnaround_candidates_for_slug(t_dir, self_slug, prefer_outfit=prefer_outfit):
        _try(p, char_name)

    # 3 & 4. Same canonical identity across other cast names (prefer exact base slug first, then variants)
    sibling_entries: list[tuple[int, str, str]] = []
    seen_slugs: set[str] = {self_slug}
    for kn in names:
        kslug = safe_char_slug(kn)
        if kslug in seen_slugs:
            continue
        if canonical_character_key(kn, known_names=names, overrides=overrides) == canon:
            seen_slugs.add(kslug)
            prio = 0 if kslug == canon else 1
            sibling_entries.append((prio, kslug, kn))

    # Also check canonical base slug on disk even if not listed in known_names
    if canon not in seen_slugs:
        seen_slugs.add(canon)
        sibling_entries.append((0, canon, canon.replace("_", " ").upper()))

    sibling_entries.sort(key=lambda x: (x[0], x[1]))

    # Pass A: Front views across all same-identity variants
    for _prio, slug, label in sibling_entries:
        for p in _iter_turnaround_candidates_for_slug(t_dir, slug):
            if p.name.endswith("_front.png"):
                _try(p, label)

    # Pass B: Scan any turnaround file on disk whose stem prefix resolves to the same canonical key
    # (catches files like `first_officer_judah_front.png` even when `known_names` wasn't passed!)
    for p in sorted(t_dir.glob("*_front.png")):
        if len(found) >= limit:
            break
        stem = p.name[: -len("_front.png")]
        stem_no_outfit = re.sub(r"_outfit\d+$", "", stem)
        inferred_name = stem_no_outfit.replace("__", " ").replace("_", " ").strip()
        if inferred_name and canonical_character_key(inferred_name, known_names=names, overrides=overrides) == canon:
            _try(p, inferred_name.upper())

    # Pass C: Non-front views of same-identity variants as last resort
    for _prio, slug, label in sibling_entries:
        for p in _iter_turnaround_candidates_for_slug(t_dir, slug):
            if not p.name.endswith("_front.png"):
                _try(p, label)

    return found


def build_cast_identity_map(
    characters: list[dict[str, Any]],
    t_dir: Path,
    *,
    overrides: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Compute canonical identity, linked variants, primary reference, and twin status for every character."""
    names = [str(c.get("name") or "").strip() for c in characters if str(c.get("name") or "").strip()]
    groups: dict[str, list[dict[str, Any]]] = {}
    for c in characters:
        nm = str(c.get("name") or "").strip()
        if not nm:
            continue
        ckey = canonical_character_key(nm, known_names=names, overrides=overrides)
        groups.setdefault(ckey, []).append(c)

    result: dict[str, dict[str, Any]] = {}
    for c in characters:
        nm = str(c.get("name") or "").strip()
        if not nm:
            continue
        desc = str(c.get("desc") or "").strip()
        ckey = canonical_character_key(nm, known_names=names, overrides=overrides)
        siblings = [str(s.get("name") or "").strip() for s in groups.get(ckey, []) if str(s.get("name") or "").strip().lower() != nm.lower()]

        # Find the primary existing reference image across this canonical group
        refs = find_canonical_character_refs(t_dir, nm, known_names=names, overrides=overrides, limit=1)
        ref_path, ref_src = refs[0] if refs else (None, "")

        # Detect explicit twin relationships with other distinct canonical characters
        twin_with: list[str] = []
        for other in characters:
            onm = str(other.get("name") or "").strip()
            if not onm:
                continue
            okey = canonical_character_key(onm, known_names=names, overrides=overrides)
            if okey == ckey:
                continue
            if explicit_twin_relationship(nm, desc, onm, str(other.get("desc") or "")):
                twin_with.append(onm)

        ov_val = (overrides or {}).get(nm.lower(), "")
        result[nm.lower()] = {
            "canonical_id": ckey,
            "canonical_label": ckey.replace("_", " ").upper(),
            "linked_variants": siblings,
            "has_canonical_ref": bool(ref_path is not None),
            "ref_source_name": ref_src,
            "ref_source_file": ref_path.name if ref_path else "",
            "is_twin": bool(twin_with),
            "twin_with": twin_with,
            "override": ov_val,
        }
    return result


# Curated distinctive facial/silhouette archetypes used ONLY to differentiate unspecified traits
# between non-twin distinct characters so diffusion models don't collapse onto one default face.
_FACE_SHAPES: tuple[str, ...] = (
    "oval face with gentle jawline",
    "square jaw with broader cheekbones",
    "heart-shaped face with pointed chin",
    "long narrow face with high forehead",
    "soft diamond-shaped face with defined cheekbones",
    "compact round face with full cheeks",
)
_BROW_EYE_STYLES: tuple[str, ...] = (
    "wide almond-shaped eyes under slim arched eyebrows",
    "deep-set lively eyes under thick expressive eyebrows",
    "bright narrow-set eyes under straight angled eyebrows",
    "large expressive eyes with long lashes and soft curved brows",
    "warm slightly downturned eyes under bushy brows",
    "alert wide-set eyes under high delicate eyebrows",
)
_NOSE_STYLES: tuple[str, ...] = (
    "small upturned button nose",
    "broad rounded nose",
    "long straight narrow nose",
    "short wide nose with soft tip",
    "prominent sculpted bridge nose",
    "petite gently sloped nose",
)
_HAIR_STYLES: tuple[str, ...] = (
    "neatly side-parted smooth hair",
    "tightly coiled voluminous curly hair",
    "wavy tousled mid-length hair",
    "short cropped textured hair",
    "straight sleek hair with clean bangs",
    "loose wavy hair swept back from the forehead",
)

_NON_HUMAN_HINTS = re.compile(
    r"\b(?:dog|cat|labrador|puppy|kitten|doll|rag doll|action figure|plastic soldier|toy|robot|bear|rabbit|bunny|fox|wolf|dragon|bird|owl|alien|monster|creature)\b",
    re.IGNORECASE,
)


def build_distinct_character_cues(
    char_name: str,
    char_desc: str,
    other_non_twin_chars: list[dict[str, str]],
    *,
    attempt: int = 0,
) -> tuple[str, str]:
    """Build positive & negative prompt cues ensuring a non-twin character looks uniquely different.

    Only fills in facial geometry traits NOT already specified by `char_desc`, so user-defined
    traits are always respected while avoiding generic "same-face" collapse across the cast.
    """
    neg = "twin, identical face, clone, duplicate character, lookalike"
    if not other_non_twin_chars:
        return "", neg

    desc_low = str(char_desc or "").lower()
    # Non-human characters (dogs, rag dolls, action figures) already have species/material distinctness;
    # keep cues lightweight so we don't inject human nose/brow terms onto a Labrador or toy.
    if _NON_HUMAN_HINTS.search(desc_low):
        cues = "distinctive individual silhouette, unique markings, and unmistakable character proportions"
        if attempt > 0:
            cues = "dramatically distinct silhouette, unique posture, and clearly individual facial structure"
        return cues, neg

    # Deterministic per-character index shifted on retry attempts, avoiding indices used by earlier cast members
    seed_int = int.from_bytes(hashlib.sha256(f"{char_name.lower()}:{attempt}".encode()).digest()[:4], "little")
    used_face = {
        int.from_bytes(hashlib.sha256(f"{str(o.get('name', '')).lower()}:0".encode()).digest()[:4], "little") % len(_FACE_SHAPES)
        for o in other_non_twin_chars
    }
    f_idx = seed_int % len(_FACE_SHAPES)
    for offset in range(len(_FACE_SHAPES)):
        cand = (f_idx + offset) % len(_FACE_SHAPES)
        if cand not in used_face:
            f_idx = cand
            break

    be_idx = (seed_int // 7 + attempt * 2) % len(_BROW_EYE_STYLES)
    n_idx = (seed_int // 13 + attempt * 3) % len(_NOSE_STYLES)
    h_idx = (seed_int // 19 + attempt * 5) % len(_HAIR_STYLES)

    additions: list[str] = []
    if not re.search(r"\b(?:round|oval|square|heart|long|narrow|angular|thin)\s+(?:face|jaw|chin)\b", desc_low):
        additions.append(_FACE_SHAPES[f_idx])
    if not re.search(r"\b(?:almond|wide-set|deep-set|narrow|slanted)\s+eyes\b|\beyebrows?\b|\bbrows?\b", desc_low):
        additions.append(_BROW_EYE_STYLES[be_idx])
    if not re.search(r"\bnose\b", desc_low):
        additions.append(_NOSE_STYLES[n_idx])
    if not re.search(r"\b(?:curly|wavy|straight|braid|bun|ponytail|messy|cropped|bald|shaved|parted|tied back|short|long)\b.*\bhair\b|\bhair\b.*\b(?:curly|wavy|straight|braid|bun|ponytail|messy|cropped|parted|tied back)\b", desc_low):
        additions.append(_HAIR_STYLES[h_idx])

    if attempt > 0:
        additions.append("unmistakably unique individual face structure and distinct proportions")
    elif not additions:
        additions.append("distinctive individual facial proportions and unique silhouette")

    return ", ".join(additions), neg


def _extract_head_crop(img_path: Path) -> Any:
    """Isolate foreground character and crop upper-center head/face region as 96x96 BGR array."""
    import cv2
    import numpy as np

    arr = np.fromfile(str(img_path), dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        return None

    h, w = img.shape[:2]
    # Estimate uniform studio backdrop color from the 4 corners
    corners = np.concatenate([
        img[: max(4, h // 20), : max(4, w // 20)].reshape(-1, 3),
        img[: max(4, h // 20), -max(4, w // 20) :].reshape(-1, 3),
        img[-max(4, h // 20) :, : max(4, w // 20)].reshape(-1, 3),
        img[-max(4, h // 20) :, -max(4, w // 20) :].reshape(-1, 3),
    ], axis=0)
    bg = np.median(corners, axis=0)
    dist = np.linalg.norm(img.astype(np.float32) - bg.astype(np.float32), axis=2)
    mask = dist > 22.0
    ys, xs = np.where(mask)
    if len(ys) < 100:
        y0, y1, x0, x1 = int(h * 0.08), int(h * 0.45), int(w * 0.25), int(w * 0.75)
    else:
        fy0, fy1 = int(ys.min()), int(ys.max())
        fx0, fx1 = int(xs.min()), int(xs.max())
        fh = max(16, fy1 - fy0)
        fw = max(16, fx1 - fx0)
        # Head/face occupies roughly the top 42% of a full-body character turnaround
        y0 = fy0
        y1 = min(h, fy0 + max(16, int(fh * 0.42)))
        cx = (fx0 + fx1) // 2
        half_w = max(16, int(min(fw, fh * 0.42) * 0.65))
        x0 = max(0, cx - half_w)
        x1 = min(w, cx + half_w)

    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    return cv2.resize(crop, (96, 96), interpolation=cv2.INTER_AREA)


def measure_head_similarity(img_a: Path, img_b: Path) -> float:
    """Measure head/face visual similarity in [0.0, 1.0] between two character Front View PNGs."""
    try:
        import cv2
        import numpy as np
    except Exception:
        return 0.0

    crop_a = _extract_head_crop(img_a)
    crop_b = _extract_head_crop(img_b)
    if crop_a is None or crop_b is None:
        return 0.0

    # 1. HSV color distribution correlation (skin tone + hair color + eye/hat palette)
    hsv_a = cv2.cvtColor(crop_a, cv2.COLOR_BGR2HSV)
    hsv_b = cv2.cvtColor(crop_b, cv2.COLOR_BGR2HSV)
    hist_a = cv2.calcHist([hsv_a], [0, 1], None, [24, 16], [0, 180, 0, 256])
    hist_b = cv2.calcHist([hsv_b], [0, 1], None, [24, 16], [0, 180, 0, 256])
    cv2.normalize(hist_a, hist_a, 0, 1, cv2.NORM_MINMAX)
    cv2.normalize(hist_b, hist_b, 0, 1, cv2.NORM_MINMAX)
    color_sim = float(max(0.0, cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL)))

    # 2. Structural facial-feature edge similarity (Sobel magnitude cosine)
    gray_a = cv2.cvtColor(crop_a, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gray_b = cv2.cvtColor(crop_b, cv2.COLOR_BGR2GRAY).astype(np.float32)
    edge_a = np.hypot(cv2.Sobel(gray_a, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(gray_a, cv2.CV_32F, 0, 1, ksize=3)).ravel()
    edge_b = np.hypot(cv2.Sobel(gray_b, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(gray_b, cv2.CV_32F, 0, 1, ksize=3)).ravel()
    na, nb = float(np.linalg.norm(edge_a)), float(np.linalg.norm(edge_b))
    struct_sim = float(np.dot(edge_a, edge_b) / (na * nb)) if (na > 1e-6 and nb > 1e-6) else 0.0

    # 3. Normalized luminance correlation on inner face patch
    inner_a = gray_a[16:80, 16:80].ravel()
    inner_b = gray_b[16:80, 16:80].ravel()
    inner_a = inner_a - float(inner_a.mean())
    inner_b = inner_b - float(inner_b.mean())
    la, lb = float(np.linalg.norm(inner_a)), float(np.linalg.norm(inner_b))
    luma_sim = float(max(0.0, np.dot(inner_a, inner_b) / (la * lb))) if (la > 1e-6 and lb > 1e-6) else 0.0

    score = 0.40 * color_sim + 0.35 * struct_sim + 0.25 * luma_sim
    return round(max(0.0, min(1.0, score)), 4)


def check_non_twin_distinctness(
    candidate_png: Path,
    other_front_pngs: list[tuple[str, Path]],
    *,
    threshold: float = 0.86,
) -> dict[str, Any]:
    """Compare a candidate Front View against existing non-twin cast Front Views."""
    max_sim = 0.0
    closest = ""
    for other_name, other_path in other_front_pngs:
        if not other_path.is_file() or other_path.resolve() == candidate_png.resolve():
            continue
        sim = measure_head_similarity(candidate_png, other_path)
        if sim > max_sim:
            max_sim = sim
            closest = other_name
    return {
        "distinct": max_sim < threshold,
        "max_similarity": round(max_sim, 4),
        "closest_character": closest,
        "threshold": threshold,
    }
