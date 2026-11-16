"""Clips per style for the page (milestone M11).

POST /api/clips_motion {project, engine, claude_model}           the Animation Supervisor's motion prompts, shared by every style (a job)
GET  /api/clips?project=&style=                                  {style, set, clips, approved, checklist, gate, motion: bool, styles, master}
POST /api/clips_render {project, style?, service, gpu, kaggle_user, video_model, first?, last?}   the style's clips (a job)
POST /api/clip_review {project, style, row, approved?, note?}
POST /api/clips_approve {project, style?}                        the REVIEW GATE of a style's clips
"""
from __future__ import annotations

import re
from pathlib import Path

import clips
import gates
import production
from layout import project_dir

from .api import Request, route
from .common import PlanError
from .config import GPUS, I2V_MODELS
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


def _style(d: Path, sid: str) -> str:
    sids = [s["id"] for s in production.load(d)["styles"]]
    sid = sid or production.load(d)["master"]
    if sid not in sids:
        raise PlanError(f"{sid} is not one of this book's styles")
    return sid


def _view(d: Path, sid: str) -> dict:
    return {**clips.status(d, sid), "gate": gates.status(d, clips.gate_step(d, sid), clips.gate_data(d, sid)), "motion": bool(clips.load_motion(d)),
            "styles": [s["id"] for s in production.load(d)["styles"]], "master": production.load(d)["master"]}


@route("POST", "/api/clips_motion")
def _motion(r: Request):
    d = _book(r.body.get("project"))
    engine = str(r.body.get("engine") or "claude")
    argv = ["python3", "clips.py", d.name] + (["--engine", "fake"] if engine == "fake" else engine_args(r.body))
    ahead = JOB.start([{"label": "Write the motion prompts", "argv": argv, "env": {}}], r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead}


@route("GET", "/api/clips")
def _get(r: Request):
    try:
        d = _book(r.q("project"))
        return _view(d, _style(d, r.q("style")))
    except PlanError:
        return {"style": "", "set": "", "clips": [], "approved": 0, "checklist": list(clips.CHECKLIST), "motion": False, "styles": [], "master": "",
                "gate": {"approved": False, "approved_at": "", "changed_since": False}}


@route("POST", "/api/clips_render")
def _render(r: Request):
    d = _book(r.body.get("project"))
    sid = _style(d, str(r.body.get("style") or ""))
    try:
        made = clips.prepare(d, sid)
    except clips.ClipError as e:
        raise PlanError(str(e)) from e
    service, gpu, model = r.body.get("service"), r.body.get("gpu"), str(r.body.get("video_model", ""))
    if service not in GPUS or gpu not in [g for g, _ in GPUS[service]]:
        raise PlanError("choose where the models run, and the GPU")
    if gpu_blocker(service, gpu):
        raise PlanError(gpu_blocker(service, gpu))
    if model not in I2V_MODELS:
        raise PlanError(f"choose a 'from a picture' video model: {', '.join(sorted(I2V_MODELS))}")
    check_models(service, gpu, [model])
    user = str(r.body.get("kaggle_user") or "").strip()
    if service == "kaggle" and not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", user):
        raise PlanError("enter your Kaggle username (letters, digits, - and _)")
    try:
        first, last = int(r.body.get("first") or 1), int(r.body.get("last") or made["rows"])
    except (TypeError, ValueError) as e:
        raise PlanError("first and last are row numbers") from e
    if not 1 <= first <= last <= made["rows"]:
        raise PlanError(f"rows must be within 1-{made['rows']}")
    argv, env = make_runner(service, gpu, user, made["set"])(model, first, last, "all_shots.csv")
    env["KEYFRAME_MODEL"] = clips.KEYFRAMES
    ahead = JOB.start([{"label": f"Make the {sid} clips {first}-{last}", "argv": argv, "env": env}], r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead}


@route("POST", "/api/clip_review")
def _review(r: Request):
    d = _book(r.body.get("project"))
    sid = _style(d, str(r.body.get("style") or ""))
    try:
        clips.review(d, sid, int(r.body.get("row", 0)), r.body.get("approved") if isinstance(r.body.get("approved"), bool) else None,
                     str(r.body["note"]) if "note" in r.body else None)
    except (clips.ClipError, TypeError, ValueError) as e:
        raise PlanError(str(e)) from e
    return _view(d, sid)


@route("POST", "/api/clips_approve")
def _approve(r: Request):
    d = _book(r.body.get("project"))
    sid = _style(d, str(r.body.get("style") or ""))
    try:
        clips.approve_all(d, sid)
    except clips.ClipError as e:
        raise PlanError(str(e)) from e
    return _view(d, sid)
