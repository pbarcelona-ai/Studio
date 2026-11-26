"""Keyframe-to-keyframe prompt continuity, prop persistence, and architectural scale auditor.

Runs:
1. Automatically inside `scripts/shot_list.py` whenever a new book builds its Step 12 shot list.
2. On demand via `POST /api/v2_shot_continuity_audit` (Step 17 / Step 12 UI), feeding all fixes
   back into Step 12 (`shots/shotlist.json`), Step 17 (`keyframes_v2.json` unlocked prompts),
   and the Bi-Directional Sync Queue (`workflow_sync`).

Catches and corrects:
- Self-contradictions within a shot (e.g. "bare/empty coat hook" vs "coat hanging on it").
- Non-existent furniture / surfaces compared to the locked Step 11 set description
  (e.g. placing a tea mug on a "coffee table" when the imported set only has a dining table).
- Prop teleportation / disappearing props / room-boundary violations across shots in a scene
  (e.g. a cardboard box popping in for one shot and disappearing, or a kitchen dog bowl
  wandering onto the living room rug and changing size from shot to shot).
- Character-to-character & prop-to-furniture proportion mismatches (e.g. "Judah fills the
  frame" making a Labrador dog larger than Mom, or a giant mug/bowl floating on the rug).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("studio.shot_continuity_audit")

_DOG_WORDS = ("dog", "labrador", "puppy", "hound", "retriever", "terrier", "poodle", "beagle", "canine")
_CHILD_WORDS = ("boy", "girl", "child", "kid", "toddler", "5-year-old", "4-year-old", "3-year-old", "waist-high")
_TOY_WORDS = ("action figure", "rag doll", "stuffed", "plush", "toy", "foot-tall", "doll")
_SEVERITY_RANK = {"critical": 0, "major": 1, "minor": 2}


def _norm_severity(val: Any, default: str = "major") -> str:
    s = str(val or "").strip().lower()
    return s if s in _SEVERITY_RANK else default


def _build_shot_scorecard(
    fixes: list[dict[str, Any]],
    ambiguous_items: list[dict[str, Any]],
    *,
    unverified_sets: int = 0,
) -> list[dict[str, str]]:
    def _rate(keywords: tuple[str, ...], default_ok: str) -> dict[str, str]:
        matched_amb = [x for x in ambiguous_items if any(k in str(x.get("issue") or "").lower() for k in keywords)]
        matched_fix = [x for x in fixes if any(k in str(x.get("issue") or "").lower() for k in keywords)]
        if matched_amb:
            return {"rating": "Fail", "reason": f"{len(matched_amb)} ambiguous issue(s) need user decision."}
        if matched_fix:
            return {"rating": "Needs Work", "reason": f"{len(matched_fix)} issue(s) detected and auto-repaired."}
        return {"rating": "Pass", "reason": default_ok}

    prop_r = _rate(("prop", "hook", "coat", "box", "bowl", "vanish", "teleport"), "Props persist cleanly without contradictions.")
    surf_r = _rate(("table", "surface", "furniture", "room", "kitchen", "rug", "set"), "Props rest on real furniture matching the set.")
    if surf_r["rating"] == "Pass" and unverified_sets > 0:
        surf_r = {"rating": "Needs Work", "reason": f"{unverified_sets} scene(s) lack a Step 11 baselined set description."}
    scale_r = _rate(("scale", "proportion", "fills the frame", "height", "size", "giant"), "Character & prop proportions match real-world scale.")
    flow_r = _rate(("continuity", "wardrobe", "lighting", "aligned"), "Shot-to-shot flow and framing stay consistent.")
    return [
        {"criterion": "Prop Persistence", **prop_r},
        {"criterion": "Room & Surface Grounding", **surf_r},
        {"criterion": "Character & Prop Scale", **scale_r},
        {"criterion": "Shot-to-Shot Continuity", **flow_r},
    ]


def _classify_cast_scale_hints(cast_profiles: dict[str, dict[str, Any]]) -> list[str]:
    hints: list[str] = []
    seen: set[str] = set()
    for rec in cast_profiles.values():
        name = str(rec.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        tok = str(rec.get("token") or "").lower()
        if any(w in tok for w in _TOY_WORDS):
            hints.append(f"{name}: small toy/figure (~10-14 inches tall)")
        elif any(w in tok for w in _DOG_WORDS):
            hints.append(f"{name}: adult dog (~2 ft tall at shoulder, knee-high to an adult, NEVER larger than a human)")
        elif any(w in tok for w in _CHILD_WORDS):
            hints.append(f"{name}: young child (~3'6\" tall, waist-high to an adult)")
        elif "never appears" in tok or "offstage" in name.lower():
            continue
        else:
            hints.append(f"{name}: adult human (~5'4\"-5'10\" tall, head well below 8-ft doorways)")
    return hints


def apply_deterministic_shot_fixes(
    sc: dict[str, Any],
    *,
    set_description: str = "",
    cast_profiles: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Fast, offline deterministic pass fixing unambiguous contradictions, giant-scale phrasing, and missing surfaces."""
    fixes: list[dict[str, Any]] = []
    raw_shots = sc.get("shots")
    shots: list[Any] = raw_shots if isinstance(raw_shots, list) else []
    sc_id = str(sc.get("id") or sc.get("scene") or "S001")
    set_low = str(set_description or "").lower()
    cast = cast_profiles or {}

    has_coffee_table = ("coffee table" in set_low) and not bool(
        re.search(r"\b(?:no|without|missing|absent)\s+(?:a\s+)?coffee\s+table\b", set_low)
    )
    has_dining_table = any(w in set_low for w in ("dining", "round wooden table", "round table", "table"))

    for idx, sh in enumerate(shots, start=1):
        if not isinstance(sh, dict):
            continue
        n = int(sh.get("n") or idx)
        sid = f"{sc_id}-{n:02d}"
        comp = str(sh.get("composition") or "")
        act = str(sh.get("action") or "")
        blk = str(sh.get("blocking") or "")
        props_txt = " ".join(str(p) for p in (sh.get("props") or [])).lower()

        # 1. Self-contradiction: "empty/bare hook" in action/props while composition adds a coat hanging on it
        if ("empty coat hook" in props_txt or "bare hook" in act.lower() or "empty hook" in act.lower()) and re.search(
            r"with\s+(?:the|a)\s+[^,.]*\bcoat\s+hanging\s+on\s+it", comp, re.IGNORECASE
        ):
            new_comp = re.sub(
                r",?\s*with\s+(?:the|a)\s+[^,.]*\bcoat\s+hanging\s+on\s+it",
                ", completely bare and empty",
                comp,
                flags=re.IGNORECASE,
            )
            sh["composition"] = new_comp
            comp = new_comp
            fixes.append({
                "shot": sid,
                "field": "composition",
                "severity": "critical",
                "risk": "Direct visual self-contradiction inside a single keyframe prompt.",
                "ambiguous": False,
                "fixed": True,
                "issue": "Removed coat hanging on an explicitly bare/empty coat hook",
            })

        # 2. Non-existent coffee table when locked set has a dining table instead -> relocate mug/cup cleanly ON tabletop
        if set_low and not has_coffee_table and has_dining_table and "coffee table" in comp.lower():
            new_comp = re.sub(
                r"\b(?:to|on|onto)\s+the\s+coffee\s+table\b",
                "onto the round wooden dining table",
                comp,
                flags=re.IGNORECASE,
            )
            new_comp = re.sub(r"\bcoffee\s+table\b", "round wooden dining table", new_comp, flags=re.IGNORECASE)
            if new_comp != comp:
                sh["composition"] = new_comp
                comp = new_comp
                fixes.append({
                    "shot": sid,
                    "field": "composition",
                    "severity": "critical",
                    "risk": "Image generator will hallucinate missing furniture or float the prop.",
                    "ambiguous": False,
                    "fixed": True,
                    "issue": "Relocated prop from nonexistent coffee table to existing dining table in locked set",
                })

        # 3. "fills the frame" on a dog or child alongside an adult causes giant horse-sized proportions
        chars = [str(c).strip() for c in (sh.get("characters") or []) if str(c).strip()]
        if len(chars) >= 2 and re.search(r"\bfills\s+the\s+frame\b", comp, re.IGNORECASE):
            has_non_adult = any(
                any(w in str((cast.get(c.lower()) or {}).get("token") or "").lower() for w in (_DOG_WORDS + _CHILD_WORDS + _TOY_WORDS))
                for c in chars
            )
            if has_non_adult:
                new_comp = re.sub(
                    r"\band\s+fills\s+the\s+frame\b",
                    "at natural knee-high scale relative to the adult beside them",
                    comp,
                    flags=re.IGNORECASE,
                )
                new_comp = re.sub(
                    r"\bfills\s+the\s+frame\b",
                    "stays naturally scaled relative to the adult and room furniture",
                    new_comp,
                    flags=re.IGNORECASE,
                )
                if new_comp != comp:
                    sh["composition"] = new_comp
                    comp = new_comp
                    fixes.append({"shot": sid, "field": "composition", "issue": "Replaced 'fills the frame' with natural relative scale between dog/child and adult"})

        # 4. Small tabletop mug / tea cup without explicit grounded size -> anchor to 4-inch scale resting flat on wooden tabletop
        if re.search(r"\b(mug|teacup|tea\s+cup)\b", comp, re.IGNORECASE) and not re.search(r"\b4[- ]inch|small\s+(?:ceramic|chipped|white)\s+mug\b", comp, re.IGNORECASE):
            new_comp = re.sub(
                r"\b(?:the|a)\s+(chipped\s+white\s+mug|white\s+mug|ceramic\s+mug|mug)\b",
                r"a small 4-inch \1 resting flat on the wooden tabletop",
                comp,
                count=1,
                flags=re.IGNORECASE,
            )
            if new_comp != comp:
                sh["composition"] = new_comp
                comp = new_comp
                fixes.append({"shot": sid, "field": "composition", "issue": "Anchored mug to realistic 4-inch tabletop scale so it cannot render giant on the rug"})

        # 5. Dog bowl without consistent small size -> anchor to 8-inch stainless steel bowl flat on floor
        if re.search(r"\b(steel\s+bowl|dog\s+bowl)\b", comp, re.IGNORECASE) and not re.search(r"\b8[- ]inch|small\s+8[- ]inch\b", comp, re.IGNORECASE):
            new_comp = re.sub(
                r"\b(?:the|a)\s+(shiny\s+steel\s+dog\s+bowl|steel\s+dog\s+bowl|steel\s+bowl|dog\s+bowl)\b",
                r"the small 8-inch \1 resting flat on the floor",
                comp,
                count=1,
                flags=re.IGNORECASE,
            )
            if new_comp != comp:
                sh["composition"] = new_comp
                fixes.append({"shot": sid, "field": "composition", "issue": "Anchored dog bowl to consistent 8-inch floor scale across shots"})
        _ = blk

    return fixes


def audit_scene_shots_llm(
    sc: dict[str, Any],
    *,
    set_description: str = "",
    set_lighting: str = "",
    cast_profiles: dict[str, dict[str, Any]] | None = None,
    timeout: float = 45.0,
) -> tuple[list[dict[str, Any]], str]:
    """Use Ollama Vision/LLM or Gemini 3.8 Flash to audit shot-to-shot continuity, prop persistence, and proportions."""
    from studio_app import set_vision_sync as svs

    raw_shots = sc.get("shots")
    shots: list[Any] = raw_shots if isinstance(raw_shots, list) else []
    if len(shots) < 2:
        return [], ""

    sc_id = str(sc.get("id") or sc.get("scene") or "S001")
    heading = str(sc.get("heading") or "")
    scale_hints = _classify_cast_scale_hints(cast_profiles or {})

    compact_shots = [
        {
            "n": int(sh.get("n") or idx),
            "type": str(sh.get("type") or "MS"),
            "lens_mm": int(sh.get("lens_mm") or 35),
            "characters": list(sh.get("characters") or []),
            "props": list(sh.get("props") or []),
            "composition": str(sh.get("composition") or ""),
            "blocking": str(sh.get("blocking") or ""),
            "action": str(sh.get("action") or ""),
        }
        for idx, sh in enumerate(shots, start=1)
        if isinstance(sh, dict)
    ]

    prompt = (
        f"You are a senior film script supervisor & storyboard continuity auditor reviewing Scene {sc_id} ({heading}) shot-by-shot.\n"
        f"LOCKED VISUAL SET PLATE (ground-truth architecture & furniture):\n"
        f"- Set: {set_description or 'Use consistent room layout from the scene heading'}\n"
        f"- Lighting: {set_lighting or 'consistent across scene'}\n"
        f"CHARACTER SCALE REFERENCE:\n"
        + ("\n".join(f"- {h}" for h in scale_hints) if scale_hints else "- Realistic human/pet/prop proportions")
        + "\n\nAUDIT EVERY SHOT SEQUENTIALLY FOR THESE 4 DEFECTS:\n"
        "1. PROP PERSISTENCE & TELEPORTATION: If a notable prop (e.g. a cardboard box, folded newspaper, remote, bowl) is introduced in Shot N, "
        "ensure it does NOT randomly appear in one shot and vanish in adjacent shots showing the same area, AND never contradict the same shot "
        "(e.g. 'empty/bare hook' vs 'coat hanging on it').\n"
        "2. ROOM-BOUNDARY PROP LOGIC: Keep kitchen/threshold props (such as a dog's food/water bowl) strictly in the kitchen/doorway area — "
        "never let a dog bowl drift into the middle of the living room rug or change size between shots.\n"
        "3. GROUNDED SURFACES (MATCH LOCKED SET): Never reference furniture that does NOT exist in the LOCKED VISUAL SET (e.g. no 'coffee table' "
        "if the set only has a round wooden dining table and oak TV console). Place every mug/prop solidly ON an existing surface in the set.\n"
        "4. RELATIVE CHARACTER & PROP PROPORTIONS: Ensure every multi-character shot states clear true-to-life relative scale "
        "(e.g. adult ~5'4\", dog knee-high ~2 ft at shoulder — never larger than Mom; child ~3'6\" waist-high to Mom; ceramic mug ~4 inches tall "
        "on tabletop; steel dog bowl ~8 inches wide flat on kitchen threshold floor). Remove giant-making phrases like 'fills the frame' on dogs/children.\n\n"
        "STRICT AUDITOR RULES:\n"
        "- Order findings by severity ('critical' | 'major' | 'minor') and state concrete downstream 'risk'.\n"
        "- NEVER invent facts, furniture, props, or intent not grounded in the locked set or scene. If a continuity question is genuinely ambiguous, "
        "set '\"ambiguous\": true' and leave replacement text fields EMPTY so the human director decides instead of guessing.\n"
        "- List any 'blind_spots' (missing set geometry, unspecified character heights, or unverified assumptions).\n"
        "Preserve 100% of the story beats, dialogue intent, camera shot types, and character names.\n"
        "Respond ONLY with valid JSON: "
        '{"fixes": [{"n": 5, "severity": "critical|major|minor", "issue": "short reason", "risk": "visual impact", "ambiguous": false, '
        '"composition": "updated composition (empty if ambiguous)", "blocking": "optional", "action": "optional", "props": ["optional updated props list"]}], '
        '"blind_spots": ["optional missing context"]}\n'
        "Return {\"fixes\": [], \"blind_spots\": []} if every shot is already consistent.\n\n"
        f"SCENE SHOTS:\n{json.dumps(compact_shots, ensure_ascii=False)}"
    )

    parsed, engine = svs._call_ollama_vision_json(prompt, None, timeout=timeout)
    if not parsed:
        parsed, engine = svs._call_gemini_vision_json(prompt, None, timeout=timeout)
    if not parsed:
        return [], ""

    raw_fixes = parsed.get("fixes")
    if not isinstance(raw_fixes, list):
        return [], engine

    applied: list[dict[str, Any]] = []
    by_n = {int(sh.get("n") or idx): sh for idx, sh in enumerate(shots, start=1) if isinstance(sh, dict)}
    for fx in raw_fixes:
        if not isinstance(fx, dict):
            continue
        try:
            n = int(fx.get("n") or 0)
        except (TypeError, ValueError):
            continue
        sh = by_n.get(n)
        if sh is None:
            continue
        sev = _norm_severity(fx.get("severity"), "major")
        risk = str(fx.get("risk") or "Visual inconsistency between consecutive keyframes.").strip()
        is_amb = bool(fx.get("ambiguous") or fx.get("needs_user_decision"))
        issue_txt = str(fx.get("issue") or "Aligned shot continuity & scale").strip()
        if is_amb:
            # Never auto-overwrite when the AI flags genuine ambiguity — surface for human decision!
            applied.append(
                {
                    "shot": f"{sc_id}-{n:02d}",
                    "fields": [],
                    "severity": sev,
                    "risk": risk,
                    "ambiguous": True,
                    "needs_user_decision": True,
                    "fixed": False,
                    "issue": issue_txt,
                }
            )
            continue
        changed_fields: list[str] = []
        for field in ("composition", "blocking", "action", "lighting"):
            val = str(fx.get(field) or "").strip()
            if val and val != str(sh.get(field) or "").strip():
                sh[field] = val[:600]
                changed_fields.append(field)
        if isinstance(fx.get("props"), list):
            clean_props = [str(p).strip()[:60] for p in fx["props"] if str(p).strip()]
            if clean_props != list(sh.get("props") or []):
                sh["props"] = clean_props
                changed_fields.append("props")
        if changed_fields:
            applied.append(
                {
                    "shot": f"{sc_id}-{n:02d}",
                    "fields": changed_fields,
                    "severity": sev,
                    "risk": risk,
                    "ambiguous": False,
                    "needs_user_decision": False,
                    "fixed": True,
                    "issue": issue_txt,
                }
            )
    raw_bs = parsed.get("blind_spots")
    if isinstance(raw_bs, list):
        existing_bs = sc.get("_audit_blind_spots")
        bs_list = list(existing_bs) if isinstance(existing_bs, list) else []
        for b in raw_bs:
            bs_txt = str(b or "").strip()
            if bs_txt and bs_txt not in bs_list:
                bs_list.append(bs_txt)
        sc["_audit_blind_spots"] = bs_list
    return applied, engine


def run_deterministic_shot_sanity(data: dict[str, Any], pd: Path) -> list[dict[str, Any]]:
    """Lightweight offline sanity pass invoked automatically by `shot_list.write()` on every new book import."""
    sets_custom: dict[str, Any] = {}
    sc_path = pd / "sets_custom.json"
    if sc_path.is_file():
        try:
            raw = json.loads(sc_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                sets_custom = raw
        except (OSError, ValueError):
            sets_custom = {}

    all_fixes: list[dict[str, Any]] = []
    for sc in data.get("scenes") or []:
        if not isinstance(sc, dict):
            continue
        heading = str(sc.get("heading") or "").lower()
        set_desc = str(sc.get("set_visual_description") or "")
        if not set_desc:
            for sk, sv in sets_custom.items():
                if isinstance(sv, dict) and sk and sk in heading:
                    set_desc = str(sv.get("description") or "")
                    break
        all_fixes.extend(apply_deterministic_shot_fixes(sc, set_description=set_desc))
    return all_fixes


def run_project_shot_continuity_audit(
    pd: Path,
    slug: str,
    *,
    target_scene: str = "",
    use_llm: bool = True,
    record_bidirectional: bool = True,
    timeout: float = 45.0,
) -> dict[str, Any]:
    """Audit shot-to-shot continuity, prop persistence, and proportions, feeding fixes back to Steps 12, 17, and Workflow Sync."""
    from studio_app import keyframe_context, workflow_sync

    sl_path = pd / "shots" / "shotlist.json"
    if not sl_path.is_file():
        return {"ok": False, "error": "No shots/shotlist.json found — build Step 12 Shot List first."}
    sl_data = json.loads(sl_path.read_text(encoding="utf-8")) or {}
    scenes = sl_data.get("scenes") if isinstance(sl_data.get("scenes"), list) else []
    if not scenes:
        return {"ok": False, "error": "Shot list has no scenes."}

    ctx = keyframe_context.load_keyframe_project_context(slug, pd)
    cast_profiles: dict[str, dict[str, Any]] = ctx["cast_profiles"]
    locations: dict[str, dict[str, Any]] = ctx["locations"]

    target_scenes: list[dict[str, Any]] = []
    for sc in scenes:
        if not isinstance(sc, dict):
            continue
        sc_id = str(sc.get("id") or sc.get("scene") or "")
        if target_scene and sc_id.upper() != target_scene.strip().upper():
            continue
        target_scenes.append(sc)

    def _resolve_scene_set(sc_obj: dict[str, Any]) -> tuple[str, str]:
        desc = str(sc_obj.get("set_visual_description") or "").strip()
        light = str(sc_obj.get("set_lighting") or "").strip()
        if desc:
            return desc, light
        heading = str(sc_obj.get("heading") or "")
        loc_tok, _img, _names = keyframe_context.match_location_context(ctx, heading)
        if loc_tok:
            return loc_tok, light
        for nk, rec in locations.items():
            if nk and nk in heading.lower():
                return str(rec.get("token") or ""), str(rec.get("lighting") or light)
        return "", light

    all_fixes: list[dict[str, Any]] = []
    ambiguous_items: list[dict[str, Any]] = []
    blind_spots: list[str] = []
    unverified_sets = 0
    touched_scene_ids: set[str] = set()
    engine_used = "deterministic"

    # 1. Deterministic pass first across all target scenes + collect set/cast blind spots
    for sc in target_scenes:
        sc_id = str(sc.get("id") or sc.get("scene") or "")
        s_desc, _s_light = _resolve_scene_set(sc)
        if not s_desc:
            unverified_sets += 1
            heading = str(sc.get("heading") or sc_id)
            blind_spots.append(f"{sc_id} ({heading}): No Step 11 baselined set description yet — furniture surfaces could not be visually verified.")
        det_fixes = apply_deterministic_shot_fixes(sc, set_description=s_desc, cast_profiles=cast_profiles)
        if det_fixes:
            all_fixes.extend(det_fixes)
            touched_scene_ids.add(sc_id)

    # 2. LLM shot-to-shot continuity & scale pass (parallelized per scene for speed)
    if use_llm and target_scenes:
        def _audit_one(sc_obj: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str]:
            sc_id = str(sc_obj.get("id") or sc_obj.get("scene") or "")
            s_desc, s_light = _resolve_scene_set(sc_obj)
            fx, eng = audit_scene_shots_llm(
                sc_obj,
                set_description=s_desc,
                set_lighting=s_light,
                cast_profiles=cast_profiles,
                timeout=timeout,
            )
            return sc_id, fx, eng

        if len(target_scenes) == 1:
            llm_results = [_audit_one(target_scenes[0])]
        else:
            with ThreadPoolExecutor(max_workers=min(4, len(target_scenes))) as pool:
                llm_results = list(pool.map(_audit_one, target_scenes))

        for sc_id, fx_list, eng in llm_results:
            if eng:
                engine_used = eng
            for fx in fx_list:
                if fx.get("ambiguous"):
                    ambiguous_items.append(fx)
                else:
                    all_fixes.append(fx)
                    touched_scene_ids.add(sc_id)

        for sc in target_scenes:
            raw_bs = sc.pop("_audit_blind_spots", None)
            if isinstance(raw_bs, list):
                for b in raw_bs:
                    bs_txt = str(b or "").strip()
                    if bs_txt and bs_txt not in blind_spots:
                        blind_spots.append(bs_txt)

    if engine_used == "deterministic":
        blind_spots.append("Offline deterministic audit only — AI semantic continuity check did not run.")

    all_fixes.sort(key=lambda x: _SEVERITY_RANK.get(_norm_severity(x.get("severity")), 1))
    ambiguous_items.sort(key=lambda x: _SEVERITY_RANK.get(_norm_severity(x.get("severity")), 1))
    scorecard = _build_shot_scorecard(all_fixes, ambiguous_items, unverified_sets=unverified_sets)

    updated_steps: list[str] = []
    keyframes_updated = 0
    keyframes_skipped_locked = 0

    if touched_scene_ids:
        # Persist updated Step 12 Shot List
        checks = dict(sl_data.get("checks") or {})
        checks["shot_continuity_audit"] = {
            "engine": engine_used,
            "fixes_applied": len(all_fixes),
            "scenes": sorted(touched_scene_ids),
        }
        sl_data["checks"] = checks
        sl_path.write_text(json.dumps(sl_data, indent=1, ensure_ascii=False), encoding="utf-8")
        updated_steps.append(f"Step 12 (Shot List: {len(all_fixes)} fix(es))")

        # Rebuild unlocked Step 17 keyframe prompts for all modified scenes
        meta_path = pd / "keyframes_v2.json"
        meta: dict[str, Any] = {}
        if meta_path.is_file():
            try:
                raw_m = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(raw_m, dict):
                    meta = raw_m
            except (OSError, ValueError):
                meta = {}
        locked_ids = {str(x) for x in (meta.get("locked") or [])}
        prompts: dict[str, Any] = dict(meta.get("prompts") or {})

        for sc in target_scenes:
            sc_id = str(sc.get("id") or sc.get("scene") or "")
            if sc_id not in touched_scene_ids:
                continue
            heading = str(sc.get("heading") or "")
            for idx, sh in enumerate(sc.get("shots") or [], start=1):
                if not isinstance(sh, dict):
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
            updated_steps.append(f"Step 17 (Storyboard Keyframes: {keyframes_updated} prompt(s) synced)")

        # Feed back into Bi-Directional Workflow Sync Queue when fixes were applied
        if record_bidirectional:
            workflow_sync.record_modification(
                pd,
                slug,
                source_step=12,
                summary=f"Shot continuity & scale audit ({len(all_fixes)} fix(es) across {', '.join(sorted(touched_scene_ids)[:4])})",
                origin_step=17,
                include_upstream=False,
            )

    return {
        "ok": True,
        "engine": engine_used,
        "scenes_audited": len(target_scenes),
        "scenes_updated": sorted(touched_scene_ids),
        "fixes_applied": len(all_fixes),
        "fixes": all_fixes,
        "ambiguous": ambiguous_items,
        "ambiguous_count": len(ambiguous_items),
        "scorecard": scorecard,
        "blind_spots": blind_spots,
        "keyframes_updated": keyframes_updated,
        "keyframes_skipped_locked": keyframes_skipped_locked,
        "updated_steps": updated_steps,
    }
