"""studio_app.overview"""
import os
import shutil
from pathlib import Path
from bookkit import SLUG_RE, slugify
import setup_check
import layout
import model_advisor

from .config import AUDIO_KINDS, AUDIO_MODELS, AUDIO_ROLE_TITLES, CLAUDE_MODELS, ENV_PATH, GPUS, IMAGE_GROUPS, IMAGE_MODELS, MODEL_DEFAULTS, ROOT, UPSCALE_MODELS, UPSCALE_SHORT, VIDEO_GROUPS, VIDEO_MODELS
from .gpus import blockers, gpu_blocker, local_gpu_label
from .kaggle_cleanup import AUTO_CLEAN_OFF
from .llm import local_llm_status
from .projects import codex_models, library_files, project_info, promptset_info
from .steps import HF_MODELS, HF_VISION_MODELS


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
        "codex_models": codex_models(), "auto_cleanup": not AUTO_CLEAN_OFF.exists(),
        "looks": [{"id": k, "label": l, "about": a, **model_advisor.STYLE[k]} for k, (l, a) in model_advisor.LOOKS.items()],
    }


# ---------------------------------------------------------------- plan -> validated argv steps
def setup_status():
    """The Setup window's data: what this computer has and lacks, plus the Kaggle account name found (never any key)."""
    items = setup_check.check(path=ENV_PATH, local_llm_ready=bool(local_llm_status().get("ready")),
                              local_gpu="" if gpu_blocker("computer", "local") else local_gpu_label(), gpu_seen=gpu_blocker("computer", "local") or "")
    return {"items": items, **setup_check.summary(items), "kaggle_username": setup_check.kaggle_state()["username"], "root": str(ROOT)}
