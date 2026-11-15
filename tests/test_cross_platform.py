"""Windows and macOS: the step wrapper, process control, the step commands, and the Python versions of the Kaggle and Colab runners."""
import io
import json
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import pytest

import fetch_kaggle_run as fetch
import run_colab_model as colab
import run_kaggle_model as rk
import runner_common as rc
from studio_app import jobs, procs, steps

ROOT = Path(__file__).resolve().parent.parent
POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="the stand-in kaggle command is a shell script")


class TestRunStep:
    def test_records_the_exit_code(self, tmp_path):
        exitf = tmp_path / "x.exit"
        r = subprocess.run(jobs.step_command([sys.executable, "-c", "print('hi'); raise SystemExit(3)"]), capture_output=True, text=True,
                           env={**os.environ, "STUDIO_EXIT_FILE": str(exitf)}, timeout=60)
        assert r.returncode == 3 and "hi" in r.stdout and exitf.read_text().strip() == "3"

    def test_a_missing_program_is_127(self, tmp_path):
        exitf = tmp_path / "x.exit"
        r = subprocess.run(jobs.step_command(["no-such-program-here"]), capture_output=True, text=True,
                           env={**os.environ, "STUDIO_EXIT_FILE": str(exitf)}, timeout=60)
        assert r.returncode == 127 and exitf.read_text().strip() == "127"

    def test_stopping_the_group_stops_the_step_and_records_it(self, tmp_path):
        exitf = tmp_path / "x.exit"
        p = subprocess.Popen(jobs.step_command([sys.executable, "-c", "import time; time.sleep(60)"]), env={**os.environ, "STUDIO_EXIT_FILE": str(exitf)},
                             **procs.group_kwargs())
        time.sleep(1.0)
        assert procs.pid_alive(p.pid)
        procs.stop_group(p.pid, hard=os.name == "nt")
        p.wait(timeout=30)
        assert not procs.pid_alive(p.pid) or p.poll() is not None
        if os.name != "nt":
            assert exitf.read_text().strip() == "143"            # 128 + SIGTERM, as a shell reports it


class TestProcs:
    def test_pid_alive(self):
        assert procs.pid_alive(os.getpid()) and not procs.pid_alive(0) and not procs.pid_alive(True) and not procs.pid_alive("12")

    def test_processes_lists_this_one(self):
        rows = procs.processes()
        assert any(pid == os.getpid() for pid, *_ in rows) or rows == []

    def test_venv_bin(self, tmp_path):
        assert procs.venv_bin(tmp_path).name == ("Scripts" if os.name == "nt" else "bin")


class TestStepCommands:
    def test_python3_is_the_studios_python(self):
        assert steps.script_argv(["python3", "book_write.py", "x"]) == [sys.executable, "scripts/book_write.py", "x"]

    def test_ported_shell_scripts_run_their_python(self):
        assert steps.script_argv(["scripts/run_kaggle_model.sh", "wan", "1", "2"]) == [sys.executable, "scripts/run_kaggle_model.py", "wan", "1", "2"]
        assert steps.script_argv(["scripts/fetch_kaggle_run.sh", "s", "--wait"])[:2] == [sys.executable, "scripts/fetch_kaggle_run.py"]
        hf = steps.script_argv(["scripts/run_hf_space.sh", "m", "1", "2"])
        assert hf[0] == "uv" and hf[-4:] == ["scripts/run_hf_space.py", "m", "1", "2"]
        assert steps.script_argv([]) == []

    def test_every_port_exists(self):
        for argv in steps.PORTS.values():
            assert (ROOT / next(a for a in argv if a.endswith(".py"))).is_file()


class TestRunnerParts:
    def test_folders_and_modes(self, tmp_path):
        assert rc.default_csv("audio_kokoro") == "audio_shots.csv" and rc.default_csv("image_sdxl") == "all_images.csv" and rc.default_csv("wan") == "all_shots.csv"
        assert rc.base_dir(tmp_path, "audio_kokoro") == tmp_path / "audio" / "kokoro" and rc.base_dir(tmp_path, "wan") == tmp_path / "videos" / "wan"
        assert rc.mode_of("all_chapters.csv") == "chapters" and rc.mode_of("keyframes.csv") == "keyframes" and rc.mode_of("keyframes.csv", keyframes=False) == ""

    def test_log_tail(self, tmp_path):
        (tmp_path / "a.log").write_text(json.dumps([{"data": "one "}, {"data": "\x1b[31mtwo\x1b[0m"}]))
        assert rc.log_tail(tmp_path / "a.log", 100) == "one two" and "no log" in rc.log_tail(tmp_path / "none.log", 10)

    def test_accelerator_rules(self):
        rk.check_accelerator("tpu_x", "TpuV5E8")
        for model, accel in (("tpu_x", "NvidiaTeslaT4"), ("wan", "TpuV5E8")):
            with pytest.raises(rc.RunError):
                rk.check_accelerator(model, accel)

    def test_fill_notebook(self, tmp_path, monkeypatch):
        src = tmp_path / "a.ipynb"
        src.write_text(json.dumps({"cells": [{"cell_type": "code", "source": ["START, END = 1, 1\n", "CSV_NAME = 'x'"]}]}))
        monkeypatch.setenv("HF_TOKEN", "tok")
        rk.fill_notebook(src, tmp_path / "b.ipynb", 3, 9, "keyframes.csv")
        cells = json.loads((tmp_path / "b.ipynb").read_text())["cells"]
        assert "tok" in "".join(cells[0]["source"]) and cells[1]["source"] == ["START, END = 3, 9\n", "CSV_NAME = 'keyframes.csv'"]

    def test_keyframes_needed_for_i2v(self, tmp_path):
        with pytest.raises(rc.RunError, match="needs keyframes"):
            rk.keyframe_dir(tmp_path, "ltx_video_i2v", "all_shots.csv", 1, 2)
        (tmp_path / "images" / "sdxl_keyframes").mkdir(parents=True)
        (tmp_path / "images" / "sdxl_keyframes" / "image-0001.png").write_bytes(b"x")
        with pytest.raises(rc.RunError, match="row\\(s\\): 2"):
            rk.keyframe_dir(tmp_path, "ltx_video_i2v", "all_shots.csv", 1, 2)
        assert rk.keyframe_dir(tmp_path, "ltx_video_i2v", "all_shots.csv", 1, 1).name == "sdxl_keyframes"
        assert rk.keyframe_dir(tmp_path, "wan", "all_shots.csv", 1, 1) is None

    def test_upscale_source_is_checked(self, tmp_path, monkeypatch):
        monkeypatch.setenv("UPSCALE_SOURCE", "../x")
        with pytest.raises(rc.RunError, match="bad UPSCALE_SOURCE"):
            rk.upscale_dirs(tmp_path, "upscale_x2", "all_shots.csv", 1, 1)

    def test_colab_archive_cannot_escape(self, tmp_path):
        tar = tmp_path / "b.tar"
        with tarfile.open(tar, "w") as tf:
            info = tarfile.TarInfo("../evil.txt")
            info.size = 1
            tf.addfile(info, io.BytesIO(b"x"))
        with pytest.raises(rc.RunError, match="refusing"):
            colab.safe_extract(tar, tmp_path / "out")
        assert not (tmp_path / "evil.txt").exists()

    def test_fetch_suffix_and_options(self):
        assert fetch.suffix_of("demo-wan-keyframes-1-4") == "_keyframes" and fetch.suffix_of("demo-wan-1-4") == ""
        assert fetch.parse(["a-b", "--wait", "--project", "p"]) == ("a-b", True, "p", "")
        with pytest.raises(rc.RunError):
            fetch.parse(["--nope"])


FAKE_KAGGLE = """#!/bin/sh
case "$1 $2" in
  "datasets files") exit 1 ;;
  "datasets status") echo ready ;;
  "datasets download") exit 1 ;;
  "kernels push") echo "Kernel version 1 successfully pushed" ;;
  "kernels status") echo 'status "KernelWorkerStatus.COMPLETE"' ;;
  "kernels output") d="$5"; mkdir -p "$d/videos/wan"; echo clip > "$d/videos/wan/shot-0001.mp4"; echo '[]' > "$d/x.log" ;;
esac
exit 0
"""


@POSIX_ONLY
def test_a_whole_kaggle_run_with_a_stand_in(tmp_path, book, monkeypatch, capsys):
    import contextlib
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "kaggle").write_text(FAKE_KAGGLE)
    (bin_ / "kaggle").chmod(0o755)
    nb = tmp_path / "Studio_Kaggle_wan.ipynb"
    nb.write_text(json.dumps({"cells": [{"cell_type": "code", "source": ["START, END = 1, 1\n"]}]}))
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("KAGGLE_USER", "pat")
    monkeypatch.setenv("PROJECT", "demo")
    monkeypatch.setattr(rk, "project_folder", lambda p: book)
    monkeypatch.setattr(rk, "generated", lambda n: contextlib.nullcontext(nb))
    monkeypatch.setattr(rk.time, "sleep", lambda s: None)
    assert rk.main(["wan", "1", "1"]) == 0
    out = capsys.readouterr().out
    assert (book / "videos" / "wan" / "shot-0001.mp4").is_file() and "successfully pushed" in out and "pat/demo-wan-1-1" in out
