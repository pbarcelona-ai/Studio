"""run_local_model: GPU detection and explanations, turning a notebook into a script, and the pip-line safety rules (no real GPU or network)."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_local_model as rl


class TestMemory:
    @pytest.mark.parametrize("text,want", [("1536 MB", 1.5), ("8 GB", 8.0), ("1 TB", 1024.0), (2**30, 1.0), ("", None), (None, None), ("abc", None)])
    def test_mem_gb(self, text, want):
        assert rl._mem_gb(text) == want


class TestGpuInfo:
    def test_no_nvidia_smi(self, monkeypatch):
        monkeypatch.setattr(rl.shutil, "which", lambda n: None)
        assert rl.gpu_info() == [] and rl.rocm_info() == []

    def test_nvidia_smi_output(self, monkeypatch):
        monkeypatch.setattr(rl.shutil, "which", lambda n: "/bin/nvidia-smi")
        monkeypatch.setattr(rl.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="NVIDIA RTX 4090, 24564, 8.9\nbroken line\nTesla T4, notanumber, 7.5\n"))
        assert rl.gpu_info() == [("NVIDIA RTX 4090", 24.0, "8.9")]

    def test_nvidia_smi_failure(self, monkeypatch):
        monkeypatch.setattr(rl.shutil, "which", lambda n: "/bin/nvidia-smi")

        def boom(*a, **k):
            raise OSError("no driver")
        monkeypatch.setattr(rl.subprocess, "run", boom)
        assert rl.gpu_info() == []

    def test_rocm_smi_output(self, monkeypatch):
        data = {"card0": {"Card Series": "Navi 31 [Radeon RX 7900 XTX]", "VRAM Total Memory (B)": str(24 * 2**30), "GFX Version": "gfx1100"}, "system": {"x": 1}, "card1": "junk"}
        monkeypatch.setattr(rl.shutil, "which", lambda n: "/bin/rocm-smi")
        monkeypatch.setattr(rl.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=json.dumps(data)))
        assert rl.rocm_info() == [("AMD Radeon RX 7900 XTX", 24.0, "gfx1100")]

    def test_rocm_bad_json(self, monkeypatch):
        monkeypatch.setattr(rl.shutil, "which", lambda n: "/bin/rocm-smi")
        monkeypatch.setattr(rl.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="not json"))
        assert rl.rocm_info() == []


class TestDetectGpus:
    def test_nvidia_wins(self, monkeypatch):
        monkeypatch.setattr(rl, "gpu_info", lambda: [("RTX", 24.0, "8.9")])
        monkeypatch.setattr(rl, "rocm_info", lambda: [])
        g = rl.detect_gpus()
        assert len(g) == 1 and g[0]["nvidia_ready"] and not g[0]["rocm_ready"]

    def test_linux_lspci_fallback(self, monkeypatch):
        monkeypatch.setattr(rl, "gpu_info", lambda: [])
        monkeypatch.setattr(rl, "rocm_info", lambda: [])
        monkeypatch.setattr(rl.sys, "platform", "linux")
        monkeypatch.setattr(rl, "_run", lambda argv, timeout=20: "00:02.0 VGA compatible controller: Intel Corporation UHD 620\n00:01.0 Host bridge: x\n")
        g = rl.detect_gpus()
        assert [(x["vendor"], x["shared"], x["nvidia_ready"]) for x in g] == [("Intel", True, False)]

    def test_mac_system_profiler(self, monkeypatch):
        monkeypatch.setattr(rl, "gpu_info", lambda: [])
        monkeypatch.setattr(rl, "rocm_info", lambda: [])
        monkeypatch.setattr(rl.sys, "platform", "darwin")
        out = json.dumps({"SPDisplaysDataType": [{"sppci_model": "Intel Iris Plus Graphics 645", "spdisplays_vendor": "sppci_vendor_Intel", "spdisplays_vram": "1536 MB"}]})
        monkeypatch.setattr(rl, "_run", lambda argv, timeout=20: out)
        g = rl.detect_gpus()
        assert g[0]["name"].startswith("Intel Iris") and g[0]["gb"] == 1.5 and not rl.usable(g)

    def test_run_returns_empty_on_failure(self, monkeypatch):
        def boom(*a, **k):
            raise OSError
        monkeypatch.setattr(rl.subprocess, "run", boom)
        assert rl._run(["x"]) == ""


NV = {"name": "RTX 4090", "vendor": "NVIDIA", "gb": 24.0, "shared": False, "cap": "8.9", "nvidia_ready": True, "rocm_ready": False}
AMD = {"name": "AMD Radeon RX 7900", "vendor": "AMD", "gb": 24.0, "shared": False, "cap": "gfx1100", "nvidia_ready": False, "rocm_ready": True}
INTEL = {"name": "Intel UHD", "vendor": "Intel", "gb": 1.5, "shared": True, "cap": "", "nvidia_ready": False, "rocm_ready": False}


class TestExplanations:
    def test_gpu_text(self):
        assert rl.gpu_text(NV) == "RTX 4090 (24 GB)"
        assert rl.gpu_text(AMD) == "AMD Radeon RX 7900 (24 GB, ROCm, experimental)"
        assert rl.gpu_text(INTEL) == "Intel UHD (1.5 GB shared)"
        assert rl.gpu_text({"name": "x", "gb": None, "shared": False}) == "x"

    def test_usable(self):
        assert rl.usable([NV, AMD, INTEL]) == [NV, AMD]

    def test_ready_on_linux(self):
        assert rl.gpu_problem([NV], "linux") is None

    def test_ready_elsewhere_is_explained(self):
        assert "only under Linux" in rl.gpu_problem([NV], "darwin") and "macOS" in rl.gpu_problem([NV], "darwin")

    def test_no_gpu(self):
        assert "no graphics processor" in rl.gpu_problem([], "linux")

    @pytest.mark.parametrize("gpu,platform,word", [(INTEL, "darwin", "built-in graphics"), (dict(INTEL, vendor="Apple", name="Apple M2"), "darwin", "Metal"),
                                                   (dict(NV, nvidia_ready=False), "linux", "nvidia-smi"), (dict(AMD, rocm_ready=False), "linux", "ROCm is not installed"),
                                                   (dict(AMD, rocm_ready=False), "win32", "only on Linux"), (dict(INTEL, vendor=""), "linux", "NVIDIA graphics card")])
    def test_reasons(self, gpu, platform, word):
        assert word in rl.gpu_problem([gpu], platform) and "Use Kaggle" in rl.gpu_problem([gpu], platform)


class TestPipLines:
    def test_plain(self):
        assert rl.pip_argv("pip install numpy pandas") == ["pip", "install", "numpy", "pandas"]
        assert rl.pip_argv("pip3 install -q 'numpy<2'") == ["pip", "install", "-q", "numpy<2"]

    @pytest.mark.parametrize("cmd", ["pip install x && rm -rf /", "pip install x | tee y", "pip install x; ls", "pip install x > f", "pip install `id`", "pip install $(id)"])
    def test_lines_that_need_a_shell_are_refused(self, cmd, capsys):
        with pytest.raises(SystemExit):
            rl.pip_argv(cmd)
        assert "needs a shell" in capsys.readouterr().out

    @pytest.mark.parametrize("cmd,want", [("pip install torch torchvision numpy", "pip install numpy"), ("pip install torch", ""), ("pip install -q torch", ""),
                                          ("apt-get install ffmpeg", "apt-get install ffmpeg"), ("pip3 install torchaudio==2.1", "pip3 install torchaudio==2.1")])
    def test_keep_torch(self, cmd, want):
        assert rl.keep_torch(cmd) == want


NB = {"cells": [
    {"cell_type": "markdown", "source": ["# title"]},
    {"cell_type": "code", "source": ["!pip install -q numpy\n", "%matplotlib inline\n", "START, END = 1, 99\n", "CSV_NAME = 'x.csv'\n",
                                     "DATA = '/kaggle/input/books'\n", "OUT = '/kaggle/working/out'\n", "!ls -la\n", "sh('apt-get install -y ffmpeg')\n", "if True:\n", "    !echo hi\n"]},
]}


class TestToScript:
    @pytest.fixture
    def script(self, tmp_path):
        nb = tmp_path / "n.ipynb"
        nb.write_text(json.dumps(NB))
        return rl.to_script(nb, 3, 5, "all_shots.csv", Path("/in"), Path("/work"))

    def test_pip_lines_are_collected_not_run_inline(self, script):
        text, pip = script
        assert pip == ["pip install -q numpy"] and "pass  # pip install -q numpy" in text

    def test_settings_and_paths_are_rewritten(self, script):
        text, _ = script
        assert "START, END = 3, 5" in text and "CSV_NAME = 'all_shots.csv'" in text and "/in/books" in text and "/work/out" in text
        assert "/kaggle/" not in text.split("import torch")[1]

    def test_shell_lines_become_calls_and_magics_vanish(self, script):
        text, _ = script
        assert "_studio_sh('ls -la')" in text and "    _studio_sh('echo hi')" in text and "%matplotlib" not in text
        assert "_studio_apt('apt-get install -y ffmpeg')" in text

    def test_the_script_is_valid_python(self, script):
        compile(script[0], "generated.py", "exec")


def test_csv_rows(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("a,b\n1,2\n3,4\n")
    assert rl.csv_rows(p) == 2


def test_die_exits_with_a_message(capsys):
    with pytest.raises(SystemExit) as e:
        rl.die("nope")
    assert e.value.code == 1 and "!! nope" in capsys.readouterr().out


class TestMakeEnv:
    def test_own_python_must_exist(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("STUDIO_GPU_PYTHON", str(tmp_path / "nopython"))
        with pytest.raises(SystemExit):
            rl.make_env([], open(tmp_path / "log", "w"))
        assert "does not exist" in capsys.readouterr().out

    def test_own_python_runs_the_installs_without_torch(self, tmp_path, monkeypatch):
        py = tmp_path / "python"
        py.write_text("")
        monkeypatch.setenv("STUDIO_GPU_PYTHON", str(py))
        ran = []
        monkeypatch.setattr(rl, "run_logged", lambda argv, log, **kw: ran.append(argv) or 0)
        assert rl.make_env(["pip install torch numpy"], None) == py
        assert ran == [[str(py), "-m", "pip", "install", "numpy"]]

    def test_a_ready_environment_is_reused(self, tmp_path, monkeypatch):
        monkeypatch.delenv("STUDIO_GPU_PYTHON", raising=False)
        monkeypatch.setenv("STUDIO_GPU_ENVS", str(tmp_path / "envs"))
        monkeypatch.setattr(rl, "run_logged", lambda *a, **k: pytest.fail("should not install"))
        # find the folder make_env will look for by letting it fail once without uv
        monkeypatch.setattr(rl.shutil, "which", lambda *a, **k: None)
        with pytest.raises(SystemExit):
            rl.make_env([], None)
        # now mark a matching environment as ready
        import hashlib
        recipe = json.dumps({"py": rl.PY_VERSION, "base": rl.BASE_PACKAGES, "torch_index": "", "pip": []})
        key = hashlib.sha1(recipe.encode()).hexdigest()[:12]
        (tmp_path / "envs" / key / "bin").mkdir(parents=True)
        (tmp_path / "envs" / key / "bin" / "python").write_text("")
        (tmp_path / "envs" / key / ".studio_ready").write_text("x")
        assert rl.make_env([], None) == tmp_path / "envs" / key / "bin" / "python"


def test_generated_studio_sh_uses_a_shell_only_when_the_line_needs_one(tmp_path):
    """Regression: the prelude is an f-string, so an unescaped \\n in its regex split the line and the whole generated script was a SyntaxError."""
    nb = tmp_path / "n.ipynb"
    nb.write_text(json.dumps({"cells": []}))
    text, _ = rl.to_script(nb, 1, 1, "x.csv", tmp_path, tmp_path)
    prelude = text.split("import torch")[0]
    calls = []
    ns = {"__name__": "gen"}
    exec(prelude.replace("_os.chdir(", "(lambda p: None)("), ns)        # defines _studio_sh without touching the folder
    ns["_subprocess"] = SimpleNamespace(run=lambda argv, check: calls.append(argv))
    ns["_studio_sh"]("ls -la")
    ns["_studio_sh"]("echo a && echo b")
    ns["_studio_sh"]("echo a\necho b")
    assert calls == [["ls", "-la"], ["bash", "-c", "echo a && echo b"], ["bash", "-c", "echo a\necho b"]]
