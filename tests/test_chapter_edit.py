"""chapter_edit.py (rename, merge, split, drop) and its routes."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import TOKEN

import chapter_edit as ce

JS = Path(__file__).resolve().parent / "js"


@pytest.fixture()
def book(fake_root):
    d = fake_root / "projects" / "books" / "demo"
    (d / "chapters").mkdir(parents=True)
    texts = ["alpha one two three four five six seven", "bravo " * 50, "charlie short", "delta " * 20]
    for n, t in enumerate(texts, start=1):
        (d / "chapters" / f"chapter-{n:03d}.txt").write_text(t.strip())
    (d / "chapters.json").write_text(json.dumps({"method": "chapter", "pdf": "demo.pdf", "chapters": [{"n": n, "title": f"T{n}", "words": 1, "chars": 1} for n in range(1, 5)]}))
    return d


def titles(d):
    return [c["title"] for c in ce.load(d)["chapters"]]


class TestEdits:
    def test_load(self, book):
        out = ce.load(book)
        assert [c["n"] for c in out["chapters"]] == [1, 2, 3, 4] and out["chapters"][0]["words"] == 8 and out["downstream"] == {"scripts": 0, "built": False}

    def test_rename(self, book):
        ce.rename(book, 2, "  The   Long  Night ")
        assert titles(book)[1] == "The Long Night"
        with pytest.raises(ce.ChapterEditError):
            ce.rename(book, 2, "   ")
        with pytest.raises(ce.ChapterEditError):
            ce.rename(book, 9, "x")

    def test_merge_renumbers(self, book):
        out = ce.merge(book, 2)
        assert titles(book) == ["T1", "T2", "T4"] and out["chapters"][1]["words"] == 52
        assert not (book / "chapters" / "chapter-004.txt").exists() and json.loads((book / "chapters.json").read_text())["edited"] is True
        with pytest.raises(ce.ChapterEditError, match="no next"):
            ce.merge(book, 3)

    def test_split_moves_back_to_the_word_start(self, book):
        text = (book / "chapters" / "chapter-001.txt").read_text()
        at = text.index("three") + 2                          # in the middle of "three"
        ce.split(book, 1, at, "Second half")
        assert titles(book)[:3] == ["T1", "Second half", "T2"]
        assert (book / "chapters" / "chapter-001.txt").read_text() == "alpha one two"
        assert (book / "chapters" / "chapter-002.txt").read_text() == "three four five six seven"

    def test_split_default_title_and_bad_points(self, book):
        ce.split(book, 4, 12)
        assert titles(book)[3] == "T4" and titles(book)[4] == "T4 (part 2)"
        for bad in (0, 10**6, "5", True):
            with pytest.raises(ce.ChapterEditError):
                ce.split(book, 1, bad)

    def test_drop_keeps_the_text(self, book):
        ce.drop(book, [1, 3])
        assert titles(book) == ["T2", "T4"]
        dropped = (book / "dropped_text.txt").read_text()
        assert "## T1" in dropped and "charlie short" in dropped
        with pytest.raises(ce.ChapterEditError, match="at least one"):
            ce.drop(book, [1, 2])
        with pytest.raises(ce.ChapterEditError):
            ce.drop(book, [])

    def test_written_work_blocks_renumbering_unless_forced(self, book):
        (book / "scripts").mkdir()
        (book / "scripts" / "chapter-001.json").write_text("{}")
        with pytest.raises(ce.ChapterEditError, match="renumbers"):
            ce.merge(book, 1)
        with pytest.raises(ce.ChapterEditError, match="renumbers"):
            ce.drop(book, [1])
        ce.rename(book, 1, "Fine")                                  # always allowed
        assert len(ce.merge(book, 1, force=True)["chapters"]) == 3

    def test_adaptation_is_marked_stale(self, book):
        (book / "adaptation").mkdir()
        (book / "adaptation" / "adaptation.json").write_text(json.dumps({"scenes": []}))
        ce.merge(book, 1)
        assert json.loads((book / "adaptation" / "adaptation.json").read_text())["stale"] is True

    def test_no_chapters(self, fake_root):
        d = fake_root / "projects" / "books" / "empty"
        d.mkdir(parents=True)
        with pytest.raises(ce.ChapterEditError, match="Read book"):
            ce.load(d)


class TestRoutes:
    def test_list_text_and_edit(self, server, book):
        assert server.api("GET", "/api/chapters?project=demo")[1]["chapters"][0]["title"] == "T1"
        assert server.api("GET", "/api/chapter_text?project=demo&n=3")[1]["text"] == "charlie short"
        st, out = server.api("POST", "/api/chapter_edit", {"project": "demo", "action": "merge", "n": 3})
        assert st == 200 and [c["title"] for c in out["chapters"]] == ["T1", "T2", "T3"]
        st, out = server.api("POST", "/api/chapter_edit", {"project": "demo", "action": "split", "n": 2, "at": 12, "title": "Back half"})
        assert st == 200 and out["chapters"][2]["title"] == "Back half"
        st, out = server.api("POST", "/api/chapter_edit", {"project": "demo", "action": "drop", "ns": [1]})
        assert st == 200 and out["chapters"][0]["title"] == "T2"

    def test_errors(self, server, book):
        assert server.api("POST", "/api/chapter_edit", {"project": "demo", "action": "explode"})[0] == 400
        assert server.api("POST", "/api/chapter_edit", {"project": "demo", "action": "merge", "n": 99})[0] == 400
        assert server.api("POST", "/api/chapter_edit", {"project": "../x", "action": "merge", "n": 1})[0] == 400
        assert server.api("GET", "/api/chapters?project=nothere")[0] == 400
        assert server.api("GET", "/api/chapter_text?project=demo&n=abc")[0] == 400
        assert server.api("GET", "/api/chapter_text?project=demo&n=77")[0] == 400
        assert server.api("POST", "/api/chapter_edit", {"project": "adam_eve", "action": "merge", "n": 1})[0] == 400

    def test_refused_while_a_job_runs(self, server, book, monkeypatch):
        from studio_app.jobs import JOB
        monkeypatch.setattr(JOB, "running", True)
        assert server.api("POST", "/api/chapter_edit", {"project": "demo", "action": "rename", "n": 1, "title": "x"})[0] == 400


@pytest.mark.skipif(not shutil.which("node") or not (JS / "node_modules" / "jsdom").is_dir(), reason="node or jsdom is not installed (cd tests/js && npm install)")
def test_chapters_card_in_the_page(server, book):
    r = subprocess.run(["node", "chapters.js", f"http://127.0.0.1:{server.port}/?t={TOKEN}"], cwd=JS, capture_output=True, text=True, timeout=90)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["errors"] == [], out
    assert (out["rows0"], out["rows1"], out["title"]) == (4, 3, "Renamed") and "3 chapters" in out["summary"]
    assert [c["title"] for c in ce.load(book)["chapters"]][0] == "Renamed"
