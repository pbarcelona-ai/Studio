#!/usr/bin/env python3
"""Media sources (BOOK_TO_SCREEN_BUILD.md Section 4.2, milestone M13): video and audio as story sources, real footage among the AI shots,
raw-footage auto-edit, and cutting to an uploaded music track.

  python3 media_sources.py <project> <source id> [--engine ... | fake] [--model M]     understand a video / audio source

understand():  shot and scene detection (ffmpeg's scene score), one keyframe per shot, a transcript (Whisper on this computer, when the
               faster-whisper package is there; otherwise the words are left out and the pictures still tell the story), and the Story
               Analyst's account of what happens (one vision call on a contact sheet of the keyframes). The source's text becomes the
               transcript + the account, so Read it in can use it like any other source.
bind():        a clip, a key frame or an audio segment of a source, bound to a character, location, shot or music cue (MEDIA UNDERSTANDING).
use_footage(): the owner's own footage as a real shot of the shot list (source "footage"); the clip of that shot in every style is that
               segment. footage_look() has the Animation / VFX Supervisor describe the footage's look (lens, light, colour) as a note to the
               Cinematographer and the Storyboard Artist, so the AI shots match it.
auto_edit():   "Make a story from my clips": the Editor picks the best moments of the detected shots and orders them into a story, the
               Screenwriter writes narration to tie them together; the result is a shot list of real shots (and their footage), ready for
               the sound plan, the edit and the film.
set_score():   an uploaded track as the film's score; its tempo (estimated here, standard library only) lets the edit snap cuts to its beats.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import re
import subprocess
import sys
import tempfile
import wave
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crew  # noqa: E402
import edl  # noqa: E402
import layout  # noqa: E402
import notes  # noqa: E402
import shot_list  # noqa: E402
import sources  # noqa: E402

SCENE_THRESHOLD = 0.3
MIN_SHOT = 0.6
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm")
Ask = Callable[..., dict]
Transcriber = Callable[[Path], list[dict]]


class MediaError(RuntimeError):
    """A media step cannot be done as asked; the message says why."""


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def duration(path: Path) -> float:
    r = subprocess.run([ffmpeg(), "-i", str(path)], capture_output=True, text=True, errors="replace", check=False)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    if not m:
        raise MediaError(f"{path.name} is not a video or sound file ffmpeg can read")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def has_video(path: Path) -> bool:
    r = subprocess.run([ffmpeg(), "-i", str(path)], capture_output=True, text=True, errors="replace", check=False)
    return "Video:" in r.stderr


def detect_shots(path: Path, threshold: float = SCENE_THRESHOLD) -> list[dict]:
    """[{n, start, end}] cut where the picture changes (ffmpeg's scene score above the threshold); very short pieces join the one before."""
    total = duration(path)
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path), "-vf", f"select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace", check=False)
    cuts = sorted({round(float(t), 3) for t in re.findall(r"pts_time:([\d.]+)", r.stderr)})
    edges = [0.0] + [c for c in cuts if 0 < c < total] + [total]
    shots: list[dict] = []
    for a, b in zip(edges, edges[1:], strict=False):
        if shots and b - a < MIN_SHOT:
            shots[-1]["end"] = round(b, 3)
            continue
        shots.append({"n": len(shots) + 1, "start": round(a, 3), "end": round(b, 3)})
    return shots


def keyframe(path: Path, at: float, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{max(0.0, at):.3f}", "-i", str(path), "-frames:v", "1", "-vf", "scale=640:-2", str(dest)], check=True)
    return dest


def contact_sheet(frames: list[Path], dest: Path, cols: int = 4) -> Path:
    from PIL import Image, ImageDraw
    cells = [Image.open(f).convert("RGB") for f in frames[:24]]
    w, h = 320, 180
    rows = max(1, math.ceil(len(cells) / cols))
    sheet = Image.new("RGB", (cols * w, rows * h), (20, 20, 20))
    draw = ImageDraw.Draw(sheet)
    for i, im in enumerate(cells):
        im.thumbnail((w, h))
        x, y = (i % cols) * w, (i // cols) * h
        sheet.paste(im, (x, y))
        draw.text((x + 6, y + 4), str(i + 1), fill=(255, 230, 0))
    sheet.save(dest)
    return dest


def whisper_transcriber() -> Transcriber | None:
    """Whisper on this computer (faster-whisper, small model), or None when it is not installed."""
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        return None
    model = WhisperModel("small", device="cpu", compute_type="int8")

    def run(path: Path) -> list[dict]:
        segs, _ = model.transcribe(str(path))
        return [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segs]
    return run


def check_account(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("shots"), list) or not str(d.get("story", "")).strip():
        raise ValueError('reply with {"shots": [{"n": 1, "what": "..."}], "story": "...", "characters": [...]}')


def _source(pdir: Path, sid: str) -> tuple[dict, Path]:
    s = sources.get(pdir, sid)
    if s["kind"] != "media" or not s.get("media"):
        raise MediaError("that source is not a video or sound file")
    return s, pdir / s["media"][0]


def understand(pdir: Path, sid: str, ask: Ask, transcribe: Transcriber | None = None, say: Callable[[str], None] = print) -> dict:
    s, f = _source(pdir, sid)
    out_dir = sources.folder(pdir) / sid
    words: list[dict] = []
    say("Your editor is finding the shots")
    video = has_video(f)
    shots: list[dict] = detect_shots(f) if video else [{"n": 1, "start": 0.0, "end": round(duration(f), 3)}]
    if transcribe is not None:
        say("Your story analyst is listening (transcribing)")
        words = transcribe(f)
    account: dict = {"shots": [], "story": "", "characters": []}
    if video:
        say(f"Your story analyst is watching {len(shots)} shot(s)")
        frames = [keyframe(f, (x["start"] + x["end"]) / 2, out_dir / "keyframes" / f"shot-{x['n']:03d}.jpg") for x in shots]
        for x, fr in zip(shots, frames, strict=True):
            x["keyframe"] = fr.relative_to(pdir).as_posix()
        sheet = contact_sheet(frames, out_dir / "contact_sheet.jpg")
        said = "\n".join(f"[{w['start']:.1f}-{w['end']:.1f}] {w['text']}" for w in words)[:8000]
        account = ask("These are the key frames of a video, numbered in order (one per shot). Say what happens in each shot, then the story the "
                      "video tells, and who is in it. " + (f"What is said:\n{said}\n" if said else "") +
                      'Reply as JSON: {"shots": [{"n": 1, "what": "..."}], "story": "...", "characters": [{"name": "...", "look": "..."}]}',
                      "story_analyst", "media: what happens", check_account, image=str(sheet))
        what = {int(a["n"]): str(a.get("what", "")) for a in account["shots"] if isinstance(a, dict) and isinstance(a.get("n"), int)}
        for x in shots:
            x["what"] = what.get(x["n"], "")
    for x in shots:
        x["words"] = " ".join(w["text"] for w in words if w["start"] < x["end"] and w["end"] > x["start"])
    lines = [f"Shot {x['n']} ({x['start']:.1f}-{x['end']:.1f} s): {x.get('what', '')}" + (f' — "{x["words"]}"' if x["words"] else "")
             for x in shots if x.get("what") or x["words"]]
    text = "\n\n".join(filter(None, [account.get("story", ""), "\n".join(lines)]))
    if not text.strip():
        text = "(a sound file with no transcript: install faster-whisper to read its words)"
    (out_dir / "understanding.json").write_text(json.dumps({"shots": shots, "transcript": words, "account": account}, indent=1, ensure_ascii=False), encoding="utf-8")
    sources.set_text(pdir, sid, text, described=True, extra={"transcribed": bool(words), "shots": len(shots), "video": video,
                                                             "characters": account.get("characters", [])[:20]})
    return {"shots": shots, "transcript": len(words)}


def understanding(pdir: Path, sid: str) -> dict:
    try:
        return json.loads((sources.folder(pdir) / sid / "understanding.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def cut_segment(src: Path, start: float, end: float, dest: Path, audio_only: bool = False) -> Path:
    if not 0 <= start < end:
        raise MediaError("a segment needs a start before its end")
    dest.parent.mkdir(parents=True, exist_ok=True)
    argv = [ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(src)]
    argv += ["-vn", "-c:a", "pcm_s16le"] if audio_only else ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"]
    subprocess.run([*argv, str(dest)], check=True)
    return dest


BIND_KINDS = ("character", "location", "shot", "music")


def bind(pdir: Path, sid: str, start: float, end: float, what: str, kind: str, target: str) -> dict:
    """Bind a clip ("clip"), a key frame ("frame", at start) or an audio segment ("audio") to a character, location, shot or music cue."""
    if kind not in BIND_KINDS or what not in ("clip", "frame", "audio") or not target.strip():
        raise MediaError(f"bind a clip, frame or audio segment to a {', '.join(BIND_KINDS)}")
    _, f = _source(pdir, sid)
    d = sources.folder(pdir) / sid / "bound"
    name = f"{what}-{kind}-{re.sub(r'[^a-z0-9]+', '_', target.lower()).strip('_')[:30]}-{round(start * 1000)}"
    if what == "frame":
        out = keyframe(f, start, d / f"{name}.png")
    else:
        out = cut_segment(f, start, end, d / f"{name}.{'wav' if what == 'audio' else 'mp4'}", audio_only=what == "audio")
    bfile = sources.folder(pdir) / sid / "bindings.json"
    items = json.loads(bfile.read_text(encoding="utf-8")) if bfile.is_file() else []
    item = {"what": what, "kind": kind, "target": target.strip(), "start": start, "end": end, "file": out.relative_to(pdir).as_posix()}
    items.append(item)
    bfile.write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
    return item


def bindings(pdir: Path) -> list[dict]:
    out = []
    for s in sources.load_index(pdir):
        f = sources.folder(pdir) / s["id"] / "bindings.json"
        if f.is_file():
            out += [{**b, "source": s["id"]} for b in json.loads(f.read_text(encoding="utf-8"))]
    return out


# ---------------------------------------------------------------------------------------------- real footage among the AI shots
def footage_path(pdir: Path) -> Path:
    return pdir / "shots" / "footage.json"


def footage(pdir: Path) -> dict[str, str]:
    """{row: clip path under the book} for the shots made from the owner's footage."""
    try:
        return json.loads(footage_path(pdir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def row_of(pdir: Path, scene: str, n: int) -> int:
    row = 0
    for sc in shot_list.load(pdir).get("scenes", []):
        for s in sc["shots"]:
            row += 1
            if sc["id"] == scene and s["n"] == n:
                return row
    raise MediaError("no such shot in the shot list")


def use_footage(pdir: Path, scene: str, n: int, sid: str, start: float, end: float) -> dict:
    """Make a shot of the shot list a real shot: its clip (in every style) is this segment of the owner's footage."""
    _, f = _source(pdir, sid)
    row = row_of(pdir, scene, n)
    clip = cut_segment(f, start, end, pdir / "footage" / f"shot-{row:04d}.mp4")
    shot_list.edit_shot(pdir, scene, n, {"source": "footage", "seconds": round(min(60.0, max(1.5, end - start)), 1)})
    fm = footage(pdir)
    fm[str(row)] = clip.relative_to(pdir).as_posix()
    footage_path(pdir).parent.mkdir(parents=True, exist_ok=True)
    footage_path(pdir).write_text(json.dumps(fm, indent=1), encoding="utf-8")
    return {"row": row, "clip": fm[str(row)]}


def check_look(d) -> None:
    if not isinstance(d, dict) or not all(str(d.get(k, "")).strip() for k in ("lens", "lighting", "colour")):
        raise ValueError('reply with {"lens": "...", "lighting": "...", "colour": "...", "notes": "..."}')


def footage_look(pdir: Path, sid: str, ask: Ask) -> dict:
    """The Animation / VFX Supervisor describes the footage's look; it becomes notes to the Cinematographer and the Storyboard Artist."""
    sheet = sources.folder(pdir) / sid / "contact_sheet.jpg"
    if not sheet.is_file():
        raise MediaError("understand the video first (it makes the contact sheet)")
    d = ask("These frames are the owner's real footage. Describe its look so AI shots can be cut together with it: the lens (focal length, depth "
            'of field), the lighting, the colour (palette, grade, grain). Reply as JSON: {"lens": "...", "lighting": "...", "colour": "...", "notes": "..."}',
            "animation_supervisor", "media: footage look", check_look, image=str(sheet))
    text = f"Match the real footage: lens {d['lens']}; lighting {d['lighting']}; colour {d['colour']}. {d.get('notes', '')}".strip()
    for role in ("cinematographer", "storyboard_artist"):
        notes.add(pdir, "project", f"footage {sid}", text, role, who="animation_supervisor")
    return d


# ---------------------------------------------------------------------------------------------- "Make a story from my clips"
def check_edit(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("moments"), list) or not d["moments"]:
        raise ValueError('reply with {"moments": [{"source": "s001", "shot": 1, "narration": "..."}], "title": "..."}')
    for m in d["moments"]:
        if not isinstance(m, dict) or not isinstance(m.get("shot"), int) or not str(m.get("source", "")).strip():
            raise ValueError("every moment names its source id and shot number")


def auto_edit(pdir: Path, ask: Ask, say: Callable[[str], None] = print) -> dict:
    """The Editor picks and orders the best moments of every understood video; the Screenwriter's narration ties them together. Writes a
    shot list of real shots (one scene per source) and their footage, ready for the sound plan, the edit and the film."""
    found = {s["id"]: understanding(pdir, s["id"]) for s in sources.load_index(pdir) if s["kind"] == "media"}
    found = {k: v for k, v in found.items() if v.get("shots") and any(x.get("keyframe") for x in v["shots"])}
    if not found:
        raise MediaError("understand at least one video source first")
    listing = "\n".join(f"{sid} shot {x['n']} ({x['end'] - x['start']:.1f} s): {x.get('what', '')} {x.get('words', '')}" for sid, u in found.items() for x in u["shots"])
    say("Your editor is choosing the best moments, your screenwriter is writing the narration")
    d = ask("Make a story from these clips: pick the best moments, order them into a story with smart cuts, and write a line of narration for "
            'each moment that ties them together. Reply as JSON: {"title": "...", "moments": [{"source": "s001", "shot": 3, "narration": "..."}]}\n\n'
            + listing, ["editor", "screenwriter"], "media: auto-edit", check_edit)
    scenes, fm, row = [], {}, 0
    by_source: dict[str, list[dict]] = {}
    for m in d["moments"]:
        u = found.get(str(m["source"]))
        x = next((s for s in (u or {}).get("shots", []) if s["n"] == m["shot"]), None)
        if x is None:
            continue
        by_source.setdefault(str(m["source"]), []).append({**x, "narration": str(m.get("narration", ""))})
    for i, (sid, moments) in enumerate(by_source.items(), 1):
        shots = []
        _, f = _source(pdir, sid)
        for k, x in enumerate(moments, 1):
            row += 1
            clip = cut_segment(f, x["start"], x["end"], pdir / "footage" / f"shot-{row:04d}.mp4")
            fm[str(row)] = clip.relative_to(pdir).as_posix()
            shots.append(shot_list.clean_shot({"type": "MS", "lens_mm": 35, "height": "eye", "movement": "static", "action": x.get("what") or f"moment {x['n']}",
                                               "dialogue": f"NARRATOR: {x['narration']}" if x["narration"] else "", "seconds": round(min(60.0, max(1.5, x["end"] - x["start"])), 1),
                                               "transition": "cut", "priority": 1, "source": "footage"}, k))
        scenes.append({"id": f"S{i:03d}", "heading": f"EXT. FOOTAGE {i} - DAY", "breakdown": {"intent": d.get("title", ""), "emotional_beat": "", "blocking": "", "performance": ""},
                       "shots": shots, "target_seconds": sum(s["seconds"] for s in shots)})
    if not scenes:
        raise MediaError("the editor chose no usable moments")
    data = {"scenes": scenes, "target_seconds": sum(sc["target_seconds"] for sc in scenes), "checks": {}, "from_footage": True, "title": d.get("title", "")}
    shot_list.save(pdir, data)
    footage_path(pdir).write_text(json.dumps(fm, indent=1), encoding="utf-8")
    return {"scenes": len(scenes), "shots": row, "title": d.get("title", "")}


# ---------------------------------------------------------------------------------------------- an uploaded track as the score
def tempo(wav: Path) -> float:
    """The beats per minute of a WAV file, from the autocorrelation of its loudness envelope (standard library only; 60-180 bpm)."""
    with wave.open(str(wav)) as w:
        rate, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(min(n, rate * 60))
    if width != 2:
        raise MediaError("the music must be 16-bit WAV (convert it first)")
    samples = array.array("h", raw)
    hop = max(1, rate // 100)                               # a 10 ms envelope
    env = []
    for i in range(0, len(samples) - hop * ch, hop * ch):
        seg = samples[i:i + hop * ch:ch]
        env.append(sum(abs(v) for v in seg) / len(seg))
    diff = [max(0.0, b - a) for a, b in zip(env, env[1:], strict=False)]
    best, best_lag = 0.0, 0
    for bpm in range(60, 181):
        lag = round(6000 / bpm)
        if lag >= len(diff):
            continue
        c = sum(diff[i] * diff[i + lag] for i in range(len(diff) - lag)) / (len(diff) - lag)
        if c > best:
            best, best_lag = c, lag
    return round(6000 / best_lag, 1) if best_lag else 0.0


def set_score(pdir: Path, sid: str) -> dict:
    """The track becomes the score of the current cut: one music item over the whole film, at its tempo, so the edit can snap to its beats."""
    s, f = _source(pdir, sid)
    with tempfile.TemporaryDirectory() as t:
        wav = Path(t) / "score.wav"
        subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(f), "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le", str(wav)], check=True)
        bpm = tempo(wav)
        dest = pdir / "audio" / "score" / "score.wav"
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(f), "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(dest)], check=True)
    d = edl.load(pdir) or edl.assemble(pdir)
    c = edl.cut(d)
    first = c["tracks"]["video"][0]["scene"] if c["tracks"]["video"] else "S001"
    c["tracks"]["music"] = [{"id": "m-score", "attach": first, "offset": 0.0, "seconds": None, "volume": 1.0, "ref": 0, "tempo_bpm": bpm or None,
                             "text": f"score: {s['title']}", "file": dest.relative_to(pdir).as_posix(), "whole": True}]
    edl.save(pdir, d)
    return {"tempo_bpm": bpm, "file": dest.relative_to(pdir).as_posix()}


def fake_ask() -> Ask:
    def ask(prompt: str, roles, step: str, validate: Callable[[dict], None], image: str = "") -> dict:
        if step == "media: what happens":
            d: dict = {"shots": [{"n": i, "what": f"something happens in shot {i}"} for i in range(1, 25)], "story": "A day at the sea.",
                       "characters": [{"name": "MARA", "look": "red coat"}]}
        elif step == "media: footage look":
            d = {"lens": "35 mm, deep focus", "lighting": "soft overcast daylight", "colour": "muted greens, light grain", "notes": "handheld"}
        else:
            picks = [(m.group(1), int(m.group(2))) for m in re.finditer(r"^(s\d{3}) shot (\d+)", prompt, re.M)]
            d = {"title": "The sea", "moments": [{"source": s, "shot": n, "narration": f"Moment {k}."} for k, (s, n) in enumerate(picks, 1)]}
        validate(d)
        return d
    return ask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("source")
    ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex", "fake"])
    ap.add_argument("--model", default=None)
    a = ap.parse_args(argv)
    pdir = layout.project_dir(a.project, "book")
    if a.engine == "fake":
        ask = fake_ask()
    else:
        import bookkit

        def ask(prompt, roles, step, validate, image=None):
            return bookkit.llm_json(prompt, crew.system(roles, pdir, step), model=a.model, engine=a.engine, validate=validate, image=image)
    try:
        out = understand(pdir, a.source, ask, whisper_transcriber(), lambda t: print(t, flush=True))
        print(f"Done: {len(out['shots'])} shot(s), {out['transcript']} transcript line(s).", flush=True)
    except (MediaError, sources.SourceError, RuntimeError, ValueError, subprocess.CalledProcessError) as e:
        print(f"The video was not understood: {e}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
