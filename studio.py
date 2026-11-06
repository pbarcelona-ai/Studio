#!/usr/bin/env python3
"""Local control page for the Bible film pipeline.

    cd /Users/paulbarcelona/Downloads/Bible && python3 studio.py

Opens http://127.0.0.1:8765/?t=<token>. Pick a book (project), optionally upload a new PDF, tick what to do, and this
server runs the project's own scripts one after another: book_ingest.py, book_bible.py, book_write.py, book_build.py
(prompts written by Claude Code), run_kaggle_model.sh / run_colab_model.sh (video and audio on a free GPU), then
merge_videos.py / mix_film.py (one film per ~10-minute movie).
Safety: listens on 127.0.0.1 only, every API call needs the random token printed at start-up, and only whitelisted
scripts with validated arguments can run (no shell, no free-form commands).
"""
import argparse, csv, io, json, mimetypes, os, re, secrets, shutil, signal, subprocess, threading, time, webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bookkit import EDIT_FIELDS, SLUG_RE, build_movies, llm_json, read_json, set_scene_field, slugify, write_json

ROOT = Path(__file__).resolve().parent          # Bible project root
SCRIPTS = ROOT / "scripts"                      # where the script files live
PROJECTS = ROOT / "projects"
LIBRARY = ROOT / "books"          # every book PDF lives here; the page lists them
TOKEN = secrets.token_urlsafe(16)

VIDEO_MODELS = ["ltx_video", "wan", "cogvideox", "tpu_wan"]     # tpu_wan = Kaggle TPU experiment
AUDIO_KINDS = ["kokoro", "musicgen", "mmaudio"]
IMAGE_MODELS = ["sdxl_turbo", "sdxl", "flux_schnell", "sd35_medium", "moss_image_sft", "moss_image_base",
                "tpu_mage_flow", "tpu_flux_jax"]                          # the tpu_ ones run only on Kaggle's TPU
# Defaults baked into each generator script; shown as placeholders on the page. "locked" = fields the model ignores (greyed out).
MODEL_DEFAULTS = {
    "ltx_video": {"width": 768, "height": 320, "frames": 97, "steps": 40, "guidance": 3.0},
    "wan": {"width": 512, "height": 288, "frames": 33, "steps": 30, "guidance": 5.0},
    "cogvideox": {"width": 720, "height": 480, "frames": 49, "steps": 50, "guidance": 6.0, "locked": ["width", "height", "frames"]},
    "tpu_wan": {"width": 832, "height": 480, "frames": 33, "steps": 30, "guidance": 5.0, "locked": ["width", "height", "frames"]},   # same settings for every row
    "tpu_mage_flow": {"width": 512, "height": 512, "steps": 4, "guidance": 0.0, "locked": ["height", "steps", "guidance", "negative"]},   # width picks 512/768/1024
    "tpu_flux_jax": {"width": 512, "height": 512, "steps": 20, "guidance": 4.0, "locked": ["negative"]},
    "sdxl_turbo": {"width": 512, "height": 512, "steps": 4, "guidance": 0.0},
    "sdxl": {"width": 1024, "height": 1024, "steps": 30, "guidance": 7.0},
    "flux_schnell": {"width": 1024, "height": 1024, "steps": 4, "guidance": 0.0, "locked": ["negative"]},
    "sd35_medium": {"width": 1024, "height": 1024, "steps": 28, "guidance": 4.5},
    "moss_image_sft": {"width": 1024, "height": 1024, "steps": 50, "guidance": 3.0},
    "moss_image_base": {"width": 1024, "height": 1024, "steps": 50, "guidance": 3.0},
}
LEGACY = {"adam_eve", "enoch"}        # imported production bibles; rebuilt with legacy_extract.py
# Suggestions only: the page lets you type ANY model name that `claude --model` accepts (aliases or full IDs).
CLAUDE_MODELS = ["sonnet", "opus", "haiku", "claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/\[\]-]{1,79}$")
GPUS = {  # "paid"/"restricted" are warnings only; Kaggle's own docs say some accelerators are not open to everyone
    "colab": [("T4", "T4 (free tier, often unavailable)"), ("L4", "L4 (paid)"), ("A100", "A100 (paid)"), ("H100", "H100 (paid)")],
    "kaggle": [("NvidiaTeslaT4", "T4 x2 (free)"), ("NvidiaL4", "L4 (may be restricted)"),
               ("NvidiaTeslaA100", "A100 (may be restricted)"), ("NvidiaH100", "H100 (may be restricted)"),
               ("TpuV5E8", "TPU v5e-8 (experimental; only for tpu_wan)")],
}
MAX_UPLOAD = 300 * 1024 * 1024

# Run jobs in a clean environment: the OSS CAD Suite shell setup sets PYTHONHOME and puts its own Python first
# on PATH, which breaks uv-managed Pythons. Drop those so `uv run` and `python3` behave normally.
_PATH = [d for d in os.environ.get("PATH", "").split(":") if d and "oss-cad-suite" not in d]
ENV_PATH = ":".join([f"{Path.home()}/.local/bin", "/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin"] + _PATH)
DROP_ENV = ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "PYTHONSTARTUP", "VIRTUAL_ENV", "__PYVENV_LAUNCHER__")


def clean_env():
    env = {k: v for k, v in os.environ.items() if k not in DROP_ENV and "OSS_CAD" not in k}
    env.update({"PATH": ENV_PATH, "PYTHONUNBUFFERED": "1"})
    return env


# ---------------------------------------------------------------- project discovery
def count_files(folder, pattern):
    return len(list(folder.glob(pattern))) if folder.exists() else 0


def library_files():
    LIBRARY.mkdir(exist_ok=True)
    return sorted(p.name for p in LIBRARY.glob("*.pdf"))


def pdf_choices(slug):
    """PDFs a project can be read from: the matching file in books/ first, then PDFs already copied to its source/."""
    out = [{"value": f"books/{f}", "label": f"books/{f}"} for f in library_files() if slugify(Path(f).stem) == slug]
    out += [{"value": f"books/{f}", "label": f"books/{f} (other)"} for f in library_files() if slugify(Path(f).stem) != slug]
    src = PROJECTS / slug / "source"
    out += [{"value": p.name, "label": f"projects/{slug}/source/{p.name}"} for p in sorted(src.glob("*.pdf"))] if src.exists() else []
    return out


def project_info(slug):
    d = PROJECTS / slug
    chapters = read_json(d / "chapters.json", {})
    if (d / "all_shots.csv").exists() and not (d / "movies.json").exists():
        build_movies(d, 10)
    movies = read_json(d / "movies.json", {})
    return {
        "slug": slug, "legacy": slug in LEGACY, "not_started": not d.exists(), "pdf_choices": pdf_choices(slug),
        "pdfs": sorted(p.name for p in (d / "source").glob("*.pdf")) if (d / "source").exists() else [],
        "chapters": len(chapters.get("chapters", [])), "split_method": chapters.get("method"),
        "bible": (d / "bible.json").exists(), "scripts": count_files(d / "scripts", "chapter-*.json"),
        "built": (d / "all_shots.csv").exists(),
        "movies": {"shots": movies.get("shots", []), "chapters": movies.get("chapters", [])},
        "have": {
            **{f"videos/{m}": count_files(d / "videos" / m, "shot-*.mp4") for m in VIDEO_MODELS},
            **{f"videos/{m}_chapters": count_files(d / "videos" / f"{m}_chapters", "shot-*.mp4") for m in VIDEO_MODELS},
            **{f"audio/{k}": count_files(d / "audio" / k, "*.wav") for k in AUDIO_KINDS},
            **{f"audio/{k}_chapters": count_files(d / "audio" / f"{k}_chapters", "*.wav") for k in AUDIO_KINDS},
            "films": count_files(d / "films", "*.mp4"),
        },
    }


FCC_CATALOG = Path.home() / ".fcc" / "codex-model-catalog.json"
NOT_CHAT = ("guard", "safety", "embed", "parse", "translate", "topic-control", "calibration", "diffusion")


def codex_models():
    """Model names from the Free Claude Code catalog that look like chat/text models (suggestions for codex engines)."""
    try:
        data = json.loads(FCC_CATALOG.read_text())
        items = data["models"] if isinstance(data, dict) else data
        slugs = [m["slug"] for m in items if isinstance(m, dict) and MODEL_RE.match(m.get("slug", ""))]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return [x for x in slugs if not any(k in x.lower() for k in NOT_CHAT)]


def is_promptset(slug):
    return (PROJECTS / slug / "promptset.json").exists()


def promptset_info(slug):
    d = PROJECTS / slug
    return {"slug": slug, "video_rows": len(read_csv_rows(d / "all_shots.csv")), "image_rows": len(read_csv_rows(d / "all_images.csv")),
            "have": {**{f"videos/{m}": count_files(d / "videos" / m, "shot-*.mp4") for m in VIDEO_MODELS},
                     **{f"images/{m}": count_files(d / "images" / m, "image-*.png") for m in IMAGE_MODELS}}}


def read_csv_rows(path):
    try:
        with open(path, newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def status():
    PROJECTS.mkdir(exist_ok=True)
    all_dirs = {p.name for p in PROJECTS.iterdir() if p.is_dir() and SLUG_RE.match(p.name)}
    sets = sorted(x for x in all_dirs if is_promptset(x))
    slugs = {x for x in all_dirs if not is_promptset(x)}
    slugs |= {slugify(Path(f).stem) for f in library_files()}          # books in books/ that have no project yet
    slugs = sorted(x for x in slugs if SLUG_RE.match(x))
    return {
        "tools": {t: bool(shutil.which(t, path=ENV_PATH)) for t in ("claude", "fcc-claude", "codex", "fcc-codex", "colab", "kaggle", "uv")},
        "projects": [project_info(s) for s in slugs], "library": library_files(),
        "promptsets": [promptset_info(x) for x in sets], "image_models": IMAGE_MODELS, "model_defaults": MODEL_DEFAULTS,
        "blockers": blockers(),
        "gpu_blockers": {svc: {g: gpu_blocker(svc, g) for g, _ in gl if gpu_blocker(svc, g)} for svc, gl in GPUS.items()},
        "video_models": VIDEO_MODELS, "audio_kinds": AUDIO_KINDS, "gpus": GPUS, "claude_models": CLAUDE_MODELS,
        "codex_models": codex_models(),
    }


# ---------------------------------------------------------------- plan -> validated argv steps
class PlanError(ValueError):
    pass


def num(opt, key, default, cast=float, lo=None, hi=None):
    try:
        v = cast(opt.get(key) if opt.get(key) not in (None, "") else default)
    except (TypeError, ValueError):
        raise PlanError(f"{key} must be a number")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise PlanError(f"{key} must be between {lo} and {hi}")
    return v


def shell_form(step):
    if "expand" in step:
        return "(chosen when the earlier steps finish: " + step["label"] + ")"
    env = " ".join(f"{k}={v}" for k, v in step["env"].items())
    return (env + " " if env else "") + " ".join(step["argv"])


ENGINES = ["claude", "fcc-claude", "codex", "fcc-codex"]


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
    if narration not in ("condensed", "verbatim"):
        raise PlanError("narration must be condensed or verbatim")
    args = ["--narration", narration, "--min-shots", str(num(opt, "min_shots", 1, int, 1, 60)),
            "--max-shots", str(num(opt, "max_shots", 12, int, 1, 200))] + engine_args(opt) + [
            "--workers", str(num(opt, "workers", 2, int, 1, 6)), "--minutes", str(num(opt, "movie_minutes", 10, float, 1, 120))]
    if opt.get("words_per_shot"):
        args += ["--words-per-shot", str(num(opt, "words_per_shot", 60, int, 5, 2000))]
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
    if not (PROJECTS / slug).is_dir() and not (opt.get("steps", {}).get("ingest") and str(opt.get("pdf", "")).startswith("books/")):
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
        path = f"books/{name}" if raw.startswith("books/") else f"projects/{slug}/source/{name}"
        if not name.lower().endswith(".pdf") or not (ROOT / path).exists():
            raise PlanError("choose a PDF to read (put PDFs in the books folder)")
        steps.append({"label": f"Read PDF and split chapters ({name})", "env": {},
                      "argv": ["uv", "run", "--with", "pypdf", "python", "book_ingest.py", slug, path]})
    if st.get("bible"):
        steps.append({"label": "Write the continuity bible", "env": {},
                      "argv": ["python3", "book_bible.py", slug] + engine_args(opt) + ["--force"]})
    if st.get("write"):
        steps.append({"label": "Write shots, narration, sound and music", "env": {},
                      "argv": ["python3", "book_write.py", slug] + book_args(opt)})
    if st.get("build"):
        steps.append({"label": "Build CSVs and plan movies", "argv": ["python3", "book_build.py", slug, "--minutes", minutes], "env": {}})
    return steps


def chunks(lo, hi, batch):
    if batch <= 0:
        yield lo, hi
        return
    s = lo
    while s <= hi:
        yield s, min(s + batch - 1, hi)
        s += batch


# Set to True once a TPU notebook started from the command line really gets a TPU. On Oct 27, 2026 two such runs were
# accepted by Kaggle (enable_tpu=true, machine_shape=TpuV5E8) but the sessions had no TPU: no /dev/accel* devices,
# CPU-only JAX, and 0.00 h of the 20 h weekly TPU quota used. See README_TPU_EXPERIMENT.md.
TPU_CLI_WORKS = True
TPU_CLI_NOTE = ("Kaggle did not attach a TPU to notebooks started from the command line (tested twice, 0 h of TPU quota used; "
                "TPUs may also just have been busy). Try the notebook in the Kaggle web page, or retest later (README_TPU_EXPERIMENT.md)")


def gpu_blocker(service, gpu):
    return TPU_CLI_NOTE if gpu.startswith("Tpu") and not TPU_CLI_WORKS else None


TPU_ONLY = {"tpu_wan", "tpu_mage_flow", "tpu_flux_jax"}      # JAX models that run only on Kaggle's TPU v5e-8
BIG_RAM_MODELS = {"flux_schnell", "moss_image_sft", "moss_image_base"}      # 12-25 GB of weights: more system RAM than Colab's free tier


def model_blocker(name, service, gpu):
    """Why this video/image/audio model cannot run with this service and GPU, or None if it can (it may still be untested)."""
    on_tpu = gpu.startswith("Tpu")
    if name in TPU_ONLY:
        if service != "kaggle":
            return "TPU runs are only offered through Kaggle"
        if on_tpu:
            return gpu_blocker(service, gpu)
        return "needs the TPU v5e-8 accelerator"
    if on_tpu:
        return "needs a CUDA GPU, not a TPU"
    if name == "sd35_medium":
        return "gated model: needs a Hugging Face token, which the command-line runs cannot pass (use the notebook, see README_TEXT_TO_MEDIA.md)"
    if name in BIG_RAM_MODELS and service == "colab" and gpu == "T4":
        return "needs more system RAM than Colab's free tier has (use Kaggle)"
    return None


def blockers():
    """{model: {service: {gpu: reason}}} for every combination that cannot work (sent to the page so it can grey them out)."""
    out = {}
    for name in VIDEO_MODELS + IMAGE_MODELS + AUDIO_KINDS:
        for service, gpus in GPUS.items():
            for g, _ in gpus:
                why = model_blocker(name, service, g)
                if why:
                    out.setdefault(name, {}).setdefault(service, {})[g] = why
    return out


def check_models(service, gpu, names):
    for n in names:
        why = model_blocker(n, service, gpu)
        if why:
            raise PlanError(f"{n} cannot run on {service} {gpu}: {why}")


def make_runner(service, gpu, user, slug):
    """Returns runner(model, first_row, last_row, csv_name) -> (argv, env) for the Kaggle or Colab CLI scripts."""
    def runner(model, s, e, csv_name):
        env = {"PROJECT": slug, "SHOTS_CSV": csv_name}
        if service == "colab":
            return ["./run_colab_model.sh", model, str(s), str(e), gpu], env
        env.update({"KAGGLE_USER": user, "KAGGLE_ACCELERATOR": gpu})
        return ["./run_kaggle_model.sh", model, str(s), str(e)], env
    return runner


def generation_steps(opt, slug):
    """Video/audio/merge/mix steps for the chosen movies. Needs movies.json, so it may run after the book steps."""
    service = opt.get("service")
    if service not in GPUS:
        raise PlanError("service must be kaggle or colab")
    gpu = opt.get("gpu")
    if gpu not in [g for g, _ in GPUS[service]]:
        raise PlanError(f"gpu {gpu!r} is not an option for {service}")
    if gpu_blocker(service, gpu):
        raise PlanError(gpu_blocker(service, gpu))
    st = opt.get("steps", {})
    chapters_mode = opt.get("granularity") == "chapters"
    vmodels = [m for m in opt.get("video_models", []) if m in VIDEO_MODELS]
    akinds = [k for k in opt.get("audio", []) if k in AUDIO_KINDS]
    user = (opt.get("kaggle_user") or "").strip()
    if service == "kaggle" and (st.get("video") or st.get("audio")) and not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", user):
        raise PlanError("enter your Kaggle username (letters, digits, - and _)")
    check_models(service, gpu, (vmodels if st.get("video") else []) + (akinds if st.get("audio") else []))
    batch = num(opt, "batch", 0, int, 0, 100000)
    sync = opt.get("sync", "stretch")
    if sync not in ("stretch", "speed", "trim"):
        raise PlanError("bad sync mode")
    vols = {k: num(opt.get("vol", {}), k, d, float, 0, 5) for k, d in (("narration", 1.0), ("sfx", 0.5), ("music", 0.25))}

    plan = read_json(PROJECTS / slug / "movies.json", {})
    movies = plan.get("chapters" if chapters_mode else "shots", [])
    if not movies:
        raise PlanError("no movies planned yet for this book and mode: run the 'Build CSVs and plan movies' step first")
    sel = opt.get("movies", {})
    if sel.get("mode") == "all":
        chosen = movies
    elif sel.get("mode") == "first":
        chosen = movies[: num(sel, "n", 1, int, 1, 1000)]
    else:
        ids = {int(i) for i in sel.get("ids", [])}
        chosen = [m for m in movies if m["id"] in ids]
    if not chosen:
        raise PlanError("tick at least one movie")
    lo_o = num(opt, "range_start", 0, int, 0) or None
    hi_o = num(opt, "range_end", 0, int, 0) or None

    suf = "_chapters" if chapters_mode else ""
    vcsv = "all_chapters.csv" if chapters_mode else "all_shots.csv"
    acsv = "audio_chapters.csv" if chapters_mode else "audio_shots.csv"
    steps = []

    runner = make_runner(service, gpu, user, slug)

    done = set()
    for mv in chosen:
        lo, hi = mv["rows"]
        lo, hi = max(lo, lo_o or lo), min(hi, hi_o or hi)
        for s, e in (chunks(lo, hi, batch) if lo <= hi else []):
            if st.get("video"):
                for m in vmodels:
                    if (m, s, e) not in done:
                        done.add((m, s, e)); argv, env = runner(m, s, e, vcsv)
                        steps.append({"label": f"Movie {mv['id']} video {m}: rows {s}-{e}", "argv": argv, "env": env})
            if st.get("audio"):
                for k in akinds:
                    if (k, s, e) not in done:
                        done.add((k, s, e)); argv, env = runner(f"audio_{k}", s, e, acsv)
                        steps.append({"label": f"Movie {mv['id']} audio {k}: rows {s}-{e}", "argv": argv, "env": env})
    uv = ["uv", "run", "--with", "imageio-ffmpeg", "python"]
    for mv in chosen:
        lo, hi = mv["rows"]
        name = f"{slug}-movie-{mv['id']:02d}{suf}"
        for m in vmodels:
            if st.get("merge"):
                steps.append({"label": f"Movie {mv['id']} silent film ({m})", "env": {},
                              "argv": uv + ["merge_videos.py", f"videos/{m}{suf}", f"{name}_{m}_silent.mp4", "--project", slug,
                                            "--start", str(lo), "--end", str(hi)]})
            if st.get("mix"):
                steps.append({"label": f"Movie {mv['id']} final film with audio ({m})", "env": {},
                              "argv": uv + ["mix_film.py", "--project", slug, "--model", m, "--start", str(lo), "--end", str(hi),
                                            "--sync", sync, "--out", f"{name}_{m}.mp4",
                                            "--vol-narration", str(vols["narration"]), "--vol-sfx", str(vols["sfx"]),
                                            "--vol-music", str(vols["music"])] + (["--chapters"] if chapters_mode else [])})
    return steps


def build_plan(opt, commit=False):
    if opt.get("mode") == "prompts":
        return prompt_plan(opt, commit)
    slug = project_slug(opt)
    st = opt.get("steps", {})
    steps = book_steps(opt, slug)
    if any(st.get(k) for k in ("video", "audio", "merge", "mix")):
        if any(s["label"].startswith(("Build CSVs", "Rebuild", "Plan movies")) for s in steps):
            steps.append({"label": "generate the chosen movies", "expand": True})   # movies.json changes while the plan runs
        else:
            steps += generation_steps(opt, slug)
    if not steps:
        raise PlanError("nothing selected: tick at least one step")
    return steps


def estimate(opt):
    slug = project_slug(opt)
    if slug in LEGACY:
        raise PlanError("estimates are for books made from a PDF")
    if not (PROJECTS / slug / "chapters.json").exists():
        raise PlanError("read the PDF first (tick 'Read PDF and split chapters'), then the estimate can run")
    r = subprocess.run(["python3", "book_write.py", slug] + book_args(opt) + ["--dry-run"], cwd=SCRIPTS, env=clean_env(),
                       capture_output=True, text=True, timeout=60)
    return (r.stdout + r.stderr).strip() or "no output"


# ---------------------------------------------------------------- single prompts (text to video / text to image)
VIDEO_COLS = ["chapter", "shot", "prompt", "negative", "width", "height", "frames", "steps", "guidance", "seed"]
IMAGE_COLS = ["chapter", "shot", "prompt", "negative", "width", "height", "steps", "guidance", "seed"]


def snap(value, multiple, lo, hi):
    """Round a size/frame count to what the model accepts and keep it in range."""
    v = int(round(value / multiple)) * multiple
    return max(lo, min(hi, v))


def prompt_set_slug(opt, create_ok):
    slug = (opt.get("set") or "").strip().lower()
    if not SLUG_RE.match(slug):
        raise PlanError("name the prompt set: 2-40 lowercase letters, digits or underscores")
    d = PROJECTS / slug
    if d.exists() and not is_promptset(slug):
        raise PlanError(f"{slug} is a book, not a prompt set; pick another name")
    return slug


def prompt_rows(opt, slug, kind, model, first_row):
    prompts = [ln.strip() for ln in str(opt.get("prompts", "")).splitlines() if ln.strip()]
    if not prompts:
        raise PlanError("type at least one prompt (one per line)")
    if len(prompts) > 100 or any(len(p) > 2000 for p in prompts):
        raise PlanError("up to 100 prompts at a time, 2000 characters each")
    o = opt.get("opts", {}) or {}
    variations = num(o, "variations", 1, int, 1, 8)
    w = num(o, "width", 0, int, 0, 4096) or None
    h = num(o, "height", 0, int, 0, 4096) or None
    frames = num(o, "frames", 0, int, 0, 400) or None
    steps = num(o, "steps", 0, int, 0, 150) or None
    guidance = o.get("guidance")
    guidance = None if guidance in (None, "") else num(o, "guidance", 0, float, 0, 30)
    seed = o.get("seed")
    seed = None if seed in (None, "") else num(o, "seed", 0, int, 0, 2**31 - 1)
    negative = str(o.get("negative") or "").strip()[:500]
    if kind == "video":
        if model == "ltx_video":
            w = snap(w, 32, 256, 1280) if w else None; h = snap(h, 32, 256, 1280) if h else None
            frames = snap(frames - 1, 8, 8, 160) + 1 if frames else None          # 8*k+1
        elif model == "wan":
            w = snap(w, 16, 256, 1280) if w else None; h = snap(h, 16, 256, 1280) if h else None
            frames = snap(frames - 1, 4, 4, 120) + 1 if frames else None          # 4*k+1
        else:                                                                       # cogvideox: fixed size and length
            w = h = frames = None
    elif model == "tpu_mage_flow":                    # the author's runner makes square 512, 768 or 1024 images in 4 steps
        size = max(w or 0, h or 0)
        w = h = min((512, 768, 1024), key=lambda r: abs(r - size)) if size else None
        steps = guidance = None
        negative = ""
    elif model == "tpu_flux_jax":
        w = snap(w, 16, 256, 1024) if w else None; h = snap(h, 16, 256, 1024) if h else None
        negative = ""
    else:
        w = snap(w, 16, 256, 1536) if w else None; h = snap(h, 16, 256, 1536) if h else None
        if model == "flux_schnell":
            negative = ""
    rows, n = [], first_row
    for p in prompts:
        for v in range(variations):
            row = {"chapter": slug, "shot": n, "prompt": p, "negative": negative, "width": w or "", "height": h or "",
                   "steps": steps or "", "guidance": "" if guidance is None else guidance,
                   "seed": "" if seed is None else seed + v}
            if kind == "video":
                row["frames"] = frames or ""
            rows.append(row)
            n += 1
    return rows


def append_rows(path, cols, new_rows):
    old = read_csv_rows(path)
    fields = list(cols) + [c for r in old for c in r if c not in cols]
    fields = list(dict.fromkeys(fields))
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(old + new_rows)


def wan_t4_check(gpu, w, h, frames):
    """Wan on a T4 runs plain bf16 attention: one matrix is 48 x tokens^2 bytes. Refuse sizes that cannot fit (the 832x480x81 default crashed)."""
    if "T4" not in gpu:
        return
    d = MODEL_DEFAULTS["wan"]
    w, h, frames = w or d["width"], h or d["height"], frames or d["frames"]
    tokens = ((frames - 1) // 4 + 1) * (h // 16) * (w // 16)
    need = 48 * tokens * tokens / 2**30
    if tokens > 7500:
        raise PlanError(f"wan at {w}x{h} with {frames} frames needs about {need:.1f} GiB for one attention matrix on a T4 (it has about 14 GiB and the model uses 4.7); "
                        f"keep ((frames-1)//4+1) x (height/16) x (width/16) under about 7,000 (now {tokens:,}), for example 512x288 with 33 frames, or use an L4/A100")


def prompt_plan(opt, commit):
    slug = prompt_set_slug(opt, True)
    kind = opt.get("kind")
    if kind not in ("video", "image"):
        raise PlanError("choose video or image")
    model = opt.get("model")
    if model not in (VIDEO_MODELS if kind == "video" else IMAGE_MODELS):
        raise PlanError("unknown model for that kind")
    service = opt.get("service")
    if service not in GPUS:
        raise PlanError("service must be kaggle or colab")
    gpu = opt.get("gpu")
    if gpu not in [g for g, _ in GPUS[service]]:
        raise PlanError(f"gpu {gpu!r} is not an option for {service}")
    if gpu_blocker(service, gpu):
        raise PlanError(gpu_blocker(service, gpu))
    user = (opt.get("kaggle_user") or "").strip()
    if service == "kaggle" and not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", user):
        raise PlanError("enter your Kaggle username (letters, digits, - and _)")
    check_models(service, gpu, [model])
    batch = num(opt, "batch", 0, int, 0, 100000)
    d = PROJECTS / slug
    csv_name, cols = ("all_shots.csv", VIDEO_COLS) if kind == "video" else ("all_images.csv", IMAGE_COLS)
    first = len(read_csv_rows(d / csv_name)) + 1
    rows = prompt_rows(opt, slug, kind, model, first)
    if model == "wan":
        for r in rows:
            wan_t4_check(gpu, int(r["width"] or 0), int(r["height"] or 0), int(r.get("frames") or 0))
    last = first + len(rows) - 1
    if commit:
        d.mkdir(parents=True, exist_ok=True)
        (d / "promptset.json").write_text(json.dumps({"type": "prompts"}))
        append_rows(d / csv_name, cols, rows)
    runner = make_runner(service, gpu, user, slug)
    runner_model = model if kind == "video" else f"image_{model}"
    steps = []
    for s_, e_ in chunks(first, last, batch):
        argv, env = runner(runner_model, s_, e_, csv_name)
        steps.append({"label": f"{kind} {model}: rows {s_}-{e_}", "argv": argv, "env": env})
    return steps


def expand_idea(opt):
    kind = opt.get("kind")
    if kind not in ("video", "image"):
        raise PlanError("choose video or image")
    idea = str(opt.get("idea") or "").strip()
    if not idea or len(idea) > 1000:
        raise PlanError("write a short idea (up to 1000 characters)")
    count = num(opt, "count", 3, int, 1, 4)
    args = engine_args(opt)
    engine = args[1]
    model = args[3] if len(args) > 3 else None
    what = ("a text-to-video model. Each prompt is one 4-6 second clip: 40-70 words naming the subject, what happens "
            "over the clip, the camera movement, the setting, the light and the style.") if kind == "video" else (
            "a text-to-image model. Each prompt is one picture: 30-60 words naming the subject, composition, setting, "
            "light, style and lens or medium.")
    prompt = (f'Idea: "{idea}"\n\nWrite {count} different, vivid prompts for {what} No on-screen text, no logos, nothing '
              f'that depends on previous prompts. Reply with one JSON object: {{"prompts": ["...", ...]}} with exactly {count} strings.')

    def check(d):
        ps = d.get("prompts")
        if not isinstance(ps, list) or len(ps) != count or not all(isinstance(x, str) and len(x) > 20 for x in ps):
            raise ValueError(f"'prompts' must be a list of exactly {count} strings")

    data = llm_json(prompt, f"You write prompts for {kind} generation models. You reply with a single JSON object and nothing else.",
                    model=model, engine=engine, validate=check)
    return [x.strip() for x in data["prompts"]]


def gallery(slug, limit=60):
    """Newest results of a project: clips, images and films, each with the prompt that made it."""
    d = PROJECTS / slug
    if not d.is_dir():
        return []
    prompts = {name: read_csv_rows(d / name) for name in ("all_shots.csv", "all_chapters.csv", "all_images.csv")}
    items = []
    for sub, pattern, kind in (("videos", "*/shot-*.mp4", "video"), ("images", "*/image-*.png", "image"), ("films", "*.mp4", "film")):
        for f in (d / sub).glob(pattern) if (d / sub).exists() else []:
            model = f.parent.name if kind != "film" else ""
            n = int(re.search(r"(\d+)", f.stem).group(1)) if kind != "film" else 0
            csv_name = "all_images.csv" if kind == "image" else "all_chapters.csv" if model.endswith("_chapters") else "all_shots.csv"
            rows = prompts.get(csv_name, [])
            text = rows[n - 1]["prompt"] if kind != "film" and 0 < n <= len(rows) else ""
            items.append({"kind": kind, "model": model, "row": n, "name": f.name, "prompt": text[:600],
                          "path": f.relative_to(d).as_posix(), "mtime": f.stat().st_mtime})
    items.sort(key=lambda x: -x["mtime"])
    return items[:limit]


# ---------------------------------------------------------------- Kaggle runs: list them and fetch their results
KERNEL_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,120}$")


def guess_project(slug):
    """Longest projects/<name> whose name (underscores -> dashes) starts the slug after 'bible-' (same rule as fetch_kaggle_run.sh)."""
    best = ""
    for d in PROJECTS.iterdir() if PROJECTS.exists() else []:
        if d.is_dir() and slug.startswith(f"bible-{d.name.replace('_', '-')}-") and len(d.name) > len(best):
            best = d.name
    return best


def kaggle_runs(limit=10):
    """Your newest Kaggle notebooks made by this tool, with their status. Read-only."""
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
    rows = [x for x in csv.DictReader(io.StringIO("\n".join(lines[start:]))) if x["ref"].split("/")[-1].startswith("bible-")]

    def status_of(ref):
        t = subprocess.run([kaggle, "kernels", "status", ref], env=clean_env(), capture_output=True, text=True, timeout=40)
        m = re.search(r"KernelWorkerStatus\.([A-Za-z]+)", t.stdout + t.stderr)
        return m.group(1) if m else "UNKNOWN"

    with ThreadPoolExecutor(max_workers=5) as ex:
        statuses = list(ex.map(status_of, [x["ref"] for x in rows]))
    return [{"ref": x["ref"], "slug": x["ref"].split("/")[-1], "status": st, "last_run": x.get("lastRunTime", "")[:16],
             "project": guess_project(x["ref"].split("/")[-1])} for x, st in zip(rows, statuses)]


def fetch_step(opt):
    slug = str(opt.get("slug", "")).strip()
    if not KERNEL_SLUG_RE.match(slug):
        raise PlanError("that is not a Kaggle notebook name")
    argv = ["./fetch_kaggle_run.sh", slug]
    if opt.get("wait"):
        argv.append("--wait")
    project = str(opt.get("project") or "").strip()
    if project:
        if not SLUG_RE.match(project) or not (PROJECTS / project).is_dir():
            raise PlanError("unknown project")
        argv += ["--project", project]
    # exit code 2 = "still running on Kaggle", which is information, not a failure
    return {"label": f"Fetch results of {slug}" + (" (waiting for it to finish)" if opt.get("wait") else ""), "argv": argv, "env": {}, "ok_codes": (0, 2)}


# ---------------------------------------------------------------- make a film from the downloaded files you tick
AUDIO_KINDS_FILES = {"narration": "narration-*.wav", "sfx": "sfx-*.wav", "music": "music-*.wav"}
FILM_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,60}$")


def media_inventory(slug):
    """What has been downloaded for a project: clip folders and audio folders with the rows each holds, plus a line of text per row."""
    d = PROJECTS / slug
    if not SLUG_RE.match(slug) or not d.is_dir():
        raise PlanError("pick a book or prompt set first")
    inv = {"videos": {}, "narration": {}, "sfx": {}, "music": {}, "texts": {}}

    def rows_of(folder, pattern):
        out = []
        for f in folder.glob(pattern):
            m = re.search(r"-(\d+)\.", f.name)
            if m:
                out.append(int(m.group(1)))
        return sorted(out)

    for sub in sorted((d / "videos").glob("*")) if (d / "videos").is_dir() else []:
        rows = rows_of(sub, "shot-*.mp4") if sub.is_dir() else []
        if rows:
            inv["videos"][f"videos/{sub.name}"] = rows
    for sub in sorted((d / "audio").glob("*")) if (d / "audio").is_dir() else []:
        if sub.is_dir():
            for kind, pattern in AUDIO_KINDS_FILES.items():
                rows = rows_of(sub, pattern)
                if rows:
                    inv[kind][f"audio/{sub.name}"] = rows
    for src, rows in inv["videos"].items():
        csv_name = "all_chapters.csv" if src.endswith("_chapters") else "all_shots.csv"
        table = read_csv_rows(d / csv_name)
        inv["texts"][src] = {str(n): (f"{table[n - 1]['chapter']}: {table[n - 1]['prompt']}"[:110] if 0 < n <= len(table) else "") for n in rows}
    return inv


def film_step(opt):
    slug = str(opt.get("project", ""))
    inv = media_inventory(slug)
    name = str(opt.get("name") or "my_film").strip()
    if not FILM_NAME_RE.match(name):
        raise PlanError("film name: letters, digits, - and _ only (up to 60)")
    vsrc = opt.get("video_source")
    if vsrc not in inv["videos"]:
        raise PlanError("choose where the video clips come from")
    srcs = {}
    for kind in AUDIO_KINDS_FILES:
        v = (opt.get("sources") or {}).get(kind) or ""
        if v and v not in inv[kind]:
            raise PlanError(f"unknown {kind} folder {v!r}")
        srcs[kind] = v
    have = {"video": set(inv["videos"][vsrc]), **{k: set(inv[k][srcs[k]]) if srcs[k] else set() for k in AUDIO_KINDS_FILES}}
    clips = []
    for item in opt.get("rows") or []:
        n = int(item.get("n"))
        if n not in have["video"]:
            raise PlanError(f"row {n} has no clip in {vsrc}")
        c = {"row": n, "video": f"{vsrc}/shot-{n:04d}.mp4"}
        for kind in AUDIO_KINDS_FILES:
            use = bool(item.get(kind)) and n in have[kind]
            c[kind] = f"{srcs[kind]}/{kind}-{n:04d}.wav" if use else None
        clips.append(c)
    if not clips:
        raise PlanError("tick at least one clip")
    sync = opt.get("sync", "stretch")
    if sync not in ("stretch", "speed", "trim"):
        raise PlanError("bad sync mode")
    vols = {k: num(opt.get("vol", {}), k, d, float, 0, 5) for k, d in (("narration", 1.0), ("sfx", 0.5), ("music", 0.25))}
    (PROJECTS / slug / "films").mkdir(exist_ok=True)
    sel_path = (PROJECTS / slug / "films" / "_selection.json").resolve()
    (sel_path).write_text(json.dumps({"clips": clips}, indent=1))
    mix_film = (SCRIPTS / "mix_film.py").resolve()
    return slug, clips, {"label": f"Make film {name}.mp4 from {len(clips)} clip(s)", "env": {}, "cwd": str(PROJECTS / slug),
        "argv": ["uv", "run", "--with", "imageio-ffmpeg", "python", str(mix_film), "--project", slug, "--selection", str(sel_path),
                 "--sync", sync, "--out", f"{name}.mp4", "--vol-narration", str(vols["narration"]), "--vol-sfx", str(vols["sfx"]),
                 "--vol-music", str(vols["music"])]}


# ---------------------------------------------------------------- clean-up: find old generated files, move them to the Trash
CLEAN_CATEGORIES = [   # id, title, ticked by default, what to know
    ("pycache", "Python cache folders", True, "Made automatically by Python; they come back by themselves."),
    ("notebooks", "Generated notebooks and scripts (Bible_*.ipynb, colab_generate_*.py)", True,
     "Written by the scripts in tools/. They are re-created automatically when a run needs one, or with the Re-create button; "
     "delete them only if you do not need to upload a notebook by hand."),
    ("temp", "Temporary and leftover files", True, "Partial uploads, old progress markers, the film selection file and stray logs inside video folders."),
    ("empty", "Empty output folders", True, "Folders in videos/, audio/ and images/ with nothing in them."),
    ("logs", "Kaggle run logs", False, "Kept for troubleshooting failed runs; safe to delete once the run no longer matters."),
    ("stale", "Outputs numbered past the end of the prompt file", False, "Clips, audio or images for rows that no longer exist (left over after the prompts were shortened or re-split)."),
    ("other", "Folders made by other tools", False, "graphify-out is made by your graphify tool, not by this project."),
]
OUTPUT_PATTERN = re.compile(r"^(shot|image|narration|sfx|music)-(\d{4})(_alt\d)?\.(mp4|png|wav)$")


def _size(path):
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def cleanup_scan():
    found = {c[0]: [] for c in CLEAN_CATEGORIES}

    def add(cat, path):
        if path.exists() and not any(i["path"] == str(path.relative_to(ROOT)) for i in found[cat]):
            found[cat].append({"path": str(path.relative_to(ROOT)), "bytes": _size(path), "dir": path.is_dir()})

    for dirpath, dirnames, _ in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "source")]       # never walk into a book's source folder
        if "__pycache__" in dirnames:
            add("pycache", Path(dirpath) / "__pycache__")
            dirnames.remove("__pycache__")
    for pat in ("Bible_*.ipynb", "colab_generate_*.py"):
        for f in ROOT.glob(pat):
            add("notebooks", f)
    for pat in (".batch_progress*", ".adam_progress", ".enoch_progress", ".generation_progress"):
        for f in ROOT.glob(pat):
            add("temp", f)
    for f in (ROOT / "books").glob("*.part") if (ROOT / "books").exists() else []:
        add("temp", f)
    for proj in PROJECTS.iterdir() if PROJECTS.exists() else []:
        if not proj.is_dir():
            continue
        for f in list((proj / "source").glob("*.part")) + [proj / "films" / "_selection.json"] + list((proj / "videos").glob("*.log")):
            add("temp", f)
        for f in (proj / "logs").glob("*.log") if (proj / "logs").exists() else []:
            add("logs", f)
        rows = {name: len(read_csv_rows(proj / name)) for name in ("all_shots.csv", "all_chapters.csv", "audio_shots.csv", "audio_chapters.csv", "all_images.csv")}
        for top in ("videos", "audio", "images"):
            for sub in sorted((proj / top).glob("*")) if (proj / top).is_dir() else []:
                if not sub.is_dir():
                    continue
                files = [f for f in sub.iterdir() if f.is_file()]
                if not files:
                    add("empty", sub)
                    continue
                chapters = sub.name.endswith("_chapters")
                csv_name = "all_images.csv" if top == "images" else (("audio_chapters.csv" if chapters else "audio_shots.csv") if top == "audio" else ("all_chapters.csv" if chapters else "all_shots.csv"))
                limit = rows.get(csv_name, 0)
                if not limit:
                    continue                                    # no prompt file to compare with: leave everything alone
                for f in files:
                    m = OUTPUT_PATTERN.match(f.name)
                    if m and int(m.group(2)) > limit:
                        add("stale", f)
    add("other", ROOT / "graphify-out")
    return [{"id": cid, "title": title, "default": default, "note": note, "items": sorted(found[cid], key=lambda i: i["path"]),
             "bytes": sum(i["bytes"] for i in found[cid])} for cid, title, default, note in CLEAN_CATEGORIES]


def move_to_trash(paths, label):
    """Move files/folders (given relative to the project folder) into ~/.Trash/<label>-<time>/, keeping their folder structure."""
    dest = Path.home() / ".Trash" / f"{label}-{time.strftime('%Y%m%d-%H%M%S')}"
    moved, total = 0, 0
    for rel in paths:
        src = (ROOT / rel).resolve()
        if ROOT.resolve() not in src.parents or not src.exists():          # only things inside this project, and only if still there
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        total += _size(src)
        shutil.move(str(src), str(target))
        moved += 1
    return {"moved": moved, "bytes": total, "trash": str(dest) if moved else ""}


def cleanup_delete(categories):
    wanted = {c for c in categories if c in {x[0] for x in CLEAN_CATEGORIES}}
    if not wanted:
        raise PlanError("tick at least one group")
    paths, seen = [], []
    for cat in cleanup_scan():                                              # re-scan: only what the server finds itself is ever removed
        if cat["id"] in wanted:
            for item in cat["items"]:
                if not any(item["path"] == p or item["path"].startswith(p + "/") for p in seen):
                    paths.append(item["path"]); seen.append(item["path"])
    return move_to_trash(paths, "pistachio-cleanup")


# ---------------------------------------------------------------- downloaded files: list them, move chosen ones to the Trash (to regenerate)
def files_inventory(slug):
    """Every downloaded clip, audio file, image and film of a project, grouped by folder, with the row it belongs to."""
    d = PROJECTS / slug
    if not SLUG_RE.match(slug) or not d.is_dir():
        raise PlanError("pick a book or prompt set first")
    tables = {n: read_csv_rows(d / n) for n in ("all_shots.csv", "all_chapters.csv", "audio_shots.csv", "audio_chapters.csv", "all_images.csv")}
    folders = {}
    for top in ("videos", "audio", "images"):
        for sub in sorted((d / top).glob("*")) if (d / top).is_dir() else []:
            files = []
            for f in sorted(sub.iterdir()) if sub.is_dir() else []:
                m = OUTPUT_PATTERN.match(f.name)
                if not m:
                    continue
                n = int(m.group(2))
                chapters = sub.name.endswith("_chapters")
                csv_name = "all_images.csv" if top == "images" else (("audio_chapters.csv" if chapters else "audio_shots.csv") if top == "audio" else ("all_chapters.csv" if chapters else "all_shots.csv"))
                rows = tables.get(csv_name, [])
                row = rows[n - 1] if 0 < n <= len(rows) else None
                text = ""
                if row:
                    text = (f"{row['chapter']}: " + (row.get("prompt") or row.get("narration") or row.get("sfx") or ""))[:100]
                files.append({"name": f.name, "row": n, "bytes": f.stat().st_size, "text": text})
            if files:
                folders[f"{top}/{sub.name}"] = files
    films = [{"name": f.name, "row": 0, "bytes": f.stat().st_size, "text": ""} for f in sorted((d / "films").glob("*.mp4"))] if (d / "films").is_dir() else []
    if films:
        folders["films"] = films
    return folders


def trash_files(slug, folder, names):
    inv = files_inventory(slug)
    if folder not in inv:
        raise PlanError("unknown folder")
    known = {f["name"] for f in inv[folder]}
    chosen = [n for n in names if n in known]
    if not chosen:
        raise PlanError("tick at least one file")
    res = move_to_trash([f"projects/{slug}/{folder}/{n}" for n in chosen], "pistachio-deleted")
    # a folder emptied by this is tidied away too
    d = PROJECTS / slug / folder
    try:
        if d.is_dir() and not any(d.iterdir()) and folder != "films":
            d.rmdir()
    except OSError:
        pass
    return res


# ---------------------------------------------------------------- scene prompts: look at them, add your own details, get suggestions, save
FIELD_LIMITS = {"prompt": 1500, "narration": 600, "sfx": 600, "music": 600}
FIELD_TITLES = {"prompt": "video prompt", "narration": "narration", "sfx": "sound-effects prompt", "music": "music prompt"}


def _scene_tables(slug):
    d = PROJECTS / slug
    if not SLUG_RE.match(slug) or not d.is_dir():
        raise PlanError("pick a book or prompt set first")
    shots = read_csv_rows(d / "all_shots.csv")
    if not shots:
        raise PlanError("this project has no video prompts yet (build the prompt files first)")
    return d, shots, read_csv_rows(d / "audio_shots.csv")


def _audio_row(shots, audio, i):
    if i < len(audio) and audio[i]["chapter"] == shots[i]["chapter"] and str(audio[i]["shot"]) == str(shots[i]["shot"]):
        return audio[i]
    return {}


def scene_data(slug, chapter=""):
    d, shots, audio = _scene_tables(slug)
    edits = read_json(d / "prompt_edits.json", {})
    order, counts, edited = [], {}, {}
    for r in shots:
        if r["chapter"] not in counts:
            order.append(r["chapter"]); counts[r["chapter"]] = 0; edited[r["chapter"]] = 0
        counts[r["chapter"]] += 1
    for e in edits.values():
        if e.get("chapter") in edited:
            edited[e["chapter"]] += 1
    chapter = chapter if chapter in counts else order[0]
    existing = {}                                           # which downloaded files already exist, per row (shot-mode folders only)
    for top, pattern in (("videos", "shot-{:04d}.mp4"), ("audio", None)):
        for sub in sorted((d / top).glob("*")) if (d / top).is_dir() else []:
            if sub.is_dir() and not sub.name.endswith("_chapters"):
                for f in sub.iterdir():
                    m = OUTPUT_PATTERN.match(f.name)
                    if m and m.group(1) != "image":
                        existing.setdefault(int(m.group(2)), []).append(f"{top}/{sub.name}/{f.name}")
    items = []
    for i, r in enumerate(shots):
        if r["chapter"] != chapter:
            continue
        a = _audio_row(shots, audio, i)
        mine = edits.get(f"{chapter}#{r['shot']}", {}).get("fields", {})
        items.append({"shot": int(r["shot"]), "row": i + 1, "prompt": r["prompt"], "narration": a.get("narration", ""),
                      "sfx": a.get("sfx", ""), "music": a.get("music", ""), "has_audio": bool(a),
                      "edited": {k: v["original"] for k, v in mine.items()}, "clips": sorted(existing.get(i + 1, []))})
    return {"chapters": [{"chapter": c, "shots": counts[c], "edited": edited[c]} for c in order], "chapter": chapter, "shots": items}


def _check_scene_args(opt):
    slug = str(opt.get("project", ""))
    d, shots, audio = _scene_tables(slug)
    chapter, field = str(opt.get("chapter", "")), str(opt.get("field", "prompt"))
    try:
        shot = int(opt.get("shot"))
    except (TypeError, ValueError):
        raise PlanError("choose a shot")
    if field not in EDIT_FIELDS:
        raise PlanError("unknown field")
    idx = next((i for i, r in enumerate(shots) if r["chapter"] == chapter and str(r["shot"]) == str(shot)), None)
    if idx is None:
        raise PlanError("that scene does not exist in this project")
    if field != "prompt" and not _audio_row(shots, audio, idx):
        raise PlanError("this project has no narration/sound/music prompts to edit")
    return slug, d, shots, audio, idx, chapter, shot, field


def _current(shots, audio, idx, field):
    return shots[idx]["prompt"] if field == "prompt" else _audio_row(shots, audio, idx).get(field, "")


def prompt_save(opt):
    slug, d, shots, audio, idx, chapter, shot, _ = _check_scene_args({**opt, "field": "prompt"})
    fields = opt.get("fields") or {}
    if not isinstance(fields, dict) or not fields:
        raise PlanError("nothing to save")
    edits = read_json(d / "prompt_edits.json", {})
    key = f"{chapter}#{shot}"
    entry = edits.setdefault(key, {"chapter": chapter, "shot": shot, "fields": {}})
    saved, reverted = [], []
    for field, new in fields.items():
        if field not in EDIT_FIELDS:
            raise PlanError(f"unknown field {field!r}")
        if field != "prompt" and not _audio_row(shots, audio, idx):
            raise PlanError("this project has no narration/sound/music prompts to edit")
        new = " ".join(str(new).split())
        if not new or len(new) > FIELD_LIMITS[field]:
            raise PlanError(f"the {FIELD_TITLES[field]} must be 1 to {FIELD_LIMITS[field]} characters")
        cur = _current(shots, audio, idx, field)
        orig = entry["fields"].get(field, {}).get("original", cur)
        if new == orig:                                      # back to the original text: the same as reverting
            entry["fields"].pop(field, None); reverted.append(field)
        else:
            entry["fields"][field] = {"original": orig, "edited": new}; saved.append(field)
        set_scene_field(d, chapter, shot, field, new)
    if not entry["fields"]:
        edits.pop(key, None)
    else:
        entry["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_json(d / "prompt_edits.json", edits)
    return {"saved": saved, "reverted": reverted, "row": idx + 1}


def prompt_revert(opt):
    slug, d, shots, audio, idx, chapter, shot, _ = _check_scene_args({**opt, "field": "prompt"})
    edits = read_json(d / "prompt_edits.json", {})
    entry = edits.get(f"{chapter}#{shot}")
    if not entry:
        raise PlanError("this scene has no saved edits")
    only = opt.get("field")
    for field in [f for f in list(entry["fields"]) if not only or f == only]:
        set_scene_field(d, chapter, shot, field, entry["fields"][field]["original"])
        del entry["fields"][field]
    if not entry["fields"]:
        edits.pop(f"{chapter}#{shot}", None)
    write_json(d / "prompt_edits.json", edits)
    return {"row": idx + 1}


def prompt_suggest(opt):
    slug, d, shots, audio, idx, chapter, shot, field = _check_scene_args(opt)
    hint = " ".join(str(opt.get("hint") or "").split())
    if not hint or len(hint) > 1500:
        raise PlanError("write your idea or hint first (up to 1500 characters)")
    count = num(opt, "count", 3, int, 1, 4)
    current = " ".join(str(opt.get("current") or "").split()) or _current(shots, audio, idx, field)
    a = _audio_row(shots, audio, idx)
    same = [i for i, r in enumerate(shots) if r["chapter"] == chapter]
    before = shots[idx - 1]["prompt"][:350] if idx - 1 in same else ""
    after = shots[idx + 1]["prompt"][:350] if idx + 1 in same else ""
    source = ""
    mm = re.match(rf"^{re.escape(slug)}-(\d+)$", chapter)
    if mm:
        sc = read_json(d / "scripts" / f"chapter-{int(mm.group(1)):03d}.json", {})
        sh = (sc.get("shots") or [])
        source = (sh[shot - 1].get("slice") or "")[:900] if 0 < shot <= len(sh) else ""
    bible = read_json(d / "bible.json", {})
    chars = "; ".join(f"{c['name']}: {c['token']}" for c in bible.get("characters", []))[:1800]
    rules = {
        "prompt": ("a text-to-video prompt for ONE continuous shot of about 4 seconds: shot size, camera movement, subject, action, setting, light. "
                   "No on-screen text, nothing modern. Keep any fixed character descriptions (like NAME: description) and any trailing style/quality "
                   "phrases exactly as they are in the current prompt. At most 900 characters.", 900),
        "narration": ("one line the narrator speaks over the shot, at most 14 words, in the same voice as the current line.", 200),
        "sfx": ("a description of ambience and sound effects to hear in the shot, at most 25 words, no speech or music.", 300),
        "music": ("a description of the score for the shot (instruments, mood, tempo), at most 25 words.", 300),
    }
    rule, limit = rules[field]
    prompt = (f"A director is refining ONE scene of a film adapted from a book. They want to change the {FIELD_TITLES[field]}.\n\n"
              f"CURRENT {FIELD_TITLES[field].upper()}:\n{current}\n\n"
              + (f"THE BOOK TEXT FOR THIS SHOT:\n{source}\n\n" if source else "")
              + (f"WHAT IS SPOKEN OVER THIS SHOT: {a.get('narration', '')}\n\n" if a.get("narration") and field != "narration" else "")
              + (f"PREVIOUS SHOT'S PROMPT (for continuity): {before}\n" if before else "") + (f"NEXT SHOT'S PROMPT: {after}\n" if after else "")
              + (f"\nCHARACTERS (keep their descriptions unchanged): {chars}\n" if chars and field == "prompt" else "")
              + f"\nTHE DIRECTOR'S IDEA OR HINT (include it, even though the book text does not mention it; be creative about how):\n{hint}\n\n"
              f"Write {count} different versions of the {FIELD_TITLES[field]} that work the idea in. Each must be {rule}\n"
              f'Reply with one JSON object: {{"suggestions": ["...", ...]}} with exactly {count} strings.')

    def check(data):
        sug = data.get("suggestions")
        if not isinstance(sug, list) or len(sug) != count or not all(isinstance(x, str) and 10 < len(x.strip()) <= limit + 100 for x in sug):
            raise ValueError(f"'suggestions' must be {count} strings, each at most {limit} characters")

    args = engine_args(opt)
    data = llm_json(prompt, "You are a film director and prompt writer. You reply with a single JSON object and nothing else.",
                    model=(args[3] if len(args) > 3 else None), engine=args[1], validate=check)
    return [x.strip() for x in data["suggestions"]]


# ---------------------------------------------------------------- creative direction
DIR_SYSTEM = (
    "You are a film director and creative consultant for a book-to-film adaptation project. "
    "The user provides creative direction — visual style, tone, directorial choices, things not in the book bible. "
    "Your job: analyze their direction, ask clarifying questions to fill gaps, and produce a finalized "
    "creative direction document that will be appended to EVERY shot prompt for this book. "
    "You have access to the book's bible (characters, setting, visual_style, music_theme). "
    "Be specific, practical, and respect the source material. "
    "When you have enough information, output a finalized direction and set finalized=true. "
    "Reply with a single JSON object: "
    '{"messages": [...], "status": "...", "finalized": true|false}'
)

def creative_direction(opt):
    messages = opt.get("messages", [])
    if not isinstance(messages, list):
        raise PlanError("messages must be a list")
    project = opt.get("project", "")
    bible_data = opt.get("bible", {})

    # Build context from bible
    chars = []
    for c in bible_data.get("characters", []):
        chars.append(f"{c['name']}: {c['token']}")
    char_text = "; ".join(chars) if chars else "none defined"
    setting = bible_data.get("setting", "")
    visual_style = bible_data.get("visual_style", "")
    music_theme = bible_data.get("music_theme", "")

    context = (
        f"BOOK BIBLE:\n"
        f"Setting: {setting}\n"
        f"Visual Style: {visual_style}\n"
        f"Music Theme: {music_theme}\n"
        f"Characters: {char_text}\n"
    )

    # Build the conversation for the LLM
    convo = [{"role": "system", "content": DIR_SYSTEM + "\n\n" + context}]
    for m in messages:
        convo.append({"role": m.get("role", "user"), "content": m.get("content", "")})

    def check(data):
        if not isinstance(data.get("messages"), list):
            raise ValueError("messages must be a list")
        # Each message should have role and content
        for m in data["messages"]:
            if not isinstance(m.get("role"), str) or not isinstance(m.get("content"), str):
                raise ValueError("each message must have role and content strings")

    args = engine_args(opt)
    data = llm_json(
        "Continue the conversation. Analyze the user's creative direction, ask questions if needed, "
        "or produce the finalized creative direction document.",
        DIR_SYSTEM + "\n\n" + context,
        model=(args[3] if len(args) > 3 else None),
        engine=args[1],
        validate=check
    )

    # Save the conversation to project file
    if project:
        d = PROJECTS / project
        d.mkdir(parents=True, exist_ok=True)
        # Save full conversation
        write_json(d / "creative_direction.json", {"messages": data["messages"], "updated": time.strftime("%Y-%m-%d %H:%M:%S")})
        # If finalized, also save the finalized direction text for easy access
        finalized_msgs = [m for m in data["messages"] if m.get("finalized")]
        if finalized_msgs:
            # Add to bible.json as creative_direction field
            bible = read_json(d / "bible.json", {})
            bible["creative_direction"] = finalized_msgs[-1]["content"]
            write_json(d / "bible.json", bible)

    return data


def creative_direction_get(opt):
    project = opt.get("project", "")
    if not project:
        raise PlanError("project required")
    d = PROJECTS / project
    path = d / "creative_direction.json"
    if path.exists():
        return read_json(path, {"messages": []})
    return {"messages": []}


def bible_get(opt):
    project = opt.get("project", "")
    if not project:
        raise PlanError("project required")
    d = PROJECTS / project
    return read_json(d / "bible.json", {})


def recreate_notebooks():
    r = subprocess.run(["python3", "tools/make_all.py"], cwd=SCRIPTS, env=clean_env(), capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise PlanError("could not re-create the notebooks: " + (r.stderr or r.stdout)[-300:])
    return {"notebooks": len(list(ROOT.glob("Bible_*.ipynb"))), "scripts": len(list(ROOT.glob("colab_generate_*.py")))}


# ---------------------------------------------------------------- job runner
class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.lines, self.running, self.proc, self.stop_flag = [], False, None, False
        self.current = ""

    def log(self, line):
        with self.lock:
            self.lines.append(line)

    def start(self, steps, opt):
        with self.lock:
            if self.running:
                raise PlanError("a job is already running")
            self.lines, self.running, self.stop_flag = [], True, False
        threading.Thread(target=self._run, args=(list(steps), opt), daemon=True).start()

    def _run(self, steps, opt):
        keep_going = bool(opt.get("keep_going"))
        env_base = clean_env()
        n = 0
        while n < len(steps):
            step = steps[n]
            n += 1
            if self.stop_flag:
                break
            if "expand" in step:
                try:
                    new = generation_steps(opt, project_slug(opt))
                except PlanError as e:
                    self.log(f"!! cannot plan the movies: {e}")
                    break
                self.log(f"\n===== planned {len(new)} generation step(s) for the chosen movies")
                steps[n:n] = new
                continue
            self.current = f"{n}/{len(steps)} {step['label']}"
            self.log(f"\n===== [{n}/{len(steps)}] {step['label']}\n$ {shell_form(step)}")
            cwd = step.get("cwd", SCRIPTS)
            try:
                self.proc = subprocess.Popen(step["argv"], cwd=cwd, env={**env_base, **step["env"]}, text=True,
                                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
                for line in self.proc.stdout:
                    self.log(line.rstrip("\n"))
                code = self.proc.wait()
            except FileNotFoundError as e:
                self.log(f"!! cannot start: {e}")
                code = 127
            if self.stop_flag:
                break
            if code not in step.get("ok_codes", (0,)):
                self.log(f"!! step failed with exit code {code}")
                if not keep_going:
                    self.log("Stopped. Fix the problem and run again (finished work is kept).")
                    break
        with self.lock:
            self.running = False
            self.current = ""
        self.log("\n===== job finished" + (" (stopped)" if self.stop_flag else ""))

    def stop(self):
        self.stop_flag = True
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass


JOB = Job()


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "PistachiosStudio"

    def log_message(self, *a):
        pass

    def _host_ok(self):
        host, origin, port = self.headers.get("Host", ""), self.headers.get("Origin"), self.server.server_port
        return host in (f"127.0.0.1:{port}", f"localhost:{port}") and (
            origin is None or origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"))

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj))

    def _authed(self):
        return self._host_ok() and secrets.compare_digest(self.headers.get("X-Studio-Token", ""), TOKEN)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            if not self._host_ok() or not secrets.compare_digest(parse_qs(url.query).get("t", [""])[0], TOKEN):
                return self._send(403, "Open the link printed by studio.py (it contains the token).", "text/plain")
            return self._send(200, (ROOT / "studio.html").read_text().replace("__TOKEN__", TOKEN), "text/html; charset=utf-8")
        if url.path.startswith("/file/"):
            return self._file(url)
        if not self._authed():
            return self._json(403, {"error": "forbidden"})
        if url.path == "/api/scenes":
            q = parse_qs(url.query)
            try:
                return self._json(200, scene_data(q.get("project", [""])[0], q.get("chapter", [""])[0]))
            except PlanError as e:
                return self._json(400, {"error": str(e)})
        if url.path == "/api/files":
            try:
                return self._json(200, {"folders": files_inventory(parse_qs(url.query).get("project", [""])[0])})
            except PlanError as e:
                return self._json(400, {"error": str(e)})
        if url.path == "/api/cleanup_scan":
            return self._json(200, {"categories": cleanup_scan()})
        if url.path == "/api/media":
            try:
                return self._json(200, media_inventory(parse_qs(url.query).get("project", [""])[0]))
            except PlanError as e:
                return self._json(400, {"error": str(e)})
        if url.path == "/api/kaggle_runs":
            try:
                return self._json(200, {"runs": kaggle_runs()})
            except PlanError as e:
                return self._json(400, {"error": str(e)})
            except subprocess.TimeoutExpired:
                return self._json(400, {"error": "Kaggle did not answer in time; try again"})
        if url.path == "/api/gallery":
            slug = parse_qs(url.query).get("project", [""])[0]
            return self._json(200, {"items": gallery(slug) if SLUG_RE.match(slug) else []})
        if url.path == "/api/status":
            return self._json(200, status())
        if url.path == "/api/bible":
            slug = parse_qs(url.query).get("project", [""])[0]
            if not SLUG_RE.match(slug):
                return self._json(400, {"error": "project required"})
            return self._json(200, bible_get({"project": slug}))
        if url.path == "/api/log":
            since = int(parse_qs(url.query).get("since", ["0"])[0])
            with JOB.lock:
                return self._json(200, {"lines": JOB.lines[since:], "next": len(JOB.lines),
                                        "running": JOB.running, "current": JOB.current})
        self._json(404, {"error": "not found"})

    MEDIA = {".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg", ".wav": "audio/wav"}

    def _file(self, url):
        """Serve a result file: /file/<project>/<path under it>?t=<token>. Only media inside projects/<project>/."""
        if not self._host_ok() or not secrets.compare_digest(parse_qs(url.query).get("t", [""])[0], TOKEN):
            return self._json(403, {"error": "forbidden"})
        parts = url.path[len("/file/"):].split("/", 1)
        if len(parts) != 2 or not SLUG_RE.match(parts[0]):
            return self._json(404, {"error": "not found"})
        base = (PROJECTS / parts[0]).resolve()
        target = (base / parts[1]).resolve()
        if base not in target.parents or target.suffix.lower() not in self.MEDIA or not target.is_file():
            return self._json(404, {"error": "not found"})
        size, start, end, code = target.stat().st_size, 0, target.stat().st_size - 1, 200
        rng = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if rng and (rng.group(1) or rng.group(2)):
            if rng.group(1):
                start = int(rng.group(1)); end = int(rng.group(2)) if rng.group(2) else end
            else:
                start = max(size - int(rng.group(2)), 0)
            end = min(end, size - 1)
            if start > end:
                self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.end_headers(); return
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", self.MEDIA[target.suffix.lower()])
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with open(target, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                self.wfile.write(chunk); left -= len(chunk)

    def _upload(self, url):
        q = parse_qs(url.query)
        fname = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(q.get("filename", ["book.pdf"])[0]).name).strip()
        if not fname.lower().endswith(".pdf") or len(fname) < 5:
            return self._json(400, {"error": "only .pdf files"})
        if not SLUG_RE.match(slugify(Path(fname).stem)):
            return self._json(400, {"error": "that file name has no letters or digits to name the book from"})
        size = int(self.headers.get("Content-Length", 0))
        if size <= 0 or size > MAX_UPLOAD:
            return self._json(400, {"error": f"file must be 1 byte to {MAX_UPLOAD // 2**20} MB"})
        LIBRARY.mkdir(exist_ok=True)
        tmp = LIBRARY / (fname + ".part")
        left = size
        with open(tmp, "wb") as f:
            while left:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk); left -= len(chunk)
        with open(tmp, "rb") as f:
            ok = f.read(5) == b"%PDF-"
        if left or not ok:
            tmp.unlink(missing_ok=True)
            return self._json(400, {"error": "that is not a complete PDF file"})
        tmp.replace(LIBRARY / fname)
        return self._json(200, {"filename": fname, "project": slugify(Path(fname).stem), "bytes": size})

    def do_POST(self):
        if not self._authed():
            return self._json(403, {"error": "forbidden"})
        url = urlparse(self.path)
        try:
            if url.path == "/api/upload":
                return self._upload(url)
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
            if url.path == "/api/plan":
                steps = build_plan(body)
                return self._json(200, {"steps": [{"label": s["label"], "cmd": shell_form(s)} for s in steps]})
            if url.path == "/api/estimate":
                return self._json(200, {"text": estimate(body)})
            if url.path == "/api/prompt_suggest":
                return self._json(200, {"suggestions": prompt_suggest(body)})
            if url.path == "/api/prompt_save":
                return self._json(200, prompt_save(body))
            if url.path == "/api/prompt_revert":
                return self._json(200, prompt_revert(body))
            if url.path == "/api/trash_files":
                if JOB.running:
                    raise PlanError("a job is running; wait for it to finish first")
                return self._json(200, trash_files(str(body.get("project", "")), str(body.get("folder", "")), [str(n) for n in body.get("names", [])]))
            if url.path == "/api/cleanup_delete":
                if JOB.running:
                    raise PlanError("a job is running; wait for it to finish first")
                return self._json(200, cleanup_delete(body.get("categories") or []))
            if url.path == "/api/recreate_notebooks":
                return self._json(200, recreate_notebooks())
            if url.path == "/api/make_film":
                slug, clips, step = film_step(body)
                (PROJECTS / slug / "films" / "_selection.json").write_text(json.dumps({"clips": clips}, indent=1))
                JOB.start([step], body)
                return self._json(200, {"clips": len(clips)})
            if url.path == "/api/fetch":
                JOB.start([fetch_step(body)], body)
                return self._json(200, {"started": 1})
            if url.path == "/api/expand":
                return self._json(200, {"prompts": expand_idea(body)})
            if url.path == "/api/creative_direction":
                return self._json(200, creative_direction(body))
            if url.path == "/api/creative_direction_get":
                return self._json(200, creative_direction_get(body))
            if url.path == "/api/run":
                steps = build_plan(body, commit=True)       # prompt mode writes its rows here, not when previewing
                JOB.start(steps, body)
                return self._json(200, {"started": len(steps)})
            if url.path == "/api/stop":
                JOB.stop()
                return self._json(200, {"stopping": True})
        except PlanError as e:
            return self._json(400, {"error": str(e)})
        except (ValueError, KeyError, TypeError) as e:
            return self._json(400, {"error": f"bad request: {e}"})
        self._json(404, {"error": "not found"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    srv = None
    for port in range(a.port, a.port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if srv is None:
        raise SystemExit("no free port found")
    url = f"http://127.0.0.1:{srv.server_port}/?t={TOKEN}"
    print(f"Pistachio's Studio running. Open: {url}\nCtrl-C to stop.", flush=True)
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        JOB.stop()
        print("\nstopped")


if __name__ == "__main__":
    main()
