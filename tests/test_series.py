"""M14: episodes (the Development Executive's split, episode books with their part of the source, sharing the series' continuity book, styles,
approvals and voices; next episode), the production queue, and the marketing kit (plan checks, trailer 16:9 + 9:16, three teasers with
captions, poster, thumbnail, captions.txt) per style."""
import json
import subprocess

import pytest

import clips
import edl
import gates
import layout
import marketing as mk
import pictures as px
import series
import sound_design as sd
import sources as src
from test_clips import make_clip
from test_pictures import approve_everything_before_pictures, render_all
from test_read_it_in import STORY


@pytest.fixture
def book4(fake_root):
    d = fake_root / "projects" / "books" / "door"
    (d / "chapters").mkdir(parents=True)
    for n in range(1, 5):
        (d / "chapters" / f"chapter-{n:03d}.txt").write_text(f"Chapter {n}. " + STORY)
    (d / "chapters.json").write_text(json.dumps({"chapters": [{"n": n, "title": f"Chapter {n}"} for n in range(1, 5)]}))
    return d


class TestSeries:
    def test_split_episodes_and_share(self, book4):
        (book4 / "door.json").write_text(json.dumps({"characters": [{"name": "MARA", "token": "a tall woman", "voice": "female", "personality": {}}]}))
        (book4 / "styles" / "anime").mkdir(parents=True)
        (book4 / "styles" / "anime" / "card.json").write_text("{}")
        (book4 / "gates.json").write_text(json.dumps({"continuity": {"hash": "x"}, "shotlist": {"hash": "y"}}))
        (book4 / "sound").mkdir()
        (book4 / "sound" / "plan.json").write_text(json.dumps({"cast": {"MARA": {"voice": "bf_emma"}}, "narrator": {"voice": "bm_george"}, "lines": [1]}))
        d = series.split(book4, series.fake_ask(), 2, lambda t: None)
        assert [e["slug"] for e in d["episodes"]] == ["door_e01", "door_e02"] and d["episodes"][1]["recap"] == "Mara found the door."
        ep2 = layout.find_dir("door_e02")
        text = src.document(ep2, "s001").text
        assert text.startswith("Previously: Mara found the door.") and "=== Chapter 3 ===" in text and "=== Chapter 1 ===" not in text
        assert json.loads((ep2 / "door_e02.json").read_text())["characters"][0]["name"] == "MARA" and (ep2 / "styles" / "anime" / "card.json").is_file()
        g = json.loads((ep2 / "gates.json").read_text())
        assert "continuity" in g and "shotlist" not in g                                      # shared parts keep their approval, the episode's own do not
        assert json.loads((ep2 / "sound" / "series_cast.json").read_text()) == {"cast": {"MARA": {"voice": "bf_emma"}}, "narrator": {"voice": "bm_george"}}
        assert series.series_of(ep2) == book4 and series.next_episode(book4)["slug"] == "door_e01"
        (layout.find_dir("door_e01") / "readin").mkdir()
        (layout.find_dir("door_e01") / "readin" / "summary.json").write_text("{}")
        assert series.next_episode(book4)["slug"] == "door_e02"
        with pytest.raises(series.SeriesError):
            series.sync(book4)

    def test_episode_voices_come_from_the_series(self, fake_root):
        d = fake_root / "projects" / "books" / "door"
        approve_everything_before_pictures(d)
        (d / "sound").mkdir(exist_ok=True)
        (d / "sound" / "series_cast.json").write_text(json.dumps({"cast": {"MARA": {"voice": "bf_emma", "emotion": "calm"}}, "narrator": {"voice": "bm_lewis", "emotion": "warm"}}))
        plan = sd.write_plan(d, sd.fake_ask(d), lambda t: None)
        assert plan["cast"]["MARA"]["voice"] == "bf_emma" and plan["narrator"]["voice"] == "bm_lewis"

    def test_bad_splits(self):
        for bad in ({"episodes": []}, {"episodes": [{"title": "x"}]}, {"episodes": [{"title": "a", "summary": "b", "hook": "c", "cliffhanger": "d", "parts": "1"}]}):
            with pytest.raises(ValueError):
                series.check_split(bad)


@pytest.fixture
def filmed(fake_root):
    pytest.importorskip("imageio_ffmpeg")
    d = fake_root / "projects" / "books" / "door"
    approve_everything_before_pictures(d)
    sd.write_plan(d, sd.fake_ask(d), lambda t: None)
    px.write_prompts(d)
    render_all(d)
    for row in range(1, 10):
        px.approve(d, "claymation", row)
    px.approve_all_ready(d)
    c = edl.assemble(d)
    for v in edl.cut(c)["tracks"]["video"]:
        v["seconds"] = 5.0
    edl.save(d, c)
    clips.write_motion(d, clips.fake_ask(), lambda t: None)
    setdir = layout.find_dir(clips.prepare(d, "claymation")["set"])
    for row in range(1, 10):
        make_clip(setdir / "videos" / "ltx_video_fast_i2v" / f"shot-{row:04d}.mp4", 5.0)
        clips.review(d, "claymation", row, approved=True)
    clips.approve_all(d, "claymation")
    return d


class TestMarketing:
    def test_needs_the_approved_edit(self, filmed):
        with pytest.raises(mk.MarketingError, match="edit"):
            mk.write_plan(filmed, mk.fake_ask())

    def test_plan_and_kit(self, filmed):
        gates.approve(filmed, "edit", edl.load(filmed)["cuts"])
        roles = []
        fake = mk.fake_ask()
        p = mk.write_plan(filmed, lambda pr, r, s, v: (roles.append(r), fake(pr, r, s, v))[1])
        assert roles == [["trailer_editor", "producer"]] and 30 <= sum(x["seconds"] for x in p["trailer"]) <= 90 and len(p["teasers"]) == 3
        out = mk.render(filmed, "claymation", {"wide": (160, 90), "tall": (90, 160), "poster": (120, 180), "thumb": (160, 90)})
        kit = filmed / "exports" / "marketing_claymation"
        assert sorted(out["files"]) == sorted(["trailer_16x9.mp4", "trailer_9x16.mp4", "teaser_1.mp4", "teaser_2.mp4", "teaser_3.mp4", "poster.png", "thumbnail.png", "captions.txt"])
        probe = subprocess.run([mk.render_cut.ffmpeg(), "-i", str(kit / "trailer_9x16.mp4")], capture_output=True, text=True).stderr
        assert "90x160" in probe
        from PIL import Image
        with Image.open(kit / "poster.png") as im:
            assert im.size == (120, 180)
        caps = (kit / "captions.txt").read_text()
        assert "LOGLINE: A keeper finds a door." in caps and "TEASER 3: Teaser 3" in caps and "POST 2:" in caps

    @pytest.mark.parametrize("change", [{"trailer": [{"row": 1, "seconds": 5}]}, {"teasers": []}, {"poster": {"row": 99}}, {"title": ""},
                                        {"trailer": [{"row": 1, "seconds": 15}] * 7}])
    def test_bad_plans(self, change):
        good = {"title": "t", "logline": "l", "tagline": "g", "trailer": [{"row": 1, "seconds": 10}] * 4,
                "teasers": [{"shots": [{"row": 1, "seconds": 3}], "caption": "c"}] * 3, "poster": {"row": 1}, "thumbnail": {"row": 2}, "posts": []}
        with pytest.raises(ValueError):
            mk.checker(9)({**good, **change})


class TestRoutes:
    def test_over_http(self, server, book):
        src.store(book, src.from_idea(STORY), True)
        series.split(book, series.fake_ask(), 0, lambda t: None)
        st, j = server.api("GET", "/api/series?project=demo")
        assert st == 200 and j["episodes"][0]["slug"] == "demo_e01" and j["next"] == "demo_e01" and j["episodes"][0]["state"] == "ready to read in"
        st, j = server.api("GET", "/api/series?project=demo_e01")
        assert j["series"] == "demo"
        st, j = server.api("POST", "/api/series_sync", {"project": "demo_e01"})
        assert st == 200 and "continuity book" in j["synced"]
        st, j = server.api("GET", "/api/queue")
        assert st == 200 and j["waiting"] == []
        st, j = server.api("POST", "/api/queue_add", {"projects": []})
        assert st == 400
        st, j = server.api("POST", "/api/marketing_render", {"project": "demo"})
        assert st == 400 and "plan" in j["error"]
        st, j = server.api("GET", "/api/marketing?project=demo")
        assert j == {"plan": None, "kits": {}}
