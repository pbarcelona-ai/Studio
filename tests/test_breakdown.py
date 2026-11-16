"""M4: the style-neutral continuity book with personalities, the director's breakdown + shot list with the continuity and pacing checks,
hand edits, and the review gates."""
import json

import pytest

import continuity_book as cb
import gates
import read_it_in as ri
import shot_list as sl
import sources as src
from test_read_it_in import STORY


@pytest.fixture
def scripted(tmp_path):
    src.store(tmp_path, src.from_idea(STORY, "Door"), True)
    ri.ReadItIn(tmp_path, ri.fake_ask(tmp_path)).run()
    return tmp_path


def good_char(**kw):
    return {"name": "MARA", "token": "a woman in her thirties, tall, short black hair, grey eyes, navy coat", "voice": "female",
            "personality": dict.fromkeys(cb.PERSONALITY, "x"), **kw}


class TestContinuity:
    def test_written_from_the_screenplay(self, scripted):
        seen = []
        fake = cb.fake_ask(scripted)

        def ask(prompt, roles, step, validate):
            seen.append((roles, prompt))
            return fake(prompt, roles, step, validate)
        (scripted / f"{scripted.name}.json").write_text(json.dumps({"visual_style": "kept", "title": "Old"}))
        book = cb.write(scripted, ask)
        assert seen[0][0] == ["script_supervisor", "casting_director", "production_designer"] and "SCREENPLAY (with each scene's block)" in seen[0][1]
        assert book["characters"][0]["name"] == "MARA" and set(book["characters"][0]["personality"]) == set(cb.PERSONALITY)
        assert book["style_neutral"] and book["visual_style"] == "kept" and book["props"][0]["name"] == "the lamp"
        assert (scripted / f"{scripted.name}.json.bak").is_file() and cb.load(scripted)["characters"]

    @pytest.mark.parametrize("token", ["a photorealistic woman", "a 3D render of a man", "an anime girl", "a Pixar-style boy", "claymation fox"])
    def test_rendering_words_are_refused(self, token):
        with pytest.raises(ValueError, match="rendering words"):
            cb.check({"characters": [good_char(token=token)]})

    def test_identity_words_are_fine(self):
        cb.check({"characters": [good_char()], "props": [{"name": "pot", "token": "a clay pot with a felt lid and ink stains"}]})

    @pytest.mark.parametrize("bad", [{"characters": []}, {"characters": [good_char(voice="robot")]}, {"characters": [good_char(personality={"temperament": "x"})]},
                                     {"characters": [good_char(token="x" * 300)]}])
    def test_bad_books(self, bad):
        with pytest.raises(ValueError):
            cb.check(bad)

    def test_edit_by_hand(self, scripted):
        cb.write(scripted, cb.fake_ask(scripted))
        new = cb.edit(scripted, "characters", "MARA", {"token": "a woman of forty, grey streak in her black hair, red scarf", "name": "ignored"})
        assert new["name"] == "MARA" and "red scarf" in cb.load(scripted)["characters"][0]["token"]
        with pytest.raises(ValueError, match="rendering"):
            cb.edit(scripted, "characters", "MARA", {"token": "photorealistic woman"})
        with pytest.raises(ValueError, match="no location"):
            cb.edit(scripted, "locations", "nowhere", {"token": "x"})
        cb.edit(scripted, "props", "the lamp", {"token": "a brass lamp, dented"})

    def test_no_screenplay_yet(self, tmp_path):
        with pytest.raises(cb.ContinuityError, match="Read it in"):
            cb.write(tmp_path, cb.fake_ask(tmp_path))


class TestShotList:
    @pytest.fixture
    def listed(self, scripted):
        cb.write(scripted, cb.fake_ask(scripted))
        said = []
        sl.write(scripted, sl.fake_ask(scripted), said.append)
        return scripted, said

    def test_written_per_scene_with_checks(self, listed):
        pdir, said = listed
        d = sl.load(pdir)
        assert len(d["scenes"]) == 3 and all(len(sc["shots"]) == 3 for sc in d["scenes"])
        s = d["scenes"][0]["shots"][1]
        assert s["type"] == "MCU" and s["lens_mm"] == 50 and s["movement"] == "push in" and s["characters"] == ["MARA"] and s["source"] == "ai"
        assert set(d["scenes"][0]["breakdown"]) == {"intent", "emotional_beat", "blocking", "performance"}
        assert d["checks"]["continuity"][0]["fixed"] and d["scenes"][0]["shots"][0]["lighting"].startswith("warm lamplight")
        assert "Your director and cinematographer are breaking down scene 2 of 3" in said and said[-1].startswith("Done:")

    def test_a_second_run_uses_the_cache(self, listed):
        pdir, _ = listed
        calls = []
        fake = sl.fake_ask(pdir)
        sl.write(pdir, lambda p, r, s, v: (calls.append(s), fake(p, r, s, v))[1])
        assert [c for c in calls if c.startswith("shot list: scene")] == []

    def test_pacing_fits_the_target(self):
        shots = [{"seconds": 4.0, "priority": p} for p in (1, 2, 3) * 10]                 # 120 s
        d = {"scenes": [{"shots": shots}], "target_seconds": 60}
        note = sl.pace(d)
        assert note["changed"] == 30 and 54 <= note["runtime"] <= 66 and "trimmed" in note["note"]
        assert all(sl.MIN_SECONDS <= s["seconds"] <= sl.MAX_SECONDS for s in shots)
        p1 = [s["seconds"] for s in shots if s["priority"] == 1][0]
        p3 = [s["seconds"] for s in shots if s["priority"] == 3][0]
        assert p3 < p1                                                                      # the nice-to-have shots give the most
        assert sl.pace({"scenes": [{"shots": [{"seconds": 4.0, "priority": 2}]}], "target_seconds": 4.2})["changed"] == 0

    def test_hand_edits_and_reorder(self, listed):
        pdir, _ = listed
        sl.edit_shot(pdir, "S001", 2, {"action": "She lights the lamp twice.", "seconds": 6, "bogus": 1})
        d = sl.load(pdir)
        assert d["scenes"][0]["shots"][1]["action"] == "She lights the lamp twice." and "bogus" not in d["scenes"][0]["shots"][1]
        with pytest.raises(sl.ShotListError, match="seconds"):
            sl.edit_shot(pdir, "S001", 2, {"seconds": 0})
        sl.move_shot(pdir, "S001", 3, 1)
        assert [s["action"] for s in sl.load(pdir)["scenes"][0]["shots"]][0] == "Her eyes on the sea." and sl.load(pdir)["scenes"][0]["shots"][0]["n"] == 1
        sl.add_shot(pdir, "S001", 1)
        assert len(sl.load(pdir)["scenes"][0]["shots"]) == 4
        sl.delete_shot(pdir, "S001", 4)
        assert len(sl.load(pdir)["scenes"][0]["shots"]) == 3
        with pytest.raises(sl.ShotListError):
            sl.move_shot(pdir, "S001", 1, 9)
        with pytest.raises(sl.ShotListError):
            sl.edit_shot(pdir, "S999", 1, {})

    @pytest.mark.parametrize("bad", [{"type": "XYZ"}, {"lens_mm": 2}, {"height": "space"}, {"movement": "teleport"}, {"transition": "explode"},
                                     {"priority": 4}, {"action": ""}, {"source": "stock"}, {"seconds": "x"}])
    def test_shot_checks(self, bad):
        base = {"type": "MS", "lens_mm": 35, "height": "eye", "movement": "static", "transition": "cut", "priority": 2, "action": "x", "seconds": 3, "source": "ai"}
        with pytest.raises(ValueError):
            sl.clean_shot({**base, **bad}, 1)

    def test_needs_a_continuity_book(self, scripted):
        with pytest.raises(sl.ShotListError, match="continuity book"):
            sl.write(scripted, sl.fake_ask(scripted))


class TestGates:
    def test_approval_lasts_only_while_unchanged(self, tmp_path):
        data = {"a": 1}
        assert not gates.approved(tmp_path, "shotlist", data)
        gates.approve(tmp_path, "shotlist", data)
        assert gates.approved(tmp_path, "shotlist", {"a": 1}) and gates.status(tmp_path, "shotlist", data)["approved"]
        st = gates.status(tmp_path, "shotlist", {"a": 2})
        assert not st["approved"] and st["changed_since"]
        gates.revoke(tmp_path, "shotlist")
        assert not gates.status(tmp_path, "shotlist", data)["changed_since"]
        with pytest.raises(ValueError):
            gates.approve(tmp_path, "nope", data)


class TestRoutes:
    def test_continuity_and_shot_list_over_http(self, server, book):
        src.store(book, src.from_idea(STORY), True)
        ri.ReadItIn(book, ri.fake_ask(book)).run()
        st, j = server.api("POST", "/api/shot_list", {"project": "demo", "engine": "fake"})
        assert st == 400 and "continuity book first" in j["error"]
        cb.write(book, cb.fake_ask(book))
        st, j = server.api("GET", "/api/continuity_book?project=demo")
        assert j["book"]["characters"][0]["name"] == "MARA" and not j["gate"]["approved"]
        st, j = server.api("POST", "/api/continuity_approve", {"project": "demo"})
        assert j["gate"]["approved"]
        st, j = server.api("POST", "/api/continuity_edit", {"project": "demo", "kind": "characters", "name": "MARA", "fields": {"token": "a tall woman, red coat"}})
        assert st == 200 and j["gate"]["changed_since"]                                     # an edit takes the approval away
        st, j = server.api("POST", "/api/continuity_edit", {"project": "demo", "kind": "characters", "name": "MARA", "fields": {"token": "an anime woman"}})
        assert st == 400
        server.api("POST", "/api/continuity_approve", {"project": "demo"})
        sl.write(book, sl.fake_ask(book), lambda t: None)
        st, j = server.api("GET", "/api/shot_list?project=demo")
        assert len(j["list"]["scenes"]) == 3 and not j["gate"]["approved"]
        st, j = server.api("POST", "/api/shot_edit", {"project": "demo", "scene": "S001", "n": 1, "action": "move", "to": 2})
        assert st == 200
        st, j = server.api("POST", "/api/shot_edit", {"project": "demo", "scene": "S001", "n": 1, "action": "fly"})
        assert st == 400
        st, j = server.api("POST", "/api/shot_list_approve", {"project": "demo"})
        assert j["gate"]["approved"]
        st, j = server.api("POST", "/api/shot_edit", {"project": "demo", "scene": "S001", "n": 1, "action": "edit", "fields": {"seconds": 5}})
        assert j["gate"]["changed_since"]
        st, j = server.api("GET", "/api/shot_list?project=not_a_book")
        assert st == 200 and j["list"] is None
