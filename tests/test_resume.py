"""Work that outlives a session of the Studio: steps write to log files and keep running, the next Studio follows them or carries on, and
Studio programs and Kaggle notebooks left running are found and reported (studio_app/jobs.py, studio_app/resume.py)."""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


from studio_app import jobs, procs, resume
from studio_app.common import PlanError
from studio_app.config import ROOT
from studio_app.jobs import Job


@pytest.fixture()
def jobdir(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_JOB_DIR", str(tmp_path / "jobs"))
    return tmp_path / "jobs"


def step(code, label="t"):
    return {"label": label, "argv": [sys.executable, "-c", code], "env": {}}


def test_a_step_writes_its_log_and_the_job_its_state(jobdir):
    j = Job()
    j.start([step("print('hello', flush=True)", "say hello")], {"project": "demo"})
    assert j.wait(20)
    st = jobs.read_state()
    assert st["status"] == "finished" and st["project"] == "demo" and st["label"] == "say hello"
    assert "hello" in Path(st["log"]).read_text() and jobs.exit_code(st["exit"]) == 0
    assert "hello" in j.lines


def _earlier(jobdir, code_now, more_steps, exit_now=None):
    """A job as an earlier session leaves it: step 1 of the plan started (still running, finished, or cut off)."""
    d = jobdir / "20260101-000000-1"
    d.mkdir(parents=True)
    logf, exitf = d / "step-1.log", d / "step-1.exit"
    proc = None
    if code_now is not None:
        out = open(logf, "ab")
        proc = subprocess.Popen(jobs.step_command([sys.executable, "-c", code_now]), stdout=out, stderr=subprocess.STDOUT,
                                env={**os.environ, "STUDIO_EXIT_FILE": str(exitf)}, **procs.group_kwargs())
        out.close()
    else:
        logf.write_text("pushing kernel pat/demo-image-keyframes-1-4\nworking...\n")
        if exit_now is not None:
            exitf.write_text(str(exit_now))
    steps = [step("pass", "make the pictures")] + more_steps
    jobs.write_state({"id": d.name, "dir": str(d), "studio_pid": 1, "started": "2026-01-01 00:00:00", "status": "running", "project": "demo",
                      "steps": steps, "opt": {"project": "demo"}, "index": 0, "label": "make the pictures",
                      "step_pid": proc.pid if proc else 999999, "log": str(logf), "exit": str(exitf)})
    return proc


def test_the_next_session_follows_a_step_that_is_still_running_and_carries_on(jobdir):
    proc = _earlier(jobdir, "import time\nprint('first half', flush=True)\ntime.sleep(1.5)\nprint('second half', flush=True)", [step("print('the next step')", "next")])
    time.sleep(0.4)
    info = resume.earlier_job()
    assert info["still_running"] and info["step"] == 1 and info["left"] == ["next"]
    j = Job()
    assert j.attach(jobs.read_state())
    assert j.running and j.attached_pid == proc.pid
    assert j.wait(30)
    text = "\n".join(j.lines)
    assert "carrying on with the job" in text and text.index("first half") < text.index("second half") < text.index("the next step")
    assert jobs.read_state()["status"] == "finished"
    proc.wait()


def test_a_failed_earlier_step_stops_the_job(jobdir):
    _earlier(jobdir, "import sys; sys.exit(4)", [step("print('never')", "next")])
    j = Job()
    assert j.attach(jobs.read_state()) and j.wait(30)
    text = "\n".join(j.lines)
    assert "exit code 4" in text and "never" not in text


def test_on_startup_attaches(jobdir, monkeypatch):
    proc = _earlier(jobdir, "import time; time.sleep(1)", [])
    j = Job()
    monkeypatch.setattr(resume, "JOB", j)
    resume.on_startup()
    assert j.running and j.wait(30)
    proc.wait()


def test_a_finished_step_offers_to_continue_from_the_next(jobdir, monkeypatch):
    _earlier(jobdir, None, [step("print('step two ran')", "two")], exit_now=0)
    info = resume.earlier_job()
    assert not info["still_running"] and info["step_exit"] == 0 and info["kernels"] == ["pat/demo-image-keyframes-1-4"]
    assert "working..." in info["log"]
    j = Job()
    monkeypatch.setattr(resume, "JOB", j)
    resume.sessions_action({"action": "continue"})
    assert j.wait(30)
    text = "\n".join(j.lines)
    assert "step two ran" in text and "[2/2] two" in text and "[1/2]" not in text


def test_a_cut_off_step_runs_again(jobdir, monkeypatch):
    _earlier(jobdir, None, [step("print('two')", "two")])           # no exit file: it was cut off
    j = Job()
    monkeypatch.setattr(resume, "JOB", j)
    resume.sessions_action({"action": "continue"})
    assert j.wait(30) and "[1/2] make the pictures" in "\n".join(j.lines)


def test_discard(jobdir):
    _earlier(jobdir, None, [], exit_now=1)
    resume.sessions_action({"action": "discard"})
    assert resume.earlier_job() is None and jobs.read_state()["status"] == "discarded"
    with pytest.raises(PlanError, match="no earlier job"):
        resume.sessions_action({"action": "continue"})
    with pytest.raises(PlanError, match="unknown"):
        resume.sessions_action({"action": "nope"})


@pytest.mark.skipif(sys.platform == "win32", reason="Windows finds Studio programs by the folder in their command line; this stand-in has none")
def test_studio_programs_left_running_are_found_and_can_be_stopped(jobdir, monkeypatch):
    monkeypatch.delenv("STUDIO_NO_BUSY_CHECK", raising=False)
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "scripts/run_local_model.py"], cwd=ROOT, start_new_session=True)
    try:
        for _ in range(50):
            found = [x for x in resume.studio_processes() if x["pid"] == p.pid]
            if found:
                break
            time.sleep(0.1)
        assert found and found[0]["kind"] == "GPU"
        assert "still working on this computer" in resume.busy_elsewhere()      # (another real run on this machine would say so too)
        with pytest.raises(PlanError, match="not a Studio program"):
            resume.sessions_action({"action": "stop", "pid": 1})
        resume.sessions_action({"action": "stop", "pid": p.pid})
        assert p.wait(15) != 0
        assert p.pid not in [x["pid"] for x in resume.studio_processes()]
    finally:
        if p.poll() is None:
            p.kill()


def test_kinds():
    assert resume.kind_of("bash scripts/run_kaggle_model.sh image_flux 1 40") == "GPU"
    assert resume.kind_of("python3 book_write.py demo") == "AI"
    assert resume.kind_of("python3 mix_film.py demo") == "other"


def test_sessions_data_and_kernel_status(jobdir, monkeypatch):
    _earlier(jobdir, None, [], exit_now=0)
    import studio_app.kaggle_runs as kr
    monkeypatch.setattr(kr, "kernel_status", lambda ref: {"ref": ref, "status": "RUNNING", "raw": ""})
    d = resume.sessions_data(with_kernels=True)
    assert d["job"]["project"] == "demo" and d["kernels"] == [{"ref": "pat/demo-image-keyframes-1-4", "status": "RUNNING", "raw": ""}]
    assert resume.sessions_data()["kernels"][0]["status"] is None


def test_routes(server, jobdir):
    status, data = server.api("GET", "/api/sessions")
    assert status == 200 and data["job"] is None and isinstance(data["processes"], list)
    status, data = server.api("POST", "/api/sessions", {"action": "nope"})
    assert status == 400


JS = Path(__file__).resolve().parent / "js"


@pytest.mark.skipif(not __import__("shutil").which("node") or not (JS / "node_modules" / "jsdom").is_dir(), reason="node or jsdom is not installed")
def test_the_page_warns_about_an_unfinished_job(server, jobdir, monkeypatch):
    monkeypatch.setattr(resume, "_ps", lambda: [])          # a real run on this computer would add its own warning
    import json
    from conftest import TOKEN
    _earlier(jobdir, None, [step("print(2)", "two")], exit_now=0)
    r = subprocess.run(["node", "sessions.js", f"http://127.0.0.1:{server.port}/?t={TOKEN}"], cwd=JS, capture_output=True, text=True, timeout=90)
    assert r.stdout.strip(), r.stderr[-600:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["errors"] == [], out
    assert not out["hidden0"] and "did not finish" in out["text"] and "Kaggle notebook pat/demo-image-keyframes-1-4" in out["text"]
    assert out["buttons"][:3] == ["Carry on (1 step(s) left)", "Do that step again", "Forget it"] and out["hidden1"]
