"""POST routes through the real HTTP server on a throw-away Studio folder (the `book` fixture remaps every path into tmp)."""
import json

import pytest

from studio_app import routes_post
from studio_app.jobs import JOB


def post(server, path, body=None):
    return server.api("POST", path, body or {})


class TestPlanning:
    def test_plan_lists_the_commands(self, server, book):
        status, out = post(server, "/api/plan", {"project": "demo", "steps": {"write": True}})
        assert status == 200 and out["steps"] and all({"label", "cmd"} <= set(s) for s in out["steps"])

    def test_nothing_ticked_is_a_400_with_a_message(self, server, book):
        status, out = post(server, "/api/plan", {"project": "demo", "steps": {}})
        assert status == 400 and "nothing selected" in out["error"]

    def test_run_refuses_a_bad_plan_without_starting(self, server, book):
        status, out = post(server, "/api/run", {"project": "demo", "steps": {}})
        assert status == 400 and not JOB.running

    def test_estimate(self, server, book):
        status, out = post(server, "/api/estimate", {"project": "demo", "steps": {"write": True}})
        assert status == 200 and isinstance(out["text"], str)

    def test_stop_when_idle(self, server, book):
        assert post(server, "/api/stop") == (200, {"stopping": True})


class TestChapterShots:
    def test_read_and_save(self, server, book):
        status, out = post(server, "/api/chapter_shots", {"project": "demo"})
        assert status == 200 and out["chapters"][0]["n"] == 1 and out["chapters"][0]["shots"] is None
        status, out = post(server, "/api/chapter_shots", {"project": "demo", "shots": {"1": "7"}})
        assert out["chapters"][0]["shots"] == 7
        assert json.loads((book / "overrides.json").read_text()) == {"1": {"shots": 7}}
        status, out = post(server, "/api/chapter_shots", {"project": "demo", "shots": {"1": ""}})
        assert out["chapters"][0]["shots"] is None and json.loads((book / "overrides.json").read_text()) == {}

    @pytest.mark.parametrize("shots,msg", [({"9": "3"}, "does not exist"), ({"1": "abc"}, "whole number"), ({"1": "501"}, "whole number")])
    def test_bad_counts(self, server, book, shots, msg):
        status, out = post(server, "/api/chapter_shots", {"project": "demo", "shots": shots})
        assert status == 400 and msg in out["error"]

    def test_unread_book(self, server, book):
        (book / "chapters.json").unlink()
        status, out = post(server, "/api/chapter_shots", {"project": "demo"})
        assert status == 400 and "read the book first" in out["error"]

    def test_bad_project(self, server, book):
        assert post(server, "/api/chapter_shots", {"project": "../x"})[0] == 400


class TestSmallRoutes:
    def test_global_params_need_a_project(self, server, book):
        status, out = post(server, "/api/global_params", {})
        assert status == 400 and "project is required" in out["error"]

    def test_global_params_round_trip(self, server, book):
        assert post(server, "/api/global_params", {"project": "demo", "positives": "cinematic", "negatives": "blurry"}) == (200, {"saved": True})

    def test_rate_validates_the_key(self, server, book):
        assert post(server, "/api/rate", {"key": "nope", "stars": 3})[0] == 400
        status, out = post(server, "/api/rate", {"key": "regtest_a/images/m/image-001.png", "stars": 4, "keep": True})
        assert status == 200 and out == {"stars": 4, "keep": True}

    def test_auto_cleanup_toggles_the_switch_file(self, server, book, tmp_path, monkeypatch):
        flag = tmp_path / "state" / "auto_clean_off"
        monkeypatch.setattr(routes_post, "AUTO_CLEAN_OFF", flag)
        assert post(server, "/api/auto_cleanup", {"on": False}) == (200, {"on": False}) and flag.exists()
        assert post(server, "/api/auto_cleanup", {"on": True}) == (200, {"on": True}) and not flag.exists()

    def test_trash_files_refuses_unknown_folders(self, server, book):
        status, _ = post(server, "/api/trash_files", {"project": "demo", "folder": "../..", "names": ["x"]})
        assert status == 400

    def test_cleanup_delete_with_nothing_chosen(self, server, book):
        status, out = post(server, "/api/cleanup_delete", {"categories": []})
        assert status == 400 and out["error"]


class TestDirectionRoutes:
    def test_creative_direction_get(self, server, book):
        assert post(server, "/api/creative_direction_get", {"project": "demo"}) == (200, {"messages": [], "direction": ""})

    def test_creative_direction_needs_a_message(self, server, book):
        status, out = post(server, "/api/creative_direction", {"project": "demo", "messages": []})
        assert status == 400 and "write something" in out["error"]

    def test_voice_cast_without_csvs(self, server, book):
        (book / "audio_shots.csv").unlink()
        assert post(server, "/api/voice_cast", {"project": "demo"})[0] == 400

    def test_new_scene_validates(self, server, book):
        status, out = post(server, "/api/new_scene", {"project": "demo", "chapter": "1", "description": ""})
        assert status == 400 and "describe the new scene" in out["error"]


def test_post_without_a_token_is_refused(server, book):
    assert server.api("POST", "/api/plan", {"project": "demo"}, token=None)[0] in (401, 403)


def test_malformed_json_is_a_400(server, book):
    status, out = server.api("POST", "/api/plan", raw=b"{not json")
    assert status == 400
