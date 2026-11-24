"""Phase 1 platform hardware matrix tests: Windows 5090 (full_48g), 8 GB Mac (mac_8g_lite), RAM detection, Blackwell cu128, and STUDIO_LEGACY_CLOUD=1 gating."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_local_model as rl
from studio_app import gpus, llm, providers

WIN_5090 = {
    "name": "NVIDIA GeForce RTX 5090",
    "vendor": "NVIDIA",
    "gb": 48.0,
    "shared": False,
    "cap": "12.0",
    "nvidia_ready": True,
    "rocm_ready": False,
    "mps_ready": False,
}

MAC_8G = {
    "name": "Apple M2",
    "vendor": "Apple",
    "gb": 8.0,
    "shared": True,
    "cap": "MPS",
    "nvidia_ready": False,
    "rocm_ready": False,
    "mps_ready": True,
}

ROCM_24G = {
    "name": "AMD Radeon RX 7900 XTX",
    "vendor": "AMD",
    "gb": 24.0,
    "shared": False,
    "cap": "gfx1100",
    "nvidia_ready": False,
    "rocm_ready": True,
    "mps_ready": False,
}


def test_win32_rtx_5090_blackwell_full_48g(monkeypatch, tmp_path, book, fake_root):
    monkeypatch.setattr(gpus.sys, "platform", "win32")
    monkeypatch.setattr(gpus, "all_gpus", lambda: [WIN_5090])
    monkeypatch.setattr(gpus, "system_ram_gb", lambda: 64.0)
    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)

    assert gpus.local_gpus() == [("NVIDIA GeForce RTX 5090", 48.0, "12.0")]
    assert gpus.local_is_amd() is False
    assert gpus.local_is_mps() is False
    assert rl.gpu_problem([WIN_5090], "win32") is None

    prof = gpus.gpu_profile()
    assert prof == {
        "platform": "win32",
        "backend": "cuda",
        "name": "NVIDIA GeForce RTX 5090",
        "vram_gb": 48.0,
        "ram_gb": 64.0,
        "compute_cap": "12.0",
        "is_blackwell": True,
        "tier": "full_48g",
        "supports_local_video": True,
        "supports_local_images": True,
        "default_image_backend": "comfyui",
        "default_video_backend": "comfyui",
        "legacy_cloud": False,
    }

    opts = rl.gpu_optimizations("NVIDIA GeForce RTX 5090", "12.0", 48.0)
    assert opts["use_bf16"] is True
    assert opts["use_flash_attn"] is True
    assert opts["use_torch_compile"] is True
    assert opts["allow_cpu_offload"] is False

    opts_small = rl.gpu_optimizations("NVIDIA GeForce RTX 5070", "12.0", 12.0)
    assert opts_small["allow_cpu_offload"] is True
    assert opts_small["memory_fraction"] == 0.80

    nb_path = tmp_path / "nb.ipynb"
    nb_path.write_text(json.dumps({
        "cells": [{
            "cell_type": "code",
            "source": [
                "# pipe.enable_model_cpu_offload()\n",
                "pipe.enable_model_cpu_offload()\n",
                "pipe2.enable_sequential_cpu_offload()\n",
            ],
        }]
    }), encoding="utf-8")

    script_no_offload, _ = rl.to_script(nb_path, 1, 1, "all_shots.csv", tmp_path, tmp_path, opts)
    assert "_ALLOW_CPU_OFFLOAD = False" in script_no_offload
    assert "\npipe.to(_device)\n" in script_no_offload
    assert "\npipe2.to(_device)\n" in script_no_offload
    assert "# pipe.enable_model_cpu_offload()" in script_no_offload
    compile(script_no_offload, "gen_no_offload.py", "exec")

    script_with_offload, _ = rl.to_script(nb_path, 1, 1, "all_shots.csv", tmp_path, tmp_path, opts_small)
    assert "_ALLOW_CPU_OFFLOAD = True" in script_with_offload
    assert "pipe.enable_model_cpu_offload()" in script_with_offload

    # Verify main() sets BLACKWELL_TORCH_INDEX when STUDIO_TORCH_INDEX is unset
    monkeypatch.setattr(rl, "ROOT", fake_root)
    monkeypatch.setattr(rl, "detect_gpus", lambda: [WIN_5090])
    monkeypatch.setattr(rl, "gpu_problem", lambda gpus_list, platform=None: None)
    monkeypatch.setattr(rl, "find_notebook", lambda model, tmp: nb_path)
    monkeypatch.setattr(rl, "make_env", lambda pip, log, gpu_opts=None: Path(sys.executable))
    monkeypatch.setattr(rl, "run_logged", lambda argv, log, cwd=None, env=None, **kw: 0)
    monkeypatch.setenv("PROJECT", "demo")
    monkeypatch.setenv("STUDIO_TORCH_INDEX", "")
    monkeypatch.delenv("STUDIO_TORCH_INDEX", raising=False)
    monkeypatch.delenv("SHOTS_CSV", raising=False)

    with pytest.raises(SystemExit) as exc:
        rl.main(["ltx_video", "1", "1"])
    assert exc.value.code == 0
    assert rl.os.environ["STUDIO_TORCH_INDEX"] == rl.BLACKWELL_TORCH_INDEX

    # Respects explicit STUDIO_TORCH_INDEX override
    monkeypatch.setenv("STUDIO_TORCH_INDEX", "https://custom.example/cu129")
    with pytest.raises(SystemExit) as exc2:
        rl.main(["ltx_video", "1", "1"])
    assert exc2.value.code == 0
    assert rl.os.environ["STUDIO_TORCH_INDEX"] == "https://custom.example/cu129"


def test_darwin_8gb_apple_silicon_mac_8g_lite(monkeypatch):
    monkeypatch.setattr(gpus.sys, "platform", "darwin")
    monkeypatch.setattr(gpus, "all_gpus", lambda: [MAC_8G])
    monkeypatch.setattr(gpus, "system_ram_gb", lambda: 8.0)
    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)

    assert gpus.local_gpus() == [("Apple M2", 8.0, "MPS")]
    assert gpus.local_is_amd() is False
    assert gpus.local_is_mps() is True
    assert rl.gpu_problem([MAC_8G], "darwin") is None

    prof = gpus.gpu_profile()
    assert prof == {
        "platform": "darwin",
        "backend": "mps",
        "name": "Apple M2",
        "vram_gb": 8.0,
        "ram_gb": 8.0,
        "compute_cap": "MPS",
        "is_blackwell": False,
        "tier": "mac_8g_lite",
        "supports_local_video": False,
        "supports_local_images": True,
        "default_image_backend": "sd_cli",
        "default_video_backend": "none",
        "legacy_cloud": False,
    }

    # Verify llm.local_llm_status accepts 8 GB Apple Silicon in lite tier
    import platform as _platform
    import urllib.request

    monkeypatch.setattr(_platform, "system", lambda: "Darwin")
    monkeypatch.setattr(_platform, "machine", lambda: "arm64")
    monkeypatch.setattr(llm.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=str(8 * 2**30)))
    monkeypatch.delenv("STUDIO_LOCAL_LLM", raising=False)

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"data": [{"id": "qwen2.5:3b"}]}).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())
    st = llm.local_llm_status(force=True)
    assert st["ready"] is True
    assert st["tier"] == "lite"
    assert st["memory_gb"] == 8
    assert "qwen2.5:3b" in st["recommended_models"]


def test_gpu_profile_rocm_standard_and_cpu_fallbacks(monkeypatch):
    monkeypatch.setattr(gpus, "system_ram_gb", lambda: 32.0)

    monkeypatch.setattr(gpus.sys, "platform", "linux")
    monkeypatch.setattr(gpus, "all_gpus", lambda: [ROCM_24G])
    rocm_prof = gpus.gpu_profile()
    assert rocm_prof["backend"] == "rocm"
    assert rocm_prof["tier"] == "standard_gpu"
    assert rocm_prof["ram_gb"] == 32.0
    assert rocm_prof["supports_local_video"] is True

    monkeypatch.setattr(gpus, "all_gpus", lambda: [])
    cpu_prof = gpus.gpu_profile()
    assert cpu_prof["backend"] == "cpu"
    assert cpu_prof["tier"] == "cpu"
    assert cpu_prof["ram_gb"] == 32.0
    assert cpu_prof["supports_local_images"] is False
    assert cpu_prof["supports_local_video"] is False


def test_system_ram_gb_platforms(monkeypatch):
    monkeypatch.setattr(gpus.sys, "platform", "darwin")
    monkeypatch.setattr(gpus.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=str(8 * 2**30)))
    assert gpus.system_ram_gb() == 8.0

    monkeypatch.setattr(gpus.sys, "platform", "linux")
    monkeypatch.setattr(gpus.os, "sysconf", lambda k: 4096 if k == "SC_PAGE_SIZE" else (64 * 2**30) // 4096, raising=False)
    assert gpus.system_ram_gb() == 64.0

    import ctypes

    monkeypatch.setattr(gpus.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "windll", None, raising=False)
    assert gpus.system_ram_gb() == 0.0

    class _FakeKernel32:
        def GlobalMemoryStatusEx(self, ref):
            ref._obj.ullTotalPhys = 64 * 2**30
            return 1

    fake_windll = types.SimpleNamespace(kernel32=_FakeKernel32())
    monkeypatch.setattr(ctypes, "windll", fake_windll, raising=False)
    assert gpus.system_ram_gb() == 64.0


def test_legacy_cloud_gating(monkeypatch, server):
    monkeypatch.setattr(gpus, "all_gpus", lambda: [MAC_8G])
    monkeypatch.setattr(gpus, "system_ram_gb", lambda: 8.0)

    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)
    assert gpus.legacy_cloud_enabled() is False
    assert gpus.gpu_profile()["legacy_cloud"] is False
    pdata = providers.providers_data()
    assert pdata["free"] == [] and pdata["paid"] == [] and pdata["legacy_cloud"] is False

    code, api_p = server.api("GET", "/api/providers")
    assert code == 200 and api_p["legacy_cloud"] is False and api_p["free"] == []
    code_gp, api_gp = server.api("GET", "/api/gpu_profile")
    assert code_gp == 200 and api_gp["legacy_cloud"] is False and api_gp["ram_gb"] == 8.0
    code_st, api_st = server.api("GET", "/api/status")
    assert code_st == 200 and api_st["legacy_cloud"] is False and set(api_st["gpus"]) == {"computer"}

    monkeypatch.setenv("STUDIO_LEGACY_CLOUD", "1")
    assert gpus.legacy_cloud_enabled() is True
    assert gpus.gpu_profile()["legacy_cloud"] is True
    pdata2 = providers.providers_data()
    assert {p["id"] for p in pdata2["free"]} == {"kaggle", "colab", "huggingface"}
    assert len(pdata2["paid"]) >= 10
    assert pdata2["legacy_cloud"] is True
