"""The conflict prompt (BOOK_TO_SCREEN_BUILD.md Section 6c, milestone M12): an edit made while a job is changing the same thing.

check(kind, body) raises a 409 HttpError ("conflict: ...") when the running job's program writes what the owner is editing, unless the page sends
force: true. The page then shows both versions (the job's, the owner's) and asks which to keep; keeping the owner's sends the edit again with force.
"""
from __future__ import annotations

from .api import HttpError
from .jobs import JOB

WRITERS = {"shotlist": ("shot_list.py",), "continuity": ("continuity_book.py", "book_continuity.py"), "edit": ("render_cut.py",),
           "screenplay": ("read_it_in.py", "book_screenplay.py")}


def running_writer(kind: str) -> str:
    """The step of the running job that writes `kind`, or ""."""
    if not JOB.running:
        return ""
    steps = (getattr(JOB, "state", {}) or {}).get("steps", [])
    idx = int((getattr(JOB, "state", {}) or {}).get("index", 0) or 0)
    step = steps[idx] if 0 <= idx < len(steps) else {}
    argv = " ".join(str(a) for a in step.get("argv", []))
    return step.get("label", "a job") if any(w in argv for w in WRITERS.get(kind, ())) else ""


def check(kind: str, body: dict) -> None:
    if body.get("force"):
        return
    who = running_writer(kind)
    if who:
        raise HttpError(409, f"conflict: {who} is changing this right now. Keep your change (it may be overwritten when the job saves), or wait for the job.")
