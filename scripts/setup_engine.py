"""The install engine behind the Windows and macOS installers and the Studio's Setup window (BOOK_TO_SCREEN_BUILD.md rule 12, milestone MI).

An install is a list of Tasks, each named in plain words ("Installing Python 3.12"). The Engine runs them in order and keeps a status that a page
shows as two bars: the whole install (task N of M, a percentage) and the current task (a percentage and a detail such as
"145 of 610 MB, 3.2 MB/s, about 2 min left"). Every line of work goes to a log the page can show and copy.

- Cancel at any time: the running program is stopped and the task's half-made files are removed (each task builds in a staging folder and
  moves it into place only when it is complete), so nothing is left half-installed.
- A failed task says what went wrong in plain words; Retry runs it again. Finished tasks are remembered in .install/state.json, so running the
  installer again carries on where it stopped. A new version (or new requirements) starts the list again, and updates never touch projects/,
  books/ or the saved settings (~/.pistachios_studio).

Standard library only: it runs on the Python the installer brings, before anything else is installed. Works on Windows and macOS.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

IS_WIN = sys.platform == "win32"
STATE_DIR = ".install"
USER_DATA = frozenset({"projects", "books", "my_downloads", "logs", ".venv", ".venv.partial", STATE_DIR, "studio.log", ".studio_session.json"})
LOG_KEEP = 4000                          # lines of the log kept in memory for the page


class Cancelled(Exception):
    """The person pressed Cancel."""


class StepFailed(Exception):
    """A task cannot finish; the message says why in plain words and what to do."""


@dataclass
class Task:
    id: str
    title: str                                           # plain words: "Installing Python 3.12"
    run: Callable[[Ctx], None]
    weight: float = 1.0                                  # share of the overall bar
    done: Callable[[Ctx], bool] | None = None            # already in place? (checked before running; a finished task is also remembered)


def human_mb(n: float) -> str:
    return f"{n / 1e6:.0f} MB" if n >= 1e6 else f"{n / 1e3:.0f} KB"


def download_detail(done: int, total: int, seconds: float) -> str:
    """'145 of 610 MB, 3.2 MB/s, about 2 min left' (no size known: '145 MB, 3.2 MB/s')."""
    speed = done / seconds if seconds > 0 else 0.0
    text = f"{human_mb(done)} of {human_mb(total)}" if total else human_mb(done)
    if speed > 0:
        text += f", {speed / 1e6:.1f} MB/s"
        if total and total > done:
            left = (total - done) / speed
            text += f", about {left / 60:.0f} min left" if left >= 90 else f", about {left:.0f} s left"
    return text


class Ctx:
    """What a task can use: the install folder, progress, the log, running programs and downloads, all of them cancellable."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.home = engine.home
        self.options = engine.options

    def log(self, text: str) -> None:
        self.engine.log(text)

    def progress(self, fraction: float, detail: str = "") -> None:
        self.engine.task_progress(fraction, detail)

    def check(self) -> None:
        if self.engine.cancel_event.is_set():
            raise Cancelled

    @contextlib.contextmanager
    def staging(self, name: str) -> Iterator[Path]:
        """A fresh folder under .install/ for building something; removed again if the task fails or is cancelled."""
        path = self.home / STATE_DIR / "stage" / name
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True)
        try:
            yield path
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def run(self, argv: list[str], what: str, on_line: Callable[[str], None] | None = None, cwd: Path | None = None,
            env: dict[str, str] | None = None) -> None:
        """Run a program (no shell), copying its output to the log line by line. Raises StepFailed (in plain words) if it fails, Cancelled if
        Cancel is pressed (the program and its children are stopped)."""
        self.check()
        self.log("$ " + " ".join(argv))
        kw = group_kwargs()
        try:
            p = subprocess.Popen(argv, cwd=cwd or self.home, env={**os.environ, "PYTHONUTF8": "1", **(env or {})}, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", **kw)
        except OSError as e:
            raise StepFailed(f"{what}: could not start {Path(argv[0]).name} ({e})") from e
        self.engine.child = p
        stopper = threading.Thread(target=self._stop_on_cancel, args=(p,), daemon=True)
        stopper.start()
        assert p.stdout is not None
        try:
            for line in p.stdout:
                line = line.rstrip()
                if line:
                    self.log(line)
                    if on_line:
                        on_line(line)
            code = p.wait()
        finally:
            if p.poll() is None:                              # an error in on_line: do not leave the program running
                stop_tree(p)
            self.engine.child = None
        self.check()
        if code != 0:
            raise StepFailed(f"{what} did not work (exit {code}). The last lines of the log say why; press Retry, or copy the log and ask for help.")

    def _stop_on_cancel(self, p: subprocess.Popen) -> None:
        while p.poll() is None:
            if self.engine.cancel_event.wait(0.2):
                stop_tree(p)
                return

    def download(self, url: str, dest: Path, sha256: str = "", label: str = "Downloading") -> Path:
        """Download with size, speed and time left; carries on a part-downloaded file (dest + '.part'); checks sha256 when given."""
        part = dest.with_name(dest.name + ".part")
        have = part.stat().st_size if part.is_file() else 0
        req = urllib.request.Request(url, headers={"User-Agent": "studio-installer", **({"Range": f"bytes={have}-"} if have else {})})
        self.log(f"download {url}")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310  installer URLs are fixed https addresses
                if have and r.status != 206:
                    have = 0                                   # the server ignored the range: start again
                total = int(r.headers.get("Content-Length") or 0) + have
                start, done = time.monotonic(), have
                with open(part, "ab" if have else "wb") as fh:
                    while chunk := r.read(1 << 16):
                        self.check()
                        fh.write(chunk)
                        done += len(chunk)
                        self.progress(done / total if total else 0.0, f"{label}: {download_detail(done - have, total - have, time.monotonic() - start)}")
        except OSError as e:
            raise StepFailed(f"{label} failed ({e}). Check the internet connection and press Retry; the download carries on where it stopped.") from e
        if sha256 and file_sha256(part) != sha256.lower():
            part.unlink(missing_ok=True)
            raise StepFailed(f"{label}: the downloaded file is damaged (wrong checksum). Press Retry to download it again.")
        os.replace(part, dest)
        return dest


def group_kwargs(detached: bool = False) -> dict:
    """Popen options that start a program in its own process group (so Cancel can stop it and its children); detached: no console window."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | (subprocess.DETACHED_PROCESS if detached else 0)}
    return {"start_new_session": True}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):                      # in pieces: a download can be several GB
            h.update(chunk)
    return h.hexdigest()


def stop_tree(p: subprocess.Popen) -> None:
    """Stop a program and everything it started."""
    if p.poll() is not None:
        return
    if IS_WIN:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, check=False)
    elif sys.platform != "win32":
        with contextlib.suppress(OSError):
            os.killpg(p.pid, signal.SIGTERM)
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError):
                os.killpg(p.pid, signal.SIGKILL)


@dataclass
class Status:
    state: str = "ready"              # ready | running | failed | cancelled | done
    step: int = 0                     # 1-based number of the current task
    steps: int = 0
    task: str = ""
    task_percent: float = 0.0
    detail: str = ""
    percent: float = 0.0
    error: str = ""
    done_ids: list[str] = field(default_factory=list)


class Engine:
    """Runs tasks in order with progress, cancel, retry and resume. status() and log_text() are safe to call from another thread."""

    def __init__(self, tasks: list[Task], home: Path, stamp: str = "", options: dict | None = None,
                 on_change: Callable[[], None] | None = None, state_name: str = "state.json") -> None:
        self.tasks = tasks
        self.state_name = state_name
        self.home = Path(home)
        self.stamp = stamp
        self.options = dict(options or {})
        self.on_change = on_change
        self.cancel_event = threading.Event()
        self.child: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._lines: list[str] = []
        self._status = Status(steps=len(tasks))
        self._done: list[str] = self._load_done()
        self._status.done_ids = list(self._done)

    # ---- state on disk (resume)
    @property
    def state_file(self) -> Path:
        return self.home / STATE_DIR / self.state_name

    @property
    def log_file(self) -> Path:
        return self.home / STATE_DIR / "install.log"

    def _load_done(self) -> list[str]:
        try:
            saved = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(saved, dict) or saved.get("stamp") != self.stamp:
            return []                                           # a new version or new requirements: do everything again
        ids = {t.id for t in self.tasks}
        return [i for i in saved.get("done", []) if i in ids]

    def _save(self, finished: bool = False) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"stamp": self.stamp, "done": self._done, "finished": finished, "options": self.options}, indent=1), encoding="utf-8")
        os.replace(tmp, self.state_file)

    # ---- log and progress
    def log(self, text: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {text}"
        with self._lock:
            self._lines.append(line)
            del self._lines[:-LOG_KEEP]
        with contextlib.suppress(OSError):
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        self._changed()

    def log_text(self) -> str:
        with self._lock:
            return "\n".join(self._lines)

    def task_progress(self, fraction: float, detail: str = "") -> None:
        with self._lock:
            s = self._status
            s.task_percent = round(max(0.0, min(1.0, fraction)) * 100, 1)
            if detail:
                s.detail = detail
            s.percent = self._overall(fraction)
        self._changed()

    def _overall(self, fraction: float) -> float:
        total = sum(t.weight for t in self.tasks) or 1.0
        done = sum(t.weight for t in self.tasks if t.id in self._done)
        cur = self.tasks[self._status.step - 1] if 0 < self._status.step <= len(self.tasks) else None
        if cur is not None and cur.id not in self._done:
            done += cur.weight * max(0.0, min(1.0, fraction))
        return round(done * 100 / total, 1)

    def _changed(self) -> None:
        if self.on_change:
            with contextlib.suppress(Exception):
                self.on_change()

    def status(self) -> dict:
        with self._lock:
            s = self._status
            title = f"{s.task} ({s.step} of {s.steps})" if s.task else ""
            return {"state": s.state, "step": s.step, "steps": s.steps, "task": s.task, "task_title": title, "task_percent": s.task_percent,
                    "detail": s.detail, "percent": s.percent, "error": s.error, "done": list(self._done),
                    "tasks": [{"id": t.id, "title": t.title, "done": t.id in self._done} for t in self.tasks]}

    def _set(self, **kw) -> None:
        with self._lock:
            for k, v in kw.items():
                setattr(self._status, k, v)
        self._changed()

    # ---- running
    def cancel(self) -> None:
        self.cancel_event.set()
        if self.child is not None:
            stop_tree(self.child)

    def run(self) -> bool:
        """Run every task not yet done, from the first. True when all are done; False after a failure or Cancel (status() says which)."""
        self.cancel_event.clear()
        self._set(state="running", error="")
        ctx = Ctx(self)
        for n, t in enumerate(self.tasks, 1):
            self._set(step=n, task=t.title, task_percent=0.0, detail="")
            if t.id in self._done:
                continue
            try:
                ctx.check()
                if t.done is not None and t.done(ctx):
                    self.log(f"{t.title}: already in place")
                else:
                    self.log(f"== {t.title} ({n} of {len(self.tasks)})")
                    t.run(ctx)
            except Cancelled:
                self.log("Cancelled. Nothing was left half-installed; run the installer again to carry on.")
                self._set(state="cancelled", error="Cancelled. Nothing was left half-installed; start again to carry on where it stopped.")
                return False
            except StepFailed as e:
                self.log(f"FAILED: {e}")
                self._set(state="failed", error=f"{t.title}: {e}")
                return False
            except Exception as e:  # noqa: BLE001  any surprise becomes a plain message with Retry, never a crash of the installer
                self.log(f"FAILED: {type(e).__name__}: {e}")
                self._set(state="failed", error=f"{t.title} went wrong ({type(e).__name__}: {e}). Press Retry, or copy the log and ask for help.")
                return False
            self._done.append(t.id)
            self._save()
            self.task_progress(1.0, "done")
        self._save(finished=True)
        self._set(state="done", task="", detail="", task_percent=100.0, percent=100.0)
        self.log("Everything is installed.")
        return True

    def start(self) -> threading.Thread:
        th = threading.Thread(target=self.run, daemon=True, name="install")
        th.start()
        return th


# ---- uv output: "Resolved 45 packages", "Downloading torch (610.0MiB)", "Prepared 12 packages", "Installed 45 packages"
_UV_RESOLVED = re.compile(r"Resolved (\d+) packages?")
_UV_DOWNLOADING = re.compile(r"Downloading (\S+) \(([\d.]+\s?[KMG]i?B)\)")
_UV_DONE = re.compile(r"^\s*(?:Downloaded|Built|Installed|Prepared|Audited) ")


class UvProgress:
    """Turns uv's output into a task percentage and a plain detail ("Downloading torch (610 MiB)")."""

    def __init__(self, ctx: Ctx, label: str) -> None:
        self.ctx, self.label, self.total, self.seen = ctx, label, 0, 0

    def __call__(self, line: str) -> None:
        if m := _UV_RESOLVED.search(line):
            self.total = int(m.group(1))
            self.ctx.progress(0.05, f"{self.label}: {self.total} packages")
        elif m := _UV_DOWNLOADING.search(line):
            self.seen += 1
            self.ctx.progress(self._fraction(), f"{self.label}: downloading {m.group(1)} ({m.group(2)})")
        elif _UV_DONE.search(line):
            self.seen += 1
            self.ctx.progress(self._fraction(), f"{self.label}: {line.strip()}")

    def _fraction(self) -> float:
        return min(0.95, 0.05 + 0.9 * self.seen / max(self.total, self.seen + 1))
