"""creative_direction, voice_cast and new_scene with the language model replaced by a stub."""
import csv
import json

import pytest

from conftest import write_csv
from studio_app import direction
from studio_app.common import PlanError


@pytest.fixture
def llm(monkeypatch):
    calls = []
    answer = {"value": {"reply": "Try warm light.", "direction": ""}}

    def fake(prompt, system, model=None, engine=None, validate=None):
        calls.append({"prompt": prompt, "engine": engine, "model": model})
        out = answer["value"]
        if validate:
            validate(out)
        return out
    monkeypatch.setattr(direction, "llm_json", fake)
    fake.calls, fake.answer = calls, answer
    return fake


class TestBookGuard:
    @pytest.mark.parametrize("project", ["", "Bad Name", "../x", "nothere"])
    def test_refused(self, book, project):
        with pytest.raises(PlanError):
            direction.creative_direction_get({"project": project})


class TestCreativeDirection:
    def test_empty_when_nothing_saved(self, book):
        assert direction.creative_direction_get({"project": "demo"}) == {"messages": [], "direction": ""}

    @pytest.mark.parametrize("msgs", [None, [], "hi", [{"role": "user"}], [{"role": "bot", "content": "x"}], [{"role": "assistant", "content": "x"}],
                                      [{"role": "user", "content": "  "}], [{"role": "user", "content": "x"}] * 61])
    def test_bad_conversations(self, book, llm, msgs):
        with pytest.raises(PlanError):
            direction.creative_direction({"project": "demo", "messages": msgs})
        assert not llm.calls

    def test_reply_is_saved_without_a_direction(self, book, llm):
        out = direction.creative_direction({"project": "demo", "messages": [{"role": "user", "content": "noir please"}]})
        assert out["status"] == "" and out["messages"][-1] == {"role": "assistant", "content": "Try warm light."}
        assert json.loads((book / "creative_direction.json").read_text())["messages"] == out["messages"]
        assert direction.creative_direction_get({"project": "demo"})["messages"] == out["messages"]
        assert "Eve: a woman with long hair" in llm.calls[0]["prompt"]

    def test_finished_direction_goes_into_the_continuity_book(self, book, llm):
        llm.answer["value"] = {"reply": "Done.", "direction": "Rain, neon, slow dolly."}
        out = direction.creative_direction({"project": "demo", "messages": [{"role": "user", "content": "go"}], "engine": "codex", "claude_model": "gpt-x"})
        assert "writing steps will use it" in out["status"] and out["messages"][-1]["finalized"] is True
        assert json.loads((book / "demo.json").read_text())["creative_direction"] == "Rain, neon, slow dolly."
        assert direction.creative_direction_get({"project": "demo"})["direction"] == "Rain, neon, slow dolly."
        assert llm.calls[0]["engine"] == "codex" and llm.calls[0]["model"] == "gpt-x"

    def test_no_continuity_book_is_never_invented(self, book, llm):
        (book / "demo.json").unlink()
        llm.answer["value"] = {"reply": "Done.", "direction": "Rain."}
        out = direction.creative_direction({"project": "demo", "messages": [{"role": "user", "content": "go"}]})
        assert "read the book first" in out["status"] and not (book / "demo.json").exists()

    def test_a_reply_that_fails_validation_is_rejected(self, book, llm):
        llm.answer["value"] = {"reply": "", "direction": ""}
        with pytest.raises(ValueError):
            direction.creative_direction({"project": "demo", "messages": [{"role": "user", "content": "go"}]})

    def test_unknown_engine(self, book, llm):
        with pytest.raises(PlanError, match="engine"):
            direction.creative_direction({"project": "demo", "messages": [{"role": "user", "content": "go"}], "engine": "gpt9"})


def lines(*rows):
    return json.dumps([list(r) for r in rows])


@pytest.fixture
def cast_book(book):
    write_csv(book / "audio_shots.csv", [
        {"chapter": "demo-1", "shot": 1, "narration": "n", "lines_json": lines(["NARRATOR", "It was dark.", "bm_george"])},
        {"chapter": "demo-1", "shot": 2, "narration": "n", "lines_json": lines(["Eve", "Hello", "af_bella"], ["Eve", "Bye", "af_bella"], ["NARRATOR", "x"])},
        {"chapter": "demo-1", "shot": 3, "narration": "n", "lines_json": "not json"},
    ])
    return book


class TestVoiceCast:
    def test_needs_the_csvs(self, book):
        (book / "audio_shots.csv").unlink()
        with pytest.raises(PlanError, match="build the CSVs"):
            direction.voice_cast({"project": "demo"})

    def test_lists_speakers_narrator_first(self, cast_book):
        out = direction.voice_cast({"project": "demo"})
        assert [s["name"] for s in out["speakers"]] == ["NARRATOR", "Eve"]
        narrator, eve = out["speakers"]
        assert narrator["lines"] == 2 and narrator["voice"] == "bm_george" and eve["lines"] == 2 and eve["voice"] == "af_bella"
        assert out["voices"] and out["changed"] == [] and out["moved"] == 0

    @pytest.mark.parametrize("cast", ["x", {"Eve": "not-a-voice"}])
    def test_bad_cast(self, cast_book, cast):
        with pytest.raises(PlanError):
            direction.voice_cast({"project": "demo", "cast": cast})

    def test_bad_series(self, cast_book):
        with pytest.raises(PlanError, match="bad series"):
            direction.voice_cast({"project": "demo", "series": "../x"})

    def test_cast_is_saved_and_reported(self, cast_book):
        out = direction.voice_cast({"project": "demo", "cast": {"Eve": "bf_emma", "  ": "af_bella", "Nobody": ""}})
        saved = json.loads((cast_book / direction.VOICE_CAST_FILE).read_text())
        assert saved == {"cast": {"Eve": "bf_emma"}}
        assert next(s for s in out["speakers"] if s["name"] == "Eve")["cast"] == "bf_emma"

    def test_changed_rows_move_old_narration_to_trash(self, cast_book, monkeypatch):
        wav = cast_book / "audio" / "kokoro"
        wav.mkdir(parents=True)
        for n in (1, 2, 3, 4):
            (wav / f"narration-{n:04d}.wav").write_bytes(b"w")
        moved = []
        monkeypatch.setattr(direction, "move_to_trash", lambda files, label: moved.append(files) or {"moved": len(files)})
        monkeypatch.setattr(direction, "apply_voice_cast", lambda d, c: [1, 2])
        out = direction.voice_cast({"project": "demo", "cast": {"Eve": "bf_emma"}, "move_old": True})
        assert out["changed"] == [1, 2] and out["moved"] == 2 and len(moved[0]) == 2 and all("narration-000" in f for f in moved[0])


@pytest.fixture
def scene_book(book):
    rows = [{"chapter": "demo-1", "shot": i, "prompt": p} for i, p in enumerate(["first shot prompt", "second shot prompt"], 1)]
    write_csv(book / "all_shots.csv", rows)
    write_csv(book / "audio_shots.csv", [{"chapter": "demo-1", "shot": i, "narration": f"line {i}"} for i in (1, 2)])
    return book


class TestNewScene:
    base = {"project": "demo", "chapter": "1", "description": "a cat jumps on a table"}

    @pytest.mark.parametrize("patch,msg", [({"description": ""}, "describe the new scene"), ({"description": "x" * 1501}, "describe"), ({"chapter": "x"}, "choose a chapter"),
                                           ({"position": "middle"}, "before or after"), ({"chapter": "9"}, "has no shots"), ({"series": "no-such-series"}, "unknown character series")])
    def test_refused(self, scene_book, llm, patch, msg):
        with pytest.raises(PlanError, match=msg):
            direction.new_scene({**self.base, **patch})

    def test_preview_asks_the_model_and_changes_nothing(self, scene_book, llm):
        llm.answer["value"] = {"prompt": "A close shot of a cat leaping onto a wooden table.", "narration": "The cat arrived without a sound."}
        before = (scene_book / "all_shots.csv").read_text()
        out = direction.new_scene({**self.base, "preview_only": True})
        assert out["prompt"].startswith("A close shot") and "NARRATION:" in out["preview"]
        assert (scene_book / "all_shots.csv").read_text() == before

    def test_apply_inserts_after_and_renumbers(self, scene_book):
        out = direction.new_scene({**self.base, "prompt": "inserted prompt", "narration": "inserted line"})
        assert out["scene"] == "Inserted as shot 3 of chapter 1"
        rows = list(csv.DictReader(open(scene_book / "all_shots.csv")))
        assert [r["prompt"] for r in rows] == ["first shot prompt", "second shot prompt", "inserted prompt"] and [r["shot"] for r in rows] == ["1", "2", "3"]
        audio = list(csv.DictReader(open(scene_book / "audio_shots.csv")))
        assert [r["narration"] for r in audio] == ["line 1", "line 2", "inserted line"]

    def test_apply_before(self, scene_book):
        direction.new_scene({**self.base, "position": "before", "prompt": "opening", "narration": "first"})
        rows = list(csv.DictReader(open(scene_book / "all_shots.csv")))
        assert [r["prompt"] for r in rows][0] == "opening" and [r["shot"] for r in rows] == ["1", "2", "3"]

    def test_apply_needs_a_preview(self, scene_book):
        with pytest.raises(PlanError, match="preview the scene first"):
            direction.new_scene(self.base)

    def test_refused_once_media_exists(self, scene_book):
        (scene_book / "videos").mkdir()
        (scene_book / "videos" / "shot-0001.mp4").write_bytes(b"v")
        with pytest.raises(PlanError, match="already has clips"):
            direction.new_scene({**self.base, "prompt": "p", "narration": "n"})


class TestAnimaticStep:
    def test_builds_the_command_and_caps_the_range(self, book):
        s = direction.animatic_step({"project": "demo", "start": 3, "end": 9000, "keyframes": "flux1_schnell"})
        assert s["argv"][5:11] == ["make_animatic.py", "--project", "demo", "--start", "3", "--end"] and s["argv"][11:15] == ["202", "--out", "animatic_3-202.mp4", "--keyframes"]
        assert s["argv"][:5] == ["uv", "run", "--with", "imageio-ffmpeg", "python"] and s["argv"][-2:] == ["--keyframes", "flux1_schnell"] and "rows 3-202" in s["label"]

    def test_defaults_and_refusals(self, book):
        assert direction.animatic_step({"project": "demo"})["argv"][-2:] == ["--out", "animatic_1-24.mp4"]
        for body in ({"project": "ghost"}, {"project": "Bad Name"}, {"project": "demo", "start": 5, "end": 2}, {"project": "demo", "keyframes": "Bad Name"}):
            with pytest.raises(PlanError):
                direction.animatic_step(body)


class TestUpscaleStep:
    @pytest.fixture()
    def clips(self, book):
        for sub, rows in (("ltx_video", (1, 2, 3)), ("ltx_video_x2", (1,)), ("ltx_video_lipsync", (1,))):
            (book / "videos" / sub).mkdir(parents=True)
            for n in rows:
                (book / "videos" / sub / f"shot-{n:04d}.mp4").write_bytes(b"x")
        return book

    BASE = {"project": "demo", "source": "videos/ltx_video", "start": 1, "end": 2}

    def test_kaggle(self, clips):
        s = direction.upscale_step({**self.BASE, "kaggle_user": "pat"})
        assert s["argv"] == ["scripts/run_kaggle_model.sh", "upscale_x2", "1", "2"] and s["env"]["UPSCALE_SOURCE"] == "ltx_video" and s["env"]["KAGGLE_USER"] == "pat"
        assert s["label"].endswith("on Kaggle") and s["env"]["KAGGLE_ACCELERATOR"] == "NvidiaTeslaT4"

    @pytest.fixture(autouse=True)
    def a_gpu_this_computer_could_use(self, monkeypatch):
        monkeypatch.setattr(direction, "gpu_blocker", lambda service, gpu: None)
        monkeypatch.setattr(direction, "model_blocker", lambda model, service, gpu: None)

    def test_this_computer(self, clips):
        s = direction.upscale_step({**self.BASE, "service": "computer"})
        assert s["argv"] == ["python3", "scripts/run_local_model.py", "upscale_x2", "1", "2"] and s["label"].endswith("on this computer") and "KAGGLE_USER" not in s["env"]

    def test_lipsync_needs_narration(self, clips):
        body = {**self.BASE, "model": "upscale_lipsync", "service": "computer"}
        with pytest.raises(PlanError, match="have none yet"):
            direction.upscale_step(body)
        (clips / "audio" / "kokoro").mkdir(parents=True)
        (clips / "audio" / "kokoro" / "narration-0001.wav").write_bytes(b"x")
        assert direction.upscale_step(body)["label"].startswith("Lip-sync ltx_video rows 1-2")

    @pytest.mark.parametrize("change,msg", [
        ({"project": "ghost"}, "pick a book"), ({"model": "nope"}, "choose an upscaler"), ({"source": "videos/missing"}, "choose the video folder"),
        ({"source": "videos/ltx_video_x2"}, "already upscaled"), ({"model": "upscale_lipsync", "source": "videos/ltx_video_lipsync"}, "already lip-synced"),
        ({"start": 3, "end": 1}, "end is before start"), ({"end": 5}, "no clip in ltx_video for row\\(s\\) 4, 5"), ({"service": "colab"}, "Kaggle or this computer"),
        ({"gpu": "Tpu1"}, "choose a GPU"), ({"kaggle_user": "x"}, "Kaggle username"),
    ])
    def test_refusals(self, clips, change, msg):
        with pytest.raises(PlanError, match=msg):
            direction.upscale_step({**self.BASE, "kaggle_user": "pat", **change})

    def test_many_missing_rows_are_abbreviated(self, clips):
        with pytest.raises(PlanError, match=r"\.\.\."):
            direction.upscale_step({**self.BASE, "end": 40, "kaggle_user": "pat"})
