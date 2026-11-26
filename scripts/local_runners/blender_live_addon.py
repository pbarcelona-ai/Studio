"""Pistachio's Studio Live Blender 5.4 Bridge Addon (100% self-contained inside Neon).

Loaded automatically when Blender GUI is launched via `--python blender_live_addon.py`,
or installable inside Blender Preferences > Add-ons. Runs a lightweight localhost JSON-line
socket bridge on 127.0.0.1:9876 and executes `bpy` operations safely on Blender's main
thread via `bpy.app.timers`.
"""
from __future__ import annotations

import json
import os
import queue
import socket
import threading
from typing import Any

bl_info = {
    "name": "Pistachio's Studio Live MCP Bridge",
    "author": "Pistachio's Studio",
    "version": (1, 0, 0),
    "blender": (5, 0, 0),
    "location": "System > Live MCP Bridge",
    "description": "Two-way localhost JSON bridge allowing Pistachio's Studio MCP server to drive an open Blender window.",
    "category": "System",
}

_CMD_QUEUE: queue.Queue[tuple[dict[str, Any], queue.Queue[dict[str, Any]]]] = queue.Queue()
_SERVER_THREAD: threading.Thread | None = None
_STOP_EVENT = threading.Event()


def _execute_on_main_thread(req: dict[str, Any]) -> dict[str, Any]:
    import bpy

    cmd = str(req.get("command") or "").strip().lower()
    if cmd == "ping":
        return {"ok": True, "version": bpy.app.version_string, "objects": len(bpy.data.objects)}
    if cmd == "scene_info":
        sc = bpy.context.scene
        return {
            "ok": True,
            "scene": sc.name,
            "objects": [{"name": o.name, "type": o.type, "location": [round(v, 3) for v in o.location]} for o in sc.objects],
            "camera": sc.camera.name if sc.camera else "",
        }
    if cmd == "export_gltf":
        out = str(req.get("output") or "").strip()
        if not out:
            return {"ok": False, "error": "output path required"}
        bpy.ops.export_scene.gltf(filepath=out, export_format="GLB")
        return {"ok": True, "output": out}
    if cmd == "render_still":
        out = str(req.get("output") or "").strip()
        if not out:
            return {"ok": False, "error": "output path required"}
        bpy.context.scene.render.filepath = out
        bpy.ops.render.render(write_still=True)
        return {"ok": True, "output": out}
    if cmd == "run_python":
        code = str(req.get("code") or "")
        ns: dict[str, Any] = {"bpy": bpy}
        exec(code, ns, ns)  # noqa: S102  (explicit local developer bridge command)
        return {"ok": True, "result": str(ns.get("RESULT", "executed"))}
    return {"ok": False, "error": f"Unknown command: {cmd}"}


def _drain_timer() -> float | None:
    if _STOP_EVENT.is_set():
        return None
    while True:
        try:
            req, reply_q = _CMD_QUEUE.get_nowait()
        except queue.Empty:
            break
        try:
            res = _execute_on_main_thread(req)
        except Exception as exc:  # noqa: BLE001
            res = {"ok": False, "error": str(exc)}
        reply_q.put(res)
    return 0.1


def _serve_socket(port: int) -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("127.0.0.1", port))
        srv.listen(4)
        srv.settimeout(1.0)
    except OSError:
        srv.close()
        return

    while not _STOP_EVENT.is_set():
        try:
            conn, _addr = srv.accept()
        except TimeoutError:
            continue
        except OSError:
            break
        with conn:
            try:
                raw = conn.recv(65536).decode("utf-8", "replace").strip()
                req = json.loads(raw) if raw else {}
                reply_q: queue.Queue[dict[str, Any]] = queue.Queue()
                _CMD_QUEUE.put((req, reply_q))
                res = reply_q.get(timeout=60.0)
            except Exception as exc:  # noqa: BLE001
                res = {"ok": False, "error": str(exc)}
            conn.sendall((json.dumps(res) + "\n").encode("utf-8"))
    srv.close()


def register() -> None:
    global _SERVER_THREAD
    import bpy

    if _SERVER_THREAD is not None and _SERVER_THREAD.is_alive():
        return
    _STOP_EVENT.clear()
    port = int(os.environ.get("STUDIO_BLENDER_MCP_PORT") or "9876")
    _SERVER_THREAD = threading.Thread(target=_serve_socket, args=(port,), daemon=True)
    _SERVER_THREAD.start()
    bpy.app.timers.register(_drain_timer, persistent=True)
    print(f"[Pistachio's Studio] Live Blender MCP Bridge listening on 127.0.0.1:{port}", flush=True)


def unregister() -> None:
    _STOP_EVENT.set()


if __name__ == "__main__":
    register()
