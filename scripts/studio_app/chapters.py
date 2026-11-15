"""The Chapters card: list a book's chapters, read one, and edit them (rename, merge, split, drop) with chapter_edit.py."""
from pathlib import Path

import chapter_edit
from bookkit import SLUG_RE
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .common import PlanError
from .config import LEGACY


def _book(slug) -> Path:
    slug = str(slug or "")
    if not SLUG_RE.match(slug) or slug in LEGACY or not pdir(slug).is_dir():
        raise PlanError("pick a book that has been started")
    return pdir(slug)


def chapter_list(slug):
    try:
        return chapter_edit.load(_book(slug))
    except chapter_edit.ChapterEditError as e:
        raise PlanError(str(e)) from e


def chapter_text(slug, n):
    try:
        return chapter_edit.read_chapter(_book(slug), int(n))
    except (chapter_edit.ChapterEditError, ValueError) as e:
        raise PlanError(str(e)) from e


def chapter_edit_action(b):
    """POST body: {project, action: rename|merge|split|drop, n | ns, title, at, force}"""
    d, action, force = _book(b.get("project")), b.get("action"), bool(b.get("force"))
    try:
        if action == "rename":
            return chapter_edit.rename(d, b.get("n"), b.get("title", ""))
        if action == "merge":
            return chapter_edit.merge(d, b.get("n"), force)
        if action == "split":
            return chapter_edit.split(d, b.get("n"), b.get("at"), b.get("title") or None, force)
        if action == "drop":
            return chapter_edit.drop(d, b.get("ns"), force)
    except chapter_edit.ChapterEditError as e:
        raise PlanError(str(e)) from e
    raise PlanError("unknown chapter action")
