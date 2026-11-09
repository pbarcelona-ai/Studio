"""Character tokens: storage and index, validation, sync from and to a book's continuity file."""
import json

import pytest

import character_tokens as ct


@pytest.fixture
def chars(fake_root):
    return fake_root


def make(name="Eve", series="saga", **kw):
    return {"name": name, "series": series, "visual_token": f"{name.lower()} token", "voice": "af_bella", **kw}


class TestStorage:
    def test_paths_are_slugged_so_names_cannot_escape(self, chars):
        p = ct.get_character_path("../../etc", "../passwd")
        assert ct.CHARACTERS_ROOT in p.parents and ".." not in p.relative_to(ct.CHARACTERS_ROOT).parts

    def test_save_load_and_index(self, chars):
        path = ct.save_character(make())
        assert path.exists() and ct.load_character("saga", "Eve")["visual_token"] == "eve token"
        c = ct.load_character("saga", "Eve")
        assert c["created"] and c["updated"]
        assert ct.list_characters("saga") == [{"name": "Eve", "file": "eve.json", "visual_token": "eve token", "has_lora": False, "updated": c["updated"]}]
        assert ct.list_series() == ["saga"]

    def test_missing_and_corrupt(self, chars):
        assert ct.load_character("saga", "Nobody") is None and ct.list_characters("saga") == [] and ct.list_series() == []
        ct.save_character(make())
        ct.get_character_path("saga", "Eve").write_text("{broken")
        assert ct.load_character("saga", "Eve") is None
        ct.update_index("saga")                                   # a damaged file is left out of the index, not fatal
        assert ct.list_characters("saga") == []

    def test_unreadable_index(self, chars):
        ct.save_character(make())
        ct.get_index_path("saga").write_text("nope")
        assert ct.list_characters("saga") == []

    def test_image_sets_are_not_series(self, chars):
        ct.save_character(make())
        (ct.CHARACTERS_ROOT / "char_adam").mkdir()
        (ct.CHARACTERS_ROOT / "char_adam" / "promptset.json").write_text("{}")
        (ct.CHARACTERS_ROOT / "_schema").mkdir()
        assert ct.list_series() == ["saga"]

    def test_prompt_tokens(self, chars):
        ct.save_character(make())
        assert "eve token" in ct.get_character_tokens_for_prompt("saga", ["Eve", "Nobody"])
        assert ct.get_character_tokens_for_prompt("saga", []) == ""

    def test_create_from_description(self, chars):
        c = ct.create_character_from_description("saga", "Zed", "tall", "")
        assert c["name"] == "Zed" and c["consistency_notes"] == "tall" and c["visual_token"] and c["trigger_words"] == ["zed"]
        assert ct.create_character_from_description("saga", "Zed", "tall", "my token")["visual_token"] == "my token"


class TestValidation:
    def test_unknown_and_free_text_fields_pass(self):
        assert ct.validate_trait("no_such_field", "x") == (True, "")
        assert ct.validate_trait("hair", "anything goes")[0]

    def test_strict_field_rejects_unknown_values(self):
        ok, msg = ct.validate_trait("luminosity", "definitely-not-valid")
        assert not ok and "Invalid luminosity" in msg and "Valid options" in msg

    def test_strict_field_accepts_each_listed_value(self):
        for v in ct.get_valid_values("luminosity")[:3]:
            assert ct.validate_trait("luminosity", v)[0]
        assert ct.validate_trait("luminosity", "")[0]

    def test_unknown_archetype_is_reported(self):
        errs = ct.validate_character({"archetype": "dragon"})
        assert any("Unknown archetype: dragon" in e for e in errs)

    def test_every_archetype_has_config_and_template(self):
        for a in ct.CharacterArchetype:
            assert isinstance(ct.get_archetype_fields(a), dict)
            t = ct.create_character_template(a, "N", "S")
            assert t["name"] == "N" and t["series"] == "S"

    def test_missing_required_trait_is_listed(self):
        a = next(a for a in ct.CharacterArchetype if ct.get_archetype_fields(a).get("required_physical"))
        req = ct.get_archetype_fields(a)["required_physical"][0]
        assert any(req in e for e in ct.validate_character({"physical_traits": {}}, a))

    def test_valid_values_for_unknown_field(self):
        assert ct.get_valid_values("zzz") == []


BOOK = {"title": "Saga", "setting": "s", "visual_style": "v", "music_theme": "m", "locations": [],
        "characters": [{"name": "Eve", "token": "a woman in red", "voice": "female"}, {"name": "Adam", "token": "a tall man", "voice": "male"}]}


@pytest.fixture
def saga(chars):
    d = chars / "projects" / "books" / "saga"
    d.mkdir(parents=True)
    (d / "saga.json").write_text(json.dumps(BOOK))
    return d


class TestSyncFromBook:
    def test_no_continuity_file(self, chars):
        assert ct.sync_from_book("nothing")["continuity"] is False

    def test_adds_then_skips(self, saga):
        r = ct.sync_from_book("saga", "series1")
        assert (r["total"], r["added"], r["skipped"]) == (2, 2, 0)
        c = ct.load_character("series1", "Eve")
        assert c["visual_token"] == "a woman in red" and c["voice"] == "af_bella" and c["trigger_words"] == ["eve"]
        again = ct.sync_from_book("saga", "series1")
        assert (again["added"], again["skipped"]) == (0, 2)

    def test_dry_run_writes_nothing(self, saga):
        assert ct.sync_from_book("saga", "series1", dry_run=True)["added"] == 2
        assert ct.list_series() == []

    def test_overwrite_merges_and_keeps_hand_made_fields(self, saga):
        ct.sync_from_book("saga", "series1")
        mine = ct.load_character("series1", "Eve")
        mine["visual_token"] = "hand edited"
        mine["trigger_words"] = ["eve", "my word"]
        mine["reference_images"] = ["ref.png"]
        ct.save_character(mine)
        r = ct.sync_from_book("saga", "series1", overwrite=True)
        assert r["updated"] == 2
        c = ct.load_character("series1", "Eve")
        assert c["visual_token"] == "a woman in red" and c["trigger_words"] == ["eve", "my word"] and c["reference_images"] == ["ref.png"]

    def test_older_dict_layout(self, saga):
        (saga / "saga.json").write_text(json.dumps({**BOOK, "characters": {"Eve": {"visual_token": "old style", "aliases": ["E"], "notes": "n", "voice": "elder"}, "bad": 5}}))
        ct.sync_from_book("saga", "s2")
        c = ct.load_character("s2", "Eve")
        assert c["visual_token"] == "old style" and c["trigger_words"] == ["eve", "E"] and c["voice"] == "bm_lewis" and c["consistency_notes"] == "n"

    def test_unreadable_book(self, saga):
        (saga / "saga.json").write_text("{nope")
        assert ct.extract_characters_from_book(saga / "saga.json") == [] and ct.extract_characters_from_book(saga / "missing.json") == []

    def test_project_sync_returns_the_added_count(self, saga):
        assert ct.sync_characters_from_project("saga") == 2 and ct.sync_characters_from_project("saga") == 0


class TestSendToBook:
    @pytest.fixture(autouse=True)
    def series(self, saga):
        ct.sync_from_book("saga", "series1")

    def read(self, saga):
        return json.loads((saga / "saga.json").read_text())

    def test_no_book(self, chars):
        assert ct.send_to_book("nothing", "series1", ["Eve"])["found"] is False

    def test_unchanged(self, saga):
        r = ct.send_to_book("saga", "series1", ["Eve", "Adam"])
        assert (r["unchanged"], r["updated"], r["added"], r["missing"]) == (2, 0, 0, [])

    def test_token_edit_travels_to_the_book(self, saga):
        c = ct.load_character("series1", "Eve")
        c["visual_token"] = "a woman in blue"
        ct.save_character(c)
        r = ct.send_to_book("saga", "series1", ["Eve"], dry_run=True)
        assert r["updated"] == 1 and self.read(saga)["characters"][0]["token"] == "a woman in red"        # a dry run changes nothing
        assert ct.send_to_book("saga", "series1", ["Eve"])["updated"] == 1
        assert self.read(saga)["characters"][0]["token"] == "a woman in blue" and self.read(saga)["title"] == "Saga"

    def test_new_character_is_added_and_missing_ones_reported(self, saga):
        ct.save_character(make("Zed", "series1", voice="am_michael"))
        r = ct.send_to_book("saga", "series1", ["Zed", "Ghost"])
        assert r["added"] == 1 and r["missing"] == ["Ghost"]
        zed = next(c for c in self.read(saga)["characters"] if c["name"] == "Zed")
        assert zed["token"] == "zed token" and zed["voice"] == "male"

    def test_old_layout_cannot_be_updated(self, saga):
        (saga / "saga.json").write_text(json.dumps({**BOOK, "characters": {"Eve": {}}}))
        with pytest.raises(ValueError, match="older layout"):
            ct.send_to_book("saga", "series1", ["Eve"])


def test_prompt_constants_are_nonempty():
    assert ct.get_prompt_suffix() and ct.get_negative_prompt()
