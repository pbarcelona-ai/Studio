"""The status the page loads first (projects, models, services, setup)."""
import os
import shutil
from pathlib import Path
from bookkit import SLUG_RE, slugify
import setup_check
import layout
import model_advisor

from .config import ADULT_GROUP, ADULT_MODELS, AUDIO_KINDS, AUDIO_MODELS, AUDIO_ROLE_TITLES, CLAUDE_MODELS, ENV_PATH, GPUS, IMAGE_GROUPS, IMAGE_MODELS, MODEL_DEFAULTS, ROOT, UPSCALE_MODELS, UPSCALE_SHORT, VIDEO_GROUPS, VIDEO_MODELS, adult_enabled
from .gpus import blockers, gpu_blocker, gpu_profile, legacy_cloud_enabled, local_gpu_label
from .kaggle_cleanup import AUTO_CLEAN_OFF
from .llm import local_llm_status
from .projects import codex_models, library_files, project_info, promptset_info
from .steps import HF_MODELS, HF_VISION_MODELS


def status():
    adult = adult_enabled()
    legacy = legacy_cloud_enabled()
    profile = gpu_profile()
    video_models = VIDEO_MODELS if adult else [m for m in VIDEO_MODELS if m not in ADULT_MODELS]
    image_models = IMAGE_MODELS if adult else [m for m in IMAGE_MODELS if m not in ADULT_MODELS]
    video_groups = VIDEO_GROUPS if adult else [g for g in VIDEO_GROUPS if g[0] != ADULT_GROUP]
    image_groups = IMAGE_GROUPS if adult else [g for g in IMAGE_GROUPS if g[0] != ADULT_GROUP]
    for base in (layout.BOOKS, layout.CHARACTERS, layout.PROMPTS, layout.REGRESSION):
        base.mkdir(parents=True, exist_ok=True)
    sets = layout.promptset_slugs()               # Single Prompts sets and character image sets
    slugs = set(layout.book_slugs())              # books
    slugs |= {slugify(Path(f).stem) for f in library_files()}          # books in books/ that have no project yet
    names = sorted(x for x in slugs if SLUG_RE.match(x))

    tool_names = ("claude", "fcc-claude", "codex", "fcc-codex", "colab", "kaggle", "uv") if legacy else ("claude", "fcc-claude", "codex", "fcc-codex", "uv")
    tools: dict[str, bool] = {t: bool(shutil.which(t, path=ENV_PATH)) for t in tool_names}
    if legacy:
        tools.update({"hf": True, "huggingface": True})
    computer_why = gpu_blocker("computer", "local")
    tools["computer"] = not computer_why
    tools["local"] = bool(local_llm_status()["ready"])

    visible_gpus = {**GPUS, "computer": [("local", local_gpu_label())]} if legacy else {"computer": [("local", local_gpu_label())]}
    visible_gpu_blockers = (
        {svc: {g: gpu_blocker(svc, g) for g, _ in gl if gpu_blocker(svc, g)} for svc, gl in GPUS.items()}
        if legacy
        else ({"computer": {"local": computer_why}} if computer_why else {})
    )
    all_blockers = blockers()
    visible_blockers = (
        all_blockers
        if legacy
        else {m: {"computer": svcs["computer"]} for m, svcs in all_blockers.items() if "computer" in svcs}
    )

    return {
        "tools": tools,
        "projects": [project_info(s) for s in names], "library": library_files(),
        "promptsets": [promptset_info(x) for x in sets], "image_models": image_models, "model_defaults": MODEL_DEFAULTS,
        "blockers": visible_blockers,
        "gpu_blockers": visible_gpu_blockers,
        "video_models": video_models, "video_groups": video_groups, "image_groups": image_groups, "adult_models": {"enabled": adult, "count": len(ADULT_MODELS)}, "audio_kinds": AUDIO_KINDS, "audio_models": {k: {"role": r, "label": l, "note": n} for k, (r, l, n) in AUDIO_MODELS.items()}, "audio_roles": AUDIO_ROLE_TITLES, "gpus": visible_gpus, "computer_why": computer_why,
        "upscale_models": {k: {"label": l, "short": UPSCALE_SHORT[k], "memory": m, "least_gb": g, "ampere": a} for k, (l, m, g, a) in UPSCALE_MODELS.items()}, "claude_models": CLAUDE_MODELS, "hf_models": HF_MODELS, "hf_vision_models": HF_VISION_MODELS, "hf_token_set": bool(os.environ.get("HF_TOKEN", "").strip()), "local_llm": local_llm_status(),
        "codex_models": codex_models(), "auto_cleanup": not AUTO_CLEAN_OFF.exists(),
        "legacy_cloud": legacy,
        "gpu_profile": profile,
        "looks": [{"id": k, "label": l, "about": a, **model_advisor.STYLE[k]} for k, (l, a) in model_advisor.LOOKS.items()],
    }


# ---------------------------------------------------------------- plan -> validated argv steps
def setup_status():
    """The Setup window's data: what this computer has and lacks, plus the Kaggle account name found (never any key)."""
    items = setup_check.check(path=ENV_PATH, local_llm_ready=bool(local_llm_status().get("ready")),
                              local_gpu="" if gpu_blocker("computer", "local") else local_gpu_label(), gpu_seen=gpu_blocker("computer", "local") or "")
    return {"items": items, **setup_check.summary(items), "kaggle_username": setup_check.kaggle_state()["username"], "root": str(ROOT)}
