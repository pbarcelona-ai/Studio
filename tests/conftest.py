"""Shared fixtures: a real Studio HTTP server on a free port with a known token, and a tiny HTTP client for it."""
import http.client
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from studio_app import handler  # noqa: E402
from studio_app.server import make_server  # noqa: E402
from studio_app.session import SESSION  # noqa: E402

TOKEN = "t" * 32


class Client:
    def __init__(self, port: int):
        self.port = port

    def request(self, method, path, body=None, headers=None, raw=None, host=None):
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        h.update(headers or {})
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        if data is not None:
            h.setdefault("Content-Type", "application/json")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for k, v in h.items():
            conn.putheader(k, v)
        if data is not None:
            conn.putheader("Content-Length", h.get("Content-Length", str(len(data))))
        conn.endheaders(data)
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        return resp.status, dict(resp.getheaders()), payload

    def api(self, method, path, body=None, token=TOKEN, **kw):
        headers = dict(kw.pop("headers", {}))
        if token:
            headers["X-Studio-Token"] = token
        status, hdrs, payload = self.request(method, path, body=body, headers=headers, **kw)
        try:
            return status, json.loads(payload)
        except ValueError:
            return status, payload


@pytest.fixture(scope="session")
def server():
    SESSION.token = TOKEN
    srv = make_server([0])
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield Client(srv.server_port)
    srv.shutdown()
    srv.server_close()


@pytest.fixture()
def project_tree(tmp_path, monkeypatch):
    """A throw-away projects folder for the file-serving routes: tmp/<slug>/..."""
    monkeypatch.setattr(handler, "pdir", lambda slug: tmp_path / slug)
    (tmp_path / "demo" / "videos").mkdir(parents=True)
    (tmp_path / "demo" / "videos" / "a.mp4").write_bytes(b"0123456789")
    (tmp_path / "demo" / "notes.txt").write_text("secret")
    (tmp_path / "outside.png").write_bytes(b"png")
    return tmp_path


# ---- a complete throw-away Studio folder: every module's ROOT/PROJECTS/... points into tmp_path
KEEP = {"SESSION_FILE", "LOG_FILE", "WEB", "CATALOG_FILE", "AUTO_CLEAN_OFF"}


@pytest.fixture()
def fake_root(tmp_path, monkeypatch):
    import importlib

    import bookkit
    import character_tokens
    import layout
    from studio_app import config

    for name in ("studio_app.cleanup", "studio_app.generation", "studio_app.media", "studio_app.gallery", "studio_app.llm", "studio_app.direction",
                 "studio_app.planner", "studio_app.projects", "studio_app.scenes", "studio_app.steps", "studio_app.takes", "studio_app.kaggle_cleanup",
                 "studio_app.kaggle_runs", "studio_app.overview", "studio_app.single_prompts", "studio_app.common", "studio_app.gpus", "studio_app.jobs"):
        importlib.import_module(name)
    real = config.ROOT
    root = tmp_path / "studio"
    (root / "projects" / "books").mkdir(parents=True)
    (root / "projects" / "prompts").mkdir()
    (root / "projects" / "characters").mkdir()
    (root / "books").mkdir()
    for mod in list(sys.modules.values()):
        mname = getattr(mod, "__name__", "")
        if not (mname.startswith("studio_app") or mname in ("layout", "bookkit", "character_tokens", "setup_check")):
            continue
        for attr, val in list(vars(mod).items()):
            if attr in KEEP or not isinstance(val, Path):
                continue
            try:
                rel = val.relative_to(real)
            except ValueError:
                continue
            monkeypatch.setattr(mod, attr, root / rel)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    assert root / "projects" / "books" == layout.BOOKS and root == bookkit.ROOT and root == character_tokens.ROOT
    return root


def write_csv(path, rows):
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)


@pytest.fixture()
def book(fake_root):
    """books/demo with 4 shots in one movie, chapters and a continuity book."""
    d = fake_root / "projects" / "books" / "demo"
    shots = [{"chapter": "1", "shot": i, "prompt": p, "negative": "", "width": 768, "height": 512, "frames": 49, "steps": 30, "guidance": 5, "seed": 1}
             for i, p in enumerate(["a woman walks in a garden", "a mountain at dawn", "he raises his hand", "a river at night"], 1)]
    write_csv(d / "all_shots.csv", shots)
    write_csv(d / "audio_shots.csv", [{"chapter": "1", "shot": i, "narration": f"line {i}", "sfx": "wind", "music": "calm"} for i in range(1, 5)])
    write_csv(d / "audio_chapters.csv", [{"chapter": "1", "music": "calm"}])
    (d / "movies.json").write_text(json.dumps({"shots": [{"id": 1, "rows": [1, 4]}]}))
    (d / "chapters.json").write_text(json.dumps({"chapters": [{"n": 1, "title": "One"}]}))
    (d / "demo.json").write_text(json.dumps({"title": "Demo", "setting": "s", "visual_style": "v", "music_theme": "m",
                                              "characters": [{"name": "Eve", "token": "a woman with long hair", "voice": "female"}], "locations": []}))
    return d


@pytest.fixture()
def run_script(monkeypatch, capsys):
    """Run one of the command-line scripts in scripts/ as `python scripts/<name> <args>` inside this process.
    Returns (exit code or None, stdout). Modules the script imports (bookkit, layout...) are the ones fake_root already redirected."""
    import runpy

    scripts = Path(__file__).resolve().parent.parent / "scripts"

    def run(name, *args):
        monkeypatch.setattr(sys, "argv", [name, *args])
        code = None
        try:
            runpy.run_path(str(scripts / name), run_name="__main__")
        except SystemExit as e:
            code = e.code if e.code is not None else 0
        return code, capsys.readouterr().out
    return run
