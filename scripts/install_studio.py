#!/usr/bin/env python3
"""Install, update and start Pistachio's Studio: what the Windows installer's shortcuts and the macOS app run (milestone MI, rule 12).

  python scripts/install_studio.py [--launch] [--cli] [--3d] [--home DIR] [--payload DIR]

    (no option)  open the install page in the browser: a bar for the whole install and one for the current task, named in plain words,
                 a details log with "Copy the log", Cancel, Retry, and tick boxes for the optional parts (off by default)
    --launch     what the shortcuts and the app do: if the Studio is installed and up to date, start it; else show the install page
    --cli        install in this terminal instead (progress as text lines; used by CI and by people who prefer a terminal)
    --3d         also install the optional 3D depth view (about 2 GB)
    --home DIR   where the Studio lives (default: the folder this script is in). The macOS app uses ~/Library/Application Support/Pistachios Studio
    --payload DIR  copy the Studio's files from DIR into --home first (the macOS app passes the copy inside the app). Never touches projects/,
                 books/ or the saved settings

Standard library only: it runs on the Python the installer brings (python-build-standalone in runtime/python), before .venv exists.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import http.server
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from setup_engine import IS_WIN, STATE_DIR, USER_DATA, Ctx, Engine, StepFailed, Task, UvProgress, group_kwargs  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
OPTIONAL = {"3d": {"title": "The 3D depth view", "size": "about 2 GB", "requirements": "requirements-3d.txt"}}
UV_ENV = {"UV_PYTHON_DOWNLOADS": "never", "UV_LINK_MODE": "copy", "UV_NO_PROGRESS": "1"}


# ---- where things are
def runtime_python(home: Path) -> Path:
    """The Python the installer brings (runtime/python), else the one running this (a developer's checkout)."""
    py = home / "runtime" / "python" / ("python.exe" if IS_WIN else "bin/python3")
    return py if py.is_file() else Path(sys.executable)


def venv_python(venv: Path, windowless: bool = False) -> Path:
    return venv / "Scripts" / ("pythonw.exe" if windowless else "python.exe") if IS_WIN else venv / "bin" / "python"


def find_uv(home: Path) -> str:
    bundled = home / "runtime" / ("uv.exe" if IS_WIN else "uv")
    if bundled.is_file():
        return str(bundled)
    found = shutil.which("uv")
    if found:
        return found
    with contextlib.suppress(ImportError, FileNotFoundError):
        import uv  # type: ignore[import-not-found,unused-ignore]  # the uv package, if pip installed it next to this Python
        return str(uv.find_uv_bin())
    raise StepFailed("the uv tool is missing (it comes with the installer). Download the installer again and run it.")


def version_of(root: Path) -> str:
    try:
        for line in (root / "pyproject.toml").read_text(encoding="utf-8").splitlines():
            if line.startswith("version"):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "0"


def stamp_of(root: Path, options: dict) -> str:
    """Changes when the version, the requirements or the chosen parts change: then everything is checked and installed again."""
    h = hashlib.sha256(version_of(root).encode())
    for name in ("BUILD_ID", "requirements.txt", "constraints.txt", *(p["requirements"] for k, p in OPTIONAL.items() if options.get(k))):
        with contextlib.suppress(OSError):
            h.update((root / name).read_bytes())
    h.update(json.dumps(sorted(k for k, v in options.items() if v)).encode())
    return h.hexdigest()[:16]


# ---- the tasks
def copy_files(payload: Path) -> Task:
    def run(ctx: Ctx) -> None:
        entries = [p for p in sorted(payload.iterdir()) if p.name not in USER_DATA and not p.name.startswith(".git")]
        with ctx.staging("files") as stage:
            for i, p in enumerate(entries):                   # 1: copy everything into the staging folder
                ctx.check()
                ctx.progress(0.9 * i / max(1, len(entries)), f"Copying {p.name}")
                (shutil.copytree(p, stage / p.name, symlinks=True) if p.is_dir() else shutil.copy2(p, stage / p.name))
            old = ctx.home / STATE_DIR / "stage" / "old"
            shutil.rmtree(old, ignore_errors=True)
            old.mkdir(parents=True)
            for p in entries:                                  # 2: swap each one into place (quick; projects/ and books/ are never touched)
                dest = ctx.home / p.name
                if dest.exists() or dest.is_symlink():
                    os.replace(dest, old / p.name)
                os.replace(stage / p.name, dest)
            shutil.rmtree(old, ignore_errors=True)
    return Task("files", "Copying the Studio's files", run, weight=1, done=lambda ctx: payload.resolve() == ctx.home.resolve())


def check_python() -> Task:
    def run(ctx: Ctx) -> None:
        py = runtime_python(ctx.home)
        ctx.run([str(py), "-c", "import ssl, sqlite3, venv, sys; print('Python', sys.version.split()[0], 'is ready')"], "Checking Python")
    return Task("python", f"Installing Python {sys.version_info.major}.{sys.version_info.minor}", run, weight=1)   # this runs on that Python


def check_uv() -> Task:
    def run(ctx: Ctx) -> None:
        ctx.run([find_uv(ctx.home), "--version"], "Checking uv")
    return Task("uv", "Installing the Studio's tools (uv)", run, weight=1)


def make_venv() -> Task:
    def run(ctx: Ctx) -> None:
        partial = ctx.home / ".venv.partial"
        shutil.rmtree(partial, ignore_errors=True)
        try:
            ctx.run([find_uv(ctx.home), "venv", "--relocatable", "--python", str(runtime_python(ctx.home)), str(partial)], "Making .venv", env=UV_ENV)
            check_private(partial)
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
    return Task("venv", "Making the Studio's private Python (.venv)", run, weight=1)


def check_private(venv: Path) -> None:
    """The new .venv's Python must report .venv as its home. A wrapper script posing as Python (some tool suites ship one) does not, and uv
    would then install into that tool suite instead: refuse before anything is installed."""
    py = venv_python(venv)
    r = subprocess.run([str(py), "-c", "import sys; print(sys.prefix)"], capture_output=True, text=True, encoding="utf-8", check=False)
    if r.returncode != 0 or Path(r.stdout.strip()).resolve() != venv.resolve():
        raise StepFailed(f"the Python at {runtime_python(venv.parent)} cannot make a private environment (it reports {r.stdout.strip() or 'nothing'}). "
                         "Download the installer again; it brings its own Python.")


def install_reqs(tid: str, title: str, files: list[str], weight: float) -> Task:
    """Install requirement files into .venv.partial (made again if a cancelled run removed it)."""
    def run(ctx: Ctx) -> None:
        partial = ctx.home / ".venv.partial"
        if not venv_python(partial).is_file():
            make_venv().run(ctx)
        check_private(partial)                                 # never install anywhere but the Studio's own .venv
        argv = [find_uv(ctx.home), "pip", "install", "--python", str(venv_python(partial))]
        for f in files:
            argv += ["-r", str(ctx.home / f)]
        if (ctx.home / "constraints.txt").is_file() and tid == "requirements":
            argv += ["-c", str(ctx.home / "constraints.txt")]
        try:
            ctx.run(argv, title, on_line=UvProgress(ctx, title), env=UV_ENV)
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)        # never leave a half-filled .venv; the next run makes it again
            raise
    return Task(tid, title, run, weight=weight)


def put_in_place() -> Task:
    def run(ctx: Ctx) -> None:
        partial, venv, old = ctx.home / ".venv.partial", ctx.home / ".venv", ctx.home / STATE_DIR / "old-venv"
        if not venv_python(partial).is_file():
            raise StepFailed("the new tools are missing (an earlier run was stopped). Press Retry to make them again.")
        shutil.rmtree(old, ignore_errors=True)
        try:
            if venv.exists():
                old.parent.mkdir(parents=True, exist_ok=True)
                os.replace(venv, old)
            os.replace(partial, venv)
        except PermissionError as e:
            raise StepFailed("the Studio is still open and using its tools. Close the Studio, then press Retry.") from e
        shutil.rmtree(old, ignore_errors=True)
    return Task("place", "Putting the new tools in place", run, weight=0.5,
                done=lambda ctx: not (ctx.home / ".venv.partial").exists() and venv_python(ctx.home / ".venv").is_file())


def check_ffmpeg() -> Task:
    def run(ctx: Ctx) -> None:
        ctx.run([str(venv_python(ctx.home / ".venv")), "-c", "import imageio_ffmpeg as f; print('ffmpeg:', f.get_ffmpeg_exe())"], "Installing ffmpeg")
    return Task("ffmpeg", "Installing ffmpeg (joins clips into a film)", run, weight=0.5)


def check_kaggle() -> Task:
    def run(ctx: Ctx) -> None:
        code = "import importlib.util as u, sys; sys.exit(0 if u.find_spec('kaggle') else 1)"   # importing kaggle itself asks for a token
        ctx.run([str(venv_python(ctx.home / ".venv")), "-c", code], "Setting up Kaggle")
        ctx.log("Kaggle is ready. Your own Kaggle token is added later, in the Studio's Setup window.")
    return Task("kaggle", "Setting up Kaggle", run, weight=0.5)


def check_all() -> Task:
    def run(ctx: Ctx) -> None:
        ctx.run([str(venv_python(ctx.home / ".venv")), str(ctx.home / "scripts" / "studio.py"), "--help"], "Checking the Studio starts")
    return Task("check", "Checking everything works", run, weight=0.5)


def plan(options: dict, payload: Path | None = None) -> list[Task]:
    tasks = [copy_files(payload)] if payload else []
    tasks += [check_python(), check_uv(), make_venv(), install_reqs("requirements", "Installing the Studio's requirements", ["requirements.txt"], 4)]
    for key, part in OPTIONAL.items():
        if options.get(key):
            tasks.append(install_reqs(key, f"Downloading {part['title'].lower()} ({part['size']})", [part["requirements"]], 8))
    return tasks + [put_in_place(), check_ffmpeg(), check_kaggle(), check_all()]


def saved_state(home: Path) -> dict:
    try:
        s = json.loads((home / STATE_DIR / "state.json").read_text(encoding="utf-8"))
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def is_installed(home: Path, payload: Path | None, options: dict) -> bool:
    s = saved_state(home)
    return bool(s.get("finished")) and s.get("stamp") == stamp_of(payload or home, options) and venv_python(home / ".venv").is_file()


def start_studio(home: Path) -> subprocess.Popen:
    """Start the Studio from its .venv, detached (it opens the browser itself) so the installer can close."""
    py = venv_python(home / ".venv", windowless=True)
    log = home / "logs"
    log.mkdir(exist_ok=True)
    kw = group_kwargs(detached=True)
    with open(log / "studio-start.log", "a", encoding="utf-8") as out:
        return subprocess.Popen([str(py), str(home / "scripts" / "studio.py")], cwd=home, stdout=out, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, env={**os.environ, "PYTHONUTF8": "1"}, **kw)


# ---- the install page
class Installer:
    """One install: the engine, its options and the page server's token."""

    def __init__(self, home: Path, payload: Path | None, options: dict) -> None:
        self.home, self.payload = home, payload
        self.token = secrets.token_urlsafe(16)
        self.first = not saved_state(home)
        self.options = options if self.first else {**saved_state(home).get("options", {}), **{k: v for k, v in options.items() if v}}
        self.engine = self._engine()
        self.thread: threading.Thread | None = None
        self.opened = False

    def _engine(self) -> Engine:
        return Engine(plan(self.options, self.payload), self.home, stamp_of(self.payload or self.home, self.options), self.options)

    def begin(self, options: dict | None = None) -> None:
        if self.thread and self.thread.is_alive():
            return
        if options is not None and options != self.options:
            self.options = {k: bool(options.get(k)) for k in OPTIONAL}
            self.engine = self._engine()
        self.thread = self.engine.start()

    def state(self) -> dict:
        return {**self.engine.status(), "first": self.first, "options": self.options,
                "parts": [{"id": k, "title": p["title"], "size": p["size"]} for k, p in OPTIONAL.items()],
                "version": version_of(self.payload or self.home)}


def make_handler(inst: Installer, web: Path):
    files = {"/": ("setup_progress.html", "text/html"), "/static/js/progress.js": ("static/js/progress.js", "text/javascript"),
             "/static/js/installer.js": ("static/js/installer.js", "text/javascript")}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a) -> None:
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj: dict, code: int = 200) -> None:
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _allowed(self) -> bool:
            u = urlparse(self.path)
            tok = self.headers.get("X-Token") or parse_qs(u.query).get("t", [""])[0]
            return secrets.compare_digest(tok, inst.token) and self.headers.get("Host", "").startswith("127.0.0.1:")

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in files and path != "/":
                name, ctype = files[path]
                return self._send(200, (web / name).read_bytes(), ctype)       # scripts are not secret; the API needs the token
            if not self._allowed():
                return self._send(403, b"forbidden", "text/plain")
            if path == "/":
                return self._send(200, (web / files["/"][0]).read_bytes(), "text/html")
            if path == "/api/state":
                return self._json(inst.state())
            if path == "/api/log":
                return self._send(200, inst.engine.log_text().encode(), "text/plain")
            return self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            if not self._allowed():
                return self._send(403, b"forbidden", "text/plain")
            n = min(int(self.headers.get("Content-Length") or 0), 10_000)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                body = {}
            path = urlparse(self.path).path
            if path in ("/api/start", "/api/retry"):
                inst.begin(body.get("options") if isinstance(body.get("options"), dict) and inst.first else None)
            elif path == "/api/cancel":
                inst.engine.cancel()
            elif path == "/api/open":
                if inst.engine.status()["state"] != "done":
                    return self._json({"error": "not installed yet"}, 409)
                start_studio(inst.home)
                inst.opened = True
            else:
                return self._send(404, b"not found", "text/plain")
            return self._json(inst.state())

    return Handler


def serve(inst: Installer, open_browser: bool = True, idle_minutes: float = 30) -> None:
    """Show the install page and keep serving until the Studio is opened, or the page has been left alone for a while."""
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(inst, HERE / "web"))
    url = f"http://127.0.0.1:{srv.server_address[1]}/?t={inst.token}"
    print(f"Install page: {url}", flush=True)
    if not inst.first:
        inst.begin()                                          # an update or a resume: carry on with the parts chosen before
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if open_browser:
        webbrowser.open(url)
    end = time.monotonic() + idle_minutes * 60
    while not inst.opened and time.monotonic() < end:
        time.sleep(0.5)
        if inst.engine.status()["state"] == "running":
            end = time.monotonic() + idle_minutes * 60
    time.sleep(1.0)                                           # let the page get its last answer
    srv.shutdown()


def run_cli(inst: Installer) -> int:
    last = ""

    def show() -> None:
        nonlocal last
        s = inst.engine.status()
        line = f"[{s['percent']:5.1f}%] {s['task_title']}: {s['task_percent']:.0f}% {s['detail']}".rstrip()
        if s["task_title"] and line != last:
            last = line
            print(line, flush=True)

    inst.engine.on_change = show
    try:
        ok = inst.engine.run()
    except KeyboardInterrupt:
        inst.engine.cancel()
        ok = False
    s = inst.engine.status()
    print("Done. Start the Studio with the shortcut, or: " + str(venv_python(inst.home / ".venv")) + " scripts/studio.py" if ok else s["error"], flush=True)
    if not ok:
        print("The log is in " + str(inst.engine.log_file), flush=True)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--launch", action="store_true")
    ap.add_argument("--cli", action="store_true")
    ap.add_argument("--3d", dest="three_d", action="store_true")
    ap.add_argument("--home", type=Path, default=HERE)
    ap.add_argument("--payload", type=Path)
    ap.add_argument("--no-open", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    home = a.home.expanduser().resolve()
    home.mkdir(parents=True, exist_ok=True)
    payload = a.payload.resolve() if a.payload else None
    options = {"3d": a.three_d}
    if a.launch and is_installed(home, payload, {**saved_state(home).get("options", {}), **{k: v for k, v in options.items() if v}}):
        start_studio(home)
        return 0
    inst = Installer(home, payload, options)
    if a.cli:
        return run_cli(inst)
    serve(inst, open_browser=not a.no_open)
    return 0


if __name__ == "__main__":
    sys.exit(main())
