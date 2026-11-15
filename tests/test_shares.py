"""Private preview links: the store, the watch routes (no Studio token, only the linked film), expiry, revocation, hosts and Range."""
import sys
import http.client
import json

import pytest

import shares as sh


@pytest.fixture()
def films(book):
    d = book / "films"
    d.mkdir()
    (d / "cut.mp4").write_bytes(bytes(range(256)) * 40)
    (d / "cut.srt").write_text("1\n00:00:00,000 --> 00:00:01,500\nHello <there> & you.\n\n")
    (d / "other.mp4").write_bytes(b"other film")
    (book / "demo.json.secret").write_text("do not leak")
    return book


def get(server, path, host=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    conn.putrequest("GET", path, skip_host=True, skip_accept_encoding=True)
    conn.putheader("Host", host or f"127.0.0.1:{server.port}")
    for k, v in (headers or {}).items():
        conn.putheader(k, v)
    conn.endheaders()
    r = conn.getresponse()
    body = r.read()
    out = (r.status, dict(r.getheaders()), body)
    conn.close()
    return out


class TestStore:
    def test_create_lookup_expire_revoke(self, films):
        link = sh.create(films, "cut.mp4", 2, "  My   cut ", now=1000)
        assert len(link["token"]) >= 30 and link["expires"] == 1000 + 7200 and link["title"] == "My cut"
        assert sh.lookup(films, link["token"], now=1500)["film"] == "cut.mp4" and sh.lookup(films, "nope", now=1500) is None
        assert sh.lookup(films, link["token"], now=1500, count_view=True)["views"] == 1 and sh.listing(films, now=1500)[0]["views"] == 1
        assert sh.lookup(films, link["token"], now=1000 + 7201) is None and sh.listing(films) == []            # expired links are removed
        forever = sh.create(films, "other.mp4", 0)
        assert forever["expires"] is None and sh.lookup(films, forever["token"], now=10**12)
        assert sh.revoke(films, forever["token"]) is True and sh.revoke(films, forever["token"]) is False and sh.lookup(films, forever["token"]) is None

    def test_refusals(self, films):
        for film, hours in (("../x.mp4", 1), ("gone.mp4", 1), ("cut.srt", 1), ("cut.mp4", -1), ("cut.mp4", 10**6), ("cut.mp4", "abc")):
            with pytest.raises(sh.ShareError):
                sh.create(films, film, hours)
        for _ in range(sh.MAX_LINKS):
            sh.create(films, "cut.mp4")
        with pytest.raises(sh.ShareError, match="at most"):
            sh.create(films, "cut.mp4")

    def test_file_is_private_and_a_missing_film_ends_the_link(self, films):
        link = sh.create(films, "cut.mp4")
        assert sys.platform == "win32" or oct(sh.shares_file(films).stat().st_mode & 0o777) == "0o600"     # Windows has no permission bits
        (films / "films" / "cut.mp4").unlink()
        assert sh.lookup(films, link["token"]) is None
        sh.shares_file(films).write_text("[1]")
        assert sh.listing(films) == []

    def test_vtt(self):
        assert sh.srt_to_vtt("1\r\n00:00:01,500 --> 00:00:02,000\r\nHi\r\n") == "WEBVTT\n\n1\n00:00:01.500 --> 00:00:02.000\nHi\n"


class TestWatch:
    @pytest.fixture()
    def link(self, films):
        return sh.create(films, "cut.mp4", 24, "Rough <cut>")["token"]

    def test_the_page_the_film_and_the_captions_need_no_studio_token(self, server, films, link):
        st, hdrs, body = get(server, f"/watch/demo/{link}")
        page = body.decode()
        assert st == 200 and "<title>Rough &lt;cut&gt;</title>" in page and f"/watch/demo/{link}/film.mp4" in page and "captions.vtt" in page and "noindex" in hdrs["X-Robots-Tag"]
        st, hdrs, body = get(server, f"/watch/demo/{link}/film.mp4")
        assert st == 200 and hdrs["Content-Type"] == "video/mp4" and hdrs["Accept-Ranges"] == "bytes" and len(body) == 256 * 40
        st, hdrs, body = get(server, f"/watch/demo/{link}/captions.vtt")
        assert st == 200 and body.startswith(b"WEBVTT") and b"00:00:00.000 --> 00:00:01.500" in body and hdrs["Content-Type"].startswith("text/vtt")

    def test_range_requests(self, server, films, link):
        st, hdrs, body = get(server, f"/watch/demo/{link}/film.mp4", headers={"Range": "bytes=10-19"})
        assert st == 206 and body == bytes(range(10, 20)) and hdrs["Content-Range"] == "bytes 10-19/10240"

    def test_the_views_are_counted_on_the_page_only(self, server, films, link):
        get(server, f"/watch/demo/{link}")
        get(server, f"/watch/demo/{link}/film.mp4")
        assert sh.listing(films)[0]["views"] == 1

    def test_nothing_else_is_reachable(self, server, films, link):
        for path in (f"/watch/demo/{link}x", f"/watch/demo/{link[:-1]}", "/watch/demo/short", f"/watch/demo/{link}/other.mp4", f"/watch/demo/{link}/..%2Fdemo.json.secret",
                     f"/watch/demo/{link}/film.mp4/extra", f"/watch/ghost/{link}", "/watch/../x/" + link, "/watch/"):
            assert get(server, path)[0] == 404, path
        assert get(server, "/api/status")[0] == 403 and get(server, "/file/demo/films/cut.mp4")[0] == 403          # the link opens only /watch

    def test_revoked_and_expired_links_stop_working(self, server, films, link):
        sh.revoke(films, link)
        assert get(server, f"/watch/demo/{link}")[0] == 404 and get(server, f"/watch/demo/{link}/film.mp4")[0] == 404
        old = sh.create(films, "cut.mp4", 1, now=1000)["token"]                      # created long ago: already expired
        assert get(server, f"/watch/demo/{old}")[0] == 404

    def test_only_allowed_hosts(self, server, films, link, monkeypatch):
        assert get(server, f"/watch/demo/{link}", host="share.example.org")[0] == 404
        monkeypatch.setenv("STUDIO_WATCH_HOSTS", "share.example.org, other.example.org:8443")
        assert get(server, f"/watch/demo/{link}", host="share.example.org")[0] == 200
        assert get(server, f"/watch/demo/{link}", host="Other.Example.org:8443")[0] == 200
        assert get(server, f"/watch/demo/{link}", host="evil.example.org")[0] == 404
        assert get(server, "/api/status", host="share.example.org")[0] == 403          # the allowed host still cannot use the Studio


class TestApi:
    def test_make_list_and_revoke(self, server, films):
        out = server.api("POST", "/api/share", {"project": "demo", "film": "cut.mp4", "hours": 24, "title": "For the team"})[1]
        path = out["created"]
        assert path.startswith("/watch/demo/") and out["links"][0]["title"] == "For the team" and out["links"][0]["path"] == path
        assert get(server, path)[0] == 200
        listed = server.api("GET", "/api/shares?project=demo")[1]["links"]
        assert len(listed) == 1
        assert server.api("POST", "/api/share_revoke", {"project": "demo", "token": listed[0]["token"]})[1]["links"] == []
        assert get(server, path)[0] == 404
        assert server.api("POST", "/api/share_revoke", {"project": "demo", "token": "nope"})[0] == 400
        assert server.api("POST", "/api/share", {"project": "demo", "film": "../x.mp4"})[0] == 400
        assert server.api("POST", "/api/share", {"project": "ghost", "film": "cut.mp4"})[0] == 400
        assert json.loads(json.dumps(server.api("GET", "/api/shares?project=demo")[1])) == {"links": []}


def test_concurrent_views_never_bring_back_a_revoked_link(films):
    import threading
    link = sh.create(films, "cut.mp4", 24)["token"]
    other = sh.create(films, "other.mp4", 24)["token"]
    stop = threading.Event()

    def viewer():
        while not stop.is_set():
            sh.lookup(films, other, count_view=True)
    threads = [threading.Thread(target=viewer) for _ in range(4)]
    for t in threads:
        t.start()
    try:
        for _ in range(20):
            assert sh.revoke(films, link) in (True, False)
            assert sh.lookup(films, link) is None
            link = sh.create(films, "cut.mp4", 24)["token"]
            assert sh.revoke(films, link) is True
            assert sh.lookup(films, link) is None
    finally:
        stop.set()
        for t in threads:
            t.join()
    assert sh.lookup(films, other)["views"] > 0 and len(sh.listing(films)) == 1
