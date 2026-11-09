"""Upload success and failure paths, static files, thumbnails and GET routes, against a throw-away Studio folder."""
import pytest
from PIL import Image

from studio_app.single_prompts import model_advisor

LOOK = next(iter(model_advisor.LOOKS))
PDF = b"%PDF-1.4\n" + b"x" * 50
TEXT = b"Once upon a time there was a small green dragon who loved books."


def upload(server, name, data, **kw):
    return server.api("POST", f"/api/upload?filename={name}", raw=data, headers={"Content-Type": "application/octet-stream"}, **kw)


class TestUpload:
    def test_pdf_is_saved_in_the_library(self, server, fake_root):
        status, out = upload(server, "My%20Book.pdf", PDF)
        assert status == 200 and out["filename"] == "My Book.pdf" and out["bytes"] == len(PDF)
        assert (fake_root / "books" / "My Book.pdf").read_bytes() == PDF and not list((fake_root / "books").glob("*.part"))

    def test_text_is_saved(self, server, fake_root):
        assert upload(server, "story.txt", TEXT)[0] == 200

    def test_text_needs_real_words(self, server, fake_root):
        assert upload(server, "story.txt", b"too few")[0] == 400
        assert upload(server, "story.txt", b"binary \x00 data with enough words in it to pass the count")[0] == 400
        assert not (fake_root / "books" / "story.txt").exists() and not list((fake_root / "books").glob("*.part"))

    def test_path_tricks_are_flattened_or_refused(self, server, fake_root):
        status, out = upload(server, "..%2F..%2Fevil.txt", TEXT)
        assert not (fake_root.parent / "evil.txt").exists()
        if status == 200:
            assert (fake_root / "books" / out["filename"]).exists() and "/" not in out["filename"]


class TestStaticAndPage:
    def test_static_files_need_no_token_and_have_types(self, server):
        status, hdrs, body = server.request("GET", "/static/js/core.js")
        assert status == 200 and hdrs["Content-Type"].startswith("text/javascript") or "javascript" in hdrs["Content-Type"]
        assert "charset=utf-8" in hdrs["Content-Type"]

    def test_static_traversal_is_a_404(self, server):
        for p in ("/static/../index.html", "/static/%2e%2e/index.html", "/static/js/nothere.js"):
            assert server.request("GET", p)[0] == 404

    def test_static_with_a_foreign_host_is_refused(self, server):
        assert server.request("GET", "/static/js/core.js", host="evil.example")[0] == 403


class TestThumbs:
    def test_thumbnail_is_made_and_cached(self, server, book):
        f = book / "images" / "flux" / "image-001.png"
        f.parent.mkdir(parents=True)
        Image.new("RGB", (400, 300), "green").save(f)
        status, hdrs, body = server.request("GET", "/thumb/demo/images/flux/image-001.png?t=" + "t" * 32)
        assert status == 200 and hdrs["Content-Type"] == "image/jpeg" and body[:2] == b"\xff\xd8"
        assert list((book / ".thumbs").glob("*.jpg"))
        assert server.request("GET", "/thumb/demo/images/flux/image-001.png?t=" + "t" * 32)[0] == 200

    def test_thumbnail_needs_the_token_and_a_real_file(self, server, book):
        assert server.request("GET", "/thumb/demo/images/x.png")[0] == 403
        assert server.request("GET", "/thumb/demo/images/none.png?t=" + "t" * 32)[0] == 404
        assert server.request("GET", "/thumb/demo/../../x.png?t=" + "t" * 32)[0] == 404

    def test_unreadable_picture_is_a_404_not_a_crash(self, server, book):
        f = book / "images" / "bad.png"
        f.parent.mkdir(parents=True)
        f.write_bytes(b"not a png")
        assert server.request("GET", "/thumb/demo/images/bad.png?t=" + "t" * 32)[0] == 404


class TestGetRoutes:
    @pytest.mark.parametrize("path", ["/api/scenes?project=demo", "/api/chapter_shots?project=demo", "/api/files?project=demo", "/api/cleanup_scan",
                                      "/api/storyboard?project=demo", "/api/film_status?project=demo", f"/api/suggest?look={LOOK}&service=kaggle&gpu=NvidiaTeslaT4",
                                      "/api/media?project=demo", "/api/setup"])
    def test_ok_on_a_book(self, server, book, path):
        status, out = server.api("GET", path)
        assert status == 200, out

    @pytest.mark.parametrize("path", ["/api/scenes?project=../x", "/api/chapter_shots?project=nothere", "/api/storyboard?project=demo&start=abc"])
    def test_bad_input_is_a_400(self, server, book, path):
        assert server.api("GET", path)[0] == 400

    def test_unknown_route(self, server, book):
        assert server.api("GET", "/api/nope")[0] == 404
