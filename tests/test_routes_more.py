"""More POST routes: file copy and frame extraction (path safety), character actions, and the routes that start background jobs."""
import pytest

from studio_app.jobs import JOB


def post(server, path, body=None):
    return server.api("POST", path, body or {})


@pytest.fixture
def started(monkeypatch):
    """Record JOB.start instead of running anything."""
    calls = []
    monkeypatch.setattr(JOB, "start", lambda steps, opt: calls.append(steps))
    return calls


class TestCopyFile:
    def test_needs_both_paths(self, server, book):
        assert post(server, "/api/copy_file", {"source": "x"})[0] == 400

    def test_copies_within_projects(self, server, book):
        (book / "a.txt").write_text("hello")
        status, out = post(server, "/api/copy_file", {"source": "demo/a.txt", "dest": "projects/books/demo/copy/b.txt"})
        assert status == 200 and (book / "copy" / "b.txt").read_text() == "hello"

    def test_destination_outside_projects_is_refused(self, server, book, fake_root):
        (book / "a.txt").write_text("hello")
        status, out = post(server, "/api/copy_file", {"source": "demo/a.txt", "dest": "outside.txt"})
        assert status == 403 and not (fake_root / "outside.txt").exists()
        assert post(server, "/api/copy_file", {"source": "demo/a.txt", "dest": "projects/../escape.txt"})[0] == 403
        assert not (fake_root / "escape.txt").exists()

    def test_source_outside_projects_is_refused(self, server, book):
        status, _ = post(server, "/api/copy_file", {"source": "../../etc/passwd", "dest": "projects/x.txt"})
        assert status in (400, 403, 404)


class TestExtractFrame:
    @pytest.mark.parametrize("body,code", [({}, 400), ({"project": "demo"}, 400), ({"project": "../x", "video": "a.mp4"}, 400),
                                           ({"project": "demo", "video": "a.mp4", "frame": -1}, 400), ({"project": "demo", "video": "a.mp4", "frame": "3"}, 400),
                                           ({"project": "demo", "video": "../../x.mp4", "model": "wan"}, 400), ({"project": "demo", "video": "none.mp4"}, 404)])
    def test_refused(self, server, book, body, code):
        assert post(server, "/api/extract_frame", body)[0] == code

    def test_unreadable_video(self, server, book):
        pytest.importorskip("cv2")
        v = book / "videos" / "wan" / "a.mp4"
        v.parent.mkdir(parents=True)
        v.write_bytes(b"not a video")
        assert post(server, "/api/extract_frame", {"project": "demo", "video": "a.mp4"})[0] == 500


class TestCharacters:
    def test_unknown_action(self, server, book):
        status, out = post(server, "/api/characters", {"action": "explode"})
        assert status == 400 and "unknown action" in out["error"]

    def test_archetypes(self, server, book):
        status, out = post(server, "/api/characters", {"action": "archetypes"})
        assert status == 200 and out["archetypes"] and {"value", "label"} <= set(out["archetypes"][0])

    def test_unknown_archetype(self, server, book):
        assert post(server, "/api/characters", {"action": "archetype_fields", "archetype": "nope"})[0] == 400

    def test_sync_needs_a_series(self, server, book):
        status, out = post(server, "/api/characters", {"action": "sync", "project": "demo"})
        assert status == 400 and "pick a series" in out["error"]

    def test_sync_unknown_project(self, server, book):
        assert post(server, "/api/characters", {"action": "sync", "project": "nothere", "series": "s"})[0] == 400

    def test_send_to_book_needs_names(self, server, book):
        status, out = post(server, "/api/characters", {"action": "send_to_book", "project": "demo", "series": "s", "names": []})
        assert status == 400 and "tick at least one" in out["error"]

    def test_sync_copies_the_books_characters(self, server, book):
        status, out = post(server, "/api/characters", {"action": "sync", "project": "demo", "series": "demoseries"})
        assert status == 200 and out["count"] == out["added"] and out["added"] >= 1

    def test_create_validate_delete(self, server, book):
        status, out = post(server, "/api/characters", {"action": "create", "series": "demoseries", "name": "Zed", "description": "a tall man", "visual_token": "a tall man in grey"})
        assert status == 200 and out["created"] is True
        assert post(server, "/api/characters", {"action": "delete", "series": "demoseries", "name": "Zed"})[0] == 200


class TestJobStartingRoutes:
    def test_upscale_face_animatic_fetch_start_one_step(self, server, book, started):
        for path, body in (("/api/face_check", {"project": "demo", "series": "heroes"}),):
            status, out = post(server, path, body)
            assert status == 200, out
        assert len(started) == 1 and len(started[0]) == 1

    def test_invalid_requests_start_nothing(self, server, book, started):
        for path in ("/api/upscale", "/api/face_check", "/api/make_animatic", "/api/fetch", "/api/make_film"):
            assert post(server, path, {})[0] == 400
        assert started == []

    def test_open_reference_folder_validates(self, server, book):
        assert post(server, "/api/open_reference_folder", {"series": "../x", "name": "a"})[0] == 400

    def test_expand_validates(self, server, book):
        assert post(server, "/api/expand", {"kind": "video", "idea": ""})[0] == 400

    def test_enhance_prompt_validates(self, server, book):
        assert post(server, "/api/enhance_prompt", {"project": "demo"})[0] == 400

    def test_describe_and_review_validate(self, server, book):
        assert post(server, "/api/describe_image", {"file": "nope"})[0] == 400
        assert post(server, "/api/review_result", {"prompt": ""})[0] == 400
