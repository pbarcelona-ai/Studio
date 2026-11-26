"""End-to-end tests for Studio Adders #1–#5:
1. Reference-Video -> Editing Style Guide Analyzer (POST/GET /api/v2_editing_style*)
2. Dialogue & Narration Humanizer Pass (POST /api/v2_humanize_script)
3. One-Click Pitch Deck (.pptx) & Production Breakdown (.xlsx) Exports (POST /api/v2_export_make)
4. Deterministic 60fps Code-Drawn Animation & Title-Card Pack (GET/POST /api/v2_code_drawn_*)
5. Burn-In Safe-Zone Captions Directly Into Step 22 MP4 / 9:16 Shorts Exports
"""
from __future__ import annotations

import json
from pathlib import Path

import audio_first_clock as afc
import code_drawn_templates as cdt
import openpyxl
import pytest
import script_humanizer as sh
from PIL import Image
from pptx import Presentation
from studio_app import routes_get, routes_post
from studio_app.api import Request


def _req(body: dict | None = None, query: dict | None = None) -> Request:
    q = {k: ([v] if isinstance(v, str) else list(v)) for k, v in (query or {}).items()}
    return Request(query=q, body=body or {}, path="/test")


def _make_png(path: Path, size: tuple[int, int] = (320, 180), color: tuple[int, int, int] = (80, 130, 190)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", size, color)
    px = im.load()
    assert px is not None
    for y in range(0, size[1], 4):
        for x in range(0, size[0], 4):
            px[x, y] = ((color[0] + x) % 255, (color[1] + y) % 255, color[2])
    im.save(path, "PNG")
    return path


def test_adder2_script_humanizer_cleans_ai_cliches_and_updates_screenplay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cleaned, reasons = sh.humanize_text(
        "It is important to note that we must delve into a tapestry of stars — a testament to unwavering courage — moreover, let us embark on a journey!",
        is_dialogue=True,
    )
    assert "delve" not in cleaned.lower()
    assert "tapestry" not in cleaned.lower()
    assert "testament" not in cleaned.lower()
    assert "unwavering" not in cleaned.lower()
    assert "—" not in cleaned
    assert reasons

    pd = tmp_path / "space_book"
    (pd / "screenplay").mkdir(parents=True)
    scene_file = pd / "screenplay" / "scene-001.json"
    scene_file.write_text(json.dumps({
        "heading": "INT. BRIDGE - DAY",
        "elements": [
            {"type": "action", "text": "Tommy meticulously checks the gleaming controls."},
            {"type": "dialogue", "character": "TOMMY", "text": "Furthermore, we shall embark on a journey — a beacon of hope!"},
        ],
    }), encoding="utf-8")

    monkeypatch.setattr(routes_post, "pdir", lambda slug, kind="book": pd)
    res = routes_post._v2_humanize_script(_req({"project": "space_book", "apply": True, "dialogue_only": False}))
    assert res["lines_changed"] == 2
    saved = json.loads(scene_file.read_text(encoding="utf-8"))
    assert "carefully" in saved["elements"][0]["text"].lower()
    assert "set out" in saved["elements"][1]["text"].lower()
    assert "—" not in saved["elements"][1]["text"]


def test_adder3_pitch_deck_pptx_and_production_breakdown_xlsx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    pd = tmp_path / "saturn_trip"
    (pd / "shots").mkdir(parents=True)
    (pd / "readin").mkdir(parents=True)
    _make_png(pd / "assets" / "turnarounds" / "tommy_front.png", size=(256, 256), color=(190, 120, 80))
    _make_png(pd / "assets" / "sets" / "living_room_baseline.png", size=(320, 180), color=(90, 140, 110))
    _make_png(pd / "keyframes" / "S001-01.png", size=(320, 180), color=(60, 110, 200))

    (pd / "sets_views.json").write_text(json.dumps({
        "sets": {"living room": {"name": "Living Room", "baseline_snapshot": "assets/sets/living_room_baseline.png", "views": []}}
    }), encoding="utf-8")
    (pd / "saturn_trip.json").write_text(json.dumps({
        "characters": [{"name": "Tommy", "token": "5-year-old boy in brown t-shirt"}],
        "locations": [{"name": "Living Room", "token": "Cozy living room with floral rug"}],
    }), encoding="utf-8")
    (pd / "readin" / "coverage.json").write_text(json.dumps({
        "title": "Mission to Saturn",
        "logline": "A boy and his Labrador turn a cardboard box into a starship.",
    }), encoding="utf-8")
    (pd / "shots" / "shotlist.json").write_text(json.dumps({
        "scenes": [{
            "id": "S001",
            "heading": "INT. LIVING ROOM - DAY",
            "shots": [
                {"n": 1, "type": "WS", "lens_mm": 24, "seconds": 4.5, "characters": ["Tommy"], "action": "Tommy climbs into the box"},
                {"n": 2, "type": "CU", "lens_mm": 85, "seconds": 3.0, "characters": ["Tommy"], "action": "Tommy grins wide"},
            ],
        }]
    }), encoding="utf-8")

    monkeypatch.setattr(routes_post, "pdir", lambda slug, kind="book": pd)

    pptx_res = routes_post._v2_export_make(_req({"project": "saturn_trip", "target": "pitch_pptx"}))
    assert pptx_res["status"] == "ok"
    pptx_path = pd / "exports" / "saturn_trip_pitch_deck.pptx"
    assert pptx_path.is_file() and pptx_path.stat().st_size > 10_000
    prs = Presentation(str(pptx_path))
    assert len(prs.slides) >= 4

    xlsx_res = routes_post._v2_export_make(_req({"project": "saturn_trip", "target": "prod_xlsx"}))
    assert xlsx_res["status"] == "ok"
    xlsx_path = pd / "exports" / "saturn_trip_production_breakdown.xlsx"
    assert xlsx_path.is_file() and xlsx_path.stat().st_size > 3_000
    wb = openpyxl.load_workbook(str(xlsx_path))
    assert set(wb.sheetnames) == {"Shot List", "Cast & Wardrobe", "Locations & Sets"}
    assert wb["Shot List"]["G4"].value == "=SUM(G2:G3)"


def test_adder4_code_drawn_clip_and_adder1_reference_analyzer_and_adder5_caption_burnin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    pd = tmp_path / "studio_demo"
    (pd / "screenplay").mkdir(parents=True)
    (pd / "screenplay" / "scene-001.json").write_text(json.dumps({
        "heading": "INT. STUDIO - DAY",
        "elements": [{"type": "dialogue", "character": "NARRATOR", "text": "Welcome to Mission Saturn 2.5 on site.com"}],
    }), encoding="utf-8")
    _make_png(pd / "keyframes" / "S001-01.png", size=(320, 180), color=(70, 90, 160))

    monkeypatch.setattr(routes_post, "pdir", lambda slug, kind="book": pd)
    monkeypatch.setattr(routes_get, "pdir", lambda slug, kind="book": pd)

    # Adder #4: list templates + render a real deterministic code-drawn MP4
    tpls = routes_get._v2_code_drawn_templates_get(_req())
    assert len(tpls["templates"]) == len(cdt.CODE_DRAWN_TEMPLATES) >= 6
    cd_res = routes_post._v2_code_drawn_render(_req({
        "project": "studio_demo",
        "template_id": "chalkboard_handdraw",
        "title": "Mission Saturn",
        "subtitle": "Chapter 01",
        "bullets": ["Build Rocket", "Visit Titan"],
        "aspect": "16:9",
        "duration": 2.0,
        "fps": 12,
    }))
    assert cd_res["status"] == "ok"
    mp4_name = Path(cd_res["video_url"]).name
    clip_path = pd / "exports" / "code_drawn" / mp4_name
    assert clip_path.is_file() and clip_path.stat().st_size > 5_000

    # Adder #1: analyze that real MP4 as a reference video -> generates Editing Style Guide.md + JSON
    style_res = routes_post._v2_editing_style_analyze(_req({
        "project": "studio_demo",
        "local_path": str(clip_path),
        "use_whisper": False,
    }))
    assert style_res["status"] == "ok"
    assert style_res["video_count"] == 1
    assert style_res["palette"]
    assert (pd / "references" / "Editing Style Guide.md").is_file()
    cached_style = routes_get._v2_editing_style_get(_req(query={"project": "studio_demo"}))
    assert cached_style["has_guide"] is True

    # Adder #5: burn safe-zone captions into a 9:16 Shorts export via _v2_export_make
    ass_text = afc.cues_to_ass([{"start": 0.0, "end": 1.5, "text": "Mission Saturn 2.5", "font_px": 60}], is_vertical=True)
    assert "PlayResX: 1080" in ass_text and "PlayResY: 1920" in ass_text
    exp_res = routes_post._v2_export_make(_req({
        "project": "studio_demo",
        "target": "shorts_9x16",
        "burn_captions": True,
    }))
    assert exp_res["status"] == "ok"
    assert exp_res["captions_burned"] >= 1
    assert (pd / "films" / "shorts_9x16.mp4").is_file()
