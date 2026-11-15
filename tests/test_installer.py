"""MI: the install engine (progress, cancel, retry, resume, downloads), the Studio's install plan and the install page's server."""
import http.server
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

import install_studio as ins
import setup_engine as se

ROOT = Path(__file__).resolve().parent.parent


def task(tid, fn=None, title=None, weight=1.0):
    return se.Task(tid, title or f"Doing {tid}", fn or (lambda ctx: None), weight=weight)


class TestEngine:
    def test_runs_in_order_with_progress_and_names(self, tmp_path):
        seen = []

        def half(ctx):
            ctx.progress(0.5, "half way")
            seen.append(ctx.engine.status())
        e = se.Engine([task("a"), task("b", half, "Installing Python 3.12")], tmp_path, stamp="s1")
        assert e.run()
        mid = seen[0]
        assert mid["task_title"] == "Installing Python 3.12 (2 of 2)" and mid["task_percent"] == 50 and mid["percent"] == 75 and mid["detail"] == "half way"
        s = e.status()
        assert s["state"] == "done" and s["percent"] == 100 and s["done"] == ["a", "b"]
        assert "Doing a (1 of 2)" in e.log_text() and (tmp_path / ".install" / "install.log").is_file()

    def test_failure_then_retry_carries_on(self, tmp_path):
        calls = {"a": 0, "b": 0}

        def a(ctx):
            calls["a"] += 1

        def b(ctx):
            calls["b"] += 1
            if calls["b"] == 1:
                raise se.StepFailed("the internet is off")
        e = se.Engine([task("a", a), task("b", b)], tmp_path)
        assert not e.run()
        s = e.status()
        assert s["state"] == "failed" and "the internet is off" in s["error"] and s["error"].startswith("Doing b")
        assert e.run() and calls == {"a": 1, "b": 2}

    def test_a_surprise_error_is_a_plain_failure(self, tmp_path):
        e = se.Engine([task("a", lambda ctx: 1 / 0)], tmp_path)
        assert not e.run() and "ZeroDivisionError" in e.status()["error"] and "Retry" in e.status()["error"]

    def test_resume_in_a_new_run_and_a_new_stamp_starts_again(self, tmp_path):
        ran = []
        mk = lambda: [task("a", lambda c: ran.append("a")), task("b", lambda c: (ran.append("b"), (_ for _ in ()).throw(se.StepFailed("x"))))]
        assert not se.Engine(mk(), tmp_path, stamp="v1").run()
        assert not se.Engine(mk(), tmp_path, stamp="v1").run()
        assert ran == ["a", "b", "b"]                        # a was remembered
        se.Engine(mk(), tmp_path, stamp="v2").run()
        assert ran[-2:] == ["a", "b"]                         # a new version does everything again

    def test_done_check_skips(self, tmp_path):
        t = se.Task("a", "A", lambda c: pytest.fail("should not run"), done=lambda c: True)
        assert se.Engine([t], tmp_path).run()

    def test_cancel_stops_a_program_and_removes_staging(self, tmp_path):
        made = {}

        def slow(ctx):
            with ctx.staging("x") as st:
                (st / "half").write_text("1")
                made["dir"] = st
                ctx.run([sys.executable, "-c", "import time; print('working', flush=True); time.sleep(60)"], "Waiting")
        e = se.Engine([task("a", slow)], tmp_path)
        th = e.start()
        for _ in range(100):
            if "working" in e.log_text():
                break
            time.sleep(0.1)
        t0 = time.monotonic()
        e.cancel()
        th.join(30)
        assert not th.is_alive() and time.monotonic() - t0 < 20
        s = e.status()
        assert s["state"] == "cancelled" and "half-installed" in s["error"] and not made["dir"].exists() and s["done"] == []

    def test_a_failing_program_says_so(self, tmp_path):
        e = se.Engine([task("a", lambda ctx: ctx.run([sys.executable, "-c", "print('boom'); raise SystemExit(4)"], "Installing uv"))], tmp_path)
        assert not e.run() and "Installing uv did not work (exit 4)" in e.status()["error"] and "boom" in e.log_text()

    def test_a_missing_program(self, tmp_path):
        e = se.Engine([task("a", lambda ctx: ctx.run(["no-such-program-xyz"], "Checking"))], tmp_path)
        assert not e.run() and "could not start" in e.status()["error"]


class TestDownloads:
    def test_detail_words(self):
        assert se.download_detail(145_000_000, 610_000_000, 45.0).startswith("145 MB of 610 MB, 3.2 MB/s, about")
        assert "min left" in se.download_detail(145_000_000, 610_000_000, 45.0)
        assert se.download_detail(1500, 0, 0) == "2 KB"

    def test_download_with_resume_and_checksum(self, tmp_path):
        import hashlib
        data = bytes(range(256)) * 2000

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                rng = self.headers.get("Range")
                start = int(rng.split("=")[1].rstrip("-")) if rng else 0
                self.send_response(206 if rng else 200)
                self.send_header("Content-Length", str(len(data) - start))
                self.end_headers()
                self.wfile.write(data[start:])
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_address[1]}/f"
            dest = tmp_path / "f.bin"
            (tmp_path / "f.bin.part").write_bytes(data[:1000])          # an earlier, stopped download
            sha = hashlib.sha256(data).hexdigest()
            e = se.Engine([task("d", lambda ctx: ctx.download(url, dest, sha, "Downloading the picture tools"))], tmp_path)
            assert e.run() and dest.read_bytes() == data
            e2 = se.Engine([task("d", lambda ctx: ctx.download(url, tmp_path / "g.bin", "0" * 64, "Downloading"))], tmp_path / "2")
            assert not e2.run() and "damaged" in e2.status()["error"] and not (tmp_path / "g.bin.part").exists()
        finally:
            srv.shutdown()


class TestUvProgress:
    def test_lines(self, tmp_path):
        e = se.Engine([task("a")], tmp_path)
        e._status.step = 1
        p = se.UvProgress(se.Ctx(e), "Installing")
        for line in ("Resolved 4 packages in 1s", "Downloading torch (610.0MiB)", "Prepared 4 packages in 3s", "Installed 4 packages in 1s"):
            p(line)
        s = e.status()
        assert 50 < s["task_percent"] <= 95 and s["detail"].startswith("Installing: Installed 4")


class TestPlan:
    def test_tasks_named_in_plain_words(self):
        titles = [t.title for t in ins.plan({})]
        assert titles[0].startswith("Installing Python 3.") and "Installing the Studio's tools (uv)" in titles and titles[-1] == "Checking everything works"
        assert "Setting up Kaggle" in titles and any("ffmpeg" in t for t in titles)
        assert len(ins.plan({"3d": True})) == len(titles) + 1 and any("3d depth view" in t for t in (x.title for x in ins.plan({"3d": True})))
        assert ins.plan({}, Path("/x"))[0].id == "files"

    def test_stamp_changes_with_requirements_and_parts(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('version = "1.2.3"\n')
        (tmp_path / "requirements.txt").write_text("a\n")
        s1 = ins.stamp_of(tmp_path, {})
        assert ins.version_of(tmp_path) == "1.2.3" and s1 == ins.stamp_of(tmp_path, {"3d": False}) and s1 != ins.stamp_of(tmp_path, {"3d": True})
        (tmp_path / "requirements.txt").write_text("a\nb\n")
        assert ins.stamp_of(tmp_path, {}) != s1

    def test_copy_files_keeps_projects_and_replaces_the_rest(self, tmp_path):
        payload, home = tmp_path / "payload", tmp_path / "home"
        (payload / "scripts").mkdir(parents=True)
        (payload / "scripts" / "studio.py").write_text("new")
        (payload / "projects").mkdir()
        (payload / "projects" / "x").write_text("from the app: must not land")
        (home / "scripts").mkdir(parents=True)
        (home / "scripts" / "old.py").write_text("old")
        (home / "projects" / "books" / "mine").mkdir(parents=True)
        e = se.Engine([ins.copy_files(payload)], home)
        assert e.run()
        assert (home / "scripts" / "studio.py").read_text() == "new" and not (home / "scripts" / "old.py").exists()
        assert (home / "projects" / "books" / "mine").is_dir() and not (home / "projects" / "x").exists()
        assert not (home / ".install" / "stage" / "files").exists()

    def test_put_in_place_swaps_and_needs_the_new_tools(self, tmp_path):
        e = se.Engine([ins.put_in_place()], tmp_path)
        assert not e.run() and "Retry" in e.status()["error"]
        new = ins.venv_python(tmp_path / ".venv.partial")
        new.parent.mkdir(parents=True)
        new.write_text("py")
        old = ins.venv_python(tmp_path / ".venv")
        old.parent.mkdir(parents=True)
        old.write_text("old")
        assert se.Engine([ins.put_in_place()], tmp_path, stamp="2").run()
        assert ins.venv_python(tmp_path / ".venv").read_text() == "py" and not (tmp_path / ".venv.partial").exists()

    def test_is_installed(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('version = "1"\n')
        assert not ins.is_installed(tmp_path, None, {})
        py = ins.venv_python(tmp_path / ".venv")
        py.parent.mkdir(parents=True)
        py.write_text("")
        se.Engine([task("a")], tmp_path, stamp=ins.stamp_of(tmp_path, {})).run()
        assert ins.is_installed(tmp_path, None, {}) and not ins.is_installed(tmp_path, None, {"3d": True})


class TestPage:
    @pytest.fixture
    def page(self, tmp_path, monkeypatch):
        (tmp_path / "pyproject.toml").write_text('version = "9.9"\n')
        inst = ins.Installer(tmp_path, None, {})
        monkeypatch.setattr(ins, "plan", lambda options, payload=None: [task("a", title="Checking everything works")])
        inst.engine = inst._engine()
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ins.make_handler(inst, ROOT / "web"))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        yield inst, f"http://127.0.0.1:{srv.server_address[1]}"
        srv.shutdown()

    def call(self, url, token, body=None):
        req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers={"X-Token": token})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode()

    def test_needs_the_token(self, page):
        inst, base = page
        with pytest.raises(urllib.error.HTTPError) as e:
            self.call(base + "/api/state", "wrong")
        assert e.value.code == 403
        assert "StudioProgress" in self.call(base + "/static/js/progress.js", "")      # the scripts are not secret
        assert "Installing Pistachio" in self.call(base + "/?t=" + inst.token, "")

    def test_start_state_log_open(self, page, monkeypatch):
        inst, base = page
        s = json.loads(self.call(base + "/api/state", inst.token))
        assert s["first"] and s["state"] == "ready" and s["parts"][0]["id"] == "3d" and s["version"] == "9.9"
        self.call(base + "/api/start", inst.token, {"options": {"3d": False}})
        inst.thread.join(10)
        assert json.loads(self.call(base + "/api/state", inst.token))["state"] == "done"
        assert "Everything is installed" in self.call(base + "/api/log", inst.token)
        started = []
        monkeypatch.setattr(ins, "start_studio", lambda home: started.append(home))
        self.call(base + "/api/open", inst.token, {})
        assert started == [inst.home] and inst.opened


def test_cli_install_with_a_failing_step(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ins, "plan", lambda options, payload=None: [task("a", lambda c: (_ for _ in ()).throw(se.StepFailed("no disk space")))])
    assert ins.main(["--cli", "--home", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "no disk space" in out and "install.log" in out


def test_launch_starts_an_installed_studio(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('version = "1"\n')
    py = ins.venv_python(tmp_path / ".venv")
    py.parent.mkdir(parents=True)
    py.write_text("")
    se.Engine([task("a")], tmp_path, stamp=ins.stamp_of(tmp_path, {})).run()
    started = []
    monkeypatch.setattr(ins, "start_studio", lambda home: started.append(home))
    assert ins.main(["--launch", "--home", str(tmp_path)]) == 0 and started == [tmp_path.resolve()]


def test_setup_window_part_install(tmp_path, monkeypatch):
    from studio_app import setup_install
    with pytest.raises(Exception, match="unknown part"):
        setup_install.part_engine("nope")
    monkeypatch.setattr(ins, "find_uv", lambda home: sys.executable)
    e = setup_install.part_engine("3d")
    e.home = tmp_path
    e.tasks[0].run = lambda ctx: ctx.run([sys.executable, "-c", "print('Installed 5 packages')"], "x", on_line=se.UvProgress(ctx, "x"))
    assert e.run() and e.status()["task_title"] == "" and e.status()["done"] == ["3d"]
    assert setup_install._state()["parts"][0]["size"] == "about 2 GB"


def test_setup_window_routes(tmp_path, monkeypatch):
    from studio_app import setup_install as si
    from studio_app.api import Request
    monkeypatch.setattr(si, "_current", None)
    assert si._get(Request())["state"] == "ready" and si._log(Request()) == {"log": ""}
    assert si._cancel(Request())["state"] == "ready" and si._retry(Request())["state"] == "ready"
    fails = {"n": 0}

    def fake_engine(part, python=""):
        def run(ctx):
            fails["n"] += 1
            if fails["n"] == 1:
                raise se.StepFailed("offline")
        return se.Engine([se.Task(part, "Installing it", run)], tmp_path, state_name="p.json")
    monkeypatch.setattr(si, "part_engine", fake_engine)
    si._start(Request(body={"part": "3d"}))
    si._current.status()                                    # noqa: B018
    for _ in range(50):
        if si._current.status()["state"] != "running":
            break
        time.sleep(0.05)
    assert si._get(Request())["state"] == "failed" and "offline" in si._log(Request())["log"]
    si._retry(Request())
    for _ in range(50):
        if si._current.status()["state"] == "done":
            break
        time.sleep(0.05)
    assert si._get(Request())["state"] == "done"
