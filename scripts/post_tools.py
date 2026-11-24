"""Local FFmpeg post-processing tools: silence_cutter (mark/remove/speed_up) and auto_reframe (aspect ratio + face tracking)."""
from __future__ import annotations

import contextlib
from fractions import Fraction
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any

ASPECT_PRESETS: dict[str, tuple[int, int]] = {
    "portrait": (9, 16),
    "square": (1, 1),
    "landscape": (16, 9),
    "cinematic": (21, 9),
    "vertical_4_5": (4, 5),
}

SILENCE_MODES = {"remove", "speed_up", "mark"}


def _ffmpeg_bin() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg

    return str(imageio_ffmpeg.get_ffmpeg_exe())


def _probe_video_info(path: Path) -> tuple[int, int, float, float, float, bool]:
    """Return (width, height, fps, sar, duration, has_audio) using ffprobe or ffmpeg -i + OpenCV fallback."""
    ffprobe = shutil.which("ffprobe")
    width = 0
    height = 0
    fps = 25.0
    sar = 1.0
    duration = 0.0
    has_audio = False

    if ffprobe:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=width,height,r_frame_rate,sample_aspect_ratio,codec_type",
                "-of",
                "json",
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            with contextlib.suppress(Exception):
                data = json.loads(proc.stdout)
                duration = float(data.get("format", {}).get("duration", 0) or 0.0)
                for s in data.get("streams", []):
                    if s.get("codec_type") == "video" and width == 0:
                        width = int(s.get("width") or 0)
                        height = int(s.get("height") or 0)
                        rfps = str(s.get("r_frame_rate") or "25/1").split("/")
                        fps = float(rfps[0]) / float(rfps[1]) if len(rfps) == 2 and float(rfps[1]) > 0 else float(rfps[0])
                        raw_sar = str(s.get("sample_aspect_ratio") or "1:1").replace(":", "/")
                        try:
                            sar_val = float(Fraction(raw_sar))
                            sar = sar_val if sar_val > 0 else 1.0
                        except (ValueError, ZeroDivisionError):
                            sar = 1.0
                    elif s.get("codec_type") == "audio":
                        has_audio = True
                if width > 0 and height > 0 and duration > 0:
                    return width, height, fps, sar, duration, has_audio

    ffmpeg = _ffmpeg_bin()
    proc = subprocess.run([ffmpeg, "-i", str(path)], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
    stderr = proc.stderr or ""
    has_audio = "Audio:" in stderr
    m_res = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", stderr)
    if m_res:
        width = int(m_res.group(1))
        height = int(m_res.group(2))
    m_sar = re.search(r"SAR\s+(\d+):(\d+)", stderr)
    if m_sar and int(m_sar.group(2)) > 0:
        sar_val = int(m_sar.group(1)) / float(m_sar.group(2))
        if sar_val > 0:
            sar = sar_val
    m_fps = re.search(r"([\d.]+)\s+fps", stderr)
    if m_fps:
        fps = float(m_fps.group(1))
    m_dur = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", stderr)
    if m_dur:
        duration = int(m_dur.group(1)) * 3600 + int(m_dur.group(2)) * 60 + float(m_dur.group(3))

    return width, height, fps, sar, duration, has_audio


def build_atempo_chain(factor: float) -> str:
    """Build chained atempo filters where each stage stays within [0.5, 100.0]."""
    filters: list[str] = []
    remaining = float(factor)
    while remaining > 100.0:
        filters.append("atempo=100.0")
        remaining /= 100.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.4f}")
    return ",".join(filters)


def _compute_speech_segments(
    silences: list[dict[str, float]],
    total_duration: float,
    padding: float,
) -> list[dict[str, float]]:
    segments: list[dict[str, float]] = []
    cursor = 0.0
    for silence in silences:
        s_start = float(silence["start"])
        s_end = float(silence["end"])
        if s_start > cursor + 0.05:
            speech_end = min(s_start + padding, total_duration)
            if speech_end > cursor:
                segments.append({"start": round(cursor, 4), "end": round(speech_end, 4)})
        if s_end < total_duration - 0.05:
            cursor = max(cursor, s_end - padding)
        else:
            cursor = total_duration

    if cursor < total_duration - 0.05:
        segments.append({"start": round(cursor, 4), "end": round(total_duration, 4)})

    merged: list[dict[str, float]] = []
    for seg in segments:
        if seg["end"] - seg["start"] < 0.01:
            continue
        if merged and seg["start"] - merged[-1]["end"] < 0.05:
            merged[-1]["end"] = seg["end"]
        else:
            merged.append(seg)
    return merged


def silence_cutter(inputs: dict[str, Any]) -> dict[str, Any]:
    """Detect, mark, remove, or speed up silent regions in a video file."""
    spec = dict(inputs or {})

    input_str = str(spec.get("input_path") or "").strip()
    if not input_str:
        raise ValueError("input_path is required")
    input_path = Path(input_str)
    if not input_path.is_file():
        return {"success": False, "error": f"Input not found: {input_path}"}

    mode = str(spec.get("mode", "remove")).strip()
    if mode not in SILENCE_MODES:
        raise ValueError(f"Invalid silence_cutter mode {mode!r}; expected one of {sorted(SILENCE_MODES)}")

    threshold_db = float(spec.get("silence_threshold_db", -35))
    min_dur = float(spec.get("min_silence_duration", 0.5))
    padding = float(spec.get("padding_seconds", 0.08))
    speed_factor = float(spec.get("silence_speed_factor", 6.0))
    codec = str(spec.get("codec", "libx264"))
    crf = int(spec.get("crf", 18))

    start_t = time.time()
    width, height, _fps, _sar, total_duration, _has_audio = _probe_video_info(input_path)
    if width == 0 or height == 0 or total_duration <= 0:
        return {"success": False, "error": f"Invalid or corrupt media file: {input_path}"}

    ffmpeg = _ffmpeg_bin()
    detect_cmd = [
        ffmpeg,
        "-hide_banner",
        "-i",
        str(input_path),
        "-af",
        f"silencedetect=noise={threshold_db}dB:d={min_dur}",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(detect_cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        return {"success": False, "error": f"Silence detection failed: {proc.stderr[-300:]}"}

    stderr = proc.stderr or ""
    starts = [float(x) for x in re.findall(r"silence_start:\s*([-0-9.]+)", stderr)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([-0-9.]+)", stderr)]
    durations = [float(x) for x in re.findall(r"silence_duration:\s*([-0-9.]+)", stderr)]
    if len(starts) > len(ends):
        ends.append(total_duration)

    silences: list[dict[str, float]] = []
    for i in range(min(len(starts), len(ends))):
        s_val = max(0.0, starts[i])
        e_val = min(total_duration, ends[i])
        d_val = durations[i] if i < len(durations) else max(0.0, e_val - s_val)
        silences.append({"start": s_val, "end": e_val, "duration": d_val})

    if not silences:
        return {
            "success": True,
            "message": "No silence detected — video unchanged",
            "silence_segments": 0,
            "silences": [],
            "speech_segments": [{"start": 0.0, "end": total_duration}],
            "input": str(input_path),
            "output": str(input_path),
            "artifacts": [str(input_path)],
            "duration_seconds": round(time.time() - start_t, 2),
        }

    speech_segments = _compute_speech_segments(silences, total_duration, padding)
    silence_dur = sum(s["duration"] for s in silences)
    speech_dur = sum(s["end"] - s["start"] for s in speech_segments)

    if mode == "mark":
        output_json = Path(str(spec.get("output_path") or input_path.with_suffix(".silence.json")))
        result_data = {
            "silences": silences,
            "speech_segments": speech_segments,
            "total_duration": total_duration,
            "silence_duration": silence_dur,
            "speech_duration": speech_dur,
        }
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(result_data, indent=2), encoding="utf-8")
        return {
            "success": True,
            "mode": "mark",
            "silences": silences,
            "speech_segments": speech_segments,
            "silence_segments": len(silences),
            "silence_duration_seconds": round(silence_dur, 2),
            "speech_duration_seconds": round(speech_dur, 2),
            "output": str(output_json),
            "artifacts": [str(output_json)],
            "duration_seconds": round(time.time() - start_t, 2),
        }

    output_path = Path(str(spec.get("output_path") or input_path.with_stem(f"{input_path.stem}_cut")))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if mode == "remove":
        if not speech_segments:
            return {"success": False, "error": "No speech segments remaining after silence removal"}
        err = _render_jump_cut(ffmpeg, input_path, output_path, speech_segments, codec, crf)
    else:
        err = _render_speed_up(
            ffmpeg,
            input_path,
            output_path,
            speech_segments,
            total_duration,
            speed_factor,
            codec,
            crf,
        )

    if err:
        output_path.unlink(missing_ok=True)
        return {"success": False, "error": err}

    return {
        "success": True,
        "mode": mode,
        "input": str(input_path),
        "output": str(output_path),
        "silences": silences,
        "speech_segments": speech_segments,
        "input_duration": round(total_duration, 2),
        "output_duration": round(speech_dur, 2) if mode == "remove" else None,
        "silence_removed_seconds": round(silence_dur, 2),
        "silence_segments": len(silences),
        "time_saved_percent": round(silence_dur / total_duration * 100, 1) if total_duration > 0 else 0.0,
        "artifacts": [str(output_path)],
        "duration_seconds": round(time.time() - start_t, 2),
    }


def _render_jump_cut(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    speech_segments: list[dict[str, float]],
    codec: str,
    crf: int,
) -> str | None:
    temp_dir = output_path.parent / ".silence_cut_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        seg_files: list[Path] = []
        for i, seg in enumerate(speech_segments):
            seg_path = temp_dir / f"seg_{i:04d}.mp4"
            cmd = [
                ffmpeg,
                "-v",
                "error",
                "-y",
                "-i",
                str(input_path),
                "-ss",
                f"{seg['start']:.3f}",
                "-to",
                f"{seg['end']:.3f}",
                "-c:v",
                codec,
                "-crf",
                str(crf),
                "-preset",
                "fast",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-force_key_frames",
                f"{seg['start']:.3f}",
                str(seg_path),
            ]
            proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                return f"Segment cut failed: {proc.stderr}"
            if seg_path.is_file() and seg_path.stat().st_size > 0:
                seg_files.append(seg_path)
        if not seg_files:
            return "No speech segments were cut"

        list_path = temp_dir / "concat_list.txt"
        with list_path.open("w", encoding="utf-8") as fh:
            for sf in seg_files:
                safe = str(sf.resolve()).replace("\\", "/").replace("'", "'\\''")
                fh.write(f"file '{safe}'\n")

        concat_cmd = [
            ffmpeg,
            "-v",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(output_path),
        ]
        proc = subprocess.run(concat_cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            return f"Concat failed: {proc.stderr}"
        return None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _render_speed_up(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    speech_segments: list[dict[str, float]],
    total_duration: float,
    speed_factor: float,
    codec: str,
    crf: int,
) -> str | None:
    temp_dir = output_path.parent / ".silence_speed_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        all_segments: list[dict[str, float]] = []
        cursor = 0.0
        for seg in speech_segments:
            if seg["start"] > cursor:
                all_segments.append({"start": cursor, "end": seg["start"], "speed": speed_factor})
            all_segments.append({"start": seg["start"], "end": seg["end"], "speed": 1.0})
            cursor = seg["end"]
        if cursor < total_duration:
            all_segments.append({"start": cursor, "end": total_duration, "speed": speed_factor})

        seg_files: list[Path] = []
        for i, seg in enumerate(all_segments):
            duration = seg["end"] - seg["start"]
            if duration < 0.05:
                continue
            seg_path = temp_dir / f"seg_{i:04d}.mp4"
            if seg["speed"] == 1.0:
                cmd = [
                    ffmpeg,
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(input_path),
                    "-ss",
                    f"{seg['start']:.3f}",
                    "-to",
                    f"{seg['end']:.3f}",
                    "-c:v",
                    codec,
                    "-crf",
                    str(crf),
                    "-preset",
                    "fast",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    str(seg_path),
                ]
            else:
                pts = 1.0 / seg["speed"]
                atempo_chain = build_atempo_chain(seg["speed"])
                cmd = [
                    ffmpeg,
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(input_path),
                    "-filter:v",
                    f"trim=start={seg['start']:.6f}:end={seg['end']:.6f},setpts={pts:.8f}*(PTS-STARTPTS)",
                    "-filter:a",
                    f"atrim=start={seg['start']:.6f}:end={seg['end']:.6f},asetpts=PTS-STARTPTS,{atempo_chain}",
                    "-c:v",
                    codec,
                    "-crf",
                    str(crf),
                    "-preset",
                    "fast",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    str(seg_path),
                ]
            proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                return f"Speed-up segment failed: {proc.stderr}"
            if seg_path.is_file() and seg_path.stat().st_size > 0:
                seg_files.append(seg_path)

        if not seg_files:
            return "No speed-up segments were rendered"

        list_path = temp_dir / "concat_list.txt"
        with list_path.open("w", encoding="utf-8") as fh:
            for sf in seg_files:
                safe = str(sf.resolve()).replace("\\", "/").replace("'", "'\\''")
                fh.write(f"file '{safe}'\n")

        concat_cmd = [
            ffmpeg,
            "-v",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(output_path),
        ]
        proc = subprocess.run(concat_cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            return f"Speed-up concat failed: {proc.stderr}"
        return None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _parse_face_tracking_file(json_path: str | Path | None) -> list[dict[str, Any]]:
    """Parse face tracking JSON in either OpenMontage format or E2E list-of-timestamps format."""
    if not json_path:
        return []
    p = Path(str(json_path))
    if not p.is_file():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []

    records: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        items = raw.get("faces") or []
    elif isinstance(raw, list):
        items = raw
    else:
        return []

    for item in items:
        if not isinstance(item, dict):
            continue
        if "bbox" in item and isinstance(item["bbox"], dict):
            b = item["bbox"]
            ts_raw = item.get("timestamp_seconds") if item.get("timestamp_seconds") is not None else item.get("timestamp")
            bw_raw = b.get("width") if b.get("width") is not None else b.get("w")
            bh_raw = b.get("height") if b.get("height") is not None else b.get("h")
            records.append(
                {
                    "timestamp": float(ts_raw or 0.0),
                    "x": float(b.get("x") or 0.0),
                    "y": float(b.get("y") or 0.0),
                    "w": float(bw_raw or 0.0),
                    "h": float(bh_raw or 0.0),
                }
            )
        elif "faces" in item and isinstance(item["faces"], list) and item["faces"]:
            f0 = item["faces"][0]
            if isinstance(f0, dict):
                ts_raw = item.get("timestamp") if item.get("timestamp") is not None else item.get("timestamp_seconds")
                fw_raw = f0.get("w") if f0.get("w") is not None else f0.get("width")
                fh_raw = f0.get("h") if f0.get("h") is not None else f0.get("height")
                records.append(
                    {
                        "timestamp": float(ts_raw or 0.0),
                        "x": float(f0.get("x") or 0.0),
                        "y": float(f0.get("y") or 0.0),
                        "w": float(fw_raw or 0.0),
                        "h": float(fh_raw or 0.0),
                    }
                )
        elif "x" in item and "y" in item:
            iw_raw = item.get("w") if item.get("w") is not None else item.get("width")
            ih_raw = item.get("h") if item.get("h") is not None else item.get("height")
            records.append(
                {
                    "timestamp": float(item.get("timestamp") or 0.0),
                    "x": float(item.get("x") or 0.0),
                    "y": float(item.get("y") or 0.0),
                    "w": float(iw_raw or 0.0),
                    "h": float(ih_raw or 0.0),
                }
            )
    return records


def auto_reframe(inputs: dict[str, Any]) -> dict[str, Any]:
    """Convert video aspect ratio with optional face-tracking crop and SAR normalization."""
    spec = dict(inputs or {})

    input_str = str(spec.get("input_path") or "").strip()
    if not input_str:
        raise ValueError("input_path is required")
    input_path = Path(input_str)
    if not input_path.is_file():
        return {"success": False, "error": f"Input not found: {input_path}"}

    explicit_size = "target_width" in spec and "target_height" in spec
    aspect_name = str(spec.get("target_aspect", "portrait")).strip()
    if not explicit_size and aspect_name not in ASPECT_PRESETS:
        raise ValueError(f"Unknown target_aspect {aspect_name!r}; expected one of {sorted(ASPECT_PRESETS)}")

    start_t = time.time()
    src_w, src_h, src_fps, src_sar, _dur, _has_audio = _probe_video_info(input_path)
    if src_w == 0 or src_h == 0:
        return {"success": False, "error": f"Could not read video dimensions for {input_path}"}

    if explicit_size:
        tw, th = int(spec["target_width"]), int(spec["target_height"])
    else:
        tw, th = ASPECT_PRESETS[aspect_name]

    target_ratio = (tw / float(th)) / src_sar
    src_ratio = src_w / float(src_h)
    if target_ratio > src_ratio:
        crop_w = src_w
        crop_h = int(src_w / target_ratio)
    else:
        crop_h = src_h
        crop_w = int(src_h * target_ratio)
    crop_w = max(2, crop_w - (crop_w % 2))
    crop_h = max(2, crop_h - (crop_h % 2))

    if explicit_size:
        out_w, out_h = int(spec["target_width"]), int(spec["target_height"])
    elif aspect_name == "portrait":
        out_w, out_h = 1080, 1920
    elif aspect_name == "square":
        out_w, out_h = 1080, 1080
    elif aspect_name == "landscape":
        out_w, out_h = 1920, 1080
    elif aspect_name == "cinematic":
        out_w, out_h = 2560, 1080
    elif aspect_name == "vertical_4_5":
        out_w, out_h = 1080, 1350
    else:
        out_w, out_h = crop_w, crop_h
    out_w = max(2, out_w - (out_w % 2))
    out_h = max(2, out_h - (out_h % 2))

    needs_crop = abs(crop_w - src_w) > 2 or abs(crop_h - src_h) > 2
    has_explicit_out = bool(spec.get("output_path"))
    if (
        not needs_crop
        and abs(src_sar - 1.0) < 1e-3
        and not has_explicit_out
        and (not explicit_size or (out_w, out_h) == (src_w, src_h))
    ):
        return {
            "success": True,
            "message": "Source already matches target aspect ratio",
            "output": str(input_path),
            "artifacts": [str(input_path)],
        }

    faces = _parse_face_tracking_file(spec.get("face_tracking_json")) if needs_crop else []
    smoothing_window = max(1, int(spec.get("smoothing_window", 15)))
    crop_x: int | list[int]
    crop_y: int | list[int]

    if faces:
        centers_x = [(f["x"] + f["w"] / 2.0) * src_w for f in faces]
        centers_y = [(f["y"] + f["h"] / 2.0) * src_h for f in faces]
        x_range = max(centers_x) - min(centers_x)
        y_range = max(centers_y) - min(centers_y)
        if len(faces) < 3 or (x_range < src_w * 0.10 and y_range < src_h * 0.10):
            avg_x = sum(centers_x) / len(centers_x)
            avg_y = sum(centers_y) / len(centers_y)
            crop_x = max(0, min(int(avg_x - crop_w / 2.0), src_w - crop_w))
            crop_y = max(0, min(int(avg_y - crop_h * 0.35), src_h - crop_h))
        else:
            sm_x: list[int] = []
            sm_y: list[int] = []
            for i in range(len(centers_x)):
                lo = max(0, i - smoothing_window // 2)
                hi = min(len(centers_x), i + smoothing_window // 2 + 1)
                sx = sum(centers_x[lo:hi]) / (hi - lo)
                sy = sum(centers_y[lo:hi]) / (hi - lo)
                sm_x.append(max(0, min(int(sx - crop_w / 2.0), src_w - crop_w)))
                sm_y.append(max(0, min(int(sy - crop_h * 0.35), src_h - crop_h)))
            crop_x, crop_y = sm_x, sm_y
        method = "face_tracked"
    else:
        crop_x = (src_w - crop_w) // 2
        crop_y = (src_h - crop_h) // 2
        method = "center_crop"

    output_path = Path(str(spec.get("output_path") or input_path.with_stem(f"{input_path.stem}_{aspect_name}")))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    codec = str(spec.get("codec", "libx264"))
    crf = int(spec.get("crf", 18))
    ffmpeg = _ffmpeg_bin()

    if isinstance(crop_x, list) and isinstance(crop_y, list):
        err = _render_dynamic_reframe(
            ffmpeg,
            input_path,
            output_path,
            crop_x,
            crop_y,
            [float(f["timestamp"]) for f in faces],
            crop_w,
            crop_h,
            out_w,
            out_h,
            codec,
            crf,
        )
    else:
        static_x = crop_x[0] if isinstance(crop_x, list) else int(crop_x)
        static_y = crop_y[0] if isinstance(crop_y, list) else int(crop_y)
        err = _render_static_reframe(
            ffmpeg,
            input_path,
            output_path,
            static_x,
            static_y,
            crop_w,
            crop_h,
            out_w,
            out_h,
            codec,
            crf,
        )

    if err:
        output_path.unlink(missing_ok=True)
        return {"success": False, "error": err}

    return {
        "success": True,
        "input": str(input_path),
        "output": str(output_path),
        "source_resolution": f"{src_w}x{src_h}",
        "crop_resolution": f"{crop_w}x{crop_h}",
        "output_resolution": f"{out_w}x{out_h}",
        "method": method,
        "target_aspect": aspect_name,
        "artifacts": [str(output_path)],
        "duration_seconds": round(time.time() - start_t, 2),
    }


def _render_static_reframe(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    crop_x: int,
    crop_y: int,
    crop_w: int,
    crop_h: int,
    out_w: int,
    out_h: int,
    codec: str,
    crf: int,
) -> str | None:
    vf = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={out_w}:{out_h},setsar=1:1"
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        vf,
        "-c:v",
        codec,
        "-crf",
        str(crf),
        "-preset",
        "fast",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(output_path),
    ]
    proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        return f"FFmpeg static reframe failed: {proc.stderr}"
    return None


def _render_dynamic_reframe(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    crop_xs: list[int],
    crop_ys: list[int],
    timestamps: list[float],
    crop_w: int,
    crop_h: int,
    out_w: int,
    out_h: int,
    codec: str,
    crf: int,
) -> str | None:
    temp_dir = output_path.parent / ".reframe_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    sendcmd_path = temp_dir / "crop_commands.txt"
    try:
        lines: list[str] = []
        for i, (cx, cy) in enumerate(zip(crop_xs, crop_ys)):
            ts = timestamps[i] if i < len(timestamps) else i * 0.2
            lines.append(f"{ts:.3f} [enter] crop x {cx};")
            lines.append(f"{ts:.3f} [enter] crop y {cy};")
        sendcmd_path.write_text("\n".join(lines), encoding="utf-8")

        safe_cmd_path = str(sendcmd_path.resolve()).replace("\\", "/")
        vf = (
            f"sendcmd=f='{safe_cmd_path}',"
            f"crop={crop_w}:{crop_h}:{crop_xs[0]}:{crop_ys[0]},"
            f"scale={out_w}:{out_h},setsar=1:1"
        )
        cmd = [
            ffmpeg,
            "-v",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-vf",
            vf,
            "-c:v",
            codec,
            "-crf",
            str(crf),
            "-preset",
            "fast",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output_path),
        ]
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
        if proc.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 0:
            return None
        avg_x = int(sum(crop_xs) / len(crop_xs))
        avg_y = int(sum(crop_ys) / len(crop_ys))
        return _render_static_reframe(ffmpeg, input_path, output_path, avg_x, avg_y, crop_w, crop_h, out_w, out_h, codec, crf)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


silence_cut = silence_cutter
cut_silence = silence_cutter
run_silence_cutter = silence_cutter
reframe = auto_reframe
run_auto_reframe = auto_reframe


class SilenceCutter:
    """Object wrapper matching OpenMontage BaseTool.execute() contract."""

    name = "silence_cutter"
    version = "0.1.1"

    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return silence_cutter(inputs)


class AutoReframe:
    """Object wrapper matching OpenMontage BaseTool.execute() contract."""

    name = "auto_reframe"
    version = "0.1.1"

    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return auto_reframe(inputs)
