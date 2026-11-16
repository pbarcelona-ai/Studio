#!/usr/bin/env python3
"""Render a cut of the shared EDL in one style (BOOK_TO_SCREEN_BUILD.md Section 13; milestones M10 and M11).

  python3 render_cut.py <project> <style> [--kind animatic|film] [--cut NAME] [--size 1920x1080] [--subtitles]

  animatic (Product D): each shot's approved picture of that style, held for its clip's length with a slow Ken Burns push-in
  film     (Product E): each shot's clip of that style (clips.py: the style's image-to-video set, videos/<model>/shot-NNNN.mp4), trimmed to the EDL
Both: the cut's order, lengths and transitions (a crossfade on every dissolve); the voice track at its times; the music, ducked by the
cut's duck_db (12 dB) under speech; the effects; every track's and item's volume; the style card's colour grade; H.264 + AAC, 24 fps.
Writes exports/<kind>_<style>[_<cut>].mp4 and the matching .srt (subtitles burned in with --subtitles). The same EDL makes every style, so
every style's cut is identical in timing. ffmpeg (imageio-ffmpeg) runs without a shell; the filter graph goes in a file, so long films work on
Windows too.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edl  # noqa: E402
import grade  # noqa: E402
import layout  # noqa: E402
import pictures  # noqa: E402
import styles  # noqa: E402

FPS = 24
GRADE_WORDS = (("noir", "noir"), ("black-and-white", "noir"), ("black and white", "noir"), ("desaturat", "desaturated"), ("muted", "desaturated"),
               ("faded", "faded"), ("pastel", "faded"), ("vivid", "vivid"), ("saturated", "vivid"), ("warm", "warm"), ("amber", "warm"),
               ("cool", "cool"), ("teal", "cool"), ("night", "night"))


class RenderError(RuntimeError):
    """The cut cannot be rendered yet; the message says what is missing."""


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


_GRAPH_FLAG: dict[str, list[str]] = {}


def graph_args(ff: str, script: Path) -> list[str]:
    """The filter graph read from a file: "-/filter_complex FILE" on ffmpeg 7 and newer, "-filter_complex_script FILE" before (ffmpeg 8 removed it)."""
    if ff not in _GRAPH_FLAG:
        out = subprocess.run([ff, "-version"], capture_output=True, text=True, check=False).stdout
        m = re.search(r"ffmpeg version n?(\d+)", out)
        _GRAPH_FLAG[ff] = ["-/filter_complex"] if m and int(m.group(1)) >= 7 else ["-filter_complex_script"]
    return [*_GRAPH_FLAG[ff], str(script)]


def grade_filter(pdir: Path, sid: str) -> str:
    """The style card's colour grade as an ffmpeg filter (a grade.py preset chosen from the card's words), or "" for none."""
    try:
        text = (styles.card_of(pdir, sid).get("grade", "") + " " + styles.card_of(pdir, sid).get("palette", "")).lower()
    except styles.StyleError:
        return ""
    preset = next((p for word, p in GRADE_WORDS if word in text), "none")
    return grade.filter_for({"preset": preset}) if preset != "none" else ""


def sources(pdir: Path, sid: str, kind: str, clips: list[dict]) -> dict[str, Path]:
    """Each clip's picture (animatic) or video (film) in this style."""
    out: dict[str, Path] = {}
    missing = []
    if kind == "animatic":
        st = pictures.status(pdir, sid)
        setdir = layout.find_dir(st["set"]) if st["set"] else None
        by = {(s["scene"], s["shot"]): s for s in st["shots"]}
        for v in clips:
            s = by.get((v["scene"], v["shot"]))
            if setdir and s and s["image"]:
                out[v["id"]] = setdir / s["image"]
            else:
                missing.append(f"{v['scene']} shot {v['shot']}")
    else:
        import clips as clipmod
        for v in clips:
            f = clipmod.clip_file(pdir, sid, int(v["row"]))
            if f is not None:
                out[v["id"]] = f
            else:
                missing.append(f"{v['scene']} shot {v['shot']}")
    if missing:
        raise RenderError(f"{len(missing)} shot(s) have no {'picture' if kind == 'animatic' else 'clip'} in this style yet (first: {missing[0]})")
    return out


def audio_files(pdir: Path, tl: dict) -> list[tuple[str, dict, Path]]:
    """(track, item, file) for every voice line, effect and music cue that has been rendered."""
    out = []
    for a in tl["voice"]:
        f = pdir / "audio" / "kokoro" / f"narration-{int(a['ref']):04d}.wav"
        if f.is_file():
            out.append(("voice", a, f))
    for a in tl["effects"]:
        for f in sorted((pdir / "audio").glob(f"*/sfx-{int(a['ref']):04d}.wav")):
            out.append(("effects", a, f))
            break
    for m in tl["music"]:
        if m.get("file") and (pdir / m["file"]).is_file():  # an uploaded score (media_sources.set_score)
            out.append(("music", m, pdir / m["file"]))
            continue
        for name in ("musicgen_scenes", "musicgen"):
            f = pdir / "audio" / name / f"music-{int(m['ref']):04d}.wav"
            if f.is_file():
                out.append(("music", m, f))
                break
    return out


def render(pdir: Path, sid: str, kind: str = "animatic", cut_name: str = "", size: tuple[int, int] = (1920, 1080), subtitles: bool = False) -> Path:
    d = edl.load(pdir) or edl.assemble(pdir)
    c = edl.cut(d, cut_name)
    tl = edl.timeline(c)
    clips = tl["video"]
    if not clips:
        raise RenderError("the cut has no clips")
    src = sources(pdir, sid, kind, clips)
    w, h = size
    g = grade_filter(pdir, sid)
    ff = ffmpeg()
    out_dir = pdir / "exports"
    out_dir.mkdir(exist_ok=True)
    tag = "" if d.get("current", "main") == c["name"] == "main" else "_" + re.sub(r"[^a-z0-9]+", "_", c["name"].lower()).strip("_")
    out = out_dir / f"{kind}_{sid}{tag}.mp4"
    with tempfile.TemporaryDirectory(prefix="studio-render-") as tmp_:
        tmp = Path(tmp_)
        segs = []
        for i, v in enumerate(clips):                        # 1: one silent segment per clip, at the film's size and frame rate
            seg = tmp / f"seg-{i:04d}.mp4"
            secs = v["seconds"]
            frames = max(1, round(secs * FPS))
            look = f",{g}" if g else ""
            if kind == "animatic":
                vf = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
                      f"zoompan=z='min(1+0.0009*on,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={FPS},format=yuv420p{look}")
                cmd = [ff, "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-t", f"{secs:.3f}", "-i", str(src[v["id"]]), "-vf", vf]
            else:
                vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS},format=yuv420p{look}"
                cmd = [ff, "-y", "-loglevel", "error", "-ss", f"{v['trim_in']:.3f}", "-t", f"{secs:.3f}", "-i", str(src[v["id"]]), "-vf", vf]
            subprocess.run([*cmd, "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(seg)], check=True,
                           capture_output=True)
            segs.append(seg)
        # 2: the picture: cuts are joined, dissolves cross-fade (xfade), all in one filter graph written to a file
        fc, inputs = [], []
        for i, s in enumerate(segs):
            inputs += ["-i", str(s)]
            fc.append(f"[{i}:v]settb=AVTB,setpts=PTS-STARTPTS[s{i}]")
        blocks: list[list[int]] = [[0]]
        for i in range(1, len(segs)):
            if clips[i - 1]["transition"]["kind"] == "dissolve":
                blocks.append([i])
            else:
                blocks[-1].append(i)
        for b, idx in enumerate(blocks):
            fc.append("".join(f"[s{i}]" for i in idx) + f"concat=n={len(idx)}:v=1:a=0[b{b}]")
        last, at = "[b0]", sum(clips[i]["seconds"] for i in blocks[0])
        for b in range(1, len(blocks)):
            dur = clips[blocks[b][0] - 1]["transition"]["seconds"]
            dur = min(dur, at / 2, sum(clips[i]["seconds"] for i in blocks[b]) / 2)
            fc.append(f"{last}[b{b}]xfade=transition=fade:duration={dur:.3f}:offset={at - dur:.3f}[x{b}]")
            last = f"[x{b}]"
            at += sum(clips[i]["seconds"] for i in blocks[b]) - dur
        # 3: the sound: each item at its time and volume; the music ducked under speech
        auds = audio_files(pdir, tl)
        base = len(segs)
        mix = []
        speech = [(a["start"], a["end"]) for t, a, _ in auds if t == "voice"]
        duck = 10 ** (-float(c.get("duck_db", 12)) / 20)
        for k, (track, a, f) in enumerate(auds):
            inputs += ["-i", str(f)]
            vol = float(a.get("volume", 1.0)) * float(c["volumes"].get(track, 1.0))
            length = max(0.05, a["end"] - a["start"])
            chain = f"[{base + k}:a]aformat=sample_rates=44100:channel_layouts=stereo,atrim=0:{length:.3f},volume={vol:.3f}"
            if track == "music" and speech:
                spans = "+".join(f"between(t,{max(0.0, s - a['start']):.3f},{e - a['start']:.3f})" for s, e in speech if e > a["start"] and s < a["end"])
                if spans:
                    chain += f",volume={duck:.4f}:enable='{spans}'"
            chain += f",adelay={round(a['start'] * 1000)}:all=1[m{k}]"
            fc.append(chain)
            mix.append(f"[m{k}]")
        total = tl["total"]
        if mix:
            fc.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:dropout_transition=0,apad,atrim=0:{total:.3f}[aud]")
        else:
            fc.append(f"anullsrc=r=44100:cl=stereo,atrim=0:{total:.3f}[aud]")
        vlast = last
        srt_text = edl.srt(c, pdir)
        srt_file = out.with_suffix(".srt")
        srt_file.write_text(srt_text, encoding="utf-8")
        if subtitles and srt_text.strip():
            local = tmp / "subs.srt"
            local.write_text(srt_text, encoding="utf-8")
            fc.append(f"{vlast}subtitles=subs.srt[vs]")
            vlast = "[vs]"
        script = tmp / "graph.txt"
        script.write_text(";\n".join(fc), encoding="utf-8")
        subprocess.run([ff, "-y", "-loglevel", "error", *inputs, *graph_args(ff, script), "-map", vlast, "-map", "[aud]",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k",
                        "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)], check=True, capture_output=True, cwd=tmp)
    (out_dir / f"{out.stem}.json").write_text(json.dumps({"kind": kind, "style": sid, "cut": c["name"], "seconds": total, "clips": len(clips)}), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("style")
    ap.add_argument("--kind", default="animatic", choices=["animatic", "film"])
    ap.add_argument("--cut", default="")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--subtitles", action="store_true")
    a = ap.parse_args(argv)
    m = re.fullmatch(r"(\d{3,4})x(\d{3,4})", a.size)
    if not m:
        print("size is WIDTHxHEIGHT, e.g. 1920x1080", flush=True)
        return 1
    pdir = layout.project_dir(a.project, "book")
    try:
        print(f"Your editor is cutting the {a.kind} in {a.style}", flush=True)
        out = render(pdir, a.style, a.kind, a.cut, (int(m.group(1)), int(m.group(2))), a.subtitles)
        print(f"Done: {out.name}", flush=True)
    except (RenderError, edl.EditError, styles.StyleError) as e:
        print(f"The {a.kind} was not made: {e}", flush=True)
        return 1
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg stopped: {(e.stderr or b'').decode(errors='replace')[-800:]}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
