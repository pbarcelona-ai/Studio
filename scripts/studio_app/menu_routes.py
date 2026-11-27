"""API routes for the Studio Menu Bar: Named Projects (New/Open/Save/Save As), Undo/Redo, Manual, About, and Exit."""
from __future__ import annotations

import project_manager

from .api import Request, route
from .common import PlanError


@route("GET", "/api/studio/projects")
def _list_projects(r: Request):
    return {"status": "ok", **project_manager.list_projects()}


@route("POST", "/api/studio/project/new")
def _new_project(r: Request):
    try:
        res = project_manager.new_project(
            str(r.body.get("name") or ""),
            book_source=str(r.body.get("book_source") or ""),
            story_text=str(r.body.get("story_text") or ""),
        )
    except project_manager.ProjectError as e:
        raise PlanError(str(e)) from e
    return {"status": "ok", **res}


@route("POST", "/api/studio/project/open")
def _open_project(r: Request):
    try:
        res = project_manager.open_project(str(r.body.get("slug") or r.body.get("project") or ""))
    except project_manager.ProjectError as e:
        raise PlanError(str(e)) from e
    return {"status": "ok", **res}


@route("POST", "/api/studio/project/save")
def _save_project(r: Request):
    slug = str(r.body.get("slug") or r.body.get("project") or "")
    label = str(r.body.get("label") or "Manual Save")
    raw_step = r.body.get("last_step")
    last_step = int(raw_step) if raw_step is not None and str(raw_step).isdigit() else None
    book_source = str(r.body.get("book_source") or "").strip() or None
    try:
        res = project_manager.save_project(slug, label=label, last_step=last_step, book_source=book_source)
    except project_manager.ProjectError as e:
        raise PlanError(str(e)) from e
    return {"status": "ok", **res}


@route("POST", "/api/studio/project/save_as")
def _save_project_as(r: Request):
    src = str(r.body.get("source_slug") or r.body.get("project") or "")
    new_name = str(r.body.get("new_name") or r.body.get("name") or "")
    raw_step = r.body.get("last_step")
    last_step = int(raw_step) if raw_step is not None and str(raw_step).isdigit() else None
    try:
        res = project_manager.save_project_as(src, new_name, last_step=last_step)
    except project_manager.ProjectError as e:
        raise PlanError(str(e)) from e
    return {"status": "ok", **res}


@route("POST", "/api/studio/project/undo")
def _undo_project(r: Request):
    slug = str(r.body.get("slug") or r.body.get("project") or "")
    try:
        res = project_manager.undo_project(slug)
    except project_manager.ProjectError as e:
        raise PlanError(str(e)) from e
    return {"status": "ok", **res}


@route("POST", "/api/studio/project/redo")
def _redo_project(r: Request):
    slug = str(r.body.get("slug") or r.body.get("project") or "")
    try:
        res = project_manager.redo_project(slug)
    except project_manager.ProjectError as e:
        raise PlanError(str(e)) from e
    return {"status": "ok", **res}


@route("GET", "/api/studio/manual")
def _manual(r: Request):
    return {
        "status": "ok",
        "markdown": project_manager.load_manual_markdown(),
        "about": project_manager.about_info(),
    }


@route("GET", "/api/studio/about")
def _about(r: Request):
    return {"status": "ok", **project_manager.about_info()}


@route("POST", "/api/studio/shutdown")
def _shutdown(r: Request):
    """Cleanly stop running jobs, managed ComfyUI, and the local Studio HTTP server (File → Exit)."""
    from . import server

    stop_jobs = bool(r.body.get("stop_jobs", True))
    scheduled = server.request_shutdown(stop_jobs=stop_jobs)
    return {
        "status": "ok",
        "shutting_down": True,
        "server_scheduled": scheduled,
        "message": "Pistachio's Studio is shutting down cleanly. You may safely close this browser tab.",
    }
