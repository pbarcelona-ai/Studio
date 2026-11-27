"""GET routes of the JSON API."""
import re
from pathlib import Path
from typing import Any
import character_tokens
import detect_scene_changes
import model_advisor
from layout import project_dir as pdir
from bookkit import SLUG_RE

from .api import HttpError, Request, route
from .log import get_logger

log = get_logger("routes_get")
from .adapt import adaptation_data, cast_lock_data, grading_data, screenplay_data
from .chapters import chapter_list, chapter_text
from .export import credits_get, exports_data, shares_data
from .cleanup import cleanup_scan, files_inventory
from .common import num
from .config import ROOT
from .gallery import compare_data, library, showcase
from .generation import film_status
from .gpus import gpu_profile, suggestions
from .jobs import JOB
from .kaggle_cleanup import kaggle_cleanup_scan
from .kaggle_runs import kaggle_runs, kernel_ref, kernel_status
from .llm import clip_prompt, gallery, local_llm_status
from .media import media_inventory
from .overview import setup_status, status
from .planner import chapter_shots
from .projects import load_global_params
from .providers import providers_data
from .path import path_data
from .scenes import scene_data
from .takes import lipsync_candidates, storyboard


@route("GET", "/api/scenes")
def _scenes(r: Request):
    return scene_data(r.q("project"), r.q("chapter"))


@route("GET", "/api/adaptation")
def _adaptation(r: Request):
    return adaptation_data(r.q("project"))


@route("GET", "/api/cast_lock")
def _cast_lock(r: Request):
    return cast_lock_data(r.q("project"))


@route("GET", "/api/exports")
def _exports(r: Request):
    return exports_data(r.q("project"))


@route("GET", "/api/shares")
def _shares(r: Request):
    return shares_data(r.q("project"))


@route("GET", "/api/credits")
def _credits(r: Request):
    return credits_get(r.q("project"))


@route("GET", "/api/grading")
def _grading(r: Request):
    return grading_data(r.q("project"))


@route("GET", "/api/screenplay")
def _screenplay(r: Request):
    return screenplay_data(r.q("project"), r.q("scene"))


@route("GET", "/api/chapters")
def _chapters(r: Request):
    return chapter_list(r.q("project"))


@route("GET", "/api/chapter_text")
def _chapter_text(r: Request):
    return chapter_text(r.q("project"), r.q("n"))


@route("GET", "/api/chapter_shots")
def _chapter_shots(r: Request):
    return chapter_shots(r.q("project"))


@route("GET", "/api/files")
def _files(r: Request):
    return {"folders": files_inventory(r.q("project"))}


@route("GET", "/api/cleanup_scan")
def _cleanup_scan(r: Request):
    return {"categories": cleanup_scan()}


@route("GET", "/api/lipsync_candidates")
def _lipsync_candidates(r: Request):
    return lipsync_candidates(r.q("project"), r.q("medium") == "1")


@route("GET", "/api/storyboard")
def _storyboard(r: Request):
    return storyboard(r.q("project"), num({"s": r.q("start", "1")}, "s", 1, int, 1), num({"e": r.q("end", "24")}, "e", 24, int, 1))


@route("GET", "/api/film_status")
def _film_status(r: Request):
    return film_status(r.q("project"))


@route("GET", "/api/suggest")
def _suggest(r: Request):
    return suggestions(r.q("look"), r.q("service"), r.q("gpu"))


@route("GET", "/api/gpu_profile")
def _gpu_profile(_r: Request):
    return gpu_profile()


@route("GET", "/api/media")
def _media(r: Request):
    return media_inventory(r.q("project"))


@route("GET", "/api/kaggle_runs")
def _kaggle_runs(r: Request):
    return {"runs": kaggle_runs()}


@route("GET", "/api/kaggle_cleanup_scan")
def _kaggle_cleanup_scan(r: Request):
    return kaggle_cleanup_scan()


@route("GET", "/api/kernel_status")
def _kernel_status(r: Request):
    return kernel_status(kernel_ref(r.q("ref")))


@route("GET", "/api/setup")
def _setup(r: Request):
    return setup_status()


@route("GET", "/api/local_llm")
def _local_llm(r: Request):                              # the page asks again when you open the Models tab, come back to the window, or press Check again
    return local_llm_status(force=r.q("fresh") == "1")


@route("GET", "/api/compare")
def _compare(r: Request):
    return compare_data()


@route("GET", "/api/showcase")
def _showcase(r: Request):
    return showcase()


@route("GET", "/api/library")
def _library(r: Request):
    return library()


@route("GET", "/api/gallery")
def _gallery(r: Request):
    slug = r.q("project")
    return {"items": gallery(slug) if SLUG_RE.match(slug) else []}


@route("GET", "/api/status")
def _status(r: Request):
    return status()


@route("GET", "/api/log")
def _log(r: Request):
    from datetime import datetime
    from pathlib import Path

    since = max(num({"since": r.q("since", "0")}, "since", 0, int, 0), 0)
    with JOB.lock:
        lines = list(JOB.lines[since:])
        nxt = len(JOB.lines)
        running = JOB.running
        current = JOB.current
        queued = len(JOB.queue)
        st = dict(getattr(JOB, "state", None) or {})

    raw_steps = st.get("steps")
    steps: list[Any] = raw_steps if isinstance(raw_steps, list) else []
    idx = int(st.get("index") or 0)
    script = ""
    if steps:
        active_step = steps[min(max(0, idx), len(steps) - 1)]
        if isinstance(active_step, dict):
            argv = active_step.get("argv") or []
            for tok in argv:
                s_tok = str(tok)
                if s_tok.endswith(".py"):
                    script = Path(s_tok).name
                    break

    started = str(st.get("started") or "")
    ended = str(st.get("ended") or "")
    elapsed_sec = 0.0
    if started:
        try:
            t0 = datetime.strptime(started, "%Y-%m-%d %H:%M:%S")
            t1 = datetime.strptime(ended, "%Y-%m-%d %H:%M:%S") if (ended and not running) else datetime.now()
            elapsed_sec = max(0.0, round((t1 - t0).total_seconds(), 1))
        except ValueError:
            elapsed_sec = 0.0

    exit_code: int | None = None
    exit_path = str(st.get("exit") or "")
    if exit_path and not running:
        try:
            exit_code = int(Path(exit_path).read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            exit_code = None

    return {
        "lines": lines,
        "next": nxt,
        "running": running,
        "current": current,
        "queued": queued,
        "project": str(st.get("project") or ""),
        "status": str(st.get("status") or ("running" if running else "idle")),
        "started": started,
        "elapsed_sec": elapsed_sec,
        "step_index": idx,
        "step_total": len(steps),
        "script": script,
        "exit_code": exit_code,
    }


@route("GET", "/api/old_pictures")
def _old_pictures(r: Request):
    from .old_pictures import old_pictures
    n = r.q("n", "")
    return old_pictures(r.q("project"), int(n) if n.isdigit() else None)


@route("GET", "/api/results")
def _results(r: Request):
    from .results import results_data
    return results_data(r.q("project"), r.q("kind", "any"))


@route("GET", "/api/sessions")
def _sessions(r: Request):
    from .resume import sessions_data
    return sessions_data(with_kernels=r.q("kernels", "") == "1")


@route("GET", "/api/path")
def _path(r: Request):
    return path_data(r.q("project"))


@route("GET", "/api/providers")
def _providers(r: Request):
    return providers_data()


@route("GET", "/api/clip_prompt")
def _clip_prompt(r: Request):
    return clip_prompt(r.q("project"), int(r.q("row", "0")))


@route("GET", "/api/global_params")
def _global_params(r: Request):
    project = r.q("project")
    if not project:
        raise HttpError(400, "project is required")
    return load_global_params(project)


# ---- /api/characters?action=...
def _archetype_or_400(name: str):
    try:
        return character_tokens.CharacterArchetype(name)
    except ValueError:
        raise HttpError(400, f"unknown archetype: {name}") from None


def _ch_list_series(r: Request):
    return {"series": character_tokens.list_series()}


def _ch_list(r: Request):
    return {"series": character_tokens.list_series(), "characters": character_tokens.list_characters(r.q("series"))}


def _ch_get(r: Request):
    return {"character": character_tokens.load_character(r.q("series"), r.q("name"))}


def _ch_tokens(r: Request):
    return {"tokens": character_tokens.get_all_character_tokens(r.q("series"))}


def _ch_sync(r: Request):
    return {"synced": character_tokens.sync_characters_from_project(r.q("project")), "series": r.q("series")}


def _ch_references(r: Request):
    series, name = r.q("series"), r.q("name")
    return {"pictures": character_tokens.reference_pictures(series, name),
            "folder": character_tokens.get_reference_dir(series, name).relative_to(ROOT).as_posix()}


def _ch_archetypes(r: Request):              # the Characters tab wants {archetype: {...}} (keys fill the dropdown)
    return {"archetypes": {a.value: {"label": a.value.replace("_", " ").title(), **character_tokens.get_archetype_fields(a)}
                           for a in character_tokens.CharacterArchetype}}


def _ch_archetype_fields(r: Request):        # and {field: {type, required}} for the chosen archetype (a * marks required ones)
    name = r.q("archetype")
    cfg = character_tokens.get_archetype_fields(_archetype_or_400(name))
    fields = {}
    for key, required in (("required_physical", True), ("optional_physical", False), ("required_fields", True), ("optional_fields", False)):
        for f in cfg.get(key, []):
            fields[f] = {"type": "string", "required": required}
    return {"archetype": name, "fields": fields}


def _ch_valid_values(r: Request):            # dropdown choices: all fields at once, or one field with ?field=
    field = r.q("field")
    if field:
        values = character_tokens.get_valid_values(field)
        return {"field": field, "values": values, "valid_values": {field: values}}
    return {"valid_values": {k: list(v) for k, v in character_tokens.VALID_VALUES.items()}}


_CHARACTER_GET = {"list_series": _ch_list_series, "list": _ch_list, "get": _ch_get, "tokens": _ch_tokens, "sync": _ch_sync,
                  "references": _ch_references, "archetypes": _ch_archetypes, "archetype_fields": _ch_archetype_fields,
                  "valid_values": _ch_valid_values}


@route("GET", "/api/characters")
def _characters(r: Request):
    action = r.q("action", "list")
    fn = _CHARACTER_GET.get(action)
    if fn is None:
        raise HttpError(400, f"unknown action: {action}")
    return fn(r)


@route("GET", "/api/storyline_changes")
def _storyline_changes(r: Request):
    slug = r.q("project")
    if not slug:
        raise HttpError(400, "project is required")
    try:
        pd = pdir(slug, "book")
    except Exception as e:
        raise HttpError(400, str(e)) from e
    return detect_scene_changes.detect_changed_scenes(pd)


@route("GET", "/api/autopilot_recommend")
def _autopilot_recommend(r: Request):
    look = r.q("look", "live_action")
    step = r.q("step", "keyframe")
    shot_type = r.q("shot_type")
    hardware = r.q("hardware")
    return model_advisor.autopilot_recommend(look, step, shot_type, hardware)


@route("GET", "/api/gemini_omni_status")
def _gemini_omni_status(r: Request):
    import json
    import run_gemini_omni

    slug = r.q("project")
    interactions: dict[str, Any] = {}
    if slug:
        try:
            idx_path = pdir(slug, "book") / "videos" / "gemini_omni_12_flash" / "interactions.json"
            if idx_path.is_file():
                interactions = json.loads(idx_path.read_text(encoding="utf-8")) or {}
        except Exception:
            interactions = {}
    return {
        "model": run_gemini_omni.DEFAULT_MODEL,
        "configured": bool(run_gemini_omni.get_gemini_api_key()),
        "sdk_installed": run_gemini_omni.sdk_available(),
        "interactions": interactions,
    }


@route("GET", "/api/v2_voice_cast")
def _v2_voice_cast(r: Request):
    import json

    slug = r.q("project")
    if not slug:
        return {"cast": {}, "dialect": "american", "mode": "dialogue"}
    try:
        vc_path = pdir(slug, "book") / "voice_cast.json"
        if vc_path.is_file():
            data = json.loads(vc_path.read_text(encoding="utf-8")) or {}
            return {
                "cast": data.get("cast") or {},
                "dialect": data.get("dialect") or "american",
                "mode": data.get("mode") or "dialogue",
            }
    except Exception as e:
        log.debug("v2_voice_cast read failed: %s", e)
    return {"cast": {}, "dialect": "american", "mode": "dialogue"}


@route("GET", "/api/v2_dialogue")
def _v2_dialogue(r: Request):
    """Extract all spoken dialogue lines from screenplay/scene-*.json merged with voice_cast.json and dialogue_lines.json."""
    import json

    slug = r.q("project")
    if not slug:
        return {"lines": [], "scenes": [], "dialect": "american", "cast": {}}
    pd = pdir(slug, "book")
    vc: dict[str, Any] = {}
    profiles: dict[str, Any] = {}
    baselines_raw: dict[str, Any] = {}
    cleared_baselines = set()
    dialect = "american"
    vc_path = pd / "voice_cast.json"
    vdata: dict[str, Any] = {}
    if vc_path.is_file():
        try:
            vdata = json.loads(vc_path.read_text(encoding="utf-8")) or {}
            vc = vdata.get("cast") or {}
            profiles = vdata.get("profiles") or {}
            baselines_raw = vdata.get("baselines") or {}
            cleared_baselines = {str(c).lower() for c in (vdata.get("cleared_baselines") or [])}
            dialect = vdata.get("dialect") or "american"
        except Exception as e:
            log.debug("voice_cast.json read failed: %s", e)

    from .routes_post import VOICE_LIBRARY_DIR, _norm_voice_char, _voice_library_load, find_kokoro_python
    global_lib = _voice_library_load()
    global_lib_lc = {str(k).lower(): v for k, v in global_lib.items() if isinstance(v, dict)}
    global_lib_norm = {_norm_voice_char(str(k)): v for k, v in global_lib.items() if isinstance(v, dict)}

    vc_lc = {str(k).lower(): v for k, v in vc.items()}
    vc_norm = {_norm_voice_char(str(k)): v for k, v in vc.items()}
    prof_lc = {str(k).lower(): v for k, v in profiles.items() if isinstance(v, dict)}
    prof_norm = {_norm_voice_char(str(k)): v for k, v in profiles.items() if isinstance(v, dict)}
    baselines = {}
    for ch_name, binfo in baselines_raw.items():
        if not isinstance(binfo, dict) or not binfo.get("file"):
            continue
        bf = pd / str(binfo["file"])
        if bf.is_file() and bf.stat().st_size > 100:
            b_prof = binfo.get("profile") if isinstance(binfo.get("profile"), dict) else (prof_lc.get(ch_name.lower()) or prof_norm.get(_norm_voice_char(ch_name)) or {})
            baselines[ch_name] = {
                "file": str(binfo["file"]),
                "source": str(binfo.get("source") or "custom"),
                "text": str(binfo.get("text") or ""),
                "saved_to_library": bool(binfo.get("saved_to_library", ch_name.lower() in global_lib_lc)),
                "source_project": str(binfo.get("source_project") or slug),
                "profile": b_prof,
                "audio_url": f"/file/{slug}/{binfo['file']}",
            }

    saved: dict[str, Any] = {}
    saved_engine = ""
    dl_path = pd / "dialogue_lines.json"
    if dl_path.is_file():
        try:
            ddata = json.loads(dl_path.read_text(encoding="utf-8")) or {}
            saved = ddata.get("lines") or {}
            saved_engine = str(ddata.get("engine") or "").strip()
        except Exception as e:
            log.debug("dialogue_lines.json read failed: %s", e)

    import shutil
    import subprocess

    gemini_ready = False
    try:
        import run_gemini_omni
        gemini_ready = bool(run_gemini_omni.get_gemini_api_key())
    except Exception as e:
        log.debug("gemini_omni probe failed: %s", e)
    kokoro_py = find_kokoro_python()
    kokoro_ready = bool(kokoro_py)
    say_bin = shutil.which("say")
    macos_ready = bool(say_bin)
    macos_voices: list[dict[str, str]] = []
    if say_bin:
        try:
            out = subprocess.check_output([say_bin, "-v", "?"], text=True, timeout=5)
            for ln in out.splitlines():
                parts = ln.split()
                if len(parts) >= 2 and parts[1].startswith("en_"):
                    vname = parts[0]
                    locale = parts[1]
                    if vname not in [x["id"] for x in macos_voices]:
                        macos_voices.append({"id": vname, "label": f"{vname} ({locale})"})
        except Exception as e:
            log.debug("say -v probe failed: %s", e)
    if not saved_engine:
        saved_engine = "gemini-tts" if gemini_ready else ("kokoro" if kokoro_ready else "macos-say")

    lines = []
    scenes_seen = []
    sp_dir = pd / "screenplay"
    if sp_dir.is_dir():
        for sp_file in sorted(sp_dir.glob("scene-*.json")):
            try:
                sc = json.loads(sp_file.read_text(encoding="utf-8")) or {}
            except Exception as e:
                log.debug("skipping unreadable scene %s: %s", sp_file.name, e)
                continue
            sc_id = str(sc.get("scene") or sp_file.stem.replace("scene-", ""))
            heading = str(sc.get("heading") or "")
            idx = 0
            for el in sc.get("elements") or []:
                if not isinstance(el, dict) or el.get("type") != "dialogue":
                    continue
                idx += 1
                lid = f"{sc_id}-{idx:02d}"
                char = str(el.get("character") or "SPEAKER").strip()
                text = str(el.get("text") or "").strip()
                note = str(el.get("note") or "").strip()
                raw_ov = saved.get(lid)
                ov: dict[str, Any] = raw_ov if isinstance(raw_ov, dict) else {}
                ch_norm = _norm_voice_char(char)
                g_entry = global_lib_lc.get(char.lower()) or global_lib_norm.get(ch_norm) or {}
                b_entry = next(
                    (bv for bk, bv in baselines.items() if bk.lower() == char.lower() or _norm_voice_char(bk) == ch_norm),
                    {},
                )
                b_prof = b_entry.get("profile") if isinstance(b_entry, dict) and isinstance(b_entry.get("profile"), dict) else {}
                cp = prof_lc.get(char.lower()) or prof_norm.get(ch_norm) or b_prof or g_entry or {}
                # Auto-inherit baseline WAV from global cross-film library for new films if not cleared/set yet
                if (
                    char.lower() not in {k.lower() for k in baselines}
                    and ch_norm not in {_norm_voice_char(k) for k in baselines}
                    and char.lower() not in cleared_baselines
                    and g_entry.get("wav_file")
                ):
                    lib_wav = VOICE_LIBRARY_DIR / str(g_entry["wav_file"])
                    if lib_wav.is_file() and lib_wav.stat().st_size > 100:
                        safe_ch = "".join(c if c.isalnum() else "_" for c in char.lower()).strip("_") or "speaker"
                        ref_dir = pd / "audio" / "voice_refs"
                        ref_dir.mkdir(parents=True, exist_ok=True)
                        rel_f = f"audio/voice_refs/{safe_ch}.wav"
                        dest_f = pd / rel_f
                        if not dest_f.is_file():
                            shutil.copyfile(lib_wav, dest_f)
                        baselines[char] = {
                            "file": rel_f,
                            "source": str(g_entry.get("source") or "library"),
                            "text": str(g_entry.get("text") or ""),
                            "saved_to_library": True,
                            "source_project": str(g_entry.get("source_project") or "library"),
                            "inherited_from_library": True,
                            "profile": cp,
                            "audio_url": f"/file/{slug}/{rel_f}",
                        }
                voice = ov.get("voice") or vc_lc.get(char.lower()) or vc_norm.get(ch_norm) or cp.get("kokoro_voice") or ("bm_fable" if dialect == "british" else "am_puck")
                wav_rel = f"audio/dialogue/{lid}.wav"
                wav_path = pd / wav_rel
                has_audio = wav_path.is_file() and wav_path.stat().st_size > 100
                if sc_id not in scenes_seen:
                    scenes_seen.append(sc_id)
                eff_speed = ov.get("speed") if ov.get("speed") is not None else cp.get("speed", 1.0)
                lines.append({
                    "id": lid,
                    "scene": sc_id,
                    "heading": heading,
                    "character": char,
                    "text": ov.get("text", text),
                    "note": ov.get("note", note),
                    "voice": voice,
                    "gemini_voice": ov.get("gemini_voice") or cp.get("gemini_voice") or "",
                    "kokoro_voice": ov.get("kokoro_voice") or cp.get("kokoro_voice") or voice,
                    "kokoro_blend": ov.get("kokoro_blend") or cp.get("kokoro_blend") or "",
                    "macos_voice": ov.get("macos_voice") or cp.get("macos_voice") or "",
                    "persona": ov.get("persona") or cp.get("persona") or "",
                    "emotion": ov.get("emotion", "natural"),
                    "speed": float(eff_speed if eff_speed is not None else 1.0),
                    "has_audio": has_audio,
                    "audio_url": f"/file/{slug}/{wav_rel}" if has_audio else "",
                })
    return {
        "lines": lines,
        "scenes": scenes_seen,
        "dialect": dialect,
        "cast": vc,
        "profiles": profiles,
        "baselines": baselines,
        "engine": saved_engine,
        "macos_voices": macos_voices,
        "engines": {
            "gemini_tts": gemini_ready,
            "kokoro": kokoro_ready,
            "macos_say": macos_ready,
        },
    }


@route("GET", "/api/v2_sound_design")
def _v2_sound_design(r: Request):
    """Return Step 16 Foley & Score design state, scene cues from screenplay, and rendered track URLs."""
    import json

    slug = r.q("project")
    if not slug:
        return {"foley": {}, "score": {}, "scenes": []}
    pd = pdir(slug, "book")
    sd_path = pd / "sound_design_v2.json"
    saved: dict[str, Any] = {}
    if sd_path.is_file():
        try:
            saved = json.loads(sd_path.read_text(encoding="utf-8")) or {}
        except Exception:
            saved = {}

    from .routes_post import _auto_scene_sfx_profile, build_story_sfx_presets

    scenes = []
    raw_saved_scenes = saved.get("scenes")
    saved_scenes: dict[str, Any] = raw_saved_scenes if isinstance(raw_saved_scenes, dict) else {}
    sp_dir = pd / "screenplay"
    if sp_dir.is_dir():
        for sp_file in sorted(sp_dir.glob("scene-*.json")):
            try:
                sc = json.loads(sp_file.read_text(encoding="utf-8")) or {}
            except Exception as e:
                log.debug("skipping unreadable scene %s: %s", sp_file.name, e)
                continue
            sc_id = str(sc.get("scene") or sp_file.stem.replace("scene-", ""))
            heading = str(sc.get("heading") or "")
            actions = [str(el.get("text") or "").strip() for el in (sc.get("elements") or []) if isinstance(el, dict) and el.get("type") == "action"]
            hint = " ".join(a for a in actions if a)
            auto_preset, auto_cue, auto_mood = _auto_scene_sfx_profile(heading, hint)

            raw_ov = saved_scenes.get(sc_id)
            ov: dict[str, Any] = raw_ov if isinstance(raw_ov, dict) else {}
            sc_wav = pd / "audio" / "foley" / f"scene_{sc_id}.wav"
            has_sc_wav = sc_wav.is_file() and sc_wav.stat().st_size > 100
            scenes.append({
                "scene": sc_id,
                "heading": heading,
                "hint": hint,
                "sfx_cue": ov["sfx_cue"] if "sfx_cue" in ov else auto_cue,
                "sfx_preset": ov.get("sfx_preset") or auto_preset,
                "score_mood": ov.get("score_mood") or auto_mood,
                "has_sfx": has_sc_wav,
                "sfx_url": f"/file/{slug}/audio/foley/scene_{sc_id}.wav" if has_sc_wav else "",
            })

    story_presets = build_story_sfx_presets(pd, slug)
    default_story_preset = next((p for p in story_presets if p.get("group") == "This Story"), None) or next(
        (p for p in story_presets if p.get("id") not in ("custom", "silent")),
        {"id": "soft_rain_room", "prompt": "Quiet cozy indoor room ambiance, subtle natural air."},
    )

    foley_wav = pd / "audio" / "foley" / "foley_master.wav"
    score_wav = pd / "audio" / "score" / "score_master.wav"
    foley_cfg = dict(saved.get("foley") or {})
    score_cfg = dict(saved.get("score") or {})

    return {
        "sfx_mode": str(saved.get("sfx_mode") or "hybrid"),
        "presets": story_presets,
        "foley": {
            "prompt": foley_cfg.get("prompt") or str(default_story_preset.get("prompt") or ""),
            "preset": foley_cfg.get("preset") or str(default_story_preset.get("id") or "custom"),
            "duration": int(foley_cfg.get("duration") or 12),
            "has_audio": foley_wav.is_file() and foley_wav.stat().st_size > 100,
            "audio_url": f"/file/{slug}/audio/foley/foley_master.wav" if (foley_wav.is_file() and foley_wav.stat().st_size > 100) else "",
        },
        "score": {
            "prompt": score_cfg.get("prompt") or "Sweeping cinematic orchestral strings, warm French horns, and sparkling celesta arpeggios in major key.",
            "mood": score_cfg.get("mood") or (scenes[0]["score_mood"] if scenes else "wonder"),
            "duration": int(score_cfg.get("duration") or 12),
            "has_audio": score_wav.is_file() and score_wav.stat().st_size > 100,
            "audio_url": f"/file/{slug}/audio/score/score_master.wav" if (score_wav.is_file() and score_wav.stat().st_size > 100) else "",
        },
        "scenes": scenes,
    }


@route("GET", "/api/v2_workflow_sync")
def _v2_workflow_sync(r: Request):
    """Return the persisted bi-directional workflow sync queue and top-banner instructions for a project."""
    from studio_app import workflow_sync

    slug = r.q("project")
    raw_cur = r.q("current_step")
    cur_step = int(raw_cur) if raw_cur and raw_cur.isdigit() else 1
    if not slug:
        return {"queue": {"active": False, "items": []}, "banner": {"active": False}}
    pd = pdir(slug, "book")
    doc = workflow_sync.load_queue(pd)
    banner = workflow_sync.summarize_banner_state(doc, cur_step)
    return {"queue": doc, "banner": banner}


@route("GET", "/api/v2_local_consistency_status")
def _v2_local_consistency_status(r: Request):
    """Return live status of 100% free local consistency models (sd-cli Kontext/Klein 9B, Ollama Vision QA, ComfyUI Angles)."""
    import json as _json
    from local_runners.comfyui_runner import ComfyUIRunner
    from local_runners.sd_cli_runner import SdCliRunner
    from studio_app import local_vision_qa, routes_post

    sd_runner = SdCliRunner()
    sd_models = sd_runner.describe_consistency_models()
    ollama_info = local_vision_qa.detect_ollama_vision_models(timeout=1.5)

    # Check ComfyUI `apps/angles` readiness
    angles_ready = False
    angles_missing_gb = 0.0
    comfy_installed = False
    try:
        comfy_installed = ComfyUIRunner().is_installed()
        ad = ROOT / "apps" / "angles"
        if (ad / "app.json").is_file():
            mf = _json.loads((ad / "app.json").read_text(encoding="utf-8"))
            missing_models = []
            for m in mf.get("models") or []:
                fname = Path(str(m.get("file") or "")).name
                mdir = str(m.get("dir") or "")
                if fname and not (ROOT / "models" / mdir / fname).is_file():
                    missing_models.append(m)
            angles_ready = comfy_installed and len(missing_models) == 0
            angles_missing_gb = round(sum(float(m.get("gb", 0.0)) for m in missing_models), 2)
    except Exception as e:
        log.debug("angles app readiness probe failed: %s", e)

    dl_jobs = routes_post.get_local_model_download_status()
    return {
        "sd_cli_installed": sd_runner.is_installed(),
        "sd_cli_models": sd_models,
        "downloads": dl_jobs,
        "ollama": ollama_info,
        "comfyui": {
            "installed": comfy_installed,
            "angles_ready": angles_ready,
            "angles_missing_gb": angles_missing_gb,
        },
    }


@route("GET", "/api/v2_keyframes")
def _v2_keyframes(r: Request):
    """Return all scenes & shots from shots/shotlist.json with keyframe PNG status, turnaround refs, and accurate Steps 08-12 prompts."""
    import json
    from studio_app import keyframe_context

    slug = r.q("project")
    if not slug:
        return {"scenes": [], "look": "", "total_shots": 0, "rendered_shots": 0, "gemini_ready": False}
    pd = pdir(slug, "book")

    ctx = keyframe_context.load_keyframe_project_context(slug, pd)
    look = ctx["look"]
    hybrid_mode = ctx["hybrid_mode"]

    saved_prompts: dict[str, Any] = {}
    locked_ids: set[str] = set()
    pending_edits_map: dict[str, Any] = {}
    anchors_map: dict[str, str] = {}
    kf_meta = pd / "keyframes_v2.json"
    if kf_meta.is_file():
        try:
            kf_doc = json.loads(kf_meta.read_text(encoding="utf-8")) or {}
            saved_prompts = kf_doc.get("prompts") or {}
            locked_ids = {str(x) for x in (kf_doc.get("locked") or [])}
            pending_edits_map = kf_doc.get("pending_edits") or {}
            raw_anchors = kf_doc.get("anchors") or {}
            if isinstance(raw_anchors, dict):
                anchors_map = {str(k): str(v) for k, v in raw_anchors.items() if str(k).strip() and str(v).strip()}
        except Exception as e:
            log.debug("keyframes_v2.json read failed: %s", e)

    sl_path = pd / "shots" / "shotlist.json"
    raw_scenes: list[Any] = []
    if sl_path.is_file():
        try:
            raw_scenes = (json.loads(sl_path.read_text(encoding="utf-8")) or {}).get("scenes") or []
        except Exception as e:
            log.debug("shotlist.json read failed: %s", e)

    scenes = []
    total_shots = 0
    rendered_shots = 0
    missing_set_plates: list[str] = []
    seen_missing_locs: set[str] = set()

    for sc in raw_scenes:
        if not isinstance(sc, dict):
            continue
        sc_id = str(sc.get("id") or sc.get("scene") or "S001")
        heading = str(sc.get("heading") or "")
        anchor_shot_id = anchors_map.get(sc_id, "")
        sc_seed = keyframe_context.compute_scene_seed(slug, sc_id)
        _sc_loc_tok, sc_set_img, sc_loc_names = keyframe_context.match_location_context(ctx, heading)
        sc_has_set_plate = bool(sc_set_img and sc_set_img.is_file())
        sc_set_plate_url = ""
        if sc_has_set_plate and sc_set_img is not None:
            try:
                sc_set_plate_url = f"/file/{slug}/{sc_set_img.relative_to(pd).as_posix()}"
            except ValueError:
                sc_set_plate_url = ""
        elif heading or sc_loc_names:
            loc_label = sc_loc_names[0] if sc_loc_names else heading
            loc_key = loc_label.lower()
            if loc_key not in seen_missing_locs:
                seen_missing_locs.add(loc_key)
                missing_set_plates.append(loc_label)

        raw_sc_shots = [sh for sh in (sc.get("shots") or []) if isinstance(sh, dict)]
        shots_out = []
        prev_sh_raw: dict[str, Any] | None = None
        prev_prompt_eff = ""
        prev_rendered_id = ""

        for idx, sh in enumerate(raw_sc_shots, start=1):
            n = int(sh.get("n") or idx)
            sid = f"{sc_id}-{n:02d}"
            stype = str(sh.get("type") or "MS")
            lens = sh.get("lens_mm") or 35
            secs = sh.get("seconds") or 4.0
            comp = str(sh.get("composition") or "").strip()
            act = str(sh.get("action") or "").strip()

            info = keyframe_context.build_shot_keyframe_info(sh, sc_id, heading, ctx)
            default_prompt = info["default_prompt"]
            attention_notes = list(info["attention_notes"])
            chars = list(info["characters"])

            raw_saved = str(saved_prompts.get(sid) or "").strip()
            is_locked = sid in locked_ids
            broken_saved = bool(raw_saved) and not is_locked and keyframe_context.is_saved_prompt_broken_or_stale(raw_saved, info)
            # Auto-heal clearly broken legacy prompts (e.g. "MOM: mom" or missing matched location details) on unlocked shots
            effective_prompt = default_prompt if (not raw_saved or broken_saved) else raw_saved
            prompt_outdated = bool(raw_saved and not broken_saved and not is_locked and raw_saved != default_prompt)

            cam_mode = "none"
            rec_strength: float | None = None
            if prev_sh_raw is not None:
                cam_mode, rec_strength = keyframe_context.detect_camera_continuity(
                    sh, prev_sh_raw, effective_prompt, prev_prompt_eff
                )

            png_rel = f"keyframes/{sid}.png"
            png_path = pd / png_rel
            has_img = png_path.is_file() and png_path.stat().st_size > 200
            p1_rel = f"keyframes/{sid}_pass1.png"
            p1_path = pd / p1_rel
            has_p1 = p1_path.is_file() and p1_path.stat().st_size > 200
            total_shots += 1
            if has_img:
                rendered_shots += 1

            shots_out.append({
                "id": sid,
                "scene": sc_id,
                "n": n,
                "type": stype,
                "lens_mm": lens,
                "movement": str(sh.get("movement") or "static"),
                "seconds": secs,
                "action": act or comp[:120],
                "expression": str(sh.get("expression") or "").strip(),
                "characters": chars,
                "char_refs": info["char_refs"],
                "matched_locations": info["matched_locations"],
                "set_ref_url": info["set_ref_url"],
                "default_prompt": default_prompt,
                "prompt": effective_prompt,
                "prompt_outdated": prompt_outdated,
                "auto_upgraded": broken_saved,
                "camera_match_mode": cam_mode,
                "recommended_strength": rec_strength,
                "prev_rendered_id": prev_rendered_id,
                "is_anchor": bool(anchor_shot_id and anchor_shot_id == sid),
                "has_image": has_img,
                "has_pass1": has_p1,
                "pass1_url": f"/file/{slug}/{p1_rel}" if has_p1 else "",
                "locked": is_locked,
                "pending_edits": list(pending_edits_map.get(sid) or []),
                "image_url": f"/file/{slug}/{png_rel}" if has_img else "",
                "needs_attention": bool(attention_notes) and not has_img,
                "attention_reason": "; ".join(attention_notes),
            })
            prev_sh_raw = sh
            prev_prompt_eff = effective_prompt
            if has_img:
                prev_rendered_id = sid
        scenes.append({
            "id": sc_id,
            "heading": heading,
            "scene_seed": sc_seed,
            "anchor_shot_id": anchor_shot_id,
            "has_set_plate": sc_has_set_plate,
            "set_plate_url": sc_set_plate_url,
            "shots": shots_out,
        })

    gemini_ready = False
    try:
        import run_gemini_omni
        gemini_ready = bool(run_gemini_omni.get_gemini_api_key())
    except Exception as e:
        log.debug("gemini_omni probe failed: %s", e)

    # Collect Step 10 character sheets/front views for Step 17 Two-Pass Hybrid picker
    cast_sheets: list[dict[str, Any]] = []
    t_dir = pd / "assets" / "turnarounds"
    if t_dir.is_dir():
        seen_c: set[str] = set()
        for pat, kind_lbl in (("*_sheet.png", "3-Panel Sheet"), ("*_front.png", "Front View")):
            for p in sorted(t_dir.glob(pat)):
                if p.stat().st_size <= 100:
                    continue
                cname = p.stem.rsplit("_", 1)[0].replace("_", " ").strip().upper()
                if cname in seen_c:
                    continue
                seen_c.add(cname)
                rel_book = p.relative_to(pd).as_posix()
                cast_sheets.append({
                    "name": cname,
                    "kind": kind_lbl,
                    "url": f"/file/{slug}/{rel_book}",
                    "rel_book": rel_book,
                })

    return {
        "scenes": scenes,
        "look": look,
        "hybrid_mode": hybrid_mode,
        "cast_sheets": cast_sheets,
        "set_plates_count": ctx["set_plates_count"],
        "missing_set_plates": missing_set_plates,
        "total_shots": total_shots,
        "rendered_shots": rendered_shots,
        "gemini_ready": gemini_ready,
    }


@route("GET", "/api/v2_turnarounds")
def _v2_turnarounds(r: Request):
    """Return all characters for the active book dynamically synced with Step 08 dossiers & wardrobe_states.json."""
    import json

    slug = r.q("project")
    if not slug:
        return {"characters": [], "look": "pixar_3d"}
    pd = pdir(slug, "book")

    look = "pixar_3d"
    hybrid_mode: dict[str, Any] = {}
    gp_path = pd / "global_params.json"
    if gp_path.is_file():
        try:
            gp_doc = json.loads(gp_path.read_text(encoding="utf-8")) or {}
            look = str(gp_doc.get("look") or look)
            if isinstance(gp_doc.get("hybrid_mode"), dict):
                hybrid_mode = gp_doc["hybrid_mode"]
        except Exception as e:
            log.debug("global_params.json read failed: %s", e)

    chars = {}
    def _add(name, desc="", prefer=False):
        clean = str(name or "").strip()
        if not clean:
            return
        k = clean.lower()
        if k not in chars:
            chars[k] = {"name": clean, "desc": str(desc or "").strip()}
        elif desc and (prefer or not chars[k]["desc"]):
            chars[k]["desc"] = str(desc).strip()

    for cb_file in (pd / f"{slug}.json", pd / "continuity.json"):
        if cb_file.is_file():
            try:
                cb = json.loads(cb_file.read_text(encoding="utf-8")) or {}
                for c in cb.get("characters") or []:
                    if isinstance(c, dict):
                        _add(c.get("name"), c.get("token") or c.get("description") or "")
                break
            except Exception as e:
                log.debug("continuity book %s read failed: %s", cb_file.name, e)
    cov_path = pd / "readin" / "coverage.json"
    if cov_path.is_file():
        try:
            cov = json.loads(cov_path.read_text(encoding="utf-8")) or {}
            for c in cov.get("characters") or []:
                if isinstance(c, dict):
                    _add(c.get("name"), c.get("description") or c.get("role") or "")
                elif isinstance(c, str):
                    _add(c)
        except Exception as e:
            log.debug("coverage.json read failed: %s", e)
    sp_dir = pd / "screenplay"
    if sp_dir.is_dir():
        for sf in sorted(sp_dir.glob("scene-*.json")):
            try:
                sc = json.loads(sf.read_text(encoding="utf-8")) or {}
                for el in sc.get("elements") or []:
                    if isinstance(el, dict) and el.get("type") == "dialogue" and el.get("character"):
                        _add(el["character"])
            except Exception as e:
                log.debug("skipping unreadable scene %s: %s", sf.name, e)
                continue

    # Always prefer latest Step 08 saved character dossiers (load full per-character JSON, never truncated index preview)
    try:
        for ch in character_tokens.list_characters(slug) or []:
            if isinstance(ch, dict) and ch.get("name"):
                full_ch = character_tokens.load_character(slug, str(ch["name"])) or ch
                vt = str(full_ch.get("visual_token") or full_ch.get("token") or "").strip()
                clothing = str(full_ch.get("clothing") or "").strip()
                desc = str(full_ch.get("description") or "").strip()
                notes = str(full_ch.get("consistency_notes") or "").strip()
                parts: list[str] = []
                # Ignore bare name-only visual_token (e.g. "mom") when richer description/notes exist
                if vt and (vt.lower() != str(ch["name"]).strip().lower() or not (desc or notes or clothing)):
                    parts.append(vt)
                if clothing and clothing.lower() not in " ".join(parts).lower():
                    parts.append(f"wearing {clothing}")
                extra = desc or notes
                if extra:
                    joined_words = set(re.findall(r"[a-z0-9]+", " ".join(parts).lower()))
                    extra_words = set(re.findall(r"[a-z0-9]+", extra.lower()))
                    overlap = (len(joined_words & extra_words) / max(1, len(extra_words))) if joined_words else 0.0
                    if overlap < 0.65:
                        parts.append(extra)
                combined = ". ".join(p.rstrip(". ") for p in parts if p)
                _add(ch["name"], combined, prefer=True)
                ck = str(ch["name"]).strip().lower()
                if ck in chars:
                    chars[ck]["archetype"] = str(full_ch.get("archetype") or "")
                    chars[ck]["style_override"] = str(full_ch.get("style_override") or "")
    except Exception as e:
        log.debug("character_tokens read failed: %s", e)

    # Load Step 08 per-scene/location wardrobe states
    ws_map = {}
    ws_path = pd / "wardrobe_states.json"
    if ws_path.is_file():
        try:
            raw_ws = json.loads(ws_path.read_text(encoding="utf-8")) or {}
            ws_map = {str(k).lower(): v for k, v in raw_ws.items() if isinstance(v, list)}
        except Exception as e:
            log.debug("wardrobe_states.json read failed: %s", e)

    out: list[dict[str, Any]] = []
    for item in chars.values():
        safe = "".join(c if c.isalnum() else "_" for c in item["name"].lower()).strip("_") or "char"
        states = [st for st in (ws_map.get(item["name"].lower()) or []) if isinstance(st, dict) and str(st.get("wardrobe") or "").strip()]

        outfits = []
        if states:
            for idx, st in enumerate(states, start=1):
                sc_lbl = str(st.get("scenes") or f"Outfit {idx}").strip()
                loc_lbl = str(st.get("location") or "").strip()
                w_txt = str(st.get("wardrobe") or "").strip()
                oid = f"outfit{idx}"
                views = {}
                for v in ("front", "three_quarter", "profile"):
                    rel = f"assets/turnarounds/{safe}_{oid}_{v}.png"
                    p = pd / rel
                    # Fallback to legacy base filename for outfit1 if already generated
                    if not (p.is_file() and p.stat().st_size > 100) and idx == 1:
                        leg = f"assets/turnarounds/{safe}_{v}.png"
                        if (pd / leg).is_file() and (pd / leg).stat().st_size > 100:
                            rel, p = leg, pd / leg
                    ok = p.is_file() and p.stat().st_size > 100
                    views[v] = {"has_image": ok, "image_url": f"/file/{slug}/{rel}" if ok else ""}
                sh_rel = f"assets/turnarounds/{safe}_{oid}_sheet.png"
                sh_p = pd / sh_rel
                if not (sh_p.is_file() and sh_p.stat().st_size > 100) and idx == 1:
                    leg_sh = f"assets/turnarounds/{safe}_sheet.png"
                    if (pd / leg_sh).is_file() and (pd / leg_sh).stat().st_size > 100:
                        sh_rel, sh_p = leg_sh, pd / leg_sh
                sh_ok = sh_p.is_file() and sh_p.stat().st_size > 100
                outfits.append({
                    "id": oid,
                    "scenes": sc_lbl,
                    "location": loc_lbl,
                    "wardrobe": w_txt,
                    "views": views,
                    "sheet": {"has_image": sh_ok, "image_url": f"/file/{slug}/{sh_rel}" if sh_ok else ""},
                })
        else:
            views = {}
            for v in ("front", "three_quarter", "profile"):
                rel = f"assets/turnarounds/{safe}_{v}.png"
                p = pd / rel
                ok = p.is_file() and p.stat().st_size > 100
                views[v] = {"has_image": ok, "image_url": f"/file/{slug}/{rel}" if ok else ""}
            sh_rel = f"assets/turnarounds/{safe}_sheet.png"
            sh_p = pd / sh_rel
            sh_ok = sh_p.is_file() and sh_p.stat().st_size > 100
            outfits.append({
                "id": "default",
                "scenes": "All Scenes",
                "location": "",
                "wardrobe": item["desc"],
                "views": views,
                "sheet": {"has_image": sh_ok, "image_url": f"/file/{slug}/{sh_rel}" if sh_ok else ""},
            })

        out.append({
            "name": item["name"],
            "slug": safe,
            "desc": item["desc"],
            "archetype": item.get("archetype", ""),
            "style_override": item.get("style_override", ""),
            "outfits": outfits,
            "views": outfits[0]["views"],
        })

    import character_identity
    t_dir = pd / "assets" / "turnarounds"
    overrides = character_identity.load_identity_overrides(pd)
    id_map = character_identity.build_cast_identity_map(out, t_dir, overrides=overrides)
    for entry in out:
        ident = dict(id_map.get(entry["name"].lower()) or {})
        ref_file = ident.pop("ref_source_file", "")
        ident["ref_source_url"] = f"/file/{slug}/assets/turnarounds/{ref_file}" if ref_file else ""
        entry["identity"] = ident
    return {"characters": out, "look": look, "hybrid_mode": hybrid_mode}


@route("GET", "/api/v2_postprod")
def _v2_postprod(r: Request):
    """Unified dynamic state for Steps 19 (Polish), 20 (Timeline), 21 (Audio Mix), and 22 (Premiere & Export)."""
    import json

    slug = r.q("project")
    if not slug:
        return {"project": "", "title": "", "polish": {}, "timeline": {}, "mix": {}, "exports": {}}
    pd = pdir(slug, "book")
    title = slug.replace("_", " ").title()
    cov_path = pd / "readin" / "coverage.json"
    if cov_path.is_file():
        try:
            cov = json.loads(cov_path.read_text(encoding="utf-8")) or {}
            if cov.get("title"):
                title = str(cov["title"])
        except Exception as e:
            log.debug("coverage.json read failed: %s", e)

    # Discover rendered media dynamically for this book
    kf_files = sorted((pd / "keyframes").glob("*.png")) if (pd / "keyframes").is_dir() else []
    vid_files = []
    for vdir in (pd / "videos" / "gemini_omni_12_flash", pd / "videos"):
        if vdir.is_dir():
            vid_files.extend(sorted(vdir.glob("*.mp4")))
    dlg_files = sorted((pd / "audio" / "dialogue").glob("*.wav")) if (pd / "audio" / "dialogue").is_dir() else []
    foley_master = pd / "audio" / "foley" / "foley_master.wav"
    score_master = pd / "audio" / "score" / "score_master.wav"
    mix_master = pd / "audio" / "mix" / "master_mix.wav"
    film_master = pd / "films" / "master_cut.mp4"
    shorts_master = pd / "films" / "shorts_9x16.mp4"
    sp_fountain = pd / "exports" / f"{slug}.fountain"
    edl_file = pd / "exports" / "timeline.edl"
    stems_zip = pd / "exports" / "audio_stems.zip"

    # Load saved polish / timeline / mix settings
    pp_path = pd / "postprod_v2.json"
    saved: dict[str, Any] = {}
    if pp_path.is_file():
        try:
            saved = json.loads(pp_path.read_text(encoding="utf-8")) or {}
        except Exception:
            saved = {}

    # Build timeline summary from shots/shotlist.json
    total_shots = 0
    total_sec = 0.0
    tl_scenes = []
    sl_path = pd / "shots" / "shotlist.json"
    if sl_path.is_file():
        try:
            sl = json.loads(sl_path.read_text(encoding="utf-8")) or {}
            for sc in sl.get("scenes") or []:
                shs = sc.get("shots") or []
                sc_sec = sum(float(s.get("seconds") or 4.0) for s in shs if isinstance(s, dict))
                total_shots += len(shs)
                total_sec += sc_sec
                tl_scenes.append({"id": str(sc.get("id") or ""), "heading": str(sc.get("heading") or ""), "shots": len(shs), "seconds": round(sc_sec, 1)})
        except Exception as e:
            log.debug("shotlist.json read failed: %s", e)

    def _furl(p, kind: str = "file") -> str:
        if not (p.is_file() and p.stat().st_size > 64):
            return ""
        rel = p.relative_to(pd).as_posix()
        return f"/{kind}/{slug}/{rel}"

    preview_video = _furl(film_master) or (_furl(vid_files[0]) if vid_files else "")
    polish_cfg = saved.get("polish") or {}
    mix_cfg = saved.get("mix") or {}
    tl_cfg = saved.get("timeline") or {}

    return {
        "project": slug,
        "title": title,
        "counts": {
            "keyframes": len(kf_files),
            "videos": len(vid_files),
            "dialogue_wavs": len(dlg_files),
            "has_foley": foley_master.is_file(),
            "has_score": score_master.is_file(),
            "total_shots": total_shots,
            "total_seconds": round(total_sec, 1),
        },
        "polish": {
            "lipsync_mode": polish_cfg.get("lipsync_mode") or "gemini_native",
            "upscale_target": polish_cfg.get("upscale_target") or "1080p",
            "deflicker": bool(polish_cfg.get("deflicker", True)),
        },
        "timeline": {
            "crossfade_sec": float(tl_cfg.get("crossfade_sec", 0.5)),
            "use_keyframe_fallback": bool(tl_cfg.get("use_keyframe_fallback", True)),
            "scenes": tl_scenes,
            "master_video_url": _furl(film_master),
        },
        "mix": {
            "dialogue_db": float(mix_cfg.get("dialogue_db", 0.0)),
            "foley_db": float(mix_cfg.get("foley_db", -3.0)),
            "score_db": float(mix_cfg.get("score_db", -6.0)),
            "ducking": bool(mix_cfg.get("ducking", True)),
            "lufs": int(mix_cfg.get("lufs", -16)),
            "master_audio_url": _furl(mix_master),
        },
        "exports": {
            "preview_video_url": preview_video,
            "master_mp4_url": _furl(film_master, "download"),
            "shorts_mp4_url": _furl(shorts_master, "download"),
            "master_audio_url": _furl(mix_master, "download"),
            "fountain_url": _furl(sp_fountain, "download"),
            "edl_url": _furl(edl_file, "download"),
            "stems_zip_url": _furl(stems_zip, "download"),
        },
    }


@route("GET", "/api/v2_wardrobe_states")
def _v2_wardrobe_states(r: Request):
    """Return per-character scene/location wardrobe states from wardrobe_states.json."""
    import json

    slug = r.q("project")
    if not slug:
        return {"states": {}}
    pd = pdir(slug, "book")
    ws_path = pd / "wardrobe_states.json"
    if ws_path.is_file():
        try:
            data = json.loads(ws_path.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                return {"states": data}
        except Exception as e:
            log.debug("wardrobe_states.json read failed: %s", e)
    return {"states": {}}


@route("GET", "/api/v2_sets_hidden")
def _v2_sets_hidden(r: Request):
    """Return Step 11 deleted/hidden location set names and custom set ordering."""
    import json

    slug = r.q("project")
    if not slug:
        return {"deleted": [], "order": []}
    pd = pdir(slug, "book")
    deleted: list[str] = []
    order: list[str] = []
    for fname in ("sets_deleted.json", "sets_state.json"):
        p = pd / fname
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                continue
            raw_del = data.get("deleted")
            if isinstance(raw_del, list):
                for x in raw_del:
                    k = str(x).strip().lower()
                    if k and k not in deleted:
                        deleted.append(k)
            raw_ord = data.get("order")
            if isinstance(raw_ord, list):
                order = [str(x).strip().lower() for x in raw_ord if str(x).strip()]
        except Exception as e:
            log.debug("%s read failed: %s", fname, e)
    # Remove any deleted set from order so numbering stays contiguous
    del_set = set(deleted)
    order = [x for x in order if x not in del_set]
    custom_sets: list[dict[str, Any]] = []
    cs_path = pd / "sets_custom.json"
    if cs_path.is_file():
        try:
            raw_cs = json.loads(cs_path.read_text(encoding="utf-8")) or {}
            if isinstance(raw_cs, dict):
                for k_cs, val in raw_cs.items():
                    if isinstance(val, dict) and str(k_cs).strip().lower() not in del_set:
                        custom_sets.append({
                            "name": str(val.get("name") or k_cs).strip(),
                            "description": str(val.get("description") or "").strip(),
                            "lighting": str(val.get("lighting") or "").strip(),
                            "reserve_2d_gaps": bool(val.get("reserve_2d_gaps", False)),
                            "gap_notes": str(val.get("gap_notes") or "").strip(),
                        })
        except Exception as e:
            log.debug("sets_custom.json read failed: %s", e)
    set_images: dict[str, str] = {}
    sets_img_dir = pd / "assets" / "sets"
    if sets_img_dir.is_dir():
        for sp in sorted(sets_img_dir.glob("*")):
            if sp.is_file() and sp.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and sp.stat().st_size > 100:
                if "__view_" not in sp.stem.lower() and not sp.stem.lower().endswith("_baseline"):
                    set_images[sp.stem.lower()] = f"/file/{slug}/assets/sets/{sp.name}"

    # Load multi-view metadata, imported reference photos, converted plates, and pinned baselines
    set_views: dict[str, Any] = {}
    views_path = pd / "sets_views.json"
    if views_path.is_file():
        try:
            raw_v = json.loads(views_path.read_text(encoding="utf-8")) or {}
            raw_sets = raw_v.get("sets") if isinstance(raw_v, dict) else {}
            if isinstance(raw_sets, dict):
                for sk, sdata in raw_sets.items():
                    if not isinstance(sdata, dict):
                        continue
                    sk_low = str(sk).strip().lower()
                    if sk_low in del_set:
                        continue
                    b_vid = str(sdata.get("baseline_view_id") or "").strip()
                    b_snap = str(sdata.get("baseline_snapshot") or "").strip()
                    b_snap_p = (pd / b_snap) if b_snap else None
                    b_url = (
                        f"/file/{slug}/{b_snap}"
                        if (b_snap_p and b_snap_p.is_file() and b_snap_p.stat().st_size > 100)
                        else ""
                    )
                    views_out: list[dict[str, Any]] = []
                    for vw in sdata.get("views") or []:
                        if not isinstance(vw, dict):
                            continue
                        vid = str(vw.get("id") or "main").strip()
                        ref_rel = str(vw.get("ref_image") or "").strip()
                        conv_rel = str(vw.get("converted_image") or "").strip()
                        ref_ok = bool(ref_rel and (pd / ref_rel).is_file() and (pd / ref_rel).stat().st_size > 100)
                        conv_ok = bool(conv_rel and (pd / conv_rel).is_file() and (pd / conv_rel).stat().st_size > 100)
                        views_out.append({
                            "id": vid,
                            "label": str(vw.get("label") or ("Establishing View" if vid == "main" else vid)).strip(),
                            "notes": str(vw.get("notes") or "").strip(),
                            "has_ref": ref_ok,
                            "ref_url": f"/file/{slug}/{ref_rel}" if ref_ok else "",
                            "ref_rel": ref_rel if ref_ok else "",
                            "has_converted": conv_ok,
                            "converted_url": f"/file/{slug}/{conv_rel}" if conv_ok else "",
                            "converted_rel": conv_rel if conv_ok else "",
                            "is_baseline": bool(b_vid and vid == b_vid and b_url),
                        })
                    set_views[sk_low] = {
                        "baseline_view_id": b_vid if b_url else "",
                        "baseline_url": b_url,
                        "views": views_out,
                    }
        except Exception as e:
            log.debug("sets_views.json read failed: %s", e)

    # Also return active Step 09 film style summary so Step 11 shows what imported photos convert into
    import character_types_registry as ctr

    film_style_label = "Film Visual Style"
    gp_path = pd / "global_params.json"
    if gp_path.is_file():
        try:
            gp = json.loads(gp_path.read_text(encoding="utf-8")) or {}
            raw_hm = gp.get("hybrid_mode")
            hm: dict[str, Any] = raw_hm if isinstance(raw_hm, dict) else {}
            look_id = str(hm.get("world_style") or "live_action") if hm.get("enabled") else str(gp.get("look") or "")
            st_rec = ctr.get_style(look_id) if look_id else None
            if st_rec:
                film_style_label = str(st_rec.get("name") or st_rec.get("label") or look_id)
            elif str(gp.get("positives") or "").strip():
                film_style_label = str(gp["positives"]).strip().split(",")[0][:48]
        except Exception as e:
            log.debug("global_params style label read failed: %s", e)

    return {
        "deleted": deleted,
        "order": order,
        "custom": custom_sets,
        "set_images": set_images,
        "set_views": set_views,
        "film_style_label": film_style_label,
    }


@route("GET", "/api/character_types")
def _character_types(r: Request):
    """Return all built-in + custom visual styles (with motion cadence) and character archetypes."""
    import character_types_registry as ctr

    return ctr.registry_payload()


@route("GET", "/api/v2_cast_references")
def _v2_cast_references(r: Request):
    """Return all uploaded Step 08 cast reference images and Step 10 Front View turnarounds for a book."""
    import character_identity

    slug = r.q("project")
    if not slug:
        return {"references": []}
    pd = pdir(slug, "book")
    repo_root = pd.parent.parent.parent
    refs: list[dict[str, str]] = []
    seen_rel: set[str] = set()

    def _add(char_label: str, path: Path, source: str) -> None:
        if not path.is_file() or path.stat().st_size <= 100:
            return
        try:
            rel_repo = path.relative_to(repo_root).as_posix()
            rel_book = path.relative_to(pd).as_posix()
        except ValueError:
            return
        if rel_repo in seen_rel:
            return
        seen_rel.add(rel_repo)
        refs.append({
            "character": char_label,
            "label": f"{char_label} ({source})",
            "url": f"/file/{slug}/{rel_book}",
            "rel_path": rel_repo,
            "source": source,
            "slug": character_identity.safe_char_slug(char_label),
        })

    # 1. Step 08 uploaded cast reference images
    cast_ref_dir = pd / "assets" / "cast_refs"
    if cast_ref_dir.is_dir():
        for p in sorted(cast_ref_dir.glob("*_ref.*")):
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                cname = p.stem[: -len("_ref")].replace("_", " ").strip().upper()
                _add(cname, p, "Step 08 Reference")

    # 2. Step 10 3-Panel Pro Character Sheets & Front View turnarounds
    t_dir = pd / "assets" / "turnarounds"
    if t_dir.is_dir():
        for p in sorted(t_dir.glob("*_sheet.png")):
            cname = p.stem[: -len("_sheet")].replace("__", " ").replace("_", " ").strip().upper()
            _add(cname, p, "Step 10 3-Panel Sheet")
        for p in sorted(t_dir.glob("*_front.png")):
            cname = p.stem[: -len("_front")].replace("__", " ").replace("_", " ").strip().upper()
            _add(cname, p, "Step 10 Front View")

    # 3. Step 11 Location / Set Environments (for Multi-Ref Hybrid Single Prompts)
    sets_dir = pd / "assets" / "sets"
    if sets_dir.is_dir():
        for p in sorted(sets_dir.glob("*")):
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                sname = p.stem.replace("_", " ").strip().upper()
                _add(sname, p, "Step 11 Set")

    return {"project": slug, "references": refs}


@route("GET", "/api/v2_plate_audit")
def _v2_plate_audit_get(r: Request):
    """Return cached per-plate consistency audit report (`qa/plate_audit.json`) if available."""
    import json
    slug = str(r.q("project") or "").strip()
    if not slug:
        return {"status": "ok", "project": "", "sheets": [], "missing_plates": [], "unplated_stills": [], "warnings": []}
    pd = pdir(slug, "book")
    rp = pd / "qa" / "plate_audit.json"
    if rp.is_file():
        try:
            data = json.loads(rp.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as e:
            log.debug("failed reading cached plate_audit.json: %s", e)
    return {"status": "ok", "project": slug, "passed": False, "total_rendered_stills": 0, "plate_count": 0, "sheets": [], "missing_plates": [], "unplated_stills": [], "warnings": []}


@route("GET", "/api/v2_editing_style")
def _v2_editing_style_get(r: Request):
    """Return cached Reference-Video Editing Style Guide (`references/editing_style.json`) if present."""
    import json

    slug = str(r.q("project") or "").strip()
    if not slug:
        return {"status": "ok", "project": "", "has_guide": False}
    pd = pdir(slug, "book")
    jp = pd / "references" / "editing_style.json"
    if jp.is_file():
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["has_guide"] = True
                return data
        except Exception as e:
            log.debug("failed reading editing_style.json: %s", e)
    return {"status": "ok", "project": slug, "has_guide": False}


@route("GET", "/api/v2_code_drawn_templates")
def _v2_code_drawn_templates_get(r: Request):
    """List available deterministic 60 fps code-drawn title card and explainer templates."""
    import code_drawn_templates
    return {"status": "ok", "templates": code_drawn_templates.CODE_DRAWN_TEMPLATES}


@route("GET", "/api/v2_early_prompt_audit")
def _v2_early_prompt_audit_get(r: Request):
    """Return persisted early-stage prompt continuity audit reports for Steps 03, 04, 05, 06, 07, and 12."""
    from studio_app import early_prompt_audit

    slug = str(r.q("project") or "").strip()
    if not slug:
        return {"status": "ok", "project": "", "steps": {}, "updated_at": 0.0}
    pd = pdir(slug, "book")
    data = early_prompt_audit.load_reports(pd)
    return {"status": "ok", "project": slug, **data}


@route("GET", "/api/v2_render_job")
def _v2_render_job_get(r: Request):
    """Poll status/result of an async background render job submitted with `async: true`."""
    from studio_app import render_jobs

    jid = str(r.q("id") or "").strip()
    if not jid:
        return {"status": "ok", "jobs": render_jobs.list_render_jobs()}
    rec = render_jobs.get_render_job(jid)
    if rec is None:
        raise HttpError(404, f"unknown render job: {jid}")
    return {"status": "ok", "job": rec}


@route("GET", "/api/v2_props_backdrops")
def _v2_props_backdrops_get(r: Request):
    """Step 07: List Visual Props & Dynamic Backdrops (auto-extracted from script on first load)."""
    from studio_app import props_backdrops

    slug = str(r.q("project") or "").strip()
    if not slug:
        return {"status": "ok", "project": "", "items": [], "counts": {"total": 0, "props": 0, "backdrops": 0, "with_images": 0}}
    pd = pdir(slug, "book")
    return props_backdrops.load_props_backdrops(pd, slug, auto_extract=True)




