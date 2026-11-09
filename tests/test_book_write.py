"""book_write.py: planning (--dry-run) and writing each chapter's shots with a stand-in for the language model."""
import json
import re

import pytest

import bookkit

TEXT = ('Eve walked in the garden at dawn. She saw the river. "Come and see," said Eve to Adam. He answered, "I am coming." '
        "The sun rose over the hills. A bird sang from the tree. Night fell and the stars came out. They slept under the fig tree.")


@pytest.fixture()
def prose(book):
    (book / "chapters").mkdir()
    (book / "chapters" / "chapter-001.txt").write_text(TEXT)
    (book / "chapters.json").write_text(json.dumps({"chapters": [{"n": 1, "title": "One", "words": len(TEXT.split())}]}))
    return book


def fake_llm(calls, speakers=None, fail=False):
    def llm(prompt, system, validate=None, **kw):
        calls.append(prompt)
        if fail:
            raise RuntimeError("model down")
        if "script supervisor" in system:
            d = {"scenes": [{"first": 1, "title": "Garden", "location": "", "state": "dawn"}, {"first": 5, "title": "Night", "location": "", "state": "dark"}]}
        else:
            n = int(re.search(r"with exactly (\d+) shots", prompt).group(1))
            d = {"shots": [{"n": i, "visual": "a wide view of a quiet green garden at dawn", "characters": ["Eve", 5], "narration": f"narration {i}", "speaker": "Eve",
                            "speakers": speakers if speakers is not None else ["Eve", "Adam"], "sfx": "birds", "music": "harp", "location": "", "continues": True}
                           for i in range(1, n + 1)]}
        if validate:
            validate(d)
        return d
    return llm


class TestDryRun:
    def test_prints_the_plan_and_estimates(self, prose, run_script):
        code, out = run_script("book_write.py", "demo", "--dry-run", "--words-per-shot", "10", "--narration", "verbatim", "--scenes")
        assert code == 0 and "demo: 1 chapters, narration=verbatim" in out and "TOTAL:" in out and "Claude calls: 2 (two per chapter)" in out

    def test_warns_about_long_shots_and_gpu_hours(self, prose, run_script):
        code, out = run_script("book_write.py", "demo", "--dry-run", "--narration", "verbatim", "--words-per-shot", "1000", "--weekly-gpu-hours", "0.0001")
        assert "WARNING: each shot would last" in out and "weeks of a free GPU allowance" in out

    def test_dialogue_estimate_counts_only_quoted_words(self, prose, run_script):
        assert run_script("book_write.py", "demo", "--dry-run", "--narration", "dialogue")[0] == 0

    def test_many_chapters_are_summarised(self, prose, run_script):
        (prose / "chapters.json").write_text(json.dumps({"chapters": [{"n": i, "title": f"T{i}", "words": 200} for i in range(1, 16)]}))
        assert "3 more chapters" in run_script("book_write.py", "demo", "--dry-run")[1]


class TestWrite:
    def test_condensed(self, prose, run_script, monkeypatch):
        calls = []
        monkeypatch.setattr(bookkit, "llm_json", fake_llm(calls))
        code, out = run_script("book_write.py", "demo", "--min-shots", "2", "--max-shots", "2", "--look", "live_action")
        d = json.loads((prose / "scripts" / "chapter-001.json").read_text())
        assert code == 0 and "chapter 1: 2 shots written" in out and "failed chapters: none" in out
        s = d["shots"][0]
        assert d["narration_mode"] == "condensed" and s["narration"] == "narration 1" and s["speaker"] == "Eve" and s["voice"] == "af_bella"
        assert s["characters"] == ["Eve"] and s["continues"] is False and d["shots"][1]["continues"] is True and "woman with long hair" in s["prompt"]
        assert run_script("book_write.py", "demo", "--min-shots", "2", "--max-shots", "2")[1].count("writing 0") == 1 and len(calls) == 1      # finished chapters are skipped

    def test_force_rewrites(self, prose, run_script, monkeypatch):
        calls = []
        monkeypatch.setattr(bookkit, "llm_json", fake_llm(calls))
        run_script("book_write.py", "demo", "--max-shots", "1")
        run_script("book_write.py", "demo", "--max-shots", "1", "--force")
        assert len(calls) == 2

    def test_verbatim_uses_the_books_own_words(self, prose, run_script, monkeypatch):
        monkeypatch.setattr(bookkit, "llm_json", fake_llm([]))
        run_script("book_write.py", "demo", "--narration", "verbatim", "--words-per-shot", "30", "--min-shots", "2")
        shots = json.loads((prose / "scripts" / "chapter-001.json").read_text())["shots"]
        assert " ".join(s["narration"] for s in shots).split()[:5] == TEXT.split()[:5]

    def test_dialogue_speaks_only_the_quotes(self, prose, run_script, monkeypatch):
        monkeypatch.setattr(bookkit, "llm_json", fake_llm([], speakers=["Eve"]))
        code, out = run_script("book_write.py", "demo", "--narration", "dialogue", "--min-shots", "1", "--max-shots", "1", "--workers", "1")
        assert "FAILED" in out and code == 1                         # the stand-in names one speaker but there are two quotes
        monkeypatch.setattr(bookkit, "llm_json", fake_llm([], speakers=["Eve", "Adam"]))
        run_script("book_write.py", "demo", "--narration", "dialogue", "--min-shots", "1", "--max-shots", "1")
        shot = json.loads((prose / "scripts" / "chapter-001.json").read_text())["shots"][0]
        assert shot["lines"][0][:2] == ["Eve", "Come and see,"] and shot["lines"][1][0] == "NARRATOR"       # Adam is not in the continuity book
        assert shot["narration"] == "Come and see, I am coming."

    def test_scenes_are_found_first_and_cached(self, prose, run_script, monkeypatch):
        calls = []
        monkeypatch.setattr(bookkit, "llm_json", fake_llm(calls))
        run_script("book_write.py", "demo", "--scenes", "--min-shots", "3", "--max-shots", "3")
        outline = json.loads((prose / "scripts" / "outline-001.json").read_text())
        d = json.loads((prose / "scripts" / "chapter-001.json").read_text())
        assert [s["title"] for s in outline["scenes"]] == ["Garden", "Night"] and len(calls) == 2 and {s["scene"] for s in d["shots"]} == {"Garden", "Night"}
        assert any(not s["continues"] for s in d["shots"] if s["scene"] == "Night")

    def test_chapter_range_and_failures_exit_one(self, prose, run_script, monkeypatch):
        monkeypatch.setattr(bookkit, "llm_json", fake_llm([], fail=True))
        code, out = run_script("book_write.py", "demo", "--chapters", "1-1")
        assert code == 1 and "chapter 1: FAILED - model down" in out and "failed chapters: [1]" in out
        assert "0 chapters selected" in run_script("book_write.py", "demo", "--chapters", "5-9")[1]

    def test_global_params_and_dry_start_requirements(self, prose, run_script, monkeypatch):
        (prose / "global_params.json").write_text(json.dumps({"positives": "film grain", "negatives": "cartoon"}))
        calls = []
        monkeypatch.setattr(bookkit, "llm_json", fake_llm(calls))
        run_script("book_write.py", "demo", "--max-shots", "1")
        assert "Always include: film grain" in calls[0] and "cartoon" in json.loads((prose / "scripts" / "chapter-001.json").read_text())["shots"][0]["negative"]

    def test_look_supplies_style_words(self, prose, run_script, monkeypatch):
        calls = []
        monkeypatch.setattr(bookkit, "llm_json", fake_llm(calls))
        run_script("book_write.py", "demo", "--max-shots", "1", "--look", "claymation")
        assert "GLOBAL PROMPT PARAMETERS" in calls[0]


class TestStartRequirements:
    def test_needs_ingest_and_continuity_and_a_sane_clip_length(self, book, run_script):
        assert "clip-seconds" in run_script("book_write.py", "demo", "--clip-seconds", "99")[0]
        (book / "demo.json").unlink()
        assert "book_continuity" in run_script("book_write.py", "demo")[0]
        (book / "chapters.json").unlink()
        assert "book_ingest" in run_script("book_write.py", "demo")[0]
