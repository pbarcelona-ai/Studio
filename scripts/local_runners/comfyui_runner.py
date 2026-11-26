"""Local ComfyUI workflow runner with Pantry VRAM management, WebSocket binary preview relay, and Meter progress."""
from __future__ import annotations

import base64
import contextlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from .base import LocalRunner, ProgressCallback
from .gpu_lease import acquire_media_lease
from .pantry import Meter, Pantry, apply_inputs, model_key, pick_outputs, resolve_values


def parse_ws_preview_frame(frame: bytes) -> dict[str, str] | None:
    """Decode a ComfyUI binary WebSocket preview frame: >II header (event_type=1, format 1=JPEG / 2=PNG) + image payload."""
    if not isinstance(frame, (bytes, bytearray)) or len(frame) <= 8:
        return None
    try:
        event_type, fmt = struct.unpack(">II", bytes(frame[:8]))
    except struct.error:
        return None
    if event_type != 1:
        return None
    payload = bytes(frame[8:])
    if fmt == 1:
        if not (payload.startswith(b"\xff\xd8\xff") and payload.endswith(b"\xff\xd9")):
            return None
        content_type = "image/jpeg"
    elif fmt == 2:
        if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
            return None
        content_type = "image/png"
    else:
        return None
    return {
        "content_type": content_type,
        "data_base64": base64.b64encode(payload).decode("ascii"),
    }


def relay_ws_preview_frame(frame: bytes) -> dict[str, str] | None:
    """Validate a binary ComfyUI WS preview frame and broadcast it to Studio's SSE subscribers if valid."""
    parsed = parse_ws_preview_frame(frame)
    if parsed is None:
        return None
    with contextlib.suppress(Exception):
        from studio_app import handler as _handler
        pub = getattr(_handler, "publish_preview", None)
        if callable(pub):
            pub(parsed)
    return parsed


def _ws_read_frame(sock: socket.socket) -> tuple[int, bytes] | None:
    hdr = sock.recv(2)
    if len(hdr) < 2:
        return None
    b0, b1 = hdr[0], hdr[1]
    opcode = b0 & 0x0F
    masked = bool(b1 & 0x80)
    length = b1 & 0x7F
    if length == 126:
        ext = sock.recv(2)
        if len(ext) < 2:
            return None
        length = struct.unpack(">H", ext)[0]
    elif length == 127:
        ext = sock.recv(8)
        if len(ext) < 8:
            return None
        length = struct.unpack(">Q", ext)[0]
    mask_key = sock.recv(4) if masked else b""
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            break
        data.extend(chunk)
    if masked and mask_key:
        for i in range(len(data)):
            data[i] ^= mask_key[i % 4]
    return opcode, bytes(data)


class ComfyUIRunner(LocalRunner):
    """Executes declarative `app.json` + `workflow.api.json` bundles against a local ComfyUI server."""

    name = "comfyui"

    def __init__(
        self,
        base_url: str | None = None,
        *,
        pantry: Pantry | None = None,
        timeout: float = 300.0,
    ) -> None:
        resolved_url = (
            base_url
            or os.environ.get("COMFYUI_URL")
            or os.environ.get("COMFY_BASE_URL")
            or "http://127.0.0.1:8188"
        ).rstrip("/")
        self.base_url = resolved_url
        self.pantry = pantry or Pantry(comfyui_url=self.base_url)
        self.timeout = timeout
        self._proc: subprocess.Popen[Any] | None = None
        self._lock = threading.Lock()
        self._cancelled = False

    def capabilities(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tasks": ["image", "video", "vfx", "upscale", "audio"],
            "supports_ws_preview": True,
            "supports_pantry_vram": True,
            "base_url": self.base_url,
        }

    def is_installed(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/system_stats", timeout=1.5) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False

    def has_node(self, node_name: str) -> bool:
        """Return True if the running ComfyUI server exposes `node_name` in `/object_info`."""
        try:
            quoted = urllib.parse.quote(node_name, safe="")
            with urllib.request.urlopen(f"{self.base_url}/object_info/{quoted}", timeout=2.0) as resp:
                if not (200 <= resp.status < 300):
                    return False
                data = json.loads(resp.read().decode("utf-8"))
                return isinstance(data, dict) and node_name in data
        except Exception:
            return False

    def upload_image(self, file_path: Path, max_mb: float | None = None) -> str:
        """Upload an image file to ComfyUI's `/upload/image` input directory and return its registered name."""
        return self._upload_file(file_path, max_mb=max_mb)

    def install(self, on_progress: ProgressCallback | None = None, **_kwargs: Any) -> dict[str, Any]:
        if on_progress:
            on_progress({"phase": "checking", "progress": 1.0})
        return {"ok": True, "base_url": self.base_url, "installed": self.is_installed()}

    def attach_process(self, proc: subprocess.Popen[Any]) -> None:
        with self._lock:
            self._proc = proc

    def cancel(self) -> None:
        self._cancelled = True
        with contextlib.suppress(Exception):
            req = urllib.request.Request(f"{self.base_url}/interrupt", data=b"{}", method="POST")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                _ = resp.read()
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

    def _upload_file(self, file_path: Path, max_mb: float | None = None) -> str:
        if not file_path.is_file():
            raise ValueError(f"Input file not found: {file_path}")
        size_bytes = file_path.stat().st_size
        if max_mb is not None and size_bytes > float(max_mb) * 1024 * 1024:
            raise ValueError(f"File {file_path.name} ({size_bytes / (1024 * 1024):.2f} MB) exceeds max_mb limit of {max_mb} MB")
        boundary = f"----NeonComfyBoundary{uuid.uuid4().hex}"
        raw_bytes = file_path.read_bytes()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{file_path.name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + raw_bytes + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            f"{self.base_url}/upload/image",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return str(data.get("name") or file_path.name)

    def _format_validation_error(self, err_body: str, manifest: dict[str, Any], workflow: dict[str, Any]) -> str:
        pack = manifest.get("pack", "unknown")
        models = [Path(str(m.get("file", ""))).name for m in (manifest.get("models") or []) if m.get("file")]
        classes = [str(n.get("class_type", "")) for n in workflow.values() if isinstance(n, dict) and n.get("class_type")]
        return (
            f"ComfyUI workflow validation failed for pack '{pack}' "
            f"(models: {', '.join(models) or 'none'}; nodes: {', '.join(classes) or 'none'}): {err_body}"
        )

    def run(self, spec: dict[str, Any], on_progress: ProgressCallback | None = None) -> dict[str, Any]:
        self._cancelled = False
        app_dir = Path(str(spec.get("app_dir") or ""))
        if not (app_dir / "app.json").is_file():
            raise ValueError(f"Missing app.json in {app_dir}")
        manifest = json.loads((app_dir / "app.json").read_text(encoding="utf-8"))
        wf_file = app_dir / str(manifest.get("workflow") or "workflow.api.json")
        workflow = json.loads(wf_file.read_text(encoding="utf-8"))

        raw_values = spec.get("values") if "values" in spec else spec.get("inputs")
        resolved = resolve_values(manifest, raw_values if isinstance(raw_values, dict) else {})

        # Upload any file inputs and check max_mb limits
        uploaded_names: dict[str, str] = {}
        for inp in manifest.get("inputs") or []:
            itype = inp.get("type")
            iid = str(inp.get("id"))
            if itype in ("image", "video", "audio"):
                fval = resolved.get(iid)
                if fval and isinstance(fval, (str, Path)):
                    p = Path(str(fval))
                    max_mb = (inp.get("limits") or {}).get("max_mb")
                    if p.is_file():
                        uploaded_names[iid] = self._upload_file(p, max_mb=max_mb)
                    elif max_mb is not None:
                        raise ValueError(f"File input {iid!r} path {p} does not exist")

        bound_wf = apply_inputs(
            manifest,
            workflow,
            resolved,
            preset=spec.get("preset"),
            uploaded_names=uploaded_names,
        )

        mkey = model_key(manifest)
        vram_need = float(manifest.get("min_vram_gb") or 0.0)
        declared_nodes = [str(o.get("node")) for o in (manifest.get("outputs") or []) if isinstance(o, dict) and o.get("node") is not None]
        out_dir = Path(str(spec.get("output_dir") or app_dir / "out"))
        return self._execute_workflow(
            bound_wf,
            output_dir=out_dir,
            app_id=str(manifest.get("id") or "app"),
            model_cache_key=mkey,
            min_vram_gb=vram_need,
            declared_nodes=declared_nodes,
            manifest=manifest,
            profile=spec.get("profile"),
            on_progress=on_progress,
        )

    def run_workflow(
        self,
        workflow: dict[str, Any],
        *,
        output_dir: Path,
        app_id: str = "dynamic",
        model_cache_key: str = "dynamic",
        min_vram_gb: float = 0.0,
        declared_nodes: list[str] | None = None,
        profile: Any = None,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Execute a pre-built ComfyUI API workflow dict through Pantry, WebSocket progress, and `/view` download."""
        self._cancelled = False
        return self._execute_workflow(
            workflow,
            output_dir=Path(output_dir),
            app_id=app_id,
            model_cache_key=model_cache_key,
            min_vram_gb=min_vram_gb,
            declared_nodes=declared_nodes or [],
            manifest={"id": app_id, "pack": app_id, "models": []},
            profile=profile,
            on_progress=on_progress,
        )

    def _execute_workflow(
        self,
        bound_wf: dict[str, Any],
        *,
        output_dir: Path,
        app_id: str,
        model_cache_key: str,
        min_vram_gb: float,
        declared_nodes: list[str],
        manifest: dict[str, Any],
        profile: Any = None,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        acquire_media_lease(media_vram_gb=min_vram_gb, model_key=model_cache_key, profile=profile)
        self.pantry.prepare(app_id, model_cache_key)

        client_id = f"neon-{uuid.uuid4().hex[:12]}"
        meter = Meter(
            expected_nodes=max(1, len(bound_wf)),
            class_of=lambda nid: str((bound_wf.get(nid) or {}).get("class_type") or nid),
        )

        # Open WebSocket connection before submitting /prompt
        parsed_url = urllib.parse.urlparse(self.base_url)
        host = parsed_url.hostname or "127.0.0.1"
        port = parsed_url.port or 8188
        ws_sock: socket.socket | None = None
        try:
            s = socket.create_connection((host, port), timeout=5.0)
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            handshake = (
                f"GET /ws?clientId={client_id} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
            s.sendall(handshake)
            resp_buf = b""
            while b"\r\n\r\n" not in resp_buf:
                chunk = s.recv(1024)
                if not chunk:
                    break
                resp_buf += chunk
            if b"101" in resp_buf.split(b"\r\n", 1)[0]:
                ws_sock = s
            else:
                s.close()
        except Exception:
            ws_sock = None

        try:
            req = urllib.request.Request(
                f"{self.base_url}/prompt",
                data=json.dumps({"prompt": bound_wf, "client_id": client_id}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=15.0) as resp:
                    prompt_resp = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode("utf-8", "replace")
                if exc.code == 400:
                    raise RuntimeError(self._format_validation_error(err_body, manifest, bound_wf)) from exc
                raise RuntimeError(f"ComfyUI /prompt HTTP {exc.code}: {err_body}") from exc
            except (urllib.error.URLError, OSError) as exc:
                raise RuntimeError(f"ComfyUI /prompt unreachable: {exc}") from exc

            prompt_id = str(prompt_resp.get("prompt_id") or "")
            if not prompt_id:
                raise RuntimeError("ComfyUI /prompt did not return a prompt_id")

            nodes_done = 0
            if ws_sock is not None:
                ws_sock.settimeout(15.0)
                deadline = time.monotonic() + self.timeout
                while time.monotonic() < deadline and not self._cancelled:
                    try:
                        frame_res = _ws_read_frame(ws_sock)
                    except TimeoutError:
                        # Model loading / GGUF dequantization can exceed 15s between WS events; poll /history to check if still running
                        with contextlib.suppress(Exception):
                            with urllib.request.urlopen(f"{self.base_url}/history/{prompt_id}", timeout=5.0) as hchk:
                                hdata = json.loads(hchk.read().decode("utf-8"))
                            if prompt_id in hdata:
                                break
                        continue
                    except OSError:
                        break
                    if frame_res is None:
                        break
                    opcode, payload = frame_res
                    if opcode == 0x8:  # close
                        break
                    if opcode == 0x2:  # binary preview frame
                        preview = relay_ws_preview_frame(payload)
                        if preview and on_progress:
                            on_progress({
                                "event": "preview",
                                "content_type": preview["content_type"],
                                "data_base64": preview["data_base64"],
                                "progress": meter.value,
                            })
                    elif opcode == 0x1:  # text JSON
                        try:
                            msg = json.loads(payload.decode("utf-8"))
                        except (ValueError, UnicodeDecodeError):
                            continue
                        mtype = msg.get("type")
                        mdata = msg.get("data") or {}
                        if mtype == "execution_error":
                            err_msg = mdata.get("exception_message") or mdata.get("error") or "ComfyUI execution error"
                            raise RuntimeError(f"ComfyUI execution_error: {err_msg}")
                        if mtype == "executing":
                            cur_node = mdata.get("node")
                            if cur_node is None and mdata.get("prompt_id") in (None, prompt_id):
                                break
                            val = meter.update({"current_node": cur_node, "nodes_done": nodes_done, "nodes_total": len(bound_wf)})
                            if on_progress:
                                on_progress({"event": "progress", "node": meter.node, "progress": val})
                        elif mtype == "progress":
                            val = meter.update({
                                "current_node": mdata.get("node"),
                                "nodes_done": nodes_done,
                                "nodes_total": len(bound_wf),
                                "step": mdata.get("value", 0),
                                "steps": mdata.get("max", 1),
                            })
                            if on_progress:
                                on_progress({
                                    "event": "progress",
                                    "node": meter.node,
                                    "step": mdata.get("value"),
                                    "steps": mdata.get("max"),
                                    "progress": val,
                                })
                        elif mtype == "executed":
                            nodes_done += 1
                            val = meter.update({"current_node": mdata.get("node"), "nodes_done": nodes_done, "nodes_total": len(bound_wf)})
                            if on_progress:
                                on_progress({"event": "progress", "node": meter.node, "progress": val})
        finally:
            if ws_sock is not None:
                with contextlib.suppress(Exception):
                    ws_sock.close()

        # Wait briefly for /history/{prompt_id} if WS disconnected early
        hist: dict[str, Any] = {}
        poll_deadline = time.monotonic() + min(self.timeout, 120.0)
        while time.monotonic() < poll_deadline and not self._cancelled:
            with urllib.request.urlopen(f"{self.base_url}/history/{prompt_id}", timeout=15.0) as hresp:
                hist_all = json.loads(hresp.read().decode("utf-8"))
            hist = hist_all.get(prompt_id) or {}
            if hist:
                break
            time.sleep(0.5)

        raw_outputs: list[dict[str, Any]] = []
        for nid, node_out in (hist.get("outputs") or {}).items():
            if not isinstance(node_out, dict):
                continue
            for kind_key in ("images", "videos", "audio", "gifs"):
                for item in node_out.get(kind_key) or []:
                    if isinstance(item, dict) and item.get("filename"):
                        raw_outputs.append({
                            "nodeId": str(nid),
                            "filename": str(item["filename"]),
                            "subfolder": str(item.get("subfolder") or ""),
                            "type": str(item.get("type") or "output"),
                        })

        chosen = pick_outputs(raw_outputs, declared_nodes)

        output_dir.mkdir(parents=True, exist_ok=True)
        saved_paths: list[str] = []
        for idx, item in enumerate(chosen):
            q = urllib.parse.urlencode({
                "filename": item["filename"],
                "subfolder": item.get("subfolder", ""),
                "type": item.get("type", "output"),
            })
            with urllib.request.urlopen(f"{self.base_url}/view?{q}", timeout=30.0) as vresp:
                content = vresp.read()
            dest = output_dir / f"out-{idx:02d}-{Path(item['filename']).name}"
            dest.write_bytes(content)
            saved_paths.append(str(dest))

        if on_progress:
            on_progress({"event": "progress", "progress": 1.0})

        return {
            "ok": True,
            "prompt_id": prompt_id,
            "outputs": saved_paths,
            "output_path": saved_paths[0] if saved_paths else "",
        }
