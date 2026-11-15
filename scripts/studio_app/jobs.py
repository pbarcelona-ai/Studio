"""Runs a plan (a list of validated steps) one step after another in a background thread, keeping the output for the page to poll.

A step is {"label", "argv": [...], "env": {...}, optional "ok_codes"}; argv is passed to subprocess WITHOUT a shell (a fixed /bin/sh wrapper
only records the exit code). Stopping sends SIGTERM to the step's whole process group and SIGKILL if it is still alive after STOP_GRACE seconds.

A job outlives the Studio: each step runs in its own session and writes to a log file (logs/jobs/<job id>/step-N.log) with its exit code in
step-N.exit, and the job's state (its steps, options and where it is) is kept in logs/jobs/current.json. When the Studio starts again it
follows a step that is still running and then carries on with the rest (attach), or offers to continue a job that was cut off (resume).
"""
import json
import os
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .common import PlanError
from .config import ROOT, clean_env
from .generation import film_video_steps, generation_steps
from .log import get_logger
from .steps import project_slug, script_argv, shell_form

log = get_logger("jobs")
STOP_GRACE = 10.0          # seconds between SIGTERM and SIGKILL
MAX_QUEUE = 10             # jobs that may wait behind the running one
KEEP_JOBS = 20             # job folders kept in logs/jobs
POLL = 0.2                 # seconds between looks at a step's log file
WRAPPER = 'c=0; "$@" || c=$?; echo "$c" > "$STUDIO_EXIT_FILE"; exit "$c"'


def job_dir() -> Path:
    """Where job logs and the state file live (STUDIO_JOB_DIR overrides it; the tests use a temporary folder)."""
    return Path(os.environ.get("STUDIO_JOB_DIR") or (ROOT / "logs" / "jobs"))


def state_file() -> Path:
    return job_dir() / "current.json"


def read_state() -> dict:
    try:
        d = json.loads(state_file().read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(d: dict) -> None:
    f = state_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=1, default=str))
    os.chmod(tmp, 0o600)                                 # it holds the job's options (a Kaggle name, never a key)
    os.replace(tmp, f)


def pid_alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def exit_code(path) -> int | None:
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


class Job:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.lines: list[str] = []
        self.running = False
        self.proc: subprocess.Popen | None = None
        self.attached_pid: int | None = None                     # a step started by an earlier Studio that this one follows
        self.stop_flag = False
        self.current = ""
        self.thread: threading.Thread | None = None
        self.on_finish: Callable[[], None] | None = None          # called (no arguments) after the last job of a queue; the server sets it to the Kaggle clean-up
        self.queue: list[tuple[list[dict], dict]] = []             # jobs waiting for the running one; they start one after another, sharing one log
        self.state: dict = {}

    def log(self, line: str) -> None:
        with self.lock:
            self.lines.append(line)

    def start(self, steps: list[dict], opt: dict, queue: bool = False) -> int:
        """Start the plan, or (queue=True) put it behind the running job. Returns how many jobs wait ahead of it: 0 = it started now."""
        with self.lock:
            if self.running:
                if not queue:
                    raise PlanError("a job is already running")
                if len(self.queue) >= MAX_QUEUE:
                    raise PlanError(f"{MAX_QUEUE} jobs are already waiting: wait for some to finish")
                self.queue.append((list(steps), opt))
                self.lines.append(f"\n===== queued behind the running job ({len(self.queue)} waiting)")
                return len(self.queue)
            self.lines, self.running, self.stop_flag = [], True, False
        t = threading.Thread(target=self._run, args=(list(steps), opt), daemon=True)
        t.start()
        self.thread = t                  # set once started: wait() may join it at any moment
        return 0

    def wait(self, timeout: float | None = None) -> bool:
        """Block until the running job and the queue behind it have ended (for tests and scripts). True if they have."""
        end = None if timeout is None else time.time() + timeout
        while True:
            t = self.thread
            if t is not None:
                t.join(0.05 if end is None else max(0.0, min(0.05, end - time.time())))
            if not self.running:
                return True
            if end is not None and time.time() >= end:
                return False

    # ---- the state on disk
    def _new_state(self, steps: list[dict], opt: dict) -> None:
        jid = time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
        d = job_dir() / jid
        d.mkdir(parents=True, exist_ok=True)
        self.state = {"id": jid, "dir": str(d), "studio_pid": os.getpid(), "started": time.strftime("%Y-%m-%d %H:%M:%S"), "status": "running",
                      "project": opt.get("project") or opt.get("set") or "", "steps": steps, "opt": opt, "index": 0, "label": "",
                      "step_pid": None, "log": "", "exit": ""}
        self._save()
        self._prune()

    def _save(self, **kw) -> None:
        self.state.update(kw)
        try:
            write_state(self.state)
        except OSError:
            log.exception("could not save the job state")

    @staticmethod
    def _prune() -> None:
        try:
            dirs = sorted((p for p in job_dir().iterdir() if p.is_dir()), key=lambda p: p.name)
            for p in dirs[:-KEEP_JOBS]:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass

    # ---- running
    def _run(self, steps: list[dict], opt: dict, start_at: int = 0, fresh: bool = True) -> None:
        try:
            if fresh:
                self._new_state(steps, opt)
            self._run_steps(steps, opt, start_at)
        except Exception:                                    # whatever went wrong, the page must see the job end
            log.exception("job crashed")
            self.log("!! the job stopped because of an internal error (see studio.log)")
        finally:
            self.attached_pid = None
            if self.state:
                self._save(status="stopped" if self.stop_flag else "finished", ended=time.strftime("%Y-%m-%d %H:%M:%S"), step_pid=None)
            nxt = None
            with self.lock:
                self.current = ""
                self.lines.append("\n===== job finished" + (" (stopped)" if self.stop_flag else ""))     # before `running` drops, so a reader sees it
                if self.queue and not self.stop_flag:
                    nxt = self.queue.pop(0)               # the next one starts at once; `running` never drops in between
                else:
                    self.running = False
                    self.queue.clear()
            if nxt is not None:
                self.log(f"\n===== next queued job starts ({len(self.queue)} still waiting)")
                t = threading.Thread(target=self._run, args=nxt, daemon=True)
                t.start()
                self.thread = t                  # set once started: wait() may join it at any moment
            elif self.on_finish:
                try:
                    self.on_finish()
                except Exception:
                    log.exception("on_finish hook failed")

    def _run_steps(self, steps: list[dict], opt: dict, start_at: int = 0) -> None:
        keep_going = bool(opt.get("keep_going"))
        env_base = clean_env()
        n = start_at
        while n < len(steps):
            step = steps[n]
            n += 1
            if self.stop_flag:
                break
            if "expand" in step:
                try:
                    new = film_video_steps(opt, project_slug(opt)) if step["expand"] == "film_video" else generation_steps(opt, project_slug(opt))
                except PlanError as e:
                    self.log(f"!! cannot plan the movies: {e}")
                    break
                self.log(f"\n===== planned {len(new)} generation step(s) for the chosen movies")
                steps[n:n] = new
                continue
            self.current = f"{n}/{len(steps)} {step['label']}"
            self.log(f"\n===== [{n}/{len(steps)}] {step['label']}\n$ {shell_form(step)}")
            if self.state:
                self._save(steps=steps, index=n - 1, label=step["label"])
            code = self._run_step(step, env_base)
            if self.stop_flag:
                break
            if code not in step.get("ok_codes", (0,)):
                self.log(f"!! step failed with exit code {code}")
                if not keep_going:
                    self.log("Stopped. Fix the problem and run again (finished work is kept).")
                    break

    def _run_step(self, step: dict, env_base: dict[str, str]) -> int:
        argv = script_argv(step["argv"])
        prog = argv[0] if argv else ""
        if not prog or not (shutil.which(prog) or (os.sep in prog and os.access(prog if Path(prog).is_absolute() else ROOT / prog, os.X_OK))):
            self.log(f"!! cannot start: {prog or '(nothing)'} was not found")
            return 127
        d = Path(self.state.get("dir") or job_dir() / "loose")
        d.mkdir(parents=True, exist_ok=True)
        k = int(self.state.get("index", 0)) + 1
        logf, exitf = d / f"step-{k}.log", d / f"step-{k}.exit"
        exitf.unlink(missing_ok=True)
        env = {**env_base, **step["env"], "STUDIO_EXIT_FILE": str(exitf), "PYTHONUNBUFFERED": "1"}
        try:
            with open(logf, "ab") as out:
                proc = subprocess.Popen(["/bin/sh", "-c", WRAPPER, "sh", *argv], cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                        stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as e:                                  # not found, not executable, ...
            self.log(f"!! cannot start: {e}")
            return 127
        self.proc = proc
        if self.state:
            self._save(step_pid=proc.pid, log=str(logf), exit=str(exitf))
        if self.stop_flag:                                    # Stop was pressed while this step was starting
            self._terminate(proc)
        self._follow(logf, lambda: proc.poll() is not None)
        rc = proc.wait()
        code = exit_code(exitf)
        return code if code is not None else rc

    def _follow(self, logf: Path, done: Callable[[], bool], start: int = 0) -> None:
        """Copy the step's log file into the page's log as it grows, until `done()` and the file has been read to the end."""
        pos, part = start, b""
        while True:
            finished = done()
            try:
                with open(logf, "rb") as fh:
                    fh.seek(pos)
                    chunk = fh.read()
            except OSError:
                chunk = b""
            if chunk:
                pos += len(chunk)
                part += chunk
                *whole, part = part.split(b"\n")
                for ln in whole:
                    self.log(ln.decode("utf-8", "replace").rstrip("\r"))
            if finished and not chunk:
                if part:
                    self.log(part.decode("utf-8", "replace"))
                return
            if not chunk:
                time.sleep(POLL)

    # ---- after a restart
    def attach(self, state: dict) -> bool:
        """Follow a step that an earlier Studio started and that is still running, then carry on with the rest of its job. False if busy."""
        with self.lock:
            if self.running:
                return False
            self.lines, self.running, self.stop_flag = [], True, False
        self.state = dict(state)
        self.state["studio_pid"] = os.getpid()
        self.attached_pid = int(state["step_pid"])
        t = threading.Thread(target=self._attached, daemon=True)
        t.start()
        self.thread = t                  # set once started: wait() may join it at any moment
        return True

    def _attached(self) -> None:
        st = self.state
        steps, opt, idx = st["steps"], st.get("opt") or {}, int(st.get("index", 0))
        go_on = False
        try:
            self.current = f"{idx + 1}/{len(steps)} {st.get('label', '')}"
            self.log(f"===== carrying on with the job started {st.get('started', '')} by the last session of the Studio")
            self.log(f"===== [{idx + 1}/{len(steps)}] {st.get('label', '')} (still running: following its log)")
            self._save()
            pid, exitf = self.attached_pid, st.get("exit", "")
            self._follow(Path(st.get("log", "")), lambda: not pid_alive(pid) or Path(exitf).is_file())
            code = exit_code(exitf)
            ok = code is not None and code in tuple((steps[idx] or {}).get("ok_codes", (0,)))
            if not ok and not self.stop_flag:
                self.log(f"!! step failed with exit code {code if code is not None else 'unknown (it was cut off)'}")
                if not opt.get("keep_going"):
                    self.log("Stopped. Fix the problem and run again (finished work is kept).")
            go_on = not self.stop_flag and (ok or bool(opt.get("keep_going")))
        except Exception:
            log.exception("could not follow the earlier step")
            self.log("!! could not follow the earlier step (see studio.log)")
        self._run(steps if go_on else [], opt, start_at=idx + 1, fresh=False)

    def resume(self, state: dict, redo_step: bool) -> None:
        """Carry on with a job from an earlier session that was cut off: from the step that was cut off (redo_step) or the one after it."""
        with self.lock:
            if self.running:
                raise PlanError("a job is already running")
            self.lines, self.running, self.stop_flag = [], True, False
        self.state = dict(state, studio_pid=os.getpid(), status="running")
        idx = int(state.get("index", 0)) + (0 if redo_step else 1)
        self.log(f"===== carrying on with the job started {state.get('started', '')} (from step {idx + 1} of {len(state['steps'])})")
        t = threading.Thread(target=self._run, args=(state["steps"], state.get("opt") or {}), kwargs={"start_at": idx, "fresh": False}, daemon=True)
        t.start()
        self.thread = t                  # set once started: wait() may join it at any moment

    def stop(self) -> None:
        """Stop the running job. Jobs waiting behind it are dropped too (they were planned for after it)."""
        self.stop_flag = True
        with self.lock:
            self.queue.clear()
        proc = self.proc
        if proc is not None and proc.poll() is None:
            self._terminate(proc)
        pid = self.attached_pid
        if pid and pid_alive(pid):
            kill_group(pid)

    def _terminate(self, proc: subprocess.Popen) -> None:
        self._signal(proc, signal.SIGTERM)
        timer = threading.Timer(STOP_GRACE, self._kill_if_alive, args=(proc,))
        timer.daemon = True
        timer.start()

    @staticmethod
    def _signal(proc: subprocess.Popen, sig: int) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError):
            pass

    def _kill_if_alive(self, proc: subprocess.Popen) -> None:
        if proc.poll() is None:
            log.warning("step ignored SIGTERM; sending SIGKILL")
            self._signal(proc, signal.SIGKILL)


def kill_group(pid: int) -> None:
    """SIGTERM to the process group of pid (a step runs in its own session, so this is the step and everything it started), SIGKILL later."""
    try:
        pg = os.getpgid(pid)
        os.killpg(pg, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return

    def later():
        try:
            os.killpg(pg, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    t = threading.Timer(STOP_GRACE, later)
    t.daemon = True
    t.start()


JOB = Job()
