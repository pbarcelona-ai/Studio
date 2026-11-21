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
    profiles = {}
    baselines_raw = {}
    cleared_baselines = set()
    dialect = "american"
    vc_path = pd / "voice_cast.json"
    vdata = {}
    if vc_path.is_file():
        try:
            vdata = json.loads(vc_path.read_text(encoding="utf-8")) or {}
            vc = vdata.get("cast") or {}
            profiles = vdata.get("profiles") or {}
            baselines_raw = vdata.get("baselines") or {}
            cleared_baselines = {str(c).lower() for c in (vdata.get("cleared_baselines") or [])}
            dialect = vdata.get("dialect") or "american"
        except Exception:
            pass

    from .routes_post import VOICE_LIBRARY_DIR, _voice_library_load, find_kokoro_python
    global_lib = _voice_library_load()
    global_lib_lc = {str(k).lower(): v for k, v in global_lib.items() if isinstance(v, dict)}

    vc_lc = {str(k).lower(): v for k, v in vc.items()}
    prof_lc = {str(k).lower(): v for k, v in profiles.items() if isinstance(v, dict)}
    baselines = {}
    for ch_name, binfo in baselines_raw.items():
        if not isinstance(binfo, dict) or not binfo.get("file"):
            continue
        bf = pd / str(binfo["file"])
        if bf.is_file() and bf.stat().st_size > 100:
            baselines[ch_name] = {
                "file": str(binfo["file"]),
                "source": str(binfo.get("source") or "custom"),
                "text": str(binfo.get("text") or ""),
                "saved_to_library": bool(binfo.get("saved_to_library", ch_name.lower() in global_lib_lc)),
                "source_project": str(binfo.get("source_project") or slug),
                "audio_url": f"/file/{slug}/{binfo['file']}",
            }

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

    import shutil
    import subprocess

    gemini_ready = False
    try:
        import run_gemini_omni
        gemini_ready = bool(run_gemini_omni.get_gemini_api_key())
    except Exception:
        pass
    kokoro_py = find_kokoro_python()
    kokoro_ready = bool(kokoro_py)
    say_bin = shutil.which("say")
    macos_ready = bool(say_bin)
    macos_voices = []
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
        except Exception:
            pass
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
                g_entry = global_lib_lc.get(char.lower()) or {}
                cp = prof_lc.get(char.lower()) or g_entry or {}
                # Auto-inherit baseline WAV from global cross-film library for new films if not cleared/set yet
                if (
                    char.lower() not in {k.lower() for k in baselines}
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
                            "audio_url": f"/file/{slug}/{rel_f}",
                        }
                voice = ov.get("voice") or vc_lc.get(char.lower()) or cp.get("kokoro_voice") or ("bm_fable" if dialect == "british" else "am_puck")
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
                    "gemini_voice": ov.get("gemini_voice") or cp.get("gemini_voice") or "",
                    "kokoro_voice": ov.get("kokoro_voice") or cp.get("kokoro_voice") or voice,
                    "kokoro_blend": ov.get("kokoro_blend") or cp.get("kokoro_blend") or "",
                    "macos_voice": ov.get("macos_voice") or cp.get("macos_voice") or "",
                    "persona": ov.get("persona") if "persona" in ov else cp.get("persona", ""),
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
    saved = {}
    if sd_path.is_file():
        try:
            saved = json.loads(sd_path.read_text(encoding="utf-8")) or {}
        except Exception:
            saved = {}

    scenes = []
    saved_scenes = saved.get("scenes") if isinstance(saved.get("scenes"), dict) else {}
    sp_dir = pd / "screenplay"
    if sp_dir.is_dir():
        for sp_file in sorted(sp_dir.glob("scene-*.json")):
            try:
                sc = json.loads(sp_file.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            sc_id = str(sc.get("scene") or sp_file.stem.replace("scene-", ""))
            heading = str(sc.get("heading") or "")
            actions = [str(el.get("text") or "").strip() for el in (sc.get("elements") or []) if isinstance(el, dict) and el.get("type") == "action"]
            hint = (" ".join(actions))[:180]
            low = (heading + " " + hint).lower()
            if any(w in low for w in ("launch", "blast", "liftoff", "ignition", "roar", "shake", "shaking", "rocket", "thruster")):
                auto_preset, auto_cue = "action_launch", "Rockets burning, spaceship hull shaking, heavy ignition rumble"
                auto_mood = "epic"
            elif any(w in low for w in ("rain", "window", "living room", "kitchen", "bedroom", "home", "house")):
                auto_preset, auto_cue = "rainy_home", "Rain pattering on window, warm indoor room ambiance"
                auto_mood = "cozy"
            elif any(w in low for w in ("ring", "ice", "storm", "wind", "geyser", "crater", "titan", "enceladus")):
                auto_preset, auto_cue = "cosmic_storm", "Atmospheric wind gusts, shimmering ice particles, planetary rumble"
                auto_mood = "mysterious"
            elif any(w in low for w in ("night", "backyard", "park", "garden", "grass", "tree")):
                auto_preset, auto_cue = "forest_nature", "Evening breeze and gentle outdoor ambient air"
                auto_mood = "playful"
            else:
                auto_preset, auto_cue = "space_adventure", "Starship bridge hum, cockpit console chimes, space ambiance"
                auto_mood = "wonder"

            ov = saved_scenes.get(sc_id) if isinstance(saved_scenes.get(sc_id), dict) else {}
            sc_wav = pd / "audio" / "foley" / f"scene_{sc_id}.wav"
            has_sc_wav = sc_wav.is_file() and sc_wav.stat().st_size > 100
            scenes.append({
                "scene": sc_id,
                "heading": heading,
                "hint": hint,
                "sfx_cue": ov.get("sfx_cue") or auto_cue,
                "sfx_preset": ov.get("sfx_preset") or auto_preset,
                "score_mood": ov.get("score_mood") or auto_mood,
                "has_sfx": has_sc_wav,
                "sfx_url": f"/file/{slug}/audio/foley/scene_{sc_id}.wav" if has_sc_wav else "",
            })

    foley_wav = pd / "audio" / "foley" / "foley_master.wav"
    score_wav = pd / "audio" / "score" / "score_master.wav"
    foley_cfg = dict(saved.get("foley") or {})
    score_cfg = dict(saved.get("score") or {})

    return {
        "sfx_mode": str(saved.get("sfx_mode") or "hybrid"),
        "foley": {
            "prompt": foley_cfg.get("prompt") or "Starship bridge hum, cockpit console telemetry chimes, and clean sci-fi instrumentation.",
            "preset": foley_cfg.get("preset") or "space_adventure",
            "duration": int(foley_cfg.get("duration") or 12),
            "has_audio": foley_wav.is_file() and foley_wav.stat().st_size > 100,
            "audio_url": f"/file/{slug}/audio/foley/foley_master.wav" if (foley_wav.is_file() and foley_wav.stat().st_size > 100) else "",
        },
        "score": {
            "prompt": score_cfg.get("prompt") or "Sweeping cinematic orchestral strings, warm French horns, and sparkling celesta arpeggios in major key.",
            "mood": score_cfg.get("mood") or "wonder",
            "duration": int(score_cfg.get("duration") or 12),
            "has_audio": score_wav.is_file() and score_wav.stat().st_size > 100,
            "audio_url": f"/file/{slug}/audio/score/score_master.wav" if (score_wav.is_file() and score_wav.stat().st_size > 100) else "",
        },
        "scenes": scenes,
    }


@route("GET", "/api/v2_keyframes")
def _v2_keyframes(r: Request):
    """Return all scenes & shots from shots/shotlist.json with keyframe PNG status and editable prompts."""
    import json

    slug = r.q("project")
    if not slug:
        return {"scenes": [], "look": "", "total_shots": 0, "rendered_shots": 0, "gemini_ready": False}
    pd = pdir(slug, "book")

    look = "pixar_3d"
    gp_path = pd / "global_params.json"
    if gp_path.is_file():
        try:
            gp = json.loads(gp_path.read_text(encoding="utf-8")) or {}
            look = str(gp.get("look") or look)
        except Exception:
            pass

    # Character visual/wardrobe tokens (prefer Step 08 saved dossiers, fallback to continuity book)
    char_tokens = {}
    loc_tokens = {}
    for cb_file in (pd / f"{slug}.json", pd / "continuity.json"):
        if cb_file.is_file():
            try:
                cb = json.loads(cb_file.read_text(encoding="utf-8")) or {}
                for c in cb.get("characters") or []:
                    if isinstance(c, dict) and c.get("name") and c.get("token"):
                        char_tokens[str(c["name"]).lower()] = str(c["token"]).strip()
                for loc in cb.get("locations") or []:
                    if isinstance(loc, dict) and loc.get("name") and loc.get("token"):
                        loc_tokens[str(loc["name"]).lower()] = str(loc["token"]).strip()
                break
            except Exception:
                pass
    try:
        for ch in character_tokens.list_characters(slug) or []:
            if isinstance(ch, dict) and ch.get("name"):
                vt = str(ch.get("visual_token") or ch.get("token") or "").strip()
                desc = str(ch.get("description") or "").strip()
                if vt or desc:
                    char_tokens[str(ch["name"]).lower()] = vt or desc
    except Exception:
        pass

    def _match_location_token(heading_text: str) -> str:
        low_h = heading_text.lower()
        for lname, ltok in loc_tokens.items():
            if lname and lname in low_h:
                return ltok
        return ""

    # Load per-character scene/location wardrobe states (e.g. S001-S003 Living Room vs S004-S015 Spaceship)
    wardrobe_states = {}
    ws_path = pd / "wardrobe_states.json"
    if ws_path.is_file():
        try:
            raw_ws = json.loads(ws_path.read_text(encoding="utf-8")) or {}
            wardrobe_states = {str(k).lower(): v for k, v in raw_ws.items() if isinstance(v, list)}
        except Exception:
            pass

    def _scene_num(sid: str) -> int:
        digits = "".join(c for c in str(sid or "") if c.isdigit())
        return int(digits) if digits else 0

    def _match_wardrobe_state(char_name: str, sc_id: str, heading_text: str) -> str:
        states = wardrobe_states.get(char_name.lower()) or []
        if not states:
            return ""
        sn = _scene_num(sc_id)
        low_h = heading_text.lower()
        for st in states:
            if not isinstance(st, dict) or not str(st.get("wardrobe") or "").strip():
                continue
            sc_spec = str(st.get("scenes") or "").strip()
            loc_spec = str(st.get("location") or "").strip().lower()
            # Match scene range like "S001-S003" or comma list "S001, S002"
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
                    w = str(st["wardrobe"]).strip()
                    loc_lbl = str(st.get("location") or "").strip()
                    return f"{w} (in {loc_lbl})" if loc_lbl else w
            if loc_spec and loc_spec in low_h:
                return str(st["wardrobe"]).strip()
        return ""

    saved_prompts = {}
    locked_ids = set()
    kf_meta = pd / "keyframes_v2.json"
    if kf_meta.is_file():
        try:
            kf_doc = json.loads(kf_meta.read_text(encoding="utf-8")) or {}
            saved_prompts = kf_doc.get("prompts") or {}
            locked_ids = {str(x) for x in (kf_doc.get("locked") or [])}
        except Exception:
            pass

    sl_path = pd / "shots" / "shotlist.json"
    raw_scenes = []
    if sl_path.is_file():
        try:
            raw_scenes = (json.loads(sl_path.read_text(encoding="utf-8")) or {}).get("scenes") or []
        except Exception:
            pass

    look_labels = {
        "live_action": "cinematic live-action film still, photorealistic, 35mm film grain",
        "claymation": "handcrafted stop-motion claymation still, tactile miniature set, warm studio lighting",
        "pixar_3d": "Pixar 3D animated film still, expressive characters, rich volumetric lighting",
        "pixar_disney": "classic stylized 3D animated feature film still, warm storybook lighting",
        "travel_poster": "vintage illustrated travel poster art style, bold graphic composition",
        "cyberpunk_3d": "stylized 3D sci-fi cinematic still, dramatic neon rim lighting",
    }
    style_prefix = look_labels.get(look, "cinematic 3D animated film still")

    scenes = []
    total_shots = 0
    rendered_shots = 0
    for sc in raw_scenes:
        if not isinstance(sc, dict):
            continue
        sc_id = str(sc.get("id") or sc.get("scene") or "S001")
        heading = str(sc.get("heading") or "")
        shots_out = []
        for idx, sh in enumerate(sc.get("shots") or [], start=1):
            if not isinstance(sh, dict):
                continue
            n = int(sh.get("n") or idx)
            sid = f"{sc_id}-{n:02d}"
            stype = str(sh.get("type") or "MS")
            lens = sh.get("lens_mm") or 35
            secs = sh.get("seconds") or 4.0
            comp = str(sh.get("composition") or "").strip()
            act = str(sh.get("action") or "").strip()
            light = str(sh.get("lighting") or "").strip()
            chars = [str(c) for c in (sh.get("characters") or []) if c]
            toks = []
            attention_notes = []
            for c in chars:
                base_tok = char_tokens.get(c.lower(), "")
                sc_wardrobe = _match_wardrobe_state(c, sc_id, heading)
                if sc_wardrobe and base_tok:
                    toks.append(f"{c}: {base_tok} | SCENE WARDROBE: {sc_wardrobe}")
                elif sc_wardrobe:
                    toks.append(f"{c}: {sc_wardrobe}")
                elif base_tok:
                    toks.append(f"{c}: {base_tok}")
                    if "striped" in base_tok.lower() or len(base_tok) < 25:
                        attention_notes.append(f"{c}'s wardrobe needs specific solid colors/outfit in Step 08")
                else:
                    attention_notes.append(f"{c} has no visual/wardrobe description in Step 08")
            loc_tok = _match_location_token(heading)

            bits = [f"{style_prefix}, {stype} shot ({lens}mm lens)"]
            if loc_tok:
                bits.append(f"LOCKED LOCATION ({heading}): {loc_tok}")
            elif heading:
                bits.append(f"LOCKED LOCATION: {heading}")
            if comp:
                bits.append(comp)
            if act and act.lower() not in comp.lower():
                bits.append(act)
            if light:
                bits.append(f"Lighting: {light}")
            if toks:
                bits.append("LOCKED CHARACTERS & SINGULAR WARDROBE (exact clothing colors & outfit unchanged in this scene): " + "; ".join(toks[:4]))
            default_prompt = ". ".join(b.rstrip(".") for b in bits if b)

            png_rel = f"keyframes/{sid}.png"
            png_path = pd / png_rel
            has_img = png_path.is_file() and png_path.stat().st_size > 200
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
                "characters": chars,
                "default_prompt": default_prompt,
                "prompt": saved_prompts.get(sid) or default_prompt,
                "has_image": has_img,
                "locked": sid in locked_ids,
                "image_url": f"/file/{slug}/{png_rel}" if has_img else "",
                "needs_attention": bool(attention_notes) and not has_img,
                "attention_reason": "; ".join(attention_notes),
            })
        scenes.append({"id": sc_id, "heading": heading, "shots": shots_out})

    gemini_ready = False
    try:
        import run_gemini_omni
        gemini_ready = bool(run_gemini_omni.get_gemini_api_key())
    except Exception:
        pass

    return {
        "scenes": scenes,
        "look": look,
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
    gp_path = pd / "global_params.json"
    if gp_path.is_file():
        try:
            look = str((json.loads(gp_path.read_text(encoding="utf-8")) or {}).get("look") or look)
        except Exception:
            pass

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
            except Exception:
                pass
    cov_path = pd / "readin" / "coverage.json"
    if cov_path.is_file():
        try:
            cov = json.loads(cov_path.read_text(encoding="utf-8")) or {}
            for c in cov.get("characters") or []:
                if isinstance(c, dict):
                    _add(c.get("name"), c.get("description") or c.get("role") or "")
                elif isinstance(c, str):
                    _add(c)
        except Exception:
            pass
    sp_dir = pd / "screenplay"
    if sp_dir.is_dir():
        for sf in sorted(sp_dir.glob("scene-*.json")):
            try:
                sc = json.loads(sf.read_text(encoding="utf-8")) or {}
                for el in sc.get("elements") or []:
                    if isinstance(el, dict) and el.get("type") == "dialogue" and el.get("character"):
                        _add(el["character"])
            except Exception:
                continue

    # Always prefer latest Step 08 saved character dossiers
    try:
        for ch in character_tokens.list_characters(slug) or []:
            if isinstance(ch, dict) and ch.get("name"):
                vt = str(ch.get("visual_token") or ch.get("token") or "").strip()
                desc = str(ch.get("description") or "").strip()
                combined = f"{vt}. {desc}".strip(". ") if (vt and desc and vt.lower() not in desc.lower()) else (desc or vt)
                _add(ch["name"], combined, prefer=True)
    except Exception:
        pass

    # Load Step 08 per-scene/location wardrobe states
    ws_map = {}
    ws_path = pd / "wardrobe_states.json"
    if ws_path.is_file():
        try:
            raw_ws = json.loads(ws_path.read_text(encoding="utf-8")) or {}
            ws_map = {str(k).lower(): v for k, v in raw_ws.items() if isinstance(v, list)}
        except Exception:
            pass

    out = []
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
                outfits.append({
                    "id": oid,
                    "scenes": sc_lbl,
                    "location": loc_lbl,
                    "wardrobe": w_txt,
                    "views": views,
                })
        else:
            views = {}
            for v in ("front", "three_quarter", "profile"):
                rel = f"assets/turnarounds/{safe}_{v}.png"
                p = pd / rel
                ok = p.is_file() and p.stat().st_size > 100
                views[v] = {"has_image": ok, "image_url": f"/file/{slug}/{rel}" if ok else ""}
            outfits.append({
                "id": "default",
                "scenes": "All Scenes",
                "location": "",
                "wardrobe": item["desc"],
                "views": views,
            })

        out.append({"name": item["name"], "slug": safe, "desc": item["desc"], "outfits": outfits, "views": outfits[0]["views"]})
    return {"characters": out, "look": look}


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
        except Exception:
            pass

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
    saved = {}
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
        except Exception:
            pass

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
        except Exception:
            pass
    return {"states": {}}




