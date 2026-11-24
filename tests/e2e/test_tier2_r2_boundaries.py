"""Tier 2 boundary & adversarial E2E tests for Requirement R2 / Features F5-F11 (38 tests).

Counts: F5=5, F6=5, F7=5, F8=5, F9=6, F10=6, F11=6 (total 38).
All Neon module imports are deferred inside test functions/runtime helpers so
``STUDIO_RUN_E2E=1 pytest --collect-only`` always succeeds with zero import errors.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import socket
import sys
import threading
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import pytest

from e2e.conftest import MAC_8G_PLATFORM_TAG
from e2e.helpers.fake_comfyui import MINIMAL_PNG

if TYPE_CHECKING:
    from e2e.helpers.fake_comfyui import FakeComfyUIServer
    from e2e.helpers.fake_hf import FakeHFHubServer
    from e2e.helpers.fake_ollama import FakeOllamaServer
    from e2e.helpers.studio_harness import IsolatedWorkspace, StudioHarness

_NEON_ROOT = Path(__file__).resolve().parents[2]
_PLATFORMS_ALL = {"win_cuda", "linux_cuda", "mac_metal"}
_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _create_fake_sd_cli(bin_dir: Path, *, script_body: str) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe_name = "sd-cli.exe" if sys.platform == "win32" else "sd-cli"
    exe = bin_dir / exe_name
    exe.write_text(f"#!{sys.executable}\n{script_body}\n", encoding="utf-8")
    exe.chmod(0o755)
    return exe


def _make_fake_wan2gp_dir(base: Path, *, wgp_body: str) -> Path:
    wgp_dir = base / "wan2gp"
    (wgp_dir / "defaults").mkdir(parents=True, exist_ok=True)
    (wgp_dir / "ckpts").mkdir(parents=True, exist_ok=True)
    venv_bin = wgp_dir / ("venv/Scripts" if sys.platform == "win32" else "venv/bin")
    venv_bin.mkdir(parents=True, exist_ok=True)
    py_exe = venv_bin / ("python.exe" if sys.platform == "win32" else "python")
    if sys.platform == "win32":
        py_exe.write_text("", encoding="utf-8")
    else:
        py_exe.symlink_to(sys.executable)
    (wgp_dir / "defaults" / "t2v_1.3B.json").write_text(json.dumps({"steps": 4}), encoding="utf-8")
    (wgp_dir / "ckpts" / "t2v.safetensors").write_bytes(b"ckpt")
    (wgp_dir / "wgp.py").write_text(wgp_body, encoding="utf-8")
    return wgp_dir


@contextmanager
def _fake_mcp_boundary_server(*, missing_tools: bool = False, phase_reset: bool = False) -> Iterator[str]:
    state = {"poll": 0}
    lock = threading.Lock()

    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, status: int, obj: Any, extra: dict[str, str] | None = None) -> None:
            raw = b"" if obj is None else json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if raw:
                self.wfile.write(raw)

        def do_GET(self) -> None:
            if urlparse(self.path).path == "/files/out.mp4":
                data = b"ftypmp42"
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or "0")
            req = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            method = req.get("method", "")
            rpc_id = req.get("id")
            params = req.get("params") or {}
            if method == "initialize":
                self._send_json(
                    200,
                    {"jsonrpc": "2.0", "id": rpc_id, "result": {"protocolVersion": "2025-06-18", "capabilities": {}}},
                    extra={"Mcp-Session-Id": "sess-b1"},
                )
                return
            if method == "notifications/initialized":
                self._send_json(202, None)
                return
            if method == "tools/list":
                tools = [{"name": "other_tool"}] if missing_tools else [
                    {"name": "wangp_generate"},
                    {"name": "wangp_get_job"},
                    {"name": "wangp_cancel_job"},
                    {"name": "wangp_create_gallery_download"},
                ]
                self._send_json(200, {"jsonrpc": "2.0", "id": rpc_id, "result": {"tools": tools}})
                return
            if method == "tools/call":
                tname = params.get("name", "")
                port = self.server.server_port  # type: ignore[attr-defined]
                if tname == "wangp_generate":
                    res: dict[str, Any] = {"job_id": "job-b1"}
                elif tname == "wangp_get_job":
                    with lock:
                        state["poll"] += 1
                        c = state["poll"]
                    if phase_reset and c == 1:
                        res = {"job_id": "job-b1", "done": False, "phase": "inference", "progress": 100}
                    elif phase_reset and c == 2:
                        res = {"job_id": "job-b1", "done": False, "phase": "decoding", "progress": 15}
                    else:
                        res = {"job_id": "job-b1", "done": True, "phase": "decoding", "progress": 100, "outputs": ["out.mp4"]}
                elif tname == "wangp_create_gallery_download":
                    res = {"download_url": f"http://127.0.0.1:{port}/files/out.mp4"}
                else:
                    res = {"ok": True}
                self._send_json(200, {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(res)}]}})
                return
            self._send_json(404, {"error": "not found"})

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.daemon_threads = True
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/mcp"
    finally:
        httpd.shutdown()
        httpd.server_close()
        t.join(timeout=2.0)


def _validate_manifest_strict(manifest: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    required = {"id", "name", "section", "pack", "status", "inputs", "outputs", "models"}
    if not required.issubset(manifest.keys()):
        errs.append("missing required keys")
    allowed = required | {
        "$schema", "summary", "higgsfield_feature", "workflow", "source", "modes", "mode_label",
        "presets", "custom_nodes", "vram", "test", "credits", "notes", "min_vram_gb", "platforms",
    }
    extra = set(manifest.keys()) - allowed
    if extra:
        errs.append(f"unexpected keys: {sorted(extra)}")
    if not _ID_RE.match(str(manifest.get("id", ""))):
        errs.append("invalid id")
    if manifest.get("status") == "ready" and not manifest.get("workflow"):
        errs.append("ready without workflow")
    min_vram = manifest.get("min_vram_gb")
    if not isinstance(min_vram, (int, float)) or isinstance(min_vram, bool) or min_vram < 0:
        errs.append("invalid min_vram_gb")
    platforms = manifest.get("platforms")
    if not isinstance(platforms, list) or not platforms or not set(platforms).issubset(_PLATFORMS_ALL):
        errs.append("invalid platforms")
    return errs


# ---------------------------------------------------------------------------
# Feature F5 Boundaries (5 tests)
# ---------------------------------------------------------------------------


def test_f5_boundary_incomplete_subclasses_missing_each_abstract_method() -> None:
    from local_runners.base import LocalRunner

    impls: dict[str, Any] = {
        "name": "partial",
        "capabilities": lambda self: {},
        "is_installed": lambda self: True,
        "install": lambda self, on_progress=None: {},
        "run": lambda self, spec, on_progress=None: {},
        "cancel": lambda self: None,
    }
    for omitted in ("capabilities", "is_installed", "install", "run", "cancel"):
        ns = {k: v for k, v in impls.items() if k != omitted}
        sub_cls = type(f"Missing_{omitted}", (LocalRunner,), ns)
        with pytest.raises(TypeError):
            sub_cls()


def test_f5_boundary_empty_whitespace_and_unknown_task_kind_raise_clear_error(
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.router import select_runner

    for bad_kind in ("", "   ", "unknown_pipeline_xyz"):
        with pytest.raises((ValueError, RuntimeError)) as exc_info:
            select_runner(bad_kind, profile=full_48g_profile)
        assert str(exc_info.value).strip()


def test_f5_boundary_cpu_and_low_vram_profiles_gate_gpu_tasks(
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.router import select_runner

    cpu_profile = {
        "platform": "darwin",
        "backend": "cpu",
        "name": "Intel Iris",
        "vram_gb": 0.0,
        "ram_gb": 8.0,
        "compute_cap": "",
        "is_blackwell": False,
        "tier": "cpu",
        "supports_local_video": False,
        "supports_local_images": False,
        "default_image_backend": "none",
        "default_video_backend": "none",
        "legacy_cloud": False,
    }
    low_vram_profile = {
        "platform": "win32",
        "backend": "cuda",
        "name": "RTX 3050",
        "vram_gb": 6.0,
        "ram_gb": 16.0,
        "compute_cap": "8.6",
        "is_blackwell": False,
        "tier": "low_vram",
        "supports_local_video": False,
        "supports_local_images": True,
        "default_image_backend": "comfyui",
        "default_video_backend": "none",
        "legacy_cloud": False,
    }

    for task in ("video", "image"):
        with pytest.raises((ValueError, RuntimeError)):
            select_runner(task, profile=cpu_profile)

    with pytest.raises((ValueError, RuntimeError)):
        select_runner("video", profile=low_vram_profile)


def test_f5_boundary_mps_vram_threshold_16gb_vs_24gb_video_support(
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.base import LocalRunner
    from local_runners.router import select_runner

    prof_16 = {
        "platform": "darwin",
        "backend": "mps",
        "name": "Apple M2 Pro",
        "vram_gb": 16.0,
        "ram_gb": 16.0,
        "compute_cap": "MPS",
        "is_blackwell": False,
        "tier": "standard_gpu",
        "supports_local_video": False,
        "supports_local_images": True,
        "default_image_backend": "sd_cli",
        "default_video_backend": "none",
        "legacy_cloud": False,
    }
    prof_24 = dict(prof_16, vram_gb=24.0, ram_gb=24.0, supports_local_video=True, default_video_backend="wan2gp")

    with pytest.raises((ValueError, RuntimeError)):
        select_runner("video", profile=prof_16)

    runner_24 = select_runner("video", profile=prof_24)
    assert isinstance(runner_24, LocalRunner)


def test_f5_boundary_unknown_model_id_and_case_normalization(
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.base import LocalRunner
    from local_runners.router import select_runner

    r_upper = select_runner("IMAGE", profile=full_48g_profile)
    r_trim = select_runner(" image ", profile=full_48g_profile)
    assert isinstance(r_upper, LocalRunner)
    assert isinstance(r_trim, LocalRunner)
    assert r_upper.name == r_trim.name == "comfyui"

    try:
        r_unknown = select_runner("video", model_id="wan2gp:nonexistent_model", profile=full_48g_profile)
        assert isinstance(r_unknown, LocalRunner)
    except (ValueError, RuntimeError) as exc:
        assert str(exc).strip()


# ---------------------------------------------------------------------------
# Feature F6 Boundaries (5 tests)
# ---------------------------------------------------------------------------


def test_f6_boundary_meter_monotonic_with_one_of_one_spike_and_nan_inputs() -> None:
    from local_runners.pantry import Meter

    m = Meter(expected_nodes=4, class_of=lambda nid: {"3": "KSampler"}.get(nid))
    m.update({"nodes_done": 1, "nodes_total": 1})
    assert m.value <= 0.99
    assert m.value == pytest.approx(0.25)

    m.update({"nodes_done": 1, "nodes_total": 4, "step": 2, "steps": 10, "current_node": "3"})
    assert m.node == "KSampler"
    v1 = m.value

    m.update({"nodes_done": 0, "nodes_total": 4, "step": 1, "steps": 10})
    m.update({"step": float("nan"), "steps": 0})
    assert m.value >= v1
    assert m.value <= 0.99


def test_f6_boundary_validation_error_400_explains_missing_model_and_pack(
    fake_comfyui: FakeComfyUIServer,
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.comfyui_runner import ComfyUIRunner

    app_dir = tmp_path / "val_app"
    app_dir.mkdir(parents=True, exist_ok=True)
    app_json = {
        "id": "val-app",
        "name": "Val App",
        "section": "image",
        "pack": "flux3",
        "status": "ready",
        "workflow": "workflow.api.json",
        "min_vram_gb": 12,
        "platforms": ["win_cuda"],
        "inputs": [],
        "outputs": [{"node": "9", "type": "image", "label": "Out"}],
        "models": [{"repo": "org/m", "file": "missing.safetensors", "dir": "checkpoints", "gb": 1.0, "phase": "all"}],
    }
    wf = {"4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "missing.safetensors"}}, "9": {"class_type": "SaveImage", "inputs": {}}}
    (app_dir / "app.json").write_text(json.dumps(app_json), encoding="utf-8")
    (app_dir / "workflow.api.json").write_text(json.dumps(wf), encoding="utf-8")

    fake_comfyui.set_validation_error(enabled=True)
    runner = ComfyUIRunner(base_url=fake_comfyui.base_url)
    with pytest.raises(RuntimeError) as exc_info:
        runner.run({"app_dir": str(app_dir), "values": {}, "output_dir": str(tmp_path / "out")})
    msg = str(exc_info.value)
    assert "missing.safetensors" in msg
    assert "CheckpointLoaderSimple" in msg
    assert "flux3" in msg


def test_f6_boundary_execution_error_ws_and_http_500_surface_without_hanging(
    fake_comfyui: FakeComfyUIServer,
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.comfyui_runner import ComfyUIRunner

    app_dir = tmp_path / "err_app"
    app_dir.mkdir(parents=True, exist_ok=True)
    app_json = {
        "id": "err-app",
        "name": "Err App",
        "section": "image",
        "pack": "core",
        "status": "ready",
        "workflow": "workflow.api.json",
        "min_vram_gb": 0,
        "platforms": ["win_cuda"],
        "inputs": [],
        "outputs": [{"node": "9", "type": "image", "label": "Out"}],
        "models": [],
    }
    wf = {"3": {"class_type": "KSampler", "inputs": {}}, "9": {"class_type": "SaveImage", "inputs": {}}}
    (app_dir / "app.json").write_text(json.dumps(app_json), encoding="utf-8")
    (app_dir / "workflow.api.json").write_text(json.dumps(wf), encoding="utf-8")

    runner = ComfyUIRunner(base_url=fake_comfyui.base_url)

    fake_comfyui.set_execution_error("CUDA out of memory")
    t0 = time.monotonic()
    with pytest.raises(RuntimeError) as exc1:
        runner.run({"app_dir": str(app_dir), "values": {}, "output_dir": str(tmp_path / "out1")})
    assert "CUDA out of memory" in str(exc1.value)
    assert time.monotonic() - t0 < 5.0

    fake_comfyui.set_execution_error(None)
    fake_comfyui.set_error("/prompt", 500)
    t1 = time.monotonic()
    with pytest.raises(RuntimeError):
        runner.run({"app_dir": str(app_dir), "values": {}, "output_dir": str(tmp_path / "out2")})
    assert time.monotonic() - t1 < 5.0


def test_f6_boundary_file_input_max_mb_limit_and_valid_upload(
    fake_comfyui: FakeComfyUIServer,
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.comfyui_runner import ComfyUIRunner

    app_dir = tmp_path / "up_app"
    app_dir.mkdir(parents=True, exist_ok=True)
    app_json = {
        "id": "up-app",
        "name": "Upload App",
        "section": "image",
        "pack": "core",
        "status": "ready",
        "workflow": "workflow.api.json",
        "min_vram_gb": 0,
        "platforms": ["win_cuda"],
        "inputs": [{"id": "img", "type": "image", "label": "Image", "limits": {"max_mb": 0.001}, "bind": [{"node": "2", "field": "image"}]}],
        "outputs": [{"node": "9", "type": "image", "label": "Out"}],
        "models": [],
    }
    wf = {"2": {"class_type": "LoadImage", "inputs": {"image": ""}}, "3": {"class_type": "KSampler", "inputs": {}}, "9": {"class_type": "SaveImage", "inputs": {}}}
    (app_dir / "app.json").write_text(json.dumps(app_json), encoding="utf-8")
    (app_dir / "workflow.api.json").write_text(json.dumps(wf), encoding="utf-8")

    big_png = tmp_path / "big.png"
    big_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 4096)
    small_png = tmp_path / "small.png"
    small_png.write_bytes(MINIMAL_PNG)

    runner = ComfyUIRunner(base_url=fake_comfyui.base_url)
    with pytest.raises((ValueError, RuntimeError)):
        runner.run({"app_dir": str(app_dir), "values": {"img": str(big_png)}, "output_dir": str(tmp_path / "out_big")})
    assert len(fake_comfyui.uploads) == 0

    runner.run({"app_dir": str(app_dir), "values": {"img": str(small_png)}, "output_dir": str(tmp_path / "out_small")})
    assert len(fake_comfyui.uploads) == 1


def test_f6_boundary_pantry_empty_model_key_and_free_http_503_failure(
    fake_comfyui: FakeComfyUIServer,
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.pantry import Pantry, model_key

    assert model_key({"models": []}) == ""
    assert model_key({"models": [{"dir": "loras", "file": "x.safetensors"}, {"dir": "vae", "file": "v.safetensors", "optional": True}]}) == ""

    pantry = Pantry(comfyui_url=fake_comfyui.base_url)
    pantry.prepare("core_app", "")
    fake_comfyui.set_error("/free", 503)
    with pytest.raises((RuntimeError, OSError)):
        pantry.prepare("flux_app", "diffusion_models/flux1-dev.safetensors")
    assert getattr(pantry, "models", None) in ("", None)


# ---------------------------------------------------------------------------
# Feature F7 Boundaries (5 tests)
# ---------------------------------------------------------------------------


def test_f7_boundary_cancel_terminates_active_sd_cli_and_prevents_orphan(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.sd_cli_runner import SdCliRunner
    from studio_app import procs

    pid_file = tmp_path / "sd.pid"
    bin_dir = tmp_path / "bin"
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    _create_fake_sd_cli(
        bin_dir,
        script_body=(
            "import os, time\n"
            "from pathlib import Path\n"
            f"Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
            "print('step 1/20', flush=True)\n"
            "time.sleep(30)\n"
        ),
    )
    (models_dir / "DreamShaper_8_pruned.safetensors").write_bytes(b"sd1")

    runner = SdCliRunner(bin_dir=bin_dir, models_dir=models_dir)
    errors: list[BaseException] = []

    def _run_bg() -> None:
        try:
            runner.run({"model": "dreamshaper-8", "prompt": "hang", "output_path": str(tmp_path / "cancel.png")})
        except BaseException as exc:
            errors.append(exc)

    t = threading.Thread(target=_run_bg, daemon=True)
    t.start()
    deadline = time.monotonic() + 5.0
    while not pid_file.is_file() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert pid_file.is_file()
    pid = int(pid_file.read_text(encoding="utf-8"))
    runner.cancel()
    t.join(timeout=5.0)
    assert not t.is_alive()
    assert errors
    assert not procs.pid_alive(pid)


def test_f7_boundary_missing_binary_missing_model_and_missing_z_image_aux(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.sd_cli_runner import SdCliRunner

    empty_bin = tmp_path / "no_bin"
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    r1 = SdCliRunner(bin_dir=empty_bin, models_dir=models_dir)
    assert r1.is_installed() is False
    with pytest.raises(RuntimeError):
        r1.run({"model": "dreamshaper-8", "prompt": "x"})

    ok_bin = tmp_path / "ok_bin"
    _create_fake_sd_cli(ok_bin, script_body="print('ok')")
    r2 = SdCliRunner(bin_dir=ok_bin, models_dir=models_dir)
    with pytest.raises(RuntimeError) as exc_mod:
        r2.run({"model": "dreamshaper-8", "prompt": "x"})
    assert "dreamshaper" in str(exc_mod.value).lower() or "model" in str(exc_mod.value).lower()

    (models_dir / "z_image_turbo-Q4_K.gguf").write_bytes(b"gguf")
    (models_dir / "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf").write_bytes(b"llm")
    with pytest.raises(RuntimeError) as exc_aux:
        r2.run({"model": "z-image-turbo", "prompt": "x"})
    assert "vae" in str(exc_aux.value).lower() or "ae.safetensors" in str(exc_aux.value).lower()


def test_f7_boundary_darwin_intel_x86_64_unsupported_and_empty_assets(
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.sd_cli_runner import pick_binary_asset

    try:
        res = pick_binary_asset(platform="darwin", arch="x86_64", zip_names=["sd-master-Darwin-macOS-arm64.zip"])
        assert res is None
    except (RuntimeError, ValueError) as exc:
        assert "apple silicon" in str(exc).lower() or "arm64" in str(exc).lower() or "intel" in str(exc).lower()

    assert pick_binary_asset(platform="win32", arch="x64", zip_names=[]) is None


def test_f7_boundary_seed_negative_one_zero_steps_fallback_and_zero_cfg_preserved(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.sd_cli_runner import SdCliRunner

    bin_dir = tmp_path / "bin"
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    argv_path = tmp_path / "argv.json"
    _create_fake_sd_cli(
        bin_dir,
        script_body=(
            "import json, sys\n"
            "from pathlib import Path\n"
            f"Path({str(argv_path)!r}).write_text(json.dumps(sys.argv[1:]))\n"
            "out = sys.argv[sys.argv.index('-o') + 1]\n"
            f"Path(out).write_bytes({MINIMAL_PNG!r})\n"
        ),
    )
    (models_dir / "DreamShaper_8_pruned.safetensors").write_bytes(b"sd1")

    runner = SdCliRunner(bin_dir=bin_dir, models_dir=models_dir)
    runner.run(
        {
            "model": "dreamshaper-8",
            "prompt": "bounds",
            "seed": -1,
            "steps": 0,
            "guidance_scale": 0.0,
            "output_path": str(tmp_path / "bounds.png"),
        }
    )

    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    seed_val = int(argv[argv.index("--seed") + 1])
    steps_val = int(argv[argv.index("--steps") + 1])
    cfg_val = float(argv[argv.index("--cfg-scale") + 1])
    assert seed_val >= 0
    assert steps_val == 20
    assert cfg_val == 0.0


def test_f7_boundary_exit_zero_without_output_and_ntstatus_crash_code(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.sd_cli_runner import SdCliRunner, describe_exit_code

    bin_dir = tmp_path / "bin"
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / "DreamShaper_8_pruned.safetensors").write_bytes(b"sd1")

    _create_fake_sd_cli(bin_dir, script_body="print('done without writing file')")
    runner = SdCliRunner(bin_dir=bin_dir, models_dir=models_dir)
    with pytest.raises(RuntimeError) as exc_no_out:
        runner.run({"model": "dreamshaper-8", "prompt": "x", "output_path": str(tmp_path / "missing.png")})
    assert "output" in str(exc_no_out.value).lower() or "image" in str(exc_no_out.value).lower()

    _create_fake_sd_cli(bin_dir, script_body="import sys; print('ggml fatal error', file=sys.stderr); sys.exit(1)")
    with pytest.raises(RuntimeError) as exc_fatal:
        runner.run({"model": "dreamshaper-8", "prompt": "x", "output_path": str(tmp_path / "fatal.png")})
    assert "ggml fatal error" in str(exc_fatal.value).lower()

    assert describe_exit_code(0xC0000005, "win32")
    assert describe_exit_code(0xC0000409, "win32")


# ---------------------------------------------------------------------------
# Feature F8 Boundaries (5 tests)
# ---------------------------------------------------------------------------


def test_f8_boundary_progress_parser_monotonic_across_subphase_resets_and_split_chunks() -> None:
    from local_runners.wan2gp_runner import Wan2GPProgressParser

    parser = Wan2GPProgressParser()
    chunks = [
        "\x1b[33m[3/3] Loading Model",
        "\r[0/12] Loading Weights\n[1/2] Enco",
        "ding\r[5/10] Denoising\n[1/10] Denoising\n[5/10] Denoising\n",
    ]
    events: list[dict[str, Any]] = []
    for chunk in chunks:
        events.extend(parser.feed(chunk))

    progs = [float(e["progress"]) for e in events if isinstance(e.get("progress"), (int, float))]
    assert progs
    assert progs == sorted(progs)
    for ev in events:
        assert "\x1b[" not in str(ev)


def test_f8_boundary_oom_missing_file_and_zero_of_one_queue_exit_zero_failures(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.wan2gp_runner import Wan2GPRunner

    modes = [
        ("import sys; print('torch.OutOfMemoryError: CUDA out of memory', flush=True); sys.exit(1)", ("oom", "vram", "out of memory")),
        ("import sys; print(\"File not found for 'image_start': /bad/frame.png\", flush=True); sys.exit(1)", ("image_start",)),
        ("import sys; print('Queue completed: 0/1 tasks', flush=True); sys.exit(0)", ("0/1", "task", "failed")),
    ]
    for idx, (body, expected_tokens) in enumerate(modes):
        sub = tmp_path / f"mode_{idx}"
        wgp_dir = _make_fake_wan2gp_dir(sub, wgp_body=body)
        runner = Wan2GPRunner(install_dir=wgp_dir)
        with pytest.raises(RuntimeError) as exc_info:
            runner.run({"model_id": "wan2gp:wan21-t2v-1.3b", "prompt": "fail", "output_dir": str(sub / "out")})
        msg = str(exc_info.value).lower()
        assert any(tok in msg for tok in expected_tokens), f"Unexpected error msg {msg!r}"


def test_f8_boundary_saved_path_last_match_wins_and_missing_media_fallback(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.wan2gp_runner import Wan2GPRunner

    sub_a = tmp_path / "last_match"
    out_a = sub_a / "out"
    out_a.mkdir(parents=True, exist_ok=True)
    inter = out_a / "intermediate.mp4"
    final = out_a / "final.mp4"
    wgp_a = _make_fake_wan2gp_dir(
        sub_a,
        wgp_body=(
            "from pathlib import Path\n"
            f"Path({str(inter)!r}).write_bytes(b'1')\n"
            f"Path({str(final)!r}).write_bytes(b'2')\n"
            f"print('saved to Path: ' + {str(inter)!r})\n"
            f"print('saved to Path: ' + {str(final)!r})\n"
            "print('Queue completed: 1/1 tasks')\n"
        ),
    )
    res_a = Wan2GPRunner(install_dir=wgp_a).run({"model_id": "wan2gp:wan21-t2v-1.3b", "prompt": "ok", "output_dir": str(out_a)})
    assert Path(res_a["output_path"]).resolve() == final.resolve()

    sub_b = tmp_path / "no_media"
    wgp_b = _make_fake_wan2gp_dir(sub_b, wgp_body="print('Queue completed: 1/1 tasks')\n")
    with pytest.raises(RuntimeError) as exc_b:
        Wan2GPRunner(install_dir=wgp_b).run({"model_id": "wan2gp:wan21-t2v-1.3b", "prompt": "none", "output_dir": str(sub_b / "out")})
    assert "media" in str(exc_b.value).lower() or "output" in str(exc_b.value).lower() or "found" in str(exc_b.value).lower()


def test_f8_boundary_mcp_url_normalization_missing_tools_and_postprocess_progress_reset(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.wan2gp_runner import Wan2GPRunner, normalize_mcp_url

    assert normalize_mcp_url("http://127.0.0.1:7866") == "http://127.0.0.1:7866/mcp"
    assert normalize_mcp_url("http://127.0.0.1:7866/mcp/") == "http://127.0.0.1:7866/mcp"

    with _fake_mcp_boundary_server(missing_tools=True) as mcp_missing:
        with pytest.raises(RuntimeError) as exc_t:
            Wan2GPRunner(mcp_url=mcp_missing).run({"model_id": "wan2gp:wan22-t2v", "prompt": "x", "output_dir": str(tmp_path / "o1")})
        assert "--mcp-api-version 1" in str(exc_t.value)

    with _fake_mcp_boundary_server(phase_reset=True) as mcp_reset:
        events: list[dict[str, Any]] = []
        Wan2GPRunner(mcp_url=mcp_reset).run(
            {"model_id": "wan2gp:wan22-t2v", "prompt": "x", "output_dir": str(tmp_path / "o2")},
            on_progress=events.append,
        )
        progs = [float(e["progress"]) for e in events if isinstance(e.get("progress"), (int, float))]
        assert progs == sorted(progs)


def test_f8_boundary_install_checks_and_dry_run_validation(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.wan2gp_runner import Wan2GPRunner

    assert Wan2GPRunner(install_dir=tmp_path / "does_not_exist").is_installed() is False

    no_wgp = tmp_path / "no_wgp"
    no_wgp.mkdir()
    assert Wan2GPRunner(install_dir=no_wgp).is_installed() is False

    no_venv = tmp_path / "no_venv"
    no_venv.mkdir()
    (no_venv / "wgp.py").write_text("", encoding="utf-8")
    assert Wan2GPRunner(install_dir=no_venv).is_installed() is False

    ok_dir = _make_fake_wan2gp_dir(tmp_path / "dry_ok", wgp_body="print('Validation complete. 1/1 task')\n")
    assert Wan2GPRunner(install_dir=ok_dir).dry_run({"model_id": "wan2gp:wan21-t2v-1.3b", "prompt": "ok"})["ok"] is True

    bad_dir = _make_fake_wan2gp_dir(tmp_path / "dry_bad", wgp_body="print('Validation complete. 0/1 task')\n")
    assert Wan2GPRunner(install_dir=bad_dir).dry_run({"model_id": "wan2gp:wan21-t2v-1.3b", "prompt": "bad"})["ok"] is False


# ---------------------------------------------------------------------------
# Feature F9 Boundaries (6 tests)
# ---------------------------------------------------------------------------


def test_f9_boundary_zero_vram_core_apps_and_zero_gb_pack(
    full_48g_profile: dict[str, Any],
    mac_8g_lite_profile: dict[str, Any],
) -> None:
    for app_id in ("smoke", "smoke-invert"):
        manifest = json.loads((_NEON_ROOT / "apps" / app_id / "app.json").read_text(encoding="utf-8"))
        assert manifest["min_vram_gb"] == 0
        assert manifest["models"] == []
        assert set(manifest["platforms"]) >= _PLATFORMS_ALL

    core_pack = json.loads((_NEON_ROOT / "packs" / "core.json").read_text(encoding="utf-8"))
    assert core_pack["download_gb"] == 0
    assert core_pack["needs_hf_token"] is False
    assert core_pack["models"] == []


def test_f9_boundary_8gb_vram_threshold_accuracy(mac_8g_lite_profile: dict[str, Any]) -> None:
    apps_dir = _NEON_ROOT / "apps"
    for app_file in sorted(apps_dir.glob("*/app.json")):
        m = json.loads(app_file.read_text(encoding="utf-8"))
        if m["min_vram_gb"] <= mac_8g_lite_profile["vram_gb"] and MAC_8G_PLATFORM_TAG in m["platforms"]:
            phase_totals: dict[str, float] = {}
            for mod in m["models"]:
                if mod.get("optional"):
                    continue
                phase = mod["phase"]
                phase_totals[phase] = phase_totals.get(phase, 0.0) + float(mod["gb"])
            if phase_totals:
                assert max(phase_totals.values()) <= 8.0, f"{m['id']} exceeds 8 GB single phase"


def test_f9_boundary_48gb_vram_ceiling_for_heaviest_packs(full_48g_profile: dict[str, Any]) -> None:
    apps_dir = _NEON_ROOT / "apps"
    heavy_packs = {"video-ltx25", "video-h3", "video-wan-effects"}
    checked = 0
    for app_file in sorted(apps_dir.glob("*/app.json")):
        m = json.loads(app_file.read_text(encoding="utf-8"))
        if m["pack"] in heavy_packs:
            checked += 1
            assert m["min_vram_gb"] <= full_48g_profile["vram_gb"]
    assert checked > 0


def test_f9_boundary_model_key_excludes_optional_and_loras_and_validates_custom_nodes() -> None:
    from local_runners.pantry import model_key

    apps_dir = _NEON_ROOT / "apps"
    saw_optional_or_lora = False
    saw_custom_node = False
    for app_file in sorted(apps_dir.glob("*/app.json")):
        m = json.loads(app_file.read_text(encoding="utf-8"))
        if any(mod.get("optional") or mod.get("dir") == "loras" for mod in m["models"]):
            saw_optional_or_lora = True
            key = model_key(m)
            for mod in m["models"]:
                if mod.get("optional") or mod.get("dir") == "loras":
                    assert Path(mod["file"]).name not in key
        for cn in m.get("custom_nodes", []):
            saw_custom_node = True
            assert str(cn["repo"]).startswith("https://")
            assert re.fullmatch(r"[0-9a-f]{7,40}", cn["commit"])
    assert saw_optional_or_lora
    assert saw_custom_node


def test_f9_boundary_schema_rejects_invalid_vram_platform_and_extra_fields() -> None:
    base = json.loads((_NEON_ROOT / "apps" / "smoke" / "app.json").read_text(encoding="utf-8"))
    assert _validate_manifest_strict(base) == []

    bad_cases = [
        {**base, "min_vram_gb": -0.1},
        {**base, "platforms": ["xbox"]},
        {**base, "platforms": []},
        {**base, "unknown_field": 1},
        {**base, "id": "Bad_ID"},
        {k: v for k, v in base.items() if k != "workflow"},
    ]
    for case in bad_cases:
        assert _validate_manifest_strict(case), f"Expected validation failure for {case}"


def test_f9_boundary_subgraph_node_ids_and_seed_minus_one_handling() -> None:
    from local_runners.pantry import resolve_values

    for app_id in ("z-image", "music"):
        app_dir = _NEON_ROOT / "apps" / app_id
        manifest = json.loads((app_dir / "app.json").read_text(encoding="utf-8"))
        wf = json.loads((app_dir / manifest["workflow"]).read_text(encoding="utf-8"))
        subgraph_nodes = [
            b["node"]
            for inp in manifest["inputs"]
            for b in inp.get("bind", [])
            if ":" in str(b["node"])
        ]
        assert subgraph_nodes, f"{app_id} expected colon-delimited subgraph nodes"
        for nid in subgraph_nodes:
            assert nid in wf
        resolved = resolve_values(manifest, {})
        for inp in manifest["inputs"]:
            if inp["type"] == "seed" and inp.get("default") == -1:
                assert isinstance(resolved[inp["id"]], int) and resolved[inp["id"]] >= 0


# ---------------------------------------------------------------------------
# Feature F10 Boundaries (6 tests)
# ---------------------------------------------------------------------------


def test_f10_boundary_disk_headroom_2gb_guard(
    isolated_workspace: IsolatedWorkspace,
    fake_hf_hub: FakeHFHubServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import local_runners.model_packs as model_packs

    monkeypatch.setenv("HF_ENDPOINT", fake_hf_hub.base_url)
    fake_hf_hub.register_file("org/tiny", "tiny.bin", b"ok")
    models_dir = isolated_workspace.root / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    free_gb = shutil.disk_usage(models_dir).free / 1e9
    if free_gb < 2.5:
        pytest.skip("Insufficient disk space for 2 GB headroom boundary test")

    too_big_pack = {
        "pack": "too-big",
        "models": [{"repo": "org/tiny", "file": "tiny.bin", "dir": "vae", "name": "tiny.bin", "gb": round(free_gb - 1.9, 2)}],
    }
    with pytest.raises((ValueError, RuntimeError)) as exc_info:
        model_packs.download_packs([too_big_pack], models_dir=models_dir)
    assert "space" in str(exc_info.value).lower() or "headroom" in str(exc_info.value).lower() or "gb" in str(exc_info.value).lower()
    assert fake_hf_hub.requests_log == []

    small_pack = {
        "pack": "small-ok",
        "models": [{"repo": "org/tiny", "file": "tiny.bin", "dir": "vae", "name": "tiny.bin", "gb": 0.001}],
    }
    model_packs.download_packs([small_pack], models_dir=models_dir)
    assert (models_dir / "vae" / "tiny.bin").is_file()


def test_f10_boundary_token_length_30_and_runpod_placeholder_variants(
    isolated_workspace: IsolatedWorkspace,
    fake_hf_hub: FakeHFHubServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import local_runners.model_packs as model_packs

    monkeypatch.setenv("HF_ENDPOINT", fake_hf_hub.base_url)
    assert model_packs.looks_like_token("hf_" + "a" * 26) is False
    assert model_packs.looks_like_token("hf_" + "a" * 27) is True
    assert model_packs.looks_like_token("hf_" + "a" * 27 + " ") is False
    assert model_packs.looks_like_token("hf_é" + "a" * 28) is False

    monkeypatch.setenv("HF_TOKEN", "{{ RUNPOD_SECRET_hf_token }}")
    assert model_packs.env_problem() is not None
    tok, _ = model_packs.get_token()
    assert tok == ""

    valid_tok = "hf_" + "z" * 27
    fake_hf_hub.set_valid_tokens({valid_tok: "pad-user"})
    model_packs.save_token(f"  {valid_tok}\n")
    assert model_packs.get_token() == (valid_tok, "studio")


def test_f10_boundary_unreachable_hub_and_5xx_return_unknown_without_hang(
    isolated_workspace: IsolatedWorkspace,
    fake_hf_hub: FakeHFHubServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import local_runners.model_packs as model_packs

    dead_port = _free_loopback_port()
    monkeypatch.setenv("HF_ENDPOINT", f"http://127.0.0.1:{dead_port}")
    t0 = time.monotonic()
    assert model_packs.probe_license("org/repo", "file.bin", token="hf_" + "a" * 30) == "unknown"
    assert time.monotonic() - t0 < 5.0

    models_dir = isolated_workspace.root / "models"
    pack_spec = {"pack": "dead", "models": [{"repo": "org/repo", "file": "file.bin", "dir": "vae", "name": "file.bin", "gb": 0.01}]}
    model_packs.download_packs([pack_spec], models_dir=models_dir)
    assert model_packs.downloads_status(models_dir=models_dir)["failed"]


def test_f10_boundary_corrupt_downloads_json_and_stale_failure_pruning(
    isolated_workspace: IsolatedWorkspace,
) -> None:
    import local_runners.model_packs as model_packs

    models_dir = isolated_workspace.root / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    dl_file = models_dir / ".downloads.json"
    dl_file.write_text("{corrupt", encoding="utf-8")

    st_corrupt = model_packs.downloads_status(models_dir=models_dir)
    assert isinstance(st_corrupt, dict)

    (models_dir / "vae").mkdir(parents=True, exist_ok=True)
    (models_dir / "vae" / "present.bin").write_bytes(b"ok")
    dl_file.write_text(
        json.dumps(
            {
                "job": None,
                "failed": {
                    "vae/present.bin": {"reason": "network", "at": 1},
                    "vae/still_missing.bin": {"reason": "network", "at": 1},
                },
            }
        ),
        encoding="utf-8",
    )
    st_pruned = model_packs.downloads_status(models_dir=models_dir)
    assert "vae/present.bin" not in st_pruned["failed"]
    assert "vae/still_missing.bin" in st_pruned["failed"]


def test_f10_boundary_unknown_pack_and_empty_pack_selection(
    isolated_workspace: IsolatedWorkspace,
    fake_hf_hub: FakeHFHubServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import local_runners.model_packs as model_packs

    monkeypatch.setenv("HF_ENDPOINT", fake_hf_hub.base_url)
    models_dir = isolated_workspace.root / "models"

    with pytest.raises((ValueError, KeyError, RuntimeError)):
        model_packs.download_packs(["does-not-exist"], models_dir=models_dir)
    with pytest.raises((ValueError, RuntimeError)):
        model_packs.download_packs([], models_dir=models_dir)
    assert fake_hf_hub.requests_log == []


def test_f10_boundary_lockfile_reentrant_and_no_tmp_leftovers(
    isolated_workspace: IsolatedWorkspace,
    fake_hf_hub: FakeHFHubServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import local_runners.model_packs as model_packs

    monkeypatch.setenv("HF_ENDPOINT", fake_hf_hub.base_url)
    fake_hf_hub.register_file("org/seq", "f1.bin", b"111")
    fake_hf_hub.register_file("org/seq", "f2.bin", b"222")
    models_dir = isolated_workspace.root / "models"

    model_packs.download_packs([{"pack": "s1", "models": [{"repo": "org/seq", "file": "f1.bin", "dir": "vae", "name": "f1.bin", "gb": 0.01}]}], models_dir=models_dir)
    model_packs.download_packs([{"pack": "s2", "models": [{"repo": "org/seq", "file": "f2.bin", "dir": "vae", "name": "f2.bin", "gb": 0.01}]}], models_dir=models_dir)

    assert (models_dir / "vae" / "f1.bin").is_file()
    assert (models_dir / "vae" / "f2.bin").is_file()
    assert not (models_dir / ".downloads.json.tmp").exists()


# ---------------------------------------------------------------------------
# Feature F11 Boundaries (6 tests)
# ---------------------------------------------------------------------------


def test_f11_boundary_audio_csv_edge_cases_empty_and_missing_files(
    isolated_workspace: IsolatedWorkspace,
) -> None:
    import local_audio

    assert local_audio.spans([]) == []
    assert local_audio.spans([1, 2, 3, 7, 9, 10]) == [(1, 3), (7, 7), (9, 10)]

    book_dir = isolated_workspace.root / "projects" / "books" / "empty_audio"
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "audio_shots.csv").write_text("shot,chapter,narration,lines_json\n", encoding="utf-8")
    local_audio.narration(book_dir)

    (book_dir / "audio_shots.csv").write_text('shot,chapter,narration,lines_json\n1,1,"","[]"\n', encoding="utf-8")
    local_audio.narration(book_dir)
    assert list((book_dir / "audio" / "kokoro").glob("*.wav")) == []


def test_f11_boundary_missing_audio_deps_or_offline_leaves_no_tmp_wav(
    isolated_workspace: IsolatedWorkspace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from local_runners.router import select_runner

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    book_dir = isolated_workspace.root / "projects" / "books" / "offline_audio"
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "audio_shots.csv").write_text(
        'shot,chapter,narration,lines_json\n1,1,"Line","[{\\"voice\\":\\"af_heart\\",\\"text\\":\\"Line\\"}]"\n',
        encoding="utf-8",
    )
    (book_dir / "audio_chapters.csv").write_text('chapter,music\n1,"calm"\n', encoding="utf-8")

    runner = select_runner("audio", model_id="musicgen-small")
    with pytest.raises((RuntimeError, ImportError, OSError, ValueError)):
        runner.run({"project_dir": str(book_dir), "kind": "musicgen"})

    for sub in ("kokoro", "musicgen_chapters"):
        d = book_dir / "audio" / sub
        if d.is_dir():
            assert not list(d.glob("*.tmp.wav"))
            assert not [p for p in d.glob("*.wav") if p.stat().st_size == 0]


def test_f11_boundary_full_48g_lease_42gb_threshold_during_audio_run(
    isolated_workspace: IsolatedWorkspace,
    fake_ollama: FakeOllamaServer,
    full_48g_profile: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from local_runners.gpu_lease import LeaseManager

    fake_ollama.load_model("qwen2.5:32b", size_vram=20 * 2**30)
    mgr = LeaseManager(ollama_url=fake_ollama.base_url)

    r_ok = mgr.acquire_media_lease(22.0, active_llm_gb=20.0, profile=full_48g_profile)
    assert r_ok.evicted_ollama is False
    assert fake_ollama.get_evictions() == []

    r_evict = mgr.acquire_media_lease(22.1, active_llm_gb=20.0, profile=full_48g_profile)
    assert r_evict.evicted_ollama is True
    assert fake_ollama.get_evictions()


def test_f11_boundary_local_audio_cli_rejects_invalid_mode_and_bad_slugs(
    isolated_workspace: IsolatedWorkspace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import local_audio

    for bad_argv in (
        ["local_audio.py", "demo", "bark"],
        ["local_audio.py", "../evil", "kokoro"],
        ["local_audio.py", "ghost_book_999", "kokoro"],
    ):
        monkeypatch.setattr(sys, "argv", bad_argv)
        with pytest.raises(SystemExit) as exc_info:
            local_audio.main()
        assert exc_info.value.code not in (None, 0)


def test_f11_boundary_generation_steps_legacy_vs_default_local_and_invalid_inputs(
    isolated_workspace: IsolatedWorkspace,
    live_studio_server: StudioHarness,
) -> None:
    from studio_app import common, generation, steps

    assert list(steps.chunks(1, 5, 0)) == [(1, 5)]
    assert list(steps.chunks(1, 5, 2)) == [(1, 2), (3, 4), (5, 5)]

    r_missing = live_studio_server.post("/api/plan", {"project": "nonexistent_proj", "steps": {"write": True}})
    assert r_missing.status == 400

    book_dir = isolated_workspace.root / "projects" / "books" / "empty_mv"
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "movies.json").write_text(json.dumps({"shots": []}), encoding="utf-8")
    (book_dir / "all_shots.csv").write_text("shot,chapter\n", encoding="utf-8")
    with pytest.raises(common.PlanError):
        generation.film_steps({"service": "computer", "gpu": "local", "aspect": "16:9", "sync": "gentle"}, "empty_mv")


def test_f11_boundary_audiobook_render_missing_csv_returns_400(live_studio_server: StudioHarness) -> None:
    book_dir = live_studio_server.workspace.root / "projects" / "books" / "empty_book"
    book_dir.mkdir(parents=True, exist_ok=True)

    r_ab = live_studio_server.post("/api/audiobook_render", {"project": "empty_book"})
    assert r_ab.status == 400
    assert "audiobook.csv" in r_ab.json()["error"]

    r_sound = live_studio_server.get("/api/sound?project=empty_book")
    assert r_sound.status == 200
    assert r_sound.json()["audiobook"]["chapters"] == 0
    assert r_sound.json()["audiobook"]["rendered"] == 0
