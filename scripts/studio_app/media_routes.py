"""Media sources for the page (milestone M13, Section 4.2): understand a video / audio source, bind segments, real footage as shots,
"Make a story from my clips", and an uploaded track as the score.

POST /api/media_understand {project, id, engine, claude_model}      shots, key frames, transcript, the Story Analyst's account (a job)
GET  /api/media_sources?project=                                          every media source with what was understood, and the bindings
POST /api/media_bind {project, id, start, end, what: clip|frame|audio, kind: character|location|shot|music, target}
POST /api/media_footage {project, id, start, end, scene, shot}      that segment becomes the real shot (in every style)
POST /api/media_look {project, id, engine, claude_model}            the Animation Supervisor's notes so AI shots match the footage
POST /api/media_autoedit {project, engine, claude_model}            "Make a story from my clips" (a new shot list of real shots)
POST /api/media_score {project, id}                                 the track as the score, at its tempo
"""
from __future__ import annotations

from pathlib import Path

import crew
import media_sources as ms
import sources
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


def _ask(d: Path, body: dict):
    engine = str(body.get("engine") or "claude")
    if engine == "fake":
        return ms.fake_ask()
    import bookkit
    model = str(body.get("claude_model") or "") or None

    def ask(prompt, roles, step, validate, image=None):
        return bookkit.llm_json(prompt, crew.system(roles, d, step), model=model, engine=engine, validate=validate, image=image)
    return ask


def _view(d: Path) -> dict:
    items = []
    for s in sources.load_index(d):
        if s["kind"] == "media":
            u = ms.understanding(d, s["id"])
            items.append({"id": s["id"], "title": s["title"], "understood": bool(u), "shots": u.get("shots", []), "transcript": len(u.get("transcript", [])),
                          "story": (u.get("account") or {}).get("story", "")})
    return {"media": items, "bindings": ms.bindings(d), "footage": ms.footage(d)}


def _wrap(fn):
    try:
        return fn()
    except (ms.MediaError, sources.SourceError, ValueError, TypeError, KeyError) as e:
        raise PlanError(str(e)) from e


@route("GET", "/api/media_sources")
def _get(r: Request):
    try:
        return _view(_book(r.q("project")))
    except PlanError:
        return {"media": [], "bindings": [], "footage": {}}


@route("POST", "/api/media_understand")
def _understand(r: Request):
    d = _book(r.body.get("project"))
    sid = str(r.body.get("id", ""))
    _wrap(lambda: ms._source(d, sid))
    engine = str(r.body.get("engine") or "claude")
    argv = ["uv", "run", "--quiet", "--with", "imageio-ffmpeg", "--with", "pillow", "--with", "faster-whisper", "python", "media_sources.py", d.name, sid] + \
        (["--engine", "fake"] if engine == "fake" else engine_args(r.body))
    ahead = JOB.start([{"label": f"Watch and listen to {sid}", "argv": argv, "env": {}}], r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead}


@route("POST", "/api/media_bind")
def _bind(r: Request):
    d = _book(r.body.get("project"))
    b = r.body
    _wrap(lambda: ms.bind(d, str(b["id"]), float(b["start"]), float(b.get("end", float(b["start"]) + 1)), str(b["what"]), str(b["kind"]), str(b["target"])))
    return _view(d)


@route("POST", "/api/media_footage")
def _footage(r: Request):
    d = _book(r.body.get("project"))
    b = r.body
    _wrap(lambda: ms.use_footage(d, str(b["scene"]), int(b["shot"]), str(b["id"]), float(b["start"]), float(b["end"])))
    return _view(d)


@route("POST", "/api/media_look")
def _look(r: Request):
    d = _book(r.body.get("project"))
    look = _wrap(lambda: ms.footage_look(d, str(r.body.get("id", "")), _ask(d, r.body)))
    return {**_view(d), "look": look}


@route("POST", "/api/media_autoedit")
def _autoedit(r: Request):
    d = _book(r.body.get("project"))
    if JOB.running:
        raise PlanError("a job is running: wait for it to finish (or stop it) first")
    import history
    history.create(d, "before making a story from the clips", "manual")          # the current shot list stays in the history
    out = _wrap(lambda: ms.auto_edit(d, _ask(d, r.body), lambda t: None))
    return {**_view(d), "made": out}


@route("POST", "/api/media_score")
def _score(r: Request):
    d = _book(r.body.get("project"))
    out = _wrap(lambda: ms.set_score(d, str(r.body.get("id", ""))))
    return {**_view(d), "score": out}
