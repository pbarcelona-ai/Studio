"""The film crew: role files, the system prompt each AI call gets, project rules with version checks, recipes, the crew log and the routes."""
import json

import pytest

import bookkit
import crew
from studio_app.api import Request, dispatch

EVERY_ROLE = {"producer", "story_analyst", "development_executive", "screenwriter", "script_doctor", "script_supervisor", "casting_director",
              "production_designer", "director", "cinematographer", "storyboard_artist", "illustrator", "animation_supervisor", "voice_director",
              "sound_designer", "composer", "editor", "colorist", "trailer_editor", "line_producer", "subtitle_translator"}


class TestRoles:
    def test_every_role_has_a_complete_file(self):
        assert set(crew.roles()) >= EVERY_ROLE
        for r in crew.roles():
            text = crew.role_text(r)
            assert text.startswith("# ") and "20 years of experience" in text and "## Your job" in text and "## Before you answer, check" in text
            assert "bible" not in text.lower()                  # the owner's wording rule: "continuity book"

    def test_bad_or_missing_role_is_refused(self):
        for bad in ("../etc/passwd", "Screenwriter", "", "nobody_here"):
            with pytest.raises(ValueError):
                crew.role_text(bad)

    def test_role_title(self):
        assert crew.role_title("cinematographer").startswith("Director of Photography")


class TestSystem:
    def test_one_role_with_task_and_json_reply(self):
        s = crew.system("screenwriter", None, "screenplay", "Adapt the book.")
        assert s.startswith("# Screenwriter") and "## This task\nAdapt the book." in s and s.endswith(crew.JSON_REPLY)
        assert s.roles == ("screenwriter",) and s.step == "screenplay" and len(s.digest) == 12

    def test_several_roles_work_together(self):
        s = crew.system(["director", "cinematographer"], None, "shots")
        assert "film crew, working together" in s and "# Director\n" in s and "# Director of Photography" in s

    def test_no_role_is_an_error(self):
        with pytest.raises(ValueError):
            crew.system([], None)

    def test_recipe_and_project_rules_are_added(self, tmp_path):
        crew.set_recipe(tmp_path, "vertical_microdrama")
        crew.write_rules(tmp_path, "Eve never wears red.", 0)
        s = crew.system("cinematographer", tmp_path, "shots")
        assert "## Format: Vertical microdrama series" in s and "9:16" in s and "Vertical 9:16 framing" in s
        assert s.index("## Project rules") > s.index("## Format") and "Eve never wears red." in s
        assert "cliffhanger at the end" not in s                 # another role's recipe rule is not given to this role

    def test_record_writes_the_crew_log_and_llm_json_calls_it(self, tmp_path, monkeypatch):
        s = crew.system("screenwriter", tmp_path, "screenplay")
        monkeypatch.setattr(bookkit.shutil, "which", lambda *a, **k: None)
        with pytest.raises(RuntimeError, match="not found"):        # the call itself fails (no CLI), but the log line is written first
            bookkit.llm_json("x", s, engine="claude")
        log = crew.log_tail(tmp_path)
        assert len(log) == 1 and log[0]["roles"] == ["screenwriter"] and log[0]["step"] == "screenplay" and log[0]["role_version"] == s.digest

    def test_a_plain_string_system_still_works(self, monkeypatch):
        monkeypatch.setattr(bookkit.shutil, "which", lambda *a, **k: None)
        with pytest.raises(RuntimeError, match="not found"):
            bookkit.llm_json("x", "plain system", engine="claude")


class TestRules:
    def test_versions_and_conflicts(self, tmp_path):
        assert crew.read_rules(tmp_path) == {"body": "", "rev": 0, "updated": ""}
        assert crew.write_rules(tmp_path, "  no gore  ", 0)["rev"] == 1 and crew.read_rules(tmp_path)["body"] == "no gore"
        with pytest.raises(crew.RevConflict) as e:
            crew.write_rules(tmp_path, "something else", 0)       # based on version 0, but the file is at 1
        assert e.value.current == 1 and crew.read_rules(tmp_path)["body"] == "no gore"
        assert crew.write_rules(tmp_path, "two", 1)["rev"] == 2

    def test_limits(self, tmp_path):
        with pytest.raises(ValueError):
            crew.write_rules(tmp_path, "x" * (crew.RULES_MAX + 1), 0)
        with pytest.raises(ValueError):
            crew.write_rules(tmp_path, ["not text"], 0)           # type: ignore[arg-type]

    def test_a_broken_file_reads_as_empty(self, tmp_path):
        (tmp_path / "project_rules.json").write_text("{not json")
        assert crew.read_rules(tmp_path)["rev"] == 0


class TestRecipes:
    def test_built_ins_in_order(self):
        names = [r["name"] for r in crew.recipes()]
        assert names[:3] == ["feature_film", "short_film", "vertical_microdrama"] and "picture_book" in names and "youtube_explainer" in names and len(names) == 9
        for r in crew.recipes():
            assert r["aspect"] in ("16:9", "9:16", "4:3", "1:1") and set(r["prompt_rules"]) <= set(crew.roles())

    def test_choose_and_unknown(self, tmp_path):
        assert crew.project_recipe(tmp_path) == ""
        crew.set_recipe(tmp_path, "picture_book")
        assert crew.project_recipe(tmp_path) == "picture_book"
        with pytest.raises(ValueError):
            crew.set_recipe(tmp_path, "nope")
        crew.set_recipe(tmp_path, "")
        assert crew.project_recipe(tmp_path) == ""


class TestRoutes:
    def test_crew_recipes_rules(self, book):
        code, out = dispatch("GET", "/api/crew", Request(query={"project": ["demo"]}))
        assert code == 200 and {"key": "screenwriter", "title": "Screenwriter"} in out["roles"] and out["log"] == []
        code, out = dispatch("GET", "/api/recipes", Request(query={"project": ["demo"]}))
        assert code == 200 and out["chosen"] == "" and out["recipes"][0]["name"] == "feature_film"
        assert dispatch("POST", "/api/recipe", Request(body={"project": "demo", "name": "short_film"}))[0] == 200
        assert dispatch("GET", "/api/recipes", Request(query={"project": ["demo"]}))[1]["chosen"] == "short_film"
        assert dispatch("POST", "/api/recipe", Request(body={"project": "demo", "name": "nope"}))[0] == 400

    def test_rules_save_and_conflict(self, book):
        code, out = dispatch("POST", "/api/project_rules", Request(body={"project": "demo", "body": "no gore", "rev": 0}))
        assert code == 200 and out["rev"] == 1
        code, out = dispatch("POST", "/api/project_rules", Request(body={"project": "demo", "body": "mine", "rev": 0}))
        assert code == 409 and out["current"]["body"] == "no gore" and out["current"]["rev"] == 1
        assert json.loads((book / "project_rules.json").read_text())["body"] == "no gore"
        assert dispatch("GET", "/api/project_rules", Request(query={"project": ["demo"]}))[1]["rev"] == 1
        assert dispatch("POST", "/api/project_rules", Request(body={"project": "demo", "body": "x", "rev": "a"}))[0] == 400

    def test_needs_a_book(self, book):
        for path in ("/api/project_rules", "/api/recipes", "/api/crew"):
            assert dispatch("GET", path, Request(query={"project": ["../x"]}))[0] == 400


def test_concurrent_saves_from_the_same_version_let_only_one_through(tmp_path):
    import threading
    results = []

    def save(text):
        try:
            results.append(crew.write_rules(tmp_path, text, 0)["rev"])
        except crew.RevConflict:
            results.append("conflict")
    ts = [threading.Thread(target=save, args=(f"rule {i}",)) for i in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(results, key=str) == [1] + ["conflict"] * 7 and crew.read_rules(tmp_path)["rev"] == 1


def test_a_bad_rev_in_the_file_reads_as_zero(tmp_path):
    (tmp_path / "project_rules.json").write_text('{"body": "x", "rev": "abc"}')
    assert crew.read_rules(tmp_path)["rev"] == 0
