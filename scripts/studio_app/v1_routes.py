"""The automation API (BOOK_TO_SCREEN_BUILD.md Section 11, milestone M15): the whole pipeline without the page. The same token and the same
checks as the page (X-Studio-Token header); the book is named in the body or the query ("project"), as everywhere else in the Studio API.

POST /api/v1/projects {name, sources: [{kind: idea|url, text|url}], recipe, products, styles, settings, mode: autopilot|review, stop_at, rights}
POST /api/v1/sources {project, kind: idea|url, text|url, rights}        (files: POST /api/source_upload, as the page does)
POST /api/v1/run {project, stop_at, engine, claude_model, service, gpu, kaggle_user, image_model, video_model, confirm_spend}   Autopilot
POST /api/v1/stop {project}            POST /api/v1/chat {project, text, engine}        POST /api/v1/styles {project, style, text?}
POST /api/v1/branch {project, moment, name}      GET /api/v1/project?project=       GET /api/v1/exports?project=
GET  /api/v1/events?project=&since=    server-sent events of the job's progress (handler.py; poll /api/log every 3 s as the fallback)
POST /api/v1/queue {projects, ...run settings}  one Autopilot run per book, one after another
"""
from __future__ import annotations

import re
from pathlib import Path

import crew
import gates
import history
import layout
import ledger
import production
import sources

from .api import Request, route
from .common import PlanError
from .jobs import JOB
from .steps import engine_args

STEP_NAMES = ("continuity", "shotlist", "lookdev", "pictures", "sound", "edit", "clips")


def _book(slug, create: bool = False) -> Path:
    try:
        d = layout.project_dir(str(slug or ""), "book")
    except ValueError as e:
        raise PlanError(str(e)) from e
    if not d.is_dir():
        if not create:
            raise PlanError(f"no book called {slug!r}")
        d.mkdir(parents=True)
    return d


def _add_source(d: Path, s: dict, rights: bool) -> dict:
    kind = str(s.get("kind", ""))
    try:
        if kind == "idea":
            return sources.store(d, sources.from_idea(str(s.get("text", "")), str(s.get("title", ""))), rights)
        if kind == "url":
            import tempfile
            with tempfile.TemporaryDirectory(prefix="studio-web-") as t:
                if not rights:
                    raise sources.SourceError("Tick the box to confirm you have the right to use this source.")
                doc, files = sources.from_url(str(s.get("url", "")), Path(t))
                return sources.store(d, doc, rights, files)
    except sources.SourceError as e:
        raise PlanError(str(e)) from e
    raise PlanError("a source here is an idea (text) or a web address (url); upload files with /api/source_upload")


def _run_argv(d: Path, body: dict) -> list[str]:
    stops = body.get("stop_at") or []
    if not isinstance(stops, list) or any(s not in ("script", "continuity", "shotlist", "pictures", "cut") for s in stops):
        raise PlanError("stop_at is some of script, continuity, shotlist, pictures, cut")
    engine = str(body.get("engine") or "claude")
    argv = ["python3", "autopilot.py", d.name] + (["--stop-at", ",".join(stops)] if stops else [])
    argv += ["--engine", "fake"] if engine == "fake" else engine_args(body)
    for key, flag, pat in (("service", "--service", r"kaggle|colab|huggingface|computer"), ("gpu", "--gpu", r"[A-Za-z0-9_ .-]{2,40}"),
                           ("kaggle_user", "--kaggle-user", r"[A-Za-z0-9_-]{2,40}"), ("image_model", "--image-model", r"[a-z0-9_]{2,40}"),
                           ("video_model", "--video-model", r"[a-z0-9_]{2,40}")):
        v = str(body.get(key) or "")
        if v:
            if not re.fullmatch(pat, v):
                raise PlanError(f"bad {key}")
            argv += [flag, v]
    if body.get("confirm_spend"):
        argv.append("--confirm-spend")
    return argv


@route("POST", "/api/v1/projects")
def _create(r: Request):
    b = r.body
    name = str(b.get("name") or "")
    if not layout.SLUG_RE.match(name):
        raise PlanError("name is 2-40 lowercase letters, digits or _")
    if layout.find_dir(name) is not None:
        raise PlanError(f"there is already a project called {name}")
    d = _book(name, create=True)
    for s in b.get("sources") or []:
        _add_source(d, s if isinstance(s, dict) else {}, b.get("rights") is True)
    if b.get("recipe"):
        try:
            crew.set_recipe(d, str(b["recipe"]))
        except ValueError as e:
            raise PlanError(str(e)) from e
    settings = {**(b.get("settings") or {}), **({"products": b["products"]} if b.get("products") else {}),
                **({"styles": [{"id": x} if isinstance(x, str) else x for x in b["styles"]]} if b.get("styles") else {})}
    try:
        production.save(d, settings)
    except ValueError as e:
        raise PlanError(str(e)) from e
    started = False
    if b.get("mode") == "autopilot":
        JOB.start([{"label": f"{name}: Autopilot", "argv": _run_argv(d, b), "env": {}}], {**b, "project": name}, queue=True)
        started = True
    return {"project": name, "sources": len(sources.load_index(d)), "autopilot": started}


@route("POST", "/api/v1/sources")
def _sources(r: Request):
    d = _book(r.body.get("project"))
    return {"added": _add_source(d, r.body, r.body.get("rights") is True), "sources": len(sources.load_index(d))}


@route("POST", "/api/v1/run")
def _run(r: Request):
    d = _book(r.body.get("project"))
    ahead = JOB.start([{"label": f"{d.name}: Autopilot", "argv": _run_argv(d, r.body), "env": {}}], {**r.body, "project": d.name}, queue=bool(r.body.get("queue", True)))
    return {"started": ahead == 0, "ahead": ahead}


@route("POST", "/api/v1/stop")
def _stop(r: Request):
    _book(r.body.get("project"))
    if not JOB.running:
        raise PlanError("no job is running")
    JOB.stop()
    return {"stopped": True}


@route("POST", "/api/v1/chat")
def _chat(r: Request):
    from .collab_routes import _ask
    return _ask(r)


@route("POST", "/api/v1/styles")
def _styles(r: Request):
    d = _book(r.body.get("project"))
    st = production.load(d)
    sid = str(r.body.get("style") or "")
    new = {"id": sid, **({"name": str(r.body.get("name") or sid), "text": str(r.body["text"])} if r.body.get("text") else {})}
    try:
        st, notes = production.save(d, {**st, "styles": [*st["styles"], new]})
    except ValueError as e:
        raise PlanError(str(e)) from e
    engine = str(r.body.get("engine") or "claude")
    argv = ["python3", "styles.py", d.name, "--style", sid] + (["--engine", "fake"] if engine == "fake" else engine_args(r.body))
    JOB.start([{"label": f"Add the {sid} style", "argv": argv, "env": {}}], {**r.body, "project": d.name}, queue=True)
    return {"styles": [s["id"] for s in st["styles"]], "notes": notes}


@route("POST", "/api/v1/branch")
def _branch(r: Request):
    d = _book(r.body.get("project"))
    try:
        new = history.branch(d, str(r.body.get("moment") or ""), str(r.body.get("name") or ""))
    except (history.HistoryError, FileNotFoundError) as e:
        raise PlanError(str(e)) from e
    return {"project": new.name}


def _gate_state(d: Path, step: str) -> str:
    g = gates._load(d).get(step)
    return "approved" if g else "not approved"


@route("GET", "/api/v1/project")
def _status(r: Request):
    try:
        d = _book(r.q("project"))
    except PlanError:
        if r.q("quiet"):                                      # the page asks for any project; only a book has a status
            return {"project": None}
        raise
    st = production.load(d)
    steps = {"read_it_in": "done" if (d / "readin" / "summary.json").is_file() else "to do"}
    steps.update({s: _gate_state(d, s) for s in STEP_NAMES})
    for s in st["styles"]:
        if s["id"] != st["master"]:
            steps[f"pictures_{s['id']}"] = _gate_state(d, f"pictures_{s['id']}")
    job = (getattr(JOB, "state", {}) or {})
    return {"project": d.name, "settings": st, "steps": steps, "cost": ledger.report(d),
            "job": {"running": JOB.running and job.get("project") == d.name, "step": JOB.current if job.get("project") == d.name else ""}}


@route("GET", "/api/v1/exports")
def _exports(r: Request):
    d = _book(r.q("project"))
    ex = d / "exports"
    files = sorted(p.relative_to(ex).as_posix() for p in ex.rglob("*") if p.is_file() and not p.name.endswith(".json")) if ex.is_dir() else []
    out = []
    for f in files:
        top = "download" if "/" not in f and Path(f).suffix in (".pdf", ".fountain", ".fdx", ".docx", ".epub", ".m4b") else "file"
        out.append({"name": f, "url": f"/{top}/{d.name}/exports/{f}"})
    return {"exports": out}


@route("POST", "/api/v1/queue")
def _queue(r: Request):
    names = r.body.get("projects")
    if not isinstance(names, list) or not names:
        raise PlanError("projects is a list of book names")
    out = []
    for n in names:
        d = _book(n)
        JOB.start([{"label": f"{d.name}: Autopilot", "argv": _run_argv(d, r.body), "env": {}}], {**r.body, "project": d.name}, queue=True)
        out.append(d.name)
    return {"queued": out}
