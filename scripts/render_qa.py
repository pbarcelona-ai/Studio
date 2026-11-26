#!/usr/bin/env python3
"""Pre-/post-render QA for Pistachio's Studio videos (animatics, films, Remotion/HyperFrames renders).

  python3 scripts/render_qa.py <video.mp4> [--contact-sheet out.jpg] [--samples 8] [--max-drift 0.5]

Checks a rendered MP4 for common automated-render failures:
  - Missing video stream, zero duration, or unreadable container
  - Audio/video duration drift exceeding `--max-drift` seconds
  - Blank / solid-color / near-black / near-white sampled frames
  - Frozen / stuck output where consecutive sampled frames are identical
  - Optional timestamp-labeled contact sheet JPEG for quick visual inspection
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageStat


class QAError(RuntimeError):
    """Raised when a video cannot be inspected."""


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:
        raise QAError("No ffmpeg found (install ffmpeg or imageio-ffmpeg)") from e


def _parse_timecode(h: str, m: str, s: str) -> float:
    return int(h) * 3600 + int(m) * 60 + float(s)


def probe_media(ff: str, video: Path) -> dict[str, Any]:
    """Probe resolution, fps, container duration, and per-stream (video/audio) durations."""
    if not video.is_file():
        raise QAError(f"file not found: {video}")
    rep = subprocess.run([ff, "-i", str(video)], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30).stderr
    vline = next((ln for ln in rep.splitlines() if "Video:" in ln), "")
    aline = next((ln for ln in rep.splitlines() if "Audio:" in ln), "")
    size = re.search(r", (\d{2,5})x(\d{2,5})", vline)
    fps = re.search(r"([\d.]+) fps", vline)
    dur_m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", rep)
    duration = _parse_timecode(*dur_m.groups()) if dur_m else 0.0

    # Measure exact audio stream duration via null mux when audio is present (catches A/V drift accurately)
    audio_dur: float | None = None
    if aline:
        ar = subprocess.run([ff, "-i", str(video), "-vn", "-c:a", "copy", "-f", "null", "-"],
                            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60).stderr
        tm = re.findall(r"time=(\d+):(\d+):(\d+\.\d+)", ar)
        if tm:
            audio_dur = _parse_timecode(*tm[-1])

    video_dur: float | None = None
    if vline:
        vr = subprocess.run([ff, "-i", str(video), "-an", "-c:v", "copy", "-f", "null", "-"],
                            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60).stderr
        tm = re.findall(r"time=(\d+):(\d+):(\d+\.\d+)", vr)
        if tm:
            video_dur = _parse_timecode(*tm[-1])

    drift = 0.0
    if video_dur is not None and audio_dur is not None:
        drift = round(abs(video_dur - audio_dur), 3)

    return {
        "has_video": bool(vline and size),
        "has_audio": bool(aline),
        "width": int(size.group(1)) if size else 0,
        "height": int(size.group(2)) if size else 0,
        "fps": float(fps.group(1)) if fps else 0.0,
        "duration": round(duration, 3),
        "video_duration": round(video_dur, 3) if video_dur is not None else round(duration, 3),
        "audio_duration": round(audio_dur, 3) if audio_dur is not None else None,
        "av_drift": drift,
    }


def sample_timestamps(duration: float, count: int) -> list[float]:
    """Return `count` evenly spaced timestamps inside (0, duration), avoiding exact end-of-file EOF seeks."""
    if duration <= 0 or count <= 0:
        return []
    if count == 1:
        return [round(duration * 0.5, 3)]
    margin = min(0.15, duration * 0.05)
    lo = margin
    hi = max(lo, duration - margin)
    step = (hi - lo) / (count - 1) if hi > lo else 0.0
    return [round(lo + i * step, 3) for i in range(count)]


def extract_frames(ff: str, video: Path, out_dir: Path, timestamps: list[float]) -> list[tuple[float, Path]]:
    """Extract one PNG frame at each timestamp."""
    out: list[tuple[float, Path]] = []
    for i, ts in enumerate(timestamps):
        dest = out_dir / f"frame-{i:03d}.png"
        r = subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{ts:.3f}", "-i", str(video),
                            "-frames:v", "1", str(dest)],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30)
        if r.returncode == 0 and dest.is_file():
            out.append((ts, dest))
    return out


def analyze_frame(img_path: Path) -> dict[str, Any]:
    """Compute luma statistics and blank/black/white flags for one image frame."""
    with Image.open(img_path) as im:
        gray = im.convert("L")
        stat = ImageStat.Stat(gray)
        mean = float(stat.mean[0])
        std = float(stat.stddev[0])
    return {
        "mean_luma": round(mean, 2),
        "std_luma": round(std, 2),
        "solid": std < 2.0,
        "black": mean < 5.0 and std < 3.0,
        "white": mean > 250.0 and std < 3.0,
    }


def frame_diff_mean(a_path: Path, b_path: Path) -> float:
    """Mean absolute pixel difference (0..255) between two frames resized to a fast comparison grid."""
    with Image.open(a_path) as ia, Image.open(b_path) as ib:
        ga = ia.convert("L").resize((160, 90))
        gb = ib.convert("L").resize((160, 90))
        diff = ImageChops.difference(ga, gb)
        return round(float(ImageStat.Stat(diff).mean[0]), 3)


def make_contact_sheet(frames: list[tuple[float, Path]], dest: Path, cols: int = 4, thumb_w: int = 320) -> Path:
    """Assemble timestamp-labeled thumbnails into a single JPEG contact sheet."""
    if not frames:
        raise QAError("no frames to build a contact sheet")
    cols = max(1, min(cols, len(frames)))
    rows = math.ceil(len(frames) / cols)
    with Image.open(frames[0][1]) as first:
        w0, h0 = first.size
    thumb_h = max(1, round(thumb_w * (h0 / max(1, w0))))
    pad = 8
    sheet = Image.new("RGB", (cols * (thumb_w + pad) + pad, rows * (thumb_h + pad) + pad), (18, 18, 22))
    draw = ImageDraw.Draw(sheet)
    for idx, (ts, fpath) in enumerate(frames):
        r, c = divmod(idx, cols)
        x = pad + c * (thumb_w + pad)
        y = pad + r * (thumb_h + pad)
        with Image.open(fpath) as im:
            thumb = im.convert("RGB").resize((thumb_w, thumb_h))
        sheet.paste(thumb, (x, y))
        label = f"{ts:06.2f}s"
        draw.rectangle([x + 4, y + 4, x + 64, y + 20], fill=(0, 0, 0))
        draw.text((x + 8, y + 6), label, fill=(255, 255, 255))
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest, "JPEG", quality=85)
    return dest


def inspect_video(video: Path, contact_sheet: Path | None = None, samples: int = 8, max_av_drift: float = 0.5,
                  ffmpeg_bin: str | None = None, *, strict_sync_ms: float = 40.0, check_lufs: bool = False) -> dict[str, Any]:
    """Run full QA on `video` and return {"ok", "errors", "warnings", "metrics", "frames", "contact_sheet"}."""
    ff = ffmpeg_bin or find_ffmpeg()
    metrics = probe_media(ff, video)
    errors: list[str] = []
    warnings: list[str] = []
    frame_reports: list[dict[str, Any]] = []
    sheet_out: str | None = None

    drift_ms = round(float(metrics.get("av_drift") or 0.0) * 1000.0, 1)
    metrics["av_drift_ms"] = drift_ms
    metrics["strict_sync_ok"] = (not metrics["has_audio"]) or (drift_ms <= float(strict_sync_ms))
    if check_lufs and metrics["has_audio"]:
        try:
            import audio_first_clock
            lufs_res = audio_first_clock.measure_loudness_lufs(video, ffmpeg_bin=ff)
            if lufs_res.get("ok"):
                metrics["integrated_lufs"] = lufs_res.get("integrated_lufs")
                metrics["true_peak_db"] = lufs_res.get("true_peak_db")
        except Exception as e:
            warnings.append(f"LUFS measurement unavailable: {e}")

    if not metrics["has_video"]:
        errors.append("no readable video stream found")
    if metrics["duration"] <= 0:
        errors.append("video duration is 0 seconds")
    if metrics["has_audio"] and metrics["av_drift"] > max_av_drift:
        warnings.append(f"audio/video duration drift is {metrics['av_drift']:.2f}s (limit {max_av_drift:.2f}s)")

    if metrics["has_video"] and metrics["duration"] > 0:
        ts_list = sample_timestamps(metrics["duration"], samples)
        with tempfile.TemporaryDirectory(prefix="studio-qa-") as tmp_:
            extracted = extract_frames(ff, video, Path(tmp_), ts_list)
            if not extracted:
                errors.append("could not decode any sampled video frames")
            else:
                diffs: list[float] = []
                for i, (ts, fpath) in enumerate(extracted):
                    st = analyze_frame(fpath)
                    diff = frame_diff_mean(extracted[i - 1][1], fpath) if i > 0 else None
                    if diff is not None:
                        diffs.append(diff)
                    frame_reports.append({"t": ts, **st, "diff_prev": diff})
                blank_count = sum(1 for f in frame_reports if f["solid"])
                black_count = sum(1 for f in frame_reports if f["black"])
                if blank_count == len(frame_reports):
                    errors.append(f"all {blank_count} sampled frames are solid/blank")
                elif black_count > 0:
                    warnings.append(f"{black_count} of {len(frame_reports)} sampled frames are near-black")
                elif blank_count > 0:
                    warnings.append(f"{blank_count} of {len(frame_reports)} sampled frames are solid/blank")
                if diffs and max(diffs) < 0.25:
                    warnings.append("video appears frozen (consecutive sampled frames are nearly identical)")
                if contact_sheet is not None:
                    make_contact_sheet(extracted, contact_sheet)
                    sheet_out = str(contact_sheet)

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": metrics,
        "frames": frame_reports,
        "contact_sheet": sheet_out,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "Render QA")
    ap.add_argument("video", help="Path to the rendered video file")
    ap.add_argument("--contact-sheet", default="", help="Optional output JPEG path for a timestamped contact sheet")
    ap.add_argument("--samples", type=int, default=8, help="Number of frames to sample across the video")
    ap.add_argument("--max-drift", type=float, default=0.5, help="Max allowed audio/video duration drift in seconds")
    a = ap.parse_args(argv)
    try:
        rep = inspect_video(Path(a.video), Path(a.contact_sheet) if a.contact_sheet else None, a.samples, a.max_drift)
    except QAError as e:
        print(f"QA error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(rep, indent=2))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
