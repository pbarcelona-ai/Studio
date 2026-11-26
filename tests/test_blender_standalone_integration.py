"""End-to-end integration tests for standalone Blender 5.4 inside Neon/.local_ai/blender."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
SW_DIR = ROOT / "sw"
for p in (str(SCRIPTS_DIR), str(SW_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import continuity_book  # noqa: E402
import mcp_client  # noqa: E402
import shot_list  # noqa: E402
from local_runners import blender_runner  # noqa: E402


def _seed_blender_project(tmp_path: Path) -> Path:
    pd = tmp_path / "blender_demo"
    pd.mkdir(parents=True, exist_ok=True)
    (pd / "blender_demo.json").write_text(
        json.dumps({
            "title": "Blender Demo",
            "setting": "Cozy home",
            "characters": [
                {"name": "MOM", "token": "Adult woman in her thirties wearing a green cardigan", "voice": "female", "personality": dict.fromkeys(continuity_book.PERSONALITY, "warm")},
                {"name": "TOMMY", "token": "5-year-old boy wearing a red t-shirt and jeans", "voice": "male", "personality": dict.fromkeys(continuity_book.PERSONALITY, "curious")},
                {"name": "JUDAH", "token": "Yellow Labrador dog with floppy ears", "voice": "narrator", "personality": dict.fromkeys(continuity_book.PERSONALITY, "loyal")},
            ],
            "locations": [{"name": "Living Room", "token": "Living room with brown sofa, round wooden dining table, and wall TV. No coffee table."}],
            "props": [{"name": "tea mug", "token": "ceramic tea mug"}],
        }),
        encoding="utf-8",
    )
    (pd / "sets_custom.json").write_text(
        json.dumps({
            "living room": {
                "description": "Warm beige living room with dark brown sofa, round wooden dining table, and wall-mounted TV. No coffee table.",
                "lighting": "Soft warm indoor lamp light",
            }
        }),
        encoding="utf-8",
    )
    shot_list.save(
        pd,
        {
            "scenes": [
                {
                    "id": "S001",
                    "heading": "INT. LIVING ROOM - AFTERNOON",
                    "breakdown": {"intent": "open", "emotional_beat": "cozy", "blocking": "on rug", "performance": "warm"},
                    "target_seconds": 8.0,
                    "shots": [
                        {
                            "n": 1,
                            "type": "WS",
                            "lens_mm": 24,
                            "height": "eye",
                            "angle": "straight",
                            "movement": "push in",
                            "composition": "Wide view of Mom, Tommy, and Judah in the living room.",
                            "lighting": "warm indoor light",
                            "blocking": "center rug",
                            "action": "Tommy points at the cardboard box.",
                            "expression": "excited",
                            "dialogue": "",
                            "sound": "rain",
                            "seconds": 3.0,
                            "transition": "cut",
                            "priority": 1,
                            "characters": ["MOM", "TOMMY", "JUDAH"],
                            "props": ["tea mug", "cardboard box"],
                            "source": "ai",
                        }
                    ],
                }
            ],
            "target_seconds": 8.0,
            "checks": {},
        },
    )
    return pd


def test_standalone_blender_discovery_and_mcp_ping():
    st = blender_runner.blender_status()
    assert st["installed"] is True
    assert st["is_standalone"] is True
    assert ".local_ai" in st["executable"]

    # Standalone .mcp.json blender server responds cleanly to JSON-RPC 2.0 ping
    client = mcp_client.MCPClient(timeout=20)
    assert client.check_server("blender") is True
    ping = client._call_mcp("blender", "ping", {})
    assert ping.get("installed") is True
    assert ping.get("is_standalone") is True


@pytest.mark.skipif(blender_runner.find_blender_executable() is None, reason="Portable Blender not installed")
def test_live_blender_all_four_pipelines(tmp_path: Path):
    pd = _seed_blender_project(tmp_path)

    # 1. Step 06/12 Headless 3D Previs PNG + .blend + .glb
    previs = blender_runner.render_scene_previs(pd, "blender_demo", "S001", render_animatic=False, width=480, height=270)
    assert previs["ok"] is True
    assert previs["shots_rendered"] == 1
    assert Path(previs["shots"][0]["path"]).stat().st_size > 2000
    assert (pd / "exports" / "previs_s001.blend").is_file()
    assert (pd / "exports" / "previs_s001.glb").is_file()

    # 2. Step 17 True-Scale 3D Blocking & Normalized Depth Guide
    guide = blender_runner.render_shot_depth_guide(pd, "blender_demo", "S001-01", width=480, height=270)
    assert guide["ok"] is True
    assert Path(guide["blocking_path"]).stat().st_size > 2000
    assert Path(guide["depth_path"]).stat().st_size > 1500
    blk, dep = blender_runner.find_existing_shot_guide(pd, "S001-01")
    assert blk is not None and dep is not None

    # 3. Step 11 Multi-Angle Consistent 3D Set Plates
    set_res = blender_runner.render_set_multi_angle(
        pd,
        "blender_demo",
        "Living Room",
        angles=("wide", "reverse", "top_down"),
        description="Warm living room with sofa and round wooden dining table.",
        width=480,
        height=270,
    )
    assert set_res["ok"] is True
    assert set_res["views_rendered"] == 3
    for v in set_res["views"]:
        assert Path(v["path"]).stat().st_size > 2000
    assert (pd / "sets_views.json").is_file()

    # 4. Step 18/20 3D Extruded Title Card (still + optional MP4)
    title_res = blender_runner.render_3d_title_card(
        pd,
        "blender_demo",
        title="SATURN MOONS",
        subtitle="Tommy & Judah",
        style="space_orbit",
        duration_s=1.0,
        width=480,
        height=270,
        render_video=False,
    )
    assert title_res["ok"] is True
    assert Path(title_res["still_path"]).stat().st_size > 2000

    # 5. Steps 08 & 10 True-Scale Cast Height Lineup + 4-Angle 3D Turnaround Guides
    cast_res = blender_runner.render_cast_scale_turnaround_guides(
        pd,
        "blender_demo",
        character_name="TOMMY",
        include_turnarounds=True,
        width=480,
        height=270,
    )
    assert cast_res["ok"] is True
    assert cast_res["characters_count"] == 3
    assert Path(cast_res["lineup_path"]).stat().st_size > 2000
    assert (pd / "exports" / "cast_scale_lineup.blend").is_file()
    assert len(cast_res["turnarounds"]) == 1
    assert Path(cast_res["turnarounds"][0]["path"]).stat().st_size > 2000


def test_blender_buttons_live_in_visual_steps_not_step6_text():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    # Step 06 Screenplay keeps Final Draft only — no Blender or Premiere clutter
    assert 'id="spMcpFinalDraft"' in html
    assert 'id="spMcpBlender"' not in html
    assert 'id="spMcpBlenderLive"' not in html
    assert 'id="spMcpPremiere"' not in html
    # Blender belongs in Cast (Step 08), Turnarounds (Step 10), Sets (Step 11), Shots (Step 12), Keyframes (Step 17), Timeline (Step 20)
    assert 'id="bV2CastBlenderLineup"' in html
    assert 'id="bV2TurnBlenderGuides"' in html
    assert 'id="bV2LocBlenderAngles"' in html
    assert 'id="bV2ShotsBlenderPrevis"' in html
    assert 'id="bV2KfBlenderGuide"' in html
    assert 'data-blender-context="cast"' in html
    assert 'data-blender-context="set"' in html
    assert 'data-blender-context="keyframe"' in html
