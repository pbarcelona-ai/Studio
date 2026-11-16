"""M16: security and safety (Section 14) and the accessibility pass: friendly refusals, the rating in every crew prompt, recipes checked
against a schema (and every built-in recipe usable), and every field, picture and button of the page labelled."""
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

import bookkit
import crew
import production

WEB = Path(__file__).resolve().parent.parent / "web"


class TestSafety:
    @pytest.mark.parametrize("text", ["I can't help with that request.", "This violates our policy on violence.", "I'm not able to create that.",
                                      "Your request was flagged as unsafe by the safety system"])
    def test_refusals_are_recognised(self, text):
        assert bookkit.refusal(text)

    @pytest.mark.parametrize("text", ['{"scenes": []}', "The guard can't help himself and laughs.", ""])
    def test_ordinary_replies_are_not(self, text):
        assert not bookkit.refusal(text)

    def test_a_refusal_becomes_a_plain_message(self, monkeypatch, tmp_path):
        import subprocess

        class R:
            returncode, stdout, stderr = 0, json.dumps({"result": "I can't help with that request.", "is_error": False}), ""
        calls = []
        monkeypatch.setattr(bookkit.shutil, "which", lambda *a, **k: "/bin/claude")
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: (calls.append(1), R())[1])
        monkeypatch.setattr(bookkit.subprocess, "run", lambda *a, **k: (calls.append(1), R())[1])
        with pytest.raises(RuntimeError, match="declined this request"):
            bookkit.llm_json("write", "sys", engine="claude", validate=None, retries=2)
        assert len(calls) == 1                                                                  # no pointless retries

    def test_the_rating_is_in_every_crew_prompt(self, tmp_path):
        production.save(tmp_path, {"rating": "8"})
        for role in ("screenwriter", "composer", "storyboard_artist"):
            assert "The film is rated 8+" in crew.system(role, tmp_path, "x")
        assert "rated" not in crew.system("screenwriter", None, "x")


class TestRecipes:
    def test_every_built_in_recipe_is_valid_and_usable(self, tmp_path):
        names = [r["name"] for r in crew.recipes()]
        assert len(names) == 8
        for n in names:
            crew.set_recipe(tmp_path, n)
            assert production.load(tmp_path)["target_minutes"] >= 0.5

    @pytest.mark.parametrize("bad", [{"aspect": "21:9"}, {"products": ["hologram"]}, {"target_minutes": "long"}, {"series": "yes"},
                                     {"prompt_rules": {"screenwriter": 5}}, {"critique": {"min_score": "high"}}, {"__import__": "os"}])
    def test_bad_recipes_are_refused(self, bad, tmp_path, monkeypatch):
        good = json.loads((Path(crew.RECIPES_DIR) / "short_film.json").read_text())
        assert crew.recipe_problems(good) == []
        assert crew.recipe_problems({**good, **bad})
        d = tmp_path / "recipes"
        d.mkdir()
        (d / "evil.json").write_text(json.dumps({**good, **bad, "name": "evil"}))
        (d / "short_film.json").write_text(json.dumps(good))
        monkeypatch.setattr(crew, "RECIPES_DIR", d)
        assert [r["name"] for r in crew.recipes()] == ["short_film"]                              # an invalid recipe is never used


class _Fields(HTMLParser):
    def __init__(self):
        super().__init__()
        self.labels_for, self.fields, self.imgs, self.buttons, self._label_depth, self._btn = set(), [], [], [], 0, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "label":
            self._label_depth += 1
            if a.get("for"):
                self.labels_for.add(a["for"])
        elif tag in ("input", "select", "textarea"):
            self.fields.append((a, self._label_depth > 0))
        elif tag == "img":
            self.imgs.append(a)
        elif tag == "button":
            self._btn = [a, ""]

    def handle_endtag(self, tag):
        if tag == "label":
            self._label_depth -= 1
        elif tag == "button" and self._btn is not None:
            self.buttons.append(tuple(self._btn))
            self._btn = None

    def handle_data(self, data):
        if self._btn is not None:
            self._btn[1] += data


@pytest.mark.parametrize("page", ["index.html", "setup_progress.html"])
def test_every_field_picture_and_button_is_labelled(page):
    p = _Fields()
    p.feed((WEB / page).read_text(encoding="utf-8"))
    unlabelled = [a.get("id") or a for a, wrapped in p.fields
                  if a.get("type") != "hidden" and "hidden" not in a and not wrapped and a.get("id") not in p.labels_for
                  and not a.get("aria-label") and not a.get("aria-labelledby")]
    assert unlabelled == [], f"fields without a label: {unlabelled[:10]}"
    assert all("alt" in a for a in p.imgs), "every picture has alt text"
    nameless = [a.get("id") for a, text in p.buttons if not text.strip() and not a.get("aria-label")]
    assert nameless == [], f"buttons without a name: {nameless}"
    assert re.search(r'<html lang="en"', (WEB / page).read_text(encoding="utf-8"))
