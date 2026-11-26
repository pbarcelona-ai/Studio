"""Managed single-click lifecycle for the local ComfyUI server (auto-start with Studio, clean shutdown on exit)."""
from __future__ import annotations

import atexit
import contextlib
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

_LOCK = threading.Lock()
_MANAGED_PROC: subprocess.Popen[Any] | None = None
_MANAGED_LOG_HANDLE: Any = None
_ATEXIT_REGISTERED = False


def _default_base_url() -> str:
    return (
        os.environ.get("COMFYUI_URL")
        or os.environ.get("COMFY_BASE_URL")
        or "http://127.0.0.1:8188"
    ).rstrip("/")


def is_comfyui_reachable(base_url: str | None = None, *, timeout: float = 0.8) -> bool:
    """Return True if ComfyUI's `/system_stats` endpoint responds with HTTP 2xx."""
    url = (base_url or _default_base_url()).rstrip("/")
    try:
        with urllib.request.urlopen(f"{url}/system_stats", timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def _resolve_comfyui_python(root: Path) -> Path | None:
    """Choose the best Python interpreter for ComfyUI (preferring Studio's active `.venv` Python)."""
    candidates: list[Path] = []
    if sys.executable:
        candidates.append(Path(sys.executable))
    if os.name == "nt":
        candidates.extend([
            root / ".venv" / "Scripts" / "python.exe",
            root / ".local_ai" / "ComfyUI" / ".venv" / "Scripts" / "python.exe",
        ])
    else:
        candidates.extend([
            root / ".venv" / "bin" / "python",
            root / ".venv" / "bin" / "python3",
            root / ".local_ai" / "ComfyUI" / ".venv" / "bin" / "python",
        ])
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def _build_comfyui_env(root: Path) -> dict[str, str]:
    """Build environment variables combining ComfyUI's pre-installed site-packages with Studio's `.venv` (`gguf`)."""
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    paths: list[str] = []
    if os.name == "nt":
        comfy_sp = root / ".local_ai" / "ComfyUI" / ".venv" / "Lib" / "site-packages"
        studio_sp = root / ".venv" / "Lib" / "site-packages"
        for p in (comfy_sp, studio_sp):
            if p.is_dir():
                paths.append(str(p))
    else:
        for base in (root / ".local_ai" / "ComfyUI" / ".venv" / "lib", root / ".venv" / "lib"):
            if base.is_dir():
                for sp in sorted(base.glob("python*/site-packages")):
                    if sp.is_dir():
                        paths.append(str(sp))
    existing = env.get("PYTHONPATH", "").strip()
    if existing:
        paths.append(existing)
    if paths:
        env["PYTHONPATH"] = os.pathsep.join(paths)
    return env


def _parse_host_port(base_url: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8188
    return host, port


def _is_local_host(host: str) -> bool:
    return host.lower() in ("127.0.0.1", "localhost", "::1")


def stop_managed_comfyui(*, timeout: float = 5.0) -> bool:
    """Stop the ComfyUI process if this Studio instance spawned it. Never kills an externally started server."""
    global _MANAGED_PROC, _MANAGED_LOG_HANDLE
    with _LOCK:
        proc = _MANAGED_PROC
        log_fh = _MANAGED_LOG_HANDLE
        _MANAGED_PROC = None
        _MANAGED_LOG_HANDLE = None

    stopped = False
    if proc is not None and proc.poll() is None:
        with contextlib.suppress(Exception):
            proc.terminate()
        with contextlib.suppress(Exception):
            try:
                proc.wait(timeout=timeout)
                stopped = True
            except subprocess.TimeoutExpired:
                with contextlib.suppress(Exception):
                    proc.kill()
                    proc.wait(timeout=2.0)
                stopped = True
    if log_fh is not None:
        with contextlib.suppress(Exception):
            log_fh.close()
    return stopped


def ensure_comfyui_started(
    *,
    root: Path | None = None,
    base_url: str | None = None,
    wait_ready_s: float = 0.0,
) -> dict[str, Any]:
    """Ensure the local ComfyUI server is running; spawn it silently in the background if installed and offline."""
    global _MANAGED_PROC, _MANAGED_LOG_HANDLE, _ATEXIT_REGISTERED

    url = (base_url or _default_base_url()).rstrip("/")
    if os.environ.get("STUDIO_AUTOSTART_COMFYUI", "1").strip().lower() in ("0", "false", "no", "off"):
        return {"status": "disabled", "url": url, "ready": is_comfyui_reachable(url)}

    if is_comfyui_reachable(url):
        return {"status": "already_running", "url": url, "ready": True}

    host, port = _parse_host_port(url)
    if not _is_local_host(host):
        return {"status": "remote_unreachable", "url": url, "ready": False}

    proj_root = root or ROOT
    comfy_dir = proj_root / ".local_ai" / "ComfyUI"
    main_py = comfy_dir / "main.py"
    if not main_py.is_file():
        return {"status": "not_installed", "url": url, "ready": False}

    py = _resolve_comfyui_python(proj_root)
    if py is None:
        return {"status": "no_python", "url": url, "ready": False}

    log_path = comfy_dir / "comfyui_autostart.log"

    with _LOCK:
        if _MANAGED_PROC is not None and _MANAGED_PROC.poll() is None:
            status = "starting"
            pid = _MANAGED_PROC.pid
        else:
            if _MANAGED_LOG_HANDLE is not None:
                with contextlib.suppress(Exception):
                    _MANAGED_LOG_HANDLE.close()
                _MANAGED_LOG_HANDLE = None
            env = _build_comfyui_env(proj_root)
            cmd = [str(py), "-X", "utf8", str(main_py), "--listen", host, "--port", str(port)]
            popen_kwargs: dict[str, Any] = {
                "cwd": str(comfy_dir),
                "env": env,
                "stdin": subprocess.DEVNULL,
            }
            if os.name == "nt":
                create_no_window = int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
                create_new_group = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
                popen_kwargs["creationflags"] = create_no_window | create_new_group
            else:
                popen_kwargs["start_new_session"] = True

            try:
                log_fh = log_path.open("w", encoding="utf-8", errors="replace")
            except OSError:
                log_fh = None
            if log_fh is not None:
                popen_kwargs["stdout"] = log_fh
                popen_kwargs["stderr"] = subprocess.STDOUT
            else:
                popen_kwargs["stdout"] = subprocess.DEVNULL
                popen_kwargs["stderr"] = subprocess.DEVNULL

            try:
                proc = subprocess.Popen(cmd, **popen_kwargs)
            except OSError as exc:
                if log_fh is not None:
                    with contextlib.suppress(Exception):
                        log_fh.close()
                return {"status": "spawn_failed", "url": url, "ready": False, "error": str(exc)}

            _MANAGED_PROC = proc
            _MANAGED_LOG_HANDLE = log_fh
            pid = proc.pid
            status = "started"
            if not _ATEXIT_REGISTERED:
                atexit.register(stop_managed_comfyui)
                _ATEXIT_REGISTERED = True

    ready = False
    if wait_ready_s > 0.0:
        deadline = time.monotonic() + float(wait_ready_s)
        while time.monotonic() < deadline:
            if is_comfyui_reachable(url, timeout=1.0):
                ready = True
                break
            with _LOCK:
                cur = _MANAGED_PROC
            if cur is not None and cur.poll() is not None:
                return {
                    "status": "exited_early",
                    "url": url,
                    "ready": False,
                    "returncode": cur.returncode,
                    "log_path": str(log_path),
                }
            time.sleep(0.5)

    return {
        "status": status,
        "url": url,
        "pid": pid,
        "ready": ready,
        "log_path": str(log_path),
    }
