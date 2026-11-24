"""Local Wan 2.1/2.2 multi-segment Diffusers video/image engine with VRAM-aware quantization and drift correction."""
from __future__ import annotations

import contextlib
import importlib
from pathlib import Path
import threading
from typing import Any

from .base import LocalRunner, ProgressCallback
from .gpu_lease import acquire_media_lease

WAN_VARIANTS: dict[str, dict[str, Any]] = {
    "wan2.2-ti2v-5b": {
        "repo": "Wan-AI/Wan2.2-TI2V-5B-Diffusers",
        "vram_bf16_gb": 16.0,
        "is_moe": False,
        "ops": {"text_to_video", "image_to_video", "video_to_video", "first_last_frame", "text_to_image"},
    },
    "wan2.2-t2v-a14b": {
        "repo": "Wan-AI/Wan2.2-T2V-A14B-Diffusers",
        "vram_bf16_gb": 36.0,
        "is_moe": True,
        "ops": {"text_to_video", "image_to_video", "video_to_video", "first_last_frame", "text_to_image"},
    },
    "wan2.2-i2v-a14b": {
        "repo": "Wan-AI/Wan2.2-I2V-A14B-Diffusers",
        "vram_bf16_gb": 36.0,
        "is_moe": True,
        "ops": {"image_to_video", "first_last_frame", "video_to_video"},
    },
    "wan2.1-14b": {
        "repo": "Wan-AI/Wan2.1-T2V-14B-Diffusers",
        "vram_bf16_gb": 32.0,
        "is_moe": False,
        "ops": {"text_to_video", "image_to_video", "video_to_video", "first_last_frame", "text_to_image"},
    },
    "wan2.1-1.3b": {
        "repo": "Wan-AI/Wan2.1-T2V-1.3B-Diffusers",
        "vram_bf16_gb": 8.0,
        "is_moe": False,
        "ops": {"text_to_video", "video_to_video", "text_to_image"},
    },
}

_PIPELINE_CACHE: dict[str, Any] = {}
_CACHE_LOCK = threading.Lock()


def free_wan_pipelines() -> None:
    """Clear cached Wan pipelines and release CUDA cache if available."""
    with _CACHE_LOCK:
        _PIPELINE_CACHE.clear()
    with contextlib.suppress(Exception):
        torch = importlib.import_module("torch")
        if hasattr(torch, "cuda") and torch.cuda.is_available():
            torch.cuda.empty_cache()


def _snap_spatial(val: int, multiple: int = 32) -> int:
    return max(multiple, (int(val) // multiple) * multiple)


def _snap_temporal(frames: int) -> int:
    if frames <= 1:
        return 1
    k = max(1, (int(frames) - 1) // 4)
    return k * 4 + 1


def _select_precision_and_offload(
    vram_gb: float,
    requested_precision: str = "auto",
    requested_offload: str = "auto",
) -> tuple[str, str]:
    prec = requested_precision.lower() if requested_precision and requested_precision != "auto" else ""
    if not prec:
        if vram_gb >= 24.0:
            prec = "bf16"
        elif vram_gb >= 15.0:
            prec = "int8"
        else:
            prec = "int4"

    offload = requested_offload.lower() if requested_offload and requested_offload != "auto" else ""
    if not offload:
        if vram_gb >= 18.0:
            offload = "model"
        else:
            offload = "sequential"
    return prec, offload


def _match_color_drift(frame_pil: Any, ref_means: Any, np: Any, pil_image: Any) -> Any:
    arr = np.asarray(frame_pil, dtype=np.float32)
    cur_means = arr.mean(axis=(0, 1))
    corrected = np.clip(arr + (ref_means - cur_means), 0, 255).astype(np.uint8)
    return pil_image.fromarray(corrected)


class WanDiffusersRunner(LocalRunner):
    """Direct PyTorch/Diffusers Wan 2.1/2.2 runner supporting multi-segment I2V chaining and VRAM-adaptive precision."""

    name = "wan_diffusers"

    def __init__(self) -> None:
        self._cancelled = False

    def capabilities(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tasks": ["video", "image"],
            "operations": [
                "text_to_video",
                "image_to_video",
                "video_to_video",
                "first_last_frame",
                "text_to_image",
            ],
            "features": ["multi_segment_chain", "long_form_i2v_chaining", "vram_aware_quantization"],
            "variants": list(WAN_VARIANTS.keys()),
        }

    def is_installed(self) -> bool:
        try:
            importlib.import_module("torch")
            importlib.import_module("diffusers")
            return True
        except ImportError:
            return False

    def install(self, on_progress: ProgressCallback | None = None, **_kwargs: Any) -> dict[str, Any]:
        if on_progress:
            on_progress({"phase": "verified", "progress": 1.0})
        return {"ok": self.is_installed()}

    def cancel(self) -> None:
        self._cancelled = True
        free_wan_pipelines()

    def _format_error(self, exc: BaseException) -> str:
        msg = str(exc)
        low = msg.lower()
        if "out of memory" in low or "oom" in low:
            return (
                f"CUDA out of memory during Wan generation ({msg}). "
                "Remediation: switch precision to 'int8' or 'int4' and offload_mode to 'sequential'."
            )
        if "nvml" in low or "driver" in low:
            return (
                f"CUDA/NVML driver initialization failure ({msg}). "
                "Check NVIDIA driver / CUDA compatibility or force precision='bf16'."
            )
        return msg

    def run(self, spec: dict[str, Any], on_progress: ProgressCallback | None = None) -> dict[str, Any]:
        self._cancelled = False
        profile = spec.get("profile")
        if profile is None:
            from studio_app import gpus
            profile = gpus.gpu_profile()

        if profile.get("tier") == "mac_8g_lite" or (profile.get("backend") == "mps" and float(profile.get("vram_gb") or 0) < 16):
            raise RuntimeError(
                "Wan 2.1/2.2 Diffusers video engine requires >=16 GB VRAM and is gated off on mac_8g_lite (8 GB Mac)."
            )

        operation = str(spec.get("operation") or "text_to_video").strip().lower()
        variant_key = str(spec.get("model_variant") or spec.get("model_id") or "wan2.2-ti2v-5b").removeprefix("wan_diffusers:")
        if variant_key not in WAN_VARIANTS:
            variant_key = "wan2.2-ti2v-5b"
        vinfo = WAN_VARIANTS[variant_key]

        if operation not in vinfo["ops"]:
            raise ValueError(f"Operation {operation!r} is not supported by variant {variant_key!r}")

        prompt = str(spec.get("prompt") or "").strip()
        seg_prompts = [str(p).strip() for p in (spec.get("segment_prompts") or []) if str(p).strip()]
        if not prompt and not seg_prompts:
            raise ValueError("Prompt must not be empty")
        if not prompt and seg_prompts:
            prompt = seg_prompts[0]

        if "num_frames" in spec and spec["num_frames"] is not None:
            raw_frames = int(spec["num_frames"])
            if raw_frames <= 0:
                raise ValueError(f"num_frames must be positive, got {raw_frames}")
        else:
            raw_frames = 1 if operation == "text_to_image" else 81

        torch = importlib.import_module("torch")
        diffusers = importlib.import_module("diffusers")
        pil_image = importlib.import_module("PIL.Image")
        np = importlib.import_module("numpy")
        imageio = importlib.import_module("imageio")

        vram_gb = float(profile.get("vram_gb") or 0.0)
        if hasattr(torch, "cuda") and torch.cuda.is_available():
            with contextlib.suppress(Exception):
                props = torch.cuda.get_device_properties(0)
                vram_gb = float(props.total_memory) / (1024**3)

        precision, offload_mode = _select_precision_and_offload(
            vram_gb,
            str(spec.get("precision") or "auto"),
            str(spec.get("offload_mode") or "auto"),
        )

        # Acquire GPU lease (evicting Ollama if active_llm_gb + media_vram_gb > 42 GB on 48G PC)
        media_vram_need = float(vinfo["vram_bf16_gb"]) if precision == "bf16" else 16.0
        acquire_media_lease(media_vram_gb=media_vram_need, model_key=variant_key, profile=profile)

        width = _snap_spatial(int(spec.get("width") or 640), 32)
        height = _snap_spatial(int(spec.get("height") or 384), 32)
        fps = int(spec.get("fps") or 24)
        raw_seed = spec.get("seed")
        seed = int(raw_seed) if raw_seed is not None else 42
        repo_id = str(vinfo["repo"])

        # Determine single vs multi-segment chain
        duration_s = float(spec.get("duration_seconds") or 0.0)
        seg_frames = _snap_temporal(int(spec.get("segment_frames") or 81))
        chainable = operation in ("text_to_video", "image_to_video")
        if operation == "text_to_image":
            total_segments = 1
            num_frames = 1
        elif not chainable:
            total_segments = 1
            if duration_s > 5.0 and "num_frames" not in spec:
                num_frames = 121
            else:
                num_frames = min(121, _snap_temporal(raw_frames))
        elif seg_prompts and len(seg_prompts) > 1:
            total_segments = len(seg_prompts)
            num_frames = seg_frames
        elif duration_s > 5.0:
            total_segments = max(2, int(round((duration_s * fps) / max(1, seg_frames - 1))))
            num_frames = seg_frames
        else:
            total_segments = 1
            num_frames = _snap_temporal(raw_frames)

        # Load quantized transformers if int8/int4
        load_kwargs: dict[str, Any] = {"torch_dtype": torch.bfloat16}
        if precision in ("int8", "int4"):
            q_kwargs = {"load_in_8bit": True} if precision == "int8" else {"load_in_4bit": True}
            q_cfg = diffusers.BitsAndBytesConfig(**q_kwargs)
            t1 = diffusers.WanTransformer3DModel.from_pretrained(
                repo_id,
                subfolder="transformer",
                quantization_config=q_cfg,
                torch_dtype=torch.bfloat16,
            )
            load_kwargs["transformer"] = t1
            if vinfo["is_moe"]:
                t2 = diffusers.WanTransformer3DModel.from_pretrained(
                    repo_id,
                    subfolder="transformer_2",
                    quantization_config=q_cfg,
                    torch_dtype=torch.bfloat16,
                )
                load_kwargs["transformer_2"] = t2

        def _configure_pipe(p: Any) -> Any:
            if hasattr(p, "vae"):
                if hasattr(p.vae, "enable_tiling"):
                    p.vae.enable_tiling()
                if hasattr(p.vae, "enable_slicing"):
                    p.vae.enable_slicing()
            if offload_mode == "sequential" and hasattr(p, "enable_sequential_cpu_offload"):
                p.enable_sequential_cpu_offload()
            elif hasattr(p, "enable_model_cpu_offload"):
                p.enable_model_cpu_offload()
            return p

        if on_progress:
            on_progress({"phase": "loading", "progress": 0.05})

        try:
            if operation in ("image_to_video", "first_last_frame"):
                base_pipe = _configure_pipe(diffusers.WanImageToVideoPipeline.from_pretrained(repo_id, **load_kwargs))
                i2v_pipe = base_pipe
            elif operation == "video_to_video":
                base_pipe = _configure_pipe(diffusers.WanVideoToVideoPipeline.from_pretrained(repo_id, **load_kwargs))
                i2v_pipe = None
            else:
                base_pipe = _configure_pipe(diffusers.WanPipeline.from_pretrained(repo_id, **load_kwargs))
                i2v_pipe = (
                    _configure_pipe(diffusers.WanImageToVideoPipeline.from_pipe(base_pipe))
                    if total_segments > 1
                    else None
                )

            all_frames: list[Any] = []
            ref_color_mean: Any = None
            anchor_img: Any = None

            if operation in ("image_to_video", "first_last_frame"):
                ref_path = Path(str(spec.get("reference_image_path") or spec.get("image_start") or ""))
                if not ref_path.is_file():
                    raise ValueError(f"Reference start image not found: {ref_path}")
                with pil_image.open(ref_path) as im:
                    anchor_img = im.convert("RGB").resize((width, height))

            last_img: Any = None
            if operation == "first_last_frame":
                last_path = Path(str(spec.get("last_image_path") or ""))
                if not last_path.is_file():
                    raise ValueError(f"Last frame image not found: {last_path}")
                with pil_image.open(last_path) as lim:
                    last_img = lim.convert("RGB").resize((width, height))

            for seg_idx in range(total_segments):
                if self._cancelled:
                    raise RuntimeError("Wan generation cancelled")

                seg_prompt = seg_prompts[seg_idx] if seg_idx < len(seg_prompts) else prompt
                gen = torch.Generator(device="cuda" if torch.cuda.is_available() else "cpu").manual_seed(seed + seg_idx)

                call_kwargs: dict[str, Any] = {
                    "prompt": seg_prompt,
                    "width": width,
                    "height": height,
                    "generator": gen,
                }
                if vinfo["is_moe"] and spec.get("guidance_scale_2") is not None:
                    call_kwargs["guidance_scale_2"] = float(spec["guidance_scale_2"])

                if operation == "video_to_video":
                    src_vid = Path(str(spec.get("source_video_path") or ""))
                    if not src_vid.is_file():
                        raise ValueError(f"Source video not found: {src_vid}")
                    vid_frames = [
                        pil_image.fromarray(np.asarray(f, dtype=np.uint8)).convert("RGB").resize((width, height))
                        for f in imageio.v3.imiter(str(src_vid))
                    ]
                    call_kwargs["video"] = vid_frames
                    call_kwargs["strength"] = float(spec.get("strength") or 0.7)
                    active_pipe = base_pipe
                elif seg_idx == 0 and operation in ("text_to_video", "text_to_image"):
                    call_kwargs["num_frames"] = num_frames
                    active_pipe = base_pipe
                else:
                    call_kwargs["num_frames"] = num_frames
                    call_kwargs["image"] = anchor_img
                    if operation == "first_last_frame":
                        call_kwargs["last_image"] = last_img
                    active_pipe = i2v_pipe if i2v_pipe is not None else base_pipe

                out = active_pipe(**call_kwargs)
                seg_result_frames = list(out.frames[0] if getattr(out, "frames", None) else out.images)

                if seg_idx == 0 and seg_result_frames:
                    ref_color_mean = np.asarray(seg_result_frames[0], dtype=np.float32).mean(axis=(0, 1))

                # Anchor frame for next segment is captured BEFORE drift correction so corner pixel markers propagate intact
                if seg_result_frames:
                    anchor_img = seg_result_frames[-1]

                if seg_idx > 0 and spec.get("correct_drift") and ref_color_mean is not None:
                    seg_result_frames = [
                        _match_color_drift(f, ref_color_mean, np, pil_image) for f in seg_result_frames
                    ]

                if seg_idx == 0:
                    all_frames.extend(seg_result_frames)
                else:
                    all_frames.extend(seg_result_frames[1:] if len(seg_result_frames) > 1 else seg_result_frames)

                if on_progress:
                    on_progress({
                        "phase": "generating",
                        "segment": seg_idx + 1,
                        "total_segments": total_segments,
                        "progress": round(0.1 + 0.85 * ((seg_idx + 1) / float(total_segments)), 4),
                    })

                if self._cancelled:
                    raise RuntimeError("Wan generation cancelled")

            out_path = Path(str(spec.get("output_path") or "wan_out.mp4"))
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if operation == "text_to_image":
                img0 = all_frames[0]
                if not hasattr(img0, "save"):
                    img0 = pil_image.fromarray(np.asarray(img0, dtype=np.uint8))
                img0.resize((width, height)).save(out_path, format="PNG")
            else:
                writer = imageio.get_writer(str(out_path), fps=fps)
                try:
                    for fr in all_frames:
                        writer.append_data(np.asarray(fr, dtype=np.uint8))
                finally:
                    writer.close()

            if on_progress:
                on_progress({"phase": "done", "progress": 1.0})

            return {
                "ok": True,
                "output_path": str(out_path),
                "outputs": [str(out_path)],
                "precision": precision,
                "offload_mode": offload_mode,
                "segments": total_segments,
                "width": width,
                "height": height,
            }
        except ValueError:
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                if hasattr(torch, "cuda") and torch.cuda.is_available():
                    torch.cuda.empty_cache()
            raise RuntimeError(self._format_error(exc)) from exc
