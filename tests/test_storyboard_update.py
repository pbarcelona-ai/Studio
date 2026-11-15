"""Updating the storyboard when the storyline changes: the stamp on the shot list, the warning, and the reset that archives old stills and clips."""
import json

import pytest

import adaptation as ad
import review
import screenplay as sp
from studio_app.common import PlanError
from studio_app.takes import reset_storyboard, storyboard
from test_adaptation import GOOD, make_plan


@pytest.fixture()
def approved(book):
    chs = [{"n": n, "title": f"C{n}", "words": 100} for n in range(1, 7)]
    (book / "chapters.json").write_text(json.dumps({"chapters": chs}))
    plan = make_plan()
    ad.save(book, plan)
    for s in plan["scenes"]:
        sp.save_scene(book, s["id"], GOOD, edited=False)
    sp.approve(book, ad.load(book))
    return book


def test_no_stamp_means_unknown_not_changed(approved):
    assert sp.storyline_changed(approved) is False


def test_stamp_then_edit_marks_the_storyline_changed(approved):
    sp.stamp_shots(approved)
    assert sp.storyline_changed(approved) is False
    sid = ad.load(approved)["scenes"][0]["id"]
    sp.save_scene(approved, sid, {**GOOD, "heading": "ext. hill - day"}, edited=True)     # editing a scene removes the approval
    assert sp.storyline_changed(approved) is True
    sp.approve(approved, ad.load(approved))                                               # approving the new text: still not the text the shots came from
    assert sp.storyline_changed(approved) is True
    sp.stamp_shots(approved)                                                              # rebuilding the shots catches up
    assert sp.storyline_changed(approved) is False


def test_book_without_a_plan_has_no_stamp(book):
    (book / sp.STAMP_FILE).write_text(json.dumps({"fingerprint": "x"}))
    sp.stamp_shots(book)
    assert not (book / sp.STAMP_FILE).exists() and sp.storyline_changed(book) is False


def test_storyboard_reports_the_change(approved):
    sp.stamp_shots(approved)
    assert storyboard("demo", 1, 4)["storyline_changed"] is False
    sid = ad.load(approved)["scenes"][0]["id"]
    sp.save_scene(approved, sid, {**GOOD, "heading": "ext. hill - day"}, edited=True)
    assert storyboard("demo", 1, 4)["storyline_changed"] is True


def _make_outputs(book):
    kf = book / "images" / "flux_keyframes"
    kf.mkdir(parents=True)
    (kf / "image-0001.png").write_bytes(b"png")
    (kf / "image-0002.png").write_bytes(b"png")
    (kf / "takes").mkdir()
    (kf / "takes" / "image-0001-t1.png").write_bytes(b"old")
    vd = book / "videos" / "ltx"
    vd.mkdir(parents=True)
    (vd / "shot-0001.mp4").write_bytes(b"mp4")
    (book / "videos" / "ltx_chapters").mkdir()
    (book / "videos" / "ltx_chapters" / "chapter-1.mp4").write_bytes(b"keep")
    review.set_status(book, ["1#1"], "approved")
    (book / "critic.json").write_text("{}")
    (book / "prompt_edits.json").write_text("{}")


def test_reset_archives_everything_and_deletes_nothing(book):
    _make_outputs(book)
    r = reset_storyboard({"project": "demo"})
    assert r["moved"] >= 7 and r["folder"].startswith("replaced/")
    dest = book / r["folder"]
    assert (dest / "prompt_edits.json").is_file() and not (book / "prompt_edits.json").exists()
    assert (dest / "images" / "flux_keyframes" / "image-0001.png").is_file()
    assert (dest / "images" / "flux_keyframes" / "takes" / "image-0001-t1.png").is_file()
    assert (dest / "videos" / "ltx" / "shot-0001.mp4").is_file() and (dest / "review.json").is_file() and (dest / "critic.json").is_file()
    assert not list((book / "images" / "flux_keyframes").glob("image-*.png")) and not (book / "review.json").exists()
    assert (book / "videos" / "ltx_chapters" / "chapter-1.mp4").read_bytes() == b"keep"        # one-clip-per-chapter films are not part of the storyboard
    assert review.load(book) == {} and storyboard("demo", 1, 4)["cards"][0]["keyframes"] == {}


def test_reset_with_nothing_to_move(book):
    assert reset_storyboard({"project": "demo"}) == {"moved": 0, "folder": ""}


def test_reset_refuses_while_a_job_runs(book, monkeypatch):
    from studio_app.jobs import JOB
    monkeypatch.setattr(JOB, "running", True)
    with pytest.raises(PlanError, match="job is running"):
        reset_storyboard({"project": "demo"})


def test_reset_needs_a_book():
    with pytest.raises(PlanError):
        reset_storyboard({"project": "nope"})


def test_reset_route(server, book):
    _make_outputs(book)
    status, r = server.api("POST", "/api/storyboard_reset", {"project": "demo"})
    assert status == 200 and r["moved"] >= 6
