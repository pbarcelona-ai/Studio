"""POST routes of the JSON API (uploads are streamed by handler.py instead)."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import character_tokens
import detect_scene_changes
import redo_audio
import setup_check
from bookkit import SLUG_RE
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .api import HttpError, Request, route
from .log import get_logger

log = get_logger("routes_post")
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


@route("POST", "/api/v2_beats_sync_from_screenplay")
def _v2_beats_sync_from_screenplay(r: Request):
    """Reverse-sync Step 06 screenplay scenes back into Step 05 Story Outline & Beat Sheet."""
    import adaptation

    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("pick a project first")
    pd = pdir(slug, "book")
    res = adaptation.sync_beats_from_screenplay(pd)
    if not res.get("synced"):
        raise PlanError("No screenplay scenes found in Step 06 to sync into Step 05.")
    return {"status": "ok", **res}


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
    hm = r.body.get("hybrid_mode")
    save_global_params(
        project,
        r.body.get("positives", ""),
        r.body.get("negatives", ""),
        look=str(r.body.get("look", "") or ""),
        motion_cadence=str(r.body.get("motion_cadence", "") or ""),
        hybrid_mode=hm if isinstance(hm, dict) else None,
    )
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
    import continuity_sync

    char = b.get("character", {})
    series = str(char.get("series") or b.get("series") or "").strip()
    cname = str(char.get("name") or "").strip()
    prev = character_tokens.load_character(series, cname) if (series and cname) else None
    char["stages"] = clean_stages(char.get("stages"))
    saved_path = str(character_tokens.save_character(char))
    sync_report: dict[str, Any] = {"updated_steps": [], "changes": [], "preserved": []}
    if series and cname and SLUG_RE.match(series) and pdir(series, "book").is_dir():
        old_tok = str((prev or {}).get("visual_token") or (prev or {}).get("description") or "")
        new_tok = str(char.get("visual_token") or char.get("description") or "")
        old_v = str((prev or {}).get("voice") or "")
        new_v = str(char.get("voice") or "")
        sync_report = continuity_sync.sync_character_profile(
            pdir(series, "book"),
            series,
            name=cname,
            old_token=old_tok,
            new_token=new_tok,
            old_voice=old_v,
            new_voice=new_v,
            source_step="step08",
        )
    return {"saved": True, "path": saved_path, "sync_report": sync_report}


def _ch_use_reference(b):
    return {"updated": character_tokens.use_reference(b.get("series", ""), b.get("name", ""), b.get("path", ""))}


def _ch_add_reference(b):
    return {"updated": character_tokens.add_reference_image(b.get("series", ""), b.get("name", ""), b.get("image_path", ""))}


def _ch_update_lora(b):
    return {"updated": character_tokens.update_lora_info(b.get("series", ""), b.get("name", ""), b.get("lora_repo", ""),
                                                         b.get("trigger_word", ""), b.get("base_model", ""))}


def _ch_create(b):
    char = character_tokens.create_character_from_description(b.get("series", ""), b.get("name", ""), b.get("description", ""), b.get("visual_token", ""))
    if b.get("archetype"):
        char["archetype"] = str(b.get("archetype")).strip()
    if b.get("style_override") is not None:
        char["style_override"] = str(b.get("style_override") or "").strip()
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


def _run_book_ingest_sync(slug: str, src_path: Path) -> dict:
    """Run scripts/book_ingest.py synchronously to create source_text.txt, chapters/, and chapters.json for a book."""
    import sys

    ingest_script = ROOT / "scripts" / "book_ingest.py"
    if not ingest_script.is_file():
        raise PlanError("book_ingest.py not found")
    proc = subprocess.run(
        [sys.executable, str(ingest_script), slug, str(src_path)],
        cwd=str(ROOT / "scripts"),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "book_ingest failed").strip()[-350:]
        raise PlanError(f"Could not read & split book: {err}")
    pd = pdir(slug, "book")
    chap_count = 0
    cj = pd / "chapters.json"
    if cj.is_file():
        try:
            chap_count = len((json.loads(cj.read_text(encoding="utf-8")) or {}).get("chapters") or [])
        except Exception as e:
            log.debug("chapters.json read failed: %s", e)
    return {"slug": slug, "chapters": chap_count, "read": cj.is_file()}


@route("POST", "/api/save_story")
def _save_story(r: Request):
    from bookkit import slugify

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

    slug = slugify(Path(safe_name).stem)
    ingest_info = _run_book_ingest_sync(slug, target)
    return {
        "saved": True,
        "slug": slug,
        "filename": safe_name,
        "path": str(target.relative_to(ROOT)),
        "bytes": len(text),
        "chapters": ingest_info.get("chapters", 0),
        "read": ingest_info.get("read", False),
    }


@route("POST", "/api/v2_ingest_book")
def _v2_ingest_book(r: Request):
    """Read & split an uploaded or books/-folder book into chapters/ + chapters.json immediately."""
    from bookkit import slugify

    raw_proj = str(r.body.get("project") or r.body.get("filename") or "").strip()
    if not raw_proj:
        raise PlanError("project or filename is required")
    slug = slugify(Path(raw_proj).stem if "." in raw_proj else raw_proj)
    pd = pdir(slug, "book")

    src_file = None
    if r.body.get("filename"):
        cand = ROOT / "books" / Path(str(r.body["filename"])).name
        if cand.is_file():
            src_file = cand
    if src_file is None and (pd / "source").is_dir():
        for p in sorted((pd / "source").iterdir()):
            if p.is_file() and p.suffix.lower() in (".pdf", ".epub", ".docx", ".txt", ".md", ".html"):
                src_file = p
                break
    if src_file is None and (ROOT / "books").is_dir():
        for p in sorted((ROOT / "books").iterdir()):
            if p.is_file() and slugify(p.stem) == slug:
                src_file = p
                break
    if src_file is None:
        raise PlanError(f"Could not find source book file for '{slug}'. Save or upload the book in Step 01 first.")

    info = _run_book_ingest_sync(slug, src_file)
    return {"status": "ok", **info, "source": src_file.name}


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
    vc_data: dict[str, Any] = {}
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
        idx: dict[str, Any] = {}
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
    existing_doc: dict[str, Any] = {}
    if dl_path.is_file():
        try:
            existing_doc = json.loads(dl_path.read_text(encoding="utf-8")) or {}
        except Exception:
            existing_doc = {}
    raw_existing = existing_doc.get("lines")
    existing: dict[str, Any] = raw_existing if isinstance(raw_existing, dict) else {}
    engine = str(r.body.get("engine") or existing_doc.get("engine") or "").strip()
    incoming = r.body.get("lines")
    if isinstance(incoming, list):
        for item in incoming:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            lid = str(item["id"]).strip()
            raw_prev = existing.get(lid)
            prev: dict[str, Any] = raw_prev if isinstance(raw_prev, dict) else {}
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
                "speed": max(0.5, min(1.8, float((item.get("speed") if item.get("speed") is not None else prev.get("speed")) or 1.0))),
            }
    elif isinstance(r.body.get("id"), str) and r.body["id"].strip():
        lid = r.body["id"].strip()
        raw_prev = existing.get(lid)
        prev = raw_prev if isinstance(raw_prev, dict) else {}
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
            "speed": max(0.5, min(1.8, float((r.body.get("speed") if r.body.get("speed") is not None else prev.get("speed")) or 1.0))),
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
        except Exception as e:
            log.debug("voice library load failed: %s", e)
    return {}


def _voice_library_save_entry(character: str, entry: dict, src_wav: Path | None = None) -> dict:
    """Persist a character's voice profile and/or baseline WAV to the global cross-film voice library."""
    from datetime import UTC, datetime

    VOICE_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    lib = _voice_library_load()
    key = next((k for k in lib if k.lower() == character.lower()), character)
    cur = dict(lib.get(key) or {})
    cur.update({k: v for k, v in entry.items() if v is not None})
    cur["character"] = key
    cur["updated_at"] = datetime.now(UTC).isoformat()

    safe_char = "".join(c if c.isalnum() else "_" for c in key.lower()).strip("_") or "speaker"
    if src_wav and src_wav.is_file() and src_wav.stat().st_size > 100:
        lib_wav = VOICE_LIBRARY_DIR / f"{safe_char}.wav"
        shutil.copyfile(src_wav, lib_wav)
        cur["wav_file"] = f"{safe_char}.wav"

    lib[key] = cur
    (VOICE_LIBRARY_DIR / "library.json").write_text(json.dumps(lib, indent=2), encoding="utf-8")
    return cur


def _norm_voice_char(name: str) -> str:
    """Normalize a screenplay speaker name by stripping parenthetical tags like (V.O.), (O.S.), (CONT'D)."""
    import re as _re

    return _re.sub(r"\s*\([^)]*\)\s*", " ", str(name or "")).strip().lower()


def _apply_voice_profile_to_character(
    pd: Path,
    slug: str,
    character: str,
    incoming_fields: dict[str, Any],
    *,
    vdata: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], int, dict[str, Any]]:
    """Save a character's voice profile into voice_cast.json and propagate it to EVERY dialogue line
    spoken by that character across all scenes (preserving each line's emotion/tone and delivery note)."""
    vc_path = pd / "voice_cast.json"
    if vdata is None:
        vdata = {}
        if vc_path.is_file():
            try:
                vdata = json.loads(vc_path.read_text(encoding="utf-8")) or {}
            except Exception:
                vdata = {}
    raw_cast = vdata.get("cast")
    cast: dict[str, Any] = raw_cast if isinstance(raw_cast, dict) else {}
    raw_profiles = vdata.get("profiles")
    profiles: dict[str, Any] = raw_profiles if isinstance(raw_profiles, dict) else {}

    target_norm = _norm_voice_char(character)
    existing_key = next(
        (k for k in profiles if k.lower() == character.lower() or _norm_voice_char(k) == target_norm),
        character,
    )
    raw_prof = profiles.get(existing_key)
    prof: dict[str, Any] = dict(raw_prof) if isinstance(raw_prof, dict) else {}
    for field in ("gemini_voice", "kokoro_voice", "kokoro_blend", "macos_voice", "persona"):
        if field in incoming_fields and incoming_fields[field] is not None:
            prof[field] = str(incoming_fields[field]).strip()
    if incoming_fields.get("speed") is not None:
        try:
            prof["speed"] = max(0.5, min(1.8, float(incoming_fields["speed"])))
        except (TypeError, ValueError):
            pass
    if prof.get("kokoro_voice"):
        cast_key = next(
            (k for k in cast if k.lower() == character.lower() or _norm_voice_char(k) == target_norm),
            character,
        )
        cast[cast_key] = str(prof["kokoro_voice"]).strip()
    profiles[existing_key] = prof
    vdata["cast"] = cast
    vdata["profiles"] = profiles
    vc_path.write_text(json.dumps(vdata, indent=2), encoding="utf-8")

    # Propagate profile to every dialogue line spoken by this character, WITHOUT touching each line's emotion/tone or note
    dl_path = pd / "dialogue_lines.json"
    ddata: dict[str, Any] = {}
    if dl_path.is_file():
        try:
            ddata = json.loads(dl_path.read_text(encoding="utf-8")) or {}
        except Exception:
            ddata = {}
    raw_saved_lines = ddata.get("lines")
    saved_lines: dict[str, Any] = raw_saved_lines if isinstance(raw_saved_lines, dict) else {}

    updated_count = 0
    sp_dir = pd / "screenplay"
    if sp_dir.is_dir():
        for sp_file in sorted(sp_dir.glob("scene-*.json")):
            try:
                sc = json.loads(sp_file.read_text(encoding="utf-8")) or {}
            except Exception as e:
                log.debug("skipping unreadable scene %s: %s", sp_file.name, e)
                continue
            sc_id = str(sc.get("scene") or sp_file.stem.replace("scene-", ""))
            idx = 0
            for el in sc.get("elements") or []:
                if not isinstance(el, dict) or el.get("type") != "dialogue":
                    continue
                idx += 1
                el_char = str(el.get("character") or "").strip()
                if el_char.lower() != character.lower() and _norm_voice_char(el_char) != target_norm:
                    continue
                lid = f"{sc_id}-{idx:02d}"
                raw_cur = saved_lines.get(lid)
                cur: dict[str, Any] = dict(raw_cur) if isinstance(raw_cur, dict) else {}
                for field in ("gemini_voice", "kokoro_voice", "kokoro_blend", "macos_voice", "persona"):
                    if field in prof:
                        cur[field] = prof[field]
                if "speed" in prof:
                    cur["speed"] = prof["speed"]
                if prof.get("kokoro_voice"):
                    cur["voice"] = prof["kokoro_voice"]
                # Preserve per-line emotion/tone and delivery note untouched!
                saved_lines[lid] = cur
                updated_count += 1

    ddata["lines"] = saved_lines
    dl_path.write_text(json.dumps(ddata, indent=2), encoding="utf-8")
    return prof, updated_count, vdata


@route("POST", "/api/v2_voice_profile_apply")
def _v2_voice_profile_apply(r: Request):
    """Save a character's voice profile (voice, blend, persona, speed) for ALL scenes while leaving per-line emotion/tone untouched."""
    slug = str(r.body.get("project") or "").strip()
    character = str(r.body.get("character") or "").strip()
    if not slug or not character:
        raise PlanError("project and character are required")

    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    prof, updated_count, _vdata = _apply_voice_profile_to_character(pd, slug, character, r.body)

    # Also save character voice profile to global cross-film library for future films
    _voice_library_save_entry(character, {**prof, "source_project": slug})
    return {"status": "ok", "character": character, "profile": prof, "updated_lines": updated_count}


@route("POST", "/api/v2_dialogue_upload")
def _v2_dialogue_upload(r: Request):
    """Save a user-uploaded custom audio take (base64 WAV/MP3/M4A/AIFF) for a single dialogue line."""
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
    from studio_app import upload_validation

    raw, _audio_ext = upload_validation.decode_verified_base64(b64, kind="audio", min_bytes=64)

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
                subprocess.run([afconvert_bin, "-f", "WAVE", "-d", "LEI16@24000", str(tmp_in), str(wav_path)], stdin=subprocess.DEVNULL, check=True, timeout=30)
            elif ffmpeg_bin:
                subprocess.run([ffmpeg_bin, "-y", "-i", str(tmp_in), str(wav_path)], stdin=subprocess.DEVNULL, check=True, timeout=30)
            else:
                wav_path.write_bytes(raw)
        finally:
            tmp_in.unlink(missing_ok=True)

    return {"status": "ok", "id": safe_id, "audio_url": f"/file/{slug}/audio/dialogue/{safe_id}.wav"}


@route("POST", "/api/v2_voice_baseline_set")
def _v2_voice_baseline_set(r: Request):
    """Lock a rendered dialogue take or uploaded audio clip as a character's permanent voice baseline (or clear it)."""
    import tempfile

    slug = str(r.body.get("project") or "").strip()
    character = str(r.body.get("character") or "").strip()
    if not slug or not character:
        raise PlanError("project and character are required")

    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    vc_path = pd / "voice_cast.json"
    vdata: dict[str, Any] = {}
    if vc_path.is_file():
        try:
            vdata = json.loads(vc_path.read_text(encoding="utf-8")) or {}
        except Exception:
            vdata = {}
    raw_baselines = vdata.get("baselines")
    baselines: dict[str, Any] = raw_baselines if isinstance(raw_baselines, dict) else {}
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
        from studio_app import upload_validation

        filename = str(r.body.get("filename") or "baseline.wav").strip()
        raw, _audio_ext = upload_validation.decode_verified_base64(b64, kind="audio", min_bytes=64)
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
                    subprocess.run([afconvert_bin, "-f", "WAVE", "-d", "LEI16@24000", str(tmp_in), str(dest_wav)], stdin=subprocess.DEVNULL, check=True, timeout=30)
                elif ffmpeg_bin:
                    subprocess.run([ffmpeg_bin, "-y", "-i", str(tmp_in), str(dest_wav)], stdin=subprocess.DEVNULL, check=True, timeout=30)
                else:
                    dest_wav.write_bytes(raw)
            finally:
                tmp_in.unlink(missing_ok=True)
        source_label = filename
    else:
        raise PlanError("Provide either from_line_id or audio_base64 to set a character voice baseline.")

    # Collect voice profile settings from the request, falling back to the source line's saved settings
    profile_fields: dict[str, Any] = {}
    if from_line:
        dl_path = pd / "dialogue_lines.json"
        if dl_path.is_file():
            try:
                dl_doc = json.loads(dl_path.read_text(encoding="utf-8")) or {}
                src_line_cfg = (dl_doc.get("lines") or {}).get(from_line)
                if isinstance(src_line_cfg, dict):
                    for fld in ("gemini_voice", "kokoro_voice", "kokoro_blend", "macos_voice", "persona", "speed"):
                        if src_line_cfg.get(fld) is not None and src_line_cfg.get(fld) != "":
                            profile_fields[fld] = src_line_cfg[fld]
            except Exception as e:
                log.debug("dialogue_lines.json read for baseline profile failed: %s", e)
    for fld in ("gemini_voice", "kokoro_voice", "kokoro_blend", "macos_voice", "persona", "speed"):
        if fld in r.body and r.body[fld] is not None:
            profile_fields[fld] = r.body[fld]

    # Save & automatically propagate the baselined character's voice profile to every line of that character across all scenes
    prof, updated_lines, vdata = _apply_voice_profile_to_character(
        pd, slug, existing_key, profile_fields, vdata=vdata
    )

    # Also persist this baseline WAV & metadata into the global cross-film voice library
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
        "profile": prof,
    }
    cleared_list = [c for c in (vdata.get("cleared_baselines") or []) if c.lower() != existing_key.lower()]
    vdata["cleared_baselines"] = cleared_list
    vdata["baselines"] = baselines
    vc_path.write_text(json.dumps(vdata, indent=2), encoding="utf-8")
    return {
        "status": "ok",
        "character": existing_key,
        "profile": prof,
        "updated_lines": updated_lines,
        "baseline": {
            "file": rel_file,
            "source": source_label,
            "text": sample_text,
            "saved_to_library": True,
            "source_project": slug,
            "profile": prof,
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
        content_variants: list[Any] = []
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
            except Exception as e:
                log.debug("kokoro entry read failed for %s: %s", kb, e)
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
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=4,
            )
            if r.returncode == 0:
                return py
        except Exception as e:
            log.debug("kokoro probe failed for %s: %s", py, e)
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
        stdin=subprocess.DEVNULL,
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
        stdin=subprocess.DEVNULL,
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
            out = subprocess.check_output([say_bin, "-v", "?"], stdin=subprocess.DEVNULL, text=True, timeout=5)
            for ln in out.splitlines():
                parts = ln.strip().split()
                if parts:
                    avail.add(parts[0])
        except Exception as e:
            log.debug("say -v probe failed: %s", e)

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
                except Exception as e:
                    log.debug("voice_cast baselines read failed: %s", e)
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
            assert say_bin is not None
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
                subprocess.run(cmd, stdin=subprocess.DEVNULL, check=True, timeout=30)
                if afconvert_bin:
                    subprocess.run([afconvert_bin, "-f", "WAVE", "-d", "LEI16@22050", str(aiff_path), str(wav_path)], stdin=subprocess.DEVNULL, check=True, timeout=20)
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


_STOCK_FOLEY_PROMPTS = {
    "space_adventure": {
        "starship bridge hum, cockpit console telemetry chimes, and clean sci-fi instrumentation.",
        "starship bridge hum, cockpit console chimes, space ambiance",
    },
    "spaceship_voices": {
        "a low spaceship hum and distant voices in background",
        "low warm spaceship cabin hum with muffled distant crew voices murmuring in the background.",
    },
    "rainy_home": {
        "steady rain pattering on a living room window, individual droplets on glass, and soft distant thunder.",
        "rain pattering on window, warm indoor room ambiance",
    },
    "soft_rain_room": {
        "subtle muffled distant rain outside a quiet cozy room (not hitting the window), gentle soft indoor room tone.",
    },
    "cosmic_storm": {
        "sweeping atmospheric wind gusts, sparkling ice-ring crystal chimes, and deep planetary resonance.",
        "atmospheric wind gusts, shimmering ice particles, planetary rumble",
    },
    "action_launch": {
        "building rocket engine roar, heavy sub-bass ignition rumble, and rising thruster turbine whine.",
        "rockets burning, spaceship hull shaking, heavy ignition rumble",
    },
    "forest_nature": {
        "gentle evening breeze with rhythmic distant night crickets and quiet outdoor air.",
        "evening breeze and gentle outdoor ambient air",
    },
    "silent": {
        "silent (no ambient sfx or foley).",
        "silent",
    },
}


def _parse_custom_foley_layers(prompt: str) -> tuple[list[str], float]:
    """Parse a free-text SFX description into acoustic synthesis layers and a gain multiplier."""
    low = " ".join(str(prompt or "").strip().lower().split())
    if not low:
        return [], 1.0
    if any(w in low for w in ("no sound", "no sfx", "muted", "mute only")) or low in ("silent", "silence", "none", "mute"):
        return ["silent"], 0.0

    # Volume / intensity modifier (ignore "distant" when it only modifies "voices"/"thunder")
    low_no_distant_src = low.replace("distant voices", "").replace("distant voice", "").replace("distant thunder", "")
    gain = 1.0
    if any(w in low_no_distant_src for w in ("very quiet", "barely audible", "whisper", "very subtle", "ultra soft")):
        gain = 0.25
    elif any(w in low_no_distant_src for w in ("subtle", "soft", "quiet", "gentle", "distant", "faint", "muffled", "low volume", "light")):
        gain = 0.38
    elif any(w in low_no_distant_src for w in ("loud", "heavy", "intense", "booming", "roaring", "strong")):
        gain = 1.30

    layers: list[str] = []
    if any(w in low for w in ("fireplace", "hearth", "campfire", "fire", "crackl", "flame", "ember")):
        layers.append("fireplace")
    if any(w in low for w in ("rain", "drizzle", "downpour", "shower", "droplet", "patter")):
        if any(w in low for w in ("window", "glass", "tap", "hitting")) and not any(w in low for w in ("not hitting", "no window", "no glass")):
            layers.append("window_rain")
        else:
            layers.append("soft_rain")
    if any(w in low for w in ("thunder", "lightning")) and "no thunder" not in low:
        layers.append("thunder")
    if any(w in low for w in ("ocean", "wave", "surf", "beach", "sea", "tide")):
        layers.append("ocean")
    if any(w in low for w in ("river", "stream", "brook", "waterfall", "water", "fountain", "splash")):
        layers.append("water_stream")
    if any(w in low for w in ("wind", "breeze", "gust", "howl", "blizzard", "whoosh", "storm")):
        layers.append("wind")
    if any(w in low for w in ("footstep", "footsteps", "walking", "steps", "boots", "gravel", "crunch", "march")):
        layers.append("footsteps")
    if any(w in low for w in ("clock", "tick", "ticking", "watch")):
        layers.append("clock")
    if any(w in low for w in ("heartbeat", "heart beat", "pulse")):
        layers.append("heartbeat")
    if any(w in low for w in ("door", "knock", "creak", "wood")):
        layers.append("door_knock")
    if any(w in low for w in ("cricket", "cicada", "insect", "night")):
        layers.append("crickets")
    if any(w in low for w in ("bird", "birds", "chirp", "songbird", "morning", "forest", "meadow", "park", "garden")):
        layers.append("birds")
    if any(w in low for w in ("chime", "bell", "crystal", "sparkle", "magic", "shimmer", "ice ring", "fairy")):
        layers.append("chimes")
    if any(w in low for w in ("rocket", "launch", "thruster", "ignition", "jet", "explosion", "rumble", "earthquake", "shake")):
        layers.append("rocket_rumble")
    if any(w in low for w in ("spaceship", "starship", "bridge", "cockpit", "engine hum", "reactor", "cabin hum", "ship hum", "low hum", "hull hum")):
        layers.append("cabin_hum")
    if any(w in low for w in ("voice", "voices", "chatter", "murmur", "talking", "crowd", "crew", "intercom", "comms", "pa system")):
        layers.append("distant_voices")
    if any(w in low for w in ("telemetry", "sonar", "radar", "beep", "console")):
        layers.append("telemetry")
    if any(w in low for w in ("room", "indoor", "cozy", "home", "house", "library", "hall", "office", "ambient")):
        layers.append("room_tone")

    if not layers:
        layers.append("warm_ambience")
    return layers, gain


def _synth_custom_text_foley_wav(wav_path: Path, prompt: str, duration: int = 10) -> list[str]:
    """Synthesize a custom multi-layer stereo foley soundscape directly from the user's text description."""
    import math
    import random
    import struct
    import wave

    sr = 22050
    dur = max(4, min(30, int(duration or 10)))
    n = sr * dur
    layers, gain = _parse_custom_foley_layers(prompt)
    if layers == ["silent"] or gain <= 0.0:
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(bytes(n * 4))
        return ["silent"]

    rng = random.Random(hash("custom:" + prompt.strip().lower()) & 0xFFFFFFFF)
    layer_set = set(layers)
    lp1_l = lp1_r = lp2_l = lp2_r = 0.0
    hp_prev_l = hp_prev_r = 0.0
    frames = bytearray()

    # Pre-schedule transient events (crackles, droplets, birds, chimes, footsteps, knocks)
    events: list[tuple[float, str, float, float, float]] = []  # (t, kind, freq, decay, pan)
    if "fireplace" in layer_set:
        for _ in range(int(dur * 7)):
            events.append((rng.uniform(0.1, dur - 0.1), "crackle", rng.uniform(1400.0, 4200.0), rng.uniform(55.0, 120.0), rng.uniform(0.25, 0.75)))
    if "window_rain" in layer_set:
        for _ in range(int(dur * 6)):
            events.append((rng.uniform(0.1, dur - 0.2), "ping", rng.uniform(950.0, 2100.0), rng.uniform(30.0, 55.0), rng.uniform(0.15, 0.85)))
    if "chimes" in layer_set:
        for _ in range(int(dur * 2.5)):
            f = rng.choice([880.0, 1046.5, 1318.5, 1567.98, 2093.0])
            events.append((rng.uniform(0.2, dur - 0.4), "ping", f, rng.uniform(3.0, 6.0), rng.uniform(0.15, 0.85)))
    if "birds" in layer_set:
        for _ in range(int(dur * 1.4)):
            events.append((rng.uniform(0.3, dur - 0.4), "bird", rng.uniform(2200.0, 3600.0), 14.0, rng.uniform(0.1, 0.9)))
    if "footsteps" in layer_set:
        t_step = 0.35
        side = 0
        while t_step < dur - 0.3:
            events.append((t_step, "step", rng.uniform(110.0, 165.0), 26.0, 0.42 if side % 2 == 0 else 0.58))
            t_step += rng.uniform(0.46, 0.56)
            side += 1
    if "clock" in layer_set:
        t_ck = 0.25
        tick_i = 0
        while t_ck < dur - 0.15:
            events.append((t_ck, "tick", 1950.0 if tick_i % 2 == 0 else 1550.0, 95.0, 0.5))
            t_ck += 0.5
            tick_i += 1
    if "door_knock" in layer_set:
        for kt in (0.7, 1.05, 1.4, dur * 0.6, dur * 0.6 + 0.35):
            if kt < dur - 0.2:
                events.append((kt, "step", 155.0, 32.0, 0.5))
    events.sort(key=lambda x: x[0])
    ev_idx = 0
    active: list[tuple[float, str, float, float, float]] = []

    # Pre-schedule muffled distant conversational utterances (natural phrases + pauses, 3 distinct speakers)
    # Each phrase: (t_start, t_end, base_f0, syl_rate, pan, amp, formant_f)
    voice_phrases: list[tuple[float, float, float, float, float, float, float]] = []
    if "distant_voices" in layer_set:
        speakers = [
            (118.0, 4.2, 0.28, 0.13, 540.0),   # Low male voice softly left
            (196.0, 4.9, 0.72, 0.11, 760.0),   # Soft female voice softly right
            (138.0, 3.8, 0.48, 0.09, 620.0),   # Distant corridor voice center
        ]
        for sp_idx, (f0, srate, span, samp, ff) in enumerate(speakers):
            cursor = 0.35 + sp_idx * 0.85 + rng.uniform(0.0, 0.45)
            while cursor < dur - 0.6:
                plen = rng.uniform(0.9, 2.3)
                voice_phrases.append((cursor, min(dur - 0.2, cursor + plen), f0 * rng.uniform(0.94, 1.06), srate * rng.uniform(0.9, 1.12), span, samp, ff))
                cursor += plen + rng.uniform(0.7, 2.1)
    v_lp_l = v_lp_r = v_lp2_l = v_lp2_r = 0.0

    norm_scale = gain / math.sqrt(max(1, len(layer_set)))
    for i in range(n):
        t = i / sr
        env = min(1.0, t / 0.5) * min(1.0, (dur - t) / 0.5)
        sig_l = sig_r = 0.0

        while ev_idx < len(events) and events[ev_idx][0] <= t:
            active.append(events[ev_idx])
            ev_idx += 1

        nl, nr = rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0)
        lp1_l = lp1_l * 0.84 + nl * 0.16
        lp1_r = lp1_r * 0.84 + nr * 0.16
        lp2_l = lp2_l * 0.92 + lp1_l * 0.08
        lp2_r = lp2_r * 0.92 + lp1_r * 0.08
        hp_l = nl - hp_prev_l
        hp_r = nr - hp_prev_r
        hp_prev_l, hp_prev_r = nl, nr

        if "soft_rain" in layer_set:
            sig_l += lp1_l * 0.16
            sig_r += lp1_r * 0.16
        if "window_rain" in layer_set:
            sig_l += (lp1_l * 0.34 + hp_l * 0.02)
            sig_r += (lp1_r * 0.34 + hp_r * 0.02)
        if "thunder" in layer_set:
            th = 0.20 * max(0.0, math.sin(2 * math.pi * 0.13 * t - 0.9)) * (lp2_l * 1.4 + 0.5 * math.sin(2 * math.pi * 46.0 * t))
            sig_l += th
            sig_r += th * 0.92
        if "fireplace" in layer_set:
            flick = 0.75 + 0.25 * math.sin(2 * math.pi * 0.7 * t)
            sig_l += lp2_l * 0.35 * flick
            sig_r += lp2_r * 0.35 * flick
        if "ocean" in layer_set:
            wave_env = 0.18 + 0.42 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.16 * t)) ** 2
            sig_l += lp1_l * wave_env
            sig_r += lp1_r * wave_env * 0.94
        if "water_stream" in layer_set:
            babble = 0.22 + 0.08 * math.sin(2 * math.pi * 1.3 * t)
            sig_l += lp1_l * babble
            sig_r += lp1_r * babble
        if "wind" in layer_set:
            sw = 0.25 + 0.25 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.21 * t))
            wh = 0.07 * sw * math.sin(2 * math.pi * (290.0 + 70.0 * math.sin(2 * math.pi * 0.14 * t)) * t)
            sig_l += lp1_l * sw + wh * 0.8
            sig_r += lp1_r * sw + wh * 1.1
        if "crickets" in layer_set:
            gate = 1.0 if (t % 0.9) < 0.26 else 0.0
            pulse = 0.5 + 0.5 * math.sin(2 * math.pi * 24.0 * t)
            cr = 0.09 * gate * pulse * math.sin(2 * math.pi * 4100.0 * t)
            sig_l += cr * 0.65
            sig_r += cr * 1.05
        if "heartbeat" in layer_set:
            hb_t = t % 0.95
            lub = 0.32 * math.exp(-hb_t * 22.0) * math.sin(2 * math.pi * 58.0 * hb_t)
            dub = 0.22 * math.exp(-max(0.0, hb_t - 0.22) * 26.0) * math.sin(2 * math.pi * 50.0 * max(0.0, hb_t - 0.22)) if hb_t > 0.22 else 0.0
            sig_l += lub + dub
            sig_r += lub + dub
        if "rocket_rumble" in layer_set:
            ramp = min(1.0, 0.3 + 0.7 * (t / dur))
            sig_l += lp2_l * 0.72 * ramp + 0.22 * ramp * math.sin(2 * math.pi * 42.0 * t)
            sig_r += lp2_r * 0.72 * ramp + 0.22 * ramp * math.sin(2 * math.pi * 42.0 * t)
        if "cabin_hum" in layer_set:
            # Deep smooth warm spaceship hull/reactor hum + soft ventilation air (zero beeps)
            lfo = 0.88 + 0.12 * math.sin(2 * math.pi * 0.17 * t)
            hum = (
                0.22 * math.sin(2 * math.pi * 55.0 * t)
                + 0.12 * math.sin(2 * math.pi * 82.41 * t)
                + 0.06 * math.sin(2 * math.pi * 110.0 * t)
            ) * lfo
            sig_l += hum + lp2_l * 0.16
            sig_r += hum * 0.96 + lp2_r * 0.16
        if "distant_voices" in layer_set:
            vl_raw = vr_raw = 0.0
            for vt0, vt1, vf0, vsrate, vpan, vamp, vff in voice_phrases:
                if vt0 <= t <= vt1:
                    dt_v = t - vt0
                    plen_v = max(0.2, vt1 - vt0)
                    phr_env = min(1.0, dt_v / 0.12) * min(1.0, (vt1 - t) / 0.18)
                    # Natural syllable cadence with slight vowel variation
                    syl_phase = dt_v * vsrate
                    syl_env = max(0.0, math.sin(math.pi * (syl_phase % 1.0))) ** 1.6
                    # Gentle pitch contour (slight rise/fall over each phrase)
                    pitch = vf0 * (1.0 + 0.09 * math.sin(2 * math.pi * (dt_v / plen_v) * 1.2) + 0.03 * math.sin(2 * math.pi * 5.2 * dt_v))
                    # Soft vocal-tract formant harmonic blend + faint whispered consonant air
                    voiced = (
                        0.45 * math.sin(2 * math.pi * pitch * t)
                        + 0.35 * math.sin(2 * math.pi * (pitch * 2.0) * t)
                        + 0.28 * math.sin(2 * math.pi * vff * t) * math.sin(2 * math.pi * pitch * t)
                        + 0.14 * lp1_l * (0.5 + 0.5 * math.sin(2 * math.pi * 11.0 * dt_v))
                    )
                    v_sig = vamp * phr_env * syl_env * voiced
                    vl_raw += v_sig * (1.0 - vpan)
                    vr_raw += v_sig * vpan
            # Double low-pass muffle so voices sit smoothly behind walls / in the distance
            v_lp_l = v_lp_l * 0.78 + vl_raw * 0.22
            v_lp_r = v_lp_r * 0.78 + vr_raw * 0.22
            v_lp2_l = v_lp2_l * 0.72 + v_lp_l * 0.28
            v_lp2_r = v_lp2_r * 0.72 + v_lp_r * 0.28
            sig_l += v_lp2_l * 1.45
            sig_r += v_lp2_r * 1.45
        if "telemetry" in layer_set:
            cyc = t % 1.8
            if 0.25 < cyc < 0.38:
                be = math.sin(math.pi * (cyc - 0.25) / 0.13)
                bp = 0.14 * be * math.sin(2 * math.pi * 987.77 * t)
                sig_l += bp * 0.7
                sig_r += bp
        if "room_tone" in layer_set or "warm_ambience" in layer_set:
            sig_l += lp2_l * 0.10
            sig_r += lp2_r * 0.10

        if active:
            keep = []
            for st_t, ekind, efreq, edec, epan in active:
                dt = t - st_t
                if dt < 0.55:
                    if ekind == "crackle":
                        v = 0.18 * math.exp(-dt * edec) * (nl if epan < 0.5 else nr)
                    elif ekind == "bird":
                        chirp_f = efreq + 650.0 * math.sin(2 * math.pi * 16.0 * dt)
                        v = 0.10 * math.exp(-dt * edec) * math.sin(2 * math.pi * chirp_f * dt)
                    elif ekind == "step":
                        v = 0.26 * math.exp(-dt * edec) * (0.6 * math.sin(2 * math.pi * efreq * dt) + 0.4 * lp1_l)
                    elif ekind == "tick":
                        v = 0.14 * math.exp(-dt * edec) * math.sin(2 * math.pi * efreq * dt)
                    else:
                        v = 0.11 * math.exp(-dt * edec) * math.sin(2 * math.pi * efreq * dt)
                    sig_l += v * (1.0 - epan)
                    sig_r += v * epan
                    keep.append((st_t, ekind, efreq, edec, epan))
            active = keep

        sig_l = max(-0.95, min(0.95, sig_l * norm_scale * env))
        sig_r = max(-0.95, min(0.95, sig_r * norm_scale * env))
        frames.extend(struct.pack("<hh", int(sig_l * 32767), int(sig_r * 32767)))

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(frames))
    return layers


def _synth_foley_wav(wav_path: Path, prompt: str, preset: str, duration: int = 10) -> list[str]:
    """Synthesize a distinct stereo foley soundscape. Custom user text overrides the pulldown preset."""
    import math
    import random
    import struct
    import wave

    sr = 22050
    dur = max(4, min(30, int(duration or 10)))
    n = sr * dur
    mode = (preset or "space_adventure").strip().lower()
    clean_prompt = " ".join(str(prompt or "").strip().lower().split())

    # Custom text overrides the pulldown whenever mode=="custom" OR user typed non-stock custom text
    if mode == "spaceship_voices":
        return _synth_custom_text_foley_wav(wav_path, prompt or "a low spaceship hum and distant voices in background", dur)
    if mode.startswith(("story_", "lib_")):
        eff_p = prompt.strip()
        if not eff_p and mode.startswith("lib_"):
            found_lib = next((x for x in _sfx_library_load() if x.get("id") == mode), None)
            if found_lib:
                eff_p = str(found_lib.get("prompt") or "")
        return _synth_custom_text_foley_wav(wav_path, eff_p or mode.replace("_", " "), dur)
    stock_set = _STOCK_FOLEY_PROMPTS.get(mode, set())
    if mode == "custom" or (clean_prompt and mode not in ("silent", "none", "mute") and clean_prompt not in stock_set):
        return _synth_custom_text_foley_wav(wav_path, prompt, dur)

    if mode in ("silent", "none", "mute"):
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(bytes(n * 4))
        return ["silent"]
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
        elif mode == "soft_rain_room":
            # Exact same warm stereo rain as rainy_home, slightly muffled and much lower volume (zero glass taps, zero sine tones/beeps)
            nl, nr = rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0)
            lp1_l = lp1_l * 0.80 + nl * 0.20
            lp1_r = lp1_r * 0.80 + nr * 0.20
            sig_l += lp1_l * 0.095
            sig_r += lp1_r * 0.095
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
    return [mode]


def _synth_score_wav(wav_path: Path, mood: str, duration: int = 12):
    """Synthesize a distinctly orchestrated stereo score preview per mood (tempo, rhythm, instruments, and harmony)."""
    import math
    import struct
    import wave

    sr = 22050
    dur = max(6, min(30, int(duration or 12)))
    n = sr * dur
    m = (mood or "wonder").strip().lower()
    if m in ("none", "silent", "mute"):
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(bytes(n * 4))
        return
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
            wonder_chords = [(130.81, 261.63, 329.63, 392.00, 493.88), (110.00, 220.00, 261.63, 329.63, 392.00), (87.31, 174.61, 220.00, 261.63, 329.63), (98.00, 196.00, 246.94, 293.66, 392.00)]
            clen = dur / len(wonder_chords)
            ci = min(len(wonder_chords) - 1, int(t / clen))
            ct = t - ci * clen
            c_env = min(1.0, ct / 0.45) * min(1.0, (clen - ct) / 0.45)
            ch5 = wonder_chords[ci]
            for idx, f in enumerate(ch5):
                w = 0.14 if idx == 0 else 0.085
                sig_l += w * c_env * math.sin(2 * math.pi * f * t)
                sig_r += w * c_env * math.sin(2 * math.pi * (f * 1.003) * t)
            arp_step = int(t * 2.5)
            arp_t = (t * 2.5) - arp_step
            arp_f = ch5[1 + (arp_step % (len(ch5) - 1))] * 2.0
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
    cur: dict[str, Any] = {}
    if sd_path.is_file():
        try:
            cur = json.loads(sd_path.read_text(encoding="utf-8")) or {}
        except Exception:
            cur = {}
    if r.body.get("sfx_mode"):
        cur["sfx_mode"] = str(r.body["sfx_mode"]).strip()
    if isinstance(r.body.get("foley"), dict):
        raw_foley = cur.get("foley")
        cur["foley"] = {**(raw_foley if isinstance(raw_foley, dict) else {}), **r.body["foley"]}
    if isinstance(r.body.get("score"), dict):
        raw_score = cur.get("score")
        cur["score"] = {**(raw_score if isinstance(raw_score, dict) else {}), **r.body["score"]}
    if isinstance(r.body.get("scenes"), dict):
        raw_sc = cur.get("scenes")
        sc_map: dict[str, Any] = dict(raw_sc) if isinstance(raw_sc, dict) else {}
        for sid, sinfo in r.body["scenes"].items():
            if isinstance(sinfo, dict):
                raw_s = sc_map.get(str(sid))
                sc_map[str(sid)] = {**(raw_s if isinstance(raw_s, dict) else {}), **sinfo}
        cur["scenes"] = sc_map
    sd_path.write_text(json.dumps(cur, indent=2), encoding="utf-8")
    return {"status": "ok", "saved": cur}


@route("POST", "/api/v2_sound_design_render")
def _v2_sound_design_render(r: Request):
    """Render or upload Step 16 master Foley/Score OR a specific scene's Foley WAV."""
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
        from studio_app import upload_validation

        filename = str(r.body.get("filename") or f"{sub}.wav").strip()
        raw, _audio_ext = upload_validation.decode_verified_base64(b64, kind="audio", min_bytes=64)
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
                    subprocess.run([afconvert_bin, "-f", "WAVE", "-d", "LEI16@22050", str(tmp_in), str(wav_path)], stdin=subprocess.DEVNULL, check=True, timeout=30)
                elif ffmpeg_bin:
                    subprocess.run([ffmpeg_bin, "-y", "-i", str(tmp_in), str(wav_path)], stdin=subprocess.DEVNULL, check=True, timeout=30)
                else:
                    wav_path.write_bytes(raw)
            finally:
                tmp_in.unlink(missing_ok=True)
        return {"status": "ok", "kind": kind, "audio_url": rel_url, "source": filename}

    prompt = str(r.body.get("prompt") or "").strip()
    duration = int(r.body.get("duration") or (10 if kind == "foley" else 12))
    synth_layers: list[str] = []
    if kind == "foley":
        preset = str(r.body.get("preset") or "space_adventure").strip()
        synth_layers = _synth_foley_wav(wav_path, prompt, preset, duration)
    else:
        mood = str(r.body.get("mood") or "wonder").strip()
        _synth_score_wav(wav_path, mood, duration)

    # Save settings alongside render
    sd_path = pd / "sound_design_v2.json"
    cur: dict[str, Any] = {}
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
    return {"status": "ok", "kind": kind, "scene": scene_id, "audio_url": rel_url, "duration": duration, "layers": synth_layers}


SFX_LIBRARY_DIR = PROJECTS / "characters" / "_sfx_library"


def _sfx_library_load() -> list[dict[str, str]]:
    """Load reusable cross-story SFX presets saved by the user."""
    lib_file = SFX_LIBRARY_DIR / "presets.json"
    if lib_file.is_file():
        try:
            data = json.loads(lib_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict) and x.get("id") and x.get("prompt")]
        except Exception as e:
            log.debug("sfx library load failed: %s", e)
    return []


def _sfx_library_save(label: str, prompt: str, source_project: str = "") -> dict[str, str]:
    """Save or update a reusable cross-story SFX preset in the shared library."""
    clean_lbl = str(label or "").strip()[:60]
    clean_prompt = str(prompt or "").strip()[:400]
    if not clean_prompt:
        raise PlanError("Enter an SFX description first.")
    if not clean_lbl:
        clean_lbl = clean_prompt[:36].rstrip(" ,.;:")
    safe_id = "lib_" + ("".join(c if c.isalnum() else "_" for c in clean_lbl.lower()).strip("_")[:28] or "custom")
    entry = {
        "id": safe_id,
        "label": clean_lbl,
        "prompt": clean_prompt,
        "group": "Reusable Library",
        "source_project": source_project,
    }
    SFX_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    items = [x for x in _sfx_library_load() if x.get("id") != safe_id]
    items.insert(0, entry)
    (SFX_LIBRARY_DIR / "presets.json").write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    return entry


def _auto_scene_sfx_profile(heading: str, hint: str) -> tuple[str, str, str]:
    """Derive (preset_id, sfx_cue, score_mood) dynamically from a scene's actual heading & action."""
    low = (heading + " " + hint).lower()
    if any(w in low for w in ("launch", "blast", "liftoff", "ignition", "thruster", "rocket")):
        return "action_launch", "Rockets burning, spaceship hull shaking, heavy ignition rumble", "epic"
    if any(w in low for w in ("tavern", "inn", "hearth", "fireplace", "campfire", "pub", "feast")):
        return "story_hearth", "Crackling warm fireplace, soft distant voices murmuring, cozy wooden room", "cozy"
    if any(w in low for w in ("ocean", "sea", "ship deck", "harbor", "beach", "waves", "surf", "pirate", "sail")):
        return "story_ocean", "Rolling ocean waves, gentle sea breeze, distant gulls", "wonder"
    if any(w in low for w in ("spaceship", "starship", "cockpit", "bridge", "airlock", "space station", "orbit")):
        return "spaceship_voices", "A low spaceship hum and distant voices in background", "wonder"
    if any(w in low for w in ("ring", "ice", "geyser", "crater", "titan", "enceladus", "saturn", "blizzard", "glacier")):
        return "cosmic_storm", "Atmospheric wind gusts, shimmering ice particles, planetary rumble", "mysterious"
    if any(w in low for w in ("rain", "storm", "thunder")):
        return "soft_rain_room", "Subtle muffled distant rain outside a quiet cozy room, gentle soft indoor room tone", "cozy"
    if any(w in low for w in ("forest", "woods", "meadow", "park", "garden", "trail", "jungle", "tree", "river", "stream")):
        return "forest_nature", "Gentle breeze through trees, soft distant birds and quiet woodland air", "playful"
    if any(w in low for w in ("market", "street", "alley", "crowd", "village", "town", "station", "hall", "plaza")):
        return "story_crowd", "Soft distant crowd voices murmuring, occasional footsteps, natural open ambiance", "wonder"
    if any(w in low for w in ("living room", "kitchen", "bedroom", "home", "house", "library", "study", "office", "attic")):
        return "story_quiet_room", "Quiet cozy indoor room tone, soft distant ambient air, subtle wood creaks", "cozy"
    if heading.strip().upper().startswith("EXT."):
        return "forest_nature", "Gentle outdoor breeze and soft natural open air", "wonder"
    return "story_quiet_room", "Quiet indoor room ambiance, subtle warm air", "cozy"


def _auto_scene_sfx_cue(heading: str, hint: str) -> str:
    """Derive the default Step 16 scene SFX cue description from the scene's actual setting."""
    return _auto_scene_sfx_profile(heading, hint)[1]


def build_story_sfx_presets(pd: Path, slug: str) -> list[dict[str, str]]:
    """Build dynamic Step 16 SFX presets determined from the current story + reusable cross-story library."""
    presets: list[dict[str, str]] = [
        {"id": "custom", "label": "✏️ Custom (Override with Text)", "prompt": "", "group": "Core"},
        {"id": "silent", "label": "🔇 Silent (No SFX)", "prompt": "Silent (no ambient SFX or foley).", "group": "Core"},
    ]
    seen_ids: set[str] = {"custom", "silent"}
    seen_prompts: set[str] = set()

    def _add(pid: str, label: str, prompt: str, group: str) -> None:
        norm_p = " ".join(prompt.strip().lower().split())
        if pid in seen_ids or (norm_p and norm_p in seen_prompts):
            return
        seen_ids.add(pid)
        if norm_p:
            seen_prompts.add(norm_p)
        presets.append({"id": pid, "label": label, "prompt": prompt, "group": group})

    # 1. Story-specific presets derived from THIS book's actual screenplay scenes & locations
    sp_dir = pd / "screenplay"
    story_buckets: dict[str, tuple[str, str]] = {}  # preset_id -> (label, prompt)
    loc_names: list[str] = []
    if sp_dir.is_dir():
        for sp_file in sorted(sp_dir.glob("scene-*.json")):
            try:
                sc = json.loads(sp_file.read_text(encoding="utf-8")) or {}
            except Exception as e:
                log.debug("skipping unreadable scene %s in build_story_sfx_presets: %s", sp_file.name, e)
                continue
            heading = str(sc.get("heading") or "").strip()
            actions = [str(el.get("text") or "").strip() for el in (sc.get("elements") or []) if isinstance(el, dict) and el.get("type") == "action"]
            hint = (" ".join(actions))[:200]
            pid, cue, _mood = _auto_scene_sfx_profile(heading, hint)
            # Clean readable location name from heading (e.g. "INT. COZY TAVERN - NIGHT" -> "Cozy Tavern")
            loc_lbl = heading
            for pfx in ("INT./EXT.", "EXT./INT.", "INT.", "EXT."):
                if loc_lbl.upper().startswith(pfx):
                    loc_lbl = loc_lbl[len(pfx):].strip()
                    break
            if " - " in loc_lbl:
                loc_lbl = loc_lbl.split(" - ", 1)[0].strip()
            loc_title = loc_lbl.title()[:32] if loc_lbl else pid.replace("_", " ").title()
            if loc_title and loc_title.lower() not in [x.lower() for x in loc_names]:
                loc_names.append(loc_title)
            if pid not in story_buckets:
                story_buckets[pid] = (f"📖 {loc_title}", cue)

    # Also inspect saved per-scene custom cues in sound_design_v2.json so user's story cues are reusable across scenes
    sd_path = pd / "sound_design_v2.json"
    if sd_path.is_file():
        try:
            sd = json.loads(sd_path.read_text(encoding="utf-8")) or {}
            for _sid, sinfo in (sd.get("scenes") or {}).items():
                if isinstance(sinfo, dict):
                    c_txt = str(sinfo.get("sfx_cue") or "").strip()
                    c_pre = str(sinfo.get("sfx_preset") or "").strip()
                    if c_txt and c_pre and c_pre not in ("custom", "silent") and c_pre not in story_buckets:
                        story_buckets[c_pre] = (f"📖 {c_txt[:34]}", c_txt)
        except Exception as e:
            log.debug("sound_design_v2.json read for presets failed: %s", e)

    for pid, (lbl, cue) in story_buckets.items():
        _add(pid, lbl, cue, "This Story")

    # 2. User-saved Reusable SFX Library (shared across all stories!)
    for item in _sfx_library_load():
        _add(
            str(item["id"]),
            f"📚 {item.get('label') or item['id']}",
            str(item["prompt"]),
            "Reusable Library",
        )

    # 3. Genre-neutral universal fallbacks (always useful for any story; no forced space-only presets)
    _add("soft_rain_room", "Soft Distant Rain & Quiet Room", "Subtle muffled distant rain outside a quiet cozy room (not hitting the window), gentle soft indoor room tone.", "Universal")
    _add("rainy_home", "Rain on Window & Cozy Room", "Steady rain pattering on a living room window, individual droplets on glass, and soft distant thunder.", "Universal")
    _add("forest_nature", "Quiet Night & Nature Breeze", "Gentle evening breeze with rhythmic distant night crickets and quiet outdoor air.", "Universal")
    _add("story_hearth", "Cozy Fireplace & Distant Voices", "Crackling warm fireplace, soft distant voices murmuring, cozy wooden room.", "Universal")
    return presets


@route("POST", "/api/v2_sound_preset_save")
def _v2_sound_preset_save(r: Request):
    """Save a custom SFX preset to the reusable cross-story SFX library."""
    slug = str(r.body.get("project") or "").strip()
    label = str(r.body.get("label") or "").strip()
    prompt = str(r.body.get("prompt") or "").strip()
    saved = _sfx_library_save(label, prompt, source_project=slug)
    presets = build_story_sfx_presets(pdir(slug, "book"), slug) if slug else []
    return {"status": "ok", "saved": saved, "presets": presets}


@route("POST", "/api/v2_sound_sfx_propagate")
def _v2_sound_sfx_propagate(r: Request):
    """Save a scene's SFX (cue, preset, score mood, and WAV audio) and propagate it to every scene
    that shares the same SFX description."""
    slug = str(r.body.get("project") or "").strip()
    source_scene = "".join(c for c in str(r.body.get("source_scene") or "").strip() if c.isalnum() or c in "-_")
    if not slug or not source_scene:
        raise PlanError("project and source_scene are required")

    sfx_cue = str(r.body.get("sfx_cue") if r.body.get("sfx_cue") is not None else "").strip()
    has_match_cue = "match_cue" in r.body and r.body.get("match_cue") is not None
    match_cue = str(r.body.get("match_cue") if has_match_cue else sfx_cue).strip()
    sfx_preset = str(r.body.get("sfx_preset") or "space_adventure").strip()
    score_mood = str(r.body.get("score_mood") or "").strip()
    duration = int(r.body.get("duration") or 8)
    render_source = bool(r.body.get("render_source", False))

    def _norm(s: str) -> str:
        return " ".join(str(s or "").strip().lower().split())

    norm_match = _norm(match_cue)
    norm_sfx = _norm(sfx_cue)
    match_keys = {k for k in (norm_match, norm_sfx) if k}
    match_empty = (norm_match == "" and norm_sfx == "")

    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    sd_path = pd / "sound_design_v2.json"
    cur: dict[str, Any] = {}
    if sd_path.is_file():
        try:
            cur = json.loads(sd_path.read_text(encoding="utf-8")) or {}
        except Exception:
            cur = {}
    raw_sc = cur.get("scenes")
    sc_map: dict[str, Any] = dict(raw_sc) if isinstance(raw_sc, dict) else {}

    # Discover all scenes in screenplay and find every scene sharing the same SFX description
    matched_scenes: list[str] = [source_scene]
    sp_dir = pd / "screenplay"
    if sp_dir.is_dir():
        for sp_file in sorted(sp_dir.glob("scene-*.json")):
            try:
                sc = json.loads(sp_file.read_text(encoding="utf-8")) or {}
            except Exception as e:
                log.debug("skipping unreadable scene %s: %s", sp_file.name, e)
                continue
            sc_id = str(sc.get("scene") or sp_file.stem.replace("scene-", ""))
            if sc_id in matched_scenes:
                continue
            heading = str(sc.get("heading") or "")
            actions = [str(el.get("text") or "").strip() for el in (sc.get("elements") or []) if isinstance(el, dict) and el.get("type") == "action"]
            hint = (" ".join(actions))[:180]
            raw_ov = sc_map.get(sc_id)
            ov: dict[str, Any] = raw_ov if isinstance(raw_ov, dict) else {}
            eff_cue = str(ov["sfx_cue"]) if "sfx_cue" in ov else _auto_scene_sfx_cue(heading, hint)
            eff_norm = _norm(eff_cue)
            if (match_empty and eff_norm == "") or (match_keys and eff_norm in match_keys):
                matched_scenes.append(sc_id)

    # Ensure source WAV exists (render once if missing or if preset/text was changed before propagating)
    foley_dir = pd / "audio" / "foley"
    foley_dir.mkdir(parents=True, exist_ok=True)
    src_wav = foley_dir / f"scene_{source_scene}.wav"
    if render_source or not (src_wav.is_file() and src_wav.stat().st_size > 100):
        _synth_foley_wav(src_wav, sfx_cue, sfx_preset, duration)

    audio_urls: dict[str, str] = {}
    for sid in matched_scenes:
        raw_prev = sc_map.get(sid)
        prev: dict[str, Any] = dict(raw_prev) if isinstance(raw_prev, dict) else {}
        prev["sfx_cue"] = sfx_cue
        prev["sfx_preset"] = sfx_preset
        if score_mood:
            prev["score_mood"] = score_mood
        sc_map[sid] = prev

        dest_wav = foley_dir / f"scene_{sid}.wav"
        if sid != source_scene and src_wav.is_file() and src_wav.stat().st_size > 100:
            shutil.copyfile(src_wav, dest_wav)
        if dest_wav.is_file() and dest_wav.stat().st_size > 100:
            audio_urls[sid] = f"/file/{slug}/audio/foley/scene_{sid}.wav"

    cur["scenes"] = sc_map
    sd_path.write_text(json.dumps(cur, indent=2), encoding="utf-8")
    return {
        "status": "ok",
        "source_scene": source_scene,
        "updated_scenes": matched_scenes,
        "count": len(matched_scenes),
        "sfx_cue": sfx_cue,
        "sfx_preset": sfx_preset,
        "score_mood": score_mood,
        "audio_urls": audio_urls,
    }


def _inspect_keyframe_physics(png_path: Path, shot_prompt: str, api_key: str) -> dict:
    """Use Gemini Vision to inspect a generated keyframe for solid-object clipping, interpenetration, floating/gravity errors, or fused anatomy."""
    import base64
    import urllib.request

    if not api_key or not png_path.is_file() or png_path.stat().st_size < 200:
        return {"passed": True, "issues": []}

    qa_prompt = (
        "You are a strict VFX & Animation Physics Supervisor inspecting a film storyboard keyframe.\n"
        "Inspect the image carefully for ANY violation of solid-object physics:\n"
        "1. Solid objects passing through, clipping into, or intersecting other solid objects (arms, hands, legs, heads, dog tails, toys, furniture, chairs, walls, rugs, doors).\n"
        "2. Fused or merged anatomy/objects (toys merged into arms/hands, extra limbs, duplicate tails, deformed fingers/paws).\n"
        "3. Gravity / contact violations (people, dogs, furniture, or props floating above the floor/rug without support, unless explicitly in zero-gravity space).\n"
        "Ignore intentional ghosts/holograms if mentioned in the prompt.\n"
        f"Shot context: {shot_prompt[:300]}\n\n"
        'Reply ONLY with strict JSON: {"passed": true, "issues": []} or {"passed": false, "issues": ["short specific description of each physics/clipping error"]}.'
    )
    b64 = base64.b64encode(png_path.read_bytes()).decode("ascii")
    payload = json.dumps({
        "contents": [{
            "parts": [
                {"inlineData": {"mimeType": "image/png", "data": b64}},
                {"text": qa_prompt},
            ]
        }],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }).encode("utf-8")

    for model_name in ("gemini-2.5-flash", "gemini-2.0-flash"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for cand in data.get("candidates") or []:
                for part in (cand.get("content") or {}).get("parts") or []:
                    txt = (part.get("text") or "").strip()
                    if txt:
                        parsed = json.loads(txt)
                        issues = [str(x).strip() for x in (parsed.get("issues") or []) if str(x).strip()]
                        return {"passed": bool(parsed.get("passed", not issues)), "issues": issues}
        except Exception as e:
            log.debug("keyframe physics check failed on %s: %s", model_name, e)
            continue
    return {"passed": True, "issues": []}


def _inspect_keyframe_local_qa(png_path: Path) -> dict[str, Any]:
    """Local visual QA fallback checking black frame / corrupt image when running offline without Gemini Vision."""
    from qa.visual_qa import _is_frame_black

    if not png_path.is_file() or png_path.stat().st_size < 100:
        return {"passed": False, "issues": ["Generated image file is missing or empty"]}
    if _is_frame_black(png_path):
        return {"passed": False, "issues": ["Black frame detected in generated keyframe"]}
    return {"passed": True, "issues": []}


def _synthesize_local_preview_png(prompt: str, out_png: Path, aspect_ratio: str = "16:9", ref_images: list[Path] | None = None) -> str:
    """Deterministic local PIL storyboard frame synthesizer when sd-cli/ComfyUI binaries are not running on the host."""
    import hashlib
    from PIL import Image, ImageDraw

    w, h = (768, 768) if aspect_ratio == "1:1" else ((576, 1024) if aspect_ratio == "9:16" else (1024, 576))
    digest = hashlib.sha256(prompt.encode("utf-8")).digest()
    c1 = (30 + digest[0] % 80, 45 + digest[1] % 80, 75 + digest[2] % 95)
    c2 = (80 + digest[3] % 90, 60 + digest[4] % 90, 110 + digest[5] % 90)
    img = Image.new("RGB", (w, h), c1)
    draw = ImageDraw.Draw(img)
    for y in range(0, h, 4):
        t = y / float(max(1, h - 1))
        r_c = int(c1[0] * (1 - t) + c2[0] * t)
        g_c = int(c1[1] * (1 - t) + c2[1] * t)
        b_c = int(c1[2] * (1 - t) + c2[2] * t)
        draw.rectangle([0, y, w, min(h, y + 4)], fill=(r_c, g_c, b_c))

    # Overlay reference thumbnail if provided
    for idx, rp in enumerate((ref_images or [])[:2]):
        try:
            if rp and rp.is_file():
                with Image.open(rp) as rim:
                    thumb = rim.convert("RGB").resize((96, 96))
                    img.paste(thumb, (24 + idx * 108, 24))
        except (OSError, ValueError):
            continue

    draw.rectangle([24, h - 110, w - 24, h - 24], fill=(15, 23, 42))
    short = " ".join(prompt.split())[:110]
    draw.text((38, h - 85), f"LOCAL GPU STORYBOARD · {aspect_ratio}", fill=(245, 158, 11))
    draw.text((38, h - 60), short, fill=(248, 250, 252))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png, format="PNG")
    return "local_storyboard_synth"


def _inspect_keyframe_free_first(
    png_path: Path,
    prompt: str,
    req_engine: str,
    api_key: str,
    ref_image: Path | None = None,
) -> dict[str, Any]:
    """Run 100% free-first visual QA: local sanity -> free Ollama Vision QA -> Gemini ONLY if engine=='gemini'."""
    from studio_app import local_vision_qa

    sanity = _inspect_keyframe_local_qa(png_path)
    if not sanity.get("passed"):
        return {**sanity, "engine": "local_sanity"}

    # Always prefer free local Ollama Vision QA when running locally or in auto mode
    if req_engine != "gemini":
        ollama_qa = local_vision_qa.inspect_keyframe_with_ollama(png_path, prompt, ref_image=ref_image)
        if ollama_qa is not None:
            return ollama_qa
        return {**sanity, "engine": "local_sanity"}

    # Paid Gemini Vision QA ONLY when user explicitly chose engine="gemini"
    if api_key:
        gqa = _inspect_keyframe_physics(png_path, prompt, api_key)
        return {**gqa, "engine": "gemini_vision"}
    return {**sanity, "engine": "local_sanity"}


def _try_comfyui_image(
    prompt: str,
    out_png: Path,
    aspect_ratio: str = "16:9",
    ref_images: list[Path] | None = None,
    view: str = "",
    angle_move: str = "",
    *,
    seed: int = -1,
    init_strength: float | None = None,
    init_image: Path | None = None,
    require_ref: bool = False,
    extra_negative: str = "",
    single_subject: bool | None = None,
) -> str:
    """Run ComfyUI locally: `apps/angles` for angle shifts, GGUF FLUX.2 Klein (multi-ref) / Z-Image Turbo, or `apps/z-image`."""
    import shutil
    import tempfile
    from local_runners.comfyui_gguf_workflows import (
        GGUF_MODEL_SPECS,
        build_flux2_klein_gguf_workflow,
        build_z_image_gguf_workflow,
        compute_flux2_dimensions,
        ready_gguf_models,
        resolve_gguf_model_files,
    )
    from local_runners.comfyui_lifecycle import ensure_comfyui_started
    from local_runners.comfyui_runner import ComfyUIRunner
    from local_runners.sd_cli_runner import compute_dimensions

    runner = ComfyUIRunner()
    if not runner.is_installed():
        boot = ensure_comfyui_started(root=ROOT, base_url=getattr(runner, "base_url", None), wait_ready_s=45.0)
        if not boot.get("ready") and not runner.is_installed():
            return ""
    models_root = ROOT / "models"

    def _app_ready(app_name: str) -> tuple[Path, dict[str, Any]] | None:
        ad = ROOT / "apps" / app_name
        if not (ad / "app.json").is_file():
            return None
        mf = json.loads((ad / "app.json").read_text(encoding="utf-8"))
        for m in mf.get("models") or []:
            fname = Path(str(m.get("file") or "")).name
            mdir = str(m.get("dir") or "")
            if fname and not (models_root / mdir / fname).is_file():
                return None
        return ad, mf

    # 1. Identity-locked multi-angle rotation via Qwen-Image-Edit for Step 10 views OR Step 17 camera-angle changes
    valid_refs = [p for p in (ref_images or []) if p and p.is_file() and p.stat().st_size > 100]
    if valid_refs and (angle_move or view in ("three_quarter", "profile")):
        ready = _app_ready("angles")
        if ready is not None:
            ad, _ = ready
            move_val = angle_move or (
                "\u5c06\u955c\u5934\u5411\u5de6\u65cb\u8f6c45\u5ea6 Rotate the camera 45 degrees to the left."
                if view == "three_quarter"
                else "\u5c06\u955c\u5934\u5411\u5de6\u65cb\u8f6c45\u5ea6 Rotate the camera 90 degrees to a strict side profile."
            )
            with tempfile.TemporaryDirectory(prefix="studio-comfy-angle-") as tmp_:
                res = runner.run({
                    "app_dir": str(ad),
                    "values": {"image": str(valid_refs[0]), "move": move_val, "details": prompt[:320], "seed": seed},
                    "output_dir": tmp_,
                })
                produced = Path(str(res.get("output_path") or ""))
                if produced.is_file() and produced.stat().st_size > 100:
                    out_png.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(produced, out_png)
                    return "comfyui:angles"
        if angle_move:
            # Do not fall through to non-angle generation when an explicit angle shift was requested
            return ""

    # 2. Local GGUF workflows (FLUX.2 Klein multi-ref OR Z-Image Turbo text-to-image) via ComfyUI-GGUF
    gguf_ready = ready_gguf_models(models_root=models_root, require_ref_support=bool(valid_refs))
    if gguf_ready and runner.has_node("UnetLoaderGGUF") and runner.has_node("CLIPLoaderGGUF"):
        chosen = gguf_ready[0]
        files = resolve_gguf_model_files(chosen, models_root=models_root)
        spec = GGUF_MODEL_SPECS[chosen]
        if files is not None:
            w, h = compute_flux2_dimensions(aspect_ratio)
            is_single = (aspect_ratio == "1:1") if single_subject is None else bool(single_subject)
            neg_prompt = (
                "multiple views, turnaround sheet, character sheet, grid, collage, split screen, multiple people, duplicate figure, text, watermark"
                if is_single
                else "multiple views, turnaround sheet, character sheet, grid, collage, split screen, text, watermark"
            )
            if extra_negative.strip():
                neg_prompt = f"{neg_prompt}, {extra_negative.strip()}"

            uploaded_refs: list[str] = []
            if valid_refs and spec.get("supports_ref_images"):
                for rp in valid_refs[:4]:
                    uploaded_refs.append(runner.upload_image(rp))

            effective_init = (
                init_image
                if (init_image and init_image.is_file() and init_image.stat().st_size > 100)
                else (valid_refs[0] if (valid_refs and init_strength is not None) else None)
            )
            uploaded_init: str | None = None
            eff_denoise = 1.0
            # For 4-step FLUX.2 Klein with ReferenceMultiLatent, high-strength style conversion (>= 0.55)
            # works far better starting from EmptyFlux2LatentImage (full 4 steps) instead of double-locking
            # the raw photo latent with only 2 partial denoise steps. Tight edits (< 0.55) keep VAEEncode init.
            same_as_ref = bool(
                uploaded_refs
                and effective_init is not None
                and valid_refs
                and effective_init.resolve() == valid_refs[0].resolve()
            )
            use_init_latent = (
                init_strength is not None
                and effective_init is not None
                and not (spec["kind"] == "flux2" and same_as_ref and float(init_strength) >= 0.55)
            )
            if use_init_latent and effective_init is not None and init_strength is not None:
                uploaded_init = runner.upload_image(effective_init)
                eff_denoise = max(0.05, min(1.0, float(init_strength)))

            if spec["kind"] == "flux2":
                wf = build_flux2_klein_gguf_workflow(
                    prompt=prompt,
                    unet_name=files["unet"],
                    clip_name=files["clip"],
                    vae_name=files["vae"],
                    width=w,
                    height=h,
                    steps=int(spec["steps"]),
                    cfg=float(spec["cfg"]),
                    seed=seed,
                    ref_image_names=uploaded_refs,
                    init_image_name=uploaded_init,
                    denoise=eff_denoise,
                    negative_prompt=neg_prompt,
                )
            else:
                wf = build_z_image_gguf_workflow(
                    prompt=prompt,
                    unet_name=files["unet"],
                    clip_name=files["clip"],
                    vae_name=files["vae"],
                    width=w,
                    height=h,
                    steps=int(spec["steps"]),
                    cfg=float(spec["cfg"]),
                    seed=seed,
                    init_image_name=uploaded_init,
                    denoise=eff_denoise,
                )

            with tempfile.TemporaryDirectory(prefix="studio-comfy-gguf-") as tmp_:
                res = runner.run_workflow(
                    wf,
                    output_dir=Path(tmp_),
                    app_id=f"gguf-{chosen}",
                    model_cache_key=f"{chosen}:{files['unet']}:{files['clip']}:{files['vae']}",
                    min_vram_gb=float(spec.get("vram_gb") or 6.0),
                    declared_nodes=["9"],
                )
                produced = Path(str(res.get("output_path") or ""))
                if produced.is_file() and produced.stat().st_size > 100:
                    out_png.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(produced, out_png)
                    return f"comfyui:{chosen}"

    if require_ref and valid_refs:
        # Never fall through to text-only z-image when reference images are required
        return ""

    # 3. Legacy safetensors `apps/z-image` text-to-image fallback
    ready_z = _app_ready("z-image")
    if ready_z is None:
        return ""
    app_dir, _ = ready_z
    w, h = compute_dimensions(1024, aspect_ratio)
    with tempfile.TemporaryDirectory(prefix="studio-comfy-") as tmp_:
        res = runner.run({
            "app_dir": str(app_dir),
            "values": {"prompt": prompt, "width": w, "height": h, "steps": 8, "seed": seed},
            "output_dir": tmp_,
        })
        produced = Path(str(res.get("output_path") or ""))
        if produced.is_file() and produced.stat().st_size > 100:
            out_png.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(produced, out_png)
            return "comfyui:z-image"
    return ""


def _try_sd_cli_image(
    prompt: str,
    out_png: Path,
    aspect_ratio: str = "16:9",
    model_id: str | None = None,
    ref_images: list[Path] | None = None,
    seed: int = -1,
    init_strength: float | None = None,
    init_image: Path | None = None,
    mask_image: Path | None = None,
    prefer_edit: bool = False,
    require_ref: bool = False,
    extra_negative: str = "",
    single_subject: bool | None = None,
) -> str:
    """Run local `sd-cli` with the best installed free model on disk (FLUX.1 Kontext Dev / FLUX.2 Klein 9B / 4B)."""
    from local_runners.sd_cli_runner import MODEL_CATALOG, SdCliRunner

    runner = SdCliRunner()
    if not runner.is_installed():
        return ""
    valid_refs = [p for p in (ref_images or []) if p and p.is_file() and p.stat().st_size > 100]
    chosen = (model_id or "").removeprefix("sd_cli:").strip()
    if not chosen:
        if valid_refs:
            try:
                ref_ready = runner.ready_models(require_ref_support=True, prefer_edit=prefer_edit)
            except TypeError:
                ref_ready = runner.ready_models(require_ref_support=True)
        else:
            ref_ready = []
        if require_ref and valid_refs and not ref_ready:
            return ""
        ready = ref_ready or runner.ready_models()
        if not ready:
            return ""
        chosen = ready[0]
    is_single = (aspect_ratio == "1:1") if single_subject is None else bool(single_subject)
    neg_prompt = (
        "multiple views, turnaround sheet, character sheet, grid, collage, split screen, multiple people, duplicate figure, text, watermark"
        if is_single
        else "multiple views, turnaround sheet, character sheet, grid, collage, split screen, text, watermark"
    )
    if extra_negative.strip():
        neg_prompt = f"{neg_prompt}, {extra_negative.strip()}"
    spec: dict[str, Any] = {
        "model": chosen,
        "prompt": prompt,
        "negative_prompt": neg_prompt,
        "aspect_ratio": aspect_ratio,
        "seed": seed,
        "output_path": str(out_png),
    }
    if valid_refs:
        spec["ref_images"] = [str(p) for p in valid_refs[:4]]
    effective_init = init_image if (init_image and init_image.is_file() and init_image.stat().st_size > 100) else (valid_refs[0] if valid_refs else None)
    entry_kind = str((MODEL_CATALOG.get(chosen) or {}).get("kind") or "")
    same_as_ref = bool(
        valid_refs
        and effective_init is not None
        and effective_init.resolve() == valid_refs[0].resolve()
    )
    # Match _try_comfyui_image: for 4-step FLUX.2 Klein (and FLUX.1 Kontext) with -r reference conditioning,
    # high-strength style conversion (>= 0.55) MUST start from pure noise (full steps) instead of double-locking
    # the raw photographic latent with -i + --strength (which leaves only ~2 denoise steps and outputs the raw photo).
    use_init_latent = (
        init_strength is not None
        and effective_init is not None
        and not (entry_kind in ("flux2", "flux_kontext") and same_as_ref and float(init_strength) >= 0.55)
    )
    if use_init_latent and effective_init is not None and init_strength is not None:
        spec["init_image"] = str(effective_init)
        spec["strength"] = float(init_strength)
    if mask_image is not None and mask_image.is_file() and mask_image.stat().st_size > 100:
        spec["mask_image"] = str(mask_image)
    res = runner.run(spec)
    if out_png.is_file() and out_png.stat().st_size > 100:
        return f"sd_cli:{res.get('model') or chosen}"
    return ""


def _render_keyframe_local_or_gemini(
    prompt: str,
    out_png: Path,
    aspect_ratio: str = "16:9",
    ref_images: list[Path] | None = None,
    engine: str = "auto",
    *,
    view: str = "",
    angle_move: str = "",
    seed: int = -1,
    init_strength: float | None = None,
    init_image: Path | None = None,
    mask_image: Path | None = None,
    prefer_edit: bool = False,
    require_ref: bool = False,
    bypass_cache: bool = False,
    extra_negative: str = "",
) -> str:
    """Route Step 10/17 image generation through Local-GPU runners first (ComfyUI -> sd-cli), then Gemini API, never caching placeholders."""
    import hashlib
    from local_runners.asset_cache import asset_cache_enabled, compute_cache_key, get_default_asset_cache
    import run_gemini_omni

    eng = str(engine or "auto").strip().lower()
    ref_fingerprints: list[str] = []
    for rp in (ref_images or []):
        if rp and rp.is_file():
            try:
                digest = hashlib.sha256(rp.read_bytes()).hexdigest()[:16]
                ref_fingerprints.append(f"{rp}:{digest}")
            except OSError:
                ref_fingerprints.append(str(rp))
    cache_inputs = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "engine": eng,
        "seed": seed,
        "init_strength": init_strength,
        "init_image": str(init_image) if init_image else "",
        "mask_image": str(mask_image) if mask_image else "",
        "angle_move": angle_move,
        "prefer_edit": prefer_edit,
        "refs": ref_fingerprints,
    }
    if asset_cache_enabled() and not bypass_cache:
        cache = get_default_asset_cache()
        ckey = compute_cache_key("v2_image_render", "1.0", cache_inputs, output_path=str(out_png))
        hit = cache.try_restore(ckey, out_png)
        if hit and hit.get("model") != "local_storyboard_synth" and out_png.is_file():
            return f"cache:{hit.get('model') or eng}"

    api_key = run_gemini_omni.get_gemini_api_key()
    prefer_local = eng not in ("gemini", "cloud")

    model_used = ""
    if prefer_local:
        def _run_comfy() -> str:
            try:
                return _try_comfyui_image(
                    prompt,
                    out_png,
                    aspect_ratio,
                    ref_images=ref_images,
                    view=view,
                    angle_move=angle_move,
                    seed=seed,
                    init_strength=init_strength,
                    init_image=init_image,
                    require_ref=require_ref,
                    extra_negative=extra_negative,
                    single_subject=(aspect_ratio == "1:1"),
                )
            except TypeError:
                return _try_comfyui_image(
                    prompt,
                    out_png,
                    aspect_ratio,
                    ref_images=ref_images,
                    view=view,
                    angle_move=angle_move,
                )

        def _run_sd() -> str:
            return _try_sd_cli_image(
                prompt,
                out_png,
                aspect_ratio,
                ref_images=ref_images,
                seed=seed,
                init_strength=init_strength,
                init_image=init_image,
                mask_image=mask_image,
                prefer_edit=prefer_edit,
                require_ref=require_ref,
                extra_negative=extra_negative,
                single_subject=(aspect_ratio == "1:1"),
            )

        # Route priority:
        # - Explicit angle_move or character rotation -> try ComfyUI `apps/angles` (Qwen-Image-Edit) first, then sd-cli Kontext/FLUX.2
        # - Reference images or native --mask -> try sd-cli first (if available), automatically falling back to ComfyUI GGUF FLUX.2 Klein multi-ref
        has_valid_refs = any(p and p.is_file() and p.stat().st_size > 100 for p in (ref_images or []))
        has_mask = bool(mask_image and mask_image.is_file() and mask_image.stat().st_size > 100)
        wants_comfy_angles = bool(angle_move or view in ("three_quarter", "profile")) and has_valid_refs and eng != "sd_cli"
        prefer_sd_for_refs = (has_valid_refs or has_mask) and not wants_comfy_angles and eng != "comfyui"
        attempts = (_run_sd, _run_comfy) if (eng == "sd_cli" or prefer_sd_for_refs) else (_run_comfy, _run_sd)
        sd_blocked_policy = False
        for fn in attempts:
            try:
                model_used = fn()
                if model_used:
                    break
            except Exception as e:
                if getattr(e, "winerror", None) == 4551 or "Application Control policy" in str(e):
                    sd_blocked_policy = True
                log.warning("local image runner %s failed: %s", fn.__name__, e)

        if not model_used:
            if api_key and eng == "auto":
                model_used = _render_keyframe_gemini(prompt, out_png, aspect_ratio=aspect_ratio, ref_images=ref_images)
            elif sd_blocked_policy:
                raise PlanError(
                    "Local sd-cli was blocked by Windows Application Control and the local ComfyUI engine could not be reached "
                    "at http://127.0.0.1:8188 (check .local_ai/ComfyUI/comfyui_autostart.log or restart Studio)."
                )
            else:
                model_used = _synthesize_local_preview_png(prompt, out_png, aspect_ratio=aspect_ratio, ref_images=ref_images)
    else:
        model_used = _render_keyframe_gemini(prompt, out_png, aspect_ratio=aspect_ratio, ref_images=ref_images)

    if asset_cache_enabled() and out_png.is_file() and model_used and model_used != "local_storyboard_synth":
        cache = get_default_asset_cache()
        ckey = compute_cache_key("v2_image_render", "1.0", cache_inputs, output_path=str(out_png))
        cache.store(ckey, out_png, tool_name="v2_image_render", model=model_used)
    return model_used


def _render_keyframe_gemini(prompt: str, out_png: Path, aspect_ratio: str = "16:9", ref_images: list[Path] | None = None) -> str:
    """Generate a storyboard keyframe or turnaround PNG using Gemini Image Generation, attaching existing character reference images for visual consistency."""
    import base64
    import urllib.error
    import urllib.request
    import run_gemini_omni

    api_key = run_gemini_omni.get_gemini_api_key()
    if not api_key:
        raise PlanError("Gemini API key is not configured. Save your GEMINI_API_KEY in Step 13 first.")

    valid_refs: list[bytes] = []
    for rp in (ref_images or [])[:4]:
        try:
            if rp and rp.is_file() and rp.stat().st_size > 100:
                valid_refs.append(rp.read_bytes())
        except OSError:
            continue

    ref_clause = (
        "- REFERENCE IDENTITY LOCK: Match the EXACT face, hair, eyes, skin tone, age, and body proportions of the character(s) shown in the attached reference image(s). Apply ONLY the requested camera angle, pose, or explicit wardrobe change.\n"
        if valid_refs else ""
    )
    frame_hint = "square 1:1 SINGLE standalone character portrait (ONLY ONE figure in frame, NO multi-view sheet, NO collage, NO split panels, NO duplicate figures)" if aspect_ratio == "1:1" else "widescreen 16:9 film storyboard keyframe"
    full_prompt = (
        f"Generate a single clean cinematic {frame_hint} with NO text, NO captions, NO watermarks.\n"
        "STRICT CONTINUITY & SOLID-OBJECT PHYSICS RULES:\n"
        f"{ref_clause}"
        "- SOLID-OBJECT PHYSICS & ANATOMICAL INTEGRITY (CRITICAL): Strictly obey real-world solid-object physics, gravity, and depth occlusion. "
        "NO solid object may ever pass through, clip into, intersect, or fuse with another solid object. "
        "Arms, hands, fingers, heads, legs, feet, dog paws, dog tails, stuffed toys, chairs, tables, rugs, walls, and doors must be cleanly separated with realistic physical contact shadows resting ON surfaces (never floating, never merging, never clipping through limbs or furniture — unless explicitly described as a ghost/hologram).\n"
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
        variants: list[tuple[int, Any]] = []
        if valid_refs:
            parts = [types.Part.from_bytes(data=b, mime_type="image/png") for b in valid_refs]
            parts.append(full_prompt)
            variants.append((len(valid_refs), parts))
        variants.append((0, full_prompt))

        for nrefs, contents_arg in variants:
            for m in models:
                try:
                    resp = client.models.generate_content(
                        model=m,
                        contents=contents_arg,
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
                            return f"{m}+ref({nrefs})" if nrefs else m
                except Exception as e:
                    last_err = e
                    continue

    rest_variants = []
    if valid_refs:
        rparts: list[dict[str, Any]] = [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(b).decode("ascii")}} for b in valid_refs]
        rparts.append({"text": full_prompt})
        rest_variants.append((len(valid_refs), rparts))
    rest_variants.append((0, [{"text": full_prompt}]))

    for nrefs, rparts in rest_variants:
        payload = json.dumps({
            "contents": [{"parts": rparts}],
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
                            return f"{m}+ref({nrefs})" if nrefs else m
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


def _load_project_cast_profiles(slug: str, pd: Path) -> list[dict[str, str]]:
    """Collect character names and descriptions for identity grouping and twin/non-twin checks."""
    import character_tokens

    chars: dict[str, dict[str, str]] = {}

    def _add(name: Any, desc: Any = "", prefer: bool = False) -> None:
        clean = str(name or "").strip()
        if not clean:
            return
        k = clean.lower()
        d = str(desc or "").strip()
        if k not in chars:
            chars[k] = {"name": clean, "desc": d}
        elif d and (prefer or not chars[k]["desc"]):
            chars[k]["desc"] = d

    for cb_file in (pd / f"{slug}.json", pd / "continuity.json"):
        if cb_file.is_file():
            try:
                cb = json.loads(cb_file.read_text(encoding="utf-8")) or {}
                for c in cb.get("characters") or []:
                    if isinstance(c, dict):
                        _add(c.get("name"), c.get("token") or c.get("description") or "")
                break
            except Exception as e:
                log.debug("continuity cast profile read failed (%s): %s", cb_file.name, e)
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
            log.debug("coverage cast profile read failed: %s", e)
    try:
        for ch in character_tokens.list_characters(slug) or []:
            if isinstance(ch, dict) and ch.get("name"):
                full_ch = character_tokens.load_character(slug, str(ch["name"])) or ch
                combined = ". ".join(
                    p.rstrip(". ")
                    for p in (
                        str(full_ch.get("visual_token") or full_ch.get("token") or "").strip(),
                        str(full_ch.get("description") or "").strip(),
                        str(full_ch.get("consistency_notes") or "").strip(),
                    )
                    if p
                )
                _add(ch["name"], combined, prefer=True)
    except Exception as e:
        log.debug("character_tokens cast profile read failed: %s", e)
    return list(chars.values())


def _find_character_turnaround_refs(
    pd: Path,
    char_name: str,
    prefer_outfit: str = "",
    exclude_path: Path | None = None,
    limit: int = 3,
    *,
    known_names: list[str] | None = None,
    overrides: dict[str, str] | None = None,
) -> list[Path]:
    """Find existing generated turnaround PNGs for a character and all same-canonical-identity variants."""
    import character_identity

    t_dir = pd / "assets" / "turnarounds"
    if not t_dir.is_dir():
        return []
    ov = overrides if overrides is not None else character_identity.load_identity_overrides(pd)
    refs = character_identity.find_canonical_character_refs(
        t_dir,
        char_name,
        prefer_outfit=prefer_outfit,
        exclude_path=exclude_path,
        known_names=known_names,
        overrides=ov,
        limit=limit,
    )
    return [p for p, _src in refs]


@route("POST", "/api/v2_keyframe_render")
def _v2_keyframe_render(r: Request):
    """Generate or upload a storyboard keyframe PNG in <project>/keyframes/<shot_id>.png."""

    slug = str(r.body.get("project") or "").strip()
    shot_id = "".join(c for c in str(r.body.get("id") or "").strip() if c.isalnum() or c in "-_")
    if not slug or not shot_id:
        raise PlanError("project and id are required")

    pd = pdir(slug, "book")
    kf_dir = pd / "keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)
    out_png = kf_dir / f"{shot_id}.png"
    rel_url = f"/file/{slug}/keyframes/{shot_id}.png"

    # Refuse to overwrite a locked keyframe
    meta_path = pd / "keyframes_v2.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            meta = {}
    if shot_id in (meta.get("locked") or []):
        raise PlanError(f"Keyframe {shot_id} is locked. Unlock it first before re-rolling or replacing it.")

    # Persist edited prompt if provided
    prompt = str(r.body.get("prompt") or "").strip()
    if prompt:
        prompts = dict(meta.get("prompts") or {})
        prompts[shot_id] = prompt
        meta["prompts"] = prompts
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    b64 = str(r.body.get("image_base64") or "").strip()
    if b64:
        from studio_app import upload_validation

        raw, _img_ext = upload_validation.decode_verified_base64(b64, kind="image", min_bytes=64)
        out_png.write_bytes(raw)
        return {"status": "ok", "id": shot_id, "image_url": rel_url, "model": "uploaded"}

    if not prompt:
        raise PlanError("prompt is required to generate a keyframe")

    if bool(r.body.get("async", False)):
        from studio_app import render_jobs

        sync_body = {k: v for k, v in r.body.items() if k != "async"}
        return render_jobs.submit_render_job(
            f"keyframe:{slug}:{shot_id}",
            lambda: _v2_keyframe_render(Request(query=r.query, body=sync_body)),
        )

    # Collect Step 10 character turnarounds, Step 08 cast photos, Step 11 set plate,
    # pinned Scene Anchor, and same-scene previous keyframe continuity using the shared Step 17 context builder.
    from studio_app import keyframe_context

    saved_prompts_map: dict[str, Any] = dict(meta.get("prompts") or {})
    raw_anchors = meta.get("anchors") or {}
    anchors_map: dict[str, str] = (
        {str(k): str(v) for k, v in raw_anchors.items() if str(k).strip() and str(v).strip()}
        if isinstance(raw_anchors, dict)
        else {}
    )
    sc_id = shot_id.split("-")[0] if "-" in shot_id else ""
    use_anchor = bool(r.body.get("use_anchor", True))
    anchor_shot_id = anchors_map.get(sc_id, "") if use_anchor else ""

    raw_strength = r.body.get("init_strength")
    user_strength: float | None = None
    if raw_strength is not None and str(raw_strength).strip().lower() not in ("", "auto", "none"):
        try:
            user_strength = float(raw_strength)
        except (TypeError, ValueError):
            user_strength = None

    fresh_seed = bool(r.body.get("fresh_seed", False))

    sl_data: dict[str, Any] = {}
    sl_path = pd / "shots" / "shotlist.json"
    if sl_path.is_file():
        try:
            sl_data = json.loads(sl_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            log.debug("shotlist.json read failed: %s", e)

    kf_ctx = keyframe_context.load_keyframe_project_context(slug, pd)
    ref_pack = keyframe_context.collect_render_references(
        kf_ctx,
        shot_id,
        prompt,
        sl_data,
        kf_dir,
        saved_prompts_map,
        anchor_shot_id=anchor_shot_id,
        user_strength=user_strength,
    )
    ref_imgs: list[Path] = ref_pack["ref_imgs"]
    init_image: Path | None = ref_pack["init_image"]
    init_strength: float | None = ref_pack["init_strength"]
    seed_to_use: int = -1 if fresh_seed else int(ref_pack["scene_seed"])
    prev_shot_ref: str = ref_pack["prev_shot_ref"]
    anchor_shot_ref: str = ref_pack["anchor_shot_ref"]
    continuity_mode: str = ref_pack["continuity_mode"]
    continuity_prefix: str = ref_pack["continuity_prefix"]
    ref_legend: str = ref_pack["ref_legend"]
    char_refs_used: list[dict[str, str]] = ref_pack["char_refs_used"]
    style_negatives: str = ref_pack["style_negatives"]

    # Optional Blender 3D true-scale blocking/depth guide lock (Step 17 spatial proportion lock)
    blender_guide_note = ""
    if bool(r.body.get("use_blender_guide", True)):
        from local_runners import blender_runner

        blk_png, _dep_png = blender_runner.find_existing_shot_guide(pd, shot_id)
        if blk_png is not None and blk_png not in ref_imgs:
            ref_imgs = [*ref_imgs, blk_png]
            blender_guide_note = (
                f"[3D SPATIAL SCALE LOCK: Image {len(ref_imgs)} is a true-scale 3D Blender blocking plate for this exact shot. "
                "Strictly preserve the relative heights, positions, camera perspective, and furniture placement shown in that 3D guide.] "
            )

    final_prompt = f"{ref_legend}{blender_guide_note}{continuity_prefix}{prompt}"
    # On interior shots mentioning rain/streaks/rivulets, collapse repeated rain-streak tokens
    # so CFG=1 models (FLUX.2 Klein) do NOT bleed droplets onto the camera lens, TV, or floor
    # and do NOT invent extra windows where hallways belong.
    if "DRY INDOOR ROOM & ARCHITECTURE LOCK" in continuity_prefix:
        final_prompt = re.sub(
            r"\bwith rain streaks running down its panes\b",
            "showing gray rainy overcast daylight outdoors",
            final_prompt,
            flags=re.IGNORECASE,
        )
        final_prompt = re.sub(
            r"\brain runs down the glass in steady rivulets[^.]*",
            "gray overcast rainy weather is visible outdoors beyond the existing windowpane while the room interior stays completely dry",
            final_prompt,
            flags=re.IGNORECASE,
        )
        final_prompt = re.sub(
            r"\brain[- ]streaked\b|\brain streaks\b|\bsteady rivulets\b",
            "overcast rainy",
            final_prompt,
            flags=re.IGNORECASE,
        )
    req_engine = str(r.body.get("engine") or "auto").strip().lower()
    use_edit_model = continuity_mode in ("same_angle", "incremental") or init_strength is not None
    suggested_angle_move = str(ref_pack.get("suggested_angle_move") or "") if continuity_mode == "scene_cut" else ""
    model_used = _render_keyframe_local_or_gemini(
        final_prompt,
        out_png,
        aspect_ratio=str(r.body.get("aspect_ratio") or "16:9"),
        ref_images=ref_imgs,
        engine=req_engine,
        angle_move=suggested_angle_move,
        seed=seed_to_use,
        init_strength=init_strength,
        init_image=init_image,
        prefer_edit=use_edit_model,
        bypass_cache=fresh_seed,
        extra_negative=style_negatives,
    )

    # Free-First Visual QA (local sanity -> free local Ollama Vision QA -> Gemini ONLY if engine=="gemini")
    import run_gemini_omni
    api_key = run_gemini_omni.get_gemini_api_key() if req_engine == "gemini" else ""
    qa_ref_img = init_image or (ref_imgs[0] if ref_imgs else None)
    qa = _inspect_keyframe_free_first(out_png, prompt, req_engine, api_key, ref_image=qa_ref_img)
    physics_repaired = False
    if not qa.get("passed") and qa.get("issues"):
        issues_str = "; ".join(qa["issues"][:4])
        repair_prompt = (
            f"PHYSICS REPAIR PASS: The first attached image has solid-object physics / clipping error(s): {issues_str}.\n"
            "Redraw this EXACT same shot with the exact same camera angle, room layout, lighting, character faces, and clothing, "
            "but COMPLETELY FIX every clipping, floating, or merged-object error listed above so all solid objects (arms, hands, heads, tails, toys, furniture, floor) "
            "rest naturally with proper physical contact and occlusion.\n\n"
            f"Original shot description: {prompt}"
        )
        try:
            repair_refs = [out_png] + [p for p in ref_imgs if p != out_png][:3]
            model_used = _render_keyframe_local_or_gemini(
                repair_prompt,
                out_png,
                aspect_ratio=str(r.body.get("aspect_ratio") or "16:9"),
                ref_images=repair_refs,
                engine=req_engine,
                seed=seed_to_use,
                init_strength=0.45,
                init_image=out_png,
                prefer_edit=True,
                extra_negative=style_negatives,
            )
            physics_repaired = True
            qa = _inspect_keyframe_free_first(out_png, prompt, req_engine, api_key, ref_image=qa_ref_img)
        except Exception as e:
            log.debug("physics repair pass failed: %s", e)

    return {
        "status": "ok",
        "id": shot_id,
        "image_url": rel_url,
        "model": model_used,
        "refs_used": len(ref_imgs),
        "char_refs_used": char_refs_used,
        "set_ref_used": ref_pack.get("set_ref_used"),
        "resolved_characters": ref_pack["resolved_characters"],
        "prev_shot_ref": prev_shot_ref,
        "anchor_shot_ref": anchor_shot_ref,
        "primary_ref_id": ref_pack["primary_ref_id"],
        "seed_used": seed_to_use,
        "init_strength_used": init_strength,
        "continuity_mode": continuity_mode,
        "qa_engine": qa.get("engine") or "local_sanity",
        "physics_passed": bool(qa.get("passed", True)),
        "physics_repaired": physics_repaired,
        "physics_issues": qa.get("issues") or [],
        "continuity_issues": qa.get("continuity_issues") or [],
    }


@route("POST", "/api/v2_keyframe_anchor")
def _v2_keyframe_anchor(r: Request):
    """Pin or clear a Scene Anchor (Master Plate) keyframe in keyframes_v2.json to eliminate chain drift."""
    slug = str(r.body.get("project") or "").strip()
    sc_id = "".join(c for c in str(r.body.get("scene") or "").strip() if c.isalnum() or c in "-_")
    shot_id = "".join(c for c in str(r.body.get("shot_id") or r.body.get("id") or "").strip() if c.isalnum() or c in "-_")
    if not slug or not sc_id:
        raise PlanError("project and scene are required")

    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    if shot_id:
        cand = pd / "keyframes" / f"{shot_id}.png"
        if not (cand.is_file() and cand.stat().st_size > 200):
            raise PlanError(f"Render keyframe {shot_id} first before pinning it as the Scene Anchor.")

    meta_path = pd / "keyframes_v2.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            meta = {}
    raw_anchors = meta.get("anchors")
    anchors: dict[str, str] = dict(raw_anchors) if isinstance(raw_anchors, dict) else {}
    if shot_id:
        anchors[sc_id] = shot_id
    else:
        anchors.pop(sc_id, None)
    meta["anchors"] = anchors
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"status": "ok", "scene": sc_id, "anchor_shot_id": anchors.get(sc_id, "")}


@route("POST", "/api/v2_keyframe_clone_edit")
def _v2_keyframe_clone_edit(r: Request):
    """Clone a previous shot or Scene Anchor into <shot_id>.png, optionally applying a low-strength targeted action edit."""
    import shutil
    from studio_app import keyframe_context

    slug = str(r.body.get("project") or "").strip()
    shot_id = "".join(c for c in str(r.body.get("id") or "").strip() if c.isalnum() or c in "-_")
    source_id = "".join(c for c in str(r.body.get("source_id") or "").strip() if c.isalnum() or c in "-_")
    edit_inst = str(r.body.get("edit_instruction") or "").strip()
    apply_edit = bool(r.body.get("apply_edit", True))
    req_engine = str(r.body.get("engine") or "auto").strip().lower()
    try:
        strength = max(0.18, min(0.85, float(r.body.get("strength") or 0.38)))
    except (TypeError, ValueError):
        strength = 0.38

    if not slug or not shot_id:
        raise PlanError("project and id are required")

    pd = pdir(slug, "book")
    kf_dir = pd / "keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)
    out_png = kf_dir / f"{shot_id}.png"

    meta_path = pd / "keyframes_v2.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            meta = {}
    if shot_id in (meta.get("locked") or []):
        raise PlanError(f"Keyframe {shot_id} is locked. Unlock it first before cloning over it.")

    sc_id = shot_id.split("-")[0] if "-" in shot_id else ""
    sh_num = int(shot_id.split("-")[1]) if ("-" in shot_id and shot_id.split("-")[1].isdigit()) else 0

    # Auto-pick source frame: explicit source_id -> previous rendered shot -> pinned scene anchor
    src_png: Path | None = None
    if source_id:
        cand = kf_dir / f"{source_id}.png"
        if cand.is_file() and cand.stat().st_size > 200:
            src_png = cand
    if src_png is None and sc_id and sh_num > 1:
        for pn in range(sh_num - 1, 0, -1):
            cid = f"{sc_id}-{pn:02d}"
            cand = kf_dir / f"{cid}.png"
            if cand.is_file() and cand.stat().st_size > 200:
                source_id = cid
                src_png = cand
                break
    if src_png is None and sc_id:
        raw_anchors = meta.get("anchors")
        if isinstance(raw_anchors, dict):
            aid = str(raw_anchors.get(sc_id) or "").strip()
            if aid and aid != shot_id:
                cand = kf_dir / f"{aid}.png"
                if cand.is_file() and cand.stat().st_size > 200:
                    source_id = aid
                    src_png = cand
    if src_png is None:
        raise PlanError("No rendered previous shot or Scene Anchor found in this scene to clone from.")

    shutil.copy2(src_png, out_png)
    rel_url = f"/file/{slug}/keyframes/{shot_id}.png"
    if not apply_edit or not edit_inst:
        return {
            "status": "ok",
            "id": shot_id,
            "source_id": source_id,
            "image_url": rel_url,
            "model": f"cloned:{source_id}",
            "strength_used": 0.0,
        }

    sl_data: dict[str, Any] = {}
    sl_path = pd / "shots" / "shotlist.json"
    if sl_path.is_file():
        try:
            sl_data = json.loads(sl_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            log.debug("shotlist.json read failed in clone_edit: %s", e)

    base_prompt = str(r.body.get("prompt") or (meta.get("prompts") or {}).get(shot_id) or edit_inst).strip()
    kf_ctx = keyframe_context.load_keyframe_project_context(slug, pd)
    ref_pack = keyframe_context.collect_render_references(
        kf_ctx,
        shot_id,
        f"{base_prompt}. {edit_inst}",
        sl_data,
        kf_dir,
        dict(meta.get("prompts") or {}),
    )
    # Put cloned source frame as Image 1 (and init_image), followed by up to 3 character turnarounds
    char_turnarounds = [p for p in ref_pack["ref_imgs"] if p != src_png and p != out_png][:3]
    clone_refs = [out_png] + char_turnarounds
    turn_note = (
        " Additional attached images are the locked Step 10 character turnarounds — match their exact faces and outfits."
        if char_turnarounds
        else ""
    )
    clone_prompt = (
        f"LOCKED-CAMERA CLONE & TARGETED ACTION EDIT (cloned from {source_id}):\n"
        f"Image 1 is the EXACT locked camera frame from {source_id}.{turn_note}\n"
        "Keep the ENTIRE background, walls, windows, furniture positions, props, camera angle, and lighting PIXEL-CONSISTENT with Image 1.\n"
        f"Apply ONLY this character/action update for {shot_id}: {edit_inst}\n\n"
        f"Shot context: {base_prompt}"
    )
    model_used = _render_keyframe_local_or_gemini(
        clone_prompt,
        out_png,
        aspect_ratio="16:9",
        ref_images=clone_refs,
        engine=req_engine,
        seed=int(ref_pack["scene_seed"]),
        init_strength=strength,
        init_image=out_png,
        prefer_edit=True,
        bypass_cache=True,
        extra_negative=ref_pack["style_negatives"],
    )
    return {
        "status": "ok",
        "id": shot_id,
        "source_id": source_id,
        "image_url": rel_url,
        "model": model_used,
        "strength_used": strength,
        "char_refs_used": ref_pack["char_refs_used"],
    }


@route("POST", "/api/v2_keyframe_mask_inpaint")
def _v2_keyframe_mask_inpaint(r: Request):
    """Pixel-locked masked inpainting for a Step 17 keyframe using Canvas Studio box/lasso regions.

    Generates the requested edit with the keyframe + Step 10 turnarounds, then alpha-composites
    ONLY inside the feathered mask onto the original PNG so outside background pixels stay 100% identical.
    """
    import tempfile
    from PIL import Image, ImageDraw, ImageFilter
    from studio_app import keyframe_context

    slug = str(r.body.get("project") or "").strip()
    shot_id = "".join(c for c in str(r.body.get("id") or "").strip() if c.isalnum() or c in "-_")
    inpaint_prompt = str(r.body.get("prompt") or "").strip()
    regions = r.body.get("regions") or []
    req_engine = str(r.body.get("engine") or "auto").strip().lower()
    try:
        strength = max(0.25, min(0.95, float(r.body.get("strength") or 0.72)))
    except (TypeError, ValueError):
        strength = 0.72
    try:
        raw_feather = r.body.get("feather_px")
        feather_px = max(0, min(64, int(18 if raw_feather is None else raw_feather)))
    except (TypeError, ValueError):
        feather_px = 18

    if not slug or not shot_id or not inpaint_prompt:
        raise PlanError("project, id, and prompt are required for masked inpainting")
    if not isinstance(regions, list) or not regions:
        raise PlanError("Draw at least one Box or Lasso region on Canvas Studio before running Masked Inpaint.")

    pd = pdir(slug, "book")
    kf_dir = pd / "keyframes"
    out_png = kf_dir / f"{shot_id}.png"
    if not (out_png.is_file() and out_png.stat().st_size > 200):
        raise PlanError(f"Keyframe {shot_id} does not exist yet.")

    meta_path = pd / "keyframes_v2.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            meta = {}
    if shot_id in (meta.get("locked") or []):
        raise PlanError(f"Keyframe {shot_id} is locked. Unlock it first before inpainting.")

    orig_im = Image.open(out_png).convert("RGBA")
    w, h = orig_im.size

    # Build normalized-coordinate mask from Canvas Studio box/lasso regions
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    drawn_any = False
    for reg in regions:
        if not isinstance(reg, dict):
            continue
        rtype = str(reg.get("type") or "").lower()
        if rtype == "box" and isinstance(reg.get("bbox"), dict):
            bb = reg["bbox"]
            x0 = int(max(0.0, min(1.0, float(bb.get("x", 0.0)))) * w)
            y0 = int(max(0.0, min(1.0, float(bb.get("y", 0.0)))) * h)
            bw = int(max(0.0, min(1.0, float(bb.get("width", 0.0)))) * w)
            bh = int(max(0.0, min(1.0, float(bb.get("height", 0.0)))) * h)
            if bw > 2 and bh > 2:
                draw.rectangle([x0, y0, min(w, x0 + bw), min(h, y0 + bh)], fill=255)
                drawn_any = True
        elif rtype == "lasso" and isinstance(reg.get("points"), list) and len(reg["points"]) >= 3:
            pts = [
                (
                    int(max(0.0, min(1.0, float(pt.get("x", 0.0)))) * w),
                    int(max(0.0, min(1.0, float(pt.get("y", 0.0)))) * h),
                )
                for pt in reg["points"]
                if isinstance(pt, dict)
            ]
            if len(pts) >= 3:
                draw.polygon(pts, fill=255)
                drawn_any = True

    if not drawn_any:
        raise PlanError("Marked mask region is too small. Draw a larger Box or Lasso area on the canvas.")

    raw_mask = mask.copy()
    if feather_px > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=feather_px))

    # Render candidate edit into a temp file using original keyframe + native --mask + character turnarounds
    sl_data: dict[str, Any] = {}
    sl_path = pd / "shots" / "shotlist.json"
    if sl_path.is_file():
        try:
            sl_data = json.loads(sl_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            log.debug("shotlist.json read failed in mask_inpaint: %s", e)

    kf_ctx = keyframe_context.load_keyframe_project_context(slug, pd)
    ref_pack = keyframe_context.collect_render_references(
        kf_ctx, shot_id, inpaint_prompt, sl_data, kf_dir, dict(meta.get("prompts") or {})
    )
    extra_refs = [p for p in ref_pack["ref_imgs"] if p != out_png][:3]
    inpaint_refs = [out_png] + extra_refs
    full_prompt = (
        f"MASKED REGION INPAINT ON KEYFRAME ({shot_id}):\n"
        "Image 1 is the exact locked keyframe. Keep the exact lighting, camera perspective, color grading, and style of Image 1. "
        f"Inside the edited region, seamlessly render: {inpaint_prompt}"
    )

    with tempfile.TemporaryDirectory(prefix="neon-inpaint-") as tmp_:
        cand_png = Path(tmp_) / f"{shot_id}_cand.png"
        cand_mask = Path(tmp_) / f"{shot_id}_mask.png"
        # Save binary grayscale mask for native sd-cli `--mask` diffusion inpainting
        raw_mask.save(cand_mask, format="PNG")
        model_used = _render_keyframe_local_or_gemini(
            full_prompt,
            cand_png,
            aspect_ratio="16:9",
            ref_images=inpaint_refs,
            engine=req_engine,
            seed=int(ref_pack["scene_seed"]),
            init_strength=strength,
            init_image=out_png,
            mask_image=cand_mask,
            prefer_edit=True,
            bypass_cache=True,
            extra_negative=ref_pack["style_negatives"],
        )
        gen_im = Image.open(cand_png).convert("RGBA")
        if gen_im.size != (w, h):
            gen_im = gen_im.resize((w, h), Image.Resampling.LANCZOS)
        # Composite ONLY inside feathered mask — every outside pixel stays 100% pixel-identical!
        composited = Image.composite(gen_im, orig_im, mask).convert("RGB")
        composited.save(out_png, format="PNG")

    return {
        "status": "ok",
        "id": shot_id,
        "image_url": f"/file/{slug}/keyframes/{shot_id}.png",
        "model": f"mask_inpaint:{model_used}",
        "native_mask_used": True,
        "regions_applied": len(regions),
        "char_refs_used": ref_pack["char_refs_used"],
    }


@route("POST", "/api/v2_keyframe_angle_shift")
def _v2_keyframe_angle_shift(r: Request):
    """Generate a new camera angle of the Scene Anchor / previous shot / Step 11 Set Plate via ComfyUI `apps/angles` (Qwen-Image-Edit) with free local Kontext/FLUX.2 fallback."""
    from studio_app import keyframe_context

    slug = str(r.body.get("project") or "").strip()
    shot_id = "".join(c for c in str(r.body.get("id") or "").strip() if c.isalnum() or c in "-_")
    move_key = str(r.body.get("move") or "rotate_left_45").strip().lower()
    details = str(r.body.get("details") or r.body.get("prompt") or "").strip()
    source_id = "".join(c for c in str(r.body.get("source_id") or "").strip() if c.isalnum() or c in "-_")
    req_engine = str(r.body.get("engine") or "auto").strip().lower()

    if not slug or not shot_id:
        raise PlanError("project and id are required")
    move_entry = keyframe_context.ANGLES_CAMERA_MOVES.get(move_key)
    if not move_entry:
        raise PlanError(f"Unknown camera move '{move_key}'")
    move_label, move_value = move_entry

    pd = pdir(slug, "book")
    kf_dir = pd / "keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)
    out_png = kf_dir / f"{shot_id}.png"

    meta_path = pd / "keyframes_v2.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            meta = {}
    if shot_id in (meta.get("locked") or []):
        raise PlanError(f"Keyframe {shot_id} is locked. Unlock it first.")

    sc_id = shot_id.split("-")[0] if "-" in shot_id else ""
    sh_num = int(shot_id.split("-")[1]) if ("-" in shot_id and shot_id.split("-")[1].isdigit()) else 0

    sl_data: dict[str, Any] = {}
    sl_path = pd / "shots" / "shotlist.json"
    if sl_path.is_file():
        try:
            sl_data = json.loads(sl_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            log.debug("shotlist.json read failed in angle_shift: %s", e)

    kf_ctx = keyframe_context.load_keyframe_project_context(slug, pd)
    heading = ""
    for sc in sl_data.get("scenes") or []:
        if str(sc.get("id") or sc.get("scene") or "") == sc_id:
            heading = str(sc.get("heading") or "")
            break

    # Pick source room/frame: explicit source_id -> pinned Scene Anchor -> previous rendered shot -> Step 11 Set Plate
    src_png: Path | None = None
    src_label = ""
    if source_id:
        cand = kf_dir / f"{source_id}.png"
        if cand.is_file() and cand.stat().st_size > 200:
            src_png, src_label = cand, source_id
    if src_png is None and sc_id:
        raw_anchors = meta.get("anchors")
        if isinstance(raw_anchors, dict):
            aid = str(raw_anchors.get(sc_id) or "").strip()
            if aid and aid != shot_id:
                cand = kf_dir / f"{aid}.png"
                if cand.is_file() and cand.stat().st_size > 200:
                    src_png, src_label = cand, f"Anchor {aid}"
    if src_png is None and sc_id and sh_num > 1:
        for pn in range(sh_num - 1, 0, -1):
            cid = f"{sc_id}-{pn:02d}"
            cand = kf_dir / f"{cid}.png"
            if cand.is_file() and cand.stat().st_size > 200:
                src_png, src_label = cand, cid
                break
    if src_png is None and heading:
        _ltok, set_p, _lnames = keyframe_context.match_location_context(kf_ctx, heading)
        if set_p and set_p.is_file():
            src_png, src_label = set_p, f"Set Plate ({set_p.stem})"
    if src_png is None:
        raise PlanError("Render a Step 11 Set Plate or an earlier keyframe in this scene first before shifting camera angle.")

    ref_pack = keyframe_context.collect_render_references(
        kf_ctx, shot_id, details, sl_data, kf_dir, dict(meta.get("prompts") or {})
    )
    extra_chars = [p for p in ref_pack["ref_imgs"] if p != src_png and p != out_png][:3]
    angle_refs = [src_png] + extra_chars

    angle_prompt = (
        f"CAMERA ANGLE SHIFT ({move_label}) OF THE EXACT SAME ROOM & CHARACTERS FROM {src_label}: "
        f"{move_value} Keep the EXACT SAME room layout, wall colors, furniture, lighting, and character identities/outfits from Image 1. "
        f"{details}"
    ).strip()

    model_used = _render_keyframe_local_or_gemini(
        angle_prompt,
        out_png,
        aspect_ratio="16:9",
        ref_images=angle_refs,
        engine=req_engine,
        angle_move=move_value,
        seed=int(ref_pack["scene_seed"]),
        prefer_edit=True,
        bypass_cache=True,
        extra_negative=ref_pack["style_negatives"],
    )
    return {
        "status": "ok",
        "id": shot_id,
        "source": src_label,
        "move": move_key,
        "move_label": move_label,
        "image_url": f"/file/{slug}/keyframes/{shot_id}.png",
        "model": model_used,
        "char_refs_used": ref_pack["char_refs_used"],
    }


_LOCAL_MODEL_DOWNLOADS: dict[str, dict[str, Any]] = {}


def get_local_model_download_status() -> dict[str, dict[str, Any]]:
    return {k: dict(v) for k, v in _LOCAL_MODEL_DOWNLOADS.items()}


@route("POST", "/api/v2_workflow_sync_event")
def _v2_workflow_sync_event(r: Request):
    """Handle bi-directional workflow events: `preview`, `modify`, `tool_done`, or `approve`."""
    from studio_app import workflow_sync

    slug = str(r.body.get("project") or "").strip()
    action = str(r.body.get("action") or "").strip().lower()
    if not slug or action not in ("preview", "modify", "tool_done", "approve"):
        raise PlanError("project and valid action (preview, modify, tool_done, approve) are required")

    pd = pdir(slug, "book")
    step_num = int(r.body.get("step") or 1)
    cur_step = int(r.body.get("current_step") or step_num)

    if action in ("preview", "modify"):
        summary = str(r.body.get("summary") or f"Modified Step {step_num:02d}").strip()
        raw_origin = r.body.get("origin_step")
        origin_step = int(raw_origin) if raw_origin else step_num
        include_upstream = bool(r.body.get("include_upstream", False))
        raw_up = r.body.get("upstream_steps")
        raw_down = r.body.get("downstream_steps")
        exp_up = [int(x) for x in raw_up] if isinstance(raw_up, list) else None
        exp_down = [int(x) for x in raw_down] if isinstance(raw_down, list) else None
        if action == "preview":
            prev = workflow_sync.preview_modification(
                pd,
                slug,
                step_num,
                summary,
                origin_step=origin_step,
                include_upstream=include_upstream,
                explicit_upstream=exp_up,
                explicit_downstream=exp_down,
            )
            banner = workflow_sync.summarize_banner_state(prev["queue"], cur_step)
            return {
                "status": "ok",
                "queue": prev["queue"],
                "banner": banner,
                "plan_chain": prev["plan_chain"],
                "plan_lines": prev["plan_lines"],
            }
        doc = workflow_sync.record_modification(
            pd,
            slug,
            step_num,
            summary,
            origin_step=origin_step,
            include_upstream=include_upstream,
            explicit_upstream=exp_up,
            explicit_downstream=exp_down,
        )
        plan = workflow_sync.format_action_plan(doc.get("items") or [], int(doc.get("origin_step") or step_num))
        banner = workflow_sync.summarize_banner_state(doc, cur_step)
        return {
            "status": "ok",
            "queue": doc,
            "banner": banner,
            "plan_chain": plan["plan_chain"],
            "plan_lines": plan["plan_lines"],
        }

    if action == "tool_done":
        tool_label = str(r.body.get("tool_label") or "").strip()
        doc = workflow_sync.mark_tool_performed(pd, slug, step_num, tool_label=tool_label)
        banner = workflow_sync.summarize_banner_state(doc, cur_step)
        return {"status": "ok", "queue": doc, "banner": banner}

    # action == "approve"
    res = workflow_sync.approve_step(pd, slug, step_num)
    next_cur = int(res["next_step"] or cur_step)
    banner = workflow_sync.summarize_banner_state(res["queue"], next_cur)
    return {
        "status": "ok",
        "queue": res["queue"],
        "banner": banner,
        "advanced": res["advanced"],
        "blocked_needs_run": res["blocked_needs_run"],
        "required_action": res.get("required_action", ""),
        "completed": res["completed"],
        "next_step": res["next_step"],
        "origin_step": res["origin_step"],
    }


@route("POST", "/api/v2_local_consistency_download")
def _v2_local_consistency_download(r: Request):
    """Download free open-weight GGUF consistency models (flux1-kontext-dev / flux2-klein-9b) into models/sd_cli/ in the background."""
    import threading
    import urllib.request
    from local_runners.sd_cli_runner import SdCliRunner

    model_id = str(r.body.get("model_id") or "").strip()
    runner = SdCliRunner()
    catalog = {m["id"]: m for m in runner.describe_consistency_models()}
    if model_id not in catalog:
        raise PlanError(f"Unknown free consistency model '{model_id}'")

    info = catalog[model_id]
    if info["ready"]:
        return {"status": "ready", "model_id": model_id, "message": f"{info['label']} is already installed."}

    cur_job = _LOCAL_MODEL_DOWNLOADS.get(model_id)
    if cur_job and cur_job.get("state") == "downloading":
        return {"status": "downloading", "model_id": model_id, "job": dict(cur_job)}

    missing = list(info.get("missing_files") or [])
    if not missing:
        return {"status": "ready", "model_id": model_id}

    job_state: dict[str, Any] = {
        "model_id": model_id,
        "state": "downloading",
        "current_file": str(missing[0]["file"]),
        "files_done": 0,
        "files_total": len(missing),
        "bytes_done": 0,
        "bytes_total": 0,
        "pct": 0,
        "error": "",
    }
    _LOCAL_MODEL_DOWNLOADS[model_id] = job_state

    def _worker() -> None:
        dest_dir = runner.models_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            for idx, item in enumerate(missing):
                fname = str(item["file"])
                url = str(item["url"])
                dest = dest_dir / fname
                tmp_dest = dest_dir / f"{fname}.part"
                job_state["current_file"] = fname
                job_state["files_done"] = idx
                req = urllib.request.Request(url, headers={"User-Agent": "PistachiosStudio/2.0"})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    total = int(resp.headers.get("Content-Length") or 0)
                    job_state["bytes_total"] = total
                    done = 0
                    with open(tmp_dest, "wb") as fh:
                        while True:
                            chunk = resp.read(1024 * 1024)
                            if not chunk:
                                break
                            fh.write(chunk)
                            done += len(chunk)
                            job_state["bytes_done"] = done
                            if total > 0:
                                job_state["pct"] = min(99, int(((idx + done / total) / len(missing)) * 100))
                tmp_dest.replace(dest)
            job_state["files_done"] = len(missing)
            job_state["pct"] = 100
            job_state["state"] = "done"
        except Exception as exc:
            job_state["state"] = "error"
            job_state["error"] = str(exc)

    threading.Thread(target=_worker, name=f"dl-{model_id}", daemon=True).start()
    return {"status": "started", "model_id": model_id, "job": dict(job_state)}


@route("POST", "/api/v2_keyframe_sync_prompts")
def _v2_keyframe_sync_prompts(r: Request):
    """Rebuild & persist Step 17 prompts from latest Steps 08-12 for one scene or all unlocked scenes."""
    from studio_app import keyframe_context

    slug = str(r.body.get("project") or "").strip()
    target_scene = str(r.body.get("scene") or "").strip()
    if not slug:
        raise PlanError("project is required")

    pd = pdir(slug, "book")
    sl_path = pd / "shots" / "shotlist.json"
    if not sl_path.is_file():
        raise PlanError("No shotlist.json found — generate Step 12 Shot List first.")
    sl_data = json.loads(sl_path.read_text(encoding="utf-8")) or {}

    meta_path = pd / "keyframes_v2.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            meta = {}
    locked_ids = {str(x) for x in (meta.get("locked") or [])}
    prompts: dict[str, Any] = dict(meta.get("prompts") or {})

    ctx = keyframe_context.load_keyframe_project_context(slug, pd)
    updated_count = 0
    skipped_locked = 0
    for sc in sl_data.get("scenes") or []:
        if not isinstance(sc, dict):
            continue
        sc_id = str(sc.get("id") or sc.get("scene") or "S001")
        if target_scene and sc_id != target_scene:
            continue
        heading = str(sc.get("heading") or "")
        for idx, sh in enumerate(sc.get("shots") or [], start=1):
            if not isinstance(sh, dict):
                continue
            n = int(sh.get("n") or idx)
            sid = f"{sc_id}-{n:02d}"
            if sid in locked_ids:
                skipped_locked += 1
                continue
            info = keyframe_context.build_shot_keyframe_info(sh, sc_id, heading, ctx)
            prompts[sid] = info["default_prompt"]
            updated_count += 1

    meta["prompts"] = prompts
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {
        "status": "ok",
        "updated": updated_count,
        "skipped_locked": skipped_locked,
        "scene": target_scene or "ALL",
    }


@route("POST", "/api/v2_shot_continuity_audit")
def _v2_shot_continuity_audit(r: Request):
    """Audit shot-to-shot continuity, prop persistence, grounded surfaces, and character/prop scale; feed fixes back to Steps 12, 17 & Bi-Directional Sync."""
    from studio_app import early_prompt_audit, shot_continuity_audit

    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    res = shot_continuity_audit.run_project_shot_continuity_audit(
        pd,
        slug,
        target_scene=str(r.body.get("scene") or "").strip(),
        use_llm=bool(r.body.get("use_llm", True)),
        record_bidirectional=bool(r.body.get("record_bidirectional", True)),
    )
    if not res.get("ok"):
        raise PlanError(str(res.get("error") or "Shot continuity audit failed."))
    step12_rep = early_prompt_audit.format_shot_audit_report(res)
    early_prompt_audit.save_step_report(pd, 12, step12_rep)
    return {"status": "ok", **res, "issues": step12_rep.get("issues", []), "report": step12_rep}


@route("POST", "/api/v2_early_prompt_audit")
def _v2_early_prompt_audit(r: Request):
    """Run early-stage AI/deterministic prompt continuity audit for Steps 3, 4, 5, 6, 7, 12, or 'all'."""
    from studio_app import early_prompt_audit

    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    raw_step = r.body.get("step", "all")
    use_llm = bool(r.body.get("use_llm", True))
    auto_apply = bool(r.body.get("auto_apply", True))
    record_bi = bool(r.body.get("record_bidirectional", True))
    target_scene = str(r.body.get("scene") or "").strip()

    if str(raw_step).strip().lower() == "all":
        res = early_prompt_audit.audit_all_early_steps(
            pd,
            slug,
            target_scene=target_scene,
            use_llm=use_llm,
            auto_apply=auto_apply,
            record_bidirectional=record_bi,
        )
    else:
        try:
            step_num = int(raw_step)
        except (TypeError, ValueError) as e:
            raise PlanError(f"Invalid step: {raw_step!r}") from e
        res = early_prompt_audit.audit_step(
            pd,
            slug,
            step_num,
            target_scene=target_scene,
            use_llm=use_llm,
            auto_apply=auto_apply,
            record_bidirectional=record_bi,
        )
    if not res.get("ok"):
        raise PlanError(str(res.get("error") or "Early prompt audit failed."))
    return {"status": "ok", **res}


@route("POST", "/api/v2_early_audit_resolve")
def _v2_early_audit_resolve(r: Request):
    """Apply a user's resolution choice for a [Needs Decision] early-audit finding directly to the project."""
    from studio_app import early_prompt_audit

    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    try:
        step_num = int(r.body.get("step", 6))
    except (TypeError, ValueError) as e:
        raise PlanError("step must be a number") from e
    pd = pdir(slug, "book")
    res = early_prompt_audit.resolve_audit_decision(
        pd,
        slug,
        step_num=step_num,
        target=str(r.body.get("target") or "").strip(),
        scene_id=str(r.body.get("scene_id") or "").strip(),
        line_index=int(r.body.get("line_index", -1)),
        field=str(r.body.get("field") or "").strip(),
        issue_text=str(r.body.get("issue") or "").strip(),
        replacement_text=str(r.body.get("replacement_text") or ""),
        keep_original=bool(r.body.get("keep_original", False)),
        option_label=str(r.body.get("option_label") or "").strip(),
        record_bidirectional=bool(r.body.get("record_bidirectional", True)),
    )
    if not res.get("ok"):
        raise PlanError(str(res.get("error") or "Could not apply resolution."))
    return {"status": "ok", **res}


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
    meta: dict[str, Any] = {}
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


@route("POST", "/api/v2_keyframe_edit")
def _v2_keyframe_edit(r: Request):
    """Apply an ordered cascade of modification boxes to an existing unlocked Step 17 keyframe image."""
    slug = str(r.body.get("project") or "").strip()
    shot_id = "".join(c for c in str(r.body.get("id") or "").strip() if c.isalnum() or c in "-_")
    raw_edits = r.body.get("edits")
    if isinstance(raw_edits, list):
        edits = [str(x).strip() for x in raw_edits if str(x or "").strip()]
    else:
        single = str(r.body.get("edit_instruction") or "").strip()
        edits = [single] if single else []
    base_prompt = str(r.body.get("prompt") or "").strip()
    if not slug or not shot_id or not edits:
        raise PlanError("project, id, and at least one modification box are required")

    pd = pdir(slug, "book")
    out_png = pd / "keyframes" / f"{shot_id}.png"
    if not out_png.is_file():
        raise PlanError(f"Keyframe {shot_id} has not been generated yet. Generate it first before modifying.")

    meta_path = pd / "keyframes_v2.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            meta = {}
    if shot_id in (meta.get("locked") or []):
        raise PlanError(f"Keyframe {shot_id} is locked. Unlock it first before modifying.")

    from studio_app import keyframe_context

    sl_data: dict[str, Any] = {}
    sl_path = pd / "shots" / "shotlist.json"
    if sl_path.is_file():
        try:
            sl_data = json.loads(sl_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            log.debug("shotlist.json read failed in keyframe_edit: %s", e)
    kf_ctx = keyframe_context.load_keyframe_project_context(slug, pd)
    ref_pack = keyframe_context.collect_render_references(
        kf_ctx, shot_id, base_prompt, sl_data, pd / "keyframes", dict(meta.get("prompts") or {})
    )
    extra_turnaround_refs = [p for p in ref_pack["ref_imgs"] if p != out_png][:3]
    edit_refs = [out_png] + extra_turnaround_refs
    extra_ref_note = (
        " Additional attached images are the locked Step 10 character turnaround references — preserve those exact faces and outfits."
        if extra_turnaround_refs else ""
    )

    cascade_lines = "\n".join(f"{i}. {txt}" for i, txt in enumerate(edits, start=1))
    edit_prompt = (
        f"TARGETED CASCADED IMAGE EDIT ON EXISTING KEYFRAME ({shot_id}):\n"
        f"Image 1 is the current keyframe.{extra_ref_note} Keep EVERYTHING in Image 1 identical — "
        "exact same camera angle, composition, room layout, lighting, character faces, proportions, and clothing — "
        f"and apply ONLY these ordered modifications:\n{cascade_lines}\n\n"
        f"Original shot context: {base_prompt}"
    )
    req_engine = str(r.body.get("engine") or "auto").strip().lower()
    model_used = _render_keyframe_local_or_gemini(
        edit_prompt,
        out_png,
        aspect_ratio="16:9",
        ref_images=edit_refs,
        engine=req_engine,
        init_strength=0.48,
        init_image=out_png,
        prefer_edit=True,
        extra_negative=ref_pack["style_negatives"],
    )

    # Free-First Visual QA on edited image (local sanity -> free Ollama Vision -> Gemini only if explicitly chosen)
    import run_gemini_omni
    api_key = run_gemini_omni.get_gemini_api_key() if req_engine == "gemini" else ""
    qa = _inspect_keyframe_free_first(out_png, f"{base_prompt}. {'; '.join(edits)}", req_engine, api_key)

    # Persist the ordered cascade of modification boxes until the user clicks Lock
    pending = dict(meta.get("pending_edits") or {})
    pending[shot_id] = edits
    if base_prompt:
        prompts = dict(meta.get("prompts") or {})
        prompts.setdefault(shot_id, base_prompt)
        meta["prompts"] = prompts
    meta["pending_edits"] = pending
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return {
        "status": "ok",
        "id": shot_id,
        "image_url": f"/file/{slug}/keyframes/{shot_id}.png",
        "model": model_used,
        "pending_edits": edits,
        "physics_passed": bool(qa.get("passed", True)),
        "physics_issues": qa.get("issues") or [],
    }


def _merge_edits_into_prompt(base_prompt: str, edits: list[str]) -> str:
    """Cleanly incorporate applied visual edits into the shot's canonical prompt when the keyframe is locked."""
    import urllib.request
    import run_gemini_omni

    if not edits:
        return base_prompt
    api_key = run_gemini_omni.get_gemini_api_key()
    if api_key:
        merge_inst = (
            "Rewrite the following film storyboard shot prompt so it seamlessly incorporates all of the approved visual modifications below. "
            "Keep all locked wardrobe colors, character details, and location locks intact. Return ONLY the single updated prompt paragraph, no quotes or commentary.\n\n"
            f"ORIGINAL PROMPT:\n{base_prompt}\n\n"
            "APPROVED MODIFICATIONS TO INCORPORATE:\n- " + "\n- ".join(edits)
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": merge_inst}]}],
            "generationConfig": {"temperature": 0.2},
        }).encode("utf-8")
        for m in ("gemini-2.5-flash", "gemini-2.0-flash"):
            try:
                req = urllib.request.Request(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                    data=payload,
                    headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                for cand in data.get("candidates") or []:
                    for part in (cand.get("content") or {}).get("parts") or []:
                        txt = (part.get("text") or "").strip()
                        if txt and len(txt) > 20:
                            return txt
            except Exception as e:
                log.debug("prompt edit merge failed on %s: %s", m, e)
                continue
    # Clean deterministic fallback if API call unavailable
    return (base_prompt.rstrip(". ") + ". Refinements: " + "; ".join(edits) + ".").strip()


@route("POST", "/api/v2_keyframe_lock")
def _v2_keyframe_lock(r: Request):
    """Lock or unlock an individual Step 17 keyframe in keyframes_v2.json; when locking, merges any pending visual edits into the shot prompt."""
    slug = str(r.body.get("project") or "").strip()
    shot_id = "".join(c for c in str(r.body.get("id") or "").strip() if c.isalnum() or c in "-_")
    locked = bool(r.body.get("locked", True))
    current_prompt = str(r.body.get("prompt") or "").strip()
    if not slug or not shot_id:
        raise PlanError("project and id are required")
    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    meta_path = pd / "keyframes_v2.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            meta = {}
    cur = [str(x) for x in (meta.get("locked") or []) if str(x) != shot_id]
    updated_prompt = ""
    if locked:
        cur.append(shot_id)
        pending = dict(meta.get("pending_edits") or {})
        saved_edits = pending.pop(shot_id, None) or []
        req_edits = [str(x).strip() for x in (r.body.get("edits") or []) if str(x or "").strip()] if isinstance(r.body.get("edits"), list) else []
        edits = req_edits if req_edits else saved_edits
        if edits:
            prompts = dict(meta.get("prompts") or {})
            base = current_prompt or str(prompts.get(shot_id) or "")
            updated_prompt = _merge_edits_into_prompt(base, edits)
            prompts[shot_id] = updated_prompt
            meta["prompts"] = prompts
        meta["pending_edits"] = pending
    meta["locked"] = sorted(cur)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"status": "ok", "id": shot_id, "locked": locked, "updated_prompt": updated_prompt, "pending_edits": []}


@route("POST", "/api/v2_keyframe_delete")
def _v2_keyframe_delete(r: Request):
    """Delete an individual unlocked Step 17 keyframe PNG so it is not used as a reference."""
    slug = str(r.body.get("project") or "").strip()
    shot_id = "".join(c for c in str(r.body.get("id") or "").strip() if c.isalnum() or c in "-_")
    if not slug or not shot_id:
        raise PlanError("project and id are required")
    pd = pdir(slug, "book")
    meta_path = pd / "keyframes_v2.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
            if shot_id in (meta.get("locked") or []):
                raise PlanError(f"Keyframe {shot_id} is locked. Unlock it first before deleting.")
        except PlanError:
            raise
        except Exception as e:
            log.debug("keyframes_v2.json lock check failed: %s", e)
    png = pd / "keyframes" / f"{shot_id}.png"
    removed = False
    if png.is_file():
        png.unlink(missing_ok=True)
        removed = True
    return {"status": "ok", "id": shot_id, "removed": removed}


@route("POST", "/api/v2_wardrobe_states_save")
def _v2_wardrobe_states_save(r: Request):
    """Save scene/location-specific wardrobe states for a character and sync real-time across Steps 07, 10, 12, and 17."""
    import continuity_sync

    slug = str(r.body.get("project") or "").strip()
    character = str(r.body.get("character") or "").strip()
    states = r.body.get("states")
    if not slug or not character or not isinstance(states, list):
        raise PlanError("project, character, and states list are required")
    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    ws_path = pd / "wardrobe_states.json"
    cur: dict[str, Any] = {}
    if ws_path.is_file():
        try:
            cur = json.loads(ws_path.read_text(encoding="utf-8")) or {}
        except Exception:
            cur = {}
    key = next((k for k in cur if k.lower() == character.lower()), character)
    prev_states = list(cur.get(key) or []) if isinstance(cur.get(key), list) else []
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

    # Surgically sync ONLY the wardrobe entries that were added or modified
    prev_by_scene = {
        str(st.get("scenes") or "").strip().lower(): str(st.get("wardrobe") or "").strip()
        for st in prev_states if isinstance(st, dict)
    }
    sync_report: dict[str, Any] = {"updated_steps": [], "changes": [], "preserved": []}
    for st in clean_states:
        sc_spec = st["scenes"]
        new_w = st["wardrobe"]
        old_w = prev_by_scene.get(sc_spec.lower(), "")
        if new_w and new_w != old_w:
            r_sync = continuity_sync.sync_scene_wardrobe(
                pd,
                slug,
                character=key,
                scene_spec=sc_spec,
                location=st["location"],
                wardrobe_text=new_w,
                old_wardrobe=old_w,
                source_step="step08",
            )
            for fld in ("updated_steps", "changes", "preserved"):
                for item in r_sync.get(fld) or []:
                    if item not in sync_report[fld]:
                        sync_report[fld].append(item)
    return {"status": "ok", "character": key, "states": clean_states, "sync_report": sync_report}


@route("POST", "/api/v2_wardrobe_state_delete")
def _v2_wardrobe_state_delete(r: Request):
    """Delete a wardrobe change state for a character (syncs back to Step 08 wardrobe_states.json & removes its Step 10 turnaround PNGs)."""
    slug = str(r.body.get("project") or "").strip()
    character = str(r.body.get("character") or "").strip()
    idx = int(r.body.get("outfit_index", -1))
    if not slug or not character or idx < 0:
        raise PlanError("project, character, and outfit_index (>= 0) are required")

    pd = pdir(slug, "book")
    ws_path = pd / "wardrobe_states.json"
    cur: dict[str, Any] = {}
    if ws_path.is_file():
        try:
            cur = json.loads(ws_path.read_text(encoding="utf-8")) or {}
        except Exception:
            cur = {}
    key = next((k for k in cur if k.lower() == character.lower()), "")
    states = list(cur.get(key) or []) if key else []
    if idx >= len(states):
        raise PlanError("wardrobe state index out of range")

    removed = states.pop(idx)
    if states:
        cur[key] = states
    elif key:
        cur.pop(key, None)
    ws_path.write_text(json.dumps(cur, indent=2), encoding="utf-8")

    # Remove the deleted outfit's PNGs and shift higher outfit indices down so remaining turnarounds stay aligned
    safe = "".join(c if c.isalnum() else "_" for c in character.lower()).strip("_") or "char"
    t_dir = pd / "assets" / "turnarounds"
    if t_dir.is_dir():
        del_num = idx + 1
        for v in ("front", "three_quarter", "profile"):
            (t_dir / f"{safe}_outfit{del_num}_{v}.png").unlink(missing_ok=True)
        for old_num in range(del_num + 1, len(states) + 2):
            for v in ("front", "three_quarter", "profile"):
                src = t_dir / f"{safe}_outfit{old_num}_{v}.png"
                dst = t_dir / f"{safe}_outfit{old_num - 1}_{v}.png"
                if src.is_file():
                    src.replace(dst)

    import continuity_sync
    sync_report: dict[str, Any] = {"updated_steps": [], "changes": [], "preserved": []}
    if isinstance(removed, dict) and str(removed.get("scenes") or "").strip():
        sync_report = continuity_sync.sync_scene_wardrobe(
            pd,
            slug,
            character=key or character,
            scene_spec=str(removed.get("scenes") or ""),
            location=str(removed.get("location") or ""),
            wardrobe_text="",
            old_wardrobe=str(removed.get("wardrobe") or ""),
            source_step="step08",
        )
    return {"status": "ok", "character": character, "removed": removed, "remaining": len(states), "sync_report": sync_report}


@route("POST", "/api/v2_sync_upstream")
def _v2_sync_upstream(r: Request):
    """User-approved upstream feedback sync: propagate edits made in a later step back to earlier steps."""
    slug = str(r.body.get("project") or "").strip()
    kind = str(r.body.get("kind") or "").strip().lower()
    if not r.body.get("approved"):
        raise PlanError("User permission is required before updating earlier steps.")
    if not slug or not kind:
        raise PlanError("project and kind are required")

    pd = pdir(slug, "book")
    payload = r.body.get("payload") or {}
    updated = 0

    if kind == "dialogue_to_screenplay":
        # Propagate Step 15 dialogue text/note edits back into screenplay/scene-*.json (Step 06)
        lines = payload.get("lines") if isinstance(payload, dict) else []
        by_scene: dict[str, dict[int, dict]] = {}
        for ln in lines or []:
            lid = str(ln.get("id") or "")
            if "-" not in lid:
                continue
            sc_id, idx_s = lid.rsplit("-", 1)
            if idx_s.isdigit():
                by_scene.setdefault(sc_id, {})[int(idx_s)] = ln
        sp_dir = pd / "screenplay"
        for sc_id, edits in by_scene.items():
            sp_file = sp_dir / f"scene-{sc_id}.json"
            if not sp_file.is_file():
                continue
            try:
                sc = json.loads(sp_file.read_text(encoding="utf-8")) or {}
            except Exception as e:
                log.debug("skipping unreadable scene %s: %s", sp_file.name, e)
                continue
            dlg_idx = 0
            changed = False
            for el in sc.get("elements") or []:
                if isinstance(el, dict) and el.get("type") == "dialogue":
                    dlg_idx += 1
                    if dlg_idx in edits:
                        new_t = str(edits[dlg_idx].get("text") or "").strip()
                        new_n = str(edits[dlg_idx].get("note") or "").strip()
                        if new_t and new_t != el.get("text"):
                            el["text"] = new_t
                            changed = True
                            updated += 1
                        if new_n != (el.get("note") or ""):
                            el["note"] = new_n
                            changed = True
            if changed:
                sp_file.write_text(json.dumps(sc, indent=1, ensure_ascii=False), encoding="utf-8")
        return {"status": "ok", "kind": kind, "updated": updated, "steps_updated": ["Step 06 (Screenplay)"]}

    if kind == "keyframe_to_shotlist":
        # Propagate Step 17 edited shot prompts back into shots/shotlist.json (Step 12)
        prompts = payload.get("prompts") if isinstance(payload, dict) else {}
        sl_path = pd / "shots" / "shotlist.json"
        if sl_path.is_file() and isinstance(prompts, dict):
            sl = json.loads(sl_path.read_text(encoding="utf-8")) or {}
            for sc in sl.get("scenes") or []:
                sc_id = str(sc.get("id") or "")
                for sh in sc.get("shots") or []:
                    sid = f"{sc_id}-{int(sh.get('n') or 0):02d}"
                    if sid in prompts and str(prompts[sid]).strip():
                        sh["composition"] = str(prompts[sid]).strip()[:400]
                        updated += 1
            if updated:
                sl_path.write_text(json.dumps(sl, indent=1, ensure_ascii=False), encoding="utf-8")
        return {"status": "ok", "kind": kind, "updated": updated, "steps_updated": ["Step 12 (Shot List)"]}

    if kind in ("character_to_continuity", "location_to_continuity", "score_to_continuity"):
        cb_file = pd / f"{slug}.json"
        if not cb_file.is_file():
            cb_file = pd / "continuity.json"
        if not cb_file.is_file():
            return {"status": "ok", "kind": kind, "updated": 0, "steps_updated": []}
        cb = json.loads(cb_file.read_text(encoding="utf-8")) or {}
        if kind == "character_to_continuity":
            cname = str(payload.get("name") or "").strip()
            ctok = str(payload.get("token") or "").strip()[:198]
            if cname and ctok:
                chars = list(cb.get("characters") or [])
                hit = next((c for c in chars if isinstance(c, dict) and str(c.get("name") or "").lower() == cname.lower()), None)
                if hit:
                    hit["token"] = ctok
                else:
                    chars.append({"name": cname, "token": ctok, "voice": "narrator", "personality": {}})
                cb["characters"] = chars
                updated = 1
        elif kind == "location_to_continuity":
            lname = str(payload.get("name") or "").strip()
            ltok = str(payload.get("token") or "").strip()[:198]
            if lname and ltok:
                locs = list(cb.get("locations") or [])
                hit = next((x for x in locs if isinstance(x, dict) and str(x.get("name") or "").lower() == lname.lower()), None)
                if hit:
                    hit["token"] = ltok
                else:
                    locs.append({"name": lname, "token": ltok})
                cb["locations"] = locs
                updated = 1
        elif kind == "score_to_continuity":
            theme = str(payload.get("music_theme") or "").strip()[:198]
            if theme:
                cb["music_theme"] = theme
                updated = 1
        if updated:
            cb_file.write_text(json.dumps(cb, indent=1, ensure_ascii=False), encoding="utf-8")
        return {"status": "ok", "kind": kind, "updated": updated, "steps_updated": ["Step 07 (Continuity Book)"]}

    raise PlanError(f"Unknown upstream sync kind: {kind}")


@route("POST", "/api/v2_turnaround_render")
def _v2_turnaround_render(r: Request):
    """Generate or upload a character turnaround view (front, three_quarter, profile) per outfit state in assets/turnarounds/."""

    slug = str(r.body.get("project") or "").strip()
    char_name = str(r.body.get("character") or "").strip()
    view = str(r.body.get("view") or "front").strip().lower()
    outfit_id = "".join(c for c in str(r.body.get("outfit_id") or "default").strip().lower() if c.isalnum() or c in "_-") or "default"
    if not slug or not char_name or view not in ("front", "three_quarter", "profile"):
        raise PlanError("project, character, and valid view (front, three_quarter, profile) are required")

    pd = pdir(slug, "book")
    safe = "".join(c if c.isalnum() else "_" for c in char_name.lower()).strip("_") or "char"
    t_dir = pd / "assets" / "turnarounds"
    t_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{safe}_{view}.png" if outfit_id == "default" else f"{safe}_{outfit_id}_{view}.png"
    out_png = t_dir / fname
    rel_url = f"/file/{slug}/assets/turnarounds/{fname}"

    b64 = str(r.body.get("image_base64") or "").strip()
    if b64:
        from studio_app import upload_validation

        raw, _img_ext = upload_validation.decode_verified_base64(b64, kind="image", min_bytes=64)
        out_png.write_bytes(raw)
        return {"status": "ok", "character": char_name, "outfit_id": outfit_id, "view": view, "image_url": rel_url, "model": "uploaded"}

    if bool(r.body.get("async", False)):
        from studio_app import render_jobs

        sync_body = {k: v for k, v in r.body.items() if k != "async"}
        return render_jobs.submit_render_job(
            f"turnaround:{slug}:{char_name}:{view}",
            lambda: _v2_turnaround_render(Request(query=r.query, body=sync_body)),
        )

    desc = str(r.body.get("desc") or "").strip()
    wardrobe = str(r.body.get("wardrobe") or "").strip()
    look = str(r.body.get("look") or "pixar_3d").strip()
    # Honor per-character visual style override (mixed-media films) if saved on Step 08 dossier
    char_style_override = str(r.body.get("style_override") or "").strip()
    if not char_style_override:
        try:
            saved_ch = character_tokens.load_character(slug, char_name)
            if isinstance(saved_ch, dict) and str(saved_ch.get("style_override") or "").strip():
                char_style_override = str(saved_ch["style_override"]).strip()
        except Exception as e:
            log.debug("style_override lookup failed: %s", e)
    effective_look = char_style_override or look
    import character_types_registry as ctr
    style_obj = ctr.get_style(effective_look) or {}
    look_desc = str(style_obj.get("positives") or effective_look)
    style_neg = str(style_obj.get("negatives") or "")
    view_desc = {
        "front": "straight-on front view facing the camera",
        "three_quarter": "three-quarter angle view turned slightly to the side",
        "profile": "strict 90-degree side profile view",
    }[view]

    import character_identity
    import hashlib
    import tempfile

    cast_profiles = _load_project_cast_profiles(slug, pd)
    cast_names = [c["name"] for c in cast_profiles]
    if char_name not in cast_names:
        cast_names.append(char_name)
    overrides = character_identity.load_identity_overrides(pd)
    canon_id = character_identity.canonical_character_key(char_name, known_names=cast_names, overrides=overrides)
    canon_label = canon_id.replace("_", " ").upper()

    # 3/4 Angle and Side Profile MUST use THIS card/outfit's Front View image as their primary visual reference
    front_candidates = (
        [t_dir / f"{safe}_{outfit_id}_front.png", t_dir / f"{safe}_front.png"]
        if outfit_id != "default"
        else [t_dir / f"{safe}_front.png", t_dir / f"{safe}_outfit1_front.png"]
    )
    front_ref = next((p for p in front_candidates if p.is_file() and p.stat().st_size > 100), None)

    ref_imgs: list[Path] = []
    ref_source = ""
    ref_reason = "new_distinct_character"
    twin_allowed_with: list[str] = []
    other_non_twin: list[dict[str, str]] = []
    other_front_pngs: list[tuple[str, Path]] = []

    if view in ("three_quarter", "profile"):
        if front_ref is None:
            raise PlanError(f"Generate or upload the Front View of {char_name} first — 3/4 Angle and Side Profile require the Front View as a visual reference.")
        ref_imgs = [front_ref]
        ref_source = f"{char_name} (Front View)"
        ref_reason = "front_view_angle_rotation"
    else:
        # 1a. Explicit Step 08 uploaded cast reference photo for THIS exact character slug takes top priority
        #     so uploading a real photo for e.g. "Security Officer Kibble" is never overridden by another variant ("kibble_front.png").
        canon_refs: list[tuple[Path, str]] = []
        cast_ref_dir = pd / "assets" / "cast_refs"
        if cast_ref_dir.is_dir():
            for ext in (".png", ".jpg", ".jpeg", ".webp"):
                exact_ref = cast_ref_dir / f"{safe}_ref{ext}"
                if exact_ref.is_file() and exact_ref.stat().st_size > 100:
                    canon_refs = [(exact_ref, f"{char_name} (Step 08 Reference)")]
                    ref_reason = "uploaded_cast_photo_restyle"
                    break

        # 1b. Same-character identity lock: if ANY picture already exists for this character
        #     (another outfit OR a costume/scene variant like CAPTAIN TOMMY <-> TOMMY, FIRST OFFICER JUDAH <-> JUDAH),
        #     use it as the visual reference so the character keeps the exact same face/body across all costumes/scenes.
        if not canon_refs:
            canon_refs = character_identity.find_canonical_character_refs(
                t_dir,
                char_name,
                prefer_outfit=outfit_id,
                exclude_path=out_png,
                known_names=cast_names,
                overrides=overrides,
                limit=1,
            )
        # 1c. Canonical-slug Step 08 uploaded cast reference photo fallback
        if not canon_refs and cast_ref_dir.is_dir() and canon_id != safe:
            for ext in (".png", ".jpg", ".jpeg", ".webp"):
                cand_p = cast_ref_dir / f"{canon_id}_ref{ext}"
                if cand_p.is_file() and cand_p.stat().st_size > 100:
                    canon_refs = [(cand_p, f"{char_name} (Step 08 Reference)")]
                    ref_reason = "uploaded_cast_photo_restyle"
                    break
        if canon_refs:
            ref_imgs = [p for p, _src in canon_refs]
            ref_source = canon_refs[0][1]
            if ref_reason != "uploaded_cast_photo_restyle":
                ref_reason = "same_character_costume_change"
        else:
            # 2. Separate character with a different canonical name:
            #    ONLY allowed to look alike if descriptions explicitly state they are twins!
            twin_ref_path: Path | None = None
            twin_ref_name = ""
            seen_other_canon: set[str] = set()
            for other in cast_profiles:
                oname = other["name"]
                ocanon = character_identity.canonical_character_key(oname, known_names=cast_names, overrides=overrides)
                if ocanon == canon_id:
                    continue
                is_twin = character_identity.explicit_twin_relationship(char_name, desc, oname, other.get("desc", ""))
                if is_twin:
                    twin_allowed_with.append(oname)
                    if twin_ref_path is None:
                        t_refs = character_identity.find_canonical_character_refs(
                            t_dir, oname, known_names=cast_names, overrides=overrides, limit=1,
                        )
                        if t_refs:
                            twin_ref_path, twin_ref_name = t_refs[0]
                elif ocanon not in seen_other_canon:
                    seen_other_canon.add(ocanon)
                    other_non_twin.append(other)
                    o_refs = character_identity.find_canonical_character_refs(
                        t_dir, oname, known_names=cast_names, overrides=overrides, limit=1,
                    )
                    if o_refs and o_refs[0][0].name.endswith("_front.png"):
                        other_front_pngs.append((oname, o_refs[0][0]))

            if twin_ref_path is not None:
                ref_imgs = [twin_ref_path]
                ref_source = f"{twin_ref_name} (explicit twin)"
                ref_reason = "explicit_twin"

    wardrobe_clause = f" Wearing: {wardrobe}." if wardrobe else ""
    req_engine = str(r.body.get("engine") or "auto").strip().lower()
    distinct_cues, distinct_neg = (
        character_identity.build_distinct_character_cues(char_name, desc, other_non_twin, attempt=0)
        if (view == "front" and not ref_imgs)
        else ("", "")
    )
    other_names_txt = ", ".join(o["name"] for o in other_non_twin[:6])

    def _build_turnaround_prompt(extra_distinct: str) -> str:
        distinct_clause = f" Distinctive individual features: {extra_distinct}." if extra_distinct else ""
        if req_engine in ("gemini", "cloud"):
            if ref_imgs and view in ("three_quarter", "profile"):
                ref_note = f" Using the attached Front View reference image of {char_name}, keep the EXACT SAME face, hair, body, and clothing, rendered as ONE single figure from a {view_desc}."
            elif ref_imgs and ref_reason == "uploaded_cast_photo_restyle":
                restyle_hint = str(style_obj.get("restyle_prompt") or f"Complete style transformation into {look_desc}")
                ref_note = (
                    f" UPLOADED REFERENCE PHOTO STYLE TRANSFORMATION: {restyle_hint}. "
                    f"Translate the person/subject shown in Image 1 ({char_name}) — preserving their recognizable likeness, hairstyle, glasses/accessories, and outfit — "
                    f"completely into the film's stylized visual look ({look_desc}, NOT a raw photograph), rendered as ONE single full-body figure from a {view_desc}."
                )
            elif ref_imgs and ref_reason == "same_character_costume_change":
                ref_note = (
                    f" CHARACTER IDENTITY LOCK: The attached image shows this EXACT SAME character ({canon_label}). "
                    f"Preserve their EXACT SAME face, head shape, eyes, nose, hair/fur, skin tone, age, and body proportions unchanged, "
                    f"and apply ONLY the costume/outfit/scene appearance described below, rendered as ONE single figure from a {view_desc}."
                )
            elif ref_imgs and ref_reason == "explicit_twin":
                ref_note = (
                    f" EXPLICIT TWIN LIKENESS: {char_name} is explicitly described as a twin of {ref_source}. "
                    f"Preserve the twin facial likeness from the attached reference image while applying {char_name}'s exact described outfit and details, rendered as ONE single figure from a {view_desc}."
                )
            elif other_names_txt:
                ref_note = (
                    f" DISTINCT CHARACTER IDENTITY: {char_name} is a completely separate character (NOT a twin of {other_names_txt}). "
                    f"Give {char_name} a visibly unique face shape, eyes, nose, hairstyle, and build that does NOT resemble any other cast member.{distinct_clause}"
                )
            else:
                ref_note = distinct_clause
            return (
                f"A single standalone full-body character portrait of {char_name} shown from a {view_desc}. "
                f"{desc}.{ref_note}{wardrobe_clause} Style: {look_desc}. Clean solid neutral studio backdrop, clearly showing the exact outfit and face, consistent soft studio lighting."
            )

        # Keep local positive prompts free of "turnaround sheet / grid / duplicate" words (CFG=1 models ignore "NO"!)
        if ref_imgs and view in ("three_quarter", "profile"):
            return (
                f"Keep the exact same character ({char_name}) from the reference image — identical face, hair, skin, body proportions, clothing, footwear, and {look_desc} style — "
                f"rotated to show a solo full-body {view_desc}, standing alone centered on the same plain solid warm light-gray seamless studio backdrop, full body head to toe, soft even studio lighting. "
                f"{desc}.{wardrobe_clause}"
            )
        if ref_imgs and ref_reason == "uploaded_cast_photo_restyle":
            restyle_hint = str(style_obj.get("restyle_prompt") or f"Complete style transformation into {look_desc}")
            return (
                f"{restyle_hint}. Transform the person/subject in Image 1 ({char_name}) completely into this stylized character look — "
                f"preserving their recognizable likeness, hairstyle, expression, glasses/accessories, and outfit while converting every surface into {look_desc} "
                f"(NOT a real-world photograph, NOT realistic human skin). {desc}.{wardrobe_clause} "
                f"Solo full-body {view_desc} standing alone centered head to toe on a clean solid warm light-gray studio backdrop, soft even studio lighting."
            )
        if ref_imgs and ref_reason == "same_character_costume_change":
            return (
                f"Keep the exact same character ({canon_label}) from the reference image — identical face, head shape, eyes, nose, hair/fur, skin tone, age, body proportions, and {look_desc} style — "
                f"now shown as a solo full-body {view_desc} wearing ONLY this new costume and scene appearance, replacing the clothing and accessories from the reference image: "
                f"{desc}.{wardrobe_clause} Standing alone centered on a plain solid warm light-gray seamless studio backdrop, full body head to toe, soft even studio lighting."
            )
        if ref_imgs and ref_reason == "explicit_twin":
            return (
                f"Show the twin character ({char_name}) keeping the same twin facial likeness and {look_desc} style from the reference image, "
                f"as a solo full-body {view_desc} with this exact outfit and details: {desc}.{wardrobe_clause} "
                f"Standing alone centered on a plain solid warm light-gray seamless studio backdrop, full body head to toe, soft even studio lighting."
            )
        return (
            f"A solo full-body studio photograph of one single character ({char_name}) standing centered alone in frame, {view_desc}. "
            f"{desc}.{distinct_clause}{wardrobe_clause} Style: {look_desc}. Plain solid warm light-gray seamless studio backdrop, full body head to toe, soft even studio lighting."
        )

    prompt = _build_turnaround_prompt(distinct_cues)
    combined_neg = ", ".join(x for x in (distinct_neg, style_neg) if x)
    is_reroll = out_png.is_file() and out_png.stat().st_size > 100
    # Use canonical identity key in base seed so same-character variants share lighting/aesthetic while distinct characters stay uncorrelated
    char_seed = -1 if is_reroll else (int.from_bytes(hashlib.sha256(f"{slug}:{canon_id}:{safe}:{outfit_id}".encode()).digest()[:4], "little") % 2_000_000_000)
    must_use_ref = bool(ref_imgs) and (view in ("three_quarter", "profile") or ref_reason in ("same_character_costume_change", "explicit_twin"))
    model_used = _render_keyframe_local_or_gemini(
        prompt, out_png, aspect_ratio="1:1", ref_images=ref_imgs, engine=req_engine,
        view=view, seed=char_seed, init_strength=None,
        require_ref=must_use_ref,
        bypass_cache=is_reroll,
        extra_negative=combined_neg,
    )

    # Non-twin distinctness verification: if a new distinct character's Front View came out
    # looking too similar to an existing non-twin cast member, automatically retry once with
    # stronger facial differentiation and keep whichever render is more visually distinct.
    distinctness: dict[str, Any] = {}
    if view == "front" and not ref_imgs and other_front_pngs and out_png.is_file():
        distinctness = character_identity.check_non_twin_distinctness(out_png, other_front_pngs, threshold=0.86)
        if not distinctness.get("distinct", True):
            first_bytes = out_png.read_bytes()
            first_sim = float(distinctness.get("max_similarity", 1.0))
            retry_cues, retry_neg = character_identity.build_distinct_character_cues(char_name, desc, other_non_twin, attempt=1)
            retry_prompt = _build_turnaround_prompt(retry_cues)
            retry_seed = (char_seed + 7919) % 2_000_000_000 if char_seed >= 0 else -1
            with tempfile.TemporaryDirectory(prefix="neon-distinct-") as tmp_dir:
                retry_png = Path(tmp_dir) / out_png.name
                try:
                    retry_model = _render_keyframe_local_or_gemini(
                        retry_prompt, retry_png, aspect_ratio="1:1", ref_images=None, engine=req_engine,
                        view=view, seed=retry_seed, init_strength=None,
                        require_ref=False, bypass_cache=True, extra_negative=retry_neg,
                    )
                    if retry_png.is_file() and retry_png.stat().st_size > 100:
                        retry_check = character_identity.check_non_twin_distinctness(retry_png, other_front_pngs, threshold=0.86)
                        if float(retry_check.get("max_similarity", 1.0)) < first_sim:
                            out_png.write_bytes(retry_png.read_bytes())
                            model_used = retry_model
                            distinctness = {**retry_check, "diversified_retry": True}
                        else:
                            out_png.write_bytes(first_bytes)
                            distinctness["diversified_retry"] = True
                except Exception as e:
                    log.debug("non-twin diversify retry failed: %s", e)
                    out_png.write_bytes(first_bytes)

    return {
        "status": "ok",
        "character": char_name,
        "outfit_id": outfit_id,
        "view": view,
        "image_url": rel_url,
        "model": model_used,
        "refs_used": len(ref_imgs),
        "character_control": {
            "canonical_id": canon_id,
            "canonical_label": canon_label,
            "reference_source": ref_source,
            "reference_reason": ref_reason,
            "twin_allowed_with": twin_allowed_with,
            "distinctness": distinctness,
        },
    }


@route("POST", "/api/v2_character_identity_link")
def _v2_character_identity_link(r: Request):
    """Save or clear a manual same-character identity link for Step 10/17 character control."""
    import character_identity

    slug = str(r.body.get("project") or "").strip()
    char_name = str(r.body.get("character") or "").strip()
    target_base = str(r.body.get("target_base") or "").strip()
    if not slug or not char_name:
        raise PlanError("project and character are required")
    pd = pdir(slug, "book")
    links = character_identity.save_identity_override(pd, char_name, target_base)
    return {"status": "ok", "character": char_name, "target_base": target_base or "auto", "links": links}


def _load_sets_state(pd: Path) -> tuple[list[str], list[str]]:
    """Load Step 11 (order, deleted) lists from sets_state.json / sets_deleted.json."""
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
    del_set = set(deleted)
    order = [x for x in order if x not in del_set]
    return order, deleted


def _save_sets_state(pd: Path, order: list[str], deleted: list[str]) -> tuple[list[str], list[str]]:
    """Persist Step 11 set order & deleted list cleanly (deduped, contiguous)."""
    pd.mkdir(parents=True, exist_ok=True)
    clean_del: list[str] = []
    for x in deleted:
        k = str(x).strip().lower()
        if k and k not in clean_del:
            clean_del.append(k)
    del_set = set(clean_del)
    clean_ord: list[str] = []
    for x in order:
        k = str(x).strip().lower()
        if k and k not in del_set and k not in clean_ord:
            clean_ord.append(k)
    (pd / "sets_state.json").write_text(
        json.dumps({"order": clean_ord, "deleted": clean_del}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (pd / "sets_deleted.json").write_text(
        json.dumps({"deleted": clean_del}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return clean_ord, clean_del


def _sync_continuity_location_order(pd: Path, slug: str, order: list[str]) -> None:
    """Keep Continuity Book location order aligned with Step 11's set numbering."""
    import continuity_book

    continuity_book.reorder(pd, "locations", order)
    legacy_cb = pd / f"{slug}.json"
    if legacy_cb.is_file() and order:
        try:
            cb = json.loads(legacy_cb.read_text(encoding="utf-8")) or {}
            locs = cb.get("locations")
            if isinstance(locs, list) and len(locs) >= 2:
                rank = {n: i for i, n in enumerate(order)}
                base = len(rank)
                ordered = [
                    e for _i, e in sorted(
                        enumerate(locs),
                        key=lambda pair: (
                            rank.get(
                                str(pair[1] if isinstance(pair[1], str) else (pair[1].get("name") or pair[1].get("location") or "") if isinstance(pair[1], dict) else "").strip().lower(),
                                base + pair[0],
                            ),
                            pair[0],
                        ),
                    )
                ]
                if ordered != locs:
                    cb["locations"] = ordered
                    legacy_cb.write_text(json.dumps(cb, indent=1, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.debug("legacy continuity book location reorder failed: %s", e)


@route("POST", "/api/v2_set_delete")
def _v2_set_delete(r: Request):
    """Delete a location/set from Step 11, persist hidden status, remove set images, and renumber remaining sets."""
    import continuity_book

    slug = str(r.body.get("project") or "").strip()
    name = str(r.body.get("name") or "").strip()
    if not slug or not name:
        raise PlanError("project and set name are required")
    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    key = name.lower()

    # 1. Remove from continuity book (continuity.json / <slug>.json) if present
    removed_from_cb = continuity_book.remove(pd, "locations", name)
    legacy_cb = pd / f"{slug}.json"
    if legacy_cb.is_file():
        try:
            cb = json.loads(legacy_cb.read_text(encoding="utf-8")) or {}
            locs = cb.get("locations")
            if isinstance(locs, list):
                kept = [
                    x for x in locs
                    if str(x if isinstance(x, str) else (x.get("name") or x.get("location") or "") if isinstance(x, dict) else "").strip().lower() != key
                ]
                if len(kept) != len(locs):
                    cb["locations"] = kept
                    legacy_cb.write_text(json.dumps(cb, indent=1, ensure_ascii=False), encoding="utf-8")
                    removed_from_cb = True
        except Exception as e:
            log.debug("legacy continuity book location delete failed: %s", e)

    # 2. Persist in sets_state.json / sets_deleted.json & remove from order so remaining sets auto-renumber 1..N
    order, deleted = _load_sets_state(pd)
    req_order = r.body.get("order")
    if isinstance(req_order, list) and req_order:
        order = [str(x).strip().lower() for x in req_order if str(x).strip()]
    if key not in deleted:
        deleted.append(key)
    order = [x for x in order if x != key]
    order, deleted = _save_sets_state(pd, order, deleted)
    _sync_continuity_location_order(pd, slug, order)

    # 3. Remove any rendered set asset images matching this location slug
    safe = "".join(c if c.isalnum() else "_" for c in key).strip("_")
    removed_images = 0
    sets_dir = pd / "assets" / "sets"
    if safe and sets_dir.is_dir():
        for p in sets_dir.glob(f"{safe}*.png"):
            if p.is_file():
                p.unlink(missing_ok=True)
                removed_images += 1

    return {
        "status": "ok",
        "name": name,
        "removed_from_continuity": removed_from_cb,
        "removed_images": removed_images,
        "deleted": deleted,
        "order": order,
    }


@route("POST", "/api/v2_set_order")
def _v2_set_order(r: Request):
    """Save Step 11 set order (supports inserting a set at a 1-based set number or reordering) and auto-renumber."""
    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    order, deleted = _load_sets_state(pd)

    req_order = r.body.get("order")
    if isinstance(req_order, list):
        order = [str(x).strip().lower() for x in req_order if str(x).strip()]

    insert_name = str(r.body.get("insert_name") or "").strip()
    raw_pos = r.body.get("position")
    if insert_name:
        ikey = insert_name.lower()
        deleted = [x for x in deleted if x != ikey]
        order = [x for x in order if x != ikey]
        if isinstance(raw_pos, (int, float)) or (isinstance(raw_pos, str) and raw_pos.strip().isdigit()):
            idx = max(0, min(len(order), int(raw_pos) - 1))
        else:
            idx = len(order)
        order.insert(idx, ikey)

    order, deleted = _save_sets_state(pd, order, deleted)
    _sync_continuity_location_order(pd, slug, order)
    return {"status": "ok", "order": order, "deleted": deleted}


@route("POST", "/api/v2_set_save")
def _v2_set_save(r: Request):
    """Save Step 11 location/set details to disk and sync real-time to Step 07 Continuity Book, Step 12, and Step 17."""
    import continuity_sync

    slug = str(r.body.get("project") or "").strip()
    name = str(r.body.get("name") or "").strip()
    description = str(r.body.get("description") or "").strip()
    lighting = str(r.body.get("lighting") or "").strip()
    if not slug or not name:
        raise PlanError("project and set name are required")
    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    custom_path = pd / "sets_custom.json"
    cur: dict[str, Any] = {}
    if custom_path.is_file():
        try:
            raw = json.loads(custom_path.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                cur = raw
        except Exception as e:
            log.debug("sets_custom.json read failed: %s", e)
    k = name.lower()
    raw_prev_entry = cur.get(k)
    prev_entry: dict[str, Any] = raw_prev_entry if isinstance(raw_prev_entry, dict) else {}
    old_desc = str(prev_entry.get("description") or "")
    reserve_2d_gaps = bool(r.body.get("reserve_2d_gaps", prev_entry.get("reserve_2d_gaps", False)))
    gap_notes = str(r.body.get("gap_notes") if "gap_notes" in r.body else prev_entry.get("gap_notes", "")).strip()
    cur[k] = {
        "name": name,
        "description": description,
        "lighting": lighting,
        "reserve_2d_gaps": reserve_2d_gaps,
        "gap_notes": gap_notes,
    }
    custom_path.write_text(json.dumps(cur, indent=2, ensure_ascii=False), encoding="utf-8")

    sync_report = continuity_sync.sync_location_change(
        pd,
        slug,
        name=name,
        old_desc=old_desc,
        new_desc=description,
        lighting=lighting,
        source_step="step11",
    )
    return {
        "status": "ok",
        "name": name,
        "description": description,
        "lighting": lighting,
        "reserve_2d_gaps": reserve_2d_gaps,
        "gap_notes": gap_notes,
        "sync_report": sync_report,
    }


def _safe_set_slug(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in str(name or "").lower()).strip("_") or "set"


def _safe_view_id(raw_id: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in str(raw_id or "").lower()).strip("_") or "main"


def _load_sets_views_doc(pd: Path) -> dict[str, Any]:
    vp = pd / "sets_views.json"
    if vp.is_file():
        try:
            doc = json.loads(vp.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and isinstance(doc.get("sets"), dict):
                return doc
        except Exception as e:
            log.debug("sets_views.json read failed: %s", e)
    return {"sets": {}}


def _save_sets_views_doc(pd: Path, doc: dict[str, Any]) -> None:
    pd.mkdir(parents=True, exist_ok=True)
    (pd / "sets_views.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


def _ensure_set_view_entry(doc: dict[str, Any], set_name: str, view_id: str = "main", view_label: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    """Ensure `<set_name>` and `<view_id>` exist inside `sets_views.json`."""
    sets_map: dict[str, Any] = doc.setdefault("sets", {})
    key = set_name.strip().lower()
    srec = sets_map.get(key)
    if not isinstance(srec, dict):
        srec = {"name": set_name.strip(), "baseline_view_id": "", "baseline_snapshot": "", "views": []}
        sets_map[key] = srec
    views_list: list[dict[str, Any]] = srec.setdefault("views", [])
    # Always ensure primary "main" view exists first
    if not any(isinstance(v, dict) and v.get("id") == "main" for v in views_list):
        views_list.insert(0, {"id": "main", "label": "Establishing View", "notes": "", "ref_image": "", "converted_image": ""})
    vid = _safe_view_id(view_id)
    found: dict[str, Any] | None = None
    for v in views_list:
        if isinstance(v, dict) and v.get("id") == vid:
            found = v
            break
    if found is None:
        found = {
            "id": vid,
            "label": view_label.strip() or ("Establishing View" if vid == "main" else vid.replace("_", " ").title()),
            "notes": "",
            "ref_image": "",
            "converted_image": "",
        }
        views_list.append(found)
    elif view_label.strip():
        found["label"] = view_label.strip()
    return srec, found


_ENV_STYLE_DROP_RE = re.compile(
    r"\b("
    r"eyes?|eyebrows?|eyelashes?|pupils?|faces?|facial|mouths?|noses?|ears?|smiles?|"
    r"hair|hairpieces?|hands?|fingers?|legs?|arms?|limbs?|anatomy|skin|"
    r"characters?|minifigures?|actors?|humans?|people|persons?|figures?|figurines?|"
    r"puppets?|dolls?|creatures?|sprites?|costumes?|wardrobes?|clothing|outfits?"
    r")\b",
    re.IGNORECASE,
)


def _sanitize_style_for_environment(style_pos: str) -> str:
    """Strip character/anatomy clauses (e.g. 'large expressive eyes', 'minifigure face') so empty set plates never hallucinate eyes or characters."""
    raw = str(style_pos or "").strip()
    if not raw:
        return ""
    kept = [part.strip() for part in raw.split(",") if part.strip() and not _ENV_STYLE_DROP_RE.search(part)]
    if kept:
        return ", ".join(kept)
    return "stylized animated feature film environment art, cohesive materials, warm global illumination"


def _resolve_set_film_style(pd: Path) -> tuple[str, str, str, bool]:
    """Return `(look_id, style_pos, style_neg, is_photorealistic)` honoring Step 09 global_params.json positives/negatives."""
    import character_types_registry as ctr

    look = "pixar_3d"
    gp_pos = ""
    gp_neg = ""
    gp_path = pd / "global_params.json"
    if gp_path.is_file():
        try:
            gp = json.loads(gp_path.read_text(encoding="utf-8")) or {}
            raw_hm = gp.get("hybrid_mode")
            hm: dict[str, Any] = raw_hm if isinstance(raw_hm, dict) else {}
            if hm.get("enabled"):
                look = str(hm.get("world_style") or "live_action")
            else:
                gp_pos = str(gp.get("positives") or "").strip()
                gp_neg = str(gp.get("negatives") or "").strip()
                explicit_look = str(gp.get("look") or "").strip()
                if explicit_look:
                    look = explicit_look
                else:
                    pl = gp_pos.lower()
                    nl = gp_neg.lower()
                    if "live action" in pl and "photorealistic" not in nl:
                        look = "live_action"
                    elif "claymation" in pl or "plasticine" in pl:
                        look = "claymation"
                    elif "anime" in pl or "cel shading" in pl:
                        look = "anime"
                    elif "watercolour" in pl or "watercolor" in pl:
                        look = "watercolour"
                    elif "comic" in pl or "halftone" in pl:
                        look = "comic_ink"
                    elif "felt" in pl or "wool" in pl:
                        look = "felt"
                    elif "noir" in pl or "black-and-white" in pl:
                        look = "noir"
                    elif "ukiyo" in pl or "woodblock" in pl:
                        look = "ukiyo_e"
                    elif "2d cartoon" in pl or "mid-century" in pl:
                        look = "midcentury_2d"
                    else:
                        look = "pixar_3d"
        except Exception as e:
            log.debug("global_params.json read failed in _resolve_set_film_style: %s", e)
    st = ctr.get_style(look)
    raw_pos = gp_pos or str((st or {}).get("positives") or "cinematic wide establishing shot, 35mm lens, warm practical lighting")
    style_pos = _sanitize_style_for_environment(raw_pos)
    style_neg = gp_neg or str((st or {}).get("negatives") or "")
    is_photo = look == "live_action" and "photorealistic" not in style_neg.lower()
    return look, style_pos, style_neg, is_photo


def _render_set_view_plate(
    slug: str,
    pd: Path,
    name: str,
    *,
    view_id: str = "main",
    view_label: str = "",
    view_notes: str = "",
    desc: str = "",
    lighting: str = "",
    reserve_2d_gaps: bool = False,
    gap_notes: str = "",
    req_engine: str = "auto",
    use_ref: bool = True,
    use_baseline: bool = True,
    style_strength: float | None = None,
) -> dict[str, Any]:
    """Core Step 11 set/view renderer supporting imported photo style-conversion AND baselined view anchoring."""
    safe = _safe_set_slug(name)
    vid = _safe_view_id(view_id)
    doc = _load_sets_views_doc(pd)
    srec, vrec = _ensure_set_view_entry(doc, name, vid, view_label=view_label)
    if view_notes:
        vrec["notes"] = view_notes

    out_rel = f"assets/sets/{safe}.png" if vid == "main" else f"assets/sets/{safe}__view_{vid}.png"
    out_png = pd / out_rel
    out_png.parent.mkdir(parents=True, exist_ok=True)

    _look, style_pos, style_neg, is_photo = _resolve_set_film_style(pd)

    # Check for imported reference photo on THIS view
    ref_rel = str(vrec.get("ref_image") or "").strip()
    ref_img: Path | None = None
    if use_ref and ref_rel:
        cand_r = pd / ref_rel
        if cand_r.is_file() and cand_r.stat().st_size > 100:
            ref_img = cand_r

    # Check for pinned Baseline image on THIS location
    base_rel = str(srec.get("baseline_snapshot") or "").strip()
    base_vid = str(srec.get("baseline_view_id") or "").strip()
    baseline_img: Path | None = None
    if use_baseline and base_rel:
        cand_b = pd / base_rel
        if cand_b.is_file() and cand_b.stat().st_size > 100:
            baseline_img = cand_b

    # Assemble visual references + img2img anchor + style-conversion / baseline-lock prompt
    ref_imgs: list[Path] = []
    init_img: Path | None = None
    init_strength: float | None = None
    directives: list[str] = []

    if ref_img is not None:
        ref_imgs.append(ref_img)
        init_img = ref_img
        if is_photo:
            init_strength = float(style_strength) if style_strength is not None else 0.52
            directives.append(
                f"Faithful rendering of the exact image in Image {len(ref_imgs)}, preserving the exact subject, shapes, colors, background, and camera framing of Image {len(ref_imgs)} unchanged."
            )
        else:
            # Real-world photo -> stylized film (e.g. 3D Pixar / 2D / claymation) conversion!
            # CRITICAL: Keep the prompt 100% subject-agnostic (NO room/cabinet/window/furniture nouns and NO
            # negative-list nouns in the positive prompt, because 4-step FLUX.2 at cfg=1.0 will draw mentioned nouns!).
            init_strength = float(style_strength) if style_strength is not None else 0.72
            directives.append(
                f"{style_pos}. Stylized animated movie rendering of the exact image in Image {len(ref_imgs)}. "
                f"Re-render only the exact subject, shapes, surfaces, colors, background, and composition already visible in Image {len(ref_imgs)} "
                f"entirely in {style_pos}, with smooth stylized surfaces, soft rounded bevelled edges, and clean animated film shading. "
                f"Keep the exact background, framing, and empty areas of Image {len(ref_imgs)} completely unchanged."
            )
            style_neg = ", ".join(x for x in (style_neg, "raw photograph, unstyled real photo, camera snapshot, added objects, extra furniture, extra props, room interior added") if x)

    if baseline_img is not None and (ref_img is None or baseline_img.resolve() != ref_img.resolve()):
        ref_imgs.append(baseline_img)
        if init_img is None:
            # Re-running the baselined view itself uses tight img2img lock; another view of the same location uses baseline as style/room reference
            if base_vid == vid:
                init_img = baseline_img
                init_strength = float(style_strength) if style_strength is not None else 0.48
                directives.append(
                    f"LOCKED BASELINE REFINEMENT (Image {len(ref_imgs)}): Refine this set view while keeping the EXACT architecture, color palette, materials, lighting mood, and visual style of the baselined image (Image {len(ref_imgs)})."
                )
            else:
                directives.append(
                    f"SAME-LOCATION BASELINE CONTINUITY (Image {len(ref_imgs)} is the baselined view '{base_vid}' of {name}): "
                    f"Match the EXACT same wall colors, flooring, furniture design, materials, lighting temperature, and film art style as Image {len(ref_imgs)}, shown from the new view '{vrec.get('label') or vid}'."
                )
        else:
            directives.append(
                f"BASELINE STYLE & PALETTE LOCK (Image {len(ref_imgs)} is the baselined view of {name}): "
                f"Convert Image 1's architecture into the EXACT color palette, wall/floor materials, lighting, and film art style established in Image {len(ref_imgs)}."
            )

    view_lbl = str(vrec.get("label") or "").strip()
    view_desc = str(vrec.get("notes") or "").strip()
    view_heading = f"{name} — {view_lbl}" if (view_lbl and vid != "main") else name
    if ref_img is not None:
        # When converting an imported photo, convert the image AS-IS into the target art style
        # WITHOUT following the old pre-import text prompt or mentioning unrelated nouns.
        bits: list[str] = list(directives)
    else:
        bits = list(directives) + [
            f"Wide establishing set plate of {view_heading}",
            view_desc,
            desc,
            f"Lighting: {lighting}" if lighting else "",
            style_pos,
            "Empty environment set plate, no people, no characters in frame",
        ]
    if reserve_2d_gaps:
        gap_clause = (
            f"IMPORTANT COMPOSITION: Keep clear empty spaces reserved for 2D cartoon characters to be added later ({gap_notes}). "
            if gap_notes
            else "IMPORTANT COMPOSITION: Leave open empty chairs, open tabletop space, and clear foreground/sky gaps where 2D cartoon characters will live. "
        )
        bits.append(gap_clause + "No people, no characters, empty set plate only.")
        style_neg = ", ".join(x for x in (style_neg, "people, characters, cartoons, crowded foreground, eyes, googly eyes, faces, anthropomorphic, stickers, decals, extra objects") if x)
    else:
        style_neg = ", ".join(x for x in (style_neg, "people, characters, person, crowd, eyes, googly eyes, faces, anthropomorphic, stickers, decals, extra objects") if x)

    prompt = ". ".join(b.rstrip(". ") for b in bits if b)
    model_used = _render_keyframe_local_or_gemini(
        prompt,
        out_png,
        aspect_ratio="16:9",
        ref_images=ref_imgs if ref_imgs else None,
        engine=req_engine,
        seed=-1,
        init_strength=init_strength,
        init_image=init_img,
        prefer_edit=bool(ref_imgs),
        bypass_cache=True,
        extra_negative=style_neg,
    )

    vrec["converted_image"] = out_rel
    _save_sets_views_doc(pd, doc)

    return {
        "status": "ok",
        "name": name,
        "view_id": vid,
        "view_label": vrec.get("label") or view_lbl,
        "image_url": f"/file/{slug}/{out_rel}",
        "converted_url": f"/file/{slug}/{out_rel}",
        "ref_url": f"/file/{slug}/{ref_rel}" if ref_img else "",
        "used_ref_photo": bool(ref_img),
        "used_baseline": bool(baseline_img),
        "baseline_view_id": base_vid if baseline_img else "",
        "rel_path": f"projects/books/{slug}/{out_rel}",
        "model": model_used,
        "reserve_2d_gaps": reserve_2d_gaps,
    }


@route("POST", "/api/v2_set_render")
def _v2_set_render(r: Request):
    """Generate or style-convert a Step 11 establishing set plate / view (honoring imported ref photos & pinned baselines)."""
    slug = str(r.body.get("project") or "").strip()
    name = str(r.body.get("name") or "").strip()
    if not slug or not name:
        raise PlanError("project and set name are required")
    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    raw_ss = r.body.get("style_strength")
    style_strength: float | None = None
    if raw_ss is not None and str(raw_ss).strip() != "":
        try:
            style_strength = max(0.25, min(0.95, float(raw_ss)))
        except (TypeError, ValueError):
            style_strength = None
    return _render_set_view_plate(
        slug,
        pd,
        name,
        view_id=str(r.body.get("view_id") or "main").strip(),
        view_label=str(r.body.get("view_label") or "").strip(),
        view_notes=str(r.body.get("view_notes") or "").strip(),
        desc=str(r.body.get("description") or "").strip(),
        lighting=str(r.body.get("lighting") or "").strip(),
        reserve_2d_gaps=bool(r.body.get("reserve_2d_gaps", False)),
        gap_notes=str(r.body.get("gap_notes") or "").strip(),
        req_engine=str(r.body.get("engine") or "auto").strip().lower(),
        use_ref=bool(r.body.get("use_ref", True)),
        use_baseline=bool(r.body.get("use_baseline", True)),
        style_strength=style_strength,
    )


@route("POST", "/api/v2_set_view_save")
def _v2_set_view_save(r: Request):
    """Add, update, or delete a named view on a Step 11 location (for multi-view sets like living room / kitchen)."""
    slug = str(r.body.get("project") or "").strip()
    name = str(r.body.get("name") or "").strip()
    if not slug or not name:
        raise PlanError("project and set name are required")
    pd = pdir(slug, "book")
    doc = _load_sets_views_doc(pd)
    raw_vid = str(r.body.get("view_id") or "").strip()
    label = str(r.body.get("label") or "").strip()
    notes = str(r.body.get("notes") or "").strip()
    delete_flag = bool(r.body.get("delete", False))

    vid = _safe_view_id(raw_vid or label or "view")
    srec, vrec = _ensure_set_view_entry(doc, name, vid, view_label=label)

    if delete_flag:
        if vid == "main":
            raise PlanError("The primary Establishing View cannot be deleted.")
        srec["views"] = [v for v in (srec.get("views") or []) if v.get("id") != vid]
        if srec.get("baseline_view_id") == vid:
            srec["baseline_view_id"] = ""
            srec["baseline_snapshot"] = ""
        for rel_k in ("ref_image", "converted_image"):
            rel = str(vrec.get(rel_k) or "").strip()
            if rel:
                (pd / rel).unlink(missing_ok=True)
        _save_sets_views_doc(pd, doc)
        return {"status": "ok", "deleted": vid, "name": name}

    if label:
        vrec["label"] = label
    if "notes" in r.body:
        vrec["notes"] = notes
    _save_sets_views_doc(pd, doc)
    return {"status": "ok", "name": name, "view": vrec}


@route("POST", "/api/v2_set_ref_upload")
def _v2_set_ref_upload(r: Request):
    """Import a reference photo and associate it with a Step 11 location + view; optionally convert it into the film's style right away."""

    slug = str(r.body.get("project") or "").strip()
    name = str(r.body.get("name") or "").strip()
    b64 = str(r.body.get("image_base64") or "").strip()
    if not slug or not name or not b64:
        raise PlanError("project, set name, and image_base64 are required")
    from studio_app import upload_validation

    raw, detected_ext = upload_validation.decode_verified_base64(b64, kind="image", min_bytes=64)
    ext = detected_ext if detected_ext in (".png", ".jpg", ".webp") else ".png"

    pd = pdir(slug, "book")
    safe = _safe_set_slug(name)
    raw_vid = str(r.body.get("view_id") or "").strip()
    view_label = str(r.body.get("view_label") or "").strip()
    vid = _safe_view_id(raw_vid or view_label or "main")

    refs_dir = pd / "assets" / "sets" / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    # Remove any old extension variants for this view's ref photo
    for old_ext in (".png", ".jpg", ".jpeg", ".webp"):
        old_p = refs_dir / f"{safe}_{vid}_ref{old_ext}"
        if old_p.is_file():
            old_p.unlink(missing_ok=True)
    ref_rel = f"assets/sets/refs/{safe}_{vid}_ref{ext}"
    (pd / ref_rel).write_bytes(raw)

    doc = _load_sets_views_doc(pd)
    _srec, vrec = _ensure_set_view_entry(doc, name, vid, view_label=view_label)
    vrec["ref_image"] = ref_rel
    if r.body.get("view_notes"):
        vrec["notes"] = str(r.body.get("view_notes") or "").strip()
    _save_sets_views_doc(pd, doc)

    out: dict[str, Any] = {
        "status": "ok",
        "name": name,
        "view_id": vid,
        "view_label": vrec.get("label") or view_label,
        "ref_url": f"/file/{slug}/{ref_rel}",
        "ref_rel": ref_rel,
    }

    if bool(r.body.get("convert_now", False)):
        raw_ss = r.body.get("style_strength")
        style_strength: float | None = None
        if raw_ss is not None and str(raw_ss).strip() != "":
            try:
                style_strength = max(0.25, min(0.95, float(raw_ss)))
            except (TypeError, ValueError):
                style_strength = None
        conv = _render_set_view_plate(
            slug,
            pd,
            name,
            view_id=vid,
            view_label=str(vrec.get("label") or ""),
            view_notes="",
            desc="",
            lighting="",
            reserve_2d_gaps=bool(r.body.get("reserve_2d_gaps", False)),
            gap_notes=str(r.body.get("gap_notes") or "").strip(),
            req_engine=str(r.body.get("engine") or "auto").strip().lower(),
            use_ref=True,
            use_baseline=False,
            style_strength=style_strength,
        )
        out["converted_url"] = conv["converted_url"]
        out["model"] = conv["model"]
        out["used_baseline"] = conv["used_baseline"]

    # Automatically run image-to-text on the imported picture to update the set's prompt/description
    from studio_app import set_vision_sync

    if bool(r.body.get("auto_describe", True)):
        try:
            vision_sync = set_vision_sync.sync_baselined_set_from_image(
                pd,
                slug,
                name,
                pd / ref_rel,
                view_id=vid,
                reconcile_shots=bool(r.body.get("reconcile_shots", True)),
            )
            out["vision_sync"] = vision_sync
            if vision_sync.get("ok"):
                out["description"] = vision_sync.get("description", "")
                out["lighting"] = vision_sync.get("lighting", "")
        except Exception as e:
            log.debug("Auto image-to-text on set import skipped for %s: %s", name, e)

    # Create a bi-directional update queue starting at the earliest inception of this set in the pipeline
    try:
        bidir = set_vision_sync.record_import_bidirectional_sync(
            pd,
            slug,
            kind="set",
            name=name,
            source_step=11,
        )
        out["earliest_inception_step"] = bidir["earliest_inception_step"]
        out["bidirectional_sync"] = bidir
    except Exception as e:
        log.debug("Bi-directional sync on set import skipped for %s: %s", name, e)
    return out


@route("POST", "/api/v2_set_ref_delete")
def _v2_set_ref_delete(r: Request):
    """Remove the imported reference photo from a Step 11 location view without deleting the view."""
    slug = str(r.body.get("project") or "").strip()
    name = str(r.body.get("name") or "").strip()
    vid = _safe_view_id(str(r.body.get("view_id") or "main"))
    if not slug or not name:
        raise PlanError("project and set name are required")
    pd = pdir(slug, "book")
    doc = _load_sets_views_doc(pd)
    _srec, vrec = _ensure_set_view_entry(doc, name, vid)
    rel = str(vrec.get("ref_image") or "").strip()
    if rel:
        (pd / rel).unlink(missing_ok=True)
    vrec["ref_image"] = ""
    _save_sets_views_doc(pd, doc)
    return {"status": "ok", "name": name, "view_id": vid}


@route("POST", "/api/v2_set_image_delete")
def _v2_set_image_delete(r: Request):
    """Delete ONLY the generated/converted set plate image for one Step 11 view without deleting the set, view, or imported reference photo."""
    slug = str(r.body.get("project") or "").strip()
    name = str(r.body.get("name") or "").strip()
    vid = _safe_view_id(str(r.body.get("view_id") or "main"))
    if not slug or not name:
        raise PlanError("project and set name are required")

    pd = pdir(slug, "book")
    safe = _safe_set_slug(name)
    doc = _load_sets_views_doc(pd)
    srec, vrec = _ensure_set_view_entry(doc, name, vid)

    removed = 0
    targets: list[Path] = []
    conv_rel = str(vrec.get("converted_image") or "").strip()
    if conv_rel:
        targets.append(pd / conv_rel)
    sets_dir = pd / "assets" / "sets"
    base_stem = safe if vid == "main" else f"{safe}__view_{vid}"
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        targets.append(sets_dir / f"{base_stem}{ext}")

    seen: set[Path] = set()
    for p in targets:
        try:
            rp = p.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            if p.is_file():
                p.unlink(missing_ok=True)
                removed += 1
        except OSError:
            continue

    vrec["converted_image"] = ""
    cleared_baseline = False
    if str(srec.get("baseline_view_id") or "") == vid:
        snap_rel = str(srec.get("baseline_snapshot") or "").strip()
        if snap_rel:
            (pd / snap_rel).unlink(missing_ok=True)
        srec["baseline_view_id"] = ""
        srec["baseline_snapshot"] = ""
        cleared_baseline = True

    _save_sets_views_doc(pd, doc)
    return {
        "status": "ok",
        "name": name,
        "view_id": vid,
        "removed": removed,
        "cleared_baseline": cleared_baseline,
    }


@route("POST", "/api/v2_set_baseline")
def _v2_set_baseline(r: Request):
    """Pin any Step 11 view as the location's Baseline image (snapshotted so future re-runs & other views lock to it), or clear baseline."""
    import shutil

    slug = str(r.body.get("project") or "").strip()
    name = str(r.body.get("name") or "").strip()
    raw_vid = str(r.body.get("view_id") or "").strip()
    if not slug or not name:
        raise PlanError("project and set name are required")

    pd = pdir(slug, "book")
    safe = _safe_set_slug(name)
    doc = _load_sets_views_doc(pd)
    srec, _main = _ensure_set_view_entry(doc, name, "main")

    # Clear baseline when view_id is empty
    if not raw_vid:
        old_snap = str(srec.get("baseline_snapshot") or "").strip()
        if old_snap:
            (pd / old_snap).unlink(missing_ok=True)
        srec["baseline_view_id"] = ""
        srec["baseline_snapshot"] = ""
        _save_sets_views_doc(pd, doc)
        return {"status": "ok", "name": name, "baseline_view_id": "", "baseline_url": ""}

    vid = _safe_view_id(raw_vid)
    srec, vrec = _ensure_set_view_entry(doc, name, vid)

    # Prefer the view's converted film-style plate (fallback to legacy assets/sets/<safe>.png for main, or imported ref)
    src_path: Path | None = None
    for cand_rel in (
        str(vrec.get("converted_image") or "").strip(),
        f"assets/sets/{safe}.png" if vid == "main" else f"assets/sets/{safe}__view_{vid}.png",
        str(vrec.get("ref_image") or "").strip(),
    ):
        if cand_rel:
            p = pd / cand_rel
            if p.is_file() and p.stat().st_size > 100:
                src_path = p
                break

    if src_path is None:
        raise PlanError(f"Generate or import an image for view '{vrec.get('label') or vid}' before setting it as baseline.")

    snap_rel = f"assets/sets/{safe}_baseline.png"
    snap_path = pd / snap_rel
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, snap_path)

    srec["baseline_view_id"] = vid
    srec["baseline_snapshot"] = snap_rel
    _save_sets_views_doc(pd, doc)

    vision_sync: dict[str, Any] = {"ok": False, "updated_steps": []}
    if bool(r.body.get("auto_analyze", True)):
        try:
            from studio_app import set_vision_sync
            vision_sync = set_vision_sync.sync_baselined_set_from_image(
                pd,
                slug,
                name,
                snap_path,
                reconcile_shots=bool(r.body.get("reconcile_shots", True)),
            )
        except Exception as e:
            log.debug("Auto set vision sync skipped for %s: %s", name, e)

    return {
        "status": "ok",
        "name": name,
        "baseline_view_id": vid,
        "baseline_label": vrec.get("label") or vid,
        "baseline_url": f"/file/{slug}/{snap_rel}",
        "vision_sync": vision_sync,
    }


@route("POST", "/api/v2_set_analyze_sync")
def _v2_set_analyze_sync(r: Request):
    """Run image-to-text analysis on a Step 11 baselined (or active) set image and feed it back to Steps 07, 11, 12, and 17."""
    from studio_app import set_vision_sync

    slug = str(r.body.get("project") or "").strip()
    name = str(r.body.get("name") or "").strip()
    if not slug or not name:
        raise PlanError("project and set name are required")

    pd = pdir(slug, "book")
    safe = _safe_set_slug(name)
    doc = _load_sets_views_doc(pd)
    srec, main_v = _ensure_set_view_entry(doc, name, "main")

    # Resolve the best visual set plate to analyze (prefer pinned baseline -> converted main -> legacy file -> imported ref)
    img_path: Path | None = None
    for cand_rel in (
        str(srec.get("baseline_snapshot") or "").strip(),
        str(main_v.get("converted_image") or "").strip(),
        f"assets/sets/{safe}_baseline.png",
        f"assets/sets/{safe}.png",
        str(main_v.get("ref_image") or "").strip(),
    ):
        if cand_rel:
            p = pd / cand_rel
            if p.is_file() and p.stat().st_size > 100:
                img_path = p
                break
    if img_path is None:
        raise PlanError(f"No baselined or rendered set image found for '{name}'. Import or generate a set plate first.")

    res = set_vision_sync.sync_baselined_set_from_image(
        pd,
        slug,
        name,
        img_path,
        reconcile_shots=bool(r.body.get("reconcile_shots", True)),
    )
    if not res.get("ok"):
        raise PlanError(str(res.get("error") or "Could not analyze set image."))
    return {"status": "ok", "name": name, "image_analyzed": img_path.name, **res}


@route("POST", "/api/v2_set_restore")
def _v2_set_restore(r: Request):
    """Unhide a previously deleted Step 11 set name when the user explicitly re-adds it."""
    slug = str(r.body.get("project") or "").strip()
    name = str(r.body.get("name") or "").strip()
    if not slug or not name:
        raise PlanError("project and set name are required")
    pd = pdir(slug, "book")
    order, deleted = _load_sets_state(pd)
    key = name.lower()
    deleted = [x for x in deleted if x != key]
    order, deleted = _save_sets_state(pd, order, deleted)
    return {"status": "ok", "name": name, "deleted": deleted, "order": order}


@route("POST", "/api/v2_turnaround_delete")
def _v2_turnaround_delete(r: Request):
    """Delete one individual turnaround image so it is no longer used as a visual reference."""
    slug = str(r.body.get("project") or "").strip()
    char_name = str(r.body.get("character") or "").strip()
    view = str(r.body.get("view") or "").strip().lower()
    outfit_id = "".join(c for c in str(r.body.get("outfit_id") or "default").strip().lower() if c.isalnum() or c in "_-") or "default"
    if not slug or not char_name or view not in ("front", "three_quarter", "profile"):
        raise PlanError("project, character, and valid view are required")

    pd = pdir(slug, "book")
    safe = "".join(c if c.isalnum() else "_" for c in char_name.lower()).strip("_") or "char"
    t_dir = pd / "assets" / "turnarounds"
    removed = 0
    targets = [t_dir / (f"{safe}_{view}.png" if outfit_id == "default" else f"{safe}_{outfit_id}_{view}.png")]
    if outfit_id == "outfit1":
        targets.append(t_dir / f"{safe}_{view}.png")
    for p in targets:
        if p.is_file():
            p.unlink(missing_ok=True)
            removed += 1
    return {"status": "ok", "character": char_name, "outfit_id": outfit_id, "view": view, "removed": removed}


@route("POST", "/api/v2_postprod_save")
def _v2_postprod_save(r: Request):
    """Save Steps 19-21 polish, timeline, and audio mix settings to postprod_v2.json."""
    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    pd.mkdir(parents=True, exist_ok=True)
    pp_path = pd / "postprod_v2.json"
    cur: dict[str, Any] = {}
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
    cur: dict[str, Any] = {}
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
    for dlg_file in dlg_files[:20]:
        try:
            dlg_track.extend(_read_mono_22k(dlg_file))
            dlg_track.extend(gap)
        except Exception as e:
            log.debug("skipping dialogue file %s: %s", dlg_file.name, e)
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

    lufs_info: dict[str, Any] = {}
    if bool(r.body.get("normalize_lufs", False)):
        import audio_first_clock
        target_lufs = float(r.body.get("lufs", -14.0))
        norm_tmp = out_dir / "master_mix_norm.wav"
        norm_res = audio_first_clock.normalize_to_lufs(out_wav, norm_tmp, target_lufs=target_lufs)
        if norm_res.get("ok") and norm_tmp.is_file():
            norm_tmp.replace(out_wav)
            lufs_info = {
                "normalized": True,
                "target_lufs": target_lufs,
                "before_lufs": norm_res.get("before_lufs"),
                "after_lufs": norm_res.get("after_lufs"),
                "true_peak_db": norm_res.get("after_true_peak_db"),
            }

    return {
        "status": "ok",
        "audio_url": f"/file/{slug}/audio/mix/master_mix.wav",
        "duration_sec": round(total_len / 22050.0, 1),
        "stems": {"dialogue_files": len(dlg_files), "foley": foley_file.is_file(), "score": score_file.is_file()},
        "lufs_master": lufs_info,
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
                except Exception as e:
                    log.debug("skipping unreadable scene %s: %s", sf.name, e)
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

    if target in ("otio", "kdenlive"):
        import external_tools

        res = external_tools.export_otio_and_kdenlive(pd, slug)
        chosen = res["kdenlive_path"] if target == "kdenlive" else res["otio_path"]
        return {
            "status": "ok",
            "target": target,
            "clips": res["clip_count"],
            "used_otio_lib": res["used_otio_lib"],
            "download_url": f"/download/{slug}/exports/{chosen.name}",
            "otio_url": f"/download/{slug}/exports/{res['otio_path'].name}",
            "kdenlive_url": f"/download/{slug}/exports/{res['kdenlive_path'].name}",
        }

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
            subprocess.run(cmd, stdin=subprocess.DEVNULL, check=True, timeout=180)
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
            subprocess.run(cmd, stdin=subprocess.DEVNULL, check=True, timeout=180)
        else:
            raise PlanError("No video clips (Step 18) or storyboard keyframes (Step 17) rendered yet to assemble.")

        import post_tools
        if target == "shorts_9x16" and bool(r.body.get("auto_reframe")):
            master_cand = films_dir / "master_cut.mp4"
            if master_cand.is_file():
                rf_res = post_tools.auto_reframe({"input_path": str(master_cand), "output_path": str(out_mp4), "target_aspect": "portrait"})
                if not rf_res.get("success", False):
                    log.debug("auto_reframe fallback: %s", rf_res.get("error"))

        if bool(r.body.get("silence_cut")) and out_mp4.is_file():
            sc_tmp = films_dir / f".tmp_sc_{out_mp4.name}"
            sc_res = post_tools.silence_cutter({"input_path": str(out_mp4), "output_path": str(sc_tmp), "mode": "remove"})
            if sc_res.get("success") and sc_tmp.is_file() and sc_tmp.stat().st_size > 0:
                sc_tmp.replace(out_mp4)
            else:
                sc_tmp.unlink(missing_ok=True)

        captions_burned = 0
        if bool(r.body.get("burn_captions")) and out_mp4.is_file():
            import audio_first_clock
            clock_json = pd / "exports" / "captions" / "audio_first_clock.json"
            if clock_json.is_file():
                try:
                    cues = (json.loads(clock_json.read_text(encoding="utf-8")) or {}).get("cues") or []
                except Exception:
                    cues = []
            else:
                cues = audio_first_clock.build_audio_first_clock(slug, pd, use_whisper=False).get("cues") or []
            if cues:
                cap_tmp = films_dir / f".tmp_cap_{out_mp4.name}"
                burn_res = audio_first_clock.burn_safe_captions_mp4(
                    out_mp4, cap_tmp, cues, is_vertical=(target == "shorts_9x16")
                )
                if burn_res.get("ok") and cap_tmp.is_file() and cap_tmp.stat().st_size > 0:
                    cap_tmp.replace(out_mp4)
                    captions_burned = int(burn_res.get("cues_burned") or len(cues))
                else:
                    cap_tmp.unlink(missing_ok=True)

        return {
            "status": "ok",
            "target": target,
            "captions_burned": captions_burned,
            "video_url": f"/file/{slug}/films/{out_mp4.name}",
            "download_url": f"/download/{slug}/films/{out_mp4.name}",
        }

    if target == "pitch_pptx":
        import studio_exports_office
        return studio_exports_office.export_pitch_deck_pptx(slug, pd)

    if target == "prod_xlsx":
        import studio_exports_office
        return studio_exports_office.export_production_sheet_xlsx(slug, pd)

    raise PlanError(f"Unknown export target: {target}")


@route("POST", "/api/v2_video_render")
def _v2_video_render(r: Request):
    """Synthesize a Step 18 shot video clip using WanDiffusersRunner, Wan2GPRunner, ComfyUIRunner, or local FFmpeg motion animatic."""
    from local_runners.wan2gp_runner import Wan2GPRunner
    from local_runners.wan_diffusers_runner import WanDiffusersRunner
    import post_tools
    from .gpus import gpu_profile

    slug = str(r.body.get("project") or "").strip()
    shot_id = "".join(c for c in str(r.body.get("id") or "S001-01").strip() if c.isalnum() or c in "-_")
    if not slug or not shot_id:
        raise PlanError("project and shot id are required")

    pd = pdir(slug, "book")
    vid_dir = pd / "videos"
    vid_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = vid_dir / f"{shot_id}.mp4"
    rel_url = f"/file/{slug}/videos/{shot_id}.mp4"

    kf_png = pd / "keyframes" / f"{shot_id}.png"
    prompt = str(r.body.get("prompt") or f"Cinematic shot {shot_id}").strip()
    duration = max(2, min(30, int(r.body.get("duration") or 4)))
    engine = str(r.body.get("engine") or "auto").strip().lower()
    prof = gpu_profile()

    if engine in ("wan_diffusers", "wan2gp") and prof.get("tier") == "mac_8g_lite":
        raise PlanError(
            f"Local video engine '{engine}' is gated off on 8 GB Apple Silicon Mac (mac_8g_lite). "
            "Select 'Local FFmpeg Motion Animatic' or run on the 48 GB Windows RTX 5090 PC."
        )

    runner_used = ""
    if engine == "wan_diffusers":
        w_runner = WanDiffusersRunner()
        if w_runner.is_installed():
            op = "image_to_video" if kf_png.is_file() else "text_to_video"
            w_runner.run({
                "operation": op,
                "prompt": prompt,
                "reference_image_path": str(kf_png) if kf_png.is_file() else None,
                "duration_seconds": float(duration),
                "output_path": str(out_mp4),
                "profile": prof,
            })
            runner_used = "wan_diffusers"
    elif engine == "wan2gp":
        wgp = Wan2GPRunner()
        if wgp.is_installed():
            wgp.run({
                "model_id": "wan2gp:wan22-i2v" if kf_png.is_file() else "wan2gp:wan21-t2v-1.3b",
                "prompt": prompt,
                "image_start": str(kf_png) if kf_png.is_file() else None,
                "output_dir": str(vid_dir),
                "profile": prof,
            })
            runner_used = "wan2gp"

    if not runner_used or not out_mp4.is_file():
        if not kf_png.is_file():
            _synthesize_local_preview_png(prompt, kf_png, aspect_ratio="16:9")
        ffmpeg = post_tools._ffmpeg_bin()
        cmd = [
            ffmpeg,
            "-v",
            "error",
            "-y",
            "-loop",
            "1",
            "-i",
            str(kf_png),
            "-t",
            str(duration),
            "-vf",
            "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "24",
            str(out_mp4),
        ]
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise PlanError(f"Local motion clip synthesis failed: {proc.stderr[-250:]}")
        runner_used = "local_animatic"

    return {
        "status": "ok",
        "id": shot_id,
        "video_url": rel_url,
        "engine": runner_used,
        "duration": duration,
    }


@route("POST", "/api/character_types_custom")
def _character_types_custom(r: Request):
    """Create or update a custom visual style or custom character archetype."""
    import character_types_registry as ctr
    import production

    kind = str(r.body.get("kind") or "style").strip().lower()
    try:
        if kind == "archetype":
            saved = ctr.save_custom_archetype(r.body)
        else:
            saved = ctr.save_custom_style(r.body)
            production.refresh_styles()
    except ValueError as e:
        raise PlanError(str(e)) from e
    return {"status": "ok", "kind": kind, "saved": saved, "registry": ctr.registry_payload()}


@route("POST", "/api/v2_character_ref_upload")
def _v2_character_ref_upload(r: Request):
    """Upload a Step 08 reference picture for a cast member and make it available to Step 10, Step 17, and Single Prompts."""
    import character_identity

    slug = str(r.body.get("project") or "").strip()
    char_name = str(r.body.get("character") or "").strip()
    b64 = str(r.body.get("image_base64") or "").strip()
    if not slug or not char_name or not b64:
        raise PlanError("project, character, and image_base64 are required")
    from studio_app import upload_validation

    raw, _img_ext = upload_validation.decode_verified_base64(b64, kind="image", min_bytes=64)

    pd = pdir(slug, "book")
    safe = character_identity.safe_char_slug(char_name)
    ref_dir = pd / "assets" / "cast_refs"
    ref_dir.mkdir(parents=True, exist_ok=True)
    ref_png = ref_dir / f"{safe}_ref.png"
    ref_png.write_bytes(raw)

    # Also copy into Step 10 Front View if none exists yet (or explicitly requested), unless convert_now will generate the stylized Front View
    t_dir = pd / "assets" / "turnarounds"
    t_dir.mkdir(parents=True, exist_ok=True)
    front_png = t_dir / f"{safe}_front.png"
    convert_now = bool(r.body.get("convert_now", False))
    seeded_front = False
    if not convert_now and (bool(r.body.get("set_as_front", False)) or not (front_png.is_file() and front_png.stat().st_size > 100)):
        front_png.write_bytes(raw)
        seeded_front = True

    # Register in character dossier JSON
    repo_root = pd.parent.parent.parent
    rel_repo = ref_png.relative_to(repo_root).as_posix()
    existing = character_tokens.load_character(slug, char_name)
    if isinstance(existing, dict):
        refs_list = [str(x) for x in (existing.get("reference_images") or []) if str(x) != rel_repo]
        refs_list.insert(0, rel_repo)
        existing["reference_images"] = refs_list
        character_tokens.save_character(existing)

    out: dict[str, Any] = {
        "status": "ok",
        "character": char_name,
        "image_url": f"/file/{slug}/assets/cast_refs/{safe}_ref.png",
        "ref_url": f"/file/{slug}/assets/cast_refs/{safe}_ref.png",
        "rel_path": rel_repo,
        "seeded_front": seeded_front,
    }

    if convert_now:
        import character_types_registry as ctr

        req_style = str(r.body.get("style_id") or r.body.get("target_style") or "").strip()
        if not req_style and isinstance(existing, dict):
            req_style = str(existing.get("style_override") or "").strip()
        book_look, book_pos, book_neg, _book_is_photo = _resolve_set_film_style(pd)
        using_book_default = not req_style
        if not req_style:
            req_style = book_look or "pixar_3d"
        st = ctr.get_style(req_style) or ctr.get_style("pixar_3d") or {"id": req_style, "name": req_style, "positives": book_pos or req_style, "negatives": book_neg}
        eff_pos = book_pos if (using_book_default and book_pos) else str(st.get("positives") or st.get("name") or req_style)
        eff_neg = book_neg if (using_book_default and book_neg) else str(st.get("negatives") or "")

        raw_ss = r.body.get("style_strength")
        eff_strength: float = 0.75
        if raw_ss is not None and str(raw_ss).strip() != "":
            try:
                eff_strength = max(0.35, min(0.95, float(raw_ss)))
            except (TypeError, ValueError):
                eff_strength = 0.75

        restyle_base = str(st.get("restyle_prompt") or f"Complete style transformation into {st['name']} style: {eff_pos}")
        # Convert the imported photo AS-IS into the target art style WITHOUT following the original character prompt
        # or introducing unrelated nouns into the positive prompt.
        prompt = (
            f"{eff_pos}. {restyle_base}. Stylized animated movie rendering of Image 1 AS-IS — "
            f"re-render only the exact subject, framing, pose, expression, features, colors, clothing, and background already visible in Image 1 "
            f"entirely in {st['name']} stylized animated art, with smooth stylized materials and clean animated film shading. "
            "Keep the exact framing, pose, and background of Image 1 unchanged."
        )
        req_engine = str(r.body.get("engine") or "auto").strip().lower()
        model_used = _render_keyframe_local_or_gemini(
            prompt,
            front_png,
            aspect_ratio="1:1",
            ref_images=[ref_png],
            engine=req_engine,
            view="front",
            seed=-1,
            init_strength=eff_strength,
            init_image=ref_png,
            require_ref=True,
            bypass_cache=True,
            extra_negative=eff_neg,
        )
        out["converted_url"] = f"/file/{slug}/assets/turnarounds/{safe}_front.png"
        out["model"] = model_used
        out["style_id"] = str(st.get("id") or req_style)
        out["style_name"] = str(st.get("name") or req_style)
        out["seeded_front"] = True

    # Automatically run image-to-text on the imported photo to update the character's prompt/description & continuity token
    from studio_app import set_vision_sync

    if bool(r.body.get("auto_describe", True)):
        try:
            vision_sync = set_vision_sync.sync_character_from_imported_image(
                pd,
                slug,
                char_name,
                ref_png,
            )
            out["vision_sync"] = vision_sync
            if vision_sync.get("ok"):
                out["description"] = vision_sync.get("description", "")
                out["token"] = vision_sync.get("token", "")
        except Exception as e:
            log.debug("Auto image-to-text on character import skipped for %s: %s", char_name, e)

    # Create a bi-directional update queue starting at the earliest inception of this character in the pipeline
    try:
        bidir = set_vision_sync.record_import_bidirectional_sync(
            pd,
            slug,
            kind="character",
            name=char_name,
            source_step=8,
        )
        out["earliest_inception_step"] = bidir["earliest_inception_step"]
        out["bidirectional_sync"] = bidir
    except Exception as e:
        log.debug("Bi-directional sync on character import skipped for %s: %s", char_name, e)

    return out


@route("POST", "/api/v2_character_ref_delete")
def _v2_character_ref_delete(r: Request):
    """Remove an uploaded Step 08 cast reference picture."""
    import character_identity

    slug = str(r.body.get("project") or "").strip()
    char_name = str(r.body.get("character") or "").strip()
    if not slug or not char_name:
        raise PlanError("project and character are required")
    pd = pdir(slug, "book")
    safe = character_identity.safe_char_slug(char_name)
    ref_dir = pd / "assets" / "cast_refs"
    removed = 0
    if ref_dir.is_dir():
        for p in ref_dir.glob(f"{safe}_ref.*"):
            if p.is_file():
                p.unlink(missing_ok=True)
                removed += 1
    existing = character_tokens.load_character(slug, char_name)
    if isinstance(existing, dict):
        existing["reference_images"] = [
            str(x) for x in (existing.get("reference_images") or [])
            if f"{safe}_ref." not in str(x)
        ]
        character_tokens.save_character(existing)
    return {"status": "ok", "character": char_name, "removed": removed}


@route("POST", "/api/v2_turnaround_restyle")
def _v2_turnaround_restyle(r: Request):
    """One-click restyle of an existing Step 10 Front View into any visual style using FLUX.2-klein-4B reference conditioning."""
    import character_identity
    import character_types_registry as ctr

    slug = str(r.body.get("project") or "").strip()
    char_name = str(r.body.get("character") or "").strip()
    style_id = str(r.body.get("style_id") or r.body.get("target_style") or "").strip()
    outfit_id = "".join(c for c in str(r.body.get("outfit_id") or "default").strip().lower() if c.isalnum() or c in "_-") or "default"
    if not slug or not char_name:
        raise PlanError("project and character are required")

    pd = pdir(slug, "book")
    if not style_id:
        book_look, _sp, _sn, _ip = _resolve_set_film_style(pd)
        style_id = book_look or "pixar_3d"
    st = ctr.get_style(style_id)
    if not st:
        raise PlanError(f"Unknown visual style: {style_id}")

    safe = character_identity.safe_char_slug(char_name)
    t_dir = pd / "assets" / "turnarounds"
    fname = f"{safe}_front.png" if outfit_id == "default" else f"{safe}_{outfit_id}_front.png"
    target_png = t_dir / fname
    if not (target_png.is_file() and target_png.stat().st_size > 100):
        # Fall back to legacy base front view
        alt = t_dir / f"{safe}_front.png"
        if alt.is_file() and alt.stat().st_size > 100:
            target_png = alt
            fname = alt.name
        else:
            raise PlanError(f"Generate or upload a Front View of {char_name} first before restyling.")

    # Copy original front view to temp ref so we can overwrite target_png cleanly
    import tempfile
    req_engine = str(r.body.get("engine") or "auto").strip().lower()
    restyle_base = str(st.get("restyle_prompt") or f"Complete style transformation into {st['name']} style: {st['positives']}")
    prompt = (
        f"{restyle_base}. Transform the person/character in Image 1 ({char_name}) completely into {st['name']} style — "
        "translate their recognizable likeness, hairstyle, expression, glasses/accessories, and exact outfit into stylized animated character design "
        "(NOT a real-world photograph, NOT realistic human skin or camera photography). "
        "Centered full-body straight-on front-facing view standing alone head to toe on a clean solid light-gray studio backdrop, no text or numbers."
    )
    # Prefer the character's uploaded Step 08 reference photo when explicitly requested or when target front view is missing
    cast_ref_dir = pd / "assets" / "cast_refs"
    uploaded_cast_ref = next(
        (cast_ref_dir / f"{safe}_ref{ext}" for ext in (".png", ".jpg", ".jpeg", ".webp") if (cast_ref_dir / f"{safe}_ref{ext}").is_file()),
        None,
    )
    source_img = uploaded_cast_ref if (bool(r.body.get("use_cast_ref", False)) and uploaded_cast_ref is not None) else target_png
    with tempfile.TemporaryDirectory(prefix="neon-restyle-") as tmp_dir:
        src_ref = Path(tmp_dir) / "source_front.png"
        src_ref.write_bytes(source_img.read_bytes())
        model_used = _render_keyframe_local_or_gemini(
            prompt,
            target_png,
            aspect_ratio="1:1",
            ref_images=[src_ref],
            engine=req_engine,
            view="front",
            seed=-1,
            require_ref=True,
            bypass_cache=True,
            extra_negative=str(st.get("negatives") or ""),
        )
    return {
        "status": "ok",
        "character": char_name,
        "outfit_id": outfit_id,
        "style_id": st["id"],
        "style_name": st["name"],
        "image_url": f"/file/{slug}/assets/turnarounds/{fname}",
        "model": model_used,
    }


@route("POST", "/api/v2_single_prompt_render")
def _v2_single_prompt_render(r: Request):
    """Direct reference-aware Single Prompt generator (Image or Video) using a cast reference photo or uploaded image."""
    import time as _time
    import character_types_registry as ctr
    import post_tools
    from local_runners.wan2gp_runner import Wan2GPRunner
    from local_runners.wan_diffusers_runner import WanDiffusersRunner
    from .gpus import gpu_profile

    set_name = "".join(c if (c.isalnum() or c == "_") else "_" for c in str(r.body.get("set") or "my_prompts").strip().lower()).strip("_") or "my_prompts"
    prompt_raw = str(r.body.get("prompt") or "").strip()
    if not prompt_raw:
        raise PlanError("Enter a prompt first.")
    mode = str(r.body.get("mode") or "image").strip().lower()
    if mode not in ("image", "video"):
        raise PlanError("mode must be 'image' or 'video'")
    aspect_ratio = str(r.body.get("aspect_ratio") or r.body.get("aspect") or ("16:9" if mode == "video" else "1:1")).strip()
    neg_raw = str(r.body.get("negative_prompt") or r.body.get("negative") or "").strip()
    style_id = str(r.body.get("style_id") or "").strip()
    duration = max(2, min(16, int(r.body.get("duration") or r.body.get("duration_sec") or 4)))
    req_engine = str(r.body.get("engine") or "auto").strip().lower()

    set_dir = ROOT / "projects" / "prompts" / set_name
    set_dir.mkdir(parents=True, exist_ok=True)
    stamp = _time.strftime("%Y%m%d_%H%M%S")

    # Resolve one or more reference images from uploaded base64(s) AND/OR cast/set reference path(s)
    ref_pngs: list[Path] = []
    refs_dir = set_dir / "refs"

    def _save_b64_ref(raw_b64: str, idx: int) -> None:
        from studio_app import upload_validation

        s = str(raw_b64 or "").strip()
        if not s:
            return
        raw, _img_ext = upload_validation.decode_verified_base64(s, kind="image", min_bytes=64)
        refs_dir.mkdir(parents=True, exist_ok=True)
        rp = refs_dir / f"ref_{stamp}_{idx}.png"
        rp.write_bytes(raw)
        ref_pngs.append(rp)

    def _add_rel_ref(rel_str: str) -> None:
        s = str(rel_str or "").strip()
        if not s:
            return
        cand = (ROOT / s.lstrip("/")).resolve()
        proj_root = (ROOT / "projects").resolve()
        try:
            cand.relative_to(proj_root)
        except ValueError as e:
            raise PlanError("reference image must be inside projects/") from e
        if not (cand.is_file() and cand.stat().st_size > 100):
            raise PlanError(f"reference image not found: {s}")
        if cand not in ref_pngs:
            ref_pngs.append(cand)

    if r.body.get("image_base64"):
        _save_b64_ref(str(r.body["image_base64"]), 0)
    for idx_ex, ex_b64 in enumerate(r.body.get("extra_images_base64") or [], start=1):
        _save_b64_ref(str(ex_b64), idx_ex)
    if r.body.get("ref_path"):
        _add_rel_ref(str(r.body["ref_path"]))
    for rp_str in r.body.get("ref_paths") or []:
        _add_rel_ref(str(rp_str))

    ref_png: Path | None = ref_pngs[0] if ref_pngs else None

    st = ctr.get_style(style_id) if style_id else None
    style_pos = str(st.get("positives") or "") if st else ""
    style_neg = str(st.get("negatives") or "") if st else ""
    motion_cadence = str(st.get("motion_cadence") or "") if st else ""

    full_neg = ", ".join(x for x in (neg_raw, style_neg) if x)
    if len(ref_pngs) > 1:
        img_prompt = (
            f"Combine all {len(ref_pngs)} attached reference sheets/images seamlessly, preserving every character's exact face, outfit, proportions, and visual style (keeping real actors photorealistic and 2D cartoon characters hand-drawn where applicable). "
            f"{prompt_raw}"
        )
    elif ref_png is not None:
        img_prompt = (
            "Keep the exact same character/subject identity, face, hair, clothing details, and proportions from the attached reference image. "
            f"{prompt_raw}"
        )
    else:
        img_prompt = prompt_raw
    if style_pos:
        img_prompt = f"{img_prompt}. Style: {style_pos}"

    img_dir = set_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    out_img = img_dir / f"single_{stamp}.png"
    img_url = f"/file/{set_name}/images/{out_img.name}"

    if mode == "image":
        model_used = _render_keyframe_local_or_gemini(
            img_prompt,
            out_img,
            aspect_ratio=aspect_ratio,
            ref_images=ref_pngs if ref_pngs else None,
            engine=req_engine,
            seed=-1,
            require_ref=bool(ref_pngs),
            bypass_cache=True,
            extra_negative=full_neg,
        )
        return {
            "status": "ok",
            "mode": "image",
            "set": set_name,
            "url": img_url,
            "image_url": img_url,
            "model": model_used,
            "style_id": style_id,
            "used_reference": bool(ref_pngs),
            "reference_count": len(ref_pngs),
        }

    # Mode == "video": build or reuse opening frame from reference image(s) + prompt, then animate
    use_ref_directly = bool(r.body.get("use_ref_as_start_frame", False)) and ref_png is not None
    start_frame: Path
    start_frame_url = ""
    img_model = ""
    if use_ref_directly and ref_png is not None:
        start_frame = ref_png
    else:
        img_model = _render_keyframe_local_or_gemini(
            img_prompt,
            out_img,
            aspect_ratio=aspect_ratio,
            ref_images=ref_pngs if ref_pngs else None,
            engine=req_engine,
            seed=-1,
            require_ref=bool(ref_pngs),
            bypass_cache=True,
            extra_negative=full_neg,
        )
        start_frame = out_img
        start_frame_url = img_url

    vid_dir = set_dir / "videos"
    vid_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = vid_dir / f"single_{stamp}.mp4"
    vid_url = f"/file/{set_name}/videos/{out_mp4.name}"
    vid_prompt = f"{prompt_raw}. Motion cadence: {motion_cadence}" if motion_cadence else prompt_raw
    prof = gpu_profile()
    runner_used = ""

    if prof.get("tier") != "mac_8g_lite":
        if req_engine in ("auto", "wan_diffusers", "local"):
            try:
                w_runner = WanDiffusersRunner()
                if w_runner.is_installed():
                    w_runner.run({
                        "operation": "image_to_video",
                        "prompt": vid_prompt,
                        "reference_image_path": str(start_frame),
                        "duration_seconds": float(duration),
                        "output_path": str(out_mp4),
                        "profile": prof,
                    })
                    if out_mp4.is_file() and out_mp4.stat().st_size > 100:
                        runner_used = "wan_diffusers"
            except Exception as e:
                log.warning("single prompt wan_diffusers failed: %s", e)
        if not runner_used and req_engine in ("auto", "wan2gp", "local"):
            try:
                wgp = Wan2GPRunner()
                if wgp.is_installed():
                    wgp.run({
                        "model_id": "wan2gp:wan22-i2v",
                        "prompt": vid_prompt,
                        "image_start": str(start_frame),
                        "output_dir": str(vid_dir),
                        "profile": prof,
                    })
                    if out_mp4.is_file() and out_mp4.stat().st_size > 100:
                        runner_used = "wan2gp"
            except Exception as e:
                log.warning("single prompt wan2gp failed: %s", e)

    if not runner_used or not out_mp4.is_file():
        # Smooth camera Ken Burns / gentle push-in animatic fallback using FFmpeg so a playable MP4 is always returned
        ffmpeg = post_tools._ffmpeg_bin()
        frames = duration * 24
        vf = (
            f"scale=1280:720:force_original_aspect_ratio=decrease,"
            f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
            f"zoompan=z='min(zoom+0.0012,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x720:fps=24"
        )
        cmd = [
            ffmpeg, "-v", "error", "-y",
            "-i", str(start_frame),
            "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "24",
            str(out_mp4),
        ]
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise PlanError(f"Video synthesis failed: {proc.stderr[-250:]}")
        runner_used = "local_i2v_animatic"

    return {
        "status": "ok",
        "mode": "video",
        "set": set_name,
        "url": vid_url,
        "video_url": vid_url,
        "start_frame_url": start_frame_url,
        "image_model": img_model,
        "model": runner_used,
        "style_id": style_id,
        "duration": duration,
        "used_reference": bool(ref_pngs),
        "reference_count": len(ref_pngs),
    }


@route("POST", "/api/v2_turnaround_sheet")
def _v2_turnaround_sheet(r: Request):
    """Generate a 4:3 3-Panel Pro Character Sheet (Front Close-Up Portrait | Full Body Front | Full Body Back)
    following the 2D-Meets-Realism workflow — works from an uploaded photo (Realistic Sheet) OR for 2D/stylized cast."""
    import character_identity
    import character_types_registry as ctr

    slug = str(r.body.get("project") or "").strip()
    char_name = str(r.body.get("character") or "").strip()
    if not slug or not char_name:
        raise PlanError("project and character are required")
    outfit_id = "".join(c for c in str(r.body.get("outfit_id") or "default").strip().lower() if c.isalnum() or c in "_-") or "default"
    desc = str(r.body.get("desc") or "").strip()
    wardrobe = str(r.body.get("wardrobe") or "").strip()
    sheet_mode = str(r.body.get("sheet_mode") or "auto").strip().lower()
    req_engine = str(r.body.get("engine") or "auto").strip().lower()

    pd = pdir(slug, "book")
    safe = character_identity.safe_char_slug(char_name)
    t_dir = pd / "assets" / "turnarounds"
    t_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{safe}_sheet.png" if outfit_id == "default" else f"{safe}_{outfit_id}_sheet.png"
    out_png = t_dir / fname

    # Resolve style: explicit style_id -> sheet_mode -> character style_override -> hybrid_mode -> book look
    look = str(r.body.get("style_id") or "").strip()
    gp_doc: dict[str, Any] = {}
    gp_path = pd / "global_params.json"
    if gp_path.is_file():
        try:
            gp_doc = json.loads(gp_path.read_text(encoding="utf-8")) or {}
        except Exception:
            gp_doc = {}
    raw_hm_sh = gp_doc.get("hybrid_mode")
    hm: dict[str, Any] = raw_hm_sh if isinstance(raw_hm_sh, dict) else {}

    full_ch = character_tokens.load_character(slug, char_name)
    if not look:
        if sheet_mode == "realistic":
            look = str(hm.get("live_style") or "live_action")
        elif sheet_mode == "2d":
            look = str(hm.get("cartoon_style") or "vintage_1940s_2d")
        elif isinstance(full_ch, dict) and str(full_ch.get("style_override") or "").strip():
            look = str(full_ch["style_override"]).strip()
        elif hm.get("enabled"):
            look = str(hm.get("cartoon_style") or "vintage_1940s_2d")
        else:
            look = str(r.body.get("look") or gp_doc.get("look") or "live_action")

    st = ctr.get_style(look)
    style_pos = str((st or {}).get("positives") or "photorealistic studio portrait")
    style_neg = str((st or {}).get("negatives") or "")

    # Gather best available reference image (Step 08 uploaded photo -> Step 10 Front View)
    ref_list: list[Path] = []
    cast_ref_dir = pd / "assets" / "cast_refs"
    if cast_ref_dir.is_dir():
        for cand in sorted(cast_ref_dir.glob(f"{safe}_ref.*")):
            if cand.is_file() and cand.stat().st_size > 100:
                ref_list.append(cand)
                break
    if not ref_list:
        for cand in (t_dir / f"{safe}_{outfit_id}_front.png", t_dir / f"{safe}_front.png"):
            if cand.is_file() and cand.stat().st_size > 100:
                ref_list.append(cand)
                break

    subject = f"{char_name}"
    if desc:
        subject += f" ({desc})"
    if wardrobe and wardrobe.lower() not in desc.lower():
        subject += f", wearing {wardrobe}"

    ref_clause = (
        "Character sheet of the exact person/character in the reference photo: "
        if ref_list
        else f"Character sheet of {subject}: "
    )
    prompt = (
        f"{ref_clause}"
        "3-panel side-by-side layout on a flat neutral grey studio background: "
        "left panel front close-up portrait, center panel full body front view, right panel full body back view. "
        f"Subject details: {subject}. "
        f"Style: {style_pos}. "
        "Soft even studio light, exact same outfit, face, hair, and proportions in every view, clean panel dividers, no text labels, 4:3."
    )
    model_used = _render_keyframe_local_or_gemini(
        prompt,
        out_png,
        aspect_ratio="4:3",
        ref_images=ref_list if ref_list else None,
        engine=req_engine,
        view="front",
        seed=-1,
        require_ref=bool(ref_list),
        bypass_cache=True,
        extra_negative=", ".join(x for x in (style_neg, "text, labels, watermark, cropped head, mismatched outfit") if x),
    )
    return {
        "status": "ok",
        "character": char_name,
        "outfit_id": outfit_id,
        "style_id": look,
        "sheet_url": f"/file/{slug}/assets/turnarounds/{fname}",
        "rel_path": f"projects/books/{slug}/assets/turnarounds/{fname}",
        "used_reference": bool(ref_list),
        "model": model_used,
    }


@route("POST", "/api/v2_keyframe_hybrid_pass")
def _v2_keyframe_hybrid_pass(r: Request):
    """Two-Pass 2D-Meets-Realism Keyframe Renderer:
    - pass_num=1: Render Live-Action Plate with planned empty spaces (FREE SPACE gaps) -> keyframes/<sid>_pass1.png
    - pass_num=2: Lock Pass 1 + composite 2D cartoon cast sheets via multi-ref FLUX.2-klein-4B -> keyframes/<sid>.png"""
    import character_types_registry as ctr

    slug = str(r.body.get("project") or "").strip()
    shot_id = str(r.body.get("id") or "").strip()
    pass_num = int(r.body.get("pass_num") or 1)
    if not slug or not shot_id or pass_num not in (1, 2):
        raise PlanError("project, id, and pass_num (1 or 2) are required")

    pd = pdir(slug, "book")
    kf_dir = pd / "keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)
    pass1_png = kf_dir / f"{shot_id}_pass1.png"
    final_png = kf_dir / f"{shot_id}.png"

    prompt_raw = str(r.body.get("prompt") or "").strip()
    gap_notes = str(r.body.get("gap_notes") or "").strip()
    placement_notes = str(r.body.get("placement_notes") or "").strip()
    cartoon_refs_rel = [str(x).strip() for x in (r.body.get("cartoon_refs") or []) if str(x).strip()]
    live_refs_rel = [str(x).strip() for x in (r.body.get("live_refs") or []) if str(x).strip()]
    req_engine = str(r.body.get("engine") or "auto").strip().lower()

    gp_doc: dict[str, Any] = {}
    gp_path = pd / "global_params.json"
    if gp_path.is_file():
        try:
            gp_doc = json.loads(gp_path.read_text(encoding="utf-8")) or {}
        except Exception:
            gp_doc = {}
    raw_hm_sh = gp_doc.get("hybrid_mode")
    hm: dict[str, Any] = raw_hm_sh if isinstance(raw_hm_sh, dict) else {}
    cartoon_style_id = str(r.body.get("cartoon_style") or hm.get("cartoon_style") or "vintage_1940s_2d").strip()
    live_st = ctr.get_style(str(hm.get("live_style") or "live_action"))
    cartoon_st = ctr.get_style(cartoon_style_id)

    def _resolve_book_refs(rels: list[str]) -> list[Path]:
        out_p: list[Path] = []
        for rel in rels:
            cand = (pd / rel.lstrip("/")).resolve()
            if not cand.is_file():
                cand = (ROOT / rel.lstrip("/")).resolve()
            if cand.is_file() and cand.stat().st_size > 100 and cand not in out_p:
                out_p.append(cand)
        return out_p

    if pass_num == 1:
        live_refs = _resolve_book_refs(live_refs_rel)
        live_pos = str((live_st or {}).get("positives") or "cinematic 35mm live-action film still, warm practical lighting")
        gap_txt = gap_notes or "the empty chair to the right, the open table foreground, and the open air above"
        p1_prompt = (
            f"PASS 1 LIVE-ACTION PLATE ONLY (NO CARTOONS YET): {prompt_raw}. "
            f"Style: {live_pos}. "
            f"IMPORTANT: Keep clear empty spaces reserved where 2D cartoon characters will be added in Pass 2: {gap_txt}. "
            "Do NOT draw any 2D cartoons or animated creatures in this pass."
        )
        model_used = _render_keyframe_local_or_gemini(
            p1_prompt,
            pass1_png,
            aspect_ratio="16:9",
            ref_images=live_refs if live_refs else None,
            engine=req_engine,
            seed=-1,
            require_ref=bool(live_refs),
            bypass_cache=True,
            extra_negative="cartoon, 2D animated character, illustration, anime, cgi monster",
        )
        return {
            "status": "ok",
            "pass_num": 1,
            "id": shot_id,
            "pass1_url": f"/file/{slug}/keyframes/{shot_id}_pass1.png",
            "model": model_used,
        }

    # pass_num == 2: Lock Pass 1 + composite 2D cartoon characters from their sheets into the empty gaps
    if not (pass1_png.is_file() and pass1_png.stat().st_size > 200):
        raise PlanError(f"Run Pass 1 (Live Plate with Gaps) for {shot_id} first before bringing the 2D cast in.")

    c_refs = _resolve_book_refs(cartoon_refs_rel)
    all_refs = [pass1_png, *c_refs]
    c_pos = str((cartoon_st or {}).get("positives") or "vintage 1940s hand-drawn 2D cartoon style, clean ink line art, flat muted colours, soft painted shading")
    place_txt = placement_notes or gap_notes or "the planned empty spaces in the live-action scene, reacting naturally to the live actor"
    p2_prompt = (
        "PASS 2 HYBRID COMPOSITE: Keep the exact camera angle, lighting, real-world set, and photorealistic human actor from the first reference image (Pass 1 live plate) 100% locked and unchanged. "
        f"Add the hand-drawn 2D cartoon characters from the remaining reference sheets into the empty spaces: {place_txt}. "
        f"The added characters MUST stay strictly in {c_pos} with grounded contact shadows and warm bounce light matching the live room, while the real actor and environment remain 100% photorealistic live action. "
        f"Scene action: {prompt_raw}"
    )
    model_used = _render_keyframe_local_or_gemini(
        p2_prompt,
        final_png,
        aspect_ratio="16:9",
        ref_images=all_refs,
        engine=req_engine,
        seed=-1,
        require_ref=True,
        bypass_cache=True,
        extra_negative="turning the real person into a cartoon, turning 2D characters photorealistic, changing the background or camera framing",
    )
    return {
        "status": "ok",
        "pass_num": 2,
        "id": shot_id,
        "image_url": f"/file/{slug}/keyframes/{shot_id}.png",
        "pass1_url": f"/file/{slug}/keyframes/{shot_id}_pass1.png",
        "cartoon_ref_count": len(c_refs),
        "model": model_used,
    }


@route("POST", "/api/v2_hybrid_video_prompts")
def _v2_hybrid_video_prompts(r: Request):
    """Generate ready-to-paste Two-Pass Hybrid Video Prompts (Pass 1 Real Plate with Gaps + Pass 2 Bring 2D Cast In,
    animated on twos) formatted for Seedance 2.5 / Wan / Kling / Claude following 2D_Realism_Tutorial.pdf."""
    import character_types_registry as ctr

    slug = str(r.body.get("project") or "").strip()
    scene_id = str(r.body.get("scene_id") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")

    gp_doc: dict[str, Any] = {}
    gp_path = pd / "global_params.json"
    if gp_path.is_file():
        try:
            gp_doc = json.loads(gp_path.read_text(encoding="utf-8")) or {}
        except Exception:
            gp_doc = {}
    raw_hm_sh = gp_doc.get("hybrid_mode")
    hm: dict[str, Any] = raw_hm_sh if isinstance(raw_hm_sh, dict) else {}
    cartoon_style_id = str(r.body.get("cartoon_style") or hm.get("cartoon_style") or "vintage_1940s_2d").strip()
    c_st = ctr.get_style(cartoon_style_id) or {}
    c_style_line = str(c_st.get("positives") or "vintage 1940s hand-drawn 2D cartoon style, clean ink line art, flat muted colours, soft painted shading")
    on_twos = bool(hm.get("animate_on_twos", True))

    # Load shots from shotlist.json
    sl_path = pd / "shots" / "shotlist.json"
    scenes: list[dict[str, Any]] = []
    if sl_path.is_file():
        try:
            scenes = (json.loads(sl_path.read_text(encoding="utf-8")) or {}).get("scenes") or []
        except Exception:
            scenes = []

    target_scene: dict[str, Any] | None = None
    for sc in scenes:
        if isinstance(sc, dict) and (not scene_id or str(sc.get("id") or sc.get("scene")) == scene_id):
            target_scene = sc
            break

    heading = str((target_scene or {}).get("heading") or "Scene Location")
    shots = list((target_scene or {}).get("shots") or [])[:6]
    total_sec = int(round(sum(float(s.get("seconds") or 3.0) for s in shots if isinstance(s, dict)) or 12))

    # Classify cast into Live-Action vs 2D Cartoon based on Step 08 style_override
    live_cast: list[str] = []
    cartoon_cast: list[str] = []
    seen_names: set[str] = set()
    for ch in character_tokens.list_characters(slug) or []:
        if not isinstance(ch, dict) or not ch.get("name"):
            continue
        full_ch = character_tokens.load_character(slug, str(ch["name"])) or ch
        cname = str(full_ch["name"]).strip()
        if cname.lower() in seen_names:
            continue
        seen_names.add(cname.lower())
        ov = str(full_ch.get("style_override") or "").strip().lower()
        if ov in ("live_action", "realistic", "noir", "vintage_16mm"):
            live_cast.append(cname)
        elif ov:
            cartoon_cast.append(cname)
        else:
            cartoon_cast.append(cname)

    if not live_cast:
        live_cast = ["Lead Actor"]
    if not cartoon_cast:
        cartoon_cast = ["Cartoon Companion"]

    gap_notes = str(r.body.get("gap_notes") or "").strip()
    if not gap_notes:
        gap_notes = ", ".join(f"clear empty space for @{c.lower().replace(' ', '_')}" for c in cartoon_cast[:4])

    shot_lines_p1: list[str] = []
    shot_lines_p2: list[str] = []
    for i, sh in enumerate(shots or [{"type": "MS", "lens_mm": 35, "movement": "slow push-in", "lighting": "warm practical light", "action": "reacting warmly to the room"}], start=1):
        stype = str(sh.get("type") or "MS")
        lens = sh.get("lens_mm") or 35
        move = str(sh.get("movement") or "static")
        light = str(sh.get("lighting") or "warm cinematic practical light")
        act = str(sh.get("action") or sh.get("composition") or "").strip()
        shot_lines_p1.append(
            f"Shot {i} ({stype}, {lens}mm, {move}, {light}): {live_cast[0]} performs naturally in {heading} ({act}). Keep clear empty space reserved: {gap_notes}. No 2D characters yet."
        )
        tags = ", ".join(f"@{c.lower().replace(' ', '_')}" for c in cartoon_cast[:4])
        shot_lines_p2.append(
            f"Shot {i} (LOCK camera, cut, lighting & {live_cast[0]} exactly as in @video1): Add {tags} into the reserved empty spaces reacting to {live_cast[0]} ({act})."
        )

    pass1_prompt = (
        f"=== PASS 1: REAL LIVE-ACTION VIDEO WITH GAPS ({total_sec}s, {len(shot_lines_p1)} shots) ===\n"
        f"References: @image1 = Realistic 3-Panel Sheet ({', '.join(live_cast)}) · @image2 = Live-Action Set ({heading})\n\n"
        f"Cinematic 35mm live-action scene ({total_sec} seconds) in {heading}. "
        f"Keep clear empty spaces in every shot where 2D cartoons will be added later ({gap_notes}).\n"
        + "\n".join(shot_lines_p1)
    )
    twos_note = "animated strictly on twos (12 fps)" if on_twos else "smooth hand-drawn cadence"
    pass2_prompt = (
        f"=== PASS 2: BRING THE 2D CAST IN (LOCKED TO @video1) ===\n"
        f"References: @video1 = Pass 1 Raw Live-Action Clip · 2D Sheets: {', '.join('@' + c.lower().replace(' ', '_') for c in cartoon_cast)}\n\n"
        f"Keep EVERY shot, cut timing, camera move, lighting, and {live_cast[0]} EXACTLY as in @video1 (zero changes to the real footage). "
        f"Composite the 2D characters into the empty spaces. They MUST stay strictly in {c_style_line}, {twos_note}, reacting naturally to {live_cast[0]} with grounded contact shadows:\n"
        + "\n".join(shot_lines_p2)
    )
    return {
        "status": "ok",
        "project": slug,
        "scene_id": str((target_scene or {}).get("id") or scene_id or "S001"),
        "cartoon_style": cartoon_style_id,
        "live_cast": live_cast,
        "cartoon_cast": cartoon_cast,
        "pass1_prompt": pass1_prompt,
        "pass2_prompt": pass2_prompt,
    }


@route("POST", "/api/v2_plate_audit")
def _v2_plate_audit_post(r: Request):
    """Build per-plate consistency contact sheets (`qa/plate_sheets/plate_*.jpg`) comparing every approved Step 10/11 plate against all Step 17 keyframes that used it."""
    import plate_audit

    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    return plate_audit.audit_project_plates(slug, pd)


@route("POST", "/api/v2_beat_motion_prompt")
def _v2_beat_motion_prompt(r: Request):
    """Build a structured beat-by-beat timed Step 18 animation prompt (0.0-Xs beats + ESSENTIAL SEQUENCE + STYLE LOCK + AUDIO Foley cues)."""
    import character_types_registry as ctr

    slug = str(r.body.get("project") or "").strip()
    shot_id = str(r.body.get("shot_id") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")

    gp_doc: dict[str, Any] = {}
    gp_path = pd / "global_params.json"
    if gp_path.is_file():
        try:
            gp_doc = json.loads(gp_path.read_text(encoding="utf-8")) or {}
        except Exception:
            gp_doc = {}
    style_id = str(r.body.get("style_id") or gp_doc.get("look") or "pixar_3d").strip()
    st = ctr.get_style(style_id) or {}
    style_name = str(st.get("name") or style_id)
    motion_cadence = str(st.get("motion_cadence") or "smooth 24-fps cinema animation with grounded physics and zero morphing")
    style_neg = str(st.get("negatives") or "morphing, extra limbs, duplicate characters, text, watermark")

    # Find matching shot in shotlist.json
    target_scene: dict[str, Any] | None = None
    target_shot: dict[str, Any] | None = None
    sl_path = pd / "shots" / "shotlist.json"
    if sl_path.is_file():
        try:
            sl = json.loads(sl_path.read_text(encoding="utf-8")) or {}
            for sc in sl.get("scenes") or []:
                if not isinstance(sc, dict):
                    continue
                sc_id = str(sc.get("id") or sc.get("scene") or "S001")
                for idx, sh in enumerate(sc.get("shots") or [], start=1):
                    if not isinstance(sh, dict):
                        continue
                    sid = f"{sc_id}-{int(sh.get('n') or idx):02d}"
                    if (shot_id and sid.upper() == shot_id.upper()) or (not shot_id and target_shot is None):
                        target_scene = sc
                        target_shot = sh
                        shot_id = sid
                        break
                if target_shot is not None:
                    break
        except Exception as e:
            log.debug("failed reading shotlist for beat prompt: %s", e)

    dur = max(3.0, min(15.0, float(r.body.get("duration") or (target_shot or {}).get("seconds") or 6.0)))
    heading = str((target_scene or {}).get("heading") or "Scene Location")
    chars = [str(c) for c in ((target_shot or {}).get("characters") or []) if c]
    char_str = ", ".join(chars) if chars else "the main subject"
    cam_move = str((target_shot or {}).get("movement") or "locked camera").strip()
    action = str(r.body.get("action") or (target_shot or {}).get("action") or (target_shot or {}).get("composition") or "performs the key story beat smoothly").strip()
    expr = str((target_shot or {}).get("expression") or "natural expressive reaction").strip()
    props = [str(p) for p in ((target_shot or {}).get("props") or []) if p]
    prop_str = f", preserving {', '.join(props)}" if props else ""

    t1 = round(dur * 0.22, 1)
    t2 = round(dur * 0.55, 1)
    t3 = round(dur * 0.80, 1)
    cam_rule = (
        "One continuous locked-camera shot with zero unintended pan, tilt, or zoom."
        if cam_move.lower() in ("", "static", "locked", "locked camera")
        else f"One continuous shot with smooth, controlled camera move: {cam_move}. No jump cuts."
    )
    foley_hint = str(r.body.get("audio_cue") or f"subtle natural ambient room tone for {heading.lower()}, crisp grounded footsteps/prop Foley matching physical contact. No music or extra dialogue.").strip()

    prompt_text = (
        f"Animate the uploaded keyframe ({shot_id or 'shot'}) into a {dur:.1f}-second {style_name} shot. "
        f"Use the uploaded image as the exact opening frame. Preserve {char_str}, wardrobe, lighting, {heading}{prop_str}. "
        f"{cam_rule}\n\n"
        f"0.0–{t1:.1f} seconds — ANTICIPATION & SETUP\n"
        f"{char_str} holds the opening composition, settles weight naturally, and begins the clear anticipation cue before main movement.\n\n"
        f"{t1:.1f}–{t2:.1f} seconds — PRIMARY ACTION\n"
        f"{action}. Keep hands, feet, and solid props physically grounded with zero sliding, clipping, or shape drift.\n\n"
        f"{t2:.1f}–{t3:.1f} seconds — FOLLOW-THROUGH & REACTION\n"
        f"Complete the motion cleanly with {expr}. Secondary motion (hair, fabric, props) settles naturally under gravity.\n\n"
        f"{t3:.1f}–{dur:.1f} seconds — FINAL HOLD\n"
        f"Hold the clean, readable ending pose so the cut lands cleanly on the beat.\n\n"
        f"ESSENTIAL SEQUENCE: opening pose locked → anticipation → {action} → natural reaction & settle → clean hold.\n"
        f"STYLE & CONSISTENCY RULES: {motion_cadence}. Avoid: {style_neg}, cuts, camera glitches, extra people, teleporting props, text, or watermarks.\n"
        f"AUDIO: {foley_hint}"
    )
    return {
        "status": "ok",
        "project": slug,
        "shot_id": shot_id or "S001-01",
        "style_id": style_id,
        "style_name": style_name,
        "duration": dur,
        "prompt": prompt_text,
    }


@route("POST", "/api/v2_audio_first_clock")
def _v2_audio_first_clock(r: Request):
    """Build Audio-First Clock word timings, frame-snapped cut timings, and Reels/Shorts safe-zone captions."""
    import audio_first_clock

    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    fps = int(r.body.get("fps") or 24)
    use_whisper = bool(r.body.get("use_whisper", True))
    return audio_first_clock.build_audio_first_clock(slug, pd, fps=fps, use_whisper=use_whisper)


@route("POST", "/api/v2_caption_proofread")
def _v2_caption_proofread(r: Request):
    """Apply interactive Caption Proofread find-and-replace rules (e.g. `Cloud -> Claude`) and regenerate `safe_captions.srt`."""
    import audio_first_clock

    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    cap_dir = pd / "exports" / "captions"
    clock_json = cap_dir / "audio_first_clock.json"
    if not clock_json.is_file():
        clock_data = audio_first_clock.build_audio_first_clock(slug, pd, use_whisper=False)
    else:
        clock_data = json.loads(clock_json.read_text(encoding="utf-8")) or {}

    replacements = r.body.get("replacements")
    if not isinstance(replacements, dict):
        find_w = str(r.body.get("find") or "").strip()
        rep_w = str(r.body.get("replace") or "").strip()
        replacements = {find_w: rep_w} if find_w else {}

    updated_cues, changed = audio_first_clock.apply_caption_proofread(clock_data.get("cues") or [], replacements)
    clock_data["cues"] = updated_cues
    clock_data["cue_count"] = len(updated_cues)
    cap_dir.mkdir(parents=True, exist_ok=True)
    clock_json.write_text(json.dumps(clock_data, indent=2), encoding="utf-8")
    srt_path = cap_dir / "safe_captions.srt"
    srt_path.write_text(audio_first_clock.cues_to_srt(updated_cues), encoding="utf-8")
    return {
        "status": "ok",
        "project": slug,
        "changed_cues": changed,
        "cue_count": len(updated_cues),
        "cues": updated_cues,
        "srt_url": f"/file/{slug}/exports/captions/safe_captions.srt",
    }


@route("POST", "/api/v2_lufs_normalize")
def _v2_lufs_normalize(r: Request):
    """Measure and normalize Step 21's master audio mix to broadcast/social loudness (default -14 LUFS, 48 kHz)."""
    import audio_first_clock

    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    mix_wav = pd / "audio" / "mix" / "master_mix.wav"
    if not mix_wav.is_file():
        raise PlanError("No Step 21 master_mix.wav found yet. Mix your audio stems first.")
    target_lufs = float(r.body.get("target_lufs", -14.0))
    tmp_out = pd / "audio" / "mix" / "master_mix_lufs.wav"
    res = audio_first_clock.normalize_to_lufs(mix_wav, tmp_out, target_lufs=target_lufs)
    if not res.get("ok") or not tmp_out.is_file():
        raise PlanError(str(res.get("error") or "LUFS normalization failed"))
    tmp_out.replace(mix_wav)
    return {
        "status": "ok",
        "project": slug,
        "audio_url": f"/file/{slug}/audio/mix/master_mix.wav",
        "target_lufs": target_lufs,
        "before_lufs": res.get("before_lufs"),
        "after_lufs": res.get("after_lufs"),
        "after_true_peak_db": res.get("after_true_peak_db"),
        "sample_rate": res.get("sample_rate", 48000),
    }


@route("POST", "/api/v2_editing_style_analyze")
def _v2_editing_style_analyze(r: Request):
    """Analyze 1-3 reference MP4 videos (uploaded base64, local path, or permitted URL via yt-dlp) into Editing Style Guide.md."""
    import re
    import editing_style_analyzer as esa

    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    ref_dir = pd / "references"
    ref_dir.mkdir(parents=True, exist_ok=True)

    video_paths: list[Path] = []
    # 1. Uploaded video file via base64
    b64 = str(r.body.get("video_base64") or "").strip()
    if b64:
        from studio_app import upload_validation

        raw, _vid_ext = upload_validation.decode_verified_base64(b64, kind="video", min_bytes=128)
        raw_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(r.body.get("filename") or "reference.mp4")).strip("_") or "reference.mp4"
        if not raw_name.lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
            raw_name += ".mp4"
        up_path = ref_dir / raw_name
        up_path.write_bytes(raw)
        video_paths.append(up_path)

    # 2. Permitted URL via yt-dlp
    ref_url = str(r.body.get("url") or "").strip()
    if ref_url:
        try:
            dl_path = esa.download_reference_url(ref_url, ref_dir)
            video_paths.append(dl_path)
        except Exception as e:
            raise PlanError(f"Reference download failed: {e}") from e

    # 3. Existing local MP4s in references/ (or explicit local_path)
    loc_p = str(r.body.get("local_path") or "").strip()
    if loc_p and Path(loc_p).is_file():
        video_paths.append(Path(loc_p))
    if not video_paths:
        video_paths = sorted(p for p in ref_dir.glob("*") if p.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm"))
    if not video_paths:
        raise PlanError("Upload a reference MP4 video or paste a permitted video URL to analyze.")

    use_whisper = bool(r.body.get("use_whisper", False))
    try:
        return esa.analyze_reference_videos(slug, pd, video_paths, use_whisper=use_whisper)
    except Exception as e:
        raise PlanError(f"Editing style analysis failed: {e}") from e


@route("POST", "/api/v2_humanize_script")
def _v2_humanize_script(r: Request):
    """Run the Dialogue & Narration Humanizer pass across Step 06 screenplay / Step 15 spoken dialogue."""
    import script_humanizer

    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    apply_changes = bool(r.body.get("apply", True))
    dialogue_only = bool(r.body.get("dialogue_only", False))
    return script_humanizer.humanize_project_screenplay(
        slug, pd, apply_changes=apply_changes, dialogue_only=dialogue_only
    )


@route("POST", "/api/v2_code_drawn_render")
def _v2_code_drawn_render(r: Request):
    """Render a deterministic code-drawn title card / explainer clip (MP4 + HTML twin) for Step 20/22."""
    import code_drawn_templates

    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    raw_bullets = r.body.get("bullets")
    if isinstance(raw_bullets, str):
        bullets = [ln.strip() for ln in raw_bullets.splitlines() if ln.strip()]
    elif isinstance(raw_bullets, list):
        bullets = [str(x).strip() for x in raw_bullets if str(x).strip()]
    else:
        bullets = []
    try:
        return code_drawn_templates.render_code_drawn_clip(
            slug,
            pd,
            template_id=str(r.body.get("template_id") or "cinema_title_card").strip(),
            title=str(r.body.get("title") or "").strip(),
            subtitle=str(r.body.get("subtitle") or "").strip(),
            bullets=bullets,
            aspect=str(r.body.get("aspect") or "16:9").strip(),
            duration=float(r.body.get("duration") or 4.0),
            fps=int(r.body.get("fps") or 30),
        )
    except Exception as e:
        raise PlanError(f"Code-drawn animation render failed: {e}") from e


@route("POST", "/api/v2_blender_previs")
def _v2_blender_previs(r: Request):
    """Step 12: Render headless Blender 5.4 3D previs stills, .blend/.glb, and optional camera-move MP4 animatic."""
    from local_runners import blender_runner

    slug = str(r.body.get("project") or "").strip()
    scene_id = str(r.body.get("scene_id") or r.body.get("scene") or "S001").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    try:
        res = blender_runner.render_scene_previs(
            pd,
            slug,
            scene_id,
            render_animatic=bool(r.body.get("render_animatic", False)),
        )
    except (RuntimeError, ValueError) as e:
        raise PlanError(str(e)) from e
    return {"status": "ok", **res}


@route("POST", "/api/v2_blender_depth_guide")
def _v2_blender_depth_guide(r: Request):
    """Step 17: Render true-scale 3D Blocking PNG + Normalized Depth Map PNG for a shot (or all shots in a scene)."""
    from local_runners import blender_runner

    slug = str(r.body.get("project") or "").strip()
    shot_id = str(r.body.get("shot_id") or r.body.get("id") or "").strip()
    scene_id = str(r.body.get("scene") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    try:
        if shot_id:
            res = blender_runner.render_shot_depth_guide(pd, slug, shot_id)
            return {"status": "ok", **res}
        sid = scene_id or "S001"
        ctx = blender_runner._load_project_scene_context(pd, sid)
        guides = []
        for idx, sh in enumerate(ctx["shots"][:12], start=1):
            n = int(sh.get("n") or idx)
            guides.append(blender_runner.render_shot_depth_guide(pd, slug, f"{sid}-{n:02d}"))
        return {"status": "ok", "scene": sid, "count": len(guides), "guides": guides}
    except (RuntimeError, ValueError) as e:
        raise PlanError(str(e)) from e


@route("POST", "/api/v2_blender_set_angles")
def _v2_blender_set_angles(r: Request):
    """Step 11: Render multi-angle consistent 3D set plates (Wide, Reverse, Corner, OTS, Top-Down) from one 3D room."""
    from local_runners import blender_runner

    slug = str(r.body.get("project") or "").strip()
    set_name = str(r.body.get("set_name") or r.body.get("name") or "").strip()
    if not slug or not set_name:
        raise PlanError("project and set_name are required")
    pd = pdir(slug, "book")
    desc = str(r.body.get("description") or "").strip()
    lighting = str(r.body.get("lighting") or "").strip()
    if not desc and (pd / "sets_custom.json").is_file():
        try:
            sc = json.loads((pd / "sets_custom.json").read_text(encoding="utf-8")) or {}
            rec = sc.get(set_name.lower()) if isinstance(sc, dict) else None
            if isinstance(rec, dict):
                desc = str(rec.get("description") or "")
                lighting = lighting or str(rec.get("lighting") or "")
        except (OSError, ValueError):
            pass
    try:
        res = blender_runner.render_set_multi_angle(pd, slug, set_name, description=desc, lighting=lighting)
    except (RuntimeError, ValueError) as e:
        raise PlanError(str(e)) from e
    return {"status": "ok", **res}


@route("POST", "/api/v2_blender_title_card")
def _v2_blender_title_card(r: Request):
    """Step 18/20: Render a 3D animated extruded bevelled title card (PNG + MP4) via standalone Blender."""
    from local_runners import blender_runner

    slug = str(r.body.get("project") or "").strip()
    title = str(r.body.get("title") or slug).strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    try:
        res = blender_runner.render_3d_title_card(
            pd,
            slug,
            title=title,
            subtitle=str(r.body.get("subtitle") or "").strip(),
            style=str(r.body.get("style") or "space_orbit").strip(),
            duration_s=float(r.body.get("duration_s") or 3.0),
            render_video=bool(r.body.get("render_video", True)),
        )
    except (RuntimeError, ValueError) as e:
        raise PlanError(str(e)) from e
    return {"status": "ok", **res}


@route("POST", "/api/v2_blender_cast_guides")
def _v2_blender_cast_guides(r: Request):
    """Steps 08 & 10: Render true-scale 3D Cast Height Lineup and 4-angle Character Turnaround Guides via standalone Blender."""
    from local_runners import blender_runner

    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    try:
        res = blender_runner.render_cast_scale_turnaround_guides(
            pd,
            slug,
            character_name=str(r.body.get("character") or "").strip(),
            include_turnarounds=bool(r.body.get("include_turnarounds", True)),
        )
    except (RuntimeError, ValueError) as e:
        raise PlanError(str(e)) from e
    return {"status": "ok", **res}


def _render_prop_or_backdrop_plate(
    slug: str,
    pd: Path,
    name: str,
    *,
    kind: str = "prop",
    item_id: str = "",
    prompt_override: str = "",
    use_ref: bool = True,
    req_engine: str = "auto",
    style_strength: float | None = None,
) -> dict[str, Any]:
    """Generate or style-convert a Step 07 Prop or Dynamic Backdrop visual plate."""
    from studio_app import props_backdrops

    safe = str(item_id or props_backdrops.safe_item_slug(name)).strip()
    resolved_kind = props_backdrops.classify_kind(name, kind)
    style_pos, style_neg, _style_lbl, _hybrid = _resolve_set_film_style(pd)

    # Check if an imported reference photo exists for this prop/backdrop
    cur_data = props_backdrops.load_props_backdrops(pd, slug, auto_extract=False)
    cur_item: dict[str, Any] = {}
    for it in cur_data.get("items") or []:
        if str(it.get("id") or "") == safe or props_backdrops.norm_item_key(str(it.get("name") or "")) == props_backdrops.norm_item_key(name):
            cur_item = it
            break

    ref_rel = str(cur_item.get("ref_image") or "").strip()
    ref_img: Path | None = None
    if use_ref and ref_rel and (pd / ref_rel).is_file() and (pd / ref_rel).stat().st_size > 64:
        ref_img = pd / ref_rel

    props_dir = pd / "assets" / "props"
    props_dir.mkdir(parents=True, exist_ok=True)
    out_rel = f"assets/props/{safe}.png"
    out_png = pd / out_rel

    ref_imgs: list[Path] = []
    init_img: Path | None = None
    init_strength = 0.0

    if ref_img is not None:
        # Convert the imported photo AS-IS into the Step 09 film art style with a strictly
        # subject-agnostic prompt — NEVER inject old text prompts or unrelated room/object nouns!
        ref_imgs.append(ref_img)
        init_img = ref_img
        init_strength = style_strength if style_strength is not None else 0.68
        prompt = (
            f"Stylized animated movie rendering of the exact image in Image 1: {style_pos}. "
            "STRICT AS-IS CONVERSION: Convert ONLY what is actually present in Image 1 into this exact illustrated film style — "
            "preserve the exact subject, silhouette, proportions, framing, surface texture, and original color palette of Image 1. "
            "Do NOT add extra objects, surrounding rooms, walls, furniture, people, or background elements that are not in Image 1."
        )
        eff_neg = ", ".join(
            x
            for x in (
                style_neg,
                "photorealistic, raw photograph, DSLR photo, camera snapshot, people, characters, extra objects, clutter, added furniture, eyes, faces, stickers, decals",
            )
            if x
        )
    else:
        item_prompt = str(prompt_override or cur_item.get("prompt") or "").strip()
        if not item_prompt:
            item_prompt = f"{name}"
        if resolved_kind == "backdrop":
            prompt = (
                f"Wide cinematic scenic backdrop plate of {name}: {item_prompt}. "
                f"Art style: {style_pos}. Empty scenic vista plate only, no people, no foreground characters."
            )
        else:
            prompt = (
                f"Clean hero prop design plate of {name}: {item_prompt}. "
                f"Art style: {style_pos}. Single isolated prop only, no people, no characters, clean neutral studio backdrop."
            )
        eff_neg = ", ".join(
            x
            for x in (
                style_neg,
                "people, characters, person, crowd, hands, eyes, googly eyes, faces, anthropomorphic, watermark, text",
            )
            if x
        )

    aspect = "16:9" if resolved_kind == "backdrop" else "1:1"
    model_used = _render_keyframe_local_or_gemini(
        prompt,
        out_png,
        aspect_ratio=aspect,
        ref_images=ref_imgs if ref_imgs else None,
        engine=req_engine,
        seed=-1,
        init_strength=init_strength,
        init_image=init_img,
        prefer_edit=bool(ref_imgs),
        bypass_cache=True,
        extra_negative=eff_neg,
    )

    updated_item = props_backdrops.update_item_assets(
        pd,
        slug,
        name=name,
        kind=resolved_kind,
        item_id=safe,
        image_rel=out_rel,
    )
    return {
        "status": "ok",
        "item": updated_item,
        "image_url": f"/file/{slug}/{out_rel}",
        "converted_url": f"/file/{slug}/{out_rel}",
        "used_ref_photo": bool(ref_img),
        "model": model_used,
    }


@route("POST", "/api/v2_props_backdrops_extract")
def _v2_props_backdrops_extract(r: Request):
    """Step 07: Pull Props & Dynamic Backdrops from script, beats, shot list, and Continuity Book."""
    from studio_app import props_backdrops

    slug = str(r.body.get("project") or "").strip()
    if not slug:
        raise PlanError("project is required")
    pd = pdir(slug, "book")
    return props_backdrops.extract_props_and_backdrops_from_script(
        pd,
        slug,
        merge_existing=bool(r.body.get("merge_existing", True)),
    )


@route("POST", "/api/v2_prop_backdrop_save")
def _v2_prop_backdrop_save(r: Request):
    """Step 07: Add, update, or delete a Prop or Dynamic Backdrop and sync its prompt downstream."""
    from studio_app import props_backdrops

    slug = str(r.body.get("project") or "").strip()
    name = str(r.body.get("name") or "").strip()
    item_id = str(r.body.get("id") or "").strip()
    delete = bool(r.body.get("delete", False))
    if not slug or (not name and not item_id):
        raise PlanError("project and item name are required")
    pd = pdir(slug, "book")
    raw_scenes = r.body.get("scenes")
    scenes: list[str] | None = None
    if isinstance(raw_scenes, list):
        scenes = [str(x).strip() for x in raw_scenes if str(x).strip()]
    elif isinstance(raw_scenes, str):
        scenes = [x.strip() for x in re.split(r"[,;\s]+", raw_scenes) if x.strip()]
    return props_backdrops.save_prop_backdrop_item(
        pd,
        slug,
        name=name,
        kind=str(r.body.get("kind") or "prop").strip().lower(),
        prompt=str(r.body.get("prompt") or "").strip(),
        home_room=str(r.body.get("home_room") or "").strip(),
        state=str(r.body.get("state") or "").strip(),
        scenes=scenes,
        item_id=item_id,
        delete=delete,
    )


@route("POST", "/api/v2_prop_backdrop_render")
def _v2_prop_backdrop_render(r: Request):
    """Step 07: Generate a stylized Prop/Backdrop plate from its prompt or re-convert an imported photo as-is."""
    slug = str(r.body.get("project") or "").strip()
    name = str(r.body.get("name") or "").strip()
    if not slug or not name:
        raise PlanError("project and item name are required")
    pd = pdir(slug, "book")
    raw_ss = r.body.get("style_strength")
    style_strength: float | None = None
    if raw_ss is not None and str(raw_ss).strip() != "":
        try:
            style_strength = max(0.25, min(0.95, float(raw_ss)))
        except (TypeError, ValueError):
            style_strength = None
    return _render_prop_or_backdrop_plate(
        slug,
        pd,
        name,
        kind=str(r.body.get("kind") or "prop").strip().lower(),
        item_id=str(r.body.get("id") or "").strip(),
        prompt_override=str(r.body.get("prompt") or "").strip(),
        use_ref=bool(r.body.get("use_ref", True)),
        req_engine=str(r.body.get("engine") or "auto").strip().lower(),
        style_strength=style_strength,
    )


@route("POST", "/api/v2_prop_backdrop_upload")
def _v2_prop_backdrop_upload(r: Request):
    """Step 07: Import a photo for a Prop or Dynamic Backdrop, convert as-is, run image-to-text, and queue bi-directional sync."""
    from studio_app import props_backdrops, set_vision_sync, upload_validation

    slug = str(r.body.get("project") or "").strip()
    name = str(r.body.get("name") or "").strip()
    b64 = str(r.body.get("image_base64") or "").strip()
    if not slug or not name or not b64:
        raise PlanError("project, item name, and image_base64 are required")

    raw, detected_ext = upload_validation.decode_verified_base64(b64, kind="image", min_bytes=64)
    ext = detected_ext if detected_ext in (".png", ".jpg", ".webp") else ".png"

    pd = pdir(slug, "book")
    kind = props_backdrops.classify_kind(name, str(r.body.get("kind") or ""))
    safe = str(r.body.get("id") or props_backdrops.safe_item_slug(name)).strip()

    refs_dir = pd / "assets" / "props" / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    for old_ext in (".png", ".jpg", ".jpeg", ".webp"):
        old_p = refs_dir / f"{safe}_ref{old_ext}"
        if old_p.is_file():
            old_p.unlink(missing_ok=True)
    ref_rel = f"assets/props/refs/{safe}_ref{ext}"
    (pd / ref_rel).write_bytes(raw)

    item = props_backdrops.update_item_assets(
        pd,
        slug,
        name=name,
        kind=kind,
        item_id=safe,
        ref_rel=ref_rel,
    )
    out: dict[str, Any] = {
        "status": "ok",
        "item": item,
        "name": name,
        "kind": kind,
        "ref_url": f"/file/{slug}/{ref_rel}",
        "ref_rel": ref_rel,
    }

    if bool(r.body.get("convert_now", True)):
        raw_ss = r.body.get("style_strength")
        style_strength: float | None = None
        if raw_ss is not None and str(raw_ss).strip() != "":
            try:
                style_strength = max(0.25, min(0.95, float(raw_ss)))
            except (TypeError, ValueError):
                style_strength = None
        conv = _render_prop_or_backdrop_plate(
            slug,
            pd,
            name,
            kind=kind,
            item_id=safe,
            use_ref=True,
            req_engine=str(r.body.get("engine") or "auto").strip().lower(),
            style_strength=style_strength,
        )
        out["converted_url"] = conv["converted_url"]
        out["image_url"] = conv["image_url"]
        out["model"] = conv["model"]
        out["item"] = conv["item"]

    # Automatically run image-to-text on the imported photo to update the prop/backdrop prompt across Steps 07 & 17
    if bool(r.body.get("auto_describe", True)):
        try:
            vision_sync = set_vision_sync.sync_prop_or_backdrop_from_imported_image(
                pd,
                slug,
                name,
                pd / ref_rel,
                kind=kind,
                item_id=safe,
            )
            out["vision_sync"] = vision_sync
            if vision_sync.get("ok"):
                out["prompt"] = vision_sync.get("prompt", "")
        except Exception as e:
            log.debug("Auto image-to-text on prop/backdrop import skipped for %s: %s", name, e)

    # Queue bi-directional workflow sync starting at the earliest inception of this prop/backdrop in the pipeline
    try:
        bidir = set_vision_sync.record_import_bidirectional_sync(
            pd,
            slug,
            kind=kind,
            name=name,
            source_step=7,
        )
        out["earliest_inception_step"] = bidir["earliest_inception_step"]
        out["bidirectional_sync"] = bidir
    except Exception as e:
        log.debug("Bi-directional sync on prop/backdrop import skipped for %s: %s", name, e)

    return out



