#!/usr/bin/env python3
"""Mix narration, sound effects and music onto the generated clips and join them into one film.

Usage:
  uv run --with imageio-ffmpeg python mix_film.py [--project adam_eve] --model ltx_video [--chapters] [--start 1 --end 40]
        [--sync stretch|gentle|speed|trim] [--out film.mp4]
        [--vol-narration 1.0 --vol-sfx 0.5 --vol-music 0.25] [--transition cut|fade --fade 0.5] [--burn-captions]
        [--no-duck] [--no-loudnorm] [--music-bed] [--match-colour]

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
--transition dissolve  each clip melts into the next over --fade seconds, picture and sound; the film gets shorter by that much at each join.
--match-colour  nudges each clip's brightness and colour halfway towards the chapter's typical clip, so shots of one chapter sit together; it does not
                make chapters look alike, and a limit keeps a deliberately dark shot from being lifted far.
--burn-captions    also draws the narration captions into the picture (the .srt is written either way).

--sync decides what happens when narration is longer than the clip:
  stretch  slow the clip (up to 2x) and hold the last frame so the whole narration plays (default)
  gentle   the same, but slow the clip by at most 1.25x, so motion still looks natural, and hold the last frame for the rest
  speed    keep the clip length and speed the narration up (up to 3x)
  trim     keep the clip length and cut the audio at the end of the clip

Sound: music dips under the narration (--no-duck turns that off), and the finished film is brought to -16 LUFS, the usual level for online
video, with peaks kept under -1.5 dB (--no-loudnorm turns that off).
--music-bed  one continuous score instead of a new piece of music for every shot: each chapter's cue from audio/musicgen_chapters/music-NNNN.wav
             (NNNN = the chapter's row in audio_chapters.csv) loops with soft joins under all of that chapter's shots. The shots' own music is not used.
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--project", default="adam_eve")
ap.add_argument("--model", default="ltx_video")
ap.add_argument("--models", default=None, help="several video folders, comma-separated, best first: each shot uses the first folder that has it, all brought to one size")
ap.add_argument("--chapters", action="store_true", help="use the *_chapters folders (one clip per chapter)")
ap.add_argument("--start", type=int, default=1)
ap.add_argument("--end", type=int, default=10**9)
ap.add_argument("--sync", choices=["stretch", "gentle", "speed", "trim"], default="stretch")
ap.add_argument("--out", default=None)
ap.add_argument("--vol-narration", type=float, default=1.0)
ap.add_argument("--vol-sfx", type=float, default=0.5)
ap.add_argument("--vol-music", type=float, default=0.25)
ap.add_argument("--selection", default=None, help="JSON file listing exactly which clips and audio files to use")
ap.add_argument("--pad", type=float, default=0.4, help="seconds of silence after narration in stretch mode")
ap.add_argument("--transition", choices=["cut", "fade", "dissolve"], default="cut")
ap.add_argument("--match-colour", action="store_true", help="nudge each clip's brightness and colour towards the chapter's typical clip")
ap.add_argument("--fade", type=float, default=0.5, help="fade length in seconds with --transition fade (0.1-1.5)")
ap.add_argument("--burn-captions", action="store_true", help="draw the captions into the picture")
ap.add_argument("--no-duck", action="store_true", help="leave the music at the same level under narration")
ap.add_argument("--no-loudnorm", action="store_true", help="leave the film's overall loudness as mixed")
ap.add_argument("--music-bed", action="store_true", help="one continuous cue per chapter under the shots, instead of each shot's own music")
args = ap.parse_args()
if args.music_bed and args.chapters:
    sys.exit("--music-bed is for films made shot by shot; with --chapters each chapter already has its own music")
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


def colour_of(path):
    """(mean Y, U, V) of a clip on the 0-255 scale, from about two frames a second, or None if it cannot be read."""
    r = subprocess.run([ffmpeg, "-i", str(path), "-vf", "select='not(mod(n,12))',signalstats,metadata=print:file=-", "-an", "-f", "null", "-"], capture_output=True, text=True)
    out = []
    for key in ("YAVG", "UAVG", "VAVG"):
        vals = [float(x) for x in re.findall(rf"lavfi\.signalstats\.{key}=([\d.]+)", r.stdout)]
        if not vals:
            return None
        out.append(sum(vals) / len(vals))
    return tuple(out)


def colour_nudges(plan):
    """{row: lutyuv filter} moving each clip halfway towards its chapter's median colour, limited to 15 steps of brightness and 8 of colour."""
    import csv
    import statistics
    try:
        with open(ROOT / "audio_shots.csv", newline="", encoding="utf-8") as fh:
            chapter_of = [r.get("chapter", "") for r in csv.DictReader(fh)]
    except OSError:
        chapter_of = []
    groups = {}
    for n, video, _, _ in plan:
        c = colour_of(video)
        if c:
            groups.setdefault(chapter_of[n - 1] if 0 < n <= len(chapter_of) else "", []).append((n, c))
    out = {}
    for rows in groups.values():
        if len(rows) < 2:
            continue
        mid = [statistics.median(c[i] for _, c in rows) for i in range(3)]
        for n, c in rows:
            d = [max(-lim, min(lim, (mid[i] - c[i]) / 2)) for i, lim in enumerate((15, 8, 8))]
            if max(abs(x) for x in d) >= 0.5:
                out[n] = f"lutyuv=y=clipval+({d[0]:.2f}):u=clipval+({d[1]:.2f}):v=clipval+({d[2]:.2f}),"
    return out


def dissolve_join(parts, lengths, fade, out):
    """Join segments so each melts into the next. Returns the seconds of overlap used (shortened to suit the shortest clip)."""
    d = min(fade, min(lengths) / 2.5)
    w, h, fps = video_shape(parts[0])
    cmd = [ffmpeg, "-y", "-loglevel", "error"]
    for p in parts:
        cmd += ["-i", str(p)]
    fc = [f"[{i}:v]fps={fps:g},settb=AVTB,format=yuv420p[v{i}];[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{i}]" for i in range(len(parts))]
    vlast, alast, at = "[v0]", "[a0]", lengths[0]
    for i in range(1, len(parts)):
        fc.append(f"{vlast}[v{i}]xfade=transition=fade:duration={d:.3f}:offset={at - d:.3f}[vx{i}]")
        fc.append(f"{alast}[a{i}]acrossfade=d={d:.3f}[ax{i}]")
        vlast, alast, at = f"[vx{i}]", f"[ax{i}]", at + lengths[i] - d
    subprocess.run(cmd + ["-filter_complex", ";".join(fc), "-map", vlast, "-map", alast, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(out)],
                   check=True, capture_output=True)
    return d


SAME_SHAPE = ""      # filter text that brings clips of different models to one size and frame rate (--models)


def build_segment(i, video, stems, out, trim_start=0.0, trim_end=0.0):
    full = duration(video)
    trim_start = min(max(trim_start, 0.0), max(full - 0.5, 0.0))
    vd = max(full - trim_start - max(trim_end, 0.0), 0.5)               # at least half a second of picture is kept
    nd = next((d for n, _, d in stems if n == "narration"), 0.0)
    video_filter, narr_tempo, total = "null", None, vd
    if args.sync in ("stretch", "gentle") and nd + args.pad > vd:
        total = nd + args.pad
        slow = min(total / vd, 2.0 if args.sync == "stretch" else 1.25)
        hold = total - vd * slow
        video_filter = f"setpts={slow:.4f}*PTS" + (f",tpad=stop_mode=clone:stop_duration={hold:.3f}" if hold > 0.01 else "")
    elif args.sync == "speed" and nd > vd - 0.2:
        narr_tempo = min(nd / max(vd - 0.2, 0.5), 3.0)

    cmd = [ffmpeg, "-y", "-i", str(video), "-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
    for _, path, _ in stems:
        cmd += ["-i", str(path)]
    fade = min(args.fade, total / 3) if args.transition == "fade" else 0.0
    vfade = f",fade=t=in:st=0:d={fade:.3f},fade=t=out:st={total - fade:.3f}:d={fade:.3f}" if fade else ""
    fc = [f"[0:v]{NUDGES.get(i, '')}trim=start={trim_start:.3f}:duration={vd:.3f},setpts=PTS-STARTPTS,{video_filter},trim=0:{total:.3f},setpts=PTS-STARTPTS{SAME_SHAPE}{vfade}[v]",
          "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[a0]"]
    labels = ["[a0]"]
    duck = not args.no_duck and {"narration", "music"} <= {n for n, _, _ in stems}
    narr_input = next((k for k, (n, _, _) in enumerate(stems, start=2) if n == "narration"), None)
    music_input = next((k for k, (n, _, _) in enumerate(stems, start=2) if n == "music"), None)
    for k, (name, path, _) in enumerate(stems, start=2):
        vol = {"narration": args.vol_narration, "sfx": args.vol_sfx, "music": args.vol_music}[name]
        chain = ["aformat=sample_rates=44100:channel_layouts=stereo", f"volume={vol}"]
        if name == "narration" and narr_tempo:
            chain.append(atempo_chain(narr_tempo))
        if name in ("sfx", "music"):
            chain += ["afade=t=in:d=0.5", f"afade=t=out:st={max(total - 0.8, 0):.3f}:d=0.8"]
        chain += ["apad", f"atrim=0:{total:.3f}"]
        fc.append(f"[{k}:a]{','.join(chain)}[a{k}]")
        labels.append(f"[a{k}]")
    if duck:                    # the narration, split off, pushes the music down while it is speaking
        at = next(i for i, x in enumerate(fc) if x.endswith(f"[a{narr_input}]"))
        fc[at] = fc[at].removesuffix(f"[a{narr_input}]") + f",asplit=2[a{narr_input}][key]"
        fc.append(f"[a{music_input}][key]{DUCK}[ducked]")
        labels[labels.index(f"[a{music_input}]")] = "[ducked]"
    afade = f",afade=t=in:d={fade:.3f},afade=t=out:st={total - fade:.3f}:d={fade:.3f}" if fade else ""
    fc.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,atrim=0:{total:.3f}{afade}[a]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(out)]
    subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
    return total


DUCK = "sidechaincompress=threshold=0.015:ratio=6:attack=30:release=500"


def looped(cue, seconds, out, overlap=2.0):
    """A cue repeated with soft joins until it lasts `seconds`, faded at both ends. Returns False if the cue is too short or ffmpeg fails."""
    length = duration(cue)
    if length <= overlap * 2:
        return False
    copies = 1
    while length + (copies - 1) * (length - overlap) < seconds:
        copies += 1
    cmd = [ffmpeg, "-y", "-loglevel", "error"]
    for _ in range(copies):
        cmd += ["-i", str(cue)]
    chain = [f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[c{i}]" for i in range(copies)]
    last = "[c0]"
    for i in range(1, copies):
        chain.append(f"{last}[c{i}]acrossfade=d={overlap}[x{i}]")
        last = f"[x{i}]"
    fade = min(1.5, seconds / 4)
    chain.append(f"{last}atrim=0:{seconds:.3f},afade=t=in:d={fade:.3f},afade=t=out:st={seconds - fade:.3f}:d={fade:.3f}[out]")
    r = subprocess.run(cmd + ["-filter_complex", ";".join(chain), "-map", "[out]", str(out)], capture_output=True, text=True)
    return r.returncode == 0


def chapter_spans(timed):
    """[(chapter row in audio_chapters.csv, start, seconds)] for the film, from its [(row, start, seconds)] in film order: one span per run of shots of a chapter."""
    import csv
    try:
        with open(ROOT / "audio_shots.csv", newline="", encoding="utf-8") as fh:
            chapter_of = [r.get("chapter", "") for r in csv.DictReader(fh)]
        with open(ROOT / "audio_chapters.csv", newline="", encoding="utf-8") as fh:
            cue_row = {r.get("chapter", ""): i for i, r in enumerate(csv.DictReader(fh), 1)}
    except OSError:
        return []
    spans = []
    for n, start, secs in timed:
        cue = cue_row.get(chapter_of[n - 1]) if 0 < n <= len(chapter_of) else None
        if spans and spans[-1][0] == cue:
            spans[-1][2] += secs
        else:
            spans.append([cue, start, secs])
    return [tuple(s) for s in spans if s[0]]


def finish_audio(src, dst, spans):
    """The film with its music bed laid under the sound, ducked, and its loudness set; the picture is copied. Returns False if ffmpeg fails."""
    cmd, fc, beds = [ffmpeg, "-y", "-loglevel", "error", "-i", str(src)], [], []
    k = 1
    for cue_file, start, secs in spans:
        cmd += ["-i", str(cue_file)]
        ms = round(start * 1000)
        fc.append(f"[{k}:a]volume={args.vol_music},adelay={ms}|{ms}[b{k}]")
        beds.append(f"[b{k}]")
        k += 1
    last = "[0:a]"
    if beds:
        fc.append("".join(beds) + (f"amix=inputs={len(beds)}:normalize=0:duration=longest[bed]" if len(beds) > 1 else "anull[bed]"))
        if args.no_duck:
            fc.append("[0:a][bed]amix=inputs=2:normalize=0:duration=first[mixed]")
        else:
            fc.append("[0:a]asplit=2[main][key]")
            fc.append(f"[bed][key]{DUCK}[ducked]")
            fc.append("[main][ducked]amix=inputs=2:normalize=0:duration=first[mixed]")
        last = "[mixed]"
    if not args.no_loudnorm:
        fc.append(f"{last}loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100[final]")
        last = "[final]"
    cmd += ["-filter_complex", ";".join(fc), "-map", "0:v", "-map", last, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print("  sound finishing failed, keeping the plain mix: " + r.stderr.strip()[-300:])
    return r.returncode == 0


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
    folders = [ROOT / "videos" / f"{m.strip()}{suffix}" for m in args.models.split(",") if m.strip()] if args.models else [VIDEO_DIR]
    found = {}
    for folder in folders:                       # best first: a shot keeps the first clip found for it
        for p in folder.glob("shot-*.mp4"):
            found.setdefault(int(p.stem.split("-")[1]), p)
    clips = sorted((n, p) for n, p in found.items() if args.start <= n <= args.end)
    if args.models and clips:
        shapes = {video_shape(p)[:2] for _, p in clips}
        if len(shapes) > 1:
            w, h = max(shapes)
            SAME_SHAPE = f",scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24"
            print(f"clips of {len(shapes)} sizes brought to {w}x{h}", flush=True)
        gaps = [n for n in range(clips[0][0], clips[-1][0] + 1) if n not in found]
        if gaps:
            print(f"no clip yet for row(s) {gaps}: the film skips them; run it again once they exist", flush=True)
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
NUDGES = colour_nudges(plan) if args.match_colour else {}
if args.match_colour:
    print(f"colour: {len(NUDGES)} clip(s) nudged towards their chapter's typical clip", flush=True)
segments, seg_lens, used = [], [], {"narration": 0, "sfx": 0, "music": 0}
timed = []                      # (row, index of its segment, seconds), for the music bed
captions, lines = [], narration_lines()
shape = video_shape(plan[0][1]) if any(titles) else None
if titles[0]:
    card = build_card(titles[0], shape, tmp / "card-open.mp4")
    if card:
        segments.append(card); seg_lens.append(CARD_SECONDS)
for k, (n, video, files, trims) in enumerate(plan):
    stems = []
    for name, f in files:
        if name == "music" and args.music_bed:      # the chapter's cue plays instead
            continue
        stems.append((name, f, duration(f))); used[name] += 1
    seg = tmp / f"seg-{k:04d}-{n:04d}.mp4"
    try:
        seg_len = build_segment(n, video, stems, seg, *trims)
        text = lines[n - 1] if 0 < n <= len(lines) else ""
        if text and any(k == "narration" for k, _, _ in stems):          # a caption only where the narration is actually heard
            captions.append((len(segments), seg_len - 0.1, text))
        timed.append((n, len(segments), seg_len))
        segments.append(seg); seg_lens.append(seg_len)
    except subprocess.CalledProcessError:
        print(f"  shot {n}: ffmpeg failed, skipped")
    print(f"  shot {n}: {len(stems)} audio stem(s)", flush=True)

if titles[1]:
    card = build_card(titles[1], shape, tmp / "card-end.mp4")
    if card:
        segments.append(card); seg_lens.append(CARD_SECONDS)
listfile = tmp / "list.txt"
listfile.write_text("".join(f"file '{s}'\n" for s in segments))
(ROOT / "films").mkdir(exist_ok=True)
out = (ROOT / "films" / (args.out or ("selected_film.mp4" if args.selection else f"{args.model}{suffix}_mixed.mp4"))).resolve()
burn = args.burn_captions and bool(captions)
finishing = args.music_bed or not args.no_loudnorm
joined = tmp / "joined.mp4" if burn or finishing else out
overlap = 0.0
if args.transition == "dissolve" and len(segments) > 1:
    try:
        overlap = dissolve_join(segments, seg_lens, args.fade, joined)
    except subprocess.CalledProcessError as e:        # for example clips of different sizes: join them plainly rather than lose the film
        print("  dissolve failed, joining with cuts: " + (e.stderr or b"").decode(errors="replace").strip()[-300:])
if not overlap:
    subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", str(joined)],
                   check=True, stderr=subprocess.DEVNULL)
starts, total_len = [], 0.0
for length in seg_lens:                       # where each segment begins in the film, and how long the film is
    starts.append(total_len)
    total_len += length - overlap
total_len += overlap
captions = [(starts[s], starts[s] + secs, t) for s, secs, t in captions]
timed = [(n, starts[s], secs) for n, s, secs in timed]
srt_text = "".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(captions, 1))
if finishing:
    beds = []
    if args.music_bed:
        for cue, start, secs in chapter_spans(timed):
            cue_file = ROOT / "audio" / "musicgen_chapters" / f"music-{cue:04d}.wav"
            bed = tmp / f"bed-{len(beds):03d}.wav"
            if cue_file.is_file() and looped(cue_file, secs, bed):
                beds.append((bed, start, secs))
                used["music"] += 1
            else:
                print(f"  no usable music cue for chapter row {cue} ({cue_file.name}): that part has no music")
    finished = tmp / "finished.mp4"
    if finish_audio(joined, finished, beds):
        joined = finished
    if not burn:
        shutil.move(str(joined), str(out))
if burn:                                      # draw the captions into the picture (sound is copied as it is)
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
