"""The film path (studio_app/path.py), the loop back from the storyboard to the screenplay (feedback.py) and moving shots (shot_move.py)."""
import json

import pytest

import feedback
import review
import screenplay as sp
import shot_move
from conftest import write_csv
from studio_app.adapt import screenplay_data, screenplay_edit
from studio_app.common import PlanError
from studio_app.path import STEP_IDS, feedback_keep, path_confirm, path_data, shot_move_action
from studio_app.projects import read_csv_rows
from studio_app.scenes import prompt_save
from test_adaptation import GOOD


def steps(slug="demo"):
    return {s["id"]: s for s in path_data(slug)["steps"]}


def test_every_step_is_listed_in_order():
    assert STEP_IDS[0] == "read" and STEP_IDS[3] == "screenplay" and STEP_IDS.index("keyframes") < STEP_IDS.index("storyboard") < STEP_IDS.index("video")
    assert STEP_IDS[-1] == "premiere" and len(STEP_IDS) == len(set(STEP_IDS)) == 16


def test_a_new_book_waits_at_the_plan(book):
    st = steps()
    assert st["read"]["ok"] and st["chapters"]["ok"]
    assert not st["plan"]["ok"] and "Plan the film" in st["plan"]["todo"]


def test_ready_book_waits_at_the_pictures(film):
    st = steps()
    assert all(st[s]["ok"] for s in ("read", "plan", "screenplay", "continuity", "write", "build", "where"))
    assert not st["keyframes"]["ok"] and "0 of 4" in st["keyframes"]["todo"]


def test_unapproved_screenplay_blocks(film):
    sp.clear_approval(film)
    st = steps()
    assert not st["screenplay"]["ok"] and "Approve the screenplay" in st["screenplay"]["todo"]


def _pictures(book, n=4):
    kf = book / "images" / "flux_keyframes"
    kf.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        (kf / f"image-{i:04d}.png").write_bytes(f"pic{i}".encode())
    return kf


def test_pictures_must_be_judged_before_more_are_made(film):
    _pictures(film)
    st = steps()
    assert st["keyframes"]["ok"] and "4 picture(s) are waiting" in st["keyframes"]["todo"]
    assert not st["storyboard"]["ok"] and "0 of 4" in st["storyboard"]["todo"]
    review.set_status(film, ["1#1", "1#2", "1#3"], "approved")
    review.set_status(film, ["1#4"], "rejected")
    st = steps()
    assert "You said no to 1" in st["keyframes"]["todo"] and not st["storyboard"]["ok"]
    review.set_status(film, ["1#4"], "approved")
    st = steps()
    assert st["storyboard"]["ok"] and st["keyframes"]["todo"] == "" and not st["video"]["ok"]
    assert [a["step"] for a in path_data("demo")["alerts"]] == []


def test_storyboard_edit_flags_the_screenplay_and_starts_the_walk_back(film):
    r = prompt_save({"project": "demo", "chapter": "1", "shot": 2, "fields": {"narration": "a brand new line"}})
    assert r["saved"] == ["narration"]
    fb = feedback.load(film)
    assert fb["revisit"] == feedback.REVISIT and fb["open"][0]["old"] == "line 2" and fb["open"][0]["new"] == "a brand new line"
    sid = fb["open"][0]["scene"]
    assert screenplay_data("demo")["flags"][sid][0]["field"] == "narration"
    st = steps()
    assert not st["screenplay"]["ok"] and "red outline" in st["screenplay"]["todo"] and not st["storyboard"]["ok"]
    data = path_data("demo")
    assert data["revisit"][0] == "screenplay" and data["alerts"][0]["step"] == "screenplay"
    with pytest.raises(PlanError, match="red outline"):
        screenplay_edit({"project": "demo", "action": "approve"})
    with pytest.raises(PlanError):
        path_confirm({"project": "demo", "step": "screenplay"})          # not fixed yet
    # fix the scene: saving it clears its flag, and it must be approved again
    screenplay_edit({"project": "demo", "action": "save_scene", "scene": sid, "heading": "EXT. FIELD - DAY", "elements": GOOD["elements"]})
    assert feedback.open_flags(film) == {}
    assert not steps()["screenplay"]["ok"]
    screenplay_edit({"project": "demo", "action": "approve"})
    assert sp.storyline_changed(film)                                      # the text changed ...
    out = path_confirm({"project": "demo", "step": "screenplay"})
    assert out["revisit"][0] == "continuity" and not sp.storyline_changed(film)   # ... but it now matches the storyboard: the shots are current
    assert path_confirm({"project": "demo", "step": "write"})["revisit"][0] == "continuity"     # out of order: nothing happens
    for s in feedback.REVISIT[1:7]:
        path_confirm({"project": "demo", "step": s})
    assert path_data("demo")["revisit"] == ["keyframes", "storyboard"]
    with pytest.raises(PlanError, match="Make the pictures"):
        path_confirm({"project": "demo", "step": "keyframes"})


def test_keep_it_clears_a_flag_without_editing(film):
    prompt_save({"project": "demo", "chapter": "1", "shot": 1, "fields": {"prompt": "a new picture"}})
    sid = next(iter(feedback.open_flags(film)))
    assert feedback_keep({"project": "demo", "scene": sid})["cleared"] == 1
    assert steps()["screenplay"]["ok"]
    with pytest.raises(PlanError):
        feedback_keep({"project": "demo", "scene": "../x"})


def test_a_book_without_a_plan_records_nothing(book):
    prompt_save({"project": "demo", "chapter": "1", "shot": 1, "fields": {"prompt": "x y z"}})
    assert feedback.load(book) == {"open": [], "revisit": []} and not (book / feedback.FILE).exists()


def test_confirm_needs_a_real_step(film):
    with pytest.raises(PlanError):
        path_confirm({"project": "demo", "step": "nope"})
    assert path_confirm({"project": "demo", "step": "read"})["revisit"] == []


# ---------------------------------------------------------------- moving a shot
def test_move_takes_everything_with_the_shot(film):
    write_csv(film / "audio_shots.csv", [{"chapter": "1", "shot": i, "narration": f"line {i}", "sfx": "wind", "music": "calm"} for i in range(1, 5)])
    kf = _pictures(film)
    (kf / "takes").mkdir()
    (kf / "takes" / "image-0002-t1.png").write_bytes(b"old2")
    au = film / "audio" / "kokoro"
    au.mkdir(parents=True)
    (au / "narration-0002.wav").write_bytes(b"say2")
    (film / "videos" / "ltx_chapters").mkdir(parents=True)
    (film / "videos" / "ltx_chapters" / "shot-0002.mp4").write_bytes(b"chapter clip")
    review.set_status(film, ["1#2"], "approved")
    (film / "prompt_edits.json").write_text(json.dumps({"1#2": {"chapter": "1", "shot": 2, "fields": {"prompt": {"original": "o", "edited": "a mountain at dawn"}}}}))
    (film / "face_check.json").write_text(json.dumps({"rows": {"2": {"status": "same"}}}))
    (film / "critic.json").write_text("{}")
    out = shot_move_action({"project": "demo", "n": 2, "direction": 1})
    assert out["n"] == 3
    rows = read_csv_rows(film / "all_shots.csv")
    assert [r["prompt"] for r in rows] == ["a woman walks in a garden", "he raises his hand", "a mountain at dawn", "a river at night"]
    assert [r["shot"] for r in rows] == ["1", "2", "3", "4"]
    assert read_csv_rows(film / "audio_shots.csv")[2]["narration"] == "line 2"
    script = json.loads((film / "scripts" / "chapter-001.json").read_text())["shots"]
    assert [s["prompt"] for s in script] == ["p1", "p3", "p2", "p4"] and [s["n"] for s in script] == [1, 2, 3, 4]
    assert (kf / "image-0003.png").read_bytes() == b"pic2" and (kf / "image-0002.png").read_bytes() == b"pic3"
    assert (kf / "takes" / "image-0003-t1.png").read_bytes() == b"old2" and not (kf / "takes" / "image-0002-t1.png").exists()
    assert (au / "narration-0003.wav").read_bytes() == b"say2"
    assert (film / "videos" / "ltx_chapters" / "shot-0002.mp4").read_bytes() == b"chapter clip"
    assert review.load(film).get("1#3", {}).get("status") == "approved" and "1#2" not in review.load(film)
    edits = json.loads((film / "prompt_edits.json").read_text())
    assert list(edits) == ["1#3"] and edits["1#3"]["shot"] == 3
    assert json.loads((film / "face_check.json").read_text())["rows"] == {"3": {"status": "same"}}
    assert not (film / "critic.json").exists()
    assert feedback.load(film)["open"][0]["kind"] == "moved" and out["path"]["revisit"][0] == "screenplay"


def test_move_limits(film):
    with pytest.raises(PlanError, match="first"):
        shot_move_action({"project": "demo", "n": 1, "direction": -1})
    with pytest.raises(PlanError, match="last"):
        shot_move_action({"project": "demo", "n": 4, "direction": 1})
    with pytest.raises(PlanError, match="no such shot"):
        shot_move_action({"project": "demo", "n": 9, "direction": 1})
    with pytest.raises(PlanError, match="direction"):
        shot_move_action({"project": "demo", "n": 2, "direction": 2})


def test_move_across_into_the_next_chapter(film):
    rows = read_csv_rows(film / "all_shots.csv")
    for r, (ch, shot) in zip(rows, [("1", 1), ("1", 2), ("2", 1), ("2", 2)], strict=True):
        r["chapter"], r["shot"] = ch, str(shot)
    write_csv(film / "all_shots.csv", rows)
    (film / "scripts" / "chapter-001.json").write_text(json.dumps({"chapter": 1, "shots": [{"n": 1, "prompt": "a1"}, {"n": 2, "prompt": "a2"}]}))
    (film / "scripts" / "chapter-002.json").write_text(json.dumps({"chapter": 2, "shots": [{"n": 1, "prompt": "b1"}, {"n": 2, "prompt": "b2"}]}))
    (film / "prompt_edits.json").write_text(json.dumps({"1#2": {"chapter": "1", "shot": 2, "fields": {"prompt": {"original": "o", "edited": "a mountain at dawn"}}}}))
    assert shot_move.move(film, 2, 1) == 3
    after = read_csv_rows(film / "all_shots.csv")
    assert [(r["chapter"], r["shot"], r["prompt"]) for r in after][1:3] == [("1", "2", "he raises his hand"), ("2", "1", "a mountain at dawn")]
    one = json.loads((film / "scripts" / "chapter-001.json").read_text())["shots"]
    two = json.loads((film / "scripts" / "chapter-002.json").read_text())["shots"]
    assert [(x["n"], x["prompt"]) for x in one] == [(1, "a1"), (2, "b1")] and [(x["n"], x["prompt"]) for x in two] == [(1, "a2"), (2, "b2")]
    edits = json.loads((film / "prompt_edits.json").read_text())
    assert list(edits) == ["2#1"] and edits["2#1"]["chapter"] == "2" and edits["2#1"]["shot"] == 1


def test_move_refused_while_a_job_runs(film, monkeypatch):
    from studio_app.jobs import JOB
    monkeypatch.setattr(JOB, "running", True)
    with pytest.raises(PlanError, match="running"):
        shot_move_action({"project": "demo", "n": 2, "direction": 1})


def test_routes(server, film):
    status, data = server.api("GET", "/api/path?project=demo")
    assert status == 200 and [s["id"] for s in data["steps"]] == STEP_IDS
    status, data = server.api("POST", "/api/shot_move", {"project": "demo", "n": 1, "direction": 1})
    assert status == 200 and data["n"] == 2
    sid = next(iter(feedback.open_flags(film)))
    status, data = server.api("POST", "/api/feedback_keep", {"project": "demo", "scene": sid})
    assert status == 200 and data["cleared"] == 1
    status, data = server.api("POST", "/api/path_confirm", {"project": "demo", "step": "screenplay"})
    assert status == 200 and data["revisit"][0] == "continuity"
