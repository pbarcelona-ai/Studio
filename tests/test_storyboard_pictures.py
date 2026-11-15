"""Storyboard cards: the order of their buttons, the pictures a shot has had (click one to use it), file versions so a swapped picture
shows at once, and thumbnails that follow a swap (studio_app/takes.py, studio_app/handler.py, web/static/js/pizazz.js)."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from studio_app.takes import storyboard


def _pictures(book):
    kf = book / "images" / "flux_keyframes"
    (kf / "takes").mkdir(parents=True)
    for n in (1, 2):
        (kf / f"image-{n:04d}.png").write_bytes(b"now%d" % n)
    (kf / "takes" / "image-0001-t1.png").write_bytes(b"older take, bigger")
    old = 1_600_000_000
    os.utime(kf / "takes" / "image-0001-t1.png", (old, old))         # a take is older than the picture it may replace
    return kf


def test_cards_carry_a_version_for_every_file(book):
    _pictures(book)
    c = storyboard("demo", 1, 1)["cards"][0]
    assert set(c["ver"]) == {"images/flux_keyframes/image-0001.png", "images/flux_keyframes/takes/image-0001-t1.png"}
    assert all(v and "-" in v for v in c["ver"].values())


def test_a_thumbnail_follows_a_swapped_in_older_file(server, book):
    kf = _pictures(book)
    pytest.importorskip("PIL")
    from PIL import Image
    Image.new("RGB", (8, 8), "red").save(kf / "image-0001.png")
    Image.new("RGB", (8, 8), "blue").save(kf / "takes" / "image-0001-t1.png")
    old = 1_600_000_000
    os.utime(kf / "takes" / "image-0001-t1.png", (old, old))
    from conftest import TOKEN
    import urllib.request
    get = lambda: urllib.request.urlopen(f"http://127.0.0.1:{server.port}/thumb/demo/images/flux_keyframes/image-0001.png?t={TOKEN}").read()
    first = get()
    status, _ = server.api("POST", "/api/pick_take", {"project": "demo", "kind": "keyframe", "model": "flux", "n": 1, "take": 1})
    assert status == 200
    assert get() != first                                             # the old thumbnail (newer than the swapped-in file) is not served


JS = Path(__file__).resolve().parent / "js"


@pytest.mark.skipif(not shutil.which("node") or not (JS / "node_modules" / "jsdom").is_dir(), reason="node or jsdom is not installed")
def test_the_card_in_the_page(server, book):
    from conftest import TOKEN
    (book / "chapters").mkdir(exist_ok=True)
    (book / "chapters" / "chapter-001.txt").write_text("It was a long day and the story goes on.")
    kf = _pictures(book)
    r = subprocess.run(["node", "sbpics.js", f"http://127.0.0.1:{server.port}/?t={TOKEN}"], cwd=JS, capture_output=True, text=True, timeout=90)
    assert r.stdout.strip(), r.stderr[-600:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["errors"] == [], out
    assert out["rows"] == ["◀ Earlier + Later ▶", "✎ Edit prompt", "editor", "↻ Retake keyframe + 🖼 Old pictures", "pictures"], out["rows"]
    assert out["nowShown"] and out["takes"] == 1
    assert "take 1 is now the one in use" in out["status"], out["status"]
    assert out["srcChanged"] and out["otherKept"], out                # the new picture at once, and only that card drawn again
    assert len(out["calls"]) == 1 and "start=1&end=1" in out["calls"][0], out["calls"]
    assert (kf / "image-0001.png").read_bytes() == b"older take, bigger" and (kf / "takes" / "image-0001-t2.png").read_bytes() == b"now1"
