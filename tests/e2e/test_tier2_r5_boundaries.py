"""Tier 2 E2E Boundary & Corner Case Coverage for R5 (F12–F16)."""
from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import types
from typing import Any
import wave

import pytest

from e2e.helpers.fake_comfyui import MINIMAL_PNG
from e2e.helpers.studio_harness import IsolatedWorkspace, StudioHarness


def _imp(name: str) -> Any:
    return importlib.import_module(name)


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


def _make_wav(
    path: Path,
    duration_s: float,
    *,
    freq_hz: float = 440.0,
    amplitude: float = 0.35,
    sample_rate: int = 16000,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    n_samples = max(1, int(round(duration_s * sample_rate)))
    frames = bytearray()
    for i in range(n_samples):
        val = int(max(-1.0, min(1.0, amplitude * math.sin(2.0 * math.pi * freq_hz * (i / sample_rate)))) * 32767)
        frames.extend(struct.pack("<h", val))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(frames))
    return path


def _make_test_mp4(
    path: Path,
    *,
    width: int = 160,
    height: int = 120,
    duration_s: float = 1.5,
    fps: int = 12,
    bg_expr: str | None = None,
    audio_expr: str | None = "0.3*sin(2*PI*440*t)",
    with_audio: bool = True,
    sar: str | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    v_input = bg_expr or f"testsrc2=size={width}x{height}:rate={fps}:duration={duration_s}"
    cmd: list[str] = [_ffmpeg_bin(), "-v", "error", "-y", "-f", "lavfi", "-i", v_input]
    if with_audio:
        a_expr = audio_expr if audio_expr is not None else "0.3*sin(2*PI*440*t)"
        cmd.extend(["-f", "lavfi", "-i", f"aevalsrc={a_expr}:s=48000:d={duration_s}"])
    if sar:
        cmd.extend(["-vf", f"setsar={sar}"])
    cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p"])
    if with_audio:
        cmd.extend(["-c:a", "aac", "-b:a", "96k", "-shortest"])
    else:
        cmd.append("-an")
    cmd.append(str(path))
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
    return path


def _probe_video_ffmpeg(path: Path) -> dict[str, Any]:
    proc = subprocess.run([_ffmpeg_bin(), "-i", str(path)], capture_output=True, text=True, timeout=15)
    stderr = proc.stderr or ""
    width = 0
    height = 0
    duration = 0.0
    sar = ""
    dar = ""
    m_res = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", stderr)
    if m_res:
        width = int(m_res.group(1))
        height = int(m_res.group(2))
    m_sar = re.search(r"SAR\s+(\d+:\d+)\s+DAR\s+(\d+:\d+)", stderr)
    if m_sar:
        sar = m_sar.group(1)
        dar = m_sar.group(2)
    m_dur = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", stderr)
    if m_dur:
        duration = int(m_dur.group(1)) * 3600 + int(m_dur.group(2)) * 60 + float(m_dur.group(3))
    return {
        "width": width,
        "height": height,
        "duration": duration,
        "has_video": "Video:" in stderr,
        "has_audio": "Audio:" in stderr,
        "sar": sar,
        "dar": dar,
    }


def _normalize_tool_output(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    out: dict[str, Any] = {}
    for attr in ("success", "error", "artifacts", "duration_seconds"):
        if hasattr(raw, attr):
            out[attr] = getattr(raw, attr)
    data = getattr(raw, "data", None)
    if isinstance(data, dict):
        out.update(data)
        out.setdefault("data", data)
    return out


def _is_valid_result(res: dict[str, Any]) -> bool:
    if "valid" in res:
        return bool(res["valid"])
    if "passed" in res:
        return bool(res["passed"])
    if "success" in res:
        return bool(res["success"]) and not res.get("errors")
    return not res.get("errors")


def _call_slideshow_risk(
    scenes: list[dict[str, Any]],
    *,
    renderer_family: str | None = None,
    render_runtime: str | None = None,
) -> dict[str, Any]:
    mod = _imp("qa.slideshow_risk")
    fn = getattr(mod, "score_slideshow_risk", None) or getattr(mod, "score", None)
    assert callable(fn)
    res = fn(scenes, renderer_family=renderer_family, render_runtime=render_runtime)
    assert isinstance(res, dict)
    return res


def _call_composition_validator(
    composition_path: Path,
    *,
    assets_root: Path | None = None,
    render_runtime: str | None = None,
) -> dict[str, Any]:
    mod = _imp("qa.composition_validator")
    payload: dict[str, Any] = {"composition_path": str(composition_path)}
    if assets_root is not None:
        payload["assets_root"] = str(assets_root)
    if render_runtime is not None:
        payload["render_runtime"] = render_runtime
    for fn_name in ("validate_composition", "validate", "run_composition_validator"):
        fn = getattr(mod, fn_name, None)
        if callable(fn):
            sig = inspect.signature(fn)
            if len(sig.parameters) == 1 and next(iter(sig.parameters.values())).name in {"inputs", "payload", "spec"}:
                return _normalize_tool_output(fn(payload))
            kwargs: dict[str, Any] = {}
            if "assets_root" in sig.parameters and assets_root is not None:
                kwargs["assets_root"] = str(assets_root)
            if "render_runtime" in sig.parameters and render_runtime is not None:
                kwargs["render_runtime"] = render_runtime
            return _normalize_tool_output(fn(str(composition_path), **kwargs))
    cls = mod.CompositionValidator
    return _normalize_tool_output(cls().execute(payload))


def _call_visual_qa(inputs: dict[str, Any]) -> dict[str, Any]:
    mod = _imp("qa.visual_qa")
    op = str(inputs.get("operation", "probe"))
    for fn_name in ("run_visual_qa", "visual_qa", op):
        fn = getattr(mod, fn_name, None)
        if callable(fn):
            sig = inspect.signature(fn)
            params = list(sig.parameters.keys())
            if params in (["inputs"], ["payload"], ["spec"]):
                return _normalize_tool_output(fn(inputs))
            if "operation" in sig.parameters:
                return _normalize_tool_output(fn(**{k: v for k, v in inputs.items() if k in sig.parameters}))
            filtered = {k: v for k, v in inputs.items() if k in sig.parameters and k != "operation"}
            if len(params) >= 1 and params[0] in {"input_path", "video_path", "path"} and "input_path" in inputs:
                key0 = params[0]
                rest = {k: v for k, v in filtered.items() if k != key0}
                return _normalize_tool_output(fn(inputs["input_path"], **rest))
            return _normalize_tool_output(fn(**filtered))
    cls = mod.VisualQA
    return _normalize_tool_output(cls().execute(inputs))


def _call_silence_cutter(inputs: dict[str, Any]) -> dict[str, Any]:
    mod = _imp("post_tools")
    for fn_name in ("silence_cutter", "silence_cut", "cut_silence", "run_silence_cutter"):
        fn = getattr(mod, fn_name, None)
        if callable(fn):
            sig = inspect.signature(fn)
            params = list(sig.parameters.keys())
            if params in (["inputs"], ["payload"], ["spec"]):
                return _normalize_tool_output(fn(inputs))
            return _normalize_tool_output(fn(**{k: v for k, v in inputs.items() if k in sig.parameters}))
    cls = mod.SilenceCutter
    return _normalize_tool_output(cls().execute(inputs))


def _call_auto_reframe(inputs: dict[str, Any]) -> dict[str, Any]:
    mod = _imp("post_tools")
    for fn_name in ("auto_reframe", "reframe", "run_auto_reframe"):
        fn = getattr(mod, fn_name, None)
        if callable(fn):
            sig = inspect.signature(fn)
            params = list(sig.parameters.keys())
            if params in (["inputs"], ["payload"], ["spec"]):
                return _normalize_tool_output(fn(inputs))
            return _normalize_tool_output(fn(**{k: v for k, v in inputs.items() if k in sig.parameters}))
    cls = mod.AutoReframe
    return _normalize_tool_output(cls().execute(inputs))


def _install_fake_wan_stack(
    monkeypatch: pytest.MonkeyPatch,
    *,
    vram_gb: float = 48.0,
    bf16: bool = True,
    cuda_available: bool = True,
    call_exception: BaseException | None = None,
) -> dict[str, Any]:
    pil_image = importlib.import_module("PIL.Image")
    np = importlib.import_module("numpy")

    state: dict[str, Any] = {
        "loads": [],
        "calls": [],
        "offload_calls": [],
        "empty_cache_calls": 0,
        "quant_configs": [],
        "transformer_loads": [],
    }

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
            pass

        def enable_slicing(self) -> None:
            pass

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
            state["calls"].append({"pipeline": self._cls_name, "kwargs": dict(kwargs)})
            if call_exception is not None:
                raise call_exception
            num_frames = int(kwargs.get("num_frames") or len(kwargs.get("video") or []) or 1)
            w = int(kwargs.get("width") or 640)
            h = int(kwargs.get("height") or 384)
            frames = [pil_image.fromarray(np.full((h, w, 3), 120, dtype=np.uint8)) for _ in range(num_frames)]
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

        def append_data(self, _arr: Any) -> None:
            pass

        def close(self) -> None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            _make_test_mp4(self._path, width=64, height=64, duration_s=0.3, fps=12)

    fake_imageio_v3: Any = types.ModuleType("imageio.v3")
    fake_imageio_v3.imiter = lambda _p: [np.full((64, 64, 3), 100, dtype=np.uint8) for _ in range(9)]
    fake_imageio.get_writer = lambda path, **kw: _FakeWriter(path, **kw)
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
) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / name
    script = f"""#!{sys.executable}
import json
import os
import sys
from pathlib import Path

log_file = Path({str(log_path)!r})
log_file.parent.mkdir(parents=True, exist_ok=True)
with log_file.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps({{"bin": {name!r}, "argv": sys.argv, "cwd": os.getcwd()}}) + "\\n")

if {stdout_text!r}:
    sys.stdout.write({stdout_text!r})
if {stderr_text!r}:
    sys.stderr.write({stderr_text!r})

args = sys.argv[1:]
out_target = None
for i, a in enumerate(args):
    if a in ("--output", "-o") and i + 1 < len(args):
        out_target = Path(args[i + 1])
        break
    if a.startswith("--output="):
        out_target = Path(a.split("=", 1)[1])
        break
if {write_png_on_render!r} and out_target is not None:
    out_target.parent.mkdir(parents=True, exist_ok=True)
    out_target.write_bytes({MINIMAL_PNG!r})

raise SystemExit({exit_code!r})
"""
    shim.write_text(script, encoding="utf-8")
    shim.chmod(0o755)
    return shim


# ---------------------------------------------------------------------------
# F12 — Pre-Render QA Gate Boundaries (6 Tests)
# ---------------------------------------------------------------------------


def test_f12_bva_slideshow_risk_empty_and_verdict_thresholds() -> None:
    empty_res = _call_slideshow_risk([])
    assert empty_res["verdict"] == "fail"
    assert float(empty_res["average"]) >= 4.0

    # len(scenes) == 2 triggers repetition == 0.0; >60% text_card triggers typography == 4.0
    two_text = [
        {"type": "text_card", "description": "Card 1"},
        {"type": "text_card", "description": "Card 2"},
    ]
    two_res = _call_slideshow_risk(two_text)
    assert float(two_res["dimensions"]["repetition"]["score"]) == 0.0
    assert float(two_res["dimensions"]["typography_overreliance"]["score"]) == 4.0

    strong_scenes = [
        {
            "type": t,
            "description": f"Unique scene {i}",
            "shot_intent": "Advance story",
            "narrative_role": "beat",
            "shot_language": {"shot_size": s, "camera_movement": "dolly_in", "lighting_key": "natural"},
            "hero_moment": i == 0,
        }
        for i, (t, s) in enumerate([("establishing", "wide"), ("action", "medium"), ("dialogue", "close_up"), ("insert", "ecu")])
    ]
    assert _call_slideshow_risk(strong_scenes)["verdict"] == "strong"

    acceptable_scenes = [
        {
            "type": "b_roll",
            "description": f"Unique scene {i}",
            "shot_intent": "Explain" if i == 0 else "",
            "shot_language": {"shot_size": "medium", "camera_movement": "static"},
        }
        for i in range(4)
    ]
    acceptable_res = _call_slideshow_risk(acceptable_scenes)
    assert 2.0 <= float(acceptable_res["average"]) < 3.0
    assert acceptable_res["verdict"] == "acceptable"

    revise_scenes = [
        {
            "type": "text_card",
            "description": "Identical slide",
            "shot_language": {"shot_size": "medium", "camera_movement": "static"},
        }
        for _ in range(4)
    ]
    revise_res = _call_slideshow_risk(revise_scenes)
    assert 3.0 <= float(revise_res["average"]) < 4.0
    assert revise_res["verdict"] == "revise"

    fail_res = _call_slideshow_risk(revise_scenes, renderer_family="cinematic-trailer")
    assert float(fail_res["average"]) >= 4.0
    assert fail_res["verdict"] == "fail"


def test_f12_bva_slideshow_risk_cinematic_non_moving_values() -> None:
    def _plan(movement: Any, *, omit: bool = False) -> list[dict[str, Any]]:
        sl: dict[str, Any] = {"shot_size": "wide", "lighting_key": "low_key"}
        if not omit:
            sl["camera_movement"] = movement
        return [
            {
                "type": f"type_{i}",
                "description": f"Distinct visual {i}",
                "shot_intent": "Move story",
                "hero_moment": i == 0,
                "shot_language": sl,
            }
            for i in range(4)
        ]

    for non_moving in ("static", "unspecified", None):
        res = _call_slideshow_risk(_plan(non_moving), renderer_family="cinematic-trailer")
        assert float(res["dimensions"]["unsupported_cinematic_claims"]["score"]) > 0.0

    omitted_res = _call_slideshow_risk(_plan(None, omit=True), renderer_family="cinematic-trailer")
    assert float(omitted_res["dimensions"]["unsupported_cinematic_claims"]["score"]) > 0.0

    moving_res = _call_slideshow_risk(_plan("dolly_in"), renderer_family="cinematic-trailer")
    assert float(moving_res["dimensions"]["unsupported_cinematic_claims"]["score"]) == 0.0


def test_f12_bva_composition_validator_narration_overshoot_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    clip = _make_test_mp4(tmp_path / "c.mp4", duration_s=4.0)
    music = _make_wav(tmp_path / "music.wav", duration_s=5.0)

    narr_ok = _make_wav(tmp_path / "narr_ok.wav", duration_s=4.5)
    comp_warn = tmp_path / "comp_warn.json"
    comp_warn.write_text(
        json.dumps(
            {
                "render_runtime": "ffmpeg",
                "cuts": [{"source": str(clip), "in_seconds": 0.0, "out_seconds": 4.0}],
                "audio": {
                    "narration": {"source": str(narr_ok), "duration_seconds": 4.5},
                    "music": {"source": str(music), "duration_seconds": 5.0},
                },
            }
        ),
        encoding="utf-8",
    )
    res_warn = _call_composition_validator(comp_warn, assets_root=tmp_path, render_runtime="ffmpeg")
    assert _is_valid_result(res_warn) is True
    assert len(list(res_warn.get("warnings") or [])) >= 1

    narr_bad = _make_wav(tmp_path / "narr_bad.wav", duration_s=5.5)
    comp_err = tmp_path / "comp_err.json"
    comp_err.write_text(
        json.dumps(
            {
                "render_runtime": "ffmpeg",
                "cuts": [{"source": str(clip), "in_seconds": 0.0, "out_seconds": 4.0}],
                "audio": {
                    "narration": {"source": str(narr_bad), "duration_seconds": 5.5},
                    "music": {"source": str(music), "duration_seconds": 5.0},
                },
            }
        ),
        encoding="utf-8",
    )
    res_err = _call_composition_validator(comp_err, assets_root=tmp_path, render_runtime="ffmpeg")
    assert _is_valid_result(res_err) is False
    assert len(list(res_err.get("errors") or [])) >= 1


def test_f12_bva_composition_validator_empty_inverted_overlap_missing_corrupt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    clip = _make_test_mp4(tmp_path / "valid.mp4", duration_s=3.0)

    cases: list[tuple[Path, str]] = [
        (tmp_path / "empty.json", json.dumps({"render_runtime": "ffmpeg", "cuts": []})),
        (
            tmp_path / "inverted.json",
            json.dumps({"render_runtime": "ffmpeg", "cuts": [{"source": str(clip), "in_seconds": 2.0, "out_seconds": 1.0}]}),
        ),
        (
            tmp_path / "overlap.json",
            json.dumps(
                {
                    "render_runtime": "ffmpeg",
                    "cuts": [
                        {"source": str(clip), "in_seconds": 0.0, "out_seconds": 2.0},
                        {"source": str(clip), "in_seconds": 1.5, "out_seconds": 3.0},
                    ],
                }
            ),
        ),
        (
            tmp_path / "missing_asset.json",
            json.dumps({"render_runtime": "ffmpeg", "cuts": [{"source": str(tmp_path / "nope.mp4"), "in_seconds": 0.0, "out_seconds": 1.0}]}),
        ),
        (tmp_path / "corrupt.json", "{not valid json"),
    ]
    for path, content in cases:
        path.write_text(content, encoding="utf-8")
        res = _call_composition_validator(path, assets_root=tmp_path, render_runtime="ffmpeg")
        assert _is_valid_result(res) is False

    nonexistent_res = _call_composition_validator(tmp_path / "does_not_exist.json", assets_root=tmp_path, render_runtime="ffmpeg")
    assert _is_valid_result(nonexistent_res) is False


def test_f12_bva_visual_qa_black_frame_silence_clipping_and_missing_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    black_silent = _make_test_mp4(
        tmp_path / "black_silent.mp4",
        width=320,
        height=240,
        duration_s=1.2,
        bg_expr="color=c=black:s=320x240:r=12:d=1.2",
        audio_expr="0.0001*sin(2*PI*440*t)",
        with_audio=True,
    )
    clipping = _make_test_mp4(
        tmp_path / "clipping.mp4",
        width=320,
        height=240,
        duration_s=1.2,
        audio_expr="1.0*sin(2*PI*440*t)",
        with_audio=True,
    )

    black_frames_dir = tmp_path / "black_frames"
    rev_black = _call_visual_qa({"operation": "review", "input_path": str(black_silent), "timestamps": [0.5], "output_dir": str(black_frames_dir)})
    extracted = rev_black.get("frames") or rev_black.get("frame_paths") or sorted(str(p) for p in black_frames_dir.glob("frame_*"))
    assert len(extracted) >= 1
    first_frame = Path(extracted[0]["path"] if isinstance(extracted[0], dict) else str(extracted[0]))
    assert first_frame.is_file()
    if "black_frames_detected" in rev_black:
        assert bool(rev_black["black_frames_detected"]) is True
    else:
        assert first_frame.stat().st_size < 3000

    aud_silent = _call_visual_qa({"operation": "audio_levels", "input_path": str(black_silent), "timestamps": [0.5]})
    assert float(aud_silent["mean_volume_db"]) < -60.0

    aud_clip = _call_visual_qa({"operation": "audio_levels", "input_path": str(clipping), "timestamps": [0.5]})
    assert float(aud_clip["max_volume_db"]) >= -0.5

    mismatch = _call_visual_qa({"operation": "probe", "input_path": str(clipping), "expected": {"width": 9999}})
    assert bool(mismatch.get("validation_passed")) is False

    missing = _call_visual_qa({"operation": "probe", "input_path": str(tmp_path / "missing.mp4")})
    assert bool(missing.get("success", False)) is False or bool(missing.get("error"))


def test_f12_bva_http_qa_check_invalid_payload_fail_and_auth(
    live_studio_server: StudioHarness,
) -> None:
    unauth = live_studio_server.post("/api/qa/check", {"scenes": []}, auth=False)
    assert unauth.status in (401, 403)

    bad_path = live_studio_server.post("/api/qa/check", {"composition_path": "../../etc/passwd"})
    assert bad_path.status in (400, 403, 404)

    empty_bad = live_studio_server.post("/api/qa/check", {})
    assert empty_bad.status < 500

    fail_scenes = [
        {"type": "text_card", "description": "Identical slide", "shot_language": {"shot_size": "medium", "camera_movement": "static"}}
        for _ in range(4)
    ]
    fail_resp = live_studio_server.post("/api/qa/check", {"scenes": fail_scenes, "renderer_family": "cinematic-trailer"})
    assert fail_resp.status in (200, 400, 422)
    body = fail_resp.json()
    verdict = body.get("verdict") or (body.get("slideshow_risk") or {}).get("verdict")
    assert verdict == "fail" or body.get("blocked") is True or fail_resp.status in (400, 422)


# ---------------------------------------------------------------------------
# F13 — Post-Processing Boundaries (6 Tests)
# ---------------------------------------------------------------------------


def test_f13_bva_silence_cutter_no_silence_and_all_silence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    loud = _make_test_mp4(tmp_path / "loud.mp4", duration_s=1.2, audio_expr="0.4*sin(2*PI*440*t)", with_audio=True)
    loud_bytes = loud.read_bytes()
    out_loud = tmp_path / "loud_out.mp4"

    res_loud = _call_silence_cutter({"input_path": str(loud), "output_path": str(out_loud), "mode": "remove"})
    assert int(res_loud.get("silence_segments", 0)) == 0
    assert loud.read_bytes() == loud_bytes

    all_silent = _make_test_mp4(tmp_path / "all_silent.mp4", duration_s=1.2, audio_expr="0", with_audio=True)
    out_silent = tmp_path / "silent_out.mp4"
    res_silent = _call_silence_cutter({"input_path": str(all_silent), "output_path": str(out_silent), "mode": "mark"})
    assert len(res_silent.get("speech_segments") or []) == 0
    assert not (tmp_path / ".silence_cut_tmp").exists()


def test_f13_bva_silence_cutter_corrupt_and_missing_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"not a media file at all")

    for mode in ("remove", "speed_up", "mark"):
        out = tmp_path / f"bad_{mode}.mp4"
        for src in (tmp_path / "missing.mp4", corrupt):
            try:
                res = _call_silence_cutter({"input_path": str(src), "output_path": str(out), "mode": mode})
                assert res.get("success") is False or bool(res.get("error"))
            except (ValueError, RuntimeError, subprocess.SubprocessError):
                pass
            assert not out.exists()

    assert corrupt.read_bytes() == b"not a media file at all"


def test_f13_bva_silence_cutter_extreme_speed_factors_atempo_chain(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    # Create 2s clip: 1s tone + 1s silence
    src = tmp_path / "tone_then_silence.mp4"
    subprocess.run(
        [
            _ffmpeg_bin(),
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=64x64:r=25:d=1",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=64x64:r=25:d=1",
            "-f",
            "lavfi",
            "-i",
            "aevalsrc=0.4*sin(2*PI*440*t):s=48000:d=1",
            "-f",
            "lavfi",
            "-i",
            "aevalsrc=0:s=48000:d=1",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a][3:a]concat=n=2:v=0:a=1[a]",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(src),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )

    for factor in (1.5, 100.0):
        out = tmp_path / f"speed_{factor}.mp4"
        res = _call_silence_cutter(
            {
                "input_path": str(src),
                "output_path": str(out),
                "mode": "speed_up",
                "silence_speed_factor": factor,
                "min_silence_duration": 0.3,
                "padding_seconds": 0.05,
            }
        )
        assert res.get("success", True) is not False and not res.get("error")
        assert out.is_file() and out.stat().st_size > 0
        probe = _probe_video_ffmpeg(out)
        assert probe["has_video"] is True and probe["has_audio"] is True


def test_f13_bva_auto_reframe_passthrough_and_anamorphic_sar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    portrait_src = _make_test_mp4(tmp_path / "already_portrait.mp4", width=180, height=320, duration_s=1.0)
    res_pass = _call_auto_reframe({"input_path": str(portrait_src), "target_aspect": "portrait"})
    assert str(res_pass.get("output") or portrait_src) == str(portrait_src)

    sar_src = _make_test_mp4(tmp_path / "anamorphic.mp4", width=96, height=64, duration_s=1.0, sar="2/1")
    sar_out = tmp_path / "anamorphic_out.mp4"
    empty_faces = tmp_path / "empty_faces.json"
    empty_faces.write_text("[]", encoding="utf-8")

    _call_auto_reframe(
        {
            "input_path": str(sar_src),
            "output_path": str(sar_out),
            "target_width": 48,
            "target_height": 64,
            "face_tracking_json": str(empty_faces),
        }
    )
    assert sar_out.is_file() and sar_out.stat().st_size > 0
    probe = _probe_video_ffmpeg(sar_out)
    assert (probe["width"], probe["height"]) == (48, 64)
    assert probe["sar"] == "1:1"
    assert probe["dar"] == "3:4"


def test_f13_bva_auto_reframe_missing_input_corrupt_json_and_few_points(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    missing_out = tmp_path / "missing_out.mp4"
    try:
        res_missing = _call_auto_reframe({"input_path": str(tmp_path / "missing.mp4"), "output_path": str(missing_out)})
        assert res_missing.get("success") is False or bool(res_missing.get("error"))
    except (ValueError, RuntimeError, FileNotFoundError):
        pass
    assert not missing_out.exists()

    src = _make_test_mp4(tmp_path / "src.mp4", width=320, height=180, duration_s=1.2)
    corrupt_json = tmp_path / "corrupt_faces.json"
    corrupt_json.write_text("{corrupt", encoding="utf-8")
    out_fallback = tmp_path / "fallback.mp4"
    _call_auto_reframe({"input_path": str(src), "output_path": str(out_fallback), "target_aspect": "portrait", "face_tracking_json": str(corrupt_json)})
    assert out_fallback.is_file()
    assert (_probe_video_ffmpeg(out_fallback)["width"], _probe_video_ffmpeg(out_fallback)["height"]) == (1080, 1920)

    two_pts = tmp_path / "two_pts.json"
    two_pts.write_text(
        json.dumps(
            [
                {"timestamp": 0.0, "faces": [{"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.3}]},
                {"timestamp": 0.6, "faces": [{"x": 0.6, "y": 0.2, "w": 0.2, "h": 0.3}]},
            ]
        ),
        encoding="utf-8",
    )
    out_two = tmp_path / "two_pts.mp4"
    _call_auto_reframe({"input_path": str(src), "output_path": str(out_two), "target_aspect": "portrait", "face_tracking_json": str(two_pts)})
    assert out_two.is_file()
    assert (_probe_video_ffmpeg(out_two)["width"], _probe_video_ffmpeg(out_two)["height"]) == (1080, 1920)


def test_f13_bva_http_post_tools_invalid_args_traversal_and_auth(
    live_studio_server: StudioHarness,
    tmp_path: Path,
) -> None:
    unauth = live_studio_server.post("/api/post/silence-cut", {"input_path": "a.mp4"}, auth=False)
    assert unauth.status in (401, 403)

    bad_aspect = live_studio_server.post(
        "/api/post/auto-reframe",
        {"input_path": str(tmp_path / "x.mp4"), "target_aspect": "invalid_99_1"},
    )
    assert bad_aspect.status in (400, 404, 422)

    traversal = live_studio_server.post(
        "/api/post/auto-reframe",
        {"input_path": "../../etc/passwd", "target_aspect": "portrait"},
    )
    assert traversal.status in (400, 403, 404)

    bad_mode = live_studio_server.post(
        "/api/post/silence-cut",
        {"input_path": str(tmp_path / "x.mp4"), "mode": "bogus_mode"},
    )
    assert bad_mode.status in (400, 404, 422)


# ---------------------------------------------------------------------------
# F14 — Content-Addressed Asset Cache Boundaries (6 Tests)
# ---------------------------------------------------------------------------


def test_f14_bva_exact_cap_vs_oversized_and_zero_capacity(tmp_path: Path) -> None:
    mod = _imp("local_runners.asset_cache")

    c_zero = mod.AssetCache(cache_dir=tmp_path / "zero", max_total_bytes=0)
    small = tmp_path / "small.bin"
    small.write_bytes(b"12345678")
    k_small = hashlib.sha256(b"12345678").hexdigest()
    assert c_zero.store(k_small, small) is False
    assert c_zero.stats()["entry_count"] == 0

    c_exact = mod.AssetCache(cache_dir=tmp_path / "exact", max_total_bytes=16)
    exact_file = tmp_path / "exact16.bin"
    exact_file.write_bytes(b"A" * 16)
    k_exact = hashlib.sha256(b"A" * 16).hexdigest()
    assert c_exact.store(k_exact, exact_file) is True
    assert c_exact.stats()["total_bytes"] == 16

    c_cap = mod.AssetCache(cache_dir=tmp_path / "cap16", max_total_bytes=16)
    assert c_cap.store(k_small, small) is True
    manifest_before = (tmp_path / "cap16" / "asset_manifest.jsonl").read_text(encoding="utf-8")

    over_file = tmp_path / "over17.bin"
    over_file.write_bytes(b"B" * 17)
    k_over = hashlib.sha256(b"B" * 17).hexdigest()
    assert c_cap.store(k_over, over_file) is False
    assert c_cap.try_restore(k_small, tmp_path / "restored_small.bin") is not None
    assert (tmp_path / "cap16" / "asset_manifest.jsonl").read_text(encoding="utf-8") == manifest_before


def test_f14_bva_reject_missing_and_zero_byte_source(tmp_path: Path) -> None:
    mod = _imp("local_runners.asset_cache")
    cache = mod.AssetCache(cache_dir=tmp_path / "cache")

    empty_file = tmp_path / "empty.bin"
    empty_file.write_bytes(b"")
    assert cache.store(hashlib.sha256(b"").hexdigest(), empty_file) is False
    assert cache.store(hashlib.sha256(b"missing").hexdigest(), tmp_path / "missing.bin") is False
    assert cache.stats()["entry_count"] == 0


def test_f14_bva_corrupt_manifest_lines_and_blob_drift_recovery(tmp_path: Path) -> None:
    mod = _imp("local_runners.asset_cache")
    cache_dir = tmp_path / "drift_cache"
    cache = mod.AssetCache(cache_dir=cache_dir)

    valid_src = tmp_path / "valid.bin"
    valid_src.write_bytes(b"good-data")
    k_valid = hashlib.sha256(b"good-data").hexdigest()
    stale_src = tmp_path / "stale.bin"
    stale_src.write_bytes(b"stale-data")
    k_stale = hashlib.sha256(b"stale-data").hexdigest()

    assert cache.store(k_valid, valid_src) is True
    assert cache.store(k_stale, stale_src) is True

    # Delete stale blob to simulate filesystem drift & prepend corrupt manifest lines
    for blob in cache_dir.glob(f"{k_stale}*"):
        blob.unlink()
    manifest = cache_dir / "asset_manifest.jsonl"
    orig_text = manifest.read_text(encoding="utf-8")
    manifest.write_text('not json\n{"missing": true}\n' + orig_text, encoding="utf-8")

    assert cache.try_restore(k_stale, tmp_path / "stale_out.bin") is None
    restored = tmp_path / "valid_out.bin"
    assert cache.try_restore(k_valid, restored) is not None
    assert restored.read_bytes() == b"good-data"


def test_f14_bva_env_var_invalid_max_gb_and_enable_flags(
    isolated_workspace: IsolatedWorkspace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = isolated_workspace
    mod = _imp("local_runners.asset_cache")
    reset_fn = getattr(mod, "reset_default_asset_cache", None)
    if callable(reset_fn):
        reset_fn()

    monkeypatch.setenv("OPENMONTAGE_ASSET_CACHE_MAX_GB", "not-a-number")
    monkeypatch.setenv("STUDIO_ASSET_CACHE_MAX_GB", "not-a-number")
    default_bytes = int(mod.default_max_total_bytes())
    assert default_bytes == 20 * (1024**3)

    enabled_fn = getattr(mod, "asset_cache_enabled", None)
    if callable(enabled_fn):
        for off in ("", "0", "false", "off"):
            monkeypatch.setenv("OPENMONTAGE_ASSET_CACHE", off)
            monkeypatch.setenv("STUDIO_ASSET_CACHE", off)
            assert enabled_fn() is False
        for on in ("1", "true", "yes", "on", "TRUE"):
            monkeypatch.setenv("OPENMONTAGE_ASSET_CACHE", on)
            monkeypatch.setenv("STUDIO_ASSET_CACHE", on)
            assert enabled_fn() is True

    if callable(reset_fn):
        reset_fn()


def test_f14_bva_eviction_skips_unremovable_blob_and_preserves_cap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mod = _imp("local_runners.asset_cache")
    cache_dir = tmp_path / "locked_evict"
    cache = mod.AssetCache(cache_dir=cache_dir, max_total_bytes=25_000)

    f1 = tmp_path / "v1.bin"
    f2 = tmp_path / "v2.bin"
    f3 = tmp_path / "v3.bin"
    f1.write_bytes(b"1" * 10_000)
    f2.write_bytes(b"2" * 10_000)
    f3.write_bytes(b"3" * 10_000)
    k1 = hashlib.sha256(b"1" * 10_000).hexdigest()
    k2 = hashlib.sha256(b"2" * 10_000).hexdigest()
    k3 = hashlib.sha256(b"3" * 10_000).hexdigest()

    assert cache.store(k1, f1) is True
    time.sleep(0.02)
    assert cache.store(k2, f2) is True
    time.sleep(0.02)

    real_unlink = Path.unlink

    def _guarded_unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name.startswith(k1):
            raise PermissionError("Simulated Windows file lock on victim 1")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _guarded_unlink)
    assert cache.store(k3, f3) is True
    monkeypatch.undo()

    # Victim 1 stayed protected on OSError; victim 2 was evicted cleanly
    assert cache.try_restore(k1, tmp_path / "out1.bin") is not None
    assert cache.try_restore(k2, tmp_path / "out2.bin") is None
    assert cache.try_restore(k3, tmp_path / "out3.bin") is not None


def test_f14_bva_lock_contention_timeout_raises_cleanly(tmp_path: Path) -> None:
    mod = _imp("local_runners.asset_cache")
    cache = mod.AssetCache(cache_dir=tmp_path / "lock_test")

    acquired = threading.Event()
    release = threading.Event()

    def _holder() -> None:
        with cache._locked(timeout=5.0):
            acquired.set()
            release.wait(timeout=5.0)

    t = threading.Thread(target=_holder, daemon=True)
    t.start()
    assert acquired.wait(timeout=2.0)

    try:
        with pytest.raises((TimeoutError, OSError, Exception)), cache._locked(timeout=0.15):
            pass
    finally:
        release.set()
        t.join(timeout=3.0)

    src = tmp_path / "after_lock.bin"
    src.write_bytes(b"unlocked")
    assert cache.store(hashlib.sha256(b"unlocked").hexdigest(), src) is True


# ---------------------------------------------------------------------------
# F15 — Wan 2.1/2.2 Diffusers Engine Boundaries (7 Tests)
# ---------------------------------------------------------------------------


def test_f15_mac_8g_lite_gracefully_gates_wan_diffusers(
    mac_8g_lite_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = isolated_workspace
    _apply_hw_profile(monkeypatch, mac_8g_lite_profile)
    _install_fake_wan_stack(monkeypatch, vram_gb=8.0, bf16=False, cuda_available=False)

    router_mod = _imp("local_runners.router")
    wan_mod = _imp("local_runners.wan_diffusers_runner")

    with pytest.raises(RuntimeError):
        router_mod.select_runner("video", model_id="wan2.2-ti2v-5b", profile=mac_8g_lite_profile)

    mac_out = tmp_path / "mac_gated.mp4"
    try:
        res = wan_mod.WanDiffusersRunner().run(
            {"operation": "text_to_video", "prompt": "test", "profile": mac_8g_lite_profile, "output_path": str(mac_out)}
        )
        assert res.get("ok") is False and bool(res.get("error"))
    except RuntimeError as exc:
        assert str(exc).strip() != ""
    assert not mac_out.exists()


def test_f15_vae_geometry_snapping_and_invalid_frame_boundaries(
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

    out = tmp_path / "snapped.mp4"
    res = runner.run(
        {
            "operation": "text_to_video",
            "model_variant": "wan2.2-ti2v-5b",
            "prompt": "geometry snap check",
            "width": 700,
            "height": 500,
            "num_frames": 19,
            "output_path": str(out),
            "profile": full_48g_profile,
        }
    )
    assert res.get("ok", True) is not False and not res.get("error")
    call_kw = state["calls"][0]["kwargs"]
    assert call_kw["width"] % 32 == 0 and call_kw["height"] % 32 == 0
    assert (int(call_kw["num_frames"]) - 1) % 4 == 0
    assert int(call_kw["num_frames"]) == 17

    for bad_frames in (0, -5):
        bad_out = tmp_path / f"bad_{bad_frames}.mp4"
        try:
            bad_res = runner.run(
                {
                    "operation": "text_to_video",
                    "prompt": "bad frames",
                    "num_frames": bad_frames,
                    "output_path": str(bad_out),
                    "profile": full_48g_profile,
                }
            )
            assert bad_res.get("ok") is False or bool(bad_res.get("error"))
        except ValueError:
            pass
        assert not bad_out.exists()


def test_f15_non_chainable_ops_clamp_over_5s_and_reject_unsupported_variant_ops(
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

    start_png = tmp_path / "s.png"
    end_png = tmp_path / "e.png"
    pil_image.new("RGB", (64, 64), (10, 20, 30)).save(start_png)
    pil_image.new("RGB", (64, 64), (30, 20, 10)).save(end_png)

    runner = wan_mod.WanDiffusersRunner()
    flf_out = tmp_path / "flf_clamped.mp4"
    res_flf = runner.run(
        {
            "operation": "first_last_frame",
            "prompt": "long transition request",
            "reference_image_path": str(start_png),
            "last_image_path": str(end_png),
            "duration_seconds": 30,
            "fps": 24,
            "output_path": str(flf_out),
            "profile": full_48g_profile,
        }
    )
    assert res_flf.get("ok", True) is not False and not res_flf.get("error")
    assert len(state["calls"]) == 1
    assert int(state["calls"][0]["kwargs"]["num_frames"]) <= 121

    loads_before = len(state["loads"])
    try:
        res_unsup = runner.run(
            {
                "operation": "image_to_video",
                "model_variant": "wan2.1-1.3b",
                "prompt": "unsupported i2v on 1.3b",
                "reference_image_path": str(start_png),
                "output_path": str(tmp_path / "unsup.mp4"),
                "profile": full_48g_profile,
            }
        )
        assert res_unsup.get("ok") is False or bool(res_unsup.get("error"))
    except ValueError:
        pass
    assert len(state["loads"]) == loads_before

    try:
        res_empty_prompt = runner.run(
            {
                "operation": "text_to_video",
                "prompt": "",
                "output_path": str(tmp_path / "empty_prompt.mp4"),
                "profile": full_48g_profile,
            }
        )
        assert res_empty_prompt.get("ok") is False or bool(res_empty_prompt.get("error"))
    except ValueError:
        pass


def test_f15_vram_quantization_boundaries_bf16_int8_int4_and_sequential_offload(
    isolated_workspace: IsolatedWorkspace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = isolated_workspace
    wan_mod = _imp("local_runners.wan_diffusers_runner")

    cases = [
        (48.0, "bf16", "model", False),
        (18.5, "int8", "model", True),
        (17.0, "int8", "sequential", True),
        (10.0, "int4", "sequential", True),
    ]
    for vram_gb, exp_prec, exp_offload, expect_quant in cases:
        free_fn = getattr(wan_mod, "free_wan_pipelines", None)
        if callable(free_fn):
            free_fn()
        state = _install_fake_wan_stack(monkeypatch, vram_gb=vram_gb, bf16=True, cuda_available=True)
        prof = {
            "platform": "win32",
            "backend": "cuda",
            "name": "Test CUDA GPU",
            "vram_gb": vram_gb,
            "ram_gb": 64.0,
            "compute_cap": "12.0",
            "is_blackwell": True,
            "tier": "full_48g" if vram_gb >= 40 else "standard_gpu",
            "supports_local_video": True,
            "supports_local_images": True,
            "default_image_backend": "comfyui",
            "default_video_backend": "comfyui",
            "legacy_cloud": False,
        }
        _apply_hw_profile(monkeypatch, prof)
        out = tmp_path / f"vram_{vram_gb}.mp4"
        res = wan_mod.WanDiffusersRunner().run(
            {
                "operation": "text_to_video",
                "model_variant": "wan2.1-14b",
                "prompt": "precision test",
                "precision": "auto",
                "offload_mode": "auto",
                "num_frames": 9,
                "output_path": str(out),
                "profile": prof,
            }
        )
        assert res.get("ok", True) is not False and not res.get("error")
        assert res.get("precision") == exp_prec
        assert res.get("offload_mode") == exp_offload
        assert bool(state["quant_configs"]) is expect_quant


def test_f15_cuda_oom_and_nvml_driver_mismatch_actionable_diagnostics(
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = isolated_workspace
    _apply_hw_profile(monkeypatch, full_48g_profile)
    wan_mod = _imp("local_runners.wan_diffusers_runner")

    for err_msg, keywords in (
        ("CUDA out of memory. Tried to allocate 2.00 GiB", ("oom", "memory", "offload", "sequential", "precision", "int4", "int8")),
        ("NVML_SUCCESS == DriverAPI::get()->nvmlInit_v2_() INTERNAL ASSERT FAILED", ("nvml", "driver", "bf16", "cuda")),
    ):
        free_fn = getattr(wan_mod, "free_wan_pipelines", None)
        if callable(free_fn):
            free_fn()
        state = _install_fake_wan_stack(monkeypatch, vram_gb=48.0, call_exception=RuntimeError(err_msg))
        caught = ""
        try:
            res = wan_mod.WanDiffusersRunner().run(
                {
                    "operation": "text_to_video",
                    "prompt": "trigger error",
                    "num_frames": 9,
                    "output_path": str(tmp_path / "err.mp4"),
                    "profile": full_48g_profile,
                }
            )
            assert res.get("ok") is False or bool(res.get("error"))
            caught = str(res.get("error") or "")
        except RuntimeError as exc:
            caught = str(exc)
        low = caught.lower()
        assert any(kw in low for kw in keywords)
        assert state["empty_cache_calls"] >= 1


def test_f15_moe_guidance_scale_2_gating_and_transformer_2_quantization(
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

    runner.run(
        {
            "operation": "text_to_video",
            "model_variant": "wan2.2-ti2v-5b",
            "prompt": "dense 5b",
            "guidance_scale_2": 3.0,
            "num_frames": 9,
            "output_path": str(tmp_path / "dense.mp4"),
            "profile": full_48g_profile,
        }
    )
    assert "guidance_scale_2" not in state["calls"][-1]["kwargs"]

    runner.run(
        {
            "operation": "text_to_video",
            "model_variant": "wan2.2-t2v-a14b",
            "prompt": "moe a14b",
            "precision": "int4",
            "guidance_scale_2": 3.0,
            "num_frames": 9,
            "output_path": str(tmp_path / "moe.mp4"),
            "profile": full_48g_profile,
        }
    )
    assert state["calls"][-1]["kwargs"].get("guidance_scale_2") == pytest.approx(3.0)
    subfolders = {item["kwargs"].get("subfolder") for item in state["transformer_loads"]}
    assert "transformer" in subfolders and "transformer_2" in subfolders


def test_f15_cancel_aborts_multi_segment_chain_and_releases_pipeline(
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

    def _on_prog(_ev: dict[str, Any]) -> None:
        if len(state["calls"]) >= 1:
            runner.cancel()

    out = tmp_path / "cancelled.mp4"
    try:
        res = runner.run(
            {
                "operation": "text_to_video",
                "prompt": "cancel mid chain",
                "duration_seconds": 15,
                "fps": 24,
                "segment_frames": 81,
                "output_path": str(out),
                "profile": full_48g_profile,
            },
            on_progress=_on_prog,
        )
        assert res.get("ok") is False or res.get("cancelled") is True or bool(res.get("error"))
    except RuntimeError:
        pass
    assert len(state["calls"]) < 4


# ---------------------------------------------------------------------------
# F16 — Multi-Runtime Composers & 3D/SVG Boundaries (7 Tests)
# ---------------------------------------------------------------------------


def test_f16_missing_binaries_report_unavailable_and_forbid_silent_fallback(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    empty_bin = tmp_path / "empty_bin"
    empty_bin.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PATH", str(empty_bin))
    monkeypatch.delenv("BLENDER_PATH", raising=False)

    status = live_studio_server.get("/api/composers/status")
    assert status.status == 200
    body = status.json()
    runtimes = body.get("runtimes") if isinstance(body.get("runtimes"), dict) else body
    for rt in ("ffmpeg", "remotion", "hyperframes", "blender"):
        entry = runtimes[rt]
        avail = entry if isinstance(entry, bool) else bool(entry.get("available"))
        assert avail is False

    for rt in ("blender", "hyperframes", "remotion"):
        out = tmp_path / f"no_fallback_{rt}.mp4"
        resp = live_studio_server.post(
            "/api/composers/render",
            {"runtime": rt, "output_path": str(out), "world_spec": {"seed": 1}, "cuts": []},
        )
        assert resp.status >= 400 or resp.json().get("ok") is False
        assert not out.exists()


def test_f16_node_version_below_22_marks_hyperframes_unavailable(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    log_path = tmp_path / "old_node.jsonl"
    bin_dir = tmp_path / "bin"
    _make_cli_shim(bin_dir, "node", log_path, stdout_text="v20.11.0\n")
    _make_cli_shim(bin_dir, "npx", log_path, stdout_text='{"ok": true}\n')
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    status = live_studio_server.get("/api/composers/status")
    assert status.status == 200
    body = status.json()
    runtimes = body.get("runtimes") if isinstance(body.get("runtimes"), dict) else body
    hf_entry = runtimes["hyperframes"]
    hf_avail = hf_entry if isinstance(hf_entry, bool) else bool(hf_entry.get("available"))
    assert hf_avail is False

    out = tmp_path / "hf_old_node.mp4"
    resp = live_studio_server.post(
        "/api/composers/render",
        {"runtime": "hyperframes", "workspace_path": str(tmp_path / "hf_ws"), "output_path": str(out)},
    )
    assert resp.status >= 400 or resp.json().get("ok") is False
    assert not out.exists()


def test_f16_remotion_missing_node_modules_reports_install_hint_not_available(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tmp_composer = tmp_path / "remotion_no_nm"
    shutil.copytree(Path(__file__).resolve().parents[2] / "remotion-composer", tmp_composer)
    nm = tmp_composer / "node_modules"
    if nm.exists():
        shutil.rmtree(nm)
    monkeypatch.setenv("REMOTION_COMPOSER_DIR", str(tmp_composer))

    bin_dir = tmp_path / "bin"
    _make_cli_shim(bin_dir, "npx", tmp_path / "npx.jsonl")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    status = live_studio_server.get("/api/composers/status")
    assert status.status == 200
    body = status.json()
    runtimes = body.get("runtimes") if isinstance(body.get("runtimes"), dict) else body
    rem = runtimes["remotion"]
    rem_avail = rem if isinstance(rem, bool) else bool(rem.get("available"))
    assert rem_avail is False

    resp = live_studio_server.post(
        "/api/composers/render",
        {"runtime": "remotion", "composer_dir": str(tmp_composer), "output_path": str(tmp_path / "rem.mp4"), "cuts": []},
    )
    assert resp.status >= 400 or resp.json().get("ok") is False


def test_f16_unknown_runtime_and_missing_required_inputs_return_400(
    live_studio_server: StudioHarness,
) -> None:
    r_unknown = live_studio_server.post("/api/composers/render", {"runtime": "nonexistent_engine"})
    assert 400 <= r_unknown.status < 500
    assert "error" in r_unknown.json()

    r_empty_cuts = live_studio_server.post("/api/composers/render", {"runtime": "ffmpeg", "cuts": []})
    assert 400 <= r_empty_cuts.status < 500
    assert "error" in r_empty_cuts.json()

    r_blender_missing = live_studio_server.post("/api/composers/render", {"runtime": "blender", "operation": "render_still"})
    assert 400 <= r_blender_missing.status < 500
    assert "error" in r_blender_missing.json()


def test_f16_subprocess_shell_false_safety_with_metacharacters_in_paths(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "meta_argv.jsonl"
    bin_dir = tmp_path / "bin"
    shim = _make_cli_shim(bin_dir, "blender", log_path, stdout_text="OPENMONTAGE_BLENDER=4.5.10\n", write_png_on_render=True)
    monkeypatch.setenv("BLENDER_PATH", str(shim))

    pwned = tmp_path / "pwned.txt"
    meta_dir = tmp_path / "dir with spaces"
    meta_dir.mkdir(parents=True, exist_ok=True)
    out_png = meta_dir / f"out;touch {pwned}&$(id).png"
    blend_path = meta_dir / "world.blend"

    resp = live_studio_server.post(
        "/api/composers/render",
        {
            "runtime": "blender",
            "operation": "render_still",
            "world_spec": {"seed": 7},
            "output_path": str(out_png),
            "blend_path": str(blend_path),
        },
    )
    assert resp.status == 200
    assert not pwned.exists()
    calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(str(out_png) in c["argv"] for c in calls)


def test_f16_blender_resume_skips_completed_frames_and_nonzero_exit_propagates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "resume_argv.jsonl"
    bin_dir = tmp_path / "bin"
    shim = _make_cli_shim(bin_dir, "blender", log_path, stdout_text="OPENMONTAGE_BLENDER=4.5.10\n")
    monkeypatch.setenv("BLENDER_PATH", str(shim))

    mod = _imp("composers.blender_world_runner")

    def _exec(payload: dict[str, Any]) -> dict[str, Any]:
        fn = getattr(mod, "run_blender", None) or getattr(mod, "run", None)
        if callable(fn):
            raw = fn(payload)
        else:
            cls = getattr(mod, "BlenderWorldRunner", None) or mod.BlenderWorld
            raw = cls().execute(payload)
        return _normalize_tool_output(raw)

    seq_dir = tmp_path / "seq"
    seq_dir.mkdir(parents=True, exist_ok=True)
    for idx in (1, 2):
        (seq_dir / f"frame_{idx:04d}.png").write_bytes(MINIMAL_PNG)

    prefix = str(seq_dir / "frame_")
    res_resume = _exec(
        {
            "operation": "render_animation",
            "world_spec": {"seed": 9},
            "output_path": prefix,
            "blend_path": str(tmp_path / "anim.blend"),
            "start_frame": 1,
            "end_frame": 5,
            "resume": True,
        }
    )
    assert res_resume.get("success", True) is True
    calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any("--start-frame" in c["argv"] and c["argv"][c["argv"].index("--start-frame") + 1] == "3" for c in calls)

    for idx in (3, 4, 5):
        (seq_dir / f"frame_{idx:04d}.png").write_bytes(MINIMAL_PNG)
    calls_before = len(calls)
    res_done = _exec(
        {
            "operation": "render_animation",
            "world_spec": {"seed": 9},
            "output_path": prefix,
            "blend_path": str(tmp_path / "anim.blend"),
            "start_frame": 1,
            "end_frame": 5,
            "resume": True,
        }
    )
    assert res_done.get("already_complete") is True
    calls_after = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(calls_after) == calls_before

    fail_shim = _make_cli_shim(bin_dir, "blender", log_path, exit_code=1, stderr_text="Eevee shader compile error\n")
    monkeypatch.setenv("BLENDER_PATH", str(fail_shim))
    res_fail = _exec(
        {
            "operation": "render_still",
            "world_spec": {"seed": 9},
            "output_path": str(tmp_path / "fail.png"),
            "blend_path": str(tmp_path / "fail.blend"),
        }
    )
    assert res_fail.get("success") is False or bool(res_fail.get("error"))
    assert "Eevee shader compile error" in str(res_fail.get("error") or "")


def test_f16_compose_routes_enforce_auth_and_host_origin_checks(
    live_studio_server: StudioHarness,
) -> None:
    r_no_tok = live_studio_server.request("GET", "/api/composers/status", auth=False)
    assert r_no_tok.status == 403

    r_bad_origin = live_studio_server.request(
        "POST",
        "/api/composers/render",
        json_body={"runtime": "ffmpeg", "cuts": []},
        origin="https://evil.example",
    )
    assert r_bad_origin.status == 403
