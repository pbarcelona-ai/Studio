"""Step building blocks: script argv, engine arguments, book steps, runner commands."""
import re
from collections.abc import Iterator
from pathlib import Path
from bookkit import SLUG_RE
import layout
import model_advisor
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .common import PlanError, num
from .config import CATALOG, BOOK_EXTS, LEGACY, MODEL_RE, ROOT


def script_argv(argv: list[str]) -> list[str]:
    """Steps name their Python scripts bare ("book_continuity.py") but the job runs from the repository root and the scripts live in scripts/."""
    out = []
    for a in argv:
        if a.endswith(".py") and "/" not in a and not (ROOT / a).exists() and (ROOT / "scripts" / a).exists():
            a = f"scripts/{a}"
        out.append(a)
    return out


def shell_form(step: dict) -> str:
    if "expand" in step:
        return "(chosen when the earlier steps finish: " + step["label"] + ")"
    env = " ".join(f"{k}={v}" for k, v in step["env"].items())
    return (env + " " if env else "") + " ".join(script_argv(step["argv"]))


ENGINES = ["claude", "fcc-claude", "codex", "fcc-codex", "hf", "local"]
# Open models served by Hugging Face Inference Providers (newest first; any other model id can be typed in the model box): studio_app/catalog.json
HF_MODELS = CATALOG["hf_models"]
HF_VISION_MODELS = CATALOG["hf_vision_models"]            # models that also read pictures (for "describe a picture" and "review a result")


def engine_args(opt):
    """--engine and --model for the Claude/Codex steps. A blank model means that tool's own default."""
    engine = opt.get("engine") or "claude"
    if engine not in ENGINES:
        raise PlanError("engine must be one of " + ", ".join(ENGINES))
    model = (opt.get("claude_model") or "").strip()
    if model and not MODEL_RE.match(model):          # any name the tool accepts; only unsafe characters are refused
        raise PlanError("model name may only use letters, digits and . _ : / [ ] -")
    return ["--engine", engine] + (["--model", model] if model else [])


def book_args(opt):
    """Settings for book_write.py (also used for the estimate)."""
    narration = opt.get("narration", "condensed")
    if narration not in ("condensed", "verbatim", "dialogue"):
        raise PlanError("narration must be condensed, verbatim or dialogue")
    args = ["--narration", narration, "--min-shots", str(num(opt, "min_shots", 1, int, 1, 60)),
            "--max-shots", str(num(opt, "max_shots", 12, int, 1, 200))] + engine_args(opt) + [
            "--workers", str(num(opt, "workers", 2, int, 1, 6)), "--minutes", str(num(opt, "movie_minutes", 10, float, 1, 120))]
    if opt.get("words_per_shot"):
        args += ["--words-per-shot", str(num(opt, "words_per_shot", 60, int, 5, 2000))]
    if opt.get("look") in model_advisor.LOOKS:
        args += ["--look", opt["look"]]     # only a realistic film ages its characters
    if opt.get("scenes"):
        args.append("--scenes")             # find the scenes first, so no shot straddles two of them
    if opt.get("clip_seconds"):
        args += ["--clip-seconds", str(num(opt, "clip_seconds", 4, float, 1, 30))]
    if opt.get("force_write"):
        args.append("--force")              # rewrite chapters that already have a script
    if opt.get("chapters"):
        if not re.fullmatch(r"\d{1,4}(-\d{1,4})?", str(opt["chapters"]).strip()):
            raise PlanError("chapters must look like 5 or 5-12")
        args += ["--chapters", str(opt["chapters"]).strip()]
    return args


def project_slug(opt):
    slug = opt.get("project", "")
    if not SLUG_RE.match(slug):
        raise PlanError("pick a book (project)")
    if not (pdir(slug)).is_dir() and not (opt.get("steps", {}).get("ingest") and str(opt.get("pdf", "")).startswith("books/")):
        raise PlanError(f"{slug} has not been started: tick 'Read the PDF and split it into chapters' first")
    return slug


def book_steps(opt, slug):
    st = opt.get("steps", {})
    minutes = str(num(opt, "movie_minutes", 10, float, 1, 120))
    steps = []
    if slug in LEGACY:
        if st.get("extract"):
            extra = ["--enoch-chars", str(num(opt, "enoch_chars", 300, int, 0, 100000))] if slug == "enoch" else []
            steps.append({"label": f"Rebuild {slug} prompt CSVs", "argv": ["python3", "legacy_extract.py", slug] + extra, "env": {}})
            steps.append({"label": "Plan movies", "argv": ["python3", "plan_movies.py", slug, "--minutes", minutes], "env": {}})
        return steps
    if st.get("ingest"):
        raw = str(opt.get("pdf", ""))
        name = Path(raw).name
        path = f"books/{name}" if raw.startswith("books/") else f"{layout.rel(slug)}/source/{name}"
        if not name.lower().endswith(BOOK_EXTS) or not (ROOT / path).exists():
            raise PlanError("choose a book to read: a PDF or a text file (put them in the books folder)")
        steps.append({"label": f"Read {'text' if not name.lower().endswith('.pdf') else 'PDF'} and split chapters ({name})", "env": {},
                      "argv": ["uv", "run", "--with", "pypdf", "python", "book_ingest.py", slug, path]})
    if st.get("continuity"):
        steps.append({"label": "Write the continuity book", "env": {},
                      "argv": ["python3", "book_continuity.py", slug] + engine_args(opt) + ["--force"]})
    if st.get("write"):
        steps.append({"label": "Write shots, narration, sound and music", "env": {},
                      "argv": ["python3", "book_write.py", slug] + book_args(opt)})
    if st.get("build"):
        steps.append({"label": "Build CSVs and plan movies", "argv": ["python3", "book_build.py", slug, "--minutes", minutes], "env": {}})
    return steps


def chunks(lo: int, hi: int, batch: int) -> Iterator[tuple[int, int]]:
    if batch <= 0:
        yield lo, hi
        return
    s = lo
    while s <= hi:
        yield s, min(s + batch - 1, hi)
        s += batch


def make_runner(service, gpu, user, slug):
    """Returns runner(model, first_row, last_row, csv_name) -> (argv, env) for the Kaggle or Colab CLI scripts."""
    def runner(model, s, e, csv_name):
        env = {"PROJECT": slug, "SHOTS_CSV": csv_name}
        if service == "colab":
            return ["scripts/run_colab_model.sh", model, str(s), str(e), gpu], env
        if service == "huggingface":
            return ["scripts/run_hf_space.sh", model, str(s), str(e)], env
        if service == "computer":
            return ["python3", "scripts/run_local_model.py", model, str(s), str(e)], env
        env.update({"KAGGLE_USER": user, "KAGGLE_ACCELERATOR": gpu})
        return ["scripts/run_kaggle_model.sh", model, str(s), str(e)], env
    return runner


PEOPLE_WORDS = re.compile(r"\b(man|woman|men|women|person|people|figure|child|boy|girl|he|she|his|her)\b", re.I)
FILM_KEYFRAMES = "flux2_klein_4b"
FILM_VIDEO = "ltx_video_fast_i2v"
FILM_SPACE = "pika_h3_flex_i2v"
