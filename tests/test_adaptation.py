"""adaptation.py (fitting, checking, editing), screenplay.py (storage, approval, gate), budget.py, and the book_adapt / book_screenplay scripts with a stand-in AI."""
import json
import re

import pytest

import adaptation as ad
import budget
import bookkit
import screenplay as sp


def scene(title, chapters=(1,), seconds=8, importance=3, **kw):
    return {"title": title, "summary": f"{title} happens here in the story", "chapters": list(chapters), "anchor": f"{title} begins", "seconds": seconds,
            "importance": importance, "keep": "condensed", **kw}


class TestFit:
    def test_total_is_exact_and_proportional(self):
        sc = [scene("a", seconds=8), scene("b", seconds=16), scene("c", seconds=8)]
        kept, dropped = ad.fit_clips(sc, 16, 4)
        assert not dropped and sum(s["clips"] for s in kept) == 16 and [s["clips"] for s in kept] == [4, 8, 4] and kept[1]["seconds"] == 32

    def test_leftover_goes_to_the_important_scene_and_comes_from_the_unimportant(self):
        sc = [scene("a", seconds=4, importance=5), scene("b", seconds=4, importance=1), scene("c", seconds=4, importance=3)]
        up, _ = ad.fit_clips(sc, 7, 4)                       # 2 + 2 + 2 in proportion, the extra clip goes to the important scene
        assert [s["clips"] for s in up] == [3, 2, 2]
        down, _ = ad.fit_clips(sc, 5, 4)                     # one clip is taken from the least important scene
        assert [s["clips"] for s in down] == [2, 1, 2]
        down, _ = ad.fit_clips([scene("a", seconds=12, importance=5), scene("b", seconds=12, importance=1)], 5, 4)
        assert [s["clips"] for s in down] == [3, 2] and sum(s["clips"] for s in down) == 5

    def test_drops_least_important_when_the_goal_is_below_one_clip_per_scene(self):
        sc = [scene("a", importance=5), scene("b", importance=1), scene("c", importance=4), scene("d", importance=2)]
        kept, dropped = ad.fit_clips(sc, 2, 4)
        assert [s["title"] for s in kept] == ["a", "c"] and {d["title"] for d in dropped} == {"b", "d"} and sum(s["clips"] for s in kept) == 2

    def test_runtime_shorter_than_a_clip(self):
        with pytest.raises(ad.AdaptationError):
            ad.fit_clips([scene("a")], 0, 4)

    @pytest.mark.parametrize("goal", [1, 5, 7, 40, 333])
    def test_any_goal_is_met(self, goal):
        sc = [scene(str(i), seconds=3 + i * 5, importance=1 + i % 5) for i in range(5)]
        kept, dropped = ad.fit_clips(sc, goal, 4)
        assert sum(s["clips"] for s in kept) == goal and len(kept) + len(dropped) == 5


class TestChecks:
    def test_summary(self):
        ad.check_summary({"summary": "Eve walks into the garden at dawn.", "importance": 4})
        for bad in ({}, {"summary": "no"}, {"summary": "a long enough summary here", "importance": 9}, {"summary": "a long enough summary here", "beats": "x"}):
            with pytest.raises(ValueError):
                ad.check_summary(bad)

    def test_shape(self):
        good = {"logline": "l", "premise": "p", "ending": "e", "acts": [{"name": "I", "purpose": "x", "share": 1, "first_chapter": 1, "last_chapter": 3}]}
        ad.check_shape(good, 3)
        with pytest.raises(ValueError, match="within 1-2"):
            ad.check_shape(good, 2)
        with pytest.raises(ValueError):
            ad.check_shape({**good, "acts": []}, 3)
        with pytest.raises(ValueError):
            ad.check_shape({**good, "logline": " "}, 3)

    def test_scenes(self):
        ad.check_scenes({"scenes": [scene("a", (1, 2))]}, 1, 3)
        for bad in (scene("a", (9,)), {**scene("a"), "anchor": ""}, {**scene("a"), "seconds": 0}, {**scene("a"), "keep": "zoom"}, {**scene("a"), "importance": 7},
                    {**scene("a"), "summary": "no"}, {**scene("a"), "chapters": []}):
            with pytest.raises(ValueError):
                ad.check_scenes({"scenes": [bad]}, 1, 3)
        with pytest.raises(ValueError):
            ad.check_scenes({"scenes": []}, 1, 3)

    def test_anchor_is_matched_loosely(self):
        assert ad.anchor_found("the  old MAN walked", ["Then the old man, walked on."]) and not ad.anchor_found("never said", ["text"]) and not ad.anchor_found("", ["x"])

    def test_acts_are_made_to_cover_the_book(self):
        acts = [{"name": "B", "first_chapter": 5, "last_chapter": 9, "share": 1}, {"name": "A", "first_chapter": 1, "last_chapter": 6, "share": 3}]
        out = ad.normalise_acts(acts, 10, 600)
        assert [(a["first_chapter"], a["last_chapter"]) for a in out] == [(1, 6), (7, 10)] and out[0]["seconds"] == 450 and round(sum(a["share"] for a in out), 3) == 1
        assert len(ad.normalise_acts([{"name": str(i), "first_chapter": 1, "last_chapter": 1, "share": 1} for i in range(4)], 2, 60)) == 2


def make_plan(minutes=2.0):
    shape = {"logline": "A tale.", "premise": "Premise.", "ending": "It ends.",
             "acts": [{"name": "Act I", "purpose": "set up", "share": 1, "first_chapter": 1, "last_chapter": 3},
                      {"name": "Act II", "purpose": "pay off", "share": 1, "first_chapter": 4, "last_chapter": 6}]}
    scs = [[scene("one", (1, 2), 30, 5), scene("two", (3,), 30, 2)], [scene("three", (4, 5), 30, 4), scene("four", (6,), 30, 3)]]
    return ad.build_plan(shape, scs, minutes, 4, 6)


class TestPlan:
    def test_build_plan(self):
        p = make_plan()
        assert [s["id"] for s in p["scenes"]] == ["S001", "S002", "S003", "S004"] and ad.total_clips(p) == 30 and ad.plan_runtime(p)["difference_seconds"] == 0
        assert p["scenes"][0]["act"] == "Act I" and p["cut"] == [] and p["stale"] is False
        with pytest.raises(ad.AdaptationError):
            ad.build_plan({"logline": "l", "premise": "p", "ending": "e", "acts": [{"name": "a", "share": 1, "first_chapter": 1, "last_chapter": 1}]}, [[]], 1, 4, 1)
        with pytest.raises(ad.AdaptationError):
            make_plan(500)

    def test_chapters_not_used_are_listed_as_cut(self):
        shape = {"logline": "l", "premise": "p", "ending": "e", "acts": [{"name": "a", "purpose": "x", "share": 1, "first_chapter": 1, "last_chapter": 4}]}
        p = ad.build_plan(shape, [[scene("x", (1,)), scene("y", (3,))]], 1, 4, 4)
        assert [c.get("chapter") for c in p["cut"]] == [2, 4]

    def test_chapter_clips_share_a_scenes_clips(self):
        p = make_plan()
        cc = ad.chapter_clips(p)
        assert sum(cc.values()) == 30 and set(cc) == {1, 2, 3, 4, 5, 6}
        assert cc[1] - cc[2] in (0, 1)

    def test_pilots(self):
        p = make_plan()
        t = ad.pilot_choice(p, "trailer", 70)
        assert t["kind"] == "trailer" and sum(s["seconds"] for s in p["scenes"] if s["id"] in t["scene_ids"]) <= 70 and "S001" in t["scene_ids"]
        c = ad.pilot_choice(p, "chapters", first=1, last=2)
        assert c["scene_ids"] == ["S001"]
        p["pilot"] = c
        assert [s["id"] for s in ad.active_scenes(p)] == ["S001"] and ad.total_clips(p) == p["scenes"][0]["clips"] and set(ad.chapter_clips(p)) == {1, 2}
        assert ad.pilot_choice(p, "none") == {"kind": "none"}
        for bad in (("chapters", 5, 9), ("chapters", 2, 2)):
            with pytest.raises(ad.AdaptationError):
                ad.pilot_choice(p, *bad[:1], first=bad[1], last=bad[2])
        with pytest.raises(ad.AdaptationError):
            ad.pilot_choice(p, "bogus")
        with pytest.raises(ad.AdaptationError):
            ad.pilot_choice(p, "trailer", 1)
        assert ad.pilot_choice(p, "trailer", 10)["scene_ids"]                       # shorter than every scene: the shortest is taken

    def test_edits(self):
        p = make_plan()
        ad.edit(p, "set_clips", {"id": "S002", "clips": 3})
        assert p["scenes"][1]["clips"] == 3 and p["scenes"][1]["seconds"] == 12
        ad.edit(p, "rename", {"id": "S002", "title": "  Two   Renamed ", "summary": "new summary"})
        assert p["scenes"][1]["title"] == "Two Renamed" and p["scenes"][1]["summary"] == "new summary"
        ad.edit(p, "move", {"id": "S002", "direction": -1})
        assert [s["id"] for s in p["scenes"]][:2] == ["S002", "S001"]
        ad.edit(p, "merge", {"id": "S002"})
        assert p["scenes"][0]["chapters"] == [1, 2, 3] and " / " in p["scenes"][0]["title"] and len(p["scenes"]) == 3
        ad.edit(p, "drop", {"id": "S003"})
        assert len(p["scenes"]) == 2 and p["cut"][-1]["reason"] == "dropped by you"
        for action, body in (("set_clips", {"id": "S001", "clips": 0}), ("move", {"id": "S001", "direction": -1}), ("merge", {"id": p["scenes"][-1]["id"]}),
                             ("explode", {"id": "S001"}), ("drop", {"id": "S999"}), ("rename", {"id": "S001", "title": " "})):
            with pytest.raises(ad.AdaptationError):
                ad.edit(p, action, body)
        ad.edit(p, "drop", {"id": p["scenes"][0]["id"]})
        with pytest.raises(ad.AdaptationError, match="at least one"):
            ad.edit(p, "drop", {"id": p["scenes"][0]["id"]})

    def test_new_ids_never_collide_after_a_merge(self):
        p = make_plan()
        ad.edit(p, "merge", {"id": "S001"})
        ids = [s["id"] for s in p["scenes"]]
        assert len(set(ids)) == len(ids)

    def test_set_pilot_through_edit_and_pilot_follows_scene_changes(self):
        p = make_plan()
        ad.edit(p, "set_pilot", {"kind": "chapters", "first": 4, "last": 6})
        assert p["pilot"]["scene_ids"] == ["S003", "S004"]
        ad.edit(p, "drop", {"id": "S004"})
        assert p["pilot"]["scene_ids"] == ["S003"]

    def test_treatment_and_storage(self, tmp_path):
        p = make_plan()
        ad.save(tmp_path, p)
        assert ad.load(tmp_path)["logline"] == "A tale." and "## Act I" in (tmp_path / "adaptation" / "treatment.md").read_text()
        assert "S001 one" in ad.treatment_md(p)
        (tmp_path / "adaptation" / "adaptation.json").write_text("[]")
        assert ad.load(tmp_path) is None


# ---------------------------------------------------------------------------------------- screenplay
GOOD = {"heading": "int. cave - night", "elements": [{"type": "action", "text": "Rain falls."}, {"type": "dialogue", "character": "eve", "note": "softly", "text": "Come in."}]}


class TestScreenplay:
    def test_check_and_clean(self):
        sp.check_scene(GOOD)
        assert sp.clean_scene(GOOD)["heading"] == "INT. CAVE - NIGHT" and sp.clean_scene(GOOD)["elements"][1]["character"] == "EVE"
        for bad in ({}, {"heading": "", "elements": GOOD["elements"]}, {"heading": "H", "elements": []}, {"heading": "H", "elements": [{"type": "song", "text": "x"}]},
                    {"heading": "H", "elements": [{"type": "dialogue", "text": "x"}]}, {"heading": "H", "elements": [{"type": "action", "text": " "}]},
                    {"heading": "H", "elements": [{"type": "dialogue", "character": "A", "text": "x", "note": 5}]}):
            with pytest.raises(ValueError):
                sp.check_scene(bad)

    def test_save_load_status_approve_and_gate(self, tmp_path):
        plan = make_plan()
        ad.save(tmp_path, plan)
        assert sp.gate(tmp_path) and "not written for every scene" in sp.gate(tmp_path)
        for s in plan["scenes"]:
            sp.save_scene(tmp_path, s["id"], GOOD, edited=False)
        st = sp.status(tmp_path, plan)
        assert st["written"] == 4 and not st["approved"] and "has not been approved" in sp.gate(tmp_path)
        assert sp.approve(tmp_path, plan)["approved"] and sp.gate(tmp_path) is None
        sp.save_scene(tmp_path, "S002", {**GOOD, "heading": "EXT. HILL - DAY"}, edited=True)               # any edit takes the approval away
        assert sp.status(tmp_path, plan)["changed"] == ["S002"] and not sp.status(tmp_path, plan)["approved"] and sp.gate(tmp_path)
        sp.approve(tmp_path, plan)
        assert sp.gate(tmp_path) is None
        sp.clear_approval(tmp_path)
        assert sp.gate(tmp_path)

    def test_approve_needs_every_scene_and_a_plan(self, tmp_path):
        plan = make_plan()
        ad.save(tmp_path, plan)
        with pytest.raises(sp.ScreenplayError, match="no screenplay yet"):
            sp.approve(tmp_path, plan)
        with pytest.raises(sp.ScreenplayError):
            sp.approve(tmp_path, None)
        with pytest.raises(sp.ScreenplayError):
            sp.save_scene(tmp_path, "S001", {"heading": ""}, edited=True)
        with pytest.raises(sp.ScreenplayError):
            sp.scene_file(tmp_path, "../x")

    def test_stale_plan_and_no_plan(self, tmp_path):
        assert sp.gate(tmp_path) is None
        plan = make_plan()
        plan["stale"] = True
        ad.save(tmp_path, plan)
        assert "chapters were changed" in sp.gate(tmp_path)

    def test_pilot_only_needs_the_pilot_scenes(self, tmp_path):
        plan = make_plan()
        plan["pilot"] = ad.pilot_choice(plan, "chapters", first=1, last=2)
        ad.save(tmp_path, plan)
        sp.save_scene(tmp_path, "S001", GOOD, edited=False)
        sp.approve(tmp_path, plan)
        assert sp.gate(tmp_path) is None
        assert "Rain falls." in sp.chapter_brief(tmp_path, plan, 1) and sp.chapter_brief(tmp_path, plan, 5) == ""

    def test_text_and_discard(self, tmp_path):
        plan = make_plan()
        ad.save(tmp_path, plan)
        sp.save_scene(tmp_path, "S001", GOOD, edited=False)
        text = sp.to_text(tmp_path, plan)
        assert "INT. CAVE - NIGHT" in text and "EVE" in text and "(softly)" in text and "[S002 two: not written yet]" in text
        assert sp.dialogue_words(sp.load_scene(tmp_path, "S001")) == 2 and sp.discard(tmp_path) == 1 and sp.discard(tmp_path) == 0


# ---------------------------------------------------------------------------------------- budget
class TestBudget:
    def test_price_matches_the_measured_run(self):
        p = budget.price(1350, "ltx_video_fast_i2v", "kaggle", "NvidiaTeslaT4", 4)
        assert p["video_hours"] == 40.5 and p["measured"] and p["usd"] == 0 and p["days_of_quota"] == 12 and p["paid"] is False

    def test_paid_cloud_and_faster_gpu(self):
        slow = budget.price(100, "wan", "cloud", "NvidiaTeslaT4")
        fast = budget.price(100, "wan", "cloud", "NvidiaH100")
        assert slow["usd"] > fast["gpu_hours"] > 0 and slow["paid"] and slow["days_of_quota"] is None and not slow["measured"]
        assert budget.price(10, "unknown_model", "computer", "local")["video_hours"] == 1.0

    def test_estimate_from_a_runtime_or_a_plan(self, tmp_path):
        e = budget.estimate(None, "ltx_video_fast_i2v", "kaggle", "NvidiaTeslaT4", 10)
        assert e["basis"] == "runtime" and e["full"]["clips"] == 150 and e["pilot"] is None
        with pytest.raises(ad.AdaptationError):
            budget.estimate(None, "x", "kaggle", "T4")
        plan = make_plan()
        plan["pilot"] = ad.pilot_choice(plan, "chapters", first=1, last=2)
        ad.save(tmp_path, plan)
        e = budget.estimate(tmp_path, "ltx_video_fast_i2v", "kaggle", "NvidiaTeslaT4")
        assert e["basis"] == "plan" and e["full"]["clips"] == 30 and e["pilot"]["clips"] < 30 and e["scenes"] == 4
        text = budget.describe(e)
        assert "Whole film" in text and "Pilot (chapters)" in text and "AI writing calls" in text
        assert "free service" in text

    def test_cli(self, fake_root, run_script):
        d = fake_root / "projects" / "books" / "demo"
        d.mkdir(parents=True)
        (d / "chapters.json").write_text(json.dumps({"chapters": [{"n": 1}]}))
        code, out = run_script("budget.py", "demo", "--minutes", "5")
        assert code is None and "75 clips" in out
        assert "say how many minutes" in str(run_script("budget.py", "demo")[0])


# ---------------------------------------------------------------------------------------- the scripts with a stand-in AI
WORDS = "the river runs past the old mill and the people watch it go by in the evening light"


@pytest.fixture()
def novel(fake_root):
    d = fake_root / "projects" / "books" / "novel"
    (d / "chapters").mkdir(parents=True)
    chs = []
    for n in range(1, 7):
        text = f"Chapter {n} opens with event{n} begins. " + (WORDS + ". ") * 20
        (d / "chapters" / f"chapter-{n:03d}.txt").write_text(text)
        chs.append({"n": n, "title": f"Chapter {n}", "words": len(text.split()), "chars": len(text)})
    (d / "chapters.json").write_text(json.dumps({"method": "chapter", "pdf": "novel.txt", "chapters": chs}))
    (d / "novel.json").write_text(json.dumps({"title": "N", "setting": "s", "visual_style": "v", "music_theme": "m",
                                              "characters": [{"name": "Eve", "token": "a woman", "voice": "female"}], "locations": []}))
    return d


def stand_in(calls, bad_anchor=False, fail_summary=None):
    def llm(prompt, system, validate=None, **kw):
        calls.append(prompt)
        if m := re.search(r'Book chapter (\d+) "', prompt):
            if fail_summary == int(m.group(1)):
                raise RuntimeError("model down")
            d = {"summary": f"Things happen in chapter {m.group(1)} of the story.", "characters": ["Eve"], "beats": ["a", "b"], "locations": ["mill"], "importance": 3 + int(m.group(1)) % 3}
        elif '"logline"' in prompt:
            d = {"logline": "A river tale.", "premise": "People by a river.", "ending": "The river runs on.",
                 "acts": [{"name": "Act I", "purpose": "begin", "share": 0.5, "first_chapter": 1, "last_chapter": 3},
                          {"name": "Act II", "purpose": "end", "share": 0.5, "first_chapter": 4, "last_chapter": 6}]}
        elif "Choose the scenes of this act" in prompt:
            lo, hi = map(int, re.search(r"from chapters (\d+) to (\d+)", prompt).groups())
            d = {"scenes": [{"title": f"Scene of chapter {n}", "summary": f"What happens in chapter {n} of the book", "chapters": [n],
                             "anchor": "not in the book at all" if bad_anchor else f"event{n} begins", "seconds": 8, "importance": 3, "keep": "condensed",
                             "location": "mill", "characters": ["Eve"], "time_of_day": "day"} for n in range(lo, hi + 1)]}
        elif "Write the scene as a screenplay" in prompt:
            d = {"heading": "ext. mill - day", "elements": [{"type": "action", "text": "The river runs."}, {"type": "dialogue", "character": "Eve", "text": "Look."}]}
        else:
            raise AssertionError("unexpected prompt " + prompt[:80])
        if validate:
            validate(d)
        return d
    return llm


class TestAdaptScript:
    def test_full_run_caches_summaries_and_fits_the_runtime(self, novel, run_script, monkeypatch):
        calls = []
        monkeypatch.setattr(bookkit, "llm_json", stand_in(calls))
        code, out = run_script("book_adapt.py", "novel", "--minutes", "1")
        plan = ad.load(novel)
        assert code is None and len(plan["scenes"]) == 6 and ad.total_clips(plan) == 15 and plan["acts"][1]["first_chapter"] == 4
        assert len(calls) == 6 + 1 + 2 and "treatment written" in out and (novel / "adaptation" / "treatment.md").exists()
        assert all(s["anchor_found"] for s in plan["scenes"]) and (novel / "adaptation" / "summaries" / "chapter-006.json").exists()
        calls.clear()
        run_script("book_adapt.py", "novel", "--minutes", "2")                   # summaries are reused: only 1 + 2 calls
        assert len(calls) == 3 and ad.total_clips(ad.load(novel)) == 30

    def test_fit_only_makes_no_ai_calls(self, novel, run_script, monkeypatch):
        monkeypatch.setattr(bookkit, "llm_json", stand_in([]))
        run_script("book_adapt.py", "novel", "--minutes", "1")
        monkeypatch.setattr(bookkit, "llm_json", stand_in(calls := []))
        code, out = run_script("book_adapt.py", "novel", "--minutes", "0.5", "--fit-only")
        assert code is None and calls == [] and ad.total_clips(ad.load(novel)) == 8
        assert ad.plan_runtime(ad.load(novel))["minutes"] == 0.53

    def test_old_screenplay_is_removed_with_a_new_plan(self, novel, run_script, monkeypatch):
        monkeypatch.setattr(bookkit, "llm_json", stand_in([]))
        run_script("book_adapt.py", "novel", "--minutes", "1")
        sp.save_scene(novel, "S001", GOOD, edited=True)
        code, out = run_script("book_adapt.py", "novel", "--minutes", "1")
        assert not (novel / "screenplay").exists() and "old screenplay" in out

    def test_paraphrased_anchors_are_flagged(self, novel, run_script, monkeypatch):
        monkeypatch.setattr(bookkit, "llm_json", stand_in([], bad_anchor=True))
        code, out = run_script("book_adapt.py", "novel", "--minutes", "1")
        assert code is None and "was not found in the book text" in out and not ad.load(novel)["scenes"][0]["anchor_found"]

    def test_failures_and_bad_arguments(self, novel, run_script, monkeypatch):
        monkeypatch.setattr(bookkit, "llm_json", stand_in([], fail_summary=3))
        code, out = run_script("book_adapt.py", "novel", "--minutes", "1")
        assert "could not summarise chapters [3]" in str(code) and ad.load(novel) is None
        assert "--minutes must be" in str(run_script("book_adapt.py", "novel", "--minutes", "999")[0])
        assert "--clip-seconds" in str(run_script("book_adapt.py", "novel", "--clip-seconds", "99")[0])
        assert "nothing to refit" in str(run_script("book_adapt.py", "novel", "--fit-only")[0])
        assert "run book_ingest" in str(run_script("book_adapt.py", "ghostbook")[0])

    def test_focus_and_long_chapter_excerpt(self, novel, run_script, monkeypatch):
        (novel / "chapters" / "chapter-002.txt").write_text(("word " * 12000).strip())
        calls = []
        monkeypatch.setattr(bookkit, "llm_json", stand_in(calls))
        run_script("book_adapt.py", "novel", "--minutes", "1", "--focus", "follow Eve")
        long_prompt = next(c for c in calls if 'Book chapter 2 "' in c)
        assert "[...]" in long_prompt and len(long_prompt.split()) < 6000
        assert any("The film must follow: follow Eve" in c for c in calls)


class TestScreenplayScript:
    @pytest.fixture()
    def planned(self, novel, run_script, monkeypatch):
        monkeypatch.setattr(bookkit, "llm_json", stand_in([]))
        run_script("book_adapt.py", "novel", "--minutes", "1")
        return novel

    def test_writes_every_scene_and_keeps_edited_ones(self, planned, run_script, monkeypatch):
        sp.save_scene(planned, "S002", {"heading": "MINE", "elements": [{"type": "action", "text": "Hand written."}]}, edited=True)
        calls = []
        monkeypatch.setattr(bookkit, "llm_json", stand_in(calls))
        code, out = run_script("book_screenplay.py", "novel")
        assert code == 0 and len(calls) == 5 and "failed scenes: none" in out
        assert sp.load_scene(planned, "S002")["heading"] == "MINE" and sp.load_scene(planned, "S001")["heading"] == "EXT. MILL - DAY"
        calls.clear()
        run_script("book_screenplay.py", "novel")
        assert calls == []                                                          # resumable
        run_script("book_screenplay.py", "novel", "--force")
        assert len(calls) == 5 and sp.load_scene(planned, "S002")["heading"] == "MINE"        # --force still keeps a scene you edited

    def test_only_some_scenes_and_errors(self, planned, run_script, monkeypatch):
        calls = []
        monkeypatch.setattr(bookkit, "llm_json", stand_in(calls))
        run_script("book_screenplay.py", "novel", "--scenes", "S001,S003")
        assert len(calls) == 2 and any('Scene S001 "' in c and "event1 begins" in c for c in calls)         # the book text starts at the scene's anchor
        assert "none of those scenes" in str(run_script("book_screenplay.py", "novel", "--scenes", "S099")[0])
        assert "run book_adapt" in str(run_script("book_screenplay.py", "ghostbook")[0])

    def test_one_failed_scene_is_reported(self, planned, run_script, monkeypatch):
        def flaky(prompt, system, validate=None, **kw):
            if "chapter 3 of the book" in prompt:
                raise RuntimeError("down")
            return stand_in([])(prompt, system, validate=validate)
        monkeypatch.setattr(bookkit, "llm_json", flaky)
        code, out = run_script("book_screenplay.py", "novel")
        assert code == 1 and "scene S003: FAILED" in out and sp.load_scene(planned, "S001")


class TestBookWriteUsesThePlan:
    def test_shots_follow_the_plan_and_unused_chapters_are_skipped(self, novel, run_script, monkeypatch):
        monkeypatch.setattr(bookkit, "llm_json", stand_in([]))
        run_script("book_adapt.py", "novel", "--minutes", "1", "--clip-seconds", "4")
        plan = ad.load(novel)
        ad.edit(plan, "drop", {"id": "S006"})
        ad.save(novel, plan)
        sp.save_scene(novel, "S001", GOOD, edited=True)

        seen = []

        def writer(prompt, system, validate=None, **kw):
            seen.append(prompt)
            n = int(re.search(r"with exactly (\d+) shots", prompt).group(1))
            d = {"shots": [{"n": i, "visual": "a wide view of a river and an old mill", "characters": ["Eve"], "narration": "n", "speaker": "NARRATOR", "sfx": "water", "music": "harp",
                            "location": "", "continues": False} for i in range(1, n + 1)]}
            if validate:
                validate(d)
            return d
        monkeypatch.setattr(bookkit, "llm_json", writer)
        code, out = run_script("book_write.py", "novel")
        assert code == 0
        written = sorted(p.name for p in (novel / "scripts").glob("chapter-*.json"))
        assert written == [f"chapter-00{n}.json" for n in range(1, 6)]                              # chapter 6 was dropped from the plan
        counts = {int(f.stem[-3:]): len(json.loads(f.read_text())["shots"]) for f in (novel / "scripts").glob("chapter-*.json")}
        assert counts == ad.chapter_clips(plan)
        assert any("SCREENPLAY for the scenes taken from this chapter" in p and "Rain falls." in p for p in seen)

    def test_a_stale_plan_is_ignored(self, novel, run_script, monkeypatch):
        monkeypatch.setattr(bookkit, "llm_json", stand_in([]))
        run_script("book_adapt.py", "novel", "--minutes", "1")
        plan = ad.load(novel)
        plan["stale"] = True
        ad.save(novel, plan)
        code, out = run_script("book_write.py", "novel", "--dry-run")
        assert code == 0 and "6 chapters" in out
