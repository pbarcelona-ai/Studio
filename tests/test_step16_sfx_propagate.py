"""Tests for Step 16 Save & Propagate SFX to all scenes sharing the same SFX description."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from studio_app import routes_get, routes_post
from studio_app.api import Request


def _req(body: dict | None = None, query: dict | None = None) -> Request:
    q = {k: ([v] if isinstance(v, str) else list(v)) for k, v in (query or {}).items()}
    return Request(query=q, body=body or {}, path="/test")


def test_sfx_propagate_updates_only_matching_description_and_copies_wav(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    book_dir = tmp_path / "projects" / "books" / "rainy_book"
    sp_dir = book_dir / "screenplay"
    sp_dir.mkdir(parents=True)

    # S001 and S003 both auto-derive soft distant rain; S002 is spaceship bridge
    (sp_dir / "scene-S001.json").write_text(
        json.dumps({"scene": "S001", "heading": "INT. LIVING ROOM - DAY", "elements": [{"type": "action", "text": "Rain outside the window."}]}),
        encoding="utf-8",
    )
    (sp_dir / "scene-S002.json").write_text(
        json.dumps({"scene": "S002", "heading": "INT. BRIDGE - SPACE", "elements": [{"type": "action", "text": "Stars glow on the display."}]}),
        encoding="utf-8",
    )
    (sp_dir / "scene-S003.json").write_text(
        json.dumps({"scene": "S003", "heading": "INT. BEDROOM - NIGHT", "elements": [{"type": "action", "text": "Soft rain in the house."}]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(routes_post, "pdir", lambda slug, kind="book": tmp_path / "projects" / "books" / slug)
    monkeypatch.setattr(routes_get, "pdir", lambda slug, kind="book": tmp_path / "projects" / "books" / slug)
    monkeypatch.setattr(routes_post, "SFX_LIBRARY_DIR", tmp_path / "_sfx_lib")

    res = routes_post._v2_sound_sfx_propagate(
        _req({
            "project": "rainy_book",
            "source_scene": "S001",
            "match_cue": "Subtle muffled distant rain outside a quiet cozy room, gentle soft indoor room tone",
            "sfx_cue": "Subtle muffled distant rain outside a quiet cozy room",
            "sfx_preset": "soft_rain_room",
            "score_mood": "cozy",
            "duration": 4,
            "render_source": True,
        })
    )
    assert res["status"] == "ok"
    assert res["updated_scenes"] == ["S001", "S003"]
    assert res["count"] == 2
    assert (book_dir / "audio" / "foley" / "scene_S001.wav").is_file()
    assert (book_dir / "audio" / "foley" / "scene_S003.wav").is_file()
    assert not (book_dir / "audio" / "foley" / "scene_S002.wav").exists()
    assert (book_dir / "audio" / "foley" / "scene_S001.wav").read_bytes() == (book_dir / "audio" / "foley" / "scene_S003.wav").read_bytes()

    # Verify Step 16 GET reflects propagated preset & cue on S001 + S003 while leaving S002 untouched
    loaded = routes_get._v2_sound_design(_req(query={"project": "rainy_book"}))
    by_sc = {s["scene"]: s for s in loaded["scenes"]}
    assert by_sc["S001"]["sfx_preset"] == "soft_rain_room"
    assert by_sc["S003"]["sfx_preset"] == "soft_rain_room"
    assert by_sc["S003"]["sfx_cue"] == "Subtle muffled distant rain outside a quiet cozy room"
    assert by_sc["S002"]["sfx_preset"] == "spaceship_voices"

    # Propagating an EMPTY text box must clear sfx_cue across all matching scenes and stay empty on reload
    res_blank = routes_post._v2_sound_sfx_propagate(
        _req({
            "project": "rainy_book",
            "source_scene": "S001",
            "match_cue": "Subtle muffled distant rain outside a quiet cozy room",
            "sfx_cue": "",
            "sfx_preset": "silent",
            "score_mood": "none",
            "duration": 4,
            "render_source": True,
        })
    )
    assert res_blank["updated_scenes"] == ["S001", "S003"]
    reloaded = routes_get._v2_sound_design(_req(query={"project": "rainy_book"}))
    by_sc2 = {s["scene"]: s for s in reloaded["scenes"]}
    assert by_sc2["S001"]["sfx_cue"] == ""
    assert by_sc2["S003"]["sfx_cue"] == ""
    assert by_sc2["S003"]["sfx_preset"] == "silent"
    assert by_sc2["S002"]["sfx_preset"] == "spaceship_voices"


def test_dynamic_story_presets_and_reusable_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(routes_post, "pdir", lambda slug, kind="book": tmp_path / "projects" / "books" / slug)
    monkeypatch.setattr(routes_get, "pdir", lambda slug, kind="book": tmp_path / "projects" / "books" / slug)
    monkeypatch.setattr(routes_post, "SFX_LIBRARY_DIR", tmp_path / "_sfx_lib")

    # Story 1: Medieval Tavern + Ocean Voyage (zero space presets!)
    s1 = tmp_path / "projects" / "books" / "tavern_tale" / "screenplay"
    s1.mkdir(parents=True)
    (s1 / "scene-S001.json").write_text(
        json.dumps({"scene": "S001", "heading": "INT. COZY WOODEN TAVERN - NIGHT", "elements": [{"type": "action", "text": "A warm fireplace crackles as patrons murmur."}]}),
        encoding="utf-8",
    )
    (s1 / "scene-S002.json").write_text(
        json.dumps({"scene": "S002", "heading": "EXT. PIRATE SHIP DECK - NIGHT", "elements": [{"type": "action", "text": "Ocean waves crash against the wooden hull."}]}),
        encoding="utf-8",
    )

    sd1 = routes_get._v2_sound_design(_req(query={"project": "tavern_tale"}))
    preset_ids = {p["id"] for p in sd1["presets"]}
    assert "story_hearth" in preset_ids
    assert "story_ocean" in preset_ids
    assert "space_adventure" not in preset_ids
    assert "action_launch" not in preset_ids
    assert "spaceship" not in sd1["foley"]["prompt"].lower()

    # Save a reusable SFX preset from Story 1 and confirm Story 2 inherits it!
    saved_res = routes_post._v2_sound_preset_save(
        _req({"project": "tavern_tale", "label": "Tavern Hearth Murmur", "prompt": "crackling fireplace with soft distant voices"})
    )
    assert saved_res["saved"]["id"].startswith("lib_")

    s2 = tmp_path / "projects" / "books" / "forest_story" / "screenplay"
    s2.mkdir(parents=True)
    (s2 / "scene-S001.json").write_text(
        json.dumps({"scene": "S001", "heading": "EXT. SUNLIT FOREST - DAY", "elements": [{"type": "action", "text": "Birds sing in the tall pines."}]}),
        encoding="utf-8",
    )
    sd2 = routes_get._v2_sound_design(_req(query={"project": "forest_story"}))
    s2_ids = {p["id"] for p in sd2["presets"]}
    assert saved_res["saved"]["id"] in s2_ids
    assert "forest_nature" in s2_ids
    assert "space_adventure" not in s2_ids


def test_custom_text_overrides_pulldown_sfx(tmp_path: Path):
    import math
    import struct
    import wave

    def _rms(p: Path) -> float:
        with wave.open(str(p), "rb") as wf:
            raw = wf.readframes(wf.getnframes())
        samples = struct.unpack(f"<{len(raw) // 2}h", raw)
        return math.sqrt(sum(s * s for s in samples) / max(1, len(samples)))

    # Custom text overrides even when pulldown is still set to space_adventure
    f_fire = tmp_path / "fire_rain.wav"
    layers = routes_post._synth_foley_wav(f_fire, "crackling fireplace with soft distant rain and ticking clock", "space_adventure", 4)
    assert "fireplace" in layers and "soft_rain" in layers and "clock" in layers
    assert "telemetry" not in layers
    assert _rms(f_fire) > 100

    # Subtle/quiet text modifier produces noticeably softer audio than heavy/loud text
    f_soft = tmp_path / "soft_ocean.wav"
    f_loud = tmp_path / "loud_ocean.wav"
    routes_post._synth_foley_wav(f_soft, "subtle distant ocean waves", "custom", 4)
    routes_post._synth_foley_wav(f_loud, "loud heavy ocean waves", "custom", 4)
    assert _rms(f_soft) < _rms(f_loud) * 0.45

    # Explicit "silent" text in custom mode produces zero-sample silence
    f_sil = tmp_path / "silent_custom.wav"
    sil_layers = routes_post._synth_foley_wav(f_sil, "silent", "custom", 4)
    assert sil_layers == ["silent"]
    assert _rms(f_sil) == 0.0

    # Low spaceship hum and distant voices in background (both via custom text and preset)
    f_ship = tmp_path / "ship_voices.wav"
    sv_layers = routes_post._synth_foley_wav(f_ship, "a low spaceship hum and distant voices in background", "custom", 4)
    assert "cabin_hum" in sv_layers and "distant_voices" in sv_layers
    assert "telemetry" not in sv_layers
    assert _rms(f_ship) > 400


