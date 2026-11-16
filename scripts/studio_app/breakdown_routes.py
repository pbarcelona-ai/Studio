"""The continuity book and the director's breakdown + shot list for the page (milestone M4), each with its review gate.

POST /api/continuity_book {project, engine, claude_model}        write it (a job: scripts/continuity_book.py)
GET  /api/continuity_book?project=                              {book, gate}
POST /api/continuity_edit {project, kind, name, fields}          change one character / location / prop by hand
POST /api/continuity_approve {project}
POST /api/shot_list {project, engine, claude_model, force}       write it (a job: scripts/shot_list.py)
GET  /api/shot_list?project=                                    {list, gate}
POST /api/shot_edit {project, scene, n, action: edit|move|delete|add, fields, to}
POST /api/shot_list_approve {project}
"""
from __future__ import annotations

from pathlib import Path

import continuity_book
import gates
import shot_list
from layout import project_dir

from .api import Request, route
from .common import PlanError
from .jobs import JOB
from .steps import engine_args


def _book(slug) -> Path:
    try:
        d = project_dir(str(slug or ""), "book")
    except ValueError as e:
        raise PlanError(str(e)) from e
    if not d.is_dir():
        raise PlanError("pick a book first")
    return d


def _job(script: str, label: str, body: dict, force: bool = False) -> dict:
    slug = str(body.get("project") or "")
    _book(slug)
    engine = str(body.get("engine") or "claude")
    argv = ["python3", script, slug] + (["--engine", "fake"] if engine == "fake" else engine_args(body)) + (["--force"] if force else [])
    ahead = JOB.start([{"label": label, "argv": argv, "env": {}}], body, queue=bool(body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead}


def _cb_view(d: Path) -> dict:
    book = continuity_book.load(d)
    data = [book.get("characters", []), book.get("locations", []), book.get("props", [])]
    return {"book": book if book else None, "gate": gates.status(d, "continuity", data)}


def _sl_view(d: Path) -> dict:
    sl = shot_list.load(d)
    return {"list": sl or None, "gate": gates.status(d, "shotlist", shot_list.gate_data(sl))}


@route("POST", "/api/continuity_book")
def _cb_start(r: Request):
    return _job("continuity_book.py", "Write the continuity book from the screenplay", r.body)


@route("GET", "/api/continuity_book")
def _cb_get(r: Request):
    try:
        return _cb_view(_book(r.q("project")))
    except PlanError:
        return {"book": None, "gate": {"approved": False, "approved_at": "", "changed_since": False}}


@route("POST", "/api/continuity_edit")
def _cb_edit(r: Request):
    d = _book(r.body.get("project"))
    fields = r.body.get("fields")
    if not isinstance(fields, dict):
        raise PlanError("fields must be an object")
    try:
        continuity_book.edit(d, str(r.body.get("kind", "")), str(r.body.get("name", "")), fields)
    except ValueError as e:
        raise PlanError(str(e)) from e
    return _cb_view(d)


@route("POST", "/api/continuity_approve")
def _cb_approve(r: Request):
    d = _book(r.body.get("project"))
    book = continuity_book.load(d)
    if not book.get("characters"):
        raise PlanError("there is no continuity book to approve yet")
    gates.approve(d, "continuity", [book.get("characters", []), book.get("locations", []), book.get("props", [])])
    return _cb_view(d)


@route("POST", "/api/shot_list")
def _sl_start(r: Request):
    d = _book(r.body.get("project"))
    book = continuity_book.load(d)
    if not gates.approved(d, "continuity", [book.get("characters", []), book.get("locations", []), book.get("props", [])]):
        raise PlanError("approve the continuity book first: the shot list is written from it")
    return _job("shot_list.py", "Write the director's breakdown and the shot list", r.body, force=bool(r.body.get("force")))


@route("GET", "/api/shot_list")
def _sl_get(r: Request):
    try:
        return _sl_view(_book(r.q("project")))
    except PlanError:
        return {"list": None, "gate": {"approved": False, "approved_at": "", "changed_since": False}}


@route("POST", "/api/shot_edit")
def _sl_edit(r: Request):
    d = _book(r.body.get("project"))
    sid, action = str(r.body.get("scene", "")), str(r.body.get("action", "edit"))
    try:
        n = int(r.body.get("n", 0))
        if action == "edit":
            fields = r.body.get("fields")
            if not isinstance(fields, dict):
                raise PlanError("fields must be an object")
            shot_list.edit_shot(d, sid, n, fields)
        elif action == "move":
            shot_list.move_shot(d, sid, n, int(r.body.get("to", 0)))
        elif action == "delete":
            shot_list.delete_shot(d, sid, n)
        elif action == "add":
            shot_list.add_shot(d, sid, n)
        else:
            raise PlanError("action is edit, move, delete or add")
    except (TypeError, ValueError, shot_list.ShotListError) as e:
        raise PlanError(str(e)) from e
    return _sl_view(d)


@route("POST", "/api/shot_list_approve")
def _sl_approve(r: Request):
    d = _book(r.body.get("project"))
    sl = shot_list.load(d)
    if not sl.get("scenes"):
        raise PlanError("there is no shot list to approve yet")
    gates.approve(d, "shotlist", shot_list.gate_data(sl))
    return _sl_view(d)
