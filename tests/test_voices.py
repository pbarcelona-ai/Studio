"""voices.py (distinct voices, delivery), its use in the Kokoro worker, the build step and the voice cast route."""
import json
import runpy
import sys
import types

import numpy as np
import pytest

import make_audio
import voices as v

CAST_ROWS = [{"chapter": "demo-001", "shot": "1", "lines_json": json.dumps([["NARRATOR", "It began.", "bm_george"], ["Eve", "Come in.", "af_bella"], ["Adam", "No.", ""]]),
              "narration": "x", "sfx": "", "music": ""},
             {"chapter": "demo-001", "shot": "2", "lines_json": json.dumps([["Eve", "Why?"]]), "narration": "y", "sfx": "", "music": ""}]


def write_audio(d, rows=CAST_ROWS):
    from conftest import write_csv
    write_csv(d / "audio_shots.csv", rows)
    write_csv(d / "audio_chapters.csv", rows[:1])


def lines_of(d, name="audio_shots.csv"):
    import csv
    with open(d / name, newline="") as f:
        return [json.loads(r["lines_json"]) for r in csv.DictReader(f)]


class TestDirection:
    def test_resolve_and_check(self):
        assert v.resolve(None) == {} and v.resolve({"emotion": "neutral"}) == {} and v.resolve({"emotion": "sorrowful"}) == {"speed": 0.86, "pause": 0.6}
        assert v.resolve({"emotion": "urgent", "speed": 5}) == {"speed": 1.3, "pause": 0.2} and v.resolve({"speed": 0.1, "pause": 9})["pause"] == 2.0
        assert v.check_spec({"emotion": "calm", "speed": "0.9"}) == {"emotion": "calm", "speed": 0.9} and v.check_spec({}) == {}
        for bad in ("x", {"emotion": "bored"}, {"speed": 3}, {"pause": "abc"}, {"speed": 0.1}):
            with pytest.raises(ValueError):
                v.check_spec(bad)

    def test_notes_become_emotions(self):
        assert v.direction_from_note("whispering") == {"emotion": "whisper"} and v.direction_from_note("Softly") == {"emotion": "calm"} and v.direction_from_note("with a grin") == {}

    def test_apply_writes_the_fourth_item(self, book):
        write_audio(book)
        v.save_direction(book, speakers={"eve": {"emotion": "sorrowful"}, "Adam": {"speed": 1.2}}, lines={"demo-001#1#1": {"emotion": "solemn"}})
        rows = v.apply_direction(book)
        got = lines_of(book)
        assert rows == [1, 2]
        assert got[0] == [["NARRATOR", "It began.", "bm_george", {"speed": 0.84, "pause": 0.6}], ["Eve", "Come in.", "af_bella", {"speed": 0.86, "pause": 0.6}], ["Adam", "No.", "", {"speed": 1.2, "pause": 0.35}]]
        assert got[1] == [["Eve", "Why?", "", {"speed": 0.86, "pause": 0.6}]]
        assert lines_of(book, "audio_chapters.csv")[0][0][3] == {"speed": 0.84, "pause": 0.6}
        assert v.apply_direction(book) == []                                              # stable
        v.save_direction(book, speakers={})
        v.save_direction(book, lines={})
        assert v.apply_direction(book) == [1, 2] and lines_of(book)[0][1] == ["Eve", "Come in.", "af_bella"] and lines_of(book)[1] == [["Eve", "Why?"]]

    def test_save_ignores_empty_and_bad_files(self, book):
        assert v.save_direction(book, speakers={"": {"emotion": "calm"}, "X": {}}) == {"speakers": {}, "lines": {}}
        (book / v.DIRECTION_FILE).write_text("[1]")
        assert v.read_direction(book) == {"speakers": {}, "lines": {}}


class TestAutoCast:
    CHARS = [{"name": "Eve", "token": "a young woman with red hair"}, {"name": "Adam", "token": "a tall man with a beard"},
             {"name": "Seth", "token": "a man in a robe"}, {"name": "Mara", "token": "an old woman, white-haired"}, {"name": "Lord", "token": "", "voice": "elder"},
             {"name": "Child", "token": "a young boy"}, {"name": "Thing", "token": "a shape"}, {"name": "NARRATOR", "token": ""}]

    def test_every_character_gets_a_different_fitting_voice(self):
        cast = v.auto_cast(self.CHARS)
        assert "NARRATOR" not in cast and len(set(cast.values())) == len(cast) and v.NARRATOR_VOICE not in cast.values()
        assert cast["Eve"].startswith(("af_", "bf_")) and cast["Adam"].startswith(("am_", "bm_")) and cast["Mara"] == "bf_isabella" and cast["Child"] in ("am_puck", "am_liam")
        assert cast["Lord"].startswith(("am_", "bm_"))

    def test_chosen_voices_stay_and_are_not_reused(self):
        cast = v.auto_cast(self.CHARS, keep={"Eve": "am_michael", "Bogus": "xx_nothing"})
        assert cast["Eve"] == "am_michael" and "Bogus" not in cast and list(cast.values()).count("am_michael") == 1

    def test_more_characters_than_voices_reuse_voices(self):
        many = [{"name": f"P{i}", "token": "a man"} for i in range(30)]
        cast = v.auto_cast(many)
        assert len(cast) == 30 and set(cast.values()) <= set(v.MALE_POOL)

    def test_traits(self):
        assert v.guess_traits("an old man") == {"sex": "m", "old": True, "young": False} and v.guess_traits("a shape")["sex"] == ""


# ---- the real Kokoro worker source, run with stand-in kokoro / soundfile modules
def run_worker(tmp_path, monkeypatch, rows):
    from conftest import write_csv
    csv_path = tmp_path / "audio_shots.csv"
    write_csv(csv_path, rows)
    calls, written = [], {}

    class KPipeline:
        def __init__(self, lang_code):
            self.lang = lang_code

        def __call__(self, text, voice, speed):
            calls.append((self.lang, voice, round(speed, 3), text))
            yield "g", "p", np.ones(2400, dtype=np.float32)               # 0.1 s of audio at 24 kHz

    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KPipeline=KPipeline))
    monkeypatch.setitem(sys.modules, "soundfile", types.SimpleNamespace(write=lambda path, audio, sr: written.__setitem__(path, (len(audio), sr))))
    worker = tmp_path / "worker.py"
    worker.write_text(make_audio.KOKORO_WORKER)
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", [str(worker), str(csv_path), "1", str(len(rows)), str(out)])
    try:
        runpy.run_path(str(worker), run_name="__main__")
    except SystemExit as e:
        assert e.code in (None, 0)
    return calls, written, out


class TestKokoroWorker:
    def test_speed_and_pause_follow_the_direction(self, tmp_path, monkeypatch):
        rows = [{"chapter": "c", "shot": "1", "narration": "", "sfx": "", "music": "",
                 "lines_json": json.dumps([["Eve", "Slowly.", "af_bella", {"speed": 0.8, "pause": 1.0}], ["Adam", "Plain.", "am_adam"], ["NARRATOR", "Table.", "", {"speed": 0.9, "pause": 0.1}]])}]
        calls, written, out = run_worker(tmp_path, monkeypatch, rows)
        assert calls == [("a", "af_bella", 0.8, "Slowly."), ("a", "am_adam", 1.0, "Plain."), ("b", "bm_george", 0.855, "Table.")]
        (path, (n, sr)), = written.items()
        assert path.endswith("narration-0001.wav") and sr == 24000
        assert n == (2400 + 24000) + (2400 + int(24000 * 0.35)) + (2400 + int(24000 * 0.1))        # each line's audio plus its own pause

    def test_old_three_item_lines_still_work(self, tmp_path, monkeypatch):
        rows = [{"chapter": "c", "shot": "1", "narration": "", "sfx": "", "music": "", "lines_json": json.dumps([["Eve", "Hi.", "af_bella"], ["NARRATOR", "Old."]])}]
        calls, written, out = run_worker(tmp_path, monkeypatch, rows)
        assert [c[:3] for c in calls] == [("a", "af_bella", 1.0), ("b", "bm_george", 0.95)] and list(written.values())[0][0] == 2 * (2400 + int(24000 * 0.35))


class TestRoutesAndBuild:
    def test_voice_cast_route_saves_delivery_and_auto_casts(self, server, book):
        write_audio(book)
        st, out = server.api("POST", "/api/voice_cast", {"project": "demo"})
        assert st == 200 and out["emotions"][0] == "neutral" and out["speakers"][0]["direction"] == {}
        st, out = server.api("POST", "/api/voice_cast", {"project": "demo", "cast": {"Eve": "af_nova"}, "direction": {"Eve": {"emotion": "whisper", "speed": 0.9}}})
        assert st == 200 and 1 in out["changed"] and next(s for s in out["speakers"] if s["name"] == "Eve")["direction"] == {"emotion": "whisper", "speed": 0.9}
        assert lines_of(book)[0][1] == ["Eve", "Come in.", "af_nova", {"speed": 0.9, "pause": 0.5}]
        st, out = server.api("POST", "/api/voice_cast", {"project": "demo", "auto": True})
        assert st == 200 and out["auto"]["Eve"] == "af_nova"                      # the cast voice you chose stays
        assert server.api("POST", "/api/voice_cast", {"project": "demo", "direction": {"Eve": {"emotion": "bored"}}})[0] == 400
        assert server.api("POST", "/api/voice_cast", {"project": "demo", "direction": []})[0] == 400

    def test_book_build_reapplies_the_direction(self, fake_root, run_script):
        d = fake_root / "projects" / "books" / "demo"
        (d / "scripts").mkdir(parents=True)
        (d / "demo.json").write_text(json.dumps({"characters": [], "locations": []}))
        shot = {"n": 1, "prompt": "p", "negative": "", "characters": [], "location": "", "continues": False, "speaker": "Eve", "narration": "Hi there", "voice": "af_bella",
                "sfx": "wind", "music": "harp"}
        (d / "scripts" / "chapter-001.json").write_text(json.dumps({"chapter": 1, "shots": [shot]}))
        v.save_direction(d, speakers={"Eve": {"emotion": "excited"}})
        code, out = run_script("book_build.py", "demo")
        assert code is None and "voice direction applied to 1 row(s)" in out
        assert lines_of(d)[0][0][3] == {"speed": 1.15, "pause": 0.2}
