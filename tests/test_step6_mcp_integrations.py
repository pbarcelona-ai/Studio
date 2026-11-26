"""Tests for Step 06 MCP integrations (real JSON-RPC 2.0 stdio transport + Premiere/Blender/Final Draft auto-export fallbacks)."""
from __future__ import annotations

import ast
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
SW_DIR = ROOT / "sw"
for p in (str(SCRIPTS_DIR), str(SW_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import adaptation  # noqa: E402
import mcp_client  # noqa: E402
import screenplay  # noqa: E402
from studio_app import mcp_routes  # noqa: E402
from studio_app.api import Request  # noqa: E402


def _seed_book_with_screenplay(tmp_path: Path, slug: str = "mcp_demo") -> Path:
    pd = tmp_path / slug
    pd.mkdir(parents=True, exist_ok=True)
    adaptation.save(
        pd,
        {
            "version": 1,
            "logline": "A boy and his dog visit Saturn's moons.",
            "premise": "Cardboard rocket adventure.",
            "ending": "Home for cocoa.",
            "runtime_minutes": 5.0,
            "clip_seconds": 4.0,
            "n_chapters": 1,
            "acts": [{"name": "Act I", "purpose": "Setup", "share": 1.0, "seconds": 30, "first_chapter": 1, "last_chapter": 1}],
            "scenes": [
                {
                    "id": "S001",
                    "act": "Act I",
                    "title": "Living Room Launch",
                    "summary": "Tommy climbs into the cardboard rocket.",
                    "chapters": [1],
                    "anchor": "",
                    "importance": 4.0,
                    "keep": "full",
                    "location": "living room",
                    "characters": ["TOMMY", "MOM"],
                    "time_of_day": "afternoon",
                    "clips": 3,
                    "seconds": 12,
                }
            ],
            "cut": [],
            "stale": False,
        },
    )
    screenplay.save_scene(
        pd,
        "S001",
        {
            "heading": "INT. LIVING ROOM - AFTERNOON",
            "elements": [
                {"type": "action", "text": "Tommy tapes silver foil to a cardboard box."},
                {"type": "dialogue", "character": "TOMMY", "text": "Countdown starts now!"},
                {"type": "dialogue", "character": "MOM", "text": "Be back by dinner."},
            ],
        },
        edited=False,
    )
    return pd


def test_mcp_client_real_stdio_jsonrpc_handshake(tmp_path: Path, monkeypatch):
    # Tiny real stdio MCP server script speaking JSON-RPC 2.0
    srv_py = tmp_path / "mock_mcp_server.py"
    srv_py.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    line = line.strip()\n"
        "    if not line: continue\n"
        "    msg = json.loads(line)\n"
        "    mid = msg.get('id')\n"
        "    if msg.get('method') == 'initialize':\n"
        "        print(json.dumps({'jsonrpc': '2.0', 'id': mid, 'result': {'protocolVersion': '2024-11-05'}}), flush=True)\n"
        "    elif msg.get('method') == 'tools/call':\n"
        "        params = msg.get('params') or {}\n"
        "        print(json.dumps({'jsonrpc': '2.0', 'id': mid, 'result': {'echo_tool': params.get('name'), 'echo_args': params.get('arguments')}}), flush=True)\n",
        encoding="utf-8",
    )
    cfg = tmp_path / ".mcp.json"
    cfg.write_text(
        json.dumps({"mcpServers": {"blender": {"command": sys.executable, "args": [str(srv_py)]}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("STUDIO_MCP_CONFIG", str(cfg))

    client = mcp_client.MCPClient(timeout=15)
    assert client.check_server("blender") is True
    res = client._call_mcp("blender", "create_scene", {"prompt": "Spaceship launch"})
    assert res["echo_tool"] == "create_scene"
    assert res["echo_args"]["prompt"] == "Spaceship launch"


def test_step6_mcp_routes_auto_export_and_generate_local_packages(tmp_path: Path, monkeypatch):
    pd = _seed_book_with_screenplay(tmp_path, "mcp_demo")
    empty_cfg = tmp_path / "empty_mcp.json"
    empty_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("STUDIO_MCP_CONFIG", str(empty_cfg))
    monkeypatch.setattr(mcp_client, "load_mcp_server_configs", lambda: {})
    monkeypatch.setattr(mcp_routes, "_premiere", None)
    monkeypatch.setattr(mcp_routes, "_blender", None)
    monkeypatch.setattr(mcp_routes, "_playwright", None)

    import layout
    monkeypatch.setattr(layout, "project_dir", lambda slug, kind=None: pd)

    # 1. Premiere Pro route auto-exports FDX AND writes valid Premiere XML with scene markers
    res_p = mcp_routes.mcp_premiere_import_fdx(Request(body={"project": "mcp_demo"}))
    assert res_p["status"] == "ok"
    assert res_p["mode"] == "local_package"
    fdx_path = Path(res_p["fdx_path"])
    xml_path = Path(res_p["xml_path"])
    assert fdx_path.is_file() and fdx_path.stat().st_size > 50
    assert xml_path.is_file()
    tree = ET.fromstring(xml_path.read_text(encoding="utf-8"))
    assert tree.tag == "xmeml"
    assert any("S001" in (m.text or "") for m in tree.findall(".//marker/name"))

    # 2. Blender Previs route writes syntactically valid runnable Blender Python script
    res_b = mcp_routes.mcp_blender_generate_previs(Request(body={"project": "mcp_demo", "scene_id": "S001"}))
    assert res_b["status"] == "ok"
    assert res_b["mode"] == "local_script"
    py_path = Path(res_b["script_path"])
    assert py_path.is_file()
    src = py_path.read_text(encoding="utf-8")
    ast.parse(src)
    assert "TOMMY" in src and "Previs_Camera_35mm" in src

    # 3. Final Draft Web route auto-exports FDX and returns clean download + open links
    res_f = mcp_routes.mcp_playwright_finaldraft_import(Request(body={"project": "mcp_demo"}))
    assert res_f["status"] == "ok"
    assert res_f["mode"] == "local_handoff"
    assert res_f["fdx_url"].endswith(".fdx")
    assert Path(res_f["fdx_path"]).is_file()
