"""Old keyframe pictures: finding them, putting one on a shot, and putting them back on their shots by themselves (studio_app/old_pictures.py)."""
import json

import pytest

import review
from conftest import write_csv
from studio_app.common import PlanError
from studio_app.old_pictures import assign_picture, auto_assign, old_pictures
from studio_app.projects import read_csv_rows
from studio_app.takes import reset_storyboard


def _set_aside(book, prompts, stamp="20260101-120000"):
    """A storyboard made again earlier: its pictures and the shot list they showed, in replaced/<stamp>/."""
    d = book / "replaced" / stamp
    kf = d / "images" / "flux_keyframes"
    kf.mkdir(parents=True)
    for n, _ in enumerate(prompts, 1):
        (kf / f"image-{n:04d}.png").write_text(f"old{n}")
    write_csv(d / "all_shots.csv", [{"chapter": "1", "shot": n, "prompt": p} for n, p in enumerate(prompts, 1)])
    return kf


def test_lists_old_pictures_most_alike_first(book):
    _set_aside(book, ["a river at night", "a mountain at dawn with snow"])
    kf = book / "images" / "flux_keyframes"
    (kf / "takes").mkdir(parents=True)
    (kf / "takes" / "image-0001-t1.png").write_text("take")
    (kf / "image-0003.png").write_text("now3")
    r = old_pictures("demo", 2)                                       # shot 2 is "a mountain at dawn"
    assert r["prompt"] == "a mountain at dawn" and r["pictures"][0]["prompt"] == "a mountain at dawn with snow" and r["pictures"][0]["score"] > 0.5
    sources = {p["source"].split(" ")[0] for p in r["pictures"]}
    assert sources == {"set", "earlier", "made"} and any(p["take"] == 1 for p in r["pictures"])
    assert old_pictures("demo", 3)["pictures"] and not any(p["path"].endswith("image-0003.png") and p["source"].startswith("made") for p in old_pictures("demo", 3)["pictures"])
    assert old_pictures("demo")["total"] == 4


def test_assign_keeps_the_old_picture_as_a_take_and_asks_again(book):
    kf = _set_aside(book, ["a river at night"])
    cur = book / "images" / "flux_keyframes"
    cur.mkdir(parents=True)
    (cur / "image-0004.png").write_text("current")
    review.set_status(book, ["1#4"], "approved")
    (book / "face_check.json").write_text(json.dumps({"rows": {"4": {"status": "same"}}}))
    r = assign_picture({"project": "demo", "n": 4, "path": "replaced/20260101-120000/images/flux_keyframes/image-0001.png"})
    assert (cur / "image-0004.png").read_text() == "old1" and (kf / "image-0001.png").exists()           # copied, the old one stays
    assert r["kept_as_take"] == "images/flux_keyframes/takes/image-0004-t1.png" and (cur / "takes" / "image-0004-t1.png").read_text() == "current"
    assert "1#4" not in review.load(book) and json.loads((book / "face_check.json").read_text())["rows"] == {}


@pytest.mark.parametrize("path", ["../../etc/passwd", "replaced/x/../../all_shots.csv", "all_shots.csv", "images/flux_keyframes/image-0009.png"])
def test_assign_refuses_what_is_not_an_old_picture(book, path):
    with pytest.raises(PlanError):
        assign_picture({"project": "demo", "n": 1, "path": path, "model": "flux"})


def test_assign_checks_the_shot_and_the_model(book):
    _set_aside(book, ["a river at night"])
    p = "replaced/20260101-120000/images/flux_keyframes/image-0001.png"
    with pytest.raises(PlanError, match="no such shot"):
        assign_picture({"project": "demo", "n": 99, "path": p})
    with pytest.raises(PlanError, match="picture maker"):
        assign_picture({"project": "demo", "n": 1, "path": p, "model": "Bad Name!"})


def test_auto_assign_puts_old_pictures_back_on_their_shots(book):
    # the storyboard was made again: the shots are the same four, now in another order, with no pictures
    _set_aside(book, ["a river at night", "a woman walks in a garden", "he raises his hand", "something nobody wants"])
    r = auto_assign({"project": "demo", "model": "flux"})
    got = {m["n"]: m["from"].rsplit("/", 1)[1] for m in r["matched"]}
    assert got == {1: "image-0002.png", 3: "image-0003.png", 4: "image-0001.png"} and r["still_missing"] == [2]
    kf = book / "images" / "flux_keyframes"
    assert (kf / "image-0001.png").read_text() == "old2" and (kf / "image-0004.png").read_text() == "old1"
    again = auto_assign({"project": "demo", "model": "flux"})
    assert again["matched"] == [] and again["still_missing"] == [2]         # nothing twice, and a shot with a picture is left alone


def test_auto_assign_needs_shots_and_a_good_name(book):
    with pytest.raises(PlanError, match="bad picture maker"):
        auto_assign({"project": "demo", "model": "x y"})
    write_csv(book / "all_shots.csv", [{"chapter": "1", "shot": 1, "prompt": ""}])
    (book / "all_shots.csv").write_text("chapter,shot,prompt\n")
    with pytest.raises(PlanError, match="no shots"):
        auto_assign({"project": "demo"})


def test_reset_keeps_the_shot_list_with_the_set_aside_pictures(book):
    kf = book / "images" / "flux_keyframes"
    kf.mkdir(parents=True)
    (kf / "image-0001.png").write_text("p")
    r = reset_storyboard({"project": "demo"})
    rows = read_csv_rows(book / r["folder"] / "all_shots.csv")
    assert rows[0]["prompt"] == "a woman walks in a garden"
    assert old_pictures("demo", 1)["pictures"][0]["prompt"] == "a woman walks in a garden"


def test_running_job_blocks(book, monkeypatch):
    from studio_app.jobs import JOB
    monkeypatch.setattr(JOB, "running", True)
    with pytest.raises(PlanError, match="running"):
        auto_assign({"project": "demo"})
    with pytest.raises(PlanError, match="running"):
        assign_picture({"project": "demo", "n": 1, "path": "x"})


def test_routes(server, book):
    _set_aside(book, ["a woman walks in a garden"])
    status, data = server.api("GET", "/api/old_pictures?project=demo&n=1")
    assert status == 200 and data["pictures"][0]["score"] == 1.0
    status, data = server.api("POST", "/api/auto_assign_pictures", {"project": "demo", "model": "flux"})
    assert status == 200 and [m["n"] for m in data["matched"]] == [1]
    status, data = server.api("POST", "/api/assign_picture", {"project": "demo", "n": 2, "path": "replaced/20260101-120000/images/flux_keyframes/image-0001.png"})
    assert status == 200 and data["n"] == 2


JS = __import__("pathlib").Path(__file__).resolve().parent / "js"


@pytest.mark.skipif(not __import__("shutil").which("node") or not (JS / "node_modules" / "jsdom").is_dir(), reason="node or jsdom is not installed")
def test_the_picker_in_the_page(server, book):
    import subprocess
    from conftest import TOKEN
    (book / "chapters").mkdir(exist_ok=True)
    (book / "chapters" / "chapter-001.txt").write_text("It was a long day and the story goes on.")
    _set_aside(book, ["a river at night", "a mountain at dawn with snow"])
    r = subprocess.run(["node", "oldpics.js", f"http://127.0.0.1:{server.port}/?t={TOKEN}"], cwd=JS, capture_output=True, text=True, timeout=90)
    assert r.stdout.strip(), r.stderr[-600:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["errors"] == [], out
    assert out["open"] and out["title"] == "Old pictures for shot 2" and "% like this shot" in out["first"] and "was shot 2" in out["first"]
    assert out["status"].startswith("Shot 2 now has that picture"), (out["status"], out.get("after"))
    assert (book / "images" / "flux_keyframes" / "image-0002.png").read_text() == "old2"
