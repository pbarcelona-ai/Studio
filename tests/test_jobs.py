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
