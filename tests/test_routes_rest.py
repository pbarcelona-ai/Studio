"""The remaining routes, over real HTTP: takes, prompt edits, Kaggle, setup, notebooks, gallery pages and the language-model check."""
import subprocess
from types import SimpleNamespace

import pytest

from studio_app import kaggle_cleanup, kaggle_runs, llm
from studio_app.jobs import JOB


def get(server, path):
    return server.api("GET", path)


def post(server, path, body=None):
    return server.api("POST", path, body or {})


class TestTakes:
    @pytest.fixture()
    def clip(self, book):
        d = book / "videos" / "ltx_video"
        d.mkdir(parents=True)
        (d / "shot-0001.mp4").write_bytes(b"current")
        return d

    BODY = {"project": "demo", "kind": "clip", "model": "ltx_video", "n": 1}

    def test_retake_keeps_the_clip_as_a_take_and_changes_the_seed(self, server, clip, book):
        status, out = post(server, "/api/retake", self.BODY)
        assert status == 200 and out["saved_as"] == 1 and out["seed"] == 1001
        assert not (clip / "shot-0001.mp4").exists() and (clip / "takes" / "shot-0001-t1.mp4").read_bytes() == b"current"
        assert "1001" in (book / "all_shots.csv").read_text()

    def test_retake_with_nothing_to_retake(self, server, clip):
        (clip / "shot-0001.mp4").unlink()
        status, out = post(server, "/api/retake", self.BODY)
        assert status == 400 and "nothing to retake" in out["error"]

    def test_pick_a_take_swaps_it_with_the_current_clip(self, server, clip):
        post(server, "/api/retake", self.BODY)
        (clip / "shot-0001.mp4").write_bytes(b"newer")
        status, out = post(server, "/api/pick_take", {**self.BODY, "take": 1})
        assert status == 200 and out == {"current_from_take": 1} and (clip / "shot-0001.mp4").read_bytes() == b"current" and (clip / "takes" / "shot-0001-t2.mp4").read_bytes() == b"newer"

    def test_bad_take_numbers(self, server, clip):
        assert post(server, "/api/pick_take", {**self.BODY, "take": 0})[0] == 400
        assert "does not exist" in post(server, "/api/pick_take", {**self.BODY, "take": 9})[1]["error"]
        assert post(server, "/api/retake", {**self.BODY, "kind": "film"})[0] == 400


class TestPromptEdits:
    BODY = {"project": "demo", "chapter": "1", "shot": 2}

    def test_save_then_revert(self, server, book):
        status, out = post(server, "/api/prompt_save", {**self.BODY, "fields": {"prompt": "a calm mountain at sunrise"}})
        assert status == 200 and "a calm mountain at sunrise" in (book / "all_shots.csv").read_text() and (book / "prompt_edits.json").exists()
        status, out = post(server, "/api/prompt_revert", self.BODY)
        assert status == 200 and "a mountain at dawn" in (book / "all_shots.csv").read_text()
        assert post(server, "/api/prompt_revert", self.BODY)[0] == 400

    def test_save_validation(self, server, book):
        assert post(server, "/api/prompt_save", {**self.BODY, "fields": {}})[0] == 400
        assert post(server, "/api/prompt_save", {**self.BODY, "fields": {"colour": "x"}})[0] == 400
        assert post(server, "/api/prompt_save", {**self.BODY, "fields": {"prompt": ""}})[0] == 400
        assert post(server, "/api/prompt_save", {**self.BODY, "shot": 99, "fields": {"prompt": "x"}})[0] == 400

    def test_suggest_uses_the_model_and_returns_ideas(self, server, book, monkeypatch):
        from studio_app import scenes
        monkeypatch.setattr(scenes, "llm_json", lambda prompt, system, **kw: {"suggestions": ["one idea " * 3, "two ideas " * 3]})
        status, out = post(server, "/api/prompt_suggest", {**self.BODY, "hint": "more dramatic", "field": "prompt"})
        assert status == 200 and len(out["suggestions"]) >= 1
        assert post(server, "/api/prompt_suggest", {**self.BODY, "hint": ""})[0] == 400


class TestKaggleRoutes:
    @pytest.fixture()
    def fake(self, book, monkeypatch, tmp_path):
        calls = []

        def run(argv, **kw):
            calls.append(argv[1:])
            if argv[1:3] == ["kernels", "list"]:
                return SimpleNamespace(returncode=0, stdout="ref,title,totalVotes,lastRunTime\npat/demo-ltx-video-1-4,t,0,2999-01-01 10:00:00\n", stderr="")
            if argv[1:3] == ["kernels", "status"]:
                return SimpleNamespace(returncode=0, stdout='pat/x has status "KernelWorkerStatus.COMPLETE"', stderr="")
            if argv[1:3] == ["kernels", "output"]:
                return SimpleNamespace(returncode=0, stdout="done", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        monkeypatch.setattr(kaggle_runs.subprocess, "run", run)
        monkeypatch.setattr(kaggle_runs.shutil, "which", lambda *a, **k: "/usr/bin/kaggle")
        monkeypatch.setattr(kaggle_cleanup, "AUTO_CLEAN_OFF", tmp_path / "off")
        monkeypatch.setattr(kaggle_cleanup.time, "sleep", lambda s: None)
        return calls

    def test_runs_and_cleanup_scan(self, server, fake):
        status, out = get(server, "/api/kaggle_runs")
        assert status == 200 and out["runs"][0]["slug"] == "demo-ltx-video-1-4" and out["runs"][0]["status"] == "COMPLETE"
        status, out = get(server, "/api/kaggle_cleanup_scan")
        assert status == 200 and {"keep", "remove", "busy"} <= set(out)

    def test_status_and_output_validate_the_reference(self, server, fake, fake_root):
        assert get(server, "/api/kernel_status?ref=pat/demo-ltx-video-1-4")[1]["status"] == "COMPLETE"
        assert get(server, "/api/kernel_status?ref=bad%20ref")[0] == 400
        status, out = post(server, "/api/kernel_output", {"ref": "pat/demo-ltx-video-1-4"})
        assert status == 200 and out["ok"] and out["dir"].endswith("demo-ltx-video-1-4")
        assert post(server, "/api/kernel_output", {"ref": "../x/y"})[0] == 400

    def test_a_download_that_times_out_is_reported(self, server, fake, monkeypatch):
        def slow(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 1)
        monkeypatch.setattr(kaggle_runs.subprocess, "run", slow)
        status, out = post(server, "/api/kernel_output", {"ref": "pat/demo-ltx-video-1-4"})
        assert status == 400 and "timed out" in out["error"]

    def test_cleanup_delete_reports_what_it_removed(self, server, fake):
        status, out = post(server, "/api/kaggle_cleanup_delete")
        assert status == 200 and "deleted" in out and "failed" in out


class TestSetup:
    def test_save_and_test_the_login(self, server, fake_root, monkeypatch):
        import setup_check
        status, out = post(server, "/api/setup_save", {"kaggle_token": "x" * 30})
        assert status == 200 and out["saved"] == ["kaggle_token"] and (fake_root.parent / "home" / ".kaggle" / "access_token").read_text() == "x" * 30
        assert post(server, "/api/setup_save", {"kaggle_token": "bad token"})[0] == 400
        monkeypatch.setattr(setup_check.shutil, "which", lambda *a, **k: None)
        status, out = post(server, "/api/setup_test")
        assert status == 200 and out["ok"] is False and "not installed" in out["message"]


class TestNotebooks:
    def test_recreate_and_delete(self, server, fake_root, monkeypatch):
        (fake_root / "scripts").mkdir()
        monkeypatch.setattr(kaggle_cleanup.subprocess, "run", lambda argv, **kw: SimpleNamespace(returncode=0, stdout="", stderr=""))
        assert post(server, "/api/recreate_notebooks")[0] == 200
        (fake_root / "Studio_Kaggle_x.ipynb").write_text("{}")
        status, out = post(server, "/api/delete_notebooks")
        assert status == 200 and out["notebooks"] == 1 and not (fake_root / "Studio_Kaggle_x.ipynb").exists()


class TestGalleryPages:
    def test_compare_showcase_and_gallery(self, server, book):
        status, out = get(server, "/api/compare")
        assert status == 200 and out["prompts"] == []
        assert get(server, "/api/showcase")[1] == {"hero": None, "art": []}
        assert get(server, "/api/gallery?project=demo")[1] == {"items": []}
        assert get(server, "/api/gallery?project=Bad%20Name")[1] == {"items": []}

    def test_clip_prompt(self, server, book):
        assert get(server, "/api/clip_prompt?project=demo&row=2")[1] == {"prompt": "a mountain at dawn"}
        assert get(server, "/api/clip_prompt?project=demo&row=99")[1] == {"prompt": ""}
        assert get(server, "/api/clip_prompt?project=ghost&row=1")[0] == 400
        assert get(server, "/api/clip_prompt?project=Bad%20Name&row=1")[0] == 400

    def test_local_llm_check_explains_itself(self, server, monkeypatch):
        monkeypatch.setattr(llm, "_LOCAL_CACHE", {"value": None, "at": 0})
        monkeypatch.setenv("STUDIO_LOCAL_LLM", "1")
        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("refused")))
        status, out = get(server, "/api/local_llm?fresh=1")
        assert status == 200 and out["ready"] is False and out["reason"]


def test_a_running_job_blocks_the_notebook_free_cleanup(server, monkeypatch):
    monkeypatch.setattr(JOB, "running", True)
    assert post(server, "/api/cleanup_delete", {"categories": ["x"]})[0] == 400
