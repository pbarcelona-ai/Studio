"""Hardware-aware local runner router and LocalAudioRunner adapter."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import LocalRunner, ProgressCallback
from .comfyui_runner import ComfyUIRunner
from .gpu_lease import acquire_media_lease
from .sd_cli_runner import SdCliRunner
from .wan2gp_runner import Wan2GPRunner
from .wan_diffusers_runner import WAN_VARIANTS, WanDiffusersRunner

_VALID_TASKS = {"image", "video", "vfx", "upscale", "audio", "inpaint"}


class LocalAudioRunner(LocalRunner):
    """Local audio runner wrapping `scripts/local_audio.py` (Kokoro-82M TTS and MusicGen-small) with GPU lease integration."""

    name = "local_audio"

    def __init__(self, model_id: str = "kokoro") -> None:
        self.model_id = model_id

    def capabilities(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tasks": ["audio"],
            "models": ["kokoro", "audiobook", "musicgen", "musicgen-small", "musicgen_scenes"],
        }

    def is_installed(self) -> bool:
        return (Path(__file__).resolve().parents[1] / "local_audio.py").is_file()

    def install(self, on_progress: ProgressCallback | None = None, **_kwargs: Any) -> dict[str, Any]:
        if on_progress:
            on_progress({"phase": "verified", "progress": 1.0})
        return {"ok": True}

    def cancel(self) -> None:
        return None

    def run(self, spec: dict[str, Any], on_progress: ProgressCallback | None = None) -> dict[str, Any]:
        import local_audio

        profile = spec.get("profile")
        ollama_url = spec.get("ollama_url")
        acquire_media_lease(media_vram_gb=1.5, model_key=self.model_id, profile=profile, ollama_url=ollama_url)

        pdir_raw = spec.get("project_dir") or spec.get("project")
        if not pdir_raw:
            raise ValueError("Missing project_dir for LocalAudioRunner")
        pdir = Path(str(pdir_raw))
        kind = str(spec.get("kind") or self.model_id or "kokoro").lower()
        if kind in ("kokoro", "narration"):
            local_audio.narration(pdir)
            out_dir = pdir / "audio" / "kokoro"
        elif kind == "audiobook":
            local_audio.narration(pdir, "audiobook.csv", "kokoro_audiobook")
            out_dir = pdir / "audio" / "kokoro_audiobook"
        elif kind in ("musicgen", "musicgen-small", "musicgen_chapters"):
            local_audio.music(pdir, scenes=False)
            out_dir = pdir / "audio" / "musicgen_chapters"
        elif kind == "musicgen_scenes":
            local_audio.music(pdir, scenes=True)
            out_dir = pdir / "audio" / "musicgen_scenes"
        else:
            raise ValueError(f"Unsupported local audio kind {kind!r}")

        files = sorted(str(p) for p in out_dir.glob("*.wav")) if out_dir.is_dir() else []
        if on_progress:
            on_progress({"phase": "done", "progress": 1.0})
        return {"ok": True, "kind": kind, "outputs": files, "output_dir": str(out_dir)}


def select_runner(
    task_kind: str,
    model_id: str | None = None,
    *,
    profile: dict[str, Any] | None = None,
) -> LocalRunner:
    """Select the appropriate LocalRunner implementation for `(task_kind, model_id, profile)`."""
    task = str(task_kind or "").strip().lower()
    if not task or task not in _VALID_TASKS:
        raise ValueError(f"Unsupported or empty local task kind {task_kind!r}; expected one of {sorted(_VALID_TASKS)}")

    if profile is None:
        from studio_app import gpus
        profile = gpus.gpu_profile()

    mid = str(model_id or "").strip()
    mid_low = mid.lower()
    tier = str(profile.get("tier") or "cpu")
    vram_gb = float(profile.get("vram_gb") or 0.0)
    backend = str(profile.get("backend") or "cpu")

    # Audio is always supported locally via Kokoro-82M / MusicGen-small
    if task == "audio":
        return LocalAudioRunner(model_id=mid or "kokoro")

    # CPU-only profile cannot run GPU image/video models
    if tier == "cpu" or backend == "cpu" or not profile.get("supports_local_images", True):
        raise RuntimeError(f"No local GPU available for {task} generation (detected tier={tier!r}, backend={backend!r})")

    # Video gating on 8 GB Mac (mac_8g_lite), <24 GB MPS, or low_vram GPUs
    if task == "video":
        if tier == "mac_8g_lite" or (backend == "mps" and vram_gb < 24.0) or not profile.get("supports_local_video", False):
            raise RuntimeError(
                f"Local video generation is gated off on {tier} ({vram_gb:g} GB VRAM/unified memory); "
                "heavy video models require at least 12 GB NVIDIA VRAM or 24 GB unified memory."
            )

    # Explicit prefix or variant routing
    if mid_low.startswith("sd_cli:"):
        return SdCliRunner()
    if mid_low.startswith("wan2gp:"):
        return Wan2GPRunner()
    if mid_low.startswith("wan_diffusers:") or mid_low in WAN_VARIANTS:
        if tier == "mac_8g_lite":
            raise RuntimeError("Wan 2.1/2.2 Diffusers video engine is gated off on 8 GB Mac (mac_8g_lite)")
        return WanDiffusersRunner()

    # Tier-default routing
    if tier == "mac_8g_lite" or backend == "mps":
        if task == "image":
            return SdCliRunner()
        if task == "video":
            return Wan2GPRunner()

    return ComfyUIRunner()
