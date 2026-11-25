"""Tests for scripts/sfx_local.py (Openverse CC0 Audio API + Earshot procedural SFX) and sound_routes /api/sfx_render."""
from __future__ import annotations

import io
import json
import urllib.error
import wave
from pathlib import Path

import pytest

import render_cut as rc
import sfx_local as sfx
import tts_audit as ta

imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._buf = io.BytesIO(payload)

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestQueryAndRecipes:
    def test_clean_query_and_match_recipe(self):
        assert sfx.clean_query("Soft rain tapping on the wooden roof") == "rain tapping wooden roof"
        assert sfx.clean_query("the a of") == "the a of"
        assert sfx.match_recipe("fast cinematic whoosh transition") == "whoosh"
        assert sfx.match_recipe("tension riser build before reveal") == "riser"
        assert sfx.match_recipe("crisp UI button click") == "click"
        assert sfx.match_recipe("soft magic chime bell") == "chime"
        assert sfx.match_recipe("heavy wooden door slam impact") == "impact"
        assert sfx.match_recipe("steady forest rain ambience") == "ambience"
        assert sfx.match_recipe("unusual uncategorized texture") == "ambience"

    @pytest.mark.parametrize("recipe", ["whoosh", "riser", "click", "chime", "impact", "ambience"])
    def test_earshot_all_recipes_valid_deterministic_wav(self, tmp_path, recipe):
        out1 = tmp_path / f"{recipe}_1.wav"
        out2 = tmp_path / f"{recipe}_2.wav"
        m1 = sfx.synthesize_earshot(f"test {recipe}", out1, duration=1.0, recipe=recipe, seed=42)
        sfx.synthesize_earshot(f"test {recipe}", out2, duration=1.0, recipe=recipe, seed=42)
        assert m1["source"] == "earshot" and m1["recipe"] == recipe
        assert out1.read_bytes() == out2.read_bytes()
        st = ta.wav_stats(out1)
        assert st["channels"] == 2 and st["sample_rate"] == 44100
        assert not st["silent"] and not st["clipped"] and st["duration"] > 0.2


class TestOpenverseClient:
    def test_pick_candidate_scoring_and_filtering(self):
        items = [
            {"url": "ftp://bad.example/a.wav", "duration": 2000, "license": "cc0"},
            {"url": "https://example.com/long.mp3", "duration": 90_000, "license": "cc0"},
            {"url": "https://example.com/by.mp3", "duration": 3000, "license": "by", "source": "jamendo"},
            {"url": "https://example.com/cc0.wav", "duration": 4000, "license": "cc0", "source": "freesound", "title": "Rain"},
        ]
        best = sfx.pick_openverse_candidate(items)
        assert best is not None and best["title"] == "Rain"
        assert sfx.pick_openverse_candidate([items[0], items[1]]) is None

    def test_search_openverse_params_and_error_handling(self, monkeypatch):
        seen_urls: list[str] = []

        def fake_open(req, timeout=15):
            seen_urls.append(req.full_url)
            return _FakeResponse(json.dumps({"results": [{"url": "https://ex/a.wav", "license": "cc0"}]}).encode())

        monkeypatch.setattr("urllib.request.urlopen", fake_open)
        r1 = sfx.search_openverse("rain on roof", license_mode="cc0")
        assert len(r1) == 1 and "license=cc0" in seen_urls[0]
        r2 = sfx.search_openverse("rain on roof", license_mode="commercial")
        assert len(r2) == 1 and "license_type=commercial" in seen_urls[1]
        assert sfx.search_openverse("   ") == []

        def broken_open(req, timeout=15):
            raise urllib.error.URLError("offline")

        monkeypatch.setattr("urllib.request.urlopen", broken_open)
        assert sfx.search_openverse("rain") == []

    def test_download_and_convert_real_ffmpeg(self, tmp_path, monkeypatch):
        src_wav = tmp_path / "src.wav"
        sfx.synthesize_earshot("rain", src_wav, duration=2.0, recipe="ambience", seed=7)
        raw_bytes = src_wav.read_bytes()

        monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=30: _FakeResponse(raw_bytes))
        dest = tmp_path / "out.wav"
        sfx.download_and_convert("https://example.com/rain.wav", dest, duration=1.0, ffmpeg_bin=FFMPEG)
        with wave.open(str(dest), "rb") as wf:
            assert wf.getnchannels() == 2 and wf.getframerate() == 44100
            assert 0.8 <= wf.getnframes() / wf.getframerate() <= 1.2

        with pytest.raises(sfx.SFXError, match="non-HTTP"):
            sfx.download_and_convert("file:///etc/passwd", dest, ffmpeg_bin=FFMPEG)
        monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=30: _FakeResponse(b""))
        with pytest.raises(sfx.SFXError, match="empty"):
            sfx.download_and_convert("https://example.com/empty.wav", dest, ffmpeg_bin=FFMPEG)


class TestBookSFXRunner:
    def test_auto_mode_mixes_openverse_and_earshot_and_integrates_with_render_cut(self, tmp_path):
        pdir = tmp_path / "book"
        pdir.mkdir()
        (pdir / "audio_shots.csv").write_text(
            "shot,sfx\n1,fast cinematic whoosh transition\n2,steady rain on window\n3,mysterious cave echo\n",
            encoding="utf-8",
        )

        def fake_fetch(q: str, lic: str) -> list[dict]:
            if "rain" in q.lower():
                return [{"url": "https://example.com/rain.wav", "duration": 5000, "license": "cc0",
                         "license_version": "1.0", "creator": "FieldRec", "title": "Window Rain",
                         "foreign_landing_url": "https://freesound.org/s/123/", "source": "freesound"}]
            return []

        def fake_dl(url: str, dest: Path, duration: float) -> Path:
            sfx.synthesize_earshot("rain", dest, duration=1.0, recipe="ambience", seed=99)
            return dest

        res = sfx.render_book_sfx(pdir, mode="auto", duration=1.5, fetcher=fake_fetch, downloader=fake_dl, say=lambda _: None)
        assert res["total"] == 3 and res["rendered"] == 3 and res["openverse"] == 1 and res["earshot"] == 2 and res["missed"] == 0
        out_dir = pdir / "audio" / "openverse"
        assert (out_dir / "sfx-0001.wav").is_file()
        assert (out_dir / "sfx-0002.wav").is_file()
        assert (out_dir / "sfx-0003.wav").is_file()
        credits_txt = (out_dir / "credits.txt").read_text(encoding="utf-8")
        assert "Window Rain" in credits_txt and "FieldRec" in credits_txt and "CC0" in credits_txt

        # Verify render_cut.audio_files discovers the rendered SFX automatically
        found = rc.audio_files(pdir, {"voice": [], "music": [], "effects": [{"ref": 1}, {"ref": 2}, {"ref": 3}]})
        assert len(found) == 3 and all(t == "effects" for t, _, _ in found)

        # Re-running without force skips all existing WAVs
        res2 = sfx.render_book_sfx(pdir, mode="auto", fetcher=fake_fetch, downloader=fake_dl, say=lambda _: None)
        assert res2["skipped"] == 3 and res2["rendered"] == 0

    def test_openverse_only_earshot_only_and_cli(self, fake_root):
        pdir = fake_root / "projects" / "books" / "demo"
        (pdir / "shots").mkdir(parents=True, exist_ok=True)
        (pdir / "sound").mkdir(parents=True, exist_ok=True)
        (pdir / "shots" / "shotlist.json").write_text(
            json.dumps({"scenes": [{"id": "S001", "shots": [{"n": 1, "seconds": 2.0}]}]}),
            encoding="utf-8",
        )
        (pdir / "sound" / "plan.json").write_text(
            json.dumps({"effects": {"S001": [{"n": 1, "sfx": "crisp UI click"}]}}),
            encoding="utf-8",
        )

        # openverse-only with no results reports missed cleanly
        r_ov = sfx.render_book_sfx(pdir, mode="openverse", fetcher=lambda q, l: [], say=lambda _: None)
        assert r_ov["missed"] == 1 and r_ov["rendered"] == 0

        # CLI in offline earshot mode renders audio/earshot/sfx-0001.wav
        assert sfx.main(["demo", "--mode", "earshot", "--duration", "1.0"]) == 0
        assert (pdir / "audio" / "earshot" / "sfx-0001.wav").is_file()

        with pytest.raises(sfx.SFXError):
            sfx.render_book_sfx(pdir, mode="invalid")
        with pytest.raises(sfx.SFXError):
            sfx.render_book_sfx(pdir, license_mode="gpl")
