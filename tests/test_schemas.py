import pytest

import schemas
from studio_app import projects


def test_global_params_are_cleaned_and_stamped():
    assert schemas.clean_global_params({"positives": "a", "negatives": 5, "junk": 1}) == {"schema_version": 1, "positives": "a", "negatives": ""}
    assert schemas.clean_global_params("nonsense") == {"schema_version": 1, "positives": "", "negatives": ""}


def test_newer_files_are_refused():
    with pytest.raises(ValueError, match="newer"):
        schemas.upgrade("global_params", {"schema_version": 99})


def test_migrations_run_in_order(monkeypatch):
    monkeypatch.setattr(schemas, "SCHEMA_VERSION", 2)
    monkeypatch.setitem(schemas.MIGRATIONS, ("demo", 0), lambda d: {**d, "a": 1})
    monkeypatch.setitem(schemas.MIGRATIONS, ("demo", 1), lambda d: {**d, "b": d["a"] + 1})
    assert schemas.upgrade("demo", {}) == {"a": 1, "b": 2, "schema_version": 2}


def test_stamp_does_not_mutate():
    src = {"x": 1}
    assert schemas.stamp(src) == {"schema_version": 1, "x": 1} and src == {"x": 1}


GOOD = {"title": "T", "setting": "s", "characters": [{"name": "Eve", "token": "tok", "stages": [{"label": "young", "chapters": "1-12", "token": "x"}]}],
        "locations": [{"name": "Garden", "token": "g"}]}


def test_continuity_validation():
    assert schemas.validate_continuity(GOOD) == []
    assert schemas.validate_continuity([]) == ["the continuity book must be a JSON object"]
    bad = {"title": 5, "characters": [{"name": "", "token": "t"}, "x", {"name": "A", "token": "t", "stages": [{"label": "l", "chapters": "x", "token": "t"}]}],
           "locations": [{"name": "only"}]}
    msgs = schemas.validate_continuity(bad)
    assert len(msgs) == 5 and any("stages[0]" in m for m in msgs) and any("locations[0]" in m for m in msgs)


def test_csv_columns():
    assert schemas.missing_columns(["chapter", "shot", "prompt"], ["chapter", "prompt", "seed"]) == ["seed"]
    assert schemas.missing_columns(None, ["a"]) == ["a"]
    assert "frames" in schemas.VIDEO_COLS and "frames" not in schemas.IMAGE_COLS


def test_global_params_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "pdir", lambda slug: tmp_path / slug)
    assert projects.load_global_params("demo") == {"schema_version": 1, "positives": "", "negatives": ""}
    projects.save_global_params("demo", "sharp", "blurry")
    assert projects.load_global_params("demo")["positives"] == "sharp"
    (tmp_path / "demo" / "global_params.json").write_text("{broken")
    assert projects.load_global_params("demo")["negatives"] == ""
