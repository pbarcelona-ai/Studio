"""Ratings, compare view, showcase and prompt library, on regression folders made in a throw-away root."""
import json

import pytest

from conftest import write_csv
from studio_app import gallery
from studio_app.common import PlanError

PROMPT = "a red fox in snow"


def make_result(root, lane, sub, model, name, size):
    f = root / "books" / lane / sub / model / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x" * size)
    return f


@pytest.fixture
def lanes(fake_root):
    from studio_app import gallery as g
    d = g.pdir("regtest_a")
    d.mkdir(parents=True, exist_ok=True)
    write_csv(d / "all_images.csv", [{"prompt": PROMPT}, {"prompt": "  second   prompt "}])
    write_csv(d / "all_shots.csv", [{"prompt": PROMPT}])
    for sub, model, name, size in (("images", "flux", "image-001.png", 200_000), ("images", "sdxl", "image-001.png", 300_000), ("videos", "ltx", "shot-001.mp4", 100_000)):
        f = d / sub / model / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x" * size)
    return d


class TestRatings:
    @pytest.mark.parametrize("key", ["bad", "regtest_a/../x", "regtest_z/a.png", ""])
    def test_bad_keys(self, fake_root, key):
        with pytest.raises(PlanError, match="bad result name"):
            gallery.save_rating(key, 3, False)

    def test_bad_stars(self, fake_root):
        with pytest.raises(PlanError, match="stars"):
            gallery.save_rating("regtest_a/images/m/image-001.png", "lots", False)

    def test_stars_are_clamped_and_saved(self, fake_root):
        assert gallery.save_rating("regtest_a/images/m/image-001.png", 9, 1) == {"stars": 5, "keep": True}
        assert gallery.save_rating("regtest_b/videos/m/shot-001.mp4", -3, 0) == {"stars": 0, "keep": False}
        assert set(gallery.load_ratings()) == {"regtest_a/images/m/image-001.png", "regtest_b/videos/m/shot-001.mp4"}

    def test_no_file_means_no_ratings(self, fake_root):
        assert gallery.load_ratings() == {}


def test_regression_minutes_only_counts_passes(fake_root):
    (gallery.ROOT / "regression_kaggle_report.json").write_text(json.dumps({
        "flux": {"result": "PASS", "minutes": 4, "prompt": "a  b"}, "ltx": {"result": "FAIL", "minutes": 9}, "junk": 5}))
    assert gallery.regression_minutes() == {("flux", "a b"): 4}


class TestCompare:
    def test_groups_by_prompt_with_newest_per_model(self, lanes):
        data = gallery.compare_data()["prompts"]
        assert len(data) == 1 and data[0]["text"] == PROMPT
        assert [(i["kind"], i["model"]) for i in data[0]["items"]] == [("image", "flux"), ("image", "sdxl"), ("video", "ltx")]

    def test_ratings_and_minutes_are_attached(self, lanes):
        gallery.save_rating("regtest_a/images/flux/image-001.png", 4, True)
        (gallery.ROOT / "regression_kaggle_report.json").write_text(json.dumps({"flux": {"result": "PASS", "minutes": 7, "prompt": PROMPT}}))
        item = next(i for i in gallery.compare_data()["prompts"][0]["items"] if i["model"] == "flux")
        assert item["stars"] == 4 and item["keep"] is True and item["minutes"] == 7

    def test_empty_without_lanes(self, fake_root):
        assert gallery.compare_data() == {"prompts": []}


class TestShowcase:
    def test_nothing_unrated_is_shown(self, lanes):
        assert gallery.showcase() == {"hero": None, "art": []}

    def test_rated_results_are_picked(self, lanes):
        gallery.save_rating("regtest_a/images/sdxl/image-001.png", 5, False)
        gallery.save_rating("regtest_a/videos/ltx/shot-001.mp4", 4, False)
        gallery.save_rating("regtest_a/images/flux/image-001.png", 2, False)      # below 4 stars: never used
        s = gallery.showcase()
        assert s["hero"] == "regtest_a/videos/ltx/shot-001.mp4" and s["art"] == ["regtest_a/images/sdxl/image-001.png"]

    def test_the_built_in_prompt_needs_no_rating(self, fake_root):
        d = gallery.pdir("regtest_a")
        write_csv(d / "all_images.csv", [{"prompt": gallery.ZOMBIE_PROMPT}])
        f = d / "images" / "flux" / "image-001.png"
        f.parent.mkdir(parents=True)
        f.write_bytes(b"x" * 200_000)
        assert gallery.showcase()["art"] == ["regtest_a/images/flux/image-001.png"]


def test_library_attaches_a_sample_when_the_prompt_was_run(lanes, monkeypatch):
    import templates
    monkeypatch.setattr(templates, "TEMPLATES", [{"name": "fox", "prompt": PROMPT, "kind": "image"}, {"name": "other", "prompt": "never run", "kind": "image"}])
    out = gallery.library()["templates"]
    fox = next(t for t in out if t["name"] == "fox")
    assert fox["sample"]["kind"] == "image" and fox["sample"]["file"].startswith("regtest_a/images/")
    assert next(t for t in out if t["name"] == "other")["sample"] is None
