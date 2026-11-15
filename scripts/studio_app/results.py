"""Get results: the Kaggle runs of one book (or prompt set) of one kind (keyframes, images, video, audio), and downloading the ones whose waiting
process has ended (the Studio was closed, the laptop slept) into the right folders.

GET  /api/results?project=&kind=      {runs: [{ref, slug, kind, model, rows, status, have, wanted, needs}], kaggle: bool}
POST /api/get_results {project, kind} start (or queue) one "fetch" step per run that finished and is not all here; a run still going is waited for
"""
import re
import shutil
from functools import lru_cache

import kaggle_names
from bookkit import SLUG_RE
from layout import project_dir as pdir

from .common import PlanError
from .config import ENV_PATH
from .kaggle_runs import fetch_step, kaggle_runs, kaggle_status_of

KINDS = ("keyframes", "image", "video", "audio", "any")
TAIL = re.compile(r"^(?P<model>.+?)(?P<mode>-chapters|-scenes|-keyframes)?-(?P<a>\d+)-(?P<b>\d+)$")


@lru_cache(maxsize=256)
def _cksum5(text: str) -> str:
    """The short number run_kaggle_model puts in a name that was too long (kaggle_names.py: the first 5 digits of the POSIX cksum)."""
    return kaggle_names.cksum5(text)


def tail_of(slug: str, project: str) -> str | None:
    """What follows the project's part of a notebook name (model, mode, rows), or None when the notebook is not this project's.
    A long project name was cut and given a number (kaggle_names.sh), so both forms are understood."""
    name = project.replace("_", "-")
    h = _cksum5(name)
    for s in (slug, slug.split("-", 1)[-1]):                 # very old runs had one extra word in front
        if s.startswith(name + "-"):
            return s[len(name) + 1:]
        m = re.match(rf"^(?P<cut>[a-z0-9-]+?)-{h}-(?P<rest>.+)$", s) if h else None
        if m and name.startswith(m.group("cut")):
            return m.group("rest")
    return None


def kind_of(tail: str) -> tuple[str, str, str, int, int] | None:
    """(kind, model, mode, first row, last row) from the end of a notebook name."""
    m = TAIL.match(tail)
    if not m:
        return None
    model, mode, a, b = m.group("model").replace("-", "_"), m.group("mode") or "", int(m.group("a")), int(m.group("b"))
    if model.startswith("image_"):
        return ("keyframes" if mode == "-keyframes" else "image"), model.removeprefix("image_"), mode, a, b
    if model.startswith("audio_"):
        return "audio", model.removeprefix("audio_"), mode, a, b
    return "video", model, mode, a, b


def _have(d, kind: str, model: str, mode: str, a: int, b: int) -> int:
    """How many of the run's rows already have their file in the project."""
    if kind == "keyframes":
        folder, pats = d / "images" / f"{model}_keyframes", ["image-{:04d}.png"]
    elif kind == "image":
        folder, pats = d / "images" / model, ["image-{:04d}.png"]
    elif kind == "audio":
        folder, pats = d / "audio" / (model + mode.replace("-", "_")), ["narration-{:04d}.wav", "sfx-{:04d}.wav", "music-{:04d}.wav"]
    else:
        folder, pats = d / "videos" / (model + mode.replace("-", "_")), ["shot-{:04d}.mp4"]
    if not folder.is_dir():
        return 0
    return sum(1 for n in range(a, b + 1) if any((folder / p.format(n)).is_file() for p in pats))


def results_data(project: str, kind: str = "any", with_status: bool = True) -> dict:
    if not SLUG_RE.match(project or "") or not pdir(project).is_dir():
        raise PlanError("pick a book first")
    if kind not in KINDS:
        raise PlanError("kind must be keyframes, image, video, audio or any")
    if not shutil.which("kaggle", path=ENV_PATH):
        return {"runs": [], "kaggle": False}
    d = pdir(project)
    mine = []
    for r in kaggle_runs(limit=60, with_status=False):
        t = tail_of(r["slug"], project)
        found = kind_of(t) if t else None
        if not found or kind not in ("any", found[0]):
            continue
        mine.append((r, found))
    mine = mine[:12]
    kaggle = shutil.which("kaggle", path=ENV_PATH) or "kaggle"
    out = []
    for r, (k, model, mode, a, b) in mine:
        st = kaggle_status_of(kaggle, r["ref"]) if with_status else ""
        have = _have(d, k, model, mode, a, b)
        wanted = b - a + 1
        needs = have < wanted and st in ("COMPLETE", "ERROR", "RUNNING", "QUEUED", "")
        out.append({"ref": r["ref"], "slug": r["slug"], "kind": k, "model": model, "rows": [a, b], "status": st, "have": have, "wanted": wanted,
                    "needs": needs, "last_run": r.get("last_run", "")})
    return {"runs": out, "kaggle": True}


def results_steps(b: dict) -> tuple[list[dict], dict]:
    """The fetch steps for every run of this kind that is not all here: a finished one is downloaded, one still going is waited for."""
    project, kind = str(b.get("project") or ""), str(b.get("kind") or "any")
    data = results_data(project, kind)
    if not data["kaggle"]:
        raise PlanError("the kaggle command is not installed (uv tool install kaggle)")
    todo = [r for r in data["runs"] if r["needs"]]
    if not todo:
        what = {"keyframes": "pictures", "image": "pictures", "video": "clips", "audio": "sounds"}.get(kind, "results")
        raise PlanError(f"Nothing to get: every Kaggle run of {what} for this book is already here (or there is none).")
    steps = [fetch_step({"slug": r["slug"], "project": project, "wait": r["status"] in ("RUNNING", "QUEUED")}) for r in todo]
    return steps, {"project": project, "keep_going": True, "queue": True}
