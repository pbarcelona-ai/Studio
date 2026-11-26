"""Image-to-text analysis of baselined Step 11 set plates with automatic feedback to Steps 07, 11, 12, and 17.

When a user imports a real photo for a Step 11 set, converts it to the film's visual style,
and pins it as the Baseline, the actual room architecture, window placement, furniture, and
lighting often differ from the original book/screenplay assumptions.

This module translates the baselined set image into structured visual text (preferring free
local Ollama Vision, then Gemini Vision when configured) and propagates it cleanly to:
  - Step 11 (`sets_custom.json`, `sets_views.json`)
  - Step 07 (`Continuity Book` location entry)
  - Step 12 (`shots/shotlist.json` scene metadata + surgical composition reconciliation)
  - Step 17 (`keyframes_v2.json` unlocked shot prompts rebuilt via `keyframe_context`)
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("studio.set_vision_sync")

_LEADING_ARTICLES_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _norm_loc(text: str) -> str:
    s = _NON_ALNUM_RE.sub(" ", str(text or "").lower()).strip()
    return _LEADING_ARTICLES_RE.sub("", s).strip()


def find_earliest_character_inception(pd: Path, slug: str, char_name: str) -> int:
    """Find the earliest pipeline step (3, 5, 6, 7, or 8) where `char_name` first appears."""
    import continuity_book

    target = str(char_name or "").strip().lower()
    if not target:
        return 7
    word_re = re.compile(rf"\b{re.escape(target)}\b", re.IGNORECASE)

    # Step 03: Coverage (`readin/coverage.json`)
    cov_path = pd / "readin" / "coverage.json"
    if cov_path.is_file():
        try:
            cov = json.loads(cov_path.read_text(encoding="utf-8")) or {}
            for c in cov.get("characters") or []:
                cname = str(c.get("name") if isinstance(c, dict) else c or "").strip().lower()
                if cname == target or (len(target) >= 3 and word_re.search(cname)):
                    return 3
            if word_re.search(str(cov.get("logline") or "")) or any(word_re.search(str(e)) for e in (cov.get("key_events") or [])):
                return 3
        except (OSError, ValueError):
            pass

    # Step 05: Beats / Adaptation (`adaptation/adaptation.json`)
    adapt_path = pd / "adaptation" / "adaptation.json"
    if adapt_path.is_file():
        try:
            ad = json.loads(adapt_path.read_text(encoding="utf-8")) or {}
            for sc in ad.get("scenes") or []:
                if not isinstance(sc, dict):
                    continue
                if any(str(ch).strip().lower() == target for ch in (sc.get("characters") or [])):
                    return 5
                if word_re.search(str(sc.get("summary") or "")) or word_re.search(str(sc.get("title") or "")):
                    return 5
        except (OSError, ValueError):
            pass

    # Step 06: Screenplay (`screenplay/scene-*.json`)
    sp_dir = pd / "screenplay"
    if sp_dir.is_dir():
        for sp_f in sorted(sp_dir.glob("scene-*.json")):
            try:
                sc = json.loads(sp_f.read_text(encoding="utf-8")) or {}
                for el in sc.get("elements") or []:
                    if not isinstance(el, dict):
                        continue
                    if str(el.get("character") or "").strip().lower() == target or word_re.search(str(el.get("text") or "")):
                        return 6
            except (OSError, ValueError):
                continue

    # Step 07: Continuity Book
    for cb_p in (continuity_book.continuity_file(pd), pd / f"{slug}.json", pd / "continuity.json"):
        if cb_p.is_file():
            try:
                cb = json.loads(cb_p.read_text(encoding="utf-8")) or {}
                if any(isinstance(c, dict) and str(c.get("name") or "").strip().lower() == target for c in (cb.get("characters") or [])):
                    return 7
            except (OSError, ValueError):
                continue

    return 7


def find_earliest_set_inception(pd: Path, slug: str, set_name: str) -> int:
    """Find the earliest pipeline step (3, 5, 6, 7, or 11) where `set_name` first appears."""
    import continuity_book

    norm_target = _norm_loc(set_name)
    if not norm_target:
        return 7
    word_re = re.compile(rf"\b{re.escape(norm_target)}\b", re.IGNORECASE)

    # Step 03: Coverage (`readin/coverage.json`)
    cov_path = pd / "readin" / "coverage.json"
    if cov_path.is_file():
        try:
            cov = json.loads(cov_path.read_text(encoding="utf-8")) or {}
            blob = " ".join([
                str(cov.get("logline") or ""),
                str(cov.get("filmable") or ""),
                " ".join(str(e) for e in (cov.get("key_events") or [])),
            ])
            if word_re.search(_norm_loc(blob)):
                return 3
        except (OSError, ValueError):
            pass

    # Step 05: Beats / Adaptation (`adaptation/adaptation.json`)
    adapt_path = pd / "adaptation" / "adaptation.json"
    if adapt_path.is_file():
        try:
            ad = json.loads(adapt_path.read_text(encoding="utf-8")) or {}
            for sc in ad.get("scenes") or []:
                if not isinstance(sc, dict):
                    continue
                if _norm_loc(str(sc.get("location") or "")) == norm_target or word_re.search(_norm_loc(f"{sc.get('title') or ''} {sc.get('summary') or ''}")):
                    return 5
        except (OSError, ValueError):
            pass

    # Step 06: Screenplay (`screenplay/scene-*.json`)
    sp_dir = pd / "screenplay"
    if sp_dir.is_dir():
        for sp_f in sorted(sp_dir.glob("scene-*.json")):
            try:
                sc = json.loads(sp_f.read_text(encoding="utf-8")) or {}
                if _heading_matches_location(str(sc.get("heading") or ""), norm_target):
                    return 6
                for el in sc.get("elements") or []:
                    if isinstance(el, dict) and word_re.search(_norm_loc(str(el.get("text") or ""))):
                        return 6
            except (OSError, ValueError):
                continue

    # Step 07: Continuity Book
    for cb_p in (continuity_book.continuity_file(pd), pd / f"{slug}.json", pd / "continuity.json"):
        if cb_p.is_file():
            try:
                cb = json.loads(cb_p.read_text(encoding="utf-8")) or {}
                if any(isinstance(loc, dict) and _norm_loc(str(loc.get("name") or "")) == norm_target for loc in (cb.get("locations") or [])):
                    return 7
            except (OSError, ValueError):
                continue

    return 7


def record_import_bidirectional_sync(
    pd: Path,
    slug: str,
    *,
    kind: str,
    name: str,
    source_step: int,
) -> dict[str, Any]:
    """Queue a bi-directional workflow update starting at the earliest pipeline inception of `name`."""
    from studio_app import workflow_sync

    earliest = (
        find_earliest_character_inception(pd, slug, name)
        if kind == "character"
        else find_earliest_set_inception(pd, slug, name)
    )
    candidate_upstream = [3, 5, 6, 7] if kind == "character" else [3, 5, 6, 7]
    upstream_steps: list[int] = []
    for st in candidate_upstream:
        if earliest <= st < source_step and (st == earliest or workflow_sync.step_has_existing_artifacts(pd, slug, st)):
            upstream_steps.append(st)
    if earliest < source_step and earliest not in upstream_steps:
        upstream_steps.insert(0, earliest)

    label = "character" if kind == "character" else "set"
    summary = (
        f"Imported reference photo for {label} '{name}' (Step {source_step:02d}) — "
        f"bi-directional sync required from earliest inception (Step {earliest:02d})"
    )
    queue = workflow_sync.record_modification(
        pd,
        slug,
        source_step=source_step,
        summary=summary,
        origin_step=source_step,
        include_upstream=True,
        explicit_upstream=upstream_steps,
    )
    return {
        "earliest_inception_step": earliest,
        "upstream_steps": upstream_steps,
        "queue": queue,
    }


def _extract_json_obj(raw_text: str) -> dict[str, Any]:
    txt = str(raw_text or "").strip()
    if not txt:
        return {}
    # Strip markdown code fences if present
    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json)?\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt).strip()
    try:
        parsed = json.loads(txt)
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        pass
    m = re.search(r"\{[\s\S]*\}", txt)
    if m:
        try:
            parsed = json.loads(m.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            pass
    return {}


def _mime_for_image(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    return "image/png"


def _call_ollama_vision_json(
    prompt: str,
    image_path: Path | None = None,
    *,
    timeout: float = 40.0,
) -> tuple[dict[str, Any], str]:
    from studio_app import local_vision_qa as lvq

    probe = lvq.detect_ollama_vision_models(timeout=1.5)
    if not probe.get("running") or not probe.get("best_model"):
        return {}, ""
    model = str(probe["best_model"])
    base = str(probe["base_url"])

    msg: dict[str, Any] = {"role": "user", "content": prompt}
    if image_path is not None and image_path.is_file():
        msg["images"] = [base64.b64encode(image_path.read_bytes()).decode("ascii")]

    payload = json.dumps(
        {
            "model": model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
            "messages": [msg],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = str((data.get("message") or {}).get("content") or "")
        parsed = _extract_json_obj(content)
        if parsed:
            return parsed, f"ollama:{model}"
    except Exception as e:
        log.debug("Ollama vision JSON call failed (%s): %s", model, e)
    return {}, ""


def _call_gemini_vision_json(
    prompt: str,
    image_path: Path | None = None,
    *,
    timeout: float = 40.0,
) -> tuple[dict[str, Any], str]:
    import run_gemini_omni

    try:
        api_key = run_gemini_omni.get_gemini_api_key()
    except OSError:
        api_key = ""
    if not api_key:
        return {}, ""

    img_bytes = image_path.read_bytes() if (image_path is not None and image_path.is_file()) else None
    mime = _mime_for_image(image_path) if image_path is not None else "image/png"
    models = ("gemini-3.8-flash", "gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.0-flash")

    if run_gemini_omni.sdk_available():
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        contents: list[Any] = []
        if img_bytes is not None:
            contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))
        contents.append(prompt)
        cfg_kwargs: dict[str, Any] = {
            "temperature": 0.1,
            "response_mime_type": "application/json",
        }
        thinking_cls = getattr(types, "ThinkingConfig", None)
        if thinking_cls is not None:
            cfg_kwargs["thinking_config"] = thinking_cls(thinking_budget=0)
        for m in models:
            try:
                resp = client.models.generate_content(
                    model=m,
                    contents=contents,
                    config=types.GenerateContentConfig(**cfg_kwargs),
                )
                txt = str(getattr(resp, "text", "") or "")
                parsed = _extract_json_obj(txt)
                if parsed:
                    return parsed, f"gemini:{m}"
            except Exception as e:
                log.debug("Gemini SDK vision call failed (%s): %s", m, e)

    # REST fallback
    parts: list[dict[str, Any]] = []
    if img_bytes is not None:
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(img_bytes).decode("ascii")}})
    parts.append({"text": prompt})
    body = json.dumps(
        {
            "contents": [{"parts": parts}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
    ).encode("utf-8")
    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cands = data.get("candidates") or []
            if cands:
                cparts = ((cands[0].get("content") or {}).get("parts")) or []
                txt = "".join(str(p.get("text") or "") for p in cparts if isinstance(p, dict))
                parsed = _extract_json_obj(txt)
                if parsed:
                    return parsed, f"gemini:{m}"
        except Exception as e:
            log.debug("Gemini REST vision call failed (%s): %s", m, e)
    return {}, ""


def describe_set_image(
    image_path: Path,
    set_name: str,
    *,
    existing_description: str = "",
    timeout: float = 40.0,
) -> dict[str, Any]:
    """Translate a baselined Step 11 set image into structured visual description, lighting, and spatial anchors."""
    if not (image_path.is_file() and image_path.stat().st_size > 100):
        return {"ok": False, "engine": "", "error": "Set image file not found or empty"}

    prompt = (
        f"You are a film production designer cataloging the locked visual set plate for '{set_name}'. "
        "Carefully inspect the attached image and describe ONLY what is actually visible in the image so downstream "
        "storyboard prompts match this exact set without inventing contradictory rooms, windows, or furniture.\n"
        "Respond ONLY with valid JSON in this exact schema:\n"
        "{\n"
        '  "description": "2 to 3 crisp sentences detailing the exact architecture, left/center/right spatial layout, '
        'wall colors, flooring, ceiling, window/door positions, furniture shapes/colors/materials, and visible fixed props. '
        'Do NOT mention people, characters, or anything not visible.",\n'
        '  "lighting": "1 concise sentence describing the visible lighting direction, color temperature, and window/lamp light sources.",\n'
        '  "layout_anchors": ["left: ...", "center: ...", "right: ..."]\n'
        "}"
    )

    parsed, engine = _call_ollama_vision_json(prompt, image_path, timeout=timeout)
    if not parsed:
        parsed, engine = _call_gemini_vision_json(prompt, image_path, timeout=timeout)

    desc = str(parsed.get("description") or "").strip()
    light = str(parsed.get("lighting") or "").strip()
    raw_anchors = parsed.get("layout_anchors")
    anchors = [str(a).strip() for a in raw_anchors if str(a).strip()][:6] if isinstance(raw_anchors, list) else []

    if not desc:
        return {
            "ok": False,
            "engine": engine or "unavailable",
            "error": "No vision model available (start Ollama with a vision model or configure GEMINI_API_KEY in Step 13).",
            "description": existing_description,
            "lighting": "",
            "layout_anchors": [],
        }
    return {
        "ok": True,
        "engine": engine,
        "description": desc,
        "lighting": light,
        "layout_anchors": anchors,
    }


def reconcile_shot_compositions_with_set(
    set_name: str,
    set_description: str,
    set_lighting: str,
    shots_payload: list[dict[str, str]],
    *,
    timeout: float = 45.0,
) -> tuple[dict[str, dict[str, str]], str]:
    """Surgically align contradictory room/window/furniture clauses in Step 12 shot compositions with the baselined set image.

    Preserves 100% of character blocking, actions, dialogue beats, camera shot sizes, and story props.
    """
    if not shots_payload or not set_description.strip():
        return {}, ""

    prompt = (
        f"You are a film continuity supervisor aligning Step 12 storyboard shot compositions to the locked visual set plate for '{set_name}'.\n"
        f"LOCKED VISUAL SET (authoritative ground truth from the baselined set image):\n"
        f"- Architecture & Furniture: {set_description}\n"
        f"- Visible Lighting: {set_lighting or 'as shown in set plate'}\n\n"
        "RULES:\n"
        "1. Keep EVERY character name, character action, emotion, story prop (e.g. newspaper, cardboard box, toybox, bowl, remote), "
        "and camera framing intent intact.\n"
        "2. Fix ONLY room-layout, wall, window position, curtain, doorway, or furniture contradictions so the shot stages naturally "
        "inside the LOCKED VISUAL SET above (for example, if a shot says 'tall window on the left' but the set's window is on the right, "
        "update the spatial reference to match the set's actual window/furniture layout).\n"
        "3. Keep each composition concise (1-2 sentences) and concrete. Do NOT invent new characters, eyes, or faces.\n"
        "Respond ONLY with valid JSON mapping each shot id to {\"composition\": \"...\", \"lighting\": \"...\"} "
        "(omit lighting if unchanged or empty).\n\n"
        f"SHOTS TO ALIGN:\n{json.dumps(shots_payload, ensure_ascii=False)}"
    )

    parsed, engine = _call_ollama_vision_json(prompt, None, timeout=timeout)
    if not parsed:
        parsed, engine = _call_gemini_vision_json(prompt, None, timeout=timeout)
    if not parsed:
        return {}, ""

    # Support either {"S001-01": {...}} or {"shots": {"S001-01": {...}}}
    source_map = parsed.get("shots") if isinstance(parsed.get("shots"), dict) else parsed
    cleaned: dict[str, dict[str, str]] = {}
    if isinstance(source_map, dict):
        for sid, val in source_map.items():
            if isinstance(val, dict):
                comp = str(val.get("composition") or "").strip()
                light = str(val.get("lighting") or "").strip()
                if comp or light:
                    cleaned[str(sid)] = {"composition": comp, "lighting": light}
            elif isinstance(val, str) and val.strip():
                cleaned[str(sid)] = {"composition": val.strip(), "lighting": ""}
    return cleaned, engine


def _heading_matches_location(heading: str, norm_target: str) -> bool:
    if not heading or not norm_target:
        return False
    nh = _norm_loc(heading)
    if norm_target == nh:
        return True
    return bool(len(norm_target) >= 3 and re.search(rf"\b{re.escape(norm_target)}\b", nh))


def _update_continuity_locations_normalized(
    pd: Path,
    slug: str,
    set_name: str,
    new_desc: str,
    new_lighting: str,
) -> bool:
    """Update matching location entries in Continuity Book using normalized matching (e.g. 'LIVING ROOM' <-> 'the living room')."""
    import continuity_book

    norm_target = _norm_loc(set_name)
    if not norm_target:
        return False

    paths: list[Path] = []
    for p in (continuity_book.continuity_file(pd), pd / f"{slug}.json", pd / "continuity.json"):
        if p.is_file() and p.resolve() not in {x.resolve() for x in paths}:
            paths.append(p)

    updated_any = False
    for cb_path in paths:
        try:
            cb = json.loads(cb_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(cb, dict):
            continue
        locs = cb.get("locations")
        if not isinstance(locs, list):
            locs = []
        matched = False
        for loc in locs:
            if not isinstance(loc, dict):
                continue
            if _norm_loc(str(loc.get("name") or "")) == norm_target:
                loc["token"] = new_desc
                loc["description"] = new_desc
                if new_lighting:
                    loc["lighting"] = new_lighting
                loc["visual_source"] = "step11_baseline_vision"
                matched = True
        if not matched:
            entry: dict[str, Any] = {
                "name": set_name,
                "token": new_desc,
                "description": new_desc,
                "visual_source": "step11_baseline_vision",
            }
            if new_lighting:
                entry["lighting"] = new_lighting
            locs.append(entry)
        cb["locations"] = locs
        cb_path.write_text(json.dumps(cb, indent=1, ensure_ascii=False), encoding="utf-8")
        updated_any = True
    return updated_any


def sync_baselined_set_from_image(
    pd: Path,
    slug: str,
    name: str,
    image_path: Path,
    *,
    view_id: str = "main",
    reconcile_shots: bool = True,
    timeout: float = 40.0,
) -> dict[str, Any]:
    """Analyze a baselined Step 11 set image and propagate its exact visual text to Steps 07, 11, 12, and 17."""
    from studio_app import keyframe_context

    norm_target = _norm_loc(name)
    sets_custom_path = pd / "sets_custom.json"
    sets_custom: dict[str, Any] = {}
    if sets_custom_path.is_file():
        try:
            raw = json.loads(sets_custom_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                sets_custom = raw
        except (OSError, ValueError):
            sets_custom = {}

    prev_entry = sets_custom.get(name.lower()) if isinstance(sets_custom.get(name.lower()), dict) else {}
    old_desc = str((prev_entry or {}).get("description") or "").strip()

    vision = describe_set_image(image_path, name, existing_description=old_desc, timeout=timeout)
    if not vision.get("ok"):
        return {
            "ok": False,
            "engine": vision.get("engine") or "unavailable",
            "error": vision.get("error") or "Vision analysis unavailable",
            "updated_steps": [],
            "shots_reconciled": 0,
            "keyframes_updated": 0,
            "keyframes_skipped_locked": 0,
        }

    new_desc = str(vision["description"]).strip()
    new_light = str(vision.get("lighting") or "").strip()
    anchors = list(vision.get("layout_anchors") or [])
    engine = str(vision.get("engine") or "")
    updated_steps: list[str] = []

    # 1. Step 11 (`sets_custom.json` + `sets_views.json`) — update this set AND any normalized alias (e.g. "the living room")
    target_keys = {name.lower()}
    for existing_k in list(sets_custom.keys()):
        if _norm_loc(existing_k) == norm_target:
            target_keys.add(existing_k)
    for tk in target_keys:
        cur_e = dict(sets_custom.get(tk) or {"name": name})
        cur_e["description"] = new_desc
        if new_light:
            cur_e["lighting"] = new_light
        cur_e["layout_anchors"] = anchors
        cur_e["vision_engine"] = engine
        cur_e["vision_synced_from"] = image_path.name
        sets_custom[tk] = cur_e
    sets_custom_path.write_text(json.dumps(sets_custom, indent=2, ensure_ascii=False), encoding="utf-8")

    views_path = pd / "sets_views.json"
    if views_path.is_file():
        try:
            vdoc = json.loads(views_path.read_text(encoding="utf-8"))
            vsets = vdoc.get("sets") if isinstance(vdoc, dict) and isinstance(vdoc.get("sets"), dict) else None
            if vsets is not None:
                for sk, srec in vsets.items():
                    if isinstance(srec, dict) and _norm_loc(str(srec.get("name") or sk)) == norm_target:
                        srec["vision_description"] = new_desc
                        if new_light:
                            srec["vision_lighting"] = new_light
                        srec["vision_engine"] = engine
                        for vrec in srec.get("views") or []:
                            if isinstance(vrec, dict) and str(vrec.get("id") or "main") == str(view_id or "main"):
                                vrec["vision_description"] = new_desc
                                if new_light:
                                    vrec["vision_lighting"] = new_light
                                if not str(vrec.get("notes") or "").strip() or str(view_id or "main") != "main":
                                    vrec["notes"] = new_desc
                views_path.write_text(json.dumps(vdoc, indent=2, ensure_ascii=False), encoding="utf-8")
        except (OSError, ValueError):
            pass
    updated_steps.append("Step 11 (Locations & Sets)")

    # 2. Step 07 (`Continuity Book`)
    if _update_continuity_locations_normalized(pd, slug, name, new_desc, new_light):
        updated_steps.append("Step 07 (Continuity Book)")

    # 3. Step 12 (`shots/shotlist.json`) — attach visual set description & reconcile contradictory room clauses
    sl_path = pd / "shots" / "shotlist.json"
    shots_reconciled = 0
    matching_scene_ids: set[str] = set()
    sl_data: dict[str, Any] = {}
    if sl_path.is_file():
        try:
            loaded_sl = json.loads(sl_path.read_text(encoding="utf-8"))
            if isinstance(loaded_sl, dict):
                sl_data = loaded_sl
        except (OSError, ValueError):
            sl_data = {}

    if sl_data and isinstance(sl_data.get("scenes"), list):
        shots_to_align: list[dict[str, str]] = []
        shot_refs_by_id: dict[str, dict[str, Any]] = {}
        scene_touched = False

        for sc in sl_data.get("scenes") or []:
            if not isinstance(sc, dict):
                continue
            sc_id = str(sc.get("id") or sc.get("scene") or "").strip()
            heading = str(sc.get("heading") or "").strip()
            if not _heading_matches_location(heading, norm_target):
                continue
            matching_scene_ids.add(sc_id)
            sc["set_visual_description"] = new_desc
            if new_light:
                sc["set_lighting"] = new_light
            scene_touched = True
            for idx, sh in enumerate(sc.get("shots") or [], start=1):
                if not isinstance(sh, dict):
                    continue
                n = int(sh.get("n") or idx)
                sid = f"{sc_id}-{n:02d}"
                shot_refs_by_id[sid] = sh
                shots_to_align.append(
                    {
                        "id": sid,
                        "type": str(sh.get("type") or "MS"),
                        "composition": str(sh.get("composition") or ""),
                        "blocking": str(sh.get("blocking") or ""),
                        "action": str(sh.get("action") or ""),
                        "lighting": str(sh.get("lighting") or ""),
                    }
                )

        if reconcile_shots and shots_to_align:
            # Batch up to 24 shots per call in parallel so 60+ shot sets sync in ~10 seconds
            chunks = [shots_to_align[i : i + 24] for i in range(0, len(shots_to_align), 24)]
            if len(chunks) == 1:
                chunk_results = [reconcile_shot_compositions_with_set(name, new_desc, new_light, chunks[0], timeout=timeout)]
            else:
                with ThreadPoolExecutor(max_workers=min(4, len(chunks))) as pool:
                    chunk_results = list(
                        pool.map(
                            lambda c: reconcile_shot_compositions_with_set(name, new_desc, new_light, c, timeout=timeout),
                            chunks,
                        )
                    )
            for aligned, _rec_eng in chunk_results:
                for sid, upd in aligned.items():
                    sh_ref = shot_refs_by_id.get(sid)
                    if sh_ref is None:
                        continue
                    changed_this = False
                    if upd.get("composition") and upd["composition"] != str(sh_ref.get("composition") or "").strip():
                        sh_ref["composition"] = upd["composition"]
                        changed_this = True
                    if upd.get("lighting") and upd["lighting"] != str(sh_ref.get("lighting") or "").strip():
                        sh_ref["lighting"] = upd["lighting"]
                        changed_this = True
                    if changed_this:
                        shots_reconciled += 1
                        scene_touched = True

        if scene_touched:
            sl_path.write_text(json.dumps(sl_data, indent=1, ensure_ascii=False), encoding="utf-8")
            updated_steps.append(f"Step 12 (Shot List: {shots_reconciled} shot(s) aligned)")

    # 4. Step 17 (`keyframes_v2.json`) — rebuild unlocked prompts for all scenes at this location
    keyframes_updated = 0
    keyframes_skipped_locked = 0
    if matching_scene_ids and sl_data:
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

        ctx = keyframe_context.load_keyframe_project_context(slug, pd)
        for sc in sl_data.get("scenes") or []:
            if not isinstance(sc, dict):
                continue
            sc_id = str(sc.get("id") or sc.get("scene") or "").strip()
            if sc_id not in matching_scene_ids:
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

    return {
        "ok": True,
        "engine": engine,
        "description": new_desc,
        "lighting": new_light,
        "layout_anchors": anchors,
        "updated_steps": updated_steps,
        "shots_reconciled": shots_reconciled,
        "keyframes_updated": keyframes_updated,
        "keyframes_skipped_locked": keyframes_skipped_locked,
    }


_STYLE_WORDS_RE = re.compile(
    r"(?i)\b(photo-?realistic|photoreal|hyper-?realistic|photograph\w*|snapshot|camera\s+photo|"
    r"claymation|plasticine|3d|cgi|pixar|anime|manga|cartoon\w*|watercolou?r|oil[- ]painting|illustrat\w*|render\w*|cel[- ]shad\w*)\b"
)


def describe_character_image(
    image_path: Path,
    char_name: str,
    *,
    existing_description: str = "",
    timeout: float = 40.0,
) -> dict[str, Any]:
    """Translate an imported Step 08 character reference photo into a style-neutral visual description & consistency token."""
    if not (image_path.is_file() and image_path.stat().st_size > 100):
        return {"ok": False, "engine": "", "error": "Character image file not found or empty"}

    prompt = (
        f"You are a film character continuity supervisor cataloging an imported reference photo for character '{char_name}'. "
        "Carefully inspect the attached image and describe ONLY the actual subject visible in the image (person, child, animal, toy, or object) "
        "in completely style-neutral visual terms (NEVER use rendering words like 'photograph', 'photorealistic', '3D', 'Pixar', 'cartoon', or 'anime').\n"
        "Respond ONLY with valid JSON in this exact schema:\n"
        "{\n"
        '  "description": "1 to 2 crisp sentences describing the exact visible subject: species/type, approximate age and build, '
        'skin/fur/material tone, hair/ears/eyes/facial features, and exact visible clothing, colors, and accessories.",\n'
        '  "token": "Compact comma-separated style-neutral visual consistency token under 210 characters covering species/age/build, face/hair/eyes, and exact solid outfit colors."\n'
        "}"
    )

    parsed, engine = _call_ollama_vision_json(prompt, image_path, timeout=timeout)
    if not parsed:
        parsed, engine = _call_gemini_vision_json(prompt, image_path, timeout=timeout)

    desc = re.sub(r"\s{2,}", " ", _STYLE_WORDS_RE.sub("", str(parsed.get("description") or ""))).strip(" ,;:-")
    tok = re.sub(r"\s{2,}", " ", _STYLE_WORDS_RE.sub("", str(parsed.get("token") or ""))).strip(" ,;:-")[:240]
    if desc and not tok:
        tok = desc[:220]
    if tok and not desc:
        desc = tok

    if not desc:
        return {
            "ok": False,
            "engine": engine or "unavailable",
            "error": "No vision model available (start Ollama with a vision model or configure GEMINI_API_KEY in Step 13).",
            "description": existing_description,
            "token": existing_description[:220],
        }
    return {
        "ok": True,
        "engine": engine,
        "description": desc,
        "token": tok,
    }


def sync_character_from_imported_image(
    pd: Path,
    slug: str,
    char_name: str,
    image_path: Path,
    *,
    timeout: float = 40.0,
) -> dict[str, Any]:
    """Run image-to-text on an imported character photo and propagate its prompt across Steps 03, 07, 08, 10, and 17."""
    import character_tokens
    import continuity_book
    from studio_app import keyframe_context

    existing = character_tokens.load_character(slug, char_name)
    old_desc = str((existing or {}).get("description") or (existing or {}).get("visual_token") or "").strip() if isinstance(existing, dict) else ""

    vision = describe_character_image(image_path, char_name, existing_description=old_desc, timeout=timeout)
    if not vision.get("ok"):
        return {
            "ok": False,
            "engine": vision.get("engine") or "unavailable",
            "error": vision.get("error") or "Vision analysis unavailable",
            "description": old_desc,
            "token": old_desc[:220],
            "updated_steps": [],
            "keyframes_updated": 0,
            "keyframes_skipped_locked": 0,
        }

    new_desc = str(vision["description"]).strip()
    new_tok = str(vision["token"]).strip()[:240]
    engine = str(vision.get("engine") or "")
    updated_steps: list[str] = []
    target_low = char_name.strip().lower()

    # 1. Step 03 Coverage (`readin/coverage.json`) — update character description at earliest coverage inception
    cov_path = pd / "readin" / "coverage.json"
    if cov_path.is_file():
        try:
            cov = json.loads(cov_path.read_text(encoding="utf-8"))
            if isinstance(cov, dict) and isinstance(cov.get("characters"), list):
                cov_changed = False
                for c in cov["characters"]:
                    if isinstance(c, dict) and str(c.get("name") or "").strip().lower() == target_low:
                        c["description"] = new_desc
                        cov_changed = True
                if cov_changed:
                    cov_path.write_text(json.dumps(cov, indent=1, ensure_ascii=False), encoding="utf-8")
                    updated_steps.append("Step 03 (Coverage)")
        except (OSError, ValueError):
            pass

    # 2. Step 08 Character Dossier (`character_tokens`)
    try:
        rec = dict(existing) if isinstance(existing, dict) else {
            "project": slug,
            "name": char_name,
            "role": "supporting",
            "reference_images": [],
        }
        rec["description"] = new_desc
        rec["visual_token"] = new_tok
        rec["vision_engine"] = engine
        rec["vision_synced_from"] = image_path.name
        character_tokens.save_character(rec)
        updated_steps.append("Step 08 (Cast & Characters)")
    except Exception as e:
        log.debug("character_tokens save failed in sync_character_from_imported_image: %s", e)

    # 3. Step 07 Continuity Book (`<slug>.json` / `continuity.json`)
    paths: list[Path] = []
    for p in (continuity_book.continuity_file(pd), pd / f"{slug}.json", pd / "continuity.json"):
        if p.is_file() and p.resolve() not in {x.resolve() for x in paths}:
            paths.append(p)
    cb_updated = False
    for cb_path in paths:
        try:
            cb = json.loads(cb_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(cb, dict):
            continue
        chars = cb.get("characters")
        if not isinstance(chars, list):
            continue
        changed = False
        for c in chars:
            if isinstance(c, dict) and str(c.get("name") or "").strip().lower() == target_low:
                c["token"] = new_tok
                if "description" in c:
                    c["description"] = new_desc
                c["visual_source"] = "step08_imported_vision"
                changed = True
        if changed:
            cb_path.write_text(json.dumps(cb, indent=1, ensure_ascii=False), encoding="utf-8")
            cb_updated = True
    if cb_updated:
        updated_steps.append("Step 07 (Continuity Book)")

    # 4. Step 17 (`keyframes_v2.json`) — rebuild unlocked prompts for all shots featuring this character
    keyframes_updated = 0
    keyframes_skipped_locked = 0
    sl_path = pd / "shots" / "shotlist.json"
    if sl_path.is_file():
        try:
            sl_data = json.loads(sl_path.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError):
            sl_data = {}
        if isinstance(sl_data, dict) and isinstance(sl_data.get("scenes"), list):
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
            name_re = re.compile(rf"\b{re.escape(target_low)}\b", re.IGNORECASE)
            ctx = keyframe_context.load_keyframe_project_context(slug, pd)
            for sc in sl_data.get("scenes") or []:
                if not isinstance(sc, dict):
                    continue
                sc_id = str(sc.get("id") or sc.get("scene") or "").strip()
                heading = str(sc.get("heading") or "")
                for idx, sh in enumerate(sc.get("shots") or [], start=1):
                    if not isinstance(sh, dict):
                        continue
                    sh_chars = [str(x).strip().lower() for x in (sh.get("characters") or [])]
                    sh_blob = f"{sh.get('composition') or ''} {sh.get('action') or ''} {sh.get('blocking') or ''}"
                    if target_low not in sh_chars and not name_re.search(sh_blob):
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

    return {
        "ok": True,
        "engine": engine,
        "description": new_desc,
        "token": new_tok,
        "updated_steps": updated_steps,
        "keyframes_updated": keyframes_updated,
        "keyframes_skipped_locked": keyframes_skipped_locked,
    }
