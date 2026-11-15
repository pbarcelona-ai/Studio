"""Clip length per shot and for a whole movie (clip_length.py, studio_app/cliplen.py), and how the video notebooks turn it into frames."""
import json

import pytest

import clip_length as cl
import shot_move
from conftest import write_csv
from studio_app.cliplen import clip_length_action, share_out
from studio_app.common import PlanError
from studio_app.projects import read_csv_rows
from studio_app.takes import storyboard


def say(book, lines):
    write_csv(book / "audio_shots.csv", [{"chapter": "1", "shot": i, "narration": t, "sfx": "", "music": ""} for i, t in enumerate(lines, 1)])


def test_spoken_and_fit():
    assert cl.spoken_seconds({"narration": " ".join(["w"] * 10)}) == 4.4
    assert cl.fit_narration({"narration": " ".join(["w"] * 10)}) == 4.5
    assert cl.spoken_seconds({"narration": "", "lines_json": json.dumps([["EVE", "one two three four five"]])}) == 2.4
    assert cl.spoken_seconds({}) == 0.0 and cl.fit_narration({}) == cl.LEAST
    assert cl.snap(0.2) == 1.0 and cl.snap(99) == 99.0 and cl.snap(3.3) == 3.5       # no longest clip
    assert cl.fit_narration({"narration": "w w"}, now=6) == 6.0 and cl.fit_narration({"narration": " ".join(["w"] * 30)}, now=6) == 12.5


def test_one_shot_set_match_and_clear(book):
    say(book, ["w " * 15, "short", "", "x"])
    r = clip_length_action({"project": "demo", "n": 1, "match_narration": True})
    assert r["shots"][0]["seconds"] == 6.5 and r["shots"][0]["spoken"] == 6.4
    assert read_csv_rows(book / "all_shots.csv")[0]["seconds"] == "6.5"
    clip_length_action({"project": "demo", "n": 2, "seconds": 7.2})
    assert cl.load(book) == {"1#1": 6.5, "1#2": 7.0}
    clip_length_action({"project": "demo", "n": 1, "seconds": None})
    assert cl.load(book) == {"1#2": 7.0} and read_csv_rows(book / "all_shots.csv")[0]["seconds"] == ""
    with pytest.raises(PlanError, match="no such shot"):
        clip_length_action({"project": "demo", "n": 9, "seconds": 3})
    assert clip_length_action({"project": "demo", "n": 1, "seconds": 95})["shots"][0]["seconds"] == 95.0          # as long as you like
    with pytest.raises(PlanError, match="at least 1"):
        clip_length_action({"project": "demo", "n": 1, "seconds": 0})
    r = clip_length_action({"project": "demo", "n": 1, "match_narration": True})
    assert r["shots"][0]["seconds"] == 95.0                     # matching the words never makes a clip shorter than it is


def test_whole_movie_match_and_target(book):
    say(book, ["w " * 15, "w " * 5, "", "w " * 2])
    r = clip_length_action({"project": "demo", "start": 1, "end": 4, "match_narration": True})
    assert [s["seconds"] for s in r["shots"]] == [6.5, 4.0, 4.0, 4.0] and r["total"] == 18.5     # longer where the words need it, never below 4 s
    r = clip_length_action({"project": "demo", "start": 1, "end": 4, "target_seconds": 30, "default_seconds": 4})
    secs = [s["seconds"] for s in r["shots"]]
    assert abs(r["total"] - 30) <= 1 and all(s >= f for s, f in zip(secs, [6.5, 2.5, 1.0, 1.5], strict=True))
    r = clip_length_action({"project": "demo", "start": 1, "end": 4, "target_seconds": 6})         # shorter than the words allow: the words win
    assert [s["seconds"] for s in r["shots"]] == [6.5, 2.5, 1.0, 1.5]
    with pytest.raises(PlanError, match="row range"):
        clip_length_action({"project": "demo", "start": 3, "end": 9, "match_narration": True})


def test_share_out_keeps_floors_and_proportions():
    out = share_out([4, 4, 4, 4], [1, 1, 8, 1], 24)
    assert out[2] == 8.0 and out[0] == out[1] == out[3] and abs(sum(out) - 24) <= 1
    assert share_out([2, 6], [1, 1], 16) == [4.0, 12.0]


def test_storyboard_cards_show_the_length(book):
    say(book, ["w " * 10, "", "", ""])
    clip_length_action({"project": "demo", "n": 1, "seconds": 5})
    c = storyboard("demo", 1, 4)["cards"]
    assert c[0]["seconds"] == "5" and c[0]["spoken"] == 4.4 and c[1]["seconds"] == ""


def test_the_length_moves_with_its_shot(book):
    say(book, ["a", "b", "c", "d"])
    clip_length_action({"project": "demo", "n": 2, "seconds": 9})
    shot_move.move(book, 2, 1)
    assert cl.load(book) == {"1#3": 9.0} and read_csv_rows(book / "all_shots.csv")[2]["seconds"] == "9"


def test_critic_uses_each_shots_length(book):
    import critic
    say(book, ["w " * 20, "", "", ""])
    assert any(f["kind"] == "pacing" and f["n"] == 1 for f in critic.run(book, 4)["findings"])
    clip_length_action({"project": "demo", "n": 1, "match_narration": True})
    assert not any(f["kind"] == "pacing" and f["n"] == 1 for f in critic.run(book, 4)["findings"])


def _frames_fn(model_id, fps):
    import make_video
    ns = {"MODEL_ID": model_id, "FPS": fps, "WIDTH": 768, "HEIGHT": 320}
    exec(make_video.OPT_BASE, ns)
    return ns["opt"]


def test_notebooks_turn_seconds_into_frames():
    ltx = _frames_fn("Lightricks/LTX-Video", 24)
    assert ltx({"seconds": "6"}, "frames", 97) == 145 and (145 - 1) % 8 == 0          # 8*k+1 at 24 fps
    assert ltx({"seconds": "20"}, "frames", 97) == 481                                # no longest clip
    assert ltx({"seconds": "", "frames": ""}, "frames", 97) == 97 and ltx({"frames": "49", "seconds": "6"}, "frames", 97) == 49
    wan = _frames_fn("Wan-AI/Wan2.2-TI2V-5B-Diffusers", 24)
    assert (wan({"seconds": "2"}, "frames", 33) - 1) % 4 == 0
    assert _frames_fn("THUDM/CogVideoX-2b", 8)({"seconds": "9"}, "frames", 49) == 49     # fixed length


def test_route(server, book):
    say(book, ["w " * 10, "", "", ""])
    status, data = server.api("POST", "/api/clip_length", {"project": "demo", "n": 1, "match_narration": True})
    assert status == 200 and data["shots"][0]["seconds"] == 4.5


JS = __import__("pathlib").Path(__file__).resolve().parent / "js"


@pytest.mark.skipif(not __import__("shutil").which("node") or not (JS / "node_modules" / "jsdom").is_dir(), reason="node or jsdom is not installed")
def test_clip_lengths_in_the_page(server, book):
    import subprocess
    from conftest import TOKEN
    (book / "chapters").mkdir(exist_ok=True)
    (book / "chapters" / "chapter-001.txt").write_text("It was a long day and the story goes on.")
    say(book, ["w " * 15, "w " * 5, "", ""])
    r = subprocess.run(["node", "cliplen.js", f"http://127.0.0.1:{server.port}/?t={TOKEN}"], cwd=JS, capture_output=True, text=True, timeout=90)
    assert r.stdout.strip(), r.stderr[-600:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["errors"] == [], out
    assert out["box"] and "too short" in out["hint1"] and out["movie0"] == "16"
    assert out["after1"].startswith("Shot 1's clip is now 6 s") and out["value1"] == "6"
    assert out["after2"].startswith("Shot 2's clip is now 4 s")
    import re
    assert re.match(r"The movie is now about (39|40|41) s", out["after3"]) and out["movie1"] in ("39", "40", "41")     # each clip is a whole half second
    assert cl.load(book)["1#1"] > 6


@pytest.mark.skipif(not __import__("shutil").which("node") or not (JS / "node_modules" / "jsdom").is_dir(), reason="node or jsdom is not installed")
def test_critic_and_cards_show_the_same_length(server, book):
    import subprocess
    from conftest import TOKEN
    (book / "chapters").mkdir(exist_ok=True)
    (book / "chapters" / "chapter-001.txt").write_text("It was a long day and the story goes on.")
    say(book, ["w " * 30, "", "", ""])                         # shot 1's words take about 12 s: a pacing finding
    r = subprocess.run(["node", "cliplink.js", f"http://127.0.0.1:{server.port}/?t={TOKEN}"], cwd=JS, capture_output=True, text=True, timeout=120)
    assert r.stdout.strip(), r.stderr[-600:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["errors"] == [], out
    assert out["critBox"] and out["pacing0"] >= 1
    assert out["cardAfterCritic"] == "5" and out["criticAfterCard"] == "5.5"
    assert out["pacing1"] == 0 and out["cardAfterMatch"] == "12.5"
