"""Tests for open-source external tool discovery, Trelby Step 06 integration, OTIO/Kdenlive export, and Wan2GP auto-discovery."""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import adaptation  # noqa: E402
import external_tools  # noqa: E402
import screenplay  # noqa: E402
from local_runners.wan2gp_runner import Wan2GPRunner  # noqa: E402
from studio_app import mcp_routes, routes_post  # noqa: E402
from studio_app.api import HttpError, Request  # noqa: E402


def _seed_book(tmp_path: Path, slug: str = "oss_demo") -> Path:
    pd = tmp_path / slug
    pd.mkdir(parents=True, exist_ok=True)
    adaptation.save(
        pd,
        {
            "version": 1,
            "logline": "A young inventor builds a starship.",
            "premise": "Garage rocket adventure.",
            "ending": "Safe landing.",
            "runtime_minutes": 3.0,
            "clip_seconds": 4.0,
            "n_chapters": 1,
            "acts": [{"name": "Act I", "purpose": "Setup", "share": 1.0, "seconds": 20, "first_chapter": 1, "last_chapter": 1}],
            "scenes": [
                {
                    "id": "S001",
                    "act": "Act I",
                    "title": "Workshop",
                    "summary": "Building the hull.",
                    "chapters": [1],
                    "anchor": "",
                    "importance": 4.0,
                    "keep": "full",
                    "location": "workshop",
                    "characters": ["ALEX"],
                    "time_of_day": "day",
                    "clips": 2,
                    "seconds": 8,
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
            "heading": "INT. WORKSHOP - DAY",
            "elements": [
                {"type": "action", "text": "Alex tightens the final bolt."},
                {"type": "dialogue", "character": "ALEX", "text": "Ready for launch."},
            ],
        },
        edited=False,
    )
    (pd / "shots").mkdir(parents=True, exist_ok=True)
    (pd / "shots" / "shotlist.json").write_text(
        json.dumps(
            {
                "scenes": [
                    {
                        "id": "S001",
                        "shots": [
                            {"n": 1, "seconds": 4.0},
                            {"n": 2, "seconds": 5.0},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return pd


def test_detect_all_tools_structure_and_local_ai(tmp_path: Path):
    local_ai = tmp_path / ".local_ai"
    (local_ai / "Wan2GP").mkdir(parents=True)
    (local_ai / "Wan2GP" / "wgp.py").write_text("# mock", encoding="utf-8")
    sub = "Scripts" if sys.platform == "win32" else "bin"
    py_name = "python.exe" if sys.platform == "win32" else "python"
    (local_ai / "Wan2GP" / ".venv" / sub).mkdir(parents=True)
    (local_ai / "Wan2GP" / ".venv" / sub / py_name).write_text("", encoding="utf-8")

    res = external_tools.detect_all_tools(repo_root=tmp_path)
    assert res["total_count"] >= 15
    assert "trelby" in res["by_id"]
    assert "kdenlive" in res["by_id"]
    assert "opentimelineio" in res["by_id"]
    assert res["by_id"]["wan2gp"]["installed"] is True


def test_trelby_route_exports_fdx_and_fountain_and_launches(tmp_path: Path, monkeypatch):
    pd = _seed_book(tmp_path, "trelby_demo")
    import layout

    monkeypatch.setattr(layout, "project_dir", lambda slug, kind=None: pd)
    fake_exe = tmp_path / "trelby.exe"
    fake_exe.write_text("", encoding="utf-8")
    monkeypatch.setattr(external_tools, "find_trelby_executable", lambda: fake_exe)

    launched_args: list[list[str]] = []

    def fake_popen(argv, **kwargs):
        launched_args.append(list(argv))
        return SimpleNamespace(pid=4242)

    monkeypatch.setattr(external_tools.subprocess, "Popen", fake_popen)

    res = mcp_routes.mcp_trelby_open(Request(body={"project": "trelby_demo"}))
    assert res["status"] == "ok"
    assert res["mode"] == "trelby_local"
    assert res["launched"] is True
    assert res["pid"] == 4242
    assert Path(res["fdx_path"]).is_file()
    assert Path(res["fountain_path"]).is_file()
    assert res["fdx_url"].endswith(".fdx")
    assert res["fountain_url"].endswith(".fountain")
    assert launched_args and launched_args[0][0] == str(fake_exe)


def test_otio_and_kdenlive_export_and_route(tmp_path: Path, monkeypatch):
    pd = _seed_book(tmp_path, "nle_demo")
    monkeypatch.setattr(routes_post, "pdir", lambda slug, kind=None: pd)

    res_k = routes_post._v2_export_make(Request(body={"project": "nle_demo", "target": "kdenlive"}))
    assert res_k["status"] == "ok"
    assert res_k["clips"] == 2
    assert res_k["download_url"].endswith("nle_demo.kdenlive")

    res_o = routes_post._v2_export_make(Request(body={"project": "nle_demo", "target": "otio"}))
    assert res_o["status"] == "ok"
    assert res_o["download_url"].endswith("nle_demo.otio")

    kdenlive_file = pd / "exports" / "nle_demo.kdenlive"
    otio_file = pd / "exports" / "nle_demo.otio"
    assert kdenlive_file.is_file() and otio_file.is_file()

    tree = ET.fromstring(kdenlive_file.read_text(encoding="utf-8"))
    assert tree.tag == "mlt"
    producers = tree.findall("producer")
    assert len(producers) == 2

    otio_json = json.loads(otio_file.read_text(encoding="utf-8"))
    assert otio_json.get("OTIO_SCHEMA") == "Timeline.1"


def test_launch_external_tool_rejects_disallowed_ids():
    with pytest.raises(ValueError, match="Unsupported"):
        external_tools.launch_external_tool("cmd.exe")

    with pytest.raises(HttpError) as exc:
        mcp_routes.api_external_tools_launch(Request(body={"tool": "powershell"}))
    assert exc.value.code == 400


def test_wan2gp_runner_supports_dot_venv(tmp_path: Path):
    wgp_dir = tmp_path / "Wan2GP"
    wgp_dir.mkdir()
    (wgp_dir / "wgp.py").write_text("# mock", encoding="utf-8")
    sub = "Scripts" if sys.platform == "win32" else "bin"
    py_name = "python.exe" if sys.platform == "win32" else "python"
    (wgp_dir / ".venv" / sub).mkdir(parents=True)
    (wgp_dir / ".venv" / sub / py_name).write_text("", encoding="utf-8")

    runner = Wan2GPRunner(install_dir=wgp_dir)
    assert runner.is_installed() is True
