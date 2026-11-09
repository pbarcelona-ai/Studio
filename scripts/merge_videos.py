#!/usr/bin/env python3
"""Merge shot-NNNN.mp4 clips into one film, in numeric order.

Usage:  uv run --with imageio-ffmpeg python merge_videos.py [CLIP_DIR] [OUTPUT.mp4] [--project NAME] [--start N] [--end N]
        e.g. uv run --with imageio-ffmpeg python merge_videos.py videos/ltx_video film_ltx.mp4 --project adam_eve
        CLIP_DIR and OUTPUT are relative to projects/NAME/ (default project adam_eve); output goes to projects/NAME/films/.
Uses system ffmpeg if present, otherwise the binary bundled with imageio-ffmpeg.
Clips are re-encoded (H.264) so mixed sizes/frame rates still join cleanly.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile

ap = argparse.ArgumentParser()
ap.add_argument("clip_dir", nargs="?", default="videos/ltx_video")
ap.add_argument("output", nargs="?", default=None)
ap.add_argument("--project", default="adam_eve")
ap.add_argument("--start", type=int, default=1)
ap.add_argument("--end", type=int, default=10**9)
args = ap.parse_args()

ffmpeg = shutil.which("ffmpeg")
if not ffmpeg:
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("No ffmpeg. Run with: uv run --with imageio-ffmpeg python merge_videos.py ...")

import layout
PD = layout.project_dir(args.project)      # projects/books/<book>/ (see layout.py)
clip_dir = PD / args.clip_dir
clips = sorted(p for p in clip_dir.glob("shot-*.mp4")
               if args.start <= int(p.stem.split("-")[1]) <= args.end)
if not clips:
    sys.exit(f"no shot-*.mp4 clips in {clip_dir} for that range")
(PD / "films").mkdir(exist_ok=True)
out = (PD / "films" / (args.output or f"{clip_dir.name}_merged.mp4")).resolve()

with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
    for c in clips:
        f.write(f"file '{c.resolve()}'\n")
    listfile = f.name

# No audio track (the open models make silent clips); scale to the first clip's size is not needed
# when all clips come from one model, so just re-encode.
subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", listfile,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-an", str(out)], check=True,
               stderr=subprocess.DEVNULL)
print(f"merged {len(clips)} clips ({clips[0].name} … {clips[-1].name}) → {out}")
