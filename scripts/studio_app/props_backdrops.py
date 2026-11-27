"""Step 07 Visual Props & Dynamic Backdrops extraction, persistence, and Continuity Book synchronization.

Static Sets (fixed rooms & permanent environments) live in Step 11.
Dynamic Props (hand props, hero objects, furniture props that move or change state like a cardboard box
or wooden toybox) and Dynamic Backdrops (planets, fly-bys, viewscreen vistas, skies like Moon, Mars,
Saturn, Titan, Enceladus, Mimas, Asteroid Field, Earth Orbit, Re-Entry Sky) live in Step 07.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_LEADING_ARTICLES_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)
_STYLE_WORDS_RE = re.compile(
    r"(?i)\b(photo-?realistic|photoreal|hyper-?realistic|photograph\w*|snapshot|camera\s+photo|"
    r"claymation|plasticine|3d|cgi|pixar|anime|manga|cartoon\w*|watercolou?r|oil[- ]painting|illustrat\w*|render\w*|cel[- ]shad\w*)\b"
)

_BACKDROP_CUES_RE = re.compile(
    r"(?i)\b(space|moon|lunar|mars|martian|saturn|titan|enceladus|mimas|rhea|jupiter|venus|mercury|neptune|uranus|pluto|"
    r"earth\s+orbit|orbit|asteroid|comet|nebula|starfield|galaxy|cosmos|planet\w*|rings\s+of\s+saturn|viewscreen|"
    r"re-?entry|atmosphere|stratosphere|sky|clouds|horizon|fly-?by|exterior\s+space|deep\s+space|starscape)\b"
)

# Common physical story props & dynamic scenic backdrops scanned from screenplay text when not yet listed in Continuity Book
_SCRIPT_PROP_PATTERNS: list[tuple[str, str, str, str]] = [
    # (canonical_name, kind, regex_pattern, default_prompt)
    (
        "Cardboard Box (Unfolded)",
        "prop",
        r"\b(?:cardboard\s+box|large\s+box|shipping\s+box|big\s+box|appliance\s+box)\b",
        "Large sturdy corrugated tan-brown cardboard box with four open top flaps, natural kraft paper grain, visible folded creases and packing tape seams, realistic child-sized interior cabin proportions, clean neutral framing with no characters",
    ),
    (
        "Cardboard Box (Flat / Folded)",
        "prop",
        r"\b(?:flat\s+cardboard|flattened\s+box|folded\s+cardboard|flat\s+box)\b",
        "Flattened folded corrugated tan-brown cardboard shipping box lying neatly with creased panels and flaps, natural kraft paper texture, clean neutral framing with no characters",
    ),
    (
        "Wooden Toybox",
        "prop",
        r"\b(?:toy\s*box|wooden\s+chest|toy\s+chest)\b",
        "Classic sturdy children's wooden toybox chest with warm honey-oak wood grain, hinged top lid, smooth beveled edges, realistic child-waist height, clean neutral framing with no characters",
    ),
    (
        "Stainless Steel Dog Bowl",
        "prop",
        r"\b(?:dog\s+bowl|steel\s+bowl|food\s+bowl|water\s+bowl|kibble\s+bowl)\b",
        "Small brushed stainless steel pet dog bowl (~8 inches wide, ~3 inches tall) with rolled rim and slight floor reflection, clean neutral framing with no characters",
    ),
    (
        "Space Picture Book",
        "prop",
        r"\b(?:picture\s+book|space\s+book|astronomy\s+book|storybook|open\s+book)\b",
        "Hardcover children's illustrated space picture book with vibrant ringed-planet cover art, thick matte pages, realistic hand-held proportions, clean neutral framing with no characters",
    ),
    (
        "Cheese Squeaky Toy",
        "prop",
        r"\b(?:cheese\s+toy|squeaky\s+cheese|cheesy\s+toy|plush\s+cheese|squeaky\s+toy)\b",
        "Small hand-sized soft yellow Swiss-cheese wedge dog squeaky toy with recessed round holes and stitched plush/rubber texture, clean neutral framing with no characters",
    ),
    (
        "Ceramic Tea Mug",
        "prop",
        r"\b(?:tea\s+mug|coffee\s+mug|white\s+mug|chipped\s+mug|ceramic\s+mug|mug)\b",
        "Small palm-sized white glazed ceramic mug (~4 inches tall) with curved handle and subtle everyday wear, clean neutral framing with no characters",
    ),
    (
        "TV Remote Control",
        "prop",
        r"\b(?:tv\s+remote|remote\s+control)\b",
        "Compact matte-black television remote control with rubberized directional pad and colorful channel buttons, realistic hand-held size, clean neutral framing with no characters",
    ),
    (
        "Newspaper",
        "prop",
        r"\bnewspaper\b",
        "Folded classic broadsheet newspaper with crisp newsprint columns and soft paper creases, realistic hand-held size, clean neutral framing with no characters",
    ),
    (
        "Toy Spacesuit Helmet",
        "prop",
        r"\b(?:space\s+helmet|astronaut\s+helmet|helmet)\b",
        "Child-sized white astronaut space helmet with clear curved visor, subtle colored trim stripes, and padded interior rim, clean neutral framing with no characters",
    ),
    (
        "Control Panel & Dashboard",
        "prop",
        r"\b(?:control\s+panel|dashboard|switches\s+and\s+dials|instrument\s+panel)\b",
        "Imaginative glowing spacecraft cockpit control console with tactile colored toggle switches, round illuminated radar dials, and soft star-chart readouts, clean framing with no characters",
    ),
]

_SCRIPT_BACKDROP_PATTERNS: list[tuple[str, str, str]] = [
    # (canonical_name, regex_pattern, default_prompt)
    (
        "Earth Orbit",
        r"\b(?:earth\s+orbit|orbiting\s+earth|blue\s+marble|earth\s+below|from\s+orbit)\b",
        "Wide cinematic deep-space scenic backdrop of curved blue Earth from low orbit with swirling white cloud bands, luminous cyan atmospheric horizon glow, and crisp starfield against velvety dark space, no people, no foreground characters",
    ),
    (
        "The Moon",
        r"\b(?:the\s+moon|moon\s+fly-?by|lunar\s+surface|craters?\s+of\s+the\s+moon|past\s+the\s+moon)\b",
        "Wide cinematic deep-space scenic backdrop of the pale silver-gray cratered Moon glowing brightly against a rich starry cosmos with crisp terminator shadows across impact basins, no people, no foreground characters",
    ),
    (
        "Mars",
        r"\b(?:mars|red\s+planet|martian)\b",
        "Wide cinematic deep-space scenic backdrop of rusty terracotta-red Mars with dusty canyons, pale polar ice cap, thin amber atmospheric rim light, and crisp distant stars, no people, no foreground characters",
    ),
    (
        "Asteroid Field",
        r"\b(?:asteroid\s+field|asteroid\s+belt|tumbling\s+asteroids|space\s+rocks)\b",
        "Wide cinematic deep-space scenic backdrop of sunlit tumbling rocky gray-brown asteroids drifting across a vast dark starfield with warm distant sunlight rim-lighting each craggy boulder, no people, no foreground characters",
    ),
    (
        "Saturn & Rings",
        r"\b(?:saturn|saturn(?:'s)?\s+rings|ringed\s+planet)\b",
        "Wide cinematic deep-space scenic backdrop of majestic golden-butterscotch Saturn banded with creamy atmospheric stripes and sweeping translucent icy-gold concentric rings arcing across deep starry space, no people, no foreground characters",
    ),
    (
        "Titan",
        r"\b(?:titan)\b",
        "Wide cinematic deep-space scenic backdrop of Saturn's largest moon Titan glowing in warm amber-orange atmospheric haze with golden hydrocarbon clouds and Saturn's distant rings gleaming behind it in starry space, no people, no foreground characters",
    ),
    (
        "Enceladus",
        r"\b(?:enceladus)\b",
        "Wide cinematic deep-space scenic backdrop of Saturn's brilliant snow-white icy moon Enceladus etched with pale blue tectonic tiger-stripe fissures and sparkling sunlit ice-geyser plumes spraying into starry space, no people, no foreground characters",
    ),
    (
        "Mimas",
        r"\b(?:mimas)\b",
        "Wide cinematic deep-space scenic backdrop of Saturn's small heavily cratered silver-gray moon Mimas featuring its giant unmistakable Herschel impact crater catching dramatic sunlight against starry deep space, no people, no foreground characters",
    ),
    (
        "Re-Entry Sky",
        r"\b(?:re-?entry|atmospheric\s+entry|descending\s+through\s+clouds|golden\s+sky)\b",
        "Wide cinematic atmospheric sky backdrop during glowing warm-amber re-entry descending above billowing sunlit white clouds and soft blue sky horizon below, no people, no foreground characters",
    ),
]


def safe_item_slug(name: str) -> str:
    s = _NON_ALNUM_RE.sub("_", str(name or "").strip().lower()).strip("_")
    return s or "item"


def norm_item_key(name: str) -> str:
    s = _NON_ALNUM_RE.sub(" ", str(name or "").lower()).strip()
    s = re.sub(r"^(?:space|sky|ext|int)\s+", "", s).strip()
    return _LEADING_ARTICLES_RE.sub("", s).strip()


def classify_kind(name: str, hint: str = "") -> str:
    h = str(hint or "").strip().lower()
    if h in ("prop", "backdrop"):
        return h
    if _BACKDROP_CUES_RE.search(str(name or "")):
        return "backdrop"
    return "prop"


def props_backdrops_path(pd: Path) -> Path:
    return pd / "props_backdrops.json"


def _clean_prompt_text(text: str) -> str:
    cleaned = _STYLE_WORDS_RE.sub("", str(text or ""))
    return re.sub(r"\s{2,}", " ", cleaned).strip(" ,;:-")


def _default_prompt_for(name: str, kind: str, *, home_room: str = "") -> str:
    clean_name = re.sub(r"^(?:SPACE|SKY|EXT\.|INT\.)\s*[:\-]?\s*", "", str(name or "").strip(), flags=re.IGNORECASE).strip()
    if kind == "backdrop":
        # Check built-in rich backdrop templates first
        for cname, pat, dprompt in _SCRIPT_BACKDROP_PATTERNS:
            if re.search(pat, clean_name, re.IGNORECASE) or norm_item_key(cname) == norm_item_key(clean_name):
                return dprompt
        return (
            f"Wide cinematic scenic backdrop plate of {clean_name or name}, rich atmospheric depth, crisp natural lighting and clear silhouette, "
            "clean empty vista with no people or foreground characters"
        )
    # Check built-in rich prop templates first
    for cname, _k, pat, dprompt in _SCRIPT_PROP_PATTERNS:
        if re.search(pat, clean_name, re.IGNORECASE) or norm_item_key(cname) == norm_item_key(clean_name):
            return dprompt
    room_bit = f" typically found in {home_room}," if home_room else ""
    return (
        f"Hero story prop: {clean_name or name},{room_bit} accurate everyday materials, clear shape and color details, "
        "realistic physical scale, clean neutral framing with no people or characters"
    )


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def _load_continuity_book_doc(pd: Path, slug: str) -> dict[str, Any]:
    import continuity_book

    for p in (continuity_book.continuity_file(pd), pd / f"{slug}.json", pd / "continuity.json"):
        doc = _read_json_dict(p)
        if doc:
            return doc
    return {}


def _discover_disk_assets(pd: Path, safe: str, existing_item: dict[str, Any] | None = None) -> tuple[str, str]:
    """Return (image_rel, ref_rel) for a prop/backdrop item if files exist on disk."""
    img_rel = str((existing_item or {}).get("image") or "").strip()
    if img_rel and not (pd / img_rel).is_file():
        img_rel = ""
    if not img_rel:
        cand = pd / "assets" / "props" / f"{safe}.png"
        if cand.is_file() and cand.stat().st_size > 100:
            img_rel = f"assets/props/{safe}.png"

    ref_rel = str((existing_item or {}).get("ref_image") or "").strip()
    if ref_rel and not (pd / ref_rel).is_file():
        ref_rel = ""
    if not ref_rel:
        refs_dir = pd / "assets" / "props" / "refs"
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            cand = refs_dir / f"{safe}_ref{ext}"
            if cand.is_file() and cand.stat().st_size > 64:
                ref_rel = f"assets/props/refs/{safe}_ref{ext}"
                break
    return img_rel, ref_rel


def _attach_urls(pd: Path, slug: str, item: dict[str, Any]) -> dict[str, Any]:
    rec = dict(item)
    safe = str(rec.get("id") or safe_item_slug(str(rec.get("name") or "")))
    rec["id"] = safe
    rec["kind"] = classify_kind(str(rec.get("name") or ""), str(rec.get("kind") or ""))
    img_rel, ref_rel = _discover_disk_assets(pd, safe, rec)
    rec["image"] = img_rel
    rec["ref_image"] = ref_rel
    rec["image_url"] = f"/file/{slug}/{img_rel}" if img_rel else ""
    rec["ref_url"] = f"/file/{slug}/{ref_rel}" if ref_rel else ""
    rec["scenes"] = sorted({str(s).strip() for s in (rec.get("scenes") or []) if str(s).strip()})
    return rec


def extract_props_and_backdrops_from_script(
    pd: Path,
    slug: str,
    *,
    merge_existing: bool = True,
) -> dict[str, Any]:
    """Extract Props and Dynamic Backdrops from script, beats, shot list, and Continuity Book, pre-populating prompts."""
    existing_doc = _read_json_dict(props_backdrops_path(pd)) if merge_existing else {}
    existing_items_raw = existing_doc.get("items")
    existing_items_list: list[Any] = existing_items_raw if isinstance(existing_items_raw, list) else []
    deleted_keys = {
        norm_item_key(str(x))
        for x in (existing_doc.get("deleted") or [])
        if str(x).strip()
    }

    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    # 0. Preserve existing saved items first (keeps user edits, imported refs, generated images, vision sync)
    for raw in existing_items_list:
        if not isinstance(raw, dict):
            continue
        nm = str(raw.get("name") or "").strip()
        if not nm:
            continue
        k = norm_item_key(nm) or safe_item_slug(nm)
        if k in deleted_keys:
            continue
        by_key[k] = dict(raw)
        if k not in order:
            order.append(k)

    def _upsert(
        name: str,
        kind: str,
        *,
        prompt: str = "",
        home_room: str = "",
        scene_id: str = "",
        source: str = "script",
        state: str = "",
    ) -> None:
        clean_name = re.sub(r"\s+", " ", str(name or "").strip())
        if not clean_name or len(clean_name) < 2:
            return
        k = norm_item_key(clean_name) or safe_item_slug(clean_name)
        if k in deleted_keys:
            return
        resolved_kind = classify_kind(clean_name, kind)
        clean_prompt = _clean_prompt_text(prompt)
        if k not in by_key:
            by_key[k] = {
                "id": safe_item_slug(clean_name),
                "name": clean_name,
                "kind": resolved_kind,
                "prompt": clean_prompt or _default_prompt_for(clean_name, resolved_kind, home_room=home_room),
                "home_room": home_room.strip(),
                "state": state.strip(),
                "scenes": [scene_id] if scene_id else [],
                "source": source,
                "image": "",
                "ref_image": "",
                "vision_engine": "",
            }
            order.append(k)
        else:
            rec = by_key[k]
            if scene_id:
                sc_list = list(rec.get("scenes") or [])
                if scene_id not in sc_list:
                    sc_list.append(scene_id)
                rec["scenes"] = sc_list
            if home_room and not str(rec.get("home_room") or "").strip():
                rec["home_room"] = home_room.strip()
            if state and not str(rec.get("state") or "").strip():
                rec["state"] = state.strip()
            # Only fill prompt if currently empty (never clobber user or vision-synced prompts)
            if clean_prompt and not str(rec.get("prompt") or "").strip():
                rec["prompt"] = clean_prompt

    # 1. Continuity Book: all `props[]` AND dynamic scenic `locations[]`
    cb = _load_continuity_book_doc(pd, slug)
    for pr in cb.get("props") or []:
        if not isinstance(pr, dict):
            continue
        pname = str(pr.get("name") or "").strip()
        if not pname:
            continue
        ptok = str(pr.get("token") or pr.get("description") or "").strip()
        hroom = str(pr.get("home_room") or "").strip()
        _upsert(pname, classify_kind(pname, str(pr.get("kind") or "prop")), prompt=ptok, home_room=hroom, source="continuity")

    for loc in cb.get("locations") or []:
        if not isinstance(loc, dict):
            continue
        lname = str(loc.get("name") or "").strip()
        if not lname:
            continue
        if classify_kind(lname) == "backdrop":
            ltok = str(loc.get("token") or loc.get("description") or "").strip()
            display_name = re.sub(r"^(?:SPACE|SKY)\s*:\s*", "", lname, flags=re.IGNORECASE).strip() or lname
            _upsert(display_name, "backdrop", prompt=ltok, source="continuity")

    # 2. Step 06 Screenplay (`screenplay/scene-*.json`): headings + action/dialogue text
    scene_texts: list[tuple[str, str, str]] = []  # (scene_id, heading, body_text)
    sp_dir = pd / "screenplay"
    if sp_dir.is_dir():
        for idx, sp_f in enumerate(sorted(sp_dir.glob("scene-*.json")), start=1):
            sc = _read_json_dict(sp_f)
            if not sc:
                continue
            sc_id = str(sc.get("id") or sc.get("scene") or f"S{idx:03d}").strip()
            heading = str(sc.get("heading") or "").strip()
            parts: list[str] = [heading]
            for el in sc.get("elements") or []:
                if isinstance(el, dict) and el.get("text"):
                    parts.append(str(el["text"]))
            body = " ".join(parts)
            scene_texts.append((sc_id, heading, body))

            # If a scene heading is a dynamic scenic backdrop (e.g. "EXT. SPACE - SATURN - CONTINUOUS"), capture it directly
            if heading and classify_kind(heading) == "backdrop":
                h_clean = re.sub(r"^(?:INT\.?/EXT\.?|EXT\.?|INT\.?)\s*", "", heading, flags=re.IGNORECASE)
                h_clean = re.sub(r"\s*[-–—]\s*(?:DAY|NIGHT|CONTINUOUS|LATER|MORNING|EVENING|DAWN|DUSK|MOMENTS LATER)\s*$", "", h_clean, flags=re.IGNORECASE).strip()
                h_clean = re.sub(r"^(?:SPACE|DEEP SPACE|SKY)\s*[-–—:]\s*", "", h_clean, flags=re.IGNORECASE).strip()
                if h_clean and len(h_clean) >= 3:
                    _upsert(h_clean.title() if h_clean.isupper() else h_clean, "backdrop", scene_id=sc_id, source="script")

    # 3. Step 05 Story Beats (`adaptation/adaptation.json`)
    adapt = _read_json_dict(pd / "adaptation" / "adaptation.json")
    for idx, sc in enumerate(adapt.get("scenes") or [], start=1):
        if not isinstance(sc, dict):
            continue
        sc_id = str(sc.get("id") or f"S{idx:03d}").strip()
        loc_txt = str(sc.get("location") or "").strip()
        blob = f"{loc_txt} {sc.get('title') or ''} {sc.get('summary') or ''}"
        scene_texts.append((sc_id, loc_txt, blob))
        if loc_txt and classify_kind(loc_txt) == "backdrop":
            clean_loc = re.sub(r"^(?:SPACE|SKY)\s*[:\-]\s*", "", loc_txt, flags=re.IGNORECASE).strip() or loc_txt
            _upsert(clean_loc, "backdrop", scene_id=sc_id, source="script")

    # 4. Step 12 Shot List (`shots/shotlist.json`): explicit `props[]` arrays & scene headings
    sl = _read_json_dict(pd / "shots" / "shotlist.json")
    for idx, sc in enumerate(sl.get("scenes") or [], start=1):
        if not isinstance(sc, dict):
            continue
        sc_id = str(sc.get("id") or sc.get("scene") or f"S{idx:03d}").strip()
        heading = str(sc.get("heading") or "").strip()
        for sh in sc.get("shots") or []:
            if not isinstance(sh, dict):
                continue
            for p in sh.get("props") or []:
                pname = str(p or "").strip()
                if pname and len(pname) >= 2:
                    _upsert(pname, classify_kind(pname), scene_id=sc_id, source="shotlist")
            sh_blob = f"{heading} {sh.get('composition') or ''} {sh.get('action') or ''}"
            scene_texts.append((sc_id, heading, sh_blob))

    # 5. Match built-in dynamic prop & backdrop patterns across all script/beat/shot text
    for sc_id, _heading, body in scene_texts:
        if not body.strip():
            continue
        for cname, kind, pat, dprompt in _SCRIPT_PROP_PATTERNS:
            if re.search(pat, body, re.IGNORECASE):
                _upsert(cname, kind, prompt=dprompt, scene_id=sc_id, source="script")
        for cname, pat, dprompt in _SCRIPT_BACKDROP_PATTERNS:
            if re.search(pat, body, re.IGNORECASE):
                _upsert(cname, "backdrop", prompt=dprompt, scene_id=sc_id, source="script")

    # 6. Also tag scenes on any already-extracted items whose name appears in scene_texts
    for rec in by_key.values():
        nm = str(rec.get("name") or "").strip()
        short_nm = re.sub(r"\s*\([^)]*\)\s*", "", nm).strip()
        tok_pat = re.escape(short_nm) if len(short_nm) >= 3 else ""
        if not tok_pat:
            continue
        rx = re.compile(rf"\b{tok_pat}\b", re.IGNORECASE)
        sc_set = set(rec.get("scenes") or [])
        for sc_id, _heading, body in scene_texts:
            if rx.search(body):
                sc_set.add(sc_id)
        rec["scenes"] = sorted(sc_set)

    # Sort backdrops & props cleanly (props first, then backdrops; alphabetical within kind while preserving explicit custom items)
    items_out = [_attach_urls(pd, slug, by_key[k]) for k in order if k in by_key]
    items_out.sort(key=lambda x: (0 if x["kind"] == "prop" else 1, str(x["name"]).lower()))

    doc = {
        "extracted": True,
        "deleted": sorted(deleted_keys),
        "items": [
            {
                "id": it["id"],
                "name": it["name"],
                "kind": it["kind"],
                "prompt": it["prompt"],
                "home_room": it.get("home_room", ""),
                "state": it.get("state", ""),
                "scenes": it.get("scenes", []),
                "source": it.get("source", "script"),
                "image": it.get("image", ""),
                "ref_image": it.get("ref_image", ""),
                "vision_engine": it.get("vision_engine", ""),
                "vision_synced_from": it.get("vision_synced_from", ""),
            }
            for it in items_out
        ],
    }
    pd.mkdir(parents=True, exist_ok=True)
    props_backdrops_path(pd).write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return _build_response(slug, items_out)


def _build_response(slug: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    props_n = sum(1 for x in items if x.get("kind") == "prop")
    backdrops_n = sum(1 for x in items if x.get("kind") == "backdrop")
    with_img = sum(1 for x in items if x.get("image_url") or x.get("ref_url"))
    return {
        "status": "ok",
        "project": slug,
        "items": items,
        "counts": {
            "total": len(items),
            "props": props_n,
            "backdrops": backdrops_n,
            "with_images": with_img,
        },
    }


def load_props_backdrops(pd: Path, slug: str, *, auto_extract: bool = True) -> dict[str, Any]:
    """Load Step 07 Props & Backdrops (auto-extracting from script on first open if not yet initialized)."""
    p = props_backdrops_path(pd)
    doc = _read_json_dict(p)
    if auto_extract and (not p.is_file() or (not doc.get("extracted") and not doc.get("items"))):
        return extract_props_and_backdrops_from_script(pd, slug, merge_existing=True)

    raw_items_val = doc.get("items")
    raw_items: list[Any] = raw_items_val if isinstance(raw_items_val, list) else []
    items = [_attach_urls(pd, slug, it) for it in raw_items if isinstance(it, dict) and str(it.get("name") or "").strip()]
    return _build_response(slug, items)


def sync_item_prompt_to_continuity_and_keyframes(
    pd: Path,
    slug: str,
    name: str,
    prompt: str,
    *,
    kind: str = "prop",
    home_room: str = "",
    visual_source: str = "step07_props_backdrops",
) -> dict[str, Any]:
    """Propagate a prop or backdrop's prompt into Continuity Book and unlocked Step 17 keyframe prompts."""
    import continuity_book
    from studio_app import keyframe_context

    clean_name = str(name or "").strip()
    clean_prompt = str(prompt or "").strip()
    if not clean_name or not clean_prompt:
        return {"continuity_updated": False, "keyframes_updated": 0, "keyframes_skipped_locked": 0}

    target_k = norm_item_key(clean_name)
    short_nm = re.sub(r"\s*\([^)]*\)\s*", "", clean_name).strip()
    short_k = norm_item_key(short_nm) or target_k

    # 1. Continuity Book (`props[]` + matching `locations[]` for backdrops)
    cb_paths: list[Path] = []
    for cand in (continuity_book.continuity_file(pd), pd / f"{slug}.json", pd / "continuity.json"):
        if cand.is_file() and cand.resolve() not in {x.resolve() for x in cb_paths}:
            cb_paths.append(cand)

    cb_updated = False
    for cb_p in cb_paths:
        cb = _read_json_dict(cb_p)
        if not cb:
            continue
        props_list = cb.get("props")
        if not isinstance(props_list, list):
            props_list = []
        matched = False
        for pr in props_list:
            if not isinstance(pr, dict):
                continue
            pk = norm_item_key(str(pr.get("name") or ""))
            if pk and pk in (target_k, short_k):
                pr["token"] = clean_prompt
                pr["description"] = clean_prompt
                pr["kind"] = kind
                if home_room:
                    pr["home_room"] = home_room
                pr["visual_source"] = visual_source
                matched = True
        if not matched:
            entry: dict[str, Any] = {
                "name": clean_name,
                "kind": kind,
                "token": clean_prompt,
                "description": clean_prompt,
                "visual_source": visual_source,
            }
            if home_room:
                entry["home_room"] = home_room
            props_list.append(entry)
        cb["props"] = props_list

        # If this is a backdrop, also update any matching scenic entry in `locations[]`
        if kind == "backdrop" and isinstance(cb.get("locations"), list):
            for loc in cb["locations"]:
                if not isinstance(loc, dict):
                    continue
                lk = norm_item_key(str(loc.get("name") or ""))
                if lk and lk in (target_k, short_k):
                    loc["token"] = clean_prompt
                    loc["description"] = clean_prompt
                    loc["visual_source"] = visual_source

        cb_p.write_text(json.dumps(cb, indent=1, ensure_ascii=False), encoding="utf-8")
        cb_updated = True

    # 2. Rebuild unlocked Step 17 `keyframes_v2.json` prompts for any shot referencing this prop/backdrop
    keyframes_updated = 0
    keyframes_skipped_locked = 0
    sl_data = _read_json_dict(pd / "shots" / "shotlist.json")
    if sl_data and isinstance(sl_data.get("scenes"), list):
        meta_path = pd / "keyframes_v2.json"
        meta = _read_json_dict(meta_path)
        locked_ids = {str(x) for x in (meta.get("locked") or [])}
        prompts: dict[str, Any] = dict(meta.get("prompts") or {})

        match_terms = [t for t in {clean_name.lower(), short_nm.lower()} if len(t) >= 3]
        match_res = [re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE) for t in match_terms]
        ctx = keyframe_context.load_keyframe_project_context(slug, pd)

        for sc in sl_data.get("scenes") or []:
            if not isinstance(sc, dict):
                continue
            sc_id = str(sc.get("id") or sc.get("scene") or "").strip()
            heading = str(sc.get("heading") or "")
            heading_hit = any(rx.search(heading) for rx in match_res)
            for idx, sh in enumerate(sc.get("shots") or [], start=1):
                if not isinstance(sh, dict):
                    continue
                sh_props = " ".join(str(p) for p in (sh.get("props") or []))
                sh_blob = f"{heading} {sh_props} {sh.get('composition') or ''} {sh.get('action') or ''} {sh.get('blocking') or ''}"
                if not heading_hit and not any(rx.search(sh_blob) for rx in match_res):
                    continue
                n = int(sh.get("n") or idx)
                sid = f"{sc_id}-{n:02d}"
                if sid in locked_ids:
                    keyframes_skipped_locked += 1
                    continue
                info = keyframe_context.build_shot_keyframe_info(sh, sc_id, heading, ctx)
                prompts[sid] = info["default_prompt"]
                keyframes_updated += 1

        if keyframes_updated:
            meta["prompts"] = prompts
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "continuity_updated": cb_updated,
        "keyframes_updated": keyframes_updated,
        "keyframes_skipped_locked": keyframes_skipped_locked,
    }


def save_prop_backdrop_item(
    pd: Path,
    slug: str,
    *,
    name: str,
    kind: str = "prop",
    prompt: str = "",
    home_room: str = "",
    state: str = "",
    scenes: list[str] | None = None,
    item_id: str = "",
    delete: bool = False,
) -> dict[str, Any]:
    """Create, update, or delete one Step 07 Prop or Backdrop item."""
    p = props_backdrops_path(pd)
    doc = _read_json_dict(p)
    items: list[dict[str, Any]] = [dict(x) for x in (doc.get("items") or []) if isinstance(x, dict)]
    deleted_set = {norm_item_key(str(x)) for x in (doc.get("deleted") or []) if str(x).strip()}

    clean_name = str(name or "").strip()
    target_id = str(item_id or safe_item_slug(clean_name)).strip()
    target_k = norm_item_key(clean_name)

    if delete:
        kept: list[dict[str, Any]] = []
        for it in items:
            if str(it.get("id") or "") == target_id or (target_k and norm_item_key(str(it.get("name") or "")) == target_k):
                if target_k:
                    deleted_set.add(target_k)
                continue
            kept.append(it)
        doc["items"] = kept
        doc["deleted"] = sorted(deleted_set)
        doc["extracted"] = True
        pd.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "status": "ok",
            "deleted": clean_name or target_id,
            **load_props_backdrops(pd, slug, auto_extract=False),
        }

    resolved_kind = classify_kind(clean_name, kind)
    final_prompt = str(prompt or "").strip() or _default_prompt_for(clean_name, resolved_kind, home_room=home_room)
    if target_k in deleted_set:
        deleted_set.discard(target_k)

    found: dict[str, Any] | None = None
    for it in items:
        if str(it.get("id") or "") == target_id or (target_k and norm_item_key(str(it.get("name") or "")) == target_k):
            found = it
            break

    if found is None:
        found = {
            "id": target_id or safe_item_slug(clean_name),
            "name": clean_name,
            "kind": resolved_kind,
            "prompt": final_prompt,
            "home_room": home_room.strip(),
            "state": state.strip(),
            "scenes": sorted({str(s).strip() for s in (scenes or []) if str(s).strip()}),
            "source": "user",
            "image": "",
            "ref_image": "",
            "vision_engine": "",
            "vision_synced_from": "",
        }
        items.append(found)
    else:
        found["name"] = clean_name or found.get("name", "")
        found["kind"] = resolved_kind
        found["prompt"] = final_prompt
        if home_room is not None:
            found["home_room"] = home_room.strip()
        if state is not None:
            found["state"] = state.strip()
        if scenes is not None:
            found["scenes"] = sorted({str(s).strip() for s in scenes if str(s).strip()})

    doc["items"] = items
    doc["deleted"] = sorted(deleted_set)
    doc["extracted"] = True
    pd.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    sync_res = sync_item_prompt_to_continuity_and_keyframes(
        pd,
        slug,
        str(found["name"]),
        final_prompt,
        kind=resolved_kind,
        home_room=str(found.get("home_room") or ""),
    )
    out = load_props_backdrops(pd, slug, auto_extract=False)
    out["item"] = _attach_urls(pd, slug, found)
    out["sync"] = sync_res
    return out


def update_item_assets(
    pd: Path,
    slug: str,
    *,
    name: str,
    kind: str = "prop",
    item_id: str = "",
    image_rel: str | None = None,
    ref_rel: str | None = None,
    prompt: str | None = None,
    vision_engine: str | None = None,
    vision_synced_from: str | None = None,
) -> dict[str, Any]:
    """Persist updated image/ref/prompt metadata for a Step 07 Prop or Backdrop item."""
    p = props_backdrops_path(pd)
    doc = _read_json_dict(p)
    items: list[dict[str, Any]] = [dict(x) for x in (doc.get("items") or []) if isinstance(x, dict)]
    clean_name = str(name or "").strip()
    target_id = str(item_id or safe_item_slug(clean_name)).strip()
    target_k = norm_item_key(clean_name)

    found: dict[str, Any] | None = None
    for it in items:
        if str(it.get("id") or "") == target_id or (target_k and norm_item_key(str(it.get("name") or "")) == target_k):
            found = it
            break

    if found is None:
        resolved_kind = classify_kind(clean_name, kind)
        found = {
            "id": target_id or safe_item_slug(clean_name),
            "name": clean_name,
            "kind": resolved_kind,
            "prompt": (prompt or "").strip() or _default_prompt_for(clean_name, resolved_kind),
            "home_room": "",
            "state": "",
            "scenes": [],
            "source": "user",
            "image": "",
            "ref_image": "",
            "vision_engine": "",
            "vision_synced_from": "",
        }
        items.append(found)

    if image_rel is not None:
        found["image"] = image_rel
    if ref_rel is not None:
        found["ref_image"] = ref_rel
    if prompt is not None and prompt.strip():
        found["prompt"] = prompt.strip()
    if vision_engine is not None:
        found["vision_engine"] = vision_engine
    if vision_synced_from is not None:
        found["vision_synced_from"] = vision_synced_from

    doc["items"] = items
    doc["extracted"] = True
    pd.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return _attach_urls(pd, slug, found)
