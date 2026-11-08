#!/usr/bin/env python3
"""Mix narration, sound effects and music onto the generated clips and join them into one film.

Usage:
  uv run --with imageio-ffmpeg python mix_film.py [--project adam_eve] --model ltx_video [--chapters] [--start 1 --end 40]
        [--sync stretch|speed|trim] [--out film.mp4]
        [--vol-narration 1.0 --vol-sfx 0.5 --vol-music 0.25]

Everything is inside projects/<project>/. Looks for, per CSV row N:  videos/<model>[_chapters]/shot-NNNN.mp4   (required)
                           audio/kokoro[_chapters]/narration-NNNN.wav
                           audio/mmaudio[_chapters]/sfx-NNNN.wav
                           audio/musicgen[_chapters]/music-NNNN.wav   (each optional; missing = skipped)

--selection FILE  use exactly the files listed in a JSON file instead of scanning folders (the studio page writes it):
    {"clips": [{"row": 3, "video": "videos/wan/shot-0003.mp4", "narration": "audio/kokoro/narration-0003.wav" or null,
                "sfx": null, "music": "audio/musicgen/music-0003.wav"}, ...]}
  Paths are relative to projects/<project>/ and must stay inside it. Clips are joined in row order. Use one video source per
  film so all clips have the same size and frame rate.

--sync decides what happens when narration is longer than the clip:
  stretch  slow the clip (up to 2x) and hold the last frame so the whole narration plays (default)
  speed    keep the clip length and speed the narration up (up to 3x)
  trim     keep the clip length and cut the audio at the end of the clip
"""
import argparse, re, shutil, subprocess, sys, tempfile
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--project", default="adam_eve")
ap.add_argument("--model", default="ltx_video")
ap.add_argument("--chapters", action="store_true", help="use the *_chapters folders (one clip per chapter)")
ap.add_argument("--start", type=int, default=1)
ap.add_argument("--end", type=int, default=10**9)
ap.add_argument("--sync", choices=["stretch", "speed", "trim"], default="stretch")
ap.add_argument("--out", default=None)
ap.add_argument("--vol-narration", type=float, default=1.0)
ap.add_argument("--vol-sfx", type=float, default=0.5)
ap.add_argument("--vol-music", type=float, default=0.25)
ap.add_argument("--selection", default=None, help="JSON file listing exactly which clips and audio files to use")
ap.add_argument("--pad", type=float, default=0.4, help="seconds of silence after narration in stretch mode")
args = ap.parse_args()

import layout
ROOT = layout.project_dir(args.project)  # clips, audio and films live per project: projects/books/<book>/ (see layout.py)
suffix = "_chapters" if args.chapters else ""
VIDEO_DIR = ROOT / "videos" / f"{args.model}{suffix}"
STEMS = [  # (name, dir, filename pattern, volume)
    ("narration", ROOT / "audio" / f"kokoro{suffix}", "narration-{:04d}.wav", args.vol_narration),
    ("sfx", ROOT / "audio" / f"mmaudio{suffix}", "sfx-{:04d}.wav", args.vol_sfx),
    ("music", ROOT / "audio" / f"musicgen{suffix}", "music-{:04d}.wav", args.vol_music),
]

ffmpeg = shutil.which("ffmpeg")
if not ffmpeg:
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("No ffmpeg. Run with: uv run --with imageio-ffmpeg python mix_film.py ...")


def duration(path):
    err = subprocess.run([ffmpeg, "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", err)
    if not m:
        raise RuntimeError(f"cannot read duration of {path}")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def atempo_chain(factor):
    """ffmpeg's atempo accepts 0.5-2.0 per filter, so chain for larger factors."""
    parts = []
    while factor > 2.0:
        parts.append("atempo=2.0"); factor /= 2.0
    parts.append(f"atempo={factor:.4f}")
    return ",".join(parts)


def build_segment(i, video, stems, out):
    vd = duration(video)
    nd = next((d for n, _, d in stems if n == "narration"), 0.0)
    video_filter, narr_tempo, total = "null", None, vd
    if args.sync == "stretch" and nd + args.pad > vd:
        total = nd + args.pad
        slow = min(total / vd, 2.0)
        hold = total - vd * slow
        video_filter = f"setpts={slow:.4f}*PTS" + (f",tpad=stop_mode=clone:stop_duration={hold:.3f}" if hold > 0.01 else "")
    elif args.sync == "speed" and nd > vd - 0.2:
        narr_tempo = min(nd / max(vd - 0.2, 0.5), 3.0)

    cmd = [ffmpeg, "-y", "-i", str(video), "-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
    for _, path, _ in stems:
        cmd += ["-i", str(path)]
    fc = [f"[0:v]{video_filter},trim=0:{total:.3f},setpts=PTS-STARTPTS[v]",
          "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[a0]"]
    labels = ["[a0]"]
    for k, (name, path, _) in enumerate(stems, start=2):
        vol = {"narration": args.vol_narration, "sfx": args.vol_sfx, "music": args.vol_music}[name]
        chain = [f"aformat=sample_rates=44100:channel_layouts=stereo", f"volume={vol}"]
        if name == "narration" and narr_tempo:
            chain.append(atempo_chain(narr_tempo))
        if name in ("sfx", "music"):
            chain += ["afade=t=in:d=0.5", f"afade=t=out:st={max(total - 0.8, 0):.3f}:d=0.8"]
        chain += ["apad", f"atrim=0:{total:.3f}"]
        fc.append(f"[{k}:a]{','.join(chain)}[a{k}]")
        labels.append(f"[a{k}]")
    fc.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,atrim=0:{total:.3f}[a]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(out)]
    subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
    return total


def inside_project(rel):
    """Resolve a path from the selection file; it must be an existing file inside projects/<project>/."""
    p = (ROOT / rel).resolve()
    if ROOT.resolve() not in p.parents or not p.is_file():
        sys.exit(f"not a file inside the project: {rel}")
    return p


if args.selection:
    import json
    sel_path = Path(args.selection)
    if not sel_path.is_absolute():
        sel_path = ROOT / sel_path                  # relative paths are inside projects/<project>/ (the studio page passes films/_selection.json)
    items = json.load(open(sel_path))["clips"]
    plan = []
    for it in sorted(items, key=lambda x: int(x["row"])):
        files = [(k, inside_project(it[k])) for k in ("narration", "sfx", "music") if it.get(k)]
        plan.append((int(it["row"]), inside_project(it["video"]), files))
else:
    clips = sorted((int(p.stem.split("-")[1]), p) for p in VIDEO_DIR.glob("shot-*.mp4"))
    clips = [(n, p) for n, p in clips if args.start <= n <= args.end]
    plan = []
    for n, video in clips:
        files = [(name, d / pattern.format(n)) for name, d, pattern, _ in STEMS if (d / pattern.format(n)).exists()]
        plan.append((n, video, files))
if not plan:
    sys.exit("no clips to use (nothing selected, or no shot-*.mp4 files in the folder for that range)")

def srt_time(t):
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def narration_lines():
    """Narration text per row number, from audio_shots.csv (empty if the book has none)."""
    import csv
    try:
        with open(ROOT / "audio_shots.csv", newline="", encoding="utf-8") as fh:
            return [(r.get("narration") or "").strip() for r in csv.DictReader(fh)]
    except OSError:
        return []


tmp = Path(tempfile.mkdtemp(prefix="mix_"))
segments, total_len, used = [], 0.0, {"narration": 0, "sfx": 0, "music": 0}
captions, lines = [], narration_lines()
for n, video, files in plan:
    stems = []
    for name, f in files:
        stems.append((name, f, duration(f))); used[name] += 1
    seg = tmp / f"seg-{n:04d}.mp4"
    try:
        seg_len = build_segment(n, video, stems, seg)
        text = lines[n - 1] if 0 < n <= len(lines) else ""
        if text and any(k == "narration" for k, _, _ in stems):          # a caption only where the narration is actually heard
            captions.append((total_len, total_len + seg_len - 0.1, text))
        total_len += seg_len
        segments.append(seg)
    except subprocess.CalledProcessError:
        print(f"  shot {n}: ffmpeg failed, skipped")
    print(f"  shot {n}: {len(stems)} audio stem(s)", flush=True)

listfile = tmp / "list.txt"
listfile.write_text("".join(f"file '{s}'\n" for s in segments))
(ROOT / "films").mkdir(exist_ok=True)
out = (ROOT / "films" / (args.out or ("selected_film.mp4" if args.selection else f"{args.model}{suffix}_mixed.mp4"))).resolve()
subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", str(out)],
               check=True, stderr=subprocess.DEVNULL)
shutil.rmtree(tmp, ignore_errors=True)
if captions:                                  # subtitles next to the film (same name, .srt): players and editors pick them up
    out.with_suffix(".srt").write_text("".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(captions, 1)), encoding="utf-8")
    print(f"captions: {len(captions)} line(s) -> {out.with_suffix('.srt').name}")
print(f"mixed {len(segments)} clips, {total_len:.1f}s, stems used {used} → {out}")
