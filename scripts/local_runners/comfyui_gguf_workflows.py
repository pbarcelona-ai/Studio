"""ComfyUI GGUF workflow builders for local FLUX.2 Klein (multi-reference) and Z-Image Turbo models."""
from __future__ import annotations

from pathlib import Path
import random
from typing import Any

from .sd_cli_runner import compute_dimensions

ROOT = Path(__file__).resolve().parents[2]

GGUF_MODEL_SPECS: dict[str, dict[str, Any]] = {
    "flux2-klein-9b": {
        "kind": "flux2",
        "unet_candidates": (
            "flux-2-klein-9b-Q8_0.gguf",
            "flux-2-klein-9b-Q6_K.gguf",
            "flux-2-klein-9b-Q5_K_M.gguf",
            "flux-2-klein-9b-Q4_K_M.gguf",
        ),
        "clip": "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf",
        "clip_type": "flux2",
        "vae": "flux2_ae.safetensors",
        "steps": 4,
        "cfg": 1.0,
        "sampler_name": "euler",
        "scheduler": "simple",
        "base_size": 1024,
        "supports_ref_images": True,
        "vram_gb": 12.0,
    },
    "flux2-klein-4b": {
        "kind": "flux2",
        "unet_candidates": (
            "flux-2-klein-4b-Q8_0.gguf",
            "flux-2-klein-4b-Q6_K.gguf",
            "flux-2-klein-4b-Q5_K_M.gguf",
            "flux-2-klein-4b-Q4_K_M.gguf",
        ),
        "clip": "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf",
        "clip_type": "flux2",
        "vae": "flux2_ae.safetensors",
        "steps": 4,
        "cfg": 1.0,
        "sampler_name": "euler",
        "scheduler": "simple",
        "base_size": 1024,
        "supports_ref_images": True,
        "vram_gb": 8.0,
    },
    "z-image-turbo": {
        "kind": "z-image",
        "unet_candidates": (
            "z_image_turbo-Q4_K.gguf",
            "z_image_turbo-Q8_0.gguf",
            "z_image_turbo-Q6_K.gguf",
        ),
        "clip": "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf",
        "clip_type": "lumina2",
        "vae": "ae.safetensors",
        "steps": 8,
        "cfg": 1.0,
        "sampler_name": "res_multistep",
        "scheduler": "simple",
        "base_size": 1024,
        "supports_ref_images": False,
        "vram_gb": 4.5,
    },
}


def _find_model_file(filename: str, search_dirs: list[Path]) -> Path | None:
    for d in search_dirs:
        p = d / filename
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def resolve_gguf_model_files(
    model_id: str,
    models_root: Path | None = None,
) -> dict[str, str] | None:
    """Return resolved ComfyUI filenames (`unet`, `clip`, `vae`) if all required files exist on disk."""
    spec = GGUF_MODEL_SPECS.get(model_id)
    if spec is None:
        return None
    mroot = models_root or (ROOT / "models")
    sd_cli_dir = mroot / "sd_cli"
    unet_dirs = [sd_cli_dir, mroot / "diffusion_models", mroot / "unet"]
    clip_dirs = [sd_cli_dir, mroot / "text_encoders", mroot / "clip"]
    vae_dirs = [sd_cli_dir, mroot / "vae"]

    unet_name = ""
    for cand in spec["unet_candidates"]:
        found = _find_model_file(str(cand), unet_dirs)
        if found is not None:
            unet_name = found.name
            break
    if not unet_name:
        return None

    clip_found = _find_model_file(str(spec["clip"]), clip_dirs)
    vae_found = _find_model_file(str(spec["vae"]), vae_dirs)
    if clip_found is None or vae_found is None:
        return None

    return {
        "unet": unet_name,
        "clip": clip_found.name,
        "vae": vae_found.name,
    }


def ready_gguf_models(
    models_root: Path | None = None,
    *,
    require_ref_support: bool = False,
) -> list[str]:
    """Return installed local GGUF model IDs ordered best-first."""
    order = (
        ("flux2-klein-9b", "flux2-klein-4b")
        if require_ref_support
        else ("z-image-turbo", "flux2-klein-9b", "flux2-klein-4b")
    )
    out: list[str] = []
    for mid in order:
        if resolve_gguf_model_files(mid, models_root=models_root) is not None:
            out.append(mid)
    return out


def compute_flux2_dimensions(aspect_ratio: str = "1:1") -> tuple[int, int]:
    """Compute width and height (multiples of 16) targeting ~1 MP for fast, crisp FLUX.2 / Z-Image renders."""
    ar = aspect_ratio.strip()
    presets: dict[str, tuple[int, int]] = {
        "1:1": (1024, 1024),
        "16:9": (1344, 768),
        "9:16": (768, 1344),
        "4:3": (1152, 896),
        "3:4": (896, 1152),
        "21:9": (1536, 640),
    }
    if ar in presets:
        return presets[ar]
    w, h = compute_dimensions(1024, ar)
    return max(64, (w // 16) * 16), max(64, (h // 16) * 16)


def normalize_seed(seed: int | None) -> int:
    if seed is None or int(seed) < 0:
        return random.randint(1, (1 << 31) - 1)
    return int(seed)


def build_flux2_klein_gguf_workflow(
    *,
    prompt: str,
    unet_name: str = "flux-2-klein-4b-Q8_0.gguf",
    clip_name: str = "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf",
    vae_name: str = "flux2_ae.safetensors",
    width: int = 1024,
    height: int = 1024,
    steps: int = 4,
    cfg: float = 1.0,
    seed: int = -1,
    ref_image_names: list[str] | None = None,
    init_image_name: str | None = None,
    denoise: float = 1.0,
    negative_prompt: str = "",
    filename_prefix: str = "studio/flux2-klein",
) -> dict[str, Any]:
    """Build a ComfyUI API prompt graph for FLUX.2 Klein GGUF with optional 1..4 reference images and img2img init."""
    w = max(64, (int(width) // 16) * 16)
    h = max(64, (int(height) // 16) * 16)
    resolved_seed = normalize_seed(seed)
    refs = [str(n).strip() for n in (ref_image_names or []) if str(n).strip()][:4]

    wf: dict[str, Any] = {
        "1": {
            "class_type": "UnetLoaderGGUF",
            "inputs": {"unet_name": unet_name},
            "_meta": {"title": "Load FLUX.2 Klein GGUF"},
        },
        "2": {
            "class_type": "CLIPLoaderGGUF",
            "inputs": {"clip_name": clip_name, "type": "flux2"},
            "_meta": {"title": "Load Qwen3-4B GGUF (FLUX.2)"},
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": vae_name},
            "_meta": {"title": "Load FLUX.2 VAE"},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": prompt},
            "_meta": {"title": "Positive Prompt"},
        },
    }

    if float(cfg) > 1.0 and negative_prompt.strip():
        wf["5"] = {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": negative_prompt.strip()},
            "_meta": {"title": "Negative Prompt"},
        }
    else:
        wf["5"] = {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["4", 0]},
            "_meta": {"title": "Conditioning Zero Out"},
        }

    pos_ref: list[Any] = ["4", 0]
    neg_ref: list[Any] = ["5", 0]

    if refs:
        rml_inputs: dict[str, Any] = {
            "positive": ["4", 0],
            "negative": ["5", 0],
            "vae": ["3", 0],
            "resolution": "resize",
            "resolution.megapixels": 1.0,
        }
        for idx, rname in enumerate(refs):
            nid = f"20_{idx}"
            wf[nid] = {
                "class_type": "LoadImage",
                "inputs": {"image": rname},
                "_meta": {"title": f"Reference Image {idx + 1}"},
            }
            rml_inputs[f"images.image{idx}"] = [nid, 0]
        wf["17"] = {
            "class_type": "ReferenceMultiLatent",
            "inputs": rml_inputs,
            "_meta": {"title": "Set Reference Multi Latent"},
        }
        pos_ref = ["17", 0]
        neg_ref = ["17", 1]

    eff_denoise = max(0.05, min(1.0, float(denoise)))
    if init_image_name and str(init_image_name).strip() and eff_denoise < 0.999:
        wf["25"] = {
            "class_type": "LoadImage",
            "inputs": {"image": str(init_image_name).strip()},
            "_meta": {"title": "Load Init Image"},
        }
        wf["26"] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["25", 0],
                "upscale_method": "lanczos",
                "width": w,
                "height": h,
                "crop": "center",
            },
            "_meta": {"title": "Scale Init Image"},
        }
        wf["27"] = {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["26", 0], "vae": ["3", 0]},
            "_meta": {"title": "Encode Init Latent"},
        }
        latent_ref: list[Any] = ["27", 0]
    else:
        wf["6"] = {
            "class_type": "EmptyFlux2LatentImage",
            "inputs": {"width": w, "height": h, "batch_size": 1},
            "_meta": {"title": "Empty FLUX.2 Latent"},
        }
        latent_ref = ["6", 0]
        eff_denoise = 1.0

    wf["7"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": ["1", 0],
            "positive": pos_ref,
            "negative": neg_ref,
            "latent_image": latent_ref,
            "seed": resolved_seed,
            "steps": max(1, int(steps)),
            "cfg": float(cfg),
            "sampler_name": "euler",
            "scheduler": "simple",
            "denoise": eff_denoise,
        },
        "_meta": {"title": "KSampler"},
    }
    wf["8"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["7", 0], "vae": ["3", 0]},
        "_meta": {"title": "VAE Decode"},
    }
    wf["9"] = {
        "class_type": "SaveImage",
        "inputs": {"images": ["8", 0], "filename_prefix": filename_prefix},
        "_meta": {"title": "Save Image"},
    }
    return wf


def build_z_image_gguf_workflow(
    *,
    prompt: str,
    unet_name: str = "z_image_turbo-Q4_K.gguf",
    clip_name: str = "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf",
    vae_name: str = "ae.safetensors",
    width: int = 1024,
    height: int = 1024,
    steps: int = 8,
    cfg: float = 1.0,
    seed: int = -1,
    init_image_name: str | None = None,
    denoise: float = 1.0,
    filename_prefix: str = "studio/z-image-gguf",
) -> dict[str, Any]:
    """Build a ComfyUI API prompt graph for Z-Image Turbo GGUF text-to-image (or img2img)."""
    w = max(64, (int(width) // 16) * 16)
    h = max(64, (int(height) // 16) * 16)
    resolved_seed = normalize_seed(seed)

    wf: dict[str, Any] = {
        "1": {
            "class_type": "UnetLoaderGGUF",
            "inputs": {"unet_name": unet_name},
            "_meta": {"title": "Load Z-Image Turbo GGUF"},
        },
        "11": {
            "class_type": "ModelSamplingAuraFlow",
            "inputs": {"model": ["1", 0], "shift": 3},
            "_meta": {"title": "ModelSamplingAuraFlow"},
        },
        "2": {
            "class_type": "CLIPLoaderGGUF",
            "inputs": {"clip_name": clip_name, "type": "lumina2"},
            "_meta": {"title": "Load Qwen3-4B GGUF (Z-Image)"},
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": vae_name},
            "_meta": {"title": "Load VAE"},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": prompt},
            "_meta": {"title": "Positive Prompt"},
        },
        "5": {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["4", 0]},
            "_meta": {"title": "Conditioning Zero Out"},
        },
    }

    eff_denoise = max(0.05, min(1.0, float(denoise)))
    if init_image_name and str(init_image_name).strip() and eff_denoise < 0.999:
        wf["25"] = {
            "class_type": "LoadImage",
            "inputs": {"image": str(init_image_name).strip()},
            "_meta": {"title": "Load Init Image"},
        }
        wf["26"] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["25", 0],
                "upscale_method": "lanczos",
                "width": w,
                "height": h,
                "crop": "center",
            },
            "_meta": {"title": "Scale Init Image"},
        }
        wf["27"] = {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["26", 0], "vae": ["3", 0]},
            "_meta": {"title": "Encode Init Latent"},
        }
        latent_ref: list[Any] = ["27", 0]
    else:
        wf["6"] = {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": w, "height": h, "batch_size": 1},
            "_meta": {"title": "Empty SD3 Latent"},
        }
        latent_ref = ["6", 0]
        eff_denoise = 1.0

    wf["7"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": ["11", 0],
            "positive": ["4", 0],
            "negative": ["5", 0],
            "latent_image": latent_ref,
            "seed": resolved_seed,
            "steps": max(1, int(steps)),
            "cfg": float(cfg),
            "sampler_name": "res_multistep",
            "scheduler": "simple",
            "denoise": eff_denoise,
        },
        "_meta": {"title": "KSampler"},
    }
    wf["8"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["7", 0], "vae": ["3", 0]},
        "_meta": {"title": "VAE Decode"},
    }
    wf["9"] = {
        "class_type": "SaveImage",
        "inputs": {"images": ["8", 0], "filename_prefix": filename_prefix},
        "_meta": {"title": "Save Image"},
    }
    return wf
