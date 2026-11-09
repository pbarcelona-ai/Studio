"""build_plan: the options ticked on the page -> validated steps; chapter shots and the cost estimate."""
import os
import subprocess
from bookkit import SLUG_RE, read_json, write_json
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .common import PlanError
from .config import LEGACY, ROOT, clean_env
from .generation import film_options, generation_steps
from .single_prompts import prompt_plan
from .steps import book_args, book_steps, project_slug, script_argv


def build_plan(opt, commit=False):
    if opt.get("mode") == "prompts":
        return prompt_plan(opt, commit)
    if opt.get("film"):
        film_options(opt)
    slug = project_slug(opt)
    st = opt.get("steps", {})
    steps = book_steps(opt, slug)
    if any(st.get(k) for k in ("keyframes", "video", "audio", "merge", "mix")):
        if any(s["label"].startswith(("Build CSVs", "Rebuild", "Plan movies")) for s in steps):
            steps.append({"label": "generate the chosen movies", "expand": True})   # movies.json changes while the plan runs
        else:
            steps += generation_steps(opt, slug)
    if not steps:
        raise PlanError("nothing selected: tick at least one step")
    return steps


def chapter_shots(slug, body=None):
    """The chapter table (number, title, words, saved shot count) and, with body={"shots": {"5": 10, "7": ""}}, save the per-chapter shot counts.
    A blank or 0 count removes the override so that chapter goes back to the automatic count. Stored in overrides.json, which book_write.py reads."""
    if not SLUG_RE.match(slug or "") or slug in LEGACY:
        raise PlanError("pick a book made from a PDF or text")
    d = pdir(slug)
    index = read_json(d / "chapters.json", None)
    if not index:
        raise PlanError("read the book first so it is split into chapters")
    ov = read_json(d / "overrides.json", {})
    if not isinstance(ov, dict):
        ov = {}
    if body is not None:
        known = {str(c["n"]) for c in index["chapters"]}
        for k, v in (body.get("shots") or {}).items():
            if str(k) not in known:
                raise PlanError(f"chapter {k} does not exist")
            v = str(v).strip()
            entry = ov.get(str(k)) if isinstance(ov.get(str(k)), dict) else {}
            if v in ("", "0"):
                entry.pop("shots", None)
            else:
                if not v.isdigit() or not 1 <= int(v) <= 500:
                    raise PlanError(f"chapter {k}: shots must be a whole number from 1 to 500 (or blank for automatic)")
                entry["shots"] = int(v)
            if entry:
                ov[str(k)] = entry
            else:
                ov.pop(str(k), None)
        tmp = d / "overrides.json.tmp"
        write_json(tmp, ov)
        os.replace(tmp, d / "overrides.json")
    return {"chapters": [{"n": c["n"], "title": c.get("title", ""), "words": c.get("words", 0),
                          "shots": (ov.get(str(c["n"])) or {}).get("shots")} for c in index["chapters"]]}


def estimate(opt):
    slug = project_slug(opt)
    if slug in LEGACY:
        raise PlanError("estimates are for books made from a PDF")
    if not (pdir(slug) / "chapters.json").exists():
        raise PlanError("read the PDF first (tick 'Read PDF and split chapters'), then the estimate can run")
    r = subprocess.run(script_argv(["python3", "book_write.py", slug] + book_args(opt) + ["--dry-run"]), cwd=ROOT, env=clean_env(),
                       capture_output=True, text=True, timeout=60)
    return (r.stdout + r.stderr).strip() or "no output"
