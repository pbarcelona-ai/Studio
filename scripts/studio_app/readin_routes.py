"""READ IT IN for the page (milestone M3): start the job, show its results (screenplay, coverage, beat sheet, treatment, crew notes) and export.

POST /api/read_it_in {project, engine, claude_model, force}   start scripts/read_it_in.py as a background job (the job log shows the progress)
GET  /api/readin?project=                                    {progress, summary, coverage, development, plan, beats, treatment, critique, script, exports}
POST /api/readin_export {project, formats: [pdf, fountain, docx, fdx, notes]}   write projects/books/<book>/exports/ and list the downloads
"""
from __future__ import annotations

import json
from pathlib import Path

import read_it_in
import screenplay_export
from layout import project_dir

from .api import Request, route
from .common import PlanError
from .jobs import JOB
from .steps import engine_args


def _book(slug: str) -> Path:
    try:
        d = project_dir(str(slug or ""), "book")
    except ValueError as e:
        raise PlanError(str(e)) from e
    if not d.is_dir():
        raise PlanError("pick a book first")
    return d


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def exports_of(d: Path) -> list[dict]:
    ex = d / "exports"
    names = ["screenplay.pdf", "screenplay.fountain", "screenplay.docx", "screenplay.fdx", "readin_notes.pdf"]
    return [{"name": n, "url": f"/download/{d.name}/exports/{n}", "bytes": (ex / n).stat().st_size} for n in names if (ex / n).is_file()]


def readin_step(body: dict) -> dict:
    slug = str(body.get("project") or "")
    _book(slug)
    engine = str(body.get("engine") or "claude")
    argv = ["python3", "read_it_in.py", slug] + (["--engine", "fake"] if engine == "fake" else engine_args(body))
    if body.get("force"):
        argv.append("--force")
    return {"label": "Read it in: from the sources to a shooting script", "argv": argv, "env": {}}


@route("POST", "/api/read_it_in")
def _start(r: Request):
    step = readin_step(r.body)
    ahead = JOB.start([step], r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead}


@route("GET", "/api/readin")
def _get(r: Request):
    try:
        d = _book(r.q("project"))
    except PlanError:                                         # not a book (an imported one, or none yet): nothing to show
        return {"progress": None, "summary": None, "coverage": None, "development": None, "plan": None, "beats": None, "treatment": "",
                "critique": [], "script": "", "exports": []}
    rd = read_it_in.folder(d)
    sp = _read(rd / "screenplay.json") or {}
    script = read_it_in.script_text(sp["scenes"]) if sp.get("scenes") else ""
    treatment = (rd / "treatment.md").read_text(encoding="utf-8") if (rd / "treatment.md").is_file() else ""
    return {"progress": _read(rd / "progress.json"), "summary": _read(rd / "summary.json"), "coverage": _read(rd / "coverage.json"),
            "development": _read(rd / "development.json"), "plan": _read(rd / "plan.json"), "beats": _read(rd / "beats.json"),
            "treatment": treatment, "critique": _read(rd / "critique.json") or [], "script": script, "exports": exports_of(d)}


@route("POST", "/api/readin_export")
def _export(r: Request):
    d = _book(str(r.body.get("project") or ""))
    formats = r.body.get("formats") or list(screenplay_export.FORMATS)
    if not isinstance(formats, list) or not all(f in screenplay_export.FORMATS for f in formats):
        raise PlanError(f"formats must be some of {', '.join(screenplay_export.FORMATS)}")
    try:
        screenplay_export.export(d, tuple(formats))
    except ValueError as e:
        raise PlanError(str(e)) from e
    return {"exports": exports_of(d)}
