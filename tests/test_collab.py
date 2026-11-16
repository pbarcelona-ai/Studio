"""M12: notes on anything (threads, roles, into the role's prompt, resolved on approval), history moments (made on approval; back to a
moment; branch with shared pictures; compare), the Producer chat (plan, accept, simple requests at once, stop / add information / continue),
and the conflict prompt."""
import json

import pytest

import crew
import gates
import history
import layout
import notes
import pictures as px
import producer
from test_pictures import approve_everything_before_pictures, png, render_all


@pytest.fixture
def ready(fake_root):
    d = fake_root / "projects" / "books" / "door"
    approve_everything_before_pictures(d)
    return d


class TestNotes:
    def test_threads_roles_prompt_and_resolve(self, ready):
        n = notes.add(ready, "shot", "S001/2", "Make her look more afraid.")
        assert n["role"] == "director" and n["status"] == "open"
        assert "Make her look more afraid." in crew.system(["director", "cinematographer"], ready, "x")
        assert "Make her look more afraid." not in crew.system("composer", ready, "x")
        notes.reply(ready, n["id"], "And closer.")
        notes.set_role(ready, n["id"], "cinematographer")
        assert "Make her look more afraid. / And closer." in crew.system("cinematographer", ready, "x")
        import shot_list as sl
        gates.approve(ready, "shotlist", sl.gate_data(sl.load(ready)))                       # approving the shot list resolves it
        assert notes.load(ready)[0]["status"] == "resolved" and "Make her" not in crew.system("cinematographer", ready, "x")
        with pytest.raises(notes.NoteError):
            notes.add(ready, "spaceship", "x", "y")
        with pytest.raises(notes.NoteError):
            notes.add(ready, "shot", "x", "")
        with pytest.raises(notes.NoteError):
            notes.set_role(ready, n["id"], "astronaut")

    def test_project_notes_reach_every_role(self, ready):
        producer.add_information(ready, "The sea is always calm.")
        assert "The sea is always calm." in crew.system("composer", ready, "x") and "The sea is always calm." in crew.system("screenwriter", ready, "x")


class TestHistory:
    def test_moments_back_and_branch(self, ready):
        assert any(m["kind"] == "approval" for m in history.moments(ready))                   # approvals made moments
        px.write_prompts(ready)
        setdir = render_all(ready)
        m = history.create(ready, "pictures made")
        assert m["files"] and any(k.startswith("sets/door_px_claymation/images/") for k in m["media"])
        assert history.create(ready, "again") == m                                             # nothing changed: no new moment
        pic = setdir / "images" / "flux1_schnell" / "image-0001.png"
        before = pic.read_bytes()
        png(pic, (1, 1, 1))
        (ready / "production.json").write_text(json.dumps({"styles": [{"id": "anime"}]}))
        (ready / "later.json").write_text("{}")
        out = history.back_to(ready, m["id"])
        assert out["restored"] == "pictures made" and pic.read_bytes() == before and not (ready / "later.json").exists()
        assert json.loads((ready / "production.json").read_text())["styles"][0]["id"] == "claymation"
        assert any(x["id"] == out["saved_as"] for x in history.moments(ready))                 # the state before going back is kept
        b = history.branch(ready, m["id"], "door_dark")
        assert (b / "door_dark.json").is_file() and not (b / "door.json").exists() and json.loads((b / "branch.json").read_text())["from"] == "door"
        assert px.status(b)["set"] == "door_dark_px_claymation" and layout.find_dir("door_dark_px_claymation") is not None
        assert px.status(b)["shots"][0]["image"]                                              # the pictures came along: nothing to pay for again
        with pytest.raises(history.HistoryError):
            history.branch(ready, m["id"], "door_dark")
        with pytest.raises(history.HistoryError):
            history.back_to(ready, "m9999")
        cmp = history.compare(ready, b)
        assert cmp["script_diff"] == [] and len(cmp["storyboard"]) == 9 and cmp["storyboard"][0]["b"]["image"]


class TestProducer:
    def test_plan_accept_dismiss_and_simple(self, ready):
        m = producer.ask_producer(ready, "make the villain scarier", producer.fake_ask())
        assert m["status"] == "proposed" and m["plan"]["steps"] == ["shot_list"]
        ran, regen = [], []
        producer.decide(ready, m["id"], True, ran.append, lambda s, r: regen.append((s, r)))
        assert ran == [["shot_list"]] and notes.load(ready)[-1]["target"] == {"kind": "character", "ref": "MARA"}
        assert any(x["kind"] == "chat" for x in history.moments(ready))
        with pytest.raises(producer.ChatError):
            producer.decide(ready, m["id"], True, ran.append, lambda s, r: None)
        m2 = producer.ask_producer(ready, "make it longer", producer.fake_ask())
        producer.decide(ready, m2["id"], False, ran.append, lambda s, r: None)
        assert producer.load(ready)[-1]["status"] == "dismissed" and len(ran) == 1
        m3 = producer.ask_producer(ready, "regenerate shot one", producer.fake_ask())
        assert m3["plan"]["simple"] and m3["plan"]["regenerate"] == [{"style": "", "row": 1}]

    def test_a_role_the_crew_does_not_have_is_mapped(self, ready):
        """The producer AI wrote a note "for the writer" (the crew has a screenwriter): the note goes to the right role, never an error."""
        plan = {"reply": "I will tell the writer.", "simple": True, "steps": [], "regenerate": [], "settings": {}, "estimate": "$0",
                "notes": [{"kind": "scene", "ref": "1", "role": "writer", "text": "Make the ending sadder."},
                          {"kind": "character", "ref": "MARA", "role": "wizard", "text": "Older."},
                          {"kind": "shot", "ref": "3", "role": "Director of Photography", "text": "Lower the camera."}]}
        seen = []

        def ask(prompt, roles, step, validate):
            seen.append(prompt)
            d = json.loads(json.dumps(plan))
            validate(d)
            return d
        m = producer.ask_producer(ready, "make the ending sadder", ask)
        assert "screenwriter" in seen[0] and "casting_director" in seen[0]                     # the prompt lists the real roles
        assert [n["role"] for n in m["plan"]["notes"]] == ["screenwriter", "casting_director", "cinematographer"]
        producer.decide(ready, m["id"], True, lambda s: None, lambda s, r: None)
        assert [n["role"] for n in notes.load(ready)[-3:]] == ["screenwriter", "casting_director", "cinematographer"]
        assert notes.role_for("scene", "") == "screenwriter" and notes.role_for("nope", "nope") == "producer"

    def test_bad_plans(self):
        for bad in ({"reply": ""}, {"reply": "x", "steps": ["launch"]}, {"reply": "x", "settings": {"budget": 5}}, {"reply": "x", "notes": [{"kind": "x", "text": "y"}]}):
            with pytest.raises(ValueError):
                producer.check_plan(bad)


class TestRoutes:
    def test_over_http(self, server, book):
        approve_everything_before_pictures(book)
        st, j = server.api("POST", "/api/note_add", {"project": "demo", "kind": "character", "ref": "MARA", "text": "Older, please."})
        assert st == 200 and j["notes"][0]["role"] == "casting_director"
        st, j = server.api("POST", "/api/producer", {"project": "demo", "text": "make it darker", "engine": "fake"})
        assert st == 200 and j["messages"][-1]["status"] == "proposed"
        st, j = server.api("POST", "/api/producer_decide", {"project": "demo", "id": j["messages"][-1]["id"], "accept": False})
        assert j["messages"][-1]["status"] == "dismissed"
        st, j = server.api("POST", "/api/producer_stop", {"project": "demo"})
        assert st == 400 and "no job" in j["error"]
        st, j = server.api("POST", "/api/producer_continue", {"project": "demo"})
        assert st == 400
        st, j = server.api("POST", "/api/producer_add", {"project": "demo", "text": "Mara is left-handed."})
        assert st == 200 and "added information" in j["messages"][-1]["text"]
        st, j = server.api("GET", "/api/history?project=demo")
        assert st == 200 and j["moments"]
        st, j = server.api("POST", "/api/branch", {"project": "demo", "id": j["moments"][0]["id"], "name": "demo_two"})
        assert st == 200 and j["branch"] == "demo_two"
        st, j = server.api("GET", "/api/branch_compare?a=demo&b=demo_two")
        assert st == 200 and j["b"] == "demo_two"

    def test_conflict_prompt(self, server, book, monkeypatch):
        approve_everything_before_pictures(book)
        from studio_app import conflicts
        monkeypatch.setattr(conflicts.JOB, "running", True)
        monkeypatch.setattr(conflicts.JOB, "state", {"steps": [{"label": "Write the shot list", "argv": ["python3", "shot_list.py", "demo"]}], "index": 0}, raising=False)
        st, j = server.api("POST", "/api/shot_edit", {"project": "demo", "scene": "S001", "n": 1, "action": "edit", "fields": {"seconds": 5}})
        assert st == 409 and j["error"].startswith("conflict:")
        st, j = server.api("POST", "/api/shot_edit", {"project": "demo", "scene": "S001", "n": 1, "action": "edit", "fields": {"seconds": 5}, "force": True})
        assert st == 200
        st, j = server.api("POST", "/api/continuity_edit", {"project": "demo", "kind": "characters", "name": "MARA", "fields": {"token": "a tall woman, grey coat"}})
        assert st == 200                                                                      # the running job does not write the continuity book
