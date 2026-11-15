"""Storyboard review: approve / reject per shot, summary, re-roll rejected."""
import pytest

import review as rv


@pytest.fixture()
def shots(book):
    """books/demo from conftest has 4 rows in chapter "1": make keyframes for them."""
    kf = book / "images" / "flux_keyframes"
    kf.mkdir(parents=True)
    for n in range(1, 5):
        (kf / f"image-{n:04d}.png").write_bytes(b"png")
    return book


def post(server, body):
    return server.api("POST", "/api/review", {"project": "demo", **body})


class TestReviewModule:
    def test_set_and_summary(self, tmp_path):
        rows = [{"chapter": "demo-001", "shot": str(i)} for i in range(1, 5)]
        valid = {rv.shot_key(r) for r in rows}
        rv.set_status(tmp_path, ["demo-001#1", "demo-001#2"], "approved", valid=valid)
        rv.set_status(tmp_path, ["demo-001#3"], "rejected", "  too   dark ", valid=valid)
        s = rv.summary(rv.load(tmp_path), rows)
        assert (s["approved"], s["rejected"], s["pending"], s["ready"]) == (2, 1, 1, False) and rv.load(tmp_path)["demo-001#3"]["note"] == "too dark"
        rv.set_status(tmp_path, ["demo-001#3"], "pending", valid=valid)
        assert "demo-001#3" not in rv.load(tmp_path)
        rv.set_status(tmp_path, ["demo-001#3", "demo-001#4"], "approved", valid=valid)
        assert rv.summary(rv.load(tmp_path), rows)["ready"] is True and rv.summary({}, []) == {"total": 0, "approved": 0, "rejected": 0, "pending": 0, "ready": False}

    def test_bad_input(self, tmp_path):
        for args in ((["a#1"], "maybe"), ([], "approved"), (["nohash"], "approved"), ("a#1", "approved"), ([5], "approved")):
            with pytest.raises(rv.ReviewError):
                rv.set_status(tmp_path, *args)
        with pytest.raises(rv.ReviewError, match="unknown shot"):
            rv.set_status(tmp_path, ["x#1"], "approved", valid={"y#1"})
        (tmp_path / "review.json").write_text("[1]")
        assert rv.load(tmp_path) == {}


class TestRoutes:
    def test_cards_carry_the_verdict(self, server, shots):
        out = server.api("GET", "/api/storyboard?project=demo&start=1&end=4")[1]
        assert out["review"] == {"total": 4, "approved": 0, "rejected": 0, "pending": 4, "ready": False}
        assert out["cards"][0]["key"] == "1#1" and out["cards"][0]["review"]["status"] == "pending"
        st, res = post(server, {"action": "set", "keys": ["1#1", "1#2"], "status": "approved"})
        assert st == 200 and res["review"]["approved"] == 2
        st, res = post(server, {"action": "set", "keys": ["1#3"], "status": "rejected", "note": "face melts"})
        out = server.api("GET", "/api/storyboard?project=demo&start=1&end=4")[1]
        assert out["cards"][2]["review"] == {**out["cards"][2]["review"], "status": "rejected", "note": "face melts"}

    def test_approve_the_rest_keeps_rejections(self, server, shots):
        post(server, {"action": "set", "keys": ["1#2"], "status": "rejected"})
        res = post(server, {"action": "approve_range", "start": 1, "end": 4})[1]
        assert res["review"]["approved"] == 3 and res["review"]["rejected"] == 1

    def test_reroll_rejected_retakes_and_resets(self, server, shots):
        post(server, {"action": "set", "keys": ["1#2", "1#4"], "status": "rejected"})
        st, res = post(server, {"action": "reroll_rejected", "start": 1, "end": 4, "kind": "keyframe", "model": "flux"})
        assert st == 200 and res["rerolled"] == 2 and res["review"]["rejected"] == 0 and res["skipped"] == []
        kf = shots / "images" / "flux_keyframes"
        assert not (kf / "image-0002.png").exists() and (kf / "takes" / "image-0002-t1.png").exists() and (kf / "image-0001.png").exists()
        assert "seed" in (shots / "all_shots.csv").read_text().splitlines()[0]                                                 # the retake gave the shots a new seed
        assert post(server, {"action": "reroll_rejected", "start": 1, "end": 4, "kind": "keyframe", "model": "flux"})[0] == 400       # nothing rejected now

    def test_reroll_skips_shots_that_have_nothing_to_retake(self, server, shots):
        (shots / "images" / "flux_keyframes" / "image-0002.png").unlink()
        post(server, {"action": "set", "keys": ["1#2", "1#3"], "status": "rejected"})
        res = post(server, {"action": "reroll_rejected", "start": 1, "end": 4, "kind": "keyframe", "model": "flux"})[1]
        assert res["rerolled"] == 1 and "shot 2" in res["skipped"][0]
        assert review_status(server)["1#2"] == "rejected"                                                                          # the skipped one stays rejected

    def test_errors(self, server, shots):
        assert post(server, {"action": "set", "keys": ["9#9"], "status": "approved"})[0] == 400
        assert post(server, {"action": "set", "keys": ["1#1"], "status": "meh"})[0] == 400
        assert post(server, {"action": "approve_range", "start": 3, "end": 99})[0] == 400
        assert post(server, {"action": "dance"})[0] == 400
        assert server.api("POST", "/api/review", {"project": "../x", "action": "set"})[0] == 400


def review_status(server):
    return {k: v["status"] for k, v in rv.load(json_dir(server)).items()}


def json_dir(server):
    from layout import project_dir
    return project_dir("demo")
