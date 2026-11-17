"""The job runner: output capture, failure handling, stop, and recovery from internal errors."""
import sys
import time

import pytest

from studio_app import jobs
from studio_app.common import PlanError
from studio_app.jobs import Job


def step(code, label="t", **kw):
    return {"label": label, "argv": [sys.executable, "-c", code], "env": {}, **kw}


def test_runs_steps_in_order_and_captures_output():
    j = Job()
    j.start([step("print('one')", "a"), step("print('two')", "b")], {})
    assert j.wait(20)
    text = "\n".join(j.lines)
    assert text.index("one") < text.index("two") and "job finished" in text and not j.running


def test_failure_stops_the_plan_unless_keep_going():
    j = Job()
    j.start([step("import sys; sys.exit(3)", "bad"), step("print('after')", "next")], {})
    assert j.wait(20)
    text = "\n".join(j.lines)
    assert "exit code 3" in text and "after" not in text
    j.start([step("import sys; sys.exit(3)"), step("print('after')")], {"keep_going": True})
    assert j.wait(20) and "after" in "\n".join(j.lines)


def test_ok_codes():
    j = Job()
    j.start([step("import sys; sys.exit(7)", ok_codes=(0, 7)), step("print('went on')")], {})
    assert j.wait(20) and "went on" in "\n".join(j.lines)


def test_missing_program_is_reported_not_raised():
    j = Job()
    j.start([{"label": "x", "argv": ["/no/such/program"], "env": {}}], {})
    assert j.wait(20) and "cannot start" in "\n".join(j.lines) and not j.running


def test_only_one_job_at_a_time():
    j = Job()
    j.start([step("import time; time.sleep(5)")], {})
    try:
        with pytest.raises(PlanError, match="already running"):
            j.start([step("print(1)")], {})
    finally:
        j.stop()
        assert j.wait(20)


def test_stop_terminates_the_process_group():
    j = Job()
    j.start([step("import time; time.sleep(60)")], {})
    for _ in range(100):
        if j.proc is not None:
            break
        time.sleep(0.05)
    t0 = time.time()
    j.stop()
    assert j.wait(20) and time.time() - t0 < 15 and "(stopped)" in j.lines[-1]


def test_sigkill_after_grace_when_sigterm_is_ignored(monkeypatch):
    monkeypatch.setattr(jobs, "STOP_GRACE", 0.5)
    j = Job()
    j.start([step("import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); time.sleep(60)")], {})
    for _ in range(200):
        if "ready" in j.lines:
            break
        time.sleep(0.05)
    j.stop()
    assert j.wait(20) and "ready" in j.lines


def test_stop_before_the_process_exists_still_stops_it():
    j = Job()
    j.start([step("import time; time.sleep(60)")], {})
    j.stop()                                  # races with the thread that starts the process
    assert j.wait(30)


def test_internal_error_does_not_leave_the_job_running(monkeypatch):
    monkeypatch.setattr(Job, "_run_step", lambda self, s, e: 1 / 0)
    j = Job()
    done = []
    j.on_finish = lambda: done.append(1)
    j.start([step("print(1)")], {})
    assert j.wait(20) and not j.running and done == [1] and any("internal error" in line for line in j.lines)


class TestQueue:
    def test_a_queued_job_waits_and_then_runs_with_one_shared_log(self):
        j = Job()
        assert j.start([step("import time; time.sleep(0.4); print('first')", "a")], {}) == 0
        assert j.start([step("print('second')", "b")], {}, queue=True) == 1
        assert j.start([step("print('third')", "c")], {}, queue=True) == 2
        assert j.running and len(j.queue) == 2
        assert j.wait(30)
        text = "\n".join(j.lines)
        assert text.index("first") < text.index("second") < text.index("third")
        assert text.count("job finished") == 3 and "next queued job starts" in text and j.queue == [] and not j.running

    def test_without_queue_a_second_job_is_still_refused(self):
        j = Job()
        j.start([step("import time; time.sleep(0.5)")], {})
        with pytest.raises(PlanError, match="already running"):
            j.start([step("print(1)")], {})
        assert j.wait(20)

    def test_the_queue_has_a_limit(self):
        j = Job()
        j.start([step("import time; time.sleep(2)")], {})
        for i in range(jobs.MAX_QUEUE):
            j.start([step(f"print({i})")], {}, queue=True)
        with pytest.raises(PlanError, match="already waiting"):
            j.start([step("print(-1)")], {}, queue=True)
        with pytest.raises(PlanError, match="already waiting in the queue"):
            j.start([step("print(0)")], {}, queue=True)                         # the same job twice is refused (one lock per job)
        j.stop()
        assert j.queue == [] and j.wait(30)

    def test_stopping_drops_the_queue(self):
        j = Job()
        j.start([step("import time; time.sleep(30)", "long")], {})
        j.start([step("print('never')", "later")], {}, queue=True)
        time.sleep(0.3)
        j.stop()
        assert j.wait(30) and "never" not in "\n".join(j.lines) and j.queue == []

    def test_a_failed_job_does_not_stop_the_queue(self):
        j = Job()
        j.start([step("import sys; sys.exit(2)", "bad")], {})
        j.start([step("print('still ran')", "next")], {}, queue=True)
        assert j.wait(30) and "still ran" in "\n".join(j.lines)

    def test_on_finish_runs_once_after_the_last_job(self):
        j, calls = Job(), []
        j.on_finish = lambda: calls.append(1)
        j.start([step("print(1)")], {})
        j.start([step("print(2)")], {}, queue=True)
        assert j.wait(30) and calls == [1]


class TestQueueRoutes:
    def test_run_queues_when_asked(self, server, book, monkeypatch):
        from studio_app.jobs import JOB
        started = []
        monkeypatch.setattr(JOB, "start", lambda steps, opt, queue=False: (started.append((len(steps), queue)), 2 if queue else 0)[1])
        st, out = server.api("POST", "/api/run", {"project": "demo", "queue": True, "steps": {"continuity": True}})
        assert st == 200 and out["queued"] == 2 and started == [(1, True)]
        st, out = server.api("POST", "/api/run", {"project": "demo", "steps": {"continuity": True}})
        assert out["queued"] == 0 and started[-1][1] is False

    def test_the_log_reports_the_queue(self, server):
        assert server.api("GET", "/api/log?since=0")[1]["queued"] == 0


def test_a_step_never_inherits_another_pythons_settings(tmp_path):
    """The Studio started from a shell with the OSS CAD Suite set up: its wrapper sets PYTHONHOME and PYTHONEXECUTABLE and puts its folders
    first on PATH. The program a step runs gets none of it (a Kaggle upload stopped with "No module named 'encodings'")."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    sys.path.insert(0, str(scripts))
    import run_step
    env = run_step.clean_env({"PYTHONHOME": "/Applications/oss-cad-suite", "PYTHONEXECUTABLE": "/x/tabbypy3", "PYTHONPATH": "/y", "HOME": "/h",
                              "PATH": os.pathsep.join(["/Applications/oss-cad-suite/bin", "/usr/bin", "/Applications/OSS-CAD-Suite/py3bin"])})
    assert env == {"HOME": "/h", "PATH": "/usr/bin"}
    probe = tmp_path / "probe.py"
    probe.write_text("import os, json; print(json.dumps({k: os.environ.get(k) for k in ('PYTHONEXECUTABLE', 'PATH')}))")
    bad = str(tmp_path / "oss-cad-suite" / "bin")
    r = subprocess.run([sys.executable, str(scripts / "run_step.py"), sys.executable, str(probe)], capture_output=True, text=True,
                       env={**os.environ, "PYTHONEXECUTABLE": sys.executable, "PATH": bad + os.pathsep + os.environ.get("PATH", ""),
                            "STUDIO_EXIT_FILE": str(tmp_path / "exit")}, timeout=60)
    import json
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["PYTHONEXECUTABLE"] is None and bad not in got["PATH"]
    assert (tmp_path / "exit").read_text().strip() == "0"


def test_steps_start_with_the_studios_own_python(monkeypatch, tmp_path):
    import sys
    from studio_app import jobs as jobmod
    monkeypatch.setattr(jobmod, "ROOT", tmp_path)
    assert jobmod.step_python() == sys.executable                                 # no .venv: the Python that runs the Studio
    py = tmp_path / ".venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("")
    assert jobmod.step_python() == str(py)
    assert jobmod.step_command(["x"])[0] == str(py)
