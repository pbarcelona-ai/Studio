"""Automatic and manual clean-up of old Kaggle notebooks and local notebook files."""
from typing import Any
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta, UTC
from pathlib import Path
from bookkit import SLUG_RE
import layout

from .common import PlanError
from .config import ENV_PATH, ROOT, clean_env
from .jobs import JOB
from .kaggle_runs import STATUS_PAUSE, guess_project, kaggle_runs, kaggle_status_of, kernel_ref


KEEP_KAGGLE_NOTEBOOKS = 3
ACTIVE_STATUSES = {"RUNNING", "QUEUED", "NEW", "UNKNOWN"}          # never delete a notebook that may still be running (or whose state is unknown)


def kaggle_cleanup_scan():
    """Which of YOUR Kaggle notebooks made by this tool would be deleted: all but the newest KEEP_KAGGLE_NOTEBOOKS. Read-only.
    Only notebooks whose names match this tool's naming are considered; anything else in the account is never listed."""
    runs: list = sorted(kaggle_runs(limit=100), key=lambda r: r["last_run"], reverse=True)
    keep = runs[:KEEP_KAGGLE_NOTEBOOKS]
    remove: list = []
    busy: list = []
    for r in runs[KEEP_KAGGLE_NOTEBOOKS:]:
        (busy if r["status"] in ACTIVE_STATUSES else remove).append(r)
    return {"keep": keep, "remove": remove, "busy": busy, "keep_count": KEEP_KAGGLE_NOTEBOOKS}


def kaggle_cleanup_delete():
    """Delete the notebooks the scan lists (it is re-run here: the browser never names what to delete)."""
    if JOB.running:
        raise PlanError("a job is running; wait for it to finish first")
    deleted, failed = delete_kaggle_runs(kaggle_cleanup_scan()["remove"])
    return {"deleted": deleted, "failed": failed}


AUTO_CLEAN_OFF = Path.home() / ".pistachios_studio" / "auto_cleanup_off"     # this file exists = the person turned automatic clean-up off
AUTO_CLEAN_EVERY = 3600                     # asking Kaggle about every notebook takes a while: at most once an hour
_AUTO_CLEAN: dict[str, Any] = {"lock": threading.Lock(), "last": 0.0}


def run_results_here(slug):
    """Are all the results of this Kaggle run on this computer? Reads the run's name, <book>-<model>[-chapters|-keyframes]-<first row>-<last row>.
    True only when every row has its file (a retaken row counts, in takes/). Anything unclear is False: that notebook may hold the only copy."""
    project = guess_project(slug)
    d = layout.find_dir(project) if project and SLUG_RE.match(project) else None
    prefix = (project or "").replace("_", "-") + "-"
    m = re.fullmatch(r"(.+?)(-chapters|-keyframes)?-(\d+)-(\d+)", slug[len(prefix):]) if d and slug.startswith(prefix) else None
    if not m or d is None:
        return False
    model, mode, lo, hi = m.group(1).replace("-", "_"), (m.group(2) or "")[1:], int(m.group(3)), int(m.group(4))
    suffix = f"_{mode}" if mode else ""
    if model.startswith("audio_"):
        folder = d / "audio" / (model[len("audio_"):] + suffix)
    elif model.startswith("image_"):
        folder = d / "images" / (model[len("image_"):] + suffix)
    elif model.startswith("upscale_"):
        return False                            # its folder is named after the clips it enlarged, which the name does not say
    else:
        folder = d / "videos" / (model + suffix)
    if not folder.is_dir() or hi < lo:
        return False
    have = {int(x.group(1)) for p in folder.rglob("*-*") if p.is_file() and (x := re.match(r"[a-z]+-(\d{4})(?:-t\d+)?\.(?:mp4|png|wav)$", p.name))}
    return all(n in have for n in range(lo, hi + 1))


FAILED_RUN_KEEP_DAYS = 7


def run_older_than(run, days):
    """Was this run last started more than this many days ago? A date that cannot be read counts as recent."""
    try:
        when = datetime.strptime(run["last_run"][:16], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    except (KeyError, TypeError, ValueError):
        return False
    return datetime.now(UTC) - when > timedelta(days=days)


def auto_cleanup_plan():
    """What automatic clean-up would delete on Kaggle: finished notebooks outside the newest few whose results are all on this computer, and old failed ones.
    Read-only. A notebook that finished but whose results are not all here is kept: deleting it would lose them. A failed one waits FAILED_RUN_KEEP_DAYS days. {"remove", "kept_not_downloaded"}"""
    kaggle = shutil.which("kaggle", path=ENV_PATH)
    runs = sorted(kaggle_runs(limit=100, with_status=False), key=lambda r: r["last_run"], reverse=True)[KEEP_KAGGLE_NOTEBOOKS:]
    remove: list = []
    kept: list = []
    for r in runs:
        here, old = run_results_here(r["slug"]), run_older_than(r, FAILED_RUN_KEEP_DAYS)
        if not here and not old:              # nothing could make it deletable, so Kaggle need not be asked about it
            kept.append(r)
            continue
        r["status"] = kaggle_status_of(kaggle, r["ref"])
        time.sleep(STATUS_PAUSE)
        if r["status"] in ACTIVE_STATUSES:
            continue
        if r["status"] == "COMPLETE":
            (remove if here else kept).append(r)
        else:                                 # a run that failed part way can still hold clips, so it waits a while
            remove.append(r)
    return {"remove": remove, "kept_not_downloaded": kept}


def delete_kaggle_runs(runs):
    """Delete these Kaggle notebooks. Returns (deleted refs, failures)."""
    kaggle = shutil.which("kaggle", path=ENV_PATH)
    if not kaggle:
        raise PlanError("the kaggle command is not installed (uv tool install kaggle)")
    deleted, failed = [], []
    for r in runs:
        ref = kernel_ref(r["ref"])
        t = subprocess.run([kaggle, "kernels", "delete", "-y", ref], env=clean_env(), capture_output=True, text=True, timeout=60)
        if t.returncode == 0:
            deleted.append(ref)
        else:
            failed.append({"ref": ref, "error": (t.stderr or t.stdout).strip()[-200:]})
    return deleted, failed


def auto_cleanup(force=False):
    """Delete generated notebooks that are no longer in use, here and on Kaggle, unless turned off. Runs in the background when the Studio starts and after each job."""
    if AUTO_CLEAN_OFF.exists() or JOB.running or not _AUTO_CLEAN["lock"].acquire(blocking=False):
        return
    try:
        local = delete_notebooks()
        if local["notebooks"] or local["scripts"]:
            JOB.log(f"clean-up: deleted {local['notebooks']} old local notebook(s) and {local['scripts']} script(s)")
        if not force and time.time() - _AUTO_CLEAN["last"] < AUTO_CLEAN_EVERY:
            return
        _AUTO_CLEAN["last"] = time.time()
        if not (Path.home() / ".kaggle").is_dir() or not shutil.which("kaggle", path=ENV_PATH):
            return
        plan = auto_cleanup_plan()
        if JOB.running:                         # a new job started while Kaggle was answering: leave everything for next time
            return
        deleted, failed = delete_kaggle_runs(plan["remove"])
        if deleted or failed or plan["kept_not_downloaded"]:
            JOB.log(f"clean-up on Kaggle: deleted {len(deleted)} old notebook(s)" + (f", {len(failed)} could not be deleted" if failed else "") +
                    (f"; kept {len(plan['kept_not_downloaded'])} whose results are not all on this computer" if plan["kept_not_downloaded"] else ""))
    except (PlanError, OSError, subprocess.SubprocessError) as e:     # never disturbs anything: it tries again next time
        JOB.log(f"clean-up skipped: {e}")
    finally:
        _AUTO_CLEAN["lock"].release()


def start_auto_cleanup():
    threading.Thread(target=auto_cleanup, daemon=True).start()


def recreate_notebooks():
    r = subprocess.run(["python3", "scripts/make_all.py"], cwd=ROOT, env=clean_env(), capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise PlanError("could not re-create the notebooks: " + (r.stderr or r.stdout)[-300:])
    return {"notebooks": len(list(ROOT.glob("Studio_*.ipynb"))), "scripts": len(list(ROOT.glob("colab_generate_*.py")))}


def delete_notebooks():
    """Delete all generated notebook and script files."""
    deleted = {"notebooks": 0, "scripts": 0}
    for pattern in ("Studio_*.ipynb", "colab_generate_*.py"):
        for f in ROOT.glob(pattern):
            f.unlink()
            if f.suffix == ".ipynb":
                deleted["notebooks"] += 1
            else:
                deleted["scripts"] += 1
    return deleted
