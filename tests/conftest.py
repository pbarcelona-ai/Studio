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
