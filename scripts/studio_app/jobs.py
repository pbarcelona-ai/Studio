"""Runs a plan (a list of validated steps) one step after another in a background thread, keeping the output for the page to poll.

A step is {"label", "argv": [...], "env": {...}, optional "ok_codes"}; argv is passed to subprocess WITHOUT a shell. Stopping sends SIGTERM to the
step's whole process group and SIGKILL if it is still alive after STOP_GRACE seconds."""
import os
import signal
import subprocess
import threading
from collections.abc import Callable

from .common import PlanError
from .config import ROOT, clean_env
from .generation import film_video_steps, generation_steps
from .log import get_logger
from .steps import project_slug, script_argv, shell_form

log = get_logger("jobs")
STOP_GRACE = 10.0          # seconds between SIGTERM and SIGKILL


class Job:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.lines: list[str] = []
        self.running = False
        self.proc: subprocess.Popen | None = None
        self.stop_flag = False
        self.current = ""
        self.thread: threading.Thread | None = None
        self.on_finish: Callable[[], None] | None = None          # called (no arguments) after every job; the server sets it to the Kaggle clean-up

    def log(self, line: str) -> None:
        with self.lock:
            self.lines.append(line)

    def start(self, steps: list[dict], opt: dict) -> None:
        with self.lock:
            if self.running:
                raise PlanError("a job is already running")
            self.lines, self.running, self.stop_flag = [], True, False
        self.thread = threading.Thread(target=self._run, args=(list(steps), opt), daemon=True)
        self.thread.start()

    def wait(self, timeout: float | None = None) -> bool:
        """Block until the running job ends (for tests and scripts). True if it has ended."""
        t = self.thread
        if t is not None:
            t.join(timeout)
        return not self.running

    def _run(self, steps: list[dict], opt: dict) -> None:
        try:
            self._run_steps(steps, opt)
        except Exception:                                    # whatever went wrong, the page must see the job end
            log.exception("job crashed")
            self.log("!! the job stopped because of an internal error (see studio.log)")
        finally:
            with self.lock:
                self.running = False
                self.current = ""
            self.log("\n===== job finished" + (" (stopped)" if self.stop_flag else ""))
            if self.on_finish:
                try:
                    self.on_finish()
                except Exception:
                    log.exception("on_finish hook failed")

    def _run_steps(self, steps: list[dict], opt: dict) -> None:
        keep_going = bool(opt.get("keep_going"))
        env_base = clean_env()
        n = 0
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
            code = self._run_step(step, env_base)
            if self.stop_flag:
                break
            if code not in step.get("ok_codes", (0,)):
                self.log(f"!! step failed with exit code {code}")
                if not keep_going:
                    self.log("Stopped. Fix the problem and run again (finished work is kept).")
                    break

    def _run_step(self, step: dict, env_base: dict[str, str]) -> int:
        try:
            proc = subprocess.Popen(script_argv(step["argv"]), cwd=ROOT, env={**env_base, **step["env"]}, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as e:                                  # not found, not executable, ...
            self.log(f"!! cannot start: {e}")
            return 127
        self.proc = proc
        if self.stop_flag:                                    # Stop was pressed while this step was starting
            self._terminate(proc)
        assert proc.stdout is not None
        for line in proc.stdout:
            self.log(line.rstrip("\n"))
        return proc.wait()

    def stop(self) -> None:
        self.stop_flag = True
        proc = self.proc
        if proc is not None and proc.poll() is None:
            self._terminate(proc)

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


JOB = Job()
