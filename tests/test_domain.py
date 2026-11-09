"""Pure planning logic: number validation, plan building, step formatting, install-line parsing, API dispatch."""
import math

import pytest

import run_local_model
from bookkit import SLUG_RE, slugify
from studio_app import api, steps
from studio_app.common import PlanError, num
from studio_app.planner import build_plan
from studio_app.steps import chunks, shell_form
from studio_app.single_prompts import snap


class TestNum:
    def test_default_and_cast(self):
        assert num({}, "x", 5, int) == 5
        assert num({"x": "7"}, "x", 5, int) == 7
        assert num({"x": ""}, "x", 2.5) == 2.5

    @pytest.mark.parametrize("bad", ["abc", [1], {"a": 1}, float("nan")])
    def test_rejects_non_numbers(self, bad):
        with pytest.raises(PlanError):
            num({"x": bad}, "x", 1.0)

    def test_range(self):
        assert num({"x": 3}, "x", 1, int, 1, 5) == 3
        for v in (0, 6):
            with pytest.raises(PlanError):
                num({"x": v}, "x", 1, int, 1, 5)

    def test_infinity_is_range_checked(self):
        with pytest.raises(PlanError):
            num({"x": math.inf}, "x", 1.0, float, 0, 10)


def test_chunks():
    assert list(chunks(1, 10, 4)) == [(1, 4), (5, 8), (9, 10)]
    assert list(chunks(1, 3, 0)) == [(1, 3)]
    assert list(chunks(5, 4, 2)) == []


def test_snap():
    assert snap(500, 64, 256, 1024) == 512
    assert snap(10, 64, 256, 1024) == 256
    assert snap(5000, 64, 256, 1024) == 1024


def test_slug_rules():
    assert slugify("Hello World!.pdf") == "hello_world_pdf"
    assert SLUG_RE.match("book1_full") and not SLUG_RE.match("../etc") and not SLUG_RE.match("a")


class TestPlan:
    @pytest.fixture(autouse=True)
    def project(self, tmp_path, monkeypatch):
        (tmp_path / "demo").mkdir()
        monkeypatch.setattr(steps, "pdir", lambda slug: tmp_path / slug)

    def test_needs_a_project(self):
        with pytest.raises(PlanError, match="pick a book"):
            build_plan({})
        with pytest.raises(PlanError, match="pick a book"):
            build_plan({"project": "../etc"})

    def test_needs_a_step(self):
        with pytest.raises(PlanError, match="nothing selected"):
            build_plan({"project": "demo"})

    def test_unknown_project_is_refused(self):
        with pytest.raises(PlanError, match="has not been started"):
            build_plan({"project": "ghost", "steps": {"continuity": True}})

    def test_continuity_and_build_steps(self):
        plan = build_plan({"project": "demo", "steps": {"continuity": True, "build": True}, "movie_minutes": 5})
        assert [s["label"] for s in plan] == ["Write the continuity book", "Build CSVs and plan movies"]
        assert plan[1]["argv"][-2:] == ["--minutes", "5.0"]

    def test_movie_minutes_validated(self):
        with pytest.raises(PlanError):
            build_plan({"project": "demo", "steps": {"build": True}, "movie_minutes": 9999})

    def test_ingest_refuses_unknown_or_wrong_file(self):
        with pytest.raises(PlanError, match="choose a book"):
            build_plan({"project": "demo", "steps": {"ingest": True}, "pdf": "../../etc/passwd"})
        with pytest.raises(PlanError, match="choose a book"):
            build_plan({"project": "demo", "steps": {"ingest": True}, "pdf": "books/missing.pdf"})

    def test_every_step_is_a_validated_argv_list_not_a_shell_string(self):
        for s in build_plan({"project": "demo", "steps": {"continuity": True, "build": True}}):
            assert isinstance(s["argv"], list) and all(isinstance(a, str) for a in s["argv"])


def test_shell_form_shows_env_and_scripts():
    text = shell_form({"label": "x", "argv": ["python3", "book_build.py", "demo"], "env": {"A": "1"}})
    assert text.startswith("A=1 python3 ") and text.endswith("demo")
    assert "chosen when the earlier steps finish" in shell_form({"label": "later", "expand": True})


class TestPipLines:
    def test_plain_and_quoted(self):
        assert run_local_model.pip_argv('pip install -q "numpy<2" foo==1.0') == ["pip", "install", "-q", "numpy<2", "foo==1.0"]
        assert run_local_model.pip_argv("pip3 install x")[0] == "pip"

    @pytest.mark.parametrize("line", ["pip install a && rm -rf x", "pip install a | tee f", "pip install $(whoami)", "pip install a; ls", "pip install a > f"])
    def test_shell_syntax_is_refused(self, line):
        with pytest.raises(SystemExit):
            run_local_model.pip_argv(line)


class TestDispatch:
    def test_status_codes(self):
        def reg(path, fn):
            api.ROUTES["GET"][path] = fn
        reg("/t/plan", lambda r: (_ for _ in ()).throw(PlanError("nope")))
        reg("/t/http", lambda r: (_ for _ in ()).throw(api.HttpError(418, "teapot")))
        reg("/t/key", lambda r: {}["x"])
        reg("/t/boom", lambda r: 1 / 0)
        reg("/t/ok", lambda r: {"a": 1})
        reg("/t/tuple", lambda r: (202, {"b": 2}))
        try:
            req = api.Request()
            assert api.dispatch("GET", "/t/plan", req) == (400, {"error": "nope"})
            assert api.dispatch("GET", "/t/http", req) == (418, {"error": "teapot"})
            assert api.dispatch("GET", "/t/key", req)[0] == 400
            assert api.dispatch("GET", "/t/boom", req) == (500, {"error": "internal error (see studio.log)"})
            assert api.dispatch("GET", "/t/ok", req) == (200, {"a": 1})
            assert api.dispatch("GET", "/t/tuple", req) == (202, {"b": 2})
            assert api.dispatch("GET", "/t/missing", req)[0] == 404
        finally:
            for p in ("plan", "http", "key", "boom", "ok", "tuple"):
                api.ROUTES["GET"].pop(f"/t/{p}")

    def test_duplicate_route_is_a_bug(self):
        with pytest.raises(RuntimeError):
            api.route("GET", "/api/status")(lambda r: {})

    def test_every_page_route_exists(self):
        """The routes the page calls must stay registered (guards the refactor)."""
        from studio_app import handler  # noqa: F401
        for p in ("/api/status", "/api/scenes", "/api/log", "/api/characters", "/api/library"):
            assert p in api.ROUTES["GET"]
        for p in ("/api/plan", "/api/run", "/api/stop", "/api/make_film", "/api/characters", "/api/copy_file"):
            assert p in api.ROUTES["POST"]
