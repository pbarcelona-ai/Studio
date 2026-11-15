"""POST routes of the JSON API (uploads are streamed by handler.py instead)."""
import json
import shutil
import subprocess
from pathlib import Path

import character_tokens
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
