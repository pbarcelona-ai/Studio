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


FULL = {"name": "Eve", "series": "main", "visual_token": "EVE: a woman", "physical_traits": {"hair": "long", "eyes": ""}, "clothing": "a red robe",
        "consistency_notes": "always sad", "voice": "af_bella"}


class TestPromptText:
    def test_tokens_for_prompt_lists_traits_clothing_and_notes(self, chars):
        ct.save_character(FULL)
        ct.save_character(make("Adam", "main"))
        text = ct.get_character_tokens_for_prompt("main", ["Eve", "Adam", "Ghost"])
        assert text.startswith("\n\nCHARACTER TOKENS:\n") and "EVE: a woman | hair: long | wearing a red robe | always sad" in text and "adam token" in text and "Ghost" not in text
        assert ct.get_character_tokens_for_prompt("main", ["Ghost"]) == ""

    def test_all_tokens_of_a_series(self, chars):
        assert ct.get_all_character_tokens("empty") == ""
        ct.save_character(FULL)
        text = ct.get_all_character_tokens("main")
        assert "### Eve\nEVE: a woman | hair: long | wearing a red robe | always sad" in text

    def test_build_character_prompt_order(self, chars):
        text = ct.build_character_prompt(FULL, "she weeps")
        parts = text.split(", ")
        assert parts[0] == "EVE: a woman" and "she weeps" in text and text.index("wearing a red robe") < text.index("she weeps") < text.index("always sad") and text.endswith(ct.PHOTOREAL_TAIL)
        assert ct.build_character_prompt({}) == ct.PHOTOREAL_TAIL


class TestReferences:
    @pytest.fixture()
    def eve(self, chars):
        ct.save_character(FULL)
        folder = ct.ensure_reference_dir("main", "Eve")
        for n in ("ref_02.png", "ref_01.png"):
            (folder / n).write_bytes(b"x")
        (folder / "notes.txt").write_text("not a picture")
        return folder

    def test_first_reference_falls_back_to_the_folder(self, eve):
        assert ct.first_reference("main", "Eve").name == "ref_01.png"
        assert ct.first_reference("main", "Nobody") is None

    def test_stage_folder_wins_and_listed_pictures_come_before_the_folder(self, eve, chars):
        stage = eve / "old"
        stage.mkdir()
        (stage / "a.png").write_bytes(b"x")
        assert ct.first_reference("main", "Eve", "Old").parent.name == "old"
        listed = chars / "elsewhere.png"
        listed.write_bytes(b"x")
        ct.add_reference_image("main", "Eve", str(listed))
        assert ct.first_reference("main", "Eve") == listed

    def test_reference_pictures_for_the_page(self, eve, chars):
        ct.add_reference_image("main", "Eve", "projects/characters/main/references/eve/ref_02.png")
        ct.add_reference_image("main", "Eve", "projects/characters/main/references/eve/gone.png")
        pics = ct.reference_pictures("main", "Eve")
        assert [p["name"] for p in pics] == ["ref_02.png", "gone.png", "ref_01.png"] and pics[0]["listed"] and not pics[2]["listed"]
        assert [p["exists"] for p in pics] == [True, False, True] and pics[0]["used"] and pics[0]["file"] == "main/references/eve/ref_02.png" and pics[1]["file"] == ""

    def test_use_reference_moves_a_picture_to_the_front(self, eve):
        path = "projects/characters/main/references/eve/ref_02.png"
        assert ct.use_reference("main", "Eve", path) and ct.load_character("main", "Eve")["reference_images"][0] == path
        assert ct.use_reference("main", "Eve", "projects/characters/main/references/eve/ref_01.png")
        assert ct.load_character("main", "Eve")["reference_images"] == ["projects/characters/main/references/eve/ref_01.png", path]
        assert not ct.use_reference("main", "Eve", "projects/elsewhere.png") and not ct.use_reference("main", "Ghost", path)

    def test_add_reference_is_idempotent_and_unknown_characters_fail(self, eve):
        assert ct.add_reference_image("main", "Eve", "a.png") and ct.add_reference_image("main", "Eve", "a.png")
        assert ct.load_character("main", "Eve")["reference_images"].count("a.png") == 1 and not ct.add_reference_image("main", "Ghost", "a.png")


class TestMisc:
    def test_lora_info_and_delete(self, chars):
        ct.save_character(FULL)
        assert ct.update_lora_info("main", "Eve", "me/eve-lora", "eve_tok", "flux") and ct.load_character("main", "Eve")["lora"]["trained"] is True
        assert not ct.update_lora_info("main", "Ghost", "r", "t", "b")
        assert ct.delete_character("main", "Eve") and not ct.delete_character("main", "Eve") and ct.list_characters("main") == []

    def test_index_of_a_series_that_does_not_exist_is_left_alone(self, chars):
        ct.update_index("nowhere")
        assert not (chars / "projects" / "characters" / "nowhere").exists()

    def test_series_listing_when_the_folder_is_missing(self, chars, monkeypatch):
        monkeypatch.setattr(ct, "CHARACTERS_ROOT", chars / "no" / "such")
        assert ct.list_series() == []

    def test_stages_travel_to_the_book(self, saga):
        stages = [{"label": "young", "chapters": "1-3", "token": "young woman"}]
        ct.save_character(make("Eve", "series1", stages=stages))
        assert ct.send_to_book("saga", "series1", ["Eve"])["updated"] == 1
        assert json.loads((saga / "saga.json").read_text())["characters"][0]["stages"] == stages

    def test_a_trait_with_a_wrong_value_is_reported_by_validate(self):
        errs = ct.validate_character({"archetype": "human", "physical_traits": {"age": "x"}, "name": "A"})
        assert isinstance(errs, list)


class TestCommandLine:
    def test_every_command(self, chars, run_script):
        ct.save_character(FULL)
        assert "Usage:" in run_script("character_tokens.py")[1] and run_script("character_tokens.py")[0] == 1
        assert '"main"' in run_script("character_tokens.py", "list-series")[1]
        assert '"Eve"' in run_script("character_tokens.py", "list", "main")[1]
        assert '"visual_token": "EVE: a woman"' in run_script("character_tokens.py", "get", "main", "Eve")[1]
        assert "### Eve" in run_script("character_tokens.py", "tokens", "main")[1]
        assert "Synced 0 characters from nobook" in run_script("character_tokens.py", "sync", "nobook")[1]
        assert "Unknown command: zap" in run_script("character_tokens.py", "zap")[1]
        assert "Deleted: True" in run_script("character_tokens.py", "delete", "main", "Eve")[1]
