"""Scene prompt editing: save, no-op save, revert, validation (on a throw-away project folder)."""
import csv

import pytest

from studio_app import scenes
from studio_app.common import PlanError


@pytest.fixture()
def project(tmp_path, monkeypatch):
    d = tmp_path / "demo"
    d.mkdir()
    with open(d / "all_shots.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["chapter", "shot", "prompt", "negative", "width", "height", "frames", "steps", "guidance", "seed"])
        w.writeheader()
        for ch, shot in (("1", 1), ("1", 2), ("2", 1)):
            w.writerow({"chapter": ch, "shot": shot, "prompt": f"original {ch}.{shot}", "negative": "", "width": 768, "height": 512,
                        "frames": 49, "steps": 30, "guidance": 5, "seed": 1})
    monkeypatch.setattr(scenes, "pdir", lambda slug: tmp_path / slug)
    return d


def prompts(d):
    with open(d / "all_shots.csv", newline="") as f:
        return [r["prompt"] for r in csv.DictReader(f)]


def test_scene_data_lists_chapters_and_shots(project):
    data = scenes.scene_data("demo")
    assert [c["shots"] for c in data["chapters"]] == [2, 1] and data["chapter"] == "1"
    assert [s["prompt"] for s in data["shots"]] == ["original 1.1", "original 1.2"]
    assert scenes.scene_data("demo", "2")["shots"][0]["row"] == 3


def test_save_then_revert(project):
    out = scenes.prompt_save({"project": "demo", "chapter": "1", "shot": 2, "fields": {"prompt": "  a   new\nprompt "}})
    assert out == {"saved": ["prompt"], "reverted": [], "row": 2}
    assert prompts(project) == ["original 1.1", "a new prompt", "original 2.1"]
    assert scenes.scene_data("demo")["shots"][1]["edited"] == {"prompt": "original 1.2"}
    scenes.prompt_revert({"project": "demo", "chapter": "1", "shot": 2})
    assert prompts(project)[1] == "original 1.2"
    assert scenes.scene_data("demo")["chapters"][0]["edited"] == 0


def test_saving_the_original_text_counts_as_revert(project):
    scenes.prompt_save({"project": "demo", "chapter": "1", "shot": 1, "fields": {"prompt": "changed"}})
    out = scenes.prompt_save({"project": "demo", "chapter": "1", "shot": 1, "fields": {"prompt": "original 1.1"}})
    assert out["reverted"] == ["prompt"] and out["saved"] == []


@pytest.mark.parametrize("opt,msg", [
    ({"project": "ghost", "chapter": "1", "shot": 1, "fields": {"prompt": "x"}}, "pick a book"),
    ({"project": "demo", "chapter": "1", "shot": "x", "fields": {"prompt": "x"}}, "choose a shot"),
    ({"project": "demo", "chapter": "9", "shot": 1, "fields": {"prompt": "x"}}, "does not exist"),
    ({"project": "demo", "chapter": "1", "shot": 1, "fields": {}}, "nothing to save"),
    ({"project": "demo", "chapter": "1", "shot": 1, "fields": {"prompt": "  "}}, "characters"),
    ({"project": "demo", "chapter": "1", "shot": 1, "fields": {"bogus": "x"}}, "unknown field"),
    ({"project": "demo", "chapter": "1", "shot": 1, "fields": {"narration": "x"}}, "no narration"),
])
def test_validation(project, opt, msg):
    with pytest.raises(PlanError, match=msg):
        scenes.prompt_save(opt)


def test_revert_without_edits_is_an_error(project):
    with pytest.raises(PlanError, match="no saved edits"):
        scenes.prompt_revert({"project": "demo", "chapter": "1", "shot": 1})
