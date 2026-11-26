"""Surgical, bidirectional real-time continuity sync across Studio V2 steps.

Propagates ONLY the exact entity/field that the user modified to all related
previous and following steps, while strictly preserving unmodified scenes,
unmodified characters, unmodified fields, and locked keyframes.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import adaptation as ad
import cast_lock
import character_identity
import character_tokens
import continuity_book

log = logging.getLogger("studio.sync")

_HEADING_RE = re.compile(r"^(INT\.\/EXT\.|EXT\.\/INT\.|INT\.|EXT\.)\s*(.+?)(?:\s*-\s*(.+))?$", re.IGNORECASE)
_WARDROBE_TAG_RE = re.compile(r"\[Wardrobe\s+([^:\]]+):\s*[^\]]*\]", re.IGNORECASE)


def _empty_report() -> dict[str, Any]:
    return {"updated_steps": [], "changes": [], "preserved": []}


def _record(report: dict[str, Any], step: str, detail: str) -> None:
    if step and step not in report["updated_steps"]:
        report["updated_steps"].append(step)
    if detail:
        report["changes"].append(detail)


def _preserve(report: dict[str, Any], detail: str) -> None:
    if detail and detail not in report["preserved"]:
        report["preserved"].append(detail)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, data: Any, *, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=indent, ensure_ascii=False), encoding="utf-8")


def _continuity_paths(pd: Path, slug: str) -> list[Path]:
    out: list[Path] = []
    for p in (continuity_book.continuity_file(pd), pd / f"{slug}.json", pd / "continuity.json"):
        if p.is_file() and p.resolve() not in {x.resolve() for x in out}:
            out.append(p)
    return out


def parse_scene_ids(spec: str, all_scene_ids: list[str]) -> list[str]:
    """Resolve a human scene selector (`S005`, `S005-S008`, `Scenes 2-4`, `All Scenes`) to matching scene IDs."""
    raw = str(spec or "").strip()
    if not raw or not all_scene_ids:
        return []
    low = raw.lower()
    if "all scene" in low or low in ("all", "*"):
        return list(all_scene_ids)

    num_to_id: dict[int, str] = {}
    id_by_low: dict[str, str] = {}
    for sid in all_scene_ids:
        id_by_low[sid.lower()] = sid
        m = re.search(r"(\d+)", sid)
        if m:
            num_to_id[int(m.group(1))] = sid

    matched: list[str] = []

    def _add(sid: str) -> None:
        if sid and sid not in matched:
            matched.append(sid)

    # 1. Explicit ranges like "S005-S008", "Scenes 5-8", "5 to 8"
    for m in re.finditer(r"(?:s|scene\s*)?0*(\d+)\s*(?:-|–|—|to)\s*(?:s|scene\s*)?0*(\d+)", raw, re.IGNORECASE):
        a, b = int(m.group(1)), int(m.group(2))
        lo, hi = (a, b) if a <= b else (b, a)
        for n in range(lo, hi + 1):
            if n in num_to_id:
                _add(num_to_id[n])

    # 2. Explicit IDs like "S005" or "Scene 5"
    for m in re.finditer(r"\bS0*(\d+)\b|\bscene\s*0*(\d+)\b", raw, re.IGNORECASE):
        n = int(m.group(1) or m.group(2))
        if n in num_to_id:
            _add(num_to_id[n])

    # 3. Bare comma/space numbers if still empty (e.g. "1, 3, 5")
    if not matched and re.fullmatch(r"[\d,\s]+", raw):
        for tok in re.findall(r"\d+", raw):
            n = int(tok)
            if n in num_to_id:
                _add(num_to_id[n])

    # 4. Exact case-insensitive scene id match
    if not matched and low in id_by_low:
        _add(id_by_low[low])

    return matched


def _shot_mentions_character(sh: dict[str, Any], char_name: str, overrides: dict[str, str]) -> bool:
    target_key = character_identity.canonical_character_key(char_name, overrides=overrides)
    for ch in sh.get("characters") or []:
        if character_identity.canonical_character_key(str(ch), overrides=overrides) == target_key:
            return True
    blob = f"{sh.get('composition') or ''} {sh.get('action') or ''}".lower()
    base_word = target_key.replace("_", " ").strip()
    return bool(base_word and re.search(rf"\b{re.escape(base_word)}\b", blob))


def _apply_character_wardrobe_to_text(text: str, char_name: str, new_wardrobe: str, old_wardrobe: str = "") -> str:
    """Surgically update ONLY `char_name`'s wardrobe clause in a prompt/shot string without altering other text."""
    cur = str(text or "").strip()
    new_w = str(new_wardrobe or "").strip()
    old_w = str(old_wardrobe or "").strip()

    # Replace existing structured tag for this character if present
    tag_pat = re.compile(rf"\[Wardrobe\s+{re.escape(char_name)}:\s*[^\]]*\]", re.IGNORECASE)
    if tag_pat.search(cur):
        if new_w:
            return tag_pat.sub(f"[Wardrobe {char_name}: {new_w}]", cur).strip()
        return re.sub(r"\s{2,}", " ", tag_pat.sub("", cur)).strip()

    # Exact phrase replacement if old wardrobe text is embedded verbatim
    if old_w and len(old_w) >= 4 and old_w.lower() in cur.lower():
        pat = re.compile(re.escape(old_w), re.IGNORECASE)
        replaced = pat.sub(new_w, cur, count=1) if new_w else re.sub(r"\s{2,}", " ", pat.sub("", cur, count=1))
        return replaced.strip()

    if not new_w or not cur:
        return cur
    sep = " " if cur.endswith((".", "!", "?", "]")) else ". "
    return f"{cur}{sep}[Wardrobe {char_name}: {new_w}]"


def _replace_phrase_ci(text: str, old_phrase: str, new_phrase: str) -> tuple[str, bool]:
    """Case-insensitive exact phrase replacement; returns (updated_text, changed)."""
    src = str(text or "")
    old_p = str(old_phrase or "").strip()
    new_p = str(new_phrase or "").strip()
    if not src or not old_p or len(old_p) < 4 or old_p.lower() == new_p.lower():
        return src, False
    if old_p.lower() not in src.lower():
        return src, False
    updated = re.sub(re.escape(old_p), new_p, src, flags=re.IGNORECASE)
    updated = re.sub(r"\s{2,}", " ", updated).strip()
    return updated, (updated != src)


def sync_scene_wardrobe(
    pd: Path,
    slug: str,
    *,
    character: str,
    scene_ids: list[str] | None = None,
    scene_spec: str = "",
    wardrobe_text: str = "",
    old_wardrobe: str = "",
    location: str = "",
    reference: str = "",
    source_step: str = "",
) -> dict[str, Any]:
    """Propagate a per-scene character wardrobe change across Steps 07, 08, 10, 12, and 17.

    Modifies ONLY `character` in the affected scene(s), preserving all other characters,
    all other scenes, and any locked Step 17 keyframes.
    """
    report = _empty_report()
    char = str(character or "").strip()
    if not char:
        return report

    plan = ad.load(pd)
    all_plan_sids = [str(s["id"]) for s in (ad.active_scenes(plan) if plan else [])]
    sl_path = pd / "shots" / "shotlist.json"
    sl = _read_json(sl_path) if sl_path.is_file() else None
    all_sl_sids = [str(sc.get("id") or "") for sc in ((sl or {}).get("scenes") or []) if sc.get("id")]
    known_sids = all_plan_sids or all_sl_sids

    target_sids = [str(s).strip() for s in (scene_ids or []) if str(s).strip()]
    if not target_sids and scene_spec:
        target_sids = parse_scene_ids(scene_spec, known_sids)
    # Also match scenes by location when scene_spec was omitted or matched nothing
    if not target_sids and location and plan:
        loc_low = location.strip().lower()
        target_sids = [str(s["id"]) for s in ad.active_scenes(plan) if str(s.get("location") or "").strip().lower() == loc_low]

    new_w = str(wardrobe_text or "").strip()
    old_w = str(old_wardrobe or "").strip()
    overrides = character_identity.load_identity_overrides(pd)

    # 1. Step 07 (cast_lock.json) — when edited from Step 08 / Step 10
    if source_step != "step07" and plan and target_sids:
        lock = cast_lock.load(pd)
        valid_plan_sids = {str(s["id"]) for s in plan.get("scenes") or []}
        locked_count = 0
        for sid in target_sids:
            if sid not in valid_plan_sids:
                continue
            existing_entry = ((lock.get(sid) or {}).get("characters") or {}).get(char) or {}
            existing_ref = str(reference or existing_entry.get("reference") or "")
            tok = new_w[: cast_lock.TOKEN_MAX]
            try:
                cast_lock.set_lock(pd, plan, sid, "character", char, tok, existing_ref)
                locked_count += 1
            except cast_lock.LockError as e:
                log.debug("cast_lock sync skipped for %s/%s: %s", sid, char, e)
        if locked_count:
            _record(report, "Step 07 (Scene Continuity Locks)", f"Updated {char} wardrobe lock in {locked_count} scene(s) ({', '.join(target_sids[:4])})")

    # 2. Step 08 & Step 10 (wardrobe_states.json) — when edited from Step 07
    if source_step != "step08" and target_sids:
        ws_path = pd / "wardrobe_states.json"
        ws_data = _read_json(ws_path)
        ws: dict[str, Any] = ws_data if isinstance(ws_data, dict) else {}
        ws_key = next((k for k in ws if k.lower() == char.lower()), char)
        states = list(ws.get(ws_key) or []) if isinstance(ws.get(ws_key), list) else []
        changed_ws = False
        for sid in target_sids:
            sid_low = sid.lower()
            loc_for_sid = location
            if not loc_for_sid and plan:
                hit_sc = next((s for s in plan.get("scenes") or [] if str(s.get("id") or "").lower() == sid_low), None)
                if hit_sc:
                    loc_for_sid = str(hit_sc.get("location") or "")
            hit_idx = next(
                (i for i, st in enumerate(states) if isinstance(st, dict) and str(st.get("scenes") or "").strip().lower() == sid_low),
                -1,
            )
            if new_w:
                entry = {"scenes": sid, "location": loc_for_sid, "wardrobe": new_w}
                if hit_idx >= 0:
                    if states[hit_idx].get("wardrobe") != new_w or (loc_for_sid and states[hit_idx].get("location") != loc_for_sid):
                        states[hit_idx] = {**states[hit_idx], **entry}
                        changed_ws = True
                else:
                    states.append(entry)
                    changed_ws = True
            elif hit_idx >= 0:
                states.pop(hit_idx)
                changed_ws = True
        if changed_ws:
            ws[ws_key] = states
            _write_json(ws_path, ws)
            _record(report, "Step 08 (Cast Wardrobe) & Step 10 (Turnarounds)", f"Synced {char} outfit state for {', '.join(target_sids[:4])}")

    # 3. Step 12 (shots/shotlist.json) — ONLY shots in target_sids featuring `character`
    affected_shot_ids: set[str] = set()
    if isinstance(sl, dict) and target_sids:
        target_set = {s.lower() for s in target_sids}
        sl_changed = 0
        for sc in sl.get("scenes") or []:
            sc_id = str(sc.get("id") or "")
            if sc_id.lower() not in target_set:
                continue
            for sh in sc.get("shots") or []:
                if not isinstance(sh, dict) or not _shot_mentions_character(sh, char, overrides):
                    continue
                sid_shot = f"{sc_id}-{int(sh.get('n') or 0):02d}"
                affected_shot_ids.add(sid_shot)
                comp = str(sh.get("composition") or "")
                new_comp = _apply_character_wardrobe_to_text(comp, char, new_w, old_w)
                if new_comp != comp:
                    sh["composition"] = new_comp
                    sl_changed += 1
        if sl_changed:
            _write_json(sl_path, sl, indent=1)
            _record(report, "Step 12 (Shot List)", f"Updated {char} wardrobe in {sl_changed} shot(s)")

    # 4. Step 17 (keyframes_v2.json) — ONLY unlocked prompts in target_sids featuring `character`
    kf_path = pd / "keyframes_v2.json"
    kf_meta = _read_json(kf_path)
    if isinstance(kf_meta, dict) and target_sids:
        locked_set = {str(x) for x in (kf_meta.get("locked") or [])}
        prompts = dict(kf_meta.get("prompts") or {})
        target_prefixes = tuple(f"{s}-".lower() for s in target_sids)
        kf_changed = 0
        for shot_id, p_txt in list(prompts.items()):
            sid_low = str(shot_id).lower()
            if not sid_low.startswith(target_prefixes):
                continue
            if affected_shot_ids and shot_id not in affected_shot_ids:
                # Only touch shots in this scene that actually mention this character
                base_word = character_identity.canonical_character_key(char, overrides=overrides).replace("_", " ").strip()
                if not (base_word and re.search(rf"\b{re.escape(base_word)}\b", str(p_txt or "").lower())):
                    continue
            if shot_id in locked_set:
                _preserve(report, f"Locked keyframe {shot_id} preserved untouched")
                continue
            updated_p = _apply_character_wardrobe_to_text(str(p_txt or ""), char, new_w, old_w)
            if updated_p != str(p_txt or ""):
                prompts[shot_id] = updated_p
                kf_changed += 1
        if kf_changed:
            kf_meta["prompts"] = prompts
            _write_json(kf_path, kf_meta)
            _record(report, "Step 17 (Storyboard Keyframes)", f"Updated {kf_changed} unlocked keyframe prompt(s)")

    return report


def sync_character_profile(
    pd: Path,
    slug: str,
    *,
    name: str,
    old_token: str = "",
    new_token: str = "",
    old_voice: str = "",
    new_voice: str = "",
    source_step: str = "",
) -> dict[str, Any]:
    """Propagate a character profile/token/voice edit bidirectionally without touching unmodified fields."""
    report = _empty_report()
    cname = str(name or "").strip()
    if not cname:
        return report

    tok_changed = bool(new_token.strip()) and new_token.strip() != old_token.strip()
    voice_changed = bool(new_voice.strip()) and new_voice.strip() != old_voice.strip()
    if not tok_changed and not voice_changed:
        return report

    # 1. Step 07 Continuity Book (when edited outside Step 07)
    if source_step != "step07":
        cb_updated = False
        for cb_path in _continuity_paths(pd, slug):
            cb = _read_json(cb_path)
            if not isinstance(cb, dict):
                continue
            chars = list(cb.get("characters") or [])
            hit = next((c for c in chars if isinstance(c, dict) and str(c.get("name") or "").strip().lower() == cname.lower()), None)
            if hit is None:
                continue
            changed_this = False
            if tok_changed:
                clean_tok = new_token.strip()[:198]
                if hit.get("token") != clean_tok:
                    hit["token"] = clean_tok
                    changed_this = True
            if voice_changed and hit.get("voice") != new_voice.strip():
                hit["voice"] = new_voice.strip()
                changed_this = True
            if changed_this:
                cb["characters"] = chars
                _write_json(cb_path, cb, indent=1)
                cb_updated = True
        if cb_updated:
            _record(report, "Step 07 (Continuity Book)", f"Updated {cname} in continuity book")

    # 2. Step 08 Character Dossier (and Step 10 Turnarounds, which read Step 08 live)
    if source_step != "step08":
        existing_ch = character_tokens.load_character(slug, cname)
        if isinstance(existing_ch, dict):
            ch_changed = False
            if tok_changed and existing_ch.get("visual_token") != new_token.strip():
                existing_ch["visual_token"] = new_token.strip()
                ch_changed = True
            if voice_changed and existing_ch.get("voice") != new_voice.strip():
                existing_ch["voice"] = new_voice.strip()
                ch_changed = True
            if ch_changed:
                character_tokens.save_character(existing_ch)
                _record(report, "Step 08 (Cast) & Step 10 (Turnarounds)", f"Updated {cname} dossier")

    # 3. Step 03 Coverage (only matching character's description if token changed)
    if tok_changed:
        cov_path = pd / "readin" / "coverage.json"
        cov = _read_json(cov_path)
        if isinstance(cov, dict) and isinstance(cov.get("characters"), list):
            cov_changed = False
            for c in cov["characters"]:
                if isinstance(c, dict) and str(c.get("name") or "").strip().lower() == cname.lower():
                    if str(c.get("description") or "").strip() != new_token.strip():
                        c["description"] = new_token.strip()
                        cov_changed = True
            if cov_changed:
                _write_json(cov_path, cov)
                _record(report, "Step 03 (Coverage)", f"Updated {cname} description in coverage")

    # 4. Step 12 Shot List & Step 17 Unlocked Keyframes — ONLY surgical old_token -> new_token replacement
    if tok_changed and old_token.strip() and len(old_token.strip()) >= 4:
        sl_path = pd / "shots" / "shotlist.json"
        sl = _read_json(sl_path)
        if isinstance(sl, dict):
            sl_hits = 0
            for sc in sl.get("scenes") or []:
                for sh in sc.get("shots") or []:
                    if not isinstance(sh, dict):
                        continue
                    for fld in ("composition", "action"):
                        nxt, chg = _replace_phrase_ci(str(sh.get(fld) or ""), old_token, new_token)
                        if chg:
                            sh[fld] = nxt
                            sl_hits += 1
            if sl_hits:
                _write_json(sl_path, sl, indent=1)
                _record(report, "Step 12 (Shot List)", f"Updated {cname} description in {sl_hits} shot field(s)")

        kf_path = pd / "keyframes_v2.json"
        kf_meta = _read_json(kf_path)
        if isinstance(kf_meta, dict) and isinstance(kf_meta.get("prompts"), dict):
            locked_set = {str(x) for x in (kf_meta.get("locked") or [])}
            prompts = dict(kf_meta["prompts"])
            kf_hits = 0
            for shot_id, p_txt in list(prompts.items()):
                nxt, chg = _replace_phrase_ci(str(p_txt or ""), old_token, new_token)
                if not chg:
                    continue
                if shot_id in locked_set:
                    _preserve(report, f"Locked keyframe {shot_id} preserved untouched")
                    continue
                prompts[shot_id] = nxt
                kf_hits += 1
            if kf_hits:
                kf_meta["prompts"] = prompts
                _write_json(kf_path, kf_meta)
                _record(report, "Step 17 (Storyboard Keyframes)", f"Updated {cname} in {kf_hits} unlocked keyframe prompt(s)")

    if voice_changed:
        _record(report, "Step 14 (Voice Casting)", f"Synced {cname} voice to {new_voice.strip()}")

    return report


def sync_location_change(
    pd: Path,
    slug: str,
    *,
    name: str,
    old_desc: str = "",
    new_desc: str = "",
    lighting: str = "",
    source_step: str = "",
) -> dict[str, Any]:
    """Propagate a location/set edit bidirectionally between Step 07, Step 11, Step 12, and Step 17."""
    report = _empty_report()
    lname = str(name or "").strip()
    if not lname:
        return report

    combined_tok = new_desc.strip()
    if lighting.strip() and lighting.strip().lower() not in combined_tok.lower():
        combined_tok = f"{combined_tok}. Lighting: {lighting.strip()}".strip(". ")

    # 1. Step 07 Continuity Book (when edited in Step 11)
    if source_step != "step07" and combined_tok:
        cb_paths = _continuity_paths(pd, slug)
        cb_updated = False
        for cb_path in cb_paths:
            cb = _read_json(cb_path)
            if not isinstance(cb, dict):
                continue
            locs = list(cb.get("locations") or [])
            hit = next(
                (x for x in locs if isinstance(x, dict) and str(x.get("name") or x.get("location") or "").strip().lower() == lname.lower()),
                None,
            )
            short_tok = combined_tok[:198]
            if hit is not None:
                if hit.get("token") != short_tok or hit.get("description") != new_desc.strip() or hit.get("lighting") != lighting.strip():
                    hit["token"] = short_tok
                    if new_desc.strip():
                        hit["description"] = new_desc.strip()
                    if lighting.strip():
                        hit["lighting"] = lighting.strip()
                    cb["locations"] = locs
                    _write_json(cb_path, cb, indent=1)
                    cb_updated = True
            else:
                entry: dict[str, Any] = {"name": lname, "token": short_tok}
                if new_desc.strip():
                    entry["description"] = new_desc.strip()
                if lighting.strip():
                    entry["lighting"] = lighting.strip()
                locs.append(entry)
                cb["locations"] = locs
                _write_json(cb_path, cb, indent=1)
                cb_updated = True
        if cb_updated:
            _record(report, "Step 07 (Continuity Book)", f"Updated location {lname} in continuity book")

    # 2. Step 11 persisted custom set details (when edited in Step 07)
    if source_step != "step11" and (new_desc.strip() or lighting.strip()):
        sets_meta_path = pd / "sets_custom.json"
        sm = _read_json(sets_meta_path)
        sets_map: dict[str, Any] = sm if isinstance(sm, dict) else {}
        k = lname.lower()
        cur_entry = dict(sets_map.get(k) or {"name": lname})
        if new_desc.strip():
            cur_entry["description"] = new_desc.strip()
        if lighting.strip():
            cur_entry["lighting"] = lighting.strip()
        sets_map[k] = cur_entry
        _write_json(sets_meta_path, sets_map)
        _record(report, "Step 11 (Locations & Sets)", f"Updated set details for {lname}")

    # 3. Step 12 Shot List & Step 17 Unlocked Keyframes — ONLY surgical old_desc -> new_desc in scenes at this location
    if old_desc.strip() and new_desc.strip() and old_desc.strip().lower() != new_desc.strip().lower():
        sl_path = pd / "shots" / "shotlist.json"
        sl = _read_json(sl_path)
        matching_sids: set[str] = set()
        if isinstance(sl, dict):
            sl_hits = 0
            for sc in sl.get("scenes") or []:
                sc_id = str(sc.get("id") or "")
                heading = str(sc.get("heading") or "").lower()
                if lname.lower() not in heading:
                    continue
                matching_sids.add(sc_id.lower())
                for sh in sc.get("shots") or []:
                    if not isinstance(sh, dict):
                        continue
                    nxt, chg = _replace_phrase_ci(str(sh.get("composition") or ""), old_desc, new_desc)
                    if chg:
                        sh["composition"] = nxt
                        sl_hits += 1
            if sl_hits:
                _write_json(sl_path, sl, indent=1)
                _record(report, "Step 12 (Shot List)", f"Updated {lname} in {sl_hits} shot(s)")

        kf_path = pd / "keyframes_v2.json"
        kf_meta = _read_json(kf_path)
        if isinstance(kf_meta, dict) and isinstance(kf_meta.get("prompts"), dict):
            locked_set = {str(x) for x in (kf_meta.get("locked") or [])}
            prompts = dict(kf_meta["prompts"])
            kf_hits = 0
            for shot_id, p_txt in list(prompts.items()):
                if matching_sids and not any(str(shot_id).lower().startswith(f"{s}-") for s in matching_sids):
                    continue
                nxt, chg = _replace_phrase_ci(str(p_txt or ""), old_desc, new_desc)
                if not chg:
                    continue
                if shot_id in locked_set:
                    _preserve(report, f"Locked keyframe {shot_id} preserved untouched")
                    continue
                prompts[shot_id] = nxt
                kf_hits += 1
            if kf_hits:
                kf_meta["prompts"] = prompts
                _write_json(kf_path, kf_meta)
                _record(report, "Step 17 (Storyboard Keyframes)", f"Updated {lname} in {kf_hits} unlocked keyframe prompt(s)")

    return report


def sync_scene_edit(
    pd: Path,
    slug: str,
    *,
    scene_id: str,
    old_scene: dict[str, Any] | None = None,
    new_scene: dict[str, Any] | None = None,
    heading: str = "",
    elements: list[dict[str, Any]] | None = None,
    source_step: str = "",
) -> dict[str, Any]:
    """Propagate a single scene edit bidirectionally between Step 05, Step 06, Step 12, and Step 15."""
    report = _empty_report()
    sid = str(scene_id or "").strip()
    if not sid:
        return report

    # Direction A: Step 05 (Adaptation Plan) -> Step 06 (Screenplay heading) & Step 12 (Shot List heading)
    if source_step == "step05" and isinstance(new_scene, dict):
        old_loc = str((old_scene or {}).get("location") or "").strip()
        new_loc = str(new_scene.get("location") or "").strip()
        old_title = str((old_scene or {}).get("title") or "").strip()
        new_title = str(new_scene.get("title") or "").strip()

        if new_loc and new_loc.lower() != old_loc.lower():
            sp_path = pd / "screenplay" / f"scene-{sid}.json"
            sc_doc = _read_json(sp_path)
            if isinstance(sc_doc, dict) and sc_doc.get("heading"):
                cur_h = str(sc_doc["heading"])
                m = _HEADING_RE.match(cur_h.strip())
                if m:
                    prefix, _place, tod = m.group(1), m.group(2), m.group(3)
                    sc_doc["heading"] = f"{prefix.upper()} {new_loc.upper()}" + (f" - {tod.upper()}" if tod else "")
                else:
                    sc_doc["heading"] = f"INT. {new_loc.upper()} - DAY"
                _write_json(sp_path, sc_doc, indent=1)
                _record(report, "Step 06 (Screenplay)", f"Updated {sid} heading location to {new_loc}")

        if (new_loc and new_loc.lower() != old_loc.lower()) or (new_title and new_title != old_title):
            sl_path = pd / "shots" / "shotlist.json"
            sl = _read_json(sl_path)
            if isinstance(sl, dict):
                changed_sl = False
                for sc in sl.get("scenes") or []:
                    if str(sc.get("id") or "") == sid:
                        if new_title and new_title != old_title and sc.get("title") != new_title:
                            sc["title"] = new_title
                            changed_sl = True
                        if new_loc and new_loc.lower() != old_loc.lower() and sc.get("heading"):
                            m = _HEADING_RE.match(str(sc["heading"]).strip())
                            if m:
                                sc["heading"] = f"{m.group(1).upper()} {new_loc.upper()}" + (f" - {m.group(3).upper()}" if m.group(3) else "")
                                changed_sl = True
                if changed_sl:
                    _write_json(sl_path, sl, indent=1)
                    _record(report, "Step 12 (Shot List)", f"Updated {sid} scene header")

    # Direction B: Step 06 (Screenplay) -> Step 05 (Adaptation Plan), Step 12 (Shot List), Step 15 (Dialogue)
    if source_step == "step06":
        new_loc = ""
        new_tod = ""
        if heading:
            m = _HEADING_RE.match(heading.strip())
            if m:
                new_loc = m.group(2).strip()
                new_tod = (m.group(3) or "").strip()

        speakers: list[str] = []
        dlg_rows: list[dict[str, str]] = []
        for el in (elements or []):
            if isinstance(el, dict) and el.get("type") == "dialogue":
                sp_char = str(el.get("character") or "").strip()
                sp_txt = str(el.get("text") or "").strip()
                sp_note = str(el.get("note") or "").strip()
                if sp_char and sp_char.lower() not in {x.lower() for x in speakers}:
                    speakers.append(sp_char)
                if sp_char and sp_txt:
                    dlg_rows.append({"character": sp_char, "text": sp_txt, "note": sp_note})

        # 1. Step 05 (adaptation.json): update ONLY this scene's changed location/time and add any newly introduced speakers
        plan = ad.load(pd)
        if plan:
            plan_changed = False
            for sc in plan.get("scenes") or []:
                if str(sc.get("id") or "") != sid:
                    continue
                if new_loc and str(sc.get("location") or "").strip().lower() != new_loc.lower():
                    sc["location"] = new_loc
                    plan_changed = True
                if new_tod and str(sc.get("time_of_day") or "").strip().lower() != new_tod.lower():
                    sc["time_of_day"] = new_tod
                    plan_changed = True
                existing_chars = [str(x) for x in (sc.get("characters") or [])]
                existing_low = {x.lower() for x in existing_chars}
                for sp_c in speakers:
                    if sp_c.lower() not in existing_low:
                        existing_chars.append(sp_c)
                        existing_low.add(sp_c.lower())
                        plan_changed = True
                if plan_changed:
                    sc["characters"] = existing_chars
                break
            if plan_changed:
                try:
                    ad.save(pd, plan)
                except (KeyError, ValueError):
                    _write_json(ad.adapt_dir(pd) / "adaptation.json", plan, indent=1)
                _record(report, "Step 05 (Story Breakdown) & Step 11 (Sets)", f"Synced {sid} location/cast from screenplay")

        # 2. Step 12 (shots/shotlist.json): update ONLY this scene's heading if changed
        if heading:
            sl_path = pd / "shots" / "shotlist.json"
            sl = _read_json(sl_path)
            if isinstance(sl, dict):
                changed_sl = False
                for sc in sl.get("scenes") or []:
                    if str(sc.get("id") or "") == sid and str(sc.get("heading") or "").strip() != heading.strip():
                        sc["heading"] = heading.strip()
                        changed_sl = True
                if changed_sl:
                    _write_json(sl_path, sl, indent=1)
                    _record(report, "Step 12 (Shot List)", f"Updated {sid} heading in shot list")

        # 3. Step 15 (dialogue_lines.json): update ONLY this scene's dialogue lines, preserving other scenes & voice settings
        dlg_path = pd / "dialogue_lines.json"
        dlg_data = _read_json(dlg_path)
        if isinstance(dlg_data, dict) and isinstance(dlg_data.get("lines"), list) and dlg_rows:
            existing_lines = list(dlg_data["lines"])
            # Preserve per-line audio/voice metadata for this scene by index
            scene_old = [ln for ln in existing_lines if isinstance(ln, dict) and str(ln.get("scene") or "") == sid]
            other_lines = [ln for ln in existing_lines if not (isinstance(ln, dict) and str(ln.get("scene") or "") == sid)]
            rebuilt_scene: list[dict[str, Any]] = []
            for idx, row in enumerate(dlg_rows, start=1):
                prev = scene_old[idx - 1] if idx - 1 < len(scene_old) else {}
                rebuilt_scene.append({
                    **prev,
                    "id": str(prev.get("id") or f"{sid}-L{idx:02d}"),
                    "scene": sid,
                    "character": row["character"],
                    "text": row["text"],
                    "note": row["note"],
                })
            if rebuilt_scene != scene_old:
                # Re-insert at the original scene position so scene order stays unchanged
                first_pos = next((i for i, ln in enumerate(existing_lines) if isinstance(ln, dict) and str(ln.get("scene") or "") == sid), len(other_lines))
                merged = other_lines[:first_pos] + rebuilt_scene + other_lines[first_pos:]
                dlg_data["lines"] = merged
                _write_json(dlg_path, dlg_data)
                _record(report, "Step 15 (Spoken Dialogue)", f"Synced {len(rebuilt_scene)} dialogue line(s) for {sid}")

    return report


def sync_shot_edit(
    pd: Path,
    slug: str,
    *,
    scene_id: str,
    shot_n: int,
    fields: dict[str, Any],
) -> dict[str, Any]:
    """Propagate a Step 12 shot edit to Step 17 (only if that shot is unlocked) without touching other shots."""
    report = _empty_report()
    sid = str(scene_id or "").strip()
    if not sid or shot_n <= 0 or not fields:
        return report

    shot_id = f"{sid}-{shot_n:02d}"
    kf_path = pd / "keyframes_v2.json"
    kf_meta = _read_json(kf_path)
    if not isinstance(kf_meta, dict):
        return report

    locked_set = {str(x) for x in (kf_meta.get("locked") or [])}
    if shot_id in locked_set:
        _preserve(report, f"Locked keyframe {shot_id} preserved untouched")
        return report

    sl_path = pd / "shots" / "shotlist.json"
    sl = _read_json(sl_path)
    shot_obj = None
    if isinstance(sl, dict):
        for sc in sl.get("scenes") or []:
            if str(sc.get("id") or "") == sid:
                for sh in sc.get("shots") or []:
                    if int(sh.get("n") or 0) == shot_n:
                        shot_obj = sh
                        break
                break
    if not isinstance(shot_obj, dict):
        return report

    if any(
        k in fields
        for k in (
            "type",
            "composition",
            "action",
            "camera",
            "lens",
            "lens_mm",
            "height",
            "movement",
            "lighting",
            "angle",
            "camera_motion",
            "camera_notes",
            "subject_action",
        )
    ):
        new_prompt = ""
        try:
            from studio_app import keyframe_context

            ctx = keyframe_context.load_keyframe_project_context(slug, pd)
            heading = ""
            if isinstance(sl, dict):
                for sc in sl.get("scenes") or []:
                    if str(sc.get("id") or "") == sid:
                        heading = str(sc.get("heading") or "")
                        break
            info = keyframe_context.build_shot_keyframe_info(shot_obj, sid, heading, ctx)
            new_prompt = str(info.get("default_prompt") or "").strip()
        except Exception:
            new_prompt = ""
        if not new_prompt:
            parts = [
                str(shot_obj.get("type") or "").strip(),
                str(shot_obj.get("composition") or "").strip(),
                str(shot_obj.get("action") or "").strip(),
                str(shot_obj.get("camera_notes") or shot_obj.get("lighting") or "").strip(),
            ]
            new_prompt = ". ".join(p.rstrip(". ") for p in parts if p)
        prompts = dict(kf_meta.get("prompts") or {})
        if new_prompt and prompts.get(shot_id) != new_prompt:
            prompts[shot_id] = new_prompt
            kf_meta["prompts"] = prompts
            _write_json(kf_path, kf_meta)
            _record(report, "Step 17 (Storyboard Keyframes)", f"Updated unlocked prompt for shot {shot_id}")

    return report
