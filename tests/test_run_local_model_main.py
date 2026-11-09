"""run_local_model.py's main(): argument checks, what is copied in, where the results go, and building the Python environment (nothing heavy runs)."""
import json
import sys
from pathlib import Path

import pytest

import run_local_model as rl

NB = {"cells": [{"cell_type": "code", "source": ["START, END = 1, 1\n", "CSV_NAME = 'all_shots.csv'\n", "print('hi')"]}]}
NVIDIA = [{"name": "RTX", "vendor": "NVIDIA", "gb": 24, "shared": False, "cap": "8.9", "nvidia_ready": True, "rocm_ready": False}]
AMD = [{"name": "AMD Radeon", "vendor": "AMD", "gb": 24, "shared": False, "cap": "gfx1100", "nvidia_ready": False, "rocm_ready": True}]


@pytest.fixture()
def rig(book, fake_root, monkeypatch, tmp_path):
    """A run that never starts a real model: GPU found, environment faked, the notebook is a one-liner, and `run_logged` stands in for the run."""
    monkeypatch.setattr(rl, "ROOT", fake_root)
    monkeypatch.setattr(rl, "detect_gpus", lambda: NVIDIA)
    monkeypatch.setattr(rl, "gpu_problem", lambda gpus, platform=None: None)
    nb = tmp_path / "nb.ipynb"
    nb.write_text(json.dumps(NB))
    monkeypatch.setattr(rl, "find_notebook", lambda model, tmp: nb)
    monkeypatch.setattr(rl, "make_env", lambda pip, log: Path(sys.executable))
    monkeypatch.setenv("PROJECT", "demo")
    monkeypatch.setenv("STUDIO_GPU_ENVS", str(tmp_path / "envs"))
    for k in ("SHOTS_CSV", "KEYFRAME_MODEL", "UPSCALE_SOURCE", "STUDIO_TORCH_INDEX"):
        monkeypatch.delenv(k, raising=False)
    seen = {"code": 0, "make": ["shot-0001.mp4"], "input": None}

    def run_logged(argv, log, cwd=None, env=None, **kw):
        seen["argv"], seen["env"] = argv, env
        work = Path(cwd)
        seen["input"] = sorted(p.name for p in (work.parent / "input" / "dataset").iterdir())
        seen["script"] = Path(argv[1]).read_text()
        for name in seen["make"]:
            (work / "sub").mkdir(exist_ok=True)
            (work / "sub" / name).write_bytes(b"x")
        return seen["code"]
    monkeypatch.setattr(rl, "run_logged", run_logged)
    return seen


def go(*args):
    with pytest.raises(SystemExit) as e:
        rl.main(list(args))
    return e.value.code


class TestArguments:
    def test_each_bad_argument_is_explained(self, rig, capsys, monkeypatch):
        assert "Usage" in str(go("ltx_video", "1"))
        for args, msg in ((("Bad Model", "1", "1"), "bad model name"), (("ltx_video", "a", "1"), "row numbers"), (("ltx_video", "3", "1"), "END not before START"),
                          (("tpu_wan", "1", "1"), "only on Kaggle's TPU"), (("ltx_video", "1", "9"), "has 4 rows")):
            assert go(*args) == 1 and msg in capsys.readouterr().out
        monkeypatch.setenv("PROJECT", "ghost")
        assert go("ltx_video", "1", "1") == 1 and "no such project" in capsys.readouterr().out
        monkeypatch.setenv("PROJECT", "Bad Name")
        assert go("ltx_video", "1", "1") == 1 and "bad project name" in capsys.readouterr().out
        monkeypatch.setenv("PROJECT", "demo")
        monkeypatch.setenv("SHOTS_CSV", "nothere.csv")
        assert go("ltx_video", "1", "1") == 1 and "build the CSVs first" in capsys.readouterr().out

    def test_no_gpu_is_explained(self, rig, capsys, monkeypatch):
        monkeypatch.setattr(rl, "detect_gpus", lambda: [])
        monkeypatch.setattr(rl, "gpu_problem", lambda gpus, platform=None: "no graphics processor found on this computer")
        assert go("ltx_video", "1", "1") == 1 and "no graphics processor" in capsys.readouterr().out

    def test_amd_refuses_nvidia_only_models_and_picks_the_rocm_build(self, rig, capsys, monkeypatch):
        monkeypatch.setattr(rl, "detect_gpus", lambda: AMD)
        assert go("upscale_flashvsr", "1", "1") == 1 and "cannot run on an AMD GPU" in capsys.readouterr().out
        assert go("ltx_video", "1", "1") == 0 and __import__("os").environ["STUDIO_TORCH_INDEX"] == rl.ROCM_TORCH_INDEX
        monkeypatch.delenv("STUDIO_TORCH_INDEX")


class TestRun:
    def test_results_move_into_the_project_and_the_log_is_kept(self, rig, book, capsys):
        assert go("ltx_video", "1", "1") == 0
        assert (book / "videos" / "ltx_video" / "shot-0001.mp4").is_file() and (book / "logs" / "local-demo-ltx-video-1-1.log").is_file()
        assert "all_shots.csv" in rig["input"] and "audio_shots.csv" in rig["input"] and "START, END = 1, 1" in rig["script"]
        assert rig["env"]["MPLBACKEND"] == "Agg" and "PYTHONHOME" not in rig["env"] and "1 file(s) now in" in capsys.readouterr().out

    def test_a_failed_run_keeps_what_was_made_and_exits_one(self, rig, book, capsys):
        rig["code"] = 3
        assert go("ltx_video", "1", "1") == 1
        assert "with errors (exit 3); keeping whatever was made" in capsys.readouterr().out and (book / "videos" / "ltx_video" / "shot-0001.mp4").is_file()

    def test_chapter_and_keyframe_csvs_get_their_own_folders(self, rig, book, monkeypatch):
        (book / "all_chapters.csv").write_text((book / "all_shots.csv").read_text())
        monkeypatch.setenv("SHOTS_CSV", "all_chapters.csv")
        go("ltx_video", "1", "1")
        assert (book / "videos" / "ltx_video_chapters" / "shot-0001.mp4").is_file()
        (book / "keyframes.csv").write_text((book / "all_shots.csv").read_text())
        (book / "keyframe_refs").mkdir()
        (book / "keyframe_refs" / "ref-eve.png").write_bytes(b"x")
        rig["make"] = ["image-0001.png"]
        monkeypatch.setenv("SHOTS_CSV", "keyframes.csv")
        go("image_flux1_schnell", "1", "1")
        assert (book / "images" / "flux1_schnell_keyframes" / "image-0001.png").is_file() and "ref-eve.png" in rig["input"]

    def test_image_and_audio_models_use_their_own_csv_and_folder(self, rig, book):
        (book / "all_images.csv").write_text("prompt\na\n")
        rig["make"] = ["image-0001.png"]
        go("image_flux1_schnell", "1", "1")
        assert (book / "images" / "flux1_schnell" / "image-0001.png").is_file()
        rig["make"] = ["narration-0001.wav"]
        go("audio_kokoro", "1", "2")
        assert (book / "audio" / "kokoro" / "narration-0001.wav").is_file()

    def test_image_to_video_needs_keyframes_for_every_row(self, rig, book, capsys, monkeypatch):
        assert go("ltx_video_i2v", "1", "2") == 1 and "needs keyframes" in capsys.readouterr().out
        kf = book / "images" / "flux_keyframes"
        kf.mkdir(parents=True)
        (kf / "image-0001.png").write_bytes(b"x")
        assert go("ltx_video_i2v", "1", "2") == 1 and "for row(s): 2" in capsys.readouterr().out
        (kf / "image-0002.png").write_bytes(b"x")
        assert go("ltx_video_i2v", "1", "2") == 0 and {"kf-0001.png", "kf-0002.png"} <= set(rig["input"])
        monkeypatch.setenv("KEYFRAME_MODEL", "Bad Name")
        assert go("ltx_video_i2v", "1", "1") == 1 and "bad KEYFRAME_MODEL" in capsys.readouterr().out
        monkeypatch.setenv("KEYFRAME_MODEL", "flux")
        assert go("ltx_video_i2v", "1", "1") == 0
        monkeypatch.setenv("SHOTS_CSV", "all_chapters.csv")
        (book / "all_chapters.csv").write_text("a\n1\n")
        assert go("ltx_video_i2v", "1", "1") == 1 and "works per shot" in capsys.readouterr().out

    def test_upscalers_take_the_clips_already_made(self, rig, book, capsys, monkeypatch):
        assert go("upscale_x2", "1", "1") == 1 and "set UPSCALE_SOURCE" in capsys.readouterr().out
        monkeypatch.setenv("UPSCALE_SOURCE", "ltx_video")
        assert go("upscale_x2", "1", "1") == 1 and "no clips folder" in capsys.readouterr().out
        clips = book / "videos" / "ltx_video"
        clips.mkdir(parents=True)
        assert go("upscale_x2", "1", "1") == 1 and "no clip in" in capsys.readouterr().out
        (clips / "shot-0001.mp4").write_bytes(b"x")
        (book / "audio" / "kokoro").mkdir(parents=True)
        (book / "audio" / "kokoro" / "narration-0001.wav").write_bytes(b"x")
        assert go("upscale_lipsync", "1", "1") == 0 and {"in-0001.mp4", "a-0001.wav"} <= set(rig["input"])
        assert (book / "videos" / "ltx_video_lipsync" / "shot-0001.mp4").is_file()


class TestEnvironment:
    @pytest.fixture()
    def uv(self, monkeypatch, tmp_path):
        ran = []

        def run_logged(argv, log, **kw):
            ran.append(argv)
            if argv[1:3] == ["venv", "-q"]:
                env = Path(argv[-1])
                (env / "bin").mkdir(parents=True)
                (env / "bin" / "python").write_text("")
            return 1 if any("failing" in a for a in argv) else 0
        monkeypatch.setattr(rl, "run_logged", run_logged)
        monkeypatch.setattr(rl.shutil, "which", lambda name, path=None: "/usr/bin/uv" if name == "uv" else None)
        monkeypatch.setenv("STUDIO_GPU_ENVS", str(tmp_path / "envs"))
        monkeypatch.delenv("STUDIO_GPU_PYTHON", raising=False)
        monkeypatch.delenv("STUDIO_TORCH_INDEX", raising=False)
        return ran

    def test_a_new_environment_is_made_once(self, uv, tmp_path):
        import io
        log = io.StringIO()
        py = rl.make_env(["pip install foo torch", "pip3 install -q bar"], log)
        steps = [a[:3] for a in uv]
        assert py.name == "python" and (py.parent.parent / ".studio_ready").is_file() and (py.parent.parent / "recipe.json").is_file()
        assert ["/usr/bin/uv", "venv", "-q"] in steps and any(a[-2:] == [str(py), "-m"] or "foo" in a for a in uv) and not any("torch" in a and "foo" in a for a in uv)
        count = len(uv)
        assert rl.make_env(["pip install foo torch", "pip3 install -q bar"], log) == py and len(uv) == count          # reused

    def test_the_torch_index_is_passed_to_uv(self, uv, monkeypatch):
        monkeypatch.setenv("STUDIO_TORCH_INDEX", "https://example.org/whl/cu128")
        rl.make_env([], None)
        assert any("--index-url" in a and "https://example.org/whl/cu128" in a for a in uv)

    def test_failures_and_a_missing_uv_are_explained(self, uv, monkeypatch, capsys):
        with pytest.raises(SystemExit):
            rl.make_env(["pip install failing-package"], None)
        assert "failed: pip install failing-package" in capsys.readouterr().out
        monkeypatch.setattr(rl.shutil, "which", lambda name, path=None: None)
        monkeypatch.setattr(rl.Path, "home", classmethod(lambda cls: Path("/nonexistent")))
        with pytest.raises(SystemExit):
            rl.make_env([], None)
        assert "uv is not installed" in capsys.readouterr().out

    def test_a_half_made_environment_is_started_again(self, uv, tmp_path):
        rl.make_env([], None)
        (next((tmp_path / "envs").glob("*/.studio_ready"))).unlink()
        n = len(uv)
        rl.make_env([], None)
        assert len(uv) > n


class TestHelpers:
    def test_run_logged_streams_and_returns_the_exit_code(self, tmp_path, capsys):
        import io
        log = io.StringIO()
        assert rl.run_logged([sys.executable, "-c", "print('hello'); raise SystemExit(4)"], log) == 4
        assert log.getvalue() == "hello\n" and "hello" in capsys.readouterr().out

    def test_find_notebook_prefers_the_repository_copy_then_generates(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(rl, "ROOT", tmp_path)
        (tmp_path / "Studio_Kaggle_ltx_video.ipynb").write_text("{}")
        assert rl.find_notebook("ltx_video", tmp_path / "gen") == tmp_path / "Studio_Kaggle_ltx_video.ipynb"
        made = []

        def gen(argv, env=None, **kw):
            made.append(argv)
            (Path(env["STUDIO_GEN_DIR"]) / "Studio_Kaggle_wan.ipynb").write_text("{}")
        monkeypatch.setattr(rl.subprocess, "run", gen)
        assert rl.find_notebook("wan", tmp_path).name == "Studio_Kaggle_wan.ipynb" and made
        with pytest.raises(SystemExit):
            rl.find_notebook("nope", tmp_path)
        assert "no such model: nope" in capsys.readouterr().out

    def test_shlex_quote(self):
        assert rl.shlex_quote(Path("a b")) == "'a b'"
