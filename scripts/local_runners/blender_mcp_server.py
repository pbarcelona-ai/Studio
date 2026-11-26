"""Standalone stdio MCP JSON-RPC 2.0 server for Blender 5.4 inside Pistachio's Studio.

Zero external dependencies: runs directly on Neon's `.venv` Python and talks to:
  1. An open Blender GUI running `blender_live_addon.py` on 127.0.0.1:9876 (if active), OR
  2. Headless portable `.local_ai/blender/blender.exe` via `blender_runner.py`.

Configured automatically in `<Neon>/.mcp.json` so both Pistachio's Studio (`sw/mcp_client.py`)
and Claude Code / MCP clients can invoke Blender tools out of the box.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from layout import project_dir as pdir  # noqa: E402
from local_runners import blender_runner  # noqa: E402

TOOLS = [
    {"name": "ping", "description": "Check portable Blender 5.4 and live GUI bridge status", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "create_scene", "description": "Create and render a 3D Blender scene from a text prompt", "inputSchema": {"type": "object", "properties": {"prompt": {"type": "string"}, "output_format": {"type": "string"}}}},
    {"name": "generate_previs", "description": "Render headless 3D previs PNGs, .blend, .glb, and optional animatic MP4 for a project scene", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}, "scene_id": {"type": "string"}, "render_animatic": {"type": "boolean"}}}},
    {"name": "render_depth_guide", "description": "Render true-scale 3D blocking + depth map guide for a Step 17 keyframe", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}, "shot_id": {"type": "string"}}}},
    {"name": "render_set_angles", "description": "Render multi-angle consistent 3D set plates for Step 11", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}, "set_name": {"type": "string"}, "description": {"type": "string"}}}},
    {"name": "render_title_card", "description": "Render a 3D animated extruded title card (PNG + MP4)", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}, "title": {"type": "string"}, "subtitle": {"type": "string"}, "style": {"type": "string"}}}},
    {"name": "export_gltf", "description": "Export live Blender scene as GLB/GLTF", "inputSchema": {"type": "object", "properties": {"output": {"type": "string"}}}},
    {"name": "live_command", "description": "Send a live command directly to an open Blender GUI window running blender_live_addon.py", "inputSchema": {"type": "object", "properties": {"command": {"type": "string"}, "code": {"type": "string"}, "output": {"type": "string"}}}},
]


def _query_live_bridge(payload: dict[str, Any], *, timeout: float = 3.0) -> dict[str, Any] | None:
    port = int(os.environ.get("STUDIO_BLENDER_MCP_PORT") or "9876")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
            sock.settimeout(max(timeout, 30.0))
            sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            data = sock.recv(65536).decode("utf-8", "replace").strip()
            parsed = json.loads(data) if data else {}
            return parsed if isinstance(parsed, dict) else None
    except (OSError, ValueError):
        return None


def _handle_tool_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "ping":
        st = blender_runner.blender_status()
        live = _query_live_bridge({"command": "ping"}, timeout=0.4)
        return {**st, "live_gui_connected": bool(live and live.get("ok")), "live": live or {}}

    if name == "live_command":
        res = _query_live_bridge(args, timeout=5.0)
        if res is None:
            return {"error": "No live Blender GUI bridge listening on 127.0.0.1:9876. Launch Blender Live first."}
        return res

    if name == "export_gltf":
        out = str(args.get("output") or "").strip()
        live = _query_live_bridge({"command": "export_gltf", "output": out}, timeout=5.0)
        if live is not None:
            return live
        return {"error": "export_gltf requires an active live Blender GUI session (launch Blender Live first)."}

    if name == "generate_previs":
        slug = str(args.get("project") or "").strip()
        sid = str(args.get("scene_id") or "S001").strip()
        if not slug:
            return {"error": "project is required"}
        pd = pdir(slug, "book")
        return blender_runner.render_scene_previs(
            pd,
            slug,
            sid,
            render_animatic=bool(args.get("render_animatic", False)),
        )

    if name == "render_depth_guide":
        slug = str(args.get("project") or "").strip()
        shot_id = str(args.get("shot_id") or "S001-01").strip()
        if not slug:
            return {"error": "project is required"}
        pd = pdir(slug, "book")
        return blender_runner.render_shot_depth_guide(pd, slug, shot_id)

    if name == "render_set_angles":
        slug = str(args.get("project") or "").strip()
        set_name = str(args.get("set_name") or "Living Room").strip()
        if not slug:
            return {"error": "project is required"}
        pd = pdir(slug, "book")
        return blender_runner.render_set_multi_angle(
            pd,
            slug,
            set_name,
            description=str(args.get("description") or ""),
            lighting=str(args.get("lighting") or ""),
        )

    if name == "render_title_card":
        slug = str(args.get("project") or "").strip()
        title = str(args.get("title") or slug or "Untitled").strip()
        if not slug:
            return {"error": "project is required"}
        pd = pdir(slug, "book")
        return blender_runner.render_3d_title_card(
            pd,
            slug,
            title=title,
            subtitle=str(args.get("subtitle") or ""),
            style=str(args.get("style") or "space_orbit"),
            render_video=bool(args.get("render_video", True)),
        )

    if name == "create_scene":
        prompt = str(args.get("prompt") or "").strip()
        live = _query_live_bridge({"command": "scene_info"}, timeout=0.4)
        if live and live.get("ok"):
            return {"ok": True, "mode": "live_gui", "prompt": prompt, "live_scene": live}
        # Headless fallback into a temporary workspace directory inside Neon/logs
        out_dir = blender_runner.REPO_ROOT / "logs" / "blender_mcp_scenes"
        out_dir.mkdir(parents=True, exist_ok=True)
        still = out_dir / "mcp_scene.png"
        feats = blender_runner._infer_room_features("INT. SCENE - DAY", prompt, [])
        src = (
            blender_runner._BPY_COMMON_HELPERS
            + f"""
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
_configure_render(scene, 960, 540, samples=12)
_build_room({repr(feats)})
_setup_lighting(is_space={repr(bool(feats.get("is_space")))})
bpy.ops.object.camera_add(location=(0.0, -3.4, 1.45))
cam = bpy.context.active_object
scene.camera = cam
_aim_camera(cam, (0.0, -3.4, 1.45), (0.0, 0.8, 1.0), lens_mm=32.0)
scene.render.filepath = {repr(str(still))}
bpy.ops.render.render(write_still=True)
"""
        )
        blender_runner._run_blender_python(src, work_dir=out_dir, timeout=90.0)
        return {"ok": True, "mode": "headless", "output_path": str(still), "prompt": prompt}

    return {"error": f"Unknown Blender MCP tool: {name}"}


def main() -> int:
    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(msg, dict):
            continue
        method = str(msg.get("method") or "")
        mid = msg.get("id")
        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "pistachio-blender-mcp", "version": "1.0.0"},
                },
            }
            print(json.dumps(resp), flush=True)
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}), flush=True)
        elif method == "tools/call":
            params = msg.get("params") or {}
            tname = str(params.get("name") or "")
            raw_targs = params.get("arguments")
            targs: dict[str, Any] = raw_targs if isinstance(raw_targs, dict) else {}
            try:
                res = _handle_tool_call(tname, targs)
            except Exception as exc:  # noqa: BLE001
                res = {"error": str(exc)}
            print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": res}), flush=True)
        elif mid is not None:
            print(json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Unknown method: {method}"}}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
