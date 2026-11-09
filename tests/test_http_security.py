"""Authentication, host/origin checks, cookies, size limits and file serving."""
import os

from conftest import TOKEN
from studio_app import handler
from studio_app.session import SESSION


def test_api_needs_token(server):
    assert server.api("GET", "/api/status", token=None)[0] == 403
    assert server.api("GET", "/api/status", token="wrong" * 8)[0] == 403
    assert server.api("GET", "/api/library")[0] == 200


def test_post_needs_token(server):
    assert server.api("POST", "/api/stop", {}, token=None)[0] == 403


def test_unicode_token_does_not_crash(server):
    status, _, _ = server.request("GET", "/api/status", headers={"X-Studio-Token": "é" * 40})
    assert status == 403


def test_bad_host_header_is_refused(server):
    assert server.api("GET", "/api/library", host="evil.example:80")[0] == 403


def test_bad_origin_is_refused(server):
    status, _ = server.api("GET", "/api/library", headers={"Origin": "http://evil.example"})
    assert status == 403


def test_good_origin_is_accepted(server):
    status, _ = server.api("GET", "/api/library", headers={"Origin": f"http://127.0.0.1:{server.port}"})
    assert status == 200


def test_token_link_sets_httponly_strict_cookie_and_redirects(server):
    status, hdrs, _ = server.request("GET", f"/?t={TOKEN}")
    assert status == 302 and hdrs["Location"] == "/"
    cookie = hdrs["Set-Cookie"]
    assert f"studio_token={TOKEN}" in cookie and "HttpOnly" in cookie and "SameSite=Strict" in cookie


def test_page_needs_token_or_cookie(server):
    assert server.request("GET", "/")[0] == 403
    assert server.request("GET", "/?t=nope")[0] == 403
    status, hdrs, body = server.request("GET", "/", headers={"Cookie": f"studio_token={TOKEN}"})
    assert status == 200 and b"<html" in body.lower()
    assert "default-src 'self'" in hdrs["Content-Security-Policy"] and hdrs["X-Content-Type-Options"] == "nosniff"


def test_cookie_authenticates_api(server):
    status, _, _ = server.request("GET", "/api/library", headers={"Cookie": f"studio_token={TOKEN}"})
    assert status == 200


def test_oversize_json_body_is_refused(server):
    status, _ = server.api("POST", "/api/plan", raw=b"{}", headers={"Content-Length": str(50 * 2**20)})
    assert status == 413


def test_bad_content_length_and_bad_json(server):
    assert server.api("POST", "/api/plan", raw=b"{}", headers={"Content-Length": "abc"})[0] == 400
    assert server.api("POST", "/api/plan", raw=b"{not json")[0] == 400
    assert server.api("POST", "/api/plan", raw=b"[1,2]")[0] == 400


def test_unknown_routes(server):
    assert server.api("GET", "/api/nope")[0] == 404
    assert server.api("POST", "/api/nope", {})[0] == 404


def test_internal_errors_do_not_leak(server, monkeypatch):
    from studio_app import routes_get

    def boom(_r):
        raise RuntimeError("secret internals /Users/someone")
    monkeypatch.setitem(__import__("studio_app.api", fromlist=["ROUTES"]).ROUTES["GET"], "/api/status", boom)
    status, body = server.api("GET", "/api/status")
    assert status == 500 and "secret" not in str(body) and routes_get


def test_static_files_do_not_escape(server):
    assert server.request("GET", "/static/../index.html")[0] in (403, 404)
    assert server.request("GET", "/static/%2e%2e/index.html")[0] in (403, 404)


class TestFileServing:
    def test_serves_media_with_range(self, server, project_tree):
        status, hdrs, body = server.request("GET", f"/file/demo/videos/a.mp4?t={TOKEN}", headers={"Range": "bytes=2-5"})
        assert status == 206 and body == b"2345" and hdrs["Content-Range"] == "bytes 2-5/10"

    def test_needs_token(self, server, project_tree):
        assert server.request("GET", "/file/demo/videos/a.mp4")[0] == 403

    def test_traversal_is_refused(self, server, project_tree):
        for p in ("/file/demo/../outside.png", "/file/demo/%2e%2e/outside.png", "/file/demo/videos/../../outside.png"):
            assert server.request("GET", f"{p}?t={TOKEN}")[0] == 404

    def test_non_media_and_bad_slugs_are_refused(self, server, project_tree):
        assert server.request("GET", f"/file/demo/notes.txt?t={TOKEN}")[0] == 404
        assert server.request("GET", f"/file/..%2f/a.mp4?t={TOKEN}")[0] == 404

    def test_symlink_escape_is_refused(self, server, project_tree):
        (project_tree / "demo" / "link.png").symlink_to(project_tree / "outside.png")
        assert server.request("GET", f"/file/demo/link.png?t={TOKEN}")[0] == 404

    def test_unsatisfiable_range(self, server, project_tree):
        status, _, _ = server.request("GET", f"/file/demo/videos/a.mp4?t={TOKEN}", headers={"Range": "bytes=50-60"})
        assert status == 416


def test_safe_project_file_unit(project_tree):
    ok = handler.safe_project_file("/file/", "/file/demo/videos/a.mp4", (".mp4",))
    assert ok == (project_tree / "demo" / "videos" / "a.mp4").resolve()
    assert handler.safe_project_file("/file/", "/file/demo/videos/a.mp4", (".png",)) is None
    assert handler.safe_project_file("/file/", "/file/demo", (".mp4",)) is None


def test_upload_rejects_wrong_type_and_size(server):
    assert server.api("POST", "/api/upload?filename=x.exe", raw=b"abc")[0] == 400
    assert server.api("POST", "/api/upload?filename=book.pdf", raw=b"not a pdf at all")[0] == 400
    assert server.api("POST", "/api/upload?filename=book.pdf", raw=b"")[0] == 400


def test_session_file_is_private_and_reloads(tmp_path, monkeypatch):
    from studio_app import session as S
    monkeypatch.setattr(S, "SESSION_FILE", tmp_path / "s.json")
    s = S.Session()
    s.save(1234)
    assert oct(os.stat(tmp_path / "s.json").st_mode & 0o777) == "0o600"
    again = S.Session()
    assert (again.token, again.port) == (s.token, 1234)
    s.reset()
    assert s.port is None and s.token != again.token
    (tmp_path / "s.json").write_text("{broken")
    assert S.Session().port is None


def test_session_matches(server):
    assert SESSION.matches(TOKEN) and not SESSION.matches("") and not SESSION.matches(TOKEN + "x")
