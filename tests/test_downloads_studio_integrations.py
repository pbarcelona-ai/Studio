"""Tests for Studio integrations imported from Downloads:
- Fabric-Collage Appliqué visual style + animated sample GIF
- Close-Up Face Crop Auto-Reference Lock (Image 1 on CU/MCU/ECU shots)
- Per-Plate Contact Sheet QA Audit (POST/GET /api/v2_plate_audit)
- Beat-by-Beat Timed Step 18 Animation Prompts (POST /api/v2_beat_motion_prompt)
- Audio-First Clock, Safe-Zone Captions, Proofread Find/Replace, -14 LUFS normalization, & strict 40 ms sync QA
"""
from __future__ import annotations

import json
import math
import struct
import wave
from pathlib import Path

import audio_first_clock as afc
import character_types_registry as ctr
import production
import pytest
from PIL import Image
from studio_app import keyframe_context as kfc
from studio_app import routes_get, routes_post
from studio_app.api import Request


def _make_png(path: Path, size: tuple[int, int] = (512, 384), color: tuple[int, int, int] = (90, 140, 210)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", size, color)
    px = im.load()
    assert px is not None
    for y in range(0, size[1], 4):
        for x in range(0, size[0], 4):
            px[x, y] = ((color[0] + x) % 255, (color[1] + y) % 255, color[2])
    im.save(path, "PNG")
    return path


def _make_sine_wav(path: Path, duration_s: float = 2.0, sr: int = 22050, amp: float = 0.08) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(sr * duration_s)
    frames = bytearray()
    for i in range(n):
        v = int(max(-1.0, min(1.0, amp * math.sin(2.0 * math.pi * 440.0 * i / sr))) * 32767)
        frames.extend(struct.pack("<h", v))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(frames))
    return path


def _req(body: dict | None = None, query: dict | None = None) -> Request:
    q = {k: ([v] if isinstance(v, str) else list(v)) for k, v in (query or {}).items()}
    return Request(query=q, body=body or {}, path="/test")


def test_fabric_collage_style_registered_with_animated_gif():
    st = ctr.get_style("fabric_collage")
    assert st is not None
    assert "blanket stitches" in st["positives"].lower()
    assert "fabric_collage" in production.STYLES
    gif = Path(__file__).resolve().parent.parent / "web" / "static" / "img" / "style_samples" / "fabric_collage.gif"
    assert gif.is_file() and gif.stat().st_size > 10_000


def test_closeup_face_crop_lock_becomes_image_1_and_plate_audit_builds_sheets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = tmp_path / "repo"
    pd = repo / "projects" / "books" / "garden_story"
    (pd / "shots").mkdir(parents=True)
    (pd / "keyframes").mkdir(parents=True)

    # Create Step 10 3-panel sheet + Step 11 set plate + Step 17 keyframes
    sheet_png = _make_png(pd / "assets" / "turnarounds" / "tommy_sheet.png", size=(768, 512), color=(180, 120, 90))
    _make_png(pd / "assets" / "sets" / "garden.png", size=(640, 360), color=(70, 150, 80))
    _make_png(pd / "keyframes" / "S001-01.png", size=(640, 360), color=(110, 130, 180))
    _make_png(pd / "keyframes" / "S001-02.png", size=(640, 360), color=(140, 110, 160))

    (pd / "garden_story.json").write_text(json.dumps({
        "characters": [{"name": "Tommy", "token": "8-year-old boy with curly brown hair and red jacket"}],
        "locations": [{"name": "Garden", "token": "sunlit stitched daisy garden with sage fence"}],
    }), encoding="utf-8")

    sl_data = {
        "scenes": [{
            "id": "S001",
            "heading": "EXT. GARDEN - DAY",
            "shots": [
                {"n": 1, "type": "WS", "lens_mm": 24, "characters": ["Tommy"], "action": "Tommy stands in the garden"},
                {"n": 2, "type": "CU", "lens_mm": 85, "characters": ["Tommy"], "action": "Close-up of Tommy smiling warmly"},
            ],
        }]
    }
    (pd / "shots" / "shotlist.json").write_text(json.dumps(sl_data), encoding="utf-8")

    monkeypatch.setattr(routes_post, "pdir", lambda slug, kind="book": pd)
    monkeypatch.setattr(routes_get, "pdir", lambda slug, kind="book": pd)

    ctx = kfc.load_keyframe_project_context("garden_story", pd)
    # Close-up shot S001-02 must auto-crop Tommy's sheet and place the face crop as Reference Image #1
    refs = kfc.collect_render_references(ctx, "S001-02", "Close-up of Tommy smiling", sl_data, pd / "keyframes", {})
    assert refs["ref_imgs"], "Expected references to be attached"
    assert refs["ref_imgs"][0].name == "tommy_face_crop.png"
    assert refs["ref_imgs"][0].is_file() and refs["ref_imgs"][0] != sheet_png
    assert "Image 1 = Tommy FACE CLOSE-UP CROP" in refs["ref_legend"]

    # Plate audit should build side-by-side contact sheets for both Tommy and Garden
    audit = routes_post._v2_plate_audit_post(_req({"project": "garden_story"}))
    assert audit["passed"] is True
    assert audit["total_rendered_stills"] == 2
    assert audit["plate_count"] == 2
    sheet_ids = {s["id"] for s in audit["sheets"]}
    assert "char_tommy" in sheet_ids and "set_garden" in sheet_ids
    for s in audit["sheets"]:
        assert (pd / "qa" / "plate_sheets" / f"plate_{s['id']}.jpg").is_file()

    # GET endpoint returns cached audit cleanly
    cached = routes_get._v2_plate_audit_get(_req(query={"project": "garden_story"}))
    assert cached["plate_count"] == 2


def test_beat_motion_prompt_emits_timed_beats_sequence_and_audio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pd = tmp_path / "garden_story"
    (pd / "shots").mkdir(parents=True)
    (pd / "global_params.json").write_text(json.dumps({"look": "fabric_collage"}), encoding="utf-8")
    (pd / "shots" / "shotlist.json").write_text(json.dumps({
        "scenes": [{
            "id": "S001",
            "heading": "EXT. GARDEN - DAY",
            "shots": [{"n": 1, "seconds": 6, "characters": ["Lily", "Rabbit"], "action": "Lily spins the pinwheel as the rabbit twitches its ear", "expression": "delighted smile"}],
        }]
    }), encoding="utf-8")

    monkeypatch.setattr(routes_post, "pdir", lambda slug, kind="book": pd)
    res = routes_post._v2_beat_motion_prompt(_req({"project": "garden_story", "shot_id": "S001-01"}))
    assert res["status"] == "ok"
    assert res["style_id"] == "fabric_collage"
    p = res["prompt"]
    assert "0.0–" in p
    assert "ESSENTIAL SEQUENCE:" in p
    assert "STYLE & CONSISTENCY RULES:" in p
    assert "AUDIO:" in p


def test_audio_first_clock_safe_captions_proofread_and_lufs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Word cleaning keeps decimals and URLs while stripping trailing periods/quotes
    assert afc.clean_caption_word("2.5,") == "2.5"
    assert afc.clean_caption_word("10,000.") == "10,000"
    assert afc.clean_caption_word("site.com.") == "site.com"
    assert afc.clean_caption_word('"Hello!"') == "Hello!"

    # Safe-zone segmentation prevents dangling small words and enforces >= 56 px floor
    words = [
        {"word": "Use", "start": 0.0, "end": 0.25},
        {"word": "Cloud", "start": 0.25, "end": 0.55},
        {"word": "Code", "start": 0.55, "end": 0.85},
        {"word": "to", "start": 0.85, "end": 1.00},
        {"word": "build", "start": 1.00, "end": 1.30},
        {"word": "site.com", "start": 1.30, "end": 1.75},
        {"word": "in", "start": 1.75, "end": 1.90},
        {"word": "2.5", "start": 1.90, "end": 2.20},
        {"word": "minutes", "start": 2.20, "end": 2.60},
    ]
    cues = afc.segment_safe_captions(words, fps=24)
    assert cues
    assert all(c["font_px"] >= afc.MIN_CAPTION_PX for c in cues)
    # First cue should NOT end with dangling small word "to"
    assert not cues[0]["text"].lower().endswith(" to")
    assert any("site.com" in c["text"] and "2.5" in c["text"] for c in cues) or (
        any("site.com" in c["text"] for c in cues) and any("2.5" in c["text"] for c in cues)
    )

    # Full route round-trip: build clock + proofread "Cloud" -> "Claude" + LUFS normalize
    pd = tmp_path / "reel_proj"
    (pd / "screenplay").mkdir(parents=True)
    (pd / "screenplay" / "scene-001.json").write_text(json.dumps({
        "heading": "INT. STUDIO - DAY",
        "elements": [{"type": "dialogue", "character": "HOST", "text": "Use Cloud Code to build site.com in 2.5 minutes"}],
    }), encoding="utf-8")
    _make_sine_wav(pd / "audio" / "mix" / "master_mix.wav", duration_s=2.0, amp=0.05)

    monkeypatch.setattr(routes_post, "pdir", lambda slug, kind="book": pd)
    clock = routes_post._v2_audio_first_clock(_req({"project": "reel_proj", "fps": 24, "use_whisper": False}))
    assert clock["cue_count"] >= 1
    assert clock["sync_drift_ms"] <= 40.0
    assert (pd / "exports" / "captions" / "safe_captions.srt").is_file()

    fixed = routes_post._v2_caption_proofread(_req({"project": "reel_proj", "find": "Cloud", "replace": "Claude"}))
    assert fixed["changed_cues"] >= 1
    srt_text = (pd / "exports" / "captions" / "safe_captions.srt").read_text(encoding="utf-8")
    assert "Claude" in srt_text and "Cloud" not in srt_text

    # LUFS normalization brings quiet sine wave up near -14 LUFS
    norm = routes_post._v2_lufs_normalize(_req({"project": "reel_proj", "target_lufs": -14.0}))
    assert norm["status"] == "ok"
    assert norm["after_lufs"] is not None
    assert abs(float(norm["after_lufs"]) - (-14.0)) < 2.0
