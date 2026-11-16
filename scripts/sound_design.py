#!/usr/bin/env python3
"""Voices, sound and music, made ONCE and shared by every style, and the audiobook (BOOK_TO_SCREEN_BUILD.md Sections 3.2, 6, 13; milestone M9).

  python3 sound_design.py <project> [--engine claude|... |fake] [--model M]        write the sound plan and the audio CSVs
  python3 sound_design.py <project> --audiobook                                     join the rendered narration into the audiobook

The Voice Director casts a voice for every character from their personality profile and directs each line (emotion -> speed and pause, as
voices.py does for Kokoro) and the audiobook narration; the Sound Designer writes effects and ambience per shot; the Composer writes the music
cues (mood, tempo, instrumentation, where each starts and ends). Results: sound/plan.json, and the CSVs the Studio's audio runners read:
  audio_shots.csv   one row per shot of the approved shot list: [speaker, text, voice, {speed, pause}] lines, effects, music
  audio_scenes.csv  one music cue per scene
  audiobook.csv     one row per scene: the narrator reads the action, the characters speak their lines (no pictures needed)
The audiobook (Product F): exports/audiobook.m4b with a chapter per scene and a cover picture, and exports/audiobook/<NN>-<scene>.mp3.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import continuity_book  # noqa: E402
import crew  # noqa: E402
import gates  # noqa: E402
import screenplay  # noqa: E402
import shot_list  # noqa: E402
import voices  # noqa: E402

KOKORO = ("af_bella", "af_heart", "af_nicole", "af_sky", "af_sarah", "am_adam", "am_michael", "am_fenrir", "am_puck",
          "bf_emma", "bf_isabella", "bm_george", "bm_lewis", "bm_daniel")
FIELDS = ["chapter", "shot", "lines_json", "narration", "sfx", "music", "scene"]
Ask = Callable[[str, str | list[str], str, Callable[[dict], None]], dict]


class SoundError(RuntimeError):
    """The sound step cannot be done as asked; the message says why."""


def path(pdir: Path) -> Path:
    return pdir / "sound" / "plan.json"


def load(pdir: Path) -> dict:
    try:
        return json.loads(path(pdir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _direction(emotion: str) -> dict:
    sp, pause = voices.EMOTIONS.get(emotion, voices.EMOTIONS["neutral"])
    return {"speed": sp, "pause": pause}


# ---------------------------------------------------------------------------------------------- the three calls
def cast_checker(names: list[str]) -> Callable[[dict], None]:
    def check(d) -> None:
        if not isinstance(d, dict) or not isinstance(d.get("cast"), dict):
            raise ValueError('reply with {"cast": {"NAME": {"voice": "...", "emotion": "...", "why": "..."}}, "narrator": {...}}')
        missing = [n for n in names if n not in d["cast"]]
        if missing:
            raise ValueError(f"cast every character: missing {', '.join(missing)}")
        for n, c in [*d["cast"].items(), ("narrator", d.get("narrator"))]:
            if not isinstance(c, dict) or c.get("voice") not in KOKORO:
                raise ValueError(f"the voice of {n} must be one of {', '.join(KOKORO)}")
            if c.get("emotion", "neutral") not in voices.EMOTIONS:
                raise ValueError(f"emotion is one of {', '.join(voices.EMOTIONS)}")
        if not isinstance(d.get("lines", {}), dict):
            raise ValueError("'lines' maps a line id to its emotion")
    return check


def check_sound(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("shots"), list):
        raise ValueError('reply with {"shots": [{"n": 1, "sfx": "...", "ambience": "..."}]}')
    for s in d["shots"]:
        if not isinstance(s, dict) or not isinstance(s.get("n"), int) or not str(s.get("sfx", "")).strip():
            raise ValueError("every shot needs its number 'n' and 'sfx'")


def check_music(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("cues"), list) or not d["cues"]:
        raise ValueError('reply with {"cues": [{"first_scene": "S001", "last_scene": "S002", "mood": "...", "tempo_bpm": 70, "instrumentation": "...", "prompt": "..."}]}')
    for c in d["cues"]:
        if not isinstance(c, dict) or not all(str(c.get(k, "")).strip() for k in ("first_scene", "last_scene", "mood", "instrumentation", "prompt")):
            raise ValueError("every cue needs first_scene, last_scene, mood, instrumentation and prompt")
        if not isinstance(c.get("tempo_bpm"), (int, float)) or not 30 <= c["tempo_bpm"] <= 220:
            raise ValueError("tempo_bpm is the cue's tempo (30-220)")


def lines_of(pdir: Path, sl: dict) -> list[dict]:
    """Every spoken line of the shot list: {id: "S001#2#1", scene, shot, character, text}. A shot's dialogue may be 'NAME: words'."""
    book = continuity_book.load(pdir)
    names = [c["name"] for c in book.get("characters", [])]
    out = []
    for sc in sl["scenes"]:
        for s in sc["shots"]:
            text = (s.get("dialogue") or "").strip()
            if not text:
                continue
            for k, part in enumerate([p for p in re.split(r"\s*/\s*|\n", text) if p.strip()], 1):
                m = re.match(r"^([A-Z][A-Z .'\-]{0,40}):\s*(.+)$", part.strip())
                who, words = (m.group(1).strip(), m.group(2).strip()) if m else ((s.get("characters") or names or ["NARRATOR"])[0], part.strip().strip('"'))
                out.append({"id": f"{sc['id']}#{s['n']}#{k}", "scene": sc["id"], "shot": s["n"], "character": who, "text": words})
    return out


def write_plan(pdir: Path, ask: Ask, say: Callable[[str], None] = print) -> dict:
    sl = shot_list.load(pdir)
    if not gates.approved(pdir, "shotlist", shot_list.gate_data(sl)):
        raise SoundError("Approve the shot list first: the sound is planned shot by shot.")
    book = continuity_book.load(pdir)
    names = [c["name"] for c in book.get("characters", [])]
    lines = lines_of(pdir, sl)
    shared = pdir / "sound" / "series_cast.json"
    say("Your voice director is casting the voices" if not shared.is_file() else "The series' voices are used (the voice director directs the new lines)")
    people = "\n".join(f"- {c['name']}: {c['token']}. Personality: " + "; ".join(f"{k} {v}" for k, v in (c.get("personality") or {}).items()) for c in book.get("characters", []))
    cast = ask(f"Cast a voice for every character and the narrator from these voices: {', '.join(KOKORO)} (a = American, b = British; f = female, "
               f"m = male). Use the personality profiles. Give each a usual emotion (one of {', '.join(voices.EMOTIONS)}) and, for any line that "
               "needs it, a different emotion by line id. Also direct the audiobook narration (voice, emotion, pace notes). "
               'Reply as JSON: {"cast": {"NAME": {"voice": "af_bella", "emotion": "calm", "why": "..."}}, "narrator": {"voice": "bm_george", '
               '"emotion": "warm", "notes": "..."}, "lines": {"S001#2#1": "whisper"}}\n\nCHARACTERS:\n' + people + "\n\nLINES:\n"
               + "\n".join(f"{x['id']} {x['character']}: {x['text']}" for x in lines), "voice_director", "sound: voice casting", cast_checker(names))
    if shared.is_file():                                      # an episode keeps the series' voices; only the line direction is new
        keep = json.loads(shared.read_text(encoding="utf-8"))
        cast = {**cast, "cast": {**cast["cast"], **keep.get("cast", {})}, "narrator": keep.get("narrator", cast["narrator"])}
    effects: dict[str, list[dict]] = {}
    for i, sc in enumerate(sl["scenes"], 1):
        say(f"Your sound designer is working on scene {i} of {len(sl['scenes'])}")
        d = ask("Write the sound effects and the ambience of every shot of this scene (what is heard, not music). "
                'Reply as JSON: {"shots": [{"n": 1, "sfx": "...", "ambience": "..."}]}\n\n' + f"{sc['heading']}\n"
                + "\n".join(f"shot {s['n']}: {s['action']} | heard: {s.get('sound', '')} | dialogue: {s.get('dialogue', '')}" for s in sc["shots"]),
                "sound_designer", f"sound: effects scene {i}", check_sound)
        effects[sc["id"]] = [{"n": s["n"], "sfx": " ".join(str(s["sfx"]).split()), "ambience": " ".join(str(s.get("ambience", "")).split())} for s in d["shots"]]
    say("Your composer is writing the music cues")
    music = ask("Write the film's music cues: mood, tempo in bpm, instrumentation, and where each starts and ends (first and last scene id). "
                f"The score's theme: {book.get('music_theme', '')}. Give each a prompt for a music model. "
                'Reply as JSON: {"cues": [{"first_scene": "S001", "last_scene": "S002", "mood": "...", "tempo_bpm": 70, "instrumentation": "...", "prompt": "..."}]}\n\n'
                + "\n".join(f"{sc['id']} {sc['heading']}: {sc['breakdown']['emotional_beat']}" for sc in sl["scenes"]), "composer", "sound: music cues", check_music)
    plan = {"cast": cast["cast"], "narrator": cast["narrator"], "line_emotions": cast.get("lines", {}), "lines": lines, "effects": effects, "cues": music["cues"]}
    path(pdir).parent.mkdir(parents=True, exist_ok=True)
    path(pdir).write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
    write_csvs(pdir, plan, sl)
    say(f"Done: {len(plan['cast'])} voices, {len(lines)} lines, {len(plan['cues'])} music cues.")
    return plan


# ---------------------------------------------------------------------------------------------- the CSVs the audio runners read
def cue_for(plan: dict, scene: str, order: list[str]) -> dict | None:
    i = order.index(scene) if scene in order else -1
    for c in plan["cues"]:
        a = order.index(c["first_scene"]) if c["first_scene"] in order else 0
        b = order.index(c["last_scene"]) if c["last_scene"] in order else len(order) - 1
        if a <= i <= b:
            return c
    return plan["cues"][-1] if plan["cues"] else None


def _line(plan: dict, x: dict) -> list:
    who = x["character"]
    c = plan["cast"].get(who) or {"voice": plan["narrator"]["voice"], "emotion": "neutral"}
    return [who, x["text"], c["voice"], _direction(plan["line_emotions"].get(x["id"], c.get("emotion", "neutral")))]


def write_csvs(pdir: Path, plan: dict, sl: dict) -> None:
    order = [sc["id"] for sc in sl["scenes"]]
    for name in ("audio_shots.csv", "audio_scenes.csv", "audiobook.csv"):
        f = pdir / name
        if f.is_file():
            f.replace(f.with_suffix(".csv.bak"))
    shots, scenes, book_rows = [], [], []
    for sc in sl["scenes"]:
        cue = cue_for(plan, sc["id"], order)
        prompt = cue["prompt"] if cue else ""
        fx = {e["n"]: e for e in plan["effects"].get(sc["id"], [])}
        for s in sc["shots"]:
            ls = [_line(plan, x) for x in plan["lines"] if x["scene"] == sc["id"] and x["shot"] == s["n"]]
            e = fx.get(s["n"], {"sfx": s.get("sound", ""), "ambience": ""})
            shots.append({"chapter": sc["id"], "shot": s["n"], "lines_json": json.dumps(ls, ensure_ascii=False), "narration": " ".join(x[1] for x in ls),
                          "sfx": ", ".join(x for x in (e["sfx"], e.get("ambience", "")) if x), "music": prompt, "scene": sc["id"]})
        scenes.append({"chapter": sc["id"], "shot": 1, "lines_json": "[]", "narration": "", "sfx": "", "music": prompt, "scene": sc["id"]})
        book_rows.append({"chapter": sc["id"], "shot": 1, "lines_json": json.dumps(audiobook_lines(pdir, plan, sc["id"]), ensure_ascii=False),
                          "narration": "", "sfx": "", "music": "", "scene": sc["id"]})
    for name, rows in (("audio_shots.csv", shots), ("audio_scenes.csv", scenes), ("audiobook.csv", book_rows)):
        with open(pdir / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, FIELDS)
            w.writeheader()
            w.writerows(rows)


def audiobook_lines(pdir: Path, plan: dict, sid: str) -> list:
    """The narrator reads the scene's action; characters speak their own lines in their own voices (from the screenplay itself)."""
    sc = screenplay.load_scene(pdir, sid) or {"elements": []}
    nar = plan["narrator"]
    out: list = []
    for e in sc["elements"]:
        if e["type"] == "dialogue":
            c = plan["cast"].get(e["character"]) or {"voice": nar["voice"], "emotion": "neutral"}
            out.append([e["character"], e["text"], c["voice"], _direction(c.get("emotion", "neutral"))])
        elif e["type"] == "action":
            out.append(["NARRATOR", e["text"], nar["voice"], _direction(nar.get("emotion", "warm"))])
    return out


def gate_data(pdir: Path) -> dict:
    p = load(pdir)
    return {k: p.get(k) for k in ("cast", "narrator", "line_emotions", "effects", "cues")}


# ---------------------------------------------------------------------------------------------- the audiobook (Product F)
def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _seconds(wav: Path) -> float:
    import wave
    with wave.open(str(wav)) as w:
        return w.getnframes() / float(w.getframerate())


def make_audiobook(pdir: Path, cover: Path | None = None) -> dict:
    """exports/audiobook.m4b (a chapter per scene, the cover picture) and exports/audiobook/NN-<scene>.mp3, from audio/kokoro_audiobook/."""
    rows = list(csv.DictReader(open(pdir / "audiobook.csv", newline="", encoding="utf-8"))) if (pdir / "audiobook.csv").is_file() else []
    if not rows:
        raise SoundError("Write the sound plan first (it makes audiobook.csv).")
    src = pdir / "audio" / "kokoro_audiobook"
    wavs = [src / f"narration-{i:04d}.wav" for i in range(1, len(rows) + 1)]
    missing = [w.name for w in wavs if not w.is_file()]
    if missing:
        raise SoundError(f"{len(missing)} chapter(s) are not rendered yet (first: {missing[0]}): render the audiobook narration first.")
    out = pdir / "exports"
    (out / "audiobook").mkdir(parents=True, exist_ok=True)
    ff = ffmpeg()
    meta = [";FFMETADATA1", f"title={pdir.name.replace('_', ' ').title()}", "artist=Pistachio's Studio"]
    t = 0.0
    for i, (w, r) in enumerate(zip(wavs, rows, strict=True), 1):
        d = _seconds(w)
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={round(t * 1000)}", f"END={round((t + d) * 1000)}", f"title=Chapter {i} ({r['chapter']})"]
        t += d
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(w), "-codec:a", "libmp3lame", "-b:a", "96k", str(out / "audiobook" / f"{i:02d}-{r['chapter']}.mp3")], check=True)
    with tempfile.TemporaryDirectory(prefix="studio-ab-") as tmp:
        lst = Path(tmp) / "list.txt"
        lst.write_text("".join(f"file '{w.resolve().as_posix()}'\n" for w in wavs), encoding="utf-8")
        mfile = Path(tmp) / "meta.txt"
        mfile.write_text("\n".join(meta) + "\n", encoding="utf-8")
        argv = [ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(mfile)]
        if cover is not None and cover.is_file():
            argv += ["-i", str(cover), "-map", "0:a", "-map", "2:v", "-c:v", "mjpeg", "-disposition:v:0", "attached_pic"]
        else:
            argv += ["-map", "0:a"]
        argv += ["-map_metadata", "1", "-c:a", "aac", "-b:a", "96k", "-f", "mp4", str(out / "audiobook.m4b")]
        subprocess.run(argv, check=True)
    return {"m4b": "exports/audiobook.m4b", "chapters": len(rows), "seconds": round(t, 1)}


def fake_ask(pdir: Path) -> Ask:
    def ask(prompt: str, roles, step: str, validate: Callable[[dict], None]) -> dict:
        if step == "sound: voice casting":
            names = [c["name"] for c in continuity_book.load(pdir).get("characters", [])]
            d: dict = {"cast": {n: {"voice": KOKORO[i % len(KOKORO)], "emotion": "calm", "why": "fits"} for i, n in enumerate(names)},
                       "narrator": {"voice": "bm_george", "emotion": "warm", "notes": "unhurried"}, "lines": {}}
        elif step.startswith("sound: effects"):
            ns = [int(m) for m in re.findall(r"^shot (\d+):", prompt, re.M)]
            d = {"shots": [{"n": n, "sfx": "wind against glass", "ambience": "distant surf"} for n in ns]}
        else:
            ids = re.findall(r"^(S\d{3}) ", prompt, re.M)
            d = {"cues": [{"first_scene": ids[0], "last_scene": ids[-1], "mood": "longing", "tempo_bpm": 66, "instrumentation": "solo cello, soft strings",
                           "prompt": "slow solo cello over soft strings, longing, 66 bpm"}]}
        validate(d)
        return d
    return ask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex", "hf", "local", "fake"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--audiobook", action="store_true")
    a = ap.parse_args(argv)
    import layout
    pdir = layout.project_dir(a.project, "book")
    if not pdir.is_dir():
        print(f"no book called {a.project}", flush=True)
        return 1
    try:
        if a.audiobook:
            import pictures
            st = pictures.status(pdir)
            setdir = layout.find_dir(st["set"]) if st["set"] else None
            cover = next((setdir / s["image"] for s in st["shots"] if s["image"] and s["approved"]), None) if setdir else None
            print(json.dumps(make_audiobook(pdir, cover)), flush=True)
            return 0
        if a.engine == "fake":
            ask = fake_ask(pdir)
        else:
            import bookkit

            def ask(prompt, roles, step, validate):
                return bookkit.llm_json(prompt, crew.system(roles, pdir, step), model=a.model, engine=a.engine, validate=validate)
        write_plan(pdir, ask, lambda t: print(t, flush=True))
    except (SoundError, RuntimeError, ValueError, subprocess.CalledProcessError) as e:
        print(f"The sound step stopped: {e}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
