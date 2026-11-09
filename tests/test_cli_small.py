"""The small command-line scripts: film_format, plan_movies, book_build, book_continuity, rename_sequential, web_batch, merge_videos, prompts, nbkit."""
import csv
import json
import subprocess
import sys

import pytest

import bookkit
import nbkit
import prompts


def rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


class TestFilmFormat:
    def test_sets_aspect_and_chain(self, book, run_script):
        code, out = run_script("film_format.py", "demo", "--aspect", "2.39:1", "--chain", "on")
        assert code is None and "2.39:1" in out and "on" in out
        assert json.loads((book / "film_format.json").read_text()) == {"aspect": "2.39:1", "chain": True}
        assert {r["aspect"] for r in rows(book / "all_shots.csv")} == {"2.39:1"}

    def test_model_means_each_models_own_shape(self, book, run_script):
        run_script("film_format.py", "demo", "--aspect", "16:9")
        code, out = run_script("film_format.py", "demo", "--aspect", "model")
        assert "each model its own" in out and json.loads((book / "film_format.json").read_text())["aspect"] == ""

    def test_unknown_or_bad_book_exits_with_a_message(self, book, run_script):
        assert "no such book" in run_script("film_format.py", "ghost")[0]
        assert "bad project name" in run_script("film_format.py", "Bad Name")[0]


class TestPlanMovies:
    def test_prints_the_plan_and_writes_movies_json(self, book, run_script):
        code, out = run_script("plan_movies.py", "demo", "--minutes", "1")
        assert code is None and "shots: " in out and "chapters: " in out
        assert "shots" in json.loads((book / "movies.json").read_text())


def write_scripts(book, chapters=2, shots=2):
    (book / "scripts").mkdir(exist_ok=True)
    for c in range(1, chapters + 1):
        (book / "scripts" / f"chapter-{c:03d}.json").write_text(json.dumps({"chapter": c, "shots": [
            {"n": n, "prompt": f"scene {c}.{n}", "negative": "", "characters": ["Eve"], "location": "garden", "continues": n > 1,
             "speaker": "narrator", "narration": "A few words of narration for this shot.", "sfx": "wind", "music": "soft strings."}
            for n in range(1, shots + 1)]}))


class TestBookBuild:
    def test_builds_the_csvs_and_plans_movies(self, book, run_script):
        write_scripts(book)
        (book / "demo.json").write_text(json.dumps({**json.loads((book / "demo.json").read_text()), "music_theme": "a lone oud."}))
        code, out = run_script("book_build.py", "demo", "--minutes", "1")
        assert code is None and "demo: 4 shots in 2 chapters" in out
        shots = rows(book / "all_shots.csv")
        assert [(r["chapter"], r["shot"]) for r in shots] == [("demo-001", "1"), ("demo-001", "2"), ("demo-002", "1"), ("demo-002", "2")]
        assert shots[0]["characters"] == "Eve" and shots[1]["continues"] == "1" and shots[0]["continues"] == ""
        assert [r["chapter"] for r in rows(book / "all_chapters.csv")] == ["demo-001", "demo-002"]
        assert len(rows(book / "audio_shots.csv")) == 4
        chapters = rows(book / "audio_chapters.csv")
        assert chapters[0]["music"].startswith("a lone oud; cinematic score") and json.loads(rows(book / "audio_shots.csv")[0]["lines_json"])[0][0] == "narrator"
        assert (book / "movies.json").exists()

    def test_dialogue_lines_and_saved_voice_cast_survive(self, book, run_script):
        write_scripts(book, chapters=1, shots=1)
        p = book / "scripts" / "chapter-001.json"
        d = json.loads(p.read_text())
        d["shots"][0]["lines"] = [["Eve", "Hello"], ["Adam", "Hi"]]
        p.write_text(json.dumps(d))
        run_script("book_build.py", "demo")
        assert json.loads(rows(book / "audio_shots.csv")[0]["lines_json"]) == [["Eve", "Hello"], ["Adam", "Hi"]]

    def test_saved_prompt_edits_are_reapplied(self, book, run_script):
        write_scripts(book, chapters=1, shots=1)
        run_script("book_build.py", "demo")
        (book / "prompt_edits.json").write_text(json.dumps({"k": {"chapter": "demo-001", "shot": 1, "fields": {"prompt": {"edited": "my own words"}}}}))
        code, out = run_script("book_build.py", "demo")
        assert "re-applied 2 saved prompt edit" in out and rows(book / "all_shots.csv")[0]["prompt"] == "my own words"

    def test_no_scripts_yet(self, book, run_script):
        assert "no scripts yet" in run_script("book_build.py", "demo")[0]


GOOD = {"title": "Demo", "setting": "a valley", "visual_style": "warm light", "music_theme": "oud",
        "characters": [{"name": "Eve", "token": "a woman, long dark hair, red robe", "voice": "female"}], "locations": [{"name": "Garden", "token": "a walled garden"}]}


class TestBookContinuity:
    @pytest.fixture()
    def fresh(self, book):
        (book / "demo.json").unlink()
        (book / "chapters").mkdir()
        (book / "chapters" / "chapter-001.txt").write_text("In the beginning there was a garden.")
        (book / "chapters.json").write_text(json.dumps({"pdf": "demo.pdf", "chapters": [{"n": 1, "title": "One"}]}))
        return book

    def test_writes_the_continuity_book(self, fresh, run_script, monkeypatch):
        seen = {}

        def fake(prompt, system, model=None, engine="claude", validate=None, **kw):
            seen["prompt"], seen["engine"] = prompt, engine
            validate(GOOD)
            return dict(GOOD)
        monkeypatch.setattr(bookkit, "llm_json", fake)
        code, out = run_script("book_continuity.py", "demo")
        assert code is None and "1 characters, 1 locations" in out and "Eve [female]" in out
        assert json.loads((fresh / "demo.json").read_text())["title"] == "Demo" and "In the beginning" in seen["prompt"] and seen["engine"] == "claude"

    def test_refuses_to_overwrite_without_force(self, fresh, run_script, monkeypatch):
        (fresh / "demo.json").write_text("{}")
        monkeypatch.setattr(bookkit, "llm_json", lambda *a, **k: pytest.fail("must not call the model"))
        assert "already exists" in run_script("book_continuity.py", "demo")[0]

    def test_needs_ingest_first(self, fresh, run_script):
        (fresh / "chapters.json").unlink()
        assert "book_ingest" in run_script("book_continuity.py", "demo")[0]

    def test_validation_rules(self, fresh, run_script, monkeypatch):
        checks = []

        def fake(prompt, system, validate=None, **kw):
            for bad in ({**GOOD, "title": ""}, {**GOOD, "characters": "x"}, {**GOOD, "characters": [{"name": "A"}]},
                        {**GOOD, "characters": [{"name": "A", "token": "x" * 300, "voice": "female"}]},
                        {**GOOD, "characters": [{"name": "A", "token": "x", "voice": "robot"}]},
                        {**GOOD, "characters": [{"name": "A", "token": "x", "voice": "female", "stages": [{"label": "l", "chapters": "x", "token": "t"}]}]},
                        {**GOOD, "characters": [{"name": "A", "token": "x", "voice": "female", "stages": [{"label": "l", "chapters": "1-", "token": "t" * 300}]}]},
                        {**GOOD, "characters": [{"name": "A", "token": "x", "voice": "female", "stages": [{}] * 6}]}):
                with pytest.raises(ValueError):
                    validate(bad)
                checks.append(1)
            ok = {**GOOD, "characters": [{"name": "A", "token": "x", "voice": "female", "stages": [{"label": "old", "chapters": "13-", "token": "t"}]}]}
            validate(ok)
            return ok
        monkeypatch.setattr(bookkit, "llm_json", fake)
        run_script("book_continuity.py", "demo")
        assert len(checks) == 8

    def test_long_books_are_sampled(self, fresh, run_script, monkeypatch):
        n = 30
        (fresh / "chapters.json").write_text(json.dumps({"chapters": [{"n": i, "title": f"T{i}"} for i in range(1, n + 1)]}))
        for i in range(1, n + 1):
            (fresh / "chapters" / f"chapter-{i:03d}.txt").write_text(f"text {i}")
        got = {}
        monkeypatch.setattr(bookkit, "llm_json", lambda prompt, system, **k: (got.update(p=prompt), dict(GOOD))[1])
        run_script("book_continuity.py", "demo")
        assert got["p"].count("--- T") == 10


class TestRenameSequential:
    def test_moves_downloads_in_story_order_and_skips_tests(self, book, run_script, tmp_path):
        dl = tmp_path / "home" / "Downloads"
        dl.mkdir(parents=True)
        import os
        for i, name in enumerate(["b.mp4", "a.mp4", "my_test.mp4", "note.txt"]):
            (dl / name).write_text(name)
            os.utime(dl / name, (1000 + i, 1000 + i))
        (book / "videos").mkdir()
        (book / "videos" / "shot-0001.mp4").write_text("old")
        code, out = run_script("rename_sequential.py", "demo")
        assert (book / "videos" / "shot-0002.mp4").read_text() == "b.mp4" and (book / "videos" / "shot-0003.mp4").read_text() == "a.mp4"
        assert (dl / "my_test.mp4").exists() and (dl / "note.txt").exists() and "2 videos moved" in out


class TestWebBatch:
    def test_copies_each_prompt_and_resumes(self, book, run_script, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        copied, opened = [], []
        monkeypatch.setattr(subprocess, "run", lambda argv, input=None, **k: copied.append(input.decode()))
        import webbrowser
        monkeypatch.setattr(webbrowser, "open", opened.append)
        answers = iter([""] * 20)
        monkeypatch.setattr("builtins.input", lambda *a: next(answers))
        code, out = run_script("web_batch.py", "demo")
        assert copied[0] == "a woman walks in a garden" and len(copied) == 4 and "ALL DONE" in out and opened == ["https://krea.ai/video"]
        assert (tmp_path / ".batch_progress_demo_all_shots").read_text() == "4"
        copied.clear()
        run_script("web_batch.py", "demo")                    # finished already: nothing to copy
        assert copied == []


class TestMergeVideos:
    def test_joins_clips_in_numeric_order(self, book, run_script, monkeypatch):
        clips = book / "videos" / "ltx_video"
        clips.mkdir(parents=True)
        for n in (2, 10, 1):
            (clips / f"shot-{n:04d}.mp4").write_text("x")
        seen = {}

        def fake(argv, **kw):
            seen["argv"] = argv
            seen["list"] = open(argv[argv.index("-i") + 1]).read()
        monkeypatch.setattr(subprocess, "run", fake)
        monkeypatch.setattr("shutil.which", lambda n: "/usr/bin/ffmpeg")
        code, out = run_script("merge_videos.py", "videos/ltx_video", "out.mp4", "--project", "demo", "--end", "9")
        assert code is None and "merged 2 clips" in out
        assert [l.split("/")[-1] for l in seen["list"].split("'\n") if l] == ["shot-0001.mp4", "shot-0002.mp4"] and seen["argv"][-1].endswith("films/out.mp4")

    def test_no_clips_in_range(self, book, run_script, monkeypatch):
        (book / "videos" / "ltx_video").mkdir(parents=True)
        monkeypatch.setattr("shutil.which", lambda n: "/usr/bin/ffmpeg")
        assert "no shot-*.mp4" in run_script("merge_videos.py", "--project", "demo")[0]

    def test_no_ffmpeg_anywhere(self, book, run_script, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda n: None)
        monkeypatch.setitem(sys.modules, "imageio_ffmpeg", None)
        assert "No ffmpeg" in run_script("merge_videos.py", "--project", "demo")[0]


class TestPrompts:
    def test_adam_shots_reads_the_fenced_prompts(self, tmp_path):
        f = tmp_path / "c.md"
        f.write_text("# t\n## Video-generation prompts\n```\none\n```\ntext\n```text\ntwo\n```\n\n```\n\n```\n## Other\n```\nnot me\n```\n")
        assert prompts.adam_shots(f) == ["one", "two"]
        f.write_text("nothing")
        assert prompts.adam_shots(f) == []

    def test_enoch_prompt(self, tmp_path):
        f = tmp_path / "c.md"
        f.write_text("## Ready-to-paste video prompt\n  a prompt \n## Next\nx")
        assert prompts.enoch_prompt(f) == "a prompt"
        f.write_text("## Ready-to-paste video prompt\n\n## Next\n")
        assert prompts.enoch_prompt(f) is None
        f.write_text("none")
        assert prompts.enoch_prompt(f) is None

    def test_chapter_files_and_adam_eve_numbering(self, tmp_path, monkeypatch):
        b1, b2 = tmp_path / "b1", tmp_path / "b2"
        for d, ns in ((b1, (0, 1, 2)), (b2, (1,))):
            d.mkdir()
            for n in ns:
                (d / f"chapter-{n:03d}.md").write_text("")
            (d / "chapter-x.md").write_text("")
        assert [n for n, _ in prompts.chapter_files(b1, 1, 1)] == [1] and [n for n, _ in prompts.chapter_files(b1, 1)] == [1, 2]
        monkeypatch.setattr(prompts, "BOOK1", b1)
        monkeypatch.setattr(prompts, "BOOK2", b2)
        assert [l for l, _ in prompts.adam_eve_chapters()] == ["adam_eve-001", "adam_eve-002", "adam_eve-003"]


class TestNbkit:
    def test_cells_and_notebook(self, tmp_path, monkeypatch):
        c = nbkit.code("\nprint(1)\nprint(2)\n")
        assert c["cell_type"] == "code" and c["source"] == ["print(1)\n", "print(2)"] and nbkit.md("# T")["source"] == ["# T"]
        nb = nbkit.notebook_dict([c], {"x": 1})
        nbkit.write_notebook(tmp_path / "n.ipynb", nb)
        assert json.loads((tmp_path / "n.ipynb").read_text())["nbformat"] == 4

    def test_output_root_honours_the_env_var(self, monkeypatch, tmp_path):
        monkeypatch.setenv("STUDIO_GEN_DIR", str(tmp_path))
        assert nbkit.output_root() == tmp_path
        monkeypatch.delenv("STUDIO_GEN_DIR")
        assert nbkit.output_root() == nbkit.ROOT
