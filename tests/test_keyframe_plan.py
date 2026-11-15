"""Making keyframes plans runs only for the shots that have no picture yet (a re-rolled shot has none)."""
import pytest

from studio_app import generation, planner
from studio_app.common import PlanError

KAGGLE = {"service": "kaggle", "gpu": "NvidiaTeslaT4", "kaggle_user": "pat"}


def plan(**kw):
    return planner.build_plan({"project": "demo", **KAGGLE, "keyframe_model": "flux2_klein_4b", "movies": {"mode": "all"}, **kw})


def _pics(book, rows):
    kf = book / "images" / "flux2_klein_4b_keyframes"
    kf.mkdir(parents=True, exist_ok=True)
    for n in rows:
        (kf / f"image-{n:04d}.png").write_bytes(b"p")
    return kf


def test_only_the_missing_rows_are_made(book):
    _pics(book, [1, 2])
    labels = [s["label"] for s in plan(steps={"keyframes": True})]
    assert [x for x in labels if "keyframes flux2" in x] == ["Movie 1 keyframes flux2_klein_4b: rows 3-4"]


def test_gaps_become_separate_runs_and_a_rerolled_shot_is_made_again(book):
    kf = _pics(book, [1, 3])
    (kf / "takes").mkdir()
    (kf / "takes" / "image-0002-t1.png").write_bytes(b"old")            # shot 2 was re-rolled: its old picture is a take
    labels = [s["label"] for s in plan(steps={"keyframes": True})]
    assert [x.split(": ")[1] for x in labels if "keyframes flux2" in x] == ["rows 2-2", "rows 4-4"]


def test_nothing_to_make_says_so(book):
    _pics(book, [1, 2, 3, 4])
    with pytest.raises(PlanError, match="Every shot has a picture"):
        plan(steps={"keyframes": True})
    steps = plan(steps={"keyframes": True, "video": True}, video_models=["ltx_video_i2v"])     # video still goes ahead from the pictures
    assert any("video ltx_video_i2v" in s["label"] for s in steps) and not any("keyframes flux2" in s["label"] for s in steps)


def test_pictures_missing():
    from pathlib import Path
    assert generation.pictures_missing(Path("/nonexistent"), 3, 6) == [(3, 6)]
