"""Visual QA tool for automated video quality checks (review frame extraction, probe metadata, audio levels)."""
from __future__ import annotations

import contextlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any


def _ffmpeg_bin() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg

    return str(imageio_ffmpeg.get_ffmpeg_exe())


def _probe_media_meta(input_path: Path) -> dict[str, Any]:
    """Probe width, height, duration, codecs, pix_fmt, and has_audio via ffprobe or ffmpeg + OpenCV fallback."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration,size:stream=width,height,codec_name,pix_fmt,r_frame_rate,sample_rate,channels,codec_type",
                "-of",
                "json",
                str(input_path),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            probe_data = json.loads(proc.stdout)
            v_stream = next((s for s in probe_data.get("streams", []) if s.get("codec_type") == "video"), None)
            a_stream = next((s for s in probe_data.get("streams", []) if s.get("codec_type") == "audio"), None)
            info: dict[str, Any] = {
                "duration": float(probe_data.get("format", {}).get("duration", 0) or 0),
                "file_size_mb": round(int(probe_data.get("format", {}).get("size", 0) or 0) / 1048576, 1),
                "has_audio": a_stream is not None,
            }
            if v_stream:
                info.update(
                    {
                        "width": int(v_stream.get("width") or 0),
                        "height": int(v_stream.get("height") or 0),
                        "pixel_format": v_stream.get("pix_fmt"),
                        "video_codec": v_stream.get("codec_name"),
                        "frame_rate": v_stream.get("r_frame_rate"),
                    }
                )
            if a_stream:
                info.update(
                    {
                        "audio_codec": a_stream.get("codec_name"),
                        "sample_rate": a_stream.get("sample_rate"),
                        "channels": a_stream.get("channels"),
                    }
                )
            return info

    ffmpeg = _ffmpeg_bin()
    proc = subprocess.run([ffmpeg, "-i", str(input_path)], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
    stderr = proc.stderr or ""
    width = 0
    height = 0
    duration = 0.0
    pix_fmt = "yuv420p"
    v_codec = "h264"
    fps_str = ""
    has_audio = "Audio:" in stderr

    m_res = re.search(r"Video:\s*([A-Za-z0-9_]+).*?(\d{2,5})x(\d{2,5})", stderr)
    if m_res:
        v_codec = m_res.group(1)
        width = int(m_res.group(2))
        height = int(m_res.group(3))
    m_pix = re.search(r"Video:[^,\n]+,\s*([a-z0-9_]+)", stderr)
    if m_pix:
        pix_fmt = m_pix.group(1)
    m_dur = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", stderr)
    if m_dur:
        duration = int(m_dur.group(1)) * 3600 + int(m_dur.group(2)) * 60 + float(m_dur.group(3))
    m_fps = re.search(r"([\d.]+)\s+fps", stderr)
    if m_fps:
        fps_str = m_fps.group(1)

    if width == 0 or height == 0 or duration == 0.0:
        with contextlib.suppress(Exception):
            import cv2

            cap = cv2.VideoCapture(str(input_path))
            try:
                if cap.isOpened():
                    if width == 0:
                        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    if height == 0:
                        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
                    fc = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                    if duration == 0.0 and fps > 0 and fc > 0:
                        duration = fc / fps
            finally:
                cap.release()

    return {
        "width": width,
        "height": height,
        "duration": duration,
        "file_size_mb": round(input_path.stat().st_size / 1048576, 1) if input_path.is_file() else 0.0,
        "has_audio": has_audio,
        "pixel_format": pix_fmt,
        "video_codec": v_codec,
        "frame_rate": fps_str,
    }


def _is_frame_black(frame_path: Path) -> bool:
    try:
        from PIL import Image, ImageStat

        with Image.open(frame_path) as img:
            gray = img.convert("L")
            mean_luma = float(ImageStat.Stat(gray).mean[0])
            return mean_luma < 5.0
    except Exception:
        return frame_path.stat().st_size < 2000 if frame_path.is_file() else True


def run_visual_qa(inputs: dict[str, Any]) -> dict[str, Any]:
    """Run review, probe, or audio_levels on a video file."""
    operation = str(inputs.get("operation", "probe"))
    input_str = str(inputs.get("input_path") or "")
    input_path = Path(input_str)
    if not input_str or not input_path.is_file():
        return {"success": False, "error": f"Input not found: {input_str}"}

    start = time.time()
    try:
        if operation == "review":
            res = _review(input_path, inputs)
        elif operation == "probe":
            res = _probe(input_path, inputs)
        elif operation == "audio_levels":
            res = _audio_levels(input_path, inputs)
        else:
            return {"success": False, "error": f"Unknown operation: {operation}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    res["duration_seconds"] = round(time.time() - start, 2)
    return res


def _review(input_path: Path, inputs: dict[str, Any]) -> dict[str, Any]:
    ffmpeg = _ffmpeg_bin()
    timestamps = list(inputs.get("timestamps") or [])
    if not timestamps:
        dur = float(_probe_media_meta(input_path).get("duration") or 4.0)
        timestamps = [1.0, dur * 0.25, dur * 0.50, dur * 0.75, max(dur - 1.0, 0.0)]

    out_dir = Path(str(inputs.get("output_dir") or (input_path.parent / "review_frames")))
    out_dir.mkdir(parents=True, exist_ok=True)

    frames: list[dict[str, Any]] = []
    frame_paths: list[str] = []
    black_detected = False

    for ts in timestamps:
        ts_val = float(ts)
        ts_label = f"{ts_val:.1f}".replace(".", "_")
        frame_path = out_dir / f"frame_{ts_label}s.jpg"
        cmd = [
            ffmpeg,
            "-v",
            "error",
            "-y",
            "-ss",
            str(ts_val),
            "-i",
            str(input_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(frame_path),
        ]
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0 and frame_path.is_file():
            is_black = _is_frame_black(frame_path)
            if is_black:
                black_detected = True
            frames.append({"timestamp": ts_val, "path": str(frame_path), "black_frame": is_black})
            frame_paths.append(str(frame_path))
        else:
            frames.append({"timestamp": ts_val, "path": None, "error": f"Failed to extract frame at {ts_val}s"})

    return {
        "success": True,
        "operation": "review",
        "input": str(input_path),
        "frame_count": len(frame_paths),
        "frames": frames,
        "frame_paths": frame_paths,
        "artifacts": frame_paths,
        "black_frames_detected": black_detected,
    }


def _probe(input_path: Path, inputs: dict[str, Any]) -> dict[str, Any]:
    raw_exp = inputs.get("expected")
    expected: dict[str, Any] = raw_exp if isinstance(raw_exp, dict) else {}
    info = _probe_media_meta(input_path)
    if info.get("width", 0) == 0 and info.get("height", 0) == 0 and info.get("duration", 0.0) == 0.0:
        return {"success": False, "error": f"Failed to probe video: {input_path}"}

    issues: list[str] = []
    if "width" in expected and info.get("width") != expected["width"]:
        issues.append(f"Width: expected {expected['width']}, got {info.get('width')}")
    if "height" in expected and info.get("height") != expected["height"]:
        issues.append(f"Height: expected {expected['height']}, got {info.get('height')}")
    if "min_duration" in expected and float(info.get("duration", 0.0)) < float(expected["min_duration"]):
        issues.append(f"Duration too short: {info['duration']:.1f}s < {expected['min_duration']}s")
    if "max_duration" in expected and float(info.get("duration", 0.0)) > float(expected["max_duration"]):
        issues.append(f"Duration too long: {info['duration']:.1f}s > {expected['max_duration']}s")
    if "pixel_format" in expected and info.get("pixel_format") != expected["pixel_format"]:
        issues.append(f"Pixel format: expected {expected['pixel_format']}, got {info.get('pixel_format')}")
    if "has_audio" in expected and bool(info.get("has_audio")) != bool(expected["has_audio"]):
        issues.append(f"Audio: expected {expected['has_audio']}, got {info.get('has_audio')}")

    info["validation_issues"] = issues
    info["validation_passed"] = len(issues) == 0
    return {
        "success": True,
        "operation": "probe",
        "input": str(input_path),
        **info,
    }


def _audio_levels(input_path: Path, inputs: dict[str, Any]) -> dict[str, Any]:
    ffmpeg = _ffmpeg_bin()
    timestamps = list(inputs.get("timestamps") or [])
    if not timestamps:
        dur = float(_probe_media_meta(input_path).get("duration") or 3.0)
        timestamps = [0.0, dur * 0.5, max(dur - 1.0, 0.0)]

    null_sink = "NUL" if sys.platform == "win32" else "/dev/null"
    levels: list[dict[str, Any]] = []
    mean_vals: list[float] = []
    max_vals: list[float] = []

    for ts in timestamps:
        ts_val = float(ts)
        cmd = [
            ffmpeg,
            "-y",
            "-ss",
            str(ts_val),
            "-t",
            "3",
            "-i",
            str(input_path),
            "-vn",
            "-af",
            "volumedetect",
            "-f",
            "null",
            null_sink,
        ]
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
        stderr = proc.stderr or ""
        mean_vol: float | None = None
        max_vol: float | None = None
        for line in stderr.splitlines():
            if "mean_volume:" in line:
                try:
                    mean_vol = float(line.split("mean_volume:")[1].strip().split()[0])
                except ValueError:
                    pass
            elif "max_volume:" in line:
                try:
                    max_vol = float(line.split("max_volume:")[1].strip().split()[0])
                except ValueError:
                    pass
        if mean_vol is not None:
            mean_vals.append(mean_vol)
        if max_vol is not None:
            max_vals.append(max_vol)
        levels.append({"timestamp": ts_val, "mean_volume_db": mean_vol, "max_volume_db": max_vol})

    agg_mean = sum(mean_vals) / len(mean_vals) if mean_vals else -91.0
    agg_max = max(max_vals) if max_vals else -91.0
    return {
        "success": True,
        "operation": "audio_levels",
        "input": str(input_path),
        "levels": levels,
        "mean_volume_db": round(agg_mean, 2),
        "max_volume_db": round(agg_max, 2),
        "unexpected_silence": agg_mean < -60.0,
        "clipping_detected": agg_max >= -0.5,
    }


visual_qa = run_visual_qa


def review(input_path: str, **kwargs: Any) -> dict[str, Any]:
    return run_visual_qa({"operation": "review", "input_path": input_path, **kwargs})


def probe(input_path: str, **kwargs: Any) -> dict[str, Any]:
    return run_visual_qa({"operation": "probe", "input_path": input_path, **kwargs})


def audio_levels(input_path: str, **kwargs: Any) -> dict[str, Any]:
    return run_visual_qa({"operation": "audio_levels", "input_path": input_path, **kwargs})


class VisualQA:
    """Object wrapper matching OpenMontage BaseTool.execute() contract."""

    name = "visual_qa"
    version = "0.1.0"

    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return run_visual_qa(inputs)
