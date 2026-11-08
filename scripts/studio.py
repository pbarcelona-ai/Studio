#!/usr/bin/env python3
"""Local control page for the Pistachio's Studio pipeline.

    cd <the Studio folder> && python3 scripts/studio.py        (or double-click the app, or run ./run_studio.sh)

Opens http://127.0.0.1:8765/?t=<token>. Pick a book (project), optionally upload a new PDF, tick what to do, and this
server runs the project's own scripts one after another: book_ingest.py, book_continuity.py, book_write.py, book_build.py
(prompts written by Claude Code), run_kaggle_model.sh / run_colab_model.sh (video and audio on a free GPU), then
merge_videos.py / mix_film.py (one film per ~10-minute movie).
Safety: listens on 127.0.0.1 only, every API call needs the random token printed at start-up, and only whitelisted
scripts with validated arguments can run (no shell, no free-form commands).
"""
import argparse, csv, hashlib, io, json, mimetypes, os, re, secrets, shutil, signal, struct, subprocess, sys, threading, time, webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bookkit import EDIT_FIELDS, KOKORO_VOICE_RE, KOKORO_VOICES, VOICE_CAST_FILE, apply_voice_cast, read_voice_cast, voice_id, continuity_file, LOCAL_LLM_URL, SLUG_RE, build_movies, hf_json, llm_json, local_chat, read_json, set_scene_field, slugify, write_json
import character_tokens
import hf_spaces
import prompt_guides
import setup_check
import layout
import model_advisor
import run_local_model
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
LIBRARY = ROOT / "books"          # every book PDF lives here; the page lists them
SESSION_FILE = ROOT / ".studio_session.json"  # persistent session storage

# Session persistence: try to load existing session, otherwise generate new
def load_or_create_session():
    """Load existing session or create new one."""
    if SESSION_FILE.exists():
        try:
            import json
            session = json.loads(SESSION_FILE.read_text())
            # Verify the session is still valid (server might be running on that port)
            if "token" in session and "port" in session:
                return session["token"], session["port"]
        except Exception:
            pass
    # Create new session
    return secrets.token_urlsafe(16), None

TOKEN, SESSION_PORT = load_or_create_session()

VIDEO_MODELS = ["ltx_video", "wan", "wan22_ti2v_5b", "wan22_t2v_a14b", "hunyuan_video", "cogvideox", "cogvideox_5b",
                "wan22_t2v_a14b_lora", "wan22_t2v_a14b_lightning", "hunyuan_video_lora", "hunyuan_video_15", "tpu_wan",     # tpu_wan = Kaggle TPU experiment
                "ltx_video_i2v", "wan22_ti2v_5b_i2v"]                     # image-to-video: animate each shot's keyframe
I2V_MODELS = {"ltx_video_i2v", "wan22_ti2v_5b_i2v"}
# Upscalers: enlarge clips already made (make_video.py); Kaggle or this computer. name -> (label, GPU memory it needs, least GPU GB, needs Ampere or newer)
UPSCALE_MODELS = {
    "upscale_x2": ("Real-ESRGAN x2", "about 2-4 GB of GPU memory, any NVIDIA GPU. Tested on a Kaggle T4: about 40 s per clip", 3, False),
    "upscale_flashvsr": ("FlashVSR v1.1", "8 GB minimum (it tiles), 16 GB+ recommended. Ampere or newer GPU only (RTX 30/40/50, A100, L4; not a T4); "
                         "the first run builds a CUDA kernel: 20-60 minutes, about 32 GB of system RAM and the CUDA compiler. Not tested yet", 8, True),
    "upscale_seedvr2_3b": ("SeedVR2 3B", "24 GB for full speed; 8-16 GB works with block swap (slower) and wants 32 GB of system RAM. Not tested yet", 8, False),
    "upscale_seedvr2_7b": ("SeedVR2 7B", "40 GB+ for full speed, 24 GB with its fp8 model; 12-16 GB works with block swap (very slow) and wants 32-64 GB "
                           "of system RAM. Not tested yet", 12, False),
}
UPSCALE_SHORT = {"upscale_x2": "2-4 GB, any NVIDIA GPU", "upscale_flashvsr": "8 GB min, 16 GB+ best; RTX 30 or newer",
                 "upscale_seedvr2_3b": "8-16 GB slow, 24 GB full speed", "upscale_seedvr2_7b": "12-16 GB very slow, 24-40 GB+ full speed"}   # beside each choice on the page
UPSCALE_SUFFIXES = tuple("_" + m.removeprefix("upscale_") for m in UPSCALE_MODELS)      # videos/<source>_x2, _flashvsr, ...: already upscaled
KAGGLE_GPU_GB = {"NvidiaTeslaT4": 15, "NvidiaL4": 22, "NvidiaTeslaA100": 40, "NvidiaH100": 80}      # memory per GPU, and which are older than Ampere
KAGGLE_PRE_AMPERE = {"NvidiaTeslaT4"}
COLAB_GPU_GB = {"T4": 15, "L4": 22, "A100": 40, "H100": 80}
REF_IMAGE_MODELS = {"flux2_klein_4b"}                                    # keyframe models that take character reference pictures                      # need keyframes (images/<model>_keyframes) for every row they make
# How the Models tab groups them: (title, [models]). A model missing here lands in "Other" on the page.
VIDEO_GROUPS = [("LTX-Video", ["ltx_video"]), ("Wan", ["wan", "wan22_ti2v_5b", "wan22_t2v_a14b", "wan22_t2v_a14b_lightning"]), ("HunyuanVideo", ["hunyuan_video_15", "hunyuan_video"]),
                ("CogVideoX", ["cogvideox", "cogvideox_5b"]), ("Uncensored (adult content)", ["wan22_t2v_a14b_lora", "hunyuan_video_lora"]),
                ("TPU (Kaggle only)", ["tpu_wan"]), ("From keyframes (image-to-video, Kaggle or this computer)", ["wan22_ti2v_5b_i2v", "ltx_video_i2v"])]
# Audio models: name -> (role, label, short note). The role decides which sound it makes (narration / sfx / music) and the file prefix it writes.
AUDIO_MODELS = {
    "kokoro": ("narration", "Kokoro", "fast, light narration voices"),
    "qwen3_tts": ("narration", "Qwen3-TTS 1.7B", "newer, more natural voices (Jan 2026)"),
    "chatterbox_turbo": ("narration", "Chatterbox-Turbo", "natural voice, understands tags like [chuckle]"),
    "mmaudio": ("sfx", "MMAudio", "experimental"),
    "musicgen": ("music", "MusicGen", "15 s background score"),
}
AUDIO_KINDS = list(AUDIO_MODELS)
AUDIO_ROLE_TITLES = {"narration": "Narration", "sfx": "Sound effects", "music": "Music"}
IMAGE_MODELS = ["sdxl_turbo", "sdxl", "sd35_large", "sd35_large_turbo", "flux1_schnell", "flux1_dev", "flux2_klein_4b", "qwen_image_21",
                "moss_image_sft", "moss_image_base", "moss_sharpness_slider",
                "qwen_image_21_uc", "qwen_image_21_lora", "moss_image_sft_lora", "chroma1_hd", "noobai_xl", "realvisxl_v5", "illustrious_xl",
                "z_image_turbo", "z_image", "ernie_image_turbo", "qwen_image_21_turbo",
                "tpu_mage_flow", "tpu_flux_jax"]                          # the tpu_ ones run only on Kaggle's TPU
IMAGE_GROUPS = [("Stable Diffusion", ["sdxl_turbo", "sdxl", "sd35_large", "sd35_large_turbo"]), ("FLUX", ["flux1_schnell", "flux1_dev", "flux2_klein_4b"]),
                ("Qwen-Image", ["qwen_image_21", "qwen_image_21_turbo"]), ("Z-Image", ["z_image_turbo", "z_image"]), ("ERNIE-Image", ["ernie_image_turbo"]), ("MOSS-Image", ["moss_image_sft", "moss_image_base", "moss_sharpness_slider"]),
                ("Uncensored (adult content)", ["qwen_image_21_uc", "qwen_image_21_lora", "moss_image_sft_lora", "chroma1_hd", "noobai_xl", "realvisxl_v5", "illustrious_xl"]),
                ("TPU (Kaggle only)", ["tpu_mage_flow", "tpu_flux_jax"])]
# Defaults baked into each generator script; shown as placeholders on the page. "locked" = fields the model ignores (greyed out).
MODEL_DEFAULTS = {
    "ltx_video": {"width": 768, "height": 320, "frames": 97, "steps": 40, "guidance": 3.0},
    "wan": {"width": 512, "height": 288, "frames": 33, "steps": 30, "guidance": 5.0},
    "cogvideox": {"width": 720, "height": 480, "frames": 49, "steps": 50, "guidance": 6.0, "locked": ["width", "height", "frames"]},
    "cogvideox_5b": {"width": 720, "height": 480, "frames": 49, "steps": 50, "guidance": 6.0, "locked": ["width", "height", "frames"]},
    "wan22_ti2v_5b": {"width": 704, "height": 384, "frames": 33, "steps": 30, "guidance": 5.0},
    "ltx_video_i2v": {"width": 768, "height": 320, "frames": 97, "steps": 40, "guidance": 3.0},
    "wan22_ti2v_5b_i2v": {"width": 704, "height": 384, "frames": 33, "steps": 30, "guidance": 5.0},
    "wan22_t2v_a14b": {"width": 448, "height": 256, "frames": 25, "steps": 30, "guidance": 4.0},
    "wan22_t2v_a14b_lora": {"width": 448, "height": 256, "frames": 25, "steps": 30, "guidance": 4.0},
    "wan22_t2v_a14b_lightning": {"width": 448, "height": 256, "frames": 25, "steps": 4, "guidance": 1.0, "locked": ["negative", "steps", "guidance"]},
    "hunyuan_video": {"width": 480, "height": 272, "frames": 33, "steps": 30, "guidance": 6.0, "locked": ["negative"]},
    "hunyuan_video_lora": {"width": 480, "height": 272, "frames": 33, "steps": 30, "guidance": 6.0, "locked": ["negative"]},
    "hunyuan_video_15": {"width": 640, "height": 368, "frames": 33, "steps": 30, "guidance": 1.0, "locked": ["negative", "guidance"]},
    "tpu_wan": {"width": 832, "height": 480, "frames": 33, "steps": 30, "guidance": 5.0, "locked": ["width", "height", "frames"]},   # same settings for every row
    "tpu_mage_flow": {"width": 512, "height": 512, "steps": 4, "guidance": 0.0, "locked": ["height", "steps", "guidance", "negative"]},   # width picks 512/768/1024
    "tpu_flux_jax": {"width": 512, "height": 512, "steps": 20, "guidance": 4.0, "locked": ["negative"]},
    "sdxl_turbo": {"width": 512, "height": 512, "steps": 4, "guidance": 0.0},
    "sdxl": {"width": 1024, "height": 1024, "steps": 30, "guidance": 7.0},
    "sd35_large": {"width": 768, "height": 768, "steps": 28, "guidance": 3.5},
    "sd35_large_turbo": {"width": 1024, "height": 1024, "steps": 4, "guidance": 0.0},
    "flux1_schnell": {"width": 1024, "height": 1024, "steps": 4, "guidance": 0.0, "locked": ["negative", "guidance"]},
    "flux1_dev": {"width": 1024, "height": 1024, "steps": 28, "guidance": 3.5, "locked": ["negative"]},
    "flux2_klein_4b": {"width": 1024, "height": 1024, "steps": 4, "guidance": 1.0, "locked": ["negative"]},
    "chroma1_hd": {"width": 1024, "height": 1024, "steps": 40, "guidance": 3.0},
    "qwen_image_21_lora": {"width": 1024, "height": 1024, "steps": 40, "guidance": 0.0, "locked": ["negative", "guidance"]},
    "noobai_xl": {"width": 1024, "height": 1024, "steps": 28, "guidance": 5.0},
    "realvisxl_v5": {"width": 1024, "height": 1024, "steps": 30, "guidance": 5.0},
    "illustrious_xl": {"width": 1024, "height": 1024, "steps": 28, "guidance": 5.5},
    "z_image_turbo": {"width": 1024, "height": 1024, "steps": 9, "guidance": 0.0, "locked": ["negative", "guidance"]},
    "z_image": {"width": 1024, "height": 1024, "steps": 50, "guidance": 4.0},
    "ernie_image_turbo": {"width": 1024, "height": 1024, "steps": 8, "guidance": 1.0, "locked": ["negative"]},
    "qwen_image_21_turbo": {"width": 1024, "height": 1024, "locked": ["steps", "negative", "guidance"]},
    "qwen_image_21": {"width": 1024, "height": 1024, "steps": 40, "guidance": 0.0, "locked": ["negative", "guidance"]},
    "qwen_image_21_uc": {"width": 1024, "height": 1024, "steps": 40, "guidance": 0.0, "locked": ["negative", "guidance"]},
    "moss_image_sft_lora": {"width": 1024, "height": 1024, "steps": 30, "guidance": 3.0},
    "moss_image_sft": {"width": 1024, "height": 1024, "steps": 50, "guidance": 3.0},
    "moss_image_base": {"width": 1024, "height": 1024, "steps": 50, "guidance": 3.0},
    "moss_sharpness_slider": {"width": 1024, "height": 1024, "steps": 50, "guidance": 3.0},
}
LEGACY = {"adam_eve", "enoch"}        # imported production notes; rebuilt with legacy_extract.py
# Suggestions only: the page lets you type ANY model name that `claude --model` accepts (aliases or full IDs).
CLAUDE_MODELS = ["sonnet", "opus", "haiku", "claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]

# Character series mapping: project slug -> character series name
# This determines which character token set to use for a project
CHARACTER_SERIES = {
    "adam_eve": "main",
    "enoch": "main",
    # Add more mappings as new series are added
    # "mcnally_1": "mcnally",
    # "mcnally_2": "mcnally",
}

def get_character_series(slug):
    """Get the character series for a project slug."""
    return CHARACTER_SERIES.get(slug, slug)  # default to project slug if not mapped
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/\[\]-]{1,79}$")
GPUS = {  # "paid"/"restricted" are warnings only; Kaggle's own docs say some accelerators are not open to everyone
    "colab": [("T4", "T4 (free tier, often unavailable)"), ("L4", "L4 (paid)"), ("A100", "A100 (paid)"), ("H100", "H100 (paid)")],
    "kaggle": [("NvidiaTeslaT4", "T4 x2 (free)"), ("NvidiaL4", "L4 (may be restricted)"),
               ("NvidiaTeslaA100", "A100 (may be restricted)"), ("NvidiaH100", "H100 (may be restricted)"),
               ("TpuV5E8", "TPU v5e-8 (experimental; only for tpu_wan)")],
    "huggingface": [("ZeroGPU", "ZeroGPU: Hugging Face's shared GPUs (free daily quota)")],     # runs a public Space, only for the models in hf_spaces.py
    "computer": [("local", "This computer's NVIDIA GPU")],       # scripts/run_local_model.py: no website; the label is filled in from nvidia-smi
}
MAX_UPLOAD = 300 * 1024 * 1024
BOOK_EXTS = (".pdf", ".txt", ".md")                   # what can be imported as a book: a PDF, or plain text (a file or pasted text)

# Run jobs in a clean environment: the OSS CAD Suite shell setup sets PYTHONHOME and puts its own Python first
# on PATH, which breaks uv-managed Pythons. Drop those so `uv run` and `python3` behave normally.
_PATH = [d for d in os.environ.get("PATH", "").split(":") if d and "oss-cad-suite" not in d]
_VENV_BIN = [str(ROOT / ".venv" / "bin")] if (ROOT / ".venv" / "bin").is_dir() else []      # install.sh puts kaggle, uv and the Python packages here
ENV_PATH = ":".join(_VENV_BIN + [f"{Path.home()}/.local/bin", "/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin"] + _PATH)
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
    return sorted(p.name for p in LIBRARY.iterdir() if p.is_file() and p.suffix.lower() in BOOK_EXTS)


def pdf_choices(slug):
    """PDFs a project can be read from: the matching file in books/ first, then PDFs already copied to its source/."""
    out = [{"value": f"books/{f}", "label": f"books/{f}"} for f in library_files() if slugify(Path(f).stem) == slug]
    out += [{"value": f"books/{f}", "label": f"books/{f} (other)"} for f in library_files() if slugify(Path(f).stem) != slug]
    src = pdir(slug) / "source"
    out += [{"value": p.name, "label": f"{layout.rel(slug)}/source/{p.name}"} for p in sorted(src.iterdir()) if p.suffix.lower() in BOOK_EXTS] if src.exists() else []
    return out


def project_info(slug):
    d = pdir(slug)
    chapters = read_json(d / "chapters.json", {})
    if (d / "all_shots.csv").exists() and not (d / "movies.json").exists():
        build_movies(d, 10)
    movies = read_json(d / "movies.json", {})

    # Sync character tokens from the continuity book file
    series = get_character_series(slug)
    character_tokens.sync_characters_from_project(slug)
    char_list = character_tokens.list_characters(series)

    return {
        "slug": slug, "legacy": slug in LEGACY, "not_started": not d.exists(), "pdf_choices": pdf_choices(slug),
        "pdfs": sorted(p.name for p in (d / "source").iterdir() if p.suffix.lower() in BOOK_EXTS) if (d / "source").exists() else [],
        "chapters": len(chapters.get("chapters", [])), "split_method": chapters.get("method"),
        "continuity": continuity_file(d).exists(), "scripts": count_files(d / "scripts", "chapter-*.json"),
        "built": (d / "all_shots.csv").exists(),
        "character_series": series,
        "characters": char_list,
        "movies": {"shots": movies.get("shots", []), "chapters": movies.get("chapters", [])},
        "have": {
            **{f"videos/{m}": count_files(d / "videos" / m, "shot-*.mp4") for m in VIDEO_MODELS},
            **{f"videos/{m}_chapters": count_files(d / "videos" / f"{m}_chapters", "shot-*.mp4") for m in VIDEO_MODELS},
            **{f"audio/{k}": count_files(d / "audio" / k, "*.wav") for k in AUDIO_KINDS},
            **{f"audio/{k}_chapters": count_files(d / "audio" / f"{k}_chapters", "*.wav") for k in AUDIO_KINDS},
            **{f"keyframes/{m}": n for m in IMAGE_MODELS if (n := count_files(d / "images" / f"{m}_keyframes", "image-*.png"))},
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
    d = layout.find_dir(slug)
    return bool(d) and (d / "promptset.json").exists()


def promptset_info(slug):
    d = pdir(slug, "prompts")
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
    for base in (layout.BOOKS, layout.CHARACTERS, layout.PROMPTS, layout.REGRESSION):
        base.mkdir(parents=True, exist_ok=True)
    sets = layout.promptset_slugs()               # Single Prompts sets and character image sets
    slugs = set(layout.book_slugs())              # books
    slugs |= {slugify(Path(f).stem) for f in library_files()}          # books in books/ that have no project yet
    slugs = sorted(x for x in slugs if SLUG_RE.match(x))
    return {
        "tools": {**{t: bool(shutil.which(t, path=ENV_PATH)) for t in ("claude", "fcc-claude", "codex", "fcc-codex", "colab", "kaggle", "uv")},
                  "hf": True, "huggingface": True, "computer": not gpu_blocker("computer", "local"), "local": local_llm_status()["ready"]},     # hf needs no program (its token is checked when it is used); local needs a capable computer and a model server
        "projects": [project_info(s) for s in slugs], "library": library_files(),
        "promptsets": [promptset_info(x) for x in sets], "image_models": IMAGE_MODELS, "model_defaults": MODEL_DEFAULTS,
        "blockers": blockers(),
        "gpu_blockers": {svc: {g: gpu_blocker(svc, g) for g, _ in gl if gpu_blocker(svc, g)} for svc, gl in GPUS.items()},
        "video_models": VIDEO_MODELS, "video_groups": VIDEO_GROUPS, "image_groups": IMAGE_GROUPS, "audio_kinds": AUDIO_KINDS, "audio_models": {k: {"role": r, "label": l, "note": n} for k, (r, l, n) in AUDIO_MODELS.items()}, "audio_roles": AUDIO_ROLE_TITLES, "gpus": {**GPUS, "computer": [("local", local_gpu_label())]}, "computer_why": gpu_blocker("computer", "local"),
        "upscale_models": {k: {"label": l, "short": UPSCALE_SHORT[k], "memory": m, "least_gb": g, "ampere": a} for k, (l, m, g, a) in UPSCALE_MODELS.items()}, "claude_models": CLAUDE_MODELS, "hf_models": HF_MODELS, "hf_vision_models": HF_VISION_MODELS, "hf_token_set": bool(os.environ.get("HF_TOKEN", "").strip()), "local_llm": local_llm_status(),
        "codex_models": codex_models(),
        "looks": [{"id": k, "label": l, "about": a, **model_advisor.STYLE[k]} for k, (l, a) in model_advisor.LOOKS.items()],
    }


# ---- Global Parameters ----
GLOBAL_PARAMS_FILE = "global_params.json"

def load_global_params(project):
    """Load global parameters for a project."""
    path = pdir(project) / GLOBAL_PARAMS_FILE
    if not path.exists():
        return {"positives": "", "negatives": ""}
    try:
        import json
        return json.loads(path.read_text())
    except Exception:
        return {"positives": "", "negatives": ""}

def save_global_params(project, positives, negatives):
    """Save global parameters for a project."""
    path = pdir(project) / GLOBAL_PARAMS_FILE
    pdir(project).mkdir(parents=True, exist_ok=True)
    import json
    path.write_text(json.dumps({"positives": positives, "negatives": negatives}, indent=1))


# ---------------------------------------------------------------- plan -> validated argv steps
def setup_status():
    """The Setup window's data: what this computer has and lacks, plus the Kaggle account name found (never any key)."""
    items = setup_check.check(path=ENV_PATH, local_llm_ready=bool(local_llm_status().get("ready")),
                              local_gpu="" if gpu_blocker("computer", "local") else local_gpu_label())
    return {"items": items, **setup_check.summary(items), "kaggle_username": setup_check.kaggle_state()["username"], "root": str(ROOT)}


class PlanError(ValueError):
    pass


def num(opt, key, default, cast=float, lo=None, hi=None):
    try:
        v = cast(opt.get(key) if opt.get(key) not in (None, "") else default)
    except (TypeError, ValueError):
        raise PlanError(f"{key} must be a number")
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


def script_argv(argv):
    """Steps name their Python scripts bare ("book_continuity.py") but the job runs from the repository root and the scripts live in scripts/."""
    out = []
    for a in argv:
        if a.endswith(".py") and "/" not in a and not (ROOT / a).exists() and (ROOT / "scripts" / a).exists():
            a = f"scripts/{a}"
        out.append(a)
    return out


def shell_form(step):
    if "expand" in step:
        return "(chosen when the earlier steps finish: " + step["label"] + ")"
    env = " ".join(f"{k}={v}" for k, v in step["env"].items())
    return (env + " " if env else "") + " ".join(script_argv(step["argv"]))


ENGINES = ["claude", "fcc-claude", "codex", "fcc-codex", "hf", "local"]
# Open models served by Hugging Face Inference Providers (newest first); any other model id the service lists can be typed in the model box.
HF_MODELS = ["Qwen/Qwen3.8-27B", "zai-org/GLM-5.3-Flash", "deepseek-ai/DeepSeek-V4.1-Flash", "MiniMaxAI/MiniMax-M3.1-Flash",
             "Qwen/Qwen3.8-2.4T-A95B", "moonshotai/Kimi-K3"]
HF_VISION_MODELS = ["Qwen/Qwen3.8-27B"]            # models that also read pictures (for "describe a picture" and "review a result")


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
# CPU-only JAX, and 0.00 h of the 20 h weekly TPU quota used.
TPU_CLI_WORKS = True
TPU_CLI_NOTE = ("Kaggle did not attach a TPU to notebooks started from the command line (tested twice, 0 h of TPU quota used; "
                "TPUs may also just have been busy). Try the notebook in the Kaggle web page, or retest later")


_LOCAL_GPUS = None


def local_gpus():
    """This computer's NVIDIA GPUs [(name, GB, compute capability)], asked once (nvidia-smi); [] if there are none."""
    global _LOCAL_GPUS
    if _LOCAL_GPUS is None:
        _LOCAL_GPUS = run_local_model.gpu_info() if sys.platform.startswith("linux") else []
    return _LOCAL_GPUS


def local_gpu_label():
    g = local_gpus()
    return f"{g[0][0]} ({g[0][1]:g} GB)" + (f" + {len(g) - 1} more" if len(g) > 1 else "") if g else "This computer's NVIDIA GPU (none found)"


def gpu_blocker(service, gpu):
    if service == "computer":
        if not sys.platform.startswith("linux"):
            return ("models run on this computer only on Linux (or Windows through WSL 2) with an NVIDIA GPU; this one is "
                    + ("macOS" if sys.platform == "darwin" else sys.platform) + ". Use Kaggle, Colab or Hugging Face here")
        if not local_gpus():
            return "no NVIDIA GPU found on this computer (nvidia-smi is missing or lists none)"
        return None
    return TPU_CLI_NOTE if gpu.startswith("Tpu") and not TPU_CLI_WORKS else None


def gpu_memory(service, gpu):
    """(GB, Ampere or newer) of the chosen GPU, or (None, None) when it is not known."""
    if service == "computer" and local_gpus():
        name, gb, cap = local_gpus()[0]
        try:
            return gb, float(cap) >= 8.0
        except ValueError:
            return gb, None
    if service == "kaggle" and gpu in KAGGLE_GPU_GB:
        return KAGGLE_GPU_GB[gpu], gpu not in KAGGLE_PRE_AMPERE
    if service == "colab" and gpu in COLAB_GPU_GB:
        return COLAB_GPU_GB[gpu], gpu != "T4"
    return None, None


def suggestions(look, service, gpu):
    """The models the Studio suggests for every step of this look, for this service and GPU (model_advisor.suggest)."""
    if look not in model_advisor.LOOKS:
        raise PlanError("choose a look")
    if service not in GPUS or gpu not in [g for g, _ in GPUS[service]]:
        raise PlanError("choose where to run (Models tab)")
    gpu_why = gpu_blocker(service, gpu)
    out = model_advisor.suggest(look, blocker=lambda m: gpu_why or model_blocker(m, service, gpu), gpu_gb=gpu_memory(service, gpu)[0])
    if service not in ("kaggle", "computer"):            # keyframes are only made (and handed to the video model) by these two runners
        out["keyframe"]["alternatives"] = ([dict(out["keyframe"]["pick"], blocked="")] if out["keyframe"]["pick"] else []) + out["keyframe"]["alternatives"]
        out["keyframe"]["pick"] = None
        out["keyframe"]["note"] = "keyframes are made on Kaggle or this computer: choose one of them in the Models tab to use them"
        for step, what in (("video_i2v", "animating keyframes"), ("upscale", "upscaling")):
            if not out[step]["pick"]:
                out[step]["note"] = f"{what} runs on Kaggle or this computer: choose one of them in the Models tab"
    return {"look": look, "service": service, "gpu": gpu, "gpu_problem": gpu_why or "", "steps": out}


TPU_ONLY = {"tpu_wan", "tpu_mage_flow", "tpu_flux_jax"}      # JAX models that run only on Kaggle's TPU v5e-8
BIG_RAM_MODELS = {"wan22_ti2v_5b", "wan22_t2v_a14b", "wan22_t2v_a14b_lora", "wan22_t2v_a14b_lightning", "hunyuan_video", "hunyuan_video_lora", "hunyuan_video_15", "cogvideox_5b",
                  "sd35_large", "sd35_large_turbo", "flux1_schnell", "flux1_dev", "flux2_klein_4b", "chroma1_hd", "qwen_image_21_lora", "z_image", "ernie_image_turbo", "qwen_image_21_turbo",
                  "qwen_image_21", "qwen_image_21_uc", "moss_image_sft_lora", "moss_image_sft", "moss_image_base"}      # 12-25 GB of weights: more system RAM than Colab's free tier


def model_blocker(name, service, gpu):
    """Why this video/image/audio model cannot run with this service and GPU, or None if it can (it may still be untested)."""
    if service == "huggingface" and name not in I2V_MODELS:
        return None if name in hf_spaces.SPACES else "no public Hugging Face Space is set up for this model (see scripts/hf_spaces.py)"
    if name in UPSCALE_MODELS:
        if service not in ("kaggle", "computer"):
            return "upscales clips you already made, which only the Kaggle and This computer runners hand to the model (use one of them)"
        label, need, least_gb, ampere = UPSCALE_MODELS[name]
        gb, is_ampere = gpu_memory(service, gpu)
        if ampere and is_ampere is False:
            return f"{label} needs an Ampere or newer GPU (RTX 30/40/50, A100, L4); this one is older"
        if gb is not None and gb < least_gb:
            return f"{label} needs at least {least_gb} GB of GPU memory; this GPU has {gb:g} GB"
    if name in I2V_MODELS and service not in ("kaggle", "computer"):
        return "starts from keyframes, which only the Kaggle and This computer runners hand to the model (use one of them)"
    on_tpu = gpu.startswith("Tpu")
    if name in TPU_ONLY:
        if service != "kaggle":
            return "TPU runs are only offered through Kaggle"
        if on_tpu:
            return gpu_blocker(service, gpu)
        return "needs the TPU v5e-8 accelerator"
    if on_tpu:
        return "needs a CUDA GPU, not a TPU"
    if name == "sd35_medium" and service == "computer":
        return None if os.environ.get("HF_TOKEN", "").strip() else "gated model: set HF_TOKEN (a Hugging Face token that has accepted its licence) before starting the Studio"
    if name == "sd35_medium":
        return "gated model: needs a Hugging Face token, which the command-line runs cannot pass (run the notebook on the Kaggle page with your token added as a secret)"
    if name in BIG_RAM_MODELS and service == "colab" and gpu == "T4":
        return "needs more system RAM than Colab's free tier has (use Kaggle)"
    return None


def blockers():
    """{model: {service: {gpu: reason}}} for every combination that cannot work (sent to the page so it can grey them out)."""
    out = {}
    for name in VIDEO_MODELS + IMAGE_MODELS + AUDIO_KINDS + list(UPSCALE_MODELS):
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
            return ["scripts/run_colab_model.sh", model, str(s), str(e), gpu], env
        if service == "huggingface":
            return ["scripts/run_hf_space.sh", model, str(s), str(e)], env
        if service == "computer":
            return ["python3", "scripts/run_local_model.py", model, str(s), str(e)], env
        env.update({"KAGGLE_USER": user, "KAGGLE_ACCELERATOR": gpu})
        return ["scripts/run_kaggle_model.sh", model, str(s), str(e)], env
    return runner


def generation_steps(opt, slug):
    """Video/audio/merge/mix steps for the chosen movies. Needs movies.json, so it may run after the book steps."""
    service = opt.get("service")
    if service not in GPUS:
        raise PlanError("choose where the models run: Kaggle, Colab, Hugging Face or this computer")
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
    if service == "kaggle" and (st.get("video") or st.get("audio") or st.get("keyframes")) and not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", user):
        raise PlanError("enter your Kaggle username (letters, digits, - and _)")
    kmodel = opt.get("keyframe_model") or ""
    if st.get("keyframes") and kmodel not in IMAGE_MODELS:
        raise PlanError("choose the image model that makes the keyframes")
    if kmodel and kmodel not in IMAGE_MODELS:
        raise PlanError("unknown keyframe image model")
    refs = bool(opt.get("keyframe_refs")) and bool(st.get("keyframes"))
    look = str(opt.get("look") or "")
    if look and look not in model_advisor.LOOKS:
        raise PlanError("unknown look")
    if refs and kmodel not in REF_IMAGE_MODELS:
        raise PlanError(f"character pictures steer only {', '.join(sorted(REF_IMAGE_MODELS))} keyframes: pick it, or untick 'Steer keyframes with character pictures'")
    if st.get("keyframes") and service not in ("kaggle", "computer"):
        raise PlanError("keyframes are made on Kaggle or this computer (the Colab and Hugging Face runners do not keep them apart from other images): choose one of those")
    i2v = [m for m in vmodels if m in I2V_MODELS] if st.get("video") else []
    if (st.get("keyframes") or i2v) and chapters_mode:
        raise PlanError("keyframes and the 'from keyframes' video models work per shot: choose 'Every shot'")
    check_models(service, gpu, (vmodels if st.get("video") else []) + (akinds if st.get("audio") else []) + ([kmodel] if st.get("keyframes") else []))
    batch = num(opt, "batch", 0, int, 0, 100000)
    sync = opt.get("sync", "stretch")
    if sync not in ("stretch", "speed", "trim"):
        raise PlanError("bad sync mode")
    vols = {k: num(opt.get("vol", {}), k, d, float, 0, 5) for k, d in (("narration", 1.0), ("sfx", 0.5), ("music", 0.25))}

    plan = read_json(pdir(slug) / "movies.json", {})
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
    if st.get("keyframes"):
        kw, kh = keyframe_size(kmodel, (i2v or vmodels or ["ltx_video"])[0])
        series = opt.get("keyframe_series") or get_character_series(slug)     # the pictures can come from any series (Characters tab)
        if refs and series not in character_tokens.list_series():
            raise PlanError(f"no character series named {series!r}: choose one on the Characters tab")
        steps.append({"label": f"Write keyframes.csv ({kw}x{kh}" + (f", character pictures from '{series}')" if refs else ")"), "env": {},
                      "argv": ["python3", "make_keyframes_csv.py", slug, "--width", str(kw), "--height", str(kh)] + (["--refs", series] if refs else [])
                              + (["--look", look] if look else [])})

    done = set()
    for mv in chosen:
        lo, hi = mv["rows"]
        lo, hi = max(lo, lo_o or lo), min(hi, hi_o or hi)
        for s, e in (chunks(lo, hi, batch) if lo <= hi else []):
            if st.get("keyframes") and ("kf", s, e) not in done:      # stills first, so the video steps after them can animate them
                done.add(("kf", s, e)); argv, env = runner(f"image_{kmodel}", s, e, "keyframes.csv")
                steps.append({"label": f"Movie {mv['id']} keyframes {kmodel}: rows {s}-{e}", "argv": argv, "env": env})
            if st.get("video"):
                for m in vmodels:
                    if (m, s, e) not in done:
                        done.add((m, s, e)); argv, env = runner(m, s, e, vcsv)
                        if m in I2V_MODELS and kmodel:
                            env["KEYFRAME_MODEL"] = kmodel           # else the run script uses the newest keyframe set
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


def keyframe_size(image_model, video_model):
    """Keyframe size: the video's shape at about the image model's usual pixel count, in multiples of 64 (so it suits every image model)."""
    v, i = MODEL_DEFAULTS.get(video_model, MODEL_DEFAULTS["ltx_video"]), MODEL_DEFAULTS.get(image_model, {"width": 1024, "height": 1024})
    ratio, area = v["width"] / v["height"], i["width"] * i["height"]
    w = max(256, min(2048, round((area * ratio) ** 0.5 / 64) * 64))
    h = max(256, min(2048, round(w / ratio / 64) * 64))
    return w, h


def storyboard(slug, start, end):
    """One card per shot row start..end: chapter, prompt, narration, and the keyframes and clips that exist for it (paths under the project)."""
    d = pdir(slug)
    if not SLUG_RE.match(slug) or not d.is_dir():
        raise PlanError("pick a book first")
    shots = read_csv_rows(d / "all_shots.csv")
    if not shots:
        raise PlanError("no shots yet: build the CSVs first")
    audio = read_csv_rows(d / "audio_shots.csv")
    start = max(1, start); end = min(len(shots), end, start + 199)         # at most 200 cards at once
    kdirs = sorted(p for p in (d / "images").glob("*_keyframes") if p.is_dir()) if (d / "images").is_dir() else []
    vdirs = sorted(p for p in (d / "videos").glob("*") if p.is_dir() and not p.name.endswith("_chapters")) if (d / "videos").is_dir() else []
    cards = []
    for n in range(start, end + 1):
        r, a = shots[n - 1], (audio[n - 1] if n <= len(audio) else {})
        cards.append({"n": n, "chapter": r.get("chapter", ""), "shot": r.get("shot", ""), "prompt": r.get("prompt", ""),
                      "characters": [c for c in (r.get("characters") or "").split("|") if c],
                      "narration": a.get("narration", ""),
                      "keyframes": {k.name.removesuffix("_keyframes"): f"images/{k.name}/image-{n:04d}.png" for k in kdirs if (k / f"image-{n:04d}.png").is_file()},
                      "clips": {v.name: f"videos/{v.name}/shot-{n:04d}.mp4" for v in vdirs if (v / f"shot-{n:04d}.mp4").is_file()},
                      "takes": {**{f"clip:{v.name}": take_files(v, "shot", n, ".mp4", d) for v in vdirs},
                                **{f"keyframe:{k.name.removesuffix('_keyframes')}": take_files(k, "image", n, ".png", d) for k in kdirs}}})
    for c in cards:
        c["takes"] = {k: v for k, v in c["takes"].items() if v}
    return {"rows": len(shots), "start": start, "end": end, "cards": cards,
            "keyframe_models": [k.name.removesuffix("_keyframes") for k in kdirs]}


TAKE_KINDS = {"clip": ("videos", "shot", ".mp4"), "keyframe": ("images", "image", ".png")}


def take_files(folder, stem, n, ext, root):
    """Saved earlier versions (takes) of one shot, oldest first, as paths under the project: <folder>/takes/<stem>-NNNN-tK<ext>."""
    t = folder / "takes"
    if not t.is_dir():
        return []
    found = sorted(t.glob(f"{stem}-{n:04d}-t*{ext}"), key=lambda p: int(p.stem.rsplit("-t", 1)[1] or 0) if p.stem.rsplit("-t", 1)[1].isdigit() else 0)
    return [p.relative_to(root).as_posix() for p in found]


def take_target(body):
    """(project dir, output folder, stem, extension, shot number) for a retake or pick request, with every part validated."""
    slug, kind, model, n = body.get("project", ""), body.get("kind", ""), body.get("model", ""), body.get("n")
    d = pdir(slug)
    if not SLUG_RE.match(slug or "") or not d.is_dir():
        raise PlanError("pick a book first")
    if kind not in TAKE_KINDS:
        raise PlanError("kind must be clip or keyframe")
    if not re.fullmatch(r"[a-z0-9_]{2,60}", model or ""):
        raise PlanError("bad model name")
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 100000:
        raise PlanError("bad shot number")
    top, stem, ext = TAKE_KINDS[kind]
    folder = d / top / (model + "_keyframes" if kind == "keyframe" else model)
    if not folder.is_dir():
        raise PlanError(f"no {kind}s from {model} yet")
    return d, folder, stem, ext, n


def next_take_number(folder, stem, n, ext):
    nums = [int(p.stem.rsplit("-t", 1)[1]) for p in (folder / "takes").glob(f"{stem}-{n:04d}-t*{ext}") if p.stem.rsplit("-t", 1)[1].isdigit()] if (folder / "takes").is_dir() else []
    return max(nums, default=0) + 1


def set_shot_seed(d, n, seed):
    """Write a seed into all_shots.csv for shot n (adds a seed column if the CSV has none), so the next run of that shot differs."""
    path = d / "all_shots.csv"
    rows = read_csv_rows(path)
    if not 1 <= n <= len(rows):
        raise PlanError(f"shot {n} is not in all_shots.csv")
    fields = list(rows[0].keys())
    if "seed" not in fields:
        fields.append("seed")
    for r in rows:
        r.setdefault("seed", "")
    rows[n - 1]["seed"] = str(seed)
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def retake(body):
    """Keep the current version of a shot as a take, clear the slot and give the shot a new seed: running that shot again makes a new version."""
    d, folder, stem, ext, n = take_target(body)
    cur = folder / f"{stem}-{n:04d}{ext}"
    if not cur.is_file():
        raise PlanError("that shot has nothing to retake yet")
    k = next_take_number(folder, stem, n, ext)
    (folder / "takes").mkdir(exist_ok=True)
    os.replace(cur, folder / "takes" / f"{stem}-{n:04d}-t{k}{ext}")
    seed = n + 1000 * k                                   # differs from the first run (seed = shot number) and from every earlier take
    set_shot_seed(d, n, seed)
    return {"saved_as": k, "seed": seed, "next": f"run shot {n} again (rows {n} to {n}) to make a new version"}


def pick_take(body):
    """Make a saved take the current version; the version it replaces is kept as a new take."""
    d, folder, stem, ext, n = take_target(body)
    k = body.get("take")
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise PlanError("bad take number")
    src = folder / "takes" / f"{stem}-{n:04d}-t{k}{ext}"
    if not src.is_file():
        raise PlanError(f"take {k} does not exist")
    cur = folder / f"{stem}-{n:04d}{ext}"
    if cur.is_file():
        os.replace(cur, folder / "takes" / f"{stem}-{n:04d}-t{next_take_number(folder, stem, n, ext)}{ext}")
    os.replace(src, cur)
    return {"current_from_take": k}


CD_SYSTEM = ("You are a film director's creative partner helping to set the look, tone, sound and pacing of a film adapted from a book. "
             "You reply with a single JSON object and nothing else.")


def _direction_book(slug):
    if not SLUG_RE.match(slug or "") or slug in LEGACY:
        raise PlanError("pick a book made from a PDF or text")
    d = pdir(slug)
    if not d.is_dir():
        raise PlanError("pick a book first")
    return d


def creative_direction_get(opt):
    """The saved direction conversation of a book and the direction the writing steps use (continuity book field creative_direction)."""
    d = _direction_book(str(opt.get("project", "")))
    conv = read_json(d / "creative_direction.json", {})
    msgs = conv.get("messages") if isinstance(conv, dict) else None
    return {"messages": msgs if isinstance(msgs, list) else [], "direction": (read_json(continuity_file(d), {}) or {}).get("creative_direction", "")}


def creative_direction(opt):
    """One turn of the direction chat. The AI answers and, when the director is happy, also returns the finished direction; that text is
    saved in the continuity book as creative_direction, which book_write.py passes to every chapter it writes."""
    d = _direction_book(str(opt.get("project", "")))
    msgs = opt.get("messages")
    if not isinstance(msgs, list) or not msgs or len(msgs) > 60:
        raise PlanError("write something first")
    clean = []
    for m in msgs:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant") or not isinstance(m.get("content"), str):
            raise PlanError("bad conversation")
        clean.append({"role": m["role"], "content": m["content"][:4000], **({"finalized": True} if m.get("finalized") else {})})
    if clean[-1]["role"] != "user" or not clean[-1]["content"].strip():
        raise PlanError("write something first")
    book = read_json(continuity_file(d), {}) or {}
    chars = "; ".join(f"{c.get('name')}: {c.get('token')}" for c in book.get("characters", []))[:1500]
    transcript = "\n\n".join(f"{'DIRECTOR' if m['role'] == 'user' else 'YOU'}: {m['content']}" for m in clean)
    prompt = (f"Book: {d.name}.\n" + (f"Characters: {chars}\n" if chars else "") + (f"Current direction: {book['creative_direction']}\n" if book.get("creative_direction") else "")
              + f"\nTHE CONVERSATION SO FAR:\n{transcript}\n\n"
              "Reply to the director's last message in a few sentences: react, suggest concrete choices (camera, light, colour, sound, pacing), ask at most one question. "
              "If they have given enough to write a complete direction, also fill \"direction\" with the finished direction, a paragraph of at most 120 words "
              "that a screenwriter and a prompt writer can follow; otherwise leave it as an empty string.\n"
              'Reply with one JSON object: {"reply": "...", "direction": "..."}')

    def check(data):
        if not isinstance(data.get("reply"), str) or not data["reply"].strip() or not isinstance(data.get("direction", ""), str):
            raise ValueError("'reply' must be text and 'direction' text or empty")
        if len(data["direction"]) > 1200:
            raise ValueError("'direction' must be at most 120 words")

    args = engine_args(opt)
    data = llm_json(prompt, CD_SYSTEM, model=(args[3] if len(args) > 3 else None), engine=args[1], validate=check)
    direction = data.get("direction", "").strip()
    clean.append({"role": "assistant", "content": data["reply"].strip() + (f"\n\nDIRECTION:\n{direction}" if direction else ""),
                  **({"finalized": True} if direction else {})})
    write_json(d / "creative_direction.json", {"messages": clean})
    if direction:
        book["creative_direction"] = direction
        if continuity_file(d).exists():          # only a book that already has its continuity book; never invent one here
            write_json(continuity_file(d), book)
    return {"messages": clean, "status": "direction saved: the writing steps will use it" if direction and continuity_file(d).exists()
            else ("direction ready; read the book first so it can be saved" if direction else "")}


def _write_rows(path, rows):
    fields = list(rows[0].keys())
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def voice_cast(opt):
    """The voice cast of a book: every speaker in audio_shots.csv with its line count and the voice its lines use now.
    With "cast" ({speaker: Kokoro voice id, or "" to leave that speaker's lines as they are}) the cast is saved to voice_cast.json and applied to the
    audio CSVs; a character's voice overrides the narrator's for that character's lines. "move_old": the Kokoro narration files of the rows
    whose voice changed go to the Trash, so the next narration run remakes them. "series": suggest each speaker's voice from that
    character series (the Characters tab)."""
    d = _direction_book(str(opt.get("project", "")))
    if not (d / "audio_shots.csv").exists():
        raise PlanError("build the CSVs first (Book Processing)")
    result = {"changed": [], "moved": 0}
    if opt.get("cast") is not None:
        cast = opt["cast"]
        if not isinstance(cast, dict) or len(cast) > 200:
            raise PlanError("cast must be {speaker: voice}")
        clean = {}
        for k, v in cast.items():
            k, v = str(k).strip()[:60], str(v or "").strip()
            if not k:
                continue
            if v and not KOKORO_VOICE_RE.match(v):
                raise PlanError(f"{v!r} is not a Kokoro voice (for example bm_george or af_bella)")
            if v:
                clean[k] = v
        write_json(d / VOICE_CAST_FILE, {"cast": clean})
        result["changed"] = apply_voice_cast(d, clean)
        if opt.get("move_old") and result["changed"]:
            rel = layout.rel(d.name)
            old = [f"{rel}/audio/kokoro/narration-{n:04d}.wav" for n in result["changed"] if (d / "audio" / "kokoro" / f"narration-{n:04d}.wav").exists()]
            result["moved"] = move_to_trash(old, "pistachio-old-voice")["moved"] if old else 0
    series = str(opt.get("series") or "")
    if series and not SLUG_RE.match(series):
        raise PlanError("bad series name")
    cast = read_voice_cast(d)
    cast_lc = {k.lower(): v for k, v in cast.items()}
    book_voice = {str(c.get("name", "")).lower(): voice_id(c.get("voice")) for c in (read_json(continuity_file(d), {}) or {}).get("characters", []) or []
                  if isinstance(c, dict)}
    speakers = {}
    for r in read_csv_rows(d / "audio_shots.csv"):
        try:
            lines = json.loads(r.get("lines_json") or "[]")
        except ValueError:
            continue
        for ln in lines if isinstance(lines, list) else []:
            if not (isinstance(ln, list) and len(ln) >= 2):
                continue
            name = str(ln[0]).strip() or "NARRATOR"
            sp = speakers.setdefault(name.lower(), {"name": name, "lines": 0, "voices": {}})
            sp["lines"] += 1
            v = str(ln[2]) if len(ln) > 2 else ""
            sp["voices"][v] = sp["voices"].get(v, 0) + 1
    out = []
    for key, sp in speakers.items():
        now = max(sp["voices"], key=sp["voices"].get) if sp["voices"] else ""
        suggest = ""
        if series:
            try:
                ch = character_tokens.load_character(series, sp["name"]) if character_tokens.get_character_path(series, sp["name"]).exists() else None
            except Exception:
                ch = None
            suggest = voice_id((ch or {}).get("voice"))
        out.append({"name": sp["name"], "lines": sp["lines"], "voice": now, "cast": cast_lc.get(key, ""),
                    "book": book_voice.get(key, ""), "suggest": suggest})
    out.sort(key=lambda x: (x["name"].upper() != "NARRATOR", -x["lines"], x["name"].lower()))
    result.update({"speakers": out, "voices": KOKORO_VOICES})
    return result


def new_scene(opt):
    """A new shot written by the AI before or after the chapter's shots. preview_only returns the text; applying inserts one row into
    all_shots.csv (and audio_shots.csv) and renumbers the chapter's shots. Applying is refused once clips, pictures or audio exist,
    because every later row would shift and the files would no longer match their shots."""
    slug = str(opt.get("project", ""))
    d, shots, audio = _scene_tables(slug)
    desc = " ".join(str(opt.get("description") or "").split())
    if not desc or len(desc) > 1500:
        raise PlanError("describe the new scene (up to 1500 characters)")
    ch = str(opt.get("chapter", ""))
    if not ch.isdigit():
        raise PlanError("choose a chapter")
    chapter = f"{slug}-{int(ch)}"
    pos = opt.get("position", "after")
    if pos not in ("before", "after"):
        raise PlanError("position must be before or after")
    idxs = [i for i, r in enumerate(shots) if r["chapter"] == chapter]
    if not idxs:
        raise PlanError(f"chapter {ch} has no shots")
    series = str(opt.get("series") or "")
    chars = ""
    if series:
        if series not in character_tokens.list_series():
            raise PlanError("unknown character series")
        chars = character_tokens.get_all_character_tokens(series)[:1800]
    near = shots[idxs[0]] if pos == "before" else shots[idxs[-1]]
    prompt = (f"A director wants to add ONE new shot {pos} the shot below, in a film adapted from a book.\n\nTHE NEIGHBOURING SHOT: {near['prompt'][:600]}\n"
              + (f"\nCHARACTERS (keep their descriptions unchanged): {chars}\n" if chars else "")
              + f"\nWHAT THE NEW SHOT SHOULD SHOW: {desc}\n\n"
              "Write a text-to-video prompt for one continuous shot of about 4 seconds (shot size, camera movement, subject, action, setting, light; no on-screen text) "
              "at most 900 characters, and one line of narration of at most 14 words.\n"
              'Reply with one JSON object: {"prompt": "...", "narration": "..."}')

    def check(data):
        if not all(isinstance(data.get(k), str) and 10 < len(data[k].strip()) <= 1000 for k in ("prompt", "narration")):
            raise ValueError("'prompt' and 'narration' must be text")

    if opt.get("preview_only"):
        args = engine_args(opt)
        data = llm_json(prompt, "You are a film director and prompt writer. You reply with a single JSON object and nothing else.",
                        model=(args[3] if len(args) > 3 else None), engine=args[1], validate=check)
        return {"preview": f"PROMPT: {data['prompt'].strip()}\nNARRATION: {data['narration'].strip()}", "prompt": data["prompt"].strip(), "narration": data["narration"].strip(),
                "feedback": "Preview ready. Click Apply & Insert to add it."}
    for top in ("videos", "audio", "images"):
        if (d / top).is_dir() and any(f.is_file() for f in (d / top).rglob("*") if f.suffix in (".mp4", ".wav", ".png")):
            raise PlanError("this book already has clips, pictures or audio: a new shot would shift their numbers. Add it before generating, or retake shots instead")
    text, narr = str(opt.get("prompt") or "").strip(), str(opt.get("narration") or "").strip()
    if not text or len(text) > 1000 or len(narr) > 1000:
        raise PlanError("preview the scene first")
    at = idxs[0] if pos == "before" else idxs[-1] + 1
    row = {k: "" for k in shots[0]}
    row.update(chapter=chapter, prompt=text)
    shots.insert(at, row)
    for n, i in enumerate((i for i, r in enumerate(shots) if r["chapter"] == chapter), 1):
        shots[i]["shot"] = str(n)
    _write_rows(d / "all_shots.csv", shots)
    if audio:
        arow = {k: "" for k in audio[0]}
        arow.update(chapter=chapter, narration=narr)
        a_at = next((i for i, r in enumerate(audio) if r["chapter"] == chapter), len(audio)) if pos == "before" else \
            (max((i for i, r in enumerate(audio) if r["chapter"] == chapter), default=len(audio) - 1) + 1)
        audio.insert(a_at, arow)
        for n, i in enumerate((i for i, r in enumerate(audio) if r["chapter"] == chapter), 1):
            audio[i]["shot"] = str(n)
        _write_rows(d / "audio_shots.csv", audio)
    return {"scene": f"Inserted as shot {shots[at]['shot']} of chapter {ch}"}


def animatic_step(body):
    """Step that makes films/animatic_<start>-<end>.mp4 from the keyframes (and narration, if made) of rows start..end."""
    slug = str(body.get("project", ""))
    if not SLUG_RE.match(slug) or not pdir(slug).is_dir():
        raise PlanError("pick a book first")
    start, end = num(body, "start", 1, int, 1, 100000), num(body, "end", 24, int, 1, 100000)
    if end < start:
        raise PlanError("end is before start")
    end = min(end, start + 199)
    argv = ["uv", "run", "--with", "imageio-ffmpeg", "python", "make_animatic.py", "--project", slug, "--start", str(start), "--end", str(end),
            "--out", f"animatic_{start}-{end}.mp4"]
    kf = str(body.get("keyframes") or "")
    if kf:
        if not re.fullmatch(r"[a-z0-9_]{2,60}", kf):
            raise PlanError("bad keyframe model name")
        argv += ["--keyframes", kf]
    return {"label": f"Make animatic for rows {start}-{end}", "argv": argv, "env": {}}


def upscale_step(body):
    """Step that upscales the clips of one video folder, rows start..end, with one of UPSCALE_MODELS on Kaggle or this computer: the result
    is videos/<source>_<model> (for example ltx_video_i2v_x2), which Make Film then offers as a video source."""
    slug = str(body.get("project", ""))
    if not SLUG_RE.match(slug) or not pdir(slug).is_dir():
        raise PlanError("pick a book or prompt set first")
    model = str(body.get("model") or "upscale_x2")
    if model not in UPSCALE_MODELS:
        raise PlanError("choose an upscaler")
    inv = media_inventory(slug)
    key = str(body.get("source") or "")                       # as Make Film names it: videos/<folder>
    src = key.split("/", 1)[1] if key.startswith("videos/") else ""
    if key not in inv["videos"] or not re.fullmatch(r"[a-z0-9_]{2,60}", src):
        raise PlanError("choose the video folder to upscale")
    if src.endswith(UPSCALE_SUFFIXES):
        raise PlanError("these clips are already upscaled")
    start, end = num(body, "start", 1, int, 1, 100000), num(body, "end", 1, int, 1, 100000)
    if end < start:
        raise PlanError("end is before start")
    have = set(inv["videos"][key])
    missing = [n for n in range(start, end + 1) if n not in have]
    if missing:
        raise PlanError(f"no clip in {src} for row(s) {', '.join(map(str, missing[:10]))}{' ...' if len(missing) > 10 else ''}")
    service = body.get("service") or "kaggle"
    if service not in ("kaggle", "computer"):
        raise PlanError("upscaling runs on Kaggle or this computer: choose one of them in the Models tab")
    gpu = body.get("gpu") or ("local" if service == "computer" else "NvidiaTeslaT4")
    if gpu not in [g for g, _ in GPUS[service]] or gpu.startswith("Tpu"):
        raise PlanError("choose a GPU in the Models tab")
    why = gpu_blocker(service, gpu) or model_blocker(model, service, gpu)
    if why:
        raise PlanError(why)
    label = UPSCALE_MODELS[model][0]
    env = {"PROJECT": slug, "SHOTS_CSV": "all_shots.csv", "UPSCALE_SOURCE": src}
    if service == "computer":
        return {"label": f"Upscale {src} rows {start}-{end} 2x with {label} on this computer", "env": env,
                "argv": ["python3", "scripts/run_local_model.py", model, str(start), str(end)]}
    user = (body.get("kaggle_user") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", user):
        raise PlanError("enter your Kaggle username (letters, digits, - and _), Models tab")
    env.update({"KAGGLE_USER": user, "KAGGLE_ACCELERATOR": gpu})
    return {"label": f"Upscale {src} rows {start}-{end} 2x with {label} on Kaggle", "argv": ["scripts/run_kaggle_model.sh", model, str(start), str(end)], "env": env}


def build_plan(opt, commit=False):
    if opt.get("mode") == "prompts":
        return prompt_plan(opt, commit)
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
    d = pdir(slug, "prompts")
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
        elif model in ("wan", "wan22_t2v_a14b", "wan22_t2v_a14b_lora", "wan22_t2v_a14b_lightning"):
            w = snap(w, 16, 256, 1280) if w else None; h = snap(h, 16, 256, 1280) if h else None
            frames = snap(frames - 1, 4, 4, 120) + 1 if frames else None          # 4*k+1
        elif model == "wan22_ti2v_5b":
            w = snap(w, 32, 256, 1280) if w else None; h = snap(h, 32, 256, 1280) if h else None
            frames = snap(frames - 1, 4, 4, 120) + 1 if frames else None
        elif model in ("hunyuan_video", "hunyuan_video_lora"):
            w = snap(w, 16, 256, 1280) if w else None; h = snap(h, 16, 256, 1280) if h else None
            frames = snap(frames - 1, 4, 4, 128) + 1 if frames else None
            negative = ""                                                           # HunyuanVideo has no negative prompt
        else:                                                                       # cogvideox (2B and 5B): fixed size and length
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


WAN_HEADS = {"wan": 12, "wan22_ti2v_5b": 24, "wan22_t2v_a14b": 40, "wan22_t2v_a14b_lora": 40, "wan22_t2v_a14b_lightning": 40, "hunyuan_video": 24, "hunyuan_video_lora": 24}      # attention heads per model
WAN_ATTN_CAP_GIB = {"wan": 2.5, "wan22_ti2v_5b": 2.5, "wan22_t2v_a14b": 1.8, "wan22_t2v_a14b_lora": 1.8, "wan22_t2v_a14b_lightning": 1.8, "hunyuan_video": 2.5, "hunyuan_video_lora": 2.5}   # what is left on a 14.5 GiB T4 next to the weights


def wan_t4_check(gpu, w, h, frames, model="wan"):
    """Wan on a T4 runs plain attention in fp32: one matrix is 4 x heads x tokens^2 bytes (the 14B model has 40 heads: 512x288x33 asked for 4.01 GiB
    with 2.2 GiB free and crashed). Refuse sizes that cannot fit."""
    if "T4" not in gpu:
        return
    d = MODEL_DEFAULTS[model]
    w, h, frames = w or d["width"], h or d["height"], frames or d["frames"]
    div = 32 if model == "wan22_ti2v_5b" else 16                  # the 5B model's VAE is 2x more compact per side
    per_token2 = 4 * WAN_HEADS[model]
    tokens = ((frames - 1) // 4 + 1) * (h // div) * (w // div)
    need = per_token2 * tokens * tokens / 2**30
    cap = WAN_ATTN_CAP_GIB[model]
    if need > cap:
        limit = int((cap * 2**30 / per_token2) ** 0.5)
        raise PlanError(f"{model} at {w}x{h} with {frames} frames needs about {need:.1f} GiB for one attention matrix on a T4 (only about {cap:.1f} GiB is free next to the model); "
                        f"keep ((frames-1)//4+1) x (height/{div}) x (width/{div}) under about {limit:,} (now {tokens:,}), for example "
                        f"{'448x256 with 25 frames' if WAN_HEADS[model] == 40 else '480x272 with 33 frames' if model.startswith('hunyuan') else '512x288 with 33 frames'}, or use an L4/A100")


# Image models whose attention matrix can overflow a T4: (heads, images per pass, GiB free next to the weights, text tokens). The T4 runs plain fp32 attention:
# one matrix is 4 x heads x batch x tokens^2 bytes (SD 3.5 Large at 1024x1024 with guidance asked for 5.55 GiB and crashed).
IMAGE_ATTN = {"sd35_large": (38, 2, 3.0, 333), "sd35_large_turbo": (38, 1, 3.0, 333)}


def image_t4_check(gpu, w, h, model):
    if "T4" not in gpu or model not in IMAGE_ATTN:
        return
    d = MODEL_DEFAULTS[model]
    w, h = w or d["width"], h or d["height"]
    heads, batch, cap, text = IMAGE_ATTN[model]
    tokens = (w // 16) * (h // 16) + text
    need = 4 * heads * batch * tokens * tokens / 2**30
    if need > cap:
        limit = int((cap * 2**30 / (4 * heads * batch)) ** 0.5) - text
        side = int((limit ** 0.5) * 16)
        raise PlanError(f"{model} at {w}x{h} needs about {need:.1f} GiB for one attention matrix on a T4 (only about {cap:.1f} GiB is free next to the model); "
                        f"keep it to about {side}x{side} or smaller, or use an L4/A100")


def prompt_plan(opt, commit):
    slug = prompt_set_slug(opt, True)
    kind = opt.get("kind")
    if kind not in ("video", "image"):
        raise PlanError("choose video or image")
    model = opt.get("model")
    if model not in (VIDEO_MODELS if kind == "video" else IMAGE_MODELS):
        raise PlanError("unknown model for that kind")
    if model in I2V_MODELS:
        raise PlanError(f"{model} animates a book's keyframes; for single prompts use {model.removesuffix('_i2v')}")
    service = opt.get("service")
    if service not in GPUS:
        raise PlanError("choose where the models run: Kaggle, Colab, Hugging Face or this computer")
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
    d = pdir(slug, "prompts")
    csv_name, cols = ("all_shots.csv", VIDEO_COLS) if kind == "video" else ("all_images.csv", IMAGE_COLS)

    # Check if we should overwrite the CSV (for single image generation)
    overwrite = opt.get("opts", {}).get("overwrite", False)
    if overwrite and (d / csv_name).exists():
        (d / csv_name).unlink()

    first = len(read_csv_rows(d / csv_name)) + 1
    rows = prompt_rows(opt, slug, kind, model, first)
    look = str(opt.get("look") or "")
    if look:
        if look not in model_advisor.LOOKS:
            raise PlanError("unknown look")
        takes_neg = "negative" not in (MODEL_DEFAULTS.get(model, {}).get("locked") or []) and model not in ("hunyuan_video", "hunyuan_video_lora", "tpu_mage_flow", "tpu_flux_jax")
        for r in rows:
            r["prompt"], r["negative"] = model_advisor.apply_look(r["prompt"], r["negative"], look, takes_neg)
            r["prompt"] = r["prompt"][:2000]; r["negative"] = r["negative"][:700]
    gname = local_gpu_label() if service == "computer" else gpu      # the T4 limits below also apply to a T4 in this computer
    if model in WAN_HEADS:
        for r in rows:
            wan_t4_check(gname, int(r["width"] or 0), int(r["height"] or 0), int(r.get("frames") or 0), model)
    if kind == "image" and model in IMAGE_ATTN:
        for r in rows:
            image_t4_check(gname, int(r["width"] or 0), int(r["height"] or 0), model)
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

    # Load global parameters for the project
    project = opt.get("project", "")
    global_positives = ""
    global_negatives = ""
    if project:
        global_params = load_global_params(project)
        global_positives = global_params.get("positives", "")
        global_negatives = global_params.get("negatives", "")

    target = str(opt.get("target") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,60}", target):
        target = ""
    _, words = prompt_guides.guide_for(kind, target)
    what = (f"a text-to-video model. Each prompt is one 4-6 second clip, {words}.") if kind == "video" else (
            f"a text-to-image model. Each prompt is one picture, {words}.")

    global_section = ""
    if global_positives or global_negatives:
        global_section = "\nGLOBAL PROMPT PARAMETERS (apply to ALL prompts):\n"
        if global_positives:
            global_section += f"  Always include: {global_positives}\n"
        if global_negatives:
            global_section += f"  Always avoid: {global_negatives}\n"

    prompt = (f'Idea: "{idea}"\n{global_section}\n\nWrite {count} different, vivid prompts for {what} No on-screen text, no logos, nothing '
              f'that depends on previous prompts. Reply with one JSON object: {{"prompts": ["...", ...]}} with exactly {count} strings.')

    def check(d):
        ps = d.get("prompts")
        if not isinstance(ps, list) or len(ps) != count or not all(isinstance(x, str) and len(x) > 20 for x in ps):
            raise ValueError(f"'prompts' must be a list of exactly {count} strings")

    data = llm_json(prompt, prompt_guides.writer_system(kind, target), model=model, engine=engine, validate=check)

    # Append global parameters to each generated prompt
    prompts = [x.strip() for x in data["prompts"]]
    if global_positives or global_negatives:
        final_prompts = []
        for p in prompts:
            parts = [p]
            if global_positives:
                parts.append(global_positives)
            # Add the standard negative tail
            neg_tail = "photorealistic epic period film, cinematic natural lighting, realistic faces and anatomy, no text, no subtitles, no logos, no watermark, no cartoon style"
            if global_negatives:
                neg_tail = f"{global_negatives}, {neg_tail}"
            parts.append(neg_tail)
            final_prompts.append(", ".join(parts))
        return final_prompts
    return prompts


_LOCAL_CACHE = {"at": 0.0, "value": None}


def local_llm_status(force=False):
    """Can this computer run the prompt writer on a local language model? {"ready", "reason", "url", "models"}. The checkbox in the Studio is greyed out
    (with this reason) until the computer qualifies: Apple Silicon or an NVIDIA GPU, 16 GB of memory or more, and a model server answering on
    LOCAL_LLM_URL (Ollama, LM Studio or llama.cpp). STUDIO_LOCAL_LLM=1 in the environment skips the hardware checks. Cached for 30 seconds."""
    if not force and _LOCAL_CACHE["value"] is not None and time.time() - _LOCAL_CACHE["at"] < 30:
        return _LOCAL_CACHE["value"]
    import platform
    reasons, models = [], []
    try:
        if platform.system() == "Darwin":
            gb = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=3).stdout.strip() or 0) / 2**30
        else:
            gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    except (OSError, ValueError, subprocess.SubprocessError):
        gb = 0
    if os.environ.get("STUDIO_LOCAL_LLM") != "1":
        if gb and gb < 16:
            reasons.append(f"this computer has {gb:.0f} GB of memory and a useful language model needs 16 GB or more")
        if platform.system() == "Darwin" and platform.machine() != "arm64":
            reasons.append("this is an Intel Mac; local models need Apple Silicon (M-series)")
        elif platform.system() != "Darwin" and not shutil.which("nvidia-smi"):
            reasons.append("no NVIDIA GPU was found")
    if not reasons:                                           # only look for a model server on a computer that could use one
        try:
            import urllib.request
            with urllib.request.urlopen(LOCAL_LLM_URL.rsplit("/chat/completions", 1)[0] + "/models", timeout=1.5) as r:
                models = [m.get("id") for m in json.loads(r.read()).get("data", []) if m.get("id")]
            if not models:
                reasons.append("the local model server has no models yet (for Ollama: ollama pull <model>)")
        except Exception:
            reasons.append(f"no local model server answered at {LOCAL_LLM_URL.rsplit('/chat/completions', 1)[0]} (install Ollama or LM Studio and start it)")
    value = {"ready": not reasons, "reason": "; ".join(reasons), "url": LOCAL_LLM_URL, "models": models, "memory_gb": round(gb)}
    _LOCAL_CACHE.update(at=time.time(), value=value)
    return value


def result_file(file):
    """Resolve "<project>/<path under it>" (as the Compare tab names a result) to a real picture or clip inside projects/<project>/."""
    parts = str(file or "").split("/", 1)
    if len(parts) != 2 or not SLUG_RE.match(parts[0]):
        raise PlanError("bad file name")
    base = pdir(parts[0]).resolve()
    target = (base / parts[1]).resolve()
    if base not in target.parents or target.suffix.lower() not in (".png", ".jpg", ".mp4") or not target.is_file():
        raise PlanError("that file was not found")
    return target


def image_data_url(path, px=1024):
    """The picture (or one frame of a clip) as a small JPEG data URL, to send to a vision model."""
    import base64
    im = load_rgb(path)
    im.thumbnail((px, px))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def vision_model(opt):
    model = str(opt.get("claude_model") or "").strip()
    if model and not MODEL_RE.match(model):
        raise PlanError("model name may only use letters, digits and . _ : / [ ] -")
    if (opt.get("engine") or "claude") == "hf":
        return model or HF_VISION_MODELS[0]
    return model                                              # claude / codex: blank = the tool's own default; local: the local server decides


def vision_json(opt, system, text, check):
    """Show one result picture (or a frame of a clip) to a model and get a JSON reply. Engines: claude / fcc-claude (the Read tool on a private copy),
    codex / fcc-codex (-i), hf (Hugging Face vision model) and local (a vision model on this computer's model server)."""
    engine = opt.get("engine") or "claude"
    if engine not in ENGINES:
        raise PlanError("unknown engine")
    path, model = result_file(opt.get("file")), vision_model(opt)
    if engine in ("hf", "local"):
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": image_data_url(path)}}]}]
        return hf_json(messages, model, check, chat=local_chat if engine == "local" else None)
    import tempfile
    fd, jpeg = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    try:
        im = load_rgb(path)
        im.thumbnail((1024, 1024))
        im.save(jpeg, "JPEG", quality=85)
        return llm_json(text, system, model or None, engine, check, image=jpeg)
    finally:
        Path(jpeg).unlink(missing_ok=True)


def describe_image(opt):
    """Look at a picture and write a prompt for it: kind "video" = a prompt that brings it to life (image-to-video), "image" = a prompt that recreates it."""
    kind = opt.get("kind") if opt.get("kind") in ("video", "image") else "video"
    target = str(opt.get("target") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,60}", target):
        target = ""
    rules, words = prompt_guides.guide_for(kind, target)
    extra = str(opt.get("note") or "").strip()[:400]
    task = ("Write ONE prompt for an image-to-video model that brings this exact picture to life: keep the subject, setting and look you can see, "
            f"then add natural motion and a camera move. {words}.") if kind == "video" else (
            f"Write ONE prompt for a text-to-image model that would recreate this picture closely. {words}.")
    text = f"{task}\n\nRules: {rules}" + (f"\n\nAlso follow this instruction from the user: {extra}" if extra else "") + '\n\nReply with {"prompt": "..."}'

    def check(d):
        if not isinstance(d.get("prompt"), str) or len(d["prompt"]) < 20:
            raise ValueError("'prompt' must be a string of at least 20 characters")
    return {"prompt": vision_json(opt, prompt_guides.writer_system(kind, target), text, check)["prompt"].strip()}


def review_result(opt):
    """Compare a result with the prompt that made it: a score from 1 to 10, a one-line summary and up to three problems."""
    prompt = " ".join(str(opt.get("prompt") or "").split())[:1500]
    if not prompt:
        raise PlanError("no prompt to compare with")
    text = (f'This picture (or frame of a clip) was made from this prompt:\n"{prompt}"\n\nJudge how well it matches the prompt and how good it looks: '
            "anatomy and faces, hands, objects, text artefacts, blur, composition, lighting. Score 1-10 (10 = excellent, 5 = usable but flawed, 1 = unusable). "
            'Reply with {"score": 7, "summary": "one sentence", "problems": ["up to three short items; empty if none"]}')

    def check(d):
        sc = d.get("score")
        if isinstance(sc, str) and sc.strip().isdigit():
            d["score"] = sc = int(sc)
        if not isinstance(sc, (int, float)) or not 1 <= sc <= 10 or not isinstance(d.get("summary"), str):
            raise ValueError("need a numeric 'score' from 1 to 10 and a 'summary' string")
        d["problems"] = [str(x)[:160] for x in (d.get("problems") or [])][:3] if isinstance(d.get("problems"), list) else []
    d = vision_json(opt, prompt_guides.review_system(), text, check)
    return {"score": round(float(d["score"])), "summary": d["summary"].strip(), "problems": d["problems"]}


def clip_prompt(slug, row):
    """Get the original prompt for a specific clip/row in a project."""
    if not SLUG_RE.match(slug):
        raise PlanError("bad project name")
    d = pdir(slug)
    if not d.is_dir():
        raise PlanError("project not found")

    # Try to find the prompt from all_shots.csv or all_chapters.csv
    for csv_name in ("all_shots.csv", "all_chapters.csv", "all_images.csv"):
        rows = read_csv_rows(d / csv_name)
        if 0 < row <= len(rows):
            return {"prompt": rows[row - 1].get("prompt", "")}
    return {"prompt": ""}


def enhance_prompt(opt):
    """Enhance a prompt based on user instruction."""
    project = opt.get("project", "")
    row = opt.get("row", 0)
    original_prompt = opt.get("original_prompt", "")
    instruction = opt.get("instruction", "").strip()
    preview_only = opt.get("preview_only", False)

    if not SLUG_RE.match(project):
        raise PlanError("bad project name")
    if not original_prompt:
        raise PlanError("no original prompt provided")
    if not instruction:
        raise PlanError("no enhancement instruction provided")

    d = pdir(project)
    if not d.is_dir():
        raise PlanError("project not found")

    # Load global parameters for the project
    global_params = load_global_params(project)
    global_positives = global_params.get("positives", "")
    global_negatives = global_params.get("negatives", "")

    # The continuity book, for context
    continuity = {}
    book_path = continuity_file(d)
    if book_path.exists():
        try:
            continuity = json.loads(book_path.read_text())
        except Exception:
            pass

    # Get the engine and model
    args = engine_args(opt)
    engine = args[1]
    model = args[3] if len(args) > 3 else None

    # Build the enhancement prompt
    book_context = ""
    if continuity:
        style = continuity.get("style", {})
        visual = style.get("visual", "")
        if visual:
            book_context += f"\nVisual style: {visual}"
        characters = continuity.get("characters", {})
        if characters:
            char_desc = ", ".join(f"{k}: {v.get('visual_token', '')}" for k, v in characters.items() if v.get('visual_token'))
            book_context += f"\nCharacters: {char_desc}"

    # Include global parameters in the enhancement prompt
    global_section = ""
    if global_positives or global_negatives:
        global_section = "\nGLOBAL PROMPT PARAMETERS (must be preserved in the enhanced prompt):\n"
        if global_positives:
            global_section += f"  Always include: {global_positives}\n"
        if global_negatives:
            global_section += f"  Always avoid: {global_negatives}\n"

    what = "a text-to-video prompt for a 4-6 second clip" if "video" in (opt.get("kind", "") or "") else "a text-to-image prompt"
    preview_text = "Preview only - do NOT save the updated prompt, just show what it would look like." if preview_only else "Provide the updated prompt ready to use."

    prompt = (f'Original prompt:\n{original_prompt}\n\n'
              f'Continuity book:{book_context}\n'
              f'{global_section}\n'
              f'User instruction: {instruction}\n\n'
              f'Rewrite the prompt incorporating the instruction. Keep the same format and length. '
              f'{preview_text} Reply with JSON: {{"updated_prompt": "...", "feedback": "..."}}')

    def check(d):
        if "updated_prompt" not in d or not isinstance(d["updated_prompt"], str) or len(d["updated_prompt"]) < 10:
            raise ValueError("missing or invalid updated_prompt")

    data = llm_json(prompt, "You are a prompt engineer enhancing prompts for video/image generation models. "
                        "Reply with a single JSON object and nothing else.",
                    model=model, engine=engine, validate=check)

    updated_prompt = data.get("updated_prompt", original_prompt)

    # Ensure global parameters are included in the updated prompt
    if global_positives and global_positives not in updated_prompt:
        updated_prompt = updated_prompt + ", " + global_positives
    # Add negative tail if not present
    neg_tail = "photorealistic epic period film, cinematic natural lighting, realistic faces and anatomy, no text, no subtitles, no logos, no watermark, no cartoon style"
    if global_negatives:
        neg_tail = f"{global_negatives}, {neg_tail}"
    if neg_tail not in updated_prompt:
        updated_prompt = updated_prompt + ", " + neg_tail

    result = {
        "updated_prompt": updated_prompt,
        "feedback": data.get("feedback", "Updated" if not preview_only else "Preview ready")
    }

    if not preview_only:
        # Update the CSV file with the new prompt
        updated = False
        for csv_name in ("all_shots.csv", "all_chapters.csv", "all_images.csv"):
            csv_path = d / csv_name
            if csv_path.exists():
                rows = read_csv_rows(csv_path)
                if 0 < row <= len(rows):
                    rows[row - 1]["prompt"] = data["updated_prompt"]
                    # Write back the CSV
                    with open(csv_path, "w", newline="") as f:
                        if rows:
                            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                            writer.writeheader()
                            writer.writerows(rows)
                    updated = True
                    break
        if updated:
            result["feedback"] = "Prompt updated and saved to CSV"

    return result


def gallery(slug, limit=60):
    """Newest results of a project: clips, images and films, each with the prompt that made it."""
    d = pdir(slug)
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


# ---------------------------------------------------------------- Compare wall, showcase art and the prompt library
REG_LANES = ("regtest_a", "regtest_b", "regtest_i")        # the two lanes of scripts/regress_kaggle.py, and regtest_i: results collected by hand (the regression never writes there)
RATINGS_FILE = PROJECTS / "regression" / "regtest_ratings.json"
ZOMBIE_PROMPT = "a young woman running towards the camera, zombies are chasing her down a city street. not blurry, no cartoon."   # the built-in prompt of the first regression


THUMB_PX = 480


def load_rgb(src):
    """A picture, or one frame from a clip, as an RGB PIL image."""
    from PIL import Image
    if src.suffix.lower() == ".mp4":
        import cv2
        cap = cv2.VideoCapture(str(src))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total // 3))
        ok, frame = cap.read()
        cap.release()
        if not ok:
            raise OSError("cannot read a frame")
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    return Image.open(src).convert("RGB")


def make_thumb(src, dest):
    """A small JPEG of a picture, or of a frame from a clip, so the grids do not load the full files."""
    im = load_rgb(src)
    im.thumbnail((THUMB_PX, THUMB_PX))
    dest.parent.mkdir(exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    im.save(tmp, "JPEG", quality=82)
    tmp.replace(dest)


DEPTH_MODEL = "depth-anything/Depth-Anything-V2-Small-hf"      # Apache-2.0, about 100 MB; downloaded once on first use
_DEPTH = {}
DEPTH_LOCK = threading.Lock()


def make_depth(src, dest):
    """A grey depth map (white = near) for the Studio's 3D view, made on this computer by Depth Anything V2 Small."""
    import numpy as np
    from PIL import Image
    im = load_rgb(src)
    im.thumbnail((1024, 1024))
    with DEPTH_LOCK:                                          # one at a time: the model is loaded once and shared
        if "pipe" not in _DEPTH:
            from transformers import pipeline
            _DEPTH["pipe"] = pipeline("depth-estimation", model=DEPTH_MODEL, device="cpu")
        depth = _DEPTH["pipe"](im)["depth"]
    arr = np.asarray(depth.resize(im.size), dtype="float32")
    lo, hi = np.percentile(arr, 1), np.percentile(arr, 99)
    arr = np.clip((arr - lo) / max(hi - lo, 1e-6), 0, 1)
    dest.parent.mkdir(exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    Image.fromarray((arr * 255).astype("uint8")).save(tmp, "PNG")
    tmp.replace(dest)


def load_ratings():
    return read_json(RATINGS_FILE, {}) if RATINGS_FILE.exists() else {}


def save_rating(key, stars, keep):
    """Remember your stars (0-5) and Keep tick for one regression result; the key is "<lane>/<path under it>"."""
    if not re.fullmatch(r"regtest_[abi]/[A-Za-z0-9_./-]+", str(key)) or ".." in str(key):
        raise PlanError("bad result name")
    try:
        stars = max(0, min(5, int(stars)))
    except (TypeError, ValueError):
        raise PlanError("stars must be a number from 0 to 5")
    ratings = load_ratings()
    ratings[key] = {"stars": stars, "keep": bool(keep)}
    write_json(RATINGS_FILE, ratings)
    return ratings[key]


def regression_minutes():
    """{(model, prompt text): minutes} from the regression reports (the zombie report has no prompt field)."""
    out = {}
    for name in ("regression_kaggle_report.zombie.json", "regression_kaggle_report.json"):
        rep = read_json(ROOT / name, {}) if (ROOT / name).exists() else {}
        for model, v in rep.items():
            if isinstance(v, dict) and v.get("result") == "PASS":
                out[(model, " ".join(str(v.get("prompt", ZOMBIE_PROMPT)).split()))] = v.get("minutes")
    return out


def compare_data():
    """Every regression picture and clip, grouped by the prompt that made it, with your ratings: {"prompts": [{"text", "items": [...]}]}."""
    ratings, minutes, groups = load_ratings(), regression_minutes(), {}
    for lane in REG_LANES:
        d = pdir(lane)
        if not d.is_dir():
            continue
        csvs = {n: read_csv_rows(d / n) for n in ("all_images.csv", "all_shots.csv")}
        for sub, pattern, kind, csv_name in (("images", "*/image-*.png", "image", "all_images.csv"), ("videos", "*/shot-*.mp4", "video", "all_shots.csv")):
            for f in (d / sub).glob(pattern) if (d / sub).exists() else []:
                n = int(re.search(r"(\d+)", f.stem).group(1))
                rows = csvs[csv_name]
                text = " ".join((rows[n - 1].get("prompt") or "").split()) if 0 < n <= len(rows) else ""
                if not text:
                    continue
                key = f"{lane}/{f.relative_to(d).as_posix()}"
                r = ratings.get(key, {})
                groups.setdefault(text, []).append({"model": f.parent.name, "kind": kind, "file": key, "row": n, "size": f.stat().st_size, "mtime": f.stat().st_mtime,
                                                    "stars": r.get("stars", 0), "keep": bool(r.get("keep")), "minutes": minutes.get((f.parent.name, text))})
    out = []
    for text, items in groups.items():
        latest = {}
        for it in sorted(items, key=lambda x: x["mtime"]):         # one result per model: the newest
            latest[(it["model"], it["kind"])] = it
        items = sorted(latest.values(), key=lambda x: (x["kind"], x["model"]))
        out.append({"text": text, "newest": max(i["mtime"] for i in items), "items": items})
    out.sort(key=lambda g: -g["newest"])
    return {"prompts": out}


def showcase():
    """Pictures and one clip made by your own models, used as the Studio's own artwork: {"hero": file or None, "art": [files]}.
    Only results you rated 4 stars or more, plus results of the built-in street-chase prompt, are used: unfiltered models can make
    unsuitable pictures, and nothing should reach the page header without you choosing it."""
    items = []
    for g in compare_data()["prompts"]:
        for it in g["items"]:
            if it["stars"] >= 4 or g["text"] == ZOMBIE_PROMPT:
                items.append(it)
    vids = sorted((i for i in items if i["kind"] == "video" and i["size"] > 60_000), key=lambda i: (-i["stars"], -i["mtime"]))
    imgs = sorted((i for i in items if i["kind"] == "image" and i["size"] > 150_000), key=lambda i: (-i["stars"], -i["mtime"]))
    seen, art = set(), []
    for i in imgs:                                            # at most one picture per model, so the artwork is varied
        if i["model"] not in seen:
            seen.add(i["model"]); art.append(i["file"])
    return {"hero": vids[0]["file"] if vids else None, "art": art[:12]}


def library():
    """The prompt library, each template with a sample from your results when the same prompt was run."""
    import templates
    results = {}
    for g in compare_data()["prompts"]:
        results[g["text"]] = sorted(g["items"], key=lambda i: (-i["stars"], i["kind"] != "video", -i["size"]))
    out = []
    for t in templates.TEMPLATES:
        items = results.get(" ".join(t["prompt"].split()), [])
        want = [i for i in items if i["kind"] == t["kind"]] or items
        out.append({**t, "sample": ({"file": want[0]["file"], "kind": want[0]["kind"], "model": want[0]["model"]} if want else None)})
    return {"templates": out}


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
    rows = [x for x in csv.DictReader(io.StringIO("\n".join(lines[start:]))) if TOOL_SLUG_RE.match(x["ref"].split("/")[-1]) or guess_project(x["ref"].split("/")[-1])]

    def status_of(ref):
        t = subprocess.run([kaggle, "kernels", "status", ref], env=clean_env(), capture_output=True, text=True, timeout=40)
        m = re.search(r"KernelWorkerStatus\.([A-Za-z]+)", t.stdout + t.stderr)
        return m.group(1) if m else "UNKNOWN"

    with ThreadPoolExecutor(max_workers=5) as ex:
        statuses = list(ex.map(status_of, [x["ref"] for x in rows]))
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


# ---------------------------------------------------------------- make a film from the downloaded files you tick
AUDIO_KINDS_FILES = {"narration": "narration-*.wav", "sfx": "sfx-*.wav", "music": "music-*.wav"}
FILM_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,60}$")


def media_inventory(slug):
    """What has been downloaded for a project: clip folders and audio folders with the rows each holds, plus a line of text per row."""
    d = pdir(slug)
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
    inv["seconds"] = {}                                # length of every clip and sound, for the timeline: {folder: {row: seconds}}
    for kind in ("videos", "narration", "sfx", "music"):
        for src, rows in inv[kind].items():
            pattern = "shot-{:04d}.mp4" if kind == "videos" else AUDIO_KINDS_FILES[kind].replace("*", "{:04d}")
            inv["seconds"].setdefault(src, {}).update({str(n): media_seconds(d / src / pattern.format(n)) for n in rows})
    for src, rows in inv["videos"].items():
        csv_name = "all_chapters.csv" if src.endswith("_chapters") else "all_shots.csv"
        table = read_csv_rows(d / csv_name)
        inv["texts"][src] = {str(n): (f"{table[n - 1]['chapter']}: {table[n - 1]['prompt']}"[:110] if 0 < n <= len(table) else "") for n in rows}
    return inv


_SECONDS = {}      # (path, size, mtime) -> seconds


def _mp4_seconds(fh, size):
    """Duration from the mp4's movie header (moov/mvhd), walking the top-level boxes; None if it has none."""
    pos = 0
    while pos + 8 <= size:
        fh.seek(pos)
        head = fh.read(16)
        box, kind = struct.unpack(">I", head[:4])[0], head[4:8]
        hdr = 8
        if box == 1:                                   # 64-bit size
            box, hdr = struct.unpack(">Q", head[8:16])[0], 16
        elif box == 0:
            box = size - pos
        if box < hdr:
            return None
        if kind == b"moov":
            end, p = pos + box, pos + hdr
            while p + 8 <= end:
                fh.seek(p)
                sub, skind = struct.unpack(">I4s", fh.read(8))
                if sub < 8:
                    return None
                if skind == b"mvhd":
                    version = fh.read(1)[0]
                    fh.read(3)
                    if version == 1:
                        fh.read(16); scale, dur = struct.unpack(">IQ", fh.read(12))
                    else:
                        fh.read(8); scale, dur = struct.unpack(">II", fh.read(8))
                    return dur / scale if scale else None
                p += sub
            return None
        pos += box
    return None


def _wav_seconds(fh):
    """Duration of a RIFF/WAVE file from its fmt (bytes per second) and data chunk sizes; None if it is not one."""
    if fh.read(4) != b"RIFF":
        return None
    fh.read(4)
    if fh.read(4) != b"WAVE":
        return None
    rate = None
    while True:
        head = fh.read(8)
        if len(head) < 8:
            return None
        cid, n = struct.unpack("<4sI", head)
        if cid == b"fmt ":
            if n < 12:
                return None                            # too short to hold the byte rate (and seeking back would never end)
            rate = struct.unpack("<HHII", fh.read(12))[3]
            fh.seek(n - 12 + (n & 1), 1)
        elif cid == b"data":
            return n / rate if rate else None
        else:
            fh.seek(n + (n & 1), 1)


def media_seconds(path):
    """Length in seconds (rounded to 0.01) of an .mp4 or .wav file, or None if it cannot be read. Cached until the file changes."""
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key not in _SECONDS:
        try:
            with open(path, "rb") as fh:
                secs = _mp4_seconds(fh, st.st_size) if path.suffix.lower() == ".mp4" else _wav_seconds(fh)
        except (OSError, ValueError, IndexError, struct.error):          # a truncated or odd file: no length, the timeline guesses
            secs = None
        _SECONDS[key] = round(secs, 2) if secs else None
    return _SECONDS[key]


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
    clips, seen = [], set()
    for item in opt.get("rows") or []:                     # in the page's order: the table can reorder clips
        n = int(item.get("n"))
        if n not in have["video"]:
            raise PlanError(f"row {n} has no clip in {vsrc}")
        if n in seen:
            raise PlanError(f"row {n} is listed twice")
        seen.add(n)
        c = {"row": n, "video": f"{vsrc}/shot-{n:04d}.mp4",
             "trim_start": num(item, "trim_start", 0.0, float, 0, 30), "trim_end": num(item, "trim_end", 0.0, float, 0, 30)}
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
    transition = opt.get("transition", "cut")
    if transition not in ("cut", "fade"):
        raise PlanError("bad transition")
    fade = num(opt, "fade", 0.5, float, 0.1, 1.5)
    titles = {k: re.sub(r"[\x00-\x1f\x7f]", " ", str(opt.get(k) or "")).strip()[:120] for k in ("title", "end_title")}   # one line of plain text each
    (pdir(slug) / "films").mkdir(exist_ok=True)
    extra = ["--transition", transition, "--fade", str(fade)] + (["--burn-captions"] if opt.get("burn_captions") else [])
    return slug, {"clips": clips, **titles}, {"label": f"Make film {name}.mp4 from {len(clips)} clip(s)", "env": {},
        "argv": ["uv", "run", "--with", "imageio-ffmpeg", "python", "mix_film.py", "--project", slug, "--selection", "films/_selection.json",
                 "--sync", sync, "--out", f"{name}.mp4", "--vol-narration", str(vols["narration"]), "--vol-sfx", str(vols["sfx"]),
                 "--vol-music", str(vols["music"])] + extra}


# ---------------------------------------------------------------- clean-up: find old generated files, move them to the Trash
CLEAN_CATEGORIES = [   # id, title, ticked by default, what to know
    ("pycache", "Python cache folders", True, "Made automatically by Python; they come back by themselves."),
    ("notebooks", "Old generated notebooks and scripts (the 3 newest notebooks are kept; TPU notebooks are always removed)", True,
     "Written by the scripts in scripts/. They are re-created automatically when a run needs one, or with the Re-create button. "
     "The 3 most recently changed notebooks, and the scripts that go with them, are kept. The TPU notebooks (tpu_wan, tpu_mage_flow, tpu_flux_jax) are always listed and do not use up one of the 3."),
    ("temp", "Temporary and leftover files", True, "Partial uploads, old progress markers, the film selection file and stray logs inside video folders."),
    ("empty", "Empty output folders", True, "Folders in videos/, audio/ and images/ with nothing in them."),
    ("logs", "Kaggle run logs", False, "Kept for troubleshooting failed runs; safe to delete once the run no longer matters."),
    ("stale", "Outputs numbered past the end of the prompt file", False, "Clips, audio or images for rows that no longer exist (left over after the prompts were shortened or re-split)."),
    ("other", "Folders made by other tools", False, "graphify-out is made by your graphify tool, not by this project."),
]
KEEP_NOTEBOOKS = 3                       # clean-up keeps this many of the newest generated notebooks
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
    nb_dirs = [ROOT, ROOT / "notebooks"]
    notebooks = sorted((f for d in nb_dirs if d.is_dir() for f in d.glob("Studio_*.ipynb")), key=lambda f: (f.stat().st_mtime, f.name), reverse=True)
    tpu = [f for f in notebooks if "tpu_" in f.name]            # the TPU experiments (Studio_Kaggle_tpu_wan, Studio_Kaggle_image_tpu_*) are never kept: they are always listed
    notebooks = [f for f in notebooks if f not in tpu]
    kept_keys = {m.group(1) for f in notebooks[:KEEP_NOTEBOOKS] if (m := re.match(r"Studio_(?:Colab|Kaggle)_(.+)\.ipynb$", f.name))}
    for f in notebooks[KEEP_NOTEBOOKS:] + tpu:
        add("notebooks", f)
    for d in nb_dirs:
        for f in (d.glob("colab_generate_*.py") if d.is_dir() else []):
            if f.name[len("colab_generate_"):-3] not in kept_keys:        # keep the script that belongs to a kept notebook
                add("notebooks", f)
    for pat in (".batch_progress*", ".adam_progress", ".enoch_progress", ".generation_progress"):
        for f in ROOT.glob(pat):
            add("temp", f)
    for f in (ROOT / "books").glob("*.part") if (ROOT / "books").exists() else []:
        add("temp", f)
    for proj in layout.all_dirs():
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
    d = pdir(slug)
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
    res = move_to_trash([f"{layout.rel(slug)}/{folder}/{n}" for n in chosen], "pistachio-deleted")
    # a folder emptied by this is tidied away too
    d = pdir(slug) / folder
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
    d = pdir(slug)
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
    continuity = read_json(continuity_file(d), {})
    chars = "; ".join(f"{c['name']}: {c['token']}" for c in continuity.get("characters", []))[:1800]
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


KEEP_KAGGLE_NOTEBOOKS = 3
ACTIVE_STATUSES = {"RUNNING", "QUEUED", "NEW", "UNKNOWN"}          # never delete a notebook that may still be running (or whose state is unknown)


def kaggle_cleanup_scan():
    """Which of YOUR Kaggle notebooks made by this tool would be deleted: all but the newest KEEP_KAGGLE_NOTEBOOKS. Read-only.
    Only notebooks whose names match this tool's naming are considered; anything else in the account is never listed."""
    runs = sorted(kaggle_runs(limit=100), key=lambda r: r["last_run"], reverse=True)
    keep, remove, busy = runs[:KEEP_KAGGLE_NOTEBOOKS], [], []
    for r in runs[KEEP_KAGGLE_NOTEBOOKS:]:
        (busy if r["status"] in ACTIVE_STATUSES else remove).append(r)
    return {"keep": keep, "remove": remove, "busy": busy, "keep_count": KEEP_KAGGLE_NOTEBOOKS}


def kaggle_cleanup_delete():
    """Delete the notebooks the scan lists (it is re-run here: the browser never names what to delete)."""
    if JOB.running:
        raise PlanError("a job is running; wait for it to finish first")
    kaggle = shutil.which("kaggle", path=ENV_PATH)
    if not kaggle:
        raise PlanError("the kaggle command is not installed (uv tool install kaggle)")
    deleted, failed = [], []
    for r in kaggle_cleanup_scan()["remove"]:
        ref = kernel_ref(r["ref"])
        t = subprocess.run([kaggle, "kernels", "delete", "-y", ref], env=clean_env(), capture_output=True, text=True, timeout=60)
        if t.returncode == 0:
            deleted.append(ref)
        else:
            failed.append({"ref": ref, "error": (t.stderr or t.stdout).strip()[-200:]})
    return {"deleted": deleted, "failed": failed}


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
            try:
                self.proc = subprocess.Popen(script_argv(step["argv"]), cwd=ROOT, env={**env_base, **step["env"]}, text=True,
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
        if url.path.startswith("/thumb/"):
            return self._thumb(url)
        if url.path.startswith("/depth/"):
            return self._depth(url)
        if not self._authed():
            return self._json(403, {"error": "forbidden"})
        if url.path == "/api/scenes":
            q = parse_qs(url.query)
            try:
                return self._json(200, scene_data(q.get("project", [""])[0], q.get("chapter", [""])[0]))
            except PlanError as e:
                return self._json(400, {"error": str(e)})
        if url.path == "/api/chapter_shots":
            try:
                return self._json(200, chapter_shots(parse_qs(url.query).get("project", [""])[0]))
            except PlanError as e:
                return self._json(400, {"error": str(e)})
        if url.path == "/api/files":
            try:
                return self._json(200, {"folders": files_inventory(parse_qs(url.query).get("project", [""])[0])})
            except PlanError as e:
                return self._json(400, {"error": str(e)})
        if url.path == "/api/cleanup_scan":
            return self._json(200, {"categories": cleanup_scan()})
        if url.path == "/api/storyboard":
            q = parse_qs(url.query)
            try:
                return self._json(200, storyboard(q.get("project", [""])[0], num({"s": q.get("start", ["1"])[0]}, "s", 1, int, 1),
                                                  num({"e": q.get("end", ["24"])[0]}, "e", 24, int, 1)))
            except PlanError as e:
                return self._json(400, {"error": str(e)})
        if url.path == "/api/suggest":
            q = parse_qs(url.query)
            try:
                return self._json(200, suggestions(q.get("look", [""])[0], q.get("service", [""])[0], q.get("gpu", [""])[0]))
            except PlanError as e:
                return self._json(400, {"error": str(e)})
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
        if url.path == "/api/kaggle_cleanup_scan":
            try:
                return self._json(200, kaggle_cleanup_scan())
            except PlanError as e:
                return self._json(400, {"error": str(e)})
            except subprocess.TimeoutExpired:
                return self._json(400, {"error": "Kaggle did not answer in time; try again"})
        if url.path == "/api/kernel_status":
            try:
                return self._json(200, kernel_status(kernel_ref(parse_qs(url.query).get("ref", [""])[0])))
            except PlanError as e:
                return self._json(400, {"error": str(e)})
            except subprocess.TimeoutExpired:
                return self._json(400, {"error": "Kaggle did not answer in time; try again"})
        if url.path == "/api/setup":
            return self._json(200, setup_status())
        if url.path == "/api/local_llm":                     # the page asks again when you open the Models tab, come back to the window, or press Check again
            return self._json(200, local_llm_status(force=parse_qs(url.query).get("fresh", [""])[0] == "1"))
        if url.path == "/api/compare":
            return self._json(200, compare_data())
        if url.path == "/api/showcase":
            return self._json(200, showcase())
        if url.path == "/api/library":
            return self._json(200, library())
        if url.path == "/api/gallery":
            slug = parse_qs(url.query).get("project", [""])[0]
            return self._json(200, {"items": gallery(slug) if SLUG_RE.match(slug) else []})
        if url.path == "/api/status":
            return self._json(200, status())
        if url.path == "/api/log":
            since = int(parse_qs(url.query).get("since", ["0"])[0])
            with JOB.lock:
                return self._json(200, {"lines": JOB.lines[since:], "next": len(JOB.lines),
                                        "running": JOB.running, "current": JOB.current})
        if url.path == "/api/clip_prompt":
            q = parse_qs(url.query)
            try:
                return self._json(200, clip_prompt(q.get("project", [""])[0], int(q.get("row", ["0"])[0])))
            except PlanError as e:
                return self._json(400, {"error": str(e)})
        if url.path == "/api/characters":
            q = parse_qs(url.query)
            action = q.get("action", ["list"])[0]
            series = q.get("series", [""])[0]
            try:
                if action == "list_series":
                    return self._json(200, {"series": character_tokens.list_series()})
                elif action == "list":
                    return self._json(200, {"series": character_tokens.list_series(), "characters": character_tokens.list_characters(series)})
                elif action == "get":
                    name = q.get("name", [""])[0]
                    char = character_tokens.load_character(series, name)
                    return self._json(200, {"character": char})
                elif action == "tokens":
                    return self._json(200, {"tokens": character_tokens.get_all_character_tokens(series)})
                elif action == "sync":
                    project = q.get("project", [""])[0]
                    count = character_tokens.sync_characters_from_project(project)
                    return self._json(200, {"synced": count, "series": series})
                elif action == "archetypes":
                    # the Characters tab wants {archetype: {...}} (keys fill the dropdown)
                    return self._json(200, {"archetypes": {a.value: {"label": a.value.replace("_", " ").title(), **character_tokens.get_archetype_fields(a)}
                                                           for a in character_tokens.CharacterArchetype}})
                elif action == "archetype_fields":
                    # and {field: {type, required}} for the chosen archetype (a * marks required ones)
                    name = q.get("archetype", [""])[0]
                    try:
                        archetype = character_tokens.CharacterArchetype(name)
                    except ValueError:
                        return self._json(400, {"error": f"unknown archetype: {name}"})
                    cfg = character_tokens.get_archetype_fields(archetype)
                    fields = {}
                    for key, required in (("required_physical", True), ("optional_physical", False), ("required_fields", True), ("optional_fields", False)):
                        for f in cfg.get(key, []):
                            fields[f] = {"type": "string", "required": required}
                    return self._json(200, {"archetype": name, "fields": fields})
                elif action == "valid_values":
                    # dropdown choices: all fields at once, or one field with ?field=
                    field = q.get("field", [""])[0]
                    if field:
                        values = character_tokens.get_valid_values(field)
                        return self._json(200, {"field": field, "values": values, "valid_values": {field: values}})
                    return self._json(200, {"valid_values": {k: list(v) for k, v in character_tokens.VALID_VALUES.items()}})
                else:
                    return self._json(400, {"error": f"unknown action: {action}"})
            except PlanError as e:
                return self._json(400, {"error": str(e)})
        if url.path == "/api/global_params":
            q = parse_qs(url.query)
            project = q.get("project", [""])[0]
            if not project:
                return self._json(400, {"error": "project is required"})
            try:
                params = load_global_params(project)
                return self._json(200, params)
            except PlanError as e:
                return self._json(400, {"error": str(e)})
        self._json(404, {"error": "not found"})

    MEDIA = {".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg", ".wav": "audio/wav"}

    def _thumb(self, url):
        """Serve a small JPEG of a result: /thumb/<project>/<path under it>?t=<token>. Cached in projects/<project>/.thumbs/."""
        if not self._host_ok() or not secrets.compare_digest(parse_qs(url.query).get("t", [""])[0], TOKEN):
            return self._json(403, {"error": "forbidden"})
        parts = url.path[len("/thumb/"):].split("/", 1)
        if len(parts) != 2 or not SLUG_RE.match(parts[0]):
            return self._json(404, {"error": "not found"})
        base = pdir(parts[0]).resolve()
        target = (base / parts[1]).resolve()
        if base not in target.parents or target.suffix.lower() not in (".png", ".jpg", ".mp4") or not target.is_file():
            return self._json(404, {"error": "not found"})
        dest = base / ".thumbs" / (hashlib.sha1(target.relative_to(base).as_posix().encode()).hexdigest()[:24] + ".jpg")
        try:
            if not dest.exists() or dest.stat().st_mtime < target.stat().st_mtime:
                make_thumb(target, dest)
            data = dest.read_bytes()
        except Exception as e:                      # no PIL / unreadable file: the page falls back to the full file
            return self._json(404, {"error": f"no thumbnail: {e}"})
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "private, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def _depth(self, url):
        """Serve a depth map of a result picture: /depth/<project>/<path under it>?t=<token>. Cached in projects/<project>/.depth/."""
        if not self._host_ok() or not secrets.compare_digest(parse_qs(url.query).get("t", [""])[0], TOKEN):
            return self._json(403, {"error": "forbidden"})
        parts = url.path[len("/depth/"):].split("/", 1)
        if len(parts) != 2 or not SLUG_RE.match(parts[0]):
            return self._json(404, {"error": "not found"})
        base = pdir(parts[0]).resolve()
        target = (base / parts[1]).resolve()
        if base not in target.parents or target.suffix.lower() not in (".png", ".jpg") or not target.is_file():
            return self._json(404, {"error": "not found"})
        dest = base / ".depth" / (hashlib.sha1(target.relative_to(base).as_posix().encode()).hexdigest()[:24] + ".png")
        try:
            if not dest.exists() or dest.stat().st_mtime < target.stat().st_mtime:
                make_depth(target, dest)
            data = dest.read_bytes()
        except Exception as e:                     # no torch / no internet for the first model download / unreadable picture
            return self._json(500, {"error": f"could not make a depth map: {e}"})
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "private, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def _file(self, url):
        """Serve a result file: /file/<project>/<path under it>?t=<token>. Only media inside projects/<project>/."""
        if not self._host_ok() or not secrets.compare_digest(parse_qs(url.query).get("t", [""])[0], TOKEN):
            return self._json(403, {"error": "forbidden"})
        parts = url.path[len("/file/"):].split("/", 1)
        if len(parts) != 2 or not SLUG_RE.match(parts[0]):
            return self._json(404, {"error": "not found"})
        base = pdir(parts[0]).resolve()
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
        if not fname.lower().endswith(BOOK_EXTS) or len(fname) < 5:
            return self._json(400, {"error": "only .pdf, .txt or .md files"})
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
        is_pdf = fname.lower().endswith(".pdf")
        with open(tmp, "rb") as f:
            head = f.read(5)
        if is_pdf:
            ok, what = head == b"%PDF-", "a complete PDF file"
        else:
            try:                                                     # text: must be readable UTF-8 with real words in it
                body = tmp.read_bytes().decode("utf-8-sig")
                ok = "\x00" not in body and len(body.split()) >= 5
            except (UnicodeDecodeError, OSError):
                ok = False
            what = "readable text of at least a few words (UTF-8)"
        if left or not ok:
            tmp.unlink(missing_ok=True)
            return self._json(400, {"error": f"that is not {what}"})
        tmp.replace(LIBRARY / fname)
        return self._json(200, {"filename": fname, "project": slugify(Path(fname).stem), "bytes": size})

    def do_HEAD(self):
        # Handle HEAD requests the same as GET but without sending the body
        # We can reuse the GET logic but skip the body writing
        self.do_GET()

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
            if url.path == "/api/chapter_shots":
                return self._json(200, chapter_shots(body.get("project", ""), body))
            if url.path == "/api/retake":
                return self._json(200, retake(body))
            if url.path == "/api/pick_take":
                return self._json(200, pick_take(body))
            if url.path == "/api/estimate":
                return self._json(200, {"text": estimate(body)})
            if url.path == "/api/setup_save":
                try:
                    saved = setup_check.save(body)
                except ValueError as e:
                    raise PlanError(str(e))
                return self._json(200, {"saved": saved, **setup_status()})
            if url.path == "/api/setup_test":
                return self._json(200, setup_check.test_kaggle(path=ENV_PATH))
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
            if url.path == "/api/kaggle_cleanup_delete":
                try:
                    return self._json(200, kaggle_cleanup_delete())
                except subprocess.TimeoutExpired:
                    return self._json(400, {"error": "Kaggle did not answer in time; try again"})
            if url.path == "/api/recreate_notebooks":
                return self._json(200, recreate_notebooks())
            if url.path == "/api/delete_notebooks":
                return self._json(200, delete_notebooks())
            if url.path == "/api/kernel_output":
                try:
                    return self._json(200, kernel_output(kernel_ref(body.get("ref"))))
                except subprocess.TimeoutExpired:
                    return self._json(400, {"error": "Kaggle download timed out; try again"})
            if url.path == "/api/make_film":
                slug, selection, step = film_step(body)
                (pdir(slug) / "films" / "_selection.json").write_text(json.dumps(selection, indent=1))
                JOB.start([step], body)
                return self._json(200, {"clips": len(selection["clips"])})
            if url.path == "/api/new_scene":
                return self._json(200, new_scene(body))
            if url.path == "/api/creative_direction":
                return self._json(200, creative_direction(body))
            if url.path == "/api/creative_direction_get":
                return self._json(200, creative_direction_get(body))
            if url.path == "/api/upscale":
                JOB.start([upscale_step(body)], body)
                return self._json(200, {"started": 1})
            if url.path == "/api/voice_cast":
                return self._json(200, voice_cast(body))
            if url.path == "/api/make_animatic":
                JOB.start([animatic_step(body)], body)
                return self._json(200, {"started": 1})
            if url.path == "/api/fetch":
                JOB.start([fetch_step(body)], body)
                return self._json(200, {"started": 1})
            if url.path == "/api/describe_image":
                try:
                    return self._json(200, describe_image(body))
                except (PlanError, RuntimeError) as e:
                    return self._json(400, {"error": str(e)})
            if url.path == "/api/review_result":
                try:
                    return self._json(200, review_result(body))
                except (PlanError, RuntimeError) as e:
                    return self._json(400, {"error": str(e)})
            if url.path == "/api/expand":
                return self._json(200, {"prompts": expand_idea(body)})
            if url.path == "/api/enhance_prompt":
                return self._json(200, enhance_prompt(body))
            if url.path == "/api/global_params":
                project = body.get("project", "")
                if not project:
                    return self._json(400, {"error": "project is required"})
                positives = body.get("positives", "")
                negatives = body.get("negatives", "")
                try:
                    save_global_params(project, positives, negatives)
                    return self._json(200, {"saved": True})
                except PlanError as e:
                    return self._json(400, {"error": str(e)})
            if url.path == "/api/characters":
                action = body.get("action", "")
                try:
                    if action == "save":
                        char = body.get("character", {})
                        path = character_tokens.save_character(char)
                        return self._json(200, {"saved": True, "path": str(path)})
                    elif action == "add_reference":
                        series = body.get("series", "")
                        name = body.get("name", "")
                        image_path = body.get("image_path", "")
                        ok = character_tokens.add_reference_image(series, name, image_path)
                        return self._json(200, {"updated": ok})
                    elif action == "update_lora":
                        series = body.get("series", "")
                        name = body.get("name", "")
                        lora_repo = body.get("lora_repo", "")
                        trigger_word = body.get("trigger_word", "")
                        base_model = body.get("base_model", "")
                        ok = character_tokens.update_lora_info(series, name, lora_repo, trigger_word, base_model)
                        return self._json(200, {"updated": ok})
                    elif action == "create":
                        series = body.get("series", "")
                        name = body.get("name", "")
                        description = body.get("description", "")
                        visual_token = body.get("visual_token", "")
                        char = character_tokens.create_character_from_description(series, name, description, visual_token)
                        path = character_tokens.save_character(char)
                        return self._json(200, {"created": True, "character": char, "path": str(path)})
                    elif action == "delete":
                        series = body.get("series", "")
                        name = body.get("name", "")
                        ok = character_tokens.delete_character(series, name)
                        return self._json(200, {"deleted": ok})
                    elif action == "archetypes":
                        return self._json(200, {"archetypes": [{"value": a.value, "label": a.value.replace("_", " ").title()} for a in character_tokens.CharacterArchetype]})
                    elif action == "archetype_fields":
                        archetype_str = body.get("archetype", "")
                        try:
                            archetype = character_tokens.CharacterArchetype(archetype_str)
                        except ValueError:
                            return self._json(400, {"error": f"unknown archetype: {archetype_str}"})
                        config = character_tokens.get_archetype_fields(archetype)
                        return self._json(200, {"fields": config})
                    elif action == "valid_values":
                        field = body.get("field", "")
                        values = character_tokens.get_valid_values(field)
                        return self._json(200, {"field": field, "values": values})
                    elif action == "sync":
                        # Copy the characters of a project's continuity book file into the series chosen on the page. Adds only, unless overwrite is set (dry_run counts without writing).
                        project = str(body.get("project", "")).strip()
                        series = str(body.get("series", "")).strip()
                        if not SLUG_RE.match(project) or not (pdir(project)).is_dir():
                            raise PlanError("unknown project")
                        if not series:
                            raise PlanError("pick a series first")
                        r = character_tokens.sync_from_book(project, series, overwrite=bool(body.get("overwrite")), dry_run=bool(body.get("dry_run")))
                        if not r["continuity"]:
                            raise PlanError(f"{project} has no continuity book file ({project}.json), so there is nothing to sync. Sync reads the file that "
                                            f"\"Write the continuity book\" creates for a PDF or text book; imported books such as adam_eve do not have one.")
                        return self._json(200, {**r, "count": r["added"]})
                    elif action == "send_to_book":
                        # Copy the ticked series characters into the book's continuity book file (the reverse of sync). dry_run only counts.
                        project = str(body.get("project", "")).strip()
                        series = str(body.get("series", "")).strip()
                        names = body.get("names")
                        if not SLUG_RE.match(project) or not (pdir(project)).is_dir():
                            raise PlanError("unknown project")
                        if not series or not isinstance(names, list) or not names or len(names) > 300 or not all(isinstance(n, str) and n.strip() for n in names):
                            raise PlanError("pick a series and tick at least one character")
                        try:
                            r = character_tokens.send_to_book(project, series, [n.strip() for n in names], dry_run=bool(body.get("dry_run")))
                        except ValueError as e:
                            raise PlanError(str(e))
                        if not r["found"]:
                            raise PlanError(f"{project} has no continuity book file ({project}.json) yet: write it first with \"Write the continuity book\" in Book Processing.")
                        return self._json(200, r)
                    elif action == "validate":
                        char = body.get("character", {})
                        archetype_str = body.get("archetype", "")
                        try:
                            archetype = character_tokens.CharacterArchetype(archetype_str) if archetype_str else None
                        except ValueError:
                            return self._json(400, {"error": f"unknown archetype: {archetype_str}"})
                        errors = character_tokens.validate_character(char, archetype)
                        return self._json(200, {"valid": len(errors) == 0, "errors": errors})
                    elif action == "template":
                        archetype_str = body.get("archetype", "")
                        series = body.get("series", "")
                        name = body.get("name", "")
                        try:
                            archetype = character_tokens.CharacterArchetype(archetype_str)
                        except ValueError:
                            return self._json(400, {"error": f"unknown archetype: {archetype_str}"})
                        template = character_tokens.create_character_template(archetype, name, series)
                        return self._json(200, {"template": template})
                    else:
                        return self._json(400, {"error": f"unknown action: {action}"})
                except PlanError as e:
                    return self._json(400, {"error": str(e)})
            if url.path == "/api/run":
                steps = build_plan(body, commit=True)       # prompt mode writes its rows here, not when previewing
                JOB.start(steps, body)
                return self._json(200, {"started": len(steps)})
            if url.path == "/api/rate":
                try:
                    return self._json(200, save_rating(body.get("key", ""), body.get("stars", 0), body.get("keep", False)))
                except PlanError as e:
                    return self._json(400, {"error": str(e)})
            if url.path == "/api/stop":
                JOB.stop()
                return self._json(200, {"stopping": True})
            if url.path == "/api/extract_frame":
                # Extract a frame from a video file using OpenCV
                project = body.get("project", "")
                video = body.get("video", "")
                frame = body.get("frame", 16)
                model = body.get("model", "wan")
                if not project or not video:
                    return self._json(400, {"error": "project and video are required"})
                if not SLUG_RE.match(project):
                    return self._json(400, {"error": "bad project name"})
                video_path = pdir(project) / "videos" / model / video
                if not video_path.exists():
                    return self._json(404, {"error": "video not found"})
                # Create output path in the same directory
                output_path = video_path.parent / f"{video_path.stem}_frame{frame:04d}.png"
                try:
                    import cv2
                    cap = cv2.VideoCapture(str(video_path))
                    if not cap.isOpened():
                        return self._json(500, {"error": "could not open video"})
                    # Set frame position
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
                    ret, frame_img = cap.read()
                    cap.release()
                    if not ret:
                        return self._json(500, {"error": f"could not read frame {frame}"})
                    cv2.imwrite(str(output_path), frame_img)
                    if not output_path.exists():
                        return self._json(500, {"error": "frame extraction failed - output not created"})
                    return self._json(200, {"success": True, "frame_path": str(output_path)})
                except ImportError:
                    return self._json(500, {"error": "OpenCV (cv2) not installed"})
                except Exception as e:
                    return self._json(500, {"error": str(e)})
            if url.path == "/api/copy_file":
                # Copy a file to a destination within projects/
                source = body.get("source", "")
                dest = body.get("dest", "")
                if not source or not dest:
                    return self._json(400, {"error": "source and dest are required"})
                src_path = resolve_project_file(source)
                # Ensure source is within projects/
                try:
                    src_path.resolve().relative_to(PROJECTS.resolve())
                except ValueError:
                    return self._json(403, {"error": "source must be within projects/"})
                # Ensure dest is within projects/
                dest_path = Path(dest)
                if not dest_path.is_absolute():
                    dest_path = ROOT / dest_path
                try:
                    dest_path.resolve().relative_to(PROJECTS.resolve())
                except ValueError:
                    return self._json(403, {"error": "dest must be within projects/"})
                # Create parent directories
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(src_path, dest_path)
                    return self._json(200, {"success": True, "dest": str(dest_path)})
                except Exception as e:
                    return self._json(500, {"error": str(e)})
        except PlanError as e:
            return self._json(400, {"error": str(e)})
        except (ValueError, KeyError, TypeError) as e:
            return self._json(400, {"error": f"bad request: {e}"})
        self._json(404, {"error": "not found"})


def save_session(token: str, port: int):
    """Save session info to file."""
    try:
        import json
        SESSION_FILE.write_text(json.dumps({"token": token, "port": port}))
    except Exception:
        pass

def remove_session():
    """Remove session file on clean shutdown."""
    try:
        if SESSION_FILE.exists():
            SESSION_FILE.unlink()
    except Exception:
        pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--new-session", action="store_true", help="Force new session (don't reuse existing)")
    a = ap.parse_args()
    setup_check.load_saved_env()                 # keys saved from the Setup window (a variable already in the environment wins)

    # If --new-session, remove old session file
    if a.new_session:
        remove_session()
        global TOKEN, SESSION_PORT
        TOKEN = secrets.token_urlsafe(16)
        SESSION_PORT = None

    srv = None
    # Try session port first, then the requested port range
    ports_to_try = []
    if SESSION_PORT:
        ports_to_try.append(SESSION_PORT)
    ports_to_try.extend(range(a.port, a.port + 20))

    for port in ports_to_try:
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue

    if srv is None:
        raise SystemExit("no free port found")

    # Save session with actual port
    save_session(TOKEN, srv.server_port)

    url = f"http://127.0.0.1:{srv.server_port}/?t={TOKEN}"
    print(f"Pistachio's Studio running. Open: {url}\nCtrl-C to stop.", flush=True)
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        JOB.stop()
        remove_session()
        print("\nstopped")


if __name__ == "__main__":
    main()
