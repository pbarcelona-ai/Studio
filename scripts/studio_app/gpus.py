"""What each GPU/service can run: memory checks, blockers, suggestions."""
import os
import sys
import hf_spaces
import model_advisor
import run_local_model

from .common import PlanError
from .config import AUDIO_KINDS, COLAB_GPU_GB, GPUS, I2V_MODELS, IMAGE_MODELS, KAGGLE_GPU_GB, KAGGLE_PRE_AMPERE, SPACE_ONLY_MODELS, UPSCALE_MODELS, VIDEO_MODELS


# Set to True once a TPU notebook started from the command line really gets a TPU. On Oct 27, 2026 two such runs were
# accepted by Kaggle (enable_tpu=true, machine_shape=TpuV5E8) but the sessions had no TPU: no /dev/accel* devices,
# CPU-only JAX, and 0.00 h of the 20 h weekly TPU quota used.
TPU_CLI_WORKS = True
TPU_CLI_NOTE = ("Kaggle did not attach a TPU to notebooks started from the command line (tested twice, 0 h of TPU quota used; "
                "TPUs may also just have been busy). Try the notebook in the Kaggle web page, or retest later")


_ALL_GPUS = None


def all_gpus():
    """Every GPU this computer has, any maker (run_local_model.detect_gpus), asked once."""
    global _ALL_GPUS
    if _ALL_GPUS is None:
        _ALL_GPUS = run_local_model.detect_gpus()
    return _ALL_GPUS


def local_gpus():
    """The GPUs the models can run on here [(name, GB, compute capability or AMD gfx name)]: NVIDIA, or AMD with ROCm (experimental);
    [] if none (or not on Linux / WSL 2)."""
    return [(g["name"], g["gb"], g["cap"]) for g in run_local_model.usable(all_gpus())] if sys.platform.startswith("linux") else []


def local_is_amd():
    u = run_local_model.usable(all_gpus())
    return bool(u) and not u[0]["nvidia_ready"]


def local_gpu_label():
    """The GPU's real name and memory, whatever its maker, e.g. 'Intel Iris Plus Graphics 645 (1.5 GB shared)'."""
    g = all_gpus()
    if not g:
        return "No graphics processor found"
    return run_local_model.gpu_text(g[0]) + (f" + {len(g) - 1} more" if len(g) > 1 else "")


def gpu_blocker(service, gpu):
    if service == "computer":
        return run_local_model.gpu_problem(all_gpus())
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
    if name in SPACE_ONLY_MODELS and service != "huggingface":
        return "far too big for this GPU: it runs on its public Hugging Face Space (Models tab, Where to run: Hugging Face). Make the keyframes on Kaggle first"
    if service == "huggingface" and (name not in I2V_MODELS or name in hf_spaces.SPACES):
        return None if name in hf_spaces.SPACES else "no public Hugging Face Space is set up for this model (see scripts/hf_spaces.py)"
    if service == "computer" and name in run_local_model.NVIDIA_ONLY and local_is_amd():
        return "cannot run on this AMD GPU: " + run_local_model.NVIDIA_ONLY[name]
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
