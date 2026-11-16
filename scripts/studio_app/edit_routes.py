"""The timeline editor and the animatic, for the page (milestone M10). One EDL for every style; renders are jobs.

GET  /api/edl?project=                         {cut, timeline, cuts, current, notes, gate, exports}   (assembled from the shot list the first time)
POST /api/edl_edit {project, op, ...}          op: move {id, to} | trim {id, seconds, trim_in?} | volume {target, volume} | split {id, at} |
                                               delete {id} | snap {scene?} | transition {id, kind, seconds?} | duck {db} | copy_cut {name, from?} |
                                               use_cut {name} | reassemble
POST /api/edl_suggest {project, engine, claude_model}   the Editor's notes (one AI call)
POST /api/edl_note {project, nid, accept}               accept a note in one click (or dismiss it)
POST /api/edl_approve {project}                         the REVIEW GATE of the edit
POST /api/animatic {project, style?, cut?, size?, subtitles?}   render the animatic (Product D) in one style, or in every style (a job)
"""
from __future__ import annotations

from pathlib import Path

import crew
import edl
import gates
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


def _view(d: Path) -> dict:
    e = edl.load(d)
    if not e:
        try:
            e = edl.assemble(d)
        except edl.EditError:
            return {"cut": None, "timeline": None, "cuts": [], "current": "", "notes": [], "gate": {"approved": False, "approved_at": "", "changed_since": False},
                    "exports": [], "styles": []}
    c = edl.cut(e)
    ex = d / "exports"
    files = sorted(p.name for p in ex.glob("animatic_*.mp4")) + sorted(p.name for p in ex.glob("film_*.mp4")) if ex.is_dir() else []
    return {"cut": c, "timeline": edl.timeline(c), "cuts": sorted(e["cuts"]), "current": e["current"], "notes": edl.notes(d),
            "gate": gates.status(d, "edit", e["cuts"]), "exports": [{"name": n, "url": f"/file/{d.name}/exports/{n}"} for n in files],
            "styles": [s["id"] for s in production.load(d)["styles"]]}


@route("GET", "/api/edl")
def _get(r: Request):
    try:
        return _view(_book(r.q("project")))
    except PlanError:
        return {"cut": None, "timeline": None, "cuts": [], "current": "", "notes": [], "gate": {"approved": False, "approved_at": "", "changed_since": False},
                "exports": [], "styles": []}


@route("POST", "/api/edl_edit")
def _edit(r: Request):
    d = _book(r.body.get("project"))
    op = str(r.body.get("op", ""))
    try:
        if op == "reassemble":
            edl.assemble(d)
        else:
            edl.apply(d, op, {k: v for k, v in r.body.items() if k not in ("project", "op")})
    except edl.EditError as e:
        raise PlanError(str(e)) from e
    return _view(d)


@route("POST", "/api/edl_suggest")
def _suggest(r: Request):
    d = _book(r.body.get("project"))
    engine = str(r.body.get("engine") or "claude")
    if engine == "fake":
        ask = edl.fake_ask()
    else:
        import bookkit
        model = str(r.body.get("claude_model") or "") or None

        def ask(prompt, roles, step, validate):
            return bookkit.llm_json(prompt, crew.system(roles, d, step), model=model, engine=engine, validate=validate)
    try:
        edl.suggest(d, ask, production.load(d)["target_minutes"] * 60)
    except (edl.EditError, RuntimeError, ValueError) as e:
        raise PlanError(f"the editor could not answer: {e}") from e
    return _view(d)


@route("POST", "/api/edl_note")
def _note(r: Request):
    d = _book(r.body.get("project"))
    try:
        edl.apply_note(d, str(r.body.get("nid", "")), bool(r.body.get("accept", True)))
    except edl.EditError as e:
        raise PlanError(str(e)) from e
    return _view(d)


@route("POST", "/api/edl_approve")
def _approve(r: Request):
    d = _book(r.body.get("project"))
    e = edl.load(d)
    if not e:
        raise PlanError("there is no edit yet")
    gates.approve(d, "edit", e["cuts"])
    return _view(d)


def render_steps(d: Path, body: dict, kind: str) -> list[dict]:
    sids = [s["id"] for s in production.load(d)["styles"]]
    sid = str(body.get("style") or "")
    if sid and sid not in sids:
        raise PlanError(f"{sid} is not one of this book's styles")
    size = str(body.get("size") or "1920x1080")
    if size not in ("1280x720", "1920x1080", "3840x2160", "1080x1920", "720x1280", "1080x1080"):
        raise PlanError("size is 1280x720, 1920x1080, 3840x2160 (4K), 1080x1920, 720x1280 or 1080x1080")
    cut = str(body.get("cut") or "")
    out = []
    for s in [sid] if sid else sids:
        argv = ["python3", "render_cut.py", d.name, s, "--kind", kind, "--size", size] + (["--cut", cut] if cut else []) + (["--subtitles"] if body.get("subtitles") else [])
        out.append({"label": f"Make the {kind} in {s}", "argv": argv, "env": {}})
    return out


@route("POST", "/api/animatic")
def _animatic(r: Request):
    d = _book(r.body.get("project"))
    steps = render_steps(d, r.body, "animatic")
    ahead = JOB.start(steps, r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead, "styles": len(steps)}
