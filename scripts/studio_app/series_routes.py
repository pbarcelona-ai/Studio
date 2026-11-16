"""Episodes and series, the production queue, and the marketing kit, for the page (milestone M14; Sections 6e, 1 product G, 13).

POST /api/series_split {project, episodes?, engine, claude_model}   the Development Executive splits the book into episodes (a job)
GET  /api/series?project=                       {episodes: [{n, slug, title, ..., state}], series: the series book (for an episode), next}
POST /api/series_sync {project}                 an episode takes the series' continuity book, styles, voices and settings again
POST /api/series_next {project, engine, claude_model}   "Make next episode": Read it in on the next episode (Autopilot carries on in M15)
GET  /api/queue                                 the production queue: the running job, the jobs waiting, their cost and finish estimate
POST /api/queue_add {projects: [...], what: read_it_in, engine}     several books or episodes, one after another
POST /api/marketing_plan {project, engine, claude_model}   the Trailer Editor's plan (a job)
GET  /api/marketing?project=                    {plan, kits: {style: [files]}}
POST /api/marketing_render {project, style?}    cut and draw the kit in one style or in every style (a job)
"""
from __future__ import annotations

import time
from pathlib import Path

import layout
import marketing
import production
import series
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


def _engine(body: dict) -> list[str]:
    return ["--engine", "fake"] if str(body.get("engine") or "claude") == "fake" else engine_args(body)


def _state(slug: str) -> str:
    d = layout.find_dir(slug)
    if d is None:
        return "not made"
    for f, word in (("exports", "film made"), ("edit", "being edited"), ("pictures", "pictures"), ("shots", "shot list"), ("readin", "screenplay")):
        if (d / f).exists():
            return word
    return "ready to read in"


@route("POST", "/api/series_split")
def _split(r: Request):
    d = _book(r.body.get("project"))
    try:
        n = max(0, min(series.MAX_EPISODES, int(r.body.get("episodes") or 0)))
    except (TypeError, ValueError) as e:
        raise PlanError("episodes is a number") from e
    argv = ["python3", "series.py", d.name, "--episodes", str(n)] + _engine(r.body)
    ahead = JOB.start([{"label": "Split the story into episodes", "argv": argv, "env": {}}], r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead}


@route("GET", "/api/series")
def _get(r: Request):
    try:
        d = _book(r.q("project"))
    except PlanError:
        return {"episodes": [], "series": None, "next": None}
    s = series.series_of(d)
    home = s or d
    eps = [{**e, "state": _state(e["slug"])} for e in series.load(home).get("episodes", [])]
    nxt = series.next_episode(home)
    return {"episodes": eps, "series": s.name if s else None, "next": nxt["slug"] if nxt else None}


@route("POST", "/api/series_sync")
def _sync(r: Request):
    d = _book(r.body.get("project"))
    try:
        return {"synced": series.sync(d)}
    except series.SeriesError as e:
        raise PlanError(str(e)) from e


@route("POST", "/api/series_next")
def _next(r: Request):
    d = _book(r.body.get("project"))
    home = series.series_of(d) or d
    e = series.next_episode(home)
    if e is None:
        raise PlanError("every episode has its screenplay: nothing to make next")
    ep = layout.find_dir(e["slug"])
    if ep is not None:
        series.sync(ep)
    ahead = JOB.start([{"label": f"Episode {e['n']}: Read it in", "argv": ["python3", "read_it_in.py", e["slug"]] + _engine(r.body), "env": {}}],
                      {**r.body, "project": e["slug"]}, queue=True)
    return {"episode": e["slug"], "ahead": ahead}


# ---------------------------------------------------------------------------------------------- the production queue
def _estimate(slug: str) -> dict:
    d = layout.find_dir(slug)
    if d is None:
        return {"gpu_hours": 0.0, "dollars": 0.0, "text_calls": 0}
    e = production.estimate(production.load(d))
    return {"gpu_hours": e["gpu_hours"], "dollars": e["dollars"], "text_calls": e["text_calls"]}


@route("GET", "/api/queue")
def _queue(r: Request):
    waiting = []
    for steps, opt in list(getattr(JOB, "queue", [])):
        slug = str(opt.get("project") or "")
        waiting.append({"project": slug, "steps": [s.get("label", "") for s in steps], **(_estimate(slug) if slug else {})})
    hours = sum(w.get("gpu_hours", 0.0) for w in waiting)
    calls = sum(w.get("text_calls", 0) for w in waiting)
    secs = hours * 3600 + calls * 40                          # about 40 s per writing call
    return {"running": {"step": JOB.current, "project": (getattr(JOB, "state", {}) or {}).get("project", "")} if JOB.running else None,
            "waiting": waiting, "total": {"gpu_hours": round(hours, 1), "dollars": round(sum(w.get("dollars", 0.0) for w in waiting), 2),
                                          "finish": time.strftime("%a %H:%M", time.localtime(time.time() + secs)) if waiting else ""}}


@route("POST", "/api/queue_add")
def _queue_add(r: Request):
    names = r.body.get("projects")
    if not isinstance(names, list) or not names:
        raise PlanError("projects is a list of book names")
    if str(r.body.get("what") or "read_it_in") != "read_it_in":
        raise PlanError("the queue runs Read it in for each book (the rest follows from its steps)")
    added = []
    for n in names:
        d = _book(n)
        JOB.start([{"label": f"{d.name}: Read it in", "argv": ["python3", "read_it_in.py", d.name] + _engine(r.body), "env": {}}],
                  {**r.body, "project": d.name}, queue=True)
        added.append(d.name)
    return {"queued": added}


# ---------------------------------------------------------------------------------------------- the marketing kit
@route("POST", "/api/marketing_plan")
def _mk_plan(r: Request):
    d = _book(r.body.get("project"))
    argv = ["python3", "marketing.py", d.name] + _engine(r.body)
    ahead = JOB.start([{"label": "Plan the marketing kit", "argv": argv, "env": {}}], r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead}


@route("GET", "/api/marketing")
def _mk_get(r: Request):
    try:
        d = _book(r.q("project"))
    except PlanError:
        return {"plan": None, "kits": {}}
    kits = {}
    for s in production.load(d)["styles"]:
        f = d / "exports" / f"marketing_{s['id']}"
        if f.is_dir():
            kits[s["id"]] = [{"name": x.name, "url": f"/file/{d.name}/exports/marketing_{s['id']}/{x.name}"} for x in sorted(f.iterdir())
                             if x.suffix in (".mp4", ".png")] + ([{"name": "captions.txt", "text": (f / "captions.txt").read_text(encoding="utf-8")}] if (f / "captions.txt").is_file() else [])
    return {"plan": marketing.load(d) or None, "kits": kits}


@route("POST", "/api/marketing_render")
def _mk_render(r: Request):
    d = _book(r.body.get("project"))
    if not marketing.load(d):
        raise PlanError("plan the marketing kit first")
    sids = [s["id"] for s in production.load(d)["styles"]]
    sid = str(r.body.get("style") or "")
    if sid and sid not in sids:
        raise PlanError(f"{sid} is not one of this book's styles")
    steps = [{"label": f"Cut the {s} marketing kit", "argv": ["python3", "marketing.py", d.name, "--render", s], "env": {}} for s in ([sid] if sid else sids)]
    ahead = JOB.start(steps, r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead}
