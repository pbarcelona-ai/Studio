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


VOICE_LIBRARY_DIR = PROJECTS / "characters" / "_voice_library"


def _voice_library_load() -> dict:
    """Load the global cross-film character voice library from projects/characters/_voice_library/library.json."""
    lib_file = VOICE_LIBRARY_DIR / "library.json"
    if lib_file.is_file():
        try:
            data = json.loads(lib_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _voice_library_save_entry(character: str, entry: dict, src_wav: Path | None = None) -> dict:
    """Persist a character's voice profile and/or baseline WAV to the global cross-film voice library."""
    from datetime import datetime, timezone

    VOICE_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    lib = _voice_library_load()
    key = next((k for k in lib if k.lower() == character.lower()), character)
    cur = dict(lib.get(key) or {})
    cur.update({k: v for k, v in entry.items() if v is not None})
    cur["character"] = key
    cur["updated_at"] = datetime.now(timezone.utc).isoformat()

    safe_char = "".join(c if c.isalnum() else "_" for c in key.lower()).strip("_") or "speaker"
    if src_wav and src_wav.is_file() and src_wav.stat().st_size > 100:
        lib_wav = VOICE_LIBRARY_DIR / f"{safe_char}.wav"
        shutil.copyfile(src_wav, lib_wav)
        cur["wav_file"] = f"{safe_char}.wav"

    lib[key] = cur
    (VOICE_LIBRARY_DIR / "library.json").write_text(json.dumps(lib, indent=2), encoding="utf-8")
    return cur


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

    # Also save character voice profile to global cross-film library for future films
    _voice_library_save_entry(existing_key, {**prof, "source_project": slug})

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
        cleared_list = list(vdata.get("cleared_baselines") or [])
        if existing_key.lower() not in [c.lower() for c in cleared_list]:
            cleared_list.append(existing_key)
        vdata["cleared_baselines"] = cleared_list
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

    # Also persist this baseline WAV & metadata into the global cross-film voice library
    prof = (vdata.get("profiles") or {}).get(existing_key) or {}
    _voice_library_save_entry(
        existing_key,
        {
            **prof,
            "source": source_label,
            "source_project": slug,
            "text": sample_text,
        },
        src_wav=dest_wav,
    )

    baselines[existing_key] = {
        "file": rel_file,
        "source": source_label,
        "text": sample_text,
        "saved_to_library": True,
        "source_project": slug,
    }
    cleared_list = [c for c in (vdata.get("cleared_baselines") or []) if c.lower() != existing_key.lower()]
    vdata["cleared_baselines"] = cleared_list
    vdata["baselines"] = baselines
    vc_path.write_text(json.dumps(vdata, indent=2), encoding="utf-8")
    return {
        "status": "ok",
        "character": existing_key,
        "baseline": {
            "file": rel_file,
            "source": source_label,
            "text": sample_text,
            "saved_to_library": True,
            "source_project": slug,
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
        # Check if this character has a locked voice baseline WAV in voice_cast.json or the global cross-film library
        ref_wav = None
        if character:
            cleared_set = set()
            vc_file = pd / "voice_cast.json"
            if vc_file.is_file():
                try:
                    vdoc = json.loads(vc_file.read_text(encoding="utf-8")) or {}
                    bmap = vdoc.get("baselines") or {}
                    cleared_set = {str(c).lower() for c in (vdoc.get("cleared_baselines") or [])}
                    bkey = next((k for k in bmap if k.lower() == character.lower()), "")
                    if bkey and isinstance(bmap[bkey], dict) and bmap[bkey].get("file"):
                        cand_ref = pd / str(bmap[bkey]["file"])
                        if cand_ref.is_file() and cand_ref.stat().st_size > 100:
                            ref_wav = cand_ref
                except Exception:
                    pass
            if ref_wav is None and character.lower() not in cleared_set:
                glib = _voice_library_load()
                gkey = next((k for k in glib if k.lower() == character.lower()), "")
                if gkey and isinstance(glib[gkey], dict) and glib[gkey].get("wav_file"):
                    cand_lib = VOICE_LIBRARY_DIR / str(glib[gkey]["wav_file"])
                    if cand_lib.is_file() and cand_lib.stat().st_size > 100:
                        ref_wav = cand_lib
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


def _synth_foley_wav(wav_path: Path, prompt: str, preset: str, duration: int = 10):
    """Synthesize a distinct stereo foley soundscape driven directly by the chosen preset."""
    import math
    import random
    import struct
    import wave

    sr = 22050
    dur = max(4, min(30, int(duration or 10)))
    n = sr * dur
    mode = (preset or "space_adventure").strip().lower()
    rng = random.Random(hash(mode + ":" + prompt) & 0xFFFFFFFF)

    lp1_l = lp1_r = lp2_l = lp2_r = 0.0
    frames = bytearray()

    # Pre-generate random droplet / crackle / crystal event timestamps so each preset has rich, distinct texture
    events = sorted(rng.uniform(0.2, dur - 0.3) for _ in range(int(dur * 6)))
    ev_idx = 0
    active_pings: list[tuple[float, float, float, float]] = []  # (start_t, freq, decay, pan)

    for i in range(n):
        t = i / sr
        env = min(1.0, t / 0.6) * min(1.0, (dur - t) / 0.6)
        sig_l = sig_r = 0.0

        while ev_idx < len(events) and events[ev_idx] <= t:
            et = events[ev_idx]
            ev_idx += 1
            if mode == "rainy_home":
                # Water droplets on glass + occasional soft hearth pop
                active_pings.append((et, rng.uniform(900.0, 2200.0), rng.uniform(28.0, 55.0), rng.uniform(0.15, 0.85)))
            elif mode == "cosmic_storm":
                # Sparkling ice-ring crystal chimes
                f = rng.choice([1046.5, 1318.5, 1567.98, 2093.0, 2637.02])
                active_pings.append((et, f, rng.uniform(3.5, 7.0), rng.uniform(0.1, 0.9)))
            elif mode == "forest_nature":
                # Cricket chirps
                active_pings.append((et, rng.uniform(3800.0, 4400.0), 18.0, rng.uniform(0.1, 0.9)))

        if mode == "rainy_home":
            # Steady warm rain patter (filtered stereo noise) + soft distant thunder swell + glass droplets
            nl, nr = rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0)
            lp1_l = lp1_l * 0.72 + nl * 0.28
            lp1_r = lp1_r * 0.72 + nr * 0.28
            thunder = 0.14 * max(0.0, math.sin(2 * math.pi * 0.11 * t - 1.0)) * (math.sin(2 * math.pi * 44.0 * t) + 0.6 * math.sin(2 * math.pi * 58.0 * t))
            sig_l += lp1_l * 0.42 + thunder
            sig_r += lp1_r * 0.42 + thunder * 0.92
        elif mode == "cosmic_storm":
            # Sweeping stereo howling wind (LFO-modulated resonant noise) + deep planetary sub-drone + ice chimes
            nl, nr = rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0)
            sweep = 0.06 + 0.14 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.18 * t))
            lp1_l = lp1_l * (1.0 - sweep) + nl * sweep
            lp1_r = lp1_r * (1.0 - sweep) + nr * sweep
            wind_whistle = 0.12 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.22 * t)) * math.sin(2 * math.pi * (310.0 + 95.0 * math.sin(2 * math.pi * 0.14 * t)) * t)
            sub = 0.14 * math.sin(2 * math.pi * 52.0 * t)
            sig_l += lp1_l * 0.55 + wind_whistle * 0.7 + sub
            sig_r += lp1_r * 0.55 + wind_whistle * 1.1 + sub
        elif mode == "action_launch":
            # Building rocket roar (heavy low-passed rumble + rising turbine whine + ignition crackle)
            ramp = min(1.0, 0.25 + 0.75 * (t / dur))
            nl, nr = rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0)
            lp1_l = lp1_l * 0.91 + nl * 0.09
            lp1_r = lp1_r * 0.91 + nr * 0.09
            lp2_l = lp2_l * 0.85 + lp1_l * 0.15
            lp2_r = lp2_r * 0.85 + lp1_r * 0.15
            roar = 0.75 * ramp
            turbine = 0.10 * ramp * math.sin(2 * math.pi * (120.0 + 380.0 * (t / dur)) * t)
            sub = 0.28 * ramp * math.sin(2 * math.pi * (36.0 + 18.0 * ramp) * t)
            sig_l += lp2_l * roar + sub + turbine * 0.9
            sig_r += lp2_r * roar + sub + turbine * 1.1
        elif mode == "forest_nature":
            # Gentle evening breeze + rhythmic cricket chorus
            nl, nr = rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0)
            lp1_l = lp1_l * 0.95 + nl * 0.05
            lp1_r = lp1_r * 0.95 + nr * 0.05
            breeze = 0.25 + 0.15 * math.sin(2 * math.pi * 0.15 * t)
            chirp_gate = 1.0 if (t % 0.9) < 0.28 else 0.0
            chirp_pulse = 0.5 + 0.5 * math.sin(2 * math.pi * 24.0 * t)
            crickets = 0.11 * chirp_gate * chirp_pulse * math.sin(2 * math.pi * 4150.0 * t)
            sig_l += lp1_l * breeze + crickets * 0.6
            sig_r += lp1_r * breeze + crickets * 1.1
        else:
            # space_adventure: Clean starship bridge hum + dual-tone sonar/telemetry chimes (NO rain)
            lfo = 0.82 + 0.18 * math.sin(2 * math.pi * 0.35 * t)
            hum = (0.20 * math.sin(2 * math.pi * 65.41 * t) + 0.11 * math.sin(2 * math.pi * 98.0 * t) + 0.05 * math.sin(2 * math.pi * 130.81 * t)) * lfo
            sig_l += hum
            sig_r += hum * 0.94
            cyc = t % 1.8
            if 0.25 < cyc < 0.40:
                be = math.sin(math.pi * (cyc - 0.25) / 0.15)
                f = [784.0, 987.77, 1174.66][int(t / 1.8) % 3]
                bp = 0.18 * be * math.sin(2 * math.pi * f * t)
                sig_l += bp * 0.65
                sig_r += bp
            elif 0.44 < cyc < 0.54:
                be = math.sin(math.pi * (cyc - 0.44) / 0.10)
                bp = 0.13 * be * math.sin(2 * math.pi * 1567.98 * t)
                sig_l += bp
                sig_r += bp * 0.65

        # Mix active transient pings (droplets / crystal chimes)
        if active_pings:
            keep = []
            for st, f, dec, pan in active_pings:
                dt = t - st
                if dt < 0.7:
                    amp = 0.11 * math.exp(-dt * dec)
                    v = amp * math.sin(2 * math.pi * f * dt)
                    sig_l += v * (1.0 - pan)
                    sig_r += v * pan
                    keep.append((st, f, dec, pan))
            active_pings = keep

        sig_l = max(-0.95, min(0.95, sig_l * env))
        sig_r = max(-0.95, min(0.95, sig_r * env))
        frames.extend(struct.pack("<hh", int(sig_l * 32767), int(sig_r * 32767)))

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(frames))


def _synth_score_wav(wav_path: Path, mood: str, duration: int = 12):
    """Synthesize a distinctly orchestrated stereo score preview per mood (tempo, rhythm, instruments, and harmony)."""
    import math
    import struct
    import wave

    sr = 22050
    dur = max(6, min(30, int(duration or 12)))
    n = sr * dur
    m = (mood or "wonder").strip().lower()
    frames = bytearray()

    for i in range(n):
        t = i / sr
        env = min(1.0, t / 0.7) * min(1.0, (dur - t) / 0.9)
        sig_l = sig_r = 0.0

        if m == "epic":
            # Driving 120 BPM orchestral ostinato + bold brass fifths + deep timpani hits
            chords = [(110.0, 164.81, 220.0, 329.63), (87.31, 130.81, 174.61, 261.63), (130.81, 196.0, 261.63, 392.0), (98.0, 146.83, 196.0, 293.66)]
            ci = int(t / 2.0) % len(chords)
            ch = chords[ci]
            # 8th-note pulsing bass ostinato (4 pulses/sec)
            pulse_t = (t * 4.0) % 1.0
            ost_env = math.exp(-pulse_t * 5.5)
            ost = 0.28 * ost_env * (math.sin(2 * math.pi * ch[0] * t) + 0.45 * math.sin(2 * math.pi * ch[0] * 2.0 * t))
            # Brass swell (rich odd+even harmonics)
            br_swell = 0.5 + 0.5 * math.sin(2 * math.pi * 0.25 * t)
            brass = 0.14 * br_swell * (math.sin(2 * math.pi * ch[2] * t) + 0.5 * math.sin(2 * math.pi * ch[2] * 2.0 * t) + 0.25 * math.sin(2 * math.pi * ch[3] * t))
            # Timpani boom on beat 1 of every bar (every 2s)
            bar_t = t % 2.0
            timp = 0.34 * math.exp(-bar_t * 6.5) * math.sin(2 * math.pi * (62.0 - 14.0 * min(1.0, bar_t * 3.0)) * bar_t)
            sig_l = ost + brass * 0.9 + timp
            sig_r = ost * 0.95 + brass * 1.1 + timp

        elif m == "playful":
            # Upbeat 145 BPM bouncy pizzicato bass + staccato xylophone/glockenspiel melody
            mel = [523.25, 659.25, 783.99, 659.25, 880.0, 783.99, 659.25, 587.33, 523.25, 587.33, 659.25, 783.99, 1046.5, 783.99, 659.25, 523.25]
            bass = [130.81, 196.0, 146.83, 196.0, 164.81, 196.0, 146.83, 130.81]
            step = int(t * 4.8)
            st = (t * 4.8) - step
            mf = mel[step % len(mel)]
            bf = bass[(step // 2) % len(bass)]
            # Bright wooden xylophone plink
            xylo = 0.22 * math.exp(-st * 14.0) * (math.sin(2 * math.pi * mf * t) + 0.35 * math.sin(2 * math.pi * mf * 3.0 * t))
            # Bouncy pizzicato string pluck
            bt = (t * 2.4) % 1.0
            pizz = 0.26 * math.exp(-bt * 9.0) * (math.sin(2 * math.pi * bf * t) + 0.4 * math.sin(2 * math.pi * bf * 2.0 * t))
            pan = 0.35 + 0.3 * (step % 2)
            sig_l = pizz + xylo * (1.0 - pan)
            sig_r = pizz + xylo * pan

        elif m == "cozy":
            # Gentle 3/4 waltz music-box / warm electric piano
            waltz_chords = [(174.61, 261.63, 349.23, 440.0), (130.81, 196.0, 261.63, 329.63), (146.83, 220.0, 293.66, 349.23), (116.54, 174.61, 233.08, 293.66)]
            bar = int(t / 1.8) % len(waltz_chords)
            beat = int((t % 1.8) / 0.6)  # 0, 1, 2 (3/4 waltz)
            bt = (t % 0.6)
            ch = waltz_chords[bar]
            if beat == 0:
                # Warm bass note on beat 1
                v = 0.26 * math.exp(-bt * 3.2) * (math.sin(2 * math.pi * ch[0] * t) + 0.25 * math.sin(2 * math.pi * ch[0] * 2.0 * t))
                sig_l += v
                sig_r += v
            else:
                # Soft Rhodes chord on beats 2 & 3
                ce = math.exp(-bt * 4.5)
                v = 0.14 * ce * (math.sin(2 * math.pi * ch[1] * t) + math.sin(2 * math.pi * ch[2] * t) + 0.8 * math.sin(2 * math.pi * ch[3] * t))
                sig_l += v * 0.9
                sig_r += v * 1.05
            # Delicate music-box twinkle
            mb_step = int(t / 0.6)
            mb_f = ch[1 + (mb_step % 3)] * 2.0
            mb = 0.10 * math.exp(-bt * 6.0) * math.sin(2 * math.pi * mb_f * t)
            sig_l += mb * 1.1
            sig_r += mb * 0.8

        elif m == "mysterious":
            # Dark minor cosmic drone + eerie glass-harmonica vibrato + sparse echoing bell
            vib = 1.0 + 0.008 * math.sin(2 * math.pi * 4.5 * t)
            drone = 0.22 * math.sin(2 * math.pi * 55.0 * t) + 0.14 * math.sin(2 * math.pi * 82.41 * t)
            eerie = 0.12 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.19 * t)) * math.sin(2 * math.pi * 311.13 * vib * t)
            # Sparse echoing metallic bell every 2.8s
            bell_t = t % 2.8
            bell_f = [440.0, 466.16, 392.0, 329.63][int(t / 2.8) % 4]
            bell = 0.18 * math.exp(-bell_t * 1.8) * (math.sin(2 * math.pi * bell_f * t) + 0.3 * math.sin(2 * math.pi * bell_f * 2.756 * t))
            sig_l = drone + eerie * 1.1 + bell * 0.7
            sig_r = drone * 0.95 + eerie * 0.7 + bell * 1.1

        else:
            # wonder: Lush sweeping orchestral strings + celesta sparkles in C Major
            chords = [(130.81, 261.63, 329.63, 392.00, 493.88), (110.00, 220.00, 261.63, 329.63, 392.00), (87.31, 174.61, 220.00, 261.63, 329.63), (98.00, 196.00, 246.94, 293.66, 392.00)]
            clen = dur / len(chords)
            ci = min(len(chords) - 1, int(t / clen))
            ct = t - ci * clen
            c_env = min(1.0, ct / 0.45) * min(1.0, (clen - ct) / 0.45)
            ch = chords[ci]
            for idx, f in enumerate(ch):
                w = 0.14 if idx == 0 else 0.085
                sig_l += w * c_env * math.sin(2 * math.pi * f * t)
                sig_r += w * c_env * math.sin(2 * math.pi * (f * 1.003) * t)
            arp_step = int(t * 2.5)
            arp_t = (t * 2.5) - arp_step
            arp_f = ch[1 + (arp_step % (len(ch) - 1))] * 2.0
            arp = 0.09 * math.exp(-arp_t * 5.0) * math.sin(2 * math.pi * arp_f * t)
            sig_l += arp * 0.85
            sig_r += arp * 1.15

        sig_l = max(-0.95, min(0.95, sig_l * env))
        sig_r = max(-0.95, min(0.95, sig_r * env))
        frames.extend(struct.pack("<hh", int(sig_l * 32767), int(sig_r * 32767)))

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(frames))


@route("POST", "/api/v2_sound_design_save")
def _v2_sound_design_save(r: Request):
    """Save Step 16 SFX mode, master Foley/Score settings, and per-scene SFX/Score cues to sound_design_v2.json."""
    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    sd_path = pd / "sound_design_v2.json"
    cur = {}
    if sd_path.is_file():
        try:
            cur = json.loads(sd_path.read_text(encoding="utf-8")) or {}
        except Exception:
            cur = {}
    if r.body.get("sfx_mode"):
        cur["sfx_mode"] = str(r.body["sfx_mode"]).strip()
    if isinstance(r.body.get("foley"), dict):
        cur["foley"] = {**(cur.get("foley") or {}), **r.body["foley"]}
    if isinstance(r.body.get("score"), dict):
        cur["score"] = {**(cur.get("score") or {}), **r.body["score"]}
    if isinstance(r.body.get("scenes"), dict):
        sc_map = dict(cur.get("scenes") or {})
        for sid, sinfo in r.body["scenes"].items():
            if isinstance(sinfo, dict):
                sc_map[str(sid)] = {**(sc_map.get(str(sid)) or {}), **sinfo}
        cur["scenes"] = sc_map
    sd_path.write_text(json.dumps(cur, indent=2), encoding="utf-8")
    return {"status": "ok", "saved": cur}


@route("POST", "/api/v2_sound_design_render")
def _v2_sound_design_render(r: Request):
    """Render or upload Step 16 master Foley/Score OR a specific scene's Foley WAV."""
    import base64
    import tempfile

    slug = str(r.body.get("project") or "").strip()
    kind = str(r.body.get("kind") or "foley").strip().lower()
    scene_id = "".join(c for c in str(r.body.get("scene") or "").strip() if c.isalnum() or c in "-_")
    if not slug:
        raise PlanError("project is required")
    if kind not in ("foley", "score"):
        raise PlanError("kind must be 'foley' or 'score'")

    pd = pdir(slug, "book")
    sub = "foley" if kind == "foley" else "score"
    out_dir = pd / "audio" / sub
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"scene_{scene_id}.wav" if scene_id else f"{sub}_master.wav"
    wav_path = out_dir / fname
    rel_url = f"/file/{slug}/audio/{sub}/{fname}"

    b64 = str(r.body.get("audio_base64") or "").strip()
    if b64:
        filename = str(r.body.get("filename") or f"{sub}.wav").strip()
        if "," in b64 and b64.startswith("data:"):
            b64 = b64.split(",", 1)[1]
        raw = base64.b64decode(b64)
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
                    subprocess.run([afconvert_bin, "-f", "WAVE", "-d", "LEI16@22050", str(tmp_in), str(wav_path)], check=True, timeout=30)
                elif ffmpeg_bin:
                    subprocess.run([ffmpeg_bin, "-y", "-i", str(tmp_in), str(wav_path)], check=True, timeout=30)
                else:
                    wav_path.write_bytes(raw)
            finally:
                tmp_in.unlink(missing_ok=True)
        return {"status": "ok", "kind": kind, "audio_url": rel_url, "source": filename}

    prompt = str(r.body.get("prompt") or "").strip()
    duration = int(r.body.get("duration") or (10 if kind == "foley" else 12))
    if kind == "foley":
        preset = str(r.body.get("preset") or "space_adventure").strip()
        _synth_foley_wav(wav_path, prompt, preset, duration)
    else:
        mood = str(r.body.get("mood") or "wonder").strip()
        _synth_score_wav(wav_path, mood, duration)

    # Save settings alongside render
    sd_path = pd / "sound_design_v2.json"
    cur = {}
    if sd_path.is_file():
        try:
            cur = json.loads(sd_path.read_text(encoding="utf-8")) or {}
        except Exception:
            cur = {}
    if scene_id:
        sc_map = dict(cur.get("scenes") or {})
        sc_map[scene_id] = {
            **(sc_map.get(scene_id) or {}),
            "sfx_cue": prompt,
            "sfx_preset": str(r.body.get("preset") or ""),
        }
        cur["scenes"] = sc_map
    else:
        cur[kind] = {
            **(cur.get(kind) or {}),
            "prompt": prompt,
            "duration": duration,
            ("preset" if kind == "foley" else "mood"): str(r.body.get("preset") or r.body.get("mood") or ""),
        }
    sd_path.write_text(json.dumps(cur, indent=2), encoding="utf-8")
    return {"status": "ok", "kind": kind, "scene": scene_id, "audio_url": rel_url, "duration": duration}


def _render_keyframe_gemini(prompt: str, out_png: Path, aspect_ratio: str = "16:9") -> str:
    """Generate a storyboard keyframe PNG using Gemini Image Generation (SDK first, else HTTPS REST fallback)."""
    import base64
    import urllib.error
    import urllib.request
    import run_gemini_omni

    api_key = run_gemini_omni.get_gemini_api_key()
    if not api_key:
        raise PlanError("Gemini API key is not configured. Save your GEMINI_API_KEY in Step 13 first.")

    full_prompt = (
        "Generate a single clean cinematic widescreen 16:9 film storyboard keyframe with NO text, NO captions, NO watermarks.\n"
        "STRICT CONTINUITY RULES:\n"
        "- WARDROBE LOCK: Keep every character's exact specified singular clothing (exact solid colors, exact top, bottoms, and footwear). Do NOT add stripes, patterns, or color changes that were not specified.\n"
        "- LOCATION LOCK: Keep the exact specified room/location, background props, and lighting consistent across every shot of this scene.\n\n"
        f"{prompt}"
    )
    models = ("gemini-2.5-flash-image", "gemini-3.1-flash-image-preview", "gemini-3.1-flash-lite-image", "gemini-2.0-flash-exp-image-generation")
    last_err = None

    if run_gemini_omni.sdk_available():
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        for m in models:
            try:
                resp = client.models.generate_content(
                    model=m,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
                    ),
                )
                for part in getattr(resp, "parts", None) or []:
                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        raw = inline.data
                        if isinstance(raw, str):
                            raw = base64.b64decode(raw)
                        out_png.write_bytes(raw)
                        return m
            except Exception as e:
                last_err = e
                continue

    payload = json.dumps({
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"],
        },
    }).encode("utf-8")

    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for cand in data.get("candidates") or []:
                for part in (cand.get("content") or {}).get("parts") or []:
                    inline = part.get("inlineData") or part.get("inline_data") or {}
                    b64 = inline.get("data")
                    if b64:
                        out_png.write_bytes(base64.b64decode(b64))
                        return m
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

    raise PlanError(f"Keyframe image generation failed: {run_gemini_omni.sanitize_error(last_err) if last_err else 'no image returned'}")


@route("POST", "/api/v2_keyframe_render")
def _v2_keyframe_render(r: Request):
    """Generate or upload a storyboard keyframe PNG in <project>/keyframes/<shot_id>.png."""
    import base64

    slug = str(r.body.get("project") or "").strip()
    shot_id = "".join(c for c in str(r.body.get("id") or "").strip() if c.isalnum() or c in "-_")
    if not slug or not shot_id:
        raise PlanError("project and id are required")

    pd = pdir(slug, "book")
    kf_dir = pd / "keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)
    out_png = kf_dir / f"{shot_id}.png"
    rel_url = f"/file/{slug}/keyframes/{shot_id}.png"

    # Persist edited prompt if provided
    prompt = str(r.body.get("prompt") or "").strip()
    if prompt:
        meta_path = pd / "keyframes_v2.json"
        meta = {}
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
            except Exception:
                meta = {}
        prompts = dict(meta.get("prompts") or {})
        prompts[shot_id] = prompt
        meta["prompts"] = prompts
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    b64 = str(r.body.get("image_base64") or "").strip()
    if b64:
        if "," in b64 and b64.startswith("data:"):
            b64 = b64.split(",", 1)[1]
        raw = base64.b64decode(b64)
        if len(raw) < 100:
            raise PlanError("uploaded image is empty")
        out_png.write_bytes(raw)
        return {"status": "ok", "id": shot_id, "image_url": rel_url, "model": "uploaded"}

    if not prompt:
        raise PlanError("prompt is required to generate a keyframe")
    model_used = _render_keyframe_gemini(prompt, out_png, aspect_ratio=str(r.body.get("aspect_ratio") or "16:9"))
    return {"status": "ok", "id": shot_id, "image_url": rel_url, "model": model_used}


@route("POST", "/api/v2_keyframe_prompts_save")
def _v2_keyframe_prompts_save(r: Request):
    """Save edited Step 17 keyframe prompts to keyframes_v2.json without regenerating images."""
    slug = str(r.body.get("project") or "").strip()
    incoming = r.body.get("prompts")
    if not slug or not isinstance(incoming, dict):
        raise PlanError("project and prompts dict are required")
    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    meta_path = pd / "keyframes_v2.json"
    meta = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            meta = {}
    prompts = dict(meta.get("prompts") or {})
    count = 0
    for sid, txt in incoming.items():
        clean_id = "".join(c for c in str(sid).strip() if c.isalnum() or c in "-_")
        if clean_id:
            prompts[clean_id] = str(txt or "").strip()
            count += 1
    meta["prompts"] = prompts
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"status": "ok", "saved": count}


@route("POST", "/api/v2_wardrobe_states_save")
def _v2_wardrobe_states_save(r: Request):
    """Save scene/location-specific wardrobe states for a character into wardrobe_states.json."""
    slug = str(r.body.get("project") or "").strip()
    character = str(r.body.get("character") or "").strip()
    states = r.body.get("states")
    if not slug or not character or not isinstance(states, list):
        raise PlanError("project, character, and states list are required")
    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    ws_path = pd / "wardrobe_states.json"
    cur = {}
    if ws_path.is_file():
        try:
            cur = json.loads(ws_path.read_text(encoding="utf-8")) or {}
        except Exception:
            cur = {}
    key = next((k for k in cur if k.lower() == character.lower()), character)
    clean_states = []
    for st in states:
        if not isinstance(st, dict):
            continue
        w = str(st.get("wardrobe") or "").strip()
        sc = str(st.get("scenes") or "").strip()
        loc = str(st.get("location") or "").strip()
        if w or sc or loc:
            clean_states.append({"scenes": sc, "location": loc, "wardrobe": w})
    cur[key] = clean_states
    ws_path.write_text(json.dumps(cur, indent=2), encoding="utf-8")
    return {"status": "ok", "character": key, "states": clean_states}


@route("POST", "/api/v2_turnaround_render")
def _v2_turnaround_render(r: Request):
    """Generate or upload a character turnaround view (front, three_quarter, profile) in assets/turnarounds/."""
    import base64

    slug = str(r.body.get("project") or "").strip()
    char_name = str(r.body.get("character") or "").strip()
    view = str(r.body.get("view") or "front").strip().lower()
    if not slug or not char_name or view not in ("front", "three_quarter", "profile"):
        raise PlanError("project, character, and valid view (front, three_quarter, profile) are required")

    pd = pdir(slug, "book")
    safe = "".join(c if c.isalnum() else "_" for c in char_name.lower()).strip("_") or "char"
    t_dir = pd / "assets" / "turnarounds"
    t_dir.mkdir(parents=True, exist_ok=True)
    out_png = t_dir / f"{safe}_{view}.png"
    rel_url = f"/file/{slug}/assets/turnarounds/{safe}_{view}.png"

    b64 = str(r.body.get("image_base64") or "").strip()
    if b64:
        if "," in b64 and b64.startswith("data:"):
            b64 = b64.split(",", 1)[1]
        raw = base64.b64decode(b64)
        if len(raw) < 100:
            raise PlanError("uploaded turnaround image is empty")
        out_png.write_bytes(raw)
        return {"status": "ok", "character": char_name, "view": view, "image_url": rel_url, "model": "uploaded"}

    desc = str(r.body.get("desc") or "").strip()
    look = str(r.body.get("look") or "pixar_3d").strip()
    view_desc = {"front": "front facing portrait", "three_quarter": "three-quarter angle view", "profile": "side profile view"}[view]
    prompt = f"Character design turnaround sheet ({view_desc}) of {char_name}. {desc}. Style: {look}. Clean neutral studio backdrop, full head and shoulders clearly visible, consistent costume and lighting."
    model_used = _render_keyframe_gemini(prompt, out_png, aspect_ratio="1:1")
    return {"status": "ok", "character": char_name, "view": view, "image_url": rel_url, "model": model_used}


@route("POST", "/api/v2_postprod_save")
def _v2_postprod_save(r: Request):
    """Save Steps 19-21 polish, timeline, and audio mix settings to postprod_v2.json."""
    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    pp_path = pd / "postprod_v2.json"
    cur = {}
    if pp_path.is_file():
        try:
            cur = json.loads(pp_path.read_text(encoding="utf-8")) or {}
        except Exception:
            cur = {}
    for section in ("polish", "timeline", "mix"):
        if isinstance(r.body.get(section), dict):
            cur[section] = {**(cur.get(section) or {}), **r.body[section]}
    pp_path.write_text(json.dumps(cur, indent=2), encoding="utf-8")
    return {"status": "ok", "saved": cur}


@route("POST", "/api/v2_audio_mix_render")
def _v2_audio_mix_render(r: Request):
    """Mix Dialogue + Foley + Score WAV stems into audio/mix/master_mix.wav using saved dB levels."""
    import math
    import struct
    import wave

    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    dlg_db = float(r.body.get("dialogue_db", 0.0))
    foley_db = float(r.body.get("foley_db", -3.0))
    score_db = float(r.body.get("score_db", -6.0))
    ducking = bool(r.body.get("ducking", True))

    # Save mix settings
    pp_path = pd / "postprod_v2.json"
    cur = {}
    if pp_path.is_file():
        try:
            cur = json.loads(pp_path.read_text(encoding="utf-8")) or {}
        except Exception:
            cur = {}
    cur["mix"] = {"dialogue_db": dlg_db, "foley_db": foley_db, "score_db": score_db, "ducking": ducking, "lufs": int(r.body.get("lufs", -16))}
    pp_path.write_text(json.dumps(cur, indent=2), encoding="utf-8")

    dlg_dir = pd / "audio" / "dialogue"
    dlg_files = sorted(dlg_dir.glob("*.wav")) if dlg_dir.is_dir() else []
    foley_file = pd / "audio" / "foley" / "foley_master.wav"
    score_file = pd / "audio" / "score" / "score_master.wav"
    if not dlg_files and not foley_file.is_file() and not score_file.is_file():
        raise PlanError("No audio tracks found yet. Render at least one Dialogue line (Step 15) or Score/Foley track (Step 16) first.")

    def _read_mono_22k(path: Path) -> list[float]:
        with wave.open(str(path), "rb") as wf:
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            sr = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
        if sw != 2:
            return []
        vals = struct.unpack(f"<{len(raw)//2}h", raw)
        mono = [(vals[i] / 32768.0) for i in range(0, len(vals), ch)] if ch > 1 else [v / 32768.0 for v in vals]
        if sr != 22050 and mono:
            ratio = sr / 22050.0
            out_n = max(1, int(len(mono) / ratio))
            mono = [mono[min(len(mono) - 1, int(i * ratio))] for i in range(out_n)]
        return mono

    dlg_track: list[float] = []
    gap = [0.0] * int(22050 * 0.35)
    for f in dlg_files[:20]:
        try:
            dlg_track.extend(_read_mono_22k(f))
            dlg_track.extend(gap)
        except Exception:
            continue

    foley_track = _read_mono_22k(foley_file) if foley_file.is_file() else []
    score_track = _read_mono_22k(score_file) if score_file.is_file() else []

    total_len = max(len(dlg_track), len(foley_track), len(score_track), 22050 * 4)
    total_len = min(total_len, 22050 * 120)  # cap preview mix at 2 min for instant response

    g_dlg = 10.0 ** (dlg_db / 20.0)
    g_fol = 10.0 ** (foley_db / 20.0)
    g_sco = 10.0 ** (score_db / 20.0)

    out_dir = pd / "audio" / "mix"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_wav = out_dir / "master_mix.wav"
    frames = bytearray()
    for i in range(total_len):
        d = dlg_track[i] * g_dlg if i < len(dlg_track) else 0.0
        duck = 0.45 if (ducking and abs(d) > 0.02) else 1.0
        f = (foley_track[i % len(foley_track)] * g_fol * (0.75 if duck < 1.0 else 1.0)) if foley_track else 0.0
        s = (score_track[i % len(score_track)] * g_sco * duck) if score_track else 0.0
        v = max(-0.96, min(0.96, d + f + s))
        frames.extend(struct.pack("<h", int(v * 32767)))

    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(bytes(frames))

    return {
        "status": "ok",
        "audio_url": f"/file/{slug}/audio/mix/master_mix.wav",
        "duration_sec": round(total_len / 22050.0, 1),
        "stems": {"dialogue_files": len(dlg_files), "foley": foley_file.is_file(), "score": score_file.is_file()},
    }


@route("POST", "/api/v2_export_make")
def _v2_export_make(r: Request):
    """Generate dynamic deliverables for the active book: fountain screenplay, EDL, WAV stems ZIP, or assembled MP4."""
    import zipfile

    slug = str(r.body.get("project") or "").strip()
    target = str(r.body.get("target") or "").strip().lower()
    if not slug or not target:
        raise PlanError("project and target are required")
    pd = pdir(slug, "book")
    exp_dir = pd / "exports"
    exp_dir.mkdir(parents=True, exist_ok=True)

    if target == "fountain":
        sp_dir = pd / "screenplay"
        lines = [f"Title: {slug.replace('_', ' ').title()}", "Credit: Adapted by Pistachio's Studio", ""]
        if sp_dir.is_dir():
            for sf in sorted(sp_dir.glob("scene-*.json")):
                try:
                    sc = json.loads(sf.read_text(encoding="utf-8")) or {}
                except Exception:
                    continue
                if sc.get("heading"):
                    lines.append(str(sc["heading"]).upper())
                    lines.append("")
                for el in sc.get("elements") or []:
                    if not isinstance(el, dict):
                        continue
                    if el.get("type") == "dialogue":
                        lines.append(str(el.get("character") or "SPEAKER").upper())
                        if el.get("note"):
                            lines.append(f"({el['note']})")
                        lines.append(str(el.get("text") or ""))
                        lines.append("")
                    elif el.get("text"):
                        lines.append(str(el["text"]))
                        lines.append("")
        out = exp_dir / f"{slug}.fountain"
        out.write_text("\n".join(lines), encoding="utf-8")
        return {"status": "ok", "target": target, "download_url": f"/download/{slug}/exports/{slug}.fountain"}

    if target == "edl":
        sl_path = pd / "shots" / "shotlist.json"
        edl_lines = [f"TITLE: {slug.upper()}", "FCM: NON-DROP FRAME", ""]
        idx = 1
        cur_sec = 0.0
        if sl_path.is_file():
            sl = json.loads(sl_path.read_text(encoding="utf-8")) or {}
            for sc in sl.get("scenes") or []:
                for sh in sc.get("shots") or []:
                    dur = float(sh.get("seconds") or 4.0)
                    def _tc(s):
                        h, rem = divmod(int(s), 3600)
                        m, sec = divmod(rem, 60)
                        return f"{h:02d}:{m:02d}:{sec:02d}:00"
                    edl_lines.append(f"{idx:03d}  AX       V     C        00:00:00:00 {_tc(dur)} {_tc(cur_sec)} {_tc(cur_sec + dur)}")
                    edl_lines.append(f"* FROM CLIP NAME: {sc.get('id', 'S001')}-{int(sh.get('n') or idx):02d}")
                    cur_sec += dur
                    idx += 1
        out = exp_dir / "timeline.edl"
        out.write_text("\n".join(edl_lines), encoding="utf-8")
        return {"status": "ok", "target": target, "download_url": f"/download/{slug}/exports/timeline.edl"}

    if target == "stems_zip":
        out = exp_dir / "audio_stems.zip"
        wavs = list((pd / "audio").rglob("*.wav")) if (pd / "audio").is_dir() else []
        if not wavs:
            raise PlanError("No rendered WAV stems found yet. Render dialogue (Step 15) or Score/Foley (Step 16) first.")
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for w in wavs:
                zf.write(w, arcname=w.relative_to(pd / "audio").as_posix())
        return {"status": "ok", "target": target, "files": len(wavs), "download_url": f"/download/{slug}/exports/audio_stems.zip"}

    if target in ("master_mp4", "shorts_9x16"):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise PlanError("ffmpeg is required to assemble MP4 video cuts.")
        films_dir = pd / "films"
        films_dir.mkdir(parents=True, exist_ok=True)
        out_mp4 = films_dir / ("shorts_9x16.mp4" if target == "shorts_9x16" else "master_cut.mp4")

        vid_files = []
        for vdir in (pd / "videos" / "gemini_omni_12_flash", pd / "videos"):
            if vdir.is_dir():
                vid_files.extend(sorted(vdir.glob("*.mp4")))
        kf_files = sorted((pd / "keyframes").glob("*.png")) if (pd / "keyframes").is_dir() else []
        mix_wav = pd / "audio" / "mix" / "master_mix.wav"

        if vid_files:
            concat_txt = films_dir / "_concat.txt"
            concat_txt.write_text("\n".join(f"file '{v.resolve()}'" for v in vid_files), encoding="utf-8")
            vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" if target == "shorts_9x16" else "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
            cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt)]
            if mix_wav.is_file():
                cmd.extend(["-i", str(mix_wav), "-map", "0:v:0", "-map", "1:a:0", "-shortest"])
            cmd.extend(["-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out_mp4)])
            subprocess.run(cmd, check=True, timeout=180)
        elif kf_files:
            # Assemble a real animatic MP4 from rendered Step 17 keyframes + Step 21 audio mix
            concat_txt = films_dir / "_kf_concat.txt"
            entries = []
            for kf in kf_files:
                entries.append(f"file '{kf.resolve()}'")
                entries.append("duration 3")
            entries.append(f"file '{kf_files[-1].resolve()}'")
            concat_txt.write_text("\n".join(entries), encoding="utf-8")
            vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" if target == "shorts_9x16" else "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
            cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt)]
            if mix_wav.is_file():
                cmd.extend(["-i", str(mix_wav), "-shortest"])
            cmd.extend(["-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "24", "-c:a", "aac", str(out_mp4)])
            subprocess.run(cmd, check=True, timeout=180)
        else:
            raise PlanError("No video clips (Step 18) or storyboard keyframes (Step 17) rendered yet to assemble.")

        return {
            "status": "ok",
            "target": target,
            "video_url": f"/file/{slug}/films/{out_mp4.name}",
            "download_url": f"/download/{slug}/films/{out_mp4.name}",
        }

    raise PlanError(f"Unknown export target: {target}")


