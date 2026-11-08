#!/usr/bin/env python3
"""Mix narration, sound effects and music onto the generated clips and join them into one film.

Usage:
  uv run --with imageio-ffmpeg python mix_film.py [--project adam_eve] --model ltx_video [--chapters] [--start 1 --end 40]
        [--sync stretch|speed|trim] [--out film.mp4]
        [--vol-narration 1.0 --vol-sfx 0.5 --vol-music 0.25] [--transition cut|fade --fade 0.5] [--burn-captions]

Everything is inside projects/<project>/. Looks for, per CSV row N:  videos/<model>[_chapters]/shot-NNNN.mp4   (required)
                           audio/kokoro[_chapters]/narration-NNNN.wav
                           audio/mmaudio[_chapters]/sfx-NNNN.wav
                           audio/musicgen[_chapters]/music-NNNN.wav   (each optional; missing = skipped)

--selection FILE  use exactly the files listed in a JSON file instead of scanning folders (the studio page writes it):
    {"clips": [{"row": 3, "video": "videos/wan/shot-0003.mp4", "narration": "audio/kokoro/narration-0003.wav" or null,
                "sfx": null, "music": "audio/musicgen/music-0003.wav", "trim_start": 0.0, "trim_end": 0.5}, ...],
     "title": "Opening title card text" (optional), "end_title": "End card text" (optional)}
  Paths are relative to projects/<project>/ and must stay inside it. Clips are joined in the order listed (so the page can reorder
  them). trim_start / trim_end cut seconds off the clip's start / end (the narration is not cut). Use one video source per film so
  all clips have the same size and frame rate. Title cards are 3.5 s of white text on black, the size of the clips.

--transition fade  fades each clip in from and out to black over --fade seconds (sound too); cut (default) joins them directly.
--burn-captions    also draws the narration captions into the picture (the .srt is written either way).

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
ap.add_argument("--transition", choices=["cut", "fade"], default="cut")
ap.add_argument("--fade", type=float, default=0.5, help="fade length in seconds with --transition fade (0.1-1.5)")
ap.add_argument("--burn-captions", action="store_true", help="draw the captions into the picture")
args = ap.parse_args()
if not 0.1 <= args.fade <= 1.5:
    sys.exit("--fade must be 0.1-1.5 seconds")

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


def build_segment(i, video, stems, out, trim_start=0.0, trim_end=0.0):
    full = duration(video)
    trim_start = min(max(trim_start, 0.0), max(full - 0.5, 0.0))
    vd = max(full - trim_start - max(trim_end, 0.0), 0.5)               # at least half a second of picture is kept
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
    fade = min(args.fade, total / 3) if args.transition == "fade" else 0.0
    vfade = f",fade=t=in:st=0:d={fade:.3f},fade=t=out:st={total - fade:.3f}:d={fade:.3f}" if fade else ""
    fc = [f"[0:v]trim=start={trim_start:.3f}:duration={vd:.3f},setpts=PTS-STARTPTS,{video_filter},trim=0:{total:.3f},setpts=PTS-STARTPTS{vfade}[v]",
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
    afade = f",afade=t=in:d={fade:.3f},afade=t=out:st={total - fade:.3f}:d={fade:.3f}" if fade else ""
    fc.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,atrim=0:{total:.3f}{afade}[a]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(out)]
    subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
    return total


FONTS = ["/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"]
CARD_SECONDS = 3.5


def filter_path(p):
    """A file path quoted for an ffmpeg filter argument. The temporary files are passed by bare name (ffmpeg runs inside the temporary
    folder), so only the font path needs this; a ' in it is closed, escaped and reopened."""
    return "'" + str(p).replace("\\", "/").replace("'", "'\\''") + "'"


def video_shape(path):
    """(width, height, fps) of a video, read from ffmpeg's stream line."""
    err = subprocess.run([ffmpeg, "-i", str(path)], capture_output=True, text=True).stderr
    line = next((ln for ln in err.splitlines() if "Video:" in ln), "")
    size, fps = re.search(r", (\d{2,5})x(\d{2,5})", line), re.search(r"([\d.]+) fps", line)
    if not size:
        raise RuntimeError(f"cannot read the picture size of {path}")
    return int(size.group(1)), int(size.group(2)), float(fps.group(1)) if fps else 24.0


def build_card(text, shape, out):
    """A title card: the text in white on black, CARD_SECONDS long, with silence, encoded like the clip segments."""
    font = next((f for f in FONTS if Path(f).is_file()), None)
    if not font:
        print("  title card skipped: no font found")
        return None
    w, h, fps = shape
    tf = out.with_suffix(".txt")
    tf.write_text(text, encoding="utf-8")                              # textfile= avoids escaping the user's text inside the filter
    size = max(16, min(h // 9, int(w * 1.7 / max(len(text), 1))))
    fade = min(0.6, CARD_SECONDS / 4)
    vf = (f"drawtext=fontfile={filter_path(font)}:textfile={tf.name}:fontcolor=white:fontsize={size}:"
          f"x=(w-text_w)/2:y=(h-text_h)/2,fade=t=in:st=0:d={fade},fade=t=out:st={CARD_SECONDS - fade}:d={fade},format=yuv420p")
    cmd = [ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps:g}:d={CARD_SECONDS}",
           "-f", "lavfi", "-t", str(CARD_SECONDS), "-i", "anullsrc=r=44100:cl=stereo", "-vf", vf, "-t", str(CARD_SECONDS),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(out)]
    try:
        subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL, cwd=out.parent)
    except subprocess.CalledProcessError:
        print("  title card skipped: ffmpeg could not draw the text")
        return None
    return out


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
    selection = json.load(open(sel_path))
    titles = (str(selection.get("title") or "").strip()[:120], str(selection.get("end_title") or "").strip()[:120])
    plan = []
    for it in selection["clips"]:                     # in the order listed: the page lets you reorder the clips
        files = [(k, inside_project(it[k])) for k in ("narration", "sfx", "music") if it.get(k)]
        trims = tuple(min(max(float(it.get(k) or 0), 0.0), 30.0) for k in ("trim_start", "trim_end"))
        plan.append((int(it["row"]), inside_project(it["video"]), files, trims))
else:
    clips = sorted((int(p.stem.split("-")[1]), p) for p in VIDEO_DIR.glob("shot-*.mp4"))
    clips = [(n, p) for n, p in clips if args.start <= n <= args.end]
    plan = []
    for n, video in clips:
        files = [(name, d / pattern.format(n)) for name, d, pattern, _ in STEMS if (d / pattern.format(n)).exists()]
        plan.append((n, video, files, (0.0, 0.0)))
    titles = ("", "")
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
shape = video_shape(plan[0][1]) if any(titles) else None
if titles[0]:
    card = build_card(titles[0], shape, tmp / "card-open.mp4")
    if card:
        segments.append(card); total_len += CARD_SECONDS
for k, (n, video, files, trims) in enumerate(plan):
    stems = []
    for name, f in files:
        stems.append((name, f, duration(f))); used[name] += 1
    seg = tmp / f"seg-{k:04d}-{n:04d}.mp4"
    try:
        seg_len = build_segment(n, video, stems, seg, *trims)
        text = lines[n - 1] if 0 < n <= len(lines) else ""
        if text and any(k == "narration" for k, _, _ in stems):          # a caption only where the narration is actually heard
            captions.append((total_len, total_len + seg_len - 0.1, text))
        total_len += seg_len
        segments.append(seg)
    except subprocess.CalledProcessError:
        print(f"  shot {n}: ffmpeg failed, skipped")
    print(f"  shot {n}: {len(stems)} audio stem(s)", flush=True)

if titles[1]:
    card = build_card(titles[1], shape, tmp / "card-end.mp4")
    if card:
        segments.append(card); total_len += CARD_SECONDS
listfile = tmp / "list.txt"
listfile.write_text("".join(f"file '{s}'\n" for s in segments))
(ROOT / "films").mkdir(exist_ok=True)
out = (ROOT / "films" / (args.out or ("selected_film.mp4" if args.selection else f"{args.model}{suffix}_mixed.mp4"))).resolve()
srt_text = "".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(captions, 1))
joined = tmp / "joined.mp4" if args.burn_captions and captions else out
subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", str(joined)],
               check=True, stderr=subprocess.DEVNULL)
if joined != out:                             # draw the captions into the picture (sound is copied as it is)
    srt_tmp = tmp / "captions.srt"
    srt_tmp.write_text(srt_text, encoding="utf-8")
    try:
        subprocess.run([ffmpeg, "-y", "-i", str(joined), "-vf", f"subtitles={srt_tmp.name}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-crf", "18", "-c:a", "copy", str(out)], check=True, stderr=subprocess.DEVNULL, cwd=tmp)
        print("captions drawn into the picture")
    except subprocess.CalledProcessError:
        shutil.move(str(joined), str(out))
        print("captions could not be drawn into the picture (no subtitle font?); the film has the .srt file only")
shutil.rmtree(tmp, ignore_errors=True)
if captions:                                  # subtitles next to the film (same name, .srt): players and editors pick them up
    out.with_suffix(".srt").write_text(srt_text, encoding="utf-8")
    print(f"captions: {len(captions)} line(s) -> {out.with_suffix('.srt').name}")
print(f"mixed {len(segments)} clips, {total_len:.1f}s, stems used {used} → {out}")
