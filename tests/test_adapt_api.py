"""The Adapt card's API, the approval gate in the run plan, and the new steps."""
import json

import pytest

import adaptation as ad
import screenplay as sp
from test_adaptation import GOOD, make_plan


@pytest.fixture()
def planned(book):
    """books/demo with chapters.json (6 chapters) and a saved plan."""
    chs = [{"n": n, "title": f"C{n}", "words": 100} for n in range(1, 7)]
    (book / "chapters.json").write_text(json.dumps({"chapters": chs}))
    (book / "chapters").mkdir(exist_ok=True)
    for n in range(1, 7):
        (book / "chapters" / f"chapter-{n:03d}.txt").write_text(f"event{n} begins here and the story goes on")
    ad.save(book, make_plan())
    return book


def post(server, path, body):
    return server.api("POST", path, body)


class TestPlanRoutes:
    def test_no_plan_yet(self, server, book):
        assert server.api("GET", "/api/adaptation?project=demo")[1] == {"exists": False, "chapters": 1}
        assert post(server, "/api/adaptation_edit", {"project": "demo", "action": "drop", "id": "S001"})[0] == 400
        assert server.api("GET", "/api/screenplay?project=demo")[0] == 400

    def test_read_and_edit(self, server, planned):
        st, out = server.api("GET", "/api/adaptation?project=demo")
        assert st == 200 and out["exists"] and len(out["plan"]["scenes"]) == 4 and out["active_clips"] == 30 and out["runtime"]["minutes"] == 2.0
        st, out = post(server, "/api/adaptation_edit", {"project": "demo", "action": "set_clips", "id": "S001", "clips": 9})
        assert st == 200 and out["plan"]["scenes"][0]["clips"] == 9 and out["runtime"]["difference_seconds"] > 0
        assert post(server, "/api/adaptation_edit", {"project": "demo", "action": "set_clips", "id": "S001", "clips": "x"})[0] == 400
        assert post(server, "/api/adaptation_edit", {"project": "demo", "action": "set_pilot", "kind": "chapters", "first": 1, "last": 2})[1]["plan"]["pilot"]["scene_ids"] == ["S001"]

    def test_dropping_or_joining_removes_those_screenplays(self, server, planned):
        for sid in ("S001", "S002", "S003"):
            sp.save_scene(planned, sid, GOOD, edited=True)
        post(server, "/api/adaptation_edit", {"project": "demo", "action": "merge", "id": "S001"})
        assert not sp.scene_file(planned, "S001").exists() and sp.load_scene(planned, "S003")
        post(server, "/api/adaptation_edit", {"project": "demo", "action": "drop", "id": "S003"})
        assert sp.load_scene(planned, "S003") is None

    def test_discard(self, server, planned):
        sp.save_scene(planned, "S001", GOOD, edited=True)
        assert post(server, "/api/adaptation_edit", {"project": "demo", "action": "discard"})[1] == {"exists": False}
        assert ad.load(planned) is None and not (planned / "screenplay").exists()

    def test_refused_while_a_job_runs_and_for_bad_books(self, server, planned, monkeypatch):
        assert server.api("GET", "/api/adaptation?project=../x")[0] == 400
        assert server.api("GET", "/api/adaptation?project=adam_eve")[0] == 400
        from studio_app.jobs import JOB
        monkeypatch.setattr(JOB, "running", True)
        for path, body in (("/api/adaptation_edit", {"project": "demo", "action": "discard"}), ("/api/screenplay_edit", {"project": "demo", "action": "approve"})):
            assert post(server, path, body)[0] == 400

    def test_screenplay_edit_and_approval(self, server, planned):
        st, out = server.api("GET", "/api/screenplay?project=demo")
        assert st == 200 and len(out["scenes"]) == 4 and out["status"]["written"] == 0 and "not written yet" in out["text"]
        assert post(server, "/api/screenplay_edit", {"project": "demo", "action": "approve"})[0] == 400
        for sid in ("S001", "S002", "S003", "S004"):
            st, out = post(server, "/api/screenplay_edit", {"project": "demo", "action": "save_scene", "scene": sid, "heading": "int. room - day", "elements": GOOD["elements"]})
            assert st == 200
        assert out["status"]["written"] == 4 and not out["status"]["approved"]
        assert post(server, "/api/screenplay_edit", {"project": "demo", "action": "approve"})[1]["status"]["approved"]
        assert post(server, "/api/screenplay_edit", {"project": "demo", "action": "unapprove"})[1]["status"]["approved"] is False
        assert server.api("GET", "/api/screenplay?project=demo&scene=S002")[1]["scenes"][0]["id"] == "S002"
        for bad in ({"action": "save_scene", "scene": "S999", "heading": "H", "elements": GOOD["elements"]}, {"action": "save_scene", "scene": "S001", "heading": "", "elements": []},
                    {"action": "dance"}):
            assert post(server, "/api/screenplay_edit", {"project": "demo", **bad})[0] == 400

    def test_budget(self, server, planned):
        st, out = post(server, "/api/budget", {"project": "demo", "model": "ltx_video_fast_i2v", "service": "kaggle", "gpu": "NvidiaTeslaT4"})
        assert st == 200 and out["full"]["clips"] == 30 and "Whole film" in out["text"]
        assert post(server, "/api/budget", {"project": "demo", "minutes": "abc"})[0] == 400

    def test_budget_for_a_book_without_a_plan(self, server, book):
        assert post(server, "/api/budget", {"project": "demo"})[0] == 400
        st, out = post(server, "/api/budget", {"project": "demo", "minutes": 10})
        assert st == 200 and out["full"]["clips"] == 150

    def test_status_lists_the_plan(self, server, planned):
        info = next(p for p in server.api("GET", "/api/status")[1]["projects"] if p["slug"] == "demo")
        assert info["adaptation"]["exists"] and info["adaptation"]["scenes"] == 4 and info["adaptation"]["approved"] is False


class TestGateAndSteps:
    def opts(self, **steps):
        return {"project": "demo", "steps": steps}

    def test_book_without_a_plan_is_not_gated(self, server, book):
        st, out = post(server, "/api/plan", self.opts(write=True))
        assert st == 200

    def test_plan_without_approved_screenplay_blocks_writing_and_pictures(self, server, planned):
        for steps in ({"write": True}, {"build": True}, {"keyframes": True}, {"video": True}, {"mix": True}):
            st, out = post(server, "/api/plan", self.opts(**steps))
            assert st == 400 and "screenplay" in out["error"].lower(), steps
        assert post(server, "/api/plan", self.opts(continuity=True))[0] == 200                 # the earlier steps are not gated

    def test_approval_opens_the_gate_and_an_edit_closes_it_again(self, server, planned):
        plan = ad.load(planned)
        for s in plan["scenes"]:
            sp.save_scene(planned, s["id"], GOOD, edited=False)
        sp.approve(planned, plan)
        assert post(server, "/api/plan", self.opts(write=True))[0] == 200
        sp.save_scene(planned, "S001", {**GOOD, "heading": "EXT. SEA - DAY"}, edited=True)
        assert post(server, "/api/plan", self.opts(write=True))[0] == 400

    def test_cannot_plan_and_generate_in_one_run(self, server, planned):
        st, out = post(server, "/api/plan", self.opts(adapt=True, write=True))
        assert st == 400 and "approve the screenplay" in out["error"]
        assert post(server, "/api/plan", self.opts(adapt=True, screenplay=True))[0] == 200

    def test_stale_plan_blocks(self, server, planned):
        plan = ad.load(planned)
        plan["stale"] = True
        ad.save(planned, plan)
        assert "chapters were changed" in post(server, "/api/plan", self.opts(write=True))[1]["error"]

    def test_adapt_and_screenplay_steps(self, server, book):
        st, out = post(server, "/api/plan", {"project": "demo", "film_minutes": 12, "clip_seconds": 5, "adapt_focus": "  follow   Eve ", "adapt_fit_only": True,
                                              "steps": {"adapt": True, "continuity": True, "screenplay": True}, "force_screenplay": True})
        cmds = [s["cmd"] for s in out["steps"]]
        assert st == 200 and "book_adapt.py demo --minutes 12.0 --clip-seconds 5.0" in cmds[0] and "--focus follow Eve" in cmds[0] and "--fit-only" in cmds[0]
        assert "book_continuity.py" in cmds[1] and "book_screenplay.py demo" in cmds[2] and "--force" in cmds[2]
        assert out["steps"][0]["label"] == "Adapt the book into a plan for a 12.0-minute film"
        assert post(server, "/api/plan", {"project": "demo", "film_minutes": 999, "steps": {"adapt": True}})[0] == 400


import shutil
import subprocess
from pathlib import Path

from conftest import TOKEN

JS = Path(__file__).resolve().parent / "js"


@pytest.mark.skipif(not shutil.which("node") or not (JS / "node_modules" / "jsdom").is_dir(), reason="node or jsdom is not installed (cd tests/js && npm install)")
def test_adapt_card_in_the_page(server, planned):
    plan = ad.load(planned)
    for s in plan["scenes"]:
        sp.save_scene(planned, s["id"], GOOD, edited=False)
    r = subprocess.run(["node", "adapt.js", f"http://127.0.0.1:{server.port}/?t={TOKEN}"], cwd=JS, capture_output=True, text=True, timeout=90)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["errors"] == [], out
    assert out["rows"] == 4 and not out["plan_hidden"] and "4 of 4 scenes written, not approved" in out["state0"] and out["budget"].startswith("Film: about")
    assert "you changed the clip counts" in out["runtime"] and out["state1"].startswith("approved")
    assert "not approved" in out["state2"] and out["still_open"] is True
