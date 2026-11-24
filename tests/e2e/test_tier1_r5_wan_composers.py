"""Tier 1 E2E Feature Coverage for R5.2 & R5.3 (F15 Wan Diffusers Engine, F16 Multi-Runtime Composers)."""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import types
from typing import Any

import pytest

from e2e.helpers.fake_comfyui import MINIMAL_PNG
from e2e.helpers.fake_comfyui import FakeComfyUIServer
from e2e.helpers.fake_ollama import FakeOllamaServer
from e2e.helpers.studio_harness import IsolatedWorkspace, StudioHarness


def _imp(name: str) -> Any:
    return importlib.import_module(name)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ffmpeg_bin() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
    return str(imageio_ffmpeg.get_ffmpeg_exe())


def _ensure_ffmpeg_on_path(monkeypatch: pytest.MonkeyPatch) -> str:
    exe = _ffmpeg_bin()
    if shutil.which("ffmpeg") is None:
        cur_dir = str(Path(exe).parent)
        monkeypatch.setenv("PATH", f"{cur_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return exe


def _apply_hw_profile(monkeypatch: pytest.MonkeyPatch, profile: dict[str, Any]) -> None:
    gpus = _imp("studio_app.gpus")
    rlm = _imp("run_local_model")
    if profile["backend"] == "cuda":
        fake_gpus = [
            {
                "name": profile["name"],
                "vendor": "NVIDIA",
                "gb": profile["vram_gb"],
                "shared": False,
                "cap": profile["compute_cap"],
                "nvidia_ready": True,
                "rocm_ready": False,
                "mps_ready": False,
            }
        ]
    elif profile["backend"] == "mps":
        fake_gpus = [
            {
                "name": profile["name"],
                "vendor": "Apple",
                "gb": profile["vram_gb"],
                "shared": True,
                "cap": "MPS",
                "nvidia_ready": False,
                "rocm_ready": False,
                "mps_ready": True,
            }
        ]
    else:
        fake_gpus = []
    monkeypatch.setattr(gpus.sys, "platform", profile["platform"])
    monkeypatch.setattr(gpus, "_ALL_GPUS", fake_gpus)
    monkeypatch.setattr(rlm, "detect_gpus", lambda: fake_gpus)
    monkeypatch.setattr(gpus, "system_ram_gb", lambda: float(profile["ram_gb"]))


def _make_test_mp4(path: Path, *, width: int = 128, height: int = 96, duration_s: float = 1.0, fps: int = 12) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg_bin(),
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=blue:s={width}x{height}:r={fps}:d={duration_s}",
        "-f",
        "lavfi",
        "-i",
        f"aevalsrc=0.2*sin(2*PI*440*t):s=48000:d={duration_s}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-shortest",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
    return path


def _probe_video_ffmpeg(path: Path) -> dict[str, Any]:
    proc = subprocess.run([_ffmpeg_bin(), "-i", str(path)], capture_output=True, text=True, timeout=15)
    stderr = proc.stderr or ""
    width = 0
    height = 0
    duration = 0.0
    m_res = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", stderr)
    if m_res:
        width = int(m_res.group(1))
        height = int(m_res.group(2))
    m_dur = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", stderr)
    if m_dur:
        duration = int(m_dur.group(1)) * 3600 + int(m_dur.group(2)) * 60 + float(m_dur.group(3))
    return {"width": width, "height": height, "duration": duration, "has_video": "Video:" in stderr}


def _install_fake_wan_stack(
    monkeypatch: pytest.MonkeyPatch,
    *,
    vram_gb: float = 48.0,
    bf16: bool = True,
    cuda_available: bool = True,
    segment_colors: list[tuple[int, int, int]] | None = None,
) -> dict[str, Any]:
    pil_image = importlib.import_module("PIL.Image")
    np = importlib.import_module("numpy")

    state: dict[str, Any] = {
        "loads": [],
        "calls": [],
        "vae_tiling": 0,
        "vae_slicing": 0,
        "offload_calls": [],
        "empty_cache_calls": 0,
        "written_frames": [],
        "quant_configs": [],
        "transformer_loads": [],
    }
    colors = segment_colors or [(128, 128, 128)]

    fake_torch: Any = types.ModuleType("torch")
    fake_torch.bfloat16 = "bfloat16"
    fake_torch.float16 = "float16"
    fake_torch.float32 = "float32"

    class _FakeProps:
        total_memory = int(vram_gb * (1024**3))

    class _FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return cuda_available

        @staticmethod
        def is_bf16_supported() -> bool:
            return bf16

        @staticmethod
        def get_device_properties(_idx: int = 0) -> _FakeProps:
            return _FakeProps()

        @staticmethod
        def empty_cache() -> None:
            state["empty_cache_calls"] += 1

    class _FakeMps:
        @staticmethod
        def is_available() -> bool:
            return not cuda_available

    class _FakeGenerator:
        def __init__(self, device: str = "cpu") -> None:
            self.device = device
            self.seed: int | None = None

        def manual_seed(self, seed: int) -> _FakeGenerator:
            self.seed = seed
            return self

    fake_torch.cuda = _FakeCuda()
    fake_torch.backends = types.SimpleNamespace(mps=_FakeMps())
    fake_torch.Generator = _FakeGenerator

    class _FakeVae:
        def enable_tiling(self) -> None:
            state["vae_tiling"] += 1

        def enable_slicing(self) -> None:
            state["vae_slicing"] += 1

    class _FakeConfig:
        patch_size = (1, 2, 2)

    class _FakeTransformer:
        config = _FakeConfig()

    class _FakePipeline:
        def __init__(self, cls_name: str, model_id: str, load_kwargs: dict[str, Any]) -> None:
            self._cls_name = cls_name
            self._model_id = model_id
            self._load_kwargs = load_kwargs
            self.vae = _FakeVae()
            self.transformer = _FakeTransformer()
            self.transformer_2 = _FakeTransformer() if "a14b" in model_id.lower() else None
            self.vae_scale_factor_temporal = 4
            self.vae_scale_factor_spatial = 16 if "ti2v" in model_id.lower() else 8
            self.components: dict[str, Any] = {"vae": self.vae, "transformer": self.transformer}

        def enable_model_cpu_offload(self) -> None:
            state["offload_calls"].append(("model", self._cls_name))

        def enable_sequential_cpu_offload(self) -> None:
            state["offload_calls"].append(("sequential", self._cls_name))

        def to(self, _device: str) -> _FakePipeline:
            return self

        def __call__(self, **kwargs: Any) -> Any:
            idx = len(state["calls"])
            state["calls"].append({"pipeline": self._cls_name, "kwargs": dict(kwargs)})
            num_frames = int(kwargs.get("num_frames") or len(kwargs.get("video") or []) or 1)
            w = int(kwargs.get("width") or 640)
            h = int(kwargs.get("height") or 384)
            color = colors[min(idx, len(colors) - 1)]
            frames: list[Any] = []
            for f_idx in range(num_frames):
                arr = np.zeros((h, w, 3), dtype=np.uint8)
                arr[:, :] = color
                # Put a deterministic corner marker on the final frame for anchor-propagation verification
                if f_idx == num_frames - 1:
                    arr[:8, :8] = (17, 231, 93)
                frames.append(pil_image.fromarray(arr))
            return types.SimpleNamespace(frames=[frames], images=frames)

    def _make_pipe_cls(cls_name: str) -> type:
        class _PipeMeta(_FakePipeline):
            @classmethod
            def from_pretrained(cls, model_id: str, **kwargs: Any) -> _FakePipeline:
                state["loads"].append({"pipeline": cls_name, "model_id": model_id, "kwargs": dict(kwargs)})
                return _FakePipeline(cls_name, model_id, kwargs)

            @classmethod
            def from_pipe(cls, pipe: _FakePipeline, **_kwargs: Any) -> _FakePipeline:
                state["loads"].append({"pipeline": cls_name, "derived_from": pipe._cls_name, "model_id": pipe._model_id})
                return _FakePipeline(cls_name, pipe._model_id, pipe._load_kwargs)

        _PipeMeta.__name__ = cls_name
        return _PipeMeta

    class _FakeBitsAndBytesConfig:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = dict(kwargs)
            state["quant_configs"].append(dict(kwargs))

    class _FakeWanTransformer3DModel:
        @classmethod
        def from_pretrained(cls, model_id: str, **kwargs: Any) -> _FakeTransformer:
            state["transformer_loads"].append({"model_id": model_id, "kwargs": dict(kwargs)})
            return _FakeTransformer()

    class _FakeAutoencoderKLWan:
        @classmethod
        def from_pretrained(cls, _model_id: str, **_kwargs: Any) -> _FakeVae:
            return _FakeVae()

    fake_diffusers: Any = types.ModuleType("diffusers")
    fake_diffusers.WanPipeline = _make_pipe_cls("WanPipeline")
    fake_diffusers.WanImageToVideoPipeline = _make_pipe_cls("WanImageToVideoPipeline")
    fake_diffusers.WanVideoToVideoPipeline = _make_pipe_cls("WanVideoToVideoPipeline")
    fake_diffusers.BitsAndBytesConfig = _FakeBitsAndBytesConfig
    fake_diffusers.WanTransformer3DModel = _FakeWanTransformer3DModel
    fake_diffusers.AutoencoderKLWan = _FakeAutoencoderKLWan

    fake_imageio: Any = types.ModuleType("imageio")

    class _FakeWriter:
        def __init__(self, path: str, **_kwargs: Any) -> None:
            self._path = Path(path)
            self._frames: list[Any] = []

        def append_data(self, arr: Any) -> None:
            self._frames.append(np.array(arr, copy=True))

        def close(self) -> None:
            state["written_frames"].extend(self._frames)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            _make_test_mp4(self._path, width=64, height=64, duration_s=0.4, fps=12)

    def _get_writer(path: str, **kwargs: Any) -> _FakeWriter:
        return _FakeWriter(path, **kwargs)

    fake_imageio_v3: Any = types.ModuleType("imageio.v3")

    def _imiter(_path: str) -> Any:
        for _ in range(16):
            yield np.full((96, 128, 3), 110, dtype=np.uint8)

    fake_imageio_v3.imiter = _imiter
    fake_imageio.get_writer = _get_writer
    fake_imageio.v3 = fake_imageio_v3

    fake_hf: Any = types.ModuleType("huggingface_hub")

    def _model_info(model_id: str) -> Any:
        siblings = [types.SimpleNamespace(rfilename="transformer/config.json")]
        if "a14b" in model_id.lower():
            siblings.append(types.SimpleNamespace(rfilename="transformer_2/config.json"))
        return types.SimpleNamespace(siblings=siblings)

    fake_hf.model_info = _model_info

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "diffusers", fake_diffusers)
    monkeypatch.setitem(sys.modules, "imageio", fake_imageio)
    monkeypatch.setitem(sys.modules, "imageio.v3", fake_imageio_v3)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hf)
    return state


def _make_cli_shim(
    bin_dir: Path,
    name: str,
    log_path: Path,
    *,
    exit_code: int = 0,
    stdout_text: str = "",
    stderr_text: str = "",
    write_png_on_render: bool = False,
    write_mp4_on_render: bool = False,
) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / name
    ffmpeg_exe = _ffmpeg_bin()
    script = f"""#!{sys.executable}
import json
import os
import subprocess
import sys
from pathlib import Path

log_file = Path({str(log_path)!r})
log_file.parent.mkdir(parents=True, exist_ok=True)
with log_file.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps({{"bin": {name!r}, "argv": sys.argv, "cwd": os.getcwd()}}) + "\\n")

args = sys.argv[1:]
stdout_text = {stdout_text!r}
stderr_text = {stderr_text!r}
if stdout_text:
    sys.stdout.write(stdout_text)
if stderr_text:
    sys.stderr.write(stderr_text)

out_target = None
for i, a in enumerate(args):
    if a in ("--output", "-o") and i + 1 < len(args):
        out_target = Path(args[i + 1])
        break
    if a.startswith("--output="):
        out_target = Path(a.split("=", 1)[1])
        break
if out_target is None and len(args) >= 2 and args[0] == "remotion" and args[1] == "render":
    out_target = Path(args[-1])

if {write_png_on_render!r} and out_target is not None:
    out_target.parent.mkdir(parents=True, exist_ok=True)
    out_target.write_bytes({MINIMAL_PNG!r})

if {write_mp4_on_render!r} and out_target is not None:
    out_target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            {ffmpeg_exe!r}, "-v", "error", "-y", "-f", "lavfi",
            "-i", "color=c=green:s=64x64:r=12:d=0.5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_target),
        ],
        check=True,
    )

raise SystemExit({exit_code!r})
"""
    shim.write_text(script, encoding="utf-8")
    shim.chmod(0o755)
    return shim


# ---------------------------------------------------------------------------
# F15 — Wan 2.1/2.2 Diffusers Engine (7 Tests)
# ---------------------------------------------------------------------------


def test_f15_wan_diffusers_runner_contract_and_router_registration(
    full_48g_profile: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _apply_hw_profile(monkeypatch, full_48g_profile)
    _install_fake_wan_stack(monkeypatch, vram_gb=48.0)

    base_mod = _imp("local_runners.base")
    router_mod = _imp("local_runners.router")
    wan_mod = _imp("local_runners.wan_diffusers_runner")

    runner_cls = wan_mod.WanDiffusersRunner
    direct = runner_cls()
    assert isinstance(direct, base_mod.LocalRunner)
    assert "wan" in direct.name.lower()
    assert direct.is_installed() is True

    caps = direct.capabilities()
    caps_blob = json.dumps(caps).lower()
    for op in ("text_to_video", "image_to_video", "video_to_video", "first_last_frame", "text_to_image"):
        assert op in caps_blob
    assert any(tok in caps_blob for tok in ("chain", "long_form", "multi_segment"))

    selected = router_mod.select_runner("video", model_id="wan2.2-ti2v-5b", profile=full_48g_profile)
    assert isinstance(selected, base_mod.LocalRunner)
    # Also confirm WanDiffusersRunner is explicitly reachable via router
    if not isinstance(selected, runner_cls):
        selected_wan = router_mod.select_runner("video", model_id="wan_diffusers:wan2.2-ti2v-5b", profile=full_48g_profile)
        assert isinstance(selected_wan, runner_cls)


def test_f15_t2v_single_pass_and_text_to_image_48g(
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = isolated_workspace
    _apply_hw_profile(monkeypatch, full_48g_profile)
    state = _install_fake_wan_stack(monkeypatch, vram_gb=48.0)
    wan_mod = _imp("local_runners.wan_diffusers_runner")

    runner = wan_mod.WanDiffusersRunner()
    t2v_out = tmp_path / "t2v.mp4"
    res_t2v = runner.run(
        {
            "operation": "text_to_video",
            "prompt": "neon rain across cobblestone alley",
            "num_frames": 17,
            "width": 640,
            "height": 384,
            "output_path": str(t2v_out),
            "profile": full_48g_profile,
        }
    )
    assert res_t2v.get("ok", True) is not False and not res_t2v.get("error")
    assert t2v_out.is_file() and t2v_out.stat().st_size > 0
    assert state["loads"][0]["pipeline"] == "WanPipeline"
    assert state["vae_tiling"] >= 1 and state["vae_slicing"] >= 1
    if "segments" in res_t2v:
        assert int(res_t2v["segments"]) == 1

    t2i_out = tmp_path / "t2i.png"
    res_t2i = runner.run(
        {
            "operation": "text_to_image",
            "prompt": "portrait under sodium streetlamp",
            "width": 640,
            "height": 384,
            "output_path": str(t2i_out),
            "profile": full_48g_profile,
        }
    )
    assert res_t2i.get("ok", True) is not False and not res_t2i.get("error")
    assert t2i_out.is_file()
    pil_image = importlib.import_module("PIL.Image")
    with pil_image.open(t2i_out) as img:
        assert img.size == (640, 384)
    assert int(state["calls"][-1]["kwargs"]["num_frames"]) == 1


def test_f15_i2v_and_first_last_frame_operations(
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = isolated_workspace
    _apply_hw_profile(monkeypatch, full_48g_profile)
    state = _install_fake_wan_stack(monkeypatch, vram_gb=48.0)
    wan_mod = _imp("local_runners.wan_diffusers_runner")
    pil_image = importlib.import_module("PIL.Image")

    start_png = tmp_path / "start.png"
    end_png = tmp_path / "end.png"
    pil_image.new("RGB", (320, 240), (220, 30, 30)).save(start_png)
    pil_image.new("RGB", (320, 240), (30, 30, 220)).save(end_png)

    runner = wan_mod.WanDiffusersRunner()
    i2v_out = tmp_path / "i2v.mp4"
    res_i2v = runner.run(
        {
            "operation": "image_to_video",
            "prompt": "camera slowly pushes toward lantern",
            "reference_image_path": str(start_png),
            "num_frames": 17,
            "width": 640,
            "height": 384,
            "output_path": str(i2v_out),
            "profile": full_48g_profile,
        }
    )
    assert res_i2v.get("ok", True) is not False and not res_i2v.get("error")
    assert i2v_out.is_file() and i2v_out.stat().st_size > 0
    assert state["calls"][0]["pipeline"] == "WanImageToVideoPipeline"
    assert state["calls"][0]["kwargs"]["image"].size == (640, 384)
    assert state["calls"][0]["kwargs"].get("last_image") is None

    flf_out = tmp_path / "flf.mp4"
    res_flf = runner.run(
        {
            "operation": "first_last_frame",
            "prompt": "morph smoothly from red to blue harbor",
            "reference_image_path": str(start_png),
            "last_image_path": str(end_png),
            "num_frames": 17,
            "width": 640,
            "height": 384,
            "output_path": str(flf_out),
            "profile": full_48g_profile,
        }
    )
    assert res_flf.get("ok", True) is not False and not res_flf.get("error")
    assert flf_out.is_file() and flf_out.stat().st_size > 0
    assert state["calls"][1]["pipeline"] == "WanImageToVideoPipeline"
    assert state["calls"][1]["kwargs"]["image"].size == (640, 384)
    assert state["calls"][1]["kwargs"]["last_image"].size == (640, 384)


def test_f15_video_to_video_operation_passes_video_and_strength(
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = isolated_workspace
    _apply_hw_profile(monkeypatch, full_48g_profile)
    state = _install_fake_wan_stack(monkeypatch, vram_gb=48.0)
    wan_mod = _imp("local_runners.wan_diffusers_runner")

    src_mp4 = _make_test_mp4(tmp_path / "src.mp4")
    v2v_out = tmp_path / "v2v.mp4"
    runner = wan_mod.WanDiffusersRunner()
    res = runner.run(
        {
            "operation": "video_to_video",
            "prompt": "stylize into painterly noir",
            "source_video_path": str(src_mp4),
            "strength": 0.65,
            "num_frames": 17,
            "width": 640,
            "height": 384,
            "output_path": str(v2v_out),
            "profile": full_48g_profile,
        }
    )
    assert res.get("ok", True) is not False and not res.get("error")
    assert v2v_out.is_file() and v2v_out.stat().st_size > 0
    call = state["calls"][0]
    assert call["pipeline"] == "WanVideoToVideoPipeline"
    assert call["kwargs"]["strength"] == pytest.approx(0.65)
    assert isinstance(call["kwargs"]["video"], list) and len(call["kwargs"]["video"]) >= 5
    assert "num_frames" not in call["kwargs"]


def test_f15_multi_segment_over_5s_i2v_chaining_and_drift_match(
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = isolated_workspace
    _apply_hw_profile(monkeypatch, full_48g_profile)
    state = _install_fake_wan_stack(
        monkeypatch,
        vram_gb=48.0,
        segment_colors=[(128, 128, 128), (220, 140, 80), (220, 140, 80)],
    )
    wan_mod = _imp("local_runners.wan_diffusers_runner")
    np = importlib.import_module("numpy")

    out_mp4 = tmp_path / "long_chain.mp4"
    runner = wan_mod.WanDiffusersRunner()
    res = runner.run(
        {
            "operation": "text_to_video",
            "prompt": "base shot",
            "segment_prompts": ["shot A", "shot B", "shot C"],
            "duration_seconds": 10,
            "fps": 24,
            "segment_frames": 81,
            "seed": 100,
            "correct_drift": True,
            "width": 640,
            "height": 384,
            "output_path": str(out_mp4),
            "profile": full_48g_profile,
        }
    )
    assert res.get("ok", True) is not False and not res.get("error")
    assert out_mp4.is_file() and out_mp4.stat().st_size > 0
    assert len(state["calls"]) == 3
    assert state["calls"][0]["pipeline"] == "WanPipeline"
    assert state["calls"][1]["pipeline"] == "WanImageToVideoPipeline"
    assert state["calls"][2]["pipeline"] == "WanImageToVideoPipeline"
    assert any(load.get("derived_from") == "WanPipeline" for load in state["loads"])

    for idx, call in enumerate(state["calls"]):
        assert call["kwargs"]["prompt"] == ["shot A", "shot B", "shot C"][idx]
        assert call["kwargs"]["generator"].seed == 100 + idx

    # Segment 1 anchor image must carry the corner pixel signature of segment 0's last frame
    anchor_px = np.asarray(state["calls"][1]["kwargs"]["image"])[2, 2]
    assert tuple(int(v) for v in anchor_px) == (17, 231, 93)

    # Drift-corrected final frame mean must sit near segment 0's neutral (128, 128, 128) rather than shifted (220, 140, 80)
    final_frame = np.asarray(state["written_frames"][-1], dtype=np.float32)
    ch_mean = final_frame.mean(axis=(0, 1))
    assert abs(float(ch_mean[0]) - 128.0) < 25.0
    assert abs(float(ch_mean[2]) - 128.0) < 25.0


def test_f15_vram_aware_bf16_precision_and_progress_callback(
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = isolated_workspace
    _apply_hw_profile(monkeypatch, full_48g_profile)
    state = _install_fake_wan_stack(monkeypatch, vram_gb=48.0, bf16=True)
    wan_mod = _imp("local_runners.wan_diffusers_runner")

    events: list[dict[str, Any]] = []
    out_mp4 = tmp_path / "bf16_prog.mp4"
    res = wan_mod.WanDiffusersRunner().run(
        {
            "operation": "text_to_video",
            "prompt": "clockwork harbor cranes",
            "model_variant": "wan2.2-ti2v-5b",
            "precision": "auto",
            "offload_mode": "auto",
            "duration_seconds": 6,
            "fps": 24,
            "segment_frames": 81,
            "output_path": str(out_mp4),
            "profile": full_48g_profile,
        },
        on_progress=events.append,
    )
    assert res.get("ok", True) is not False and not res.get("error")
    assert res.get("precision") == "bf16"
    assert res.get("offload_mode") == "model"
    assert state["quant_configs"] == []
    assert len(events) >= 2


def test_f15_gpu_lease_evicts_resident_llm_and_frees_comfyui_on_48g(
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
    fake_ollama: FakeOllamaServer,
    fake_comfyui: FakeComfyUIServer,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = isolated_workspace
    fake_ollama.set_available_models(["qwen2.5:32b"])
    fake_ollama.load_model("qwen2.5:32b", size_vram=22 * (2**30))
    monkeypatch.setenv("OLLAMA_URL", fake_ollama.base_url)
    monkeypatch.setenv("COMFYUI_URL", fake_comfyui.base_url)

    _apply_hw_profile(monkeypatch, full_48g_profile)
    _install_fake_wan_stack(monkeypatch, vram_gb=48.0, bf16=True)
    wan_mod = _imp("local_runners.wan_diffusers_runner")

    out_mp4 = tmp_path / "lease.mp4"
    res = wan_mod.WanDiffusersRunner().run(
        {
            "operation": "text_to_video",
            "prompt": "stormy sea lighthouse",
            "model_variant": "wan2.2-t2v-a14b",
            "num_frames": 17,
            "output_path": str(out_mp4),
            "profile": full_48g_profile,
        }
    )
    assert res.get("ok", True) is not False and not res.get("error")
    assert out_mp4.is_file()
    assert "qwen2.5:32b" in fake_ollama.get_evictions()
    assert fake_ollama.get_loaded_models() == []


# ---------------------------------------------------------------------------
# F16 — Multi-Runtime Composers & 3D/SVG (7 Tests)
# ---------------------------------------------------------------------------


def test_f16_bundled_remotion_ink_theater_and_blender_assets_present() -> None:
    root = _repo_root()
    remotion_pkg = root / "remotion-composer" / "package.json"
    remotion_entry = root / "remotion-composer" / "src" / "Root.tsx"
    ink_theater = root / "ink-theater" / "ink-theater.js"
    ink_puppet = root / "ink-theater" / "ink-puppet.js"
    ink_font = root / "ink-theater" / "assets" / "patrickhand.ttf"
    blender_rt = root / "scripts" / "composers" / "templates" / "blender-world-runtime.py"

    for p in (remotion_pkg, remotion_entry, ink_theater, ink_puppet, ink_font, blender_rt):
        assert p.is_file(), f"Missing bundled F16 asset: {p}"
        assert p.stat().st_size > 0

    pkg = json.loads(remotion_pkg.read_text(encoding="utf-8"))
    deps_blob = json.dumps(pkg).lower()
    assert "remotion" in deps_blob


def test_f16_compose_status_endpoint_reports_all_four_runtimes(
    live_studio_server: StudioHarness,
) -> None:
    resp = live_studio_server.get("/api/composers/status")
    assert resp.status == 200
    body = resp.json()
    runtimes = body.get("runtimes") if isinstance(body.get("runtimes"), dict) else body
    assert isinstance(runtimes, dict)
    for rt in ("ffmpeg", "remotion", "hyperframes", "blender"):
        assert rt in runtimes
        entry = runtimes[rt]
        avail = entry if isinstance(entry, bool) else bool(entry.get("available"))
        if rt == "ffmpeg":
            assert avail is (shutil.which("ffmpeg") is not None)


def test_f16_compose_render_ffmpeg_runtime_produces_real_mp4(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    c1 = _make_test_mp4(tmp_path / "c1.mp4", duration_s=1.0)
    c2 = _make_test_mp4(tmp_path / "c2.mp4", duration_s=1.0)
    out_mp4 = tmp_path / "ffmpeg_composed.mp4"

    resp = live_studio_server.post(
        "/api/composers/render",
        {
            "runtime": "ffmpeg",
            "cuts": [
                {"source": str(c1), "in_seconds": 0.0, "out_seconds": 1.0},
                {"source": str(c2), "in_seconds": 0.0, "out_seconds": 1.0},
            ],
            "output_path": str(out_mp4),
        },
    )
    assert resp.status == 200
    assert out_mp4.is_file() and out_mp4.stat().st_size > 0
    probe = _probe_video_ffmpeg(out_mp4)
    assert probe["has_video"] is True
    assert probe["duration"] >= 1.5


def test_f16_compose_render_remotion_runtime_via_npx_shim(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tmp_composer = tmp_path / "remotion-composer"
    shutil.copytree(_repo_root() / "remotion-composer", tmp_composer)
    (tmp_composer / "node_modules").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REMOTION_COMPOSER_DIR", str(tmp_composer))

    log_path = tmp_path / "shim_argv.jsonl"
    bin_dir = tmp_path / "bin"
    _make_cli_shim(bin_dir, "npx", log_path, write_mp4_on_render=True)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    clip = _make_test_mp4(tmp_path / "clip.mp4", duration_s=1.0)
    out_mp4 = tmp_path / "remotion_out.mp4"
    resp = live_studio_server.post(
        "/api/composers/render",
        {
            "runtime": "remotion",
            "composer_dir": str(tmp_composer),
            "renderer_family": "explainer",
            "cuts": [{"source": str(clip), "in_seconds": 0.0, "out_seconds": 1.0}],
            "output_path": str(out_mp4),
        },
    )
    assert resp.status == 200
    assert out_mp4.is_file() and out_mp4.stat().st_size > 0

    calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any("remotion" in c["argv"] and "render" in c["argv"] for c in calls)


def test_f16_compose_render_hyperframes_ink_theater_via_npx_shim(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    log_path = tmp_path / "hf_argv.jsonl"
    bin_dir = tmp_path / "bin"
    _make_cli_shim(bin_dir, "node", log_path, stdout_text="v22.14.0\n")
    _make_cli_shim(bin_dir, "npx", log_path, stdout_text='{"ok": true, "passed": true}\n', write_mp4_on_render=True)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    hf_ws = tmp_path / "hf_ws"
    out_mp4 = tmp_path / "hf_out.mp4"
    clip = _make_test_mp4(tmp_path / "hf_clip.mp4", duration_s=1.0)

    resp = live_studio_server.post(
        "/api/composers/render",
        {
            "runtime": "hyperframes",
            "operation": "render",
            "workspace_path": str(hf_ws),
            "output_path": str(out_mp4),
            "ink_theater": True,
            "edit_decisions": {"cuts": [{"source": str(clip), "in_seconds": 0.0, "out_seconds": 1.0}]},
        },
    )
    assert resp.status == 200
    assert out_mp4.is_file() and out_mp4.stat().st_size > 0
    index_html = hf_ws / "index.html"
    assert index_html.is_file()
    html_text = index_html.read_text(encoding="utf-8")
    assert 'data-composition-id="root"' in html_text or "__timelines" in html_text

    calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any("hyperframes" in c["argv"] and "render" in c["argv"] for c in calls)


def test_f16_compose_render_blender_world_via_blender_shim(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "blender_argv.jsonl"
    bin_dir = tmp_path / "bin"
    shim = _make_cli_shim(bin_dir, "blender", log_path, stdout_text="OPENMONTAGE_BLENDER=4.5.10\n", write_png_on_render=True)
    monkeypatch.setenv("BLENDER_PATH", str(shim))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    status_resp = live_studio_server.get("/api/composers/status")
    assert status_resp.status == 200
    status_body = status_resp.json()
    runtimes = status_body.get("runtimes") if isinstance(status_body.get("runtimes"), dict) else status_body
    blender_status = runtimes["blender"]
    assert (blender_status if isinstance(blender_status, bool) else bool(blender_status.get("available"))) is True

    out_png = tmp_path / "world.png"
    blend_file = tmp_path / "world.blend"
    render_resp = live_studio_server.post(
        "/api/composers/render",
        {
            "runtime": "blender",
            "operation": "render_still",
            "world_spec": {"seed": 42, "terrain": {"size": 120}},
            "output_path": str(out_png),
            "blend_path": str(blend_file),
        },
    )
    assert render_resp.status == 200
    assert out_png.is_file() and out_png.stat().st_size > 0
    assert blend_file.with_suffix(".world.json").is_file()

    calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any("--background" in c["argv"] and "--python" in c["argv"] and "--operation" in c["argv"] for c in calls)


def test_f16_blender_doctor_operation_verifies_bpy_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "doctor_argv.jsonl"
    bin_dir = tmp_path / "bin"
    shim = _make_cli_shim(bin_dir, "blender", log_path, stdout_text="OPENMONTAGE_BLENDER=4.5.10\n")
    monkeypatch.setenv("BLENDER_PATH", str(shim))

    mod = _imp("composers.blender_world_runner")
    fn = getattr(mod, "run_blender", None) or getattr(mod, "run", None)
    if callable(fn):
        raw = fn({"operation": "doctor"})
    else:
        cls = getattr(mod, "BlenderWorldRunner", None) or mod.BlenderWorld
        raw = cls().execute({"operation": "doctor"})

    if isinstance(raw, dict):
        res = raw
    else:
        res = {"success": getattr(raw, "success", True), **(getattr(raw, "data", None) or {})}

    assert res.get("success", True) is True
    assert "4.5.10" in str(res.get("version_line") or res.get("version") or "")
    assert Path(str(res["blender_path"])).resolve() == shim.resolve()
