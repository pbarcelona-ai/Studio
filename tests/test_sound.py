"""M9: the Voice Director's cast and line direction, the Sound Designer's effects, the Composer's cues, the audio CSVs (shared by every
style), the sound gate, and the audiobook (M4B with a chapter per scene and MP3s) built with ffmpeg."""
import csv
import json
import wave

import pytest

import gates
import shot_list as sl
import sound_design as sd
from test_pictures import approve_everything_before_pictures


@pytest.fixture
def planned(fake_root):
    d = fake_root / "projects" / "books" / "door"
    approve_everything_before_pictures(d)
    sl.edit_shot(d, "S001", 2, {"dialogue": "MARA: Is anyone there? / Answer me."})
    gates.approve(d, "shotlist", sl.gate_data(sl.load(d)))
    return d


def tone(path, seconds=0.5, rate=24000):
    import math
    import struct
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 20))) for i in range(int(rate * seconds))))


class TestPlan:
    def test_needs_the_approved_shot_list(self, fake_root):
        d = fake_root / "projects" / "books" / "x1"
        d.mkdir(parents=True)
        with pytest.raises(sd.SoundError, match="shot list"):
            sd.write_plan(d, sd.fake_ask(d))

    def test_plan_and_csvs(self, planned):
        roles, said = [], []
        fake = sd.fake_ask(planned)
        plan = sd.write_plan(planned, lambda p, r, s, v: (roles.append(r), fake(p, r, s, v))[1], said.append)
        assert roles[0] == "voice_director" and roles[-1] == "composer" and roles.count("sound_designer") == 3
        assert plan["lines"][:2] == [{"id": "S001#2#1", "scene": "S001", "shot": 2, "character": "MARA", "text": "Is anyone there?"},
                                     {"id": "S001#2#2", "scene": "S001", "shot": 2, "character": "MARA", "text": "Answer me."}]
        rows = list(csv.DictReader(open(planned / "audio_shots.csv", encoding="utf-8")))
        assert len(rows) == 9 and rows[1]["chapter"] == "S001" and rows[1]["scene"] == "S001"
        lines = json.loads(rows[1]["lines_json"])
        assert lines[0][:3] == ["MARA", "Is anyone there?", plan["cast"]["MARA"]["voice"]] and set(lines[0][3]) == {"speed", "pause"}
        assert rows[0]["sfx"] == "wind against glass, distant surf" and rows[0]["music"].startswith("slow solo cello")
        assert len(list(csv.DictReader(open(planned / "audio_scenes.csv", encoding="utf-8")))) == 3
        book = list(csv.DictReader(open(planned / "audiobook.csv", encoding="utf-8")))
        first = json.loads(book[0]["lines_json"])
        assert len(book) == 3 and first[0][0] == "NARRATOR" and first[0][2] == "bm_george" and any(x[0] == "MARA" for x in first)
        assert said[-1].startswith("Done:")

    @pytest.mark.parametrize("bad", [{"cast": {}, "narrator": {"voice": "bm_george"}}, {"cast": {"MARA": {"voice": "robot"}}, "narrator": {"voice": "bm_george"}},
                                     {"cast": {"MARA": {"voice": "af_bella", "emotion": "bored"}}, "narrator": {"voice": "bm_george"}}])
    def test_bad_casts(self, bad):
        with pytest.raises(ValueError):
            sd.cast_checker(["MARA"])(bad)

    def test_bad_cues_and_effects(self):
        with pytest.raises(ValueError, match="tempo"):
            sd.check_music({"cues": [{"first_scene": "S1", "last_scene": "S1", "mood": "m", "instrumentation": "i", "prompt": "p", "tempo_bpm": 900}]})
        with pytest.raises(ValueError):
            sd.check_sound({"shots": [{"n": "one", "sfx": "x"}]})

    def test_cue_spans(self):
        plan = {"cues": [{"first_scene": "S001", "last_scene": "S002", "prompt": "a"}, {"first_scene": "S003", "last_scene": "S003", "prompt": "b"}]}
        order = ["S001", "S002", "S003"]
        assert [sd.cue_for(plan, s, order)["prompt"] for s in order] == ["a", "a", "b"]


class TestAudiobook:
    def test_m4b_with_chapters_and_mp3s(self, planned):
        pytest.importorskip("imageio_ffmpeg")
        sd.write_plan(planned, sd.fake_ask(planned), lambda t: None)
        with pytest.raises(sd.SoundError, match="not rendered"):
            sd.make_audiobook(planned)
        for i in (1, 2, 3):
            tone(planned / "audio" / "kokoro_audiobook" / f"narration-{i:04d}.wav", 0.4 + i * 0.1)
        from test_pictures import png
        png(planned / "cover.png")
        out = sd.make_audiobook(planned, planned / "cover.png")
        assert out["chapters"] == 3 and 1.7 <= out["seconds"] <= 1.9
        m4b = planned / "exports" / "audiobook.m4b"
        assert m4b.is_file() and sorted(p.name for p in (planned / "exports" / "audiobook").iterdir()) == ["01-S001.mp3", "02-S002.mp3", "03-S003.mp3"]
        import subprocess
        probe = subprocess.run([sd.ffmpeg(), "-i", str(m4b)], capture_output=True, text=True).stderr
        assert probe.count("Chapter #") == 3 and "Chapter 2 (S002)" in probe


class TestRoutes:
    def test_over_http(self, server, book):
        approve_everything_before_pictures(book)
        st, j = server.api("GET", "/api/sound?project=demo")
        assert st == 200 and j["plan"] is None and "af_bella" in j["voices"]
        sd.write_plan(book, sd.fake_ask(book), lambda t: None)
        st, j = server.api("POST", "/api/sound_cast", {"project": "demo", "name": "MARA", "voice": "bf_emma"})
        assert st == 200 and j["plan"]["cast"]["MARA"]["voice"] == "bf_emma"
        assert json.loads(next(csv.DictReader(open(book / "audiobook.csv", encoding="utf-8")))["lines_json"])            # the CSVs follow the change
        st, j = server.api("POST", "/api/sound_cast", {"project": "demo", "name": "MARA", "voice": "nope"})
        assert st == 400
        st, j = server.api("POST", "/api/audiobook_make", {"project": "demo"})
        assert st == 400 and "approve" in j["error"]
        st, j = server.api("POST", "/api/sound_approve", {"project": "demo"})
        assert j["gate"]["approved"] and j["audiobook"]["chapters"] == 3 and j["audiobook"]["rendered"] == 0
