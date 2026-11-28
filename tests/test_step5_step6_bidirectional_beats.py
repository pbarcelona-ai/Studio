"""Tests for bi-directional Step 05 (Story Outline & Beat Sheet) <-> Step 06 (Screenplay) synchronization."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import adaptation  # noqa: E402
import screenplay  # noqa: E402
from studio_app import routes_post, workflow_sync  # noqa: E402
from studio_app.api import Request  # noqa: E402


def test_sync_beats_from_screenplay_builds_outline_and_beats_script_first(tmp_path: Path):
    pd = tmp_path / "script_first"
    pd.mkdir(parents=True)
    screenplay.save_scene(
        pd,
        "S001",
        {
            "heading": "INT. OBSERVATORY - NIGHT",
            "elements": [
                {"type": "action", "text": "Elena aligns the brass telescope toward Saturn."},
                {"type": "dialogue", "character": "ELENA", "text": "The signal is coming from Titan."},
            ],
        },
        edited=True,
    )
    screenplay.save_scene(
        pd,
        "S002",
        {
            "heading": "EXT. LAUNCH PAD - DAWN",
            "elements": [
                {"type": "action", "text": "Engines ignite in a blinding plume of steam."},
                {"type": "dialogue", "character": "MARCO", "text": "All systems nominal!"},
            ],
        },
        edited=True,
    )

    res = adaptation.sync_beats_from_screenplay(pd)
    assert res["synced"] is True
    assert res["scenes_synced"] == 2
    assert res["beats_synced"] == 2

    plan = adaptation.load(pd)
    assert plan is not None
    assert len(plan["scenes"]) == 2
    assert plan["scenes"][0]["location"] == "observatory"
    assert plan["scenes"][0]["time_of_day"] == "night"
    assert plan["scenes"][0]["characters"] == ["ELENA"]
    assert "brass telescope" in plan["scenes"][0]["summary"]

    beats = json.loads((pd / "readin" / "beats.json").read_text(encoding="utf-8"))
    assert beats["synced_from_screenplay"] is True
    assert sum(len(a["beats"]) for a in beats["acts"]) == 2


def test_route_and_workflow_sync_bidirectional_step5_step6(tmp_path: Path, monkeypatch):
    pd = tmp_path / "bidir_demo"
    pd.mkdir(parents=True)
    screenplay.save_scene(
        pd,
        "S001",
        {
            "heading": "INT. STUDIO - DAY",
            "elements": [{"type": "action", "text": "The director sketches a storyboard frame."}],
        },
        edited=True,
    )
    monkeypatch.setattr(routes_post, "pdir", lambda slug, kind=None: pd)

    res = routes_post._v2_beats_sync_from_screenplay(Request(body={"project": "bidir_demo"}))
    assert res["status"] == "ok" and res["scenes_synced"] == 1
    assert 5 in workflow_sync.DEPENDENCY_MAP[6]["upstream"]
    assert workflow_sync.STEP_CATALOG[5]["title"] == "Story Outline & Beat Sheet"


def test_sync_beats_preserves_unwritten_planned_scenes(tmp_path: Path):
    pd = tmp_path / "partial_sync"
    pd.mkdir(parents=True)
    adaptation.save(
        pd,
        {
            "version": 1,
            "logline": "Existing plan",
            "premise": "A harbor mystery.",
            "ending": "The ferry departs into dawn.",
            "runtime_minutes": 2.0,
            "clip_seconds": 4.0,
            "n_chapters": 2,
            "acts": [{"name": "Act I", "purpose": "Setup", "share": 1.0, "seconds": 120.0, "first_chapter": 1, "last_chapter": 2}],
            "scenes": [
                {"id": "S001", "act": "Act I", "title": "Opening", "summary": "Old summary", "chapters": [1], "clips": 5, "seconds": 20.0, "location": "dock", "characters": [], "time_of_day": "day", "keep": "full"},
                {"id": "S002", "act": "Act I", "title": "Second Scene", "summary": "Unwritten yet", "chapters": [2], "clips": 5, "seconds": 20.0, "location": "ferry", "characters": [], "time_of_day": "night", "keep": "full"},
            ],
            "cut": [],
            "stale": False,
        },
    )
    screenplay.save_scene(
        pd,
        "S001",
        {
            "heading": "EXT. HARBOR - SUNSET",
            "elements": [{"type": "action", "text": "Rain lashes the wooden pier as the ferry arrives."}],
        },
        edited=True,
    )

    res = adaptation.sync_beats_from_screenplay(pd)
    assert res["synced"] is True
    assert res["scenes_synced"] == 1
    assert res["beats_synced"] == 2

    plan = adaptation.load(pd)
    assert plan is not None
    assert [s["id"] for s in plan["scenes"]] == ["S001", "S002"]
    assert plan["scenes"][0]["location"] == "harbor"
    assert "wooden pier" in plan["scenes"][0]["summary"]
    assert plan["scenes"][1]["summary"] == "Unwritten yet"
