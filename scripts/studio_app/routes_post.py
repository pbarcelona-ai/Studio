"""POST routes of the JSON API (uploads are streamed by handler.py instead)."""
import json
import shutil
import subprocess
from pathlib import Path

import character_tokens
import detect_scene_changes
import redo_audio
import setup_check
from bookkit import SLUG_RE
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .api import HttpError, Request, route
from .adapt import adaptation_edit, budget_data, cast_lock_edit, grading_edit, screenplay_edit
from .chapters import chapter_edit_action
from .export import credits_set, export_step, share_create, share_revoke
from .cleanup import cleanup_delete, trash_files
from .common import PlanError, resolve_project_file
from .config import ADULT_FLAG, ENV_PATH, PROJECTS, ROOT
from .direction import animatic_step, creative_direction, creative_direction_get, new_scene, upscale_step, voice_cast
from .gallery import save_rating
from .generation import clean_stages
from .jobs import JOB
from .kaggle_cleanup import AUTO_CLEAN_OFF, delete_notebooks, kaggle_cleanup_delete, recreate_notebooks
from .kaggle_runs import fetch_step, kernel_output, kernel_ref
from .llm import describe_image, enhance_prompt, review_result
from .media import film_step
from .overview import setup_status
from .planner import build_plan, chapter_shots, estimate
from .projects import save_global_params
from .scenes import prompt_revert, prompt_save, prompt_suggest
from .single_prompts import expand_idea, face_check_step, open_folder
from .steps import shell_form
from .path import feedback_keep, path_confirm, shot_move_action
from .takes import critic_action, pick_take, reset_storyboard, retake, review_action

STARTED = {"started": 1}


def _start(steps, body):
    """Start a job, or queue it behind the running one when the page asks (queue: true). Returns the answer for the page."""
    from .resume import busy_elsewhere
    why = busy_elsewhere()
    if why:
        raise PlanError(why)
    ahead = JOB.start(steps, body, queue=bool(body.get("queue")))
    return {"started": len(steps), "queued": ahead}


def _need_idle():
    if JOB.running:
        raise PlanError("a job is running; wait for it to finish first")


@route("POST", "/api/plan")
def _plan(r: Request):
    return {"steps": [{"label": s["label"], "cmd": shell_form(s)} for s in build_plan(r.body)]}


@route("POST", "/api/run")
def _run(r: Request):
    steps = build_plan(r.body, commit=True)       # prompt mode writes its rows here, not when previewing
    return _start(steps, r.body)


@route("POST", "/api/stop")
def _stop(r: Request):
    JOB.stop()
    return {"stopping": True}


@route("POST", "/api/chapter_shots")
def _chapter_shots(r: Request):
    return chapter_shots(r.body.get("project", ""), r.body)


@route("POST", "/api/adaptation_edit")
def _adaptation_edit(r: Request):
    _need_idle()
    return adaptation_edit(r.body)


@route("POST", "/api/cast_lock")
def _cast_lock(r: Request):
    _need_idle()
    return cast_lock_edit(r.body)


@route("POST", "/api/export")
def _export(r: Request):
    return _start([export_step(r.body)], r.body)


@route("POST", "/api/share")
def _share(r: Request):
    return share_create(r.body)


@route("POST", "/api/share_revoke")
def _share_revoke(r: Request):
    return share_revoke(r.body)


@route("POST", "/api/credits")
def _credits(r: Request):
    _need_idle()
    return credits_set(r.body)


@route("POST", "/api/grading")
def _grading(r: Request):
    _need_idle()
    return grading_edit(r.body)


@route("POST", "/api/screenplay_edit")
def _screenplay_edit(r: Request):
    _need_idle()
    return screenplay_edit(r.body)


@route("POST", "/api/budget")
def _budget(r: Request):
    return budget_data(r.body)


@route("POST", "/api/chapter_edit")
def _chapter_edit(r: Request):
    _need_idle()                        # a running step reads the chapter files
    return chapter_edit_action(r.body)


@route("POST", "/api/retake")
def _retake(r: Request):
    return retake(r.body)


@route("POST", "/api/review")
def _review(r: Request):
    return review_action(r.body)


@route("POST", "/api/critic")
def _critic(r: Request):
    return critic_action(r.body)


@route("POST", "/api/pick_take")
def _pick_take(r: Request):
    return pick_take(r.body)


@route("POST", "/api/estimate")
def _estimate(r: Request):
    return {"text": estimate(r.body)}


@route("POST", "/api/setup_save")
def _setup_save(r: Request):
    try:
        saved = setup_check.save(r.body)
    except ValueError as e:
        raise PlanError(str(e)) from e
    return {"saved": saved, **setup_status()}


@route("POST", "/api/setup_test")
def _setup_test(r: Request):
    return setup_check.test_kaggle(path=ENV_PATH)


@route("POST", "/api/prompt_suggest")
def _prompt_suggest(r: Request):
    return {"suggestions": prompt_suggest(r.body)}


@route("POST", "/api/clip_length")
def _clip_length(r: Request):
    from .cliplen import clip_length_action
    return clip_length_action(r.body)


@route("POST", "/api/get_results")
def _get_results(r: Request):
    from .results import results_steps
    steps, opt = results_steps(r.body)
    out = _start(steps, opt)
    return {**out, "runs": [s["label"] for s in steps]}


@route("POST", "/api/match_pictures")
def _match_pictures(r: Request):
    from .old_pictures import match_all
    return match_all(r.body)


@route("POST", "/api/auto_assign_pictures")
def _auto_assign(r: Request):
    from .old_pictures import auto_assign
    return auto_assign(r.body)


@route("POST", "/api/assign_picture")
def _assign_picture(r: Request):
    from .old_pictures import assign_picture
    return assign_picture(r.body)


@route("POST", "/api/swap_pictures")
def _swap_pictures(r: Request):
    from .old_pictures import swap_pictures
    return swap_pictures(r.body)


@route("POST", "/api/sessions")
def _sessions_post(r: Request):
    from .resume import sessions_action
    return sessions_action(r.body)


@route("POST", "/api/path_confirm")
def _path_confirm(r: Request):
    return path_confirm(r.body)


@route("POST", "/api/shot_move")
def _shot_move(r: Request):
    return shot_move_action(r.body)


@route("POST", "/api/feedback_keep")
def _feedback_keep(r: Request):
    return feedback_keep(r.body)


@route("POST", "/api/storyboard_reset")
def _storyboard_reset(r: Request):
    return reset_storyboard(r.body)


@route("POST", "/api/prompt_save")
def _prompt_save(r: Request):
    return prompt_save(r.body)


@route("POST", "/api/prompt_revert")
def _prompt_revert(r: Request):
    return prompt_revert(r.body)


@route("POST", "/api/trash_files")
def _trash_files(r: Request):
    _need_idle()
    b = r.body
    return trash_files(str(b.get("project", "")), str(b.get("folder", "")), [str(n) for n in b.get("names", [])])


@route("POST", "/api/cleanup_delete")
def _cleanup_delete(r: Request):
    _need_idle()
    return cleanup_delete(r.body.get("categories") or [])


@route("POST", "/api/kaggle_cleanup_delete")
def _kaggle_cleanup_delete(r: Request):
    return kaggle_cleanup_delete()


@route("POST", "/api/adult_models")
def _adult_models(r: Request):
    """Show (and allow) or hide (and refuse) the adult-content models. Kept in a flag file next to the Studio so it survives a restart."""
    if r.body.get("enabled"):
        ADULT_FLAG.touch()
    else:
        ADULT_FLAG.unlink(missing_ok=True)
    return {"enabled": ADULT_FLAG.exists()}


@route("POST", "/api/auto_cleanup")
def _auto_cleanup(r: Request):
    if r.body.get("on"):
        AUTO_CLEAN_OFF.unlink(missing_ok=True)
    else:
        AUTO_CLEAN_OFF.parent.mkdir(parents=True, exist_ok=True)
        AUTO_CLEAN_OFF.touch()
    return {"on": not AUTO_CLEAN_OFF.exists()}


@route("POST", "/api/recreate_notebooks")
def _recreate_notebooks(r: Request):
    return recreate_notebooks()


@route("POST", "/api/delete_notebooks")
def _delete_notebooks(r: Request):
    return delete_notebooks()


@route("POST", "/api/kernel_output")
def _kernel_output(r: Request):
    try:
        return kernel_output(kernel_ref(r.body.get("ref")))
    except subprocess.TimeoutExpired as e:
        raise PlanError("Kaggle download timed out; try again") from e


@route("POST", "/api/make_film")
def _make_film(r: Request):
    slug, selection, step = film_step(r.body)
    (pdir(slug) / "films" / "_selection.json").write_text(json.dumps(selection, indent=1))
    JOB.start([step], r.body)
    return {"clips": len(selection["clips"])}


@route("POST", "/api/new_scene")
def _new_scene(r: Request):
    return new_scene(r.body)


@route("POST", "/api/creative_direction")
def _creative_direction(r: Request):
    return creative_direction(r.body)


@route("POST", "/api/creative_direction_get")
def _creative_direction_get(r: Request):
    return creative_direction_get(r.body)


@route("POST", "/api/voice_cast")
def _voice_cast(r: Request):
    return voice_cast(r.body)


@route("POST", "/api/upscale")
def _upscale(r: Request):
    return _start([upscale_step(r.body)], r.body)


@route("POST", "/api/face_check")
def _face_check(r: Request):
    return _start([face_check_step(r.body)], r.body)


@route("POST", "/api/make_animatic")
def _make_animatic(r: Request):
    return _start([animatic_step(r.body)], r.body)


@route("POST", "/api/fetch")
def _fetch(r: Request):
    return _start([fetch_step(r.body)], r.body)


@route("POST", "/api/open_reference_folder")
def _open_reference_folder(r: Request):
    return {"folder": open_folder(r.body.get("series"), r.body.get("name", ""))}


@route("POST", "/api/describe_image")
def _describe_image(r: Request):
    try:
        return describe_image(r.body)
    except RuntimeError as e:
        raise PlanError(str(e)) from e


@route("POST", "/api/review_result")
def _review_result(r: Request):
    try:
        return review_result(r.body)
    except RuntimeError as e:
        raise PlanError(str(e)) from e


@route("POST", "/api/expand")
def _expand(r: Request):
    return {"prompts": expand_idea(r.body)}


@route("POST", "/api/enhance_prompt")
def _enhance_prompt(r: Request):
    return enhance_prompt(r.body)


@route("POST", "/api/global_params")
def _global_params(r: Request):
    project = r.body.get("project", "")
    if not project:
        raise HttpError(400, "project is required")
    save_global_params(project, r.body.get("positives", ""), r.body.get("negatives", ""))
    return {"saved": True}


@route("POST", "/api/rate")
def _rate(r: Request):
    return save_rating(r.body.get("key", ""), r.body.get("stars", 0), r.body.get("keep", False))


@route("POST", "/api/extract_frame")
def _extract_frame(r: Request):
    """Extract one frame of a video as a PNG next to it (OpenCV)."""
    project, video = r.body.get("project", ""), r.body.get("video", "")
    frame, model = r.body.get("frame", 16), r.body.get("model", "wan")
    if not project or not video:
        raise HttpError(400, "project and video are required")
    if not SLUG_RE.match(project):
        raise HttpError(400, "bad project name")
    if not isinstance(frame, int) or not 0 <= frame < 10**7:
        raise HttpError(400, "bad frame number")
    base = (pdir(project) / "videos").resolve()
    video_path = (base / str(model) / str(video)).resolve()
    if base not in video_path.parents:
        raise HttpError(400, "bad video path")
    if not video_path.is_file():
        raise HttpError(404, "video not found")
    output_path = video_path.parent / f"{video_path.stem}_frame{frame:04d}.png"
    try:
        import cv2
    except ImportError:
        raise HttpError(500, "OpenCV (cv2) not installed") from None
    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            raise HttpError(500, "could not open video")
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
        ok, img = cap.read()
    finally:
        cap.release()
    if not ok:
        raise HttpError(500, f"could not read frame {frame}")
    cv2.imwrite(str(output_path), img)
    if not output_path.exists():
        raise HttpError(500, "frame extraction failed - output not created")
    return {"success": True, "frame_path": str(output_path)}


def _inside_projects(path: Path, what: str) -> Path:
    try:
        path.resolve().relative_to(PROJECTS.resolve())
    except ValueError:
        raise HttpError(403, f"{what} must be within projects/") from None
    return path


@route("POST", "/api/copy_file")
def _copy_file(r: Request):
    """Copy a file to a destination within projects/."""
    source, dest = r.body.get("source", ""), r.body.get("dest", "")
    if not source or not dest:
        raise HttpError(400, "source and dest are required")
    src_path = _inside_projects(resolve_project_file(source), "source")
    dest_path = Path(dest)
    if not dest_path.is_absolute():
        dest_path = ROOT / dest_path
    _inside_projects(dest_path, "dest")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dest_path)
    return {"success": True, "dest": str(dest_path)}


# ---- /api/characters {action: ...}
def _ch_archetype(name: str):
    try:
        return character_tokens.CharacterArchetype(name)
    except ValueError:
        raise HttpError(400, f"unknown archetype: {name}") from None


def _book_slug(b: dict) -> str:
    project = str(b.get("project", "")).strip()
    if not SLUG_RE.match(project) or not pdir(project).is_dir():
        raise PlanError("unknown project")
    return project


def _ch_save(b):
    char = b.get("character", {})
    char["stages"] = clean_stages(char.get("stages"))
    return {"saved": True, "path": str(character_tokens.save_character(char))}


def _ch_use_reference(b):
    return {"updated": character_tokens.use_reference(b.get("series", ""), b.get("name", ""), b.get("path", ""))}


def _ch_add_reference(b):
    return {"updated": character_tokens.add_reference_image(b.get("series", ""), b.get("name", ""), b.get("image_path", ""))}


def _ch_update_lora(b):
    return {"updated": character_tokens.update_lora_info(b.get("series", ""), b.get("name", ""), b.get("lora_repo", ""),
                                                         b.get("trigger_word", ""), b.get("base_model", ""))}


def _ch_create(b):
    char = character_tokens.create_character_from_description(b.get("series", ""), b.get("name", ""), b.get("description", ""), b.get("visual_token", ""))
    return {"created": True, "character": char, "path": str(character_tokens.save_character(char))}


def _ch_delete(b):
    return {"deleted": character_tokens.delete_character(b.get("series", ""), b.get("name", ""))}


def _ch_archetypes(b):
    return {"archetypes": [{"value": a.value, "label": a.value.replace("_", " ").title()} for a in character_tokens.CharacterArchetype]}


def _ch_archetype_fields(b):
    return {"fields": character_tokens.get_archetype_fields(_ch_archetype(b.get("archetype", "")))}


def _ch_valid_values(b):
    field = b.get("field", "")
    return {"field": field, "values": character_tokens.get_valid_values(field)}


def _ch_sync(b):
    """Copy the characters of a project's continuity book file into the series chosen on the page. Adds only, unless overwrite is set (dry_run counts)."""
    project, series = _book_slug(b), str(b.get("series", "")).strip()
    if not series:
        raise PlanError("pick a series first")
    res = character_tokens.sync_from_book(project, series, overwrite=bool(b.get("overwrite")), dry_run=bool(b.get("dry_run")))
    if not res["continuity"]:
        raise PlanError(f"{project} has no continuity book file ({project}.json), so there is nothing to sync. Sync reads the file that "
                        f"\"Write the continuity book\" creates for a PDF or text book; imported books such as adam_eve do not have one.")
    return {**res, "count": res["added"]}


def _ch_send_to_book(b):
    """Copy the ticked series characters into the book's continuity book file (the reverse of sync). dry_run only counts."""
    project, series, names = _book_slug(b), str(b.get("series", "")).strip(), b.get("names")
    if not series or not isinstance(names, list) or not names or len(names) > 300 or not all(isinstance(n, str) and n.strip() for n in names):
        raise PlanError("pick a series and tick at least one character")
    try:
        res = character_tokens.send_to_book(project, series, [n.strip() for n in names], dry_run=bool(b.get("dry_run")))
    except ValueError as e:
        raise PlanError(str(e)) from e
    if not res["found"]:
        raise PlanError(f"{project} has no continuity book file ({project}.json) yet: write it first with the Continuity book step on the Import tab.")
    return res


def _ch_validate(b):
    name = b.get("archetype", "")
    errors = character_tokens.validate_character(b.get("character", {}), _ch_archetype(name) if name else None)
    return {"valid": not errors, "errors": errors}


def _ch_template(b):
    return {"template": character_tokens.create_character_template(_ch_archetype(b.get("archetype", "")), b.get("name", ""), b.get("series", ""))}


_CHARACTER_POST = {"save": _ch_save, "use_reference": _ch_use_reference, "add_reference": _ch_add_reference, "update_lora": _ch_update_lora,
                   "create": _ch_create, "delete": _ch_delete, "archetypes": _ch_archetypes, "archetype_fields": _ch_archetype_fields,
                   "valid_values": _ch_valid_values, "sync": _ch_sync, "send_to_book": _ch_send_to_book, "validate": _ch_validate,
                   "template": _ch_template}


@route("POST", "/api/characters")
def _characters(r: Request):
    action = r.body.get("action", "")
    fn = _CHARACTER_POST.get(action)
    if fn is None:
        raise HttpError(400, f"unknown action: {action}")
    return fn(r.body)


@route("POST", "/api/save_story")
def _save_story(r: Request):
    filename = str(r.body.get("filename") or "").strip()
    text = str(r.body.get("text") or "").strip()
    if not filename:
        filename = "my_story.txt"
    if not filename.endswith(".txt"):
        filename += ".txt"
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
    if not safe_name or safe_name.startswith("."):
        safe_name = "my_story.txt"

    books_dir = ROOT / "books"
    books_dir.mkdir(parents=True, exist_ok=True)
    target = books_dir / safe_name
    target.write_text(text, encoding="utf-8")
    return {"saved": True, "filename": safe_name, "path": str(target.relative_to(ROOT)), "bytes": len(text)}


@route("POST", "/api/redo_audio")
def _redo_audio(r: Request):
    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    if not pd.is_dir():
        raise PlanError(f"project not found: {slug}")
    mode = redo_audio.canonical_mode(str(r.body.get("mode") or "dialogue"))
    dialect = (str(r.body.get("dialect") or "").strip().lower()) or None
    narrator_voice = r.body.get("narrator_voice")
    incoming_cast = r.body.get("cast")
    rows = r.body.get("rows")

    # Load existing voice_cast.json, merge incoming cast, and apply dialect mapping
    vc_path = pd / "voice_cast.json"
    vc_data = {}
    if vc_path.is_file():
        try:
            vc_data = json.loads(vc_path.read_text(encoding="utf-8")) or {}
        except Exception:
            vc_data = {}
    merged_cast = dict(vc_data.get("cast") or {})
    if isinstance(incoming_cast, dict):
        for k, v in incoming_cast.items():
            if str(k).strip() and str(v or "").strip():
                merged_cast[str(k).strip()] = str(v).strip()
    if dialect in redo_audio.DIALECT_MAP:
        merged_cast = {k: redo_audio.map_voice_dialect(v, dialect) for k, v in merged_cast.items()}
    vc_data["cast"] = merged_cast
    vc_data["mode"] = mode
    if dialect:
        vc_data["dialect"] = dialect
    vc_path.write_text(json.dumps(vc_data, indent=2), encoding="utf-8")

    # If audio_shots.csv exists, also reconfigure CSVs non-destructively; otherwise return cleanly
    has_csv = (pd / "audio_shots.csv").is_file() or (pd / "audio_shots.master.csv").is_file()
    if has_csv:
        try:
            res = redo_audio.apply_audio_reconfiguration(
                pd,
                mode=mode,
                narrator_voice=narrator_voice,
                cast=merged_cast or None,
                dialect=dialect,
                rows=rows,
            )
            res["cast"] = merged_cast
            res["dialect"] = dialect or vc_data.get("dialect") or "american"
            res["csv_updated"] = True
            return {"status": "ok", "result": res}
        except Exception as e:
            raise PlanError(str(e)) from e

    return {
        "status": "ok",
        "result": {
            "mode": mode,
            "dialect": dialect or vc_data.get("dialect") or "american",
            "cast": merged_cast,
            "csv_updated": False,
            "note": "Voice cast & dialect saved to voice_cast.json (will apply automatically when audio shots are generated).",
        },
    }


@route("POST", "/api/redo_storyline")
def _redo_storyline(r: Request):
    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    scenes = r.body.get("scenes") or []
    changes = detect_scene_changes.detect_changed_scenes(pd)
    return {"status": "ok", "project": slug, "scenes": scenes, "changes": changes}


@route("POST", "/api/gemini_omni_key")
def _gemini_omni_key(r: Request):
    import run_gemini_omni

    key = str(r.body.get("api_key") or "").strip()
    if not key:
        raise PlanError("api_key is required")
    run_gemini_omni.save_gemini_api_key(key)
    return {"saved": True, "configured": True, "sdk_installed": run_gemini_omni.sdk_available()}


@route("POST", "/api/gemini_omni_generate")
def _gemini_omni_generate(r: Request):
    import run_gemini_omni

    prompt = str(r.body.get("prompt") or "").strip()
    if not prompt:
        raise PlanError("prompt is required")
    slug = str(r.body.get("project") or "").strip()
    shot_num = int(r.body.get("shot") or 1)
    duration = int(r.body.get("duration") or 10)
    resolution = str(r.body.get("resolution") or "720p")
    aspect_ratio = str(r.body.get("aspect_ratio") or "16:9")
    previous_interaction_id = (r.body.get("previous_interaction_id") or "").strip() or None
    first_frame = (r.body.get("first_frame") or "").strip() or None
    last_frame = (r.body.get("last_frame") or "").strip() or None
    ref_images = r.body.get("reference_images") or []
    strip_audio = bool(r.body.get("strip_audio"))

    if slug:
        out_dir = pdir(slug, "book") / "videos" / "gemini_omni_12_flash"
    else:
        out_dir = PROJECTS / "prompts" / "gemini_omni" / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"shot-{shot_num:03d}.mp4"

    try:
        res = run_gemini_omni.generate_omni_video(
            prompt=prompt,
            output_path=out_path,
            aspect_ratio=aspect_ratio,
            duration=duration,
            resolution=resolution,
            first_frame=first_frame,
            last_frame=last_frame,
            reference_images=ref_images,
            strip_audio=strip_audio,
            previous_interaction_id=previous_interaction_id,
        )
    except Exception as e:
        raise PlanError(run_gemini_omni.sanitize_error(e)) from e

    # Persist interaction_id sidecar so conversational turn-by-turn edits work seamlessly
    if res.get("interaction_id"):
        idx_path = out_dir / "interactions.json"
        idx = {}
        if idx_path.is_file():
            try:
                idx = json.loads(idx_path.read_text(encoding="utf-8")) or {}
            except Exception:
                idx = {}
        idx[f"shot-{shot_num:03d}"] = {
            "interaction_id": res["interaction_id"],
            "prompt": prompt,
            "resolution": res["resolution"],
            "duration": res["duration"],
        }
        idx_path.write_text(json.dumps(idx, indent=2), encoding="utf-8")

    return res


@route("POST", "/api/v2_dialogue_save")
def _v2_dialogue_save(r: Request):
    """Save edited dialogue text, voice, emotion, speed, and delivery notes to dialogue_lines.json."""
    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    dl_path = pd / "dialogue_lines.json"
    existing = {}
    if dl_path.is_file():
        try:
            existing = (json.loads(dl_path.read_text(encoding="utf-8")) or {}).get("lines") or {}
        except Exception:
            existing = {}
    incoming = r.body.get("lines")
    if isinstance(incoming, list):
        for item in incoming:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            lid = str(item["id"]).strip()
            existing[lid] = {
                "text": str(item.get("text") or "").strip(),
                "note": str(item.get("note") or "").strip(),
                "voice": str(item.get("voice") or "").strip(),
                "emotion": str(item.get("emotion") or "natural").strip(),
                "speed": max(0.5, min(1.8, float(item.get("speed") or 1.0))),
            }
    elif isinstance(r.body.get("id"), str) and r.body["id"].strip():
        lid = r.body["id"].strip()
        existing[lid] = {
            "text": str(r.body.get("text") or "").strip(),
            "note": str(r.body.get("note") or "").strip(),
            "voice": str(r.body.get("voice") or "").strip(),
            "emotion": str(r.body.get("emotion") or "natural").strip(),
            "speed": max(0.5, min(1.8, float(r.body.get("speed") or 1.0))),
        }
    dl_path.write_text(json.dumps({"lines": existing}, indent=2), encoding="utf-8")
    return {"status": "ok", "saved": len(existing)}


def _macos_voice_for_kokoro(voice_id: str, dialect: str = "american") -> str:
    """Map Kokoro voice IDs to distinct built-in macOS speech voices for instant local preview/render."""
    v = (voice_id or "").lower()
    is_uk = v.startswith("b") or dialect == "british"
    is_fem = v.startswith("af_") or v.startswith("bf_")
    if is_uk:
        if is_fem:
            return {"bf_emma": "Serena", "bf_alice": "Kate", "bf_isabella": "Martha", "bf_lily": "Serena"}.get(v, "Serena")
        return {"bm_fable": "Daniel", "bm_george": "Oliver", "bm_lewis": "Arthur", "bm_daniel": "Daniel"}.get(v, "Daniel")
    if is_fem:
        return {"af_bella": "Samantha", "af_sarah": "Allison", "af_nicole": "Ava", "af_heart": "Samantha"}.get(v, "Samantha")
    return {"am_puck": "Alex", "am_michael": "Tom", "am_adam": "Aaron", "am_eric": "Fred", "am_onyx": "Alex"}.get(v, "Samantha" if is_fem else "Alex")


@route("POST", "/api/v2_dialogue_render")
def _v2_dialogue_render(r: Request):
    """Render one or more dialogue lines to WAV files in <project>/audio/dialogue/<id>.wav."""
    import tempfile

    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    out_dir = pd / "audio" / "dialogue"
    out_dir.mkdir(parents=True, exist_ok=True)

    items = r.body.get("lines")
    if not isinstance(items, list) or not items:
        if r.body.get("id") and r.body.get("text"):
            items = [r.body]
        else:
            raise PlanError("lines (or id + text) required")

    dialect = str(r.body.get("dialect") or "american").strip().lower()
    say_bin = shutil.which("say")
    afconvert_bin = shutil.which("afconvert")
    if not say_bin:
        raise PlanError("Local speech synthesis ('say') is unavailable on this machine; install Kokoro-82M or use macOS.")

    avail = set()
    try:
        out = subprocess.check_output([say_bin, "-v", "?"], text=True, timeout=5)
        for ln in out.splitlines():
            parts = ln.strip().split()
            if parts:
                avail.add(parts[0])
    except Exception:
        pass

    rendered = []
    for item in items:
        lid = str(item.get("id") or "").strip()
        text = str(item.get("text") or "").strip()
        if not lid or not text:
            continue
        safe_id = "".join(c for c in lid if c.isalnum() or c in "-_")
        if not safe_id:
            continue
        voice_id = str(item.get("voice") or "").strip()
        speed = max(0.5, min(1.8, float(item.get("speed") or 1.0)))
        rate = int(round(185 * speed))
        mac_voice = _macos_voice_for_kokoro(voice_id, dialect)
        if avail and mac_voice not in avail:
            if (voice_id.lower().startswith("b") or dialect == "british") and "Daniel" in avail:
                mac_voice = "Daniel"
            elif "Samantha" in avail:
                mac_voice = "Samantha"
            else:
                mac_voice = ""

        wav_path = out_dir / f"{safe_id}.wav"
        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tf:
            aiff_path = Path(tf.name)
        try:
            cmd = [say_bin, "-r", str(rate), "-o", str(aiff_path)]
            if mac_voice:
                cmd.extend(["-v", mac_voice])
            cmd.append(text)
            subprocess.run(cmd, check=True, timeout=30)
            if afconvert_bin:
                subprocess.run([afconvert_bin, "-f", "WAVE", "-d", "LEI16@22050", str(aiff_path), str(wav_path)], check=True, timeout=20)
            else:
                shutil.copyfile(aiff_path, wav_path)
            rendered.append({
                "id": safe_id,
                "audio_url": f"/file/{slug}/audio/dialogue/{safe_id}.wav",
                "voice_used": mac_voice or "system-default",
            })
        finally:
            aiff_path.unlink(missing_ok=True)

    return {"status": "ok", "engine": "macos-say", "rendered": rendered}


