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
