"""Local Wan2GP video/image runner supporting both local CLI (`wgp.py --process`) and MCP Streamable HTTP (`2025-06-18`)."""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from .base import LocalRunner, ProgressCallback
from .gpu_lease import acquire_media_lease

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_BRACKET_STEP_RE = re.compile(r"\[(\d+)\s*/\s*(\d+)\]\s*(.*)")
_SAVED_PATH_RE = re.compile(r"saved to Path:\s*(.+)", re.IGNORECASE)
_QUEUE_DONE_RE = re.compile(r"Queue completed:\s*(\d+)\s*/\s*(\d+)\s*tasks", re.IGNORECASE)

WAN2GP_CATALOG: dict[str, dict[str, Any]] = {
    "wan2gp:flux-dev": {"model_type": "flux_dev", "task": "image", "resolution": "1024x1024", "vram_gb": 12.0},
    "wan2gp:qwen-image": {"model_type": "qwen_image", "task": "image", "resolution": "1024x1024", "vram_gb": 12.0},
    "wan2gp:wan21-t2v-1.3b": {"model_type": "t2v_1.3B", "task": "video", "resolution": "832x480", "vram_gb": 8.0},
    "wan2gp:wan22-t2v": {"model_type": "t2v_2_2", "task": "video", "resolution": "832x480", "vram_gb": 12.0},
    "wan2gp:wan22-i2v": {"model_type": "i2v_2_2", "task": "video", "resolution": "832x480", "requires_image": True, "vram_gb": 12.0},
    "wan2gp:hunyuan-video": {"model_type": "hunyuan", "task": "video", "resolution": "832x480", "vram_gb": 14.0},
    "wan2gp:ltx-video": {"model_type": "ltx_video", "task": "video", "resolution": "832x480", "vram_gb": 10.0},
}

_PHASE_BANDS: dict[str, tuple[float, float]] = {
    "loading": (0.02, 0.15),
    "encoding": (0.15, 0.25),
    "generating": (0.25, 0.85),
    "decoding": (0.85, 0.95),
    "saving": (0.95, 0.99),
}


def normalize_mcp_url(url: str) -> str:
    """Normalize a Wan2GP server URL to end with `/mcp` without trailing slash."""
    clean = str(url or "").strip().rstrip("/")
    if not clean:
        return "http://127.0.0.1:7866/mcp"
    if not clean.endswith("/mcp"):
        clean += "/mcp"
    return clean


class Wan2GPProgressParser:
    """Streaming stdout parser emitting monotonic progress events across Wan2GP sub-phases."""

    def __init__(self) -> None:
        self._buf = ""
        self.progress: float = 0.0
        self.saved_paths: list[str] = []
        self.completed_tasks: tuple[int, int] | None = None

    def _classify_phase(self, line: str) -> str | None:
        low = line.lower()
        if "loading" in low:
            return "loading"
        if "encoding" in low:
            return "encoding"
        if "denoising" in low or "generating" in low or "sampling" in low:
            return "generating"
        if "decoding" in low or "vae" in low:
            return "decoding"
        if "saving" in low or "saved to path:" in low:
            return "saving"
        return None

    def feed(self, chunk: str) -> list[dict[str, Any]]:
        clean = _ANSI_RE.sub("", chunk)
        self._buf += clean
        parts = re.split(r"[\r\n]+", self._buf)
        self._buf = parts.pop()
        events: list[dict[str, Any]] = []
        for raw_line in parts:
            line = raw_line.strip()
            if not line:
                continue
            m_save = _SAVED_PATH_RE.search(line)
            if m_save:
                self.saved_paths.append(m_save.group(1).strip())
            m_q = _QUEUE_DONE_RE.search(line)
            if m_q:
                self.completed_tasks = (int(m_q.group(1)), int(m_q.group(2)))
            phase = self._classify_phase(line)
            if phase is None:
                continue
            lo, hi = _PHASE_BANDS[phase]
            m_step = _BRACKET_STEP_RE.search(line)
            if m_step:
                cur, tot = int(m_step.group(1)), int(m_step.group(2))
                frac = max(0.0, min(1.0, cur / float(tot))) if tot > 0 else 0.0
                cand = lo + (hi - lo) * frac
            else:
                cand = lo
            self.progress = max(self.progress, min(0.99, cand))
            events.append({"phase": phase, "progress": round(self.progress, 4), "message": line})
        return events


class Wan2GPRunner(LocalRunner):
    """Runs Wan2GP either via local `wgp.py --process` or remote/local MCP Streamable HTTP."""

    name = "wan2gp"

    def __init__(self, install_dir: Path | str | None = None, mcp_url: str | None = None) -> None:
        if install_dir is not None:
            self.install_dir: Path | None = Path(install_dir)
        elif os.environ.get("WAN2GP_DIR"):
            self.install_dir = Path(os.environ["WAN2GP_DIR"])
        else:
            default_dir = Path(__file__).resolve().parents[2] / ".local_ai" / "Wan2GP"
            self.install_dir = default_dir if (default_dir / "wgp.py").is_file() else None
        raw_mcp = mcp_url or os.environ.get("WAN2GP_MCP_URL")
        self.mcp_url = normalize_mcp_url(raw_mcp) if raw_mcp else None
        self._proc: subprocess.Popen[Any] | None = None
        self._lock = threading.Lock()
        self._cancelled = False
        self._active_mcp_job: tuple[str, str, str] | None = None  # (mcp_url, session_id, job_id)

    def _python_exe(self) -> Path | None:
        if self.install_dir is None:
            return None
        rels = (
            (Path(".venv/Scripts/python.exe"), Path("venv/Scripts/python.exe"))
            if sys.platform == "win32"
            else (Path(".venv/bin/python"), Path("venv/bin/python"))
        )
        for rel in rels:
            cand = self.install_dir / rel
            if cand.is_file() or cand.is_symlink():
                return cand
        return self.install_dir / rels[-1]

    def capabilities(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tasks": ["video", "image"],
            "models": list(WAN2GP_CATALOG.keys()),
            "modes": ["cli", "mcp"],
        }

    def is_installed(self) -> bool:
        if self.mcp_url:
            return True
        if self.install_dir is None or not self.install_dir.is_dir():
            return False
        wgp = self.install_dir / "wgp.py"
        py = self._python_exe()
        return wgp.is_file() and py is not None and (py.is_file() or py.is_symlink())

    def install(self, on_progress: ProgressCallback | None = None, **_kwargs: Any) -> dict[str, Any]:
        if on_progress:
            on_progress({"phase": "verified", "progress": 1.0})
        return {"ok": self.is_installed()}

    def dry_run(self, spec: dict[str, Any]) -> dict[str, Any]:
        if not self.is_installed() or self.install_dir is None:
            return {"ok": False, "error": "Wan2GP is not installed"}
        py = self._python_exe()
        wgp = self.install_dir / "wgp.py"
        assert py is not None
        with tempfile.TemporaryDirectory(prefix="neon-wgp-dry-") as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(json.dumps([self._build_settings(spec)]), encoding="utf-8")
            proc = subprocess.run(
                [str(py), str(wgp), "--process", str(settings), "--dry-run"],
                cwd=str(self.install_dir),
                capture_output=True,
                text=True,
                timeout=30.0,
            )
            out = (proc.stdout or "") + "\n" + (proc.stderr or "")
            ok = proc.returncode == 0 and "1/1 task" in out.lower() and "0/1 task" not in out.lower()
            return {"ok": ok, "output": out.strip()}

    def _build_settings(self, spec: dict[str, Any], media_id: str | None = None) -> dict[str, Any]:
        model_id = str(spec.get("model_id") or spec.get("model") or "wan2gp:wan21-t2v-1.3b")
        if not model_id.startswith("wan2gp:"):
            model_id = f"wan2gp:{model_id}"
        entry = WAN2GP_CATALOG.get(model_id, WAN2GP_CATALOG["wan2gp:wan21-t2v-1.3b"])
        img_start = media_id or spec.get("image_start") or spec.get("reference_image_path")
        if entry.get("requires_image") and not img_start:
            raise ValueError(f"Model {model_id} requires an input start image/frame (image_start)")
        payload: dict[str, Any] = {
            "model_type": entry["model_type"],
            "prompt": str(spec.get("prompt") or ""),
            "resolution": str(spec.get("resolution") or entry.get("resolution", "832x480")),
        }
        if img_start:
            payload["image_start"] = str(img_start)
        return payload

    def cancel(self) -> None:
        self._cancelled = True
        with self._lock:
            proc = self._proc
            mcp_job = self._active_mcp_job
        if proc is not None:
            try:
                from studio_app import procs
                if procs.pid_alive(proc.pid):
                    procs.stop_group(proc.pid, hard=True)
            except Exception:
                with contextlib.suppress(Exception):
                    proc.kill()
        if mcp_job is not None:
            url, sess_id, job_id = mcp_job
            with contextlib.suppress(Exception):
                self._mcp_rpc(url, "tools/call", {"name": "wangp_cancel_job", "arguments": {"job_id": job_id}}, session_id=sess_id)

    def _mcp_rpc(
        self,
        url: str,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
        is_notification: bool = False,
    ) -> tuple[Any, str | None]:
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if not is_notification:
            body["id"] = int(time.time() * 1000) % 1_000_000
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            new_sess = resp.headers.get("Mcp-Session-Id") or session_id
            raw = resp.read().decode("utf-8", "replace")
            ctype = (resp.headers.get("Content-Type") or "").lower()
        if not raw.strip():
            return None, new_sess
        if "text/event-stream" in ctype or raw.lstrip().startswith("event:"):
            data_lines = [ln[5:].strip() for ln in raw.splitlines() if ln.startswith("data:")]
            parsed = json.loads(data_lines[-1]) if data_lines else {}
        else:
            parsed = json.loads(raw)
        if "error" in parsed:
            raise RuntimeError(f"Wan2GP MCP error: {parsed['error']}")
        return parsed.get("result"), new_sess

    def _run_mcp(self, spec: dict[str, Any], on_progress: ProgressCallback | None) -> dict[str, Any]:
        assert self.mcp_url is not None
        url = self.mcp_url
        # Validate settings upfront (e.g. missing image_start on i2v)
        _ = self._build_settings(spec)

        _, sess_id = self._mcp_rpc(url, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "neon", "version": "1.0"}})
        self._mcp_rpc(url, "notifications/initialized", {}, session_id=sess_id, is_notification=True)
        tools_res, _ = self._mcp_rpc(url, "tools/list", {}, session_id=sess_id)
        tool_names = {t.get("name") for t in ((tools_res or {}).get("tools") or []) if isinstance(t, dict)}
        required_tools = {"wangp_generate", "wangp_get_job"}
        if not required_tools.issubset(tool_names):
            raise RuntimeError("Wan2GP server is missing required tools; start it with `wgp.py --mcp --mcp-api-version 1`")

        media_id: str | None = None
        img_start = spec.get("image_start") or spec.get("reference_image_path")
        if img_start:
            img_path = Path(str(img_start))
            if not img_path.is_file():
                raise ValueError(f"Start image not found: {img_path}")
            up_res, _ = self._mcp_rpc(
                url,
                "tools/call",
                {"name": "wangp_create_gallery_upload", "arguments": {"filename": img_path.name}},
                session_id=sess_id,
            )
            up_info = json.loads(up_res["content"][0]["text"])
            put_req = urllib.request.Request(up_info["upload_url"], data=img_path.read_bytes(), method="PUT")
            with urllib.request.urlopen(put_req, timeout=30.0) as presp:
                _ = presp.read()
            media_id = str(up_info["media_id"])

        settings = self._build_settings(spec, media_id=media_id)
        gen_res, _ = self._mcp_rpc(
            url,
            "tools/call",
            {"name": "wangp_generate", "arguments": {"source": settings}},
            session_id=sess_id,
        )
        gen_info = json.loads(gen_res["content"][0]["text"])
        job_id = str(gen_info["job_id"])
        with self._lock:
            self._active_mcp_job = (url, sess_id or "", job_id)

        highest_prog = 0.0
        outputs: list[str] = []
        try:
            while not self._cancelled:
                job_res, _ = self._mcp_rpc(
                    url,
                    "tools/call",
                    {"name": "wangp_get_job", "arguments": {"job_id": job_id}},
                    session_id=sess_id,
                )
                jinfo = json.loads(job_res["content"][0]["text"])
                phase_raw = str(jinfo.get("phase") or "inference").lower()
                phase_map = {
                    "loading_model": "loading",
                    "loading": "loading",
                    "encoding": "encoding",
                    "inference": "generating",
                    "generating": "generating",
                    "decoding": "decoding",
                    "saving": "saving",
                }
                phase = phase_map.get(phase_raw, "generating")
                lo, hi = _PHASE_BANDS.get(phase, (0.25, 0.85))
                pct = float(jinfo.get("progress") or 0.0) / 100.0
                cand = 1.0 if jinfo.get("done") else min(0.99, lo + (hi - lo) * max(0.0, min(1.0, pct)))
                highest_prog = max(highest_prog, cand)
                if on_progress:
                    on_progress({"phase": phase, "progress": round(highest_prog, 4)})
                if jinfo.get("done"):
                    outputs = [str(x) for x in (jinfo.get("outputs") or [])]
                    break
                time.sleep(0.05)
        finally:
            with self._lock:
                self._active_mcp_job = None

        if self._cancelled:
            raise RuntimeError(f"Wan2GP MCP job {job_id} was cancelled")

        out_dir = Path(str(spec.get("output_dir") or tempfile.mkdtemp(prefix="neon-wgp-mcp-")))
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = Path(outputs[-1]).name if outputs else "out.mp4"
        dl_res, _ = self._mcp_rpc(
            url,
            "tools/call",
            {"name": "wangp_create_gallery_download", "arguments": {"filename": fname}},
            session_id=sess_id,
        )
        dl_info = json.loads(dl_res["content"][0]["text"])
        with urllib.request.urlopen(dl_info["download_url"], timeout=30.0) as dresp:
            video_bytes = dresp.read()
        out_file = out_dir / fname
        out_file.write_bytes(video_bytes)
        return {"ok": True, "output_path": str(out_file), "outputs": [str(out_file)]}

    def run(self, spec: dict[str, Any], on_progress: ProgressCallback | None = None) -> dict[str, Any]:
        self._cancelled = False
        model_id = str(spec.get("model_id") or spec.get("model") or "wan2gp:wan21-t2v-1.3b")
        if not model_id.startswith("wan2gp:"):
            model_id = f"wan2gp:{model_id}"
        entry = WAN2GP_CATALOG.get(model_id, WAN2GP_CATALOG["wan2gp:wan21-t2v-1.3b"])
        acquire_media_lease(media_vram_gb=float(entry.get("vram_gb", 12.0)), model_key=model_id, profile=spec.get("profile"))

        if self.mcp_url:
            return self._run_mcp(spec, on_progress)

        if not self.is_installed() or self.install_dir is None:
            raise RuntimeError("Wan2GP is not installed locally")

        settings = self._build_settings(spec)
        out_dir = Path(str(spec.get("output_dir") or (self.install_dir / "outputs")))
        out_dir.mkdir(parents=True, exist_ok=True)

        py = self._python_exe()
        wgp = self.install_dir / "wgp.py"
        assert py is not None

        with tempfile.TemporaryDirectory(prefix="neon-wgp-run-") as tmp_str:
            settings_path = Path(tmp_str) / "settings.json"
            settings_path.write_text(json.dumps([settings]), encoding="utf-8")

            from studio_app import procs
            proc = subprocess.Popen(
                [str(py), str(wgp), "--process", str(settings_path), "--output-dir", str(out_dir)],
                cwd=str(self.install_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                **procs.group_kwargs(),
            )
            with self._lock:
                self._proc = proc

            parser = Wan2GPProgressParser()
            all_text: list[str] = []
            try:
                assert proc.stdout is not None
                while True:
                    chunk = proc.stdout.read(256)
                    if not chunk:
                        break
                    decoded = chunk.decode("utf-8", "replace")
                    all_text.append(decoded)
                    for ev in parser.feed(decoded):
                        if on_progress:
                            on_progress(ev)
                for ev in parser.feed("\n"):
                    if on_progress:
                        on_progress(ev)
                rc = proc.wait()
            finally:
                with self._lock:
                    self._proc = None

        if self._cancelled:
            raise RuntimeError("Wan2GP run was cancelled")

        joined = _ANSI_RE.sub("", "".join(all_text))
        if rc != 0:
            if "outofmemory" in joined.lower() or "out of memory" in joined.lower():
                raise RuntimeError(f"Wan2GP OOM / insufficient VRAM: {joined.strip()[-300:]}")
            raise RuntimeError(f"Wan2GP failed (exit {rc}): {joined.strip()[-300:]}")

        if parser.completed_tasks is not None and parser.completed_tasks[0] == 0:
            raise RuntimeError(f"Wan2GP Queue completed: 0/{parser.completed_tasks[1]} tasks (task failed)")

        final_path: Path | None = None
        if parser.saved_paths:
            cand = Path(parser.saved_paths[-1])
            if not cand.is_absolute():
                cand = (out_dir / cand).resolve()
            if cand.is_file():
                final_path = cand

        if final_path is None:
            media_files = sorted(
                [p for p in out_dir.rglob("*") if p.is_file() and p.suffix.lower() in (".mp4", ".png", ".jpg", ".webp", ".wav")],
                key=lambda p: p.stat().st_mtime,
            )
            if media_files:
                final_path = media_files[-1]

        if final_path is None or not final_path.is_file():
            raise RuntimeError(f"Wan2GP finished without producing any output media file in {out_dir}")

        if on_progress:
            on_progress({"phase": "saving", "progress": 1.0})

        return {
            "ok": True,
            "model_id": model_id,
            "output_path": str(final_path),
            "outputs": [str(final_path)],
        }
