"""critic.py: pacing, variety, continuity, runtime and clip checks, flagging in the storyboard review, and the route."""
import csv
import json

import pytest

import adaptation as ad
import critic
import review
from test_adaptation import make_plan


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)


@pytest.fixture()
def film(fake_root):
    """A book with 8 shots in chapter demo-001: shots 1-5 are wide shots, shot 6 repeats shot 5, shot 7 talks too long, shot 8 changes place."""
    d = fake_root / "projects" / "books" / "demo"
    (d / "scripts").mkdir(parents=True)
    visuals = [f"A wide shot of the plain, a rider crosses at point {i}" for i in range(1, 6)] + [
        "A wide shot of the plain, a rider crosses at point 5", "A close-up of a hand on a gate", "A medium shot of Eve at the door"]
    shots, audio, script = [], [], []
    for i, v in enumerate(visuals, start=1):
        prompt = f"{v}, EVE: a woman, SETTING: the farm" if i != 2 else v                       # shot 2 lost its character and place
        shots.append({"chapter": "demo-001", "shot": str(i), "prompt": prompt, "negative": "", "characters": "Eve", "location": "Farm" if i < 8 else "Town",
                      "continues": "1" if i in (3, 8) else ""})
        audio.append({"chapter": "demo-001", "shot": str(i), "lines_json": "[]", "narration": "word " * (22 if i == 7 else 6), "sfx": "", "music": ""})
        script.append({"n": i, "visual": v})
    write_csv(d / "all_shots.csv", shots)
    write_csv(d / "audio_shots.csv", audio)
    (d / "scripts" / "chapter-001.json").write_text(json.dumps({"chapter": "demo-001", "shots": script}))
    (d / "demo.json").write_text(json.dumps({"characters": [{"name": "Eve", "token": "a woman"}], "locations": [{"name": "Farm", "token": "a farm"}]}))
    return d


def kinds(res, kind=None, n=None):
    return [(f["n"], f["severity"]) for f in res["findings"] if (kind is None or f["kind"] == kind) and (n is None or f["n"] == n)]


class TestChecks:
    def test_pacing(self, film):
        res = critic.run(film)
        assert kinds(res, "pacing") == [(7, "high")] and "8.8 s but the clip is 4 s" in next(f["message"] for f in res["findings"] if f["kind"] == "pacing")
        assert res["flagged"] == [7] and res["counts"]["high"] == 1 and (film / "critic.json").exists()

    def test_variety(self, film):
        res = critic.run(film)
        v = kinds(res, "variety")
        assert (5, "warn") in v                               # five wide shots in a row
        assert (6, "warn") in v                               # shot 6 repeats shot 5
        assert not any(f["n"] == 3 for f in res["findings"] if f["kind"] == "variety")

    def test_continuity(self, film):
        res = critic.run(film)
        c = kinds(res, "continuity")
        assert (2, "warn") in c and (2, "info") in c          # character and place cut from the prompt
        assert (8, "warn") in c                               # continues, but the place changes
        (film / "face_check.json").write_text(json.dumps({"rows": {"4": {"status": "different"}, "5": {"status": "ok"}}}))
        res = critic.run(film)
        assert (4, "high") in kinds(res, "continuity") and res["flagged"] == [4, 7]

    def test_runtime_against_the_plan(self, film):
        ad.save(film, make_plan(minutes=0.5))
        res = critic.run(film)
        assert [f["kind"] for f in res["findings"]].count("runtime") == 1
        ad.save(film, make_plan(minutes=0.5) | {"runtime_minutes": 0.55})
        assert "runtime" not in {f["kind"] for f in critic.run(film)["findings"]}

    def test_clips_that_are_too_short(self, film):
        (film / "videos" / "ltx").mkdir(parents=True)
        for n, secs in ((1, 4.0), (2, 1.0), (3, 6.9)):
            (film / "videos" / "ltx" / f"shot-{n:04d}.mp4").write_bytes(b"x")
        lengths = {1: 4.0, 2: 1.0, 3: 6.9}
        res = critic.run(film, durations=lambda p: lengths[int(p.stem[-4:])])
        assert kinds(res, "clips") == [(2, "high"), (3, "warn")]

    def test_nothing_to_check(self, fake_root):
        d = fake_root / "projects" / "books" / "empty"
        d.mkdir(parents=True)
        with pytest.raises(ValueError, match="build the CSVs"):
            critic.run(d)


class TestFlagging:
    def test_only_undecided_shots_with_a_high_finding_are_rejected(self, film):
        res = critic.run(film)
        review.set_status(film, ["demo-001#7"], "approved")                          # you already approved shot 7: the critic does not override you
        assert critic.flag_in_review(film, res) == 0
        review.set_status(film, ["demo-001#7"], "pending")
        assert critic.flag_in_review(film) == 1
        v = review.load(film)["demo-001#7"]
        assert v["status"] == "rejected" and v["note"].startswith("critic: the narration takes")

    def test_size_words(self):
        assert [critic.shot_size(t) for t in ("An extreme close-up of an eye", "Medium shot, two men", "Aerial view of a valley", "A man walks")] == ["close", "medium", "wide", "unknown"]


class TestRouteAndCli:
    def test_route(self, server, film):
        st, out = server.api("POST", "/api/critic", {"project": "demo", "flag": True})
        assert st == 200 and out["counts"]["high"] == 1 and out["flagged_in_review"] == 1
        assert server.api("POST", "/api/critic", {"project": "ghost"})[0] == 400
        assert server.api("POST", "/api/critic", {"project": "demo", "clip_seconds": "abc"})[0] == 400

    def test_cli(self, film, run_script):
        code, out = run_script("critic.py", "demo", "--flag")
        assert code is None and "1 high" in out and "shot 7" in out and "flagged 1 shot(s)" in out
        assert "build the CSVs" in str(run_script("critic.py", "ghostbook")[0])


class TestLipsync:
    @pytest.fixture()
    def talk(self, film):
        rows = [
            ("A close-up of Eve's face as she speaks", "Eve", [["Eve", "Come in."]]),
            ("A close-up of a hand on a gate", "Eve", [["NARRATOR", "She waited."]]),                 # voice-over only
            ("A wide shot of the farm", "Eve", [["Adam", "Where are you?"]]),                           # speaks, but far away
            ("A close-up of Adam's eyes", "Adam", [["Adam", "No."]]),
            ("A close-up of the sky", "", [["Adam", "Look."]]),                                         # nobody in shot
            ("A medium shot of Eve at the door", "Eve", [["Eve", "Hello."]])]
        write_csv(film / "all_shots.csv", [{"chapter": "demo-001", "shot": str(i), "prompt": v, "characters": c, "location": "", "continues": ""} for i, (v, c, _) in enumerate(rows, 1)])
        write_csv(film / "audio_shots.csv", [{"chapter": "demo-001", "shot": str(i), "lines_json": json.dumps(ln), "narration": "", "sfx": "", "music": ""} for i, (_, _, ln) in enumerate(rows, 1)])
        (film / "scripts" / "chapter-001.json").write_text(json.dumps({"chapter": "demo-001", "shots": [{"n": i, "visual": v} for i, (v, _, _) in enumerate(rows, 1)]}))
        return film

    def test_only_close_ups_where_a_character_speaks(self, talk):
        res = critic.lipsync_rows(talk)
        assert [r["n"] for r in res["rows"]] == [1, 4] and res["rows"][0]["speaker"] == "Eve" and res["runs"] == [[1, 1], [4, 4]]
        assert [r["n"] for r in critic.lipsync_rows(talk, include_medium=True)["rows"]] == [1, 4, 6]
        assert critic.lipsync_rows(talk, True)["runs"] == [[1, 1], [4, 4], [6, 6]]

    def test_route(self, server, talk):
        st, out = server.api("GET", "/api/lipsync_candidates?project=demo")
        assert st == 200 and [r["n"] for r in out["rows"]] == [1, 4]
        assert [r["n"] for r in server.api("GET", "/api/lipsync_candidates?project=demo&medium=1")[1]["rows"]] == [1, 4, 6]
        assert server.api("GET", "/api/lipsync_candidates?project=ghost")[0] == 400

    def test_no_shots(self, fake_root):
        d = fake_root / "projects" / "books" / "empty"
        d.mkdir(parents=True)
        with pytest.raises(ValueError):
            critic.lipsync_rows(d)
