"""Small remaining gaps: step builders, session-file failures, job expansion and hooks, the layout command, model advice and prompt guides."""
import subprocess
import sys

import pytest

import layout
import model_advisor as ma
import prompt_guides as pg
from studio_app import jobs, session, steps
from studio_app.common import PlanError
from studio_app.jobs import Job


class TestBookArgs:
    def test_defaults(self):
        a = steps.book_args({})
        assert a[:2] == ["--narration", "condensed"] and "--min-shots" in a and "--force" not in a and "--scenes" not in a

    def test_every_option(self):
        a = steps.book_args({"narration": "dialogue", "words_per_shot": 30, "look": "claymation", "scenes": True, "clip_seconds": 5, "force_write": True, "chapters": "2-4",
                             "engine": "codex", "claude_model": "gpt-x", "min_shots": 2, "max_shots": 6})
        assert a[a.index("--words-per-shot"):a.index("--words-per-shot") + 2] == ["--words-per-shot", "30"]
        assert {"--look", "claymation", "--scenes", "--clip-seconds", "5.0", "--force", "--chapters", "2-4", "--engine", "codex", "--model", "gpt-x"} <= set(a)

    @pytest.mark.parametrize("opt,msg", [({"narration": "poem"}, "narration must be"), ({"chapters": "a-b"}, "chapters must look like"), ({"engine": "bing"}, "engine must be"),
                                          ({"claude_model": "x;rm"}, "model name may only")])
    def test_refused(self, opt, msg):
        with pytest.raises(PlanError, match=msg):
            steps.book_args(opt)


class TestBookSteps:
    def test_legacy_books_rebuild_their_csvs(self, fake_root):
        s = steps.book_steps({"steps": {"extract": True}, "enoch_chars": 100}, "enoch")
        assert [x["label"] for x in s] == ["Rebuild enoch prompt CSVs", "Plan movies"] and s[0]["argv"][-2:] == ["--enoch-chars", "100"]
        assert steps.book_steps({"steps": {}}, "adam_eve") == []
        assert steps.book_steps({"steps": {"extract": True}}, "adam_eve")[0]["argv"] == ["python3", "legacy_extract.py", "adam_eve"]

    def test_a_new_book_runs_every_ticked_step_in_order(self, book, fake_root):
        (fake_root / "books" / "story.txt").write_text("words " * 20)
        s = steps.book_steps({"steps": {"ingest": True, "continuity": True, "write": True, "build": True}, "pdf": "books/story.txt"}, "demo")
        assert [x["label"].split()[0] for x in s] == ["Read", "Write", "Write", "Build"]
        assert s[0]["argv"][:4] == ["uv", "run", "--with", "pypdf"] and s[0]["argv"][-1] == "books/story.txt"

    def test_the_book_to_read_must_exist(self, book):
        for pdf in ("books/missing.txt", "x.docx", ""):
            with pytest.raises(PlanError, match="choose a book to read"):
                steps.book_steps({"steps": {"ingest": True}, "pdf": pdf}, "demo")

    def test_a_pdf_already_in_the_book_folder(self, book):
        (book / "source").mkdir()
        (book / "source" / "b.pdf").write_bytes(b"%PDF")
        s = steps.book_steps({"steps": {"ingest": True}, "pdf": "b.pdf"}, "demo")
        assert s[0]["label"].startswith("Read PDF") and s[0]["argv"][-1].endswith("demo/source/b.pdf")

    def test_project_slug_rules(self, book, fake_root):
        assert steps.project_slug({"project": "demo"}) == "demo"
        with pytest.raises(PlanError, match="pick a book"):
            steps.project_slug({"project": "Bad Name"})
        with pytest.raises(PlanError, match="has not been started"):
            steps.project_slug({"project": "fresh"})
        assert steps.project_slug({"project": "fresh", "steps": {"ingest": True}, "pdf": "books/x.pdf"}) == "fresh"


class TestRunners:
    @pytest.mark.parametrize("service,first", [("colab", "scripts/run_colab_model.sh"), ("huggingface", "scripts/run_hf_space.sh"), ("computer", "python3"), ("kaggle", "scripts/run_kaggle_model.sh")])
    def test_each_service(self, service, first):
        argv, env = steps.make_runner(service, "T4", "pat", "demo")("ltx_video", 1, 4, "all_shots.csv")
        assert argv[0] == first and env["PROJECT"] == "demo" and env["SHOTS_CSV"] == "all_shots.csv"
        assert ("KAGGLE_USER" in env) == (service == "kaggle") and ("T4" in argv) == (service == "colab")

    def test_chunks(self):
        assert list(steps.chunks(1, 5, 2)) == [(1, 2), (3, 4), (5, 5)] and list(steps.chunks(1, 5, 0)) == [(1, 5)]


class TestSessionFile:
    def test_save_and_remove_survive_a_bad_location(self, tmp_path, monkeypatch):
        warnings = []
        monkeypatch.setattr(session.log, "warning", lambda msg, *a: warnings.append(msg % a))
        monkeypatch.setattr(session, "SESSION_FILE", tmp_path / "no" / "such" / "dir" / "s.json")
        s = session.Session()
        s.save(8765)                                   # cannot write: warns, does not raise
        monkeypatch.setattr(session, "SESSION_FILE", tmp_path)       # a folder: cannot be unlinked as a file
        s.remove()
        assert [w.split(":")[0] for w in warnings] == ["could not save the session file", "could not remove the session file"]

    def test_round_trip_and_reset(self, tmp_path, monkeypatch):
        monkeypatch.setattr(session, "SESSION_FILE", tmp_path / "s.json")
        s = session.Session()
        s.save(9000)
        assert oct((tmp_path / "s.json").stat().st_mode)[-3:] == "600" and session.Session().port == 9000
        token = s.token
        s.reset()
        assert s.token != token and s.port is None
        s.remove()
        assert not (tmp_path / "s.json").exists()


class TestJobExpansion:
    def test_an_expand_step_is_replaced_by_the_planned_steps(self, monkeypatch):
        monkeypatch.setattr(jobs, "project_slug", lambda opt: "demo")
        monkeypatch.setattr(jobs, "generation_steps", lambda opt, slug: [{"label": "made", "argv": [sys.executable, "-c", "print('generated')"], "env": {}}])
        j = Job()
        j.start([{"label": "later", "expand": "generation"}], {})
        j.thread.join(10)
        assert "planned 1 generation step(s)" in "\n".join(j.lines) and "generated" in "\n".join(j.lines)

    def test_film_expansion_and_planning_errors(self, monkeypatch):
        monkeypatch.setattr(jobs, "project_slug", lambda opt: "demo")
        monkeypatch.setattr(jobs, "film_video_steps", lambda opt, slug: (_ for _ in ()).throw(PlanError("no movies chosen")))
        j = Job()
        j.start([{"label": "later", "expand": "film_video"}], {})
        j.thread.join(10)
        assert "cannot plan the movies: no movies chosen" in "\n".join(j.lines)

    def test_a_failing_finish_hook_is_logged_not_raised(self):
        j = Job()
        j.on_finish = lambda: 1 / 0
        j.start([{"label": "x", "argv": [sys.executable, "-c", "pass"], "env": {}}], {})
        j.thread.join(10)
        assert not j.running

    def test_signalling_a_process_that_is_gone_is_fine(self):
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        Job._signal(p, 15)


class TestStudioCommand:
    def test_the_command_calls_main(self, run_script, monkeypatch):
        called = []
        import studio_app.server as server
        monkeypatch.setattr(server, "main", lambda: called.append(1))
        assert run_script("studio.py")[0] is None and called == [1]

    def test_an_old_python_is_refused_politely(self, run_script, monkeypatch):
        monkeypatch.setattr(sys, "version_info", (3, 9, 0, "final", 0))
        assert "needs Python 3.11" in run_script("studio.py")[0]


class TestLayoutCommand:
    def test_prints_the_folder(self, run_script):
        assert run_script("layout.py", "--kind", "prompts", "zz_new_set")[1].strip() == "projects/prompts/zz_new_set"
        assert run_script("layout.py", "zz_new_book")[1].strip() == "projects/books/zz_new_book"

    def test_usage_and_bad_names(self, run_script):
        assert "projects/" in str(run_script("layout.py")[0])
        assert "bad project name" in run_script("layout.py", "Bad Name")[0]

    def test_all_dirs(self, book, fake_root):
        assert layout.BOOKS / "demo" in layout.all_dirs()


class TestAdvisor:
    def test_the_look_is_not_added_twice(self):
        p, n = ma.apply_look("a street", "", "claymation")
        again = ma.apply_look(p, n, "claymation")
        assert again[0] == p and ma.apply_look("x", "y", "") == ("x", "y") and ma.apply_look("x", "y", "claymation", takes_negative=False)[1] == "y"

    def test_suggest_with_a_blocker_and_a_small_gpu(self):
        free = ma.suggest("live_action")
        assert all(v["pick"] for v in free.values())
        small = ma.suggest("live_action", gpu_gb=1)
        assert all(v["pick"] for v in small.values()) and any("slower on this GPU" in v["pick"]["why"] or v["alternatives"] for v in small.values())
        first = next(iter(free.values()))["pick"]["model"]
        blocked = ma.suggest("live_action", blocker=lambda m: "no" if m == first else None)
        assert any(a["blocked"] == "no" for v in blocked.values() for a in v["alternatives"])
        none = ma.suggest("live_action", blocker=lambda m: "no")
        assert all(v["pick"] is None for v in none.values())


class TestGuides:
    def test_family_and_guide(self):
        assert pg.family_for("image", "image_flux1_dev") == pg.family_for("image", "flux1_dev")
        assert "Length: 50-90 words" in pg.guide_for("video", "unknown_model")[0] and pg.guide_for("image")[1] == "30-70 words"
        for kind, model in (("image", "x"), ("video", "ltx_video"), ("image", "flux1_dev")):
            rules, words = pg.guide_for(kind, model)
            assert rules and words
