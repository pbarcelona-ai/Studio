"""Takes: retake keeps the old clip, picks swap versions, bad requests are refused (on a throw-away project)."""
import csv

import pytest

from studio_app import takes
from studio_app.common import PlanError


@pytest.fixture()
def project(tmp_path, monkeypatch):
    d = tmp_path / "demo"
    (d / "videos" / "ltx_video").mkdir(parents=True)
    with open(d / "all_shots.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["chapter", "shot", "prompt"])
        w.writeheader()
        w.writerows({"chapter": 1, "shot": i, "prompt": f"p{i}"} for i in (1, 2, 3))
    (d / "videos" / "ltx_video" / "shot-0002.mp4").write_bytes(b"first")
    monkeypatch.setattr(takes, "pdir", lambda slug: tmp_path / slug)
    return d


BODY = {"project": "demo", "kind": "clip", "model": "ltx_video", "n": 2}


def seeds(d):
    with open(d / "all_shots.csv", newline="") as f:
        return [r["seed"] for r in csv.DictReader(f)]


def test_retake_saves_the_clip_and_changes_the_seed(project):
    out = takes.retake(BODY)
    folder = project / "videos" / "ltx_video"
    assert out["saved_as"] == 1 and out["seed"] == 2 + 1000
    assert not (folder / "shot-0002.mp4").exists() and (folder / "takes" / "shot-0002-t1.mp4").read_bytes() == b"first"
    assert seeds(project) == ["", "1002", ""]
    (folder / "shot-0002.mp4").write_bytes(b"second")                 # the rerun produced a new clip
    assert takes.retake(BODY)["saved_as"] == 2
    assert takes.take_files(folder, "shot", 2, ".mp4", project) == ["videos/ltx_video/takes/shot-0002-t1.mp4", "videos/ltx_video/takes/shot-0002-t2.mp4"]


def test_pick_swaps_versions_without_losing_any(project):
    takes.retake(BODY)
    folder = project / "videos" / "ltx_video"
    (folder / "shot-0002.mp4").write_bytes(b"second")
    assert takes.pick_take({**BODY, "take": 1}) == {"current_from_take": 1}
    assert (folder / "shot-0002.mp4").read_bytes() == b"first"
    assert (folder / "takes" / "shot-0002-t2.mp4").read_bytes() == b"second"


@pytest.mark.parametrize("patch,msg", [
    ({"project": "nope"}, "pick a book"), ({"project": "../x"}, "pick a book"), ({"kind": "audio"}, "clip or keyframe"),
    ({"model": "../../etc"}, "bad model"), ({"n": 0}, "bad shot"), ({"n": True}, "bad shot"), ({"n": "2"}, "bad shot"),
    ({"model": "wan"}, "no clips from wan"), ({"n": 3}, "nothing to retake"),
])
def test_requests_are_validated(project, patch, msg):
    with pytest.raises(PlanError, match=msg):
        takes.retake({**BODY, **patch})


def test_pick_validation(project):
    with pytest.raises(PlanError, match="bad take"):
        takes.pick_take({**BODY, "take": 0})
    with pytest.raises(PlanError, match="does not exist"):
        takes.pick_take({**BODY, "take": 5})


def test_seed_outside_csv_is_refused(project):
    with pytest.raises(PlanError, match="not in all_shots.csv"):
        takes.set_shot_seed(project, 9, 1)
