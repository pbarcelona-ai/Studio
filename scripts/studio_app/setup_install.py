"""The Setup window installs an optional part later (the 3D depth view), on the same progress screen as the installer (rule 12, milestone MI).

GET  /api/setup_install                 the progress {state, percent, task_title, task_percent, detail, error, tasks, parts}
POST /api/setup_install {part}          start installing that part into the Studio's own Python (409 while one is running)
POST /api/setup_install_cancel          stop it (uv installs each package whole, so nothing is left half-installed)
POST /api/setup_install_retry           run it again
GET  /api/setup_install_log             {log: the details log}
"""
from __future__ import annotations

import sys
from pathlib import Path

import install_studio
import setup_engine

from .api import Request, route
from .common import PlanError
from .config import ROOT

_current: setup_engine.Engine | None = None


def studio_python() -> str:
    """The running Studio's python (python.exe, not the windowless pythonw.exe the Windows shortcut starts)."""
    exe = Path(sys.executable)
    return str(exe.with_name("python.exe")) if exe.name.lower() == "pythonw.exe" else str(exe)


def part_engine(part: str, python: str = "") -> setup_engine.Engine:
    """One task: install the part's requirement file into the running Studio's Python with uv."""
    info = install_studio.OPTIONAL.get(part)
    if info is None:
        raise PlanError(f"unknown part {part!r}")
    python = python or studio_python()

    def run(ctx: setup_engine.Ctx) -> None:
        if sys.prefix == sys.base_prefix:                    # never install into a Python shared with other programs
            raise setup_engine.StepFailed("the Studio is not running from its own .venv, so this would change a shared Python. "
                                          "Install the Studio with its installer (or install.sh / install.bat), then try again.")
        title = f"Downloading {info['title'].lower()} ({info['size']})"
        argv = [install_studio.find_uv(ROOT), "pip", "install", "--python", python, "-r", str(ROOT / info["requirements"])]
        ctx.run(argv, title, on_line=setup_engine.UvProgress(ctx, title), env=install_studio.UV_ENV)
        ctx.log("Installed. Reload the Studio page to use it.")

    task = setup_engine.Task(part, f"Installing {info['title'].lower()} ({info['size']})", run)
    return setup_engine.Engine([task], ROOT, stamp=f"part-{part}", options={part: True}, state_name=f"part-{part}.json")


def _state() -> dict:
    parts = [{"id": k, "title": p["title"], "size": p["size"]} for k, p in install_studio.OPTIONAL.items()]
    if _current is None:
        return {"state": "ready", "percent": 0, "task_title": "", "task_percent": 0, "detail": "", "error": "", "tasks": [], "parts": parts}
    return {**_current.status(), "parts": parts}


@route("GET", "/api/setup_install")
def _get(r: Request):
    return _state()


@route("POST", "/api/setup_install")
def _start(r: Request):
    global _current
    if _current is not None and _current.status()["state"] == "running":
        raise PlanError("an install is already running: wait for it, or cancel it first")
    _current = part_engine(str(r.body.get("part", "")))
    _current.start()
    return _state()


@route("POST", "/api/setup_install_cancel")
def _cancel(r: Request):
    if _current is not None:
        _current.cancel()
    return _state()


@route("POST", "/api/setup_install_retry")
def _retry(r: Request):
    if _current is not None and _current.status()["state"] in ("failed", "cancelled"):
        _current.start()
    return _state()


@route("GET", "/api/setup_install_log")
def _log(r: Request):
    return {"log": _current.log_text() if _current is not None else ""}
