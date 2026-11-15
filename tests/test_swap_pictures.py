"""Drag one storyboard picture onto another: the two shots trade pictures (studio_app/old_pictures.swap_pictures, /api/swap_pictures)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import review
from studio_app.common import PlanError
from studio_app.old_pictures import swap_pictures


def _pics(book, shots=(1, 2)):
    kf = book / "images" / "flux_keyframes"
    kf.mkdir(parents=True)
    for n in shots:
        (kf / f"image-{n:04d}.png").write_bytes(b"pic%d" % n)
    return kf


def test_two_shots_trade_pictures_and_are_asked_again(book):
    kf = _pics(book)
    (kf / "takes").mkdir()
    (kf / "takes" / "image-0001-t1.png").write_bytes(b"take")
    review.set_status(book, ["1#1", "1#2"], "approved")
    (book / "face_check.json").write_text(json.dumps({"rows": {"1": {"status": "same"}, "3": {"status": "same"}}}))
    r = swap_pictures({"project": "demo", "a": 1, "b": 2, "model": "flux"})
    assert r == {"a": 1, "b": 2, "a_has": True, "b_has": True}
    assert (kf / "image-0001.png").read_bytes() == b"pic2" and (kf / "image-0002.png").read_bytes() == b"pic1"
    assert (kf / "takes" / "image-0001-t1.png").read_bytes() == b"take" and not list(kf.glob(".swap-*"))   # takes stay with their shot
    assert not any(k in review.load(book) for k in ("1#1", "1#2"))                     # back to "not reviewed"
    assert json.loads((book / "face_check.json").read_text())["rows"] == {"3": {"status": "same"}}


def test_onto_a_shot_with_no_picture_it_moves(book):
    kf = _pics(book, (1,))
    r = swap_pictures({"project": "demo", "a": 1, "b": 3, "model": "flux"})
    assert not r["a_has"] and r["b_has"] and (kf / "image-0003.png").read_bytes() == b"pic1" and not (kf / "image-0001.png").exists()


@pytest.mark.parametrize("body, msg", [({"a": 1, "b": 1}, "another shot"), ({"a": 1, "b": 99}, "no such shot"), ({"a": True, "b": 2}, "no such shot"),
                                       ({"a": 1, "b": 2, "model": "../x"}, "picture maker"), ({"a": 3, "b": 4}, "neither shot")])
def test_refuses(book, body, msg):
    _pics(book)
    with pytest.raises(PlanError, match=msg):
        swap_pictures({"project": "demo", "model": "flux", **body})


def test_running_job_blocks(book, monkeypatch):
    from studio_app.jobs import JOB
    _pics(book)
    monkeypatch.setattr(JOB, "running", True)
    with pytest.raises(PlanError, match="running"):
        swap_pictures({"project": "demo", "a": 1, "b": 2, "model": "flux"})


def test_route(server, book):
    _pics(book)
    status, data = server.api("POST", "/api/swap_pictures", {"project": "demo", "a": 2, "b": 1, "model": "flux"})
    assert status == 200 and data["a"] == 2


JS = Path(__file__).resolve().parent / "js"


@pytest.mark.skipif(not shutil.which("node") or not (JS / "node_modules" / "jsdom").is_dir(), reason="node or jsdom is not installed")
def test_drag_and_drop_in_the_page(server, book):
    from conftest import TOKEN
    (book / "chapters").mkdir(exist_ok=True)
    (book / "chapters" / "chapter-001.txt").write_text("It was a long day and the story goes on.")
    kf = _pics(book)
    r = subprocess.run(["node", "sbswap.js", f"http://127.0.0.1:{server.port}/?t={TOKEN}"], cwd=JS, capture_output=True, text=True, timeout=90)
    assert r.stdout.strip(), r.stderr[-600:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["errors"] == [], out
    assert out["draggable"] == "true" and out["emptyDrop"] == "3" and out["highlighted"]
    assert out["status1"].startswith("Shots 1 and 2 swapped pictures"), out
    assert out["src1After"] != out["src1"]                             # the new picture shows at once
    assert out["status2"].startswith("Shots 2 and 3 swapped pictures") and not out["has2"] and out["has3"], out
    assert out["otherKept"] and out["calls"] == 4, out                 # two cards drawn again per drop, nothing else
    assert (kf / "image-0001.png").read_bytes() == b"pic2" and (kf / "image-0003.png").read_bytes() == b"pic1" and not (kf / "image-0002.png").exists()
