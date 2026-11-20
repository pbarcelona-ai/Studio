"""GET routes of the JSON API."""
import character_tokens
import detect_scene_changes
import model_advisor
from layout import project_dir as pdir
from bookkit import SLUG_RE

from .api import HttpError, Request, route
from .adapt import adaptation_data, cast_lock_data, grading_data, screenplay_data
from .chapters import chapter_list, chapter_text
from .export import credits_get, exports_data, shares_data
from .cleanup import cleanup_scan, files_inventory
from .common import num
from .config import ROOT
from .gallery import compare_data, library, showcase
from .generation import film_status
from .gpus import suggestions
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
    since = max(num({"since": r.q("since", "0")}, "since", 0, int, 0), 0)
    with JOB.lock:
        return {"lines": JOB.lines[since:], "next": len(JOB.lines), "running": JOB.running, "current": JOB.current, "queued": len(JOB.queue)}


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
        raise HttpError(400, str(e))
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
    interactions = {}
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
    except Exception:
        pass
    return {"cast": {}, "dialect": "american", "mode": "dialogue"}


@route("GET", "/api/v2_dialogue")
def _v2_dialogue(r: Request):
    """Extract all spoken dialogue lines from screenplay/scene-*.json merged with voice_cast.json and dialogue_lines.json."""
    import json

    slug = r.q("project")
    if not slug:
        return {"lines": [], "scenes": [], "dialect": "american", "cast": {}}
    pd = pdir(slug, "book")
    vc = {}
    dialect = "american"
    vc_path = pd / "voice_cast.json"
    if vc_path.is_file():
        try:
            vdata = json.loads(vc_path.read_text(encoding="utf-8")) or {}
            vc = vdata.get("cast") or {}
            dialect = vdata.get("dialect") or "american"
        except Exception:
            pass
    vc_lc = {str(k).lower(): v for k, v in vc.items()}

    saved = {}
    saved_engine = ""
    dl_path = pd / "dialogue_lines.json"
    if dl_path.is_file():
        try:
            ddata = json.loads(dl_path.read_text(encoding="utf-8")) or {}
            saved = ddata.get("lines") or {}
            saved_engine = str(ddata.get("engine") or "").strip()
        except Exception:
            pass

    import importlib.util, shutil
    gemini_ready = False
    try:
        import run_gemini_omni
        gemini_ready = bool(run_gemini_omni.get_gemini_api_key())
    except Exception:
        pass
    kokoro_ready = bool(importlib.util.find_spec("kokoro"))
    macos_ready = bool(shutil.which("say"))
    if not saved_engine:
        saved_engine = "gemini-tts" if gemini_ready else ("kokoro" if kokoro_ready else "macos-say")

    lines = []
    scenes_seen = []
    sp_dir = pd / "screenplay"
    if sp_dir.is_dir():
        for sp_file in sorted(sp_dir.glob("scene-*.json")):
            try:
                sc = json.loads(sp_file.read_text(encoding="utf-8")) or {}
            except Exception:
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
                ov = saved.get(lid) if isinstance(saved.get(lid), dict) else {}
                voice = ov.get("voice") or vc_lc.get(char.lower()) or ("bm_fable" if dialect == "british" else "am_puck")
                wav_rel = f"audio/dialogue/{lid}.wav"
                wav_path = pd / wav_rel
                has_audio = wav_path.is_file() and wav_path.stat().st_size > 100
                if sc_id not in scenes_seen:
                    scenes_seen.append(sc_id)
                lines.append({
                    "id": lid,
                    "scene": sc_id,
                    "heading": heading,
                    "character": char,
                    "text": ov.get("text", text),
                    "note": ov.get("note", note),
                    "voice": voice,
                    "emotion": ov.get("emotion", "natural"),
                    "speed": float(ov.get("speed", 1.0)),
                    "has_audio": has_audio,
                    "audio_url": f"/file/{slug}/{wav_rel}" if has_audio else "",
                })
    return {
        "lines": lines,
        "scenes": scenes_seen,
        "dialect": dialect,
        "cast": vc,
        "engine": saved_engine,
        "engines": {
            "gemini_tts": gemini_ready,
            "kokoro": kokoro_ready,
            "macos_say": macos_ready,
        },
    }




