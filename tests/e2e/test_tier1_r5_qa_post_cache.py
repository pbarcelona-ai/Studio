"""Tier 1 E2E Feature Coverage for R5.1 (F12 QA Gate, F13 Post Tools, F14 Asset Cache)."""
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
import threading
import time
from typing import Any
import wave

import pytest

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
        cur_path = str(Path(exe).parent)
        monkeypatch.setenv("PATH", f"{cur_path}{os.pathsep}{os.environ.get('PATH', '')}")
    return exe


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


def _make_png(
    path: Path,
    *,
    width: int = 160,
    height: int = 120,
    color: tuple[int, int, int] = (40, 120, 220),
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pil_image = importlib.import_module("PIL.Image")
    img = pil_image.new("RGB", (width, height), color)
    img.save(path, format="PNG")
    return path


def _make_test_mp4(
    path: Path,
    *,
    width: int = 320,
    height: int = 240,
    duration_s: float = 3.0,
    fps: int = 12,
    bg_expr: str | None = None,
    vf: str | None = None,
    audio_expr: str | None = "0.3*sin(2*PI*440*t)",
    with_audio: bool = True,
    sar: str | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg_bin()
    v_input = bg_expr or f"testsrc2=size={width}x{height}:rate={fps}:duration={duration_s}"
    cmd: list[str] = [ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", v_input]
    if with_audio:
        a_expr = audio_expr if audio_expr is not None else "0.3*sin(2*PI*440*t)"
        cmd.extend(["-f", "lavfi", "-i", f"aevalsrc={a_expr}:s=48000:d={duration_s}"])
    vf_parts: list[str] = []
    if vf:
        vf_parts.append(vf)
    if sar:
        vf_parts.append(f"setsar={sar}")
    if vf_parts:
        cmd.extend(["-vf", ",".join(vf_parts)])
    cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p"])
    if with_audio:
        cmd.extend(["-c:a", "aac", "-b:a", "96k", "-shortest"])
    else:
        cmd.append("-an")
    cmd.append(str(path))
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
    return path


def _make_silence_regions_mp4(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg_bin()
    filter_complex = (
        "color=c=red:s=64x64:r=25:d=1[v0];"
        "color=c=green:s=64x64:r=25:d=1[v1];"
        "color=c=blue:s=64x64:r=25:d=1[v2];"
        "[v0][v1][v2]concat=n=3:v=1:a=0[v];"
        "aevalsrc=0.4*sin(2*PI*440*t):s=48000:d=1[a0];"
        "aevalsrc=0:s=48000:d=1[a1];"
        "aevalsrc=0.4*sin(2*PI*440*t):s=48000:d=1[a2];"
        "[a0][a1][a2]concat=n=3:v=0:a=1[a]"
    )
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-y",
        "-filter_complex",
        filter_complex,
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
        "-b:a",
        "96k",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
    return path


def _make_face_zone_mp4(path: Path, *, duration_s: float = 2.0) -> Path:
    vf = "drawbox=x=0:y=0:w=160:h=180:color=blue:t=fill,drawbox=x=220:y=40:w=60:h=60:color=red:t=fill"
    return _make_test_mp4(
        path,
        width=320,
        height=180,
        duration_s=duration_s,
        fps=12,
        bg_expr=f"color=c=black:s=320x180:r=12:d={duration_s}",
        vf=vf,
        with_audio=True,
    )


def _probe_video_ffmpeg(path: Path) -> dict[str, Any]:
    ffmpeg = _ffmpeg_bin()
    proc = subprocess.run([ffmpeg, "-i", str(path)], capture_output=True, text=True, timeout=15)
    stderr = proc.stderr or ""
    width = 0
    height = 0
    fps = 0.0
    duration = 0.0
    sar = ""
    dar = ""
    has_audio = "Audio:" in stderr

    m_res = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", stderr)
    if m_res:
        width = int(m_res.group(1))
        height = int(m_res.group(2))
    m_sar = re.search(r"SAR\s+(\d+:\d+)\s+DAR\s+(\d+:\d+)", stderr)
    if m_sar:
        sar = m_sar.group(1)
        dar = m_sar.group(2)
    m_fps = re.search(r"([\d.]+)\s+fps", stderr)
    if m_fps:
        fps = float(m_fps.group(1))
    m_dur = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", stderr)
    if m_dur:
        duration = int(m_dur.group(1)) * 3600 + int(m_dur.group(2)) * 60 + float(m_dur.group(3))

    cv2 = importlib.import_module("cv2")
    cap = cv2.VideoCapture(str(path))
    try:
        if cap.isOpened():
            if width == 0:
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            if height == 0:
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if fps == 0.0:
                fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if duration == 0.0 and fps > 0 and frame_count > 0:
                duration = frame_count / fps
    finally:
        cap.release()

    return {
        "width": width,
        "height": height,
        "fps": fps,
        "duration": duration,
        "has_audio": has_audio,
        "sar": sar,
        "dar": dar,
        "stderr": stderr,
    }


def _video_color_regions(path: Path) -> list[tuple[str, int]]:
    ffmpeg = _ffmpeg_bin()
    proc = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True,
        capture_output=True,
        timeout=20,
    )
    raw = proc.stdout
    regions: list[tuple[str, int]] = []
    for i in range(0, len(raw) - 2, 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        if r > g + 30 and r > b + 30:
            label = "R"
        elif g > r + 30 and g > b + 30:
            label = "G"
        elif b > r + 30 and b > g + 30:
            label = "B"
        else:
            label = "?"
        if regions and regions[-1][0] == label:
            regions[-1] = (label, regions[-1][1] + 1)
        else:
            regions.append((label, 1))
    return regions


def _audio_rms(path: Path, start_s: float) -> float:
    ffmpeg = _ffmpeg_bin()
    proc = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-ss",
            str(start_s),
            "-i",
            str(path),
            "-t",
            "0.04",
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-",
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    raw = proc.stdout
    n = len(raw) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", raw[: n * 2])
    return math.sqrt(sum(s * s for s in samples) / n)


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


def _call_slideshow_risk(
    scenes: list[dict[str, Any]],
    *,
    edit_decisions: dict[str, Any] | None = None,
    renderer_family: str | None = None,
    render_runtime: str | None = None,
) -> dict[str, Any]:
    mod = _imp("qa.slideshow_risk")
    fn = getattr(mod, "score_slideshow_risk", None) or getattr(mod, "score", None)
    assert callable(fn), "qa.slideshow_risk must define score_slideshow_risk()"
    res = fn(
        scenes,
        edit_decisions=edit_decisions,
        renderer_family=renderer_family,
        render_runtime=render_runtime,
    )
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

    cls = getattr(mod, "CompositionValidator", None)
    assert cls is not None, "qa.composition_validator must expose validate_composition or CompositionValidator"
    return _normalize_tool_output(cls().execute(payload))


def _call_visual_qa(inputs: dict[str, Any]) -> dict[str, Any]:
    mod = _imp("qa.visual_qa")
    op = str(inputs.get("operation", "probe"))
    for fn_name in ("run_visual_qa", "visual_qa", op):
        fn = getattr(mod, fn_name, None)
        if callable(fn):
            sig = inspect.signature(fn)
            params = list(sig.parameters.keys())
            if params == ["inputs"] or params == ["payload"] or params == ["spec"]:
                return _normalize_tool_output(fn(inputs))
            if "operation" in sig.parameters:
                return _normalize_tool_output(fn(**{k: v for k, v in inputs.items() if k in sig.parameters}))
            filtered = {k: v for k, v in inputs.items() if k in sig.parameters and k != "operation"}
            if len(params) >= 1 and params[0] in {"input_path", "video_path", "path"} and "input_path" in inputs:
                key0 = params[0]
                rest = {k: v for k, v in filtered.items() if k != key0}
                return _normalize_tool_output(fn(inputs["input_path"], **rest))
            return _normalize_tool_output(fn(**filtered))

    cls = getattr(mod, "VisualQA", None)
    assert cls is not None, "qa.visual_qa must expose run_visual_qa or VisualQA"
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
            kwargs = {k: v for k, v in inputs.items() if k in sig.parameters}
            return _normalize_tool_output(fn(**kwargs))
    cls = getattr(mod, "SilenceCutter", None)
    assert cls is not None, "post_tools must expose silence_cutter or SilenceCutter"
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
            kwargs = {k: v for k, v in inputs.items() if k in sig.parameters}
            return _normalize_tool_output(fn(**kwargs))
    cls = getattr(mod, "AutoReframe", None)
    assert cls is not None, "post_tools must expose auto_reframe or AutoReframe"
    return _normalize_tool_output(cls().execute(inputs))


def _compute_cache_key(
    mod: Any,
    cache: Any,
    *,
    tool_name: str,
    tool_version: str,
    inputs: dict[str, Any],
    output_path: str | None = None,
) -> str:
    payload = dict(inputs)
    if output_path is not None:
        payload["output_path"] = output_path

    candidates: list[Any] = []
    for owner in (cache, mod):
        for attr in ("cache_key", "compute_cache_key", "make_cache_key", "content_key", "compute_key"):
            fn = getattr(owner, attr, None)
            if callable(fn):
                candidates.append(fn)

    assert candidates, "local_runners.asset_cache must expose a cache-key helper function or method"
    fn = candidates[0]
    sig = inspect.signature(fn)
    params = list(sig.parameters.keys())
    if "inputs" in params:
        kwargs: dict[str, Any] = {"inputs": payload}
        if "tool_name" in params:
            kwargs["tool_name"] = tool_name
        if "tool_version" in params:
            kwargs["tool_version"] = tool_version
        if "version" in params:
            kwargs["version"] = tool_version
        if "output_path" in params and output_path is not None:
            kwargs["output_path"] = output_path
        res = fn(**kwargs)
    elif len(params) >= 3:
        res = fn(tool_name, tool_version, payload)
    else:
        res = fn(payload)
    return str(res)


def _is_valid_result(res: dict[str, Any]) -> bool:
    if "valid" in res:
        return bool(res["valid"])
    if "passed" in res:
        return bool(res["passed"])
    if "success" in res:
        return bool(res["success"]) and not res.get("errors")
    return not res.get("errors")


# ---------------------------------------------------------------------------
# F12 — Pre-Render QA Gate (scripts/qa/ & POST /api/qa/check) — 6 Tests
# ---------------------------------------------------------------------------


def test_f12_slideshow_risk_strong_cinematic_plan() -> None:
    scenes: list[dict[str, Any]] = [
        {
            "type": "establishing",
            "description": "Wide dusk aerial across rain-soaked neon harbor docks",
            "shot_intent": "Establish scale and isolation of the coastal city",
            "narrative_role": "opening_hook",
            "shot_language": {"shot_size": "extreme_wide", "camera_movement": "dolly_in", "lighting_key": "low_key"},
            "hero_moment": True,
        },
        {
            "type": "action",
            "description": "Courier weaves through crowded alley market lanterns",
            "shot_intent": "Convey urgency and kinetic pursuit",
            "narrative_role": "rising_action",
            "shot_language": {"shot_size": "medium", "camera_movement": "tracking", "lighting_key": "motivated_neon"},
        },
        {
            "type": "dialogue",
            "description": "Two informants exchange an encrypted drive under rain awning",
            "shot_intent": "Reveal distrust between allies",
            "narrative_role": "plot_turn",
            "shot_language": {"shot_size": "close_up", "camera_movement": "slow_push", "lighting_key": "chiaroscuro"},
        },
        {
            "type": "insert",
            "description": "Macro view of relay lock clicking green inside brass casing",
            "shot_intent": "Confirm payload activation before deadline",
            "narrative_role": "escalation",
            "shot_language": {"shot_size": "extreme_close_up", "camera_movement": "rack_focus", "lighting_key": "high_contrast"},
        },
        {
            "type": "climax",
            "description": "Searchlight sweeps freight deck as protagonist leaps onto barge",
            "shot_intent": "Deliver decisive escape beat",
            "narrative_role": "climax",
            "shot_language": {"shot_size": "wide", "camera_movement": "crane_up", "lighting_key": "rim_light"},
        },
    ]

    result = _call_slideshow_risk(scenes, renderer_family="cinematic-trailer", render_runtime="ffmpeg")
    assert result["verdict"] == "strong"
    assert float(result["average"]) < 2.0
    assert result.get("render_runtime") == "ffmpeg"

    expected_dims = {
        "repetition",
        "decorative_visuals",
        "weak_motion",
        "weak_shot_intent",
        "typography_overreliance",
        "unsupported_cinematic_claims",
    }
    dims = result["dimensions"]
    assert set(dims.keys()) == expected_dims
    for name in expected_dims:
        entry = dims[name]
        assert 0.0 <= float(entry["score"]) <= 5.0
        assert isinstance(entry["reason"], str) and len(entry["reason"].strip()) > 0


def test_f12_composition_validator_passes_valid_cuts_and_media(
    isolated_workspace: IsolatedWorkspace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    assets_dir = isolated_workspace.root / "qa_assets"
    clip_a = _make_test_mp4(assets_dir / "clip_a.mp4", duration_s=2.0, with_audio=True)
    bg_png = _make_png(assets_dir / "bg.png")
    narration = _make_wav(assets_dir / "narration.wav", duration_s=3.0)
    music = _make_wav(assets_dir / "music.wav", duration_s=5.0, freq_hz=220.0)

    comp_path = tmp_path / "composition.json"
    comp_path.write_text(
        json.dumps(
            {
                "render_runtime": "ffmpeg",
                "cuts": [
                    {"source": clip_a.name, "in_seconds": 0.0, "out_seconds": 2.0, "background": bg_png.name},
                    {"source": str(clip_a), "in_seconds": 2.0, "out_seconds": 4.0},
                ],
                "audio": {
                    "narration": {"source": narration.name, "duration_seconds": 3.0},
                    "music": {"source": music.name, "duration_seconds": 5.0},
                },
            }
        ),
        encoding="utf-8",
    )

    result = _call_composition_validator(comp_path, assets_root=assets_dir, render_runtime="ffmpeg")
    assert _is_valid_result(result) is True
    assert list(result.get("errors") or []) == []


def test_f12_visual_qa_review_probe_and_audio_levels_real_media(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    mp4 = _make_test_mp4(tmp_path / "sample.mp4", width=320, height=240, duration_s=3.0, fps=12, audio_expr="0.3*sin(2*PI*440*t)", with_audio=True)
    frames_dir = tmp_path / "review_out"

    review_res = _call_visual_qa({"operation": "review", "input_path": str(mp4), "timestamps": [0.5, 1.5, 2.5], "output_dir": str(frames_dir)})
    extracted = review_res.get("frames") or review_res.get("frame_paths") or review_res.get("artifacts") or sorted(str(p) for p in frames_dir.glob("frame_*"))
    assert len(extracted) == 3
    pil_image = importlib.import_module("PIL.Image")
    for frame_item in extracted:
        fpath = Path(frame_item["path"] if isinstance(frame_item, dict) else str(frame_item))
        assert fpath.is_file()
        with pil_image.open(fpath) as img:
            assert img.size == (320, 240)

    probe_res = _call_visual_qa(
        {
            "operation": "probe",
            "input_path": str(mp4),
            "expected": {"width": 320, "height": 240, "min_duration": 2.7, "max_duration": 3.3, "has_audio": True},
        }
    )
    assert int(probe_res["width"]) == 320
    assert int(probe_res["height"]) == 240
    assert bool(probe_res["has_audio"]) is True
    assert 2.7 <= float(probe_res["duration"]) <= 3.3
    assert bool(probe_res.get("validation_passed", True)) is True

    audio_res = _call_visual_qa({"operation": "audio_levels", "input_path": str(mp4), "timestamps": [1.0]})
    mean_db = float(audio_res["mean_volume_db"])
    max_db = float(audio_res["max_volume_db"])
    assert -40.0 < mean_db < -1.0
    assert max_db < -0.5


def test_f12_visual_qa_clean_video_no_black_frames_or_clipping(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    mp4 = _make_test_mp4(tmp_path / "bright.mp4", width=320, height=240, duration_s=2.0, fps=12, audio_expr="0.2*sin(2*PI*440*t)", with_audio=True)
    frames_dir = tmp_path / "clean_frames"

    review_res = _call_visual_qa({"operation": "review", "input_path": str(mp4), "timestamps": [0.4, 1.2], "output_dir": str(frames_dir)})
    audio_res = _call_visual_qa({"operation": "audio_levels", "input_path": str(mp4), "timestamps": [1.0]})

    frames = review_res.get("frames") or review_res.get("frame_paths") or sorted(str(p) for p in frames_dir.glob("frame_*"))
    assert len(frames) >= 2
    for f in frames:
        fpath = Path(f["path"] if isinstance(f, dict) else str(f))
        assert fpath.stat().st_size >= 2000

    if "black_frames_detected" in review_res:
        assert bool(review_res["black_frames_detected"]) is False
    assert float(audio_res["mean_volume_db"]) >= -60.0
    assert float(audio_res["max_volume_db"]) < -0.5
    if "unexpected_silence" in audio_res:
        assert bool(audio_res["unexpected_silence"]) is False
    if "clipping_detected" in audio_res:
        assert bool(audio_res["clipping_detected"]) is False


def test_f12_http_qa_check_route_valid_project_and_scenes(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    ws = live_studio_server.workspace
    proj_dir = ws.root / "projects" / "books" / "qa_ok"
    proj_dir.mkdir(parents=True, exist_ok=True)
    clip = _make_test_mp4(proj_dir / "shot_01.mp4", duration_s=2.0, with_audio=True)
    comp_path = proj_dir / "composition.json"
    comp_path.write_text(
        json.dumps({"render_runtime": "ffmpeg", "cuts": [{"source": str(clip), "in_seconds": 0.0, "out_seconds": 2.0}]}),
        encoding="utf-8",
    )

    scenes = [
        {
            "type": "establishing",
            "description": "Sunlit mountain pass overlooking valley",
            "shot_intent": "Set geography",
            "narrative_role": "opening",
            "shot_language": {"shot_size": "wide", "camera_movement": "dolly_in", "lighting_key": "natural"},
            "hero_moment": True,
        },
        {
            "type": "action",
            "description": "Traveler crosses suspension bridge in wind",
            "shot_intent": "Show tension",
            "narrative_role": "escalation",
            "shot_language": {"shot_size": "medium", "camera_movement": "tracking", "lighting_key": "overcast"},
        },
        {
            "type": "close",
            "description": "Compass needle spins beside gloved hand",
            "shot_intent": "Signal disorientation",
            "narrative_role": "turn",
            "shot_language": {"shot_size": "close_up", "camera_movement": "slow_push", "lighting_key": "side_lit"},
        },
    ]

    resp = live_studio_server.post(
        "/api/qa/check",
        {
            "project": "qa_ok",
            "scenes": scenes,
            "composition_path": str(comp_path),
            "render_runtime": "ffmpeg",
            "renderer_family": "cinematic-trailer",
        },
    )
    assert resp.status == 200
    body = resp.json()
    assert isinstance(body, dict)
    assert not body.get("error")
    if "verdict" in body:
        assert body["verdict"] in ("strong", "acceptable")
    if "slideshow_risk" in body and isinstance(body["slideshow_risk"], dict):
        assert body["slideshow_risk"].get("verdict") in ("strong", "acceptable")
    if "valid" in body:
        assert body["valid"] is True
    if "passed" in body:
        assert body["passed"] is True


def test_f12_http_qa_gate_allows_passing_render_or_export(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    clip = _make_test_mp4(tmp_path / "pass_clip.mp4", duration_s=1.5, with_audio=True)
    comp_path = tmp_path / "pass_comp.json"
    comp_path.write_text(
        json.dumps({"render_runtime": "ffmpeg", "cuts": [{"source": str(clip), "in_seconds": 0.0, "out_seconds": 1.5}]}),
        encoding="utf-8",
    )
    out_mp4 = tmp_path / "gated_out.mp4"

    scenes = [
        {
            "type": "establishing",
            "description": "Harbor dawn mist lifting off moored trawlers",
            "shot_intent": "Establish calm before storm",
            "narrative_role": "hook",
            "shot_language": {"shot_size": "wide", "camera_movement": "pan_right", "lighting_key": "golden_hour"},
            "hero_moment": True,
        },
        {
            "type": "action",
            "description": "Captain checks barometer inside wooden wheelhouse",
            "shot_intent": "Foreshadow drop in pressure",
            "narrative_role": "setup",
            "shot_language": {"shot_size": "medium", "camera_movement": "dolly_in", "lighting_key": "warm_tungsten"},
        },
        {
            "type": "insert",
            "description": "Chart table compass slides across wet mahogany",
            "shot_intent": "Highlight impending gale",
            "narrative_role": "climax",
            "shot_language": {"shot_size": "close_up", "camera_movement": "handheld", "lighting_key": "low_key"},
        },
    ]

    qa_resp = live_studio_server.post(
        "/api/qa/check",
        {"scenes": scenes, "composition_path": str(comp_path), "render_runtime": "ffmpeg"},
    )
    assert qa_resp.status == 200

    render_resp = live_studio_server.post(
        "/api/composers/render",
        {
            "runtime": "ffmpeg",
            "cuts": [{"source": str(clip), "in_seconds": 0.0, "out_seconds": 1.5}],
            "scenes": scenes,
            "composition_path": str(comp_path),
            "output_path": str(out_mp4),
        },
    )
    assert render_resp.status == 200
    assert out_mp4.is_file() and out_mp4.stat().st_size > 0


# ---------------------------------------------------------------------------
# F13 — Post-Processing (scripts/post_tools.py & /api/post/*) — 6 Tests
# ---------------------------------------------------------------------------


def test_f13_silence_cutter_mark_mode_coordinates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    src = _make_silence_regions_mp4(tmp_path / "regions.mp4")
    mark_json = tmp_path / "regions.silence.json"

    res = _call_silence_cutter(
        {
            "input_path": str(src),
            "output_path": str(mark_json),
            "mode": "mark",
            "min_silence_duration": 0.3,
            "padding_seconds": 0.08,
        }
    )
    assert mark_json.is_file()
    data = json.loads(mark_json.read_text(encoding="utf-8"))
    silences = res.get("silences") or data.get("silences") or []
    speech = res.get("speech_segments") or data.get("speech_segments") or []
    assert len(silences) == 1
    assert silences[0]["start"] == pytest.approx(1.0, abs=0.15)
    assert silences[0]["end"] == pytest.approx(2.0, abs=0.15)
    assert len(speech) == 2


def test_f13_silence_cutter_remove_mode_drops_silent_region(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    src = _make_silence_regions_mp4(tmp_path / "regions.mp4")
    out = tmp_path / "removed.mp4"

    _call_silence_cutter(
        {
            "input_path": str(src),
            "output_path": str(out),
            "mode": "remove",
            "min_silence_duration": 0.3,
            "padding_seconds": 0.0,
        }
    )
    assert out.is_file() and out.stat().st_size > 0
    probe = _probe_video_ffmpeg(out)
    assert probe["duration"] < 2.4
    assert probe["has_audio"] is True
    regions = [label for label, _ in _video_color_regions(out) if label in {"R", "G", "B"}]
    assert regions == ["R", "B"]


def test_f13_silence_cutter_speed_up_mode_preserves_regions_and_rms(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    src = _make_silence_regions_mp4(tmp_path / "regions.mp4")
    out = tmp_path / "sped.mp4"

    _call_silence_cutter(
        {
            "input_path": str(src),
            "output_path": str(out),
            "mode": "speed_up",
            "silence_speed_factor": 6.0,
            "min_silence_duration": 0.3,
            "padding_seconds": 0.08,
        }
    )
    assert out.is_file() and out.stat().st_size > 0
    probe = _probe_video_ffmpeg(out)
    assert 1.8 <= probe["duration"] <= 2.6
    regions = _video_color_regions(out)
    labels = [label for label, _ in regions if label in {"R", "G", "B"}]
    assert labels == ["R", "G", "B"]

    fps = probe["fps"] or 25.0
    r_count = regions[0][1]
    g_count = regions[1][1]
    r_mid = (r_count / 2.0) / fps
    g_mid = (r_count + g_count / 2.0) / fps
    b_mid = (r_count + g_count + regions[2][1] / 2.0) / fps

    assert _audio_rms(out, r_mid) > 500.0
    assert _audio_rms(out, g_mid) < 200.0
    assert _audio_rms(out, b_mid) > 500.0


def test_f13_auto_reframe_all_five_aspect_presets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    src = _make_test_mp4(tmp_path / "wide.mp4", width=320, height=180, duration_s=1.0, fps=12, with_audio=True)
    empty_faces = tmp_path / "no_faces.json"
    empty_faces.write_text("[]", encoding="utf-8")

    expected = {
        "portrait": (1080, 1920),
        "square": (1080, 1080),
        "landscape": (1920, 1080),
        "cinematic": (2560, 1080),
        "vertical_4_5": (1080, 1350),
    }
    for preset, (exp_w, exp_h) in expected.items():
        out = tmp_path / f"out_{preset}.mp4"
        _call_auto_reframe(
            {
                "input_path": str(src),
                "output_path": str(out),
                "target_aspect": preset,
                "face_tracking_json": str(empty_faces),
            }
        )
        assert out.is_file() and out.stat().st_size > 0
        probe = _probe_video_ffmpeg(out)
        assert (probe["width"], probe["height"]) == (exp_w, exp_h)
        assert probe["has_audio"] is True


def test_f13_auto_reframe_face_tracked_static_and_dynamic_sendcmd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    src = _make_face_zone_mp4(tmp_path / "face_zone.mp4", duration_s=2.0)

    static_faces = tmp_path / "static_face.json"
    static_faces.write_text(
        json.dumps(
            [
                {"timestamp": 0.0, "faces": [{"x": 0.69, "y": 0.22, "w": 0.18, "h": 0.33}]},
                {"timestamp": 1.0, "faces": [{"x": 0.69, "y": 0.22, "w": 0.18, "h": 0.33}]},
            ]
        ),
        encoding="utf-8",
    )
    out_static = tmp_path / "static_portrait.mp4"
    _call_auto_reframe(
        {
            "input_path": str(src),
            "output_path": str(out_static),
            "target_aspect": "portrait",
            "face_tracking_json": str(static_faces),
        }
    )
    assert out_static.is_file()
    probe_s = _probe_video_ffmpeg(out_static)
    assert (probe_s["width"], probe_s["height"]) == (1080, 1920)

    cv2 = importlib.import_module("cv2")
    cap = cv2.VideoCapture(str(out_static))
    try:
        ok, frame = cap.read()
        assert ok and frame is not None
        mean_bgr = frame.mean(axis=(0, 1))
        # Red target is on the right half (x=220..280) vs blue left half (x<160): red channel > blue channel
        assert float(mean_bgr[2]) > float(mean_bgr[0])
    finally:
        cap.release()

    moving_faces = tmp_path / "moving_faces.json"
    pts = [
        {"timestamp": i * 0.3, "faces": [{"x": 0.15 + i * 0.12, "y": 0.25, "w": 0.16, "h": 0.30}]}
        for i in range(6)
    ]
    moving_faces.write_text(json.dumps(pts), encoding="utf-8")
    out_dyn = tmp_path / "dynamic_portrait.mp4"
    _call_auto_reframe(
        {
            "input_path": str(src),
            "output_path": str(out_dyn),
            "target_aspect": "portrait",
            "face_tracking_json": str(moving_faces),
            "smoothing_window": 3,
        }
    )
    assert out_dyn.is_file() and out_dyn.stat().st_size > 0
    probe_d = _probe_video_ffmpeg(out_dyn)
    assert (probe_d["width"], probe_d["height"]) == (1080, 1920)
    assert not (tmp_path / ".reframe_tmp").exists()


def test_f13_http_post_silence_cut_and_auto_reframe_routes(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ensure_ffmpeg_on_path(monkeypatch)
    ws = live_studio_server.workspace
    proj_dir = ws.root / "projects" / "books" / "post_proj"
    proj_dir.mkdir(parents=True, exist_ok=True)
    src_regions = _make_silence_regions_mp4(proj_dir / "talk.mp4")
    cut_out = proj_dir / "talk_cut.mp4"
    reframe_out = proj_dir / "talk_portrait.mp4"

    r_cut = live_studio_server.post(
        "/api/post/silence-cut",
        {
            "input_path": str(src_regions),
            "output_path": str(cut_out),
            "mode": "remove",
            "min_silence_duration": 0.3,
            "padding_seconds": 0.0,
        },
    )
    assert r_cut.status == 200
    cut_json = r_cut.json()
    assert cut_out.is_file() and cut_out.stat().st_size > 0
    assert str(cut_out) in json.dumps(cut_json) or cut_out.name in json.dumps(cut_json)

    empty_faces = proj_dir / "faces.json"
    empty_faces.write_text("[]", encoding="utf-8")
    r_ref = live_studio_server.post(
        "/api/post/auto-reframe",
        {
            "input_path": str(cut_out),
            "output_path": str(reframe_out),
            "target_aspect": "portrait",
            "face_tracking_json": str(empty_faces),
        },
    )
    assert r_ref.status == 200
    assert reframe_out.is_file() and reframe_out.stat().st_size > 0
    probe = _probe_video_ffmpeg(reframe_out)
    assert (probe["width"], probe["height"]) == (1080, 1920)


# ---------------------------------------------------------------------------
# F14 — Content-Addressed Asset Cache (scripts/local_runners/asset_cache.py) — 6 Tests
# ---------------------------------------------------------------------------


def test_f14_cache_key_deterministic_and_content_addressed(tmp_path: Path) -> None:
    mod = _imp("local_runners.asset_cache")
    cache = mod.AssetCache(cache_dir=tmp_path / "cache")

    ref_img = tmp_path / "ref.bin"
    ref_img.write_bytes(b"frame-bytes-v1")

    base_inputs = {"prompt": "neon alleyway", "seed": 42, "ref_image": str(ref_img)}
    k1 = _compute_cache_key(
        mod,
        cache,
        tool_name="sd_cli",
        tool_version="1.0",
        inputs=base_inputs,
        output_path=str(tmp_path / "dir_a" / "out.png"),
    )
    k2 = _compute_cache_key(
        mod,
        cache,
        tool_name="sd_cli",
        tool_version="1.0",
        inputs=base_inputs,
        output_path=str(tmp_path / "dir_b" / "different_name.png"),
    )
    assert len(k1) == 64
    int(k1, 16)
    assert k1 == k2

    # Mutate file content at same path -> key must change
    ref_img.write_bytes(b"frame-bytes-v2-mutated")
    k_mut_file = _compute_cache_key(
        mod,
        cache,
        tool_name="sd_cli",
        tool_version="1.0",
        inputs=base_inputs,
        output_path=str(tmp_path / "dir_a" / "out.png"),
    )
    assert k_mut_file != k1

    # Change parameter or suffix -> key must change
    k_diff_seed = _compute_cache_key(
        mod,
        cache,
        tool_name="sd_cli",
        tool_version="1.0",
        inputs={**base_inputs, "seed": 99},
        output_path=str(tmp_path / "dir_a" / "out.png"),
    )
    k_diff_ext = _compute_cache_key(
        mod,
        cache,
        tool_name="sd_cli",
        tool_version="1.0",
        inputs=base_inputs,
        output_path=str(tmp_path / "dir_a" / "out.jpg"),
    )
    assert k_diff_seed != k_mut_file
    assert k_diff_ext != k_mut_file


def test_f14_store_and_try_restore_round_trip_with_stats(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    mod = _imp("local_runners.asset_cache")
    cache = mod.AssetCache(cache_dir=isolated_workspace.cache_dir / "c1")

    src = tmp_path / "gen.png"
    payload = b"PNG-SYNTHETIC-CONTENT-123456"
    src.write_bytes(payload)
    key = hashlib.sha256(payload).hexdigest()

    assert (
        cache.store(
            key,
            src,
            tool_name="wan_diffusers",
            tool_version="0.1.0",
            model="wan2.2-ti2v-5b",
            seed=42,
            cost_usd=0.05,
            data={"output": str(src), "k": "v"},
        )
        is True
    )

    dest = tmp_path / "restored" / "gen.png"
    restored = cache.try_restore(key, dest)
    assert restored is not None
    assert dest.read_bytes() == payload
    assert restored["model"] == "wan2.2-ti2v-5b"
    assert restored["seed"] == 42
    assert restored["cost_usd"] == pytest.approx(0.05)
    assert restored["data"] == {"output": str(src), "k": "v"}

    stats = cache.stats()
    assert stats["hits_this_session"] == 1
    assert stats["misses_this_session"] == 0
    assert stats["cost_saved_usd_this_session"] == pytest.approx(0.05)


def test_f14_copy2_immutability_no_hardlink_corruption(tmp_path: Path) -> None:
    mod = _imp("local_runners.asset_cache")
    cache = mod.AssetCache(cache_dir=tmp_path / "cache")

    src = tmp_path / "orig.bin"
    src.write_bytes(b"ORIGINAL")
    key = hashlib.sha256(b"ORIGINAL").hexdigest()
    assert cache.store(key, src, tool_name="t", tool_version="1") is True

    dest1 = tmp_path / "dest1.bin"
    assert cache.try_restore(key, dest1) is not None
    dest1.write_bytes(b"MUTATED")
    src.write_bytes(b"SRC_MUTATED")

    dest2 = tmp_path / "dest2.bin"
    assert cache.try_restore(key, dest2) is not None
    assert dest2.read_bytes() == b"ORIGINAL"
    blobs = [p for p in (tmp_path / "cache").glob(f"{key}*") if p.is_file()]
    assert len(blobs) == 1
    assert blobs[0].read_bytes() == b"ORIGINAL"


def test_f14_manifest_atomic_persistence_across_instances(tmp_path: Path) -> None:
    mod = _imp("local_runners.asset_cache")
    cache_dir = tmp_path / "persist_cache"
    cache1 = mod.AssetCache(cache_dir=cache_dir)

    f1 = tmp_path / "a.bin"
    f2 = tmp_path / "b.bin"
    f1.write_bytes(b"alpha-bytes")
    f2.write_bytes(b"beta-bytes")
    k1 = hashlib.sha256(b"alpha-bytes").hexdigest()
    k2 = hashlib.sha256(b"beta-bytes").hexdigest()

    assert cache1.store(k1, f1, tool_name="t", tool_version="1") is True
    assert cache1.store(k2, f2, tool_name="t", tool_version="1") is True

    manifest = cache_dir / "asset_manifest.jsonl"
    assert manifest.is_file()
    lines = [ln for ln in manifest.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    for ln in lines:
        parsed = json.loads(ln)
        assert "key" in parsed and "file_name" in parsed
    assert list(cache_dir.glob("*.tmp")) == []

    cache2 = mod.AssetCache(cache_dir=cache_dir)
    out1 = tmp_path / "out1.bin"
    out2 = tmp_path / "out2.bin"
    assert cache2.try_restore(k1, out1) is not None
    assert cache2.try_restore(k2, out2) is not None
    assert out1.read_bytes() == b"alpha-bytes"
    assert out2.read_bytes() == b"beta-bytes"


def test_f14_lru_eviction_updates_order_on_restore(tmp_path: Path) -> None:
    mod = _imp("local_runners.asset_cache")
    cache_dir = tmp_path / "lru_cache"
    cache = mod.AssetCache(cache_dir=cache_dir, max_total_bytes=25_000)

    f1 = tmp_path / "f1.bin"
    f2 = tmp_path / "f2.bin"
    f3 = tmp_path / "f3.bin"
    f1.write_bytes(b"1" * 10_000)
    f2.write_bytes(b"2" * 10_000)
    f3.write_bytes(b"3" * 10_000)
    k1 = hashlib.sha256(b"1" * 10_000).hexdigest()
    k2 = hashlib.sha256(b"2" * 10_000).hexdigest()
    k3 = hashlib.sha256(b"3" * 10_000).hexdigest()

    assert cache.store(k1, f1, tool_name="t", tool_version="1") is True
    time.sleep(0.02)
    assert cache.store(k2, f2, tool_name="t", tool_version="1") is True
    time.sleep(0.02)

    # Touch k1 so k2 becomes the least-recently-used entry
    assert cache.try_restore(k1, tmp_path / "touch1.bin") is not None
    time.sleep(0.02)
    assert cache.store(k3, f3, tool_name="t", tool_version="1") is True

    assert cache.try_restore(k2, tmp_path / "check_k2.bin") is None
    assert cache.try_restore(k1, tmp_path / "check_k1.bin") is not None
    assert cache.try_restore(k3, tmp_path / "check_k3.bin") is not None
    assert list(cache_dir.glob(f"{k2}*")) == []
    assert cache.stats()["evictions_this_session"] >= 1


def test_f14_concurrent_threads_serialize_safely(tmp_path: Path) -> None:
    mod = _imp("local_runners.asset_cache")
    cache_dir = tmp_path / "concurrent_cache"
    cache = mod.AssetCache(cache_dir=cache_dir)

    n_threads = 8
    barrier = threading.Barrier(n_threads)
    errors: list[BaseException] = []
    keys: list[str] = []

    for idx in range(n_threads):
        data = f"payload-{idx}".encode()
        keys.append(hashlib.sha256(data).hexdigest())

    def _worker(idx: int) -> None:
        try:
            src = tmp_path / f"src_{idx}.bin"
            dst = tmp_path / f"dst_{idx}.bin"
            src.write_bytes(f"payload-{idx}".encode())
            barrier.wait(timeout=5.0)
            ok = cache.store(keys[idx], src, tool_name="t", tool_version="1")
            assert ok is True
            hit = cache.try_restore(keys[idx], dst)
            assert hit is not None
            assert dst.read_bytes() == f"payload-{idx}".encode()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)
        assert not t.is_alive()

    assert errors == []
    manifest = cache_dir / "asset_manifest.jsonl"
    lines = [ln for ln in manifest.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == n_threads
    for ln in lines:
        json.loads(ln)
    assert not (cache_dir / "asset_cache.lock").exists()
