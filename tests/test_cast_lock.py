"""Locked cast, costume and place per scene: shot -> scene mapping, the lock file, prompts and keyframe reference pictures."""
import csv
import json

import pytest

import adaptation as ad
import cast_lock as cl
import character_tokens as ct
import make_keyframes_csv as mk
from test_adaptation import make_plan


def png(path, colour="red", size=(64, 48)):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(path)


class TestShotScene:
    def test_shots_are_shared_out_in_proportion(self):
        p = make_plan()                                   # S001 = chapters 1,2 (8 clips), S002 = chapter 3 (7 clips)
        p["scenes"][0]["chapters"] = [1]
        p["scenes"][0]["clips"] = 6
        p["scenes"][1]["chapters"] = [1]
        p["scenes"][1]["clips"] = 2
        ids = [ad.shot_scene(p, 1, i, 8) for i in range(1, 9)]
        assert ids == ["S001"] * 6 + ["S002"] * 2
        assert ad.shot_scene(p, 6, 1, 1) == "S004" and ad.shot_scene(p, 99, 1, 3) is None and ad.shot_scene(p, 1, 1, 0) is None

    def test_a_scene_over_two_chapters_gives_each_a_share(self):
        p = make_plan()
        assert ad.shot_scene(p, 2, 1, 4) == "S001" and ad.shot_scene(p, 5, 1, 4) == "S003"

    def test_pilot_scenes_only(self):
        p = make_plan()
        p["pilot"] = ad.pilot_choice(p, "chapters", first=4, last=6)
        assert ad.shot_scene(p, 1, 1, 4) is None


class TestLockFile:
    @pytest.fixture()
    def plan(self):
        return make_plan()

    def test_lock_unlock_and_summary(self, fake_root, tmp_path, plan):
        pic = fake_root / "projects" / "characters" / "main" / "references" / "eve" / "cloak.png"
        png(pic)
        rel = pic.relative_to(fake_root).as_posix()
        cl.set_lock(tmp_path, plan, "S002", "character", "Eve", token="  Eve:  grey   cloak ", reference=rel)
        assert cl.load(tmp_path)["S002"]["characters"]["Eve"] == {"token": "Eve: grey cloak", "reference": rel}
        assert cl.token_overrides(cl.load(tmp_path), "S002") == {"eve": "Eve: grey cloak"} and cl.token_overrides(cl.load(tmp_path), "S001") == {}
        assert cl.reference_for(cl.load(tmp_path), "S002", "eve") == fake_root / rel and cl.reference_for(cl.load(tmp_path), "S002") is None
        cl.set_lock(tmp_path, plan, "S002", "location", reference=rel)
        assert cl.reference_for(cl.load(tmp_path), "S002") == fake_root / rel
        assert cl.summary(cl.load(tmp_path), plan) == {"scenes": 1, "characters": 1, "locations": 1, "orphans": []}
        cl.set_lock(tmp_path, plan, "S002", "character", "Eve")                       # unlock
        cl.set_lock(tmp_path, plan, "S002", "location")
        assert cl.load(tmp_path) == {} and not cl.reference_for({}, None)

    def test_refusals(self, fake_root, tmp_path, plan):
        outside = fake_root / "secret.png"
        png(outside)
        for args in (("S999", "character", "Eve"), ("S001", "bogus", "Eve"), ("S001", "character", " "), ("S001", "location", "", "a token")):
            with pytest.raises(cl.LockError):
                cl.set_lock(tmp_path, plan, *args)
        with pytest.raises(cl.LockError, match="inside the projects"):
            cl.set_lock(tmp_path, plan, "S001", "character", "Eve", reference="secret.png")
        with pytest.raises(cl.LockError, match="inside the projects"):
            cl.set_lock(tmp_path, plan, "S001", "character", "Eve", reference="projects/../secret.png")
        with pytest.raises(cl.LockError, match="not a picture"):
            cl.set_lock(tmp_path, plan, "S001", "character", "Eve", reference="projects/nothing.png")
        with pytest.raises(cl.LockError, match="at most"):
            cl.set_lock(tmp_path, plan, "S001", "character", "Eve", token="x" * 500)
        (tmp_path / "cast_lock.json").write_text("[]")
        assert cl.load(tmp_path) == {} and cl.summary({"S404": {}}, plan)["orphans"] == ["S404"]

    def test_shot_context(self, tmp_path):
        assert cl.shot_context(tmp_path)(1, 1, 3) is None
        p = make_plan()
        ad.save(tmp_path, p)
        assert cl.shot_context(tmp_path)(1, 1, 4) == "S001"
        p["stale"] = True
        ad.save(tmp_path, p)
        assert cl.shot_context(tmp_path)(1, 1, 4) is None


@pytest.fixture()
def planned_book(book):
    """books/demo with a plan whose scenes S001..S004 cover chapters 1..6, chapter files and one scripted chapter."""
    ad.save(book, make_plan())
    cont = json.loads((book / "demo.json").read_text())
    cont["characters"] = [{"name": "Eve", "token": "Eve: a woman in a red dress", "voice": "female"}]
    (book / "demo.json").write_text(json.dumps(cont))
    (book / "scripts").mkdir()
    shots = [{"n": i, "visual": f"Eve stands in the garden, view {i}", "characters": ["Eve"], "narration": "n", "speaker": "NARRATOR", "voice": "", "sfx": "", "music": "",
              "negative": "", "location": "", "continues": False, "prompt": "old"} for i in range(1, 5)]
    (book / "scripts" / "chapter-001.json").write_text(json.dumps({"chapter": 1, "title": "One", "narration_mode": "condensed", "shots": shots}))
    return book


def test_recompose_uses_the_locked_costume_only_in_that_scene(planned_book, fake_root):
    import bookkit as bk
    plan = ad.load(planned_book)
    plan["scenes"][0]["chapters"] = [1]                                          # S001 owns the first half of chapter 1, S002 the rest
    plan["scenes"][0]["clips"], plan["scenes"][1]["chapters"], plan["scenes"][1]["clips"] = 2, [1], 2
    ad.save(planned_book, plan)
    cl.set_lock(planned_book, plan, "S002", "character", "Eve", token="Eve: a woman in a grey travelling cloak")
    bk.recompose_scripts(planned_book, scene_of=cl.shot_context(planned_book), lock=cl.load(planned_book))
    shots = json.loads((planned_book / "scripts" / "chapter-001.json").read_text())["shots"]
    assert [s["scene_id"] for s in shots] == ["S001", "S001", "S002", "S002"]
    assert "red dress" in shots[0]["prompt"] and "grey travelling cloak" in shots[2]["prompt"] and "red dress" not in shots[3]["prompt"]


def test_keyframes_use_the_picture_locked_for_the_scene(planned_book, fake_root):
    plan = ad.load(planned_book)
    plan["scenes"][0]["chapters"], plan["scenes"][0]["clips"] = [1], 2
    plan["scenes"][1]["chapters"], plan["scenes"][1]["clips"] = [1], 2
    ad.save(planned_book, plan)
    ct.save_character({"name": "Eve", "series": "main", "visual_token": "EVE: a woman"})
    png(ct.get_reference_dir("main", "Eve") / "ref_01.png", "red", (900, 700))
    cloak = ct.get_reference_dir("main", "Eve") / "cloak.png"
    png(cloak, "grey", (900, 700))
    png(planned_book / "location_refs" / "garden.png")
    rel = cloak.relative_to(fake_root).as_posix()
    cl.set_lock(planned_book, plan, "S002", "character", "Eve", reference=rel)
    cl.set_lock(planned_book, plan, "S002", "location", reference=rel)
    (planned_book / "all_shots.csv").write_text("chapter,shot,prompt,characters,location,seed\n" + "".join(f"demo-001,{i},shot {i},Eve,Garden,{i}\n" for i in range(1, 5)))
    mk.main(["demo", "--width", "1024", "--height", "1024", "--refs", "main", "--max-refs", "2"])
    with open(planned_book / "keyframes.csv", newline="") as f:
        refs = [r["refs"] for r in csv.DictReader(f)]
    assert refs == ["ref-eve.png|ref-place-garden.png"] * 2 + ["ref-eve-s002.png|ref-place-s002-cloak.png"] * 2
    assert (planned_book / "keyframe_refs" / "ref-eve-s002.png").is_file()


class TestApi:
    @pytest.fixture()
    def planned(self, planned_book):
        (planned_book / "chapters.json").write_text(json.dumps({"chapters": [{"n": n, "title": f"C{n}", "words": 10} for n in range(1, 7)]}))
        plan = ad.load(planned_book)
        plan["scenes"][0]["characters"] = ["Eve", "Nobody"]
        ad.save(planned_book, plan)
        return planned_book

    def test_read_lock_and_unlock(self, server, planned, fake_root):
        out = server.api("GET", "/api/cast_lock?project=demo")[1]
        s1 = out["scenes"][0]
        assert [c["name"] for c in s1["characters"]] == ["Eve"] and s1["characters"][0]["current"] == "Eve: a woman in a red dress" and out["summary"]["characters"] == 0
        pic = fake_root / "projects" / "books" / "demo" / "location_refs" / "cave.png"
        png(pic)
        rel = pic.relative_to(fake_root).as_posix()
        out = server.api("POST", "/api/cast_lock", {"project": "demo", "scene": "S001", "kind": "location", "reference": rel})[1]
        assert out["scenes"][0]["place"]["locked"]["reference"] == rel and rel in out["scenes"][0]["place"]["references"]
        out = server.api("POST", "/api/cast_lock", {"project": "demo", "scene": "S001", "kind": "character", "name": "Eve", "token": "Eve: in armour"})[1]
        assert out["scenes"][0]["characters"][0]["current"] == "Eve: in armour" and out["summary"] == {**out["summary"], "characters": 1, "locations": 1}
        out = server.api("POST", "/api/cast_lock", {"project": "demo", "scene": "S001", "kind": "character", "name": "Eve"})[1]
        assert out["summary"]["characters"] == 0

    def test_errors_and_busy(self, server, planned, monkeypatch):
        assert server.api("POST", "/api/cast_lock", {"project": "demo", "scene": "S999", "kind": "location"})[0] == 400
        assert server.api("POST", "/api/cast_lock", {"project": "demo", "scene": "S001", "kind": "location", "reference": "etc/passwd"})[0] == 400
        assert server.api("GET", "/api/cast_lock?project=ghost")[0] == 400
        from studio_app.jobs import JOB
        monkeypatch.setattr(JOB, "running", True)
        assert server.api("POST", "/api/cast_lock", {"project": "demo", "scene": "S001", "kind": "location"})[0] == 400

    def test_build_step_recompose_option(self, server, planned):
        import screenplay as sp
        plan = ad.load(planned)
        for sc in plan["scenes"]:
            sp.save_scene(planned, sc["id"], {"heading": "INT. A - DAY", "elements": [{"type": "action", "text": "x"}]}, edited=False)
        sp.approve(planned, plan)                                                   # shots are only built from an approved screenplay
        st, out = server.api("POST", "/api/plan", {"project": "demo", "recompose": True, "look": "live_action", "steps": {"build": True}})
        assert "book_build.py demo --minutes 10.0 --recompose --look live_action" in out["steps"][0]["cmd"]
