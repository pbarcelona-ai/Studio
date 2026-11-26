"""Tests for Step 15 voice baseline & Save-for-All-Scenes auto-filling per-line voice profile settings."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from studio_app import routes_get, routes_post
from studio_app.api import Request


def _req(body: dict | None = None, query: dict | None = None) -> Request:
    q = {k: ([v] if isinstance(v, str) else list(v)) for k, v in (query or {}).items()}
    return Request(query=q, body=body or {}, path="/test")


def _seed_book(book_dir: Path) -> None:
    sp_dir = book_dir / "screenplay"
    sp_dir.mkdir(parents=True)
    (sp_dir / "scene-S001.json").write_text(
        json.dumps(
            {
                "scene": "S001",
                "heading": "INT. LIVING ROOM - DAY",
                "elements": [
                    {"type": "dialogue", "character": "TOMMY", "text": "Ready for launch!", "note": "grinning"},
                    {"type": "dialogue", "character": "JUDAH", "text": "Right behind you!", "note": "jumping"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (sp_dir / "scene-S002.json").write_text(
        json.dumps(
            {
                "scene": "S002",
                "heading": "INT. ROCKET - DAY",
                "elements": [
                    {"type": "dialogue", "character": "TOMMY (V.O.)", "text": "Saturn, here we come!", "note": "whispering"},
                    {"type": "dialogue", "character": "TOMMY", "text": "Hold on tight!", "note": "excited"},
                ],
            }
        ),
        encoding="utf-8",
    )
    # Seed a rendered WAV for S001-01 so it can be baselined
    wav_dir = book_dir / "audio" / "dialogue"
    wav_dir.mkdir(parents=True)
    (wav_dir / "S001-01.wav").write_bytes(b"RIFF" + b"\x00" * 200)
    # Seed pre-existing per-line emotion & note on S002-02 (plus an empty persona that should be overwritten by baseline/apply)
    (book_dir / "dialogue_lines.json").write_text(
        json.dumps(
            {
                "engine": "kokoro",
                "lines": {
                    "S002-02": {
                        "text": "Hold on tight!",
                        "emotion": "urgent",
                        "note": "shouting over engines",
                        "persona": "",
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_baseline_auto_fills_all_lines_for_character_preserving_tone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    book_dir = tmp_path / "projects" / "books" / "space_book"
    _seed_book(book_dir)
    monkeypatch.setattr(routes_post, "pdir", lambda slug, kind="book": tmp_path / "projects" / "books" / slug)
    monkeypatch.setattr(routes_get, "pdir", lambda slug, kind="book": tmp_path / "projects" / "books" / slug)
    monkeypatch.setattr(routes_post, "VOICE_LIBRARY_DIR", tmp_path / "voice_lib")

    res = routes_post._v2_voice_baseline_set(
        _req(
            {
                "project": "space_book",
                "character": "TOMMY",
                "from_line_id": "S001-01",
                "text": "Ready for launch!",
                "gemini_voice": "Puck",
                "kokoro_voice": "am_puck",
                "kokoro_blend": "af_heart",
                "macos_voice": "Alex",
                "persona": "energetic 7-year-old explorer boy",
                "speed": 1.1,
            }
        )
    )
    assert res["status"] == "ok"
    # Should update S001-01 (TOMMY), S002-01 (TOMMY (V.O.)), and S002-02 (TOMMY) = 3 lines, NOT JUDAH
    assert res["updated_lines"] == 3
    assert res["profile"]["persona"] == "energetic 7-year-old explorer boy"
    assert res["profile"]["speed"] == 1.1

    loaded = routes_get._v2_dialogue(_req(query={"project": "space_book"}))
    by_id = {ln["id"]: ln for ln in loaded["lines"]}

    for lid in ("S001-01", "S002-01", "S002-02"):
        assert by_id[lid]["gemini_voice"] == "Puck"
        assert by_id[lid]["kokoro_voice"] == "am_puck"
        assert by_id[lid]["kokoro_blend"] == "af_heart"
        assert by_id[lid]["macos_voice"] == "Alex"
        assert by_id[lid]["persona"] == "energetic 7-year-old explorer boy"
        assert by_id[lid]["speed"] == 1.1

    # Per-line tone & delivery note on S002-02 must remain untouched
    assert by_id["S002-02"]["emotion"] == "urgent"
    assert by_id["S002-02"]["note"] == "shouting over engines"

    # JUDAH must NOT be touched
    assert by_id["S001-02"]["persona"] == ""
    assert by_id["S001-02"]["kokoro_blend"] == ""


def test_save_voice_for_all_scenes_updates_speed_and_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    book_dir = tmp_path / "projects" / "books" / "space_book"
    _seed_book(book_dir)
    monkeypatch.setattr(routes_post, "pdir", lambda slug, kind="book": tmp_path / "projects" / "books" / slug)
    monkeypatch.setattr(routes_get, "pdir", lambda slug, kind="book": tmp_path / "projects" / "books" / slug)
    monkeypatch.setattr(routes_post, "VOICE_LIBRARY_DIR", tmp_path / "voice_lib")

    res = routes_post._v2_voice_profile_apply(
        _req(
            {
                "project": "space_book",
                "character": "TOMMY",
                "gemini_voice": "Fenrir",
                "kokoro_voice": "bm_fable",
                "kokoro_blend": "am_michael",
                "macos_voice": "Daniel",
                "persona": "curious young space captain",
                "speed": 1.2,
            }
        )
    )
    assert res["updated_lines"] == 3
    loaded = routes_get._v2_dialogue(_req(query={"project": "space_book"}))
    by_id = {ln["id"]: ln for ln in loaded["lines"]}
    for lid in ("S001-01", "S002-01", "S002-02"):
        assert by_id[lid]["gemini_voice"] == "Fenrir"
        assert by_id[lid]["kokoro_voice"] == "bm_fable"
        assert by_id[lid]["kokoro_blend"] == "am_michael"
        assert by_id[lid]["macos_voice"] == "Daniel"
        assert by_id[lid]["persona"] == "curious young space captain"
        assert by_id[lid]["speed"] == 1.2
    assert by_id["S002-02"]["emotion"] == "urgent"
