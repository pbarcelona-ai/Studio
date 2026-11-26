"""Regression tests covering all high/medium findings from review_findings_copilot.txt."""
from __future__ import annotations

import base64
import os
import subprocess
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from local_runners import comfyui_runner  # noqa: E402
from studio_app import cleanup, gallery, jobs, media, procs, projects, render_jobs, upload_validation  # noqa: E402
from studio_app.common import PlanError  # noqa: E402


def test_jobs_write_state_concurrent_atomic(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUDIO_JOB_DIR", str(tmp_path / "jobs"))

    def _writer(idx: int) -> None:
        jobs.write_state({"id": f"job-{idx}", "status": "running", "index": idx})

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_writer, range(24)))

    st = jobs.read_state()
    assert isinstance(st, dict) and st.get("status") == "running"
    # No stray .tmp files left behind
    assert list((tmp_path / "jobs").glob("*.tmp")) == []


def test_procs_pid_matches_rejects_mismatched_start_id():
    my_pid = os.getpid()
    real_id = procs.process_start_id(my_pid)
    assert real_id, "current process should report a non-empty start identity"
    assert procs.pid_matches(my_pid, real_id) is True
    assert procs.pid_matches(my_pid, "fake:0:0") is False


def test_comfyui_cancelled_raises_and_never_returns_ok(tmp_path: Path):
    runner = comfyui_runner.ComfyUIRunner(base_url="http://127.0.0.1:18188", timeout=5.0)
    runner._cancelled = True

    class _FakeResp:
        def __init__(self, data: bytes):
            self._data = data

        def read(self) -> bytes:
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with (
        mock.patch.object(comfyui_runner, "acquire_media_lease", return_value=None),
        mock.patch.object(runner.pantry, "prepare", return_value=None),
        mock.patch("socket.create_connection", side_effect=OSError("no ws")),
        mock.patch("urllib.request.urlopen", return_value=_FakeResp(b'{"prompt_id": "p-cancel-1"}')),
        pytest.raises(comfyui_runner.ComfyUICancelledError),
    ):
        runner._execute_workflow(
            {"1": {"class_type": "SaveImage", "inputs": {}}},
            output_dir=tmp_path / "out",
            app_id="test",
            model_cache_key="k",
            min_vram_gb=0.0,
            declared_nodes=[],
            manifest={},
        )


def test_render_jobs_async_submit_and_poll():
    ticket = render_jobs.submit_render_job("test-kf", lambda: {"status": "ok", "image_url": "/file/demo/kf.png"})
    assert ticket["status"] == "queued"
    jid = ticket["job_id"]
    deadline = time.monotonic() + 3.0
    rec = None
    while time.monotonic() < deadline:
        rec = render_jobs.get_render_job(jid)
        if rec and rec["status"] in ("done", "error"):
            break
        time.sleep(0.02)
    assert rec is not None and rec["status"] == "done"
    assert rec["result"]["image_url"] == "/file/demo/kf.png"


def test_upload_validation_strict_base64_and_magic_bytes():
    # Reject invalid base64
    with pytest.raises(PlanError, match="invalid base64"):
        upload_validation.decode_verified_base64("!!!not-base64!!!", kind="image")

    # Reject text disguised as image
    fake_txt = base64.b64encode(b"this is definitely not a png image file payload" * 4).decode()
    with pytest.raises(PlanError, match="not a valid PNG"):
        upload_validation.decode_verified_base64(fake_txt, kind="image")

    # Accept real PNG signature
    real_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    raw, ext = upload_validation.decode_verified_base64(base64.b64encode(real_png).decode(), kind="image")
    assert ext == ".png" and raw == real_png

    # Accept real WAV signature
    real_wav = b"RIFF" + b"\x24\x00\x00\x00" + b"WAVE" + b"\x00" * 64
    raw_a, ext_a = upload_validation.decode_verified_base64(base64.b64encode(real_wav).decode(), kind="audio")
    assert ext_a == ".wav" and raw_a == real_wav


def test_media_seconds_lru_bounded(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(media, "_SECONDS_MAX", 4)
    media._SECONDS.clear()
    for i in range(8):
        p = tmp_path / f"clip-{i}.wav"
        p.write_bytes(b"not-a-wav")
        media.media_seconds(p)
    assert len(media._SECONDS) <= 4


def test_gallery_depth_failure_backoff_retries_after_window(tmp_path: Path, monkeypatch):
    from PIL import Image

    src = tmp_path / "img.png"
    Image.new("RGB", (32, 32), (10, 20, 30)).save(src)
    dest = tmp_path / "depth.png"

    gallery._DEPTH.clear()
    gallery._DEPTH["failed"] = "transient offline error"
    gallery._DEPTH["fail_count"] = 1
    gallery._DEPTH["retry_after"] = time.monotonic() + 120.0
    with pytest.raises(RuntimeError, match="retrying in"):
        gallery.make_depth(src, dest)

    # Once backoff expires, loader retries instead of failing permanently
    gallery._DEPTH["retry_after"] = time.monotonic() - 1.0
    fake_depth_img = Image.new("L", (32, 32), 128)
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.pipeline = lambda *a, **kw: (lambda _im: {"depth": fake_depth_img})  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    gallery.make_depth(src, dest)
    assert dest.is_file()
    assert "failed" not in gallery._DEPTH


def test_install_studio_transactional_rollback_on_mid_swap_failure(tmp_path: Path, monkeypatch):
    import install_studio
    import setup_engine

    payload = tmp_path / "payload"
    home = tmp_path / "home"
    payload.mkdir()
    home.mkdir()
    (payload / "a.txt").write_text("new-a", encoding="utf-8")
    (payload / "b.txt").write_text("new-b", encoding="utf-8")
    (home / "a.txt").write_text("old-a", encoding="utf-8")
    (home / "b.txt").write_text("old-b", encoding="utf-8")

    task = install_studio.copy_files(payload)
    eng = setup_engine.Engine([task], home)
    ctx = setup_engine.Ctx(eng)

    real_replace = os.replace

    def _fail_on_b(src, dst):
        if Path(dst) == home / "b.txt" and Path(src).parent.name == "files":
            raise OSError("simulated disk error mid-swap")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _fail_on_b)
    with pytest.raises(OSError, match="simulated disk error"):
        task.run(ctx)

    # Both original files must be fully restored!
    assert (home / "a.txt").read_text(encoding="utf-8") == "old-a"
    assert (home / "b.txt").read_text(encoding="utf-8") == "old-b"


def test_projects_info_does_not_mutate_by_default(tmp_path: Path, monkeypatch):
    pd = tmp_path / "books" / "readonly_demo"
    pd.mkdir(parents=True)
    (pd / "all_shots.csv").write_text("chapter,prompt\n1,hello\n", encoding="utf-8")
    monkeypatch.setattr(projects, "pdir", lambda slug, kind=None: pd)
    monkeypatch.setattr(projects, "library_files", lambda: [])
    called_sync = []
    monkeypatch.setattr(projects.character_tokens, "sync_characters_from_project", lambda s: called_sync.append(s))
    monkeypatch.setattr(projects.character_tokens, "list_characters", lambda s: [])

    info = projects.project_info("readonly_demo")
    assert info["slug"] == "readonly_demo"
    assert not (pd / "movies.json").exists()
    assert called_sync == []


def test_book_ingest_empty_book_exits_cleanly_without_valueerror(tmp_path: Path):
    empty_txt = tmp_path / "blank.txt"
    empty_txt.write_text("   \n\n\t  ", encoding="utf-8")
    res = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "book_ingest.py"), "empty_test_book_tmp", str(empty_txt), "--no-ocr"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res.returncode != 0
    combined = (res.stdout + res.stderr).lower()
    assert "valueerror" not in combined and "min()" not in combined


def test_make_audio_has_no_shell_true():
    src = (SCRIPTS_DIR / "make_audio.py").read_text(encoding="utf-8")
    assert "shell=True" not in src


def test_cleanup_scan_cache_and_invalidation():
    cleanup.invalidate_cleanup_cache()
    first = cleanup.cleanup_scan()
    second = cleanup.cleanup_scan()
    assert first is second
    cleanup.invalidate_cleanup_cache()
    third = cleanup.cleanup_scan()
    assert third is not first
