"""Start-up: port choice and main() with the blocking and outward-facing parts replaced."""
import socket

import pytest

from studio_app import server as srv
from studio_app.session import SESSION


def test_make_server_skips_busy_ports():
    busy = socket.socket()
    busy.bind(("127.0.0.1", 0))
    busy.listen()
    port = busy.getsockname()[1]
    s = srv.make_server([port, 0])
    try:
        assert s.server_port != port and s.server_address[0] == "127.0.0.1"
    finally:
        s.server_close()
        busy.close()


def test_make_server_gives_up_when_nothing_is_free(monkeypatch):
    def refuse(*a, **k):
        raise OSError("in use")
    monkeypatch.setattr(srv, "StudioServer", refuse)
    with pytest.raises(SystemExit, match="no free port"):
        srv.make_server([1, 2])


def test_backlog_is_larger_than_the_default():
    assert srv.StudioServer.request_queue_size >= 128


class FakeHttpd:
    server_port = 4242

    def __init__(self, raise_interrupt=False):
        self.raise_interrupt, self.closed = raise_interrupt, False

    def serve_forever(self):
        if self.raise_interrupt:
            raise KeyboardInterrupt


@pytest.fixture
def quiet(monkeypatch, tmp_path):
    seen = {"opened": [], "saved": [], "cleanup": 0, "removed": 0}
    monkeypatch.setattr(srv.setup_check, "load_saved_env", lambda: None)
    monkeypatch.setattr(srv, "make_server", lambda ports: FakeHttpd(raise_interrupt=True))
    monkeypatch.setattr(srv.webbrowser, "open", lambda url: seen["opened"].append(url))
    monkeypatch.setattr(SESSION, "save", lambda port: seen["saved"].append(port))
    monkeypatch.setattr(SESSION, "remove", lambda: seen.__setitem__("removed", seen["removed"] + 1))
    monkeypatch.setattr(srv, "start_auto_cleanup", lambda: seen.__setitem__("cleanup", seen["cleanup"] + 1))
    monkeypatch.setattr(srv.JOB, "on_finish", None)
    return seen


def test_main_prints_the_link_and_cleans_up_on_ctrl_c(quiet, capsys):
    srv.main(["--no-open"])
    out = capsys.readouterr().out
    assert f"http://127.0.0.1:4242/?t={SESSION.token}" in out and "stopped" in out
    assert quiet["saved"] == [4242] and quiet["cleanup"] == 1 and quiet["removed"] == 1 and quiet["opened"] == []
    assert srv.JOB.on_finish is srv.start_auto_cleanup


def test_main_opens_the_browser_unless_told_not_to(quiet):
    srv.main([])
    assert len(quiet["opened"]) == 1 and quiet["opened"][0].startswith("http://127.0.0.1:4242/?t=")


def test_new_session_resets_the_token(quiet, monkeypatch):
    called = []
    monkeypatch.setattr(SESSION, "reset", lambda: called.append("reset"))
    srv.main(["--no-open", "--new-session"])
    assert called == ["reset"] and quiet["removed"] == 2        # once by --new-session, once on exit
