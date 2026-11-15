"""credits.py, the credits roll and extra audio tracks in mix_film.py (real ffmpeg)."""
import json
import re
import subprocess

import pytest

import credits as cr

imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def ff(*args):
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args], check=True)


def seconds(path):
    err = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def mean_volume(path, start, length):
    r = subprocess.run([FFMPEG, "-ss", str(start), "-t", str(length), "-i", str(path), "-vn", "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", r.stderr)
    return float("-inf") if not m or m.group(1) == "-inf" else float(m.group(1))


class TestCredits:
    def test_load_check_save(self, tmp_path):
        assert cr.load(tmp_path)["rating"] == "" and cr.load(tmp_path)["crew"] == []
        saved = cr.save(tmp_path, {"title": "T", "rating": "PG", "crew": [{"role": "Music", "name": "A. Person"}, {"role": "x", "name": ""}], "unknown": 1})
        assert saved["rating"] == "PG" and saved["crew"] == [{"role": "Music", "name": "A. Person"}] and "unknown" not in saved
        for bad in ("x", {"rating": "XXX"}, {"title": "t" * 500}, {"crew": "no"}, {"crew": [{"name": "n" * 200}]}):
            with pytest.raises(cr.CreditsError):
                cr.check(bad)
        (tmp_path / "credits.json").write_text("[1]")
        assert cr.load(tmp_path)["title"] == ""

    def test_lines(self, book):
        (book / "audio" / "kokoro").mkdir(parents=True)
        (book / "audio" / "kokoro" / "narration-0001.wav").write_bytes(b"x")
        (book / "audio" / "musicgen").mkdir()                                  # an empty folder is not credited
        cr.save(book, {"based_on": "The Book", "author": "A. Author", "written_by": "Me", "rating": "PG", "content_notes": "mild peril", "rights": "Public domain.",
                       "crew": [{"role": "Colour", "name": "C. Grader"}]})
        lines = cr.lines(book)
        assert lines[:3] == ["Based on", "The Book, A. Author", ""] and "Written by" in lines and "Characters" in lines and "Eve" in lines
        assert "Made with artificial intelligence" in lines and "Narration: Kokoro" in lines and not any("MusicGen" in x for x in lines)
        assert lines[-2:] == ["Rated PG", "mild peril"] and "C. Grader" in lines and lines[-1] != ""

    def test_nothing_filled_in(self, tmp_path):
        assert cr.lines(tmp_path) == []


@pytest.fixture()
def silent_film(book):
    v = book / "videos" / "ltx_video"
    v.mkdir(parents=True)
    for n in (1, 2):
        ff("-f", "lavfi", "-i", "color=c=blue:s=160x90:r=12:d=1", "-pix_fmt", "yuv420p", str(v / f"shot-{n:04d}.mp4"))
    return book


def mix(run_script, *args):
    code, out = run_script("mix_film.py", "--project", "demo", "--model", "ltx_video", "--sync", "trim", "--no-loudnorm", *args)
    assert code is None, out
    return out


class TestRoll:
    def test_the_credits_follow_the_film(self, silent_film, run_script):
        mix(run_script, "--out", "plain.mp4")
        cr.save(silent_film, {"based_on": "The Book", "rating": "PG"})
        out = mix(run_script, "--credits", "--out", "rolled.mp4")
        plain, rolled = seconds(silent_film / "films" / "plain.mp4"), seconds(silent_film / "films" / "rolled.mp4")
        assert "credits:" in out and rolled > plain + 5

    def test_the_models_used_are_credited_even_when_nothing_else_is_filled_in(self, silent_film, run_script):
        (silent_film / "demo.json").unlink()
        out = mix(run_script, "--credits", "--out", "ai.mp4")
        assert "credits: 2 line(s)" in out                                         # "Made with artificial intelligence" and the video model

    def test_no_credits_to_show(self, silent_film, run_script, monkeypatch):
        (silent_film / "demo.json").unlink()
        monkeypatch.setattr(cr, "MADE_WITH", {})
        out = mix(run_script, "--credits", "--out", "none.mp4")
        assert "credits skipped: nothing to show" in out and seconds(silent_film / "films" / "none.mp4") < 3


class TestTracks:
    @pytest.fixture()
    def tone(self, silent_film):
        (silent_film / "audio" / "ambience").mkdir(parents=True)
        ff("-f", "lavfi", "-i", "sine=f=440:d=1.2", str(silent_film / "audio" / "ambience" / "tone.wav"))
        return "audio/ambience/tone.wav"

    def test_a_track_can_cross_a_cut(self, silent_film, run_script, tone):
        (silent_film / "tracks.json").write_text(json.dumps([{"file": tone, "start": 0.6, "volume": 1.0}]))
        mix(run_script, "--tracks", "tracks.json", "--out", "t.mp4")
        film = silent_film / "films" / "t.mp4"
        assert mean_volume(film, 0.8, 0.4) > -50 and mean_volume(film, 1.2, 0.4) > -50 and mean_volume(film, 0.0, 0.4) == float("-inf") or mean_volume(film, 0.0, 0.4) < -60

    def test_a_short_track_repeats_to_the_length_asked(self, silent_film, run_script, tone):
        ff("-f", "lavfi", "-i", "sine=f=330:d=3", str(silent_film / "audio" / "ambience" / "long.wav"))
        (silent_film / "tracks.json").write_text(json.dumps([{"file": "audio/ambience/long.wav", "start": 0, "seconds": 1.9, "fade": 0.1}]))
        mix(run_script, "--tracks", "tracks.json", "--out", "l.mp4")
        assert mean_volume(silent_film / "films" / "l.mp4", 0.5, 1.0) > -50

    def test_selection_tracks_and_bad_ones(self, silent_film, run_script, tone):
        (silent_film / "films").mkdir()
        sel = {"clips": [{"row": 1, "video": "videos/ltx_video/shot-0001.mp4"}, {"row": 2, "video": "videos/ltx_video/shot-0002.mp4"}], "tracks": [{"file": tone, "start": 0.1}]}
        (silent_film / "films" / "_selection.json").write_text(json.dumps(sel))
        code, out = run_script("mix_film.py", "--project", "demo", "--selection", "films/_selection.json", "--no-loudnorm", "--sync", "trim", "--out", "s.mp4")
        assert code is None and mean_volume(silent_film / "films" / "s.mp4", 0.3, 0.5) > -50
        for bad, msg in (([{"start": 1}], "needs a file"), ([{"file": tone, "volume": 9}], "out of range"), ([{"file": "../x.wav"}], "not a file inside the project")):
            (silent_film / "tracks.json").write_text(json.dumps(bad))
            code, _ = run_script("mix_film.py", "--project", "demo", "--model", "ltx_video", "--tracks", "tracks.json", "--out", "b.mp4")
            assert msg in str(code)

    def test_a_track_after_the_end_is_skipped(self, silent_film, run_script, tone):
        (silent_film / "tracks.json").write_text(json.dumps([{"file": tone, "start": 50}]))
        assert "starts after the film ends" in mix(run_script, "--tracks", "tracks.json", "--out", "late.mp4")
