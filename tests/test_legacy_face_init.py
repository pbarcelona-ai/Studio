"""legacy_extract.py (imported production notes), face_check.py (with a stand-in for OpenCV) and init_characters.py."""
import csv
import json
import sys
import types
from types import SimpleNamespace

import pytest

import character_tokens as ct
import legacy_extract as le
import prompts


def rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


class TestParsing:
    def test_shot_numbers(self):
        assert le.shot_numbers("Shot 3") == [3] and le.shot_numbers("Shots 2–4") == [2, 3, 4] and le.shot_numbers("nothing") == []

    def test_speakers(self):
        assert le.speaker_of("NARRATOR (V.O.):") == "NARRATOR" and le.speaker_of("") == "NARRATOR"
        assert le.speaker_of("ADAM says") == "ADAM" and le.speaker_of("THE WORD OF GOD") == "WORD"

    def test_clean(self):
        assert le.clean("a [note] *b* (v. 3) c") == "a b c"

    def test_narration_by_shot_with_quotes(self):
        body = '- **Shot 1** NARRATOR: "In the beginning."\n- **Shots 2-3** ADAM: "Eve," he said "come."\n**Other** ignored "x"\n'
        got = le.parse_narration(body)
        assert got[1] == [("NARRATOR", "In the beginning.")] and got[2] == got[3] == [("ADAM", "Eve, come.")]

    def test_narration_continuation_line(self):
        body = '**Shot 1**\nTHE WORD OF GOD (V.O.): "Let there be light."\n'
        assert le.parse_narration(body)[1] == [("WORD", "Let there be light.")]

    def test_sound_per_shot_and_chapter(self):
        per, chap = le.parse_sound("- **Shot 1** birds\n- **Shots 2-3** wind\n- **Bed** low drone\nnot a bullet\n")
        assert per == {1: "birds", 2: "wind", 3: "wind"} and chap == "low drone"

    def test_prompts_are_capped(self):
        assert len(le.music_prompt("x" * 500)) == 330 and le.sfx_prompt("", "") == le.GENERIC_SFX and le.sfx_prompt("a", "b") == "a" and le.sfx_prompt("", "b") == "b"

    def test_section(self):
        assert le.section("## A\nx\n## B\ny", "A").strip() == "x" and le.section("nothing", "A") == ""

    def test_excerpt(self):
        v = ["One two three.", "Four five six.", "Seven."]
        assert le.excerpt(v, 0) == "One two three. Four five six. Seven." and le.excerpt(v, 20) == "One two three."
        assert le.excerpt(["He said to him:", "Go now. Then more."], 30).endswith("Go now.")
        long = ["word " * 40 + ". tail goes on and on " * 3]
        assert len(le.excerpt(long, 50)) < 80


class TestExtractRows:
    @pytest.fixture()
    def notes(self, tmp_path, monkeypatch):
        b1, b2 = tmp_path / "b1", tmp_path / "b2"
        b1.mkdir(); b2.mkdir()
        (b1 / "chapter-001.md").write_text(
            '## Video-generation prompts\n```\nshot one\n```\n```\nshot two\n```\n## Narration & dialogue\n- **Shot 2** NARRATOR: "Hello."\n'
            '## Sound & music\n- **Shot 1** birds\n- **Bed** drone\n')
        monkeypatch.setattr(prompts, "BOOK1", b1)
        monkeypatch.setattr(prompts, "BOOK2", b2)
        monkeypatch.setattr(le, "adam_eve_chapters", prompts.adam_eve_chapters)
        enoch = tmp_path / "enoch_notes"
        enoch.mkdir()
        (enoch / "chapter-001.md").write_text("# T\n\nA summary line.\n## Ready-to-paste video prompt\nenoch prompt\n## Audio and editing notes\nSound bed: rain. Use a calm voice\n")
        (enoch / "chapter-002.md").write_text("no prompt here")
        monkeypatch.setattr(le, "ENOCH", enoch)
        monkeypatch.setattr(le, "chapter_files", lambda book, lo, hi: prompts.chapter_files(enoch, lo, hi))
        return tmp_path

    def test_adam_rows(self, notes):
        p, a, first = le.adam_rows()
        assert [r["prompt"] for r in p] == ["shot one", "shot two"] and p[0]["chapter"] == "adam_eve-001"
        assert json.loads(a[1]["lines_json"]) == [["NARRATOR", "Hello."]] and a[0]["sfx"] == "birds" and a[1]["sfx"] == "drone"
        assert first["adam_eve-001"]["shot"] == 2         # the chapter row borrows the first narrated shot

    def test_enoch_rows_with_and_without_verses(self, notes, capsys):
        proj = notes / "proj"
        proj.mkdir()
        p, a = le.enoch_rows(proj, 300)
        assert "enoch_verses.json missing" in capsys.readouterr().out and len(p) == 1 and "A summary line." in a[0]["narration"] and a[0]["sfx"] == "rain"
        (proj / "enoch_verses.json").write_text(json.dumps({"1": {"verses": ["First verse.", "Second verse."]}}))
        assert le.enoch_rows(proj, 0)[1][0]["narration"] == "First Enoch, chapter 1. First verse. Second verse."

    def test_command_writes_four_csvs(self, notes, fake_root, monkeypatch, run_script):
        books = fake_root / "projects" / "books"
        (books / "adam_eve").mkdir()
        monkeypatch.setattr(prompts, "BOOKS", books)
        code, out = run_script("legacy_extract.py", "adam_eve")
        assert code is None and "adam_eve: 2 shots, 1 chapters; 1 rows with narration" in out
        assert [r["prompt"] for r in rows(books / "adam_eve" / "all_shots.csv")] == ["shot one", "shot two"]
        assert len(rows(books / "adam_eve" / "audio_chapters.csv")) == 1 and rows(books / "adam_eve" / "audio_chapters.csv")[0]["narration"] == "Hello."


class TestFaceCheck:
    @pytest.fixture()
    def cv(self, monkeypatch):
        state = SimpleNamespace(score=0.9, faces=1, calls=[])
        img = SimpleNamespace(shape=(200, 300, 3))

        class Detector:
            def setInputSize(self, size):
                pass

            def detect(self, im):
                state.calls.append(1)
                n = 1 if len(state.calls) == 1 else state.faces          # the first look is at the reference picture
                return (1, [[0, 0, 80, 80, 0]] * n if n else None)

        class Recogniser:
            def alignCrop(self, im, f):
                return im

            def feature(self, crop):
                return "feat"

            def match(self, a, b, mode):
                return state.score
        cv2 = types.ModuleType("cv2")
        cv2.FaceDetectorYN = SimpleNamespace(create=lambda *a: Detector())
        cv2.FaceRecognizerSF = SimpleNamespace(create=lambda *a: Recogniser())
        cv2.FaceRecognizerSF_FR_COSINE = 0
        cv2.IMREAD_COLOR = 1
        cv2.imdecode = lambda data, flag: img
        cv2.resize = lambda im, size: SimpleNamespace(shape=(size[1], size[0], 3))
        cv2.CAP_PROP_FRAME_COUNT, cv2.CAP_PROP_POS_FRAMES = 7, 1

        class Cap:
            def __init__(self, path):
                pass

            def get(self, p):
                return 10

            def set(self, p, v):
                pass

            def read(self):
                return True, img

            def release(self):
                pass
        cv2.VideoCapture = Cap
        np = types.ModuleType("numpy")
        np.fromfile = lambda path, dtype=None: b""
        np.uint8 = "uint8"
        monkeypatch.setitem(sys.modules, "cv2", cv2)
        monkeypatch.setitem(sys.modules, "numpy", np)
        import face_check as fc
        monkeypatch.setattr(fc, "model_file", lambda url: "model")
        return state

    @pytest.fixture()
    def keyed(self, book, fake_root):
        (book / "all_shots.csv").write_text("chapter,shot,prompt,characters\ndemo-001,1,p,Eve\ndemo-001,2,p,Eve\ndemo-001,3,p,\n")
        kf = book / "images" / "flux_keyframes"
        kf.mkdir(parents=True)
        for n in (1, 2, 3):
            (kf / f"image-{n:04d}.png").write_bytes(b"x")
        ref = ct.get_reference_dir("main", "Eve")
        ref.mkdir(parents=True, exist_ok=True)
        (ref / "ref_01.png").write_bytes(b"x")
        return book

    def run(self, *args):
        import face_check as fc
        fc.main(["demo", "--series", "main", *args])

    def test_matching_faces_are_ok(self, cv, keyed, capsys):
        self.run()
        out = json.loads((keyed / "face_check.json").read_text())
        assert out["rows"]["1"]["status"] == "ok" and out["rows"]["3"]["status"] == "skipped" and out["source"] == "images/flux_keyframes"

    def test_a_different_face_is_flagged(self, cv, keyed, capsys):
        cv.score = 0.1
        self.run()
        assert json.loads((keyed / "face_check.json").read_text())["rows"]["1"]["status"] == "different" and "look at these shots" in capsys.readouterr().out

    def test_no_face(self, cv, keyed):
        cv.faces = 0
        self.run()
        assert json.loads((keyed / "face_check.json").read_text())["rows"]["1"]["status"] == "no_face"

    def test_clips_use_first_and_last_frame(self, cv, keyed):
        v = keyed / "videos" / "ltx_video"
        v.mkdir(parents=True)
        (v / "shot-0001.mp4").write_bytes(b"x")
        self.run("--source", "videos/ltx_video")
        assert list(json.loads((keyed / "face_check.json").read_text())["rows"]) == ["1"]

    def test_argument_errors(self, keyed):
        for args, msg in ((["--source", "../x"], "--source must"), (["--source", "images/nothing"], "nothing to check")):
            with pytest.raises(SystemExit, match=msg):
                self.run(*args)
        import face_check as fc
        with pytest.raises(SystemExit, match="bad series"):
            fc.main(["demo", "--series", "Bad Name"])
        with pytest.raises(SystemExit, match="no such book"):
            fc.main(["ghost", "--series", "main"])

    def test_model_file_downloads_once(self, tmp_path, monkeypatch):
        import face_check as fc
        monkeypatch.undo()
        monkeypatch.setattr(fc.Path, "home", classmethod(lambda cls: tmp_path))
        got = []
        monkeypatch.setattr(fc.urllib.request, "urlretrieve", lambda url, dest: (got.append(url), open(dest, "wb").write(b"m")))
        p = fc.model_file("https://x/y/model.onnx")
        assert p.read_bytes() == b"m" and fc.model_file("https://x/y/model.onnx") == p and len(got) == 1


class TestInitCharacters:
    def test_writes_every_example_token_and_reference_folder(self, fake_root, run_script):
        code, out = run_script("init_characters.py")
        assert code is None and "Done! Character tokens initialized." in out
        d = fake_root / "projects" / "characters" / "main"
        assert (d / "adam.json").exists() and json.loads((d / "eve.json").read_text())["voice"] == "af_bella"
        assert (d / "references" / "adam").is_dir()
