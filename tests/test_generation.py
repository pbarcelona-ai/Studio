"""'Make my film' option filling, missing-file runs, people detection and the local-audio step."""
import pytest

from studio_app import generation
from studio_app.common import PlanError


def test_rows_missing_groups_neighbours(tmp_path):
    for n in (2, 5):
        (tmp_path / f"shot-{n:04d}.mp4").write_bytes(b"x")
    pattern = str(tmp_path / "shot-{:04d}.mp4")
    assert generation.rows_missing(1, 6, pattern) == [(1, 1), (3, 4), (6, 6)]
    assert generation.rows_missing(2, 2, pattern) == []


def test_a_saved_take_counts_as_present(tmp_path):
    (tmp_path / "takes").mkdir()
    (tmp_path / "takes" / "shot-0003-t1.mp4").write_bytes(b"x")
    assert generation.rows_missing(3, 3, str(tmp_path / "shot-{:04d}.mp4")) == []


def test_any_pattern_satisfies_a_row(tmp_path):
    (tmp_path / "b-0001.png").write_bytes(b"x")
    assert generation.rows_missing(1, 1, str(tmp_path / "a-{:04d}.png"), str(tmp_path / "b-{:04d}.png")) == []


@pytest.mark.parametrize("row,expected", [
    ({"characters": "Eve"}, True), ({"prompt": "a woman walks"}, True), ({"prompt": "a mountain at dawn"}, False),
    ({"prompt": "the sheep graze"}, False), ({}, False), ({"characters": "  ", "prompt": "She runs"}, True)])
def test_is_people_shot(row, expected):
    assert generation.is_people_shot(row) is expected


class TestFilmOptions:
    def test_needs_a_valid_book_name(self):
        for bad in ("", "../x", None):
            with pytest.raises(PlanError):
                generation.film_options({"project": bad})

    def test_fills_every_step_and_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(generation.layout, "find_dir", lambda slug: None)
        opt = generation.film_options({"project": "demo"})
        assert opt["steps"]["ingest"] and opt["steps"]["continuity"] and opt["steps"]["mix"]
        assert opt["aspect"] == "16:9" and opt["sync"] == "gentle" and opt["music_bed"] and not opt["force_write"]

    def test_skips_work_that_is_done(self, tmp_path, monkeypatch):
        (tmp_path / "chapters.json").write_text("{}")
        monkeypatch.setattr(generation.layout, "find_dir", lambda slug: tmp_path)
        monkeypatch.setattr(generation, "continuity_file", lambda d: tmp_path / "demo.json")
        (tmp_path / "demo.json").write_text("{}")
        opt = generation.film_options({"project": "demo", "aspect": "9:16", "sync": "tight"})
        assert not opt["steps"]["ingest"] and not opt["steps"]["continuity"]
        assert opt["aspect"] == "9:16" and opt["sync"] == "tight"


def test_local_audio_step_is_an_argv_list():
    for kind in ("kokoro", "music"):
        step = generation.local_audio_step("demo", kind)
        assert step["argv"][:2] == ["uv", "run"] and step["argv"][-3:] == ["local_audio.py", "demo", kind]
        assert all(isinstance(a, str) for a in step["argv"])
    assert "narration" in generation.local_audio_step("demo", "kokoro")["label"]
