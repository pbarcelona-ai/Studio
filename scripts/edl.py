"""The edit decision list (BOOK_TO_SCREEN_BUILD.md Section 6 "Edit", 13; milestone M10): ONE edit, reused for every style.

  projects/books/<book>/edit/edl.json   {"current": "main", "cuts": {"main": CUT, "short": CUT, ...}}
  CUT = {"name", "tracks": {"video": [CLIP], "voice": [ITEM], "music": [ITEM], "effects": [ITEM]}, "volumes": {track: 0-2}, "duck_db": 12}
  CLIP = {"id", "scene", "shot", "seconds", "trim_in", "transition": {"kind": "cut" | "dissolve", "seconds"}, "volume"}
  ITEM = {"id", "attach": clip id (voice, effects) or scene id (music), "offset", "seconds", "volume", "ref"}

Three tracks as on the page (video, voice / dialogue, music + effects). Every change goes through this module and is written to the one EDL:
move (reorder), trim, set_volume (clip or track), split, ripple_delete (the rest closes up), snap_to_beats (lengths fitted to the music's
tempo), and alternative cuts (copy_cut, use_cut). timeline() turns a cut into times on the clock (dissolves overlap), which the animatic and
film renders and the page's preview use. The Editor role suggests cuts and pacing fixes as notes the owner accepts in one click (apply_note).
Clips are referred to by scene and shot, never by a file, so the same cut renders in every style.
"""
from __future__ import annotations

import copy
import json
import math
from collections.abc import Callable
from pathlib import Path

import shot_list
import sound_design

TRACKS = ("video", "voice", "music", "effects")
MIN_CLIP = 0.5
WORDS_PER_SECOND = 2.6
Ask = Callable[[str, str | list[str], str, Callable[[dict], None]], dict]


class EditError(ValueError):
    """An edit cannot be made as asked; the message says why."""


def path(pdir: Path) -> Path:
    return pdir / "edit" / "edl.json"


def load(pdir: Path) -> dict:
    try:
        d = json.loads(path(pdir).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and d.get("cuts") else {}
    except (OSError, ValueError):
        return {}


def save(pdir: Path, d: dict) -> None:
    path(pdir).parent.mkdir(parents=True, exist_ok=True)
    tmp = path(pdir).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path(pdir))


def cut(d: dict, name: str = "") -> dict:
    name = name or d.get("current", "main")
    if name not in d.get("cuts", {}):
        raise EditError(f"no cut called {name!r}")
    return d["cuts"][name]


# ---------------------------------------------------------------------------------------------- the first assembly
def assemble(pdir: Path) -> dict:
    """The Editor's assembly from the approved shot list and sound plan: every shot in order, its lines on the voice track, a music cue per
    span of scenes, the effects of each shot."""
    sl = shot_list.load(pdir)
    if not sl.get("scenes"):
        raise EditError("There is no shot list yet.")
    plan = sound_design.load(pdir)
    video, voice, music, effects = [], [], [], []
    row = 0
    for sc in sl["scenes"]:
        for s in sc["shots"]:
            row += 1
            cid = f"v{row:04d}"
            words = sum(len(x["text"].split()) for x in plan.get("lines", []) if x["scene"] == sc["id"] and x["shot"] == s["n"])
            secs = max(float(s["seconds"]), round(words / WORDS_PER_SECOND + 0.6, 1)) if words else float(s["seconds"])
            tr = "dissolve" if s.get("transition") in ("dissolve", "fade in", "fade out") else "cut"
            video.append({"id": cid, "scene": sc["id"], "shot": s["n"], "row": row, "seconds": round(secs, 2), "trim_in": 0.0,
                          "transition": {"kind": tr, "seconds": 0.8 if tr == "dissolve" else 0.0}, "volume": 1.0})
            if words:
                voice.append({"id": f"a{row:04d}", "attach": cid, "offset": 0.2, "seconds": round(words / WORDS_PER_SECOND, 2), "volume": 1.0, "ref": row})
            fx = next((e for e in plan.get("effects", {}).get(sc["id"], []) if e["n"] == s["n"]), None)
            if fx:
                effects.append({"id": f"e{row:04d}", "attach": cid, "offset": 0.0, "seconds": round(secs, 2), "volume": 1.0, "ref": row, "text": fx["sfx"]})
    order = [sc["id"] for sc in sl["scenes"]]
    for i, sc in enumerate(sl["scenes"], 1):
        cue = sound_design.cue_for(plan, sc["id"], order) if plan.get("cues") else None
        music.append({"id": f"m{i:03d}", "attach": sc["id"], "offset": 0.0, "seconds": None, "volume": 1.0, "ref": i,
                      "tempo_bpm": float(cue["tempo_bpm"]) if cue else None, "text": cue["prompt"] if cue else ""})
    main = {"name": "main", "tracks": {"video": video, "voice": voice, "music": music, "effects": effects},
            "volumes": {"video": 1.0, "voice": 1.0, "music": 0.35, "effects": 0.6}, "duck_db": 12.0}
    d = {"current": "main", "cuts": {"main": main}}
    save(pdir, d)
    return d


# ---------------------------------------------------------------------------------------------- the clock
def timeline(c: dict) -> dict:
    """Start times: clips one after another (a dissolve overlaps the next clip by its length); voice and effects at their clip's start plus
    their offset; music from the first clip of its scene to the end of the scene's last clip."""
    t, clips = 0.0, []
    vids = c["tracks"]["video"]
    for i, v in enumerate(vids):
        clips.append({**v, "start": round(t, 3), "end": round(t + v["seconds"], 3)})
        overlap = v["transition"]["seconds"] if v["transition"]["kind"] == "dissolve" and i < len(vids) - 1 else 0.0
        t += v["seconds"] - overlap
    total = clips[-1]["end"] if clips else 0.0
    at = {x["id"]: x for x in clips}
    out: dict = {"video": clips, "total": round(total, 3)}
    for tr in ("voice", "effects"):
        out[tr] = [{**a, "start": round(at[a["attach"]]["start"] + a["offset"], 3), "end": round(at[a["attach"]]["start"] + a["offset"] + a["seconds"], 3)}
                   for a in c["tracks"][tr] if a["attach"] in at]
    scenes: dict[str, list[dict]] = {}
    for x in clips:
        scenes.setdefault(x["scene"], []).append(x)
    music: list[dict] = []
    out["music"] = music
    for m in c["tracks"]["music"]:
        if m.get("whole"):                                   # an uploaded score: under the whole film
            music.append({**m, "start": 0.0, "end": round(total, 3)})
            continue
        span = scenes.get(m["attach"])
        if span:
            s0, s1 = min(x["start"] for x in span), max(x["end"] for x in span)
            music.append({**m, "start": round(s0 + m["offset"], 3), "end": round(min(s1, s0 + m["offset"] + (m["seconds"] or s1 - s0)), 3)})
    return out


# ---------------------------------------------------------------------------------------------- edits
def _clip(c: dict, cid: str) -> tuple[int, dict]:
    for i, v in enumerate(c["tracks"]["video"]):
        if v["id"] == cid:
            return i, v
    raise EditError(f"no clip {cid}")


def _item(c: dict, iid: str) -> tuple[str, dict]:
    for tr in TRACKS:
        for x in c["tracks"][tr]:
            if x["id"] == iid:
                return tr, x
    raise EditError(f"nothing called {iid}")


def move(c: dict, cid: str, to: int) -> None:
    """Reorder a video clip (its voice and effects go with it)."""
    i, v = _clip(c, cid)
    vids = c["tracks"]["video"]
    if not 0 <= to < len(vids):
        raise EditError("no such position")
    vids.insert(to, vids.pop(i))


def trim(c: dict, iid: str, seconds: float, trim_in: float | None = None) -> None:
    tr, x = _item(c, iid)
    if not math.isfinite(seconds) or seconds < MIN_CLIP or seconds > 600:
        raise EditError(f"a clip is {MIN_CLIP}-600 seconds long")
    x["seconds"] = round(float(seconds), 3)
    if trim_in is not None:
        if not 0 <= trim_in <= 600:
            raise EditError("trim_in is seconds from the start of the source")
        x["trim_in"] = round(float(trim_in), 3)


def set_volume(c: dict, target: str, volume: float) -> None:
    """A clip's or a whole track's volume (0 = silent, 1 = as made, up to 2)."""
    if not math.isfinite(volume) or not 0 <= volume <= 2:
        raise EditError("volume is 0-2")
    if target in TRACKS:
        c["volumes"][target] = round(float(volume), 3)
    else:
        _item(c, target)[1]["volume"] = round(float(volume), 3)


def split(c: dict, cid: str, at: float) -> str:
    """Split a clip at `at` seconds into two (the second gets a new id; voice and effects stay on the first)."""
    i, v = _clip(c, cid)
    if not MIN_CLIP <= at <= v["seconds"] - MIN_CLIP:
        raise EditError(f"split at least {MIN_CLIP} s from either end")
    ids = {x["id"] for x in c["tracks"]["video"]}
    n = 2
    while f"{cid}-{n}" in ids:
        n += 1
    second = {**copy.deepcopy(v), "id": f"{cid}-{n}", "seconds": round(v["seconds"] - at, 3), "trim_in": round(v["trim_in"] + at, 3)}
    v["seconds"] = round(at, 3)
    v["transition"] = {"kind": "cut", "seconds": 0.0}
    c["tracks"]["video"].insert(i + 1, second)
    return second["id"]


def ripple_delete(c: dict, cid: str) -> None:
    """Delete a clip and close the gap (its voice and effects go with it)."""
    i, _ = _clip(c, cid)
    if len(c["tracks"]["video"]) == 1:
        raise EditError("a cut keeps at least one clip")
    c["tracks"]["video"].pop(i)
    for tr in ("voice", "effects"):
        c["tracks"][tr] = [x for x in c["tracks"][tr] if x["attach"] != cid]


def snap_to_beats(c: dict, scene: str = "") -> int:
    """Fit clip lengths to whole beats of their scene's music (tempo from the Composer's cue). Returns how many clips changed."""
    tempo = {m["attach"]: m.get("tempo_bpm") for m in c["tracks"]["music"]}
    score = next((m["tempo_bpm"] for m in c["tracks"]["music"] if m.get("whole") and m.get("tempo_bpm")), None)
    n = 0
    for v in c["tracks"]["video"]:
        bpm = score or tempo.get(v["scene"])
        if not bpm or (scene and v["scene"] != scene):
            continue
        beat = 60.0 / float(bpm)
        beats = max(1, round(v["seconds"] / beat))
        new = round(max(MIN_CLIP, beats * beat), 3)
        if abs(new - v["seconds"]) > 1e-6:
            v["seconds"], n = new, n + 1
    return n


def set_transition(c: dict, cid: str, kind: str, seconds: float = 0.8) -> None:
    if kind not in ("cut", "dissolve"):
        raise EditError("a transition is cut or dissolve")
    _, v = _clip(c, cid)
    v["transition"] = {"kind": kind, "seconds": round(float(seconds), 3) if kind == "dissolve" else 0.0}


def copy_cut(d: dict, name: str, src: str = "") -> dict:
    """An alternative cut: a copy of a cut (default: the current one) under a new name, made the current one."""
    if not name or len(name) > 40 or not all(ch.isalnum() or ch in " _-" for ch in name):
        raise EditError("a cut's name is 1-40 letters, digits, spaces, - or _")
    if name in d["cuts"]:
        raise EditError(f"there is already a cut called {name!r}")
    d["cuts"][name] = {**copy.deepcopy(cut(d, src)), "name": name}
    d["current"] = name
    return d["cuts"][name]


def use_cut(d: dict, name: str) -> None:
    cut(d, name)
    d["current"] = name


def apply(pdir: Path, op: str, args: dict) -> dict:
    """One edit on the current cut, written to the EDL. Returns the EDL."""
    d = load(pdir) or assemble(pdir)
    if op == "copy_cut":
        copy_cut(d, str(args.get("name", "")), str(args.get("from", "")))
    elif op == "use_cut":
        use_cut(d, str(args.get("name", "")))
    else:
        c = cut(d)
        try:
            if op == "move":
                move(c, str(args["id"]), int(args["to"]))
            elif op == "trim":
                trim(c, str(args["id"]), float(args["seconds"]), float(args["trim_in"]) if args.get("trim_in") is not None else None)
            elif op == "volume":
                set_volume(c, str(args["target"]), float(args["volume"]))
            elif op == "split":
                split(c, str(args["id"]), float(args["at"]))
            elif op == "delete":
                ripple_delete(c, str(args["id"]))
            elif op == "snap":
                snap_to_beats(c, str(args.get("scene", "")))
            elif op == "transition":
                set_transition(c, str(args["id"]), str(args["kind"]), float(args.get("seconds", 0.8)))
            elif op == "duck":
                db = float(args["db"])
                if not 0 <= db <= 30:
                    raise EditError("ducking is 0-30 dB")
                c["duck_db"] = db
            else:
                raise EditError(f"unknown edit {op!r}")
        except (KeyError, TypeError) as e:
            raise EditError(f"the {op} edit needs {e}") from None
    save(pdir, d)
    return d


# ---------------------------------------------------------------------------------------------- the Editor's notes
def check_notes(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("notes"), list):
        raise ValueError('reply with {"notes": [{"op": "trim", "id": "v0003", "seconds": 3.2, "why": "..."}]}')
    for n in d["notes"]:
        if not isinstance(n, dict) or n.get("op") not in ("trim", "delete", "move", "transition") or not str(n.get("why", "")).strip():
            raise ValueError("every note has an op (trim, delete, move or transition), its id, its values and why")


def suggest(pdir: Path, ask: Ask, target_seconds: float | None = None) -> list[dict]:
    """The Editor's suggestions for the current cut, kept in edit/notes.json until accepted or dismissed."""
    d = load(pdir) or assemble(pdir)
    tl = timeline(cut(d))
    listing = "\n".join(f"{v['id']} {v['scene']} shot {v['shot']}: {v['seconds']} s, {v['transition']['kind']}" for v in tl["video"])
    r = ask(f"You are cutting this film. Its runtime is {tl['total']:.0f} s" + (f", the target is {target_seconds:.0f} s" if target_seconds else "")
            + ". Suggest cuts and pacing fixes: trim a clip (new seconds), delete a clip, move a clip (to a 0-based position), or a transition "
            '(cut or dissolve), each with why. Reply as JSON: {"notes": [{"op": "trim", "id": "v0003", "seconds": 3.2, "why": "..."}]}\n\n' + listing,
            "editor", "edit: suggestions", check_notes)
    notes = [{**n, "nid": f"n{i + 1}"} for i, n in enumerate(r["notes"])]
    (path(pdir).parent / "notes.json").write_text(json.dumps(notes, indent=1, ensure_ascii=False), encoding="utf-8")
    return notes


def notes(pdir: Path) -> list[dict]:
    try:
        return json.loads((path(pdir).parent / "notes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def apply_note(pdir: Path, nid: str, accept: bool = True) -> dict:
    ns = notes(pdir)
    n = next((x for x in ns if x["nid"] == nid), None)
    if n is None:
        raise EditError("no such note")
    d = load(pdir)
    if accept:
        args = {"trim": {"id": n.get("id"), "seconds": n.get("seconds")}, "delete": {"id": n.get("id")}, "move": {"id": n.get("id"), "to": n.get("to")},
                "transition": {"id": n.get("id"), "kind": n.get("kind", "dissolve")}}[n["op"]]
        d = apply(pdir, {"trim": "trim", "delete": "delete", "move": "move", "transition": "transition"}[n["op"]], args)
    (path(pdir).parent / "notes.json").write_text(json.dumps([x for x in ns if x["nid"] != nid], indent=1, ensure_ascii=False), encoding="utf-8")
    return d


def fake_ask() -> Ask:
    def ask(prompt: str, roles, step: str, validate: Callable[[dict], None]) -> dict:
        first = next((ln.split()[0] for ln in prompt.split("\n") if ln.startswith("v0")), "v0001")
        d = {"notes": [{"op": "trim", "id": first, "seconds": 2.5, "why": "get into the scene faster"}]}
        validate(d)
        return d
    return ask


def srt(c: dict, pdir: Path) -> str:
    """Subtitles from the voice track's lines (the sound plan's words, on the clock of this cut)."""
    plan = sound_design.load(pdir)
    by_row: dict[int, list[str]] = {}
    sl = shot_list.load(pdir)
    row = 0
    for sc in sl.get("scenes", []):
        for s in sc["shots"]:
            row += 1
            by_row[row] = [x["text"] for x in plan.get("lines", []) if x["scene"] == sc["id"] and x["shot"] == s["n"]]
    out, k = [], 0
    for a in timeline(c)["voice"]:
        text = " ".join(by_row.get(int(a["ref"]), []))
        if not text:
            continue
        k += 1
        out.append(f"{k}\n{_t(a['start'])} --> {_t(a['end'])}\n{text}\n")
    return "\n".join(out)


def _t(s: float) -> str:
    ms = round(s * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
