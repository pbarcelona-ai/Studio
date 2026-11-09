"""studio_app.kaggle_runs"""
import csv
import io
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from bookkit import SLUG_RE
import layout
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .common import PlanError
from .config import ENV_PATH, ROOT, clean_env


# ---------------------------------------------------------------- Kaggle runs: list them and fetch their results
KERNEL_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,120}$")


# Notebook names made by run_kaggle_model.sh:  <project>-<model><-chapters>-<first row>-<last row>   (very old runs had one extra word in front; guess_project skips it)
TOOL_SLUG_RE = re.compile(r"^[a-z0-9-]+?-(?:image-[a-z0-9-]+?|audio-[a-z0-9-]+?|ltx-video|wan[a-z0-9]*(?:-[a-z0-9]+)*?|hunyuan-video(?:-lora|-nsfw)?|cogvideox(?:-5b)?|tpu-[a-z0-9-]+?)(?:-chapters)?-\d+-\d+$")


def guess_project(slug):
    """Longest book / character set / prompt set whose name (underscores -> dashes) starts the notebook name (same rule as fetch_kaggle_run.sh)."""
    for name in (slug, slug.split("-", 1)[-1]):           # very old runs had one extra word in front of the project name
        best = ""
        for d in layout.all_dirs():
            if d.is_dir() and name.startswith(f"{d.name.replace('_', '-')}-") and len(d.name) > len(best):
                best = d.name
        if best:
            return best
    return ""


def kaggle_status_of(kaggle, ref):
    """One notebook's status from Kaggle; UNKNOWN if Kaggle does not say (for example it is limiting how fast we may ask). UNKNOWN is never deleted."""
    t = subprocess.run([kaggle, "kernels", "status", ref], env=clean_env(), capture_output=True, text=True, timeout=40)
    m = re.search(r"KernelWorkerStatus\.([A-Za-z]+)", t.stdout + t.stderr)
    return m.group(1) if m else "UNKNOWN"


STATUS_PAUSE = 1.5           # seconds between status questions when there are many: asked all at once, Kaggle answers 429 Too Many Requests


def kaggle_runs(limit=10, with_status=True):
    """Your newest Kaggle notebooks made by this tool, with their status (with_status=False: without asking, status ""). Read-only."""
    kaggle = shutil.which("kaggle", path=ENV_PATH)
    if not kaggle:
        raise PlanError("the kaggle command is not installed (uv tool install kaggle)")
    r = subprocess.run([kaggle, "kernels", "list", "-m", "--sort-by", "dateRun", "--page-size", str(limit), "-v"],
                       env=clean_env(), capture_output=True, text=True, timeout=45)
    if r.returncode != 0:
        raise PlanError("Kaggle said: " + (r.stderr or r.stdout).strip()[-200:])
    lines = r.stdout.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("ref,")), None)
    if start is None:
        return []
    rows = [x for x in csv.DictReader(io.StringIO("\n".join(lines[start:]))) if TOOL_SLUG_RE.match(x["ref"].split("/")[-1]) or guess_project(x["ref"].split("/")[-1])]

    if not with_status:
        statuses = [""] * len(rows)
    elif len(rows) <= 12:
        with ThreadPoolExecutor(max_workers=3) as ex:
            statuses = list(ex.map(lambda x: kaggle_status_of(kaggle, x["ref"]), rows))
    else:
        statuses = []
        for x in rows:
            statuses.append(kaggle_status_of(kaggle, x["ref"]))
            time.sleep(STATUS_PAUSE)
    return [{"ref": x["ref"], "slug": x["ref"].split("/")[-1], "status": st, "last_run": x.get("lastRunTime", "")[:16],
             "project": guess_project(x["ref"].split("/")[-1])} for x, st in zip(rows, statuses)]


KERNEL_REF_RE = re.compile(r"^[A-Za-z0-9_-]{2,40}/[a-z0-9][a-z0-9-]{2,120}$")
DOWNLOADS_DIR = ROOT / "my_downloads"


def kernel_ref(value):
    """Accept 'owner/slug'; raise PlanError for anything else (it goes on a command line)."""
    ref = str(value or "").strip()
    if not KERNEL_REF_RE.match(ref):
        raise PlanError("notebook must look like owner/notebook-name")
    return ref


def kernel_status(ref):
    """Run `kaggle kernels status owner/slug` and return one of RUNNING, QUEUED, COMPLETE, ERROR, CANCEL_ACKNOWLEDGED, UNKNOWN."""
    kaggle = shutil.which("kaggle", path=ENV_PATH)
    if not kaggle:
        raise PlanError("the kaggle command is not installed (uv tool install kaggle)")
    r = subprocess.run([kaggle, "kernels", "status", ref], env=clean_env(), capture_output=True, text=True, timeout=40)
    text = (r.stdout + r.stderr).strip()
    m = re.search(r"KernelWorkerStatus\.([A-Za-z_]+)", text) or (re.search(r'status\s+"?([A-Za-z_]+)"?', text) if r.returncode == 0 else None)
    return {"ref": ref, "status": m.group(1).upper() if m else "UNKNOWN", "raw": text[-300:]}


def kernel_output(ref):
    """Run `kaggle kernels output owner/slug -p my_downloads/<slug>` and list whatever files landed there (names are not checked)."""
    kaggle = shutil.which("kaggle", path=ENV_PATH)
    if not kaggle:
        raise PlanError("the kaggle command is not installed (uv tool install kaggle)")
    dest = DOWNLOADS_DIR / ref.split("/")[-1]
    dest.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([kaggle, "kernels", "output", ref, "-p", str(dest), "-o"], env=clean_env(),
                       capture_output=True, text=True, timeout=600)
    files = sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())
    return {"ref": ref, "dir": str(dest.relative_to(ROOT)), "files": files, "ok": r.returncode == 0,
            "message": (r.stderr or r.stdout).strip()[-300:]}


def fetch_step(opt):
    slug = str(opt.get("slug", "")).strip()
    if not KERNEL_SLUG_RE.match(slug):
        raise PlanError("that is not a Kaggle notebook name")
    argv = ["scripts/fetch_kaggle_run.sh", slug]
    if opt.get("wait"):
        argv.append("--wait")
    project = str(opt.get("project") or "").strip()
    if project:
        if not SLUG_RE.match(project) or not (pdir(project)).is_dir():
            raise PlanError("unknown project")
        argv += ["--project", project]
    # exit code 2 = "still running on Kaggle", which is information, not a failure
    return {"label": f"Fetch results of {slug}" + (" (waiting for it to finish)" if opt.get("wait") else ""), "argv": argv, "env": {}, "ok_codes": (0, 2)}
