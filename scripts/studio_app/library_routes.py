"""Start over, archived attempts, the picture library and reuse, for the page (milestone M8, Section 6b.4).

POST /api/start_over {project, keep: [sources, settings, styles, continuity, screenplay]}   -> the new attempt (refused while a job runs)
GET  /api/attempts?project=                      GET /api/attempt_files?project=&id=        POST /api/attempt_restore {project, id}
GET  /api/picture_library?project=&q=&style=&character=&location=&purpose=&attempt=&all_projects=&refresh=
POST /api/library_item {project, key, verdict? | purpose? | move_to? | own: true}
GET  /api/shot_matches?project=&style=&scene=&shot=             POST /api/shot_reuse {project, style, scene, shot, key, how: picture|prompt|layout}
POST /api/auto_reuse {project, style, min_score}
"""
from __future__ import annotations

from pathlib import Path

import assets
import attempts
import library
import production
from layout import project_dir

from .api import Request, route
from .common import PlanError
from .jobs import JOB


def _book(slug) -> Path:
    try:
        d = project_dir(str(slug or ""), "book")
    except ValueError as e:
        raise PlanError(str(e)) from e
    if not d.is_dir():
        raise PlanError("pick a book first")
    return d


def _idle() -> None:
    if JOB.running:
        raise PlanError("a job is running: wait for it to finish (or stop it) first")


def _thumb(project: str, it: dict) -> dict:
    ext = Path(it["file"]).suffix.lower() or ".png"
    return {**it, "thumb": f"/thumb/{project}/assets/objects/{it['id'][:2]}/{it['id']}{ext}"}


def _groups_out(gs: list[dict]) -> list[dict]:
    return [{**g, "versions": [_thumb(g.get("project", ""), v) for v in g["versions"]]} for g in gs]


@route("POST", "/api/start_over")
def _start_over(r: Request):
    d = _book(r.body.get("project"))
    _idle()
    keep = r.body.get("keep", [])
    if not isinstance(keep, list):
        raise PlanError("keep is a list")
    try:
        a = attempts.start_over(d, [str(k) for k in keep])
    except attempts.AttemptError as e:
        raise PlanError(str(e)) from e
    library.refresh(d)
    return {"attempt": a, "attempts": attempts.attempts(d)}


@route("GET", "/api/attempts")
def _attempts(r: Request):
    try:
        return {"attempts": attempts.attempts(_book(r.q("project")))}
    except PlanError:
        return {"attempts": []}


@route("GET", "/api/attempt_files")
def _attempt_files(r: Request):
    d = _book(r.q("project"))
    try:
        return {"files": attempts.files_of(d, r.q("id"))}
    except attempts.AttemptError as e:
        raise PlanError(str(e)) from e


@route("POST", "/api/attempt_restore")
def _restore(r: Request):
    d = _book(r.body.get("project"))
    _idle()
    try:
        out = attempts.restore(d, str(r.body.get("id", "")))
    except attempts.AttemptError as e:
        raise PlanError(str(e)) from e
    library.refresh(d)
    return {**out, "attempts": attempts.attempts(d)}


@route("GET", "/api/picture_library")
def _library(r: Request):
    try:
        d = _book(r.q("project"))
    except PlanError:
        return {"groups": [], "styles": []}
    if r.q("refresh"):
        library.refresh(d)
    gs = library.search(d, r.q("q"), r.q("style"), r.q("character"), r.q("location"), r.q("purpose"), r.q("attempt"), r.q("all_projects") in ("1", "true"))
    return {"groups": _groups_out(gs)[:400], "styles": [s["id"] for s in production.load(d)["styles"]], "purposes": list(library.PURPOSES)}


@route("POST", "/api/library_item")
def _item(r: Request):
    d = _book(r.body.get("project"))
    key = str(r.body.get("key", ""))
    try:
        if "verdict" in r.body:
            library.set_verdict(d, key, str(r.body["verdict"]))
        if "purpose" in r.body:
            library.set_purpose(d, key, str(r.body["purpose"]))
        if r.body.get("own") or r.body.get("move_to"):
            library.move_version(d, key, "" if r.body.get("own") else str(r.body["move_to"]))
    except ValueError as e:
        raise PlanError(str(e)) from e
    return {"ok": True}


@route("GET", "/api/shot_matches")
def _matches(r: Request):
    d = _book(r.q("project"))
    try:
        n = int(r.q("shot", "0"))
        ms = library.matches(d, r.q("style") or production.load(d)["master"], r.q("scene"), n)
    except ValueError as e:
        raise PlanError(str(e)) from e
    return {"matches": [_thumb(d.name, m) for m in ms]}


@route("POST", "/api/shot_reuse")
def _reuse(r: Request):
    d = _book(r.body.get("project"))
    try:
        rv = library.reuse(d, str(r.body.get("style") or production.load(d)["master"]), str(r.body.get("scene", "")), int(r.body.get("shot", 0)),
                           str(r.body.get("key", "")), str(r.body.get("how", "")))
    except (ValueError, TypeError, FileNotFoundError) as e:
        raise PlanError(str(e)) from e
    return {"review": rv}


@route("POST", "/api/auto_reuse")
def _auto(r: Request):
    d = _book(r.body.get("project"))
    try:
        ms = float(r.body.get("min_score", 8))
    except (TypeError, ValueError) as e:
        raise PlanError("min_score is a number from 0 to 10") from e
    if not 0 <= ms <= 10:
        raise PlanError("min_score is a number from 0 to 10")
    library.refresh(d)
    return library.auto_reuse(d, str(r.body.get("style") or production.load(d)["master"]), ms)


def ingest_book(d: Path) -> int:
    """Store every current picture and clip of a book by its contents (used before a storyboard reset too)."""
    return sum(assets.ingest_tree(d, d / f) for f in ("images", "videos", "pictures"))
