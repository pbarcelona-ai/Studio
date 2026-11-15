#!/usr/bin/env python3
"""Pick up a Kaggle run whose local waiter is gone (laptop slept, page closed, terminal closed) and put its results in the project.

  python scripts/fetch_kaggle_run.py KERNEL_SLUG [--wait] [--project NAME] [--dest DIR]
    KERNEL_SLUG  the notebook name, e.g. adam-eve-wan-1-40 (also accepted: pbarcelona/adam-eve-wan-1-40; very old runs had one extra word in front)
    --wait       if the run is still going, check every 60 s until it ends, then download
    --project    the book / character set / prompt set name (guessed from the slug if omitted)
    --dest DIR   copy into DIR instead of the project's folder (for testing)

Exit 2: the run is still going (and --wait was not given). The run keeps going on Kaggle whatever happens here; this only downloads, it never
starts or changes a run. The Python version of the old fetch_kaggle_run.sh (which now only calls this). Works on Windows and macOS.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runner_common import ROOT, RunError, log_tail, need_tool, project_folder, run, say  # noqa: E402

STATUS_RE = re.compile(r"KernelWorkerStatus\.([A-Za-z]+)")


def parse(argv: list[str]) -> tuple[str, bool, str, str]:
    slug, wait, project, dest = "", False, "", ""
    it = iter(argv)
    for a in it:
        if a == "--wait":
            wait = True
        elif a in ("--project", "--dest"):
            v = next(it, "")
            if a == "--project":
                project = v
            else:
                dest = v
        elif a.startswith("-"):
            raise RunError(f"unknown option {a}")
        else:
            slug = a
    if not slug:
        raise RunError(__doc__ or "")
    return slug, wait, project, dest


def guess_project(slug: str) -> str:
    """The longest book / character set / prompt set whose name (underscores -> dashes) starts the slug; if none, one extra word in front of it
    is skipped (very old runs had one). A character SERIES (tokens, no promptset.json) is not a run target."""
    base = ROOT / "projects"
    for name in (slug, slug.split("-", 1)[-1]):
        best = ""
        for kind in ("books", "characters", "prompts"):
            for d in sorted((base / kind).glob("*/")) if (base / kind).is_dir() else []:
                if not d.is_dir() or (kind == "characters" and not (d / "promptset.json").is_file()):
                    continue
                if name.startswith(d.name.replace("_", "-") + "-") and len(d.name) > len(best):
                    best = d.name
        if best:
            return best
    return ""


def status(kaggle: str, ref: str) -> str:
    r = run([kaggle, "kernels", "status", ref], capture_output=True)
    m = STATUS_RE.search(r.stdout + r.stderr)
    return m.group(1) if m else ""


def suffix_of(slug: str) -> str:
    """A run of keyframes, of one clip per chapter or of one music cue per scene goes into <folder>_keyframes, _chapters or _scenes."""
    for word in ("keyframes", "chapters", "scenes"):
        if re.search(rf"-{word}-\d", slug):
            return f"_{word}"
    return ""


def copy_results(tmp: Path, pd: Path, suffix: str) -> int:
    n = 0
    for d in ("videos", "audio", "images"):
        src = tmp / d
        if not src.is_dir():
            continue
        (pd / d).mkdir(parents=True, exist_ok=True)
        for sub in src.iterdir():
            if sub.is_dir():
                name = sub.name if (not suffix or sub.name.endswith(suffix)) else sub.name + suffix
                shutil.copytree(sub, pd / d / name, dirs_exist_ok=True)
            else:
                shutil.copy2(sub, pd / d / sub.name)
        n += sum(1 for p in src.rglob("*") if p.is_file())
    return n


def main(argv: list[str]) -> int:
    slug, wait, project, dest = parse(argv)
    kaggle = need_tool("kaggle", "uv tool install kaggle")
    if "/" in slug:
        ref, slug = slug, slug.split("/", 1)[1]
    else:
        r = run([kaggle, "kernels", "list", "-m", "-v", "--page-size", "100"], capture_output=True)
        ref = next((ln.split(",")[0] for ln in r.stdout.splitlines() if ln.split(",")[0].endswith(f"/{slug}")), "")
        if not ref:
            raise RunError(f"no notebook named {slug} on your Kaggle account (try: kaggle kernels list -m)")
    if dest:
        pd = Path(dest)
    else:
        project = project or guess_project(slug)
        if not project:
            raise RunError("could not tell which project this belongs to: add --project NAME")
        try:
            pd = project_folder(project)
        except RunError:
            raise RunError("could not tell which project this belongs to: add --project NAME") from None
    s = status(kaggle, ref)
    say(f"{ref} is: {s or 'unknown'}")
    while s in ("RUNNING", "QUEUED"):
        if not wait:
            say("still going on Kaggle; run this again later, or add --wait to wait for it")
            return 2
        time.sleep(60)
        s = status(kaggle, ref)
        say(f"{time.strftime('%H:%M:%S')} {s}")
    with tempfile.TemporaryDirectory(prefix="studio-fetch-") as tmp_:
        tmp = Path(tmp_)
        run([kaggle, "kernels", "output", ref, "-p", str(tmp), "-o", "-q"])
        logs = pd / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        for f in tmp.glob("*.log"):
            shutil.copy2(f, logs / f.name)
        n = copy_results(tmp, pd, suffix_of(slug))
    say(f"✅ {n} file(s) copied into {pd}   (log saved in {logs})")
    if s != "COMPLETE":
        say(f"note: the run ended as {s or 'unknown'}. End of its log:")
        say(log_tail(logs / f"{slug}.log", 2500))
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    try:
        sys.exit(main(sys.argv[1:]))
    except RunError as e:
        say(str(e))
        sys.exit(1)
