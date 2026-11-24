"""E2E pytest collection gating and shared fixtures (top-level imports: stdlib + pytest only)."""
from __future__ import annotations

from collections.abc import Iterator
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from e2e.helpers.fake_comfyui import FakeComfyUIServer
    from e2e.helpers.fake_hf import FakeHFHubServer
    from e2e.helpers.fake_ollama import FakeOllamaServer
    from e2e.helpers.studio_harness import IsolatedWorkspace, StudioHarness

_E2E_DIR = Path(__file__).resolve().parent

FULL_48G_PLATFORM_TAG = "win_cuda"
MAC_8G_PLATFORM_TAG = "mac_metal"


def _e2e_enabled() -> bool:
    return os.environ.get("STUDIO_RUN_E2E", "").strip().lower() in {"1", "true", "yes"}


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    if _e2e_enabled():
        return None
    if _E2E_DIR in collection_path.resolve().parents:
        return True
    return None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _e2e_enabled():
        return
    skip_e2e = pytest.mark.skip(reason="E2E tests require STUDIO_RUN_E2E=1")
    for item in items:
        if _E2E_DIR in item.path.resolve().parents:
            item.add_marker(skip_e2e)


@pytest.fixture()
def full_48g_profile() -> dict[str, Any]:
    """Target hardware profile for Windows 11 PC + 48 GB NVIDIA RTX 5090 (Blackwell CC 12.0)."""
    return {
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


@pytest.fixture()
def mac_8g_lite_profile() -> dict[str, Any]:
    """Target hardware profile for Apple Silicon Mac (8 GB unified memory)."""
    return {
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


@pytest.fixture()
def isolated_workspace(tmp_path: Path) -> Iterator[IsolatedWorkspace]:
    """Isolated Studio workspace re-rooting all import-time paths and caches."""
    from e2e.helpers.studio_harness import IsolatedWorkspace

    with IsolatedWorkspace(base_dir=tmp_path / "e2e_ws") as ws:
        yield ws


@pytest.fixture()
def fake_ollama() -> Iterator[FakeOllamaServer]:
    """Loopback fake Ollama HTTP server on 127.0.0.1:0."""
    from e2e.helpers.fake_ollama import FakeOllamaServer

    with FakeOllamaServer() as srv:
        yield srv


@pytest.fixture()
def fake_comfyui() -> Iterator[FakeComfyUIServer]:
    """Loopback fake ComfyUI HTTP + RFC 6455 WebSocket server on 127.0.0.1:0."""
    from e2e.helpers.fake_comfyui import FakeComfyUIServer

    with FakeComfyUIServer() as srv:
        yield srv


@pytest.fixture()
def fake_hf_hub() -> Iterator[FakeHFHubServer]:
    """Loopback fake Hugging Face Hub HTTP server on 127.0.0.1:0."""
    from e2e.helpers.fake_hf import FakeHFHubServer

    with FakeHFHubServer() as srv:
        yield srv


@pytest.fixture()
def live_studio_server(isolated_workspace: IsolatedWorkspace) -> Iterator[StudioHarness]:
    """Live StudioServer on 127.0.0.1:0 inside an isolated workspace."""
    from e2e.helpers.studio_harness import StudioHarness

    with StudioHarness(workspace=isolated_workspace) as harness:
        yield harness
