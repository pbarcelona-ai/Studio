"""Reference-Video -> Editing Style Guide Analyzer for Pistachio's Studio.

Analyzes 1-3 reference MP4 videos (uploaded locally or fetched from a permitted URL via `yt-dlp`)
to measure:
- Cut rhythm & average shot length (via `ffmpeg` scene-change detection)
- Speech pacing (words/sec) & pause/dead-air statistics (via local Whisper when audio is present)
- Dominant color palette (hex swatches), average luma brightness, and contrast (via Pillow)

Outputs reusable `references/Editing Style Guide.md` and `references/editing_style.json` inside
the active book project so Step 12 (Shot List), Step 20 (Timeline), and Step 22 (Exports/Captions)
can adopt the reference's real pacing and look.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

log = logging.getLogger("studio.editing_style_analyzer")


def _find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:
        raise RuntimeError("ffmpeg is required to analyze reference videos") from e


def _probe_video_meta(ff: str, video_path: Path) -> dict[str, Any]:
    proc = subprocess.run([ff, "-i", str(video_path)], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30)
    err = proc.stderr or ""
    dur_m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", err)
    duration = (int(dur_m.group(1)) * 3600 + int(dur_m.group(2)) * 60 + float(dur_m.group(3))) if dur_m else 0.0
    vline = next((ln for ln in err.splitlines() if "Video:" in ln), "")
    size_m = re.search(r", (\d{2,5})x(\d{2,5})", vline)
    fps_m = re.search(r"([\d.]+) fps", vline)
    has_audio = any("Audio:" in ln for ln in err.splitlines())
    w = int(size_m.group(1)) if size_m else 0
    h = int(size_m.group(2)) if size_m else 0
    aspect = "9:16" if (h > w and w > 0) else ("1:1" if (w == h and w > 0) else "16:9")
    return {
        "duration": round(duration, 2),
        "width": w,
        "height": h,
        "fps": float(fps_m.group(1)) if fps_m else 24.0,
        "aspect": aspect,
        "has_audio": has_audio,
    }


def _detect_cuts(ff: str, video_path: Path, threshold: float = 0.28) -> list[float]:
    """Return sorted timestamps (seconds) where scene cuts exceed `threshold`."""
    cmd = [
        ff, "-v", "info", "-i", str(video_path),
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=90)
    cuts: list[float] = []
    for m in re.finditer(r"pts_time:([\d.]+)", proc.stderr or ""):
        try:
            t = round(float(m.group(1)), 2)
            if t > 0.15 and (not cuts or (t - cuts[-1]) >= 0.35):
                cuts.append(t)
        except ValueError:
            continue
    return cuts


def _extract_palette_and_luma(ff: str, video_path: Path, duration: float, sample_count: int = 6) -> dict[str, Any]:
    """Sample frames across the video and compute dominant hex swatches, brightness, and contrast."""
    if duration <= 0:
        return {"palette": [], "mean_luma": 128.0, "contrast": 48.0, "mood": "balanced"}
    n = max(1, min(sample_count, 8))
    step = duration / float(n + 1)
    timestamps = [round(step * (i + 1), 2) for i in range(n)]

    lumas: list[float] = []
    contrasts: list[float] = []
    color_buckets: dict[tuple[int, int, int], int] = {}

    with tempfile.TemporaryDirectory(prefix="refstyle-") as tmp:
        tmp_dir = Path(tmp)
        for idx, ts in enumerate(timestamps):
            frame_p = tmp_dir / f"f{idx:02d}.png"
            r = subprocess.run(
                [ff, "-y", "-v", "error", "-ss", f"{ts:.2f}", "-i", str(video_path), "-frames:v", "1", str(frame_p)],
                capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=20,
            )
            if r.returncode != 0 or not frame_p.is_file():
                continue
            try:
                with Image.open(frame_p) as im:
                    rgb = im.convert("RGB")
                    gray = rgb.convert("L")
                    st = ImageStat.Stat(gray)
                    lumas.append(float(st.mean[0]))
                    contrasts.append(float(st.stddev[0]))
                    small = rgb.resize((64, 36), Image.Resampling.BILINEAR)
                    pal_im = small.convert("P", palette=Image.Palette.ADAPTIVE, colors=5).convert("RGB")
                    for count, col in (pal_im.getcolors(maxcolors=256) or []):
                        if isinstance(col, tuple) and len(col) == 3:
                            # Bucket gently to 16-step bins to merge near-identical hues
                            q = (col[0] // 16 * 16, col[1] // 16 * 16, col[2] // 16 * 16)
                            color_buckets[q] = color_buckets.get(q, 0) + int(count)
            except Exception as e:
                log.debug("frame palette inspect failed: %s", e)

    top_cols = sorted(color_buckets.items(), key=lambda kv: kv[1], reverse=True)[:5]
    palette = [f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}" for c, _ in top_cols]
    mean_luma = round(sum(lumas) / len(lumas), 1) if lumas else 128.0
    contrast = round(sum(contrasts) / len(contrasts), 1) if contrasts else 48.0
    mood = "dark / moody" if mean_luma < 85 else ("bright / airy" if mean_luma > 165 else "balanced cinema")
    return {"palette": palette, "mean_luma": mean_luma, "contrast": contrast, "mood": mood}


def download_reference_url(url: str, dest_dir: Path) -> Path:
    """Download a permitted reference video URL via `yt-dlp` into `dest_dir`."""
    clean_url = str(url or "").strip()
    if not clean_url or not clean_url.startswith(("http://", "https://")):
        raise ValueError("Provide a valid http(s) reference video URL")
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_tpl = str(dest_dir / "ref_%(id)s.%(ext)s")
    try:
        import yt_dlp  # type: ignore[import-not-found,unused-ignore]
    except ImportError as e:
        raise RuntimeError("yt-dlp is not installed in this Python environment") from e

    ydl_opts: dict[str, Any] = {
        "outtmpl": out_tpl,
        "format": "mp4/best[ext=mp4]/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(clean_url, download=True)
        fname = ydl.prepare_filename(info)
    p = Path(fname)
    if p.is_file():
        return p
    mp4s = sorted(dest_dir.glob("ref_*.*"), key=lambda x: x.stat().st_mtime, reverse=True)
    if mp4s:
        return mp4s[0]
    raise RuntimeError("yt-dlp finished without writing a local video file")


def analyze_reference_videos(
    slug: str,
    pd: Path,
    video_paths: list[Path],
    *,
    use_whisper: bool = False,
) -> dict[str, Any]:
    """Analyze one or more reference videos and write `references/Editing Style Guide.md` + `editing_style.json`."""
    valid_paths = [p for p in video_paths if p.is_file() and p.stat().st_size > 200]
    if not valid_paths:
        raise ValueError("No valid reference video files found to analyze")

    ff = _find_ffmpeg()
    per_video: list[dict[str, Any]] = []
    all_shot_lens: list[float] = []
    all_wps: list[float] = []
    all_pauses: list[float] = []
    merged_palette: list[str] = []

    for vp in valid_paths[:5]:
        meta = _probe_video_meta(ff, vp)
        cuts = _detect_cuts(ff, vp)
        dur = float(meta["duration"])
        boundaries = [0.0, *cuts, dur] if dur > 0 else [0.0]
        shot_lens = [round(boundaries[i + 1] - boundaries[i], 2) for i in range(len(boundaries) - 1) if (boundaries[i + 1] - boundaries[i]) > 0.1]
        if not shot_lens and dur > 0:
            shot_lens = [dur]
        avg_shot = round(sum(shot_lens) / len(shot_lens), 2) if shot_lens else 3.0
        all_shot_lens.extend(shot_lens)

        vis = _extract_palette_and_luma(ff, vp, dur)
        for hx in vis["palette"]:
            if hx not in merged_palette and len(merged_palette) < 6:
                merged_palette.append(hx)

        words_per_sec: float | None = None
        avg_pause: float | None = None
        if use_whisper and meta["has_audio"]:
            try:
                import audio_first_clock
                words, _eng = audio_first_clock.transcribe_words_local(vp, model_size="tiny")
                if words and dur > 0:
                    words_per_sec = round(len(words) / dur, 2)
                    all_wps.append(words_per_sec)
                    gaps = [round(words[i]["start"] - words[i - 1]["end"], 2) for i in range(1, len(words)) if (words[i]["start"] - words[i - 1]["end"]) >= 0.25]
                    if gaps:
                        avg_pause = round(sum(gaps) / len(gaps), 2)
                        all_pauses.append(avg_pause)
            except Exception as e:
                log.debug("reference whisper pacing skipped: %s", e)

        per_video.append({
            "file": vp.name,
            "duration": dur,
            "aspect": meta["aspect"],
            "fps": meta["fps"],
            "cut_count": len(cuts),
            "avg_shot_seconds": avg_shot,
            "words_per_sec": words_per_sec,
            "avg_pause_seconds": avg_pause,
            "palette": vis["palette"],
            "mean_luma": vis["mean_luma"],
            "contrast": vis["contrast"],
            "mood": vis["mood"],
        })

    overall_avg_shot = round(sum(all_shot_lens) / len(all_shot_lens), 2) if all_shot_lens else 3.0
    if overall_avg_shot <= 1.8:
        pacing_label = "Fast / High-Retention Hook Pacing"
        rec_crossfade = 0.0
    elif overall_avg_shot <= 3.5:
        pacing_label = "Snappy Storyteller / Social Cinema"
        rec_crossfade = 0.3
    else:
        pacing_label = "Measured Theatrical / Cinematic Pacing"
        rec_crossfade = 0.5

    avg_wps = round(sum(all_wps) / len(all_wps), 2) if all_wps else None
    avg_pause_all = round(sum(all_pauses) / len(all_pauses), 2) if all_pauses else None
    dominant_aspect = per_video[0]["aspect"]
    dominant_mood = per_video[0]["mood"]

    guide_lines = [
        f"# Editing Style Guide — {slug}",
        "",
        f"Derived automatically from {len(per_video)} reference video(s).",
        "",
        "## Pacing & Cut Rhythm",
        f"- **Style Profile:** {pacing_label}",
        f"- **Average Shot Length:** {overall_avg_shot:.2f}s (target Step 12 shot durations around {max(1.5, overall_avg_shot - 0.6):.1f}–{overall_avg_shot + 0.8:.1f}s)",
        f"- **Recommended Step 20 Transition:** {'Hard cuts (0.0s)' if rec_crossfade == 0 else f'Short crossfade ({rec_crossfade:.1f}s)'}",
        f"- **Primary Aspect Ratio:** {dominant_aspect}",
        "",
        "## Audio & Speech Delivery",
        f"- **Measured Speech Rate:** {f'{avg_wps:.2f} words/sec' if avg_wps else 'Not measured (enable Whisper audio scan or inspect spoken takes)'}",
        f"- **Typical Pause Gap:** {f'{avg_pause_all:.2f}s (trim dead air above {max(0.45, avg_pause_all):.2f}s)' if avg_pause_all else 'Trim silent pauses > 0.55s via Step 22 Silence Cutter'}",
        "- **Master Loudness Target:** -14 LUFS (48 kHz, true peak <= -1.5 dBTP)",
        "",
        "## Visual Mood & Color Palette",
        f"- **Lighting Mood:** {dominant_mood}",
        f"- **Dominant Hex Swatches:** {', '.join(merged_palette) if merged_palette else 'Auto from Step 09 style'}",
        "",
        "## Per-Reference Breakdown",
    ]
    for item in per_video:
        guide_lines.append(
            f"- **{item['file']}** ({item['duration']}s, {item['aspect']}, {item['fps']} fps): "
            f"{item['cut_count']} cut(s), avg shot {item['avg_shot_seconds']}s, mood `{item['mood']}`, palette {', '.join(item['palette'])}"
        )

    guide_md = "\n".join(guide_lines) + "\n"
    ref_dir = pd / "references"
    ref_dir.mkdir(parents=True, exist_ok=True)
    md_path = ref_dir / "Editing Style Guide.md"
    json_path = ref_dir / "editing_style.json"
    md_path.write_text(guide_md, encoding="utf-8")

    summary: dict[str, Any] = {
        "status": "ok",
        "project": slug,
        "video_count": len(per_video),
        "pacing_label": pacing_label,
        "avg_shot_seconds": overall_avg_shot,
        "recommended_crossfade": rec_crossfade,
        "aspect": dominant_aspect,
        "mood": dominant_mood,
        "palette": merged_palette,
        "words_per_sec": avg_wps,
        "avg_pause_seconds": avg_pause_all,
        "videos": per_video,
        "guide_markdown": guide_md,
        "guide_url": f"/file/{slug}/references/Editing%20Style%20Guide.md",
    }
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
