"""studio_app.common"""
from bookkit import SLUG_RE
import layout

from .config import ROOT


class PlanError(ValueError):
    pass


def num(opt, key, default, cast=float, lo=None, hi=None):
    try:
        v = cast(opt.get(key) if opt.get(key) not in (None, "") else default)
    except (TypeError, ValueError):
        raise PlanError(f"{key} must be a number") from None
    if cast is float and v != v:                       # NaN passes every comparison below
        raise PlanError(f"{key} must be a number")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise PlanError(f"{key} must be between {lo} and {hi}")
    return v


def resolve_project_file(spec):
    """A file named as '<project>/<path inside it>' (e.g. 'char_adam/images/sdxl_turbo/image-0001.png') or as a path from the repository
    root ('projects/characters/char_adam/...'). The project name is looked up in books/, characters/ and prompts/ (see layout.py)."""
    spec = str(spec).replace("\\", "/").lstrip("/")
    if spec.startswith("projects/"):
        return ROOT / spec
    head, _, rest = spec.partition("/")
    if SLUG_RE.match(head) and layout.find_dir(head):
        return layout.find_dir(head) / rest
    return ROOT / spec                    # not a project: the caller's "must be within projects/" check refuses it
