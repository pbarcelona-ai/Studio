"""Every /api/characters action over real HTTP, plus global parameters and frame extraction."""
import sys
import types

import pytest

import character_tokens as ct


def get(server, query):
    return server.api("GET", "/api/characters?" + query)


def act(server, action, **body):
    return server.api("POST", "/api/characters", {"action": action, **body})


@pytest.fixture()
def eve(fake_root):
    ct.save_character({"name": "Eve", "series": "main", "visual_token": "EVE: a woman", "voice": "af_bella"})
    folder = ct.ensure_reference_dir("main", "Eve")
    (folder / "ref_01.png").write_bytes(b"x")
    return folder


class TestGetActions:
    def test_series_lists_tokens_and_references(self, server, eve):
        assert get(server, "action=list_series")[1] == {"series": ["main"]}
        assert [c["name"] for c in get(server, "series=main")[1]["characters"]] == ["Eve"]
        assert get(server, "action=get&series=main&name=Eve")[1]["character"]["visual_token"] == "EVE: a woman"
        assert "EVE: a woman" in get(server, "action=tokens&series=main")[1]["tokens"]
        out = get(server, "action=references&series=main&name=Eve")[1]
        assert out["pictures"][0]["name"] == "ref_01.png" and out["folder"].endswith("references/eve")
        assert get(server, "action=sync&series=main&project=nothing")[1] == {"synced": 0, "series": "main"}

    def test_archetypes_fields_and_values(self, server):
        out = get(server, "action=archetypes")[1]["archetypes"]
        assert "human" in out and out["human"]["label"] == "Human"
        fields = get(server, "action=archetype_fields&archetype=human")[1]
        assert fields["archetype"] == "human" and any(v["required"] for v in fields["fields"].values())
        assert get(server, "action=archetype_fields&archetype=nope")[0] == 400
        one = get(server, "action=valid_values&field=build")[1]
        assert one["field"] == "build" and one["values"] == one["valid_values"]["build"]
        assert "build" in get(server, "action=valid_values")[1]["valid_values"]
        assert get(server, "action=explode")[0] == 400


class TestPostActions:
    def test_save_picture_and_lora(self, server, eve):
        char = ct.load_character("main", "Eve")
        assert act(server, "save", character={**char, "stages": [{"label": "old", "chapters": "5-", "token": "an old woman"}]})[1]["saved"] is True
        assert ct.load_character("main", "Eve")["stages"][0]["label"] == "old"
        (eve / "ref_02.png").write_bytes(b"x")
        path = "projects/characters/main/references/eve/ref_02.png"
        assert act(server, "add_reference", series="main", name="Eve", image_path=path)[1] == {"updated": True}
        assert act(server, "use_reference", series="main", name="Eve", path=path)[1] == {"updated": True}
        assert act(server, "use_reference", series="main", name="Eve", path="nowhere.png")[1] == {"updated": False}
        assert act(server, "update_lora", series="main", name="Eve", lora_repo="me/eve", trigger_word="eve_tok", base_model="flux")[1] == {"updated": True}

    def test_archetype_fields_values_validate_and_template(self, server):
        assert "fields" in act(server, "archetype_fields", archetype="human")[1] and act(server, "archetype_fields", archetype="nope")[0] == 400
        assert act(server, "valid_values", field="build")[1]["field"] == "build"
        ok = act(server, "validate", character={"name": "A", "physical_traits": {}}, archetype="human")[1]
        assert ok["valid"] is False and ok["errors"]
        assert act(server, "validate", character={"name": "A"})[1]["valid"] in (True, False)
        t = act(server, "template", archetype="human", name="Zed", series="main")[1]["template"]
        assert t["name"] == "Zed" and t["series"] == "main"

    def test_send_to_book(self, server, book, eve):
        assert act(server, "send_to_book", project="demo", series="main", names=["Eve"])[1]["found"] is True
        assert act(server, "send_to_book", project="demo", series="main", names=[])[0] == 400
        assert act(server, "send_to_book", project="demo", series="main", names=[3])[0] == 400
        (book / "demo.json").unlink()
        status, out = act(server, "send_to_book", project="demo", series="main", names=["Eve"])
        assert status == 400 and "no continuity book file" in out["error"]
        (book / "demo.json").write_text('{"characters": {"Eve": {}}}')
        assert "older layout" in act(server, "send_to_book", project="demo", series="main", names=["Eve"])[1]["error"]

    def test_sync_needs_a_series_and_a_continuity_book(self, server, book):
        assert act(server, "sync", project="demo", series="")[0] == 400
        (book / "demo.json").unlink()
        assert "nothing to sync" in act(server, "sync", project="demo", series="main")[1]["error"]


class TestGlobalParams:
    def test_project_is_required(self, server, book):
        assert server.api("GET", "/api/global_params")[0] == 400
        assert server.api("GET", "/api/global_params?project=demo")[0] == 200


class TestExtractFrame:
    @pytest.fixture()
    def cv2(self, monkeypatch):
        state = types.SimpleNamespace(opened=True, ok=True, wrote=True)

        class Cap:
            def __init__(self, path):
                pass

            def isOpened(self):
                return state.opened

            def set(self, a, b):
                pass

            def read(self):
                return state.ok, "img"

            def release(self):
                pass
        mod = types.ModuleType("cv2")
        mod.VideoCapture, mod.CAP_PROP_POS_FRAMES = Cap, 1
        mod.imwrite = lambda path, img: open(path, "wb").write(b"png") if state.wrote else None
        monkeypatch.setitem(sys.modules, "cv2", mod)
        return state

    @pytest.fixture()
    def clip(self, book):
        d = book / "videos" / "ltx_video"
        d.mkdir(parents=True)
        (d / "shot-0001.mp4").write_bytes(b"x")
        return d

    BODY = {"project": "demo", "model": "ltx_video", "video": "shot-0001.mp4", "frame": 3}

    def test_writes_the_frame_next_to_the_clip(self, server, cv2, clip):
        status, out = server.api("POST", "/api/extract_frame", self.BODY)
        assert status == 200 and out["success"] and (clip / "shot-0001_frame0003.png").read_bytes() == b"png"

    @pytest.mark.parametrize("state,msg", [({"opened": False}, "could not open video"), ({"ok": False}, "could not read frame"), ({"wrote": False}, "output not created")])
    def test_failures_are_reported(self, server, cv2, clip, state, msg):
        for k, v in state.items():
            setattr(cv2, k, v)
        status, out = server.api("POST", "/api/extract_frame", self.BODY)
        assert status == 500 and msg in out["error"]

    def test_without_opencv(self, server, clip, monkeypatch):
        monkeypatch.setitem(sys.modules, "cv2", None)
        assert "OpenCV" in server.api("POST", "/api/extract_frame", self.BODY)[1]["error"]
