"""layout (where each kind of folder lives) and check_catalog.main/exists with the network replaced."""
import urllib.error

import pytest

import check_catalog
import layout


@pytest.fixture
def tree(fake_root):
    for d in ("books/b1", "prompts/p1", "characters/char_x", "characters/series", "regression/regtest_a"):
        (fake_root / "projects" / d).mkdir(parents=True, exist_ok=True)
    (fake_root / "projects" / "characters" / "char_x" / "promptset.json").write_text("{}")
    return fake_root


class TestLayout:
    @pytest.mark.parametrize("bad", ["A", "../x", "a b", "", "x" * 41, "a"])
    def test_names_are_checked(self, bad):
        with pytest.raises(ValueError):
            layout.find_dir(bad)

    def test_finds_where_it_is(self, tree):
        assert layout.find_dir("b1") == layout.BOOKS / "b1" and layout.find_dir("nothere") is None

    def test_new_folders_go_to_the_right_place(self, tree):
        assert layout.new_dir("fresh") == layout.BOOKS / "fresh"
        assert layout.new_dir("fresh", "prompts") == layout.PROMPTS / "fresh"
        assert layout.new_dir(layout.CHARACTER_SET_PREFIX + "adam", "prompts") == layout.CHARACTERS / (layout.CHARACTER_SET_PREFIX + "adam")
        assert layout.new_dir(layout.REGRESSION_PREFIX + "z", "prompts") == layout.REGRESSION / (layout.REGRESSION_PREFIX + "z")
        with pytest.raises(ValueError, match="unknown kind"):
            layout.new_dir("fresh", "film")

    def test_project_dir_prefers_what_exists(self, tree):
        assert layout.project_dir("p1") == layout.PROMPTS / "p1"
        assert layout.project_dir("fresh") == layout.BOOKS / "fresh"

    def test_kind_of(self, tree):
        assert [layout.kind_of(s) for s in ("b1", "char_x", "p1", "regtest_a", "nothere")] == ["book", "character", "prompts", "prompts", None]

    def test_rel_is_relative_with_forward_slashes(self, tree):
        assert layout.rel("b1") == "projects/books/b1"

    def test_listings(self, tree):
        assert layout.book_slugs() == ["b1"]
        assert layout.promptset_slugs() == ["char_x", "p1"]            # a series folder has no promptset.json, so it is not listed
        assert layout.regression_slugs() == ["regtest_a"]
        assert {p.name for p in layout.all_dirs()} == {"b1", "p1", "char_x", "regtest_a"}

    def test_listings_of_an_empty_root(self, fake_root):
        assert layout.book_slugs() == [] and layout.promptset_slugs() == [] and layout.regression_slugs() == []


class TestCatalogCheck:
    def test_exists_reads_the_status(self, monkeypatch):
        class Resp:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
        monkeypatch.setattr(check_catalog.urllib.request, "urlopen", lambda req, timeout=0: Resp())
        assert check_catalog.exists("https://x/y") is True

    @pytest.mark.parametrize("code,want", [(404, False), (410, False), (403, True), (429, True), (500, True)])
    def test_http_errors(self, monkeypatch, code, want):
        def boom(req, timeout=0):
            raise urllib.error.HTTPError("u", code, "m", {}, None)
        monkeypatch.setattr(check_catalog.urllib.request, "urlopen", boom)
        assert check_catalog.exists("https://x/y") is want

    def test_offline_is_not_evidence(self, monkeypatch):
        def boom(req, timeout=0):
            raise OSError("offline")
        monkeypatch.setattr(check_catalog.urllib.request, "urlopen", boom)
        assert check_catalog.exists("https://x/y") is True

    def test_offline_run_passes_on_the_real_catalog(self, capsys):
        assert check_catalog.main(["--offline"]) == 0 and "CATALOG:" not in capsys.readouterr().out

    def test_online_run_reports_gone_models(self, monkeypatch, capsys):
        monkeypatch.setattr(check_catalog, "exists", lambda url: "gone-model" not in url)
        monkeypatch.setattr(check_catalog, "CATALOG", {**check_catalog.CATALOG, "hf_models": ["a/ok", "a/gone-model"]})
        monkeypatch.setattr(check_catalog.hf_spaces, "SPACES", {"k": {"space": "o/s"}})
        assert check_catalog.main([]) == 1
        out = capsys.readouterr().out
        assert "GONE model a/gone-model" in out and "ok   model a/ok" in out and "ok   space o/s (k)" in out

    def test_a_malformed_catalog_fails_even_offline(self, monkeypatch, capsys):
        monkeypatch.setattr(check_catalog, "CATALOG", {"hf_models": []})
        assert check_catalog.main(["--offline"]) == 1 and "CATALOG:" in capsys.readouterr().out
