"""Pictures in the master style, their review, and the storyboard / illustrated book exports, for the page (milestone M6).

POST /api/pictures_prompts {project, style?}                          the picture prompts from the approved shot list and look development
GET  /api/pictures?project=&style=                                   {style, set, shots: [...], approved, gate, exports}
POST /api/pictures_render {project, style?, first?, last?, service, gpu, kaggle_user, image_model}   render rows (a job)
POST /api/picture_action {project, style, row, action: approve|unapprove|note|prompt|regenerate|swap, text?, other?, + render settings}
POST /api/pictures_approve {project, style?}                          the REVIEW GATE: every shot approved
POST /api/page_plan {project, style?, engine, claude_model}           the Illustrator's page plan for the illustrated book
POST /api/pictures_export {project, style?, kinds: [storyboard, illustrated, epub, comparison]}
M7, the other styles (the same routes with style=<id>, made from the approved master frames), plus:
GET  /api/style_compare?project=                                     one row per shot, one cell per style (picture, approval, consistency)
POST /api/consistency_check {project, style, engine, claude_model}    the Script Supervisor compares each picture with its master frame (a job)
POST /api/pictures_render_again {project, style, + render settings}   render the pictures that failed the check, then check them again (a job)
"""
from __future__ import annotations

import re
from pathlib import Path

import book_exports
import consistency
import crew
import gates
import pictures
import production
from layout import project_dir

from .api import Request, route
from .common import PlanError
from .config import GPUS, IMAGE_MODELS
from .gpus import check_models, gpu_blocker
from .jobs import JOB
from .steps import engine_args, make_runner


def _book(slug) -> Path:
    try:
        d = project_dir(str(slug or ""), "book")
    except ValueError as e:
        raise PlanError(str(e)) from e
    if not d.is_dir():
        raise PlanError("pick a book first")
    return d


def _style(d: Path, body_or_q: str) -> str:
    return body_or_q or production.load(d)["master"]


def _wrap(fn):
    try:
        return fn()
    except (pictures.PictureError, book_exports.ExportError, ValueError) as e:
        raise PlanError(str(e)) from e


def _view(d: Path, sid: str) -> dict:
    st = pictures.status(d, sid)
    ex = d / "exports"
    names = [f"storyboard_{sid}.pdf", f"illustrated_{sid}.pdf", f"illustrated_{sid}.epub", "style_comparison.pdf"]
    master = production.load(d)["master"]
    return {**st, "master": master, "styles": [x["id"] for x in production.load(d)["styles"]], "consistency": consistency.load(d, sid) if sid != master else {},
            "gate": gates.status(d, pictures.gate_step(d, sid), pictures.gate_data(d, sid)),
            "exports": [{"name": n, "url": f"/download/{d.name}/exports/{n}"} for n in names if (ex / n).is_file()]}


def _render_step(d: Path, sid: str, body: dict, first: int, last: int) -> dict:
    service, gpu, model = body.get("service"), body.get("gpu"), str(body.get("image_model", ""))
    if service not in GPUS or gpu not in [g for g, _ in GPUS[service]]:
        raise PlanError("choose where the models run, and the GPU")
    if gpu_blocker(service, gpu):
        raise PlanError(gpu_blocker(service, gpu))
    if model not in IMAGE_MODELS:
        raise PlanError("choose the image model")
    check_models(service, gpu, [model])
    user = str(body.get("kaggle_user") or "").strip()
    if service == "kaggle" and not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", user):
        raise PlanError("enter your Kaggle username (letters, digits, - and _)")
    argv, env = make_runner(service, gpu, user, pictures.set_name(d, sid))(f"image_{model}", first, last, "all_images.csv")
    return {"label": f"Render the {sid} pictures {first}-{last}", "argv": argv, "env": env}


@route("POST", "/api/pictures_prompts")
def _prompts(r: Request):
    d = _book(r.body.get("project"))
    out = _wrap(lambda: pictures.write_prompts(d, str(r.body.get("style") or "")))
    return {**_view(d, out["style"]), "made": out}


@route("GET", "/api/pictures")
def _get(r: Request):
    try:
        d = _book(r.q("project"))
    except PlanError:
        return {"style": "", "set": "", "shots": [], "approved": 0, "gate": {"approved": False, "approved_at": "", "changed_since": False}, "exports": []}
    return _view(d, _style(d, r.q("style")))


@route("POST", "/api/pictures_render")
def _render(r: Request):
    d = _book(r.body.get("project"))
    sid = _style(d, str(r.body.get("style") or ""))
    st = pictures.status(d, sid)
    if not st["shots"]:
        raise PlanError("make the picture prompts first")
    try:
        first, last = int(r.body.get("first") or 1), int(r.body.get("last") or len(st["shots"]))
    except (TypeError, ValueError) as e:
        raise PlanError("first and last are row numbers") from e
    if not 1 <= first <= last <= len(st["shots"]):
        raise PlanError(f"rows must be within 1-{len(st['shots'])}")
    ahead = JOB.start([_render_step(d, sid, r.body, first, last)], r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead}


@route("POST", "/api/picture_action")
def _action(r: Request):
    d = _book(r.body.get("project"))
    sid = _style(d, str(r.body.get("style") or ""))
    try:
        row = int(r.body.get("row", 0))
    except (TypeError, ValueError) as e:
        raise PlanError("row is a number") from e
    act = str(r.body.get("action", ""))
    if act in ("approve", "unapprove"):
        _wrap(lambda: pictures.approve(d, sid, row, act == "approve"))
    elif act == "note":
        _wrap(lambda: pictures.note(d, sid, row, str(r.body.get("text", ""))))
    elif act == "prompt":
        _wrap(lambda: pictures.set_prompt(d, sid, row, str(r.body.get("text", ""))))
    elif act == "swap":
        try:
            other = int(r.body.get("other", 0))
        except (TypeError, ValueError) as e:
            raise PlanError("other is a row number") from e
        _wrap(lambda: pictures.swap(d, sid, row, other))
    elif act == "regenerate":
        step = _render_step(d, sid, r.body, row, row)                 # check the GPU choice before the picture is moved aside
        _wrap(lambda: pictures.prepare_regenerate(d, sid, row))
        JOB.start([step], r.body, queue=True)
    else:
        raise PlanError("action is approve, unapprove, note, prompt, regenerate or swap")
    return _view(d, sid)


@route("POST", "/api/pictures_approve")
def _approve(r: Request):
    d = _book(r.body.get("project"))
    sid = _style(d, str(r.body.get("style") or ""))
    _wrap(lambda: pictures.approve_all_ready(d, sid))
    return _view(d, sid)


@route("POST", "/api/page_plan")
def _page_plan(r: Request):
    d = _book(r.body.get("project"))
    sid = _style(d, str(r.body.get("style") or ""))
    engine = str(r.body.get("engine") or "claude")
    if engine == "fake":
        ask = book_exports.fake_ask(d)
    else:
        import bookkit
        model = str(r.body.get("claude_model") or "") or None

        def ask(prompt, roles, step, validate):
            return bookkit.llm_json(prompt, crew.system(roles, d, step), model=model, engine=engine, validate=validate)
    try:
        pages = book_exports.page_plan(d, sid, ask)
    except (book_exports.ExportError, RuntimeError, ValueError) as e:
        raise PlanError(f"the page plan was not made: {e}") from e
    return {"pages": pages}


@route("POST", "/api/pictures_export")
def _export(r: Request):
    d = _book(r.body.get("project"))
    sid = _style(d, str(r.body.get("style") or ""))
    kinds = r.body.get("kinds") or ["storyboard", "illustrated", "epub"]
    if not isinstance(kinds, list):
        raise PlanError("kinds is a list")
    _wrap(lambda: book_exports.export(d, sid, tuple(str(k) for k in kinds)))
    return _view(d, sid)


def _check_step(d: Path, sid: str, body: dict) -> dict:
    engine = str(body.get("engine") or "claude")
    argv = ["python3", "consistency.py", d.name, sid] + (["--engine", "fake"] if engine == "fake" else engine_args(body))
    return {"label": f"Check the {sid} pictures against the master frames", "argv": argv, "env": {}}


@route("POST", "/api/consistency_check")
def _consistency(r: Request):
    d = _book(r.body.get("project"))
    sid = str(r.body.get("style") or "")
    if sid == production.load(d)["master"] or sid not in [x["id"] for x in production.load(d)["styles"]]:
        raise PlanError("choose one of the other styles (the master style is the reference)")
    ahead = JOB.start([_check_step(d, sid, r.body)], r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead}


@route("POST", "/api/pictures_render_again")
def _again(r: Request):
    d = _book(r.body.get("project"))
    sid = str(r.body.get("style") or "")
    rows = sorted(int(k) for k, v in consistency.load(d, sid).items() if v.get("pending"))
    if not rows:
        raise PlanError("no picture of this style is waiting to be rendered again")
    ranges, start = [], rows[0]
    for a, b in zip(rows, [*rows[1:], None], strict=True):
        if b != a + 1:
            ranges.append((start, a))
            start = b if b is not None else start
    steps = [_render_step(d, sid, r.body, a, b) for a, b in ranges] + [_check_step(d, sid, r.body)]
    ahead = JOB.start(steps, r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead, "rows": rows}


@route("GET", "/api/style_compare")
def _compare(r: Request):
    try:
        d = _book(r.q("project"))
    except PlanError:
        return {"styles": [], "rows": []}
    sids = [x["id"] for x in production.load(d)["styles"]]
    per = {sid: pictures.status(d, sid) for sid in sids}
    checks = {sid: consistency.load(d, sid) for sid in sids}
    n = max((len(p["shots"]) for p in per.values()), default=0)
    rows = []
    for i in range(n):
        cells = {}
        for sid in sids:
            sh = per[sid]["shots"][i] if i < len(per[sid]["shots"]) else None
            c = checks[sid].get(str(i + 1), {})
            cells[sid] = {"set": per[sid]["set"], "image": sh["image"] if sh else "", "approved": bool(sh and sh["approved"]), "score": c.get("score"),
                          "flagged": bool(c.get("flagged")), "pending": bool(c.get("pending"))}
        first: dict = next((per[s]["shots"][i] for s in sids if i < len(per[s]["shots"])), {})
        rows.append({"row": i + 1, "scene": first.get("scene", ""), "shot": first.get("shot", 0), "cells": cells})
    return {"styles": [{"id": s, "name": production.style_name({"id": s}), "master": s == production.load(d)["master"]} for s in sids], "rows": rows}
