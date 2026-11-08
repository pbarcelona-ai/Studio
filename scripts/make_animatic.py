#!/usr/bin/env python3
"""Make an animatic: the keyframe stills of a book, each held as long as its narration, with a slow push-in.

Usage: uv run --with imageio-ffmpeg python make_animatic.py --project BOOK --start 1 --end 24 [--keyframes MODEL] [--out animatic.mp4]

Per shot N (row N of all_shots.csv) it uses images/<MODEL>_keyframes/image-NNNN.png (default: the newest keyframe set) and
audio/kokoro/narration-NNNN.wav if it exists. A shot holds for its narration plus a short pause; with no narration file the length is
estimated from the words in audio_shots.csv (about 2.6 words a second, at least 2.5 s). Shots with no keyframe are skipped.
The result is written to projects/<book>/films/<out>. Use it to judge pacing before spending GPU time on video clips.
"""
import argparse, csv, re, shutil, subprocess, sys, tempfile, wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--project", required=True)
ap.add_argument("--start", type=int, default=1)
ap.add_argument("--end", type=int, default=24)
ap.add_argument("--keyframes", default="", help="keyframe model (default: the newest set)")
ap.add_argument("--out", default="animatic.mp4")
ap.add_argument("--fps", type=int, default=24)
ap.add_argument("--pause", type=float, default=0.5, help="seconds held after the narration")
a = ap.parse_args()

if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}\.mp4", a.out):
    sys.exit("--out: letters, digits, - and _ then .mp4")
if a.keyframes and not re.fullmatch(r"[a-z0-9_]{2,60}", a.keyframes):
    sys.exit("bad keyframe model name")
try:
    root = layout.find_dir(a.project)
except ValueError as e:
    sys.exit(str(e))
if root is None:
    sys.exit(f"no such book: {a.project}")

ffmpeg = shutil.which("ffmpeg")
if not ffmpeg:
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("No ffmpeg. Run with: uv run --with imageio-ffmpeg python make_animatic.py ...")

kdirs = sorted((p for p in (root / "images").glob("*_keyframes") if p.is_dir()), key=lambda p: p.stat().st_mtime) if (root / "images").is_dir() else []
kdir = root / "images" / f"{a.keyframes}_keyframes" if a.keyframes else (kdirs[-1] if kdirs else None)
if kdir is None or not kdir.is_dir():
    sys.exit("no keyframes yet: make them first (tick 'Make keyframe stills first')")
narr = []
if (root / "audio_shots.csv").exists():
    with open(root / "audio_shots.csv", newline="", encoding="utf-8") as fh:
        narr = [r.get("narration", "") for r in csv.DictReader(fh)]


def wav_seconds(p):
    try:
        with wave.open(str(p), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, EOFError, OSError):
        return None


shots = []
for n in range(max(1, a.start), a.end + 1):
    img = kdir / f"image-{n:04d}.png"
    if not img.is_file():
        continue
    wav = root / "audio" / "kokoro" / f"narration-{n:04d}.wav"
    secs = wav_seconds(wav) if wav.is_file() else None
    if secs is None:
        words = len((narr[n - 1] if n <= len(narr) else "").split())
        secs, wav = max(2.5, words / 2.6), None
    shots.append((n, img, wav, secs + a.pause))
if not shots:
    sys.exit(f"no keyframes for rows {a.start}-{a.end} in {kdir.name}")

W, H = 1280, 544
tmp = Path(tempfile.mkdtemp(prefix="animatic_"))
try:
    parts = []
    for n, img, wav, dur in shots:
        part = tmp / f"p{n:04d}.mp4"
        frames = max(1, round(dur * a.fps))
        vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
              f"zoompan=z='min(1+0.0004*on,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={a.fps},format=yuv420p")
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(img)]
        cmd += ["-i", str(wav)] if wav else ["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono"]
        cmd += ["-vf", vf, "-af", f"apad=pad_dur={a.pause}", "-t", f"{dur:.3f}", "-ar", "24000", "-ac", "1",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", str(part)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"shot {n}: ffmpeg failed: {r.stderr.strip()[-400:]}")
        parts.append(part)
        print(f"shot {n}: {dur:.1f}s" + (" (narration)" if wav else " (estimated)"), flush=True)
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    out_dir = root / "films"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / a.out
    r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)], capture_output=True, text=True)
    if r.returncode:
        sys.exit("joining failed: " + r.stderr.strip()[-400:])
    print(f"animatic: {len(shots)} shot(s), {sum(s[3] for s in shots):.0f} s -> {out}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
