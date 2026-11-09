"""prompt_suggest: what is sent to the model (book text, neighbours, characters) and how replies are validated."""
import json

import pytest

from conftest import write_csv
from studio_app import scenes
from studio_app.common import PlanError


@pytest.fixture
def scene_book(book):
    write_csv(book / "all_shots.csv", [{"chapter": "demo-1", "shot": i, "prompt": f"prompt {i}"} for i in (1, 2, 3)])
    write_csv(book / "audio_shots.csv", [{"chapter": "demo-1", "shot": i, "narration": f"spoken {i}", "sfx": "wind", "music": "calm"} for i in (1, 2, 3)])
    (book / "scripts").mkdir()
    (book / "scripts" / "chapter-001.json").write_text(json.dumps({"shots": [{"slice": "SLICE ONE"}, {"slice": "SLICE TWO"}, {"slice": "SLICE THREE"}]}))
    return book


@pytest.fixture
def llm(monkeypatch):
    seen = {"value": {"suggestions": ["a new idea for the shot", "another idea for the shot", "a third idea for the shot"]}}

    def fake(prompt, system, model=None, engine=None, validate=None):
        seen["prompt"], seen["engine"] = prompt, engine
        validate(seen["value"])
        return seen["value"]
    monkeypatch.setattr(scenes, "llm_json", fake)
    return seen


BASE = {"project": "demo", "chapter": "demo-1", "shot": 2, "hint": "make it rain"}


def test_context_reaches_the_model(scene_book, llm):
    out = scenes.prompt_suggest(BASE)
    assert len(out) == 3
    p = llm["prompt"]
    assert "SLICE TWO" in p and "make it rain" in p and "prompt 1" in p and "prompt 3" in p and "spoken 2" in p
    assert "Eve: a woman with long hair" in p                      # characters only matter for the picture prompt


def test_other_fields_use_their_own_text(scene_book, llm):
    llm["value"] = {"suggestions": ["soft rain and distant thunder", "heavy rain on a tin roof", "rain on leaves, a dog barks"]}
    scenes.prompt_suggest({**BASE, "field": "sfx"})
    assert "wind" in llm["prompt"] and "Eve:" not in llm["prompt"]


def test_engine_is_passed_through(scene_book, llm):
    scenes.prompt_suggest({**BASE, "engine": "codex"})
    assert llm["engine"] == "codex"


@pytest.mark.parametrize("patch,msg", [({"hint": ""}, "write your idea"), ({"hint": "x" * 1501}, "write your idea"), ({"shot": "x"}, "choose a shot"),
                                       ({"field": "bogus"}, "unknown field"), ({"shot": 9}, "does not exist")])
def test_refused(scene_book, llm, patch, msg):
    with pytest.raises(PlanError, match=msg):
        scenes.prompt_suggest({**BASE, **patch})


@pytest.mark.parametrize("bad", [{"suggestions": ["only one long enough text"]}, {"suggestions": ["short"] * 3}, {"suggestions": "text"}, {}])
def test_bad_replies_are_rejected(scene_book, llm, bad):
    llm["value"] = bad
    with pytest.raises(ValueError):
        scenes.prompt_suggest(BASE)


def test_count_is_respected(scene_book, llm):
    llm["value"] = {"suggestions": ["the first long suggestion", "the second long suggestion"]}
    assert len(scenes.prompt_suggest({**BASE, "count": 2})) == 2
