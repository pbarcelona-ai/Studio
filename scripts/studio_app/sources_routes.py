"""Sources and the format / products / styles step, for the page (milestone M2). Files are streamed in by handler.py (/api/source_upload).

GET  /api/sources?project=                        {sources: [...], total_words, max_words, needs_description, accepted}
POST /api/source_add {project, kind: idea|website, text|url, title, rights: true, note}
POST /api/source_remove {project, id}
POST /api/source_describe {project, id, engine}   the Story Analyst describes pictures / reads comic panels (one AI call per picture)
POST /api/sources_to_chapters {project}           make the chapters from the sources (for the chapter step and Read it in)
GET  /api/production?project=                     {settings, notes, estimate, catalog}
POST /api/production {project, recipe, products, target_minutes, aspect, rating, faithfulness, tier, styles, master}
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import bookkit
import crew
import production
import sources
from layout import project_dir

from .api import Request, route
from .common import PlanError


def book_dir(r: Request, create: bool = False) -> Path:
    slug = str((r.body or {}).get("project") or r.q("project"))
    try:
        pdir = project_dir(slug, "book")
    except ValueError as e:
        raise PlanError(str(e)) from e
    if not pdir.is_dir():
        if not create:
            raise PlanError(f"no book called {slug!r}")
        pdir.mkdir(parents=True)
    return pdir


def _wrap(fn):
    try:
        return fn()
    except sources.SourceError as e:
        raise PlanError(str(e)) from e


@route("GET", "/api/sources")
def _list(r: Request):
    try:
        pdir = book_dir(r)
    except PlanError:
        return {**sources.summary(Path(tempfile.gettempdir()) / "no-such-studio-book"), "sources": []}
    return sources.summary(pdir)


@route("POST", "/api/source_add")
def _add(r: Request):
    pdir = book_dir(r, create=True)
    kind = str(r.body.get("kind", ""))
    agreed = r.body.get("rights") is True
    note = str(r.body.get("note", ""))

    def go():
        if kind == "idea":
            doc = sources.from_idea(str(r.body.get("text", "")), str(r.body.get("title", "")))
            doc.rights_note = note
            return sources.store(pdir, doc, agreed)
        if kind == "website":
            if not agreed:
                raise sources.SourceError("Tick the box to confirm you have the right to use this source.")
            with tempfile.TemporaryDirectory(prefix="studio-web-") as t:
                doc, files = sources.from_url(str(r.body.get("url", "")), Path(t))
                doc.rights_note = note
                return sources.store(pdir, doc, agreed, files)
        raise sources.SourceError("kind must be idea or website (files are uploaded)")
    entry = _wrap(go)
    return {"added": entry, **sources.summary(pdir)}


@route("POST", "/api/source_remove")
def _remove(r: Request):
    pdir = book_dir(r)
    _wrap(lambda: sources.remove(pdir, str(r.body.get("id", ""))))
    return sources.summary(pdir)


@route("POST", "/api/source_describe")
def _describe(r: Request):
    pdir = book_dir(r)
    sid = str(r.body.get("id", ""))
    engine = str(r.body.get("engine", "claude"))
    _wrap(lambda: sources.get(pdir, sid))
    try:
        entry = sources.describe(pdir, sid, bookkit.llm_json, crew.system, engine=engine)
    except (RuntimeError, ValueError) as e:
        raise PlanError(f"the pictures could not be described: {e}") from e
    return {"described": entry, **sources.summary(pdir)}


@route("POST", "/api/sources_to_chapters")
def _to_chapters(r: Request):
    pdir = book_dir(r)
    n = _wrap(lambda: sources.write_chapters(pdir))
    return {"chapters": n, **sources.summary(pdir)}


@route("GET", "/api/production")
def _production(r: Request):
    try:
        pdir = book_dir(r)
    except PlanError:                                          # not a book (yet): the page shows nothing
        return {"settings": None, "notes": [], "estimate": None, "catalog": production.catalog()}
    d = production.load(pdir)
    return {"settings": d, "notes": [], "estimate": production.estimate(d), "catalog": production.catalog()}


@route("POST", "/api/production")
def _production_save(r: Request):
    pdir = book_dir(r)
    body = {k: v for k, v in r.body.items() if k != "project"}
    try:
        d, notes = production.save(pdir, body)
    except ValueError as e:
        raise PlanError(str(e)) from e
    early_audit = None
    try:
        from studio_app import early_prompt_audit
        early_audit = early_prompt_audit.audit_step(pdir, pdir.name, 4, use_llm=False, auto_apply=False, record_bidirectional=False)
    except Exception:
        early_audit = None
    return {"settings": d, "notes": notes, "estimate": production.estimate(d), "catalog": production.catalog(), "early_audit": early_audit}


def upload(pdir: Path, tmp: Path, fname: str, agreed: bool, comic: bool, title: str, note: str) -> dict:
    """A streamed file (handler.py) becomes a source: the adapter reads it from a private temp folder, then it moves into the source's folder."""
    named = tmp.with_name(fname)
    tmp.replace(named)
    try:
        doc = sources.from_file(named, comic=comic, ocr=False)   # no minutes-long OCR inside a request: scanned books go through Read book (a job)
        if title:
            doc.title = title
        doc.rights_note = note
        return sources.store(pdir, doc, agreed, [named])
    finally:
        named.unlink(missing_ok=True)
