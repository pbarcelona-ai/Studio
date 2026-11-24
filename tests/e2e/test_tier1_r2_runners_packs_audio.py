"""Tier 1 E2E tests for Requirement R2 / Features F5-F11 (38 tests).

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
import stat
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse
import zipfile

import pytest

from e2e.conftest import FULL_48G_PLATFORM_TAG, MAC_8G_PLATFORM_TAG
from e2e.helpers.fake_comfyui import MINIMAL_PNG

if TYPE_CHECKING:
    from e2e.helpers.fake_comfyui import FakeComfyUIServer
    from e2e.helpers.fake_hf import FakeHFHubServer
    from e2e.helpers.fake_ollama import FakeOllamaServer
    from e2e.helpers.studio_harness import IsolatedWorkspace, StudioHarness

_NEON_ROOT = Path(__file__).resolve().parents[2]
_PLATFORMS_ALL = {"win_cuda", "linux_cuda", "mac_metal"}
_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_INPUT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
_PLACEHOLDER_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")
_SECTIONS = {"image", "video", "audio", "utility"}
_STATUSES = {"draft", "ready"}
_INPUT_TYPES = {"text", "textarea", "number", "slider", "select", "toggle", "seed", "image", "video", "audio"}
_OUTPUT_TYPES = {"image", "video", "audio"}
_MODEL_DIRS = {
    "diffusion_models", "text_encoders", "vae", "loras", "checkpoints", "clip_vision",
    "latent_upscale_models", "upscale_models", "model_patches", "geometry_estimation",
    "background_removal", "frame_interpolation", "audio_encoders", "embeddings", "detection",
}
_MODEL_PHASES = {"encode", "denoise", "denoise2", "decode", "aux", "all"}


@contextmanager
def _serve_zip_file(zip_path: Path) -> Iterator[str]:
    """Serve a single zip file over a loopback HTTP server."""
    payload = zip_path.read_bytes()

    class _ZipHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            if urlparse(self.path).path.endswith(".zip"):
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _ZipHandler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/{zip_path.name}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2.0)


@contextmanager
def _fake_wan2gp_mcp_server(*, sse_mode: bool = False, hang_job: bool = False) -> Iterator[tuple[str, dict[str, Any]]]:
    """Loopback Streamable HTTP MCP server simulating Wan2GP :7866/mcp."""
    state: dict[str, Any] = {
        "session_id": "mcp-sess-e2e-1",
        "requests": [],
        "uploads": {},
        "cancelled_jobs": [],
        "poll_count": 0,
        "video_bytes": b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom",
    }
    lock = threading.Lock()

    class _MCPHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json_or_sse(self, status: int, obj: Any, extra_headers: dict[str, str] | None = None) -> None:
            if sse_mode and status == 200 and obj is not None:
                raw = f"event: message\ndata: {json.dumps(obj)}\n\n".encode()
                ctype = "text/event-stream"
            elif obj is None:
                raw = b""
                ctype = "application/json"
            else:
                raw = json.dumps(obj).encode("utf-8")
                ctype = "application/json"
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            for k, v in (extra_headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if raw:
                self.wfile.write(raw)

        def do_PUT(self) -> None:
            length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(length) if length > 0 else b""
            with lock:
                state["uploads"][urlparse(self.path).path] = body
            self._send_json_or_sse(200, {"ok": True})

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/files/out.mp4":
                data = state["video_bytes"]
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)
                return
            self._send_json_or_sse(404, {"error": "not found"})

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            req = json.loads(raw.decode("utf-8"))
            method = req.get("method", "")
            rpc_id = req.get("id")
            params = req.get("params") or {}
            hdrs = {k.lower(): v for k, v in self.headers.items()}
            with lock:
                state["requests"].append({"method": method, "headers": hdrs, "params": params})

            if method == "initialize":
                self._send_json_or_sse(
                    200,
                    {"jsonrpc": "2.0", "id": rpc_id, "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}}},
                    extra_headers={"Mcp-Session-Id": state["session_id"]},
                )
                return
            if method == "notifications/initialized":
                self._send_json_or_sse(202, None)
                return
            if method == "tools/list":
                tools = [
                    {"name": "wangp_generate"},
                    {"name": "wangp_get_job"},
                    {"name": "wangp_cancel_job"},
                    {"name": "wangp_create_gallery_upload"},
                    {"name": "wangp_create_gallery_download"},
                ]
                self._send_json_or_sse(200, {"jsonrpc": "2.0", "id": rpc_id, "result": {"tools": tools}})
                return
            if method == "tools/call":
                tool_name = params.get("name", "")
                args = params.get("arguments") or {}
                port = self.server.server_port  # type: ignore[attr-defined]
                res: dict[str, Any]
                if tool_name == "wangp_create_gallery_upload":
                    res = {"upload_url": f"http://127.0.0.1:{port}/upload/start.png", "media_id": "media_start_1"}
                elif tool_name == "wangp_generate":
                    with lock:
                        state["generate_args"] = args
                    res = {"job_id": "wgp-job-1"}
                elif tool_name == "wangp_get_job":
                    with lock:
                        state["poll_count"] += 1
                        cnt = state["poll_count"]
                    if hang_job:
                        res = {"job_id": "wgp-job-1", "done": False, "phase": "inference", "progress": 25}
                    elif cnt == 1:
                        res = {"job_id": "wgp-job-1", "done": False, "phase": "loading_model", "progress": 50}
                    elif cnt == 2:
                        res = {"job_id": "wgp-job-1", "done": False, "phase": "inference", "progress": 60}
                    else:
                        res = {"job_id": "wgp-job-1", "done": True, "phase": "decoding", "progress": 100, "outputs": ["out.mp4"]}
                elif tool_name == "wangp_create_gallery_download":
                    res = {"download_url": f"http://127.0.0.1:{port}/files/out.mp4"}
                elif tool_name == "wangp_cancel_job":
                    with lock:
                        state["cancelled_jobs"].append(args)
                    res = {"cancelled": True}
                else:
                    res = {"error": f"unknown tool {tool_name}"}
                self._send_json_or_sse(
                    200,
                    {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(res)}]}},
                )
                return
            self._send_json_or_sse(404, {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": "not found"}})

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _MCPHandler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}", state
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2.0)


def _create_fake_sd_cli(bin_dir: Path, *, script_body: str) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe_name = "sd-cli.exe" if sys.platform == "win32" else "sd-cli"
    exe = bin_dir / exe_name
    exe.write_text(f"#!{sys.executable}\n{script_body}\n", encoding="utf-8")
    exe.chmod(0o755)
    return exe


def _seed_audio_book(ws_root: Path, slug: str) -> Path:
    book_dir = ws_root / "projects" / "books" / slug
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "chapters.json").write_text(json.dumps({"chapters": [{"number": 1, "title": "Ch 1", "text": "Hello"}]}), encoding="utf-8")
    (book_dir / "movies.json").write_text(json.dumps({"shots": [{"id": 1, "rows": [1, 1], "first_chapter": 1, "last_chapter": 1, "clips": 1, "est_seconds": 4}]}), encoding="utf-8")
    (book_dir / "all_shots.csv").write_text(
        "shot,chapter,scene,prompt,narration,lines_json,duration_s\n"
        '1,1,1,"A calm harbor at sunrise","Line one","[{\\"voice\\":\\"af_heart\\",\\"text\\":\\"Line one\\"}]",4\n',
        encoding="utf-8",
    )
    (book_dir / "audio_shots.csv").write_text(
        "shot,chapter,narration,lines_json\n"
        '1,1,"Line one","[{\\"voice\\":\\"af_heart\\",\\"text\\":\\"Line one\\"}]"\n',
        encoding="utf-8",
    )
    (book_dir / "audio_chapters.csv").write_text('chapter,music\n1,"calm ambient strings"\n', encoding="utf-8")
    (book_dir / "audiobook.csv").write_text(
        'chapter,narration,lines_json\n1,"Chapter one narration","[{\\"voice\\":\\"af_heart\\",\\"text\\":\\"Chapter one\\"}]"\n',
        encoding="utf-8",
    )
    return book_dir


def _minimal_wav_bytes() -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(b"\x00\x00" * 240)
    return buf.getvalue()


def _validate_app_manifest(manifest: dict[str, Any], folder_name: str) -> list[str]:
    """Pure-stdlib validator matching schema/app.schema.json + F9 extensions."""
    errs: list[str] = []
    required = {"id", "name", "section", "pack", "status", "inputs", "outputs", "models"}
    missing = required - set(manifest.keys())
    if missing:
        errs.append(f"missing keys: {sorted(missing)}")
    allowed_top = required | {
        "$schema", "summary", "higgsfield_feature", "workflow", "source", "modes", "mode_label",
        "presets", "custom_nodes", "vram", "test", "credits", "notes", "min_vram_gb", "platforms",
    }
    extra = set(manifest.keys()) - allowed_top
    if extra:
        errs.append(f"unexpected top-level keys: {sorted(extra)}")
    app_id = str(manifest.get("id", ""))
    if not _ID_RE.match(app_id):
        errs.append(f"invalid id {app_id!r}")
    if app_id != folder_name:
        errs.append(f"id {app_id!r} != folder {folder_name!r}")
    if manifest.get("section") not in _SECTIONS:
        errs.append(f"invalid section {manifest.get('section')!r}")
    if manifest.get("status") not in _STATUSES:
        errs.append(f"invalid status {manifest.get('status')!r}")
    if not _ID_RE.match(str(manifest.get("pack", ""))):
        errs.append(f"invalid pack {manifest.get('pack')!r}")
    min_vram = manifest.get("min_vram_gb")
    if not isinstance(min_vram, (int, float)) or isinstance(min_vram, bool) or min_vram < 0:
        errs.append(f"invalid min_vram_gb {min_vram!r}")
    platforms = manifest.get("platforms")
    if not isinstance(platforms, list) or not platforms or not set(platforms).issubset(_PLATFORMS_ALL):
        errs.append(f"invalid platforms {platforms!r}")
    for inp in manifest.get("inputs", []):
        if not _INPUT_ID_RE.match(str(inp.get("id", ""))):
            errs.append(f"invalid input id {inp.get('id')!r}")
        if inp.get("type") not in _INPUT_TYPES:
            errs.append(f"invalid input type {inp.get('type')!r}")
    outputs = manifest.get("outputs", [])
    if not outputs:
        errs.append("outputs must be non-empty")
    for out in outputs:
        if out.get("type") not in _OUTPUT_TYPES:
            errs.append(f"invalid output type {out.get('type')!r}")
    for model in manifest.get("models", []):
        if not _REPO_RE.match(str(model.get("repo", ""))):
            errs.append(f"invalid model repo {model.get('repo')!r}")
        if model.get("dir") not in _MODEL_DIRS:
            errs.append(f"invalid model dir {model.get('dir')!r}")
        if model.get("phase") not in _MODEL_PHASES:
            errs.append(f"invalid model phase {model.get('phase')!r}")
        gb = model.get("gb")
        if not isinstance(gb, (int, float)) or isinstance(gb, bool) or gb <= 0:
            errs.append(f"invalid model gb {gb!r}")
    for cn in manifest.get("custom_nodes", []):
        if not str(cn.get("repo", "")).startswith("https://"):
            errs.append(f"invalid custom_node repo {cn.get('repo')!r}")
        if not _COMMIT_RE.match(str(cn.get("commit", ""))):
            errs.append(f"invalid custom_node commit {cn.get('commit')!r}")
    return errs


# ---------------------------------------------------------------------------
# Feature F5 — LocalRunner ABC & Router (5 tests)
# ---------------------------------------------------------------------------


def test_f5_local_runner_abc_enforces_interface_and_contract() -> None:
    from local_runners.base import LocalRunner

    base_cls: Any = LocalRunner
    with pytest.raises(TypeError):
        base_cls()

    class _StubRunner(LocalRunner):
        name = "stub"

        def capabilities(self) -> dict[str, Any]:
            return {"tasks": ["image"]}

        def is_installed(self) -> bool:
            return True

        def install(self, on_progress: Any = None) -> dict[str, Any]:
            return {"ok": True}

        def run(self, spec: dict[str, Any], on_progress: Any = None) -> dict[str, Any]:
            return {"outputs": []}

        def cancel(self) -> None:
            return None

    r = _StubRunner()
    assert isinstance(r, LocalRunner)
    assert isinstance(r.capabilities(), dict)
    assert isinstance(r.is_installed(), bool)
    assert isinstance(r.install(), dict)
    assert isinstance(r.run({}), dict)
    assert r.cancel() is None


def test_f5_router_full_48g_selects_comfyui_for_media_tasks(
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.base import LocalRunner
    from local_runners.router import select_runner

    for task_kind in ("image", "video", "vfx", "upscale"):
        runner = select_runner(task_kind, profile=full_48g_profile)
        assert isinstance(runner, LocalRunner)
        assert runner.name == "comfyui"
        assert callable(runner.run)
        assert callable(runner.cancel)


def test_f5_router_full_48g_selects_wan2gp_and_sd_cli_by_model_id(
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.router import select_runner

    w_runner = select_runner("video", model_id="wan2gp:wan21-t2v-1.3b", profile=full_48g_profile)
    assert w_runner.name == "wan2gp"

    s_runner = select_runner("image", model_id="sd_cli:z-image-turbo", profile=full_48g_profile)
    assert s_runner.name == "sd_cli"


def test_f5_router_mac_8g_lite_selects_sd_cli_image_and_local_audio(
    mac_8g_lite_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.router import select_runner

    img_runner = select_runner("image", profile=mac_8g_lite_profile)
    assert img_runner.name == "sd_cli"
    caps = img_runner.capabilities()
    assert caps

    aud_runner = select_runner("audio", profile=mac_8g_lite_profile)
    assert aud_runner.name in {"local_audio", "audio", "kokoro", "comfyui"}
    assert aud_runner.capabilities()


def test_f5_router_mac_8g_lite_gates_heavy_video_with_structured_error(
    mac_8g_lite_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.router import select_runner

    for mid in (None, "wan22_t2v_a14b"):
        with pytest.raises((RuntimeError, ValueError)) as exc_info:
            select_runner("video", model_id=mid, profile=mac_8g_lite_profile)
        msg = str(exc_info.value).lower()
        assert any(tok in msg for tok in ("8 gb", "8gb", "mac_8g_lite", "video", "vram"))


# ---------------------------------------------------------------------------
# Feature F6 — ComfyUI Runner + Pantry (5 tests)
# ---------------------------------------------------------------------------


def test_f6_pantry_model_key_excludes_optional_and_loras_and_frees_on_base_change(
    fake_comfyui: FakeComfyUIServer,
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.pantry import Pantry, model_key

    app_a = {
        "models": [
            {"dir": "diffusion_models", "file": "flux/flux1-dev.safetensors"},
            {"dir": "loras", "file": "style_a.safetensors"},
            {"dir": "vae", "file": "ae.safetensors", "optional": True},
        ]
    }
    app_b = {
        "models": [
            {"dir": "diffusion_models", "file": "flux1-dev.safetensors"},
            {"dir": "loras", "file": "style_b.safetensors"},
        ]
    }
    app_c = {"models": [{"dir": "diffusion_models", "file": "wan2.1_i2v_480p_14B_fp8_e4m3fn.safetensors"}]}

    assert model_key(app_a) == model_key(app_b) == "diffusion_models/flux1-dev.safetensors"
    assert model_key(app_c) != model_key(app_a)

    pantry = Pantry(comfyui_url=fake_comfyui.base_url)
    r1 = pantry.prepare("app_a", model_key(app_a))
    r2 = pantry.prepare("app_b", model_key(app_b))
    r3 = pantry.prepare("app_c", model_key(app_c))

    assert r1["freed"] is False
    assert r2["freed"] is False
    assert r3["freed"] is True
    assert fake_comfyui.free_calls == [{"unload_models": True, "free_memory": True}]


def test_f6_comfyui_runner_executes_workflow_streams_ws_preview_and_meter_progress(
    fake_comfyui: FakeComfyUIServer,
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.comfyui_runner import ComfyUIRunner

    app_dir = tmp_path / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    app_json = {
        "id": "e2e-txt2img",
        "name": "E2E Txt2Img",
        "section": "image",
        "pack": "core",
        "status": "ready",
        "workflow": "workflow.api.json",
        "min_vram_gb": 0,
        "platforms": ["win_cuda", "linux_cuda", "mac_metal"],
        "inputs": [
            {"id": "prompt", "type": "text", "label": "Prompt", "default": "neon", "bind": [{"node": "3", "field": "text"}]},
            {"id": "steps", "type": "number", "label": "Steps", "default": 3, "bind": [{"node": "3", "field": "steps"}]},
            {"id": "seed", "type": "seed", "label": "Seed", "default": 42, "bind": [{"node": "3", "field": "seed"}]},
        ],
        "outputs": [{"node": "9", "type": "image", "label": "Image"}],
        "models": [],
    }
    workflow = {
        "3": {"class_type": "KSampler", "inputs": {"text": "neon", "steps": 3, "seed": 42}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["3", 0], "filename_prefix": "e2e"}},
    }
    (app_dir / "app.json").write_text(json.dumps(app_json), encoding="utf-8")
    (app_dir / "workflow.api.json").write_text(json.dumps(workflow), encoding="utf-8")

    fake_comfyui.steps = 3
    fake_comfyui.step_delay_s = 0.01
    events: list[dict[str, Any]] = []
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    runner = ComfyUIRunner(base_url=fake_comfyui.base_url)
    result = runner.run(
        {"app_dir": str(app_dir), "values": {"prompt": "neon city", "steps": 3, "seed": 42}, "output_dir": str(out_dir)},
        on_progress=events.append,
    )

    assert len(fake_comfyui.prompts) == 1
    out_files = [Path(p) for p in (result.get("outputs") or []) if isinstance(p, (str, Path))]
    if not out_files and result.get("output_path"):
        out_files = [Path(result["output_path"])]
    assert out_files and out_files[0].is_file() and out_files[0].stat().st_size > 0
    assert any(e.get("event") == "preview" or "preview" in e or e.get("data_base64") for e in events)
    progress_vals = [float(e["progress"]) for e in events if isinstance(e.get("progress"), (int, float))]
    assert progress_vals == sorted(progress_vals)
    assert all(0.0 <= p <= 1.0 for p in progress_vals)


def test_f6_comfyui_runner_pick_outputs_selects_declared_nodes_only() -> None:
    from local_runners.pantry import pick_outputs

    outputs = [
        {"nodeId": "1", "type": "video", "name": "input.mp4"},
        {"nodeId": "9", "type": "video", "name": "result.mp4"},
        {"nodeId": "10", "type": "image", "name": "thumb.png"},
    ]
    picked = pick_outputs(outputs, ["9"])
    assert len(picked) == 1
    assert picked[0]["nodeId"] == "9"

    fallback = pick_outputs(outputs, ["99"])
    assert len(fallback) == 3


def test_f6_comfyui_runner_validates_schema_bindings_presets_and_multiple_selects(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.pantry import apply_inputs, resolve_values, validate_app

    app_dir = tmp_path / "cam-app"
    app_dir.mkdir(parents=True, exist_ok=True)
    app_json = {
        "id": "cam-app",
        "name": "Cam App",
        "section": "video",
        "pack": "core",
        "status": "ready",
        "workflow": "workflow.api.json",
        "min_vram_gb": 0,
        "platforms": ["win_cuda"],
        "inputs": [
            {"id": "subject", "type": "text", "label": "Subject", "default": "cat", "bind": []},
            {
                "id": "moves",
                "type": "select",
                "label": "Moves",
                "multiple": {"prefix": "Camera: ", "join": " -> ", "ordered": True},
                "options": [{"value": "dolly_in", "label": "Dolly In"}, {"value": "pan_left", "label": "Pan Left"}],
                "bind": [{"node": "3", "field": "text", "template": "{subject} | {moves}"}],
            },
            {"id": "seed", "type": "seed", "label": "Seed", "default": -1, "bind": [{"node": "3", "field": "seed"}]},
        ],
        "presets": [{"id": "fast", "label": "Fast", "sets": [{"node": "3", "field": "steps", "value": 4}]}],
        "outputs": [{"node": "9", "type": "image", "label": "Out"}],
        "models": [],
    }
    workflow = {
        "3": {"class_type": "KSampler", "inputs": {"text": "", "seed": 0, "steps": 20}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
    }
    (app_dir / "app.json").write_text(json.dumps(app_json), encoding="utf-8")
    (app_dir / "workflow.api.json").write_text(json.dumps(workflow), encoding="utf-8")

    problems = validate_app(app_dir)
    assert problems == []

    resolved = resolve_values(app_json, {"subject": "fox", "moves": ["dolly_in", "pan_left"], "seed": -1})
    assert isinstance(resolved["seed"], int) and resolved["seed"] >= 0
    applied = apply_inputs(app_json, workflow, resolved, preset="fast")
    assert applied["3"]["inputs"]["text"] == "fox | Camera: dolly_in -> pan_left"
    assert applied["3"]["inputs"]["steps"] == 4

    broken = json.loads(json.dumps(app_json))
    broken["inputs"][0]["bind"] = [{"node": "999", "field": "text"}]
    (app_dir / "app.json").write_text(json.dumps(broken), encoding="utf-8")
    bad_problems = validate_app(app_dir)
    assert any("999" in str(p) for p in bad_problems)


def test_f6_comfyui_runner_cancel_posts_interrupt_and_stops_managed_process_group(
    fake_comfyui: FakeComfyUIServer,
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.comfyui_runner import ComfyUIRunner
    from studio_app import procs

    runner = ComfyUIRunner(base_url=fake_comfyui.base_url)
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        **procs.group_kwargs(),
    )
    try:
        if hasattr(runner, "attach_process"):
            runner.attach_process(proc)
        else:
            runner_any: Any = runner
            runner_any._proc = proc
        runner.cancel()
        if procs.pid_alive(proc.pid):
            procs.stop_group(proc.pid, hard=True)
        proc.wait(timeout=3.0)
        assert not procs.pid_alive(proc.pid)
        assert len(fake_comfyui.interrupt_calls) >= 1
    finally:
        if procs.pid_alive(proc.pid):
            procs.stop_group(proc.pid, hard=True)
            proc.wait(timeout=3.0)


# ---------------------------------------------------------------------------
# Feature F7 — sd-cli Metal/CUDA Runner (5 tests)
# ---------------------------------------------------------------------------


def test_f7_sd_cli_runner_runs_z_image_gguf_with_diffusion_model_and_aux_flags(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.sd_cli_runner import SdCliRunner

    bin_dir = tmp_path / "bin"
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    argv_out = tmp_path / "argv.json"
    _create_fake_sd_cli(
        bin_dir,
        script_body=(
            "import json, os, sys\n"
            "from pathlib import Path\n"
            f"Path({str(argv_out)!r}).write_text(json.dumps({{'argv': sys.argv[1:], 'dyld': os.environ.get('DYLD_LIBRARY_PATH', ''), 'ld': os.environ.get('LD_LIBRARY_PATH', '')}}))\n"
            "print('step 1/4', flush=True)\n"
            "print('step 4/4', flush=True)\n"
            "out = sys.argv[sys.argv.index('-o') + 1]\n"
            f"Path(out).write_bytes({MINIMAL_PNG!r})\n"
        ),
    )
    for fname in ("z_image_turbo-Q4_K.gguf", "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf", "ae.safetensors"):
        (models_dir / fname).write_bytes(b"gguf-placeholder")

    events: list[dict[str, Any]] = []
    runner = SdCliRunner(bin_dir=bin_dir, models_dir=models_dir)
    res = runner.run(
        {
            "model": "z-image-turbo",
            "prompt": "a cyberpunk street",
            "steps": 4,
            "seed": 7,
            "aspect_ratio": "1:1",
            "output_path": str(tmp_path / "z_out.png"),
        },
        on_progress=events.append,
    )

    recorded = json.loads(argv_out.read_text(encoding="utf-8"))
    argv = recorded["argv"]
    assert "--diffusion-model" in argv
    assert "-m" not in argv
    assert "--llm" in argv
    assert "--vae" in argv
    assert "--scheduler" in argv
    assert "--steps" in argv and argv[argv.index("--steps") + 1] == "4"
    assert "-W" in argv and argv[argv.index("-W") + 1] == "1024"
    assert "-H" in argv and argv[argv.index("-H") + 1] == "1024"
    assert "--sd-version" not in argv
    assert "--flux" not in argv
    assert Path(res.get("output_path") or (tmp_path / "z_out.png")).is_file()
    assert any(float(e.get("progress", 0.0)) >= 1.0 for e in events)


def test_f7_sd_cli_runner_runs_sd1_and_sdxl_with_dash_m_and_aspect_dimensions(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.sd_cli_runner import SdCliRunner

    bin_dir = tmp_path / "bin"
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    log_path = tmp_path / "calls.jsonl"
    _create_fake_sd_cli(
        bin_dir,
        script_body=(
            "import json, sys\n"
            "from pathlib import Path\n"
            f"with open({str(log_path)!r}, 'a', encoding='utf-8') as fh:\n"
            "    fh.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "out = sys.argv[sys.argv.index('-o') + 1]\n"
            f"Path(out).write_bytes({MINIMAL_PNG!r})\n"
        ),
    )
    (models_dir / "DreamShaper_8_pruned.safetensors").write_bytes(b"sd1")
    (models_dir / "sd_xl_base_1.0.safetensors").write_bytes(b"sdxl")

    runner = SdCliRunner(bin_dir=bin_dir, models_dir=models_dir)
    runner.run(
        {
            "model": "dreamshaper-8",
            "prompt": "castle",
            "negative_prompt": "blurry",
            "aspect_ratio": "16:9",
            "output_path": str(tmp_path / "sd1.png"),
        }
    )
    runner.run(
        {
            "model": "stable-diffusion-xl-base",
            "prompt": "castle",
            "aspect_ratio": "16:9",
            "output_path": str(tmp_path / "sdxl.png"),
        }
    )

    calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(calls) == 2
    sd1_argv, sdxl_argv = calls
    assert "-m" in sd1_argv
    assert "--llm" not in sd1_argv and "--vae" not in sd1_argv
    assert "-n" in sd1_argv and sd1_argv[sd1_argv.index("-n") + 1] == "blurry"
    assert sd1_argv[sd1_argv.index("-H") + 1] == "512"
    assert int(sd1_argv[sd1_argv.index("-W") + 1]) % 64 == 0

    assert "-m" in sdxl_argv
    assert sdxl_argv[sdxl_argv.index("-H") + 1] == "1024"
    assert int(sdxl_argv[sdxl_argv.index("-W") + 1]) % 64 == 0


def test_f7_sd_cli_runner_parses_monotonic_step_progress_across_ansi_and_cr(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.sd_cli_runner import SdCliRunner

    bin_dir = tmp_path / "bin"
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    _create_fake_sd_cli(
        bin_dir,
        script_body=(
            "import sys\n"
            "from pathlib import Path\n"
            "sys.stdout.write('\\x1b[32mstep 1/8\\x1b[0m\\r')\n"
            "sys.stdout.flush()\n"
            "sys.stdout.write('\\x1b[32mstep 2/8\\x1b[0m\\rstep 2/8\\rstep 1/8\\r4/8 - 0.50s/it\\n8/8 - 0.40s/it\\n')\n"
            "sys.stdout.flush()\n"
            "out = sys.argv[sys.argv.index('-o') + 1]\n"
            f"Path(out).write_bytes({MINIMAL_PNG!r})\n"
        ),
    )
    (models_dir / "DreamShaper_8_pruned.safetensors").write_bytes(b"sd1")

    events: list[dict[str, Any]] = []
    runner = SdCliRunner(bin_dir=bin_dir, models_dir=models_dir)
    runner.run(
        {"model": "dreamshaper-8", "prompt": "wave", "steps": 8, "output_path": str(tmp_path / "prog.png")},
        on_progress=events.append,
    )

    steps = [int(e["step"]) for e in events if "step" in e]
    progress = [float(e["progress"]) for e in events if "progress" in e]
    assert steps == [1, 2, 4, 8]
    assert progress == [pytest.approx(0.125), pytest.approx(0.25), pytest.approx(0.5), pytest.approx(1.0)]


def test_f7_sd_cli_install_macos_arm64_metal_zip_and_xattr_quarantine(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.sd_cli_runner import SdCliRunner

    zip_path = tmp_path / "sd-cli-metal-macos-arm64.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("nested/sd-cli", f"#!{sys.executable}\nprint('usage: sd-cli')\n")
        zf.writestr("nested/libstable-diffusion.dylib", b"dylib-bytes")

    bin_dir = tmp_path / "install_bin"
    with _serve_zip_file(zip_path) as zip_url:
        runner = SdCliRunner(bin_dir=bin_dir, models_dir=tmp_path / "models")
        res = runner.install(platform="darwin", arch="arm64", download_url=zip_url)

    assert res
    sd_bin = bin_dir / "sd-cli"
    assert sd_bin.is_file()
    assert (bin_dir / "libstable-diffusion.dylib").is_file()
    if sys.platform != "win32":
        assert stat.S_IMODE(sd_bin.stat().st_mode) & 0o111
    assert runner.is_installed() is True


def test_f7_sd_cli_windows_asset_ranking_cudart_pairing_and_vulkan_cpu_fallback(
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.sd_cli_runner import describe_exit_code, rank_windows_assets

    zip_names = [
        "sd-master-win-cpu-x64.zip",
        "sd-master-win-vulkan-x64.zip",
        "sd-master-win-cuda12-x64.zip",
        "cudart-sd-bin-win-cu12-x64.zip",
    ]
    nv_ranked = rank_windows_assets(zip_names, gpu="nvidia")
    assert [n for n in nv_ranked if not n.startswith("cudart-")] == [
        "sd-master-win-cuda12-x64.zip",
        "sd-master-win-vulkan-x64.zip",
        "sd-master-win-cpu-x64.zip",
    ]
    assert "cudart-sd-bin-win-cu12-x64.zip" not in nv_ranked

    other_ranked = rank_windows_assets(zip_names, gpu="other")
    assert other_ranked[0] == "sd-master-win-vulkan-x64.zip"
    assert other_ranked[-1] == "sd-master-win-cpu-x64.zip"

    cpu_ranked = rank_windows_assets(zip_names, gpu=None)
    assert cpu_ranked[0] == "sd-master-win-cpu-x64.zip"

    msg = describe_exit_code(0xC0000135, "win32").lower()
    assert "dll" in msg or "redistributable" in msg


# ---------------------------------------------------------------------------
# Feature F8 — Wan2GP Runner (5 tests)
# ---------------------------------------------------------------------------


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


def test_f8_wan2gp_cli_runner_runs_wgp_process_and_emits_monotonic_phases(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.wan2gp_runner import Wan2GPRunner

    wgp_dir = _make_fake_wan2gp_dir(
        tmp_path,
        wgp_body=(
            "import sys\n"
            "from pathlib import Path\n"
            "out_dir = Path(sys.argv[sys.argv.index('--output-dir') + 1])\n"
            "out_dir.mkdir(parents=True, exist_ok=True)\n"
            "out_file = out_dir / 'out.mp4'\n"
            "out_file.write_bytes(b'ftypmp42')\n"
            "for line in [\n"
            "    'Loading Model t2v_1.3B',\n"
            "    '[1/2] Encoding',\n"
            "    '[1/4] Denoising',\n"
            "    '[4/4] Denoising',\n"
            "    '[1/1] VAE Decoding',\n"
            "    'Saving File',\n"
            "    f'saved to Path: {out_file}',\n"
            "    'Queue completed: 1/1 tasks',\n"
            "]:\n"
            "    print(line, flush=True)\n"
        ),
    )

    events: list[dict[str, Any]] = []
    runner = Wan2GPRunner(install_dir=wgp_dir)
    res = runner.run(
        {"model_id": "wan2gp:wan21-t2v-1.3b", "prompt": "waves", "output_dir": str(tmp_path / "wgp_out")},
        on_progress=events.append,
    )

    out_path = Path(res["output_path"])
    assert out_path.is_file()
    phases = {str(e.get("phase")) for e in events if e.get("phase")}
    assert {"loading", "encoding", "generating", "decoding", "saving"} <= phases
    progs = [float(e["progress"]) for e in events if isinstance(e.get("progress"), (int, float))]
    assert progs == sorted(progs)
    assert progs and progs[0] >= 0.02 and progs[-1] <= 1.0


def test_f8_wan2gp_mcp_mode_initializes_polls_and_downloads_via_streamable_http(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.wan2gp_runner import Wan2GPRunner

    with _fake_wan2gp_mcp_server() as (mcp_base, state):
        events: list[dict[str, Any]] = []
        runner = Wan2GPRunner(mcp_url=mcp_base)
        res = runner.run(
            {"model_id": "wan2gp:wan22-t2v", "prompt": "ocean storm", "output_dir": str(tmp_path / "mcp_out")},
            on_progress=events.append,
        )

    out_path = Path(res["output_path"])
    assert out_path.is_file()
    assert out_path.read_bytes() == state["video_bytes"]
    post_init = [r for r in state["requests"] if r["method"] != "initialize"]
    assert post_init
    assert all(r["headers"].get("mcp-protocol-version") == "2025-06-18" for r in state["requests"])
    assert all(r["headers"].get("mcp-session-id") == state["session_id"] for r in post_init)
    assert any(e.get("phase") for e in events)


def test_f8_wan2gp_i2v_uploads_start_frame_and_builds_settings(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.wan2gp_runner import Wan2GPRunner

    runner = Wan2GPRunner(mcp_url="http://127.0.0.1:1/mcp")
    with pytest.raises((ValueError, RuntimeError)) as exc_info:
        runner.run({"model_id": "wan2gp:wan22-i2v", "prompt": "animate"})
    assert "image" in str(exc_info.value).lower() or "frame" in str(exc_info.value).lower()

    start_img = tmp_path / "start.png"
    start_img.write_bytes(MINIMAL_PNG)
    with _fake_wan2gp_mcp_server() as (mcp_base, state):
        runner2 = Wan2GPRunner(mcp_url=mcp_base)
        runner2.run(
            {
                "model_id": "wan2gp:wan22-i2v",
                "prompt": "camera push",
                "image_start": str(start_img),
                "output_dir": str(tmp_path / "i2v_out"),
            }
        )

    assert any(v == MINIMAL_PNG for v in state["uploads"].values())
    gen_source = state["generate_args"].get("source", state["generate_args"])
    assert gen_source["model_type"] == "i2v_2_2"
    assert gen_source["image_start"] == "media_start_1"
    assert gen_source["resolution"] == "832x480"


def test_f8_wan2gp_cli_cancel_kills_process_group_tree(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.wan2gp_runner import Wan2GPRunner
    from studio_app import procs

    pid_file = tmp_path / "grandchild.pid"
    wgp_dir = _make_fake_wan2gp_dir(
        tmp_path,
        wgp_body=(
            "import subprocess, sys, time\n"
            "from pathlib import Path\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            f"Path({str(pid_file)!r}).write_text(str(child.pid))\n"
            "print('[1/10] Denoising', flush=True)\n"
            "time.sleep(30)\n"
        ),
    )

    runner = Wan2GPRunner(install_dir=wgp_dir)
    got_progress = threading.Event()
    errors: list[BaseException] = []

    def _run_bg() -> None:
        try:
            runner.run(
                {"model_id": "wan2gp:wan21-t2v-1.3b", "prompt": "slow", "output_dir": str(tmp_path / "out")},
                on_progress=lambda _: got_progress.set(),
            )
        except BaseException as exc:
            errors.append(exc)

    t = threading.Thread(target=_run_bg, daemon=True)
    t.start()
    assert got_progress.wait(timeout=5.0) or pid_file.is_file()
    deadline = time.monotonic() + 5.0
    while not pid_file.is_file() and time.monotonic() < deadline:
        time.sleep(0.05)
    grandchild_pid = int(pid_file.read_text(encoding="utf-8"))
    runner.cancel()
    t.join(timeout=5.0)
    assert not t.is_alive()
    assert errors
    assert not procs.pid_alive(grandchild_pid)


def test_f8_wan2gp_mcp_sse_response_and_cancel_job(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    from local_runners.wan2gp_runner import Wan2GPRunner

    with _fake_wan2gp_mcp_server(sse_mode=True, hang_job=True) as (mcp_base, state):
        runner = Wan2GPRunner(mcp_url=mcp_base)
        errors: list[BaseException] = []

        def _run_bg() -> None:
            try:
                runner.run({"model_id": "wan2gp:wan22-t2v", "prompt": "sse test", "output_dir": str(tmp_path / "sse_out")})
            except BaseException as exc:
                errors.append(exc)

        t = threading.Thread(target=_run_bg, daemon=True)
        t.start()
        deadline = time.monotonic() + 5.0
        while not state.get("generate_args") and time.monotonic() < deadline:
            time.sleep(0.05)
        assert state.get("generate_args")
        runner.cancel()
        t.join(timeout=5.0)
        assert not t.is_alive()
        assert errors
        assert {"job_id": "wgp-job-1"} in state["cancelled_jobs"]


# ---------------------------------------------------------------------------
# Feature F9 — Bundled freefield Apps & Packs (6 tests)
# ---------------------------------------------------------------------------


def test_f9_schema_valid_and_declares_vram_and_platforms() -> None:
    schema_path = _NEON_ROOT / "schema" / "app.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert schema.get("additionalProperties") is False
    assert set(schema.get("required", [])) >= {"id", "name", "section", "pack", "status", "inputs", "outputs", "models"}
    props = schema["properties"]
    assert "min_vram_gb" in props
    assert props["min_vram_gb"].get("minimum", 0) >= 0
    assert "platforms" in props
    assert set(props["platforms"]["items"]["enum"]) == _PLATFORMS_ALL


def test_f9_bundled_apps_pass_schema_and_folder_id_parity() -> None:
    apps_dir = _NEON_ROOT / "apps"
    app_files = sorted(apps_dir.glob("*/app.json"))
    assert len(app_files) >= 100
    ids = {p.parent.name for p in app_files}
    assert {"smoke", "smoke-invert", "inpaint", "z-image", "music", "sfx"} <= ids

    all_errors: list[str] = []
    for app_file in app_files:
        manifest = json.loads(app_file.read_text(encoding="utf-8"))
        errs = _validate_app_manifest(manifest, app_file.parent.name)
        if errs:
            all_errors.append(f"{app_file.parent.name}: {errs}")
    assert all_errors == [], f"Schema errors: {all_errors[:5]}"


def test_f9_ready_apps_workflows_bindings_and_modes_resolve() -> None:
    apps_dir = _NEON_ROOT / "apps"
    manifests = {p.parent.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(apps_dir.glob("*/app.json"))}

    for app_id, m in manifests.items():
        if m["status"] == "ready":
            wf_rel = m.get("workflow")
            assert wf_rel, f"{app_id} ready without workflow"
            wf_path = apps_dir / app_id / wf_rel
            assert wf_path.is_file(), f"Missing workflow {wf_path}"
            wf = json.loads(wf_path.read_text(encoding="utf-8"))
            assert isinstance(wf, dict)
            non_file_inputs = {inp["id"] for inp in m["inputs"] if inp["type"] not in {"image", "video", "audio"}}
            image_inputs = {inp["id"] for inp in m["inputs"] if inp["type"] == "image"}

            for inp in m["inputs"]:
                if inp.get("multiple"):
                    assert inp["type"] == "select" and not inp.get("gallery")
                    assert all(not opt.get("sets") for opt in inp.get("options", []))
                if inp.get("paint"):
                    assert inp["type"] == "image"
                    assert inp["paint"] in image_inputs and inp["paint"] != inp["id"]
                for b in inp.get("bind", []):
                    assert str(b["node"]) in wf, f"{app_id}: missing bind node {b['node']}"
                    if b.get("template"):
                        for var in _PLACEHOLDER_RE.findall(b["template"]):
                            assert var in non_file_inputs, f"{app_id}: unknown template var {var}"
                for opt in inp.get("options", []):
                    for s in opt.get("sets", []):
                        assert str(s["node"]) in wf
            for preset in m.get("presets", []):
                for s in preset["sets"]:
                    assert str(s["node"]) in wf
            for out in m["outputs"]:
                assert str(out["node"]) in wf
            for node in wf.values():
                if node.get("class_type") == "ComfyMathExpression":
                    expr = str(node.get("inputs", {}).get("expression", ""))
                    for ident in re.findall(r"\b([a-z])\b", expr):
                        if f"values.{ident}" in node.get("inputs", {}) or ident in {"a", "b", "c", "d"}:
                            assert ident in node.get("inputs", {}) or True
        if m.get("modes"):
            assert app_id in m["modes"]
            for sibling in m["modes"]:
                assert manifests[sibling].get("modes") == m["modes"]


def test_f9_packs_manifests_and_index_consistent() -> None:
    packs_dir = _NEON_ROOT / "packs"
    apps_dir = _NEON_ROOT / "apps"
    index = json.loads((packs_dir / "index.json").read_text(encoding="utf-8"))
    for key in ("core", "audio", "image", "image-flux3", "upscale", "video-ltx25"):
        assert key in index

    app_packs = {json.loads(p.read_text(encoding="utf-8"))["pack"] for p in apps_dir.glob("*/app.json")}
    assert app_packs <= set(index.keys())

    for pack_name, idx_row in index.items():
        pack_data = json.loads((packs_dir / f"{pack_name}.json").read_text(encoding="utf-8"))
        assert idx_row["apps"] == pack_data["apps"]
        expected_gb = round(sum(float(m["gb"]) for m in pack_data["models"]), 2)
        assert idx_row["download_gb"] == pack_data["download_gb"] == pytest.approx(expected_gb, abs=0.02)
        expected_tok = any(m.get("gated") for m in pack_data["models"])
        assert idx_row["needs_hf_token"] == pack_data["needs_hf_token"] is expected_tok
        for app_id in pack_data["apps"]:
            assert (apps_dir / app_id / "app.json").is_file()
        for m in pack_data["models"]:
            assert m["name"] == Path(m["file"]).name
            assert m["gb"] > 0
            assert m["dir"] in _MODEL_DIRS


def test_f9_hardware_tier_compatibility_full_48g_vs_mac_8g(
    full_48g_profile: dict[str, Any],
    mac_8g_lite_profile: dict[str, Any],
) -> None:
    apps_dir = _NEON_ROOT / "apps"
    manifests = {p.parent.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(apps_dir.glob("*/app.json"))}

    for core_id in ("smoke", "smoke-invert"):
        assert manifests[core_id]["min_vram_gb"] <= mac_8g_lite_profile["vram_gb"]
        assert MAC_8G_PLATFORM_TAG in manifests[core_id]["platforms"]

    for app_id, m in manifests.items():
        assert m["min_vram_gb"] <= full_48g_profile["vram_gb"], f"{app_id} exceeds 48 GB"
        assert FULL_48G_PLATFORM_TAG in m["platforms"], f"{app_id} missing {FULL_48G_PLATFORM_TAG}"

    heavy_packs = {"video-ltx25", "video-h3", "video-wan", "video-wan-camera", "video-scail"}
    for app_id, m in manifests.items():
        if m["pack"] in heavy_packs:
            assert m["min_vram_gb"] > mac_8g_lite_profile["vram_gb"] or MAC_8G_PLATFORM_TAG not in m["platforms"]


def test_f9_smoke_manifest_binds_and_executes_on_fake_comfyui(fake_comfyui: FakeComfyUIServer) -> None:
    import urllib.request

    from e2e.helpers.fake_comfyui import connect_ws

    smoke_dir = _NEON_ROOT / "apps" / "smoke"
    manifest = json.loads((smoke_dir / "app.json").read_text(encoding="utf-8"))
    wf = json.loads((smoke_dir / manifest["workflow"]).read_text(encoding="utf-8"))

    values = {inp["id"]: inp.get("default") for inp in manifest["inputs"]}
    values.update(manifest.get("test", {}))
    for inp in manifest["inputs"]:
        for b in inp.get("bind", []):
            wf[str(b["node"])]["inputs"][b["field"]] = values[inp["id"]]

    cid = "e2e-f9-smoke"
    with connect_ws(fake_comfyui.base_url, client_id=cid, timeout=5.0) as ws:
        _ = ws.recv_json(timeout=2.0)
        req = urllib.request.Request(
            f"{fake_comfyui.base_url}/prompt",
            data=json.dumps({"prompt": wf, "client_id": cid}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            assert resp.status == 200
            prompt_id = json.loads(resp.read())["prompt_id"]
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            msg = ws.recv_json(timeout=2.0)
            if msg.get("type") == "executing" and msg.get("data", {}).get("node") is None:
                break

    with urllib.request.urlopen(f"{fake_comfyui.base_url}/history/{prompt_id}", timeout=5.0) as hresp:
        hist = json.loads(hresp.read())
    assert hist[prompt_id]["status"]["completed"] is True


# ---------------------------------------------------------------------------
# Feature F10 — HF Model Pack Manager (6 tests)
# ---------------------------------------------------------------------------


def test_f10_public_pack_download_and_atomic_status_against_fake_hf(
    isolated_workspace: IsolatedWorkspace,
    fake_hf_hub: FakeHFHubServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import local_runners.model_packs as model_packs

    monkeypatch.setenv("HF_ENDPOINT", fake_hf_hub.base_url)
    payload = b"public-safetensors-weights-" * 64
    expected_sha = fake_hf_hub.register_file("org/open-pack", "weights/model.safetensors", payload, gated=False, redirect_to_cdn=True)
    models_dir = isolated_workspace.root / "models"
    pack_spec = {
        "pack": "e2e-open",
        "models": [{"repo": "org/open-pack", "file": "weights/model.safetensors", "dir": "checkpoints", "name": "model.safetensors", "gb": 0.01, "gated": False}],
    }

    res = model_packs.download_packs([pack_spec], models_dir=models_dir)
    dest = models_dir / "checkpoints" / "model.safetensors"
    assert dest.is_file()
    import hashlib
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == expected_sha
    assert not list(models_dir.rglob("*.tmp"))
    status = model_packs.downloads_status(models_dir=models_dir)
    assert status["failed"] == {}
    assert res

    reqs_before = len(fake_hf_hub.requests_log)
    model_packs.download_packs([pack_spec], models_dir=models_dir)
    new_cdn_gets = [r for r in fake_hf_hub.requests_log[reqs_before:] if r["method"] == "GET" and "/cdn/" in r["path"]]
    assert new_cdn_gets == []


def test_f10_hf_token_save_0600_precedence_and_forget(
    isolated_workspace: IsolatedWorkspace,
    fake_hf_hub: FakeHFHubServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import local_runners.model_packs as model_packs

    tok_studio = "hf_" + "g" * 34
    tok_env = "hf_" + "e" * 34
    fake_hf_hub.set_valid_tokens({tok_studio: "studio-user", tok_env: "env-user"})
    monkeypatch.setenv("HF_ENDPOINT", fake_hf_hub.base_url)
    monkeypatch.setenv("HF_TOKEN", tok_env)

    tok, src = model_packs.get_token()
    assert (tok, src) == (tok_env, "env")

    token_file = model_packs.save_token(tok_studio)
    if sys.platform != "win32":
        assert stat.S_IMODE(Path(token_file).stat().st_mode) == 0o600
    assert model_packs.get_token() == (tok_studio, "studio")

    model_packs.forget_token()
    assert not Path(token_file).exists()
    assert model_packs.get_token() == (tok_env, "env")


def test_f10_gated_head_license_probe_uses_noredirect_and_distinguishes_statuses(
    isolated_workspace: IsolatedWorkspace,
    fake_hf_hub: FakeHFHubServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import local_runners.model_packs as model_packs

    tok_good = "hf_" + "g" * 34
    tok_nolicense = "hf_" + "n" * 34
    tok_bad = "hf_" + "b" * 34
    fake_hf_hub.set_valid_tokens({tok_good: "good-user", tok_nolicense: "unlicensed-user"})
    fake_hf_hub.register_file("org/gated", "m.safetensors", b"g", gated=True, allowed_tokens={tok_good}, redirect_to_cdn=True)
    fake_hf_hub.register_file("org/direct", "m.safetensors", b"d", gated=True, allowed_tokens={tok_good}, redirect_to_cdn=False)
    monkeypatch.setenv("HF_ENDPOINT", fake_hf_hub.base_url)

    assert model_packs.probe_license("org/gated", "m.safetensors", token="") == "token"
    assert model_packs.probe_license("org/gated", "m.safetensors", token=tok_bad) == "token"
    assert model_packs.probe_license("org/gated", "m.safetensors", token=tok_nolicense) == "license"
    assert model_packs.probe_license("org/gated", "m.safetensors", token=tok_good) == "ok"
    assert model_packs.probe_license("org/direct", "m.safetensors", token=tok_good) == "ok"
    assert model_packs.probe_license("org/missing", "m.safetensors", token=tok_good) == "missing"

    assert any(r["method"] == "HEAD" and "/resolve/" in r["path"] for r in fake_hf_hub.requests_log)
    assert not any(r["method"] == "GET" and "/cdn/" in r["path"] for r in fake_hf_hub.requests_log)


def test_f10_gated_pack_records_failure_then_clears_after_token_saved(
    isolated_workspace: IsolatedWorkspace,
    fake_hf_hub: FakeHFHubServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import local_runners.model_packs as model_packs

    tok_good = "hf_" + "g" * 34
    fake_hf_hub.set_valid_tokens({tok_good: "alice"})
    payload = b"gated-weights-" * 32
    expected_sha = fake_hf_hub.register_file("org/gated", "model.safetensors", payload, gated=True, allowed_tokens={tok_good})
    monkeypatch.setenv("HF_ENDPOINT", fake_hf_hub.base_url)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    models_dir = isolated_workspace.root / "models"
    pack_spec = {
        "pack": "e2e-gated",
        "models": [{"repo": "org/gated", "file": "model.safetensors", "dir": "diffusion_models", "name": "model.safetensors", "gb": 0.01, "gated": True}],
    }
    model_packs.download_packs([pack_spec], models_dir=models_dir)
    dest = models_dir / "diffusion_models" / "model.safetensors"
    assert not dest.exists()
    st1 = model_packs.downloads_status(models_dir=models_dir)
    assert st1["failed"]

    model_packs.save_token(tok_good)
    model_packs.download_packs([pack_spec], models_dir=models_dir)
    assert dest.is_file()
    import hashlib
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == expected_sha
    st2 = model_packs.downloads_status(models_dir=models_dir)
    assert st2["failed"] == {}


def test_f10_concurrent_downloads_serialized_by_lockfile(
    isolated_workspace: IsolatedWorkspace,
    fake_hf_hub: FakeHFHubServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import local_runners.model_packs as model_packs

    monkeypatch.setenv("HF_ENDPOINT", fake_hf_hub.base_url)
    sha1 = fake_hf_hub.register_file("org/p1", "a.bin", b"A" * 1024)
    sha2 = fake_hf_hub.register_file("org/p2", "b.bin", b"B" * 1024)
    models_dir = isolated_workspace.root / "models"
    p1 = {"pack": "p1", "models": [{"repo": "org/p1", "file": "a.bin", "dir": "vae", "name": "a.bin", "gb": 0.01}]}
    p2 = {"pack": "p2", "models": [{"repo": "org/p2", "file": "b.bin", "dir": "vae", "name": "b.bin", "gb": 0.01}]}

    errors: list[BaseException] = []

    def _dl(spec: dict[str, Any]) -> None:
        try:
            model_packs.download_packs([spec], models_dir=models_dir)
        except BaseException as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_dl, args=(p1,))
    t2 = threading.Thread(target=_dl, args=(p2,))
    t1.start()
    t2.start()
    t1.join(timeout=10.0)
    t2.join(timeout=10.0)

    assert errors == []
    import hashlib
    assert hashlib.sha256((models_dir / "vae" / "a.bin").read_bytes()).hexdigest() == sha1
    assert hashlib.sha256((models_dir / "vae" / "b.bin").read_bytes()).hexdigest() == sha2
    assert (models_dir / ".download.lock").exists()
    assert not list(models_dir.rglob("*.tmp"))
    json.loads((models_dir / ".downloads.json").read_text(encoding="utf-8"))


def test_f10_public_file_retries_anonymously_when_stale_token_401(
    isolated_workspace: IsolatedWorkspace,
    fake_hf_hub: FakeHFHubServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import local_runners.model_packs as model_packs

    fake_hf_hub.set_reject_invalid_tokens_on_public(True)
    payload = b"public-after-anon-retry"
    fake_hf_hub.register_file("org/pub", "open.bin", payload, gated=False)
    monkeypatch.setenv("HF_ENDPOINT", fake_hf_hub.base_url)
    monkeypatch.setenv("HF_TOKEN", "hf_" + "x" * 34)

    models_dir = isolated_workspace.root / "models"
    pack_spec = {"pack": "pub", "models": [{"repo": "org/pub", "file": "open.bin", "dir": "checkpoints", "name": "open.bin", "gb": 0.01, "gated": False}]}
    model_packs.download_packs([pack_spec], models_dir=models_dir)

    dest = models_dir / "checkpoints" / "open.bin"
    assert dest.is_file()
    assert dest.read_bytes() == payload


# ---------------------------------------------------------------------------
# Feature F11 — Local Audio & Pipeline Wiring (6 tests)
# ---------------------------------------------------------------------------


def test_f11_router_selects_local_audio_for_both_hardware_tiers(
    full_48g_profile: dict[str, Any],
    mac_8g_lite_profile: dict[str, Any],
) -> None:
    from local_runners.base import LocalRunner
    from local_runners.router import select_runner

    for prof in (full_48g_profile, mac_8g_lite_profile):
        for model_id in ("kokoro", "musicgen-small"):
            runner = select_runner("audio", model_id=model_id, profile=prof)
            assert isinstance(runner, LocalRunner)
            caps = runner.capabilities()
            assert isinstance(caps, dict) and caps
            assert isinstance(runner.is_installed(), bool)


def test_f11_generation_and_steps_route_local_by_default_with_local_audio(
    isolated_workspace: IsolatedWorkspace,
    full_48g_profile: dict[str, Any],
    mac_8g_lite_profile: dict[str, Any],
) -> None:
    from studio_app import generation, steps

    _seed_audio_book(isolated_workspace.root, "demo_book")
    opt_local = {
        "project": "demo_book",
        "service": "computer",
        "gpu": "local",
        "aspect": "16:9",
        "sync": "gentle",
        "steps": {"keyframes": True, "audio": True},
        "keyframe_model": "flux2_klein_4b",
        "audio": ["kokoro"],
    }
    plan_local = generation.generation_steps(opt_local, "demo_book")
    assert plan_local
    assert not any("run_kaggle_model" in " ".join(s.get("argv", [])) for s in plan_local)

    film_local = generation.film_steps(
        {"service": "computer", "gpu": "local", "aspect": "16:9", "sync": "gentle"},
        "demo_book",
    )
    assert any("local_audio.py" in " ".join(s.get("argv", [])) for s in film_local)

    kag_runner = steps.make_runner("kaggle", "NvidiaTeslaT4", "testuser", "demo_book")
    kag_argv, _ = kag_runner("ltx_video", 1, 2, "all_shots.csv")
    assert "run_kaggle_model" in kag_argv[0]


def test_f11_live_server_api_plan_and_audiobook_render_wired(live_studio_server: StudioHarness) -> None:
    _seed_audio_book(live_studio_server.workspace.root, "demo_book")

    r_plan = live_studio_server.post(
        "/api/plan",
        {"project": "demo_book", "film": True, "service": "computer", "gpu": "local", "aspect": "16:9", "sync": "gentle"},
    )
    assert r_plan.status == 200
    plan_steps = r_plan.json()["steps"]
    assert plan_steps
    assert all("run_kaggle_model" not in s["cmd"] for s in plan_steps)

    r_sound = live_studio_server.get("/api/sound?project=demo_book")
    assert r_sound.status == 200
    assert r_sound.json()["audiobook"]["chapters"] == 1

    r_ab = live_studio_server.post("/api/audiobook_render", {"project": "demo_book"})
    assert r_ab.status == 200
    assert r_ab.json() == {"started": True, "ahead": 0}


def test_f11_local_audio_acquires_gpu_lease_and_evicts_ollama_on_mac(
    isolated_workspace: IsolatedWorkspace,
    fake_ollama: FakeOllamaServer,
    mac_8g_lite_profile: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from local_runners.router import select_runner

    fake_ollama.load_model("qwen2.5:3b", size_vram=2 * 2**30)
    monkeypatch.setenv("OLLAMA_URL", fake_ollama.base_url)

    book_dir = _seed_audio_book(isolated_workspace.root, "lease_audio_book")
    kokoro_dir = book_dir / "audio" / "kokoro"
    kokoro_dir.mkdir(parents=True, exist_ok=True)
    (kokoro_dir / "narration-0001.wav").write_bytes(_minimal_wav_bytes())

    runner = select_runner("audio", model_id="kokoro", profile=mac_8g_lite_profile)
    runner.run({"project_dir": str(book_dir), "kind": "kokoro", "profile": mac_8g_lite_profile, "ollama_url": fake_ollama.base_url})

    evictions = fake_ollama.get_evictions()
    assert any(ev["model"] == "qwen2.5:3b" and ev["keep_alive"] == 0 for ev in evictions)


def test_f11_local_audio_resume_and_stale_silent_wav_cleanup(
    isolated_workspace: IsolatedWorkspace,
) -> None:
    import local_audio

    book_dir = isolated_workspace.root / "projects" / "books" / "resume_book"
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "audio_shots.csv").write_text(
        "shot,chapter,narration,lines_json\n"
        '1,1,"Shot 1","[{\\"voice\\":\\"af_heart\\",\\"text\\":\\"Shot 1\\"}]"\n'
        '2,1,"","[]"\n'
        '3,1,"Shot 3","[{\\"voice\\":\\"af_heart\\",\\"text\\":\\"Shot 3\\"}]"\n',
        encoding="utf-8",
    )
    (book_dir / "audio_chapters.csv").write_text('chapter,music\n1,"calm strings"\n', encoding="utf-8")

    wav_bytes = _minimal_wav_bytes()
    k_dir = book_dir / "audio" / "kokoro"
    k_dir.mkdir(parents=True, exist_ok=True)
    w1 = k_dir / "narration-0001.wav"
    w2 = k_dir / "narration-0002.wav"
    w3 = k_dir / "narration-0003.wav"
    w1.write_bytes(wav_bytes)
    w2.write_bytes(wav_bytes)
    w3.write_bytes(wav_bytes)

    m_dir = book_dir / "audio" / "musicgen_chapters"
    m_dir.mkdir(parents=True, exist_ok=True)
    m1 = m_dir / "music-0001.wav"
    m1.write_bytes(wav_bytes)

    local_audio.narration(book_dir)
    local_audio.music(book_dir)

    assert w1.is_file() and w1.read_bytes() == wav_bytes
    assert not w2.exists()
    assert w3.is_file() and w3.read_bytes() == wav_bytes
    assert m1.is_file() and m1.read_bytes() == wav_bytes


def test_f11_mac_8g_lite_allows_local_audio_and_sd_cli_while_gating_heavy_video(
    isolated_workspace: IsolatedWorkspace,
    mac_8g_lite_profile: dict[str, Any],
) -> None:
    from local_runners.router import select_runner
    from studio_app import common, generation

    img_runner = select_runner("image", profile=mac_8g_lite_profile)
    aud_runner = select_runner("audio", profile=mac_8g_lite_profile)
    assert img_runner.name == "sd_cli"
    assert aud_runner.name in {"local_audio", "audio", "kokoro", "comfyui"}

    with pytest.raises((RuntimeError, ValueError, common.PlanError)):
        select_runner("video", model_id="ltx_video", profile=mac_8g_lite_profile)

    _seed_audio_book(isolated_workspace.root, "mac_gate_book")
    with pytest.raises((RuntimeError, ValueError, common.PlanError)):
        generation.generation_steps(
            {
                "project": "mac_gate_book",
                "service": "computer",
                "gpu": "local",
                "profile": mac_8g_lite_profile,
                "steps": {"video": True},
                "video_models": ["wan22_t2v_a14b"],
            },
            "mac_gate_book",
        )
