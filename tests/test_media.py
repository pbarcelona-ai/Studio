"""M13: video / audio sources: shot detection, key frames, transcript, the Story Analyst's account; binding segments; real footage as shots
(the same clip in every style); the footage's look as notes; "Make a story from my clips"; an uploaded track as the score with its tempo."""
import json
import math
import struct
import subprocess
import wave

import pytest

import clips
import edl
import media_sources as ms
import notes
import render_cut as rc
import shot_list
import sources as src
from test_pictures import approve_everything_before_pictures

pytest.importorskip("imageio_ffmpeg")


def two_shot_video(path):
    """2 s of red, then 2 s of blue: one cut at 2 s; with a 440 Hz tone."""
    ff = rc.ffmpeg()
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=red:size=160x90:rate=24:duration=2", "-f", "lavfi", "-i", "color=blue:size=160x90:rate=24:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-map", "2:a",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)


def click_track(path, bpm=120, seconds=8, rate=22050):
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        period = int(rate * 60 / bpm)
        frames = bytearray()
        for i in range(rate * seconds):
            v = int(20000 * math.sin(i / 3) * math.exp(-(i % period) / 300)) if i % period < 1500 else 0
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))


@pytest.fixture
def media_book(tmp_path):
    two_shot_video(tmp_path / "beach.mp4")
    e = src.store(tmp_path, src.from_file(tmp_path / "beach.mp4"), True, [tmp_path / "beach.mp4"])
    return tmp_path, e["id"]


class TestUnderstand:
    def test_shots_frames_transcript_account(self, media_book):
        d, sid = media_book
        assert [(s["start"], s["end"]) for s in ms.detect_shots(d / "sources" / sid / "beach.mp4")][0] == (0.0, pytest.approx(2.0, abs=0.1))
        out = ms.understand(d, sid, ms.fake_ask(), transcribe=lambda f: [{"start": 0.2, "end": 1.5, "text": "Look at the sea."}], say=lambda t: None)
        assert len(out["shots"]) == 2 and out["transcript"] == 1
        u = ms.understanding(d, sid)
        assert (d / u["shots"][0]["keyframe"]).is_file() and u["shots"][0]["words"] == "Look at the sea." and u["shots"][1]["words"] == ""
        doc = src.document(d, sid)
        assert "A day at the sea." in doc.text and "Look at the sea." in doc.text and src.get(d, sid)["described"]
        assert (d / "sources" / sid / "contact_sheet.jpg").is_file()

    def test_sound_only(self, tmp_path):
        subprocess.run([rc.ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=2", str(tmp_path / "talk.wav")], check=True)
        e = src.store(tmp_path, src.from_file(tmp_path / "talk.wav"), True, [tmp_path / "talk.wav"])
        out = ms.understand(tmp_path, e["id"], ms.fake_ask(), transcribe=None, say=lambda t: None)
        assert len(out["shots"]) == 1 and "faster-whisper" in src.document(tmp_path, e["id"]).text

    def test_bind(self, media_book):
        d, sid = media_book
        b = ms.bind(d, sid, 0.5, 1.5, "clip", "character", "MARA")
        assert (d / b["file"]).is_file() and b["file"].endswith(".mp4")
        assert (d / ms.bind(d, sid, 2.5, 2.6, "frame", "location", "the beach")["file"]).suffix == ".png"
        assert (d / ms.bind(d, sid, 0, 1, "audio", "music", "cue 1")["file"]).suffix == ".wav"
        assert len(ms.bindings(d)) == 3
        with pytest.raises(ms.MediaError):
            ms.bind(d, sid, 0, 1, "clip", "spaceship", "x")


class TestFootage:
    def test_real_shot_in_every_style_and_look(self, fake_root, tmp_path):
        d = fake_root / "projects" / "books" / "door"
        approve_everything_before_pictures(d)
        two_shot_video(tmp_path / "mine.mp4")
        e = src.store(d, src.from_file(tmp_path / "mine.mp4"), True, [tmp_path / "mine.mp4"])
        out = ms.use_footage(d, "S001", 2, e["id"], 0.0, 2.0)
        assert out["row"] == 2 and (d / out["clip"]).is_file()
        assert shot_list.load(d)["scenes"][0]["shots"][1]["source"] == "footage"
        assert clips.clip_file(d, "claymation", 2) == d / out["clip"] == clips.clip_file(d, "anime", 2)
        st = clips.status(d, "claymation")
        assert st["clips"][1]["clip"] == out["clip"] and st["clips"][1]["base"] == "door"
        ms.understand(d, e["id"], ms.fake_ask(), say=lambda t: None)
        look = ms.footage_look(d, e["id"], ms.fake_ask())
        assert look["lens"].startswith("35") and {n["role"] for n in notes.load(d)} == {"cinematographer", "storyboard_artist"}


class TestAutoEdit:
    def test_make_a_story_from_my_clips(self, fake_root, tmp_path):
        d = fake_root / "projects" / "books" / "clips"
        d.mkdir(parents=True)
        two_shot_video(tmp_path / "a.mp4")
        e = src.store(d, src.from_file(tmp_path / "a.mp4"), True, [tmp_path / "a.mp4"])
        with pytest.raises(ms.MediaError, match="understand"):
            ms.auto_edit(d, ms.fake_ask(), lambda t: None)
        ms.understand(d, e["id"], ms.fake_ask(), say=lambda t: None)
        out = ms.auto_edit(d, ms.fake_ask(), lambda t: None)
        assert out == {"scenes": 1, "shots": 2, "title": "The sea"}
        sl = shot_list.load(d)
        assert sl["from_footage"] and sl["scenes"][0]["shots"][0]["dialogue"] == "NARRATOR: Moment 1." and sl["scenes"][0]["shots"][0]["source"] == "footage"
        assert all((d / p).is_file() for p in ms.footage(d).values())


class TestScore:
    def test_tempo_and_score(self, fake_root, tmp_path):
        click_track(tmp_path / "click.wav", 120)
        assert abs(ms.tempo(tmp_path / "click.wav") - 120) <= 3
        d = fake_root / "projects" / "books" / "door"
        approve_everything_before_pictures(d)
        e = src.store(d, src.from_file(tmp_path / "click.wav"), True, [tmp_path / "click.wav"])
        out = ms.set_score(d, e["id"])
        assert abs(out["tempo_bpm"] - 120) <= 3 and (d / out["file"]).is_file()
        c = edl.cut(edl.load(d))
        tl = edl.timeline(c)
        assert tl["music"][0]["start"] == 0 and tl["music"][0]["end"] == pytest.approx(tl["total"])
        edl.trim(c, c["tracks"]["video"][0]["id"], 3.3)
        n = edl.snap_to_beats(c)
        beat = 60 / out["tempo_bpm"]
        assert n > 0 and all(abs(v["seconds"] / beat - round(v["seconds"] / beat)) < 1e-2 for v in c["tracks"]["video"])
        assert ("music", tl["music"][0], d / out["file"]) in rc.audio_files(d, tl)


class TestRoutes:
    def test_over_http(self, server, book, tmp_path):
        two_shot_video(tmp_path / "b.mp4")
        e = src.store(book, src.from_file(tmp_path / "b.mp4"), True, [tmp_path / "b.mp4"])
        st, j = server.api("GET", "/api/media_sources?project=demo")
        assert st == 200 and j["media"][0]["id"] == e["id"] and not j["media"][0]["understood"]
        ms.understand(book, e["id"], ms.fake_ask(), say=lambda t: None)
        st, j = server.api("POST", "/api/media_bind", {"project": "demo", "id": e["id"], "start": 0, "end": 1, "what": "clip", "kind": "character", "target": "MARA"})
        assert st == 200 and j["bindings"]
        st, j = server.api("POST", "/api/media_autoedit", {"project": "demo", "engine": "fake"})
        assert st == 200 and j["made"]["shots"] == 2
        st, j = server.api("POST", "/api/media_bind", {"project": "demo", "id": e["id"], "start": 2, "end": 1, "what": "clip", "kind": "character", "target": "x"})
        assert st == 400
        assert json.loads((book / "history" / "moments.json").read_text())                    # the old shot list was kept as a moment
