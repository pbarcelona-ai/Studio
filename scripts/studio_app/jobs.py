"""studio_app.jobs"""
import os
import signal
import subprocess
import threading

from .common import PlanError
from .config import ROOT, clean_env
from .generation import film_video_steps, generation_steps
from .steps import project_slug, script_argv, shell_form


# ---------------------------------------------------------------- job runner
class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.lines, self.running, self.proc, self.stop_flag = [], False, None, False
        self.current = ""
        self.on_finish = None          # called (no arguments) after every job; the server sets it to the Kaggle clean-up

    def log(self, line):
        with self.lock:
            self.lines.append(line)

    def start(self, steps, opt):
        with self.lock:
            if self.running:
                raise PlanError("a job is already running")
            self.lines, self.running, self.stop_flag = [], True, False
        threading.Thread(target=self._run, args=(list(steps), opt), daemon=True).start()

    def _run(self, steps, opt):
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
            try:
                self.proc = subprocess.Popen(script_argv(step["argv"]), cwd=ROOT, env={**env_base, **step["env"]}, text=True,
                                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
                for line in self.proc.stdout:
                    self.log(line.rstrip("\n"))
                code = self.proc.wait()
            except FileNotFoundError as e:
                self.log(f"!! cannot start: {e}")
                code = 127
            if self.stop_flag:
                break
            if code not in step.get("ok_codes", (0,)):
                self.log(f"!! step failed with exit code {code}")
                if not keep_going:
                    self.log("Stopped. Fix the problem and run again (finished work is kept).")
                    break
        with self.lock:
            self.running = False
            self.current = ""
        self.log("\n===== job finished" + (" (stopped)" if self.stop_flag else ""))
        if self.on_finish:
            self.on_finish()

    def stop(self):
        self.stop_flag = True
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass


JOB = Job()
