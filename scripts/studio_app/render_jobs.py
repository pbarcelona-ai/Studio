"""Lightweight background render-job registry for long-running local GPU image/turnaround renders.

Allows routes such as `/api/v2_keyframe_render` and `/api/v2_turnaround_render` to return
immediately with a `job_id` when `async: true` is passed (preventing 300-second ComfyUI
runs from holding HTTP request threads or hitting client timeouts), while callers poll
`GET /api/v2_render_job?id=<job_id>` for live status and final result.
"""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import uuid
from typing import Any

_MAX_JOBS = 128
_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="render-job")


def _prune_locked() -> None:
    if len(_JOBS) <= _MAX_JOBS:
        return
    finished = [
        (jid, float(rec.get("finished_at") or rec.get("created_at") or 0.0))
        for jid, rec in _JOBS.items()
        if rec.get("status") in ("done", "error")
    ]
    finished.sort(key=lambda item: item[1])
    for jid, _ts in finished[: max(1, len(_JOBS) - _MAX_JOBS)]:
        _JOBS.pop(jid, None)


def submit_render_job(label: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Queue `fn` on the render worker pool and return its initial job descriptor immediately."""
    jid = f"rj_{uuid.uuid4().hex[:12]}"
    now = round(time.time(), 3)
    rec: dict[str, Any] = {
        "job_id": jid,
        "label": str(label or "render"),
        "status": "queued",
        "created_at": now,
        "started_at": 0.0,
        "finished_at": 0.0,
        "result": None,
        "error": "",
    }
    with _LOCK:
        _JOBS[jid] = rec
        _prune_locked()

    def _run() -> None:
        with _LOCK:
            _JOBS[jid]["status"] = "running"
            _JOBS[jid]["started_at"] = round(time.time(), 3)
        try:
            res = fn()
            with _LOCK:
                _JOBS[jid]["status"] = "done"
                _JOBS[jid]["result"] = res
                _JOBS[jid]["finished_at"] = round(time.time(), 3)
        except Exception as exc:  # noqa: BLE001
            with _LOCK:
                _JOBS[jid]["status"] = "error"
                _JOBS[jid]["error"] = str(exc) or type(exc).__name__
                _JOBS[jid]["finished_at"] = round(time.time(), 3)

    _POOL.submit(_run)
    return {
        "status": "queued",
        "job_id": jid,
        "label": rec["label"],
        "poll_url": f"/api/v2_render_job?id={jid}",
    }


def get_render_job(job_id: str) -> dict[str, Any] | None:
    jid = str(job_id or "").strip()
    if not jid:
        return None
    with _LOCK:
        rec = _JOBS.get(jid)
        return dict(rec) if rec is not None else None


def list_render_jobs(limit: int = 30) -> list[dict[str, Any]]:
    with _LOCK:
        items = sorted(_JOBS.values(), key=lambda r: float(r.get("created_at") or 0.0), reverse=True)
        return [dict(r) for r in items[: max(1, int(limit))]]
