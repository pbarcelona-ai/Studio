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
    """Save edited dialogue text, voice, emotion, speed, delivery notes, and selected engine to dialogue_lines.json."""
    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    dl_path = pd / "dialogue_lines.json"
    existing_doc = {}
    if dl_path.is_file():
        try:
            existing_doc = json.loads(dl_path.read_text(encoding="utf-8")) or {}
        except Exception:
            existing_doc = {}
    existing = existing_doc.get("lines") if isinstance(existing_doc.get("lines"), dict) else {}
    engine = str(r.body.get("engine") or existing_doc.get("engine") or "").strip()
    incoming = r.body.get("lines")
    if isinstance(incoming, list):
        for item in incoming:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            lid = str(item["id"]).strip()
            prev = existing.get(lid) if isinstance(existing.get(lid), dict) else {}
            existing[lid] = {
                **prev,
                "text": str(item.get("text") if "text" in item else prev.get("text", "")).strip(),
                "note": str(item.get("note") if "note" in item else prev.get("note", "")).strip(),
                "voice": str(item.get("voice") if "voice" in item else prev.get("voice", "")).strip(),
                "gemini_voice": str(item.get("gemini_voice") if "gemini_voice" in item else prev.get("gemini_voice", "")).strip(),
                "kokoro_voice": str(item.get("kokoro_voice") if "kokoro_voice" in item else prev.get("kokoro_voice", "")).strip(),
                "kokoro_blend": str(item.get("kokoro_blend") if "kokoro_blend" in item else prev.get("kokoro_blend", "")).strip(),
                "macos_voice": str(item.get("macos_voice") if "macos_voice" in item else prev.get("macos_voice", "")).strip(),
                "persona": str(item.get("persona") if "persona" in item else prev.get("persona", "")).strip(),
                "emotion": str(item.get("emotion") if "emotion" in item else prev.get("emotion", "natural")).strip(),
                "speed": max(0.5, min(1.8, float(item.get("speed") if "speed" in item else prev.get("speed", 1.0)))),
            }
    elif isinstance(r.body.get("id"), str) and r.body["id"].strip():
        lid = r.body["id"].strip()
        prev = existing.get(lid) if isinstance(existing.get(lid), dict) else {}
        existing[lid] = {
            **prev,
            "text": str(r.body.get("text") if "text" in r.body else prev.get("text", "")).strip(),
            "note": str(r.body.get("note") if "note" in r.body else prev.get("note", "")).strip(),
            "voice": str(r.body.get("voice") if "voice" in r.body else prev.get("voice", "")).strip(),
            "gemini_voice": str(r.body.get("gemini_voice") if "gemini_voice" in r.body else prev.get("gemini_voice", "")).strip(),
            "kokoro_voice": str(r.body.get("kokoro_voice") if "kokoro_voice" in r.body else prev.get("kokoro_voice", "")).strip(),
            "kokoro_blend": str(r.body.get("kokoro_blend") if "kokoro_blend" in r.body else prev.get("kokoro_blend", "")).strip(),
            "macos_voice": str(r.body.get("macos_voice") if "macos_voice" in r.body else prev.get("macos_voice", "")).strip(),
            "persona": str(r.body.get("persona") if "persona" in r.body else prev.get("persona", "")).strip(),
            "emotion": str(r.body.get("emotion") if "emotion" in r.body else prev.get("emotion", "natural")).strip(),
            "speed": max(0.5, min(1.8, float(r.body.get("speed") if "speed" in r.body else prev.get("speed", 1.0)))),
        }
    dl_path.write_text(json.dumps({"engine": engine, "lines": existing}, indent=2), encoding="utf-8")
    return {"status": "ok", "saved": len(existing), "engine": engine}


@route("POST", "/api/v2_voice_profile_apply")
def _v2_voice_profile_apply(r: Request):
    """Save a character's voice profile (voice, blend, persona, speed) for ALL scenes while leaving per-line emotion/tone untouched."""
    slug = str(r.body.get("project") or "").strip()
    character = str(r.body.get("character") or "").strip()
    if not slug or not character:
        raise PlanError("project and character are required")

    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    vc_path = pd / "voice_cast.json"
    vdata = {}
    if vc_path.is_file():
        try:
            vdata = json.loads(vc_path.read_text(encoding="utf-8")) or {}
        except Exception:
            vdata = {}
    cast = vdata.get("cast") if isinstance(vdata.get("cast"), dict) else {}
    profiles = vdata.get("profiles") if isinstance(vdata.get("profiles"), dict) else {}

    existing_key = next((k for k in profiles if k.lower() == character.lower()), character)
    prof = dict(profiles.get(existing_key) or {})
    for field in ("gemini_voice", "kokoro_voice", "kokoro_blend", "macos_voice", "persona"):
        if field in r.body and r.body[field] is not None:
            prof[field] = str(r.body[field]).strip()
    if r.body.get("kokoro_voice"):
        cast_key = next((k for k in cast if k.lower() == character.lower()), character)
        cast[cast_key] = str(r.body["kokoro_voice"]).strip()
    profiles[existing_key] = prof
    vdata["cast"] = cast
    vdata["profiles"] = profiles
    vc_path.write_text(json.dumps(vdata, indent=2), encoding="utf-8")

    # Propagate profile to every dialogue line spoken by this character, WITHOUT touching each line's emotion/tone or note
    dl_path = pd / "dialogue_lines.json"
    ddata = {}
    if dl_path.is_file():
        try:
            ddata = json.loads(dl_path.read_text(encoding="utf-8")) or {}
        except Exception:
            ddata = {}
    saved_lines = ddata.get("lines") if isinstance(ddata.get("lines"), dict) else {}

    updated_count = 0
    sp_dir = pd / "screenplay"
    if sp_dir.is_dir():
        for sp_file in sorted(sp_dir.glob("scene-*.json")):
            try:
                sc = json.loads(sp_file.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            sc_id = str(sc.get("scene") or sp_file.stem.replace("scene-", ""))
            idx = 0
            for el in sc.get("elements") or []:
                if not isinstance(el, dict) or el.get("type") != "dialogue":
                    continue
                idx += 1
                if str(el.get("character") or "").strip().lower() != character.lower():
                    continue
                lid = f"{sc_id}-{idx:02d}"
                cur = dict(saved_lines.get(lid) or {})
                for field in ("gemini_voice", "kokoro_voice", "kokoro_blend", "macos_voice", "persona"):
                    if field in prof:
                        cur[field] = prof[field]
                if prof.get("kokoro_voice"):
                    cur["voice"] = prof["kokoro_voice"]
                # Preserve per-line emotion/tone and delivery note untouched!
                saved_lines[lid] = cur
                updated_count += 1

    ddata["lines"] = saved_lines
    dl_path.write_text(json.dumps(ddata, indent=2), encoding="utf-8")
    return {"status": "ok", "character": character, "profile": prof, "updated_lines": updated_count}


@route("POST", "/api/v2_dialogue_upload")
def _v2_dialogue_upload(r: Request):
    """Save a user-uploaded custom audio take (base64 WAV/MP3/M4A/AIFF) for a single dialogue line."""
    import base64
    import tempfile

    slug = str(r.body.get("project") or "").strip()
    lid = str(r.body.get("id") or "").strip()
    b64 = str(r.body.get("audio_base64") or "").strip()
    filename = str(r.body.get("filename") or "take.wav").strip()
    if not slug or not lid or not b64:
        raise PlanError("project, id, and audio_base64 are required")
    safe_id = "".join(c for c in lid if c.isalnum() or c in "-_")
    if not safe_id:
        raise PlanError("invalid line id")
    if "," in b64 and b64.startswith("data:"):
        b64 = b64.split(",", 1)[1]
    raw = base64.b64decode(b64)
    if len(raw) < 64:
        raise PlanError("uploaded audio file is empty")

    pd = pdir(slug, "book")
    out_dir = pd / "audio" / "dialogue"
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / f"{safe_id}.wav"

    if raw[:4] == b"RIFF":
        wav_path.write_bytes(raw)
    else:
        suffix = Path(filename).suffix or ".mp3"
        afconvert_bin = shutil.which("afconvert")
        ffmpeg_bin = shutil.which("ffmpeg")
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            tf.write(raw)
            tmp_in = Path(tf.name)
        try:
            if afconvert_bin:
                subprocess.run([afconvert_bin, "-f", "WAVE", "-d", "LEI16@24000", str(tmp_in), str(wav_path)], check=True, timeout=30)
            elif ffmpeg_bin:
                subprocess.run([ffmpeg_bin, "-y", "-i", str(tmp_in), str(wav_path)], check=True, timeout=30)
            else:
                wav_path.write_bytes(raw)
        finally:
            tmp_in.unlink(missing_ok=True)

    return {"status": "ok", "id": safe_id, "audio_url": f"/file/{slug}/audio/dialogue/{safe_id}.wav"}


@route("POST", "/api/v2_voice_baseline_set")
def _v2_voice_baseline_set(r: Request):
    """Lock a rendered dialogue take or uploaded audio clip as a character's permanent voice baseline (or clear it)."""
    import base64
    import tempfile

    slug = str(r.body.get("project") or "").strip()
    character = str(r.body.get("character") or "").strip()
    if not slug or not character:
        raise PlanError("project and character are required")

    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    vc_path = pd / "voice_cast.json"
    vdata = {}
    if vc_path.is_file():
        try:
            vdata = json.loads(vc_path.read_text(encoding="utf-8")) or {}
        except Exception:
            vdata = {}
    baselines = vdata.get("baselines") if isinstance(vdata.get("baselines"), dict) else {}
    existing_key = next((k for k in baselines if k.lower() == character.lower()), character)

    if r.body.get("clear"):
        old = baselines.pop(existing_key, None)
        if isinstance(old, dict) and old.get("file"):
            try:
                (pd / str(old["file"])).unlink(missing_ok=True)
            except OSError:
                pass
        vdata["baselines"] = baselines
        vc_path.write_text(json.dumps(vdata, indent=2), encoding="utf-8")
        return {"status": "ok", "character": existing_key, "cleared": True}

    safe_char = "".join(c if c.isalnum() else "_" for c in character.lower()).strip("_") or "speaker"
    ref_dir = pd / "audio" / "voice_refs"
    ref_dir.mkdir(parents=True, exist_ok=True)
    rel_file = f"audio/voice_refs/{safe_char}.wav"
    dest_wav = pd / rel_file

    from_line = str(r.body.get("from_line_id") or "").strip()
    b64 = str(r.body.get("audio_base64") or "").strip()
    source_label = ""
    sample_text = str(r.body.get("text") or "").strip()

    if from_line:
        safe_id = "".join(c for c in from_line if c.isalnum() or c in "-_")
        src_wav = pd / "audio" / "dialogue" / f"{safe_id}.wav"
        if not src_wav.is_file():
            raise PlanError(f"Line {safe_id} has not been rendered yet — render or play it first.")
        shutil.copyfile(src_wav, dest_wav)
        source_label = safe_id
    elif b64:
        filename = str(r.body.get("filename") or "baseline.wav").strip()
        if "," in b64 and b64.startswith("data:"):
            b64 = b64.split(",", 1)[1]
        raw = base64.b64decode(b64)
        if len(raw) < 64:
            raise PlanError("uploaded baseline audio file is empty")
        if raw[:4] == b"RIFF":
            dest_wav.write_bytes(raw)
        else:
            suffix = Path(filename).suffix or ".mp3"
            afconvert_bin = shutil.which("afconvert")
            ffmpeg_bin = shutil.which("ffmpeg")
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
                tf.write(raw)
                tmp_in = Path(tf.name)
            try:
                if afconvert_bin:
                    subprocess.run([afconvert_bin, "-f", "WAVE", "-d", "LEI16@24000", str(tmp_in), str(dest_wav)], check=True, timeout=30)
                elif ffmpeg_bin:
                    subprocess.run([ffmpeg_bin, "-y", "-i", str(tmp_in), str(dest_wav)], check=True, timeout=30)
                else:
                    dest_wav.write_bytes(raw)
            finally:
                tmp_in.unlink(missing_ok=True)
        source_label = filename
    else:
        raise PlanError("Provide either from_line_id or audio_base64 to set a character voice baseline.")

    baselines[existing_key] = {
        "file": rel_file,
        "source": source_label,
        "text": sample_text,
    }
    vdata["baselines"] = baselines
    vc_path.write_text(json.dumps(vdata, indent=2), encoding="utf-8")
    return {
        "status": "ok",
        "character": existing_key,
        "baseline": {
            "file": rel_file,
            "source": source_label,
            "text": sample_text,
            "audio_url": f"/file/{slug}/{rel_file}",
        },
    }


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


def _gemini_voice_for_kokoro(voice_id: str) -> str:
    """Map Kokoro voice IDs to distinct Gemini prebuilt neural voices."""
    v = (voice_id or "").lower()
    mapping = {
        "am_puck": "Puck",
        "am_michael": "Charon",
        "am_adam": "Fenrir",
        "am_eric": "Orus",
        "am_onyx": "Charon",
        "bm_fable": "Puck",
        "bm_george": "Charon",
        "bm_lewis": "Orus",
        "bm_daniel": "Fenrir",
        "af_bella": "Aoede",
        "af_sarah": "Kore",
        "af_nicole": "Leda",
        "af_heart": "Zephyr",
        "bf_emma": "Aoede",
        "bf_alice": "Kore",
        "bf_isabella": "Leda",
        "bf_lily": "Zephyr",
    }
    if v in mapping:
        return mapping[v]
    return "Aoede" if (v.startswith("af_") or v.startswith("bf_")) else "Puck"


def _write_wav_bytes(wav_path: Path, raw: bytes, sample_rate: int = 24000):
    """Write WAV bytes directly if already RIFF/WAVE, otherwise wrap raw 16-bit mono PCM in a WAV header."""
    import wave

    if raw[:4] == b"RIFF":
        wav_path.write_bytes(raw)
        return
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw)


def _render_line_gemini_tts(text: str, voice_id: str, dialect: str, emotion: str, note: str, wav_path: Path, persona: str = "", gemini_voice: str = "", character: str = "", ref_wav_path: Path | None = None) -> str:
    """Render one spoken line with Gemini Neural TTS using a locked voice baseline WAV (if set), deterministic per-character seed & low temperature."""
    import base64
    import hashlib
    import urllib.error
    import urllib.request
    import run_gemini_omni

    api_key = run_gemini_omni.get_gemini_api_key()
    if not api_key:
        raise PlanError("Gemini API key is not configured. Save your key in Step 13 (or ~/.zshrc) first.")

    g_voice = (gemini_voice or "").strip() or _gemini_voice_for_kokoro(voice_id)
    accent = "British English (RP)" if (voice_id.lower().startswith("b") or dialect == "british") else "American English"

    # Deterministic per-character seed so the same character keeps a consistent vocal timbre across every line & scene
    seed_key = f"{(character or 'speaker').strip().lower()}:{g_voice}:{persona.strip().lower()}:{accent}"
    char_seed = (int(hashlib.sha256(seed_key.encode("utf-8")).hexdigest()[:8], 16) % 2147483646) + 1

    # Structured Director's Notes prompt (keeps vocal identity anchored while honoring per-scene tone/direction)
    profile_desc = persona.strip() if persona.strip() else f"consistent {accent} voice actor"
    tone_desc = emotion if (emotion and emotion != "natural") else "natural, steady"
    has_ref = bool(ref_wav_path and ref_wav_path.is_file() and ref_wav_path.stat().st_size > 100)
    ref_bytes = ref_wav_path.read_bytes() if has_ref and ref_wav_path else b""

    dir_lines = [
        "# AUDIO PROFILE",
        f"Character: {(character or 'Speaker').strip()}",
        f"Voice Identity: {profile_desc}",
        f"Accent: {accent}",
        "",
        "# DIRECTOR'S NOTES",
        f"Maintain the exact same vocal pitch, age, and timbre for {(character or 'Speaker').strip()} across all lines.",
        f"Scene Tone: {tone_desc}",
    ]
    if has_ref:
        dir_lines.insert(6, "Match the exact voice pitch, age, timbre, and cadence of the attached baseline audio reference clip.")
    if note:
        dir_lines.append(f"Delivery Note: {note}")
    dir_lines.extend(["", "# TRANSCRIPT (speak ONLY the line below, nothing else)", text])
    prompt = "\n".join(dir_lines)

    models = ("gemini-2.5-flash-preview-tts", "gemini-3.1-flash-tts-preview", "gemini-3.8-flash-tts")
    last_err = None

    # Path 1: Official google-genai SDK (when installed in this Python environment)
    if run_gemini_omni.sdk_available():
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        # Try with inline baseline audio reference first if available, then fall back to text-only seeded call
        content_variants = []
        if has_ref and ref_bytes:
            content_variants.append([types.Part.from_bytes(data=ref_bytes, mime_type="audio/wav"), prompt])
        content_variants.append(prompt)

        for contents_arg in content_variants:
            used_ref = isinstance(contents_arg, list)
            for model_name in models:
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=contents_arg,
                        config=types.GenerateContentConfig(
                            temperature=0.2,
                            seed=char_seed,
                            response_modalities=["AUDIO"],
                            speech_config=types.SpeechConfig(
                                voice_config=types.VoiceConfig(
                                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=g_voice)
                                )
                            ),
                        ),
                    )
                    for part in getattr(resp, "parts", None) or []:
                        inline = getattr(part, "inline_data", None)
                        if inline and getattr(inline, "data", None):
                            raw = inline.data
                            if isinstance(raw, str):
                                raw = base64.b64decode(raw)
                            _write_wav_bytes(wav_path, raw, sample_rate=24000)
                            ref_tag = "+baseline" if used_ref else ""
                            return f"{g_voice} ({model_name}{ref_tag}, seed={char_seed})"
                except Exception as e:
                    last_err = e
                    continue

    # Path 2: Zero-dependency HTTPS REST fallback (works inside .venv without google-genai installed)
    rest_variants = []
    if has_ref and ref_bytes:
        rest_variants.append((True, [
            {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(ref_bytes).decode("ascii")}},
            {"text": prompt},
        ]))
    rest_variants.append((False, [{"text": prompt}]))

    for used_ref, parts in rest_variants:
        payload = json.dumps({
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "seed": char_seed,
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": g_voice}
                    }
                },
            },
        }).encode("utf-8")

        for model_name in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                for cand in data.get("candidates") or []:
                    for part in (cand.get("content") or {}).get("parts") or []:
                        inline = part.get("inlineData") or part.get("inline_data") or {}
                        b64 = inline.get("data")
                        if b64:
                            _write_wav_bytes(wav_path, base64.b64decode(b64), sample_rate=24000)
                            ref_tag = "+baseline" if used_ref else ""
                            return f"{g_voice} ({model_name}{ref_tag}, seed={char_seed})"
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode("utf-8", errors="ignore")[:300]
                except Exception:
                    body = str(e)
                last_err = RuntimeError(f"HTTP {e.code}: {body}")
                continue
            except Exception as e:
                last_err = e
                continue

    raise PlanError(f"Gemini Neural TTS failed: {run_gemini_omni.sanitize_error(last_err) if last_err else 'no audio returned'}")


def find_kokoro_python() -> str:
    """Return path to a Python executable that has `kokoro` installed (current venv first, then PATH / ~/.zshrc)."""
    import importlib.util
    import os
    import re
    import sys

    if importlib.util.find_spec("kokoro"):
        return sys.executable

    candidates: list[str] = []
    # 1. Check `kokoro` binary on current PATH or paths exported in ~/.zshrc / ~/.zprofile
    search_dirs = [d for d in os.environ.get("PATH", "").split(os.pathsep) if d]
    for prof in (".zshrc", ".zprofile", ".bash_profile", ".bashrc"):
        p = Path.home() / prof
        try:
            if not p.is_file():
                continue
            txt = p.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r"(/[^\s:'\"$]+/(?:bin|py3bin))", txt):
                d = m.group(1)
                if d not in search_dirs:
                    search_dirs.append(d)
        except OSError:
            continue

    def _safe_exec(path: Path) -> bool:
        try:
            return path.is_file() and os.access(path, os.X_OK)
        except OSError:
            return False

    for d in search_dirs:
        kb = Path(d) / "kokoro"
        if _safe_exec(kb):
            try:
                first = kb.read_text(encoding="utf-8", errors="ignore").splitlines()[0]
                if first.startswith("#!"):
                    interp = first[2:].strip().split()[0]
                    if _safe_exec(Path(interp)) and interp not in candidates:
                        candidates.append(interp)
            except Exception:
                pass
        for pyname in ("python3", "python"):
            pyb = Path(d) / pyname
            if _safe_exec(pyb) and str(pyb) not in candidates:
                candidates.append(str(pyb))

    for extra in ("/Applications/oss-cad-suite/py3bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3"):
        if _safe_exec(Path(extra)) and extra not in candidates:
            candidates.append(extra)

    for py in candidates:
        if py == sys.executable:
            continue
        try:
            r = subprocess.run(
                [py, "-c", "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('kokoro') else 1)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=4,
            )
            if r.returncode == 0:
                return py
        except Exception:
            continue
    return ""


def _render_line_kokoro(text: str, voice_id: str, dialect: str, speed: float, wav_path: Path, blend_voice: str = "") -> str:
    """Render one spoken line locally using Kokoro-82M (in-process if in .venv, else via detected Kokoro Python)."""
    import sys

    py = find_kokoro_python()
    if not py:
        raise PlanError("Kokoro-82M is not installed yet. Click '⬇ Install Kokoro-82M' on the Kokoro card above to install it.")

    base_vid = (voice_id or "").strip() or ("bm_fable" if dialect == "british" else "am_puck")
    blend = (blend_voice or "").strip()
    vid = f"{base_vid},{blend}" if (blend and blend != base_vid) else base_vid
    lang = "b" if base_vid.lower().startswith("b") else "a"

    if py == sys.executable:
        import numpy as np
        from kokoro import KPipeline

        pipe = KPipeline(lang_code=lang)
        chunks = []
        for _, _, audio in pipe(text, voice=vid, speed=speed):
            if audio is not None:
                chunks.append(np.asarray(audio, dtype=np.float32))
        if not chunks:
            raise PlanError("Kokoro-82M returned empty audio for this line.")
        pcm = np.clip(np.concatenate(chunks), -1.0, 1.0)
        pcm16 = (pcm * 32767.0).astype(np.int16).tobytes()
        _write_wav_bytes(wav_path, pcm16, sample_rate=24000)
        return vid

    # Subprocess render using the detected external Python where Kokoro is installed
    script = (
        "import sys, wave, numpy as np\n"
        "from kokoro import KPipeline\n"
        "lang, vid, spd, text, out_path = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4], sys.argv[5]\n"
        "pipe = KPipeline(lang_code=lang)\n"
        "chunks = [np.asarray(a, dtype=np.float32) for _, _, a in pipe(text, voice=vid, speed=spd) if a is not None]\n"
        "if not chunks:\n"
        "    raise SystemExit('empty audio')\n"
        "pcm = (np.clip(np.concatenate(chunks), -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()\n"
        "with wave.open(out_path, 'wb') as wf:\n"
        "    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(24000); wf.writeframes(pcm)\n"
    )
    proc = subprocess.run(
        [py, "-c", script, lang, vid, str(speed), text, str(wav_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0 or not wav_path.is_file():
        err = (proc.stderr or proc.stdout or "Kokoro synthesis failed").strip()[-300:]
        raise PlanError(f"Kokoro-82M render failed: {err}")
    return vid


@route("POST", "/api/v2_install_engine")
def _v2_install_engine(r: Request):
    """User-approved in-app installer for optional local engines/packages into Studio's Python environment."""
    import sys

    engine = str(r.body.get("engine") or "").strip().lower()
    if not r.body.get("approved"):
        raise PlanError("User approval is required before installing packages.")
    pkg_map = {
        "kokoro": ["kokoro", "soundfile"],
        "gemini-sdk": ["google-genai"],
        "huggingface": ["gradio_client", "huggingface_hub"],
        "pillow": ["pillow"],
        "ffmpeg": ["imageio-ffmpeg"],
    }
    pkgs = pkg_map.get(engine)
    if not pkgs:
        raise PlanError(f"Unknown installable engine: {engine}")

    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-U", *pkgs],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "pip install failed").strip()[-400:]
        raise PlanError(f"Could not install {', '.join(pkgs)}: {err}")
    return {"status": "ok", "engine": engine, "packages": pkgs, "installed": True}


@route("POST", "/api/v2_dialogue_render")
def _v2_dialogue_render(r: Request):
    """Render one or more dialogue lines to WAV files using the selected engine: gemini-tts, kokoro, or macos-say."""
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
    engine = str(r.body.get("engine") or "macos-say").strip().lower()
    if engine not in ("gemini-tts", "kokoro", "macos-say"):
        engine = "macos-say"

    say_bin = shutil.which("say") if engine == "macos-say" else None
    afconvert_bin = shutil.which("afconvert") if engine == "macos-say" else None
    avail = set()
    if engine == "macos-say":
        if not say_bin:
            raise PlanError("Local scratch speech ('say') is unavailable on this machine; choose Gemini Neural TTS or Kokoro-82M.")
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
        voice_id = str(item.get("kokoro_voice") or item.get("voice") or "").strip()
        gemini_voice = str(item.get("gemini_voice") or "").strip()
        kokoro_blend = str(item.get("kokoro_blend") or "").strip()
        explicit_macos = str(item.get("macos_voice") or "").strip()
        persona = str(item.get("persona") or "").strip()
        emotion = str(item.get("emotion") or "natural").strip()
        note = str(item.get("note") or "").strip()
        speed = max(0.5, min(1.8, float(item.get("speed") or 1.0)))
        wav_path = out_dir / f"{safe_id}.wav"

        character = str(item.get("character") or "").strip()
        # Check if this character has a locked voice baseline WAV in voice_cast.json
        ref_wav = None
        if character:
            vc_file = pd / "voice_cast.json"
            if vc_file.is_file():
                try:
                    bmap = (json.loads(vc_file.read_text(encoding="utf-8")) or {}).get("baselines") or {}
                    bkey = next((k for k in bmap if k.lower() == character.lower()), "")
                    if bkey and isinstance(bmap[bkey], dict) and bmap[bkey].get("file"):
                        cand_ref = pd / str(bmap[bkey]["file"])
                        if cand_ref.is_file() and cand_ref.stat().st_size > 100:
                            ref_wav = cand_ref
                except Exception:
                    pass
        if engine == "gemini-tts":
            voice_used = _render_line_gemini_tts(text, voice_id, dialect, emotion, note, wav_path, persona=persona, gemini_voice=gemini_voice, character=character, ref_wav_path=ref_wav)
        elif engine == "kokoro":
            voice_used = _render_line_kokoro(text, voice_id, dialect, speed, wav_path, blend_voice=kokoro_blend)
        else:
            rate = int(round(185 * speed))
            mac_voice = explicit_macos or _macos_voice_for_kokoro(voice_id, dialect)
            if avail and mac_voice not in avail:
                if (voice_id.lower().startswith("b") or dialect == "british") and "Daniel" in avail:
                    mac_voice = "Daniel"
                elif "Samantha" in avail:
                    mac_voice = "Samantha"
                else:
                    mac_voice = ""
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
            finally:
                aiff_path.unlink(missing_ok=True)
            voice_used = mac_voice or "system-default"

        rendered.append({
            "id": safe_id,
            "audio_url": f"/file/{slug}/audio/dialogue/{safe_id}.wav",
            "voice_used": voice_used,
        })

    return {"status": "ok", "engine": engine, "rendered": rendered}


