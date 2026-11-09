"""make_keyframes_csv.py (still-image prompts per shot) and make_animatic.py (stills held for their narration, real ffmpeg)."""
import csv
import json
import subprocess
import wave

import pytest

import character_tokens as ct
import make_keyframes_csv as mk


def rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def png(path, size=(64, 48), colour="red"):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(path)


@pytest.fixture()
def shots(book):
    (book / "all_shots.csv").write_text(
        "chapter,shot,prompt,characters,location,seed\n"
        "demo-001,1,a woman walks,Eve,Garden,7\ndemo-001,2,a mountain,,,8\ndemo-002,1,she waves,Eve|Adam,Cave,9\n")
    return book


class TestKeyframesCsv:
    def test_plain_rows_match_the_shots(self, shots):
        mk.main(["demo", "--width", "1600", "--height", "640"])
        r = rows(shots / "keyframes.csv")
        assert len(r) == 3 and r[0]["prompt"] == mk.LEAD + "a woman walks" and r[0]["width"] == "1600" and r[0]["seed"] == "7" and r[0]["refs"] == ""
        assert r[0]["negative"] == mk.NEGATIVE and not (shots / "keyframes.csv.tmp").exists()

    def test_look_leads_the_prompt_and_adds_negatives(self, shots, capsys):
        mk.main(["demo", "--width", "1024", "--height", "1024", "--look", "claymation"])
        r = rows(shots / "keyframes.csv")
        assert r[0]["prompt"] != mk.LEAD + "a woman walks" and "the opening frame of this shot" in r[0]["prompt"] and r[0]["negative"].endswith(mk.NEGATIVE)
        assert "look:" in capsys.readouterr().out

    def test_character_and_location_pictures_steer_the_shot(self, shots, capsys):
        for name, colour in (("Eve", "red"), ("Adam", "blue")):
            ct.save_character({"name": name, "series": "main", "visual_token": f"{name.upper()}: a person"})
            png(ct.get_reference_dir("main", name) / "ref_01.png", (900, 700), colour)
        png(shots / "location_refs" / "garden.png")
        mk.main(["demo", "--width", "1024", "--height", "1024", "--refs", "main", "--max-refs", "2"])
        r = rows(shots / "keyframes.csv")
        assert r[0]["refs"] == "ref-eve.png|ref-place-garden.png" and r[1]["refs"] == "" and r[2]["refs"] == "ref-eve.png|ref-adam.png"
        assert (shots / "keyframe_refs" / "ref-eve.png").is_file()
        from PIL import Image
        assert max(Image.open(shots / "keyframe_refs" / "ref-eve.png").size) == mk.REF_SIDE and "2 character picture(s)" in capsys.readouterr().out

    def test_a_character_without_a_picture_is_reported(self, shots, capsys):
        ct.save_character({"name": "Eve", "series": "main", "visual_token": "EVE: a woman"})
        mk.main(["demo", "--width", "1024", "--height", "1024", "--refs", "main"])
        assert "no picture yet for: Adam, Eve" in capsys.readouterr().out

    def test_stage_pictures_for_a_life_stage(self, shots):
        cont = json.loads((shots / "demo.json").read_text())
        cont["characters"][0]["stages"] = [{"label": "young", "chapters": "1", "token": "young woman"}, {"label": "old", "chapters": "2-", "token": "old woman"}]
        (shots / "demo.json").write_text(json.dumps(cont))
        ct.save_character({"name": "Eve", "series": "main", "visual_token": "EVE: a woman"})
        png(ct.get_reference_dir("main", "Eve") / "old" / "ref_01.png")
        png(ct.get_reference_dir("main", "Eve") / "ref_01.png")
        mk.main(["demo", "--width", "1024", "--height", "1024", "--refs", "main", "--look", "live_action"])
        r = rows(shots / "keyframes.csv")
        assert r[0]["refs"] == "ref-eve.png" and r[2]["refs"].split("|")[0] == "ref-eve-old.png"

    def test_refs_switched_off_removes_old_pictures(self, shots):
        (shots / "keyframe_refs").mkdir()
        (shots / "keyframe_refs" / "x.png").write_bytes(b"x")
        mk.main(["demo", "--width", "1024", "--height", "1024"])
        assert not (shots / "keyframe_refs").exists()

    def test_old_csvs_without_a_characters_column_use_token_labels(self):
        assert mk.shot_characters({"prompt": "ADAM: walks. EVE: waits"}, {"Adam": "ADAM", "Eve": "EVE", "Cain": "CAIN"}) == ["Adam", "Eve"]
        assert mk.shot_characters({"prompt": "x", "characters": ""}, {"Adam": "ADAM"}) == []
        assert mk.chapter_number({"chapter": "demo-012"}) == 12 and mk.chapter_number({"chapter": "intro"}) is None

    def test_save_small_falls_back_to_a_plain_copy(self, tmp_path):
        bad = tmp_path / "bad.png"
        bad.write_bytes(b"not a picture")
        mk.save_small(bad, tmp_path / "out.png")
        assert (tmp_path / "out.png").read_bytes() == b"not a picture"

    def test_argument_errors(self, shots):
        for argv, msg in ((["demo", "--width", "100", "--height", "640"], "256-2048"), (["demo", "--width", "512", "--height", "512", "--max-refs", "9"], "1-3"),
                          (["demo", "--width", "512", "--height", "512", "--refs", "Bad Name"], "bad series"), (["ghost", "--width", "512", "--height", "512"], "no such book"),
                          (["Bad Name", "--width", "512", "--height", "512"], "bad project name")):
            with pytest.raises(SystemExit, match=msg):
                mk.main(argv)
        (shots / "all_shots.csv").unlink()
        with pytest.raises(SystemExit, match="not found"):
            mk.main(["demo", "--width", "512", "--height", "512"])
        (shots / "all_shots.csv").write_text("chapter,shot,prompt\n")
        with pytest.raises(SystemExit, match="no rows"):
            mk.main(["demo", "--width", "512", "--height", "512"])


imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")


def wav(path, seconds):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))


class TestAnimatic:
    @pytest.fixture()
    def stills(self, book):
        for n in (1, 2, 4):
            png(book / "images" / "flux_keyframes" / f"image-{n:04d}.png", (128, 96))
        wav(book / "audio" / "kokoro" / "narration-0001.wav", 1.0)
        (book / "audio_shots.csv").write_text("chapter,shot,narration\n1,1,First line.\n1,2,\n1,3,\n1,4,Fourth line\n")
        return book

    def duration(self, path):
        import re
        err = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(path)], capture_output=True, text=True).stderr
        h, m, s = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", err).groups()
        return int(h) * 3600 + int(m) * 60 + float(s)

    def test_holds_each_still_and_writes_subtitles(self, stills, run_script):
        code, out = run_script("make_animatic.py", "--project", "demo", "--end", "4", "--fps", "8")
        f = stills / "films" / "animatic.mp4"
        assert code is None and f.is_file() and "shot 1: 1.5s (narration)" in out and "shot 2: 3.0s (estimated)" in out and "animatic: 3 shot(s)" in out
        assert 6.5 < self.duration(f) < 8.5
        srt = f.with_suffix(".srt").read_text()
        assert "First line." in srt and "Fourth line" in srt and "00:00:00,000 --> 00:00:01,000" in srt

    def test_the_book_film_shape_sets_the_picture_size(self, stills, run_script):
        (stills / "film_format.json").write_text(json.dumps({"aspect": "1:1", "chain": False}))
        assert run_script("make_animatic.py", "--project", "demo", "--end", "1", "--fps", "8", "--out", "sq.mp4")[0] is None
        assert (stills / "films" / "sq.mp4").is_file()

    def test_named_keyframe_set_and_errors(self, stills, run_script):
        assert "no keyframes for rows" in run_script("make_animatic.py", "--project", "demo", "--start", "10", "--end", "12")[0]
        assert "no keyframes yet" in run_script("make_animatic.py", "--project", "demo", "--keyframes", "other")[0]
        assert "bad keyframe" in run_script("make_animatic.py", "--project", "demo", "--keyframes", "Bad Name")[0]
        assert "--out" in run_script("make_animatic.py", "--project", "demo", "--out", "../x.mp4")[0]
        assert "no such book" in run_script("make_animatic.py", "--project", "ghost")[0]
