"""Local stable-diffusion.cpp (`sd-cli`) runner for Apple Silicon Metal, Windows/Linux CUDA, Vulkan, and CPU."""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
import platform as _platform
import random
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from typing import Any

from .base import LocalRunner, ProgressCallback
from .gpu_lease import acquire_media_lease

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_STEP_RE = re.compile(r"(?:step\s+(\d+)\s*/\s*(\d+)|(?<!\d)(\d+)\s*/\s*(\d+)\s*-\s*[\d.]+(?:s/it|it/s))", re.IGNORECASE)

MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "flux1-kontext-dev": {
        "kind": "flux_kontext",
        "file": "flux1-kontext-dev-Q6_K.gguf",
        "file_alternates": (
            "flux1-kontext-dev-Q8_0.gguf",
            "flux1-kontext-dev-Q6_K.gguf",
            "flux1-kontext-dev-Q5_K_M.gguf",
            "flux1-kontext-dev-Q4_K_M.gguf",
            "flux1-kontext-dev-Q4_K_S.gguf",
        ),
        "clip_l": "clip_l.safetensors",
        "t5xxl": "t5xxl_fp8_e4m3fn.safetensors",
        "t5xxl_alternates": (
            "t5xxl_fp8_e4m3fn.safetensors",
            "t5xxl_fp8_e4m3fn_scaled.safetensors",
            "t5xxl_fp16.safetensors",
            "t5-v1_1-xxl-encoder-Q5_K_M.gguf",
            "t5-v1_1-xxl-encoder-Q8_0.gguf",
        ),
        "vae": "ae.safetensors",
        "base_size": 1024,
        "steps": 20,
        "cfg_scale": 1.0,
        "guidance": 2.5,
        "sampling_method": "euler",
        "vram_gb": 11.5,
        "supports_ref_images": True,
        "supports_mask": True,
        "best_for_edit": True,
        "label": "FLUX.1 Kontext Dev (12B GGUF)",
        "summary": "Best free local model for locked-camera edits, room continuity, and character identity preservation.",
        "downloads": [
            {
                "file": "flux1-kontext-dev-Q6_K.gguf",
                "url": "https://huggingface.co/QuantStack/FLUX.1-Kontext-dev-GGUF/resolve/main/flux1-kontext-dev-Q6_K.gguf",
                "gb": 9.8,
            },
            {
                "file": "clip_l.safetensors",
                "url": "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors",
                "gb": 0.24,
            },
            {
                "file": "t5xxl_fp8_e4m3fn.safetensors",
                "url": "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors",
                "gb": 4.9,
            },
            {
                "file": "ae.safetensors",
                "url": "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors",
                "gb": 0.32,
            },
        ],
    },
    "flux2-klein-9b": {
        "kind": "flux2",
        "file": "flux-2-klein-9b-Q8_0.gguf",
        "file_alternates": (
            "flux-2-klein-9b-Q8_0.gguf",
            "flux-2-klein-9b-Q6_K.gguf",
            "flux-2-klein-9b-Q5_K_M.gguf",
            "flux-2-klein-9b-Q4_K_M.gguf",
        ),
        "llm": "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf",
        "vae": "flux2_ae.safetensors",
        "base_size": 1024,
        "steps": 4,
        "cfg_scale": 1.0,
        "sampling_method": "euler",
        "vram_gb": 12.0,
        "supports_ref_images": True,
        "supports_mask": True,
        "label": "FLUX.2 Klein 9B (GGUF)",
        "summary": "Fast 4-step multi-reference upgrade over 4B Klein; reuses your existing Qwen3 LLM and FLUX.2 VAE.",
        "downloads": [
            {
                "file": "flux-2-klein-9b-Q8_0.gguf",
                "url": "https://huggingface.co/leejet/FLUX.2-klein-9B-GGUF/resolve/main/flux-2-klein-9b-Q8_0.gguf",
                "gb": 9.4,
            },
        ],
    },
    "flux2-klein-4b": {
        "kind": "flux2",
        "file": "flux-2-klein-4b-Q8_0.gguf",
        "llm": "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf",
        "vae": "flux2_ae.safetensors",
        "base_size": 1024,
        "steps": 4,
        "cfg_scale": 1.0,
        "sampling_method": "euler",
        "vram_gb": 8.0,
        "supports_ref_images": True,
        "supports_mask": True,
        "label": "FLUX.2 Klein 4B (Installed)",
        "summary": "Fast 4B multi-reference generator already installed on disk.",
    },
    "z-image-turbo": {
        "kind": "z-image",
        "file": "z_image_turbo-Q4_K.gguf",
        "llm": "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf",
        "vae": "ae.safetensors",
        "base_size": 1024,
        "steps": 4,
        "cfg_scale": 1.0,
        "scheduler": "discrete",
        "vram_gb": 4.0,
    },
    "z-image-base": {
        "kind": "z-image",
        "file": "z_image-Q4_K.gguf",
        "llm": "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf",
        "vae": "ae.safetensors",
        "base_size": 1024,
        "steps": 20,
        "cfg_scale": 3.5,
        "scheduler": "discrete",
        "vram_gb": 4.5,
    },
    "dreamshaper-8": {
        "kind": "sd1",
        "file": "DreamShaper_8_pruned.safetensors",
        "base_size": 512,
        "steps": 20,
        "cfg_scale": 7.0,
        "vram_gb": 2.5,
    },
    "realistic-vision-v51": {
        "kind": "sd1",
        "file": "Realistic_Vision_V5.1_fp16-no-ema.safetensors",
        "base_size": 512,
        "steps": 20,
        "cfg_scale": 7.0,
        "vram_gb": 2.5,
    },
    "anything-v5": {
        "kind": "sd1",
        "file": "anythingV5_fp16.safetensors",
        "base_size": 512,
        "steps": 20,
        "cfg_scale": 7.0,
        "vram_gb": 2.5,
    },
    "stable-diffusion-xl-base": {
        "kind": "sdxl",
        "file": "sd_xl_base_1.0.safetensors",
        "base_size": 1024,
        "steps": 25,
        "cfg_scale": 7.0,
        "vram_gb": 6.5,
    },
}

_ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "1:1": (1, 1),
    "16:9": (16, 9),
    "9:16": (9, 16),
    "4:3": (4, 3),
    "3:4": (3, 4),
    "21:9": (21, 9),
}


def compute_dimensions(base_size: int, aspect_ratio: str = "1:1") -> tuple[int, int]:
    """Compute width and height rounded to multiples of 64 preserving base_size on the reference axis."""
    num, den = _ASPECT_RATIOS.get(aspect_ratio.strip(), (1, 1))
    if num == den:
        return base_size, base_size
    if num > den:
        h = base_size
        w = max(64, int(round((base_size * num / den) / 64.0)) * 64)
        return w, h
    w = base_size
    h = max(64, int(round((base_size * den / num) / 64.0)) * 64)
    return w, h


def rank_windows_assets(zip_names: list[str], gpu: str | None = "nvidia") -> list[str]:
    """Rank Windows sd-cli release archives with automatic fallback chain (CUDA -> Vulkan -> CPU)."""
    candidates = [n for n in zip_names if not n.lower().startswith("cudart-") and n.lower().endswith(".zip")]
    cuda_zips = [n for n in candidates if "cuda" in n.lower() or "cu12" in n.lower()]
    vulkan_zips = [n for n in candidates if "vulkan" in n.lower()]
    cpu_zips = [n for n in candidates if "cpu" in n.lower() or "avx" in n.lower() or (n not in cuda_zips and n not in vulkan_zips)]

    if gpu == "nvidia":
        return cuda_zips + vulkan_zips + cpu_zips
    if gpu in ("other", "amd", "intel"):
        return vulkan_zips + cpu_zips
    return cpu_zips


def pick_binary_asset(
    platform: str,
    arch: str,
    zip_names: list[str],
    gpu: str | None = "nvidia",
) -> str | None:
    """Pick the best sd-cli release zip for (platform, arch, gpu)."""
    if not zip_names:
        return None
    if platform == "darwin":
        if arch != "arm64":
            raise RuntimeError("sd-cli on macOS requires Apple Silicon (arm64); Intel x86_64 Macs are unsupported")
        for n in zip_names:
            low = n.lower()
            if ("darwin" in low or "macos" in low) and "arm64" in low:
                return n
        return None
    if platform == "win32":
        ranked = rank_windows_assets(zip_names, gpu=gpu)
        return ranked[0] if ranked else None
    for n in zip_names:
        if "linux" in n.lower():
            return n
    return zip_names[0]


def describe_exit_code(code: int, platform: str = sys.platform) -> str:
    """Translate OS/NTSTATUS crash exit codes into actionable error diagnostics."""
    unsigned = code & 0xFFFFFFFF
    if platform == "win32" or unsigned >= 0xC0000000:
        if unsigned == 0xC0000135:
            return "sd-cli failed to start (0xC0000135 STATUS_DLL_NOT_FOUND): missing CUDA runtime DLL or MSVC Visual C++ Redistributable"
        if unsigned == 0xC0000005:
            return "sd-cli crashed (0xC0000005 STATUS_ACCESS_VIOLATION): GPU driver or memory access fault"
        if unsigned == 0xC0000409:
            return "sd-cli crashed (0xC0000409 STATUS_STACK_BUFFER_OVERRUN)"
    return f"sd-cli exited with code {code}"


class SdCliRunner(LocalRunner):
    """Spawns stable-diffusion.cpp `sd-cli` for GGUF and safetensors local image generation."""

    name = "sd_cli"

    def __init__(self, bin_dir: Path | str | None = None, models_dir: Path | str | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.bin_dir = Path(bin_dir) if bin_dir is not None else (root / ".local_ai" / "bin")
        self.models_dir = Path(models_dir) if models_dir is not None else (root / "models" / "sd_cli")
        self._proc: subprocess.Popen[Any] | None = None
        self._lock = threading.Lock()
        self._cancelled = False

    def _exe_path(self) -> Path:
        override = os.environ.get("OPEN_GENERATIVE_AI_SD_CLI", "").strip()
        if override:
            return Path(override)
        exe_name = "sd-cli.exe" if sys.platform == "win32" else "sd-cli"
        return self.bin_dir / exe_name

    def capabilities(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tasks": ["image"],
            "models": list(MODEL_CATALOG.keys()),
            "backends": ["metal", "cuda", "vulkan", "cpu"],
        }

    def is_installed(self) -> bool:
        exe = self._exe_path()
        return exe.is_file()

    def _resolve_model_file(self, names: str | tuple[str, ...]) -> Path | None:
        """Return the first existing weight file in `self.models_dir` from a filename or tuple of alternates."""
        cands = (names,) if isinstance(names, str) else tuple(names)
        for fname in cands:
            p = self.models_dir / fname
            if p.is_file():
                return p
        return None

    def ready_models(
        self,
        *,
        require_ref_support: bool = False,
        prefer_edit: bool = False,
    ) -> list[str]:
        """Return catalog model IDs whose required weight files exist in `self.models_dir`, ordered best-first."""
        if require_ref_support and prefer_edit:
            order: tuple[str, ...] = ("flux1-kontext-dev", "flux2-klein-9b", "flux2-klein-4b")
        elif require_ref_support:
            order = ("flux2-klein-9b", "flux1-kontext-dev", "flux2-klein-4b")
        else:
            order = (
                "z-image-turbo",
                "flux2-klein-9b",
                "flux1-kontext-dev",
                "flux2-klein-4b",
                "z-image-base",
                "stable-diffusion-xl-base",
                "dreamshaper-8",
                "realistic-vision-v51",
                "anything-v5",
            )
        ready: list[str] = []
        for mid in order:
            entry = MODEL_CATALOG.get(mid)
            if not entry:
                continue
            if require_ref_support and not entry.get("supports_ref_images"):
                continue
            main_cands = entry.get("file_alternates") or entry["file"]
            if self._resolve_model_file(main_cands) is None:
                continue
            if entry["kind"] in ("z-image", "flux2"):
                if not (self.models_dir / entry["llm"]).is_file() or not (self.models_dir / entry["vae"]).is_file():
                    continue
            elif entry["kind"] == "flux_kontext":
                t5_cands = entry.get("t5xxl_alternates") or entry["t5xxl"]
                if (
                    not (self.models_dir / entry["clip_l"]).is_file()
                    or self._resolve_model_file(t5_cands) is None
                    or not (self.models_dir / entry["vae"]).is_file()
                ):
                    continue
            ready.append(mid)
        return ready

    def describe_consistency_models(self) -> list[dict[str, Any]]:
        """Return install status and missing weight info for free local consistency models."""
        out: list[dict[str, Any]] = []
        ready_set = set(self.ready_models(require_ref_support=True))
        for mid in ("flux1-kontext-dev", "flux2-klein-9b", "flux2-klein-4b"):
            entry = MODEL_CATALOG[mid]
            missing: list[dict[str, Any]] = []
            for dl in entry.get("downloads") or []:
                fname = str(dl["file"])
                # Treat alternate quants as satisfying the main weight or t5xxl slot
                if fname == entry.get("file") and self._resolve_model_file(entry.get("file_alternates") or fname):
                    continue
                if fname == entry.get("t5xxl") and self._resolve_model_file(entry.get("t5xxl_alternates") or fname):
                    continue
                if not (self.models_dir / fname).is_file():
                    missing.append(dict(dl))
            out.append({
                "id": mid,
                "label": entry.get("label") or mid,
                "summary": entry.get("summary") or "",
                "vram_gb": entry.get("vram_gb", 8.0),
                "ready": mid in ready_set,
                "missing_files": missing,
                "missing_gb": round(sum(float(m.get("gb", 0.0)) for m in missing), 2),
                "models_dir": str(self.models_dir),
            })
        return out

    def install(
        self,
        on_progress: ProgressCallback | None = None,
        *,
        platform: str | None = None,
        arch: str | None = None,
        download_url: str | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        plat = platform or sys.platform
        machine = arch or _platform.machine().lower()
        if plat == "darwin" and machine not in ("arm64", "aarch64"):
            raise RuntimeError("sd-cli on macOS requires Apple Silicon (arm64)")

        self.bin_dir.mkdir(parents=True, exist_ok=True)
        url = download_url or os.environ.get(
            "SD_CLI_DOWNLOAD_URL",
            "https://github.com/Anil-matcha/Open-Generative-AI/releases/download/v1.0.3-binaries/sd-cli-metal-macos-arm64.zip",
        )

        with tempfile.TemporaryDirectory(prefix="neon-sdcli-") as tmp_str:
            tmp_zip = Path(tmp_str) / "sd-cli.zip"
            with urllib.request.urlopen(url, timeout=60.0) as resp:
                tmp_zip.write_bytes(resp.read())
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    fname = Path(member.filename).name
                    if not fname:
                        continue
                    dest = self.bin_dir / fname
                    dest.write_bytes(zf.read(member))
                    if fname in ("sd-cli", "sd-cli.exe") or fname.endswith((".dylib", ".so")):
                        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        if plat == "darwin" and shutil.which("xattr"):
            subprocess.run(["xattr", "-cr", str(self.bin_dir)], check=False, capture_output=True)

        if on_progress:
            on_progress({"phase": "installed", "progress": 1.0})
        return {"ok": True, "binary": str(self._exe_path())}

    def cancel(self) -> None:
        self._cancelled = True
        with self._lock:
            proc = self._proc
        if proc is not None:
            try:
                from studio_app import procs
                if procs.pid_alive(proc.pid):
                    procs.stop_group(proc.pid, hard=True)
            except Exception:
                with contextlib.suppress(Exception):
                    proc.kill()

    def run(self, spec: dict[str, Any], on_progress: ProgressCallback | None = None) -> dict[str, Any]:
        self._cancelled = False
        exe = self._exe_path()
        if not exe.is_file():
            raise RuntimeError(f"sd-cli binary is not installed at {exe}")

        raw_model = str(spec.get("model") or spec.get("model_id") or "z-image-turbo").removeprefix("sd_cli:")
        if raw_model not in MODEL_CATALOG:
            raise ValueError(f"Unknown sd-cli model {raw_model!r}")
        entry = MODEL_CATALOG[raw_model]

        main_cands = entry.get("file_alternates") or entry["file"]
        model_file = self._resolve_model_file(main_cands)
        if model_file is None:
            raise RuntimeError(f"Missing model file for {raw_model}: {self.models_dir / entry['file']}")

        acquire_media_lease(media_vram_gb=float(entry.get("vram_gb", 4.0)), model_key=raw_model, profile=spec.get("profile"))

        aspect = str(spec.get("aspect_ratio") or "1:1")
        w, h = compute_dimensions(int(entry["base_size"]), aspect)
        if spec.get("width"):
            w = int(spec["width"])
        if spec.get("height"):
            h = int(spec["height"])

        raw_steps = spec.get("steps")
        steps = int(raw_steps) if isinstance(raw_steps, (int, float)) and int(raw_steps) > 0 else int(entry["steps"])

        if "guidance_scale" in spec and spec["guidance_scale"] is not None:
            cfg = float(spec["guidance_scale"])
        elif "cfg_scale" in spec and spec["cfg_scale"] is not None:
            cfg = float(spec["cfg_scale"])
        else:
            cfg = float(entry["cfg_scale"])

        raw_seed = spec.get("seed", 42)
        seed = int(raw_seed) if raw_seed is not None else 42
        if seed < 0:
            seed = random.randint(0, (1 << 31) - 1)

        out_path = Path(str(spec.get("output_path") or (self.models_dir / "out.png")))
        out_path.parent.mkdir(parents=True, exist_ok=True)

        argv: list[str] = [str(exe)]
        if entry["kind"] in ("z-image", "flux2"):
            llm_file = self.models_dir / entry["llm"]
            vae_file = self.models_dir / entry["vae"]
            if not llm_file.is_file():
                raise RuntimeError(f"Missing auxiliary LLM file for {raw_model}: {llm_file}")
            if not vae_file.is_file():
                raise RuntimeError(f"Missing auxiliary VAE file for {raw_model}: {vae_file}")
            argv.extend([
                "--diffusion-model", str(model_file),
                "--llm", str(llm_file),
                "--vae", str(vae_file),
            ])
            if entry.get("scheduler"):
                argv.extend(["--scheduler", str(entry["scheduler"])])
            if entry.get("sampling_method"):
                argv.extend(["--sampling-method", str(entry["sampling_method"])])
            if entry["kind"] == "flux2":
                argv.extend(["--flash-attn", "on"])
        elif entry["kind"] == "flux_kontext":
            clip_file = self.models_dir / entry["clip_l"]
            t5_cands = entry.get("t5xxl_alternates") or entry["t5xxl"]
            t5_file = self._resolve_model_file(t5_cands)
            vae_file = self.models_dir / entry["vae"]
            if not clip_file.is_file():
                raise RuntimeError(f"Missing clip_l file for {raw_model}: {clip_file}")
            if t5_file is None:
                raise RuntimeError(f"Missing t5xxl file for {raw_model}: {self.models_dir / entry['t5xxl']}")
            if not vae_file.is_file():
                raise RuntimeError(f"Missing VAE file for {raw_model}: {vae_file}")
            argv.extend([
                "--diffusion-model", str(model_file),
                "--clip_l", str(clip_file),
                "--t5xxl", str(t5_file),
                "--vae", str(vae_file),
                "--flash-attn", "on",
            ])
            if entry.get("sampling_method"):
                argv.extend(["--sampling-method", str(entry["sampling_method"])])
            if entry.get("guidance") is not None:
                argv.extend(["--guidance", str(float(spec.get("guidance") or entry["guidance"]))])
        else:
            argv.extend(["-m", str(model_file)])

        prompt = str(spec.get("prompt") or "")
        argv.extend([
            "-p", prompt,
            "-W", str(w),
            "-H", str(h),
            "--steps", str(steps),
            "--cfg-scale", str(cfg),
            "--seed", str(seed),
            "-o", str(out_path),
        ])
        neg = str(spec.get("negative_prompt") or "").strip()
        if neg:
            argv.extend(["-n", neg])
        init_img = str(spec.get("init_image") or "").strip()
        if init_img and Path(init_img).is_file():
            argv.extend(["-i", init_img, "--strength", str(float(spec.get("strength", 0.72)))])
        mask_img = str(spec.get("mask_image") or "").strip()
        if mask_img and Path(mask_img).is_file():
            argv.extend(["--mask", mask_img])
            if spec.get("img_cfg_scale") is not None:
                argv.extend(["--img-cfg-scale", str(float(spec["img_cfg_scale"]))])
        if entry.get("supports_ref_images"):
            for ref_p in spec.get("ref_images") or []:
                if ref_p and Path(str(ref_p)).is_file():
                    argv.extend(["-r", str(ref_p)])

        env = dict(os.environ)
        bin_str = str(self.bin_dir)
        if sys.platform == "win32":
            env["PATH"] = f"{bin_str};{env.get('PATH', '')}".rstrip(";")
        env["DYLD_LIBRARY_PATH"] = f"{bin_str}:{env.get('DYLD_LIBRARY_PATH', '')}".rstrip(":")
        env["LD_LIBRARY_PATH"] = f"{bin_str}:{env.get('LD_LIBRARY_PATH', '')}".rstrip(":")

        from studio_app import procs
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
             env=env,
            **procs.group_kwargs(),
        )
        self.attach_process(proc)

        highest_step = 0
        output_lines: list[str] = []
        try:
            assert proc.stdout is not None
            buf = ""
            while True:
                chunk = proc.stdout.read(256)
                if not chunk:
                    break
                text = _ANSI_RE.sub("", chunk.decode("utf-8", "replace"))
                buf += text
                parts = re.split(r"[\r\n]+", buf)
                buf = parts.pop()
                for seg in parts:
                    s_clean = seg.strip()
                    if not s_clean:
                        continue
                    output_lines.append(s_clean)
                    for m in _STEP_RE.finditer(s_clean):
                        cur = int(m.group(1) or m.group(3))
                        tot = int(m.group(2) or m.group(4))
                        if tot > 0 and cur > highest_step:
                            highest_step = cur
                            prog = min(1.0, cur / float(tot))
                            if on_progress:
                                on_progress({"step": cur, "steps": tot, "progress": prog})
            if buf.strip():
                s_clean = _ANSI_RE.sub("", buf.strip())
                output_lines.append(s_clean)
                for m in _STEP_RE.finditer(s_clean):
                    cur = int(m.group(1) or m.group(3))
                    tot = int(m.group(2) or m.group(4))
                    if tot > 0 and cur > highest_step:
                        highest_step = cur
                        if on_progress:
                            on_progress({"step": cur, "steps": tot, "progress": min(1.0, cur / float(tot))})
            rc = proc.wait()
        finally:
            with self._lock:
                self._proc = None

        if self._cancelled:
            raise RuntimeError("sd-cli generation was cancelled")
        if rc != 0:
            tail = " | ".join(output_lines[-5:])
            raise RuntimeError(f"{describe_exit_code(rc)}: {tail}")
        if not out_path.is_file() or out_path.stat().st_size == 0:
            raise RuntimeError(f"sd-cli exited 0 but did not write output image at {out_path}")

        return {
            "ok": True,
            "model": raw_model,
            "output_path": str(out_path),
            "outputs": [str(out_path)],
            "width": w,
            "height": h,
            "seed": seed,
        }

    def attach_process(self, proc: subprocess.Popen[Any]) -> None:
        with self._lock:
            self._proc = proc
