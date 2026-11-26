#!/usr/bin/env python3
"""Clips per style (BOOK_TO_SCREEN_BUILD.md Sections 6, 7.4e; milestone M11).

  python3 clips.py <project> [--engine claude|... |fake] [--model M]        the Animation / VFX Supervisor's motion prompts

The motion prompts are written ONCE (shots/motion.json) and used by every style, with the same length (from the shared EDL) and the same seed
as the shot's picture; the start frame of each clip is that style's approved picture (7.4e). For each style, prepare() turns its picture
prompt set into an image-to-video set: all_shots.csv (row N = shot N) and images/pictures_keyframes/image-NNNN.png, which the usual
image-to-video runners render with KEYFRAME_MODEL=pictures; the clips come back to videos/<model>/shot-NNNN.mp4 in that set. The owner
approves each clip (the Animation Supervisor's checklist: no morphing, no identity drift, the right motion) and the style's clips (gates.py,
"clips" for the master style, "clips_<style>" for the others). render_cut.py --kind film then makes the film of each style from the EDL.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crew  # noqa: E402
import edl  # noqa: E402
import gates  # noqa: E402
import layout  # noqa: E402
import pictures  # noqa: E402
import production  # noqa: E402
import shot_list  # noqa: E402
import styles  # noqa: E402

KEYFRAMES = "pictures"                      # images/pictures_keyframes in each style's set
CHECKLIST = ("no morphing", "no identity drift", "the right motion")
Ask = Callable[[str, str | list[str], str, Callable[[dict], None]], dict]


class ClipError(RuntimeError):
    """The clip step cannot be done as asked; the message says why."""


def motion_path(pdir: Path) -> Path:
    return pdir / "shots" / "motion.json"


def load_motion(pdir: Path) -> dict:
    try:
        return json.loads(motion_path(pdir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def check_motion(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("shots"), list) or not d["shots"]:
        raise ValueError('reply with {"shots": [{"n": 1, "motion": "...", "simplify": false}]}')
    for s in d["shots"]:
        if not isinstance(s, dict) or not isinstance(s.get("n"), int) or not str(s.get("motion", "")).strip():
            raise ValueError("every shot needs its number 'n' and a 'motion' prompt")


def write_motion(pdir: Path, ask: Ask, say: Callable[[str], None] = print) -> dict:
    """The Animation / VFX Supervisor: one motion prompt per shot (what moves, how the camera moves, kept simple enough for the video model)."""
    if not gates.approved(pdir, "pictures", pictures.gate_data(pdir)):
        raise ClipError("Approve the master style's pictures first: the clips start from them.")
    sl = shot_list.load(pdir)
    out: dict = {}
    for i, sc in enumerate(sl["scenes"], 1):
        say(f"Your animation supervisor is directing the motion of scene {i} of {len(sl['scenes'])}")
        d = ask("Write the motion prompt for every shot of this scene for an image-to-video model starting from the approved picture as the exact "
                "opening frame: preserve subjects, props, materials and composition; specify what moves and what stays stationary; for shots of 4 s "
                "or longer with multiple beats, structure timed phases scaled to the shot's seconds plus an ESSENTIAL SEQUENCE (A -> B -> C) and "
                "guard against teleportation, duplicated objects, premature action or cuts. Keep it to what an image-to-video model can do well; "
                'set "simplify" when the shot is too hard and was simplified. Reply as JSON: {"shots": [{"n": 1, "motion": "...", "simplify": false}]}\n\n'
                f"{sc['heading']} | intent: {sc['breakdown']['intent']} | blocking: {sc['breakdown']['blocking']}\n"
                + "\n".join(f"shot {s['n']}: {s['seconds']}s, {s['type']}, {s['movement']}; {s['action']} ({s['expression']})" for s in sc["shots"]),
                "animation_supervisor", f"clips: motion scene {i}", check_motion)
        out[sc["id"]] = {int(s["n"]): {"motion": " ".join(str(s["motion"]).split()), "simplify": bool(s.get("simplify"))} for s in d["shots"]}
    data = {"scenes": {sid: {str(n): v for n, v in shots.items()} for sid, shots in out.items()}}
    motion_path(pdir).parent.mkdir(parents=True, exist_ok=True)
    motion_path(pdir).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return data


def gate_step(pdir: Path, sid: str) -> str:
    return "clips" if sid in ("", production.load(pdir)["master"]) else f"clips_{sid}"


def prepare(pdir: Path, sid: str) -> dict:
    """The image-to-video set of a style: its approved pictures as start frames, the shared motion prompts, lengths and seeds."""
    if not gates.approved(pdir, pictures.gate_step(pdir, sid), pictures.gate_data(pdir, sid)):
        raise ClipError(f"Approve the {sid} pictures first: they are the start frames of the clips.")
    motion = load_motion(pdir).get("scenes", {})
    if not motion:
        raise ClipError("Write the motion prompts first.")
    st = pictures.status(pdir, sid)
    setdir = layout.find_dir(st["set"])
    if setdir is None:
        raise ClipError("this style has no picture set")
    seconds = {(v["scene"], v["shot"]): v["seconds"] for v in edl.cut(edl.load(pdir) or edl.assemble(pdir), "main")["tracks"]["video"]}
    card = styles.card_of(pdir, sid)
    import character_types_registry as _ctr
    st_meta = _ctr.get_style(sid) or {}
    cadence = str(st_meta.get("motion_cadence") or "").strip()
    kf = setdir / "images" / f"{KEYFRAMES}_keyframes"
    shutil.rmtree(kf, ignore_errors=True)
    kf.mkdir(parents=True)
    rows = []
    for s in st["shots"]:
        m = motion.get(s["scene"], {}).get(str(s["shot"]))
        if m is None:
            raise ClipError(f"no motion prompt for {s['scene']} shot {s['shot']}: write the motion prompts again")
        shutil.copy2(setdir / s["image"], kf / f"image-{s['row']:04d}.png")
        prompt_str = f"{card['prefix']}. {m['motion']}"
        if cadence:
            prompt_str = f"{prompt_str}. Motion cadence: {cadence}"
        rows.append({"chapter": s["scene"], "shot": s["shot"], "prompt": prompt_str, "negative": f"{card['negative']}, morphing, flicker",
                     "seed": s["seed"], "seconds": round(seconds.get((s["scene"], s["shot"]), 4.0), 2)})
    with open(setdir / "all_shots.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return {"set": st["set"], "rows": len(rows)}


def clip_file(pdir: Path, sid: str, row: int) -> Path | None:
    """The clip of a shot in a style: the owner's footage for a real shot (the same in every style), else the style's rendered clip."""
    import media_sources
    real = media_sources.footage(pdir).get(str(row))
    if real and (pdir / real).is_file():
        return pdir / real
    st = pictures.status(pdir, sid)
    setdir = layout.find_dir(st["set"]) if st["set"] else None
    if setdir is None or not (setdir / "videos").is_dir():
        return None
    for d in sorted((setdir / "videos").iterdir()):
        f = d / f"shot-{row:04d}.mp4"
        if f.is_file():
            return f
    return None


def _review_file(pdir: Path, sid: str) -> Path:
    return pictures.pdir_of(pdir, sid) / "clips.json"


def _rows(pdir: Path) -> list[tuple[int, str, int]]:
    """(row, scene, shot) for every shot of the shot list, in order (row N = shot N everywhere)."""
    out, row = [], 0
    for sc in shot_list.load(pdir).get("scenes", []):
        for s in sc["shots"]:
            row += 1
            out.append((row, sc["id"], s["n"]))
    return out


def status(pdir: Path, sid: str) -> dict:
    st = pictures.status(pdir, sid)
    rv = pictures._read(_review_file(pdir, sid), {}) or {}
    setdir = layout.find_dir(st["set"]) if st["set"] else None
    out = []
    for row, scene, shot in _rows(pdir):
        f = clip_file(pdir, sid, row)
        r = rv.get(str(row), {})
        if f is not None and setdir is not None and setdir in f.parents:
            rel, base = f.relative_to(setdir).as_posix(), st["set"]
        elif f is not None:
            rel, base = f.relative_to(pdir).as_posix(), pdir.name             # the owner's footage, inside the book
        else:
            rel, base = "", st["set"]
        out.append({"row": row, "scene": scene, "shot": shot, "clip": rel, "base": base, "approved": bool(r.get("approved")) and f is not None,
                    "note": r.get("note", "")})
    return {"style": sid, "set": st["set"], "clips": out, "approved": sum(1 for c in out if c["approved"]), "checklist": list(CHECKLIST)}


def review(pdir: Path, sid: str, row: int, approved: bool | None = None, note: str | None = None) -> dict:
    if not 1 <= row <= len(_rows(pdir)):
        raise ClipError(f"no clip {row}")
    rv = pictures._read(_review_file(pdir, sid), {}) or {}
    r = rv.setdefault(str(row), {})
    if approved is not None:
        if approved and clip_file(pdir, sid, row) is None:
            raise ClipError("that shot has no clip yet: render it first")
        r["approved"] = approved
    if note is not None:
        r["note"] = " ".join(note.split())[:1000]
    pictures._write(_review_file(pdir, sid), rv)
    return r


def gate_data(pdir: Path, sid: str) -> list:
    return [[c["row"], c["clip"], c["approved"]] for c in status(pdir, sid)["clips"]]


def approve_all(pdir: Path, sid: str) -> dict:
    st = status(pdir, sid)
    left = [c for c in st["clips"] if not c["approved"]]
    if not st["clips"] or left:
        raise ClipError(f"{len(left)} clip(s) are not approved yet" if st["clips"] else "there are no clips yet")
    return gates.approve(pdir, gate_step(pdir, sid), gate_data(pdir, sid))


def fake_ask() -> Ask:
    import re

    def ask(prompt: str, roles, step: str, validate: Callable[[dict], None]) -> dict:
        ns = [int(m) for m in re.findall(r"^shot (\d+):", prompt, re.M)]
        d = {"shots": [{"n": n, "motion": "slow push in, her hair moves in the wind", "simplify": False} for n in ns]}
        validate(d)
        return d
    return ask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex", "hf", "local", "fake"])
    ap.add_argument("--model", default=None)
    a = ap.parse_args(argv)
    pdir = layout.project_dir(a.project, "book")
    if not pdir.is_dir():
        print(f"no book called {a.project}", flush=True)
        return 1
    if a.engine == "fake":
        ask = fake_ask()
    else:
        import bookkit

        def ask(prompt, roles, step, validate):
            return bookkit.llm_json(prompt, crew.system(roles, pdir, step), model=a.model, engine=a.engine, validate=validate)
    try:
        d = write_motion(pdir, ask, lambda t: print(t, flush=True))
        print(f"Done: motion prompts for {sum(len(v) for v in d['scenes'].values())} shots.", flush=True)
    except (ClipError, RuntimeError, ValueError) as e:
        print(f"The motion prompts were not written: {e}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
