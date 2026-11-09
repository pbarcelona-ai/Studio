"""studio_app.config"""
import json
import os
import re
from pathlib import Path



ROOT = Path(__file__).resolve().parent.parent.parent
PROJECTS = ROOT / "projects"
LIBRARY = ROOT / "books"          # every book PDF lives here; the page lists them

# ---- model and GPU tables: studio_app/catalog.json (see scripts/check_catalog.py)
CATALOG_FILE = Path(__file__).with_name("catalog.json")
CATALOG = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
if CATALOG.get("schema_version") != 1:
    raise RuntimeError(f"{CATALOG_FILE.name}: unsupported schema_version {CATALOG.get('schema_version')!r}")
# Upscalers: enlarge clips already made (make_video.py); Kaggle or this computer. name -> (label, GPU memory it needs, least GPU GB, needs Ampere or newer)
UPSCALE_MODELS = {k: (v["label"], v["memory"], v["least_gb"], v["ampere"]) for k, v in CATALOG["upscale_models"].items()}
UPSCALE_SHORT = {k: v["short"] for k, v in CATALOG["upscale_models"].items()}        # beside each choice on the page
KAGGLE_GPU_GB = CATALOG["kaggle_gpu_gb"]               # memory per GPU, and which are older than Ampere
KAGGLE_PRE_AMPERE = set(CATALOG["kaggle_pre_ampere"])
COLAB_GPU_GB = CATALOG["colab_gpu_gb"]
CLAUDE_MODELS = CATALOG["claude_models"]
# "paid"/"restricted" are warnings only; Kaggle's own docs say some accelerators are not open to everyone
GPUS = {k: [tuple(x) for x in v] for k, v in CATALOG["gpus"].items()}


VIDEO_MODELS = ["ltx_video", "wan", "wan22_ti2v_5b", "wan22_t2v_a14b", "hunyuan_video", "cogvideox", "cogvideox_5b",
                "wan22_t2v_a14b_lora", "wan22_t2v_a14b_lightning", "hunyuan_video_lora", "hunyuan_video_15", "tpu_wan",     # tpu_wan = Kaggle TPU experiment
                "ltx_video_i2v", "ltx_video_fast_i2v", "wan22_ti2v_5b_i2v", "pika_h3_flex_i2v"]          # image-to-video: animate each shot's keyframe
I2V_MODELS = {"ltx_video_i2v", "ltx_video_fast_i2v", "wan22_ti2v_5b_i2v", "pika_h3_flex_i2v"}     # a model joins these lists once it has really run: skyreels_v2_i2v, svd_i2v, svd_xt_i2v and ltx25_i2v are in make_video.py, untested
SPACE_ONLY_MODELS = {"pika_h3_flex_i2v"}     # too big for any GPU here: only a Hugging Face Space runs them
UPSCALE_SUFFIXES = tuple("_" + m.removeprefix("upscale_") for m in UPSCALE_MODELS)      # videos/<source>_x2, _flashvsr, ...: already upscaled
REF_IMAGE_MODELS = {"flux2_klein_4b"}                                    # keyframe models that take character reference pictures                      # need keyframes (images/<model>_keyframes) for every row they make
# How the Models tab groups them: (title, [models]). A model missing here lands in "Other" on the page.
VIDEO_GROUPS = [("LTX-Video", ["ltx_video"]), ("Wan", ["wan", "wan22_ti2v_5b", "wan22_t2v_a14b", "wan22_t2v_a14b_lightning"]), ("HunyuanVideo", ["hunyuan_video_15", "hunyuan_video"]),
                ("CogVideoX", ["cogvideox", "cogvideox_5b"]), ("Uncensored (adult content)", ["wan22_t2v_a14b_lora", "hunyuan_video_lora"]),
                ("TPU (Kaggle only)", ["tpu_wan"]), ("From keyframes (image-to-video, Kaggle or this computer)", ["pika_h3_flex_i2v", "ltx_video_fast_i2v", "wan22_ti2v_5b_i2v", "ltx_video_i2v"])]
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
LIPSYNC_MODEL = "upscale_lipsync"      # goes the upscalers' road (clips in, clips back), but is not one of them
SYNC_MODES = ("stretch", "gentle", "speed", "trim")     # mix_film.py --sync
MODEL_DEFAULTS = {
    "ltx_video": {"width": 768, "height": 320, "frames": 97, "steps": 40, "guidance": 3.0},
    "wan": {"width": 512, "height": 288, "frames": 33, "steps": 30, "guidance": 5.0},
    "cogvideox": {"width": 720, "height": 480, "frames": 49, "steps": 50, "guidance": 6.0, "locked": ["width", "height", "frames"]},
    "cogvideox_5b": {"width": 720, "height": 480, "frames": 49, "steps": 50, "guidance": 6.0, "locked": ["width", "height", "frames"]},
    "wan22_ti2v_5b": {"width": 704, "height": 384, "frames": 33, "steps": 30, "guidance": 5.0},
    "ltx_video_i2v": {"width": 768, "height": 320, "frames": 97, "steps": 40, "guidance": 3.0},
    "ltx_video_fast_i2v": {"width": 768, "height": 320, "frames": 97, "guidance": 1.0, "locked": ["steps"]},       # fixed 8-step schedule
    "wan22_ti2v_5b_i2v": {"width": 704, "height": 384, "frames": 33, "steps": 30, "guidance": 5.0},
    "pika_h3_flex_i2v": {"width": 832, "height": 480, "frames": 121, "locked": ["width", "height", "frames", "negative", "steps", "guidance"]},
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
MAX_UPLOAD = 300 * 1024 * 1024
MAX_JSON_BODY = 8 * 1024 * 1024                        # the largest JSON request the page may send
WEB = ROOT / "web"                                       # the page: index.html and static/ (CSS, JS)
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
