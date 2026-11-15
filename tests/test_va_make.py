"""The Video and Audio card has its own "Make the keyframes" button, with the same checks as the film path (jsdom)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import TOKEN

JS = Path(__file__).resolve().parent / "js"
pytestmark = pytest.mark.skipif(not shutil.which("node") or not (JS / "node_modules" / "jsdom").is_dir(), reason="node or jsdom is not installed")


def _run(server, book):
    (book / "chapters").mkdir(exist_ok=True)
    (book / "chapters" / "chapter-001.txt").write_text("It was a long day and the story goes on.")
    r = subprocess.run(["node", "vamake.js", f"http://127.0.0.1:{server.port}/?t={TOKEN}"], cwd=JS, capture_output=True, text=True, timeout=90)
    assert r.stdout.strip(), r.stderr[-600:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["errors"] == [], out
    return out


def test_the_card_makes_the_missing_keyframes(server, book):
    out = _run(server, book)
    assert out["inCard"] and out["others"] == [True, True] and out["stillClassic"]
    assert out["runs"] == [["keyframes"]] and "4 shot(s) that need one" in out["status"]


def test_missing_pictures_are_made_even_while_others_wait_for_a_verdict(server, book):
    kf = book / "images" / "sdxl_turbo_keyframes"
    kf.mkdir(parents=True)
    (kf / "image-0001.png").write_bytes(b"p")
    out = _run(server, book)
    assert out["runs"] == [["keyframes"]] and "3 shot(s) that need one" in out["status"] and "1 picture(s) already made still wait" in out["status"]


def test_nothing_is_made_when_every_shot_has_a_picture(server, book):
    kf = book / "images" / "sdxl_turbo_keyframes"
    kf.mkdir(parents=True)
    for n in range(1, 5):
        (kf / f"image-{n:04d}.png").write_bytes(f"p{n}".encode())
    out = _run(server, book)
    assert out["runs"] == [] and "Every shot has a picture" in out["status"]


def test_the_server_check(book):
    from studio_app.common import PlanError
    from studio_app.path import check_pictures_reviewed
    import review
    kf = book / "images" / "sdxl_turbo_keyframes"
    kf.mkdir(parents=True)
    (kf / "image-0001.png").write_bytes(b"p")
    check_pictures_reviewed("demo")                                 # shots 2-4 have no picture: a run may go ahead
    for n in range(2, 5):
        (kf / f"image-{n:04d}.png").write_bytes(f"p{n}".encode())
    with pytest.raises(PlanError, match="Every shot has a picture"):
        check_pictures_reviewed("demo")
    review.set_status(book, ["1#1", "1#2", "1#3"], "approved")
    review.set_status(book, ["1#4"], "rejected")
    with pytest.raises(PlanError, match="Re-roll"):
        check_pictures_reviewed("demo")
    review.set_status(book, ["1#4"], "approved")
    with pytest.raises(PlanError, match="nothing to make"):
        check_pictures_reviewed("demo")
