"""Shared by every module: PlanError (a mistake the person can fix; answered as HTTP 400), number validation and project-file lookup."""
from pathlib import Path
from typing import Any

from bookkit import SLUG_RE
import layout

from .config import ROOT


class PlanError(ValueError):
    """The request cannot be planned or done as asked; the message says what to change. Answered to the page as HTTP 400."""


def num(opt: dict, key: str, default: float, cast: type = float, lo: float | None = None, hi: float | None = None) -> Any:
    """opt[key] (or the default) as a number of type `cast`, refusing NaN and values outside lo..hi with a PlanError."""
    try:
        v = cast(opt.get(key) if opt.get(key) not in (None, "") else default)
    except (TypeError, ValueError):
        raise PlanError(f"{key} must be a number") from None
    if cast is float and v != v:                       # NaN passes every comparison below
        raise PlanError(f"{key} must be a number")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise PlanError(f"{key} must be between {lo} and {hi}")
    return v


def resolve_project_file(spec: object) -> Path:
    """A file named as '<project>/<path inside it>' (e.g. 'char_adam/images/sdxl_turbo/image-0001.png') or as a path from the repository
    root ('projects/characters/char_adam/...'). The project name is looked up in books/, characters/ and prompts/ (see layout.py)."""
    spec = str(spec).replace("\\", "/").lstrip("/")
    if spec.startswith("projects/"):
        return ROOT / spec
    head, _, rest = spec.partition("/")
    found = layout.find_dir(head) if SLUG_RE.match(head) else None
    if found:
        return found / rest
    return ROOT / spec                    # not a project: the caller's "must be within projects/" check refuses it
