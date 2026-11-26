#!/usr/bin/env python3
"""The director's breakdown and the shot list (BOOK_TO_SCREEN_BUILD.md Sections 3.3 and 6, milestone M4).

  python3 shot_list.py <project> [--engine claude|... |fake] [--model M] [--force]

Per scene of the screenplay, the Director, the Cinematographer (DP) and the Editor write together:
  breakdown  {intent, emotional_beat, blocking, performance}: the director's notes, using the characters' personality profiles
  shots      [{n, type, lens_mm, height, angle, movement, composition, lighting, blocking, action, expression, dialogue, sound, seconds,
               transition, priority 1-3, characters[], props[], source: ai | footage}]
Then the critique loop of Section 3.3: the Script Supervisor checks continuity against the continuity book (wardrobe, props, injuries, time
of day, screen direction) and the fixes are applied; the Editor checks the pacing (runtime against the target) and the shot lengths are fitted.
The result is projects/books/<book>/shots/shotlist.json; each scene's answer is cached, so a re-run only redoes scenes that changed.
The page edits it (edit_shot / move_shot / delete_shot / add_shot) and the owner approves it (gates.py, step "shotlist").
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptation  # noqa: E402
import continuity_book  # noqa: E402
import crew  # noqa: E402
import production  # noqa: E402
import screenplay  # noqa: E402

SHOT_TYPES = ("ECU", "CU", "MCU", "MS", "MLS", "LS", "ELS", "WS", "OTS", "POV", "INSERT", "TWO SHOT", "GROUP")
HEIGHTS = ("ground", "low", "eye", "shoulder", "high", "overhead")
MOVES = ("static", "pan", "tilt", "dolly in", "dolly out", "truck", "crane", "handheld", "steadicam", "zoom", "push in", "pull out", "tracking")
TRANSITIONS = ("cut", "dissolve", "match cut", "smash cut", "fade in", "fade out", "whip pan", "j-cut", "l-cut")
TEXT_FIELDS = ("composition", "lighting", "blocking", "action", "expression", "dialogue", "sound", "angle")
EDITABLE = (*TEXT_FIELDS, "type", "lens_mm", "height", "movement", "seconds", "transition", "priority", "characters", "props", "source")
MIN_SECONDS, MAX_SECONDS = 1.5, 12.0
PACE_TOLERANCE = 0.10
Ask = Callable[[str, str | list[str], str, Callable[[dict], None]], dict]


class ShotListError(RuntimeError):
    """The shot list cannot be made or changed as asked; the message says why."""


def path(pdir: Path) -> Path:
    return pdir / "shots" / "shotlist.json"


def load(pdir: Path) -> dict:
    try:
        d = json.loads(path(pdir).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save(pdir: Path, d: dict) -> None:
    d["runtime_seconds"] = round(sum(float(s["seconds"]) for sc in d.get("scenes", []) for s in sc["shots"]), 1)
    path(pdir).parent.mkdir(parents=True, exist_ok=True)
    tmp = path(pdir).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path(pdir))


_TYPE_ALIASES: dict[str, str] = {
    "TWO-SHOT": "TWO SHOT", "2-SHOT": "TWO SHOT", "2 SHOT": "TWO SHOT",
    "GROUP SHOT": "GROUP", "CLOSE-UP": "CU", "CLOSE UP": "CU", "CLOSEUP": "CU",
    "EXTREME CLOSE-UP": "ECU", "EXTREME CLOSE UP": "ECU", "MEDIUM CLOSE-UP": "MCU", "MEDIUM CLOSE UP": "MCU",
    "MEDIUM SHOT": "MS", "MEDIUM": "MS", "MEDIUM LONG SHOT": "MLS", "MEDIUM WIDE": "MLS", "MWS": "MLS",
    "LONG SHOT": "LS", "FULL SHOT": "LS", "FS": "LS",
    "EXTREME LONG SHOT": "ELS", "EXTREME WIDE": "ELS", "EWS": "ELS", "ESTABLISHING": "ELS", "ESTABLISHING SHOT": "ELS",
    "WIDE SHOT": "WS", "WIDE": "WS", "OVER THE SHOULDER": "OTS", "OVER-THE-SHOULDER": "OTS", "OS": "OTS",
    "POINT OF VIEW": "POV", "DETAIL": "INSERT", "DETAIL SHOT": "INSERT", "CUTAWAY": "INSERT",
}

_HEIGHT_ALIASES: dict[str, str] = {
    "ground level": "ground", "floor": "ground", "floor level": "ground", "worm's eye": "ground", "worms eye": "ground", "worm eye": "ground",
    "low angle": "low", "knee": "low", "knee level": "low", "hip": "low", "hip level": "low", "table": "low", "table level": "low", "tabletop": "low", "dog": "low", "dog level": "low", "dog eye": "low",
    "eye level": "eye", "neutral": "eye", "normal": "eye", "mid": "eye", "medium": "eye", "waist": "eye", "waist level": "eye", "chest": "eye", "chest level": "eye", "child eye": "eye", "child's eye": "eye", "kid eye": "eye", "subject eye": "eye", "seated": "eye", "standing": "eye",
    "shoulder level": "shoulder", "over shoulder": "shoulder",
    "high angle": "high", "elevated": "high", "adult eye": "high", "adult's eye": "high",
    "top down": "overhead", "bird's eye": "overhead", "birds eye": "overhead", "bird eye": "overhead", "aerial": "overhead", "god's eye": "overhead", "gods eye": "overhead", "top": "overhead", "ceiling": "overhead",
}

_MOVE_ALIASES: dict[str, str] = {
    "none": "static", "still": "static", "fixed": "static", "locked": "static", "locked off": "static", "tripod": "static", "hold": "static", "stationary": "static",
    "pan left": "pan", "pan right": "pan", "panning": "pan", "whip pan": "pan", "swish pan": "pan", "pan across": "pan",
    "tilt up": "tilt", "tilt down": "tilt", "tilting": "tilt", "pedestal": "tilt", "pedestal up": "tilt", "pedestal down": "tilt",
    "dolly": "dolly in", "dolly forward": "dolly in", "push": "push in", "creep in": "push in", "move in": "push in", "drift in": "push in",
    "dolly back": "dolly out", "dolly backward": "dolly out", "pull": "pull out", "pull back": "pull out", "drift out": "pull out", "retreat": "pull out",
    "lateral": "truck", "sideways": "truck", "truck left": "truck", "truck right": "truck", "slide": "truck", "slider": "truck", "dolly lateral": "truck",
    "boom": "crane", "boom up": "crane", "boom down": "crane", "jib": "crane", "jib up": "crane", "jib down": "crane", "crane up": "crane", "crane down": "crane", "rise": "crane", "rising": "crane", "descend": "crane", "descending": "crane", "swoop": "crane", "elevation": "crane",
    "hand held": "handheld", "shaky": "handheld", "shake": "handheld", "camera shake": "handheld", "rumble": "handheld", "vibrating": "handheld", "vibration": "handheld",
    "steadycam": "steadicam", "gimbal": "steadicam", "stabilized": "steadicam", "floating": "steadicam",
    "zoom in": "zoom", "zoom out": "zoom", "crash zoom": "zoom", "snap zoom": "zoom", "dolly zoom": "zoom", "zooming": "zoom",
    "track": "tracking", "follow": "tracking", "following": "tracking", "orbit": "tracking", "orbiting": "tracking", "arc": "tracking", "arcing": "tracking", "circle": "tracking", "circling": "tracking", "drift": "tracking", "drifting": "tracking", "glide": "tracking", "gliding": "tracking", "sweep": "tracking", "sweeping": "tracking", "dolly track": "tracking",
}

_TRANSITION_ALIASES: dict[str, str] = {
    "": "cut", "none": "cut", "hard cut": "cut", "straight cut": "cut", "standard cut": "cut", "direct cut": "cut", "jump cut": "cut", "cut to": "cut", "end": "cut", "end of scene": "cut",
    "match": "match cut", "graphic match": "match cut", "visual match": "match cut", "audio match": "match cut", "sound match": "match cut",
    "smash": "smash cut", "impact cut": "smash cut", "hard smash cut": "smash cut",
    "cross dissolve": "dissolve", "crossfade": "dissolve", "cross fade": "dissolve", "lap dissolve": "dissolve", "fade": "dissolve", "morph": "dissolve", "soft dissolve": "dissolve",
    "fade from black": "fade in", "fade up": "fade in", "iris in": "fade in",
    "fade to black": "fade out", "fade to white": "fade out", "fade down": "fade out", "iris out": "fade out", "wipe": "fade out", "iris": "fade out",
    "swish pan": "whip pan", "whip": "whip pan",
    "j cut": "j-cut", "jcut": "j-cut",
    "l cut": "l-cut", "lcut": "l-cut",
}

_MODIFIER_WORDS_RE = re.compile(r"\b(?:slow|slowly|gentle|gently|subtle|subtly|slight|slightly|smooth|smoothly|quick|quickly|fast|rapid|gradual|gradually|micro|very|soft|softly|steady|steadily|dramatic|sweeping|slight|tight|wide)\b")


def _norm_spaces(val: str) -> str:
    return " ".join(re.sub(r"[-_/]+", " ", str(val or "").lower()).split())


def _normalize_type(raw: object) -> str:
    t = " ".join(str(raw or "").upper().split())
    if t in SHOT_TYPES:
        return t
    if t in _TYPE_ALIASES:
        return _TYPE_ALIASES[t]
    cleaned = t.replace("-", " ")
    if cleaned in SHOT_TYPES:
        return cleaned
    return _TYPE_ALIASES.get(cleaned, t)


def _normalize_height(raw: object) -> str:
    h = str(raw or "eye").lower().strip()
    if h in HEIGHTS:
        return h
    norm = _norm_spaces(h)
    if norm in HEIGHTS:
        return norm
    if norm in _HEIGHT_ALIASES:
        return _HEIGHT_ALIASES[norm]
    stripped = " ".join(_MODIFIER_WORDS_RE.sub(" ", norm).split())
    if stripped in HEIGHTS:
        return stripped
    if stripped in _HEIGHT_ALIASES:
        return _HEIGHT_ALIASES[stripped]
    # Check phrase prefixes/suffixes like "eye level with Tommy"
    for cand in (*HEIGHTS, *_HEIGHT_ALIASES):
        if norm.startswith(cand + " ") or norm.endswith(" " + cand):
            return cand if cand in HEIGHTS else _HEIGHT_ALIASES[cand]
    return h


def _normalize_move(raw: object) -> str:
    mv = str(raw or "static").lower().strip()
    if mv in MOVES:
        return mv
    # If compound movement ("dolly in and tilt up", "slow pan / tracking"), evaluate primary phrase first
    primary = re.split(r"\s*(?:,|/|&|\+|\band\b|\bto\b|\binto\b|\bwith\b)\s*", mv, maxsplit=1)[0].strip()
    for candidate in (mv, primary):
        norm = _norm_spaces(candidate)
        if norm in MOVES:
            return norm
        if norm in _MOVE_ALIASES:
            return _MOVE_ALIASES[norm]
        stripped = " ".join(_MODIFIER_WORDS_RE.sub(" ", norm).split())
        if stripped in MOVES:
            return stripped
        if stripped in _MOVE_ALIASES:
            return _MOVE_ALIASES[stripped]
        for key in (*MOVES, *_MOVE_ALIASES):
            if stripped.startswith(key + " ") or stripped.endswith(" " + key):
                return key if key in MOVES else _MOVE_ALIASES[key]
    return mv


def _normalize_transition(raw: object) -> str:
    tr = str(raw or "cut").lower().strip()
    if tr in TRANSITIONS:
        return tr
    norm = _norm_spaces(tr)
    if norm in TRANSITIONS:
        return norm
    if norm in _TRANSITION_ALIASES:
        return _TRANSITION_ALIASES[norm]
    stripped = " ".join(_MODIFIER_WORDS_RE.sub(" ", norm).split())
    if stripped in TRANSITIONS:
        return stripped
    if stripped in _TRANSITION_ALIASES:
        return _TRANSITION_ALIASES[stripped]
    return tr


# ---------------------------------------------------------------------------------------------- checking one shot
def clean_shot(s: dict, n: int) -> dict:
    """A checked shot (ValueError says what is wrong, for the AI or for the page)."""
    if not isinstance(s, dict):
        raise ValueError("every shot is an object")
    t = _normalize_type(s.get("type", ""))
    if t not in SHOT_TYPES:
        raise ValueError(f"shot type {t!r} must be one of {', '.join(SHOT_TYPES)}")
    try:
        raw_lens = str(s.get("lens_mm", 0)).lower().replace("mm", "").strip()
        raw_secs = str(s.get("seconds", 0)).lower().removesuffix("sec").removesuffix("s").strip()
        lens = int(float(raw_lens))
        secs = float(raw_secs)
        prio = int(s.get("priority", 2))
    except (TypeError, ValueError):
        raise ValueError("lens_mm, seconds and priority are numbers") from None
    if not 8 <= lens <= 600:
        raise ValueError("lens_mm is the focal length in mm (8-600)")
    if not MIN_SECONDS <= secs <= 60:
        raise ValueError(f"seconds is the shot's length ({MIN_SECONDS}-60)")
    if prio not in (1, 2, 3):
        raise ValueError("priority is 1 (must have), 2 or 3 (nice to have)")
    h = _normalize_height(s.get("height", "eye"))
    mv = _normalize_move(s.get("movement", "static"))
    tr = _normalize_transition(s.get("transition", "cut"))
    if h not in HEIGHTS or mv not in MOVES or tr not in TRANSITIONS:
        raise ValueError(
            f"invalid camera/transition (got height={h!r}, movement={mv!r}, transition={tr!r}): "
            f"height is one of {', '.join(HEIGHTS)}; movement one of {', '.join(MOVES)}; transition one of {', '.join(TRANSITIONS)}"
        )
    if not str(s.get("action", "")).strip():
        raise ValueError("every shot says what happens in it ('action')")
    src = str(s.get("source", "ai")).lower()
    if src not in ("ai", "footage"):
        raise ValueError("source is ai or footage")
    lists = {k: [str(x)[:60] for x in s.get(k, []) if str(x).strip()] if isinstance(s.get(k, []), list) else [] for k in ("characters", "props")}
    return {"n": n, "type": t, "lens_mm": lens, "height": h, "angle": str(s.get("angle", "straight"))[:60], "movement": mv,
            **{k: " ".join(str(s.get(k, "")).split())[:600] for k in TEXT_FIELDS if k != "angle"}, "seconds": round(secs, 1), "transition": tr,
            "priority": prio, **lists, "source": src}


def check_scene_reply(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("breakdown"), dict) or not isinstance(d.get("shots"), list) or not d["shots"]:
        raise ValueError('reply with {"breakdown": {...}, "shots": [...]} and at least one shot')
    for k in ("intent", "emotional_beat", "blocking", "performance"):
        if not str(d["breakdown"].get(k, "")).strip():
            raise ValueError(f"the breakdown needs '{k}'")
    for i, s in enumerate(d["shots"], 1):
        clean_shot(s, i)


def check_continuity_reply(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("issues"), list):
        raise ValueError('reply with {"issues": [...]} (an empty list when everything matches)')
    for i in d["issues"]:
        if not isinstance(i, dict) or not str(i.get("issue", "")).strip():
            raise ValueError("every issue needs 'issue' (and 'scene', 'shot', 'field', 'value' for the fix)")


# ---------------------------------------------------------------------------------------------- writing it
def scenes_of(pdir: Path) -> list[dict]:
    plan = adaptation.load(pdir) or {}
    try:
        blocks = {i: s.get("block", {}) for i, s in enumerate(json.loads((pdir / "readin" / "screenplay.json").read_text(encoding="utf-8"))["scenes"], 1)}
    except (OSError, ValueError, KeyError):
        blocks = {}
    out = []
    for i, s in enumerate(plan.get("scenes", []), 1):
        sc = screenplay.load_scene(pdir, s["id"])
        if sc:
            out.append({"id": s["id"], "heading": sc["heading"], "elements": sc["elements"], "seconds": float(s.get("seconds", 30)),
                        "block": blocks.get(i, {"characters": s.get("characters", []), "location": s.get("location", ""), "time_of_day": s.get("time_of_day", "")})})
    if not out:
        raise ShotListError("There is no screenplay yet: press Read it in first.")
    return out


def people(book: dict) -> str:
    return "\n".join(f"- {c['name']}: {c['token']}. Personality: " + "; ".join(f"{k} {v}" for k, v in (c.get("personality") or {}).items())
                     for c in book.get("characters", []))


SCENE_PROMPT = """Break down scene {n} of {of} and write its shot list. First the director's breakdown (intent, emotional beat, blocking,
performance notes using the characters' personalities), then the shots: shot type ({types}), lens in mm, camera height ({heights}), angle,
movement ({moves}), composition, lighting setup, blocking, action, expression, the dialogue spoken in the shot, sound, length in seconds,
transition to the next shot ({transitions}), priority (1 must have, 3 nice to have), characters and props in frame, and source "ai" (or
"footage" when the owner's own footage will be used). The shots together run about {seconds} seconds. {rules}
STRICT CONTINUITY RULES:
- WARDROBE LOCK: Every character must keep their exact, singular locked outfit and exact clothing colours from the continuity book across every shot in this scene (never change or improvise clothing mid-scene; an outfit change belongs in a new scene).
- LOCATION LOCK: Keep every shot strictly anchored in this scene's single locked location, spatial layout, and background props; characters stay in this location until a scene transition explicitly moves them to the next scene's location.
- SMOOTH FLOW & STORYLINE BRIDGES: Sequence shots for effortless visual rhythm and clear spatial continuity; when opening or closing a scene that jumps to or from a parallel storyline, choose a deliberate transition (match cut, L-cut/J-cut sound bridge, or clean establishing shot) so the cut flows smoothly.
Reply as JSON: {{"breakdown": {{"intent": "...", "emotional_beat": "...", "blocking": "...", "performance": "..."}}, "shots": [{{"type": "WS",
"lens_mm": 24, "height": "eye", "angle": "straight", "movement": "static", "composition": "...", "lighting": "...", "blocking": "...",
"action": "...", "expression": "...", "dialogue": "", "sound": "...", "seconds": 4, "transition": "cut", "priority": 1, "characters": [],
"props": [], "source": "ai"}}]}}

THE CHARACTERS (from the continuity book):
{people}

THE SCENE:
{scene}"""


def scene_key(sc: dict, book: dict) -> str:
    return hashlib.sha256(json.dumps([sc["heading"], sc["elements"], sc["block"], book.get("characters", [])], sort_keys=True).encode()).hexdigest()[:16]


def write(pdir: Path, ask: Ask, say: Callable[[str], None] = print, force: bool = False) -> dict:
    book = continuity_book.load(pdir)
    if not book.get("characters"):
        raise ShotListError("There is no continuity book yet: make it first (Continuity book card).")
    settings = production.load(pdir)
    rules = (f"Aspect ratio {settings['aspect']}. Rating {production.RATINGS[settings['rating']]}.")
    scenes = scenes_of(pdir)
    cache_dir = pdir / "shots" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_scenes = []
    for i, sc in enumerate(scenes, 1):
        key = scene_key(sc, book)
        cache = cache_dir / f"{sc['id']}-{key}.json"
        if cache.is_file() and not force:
            d = json.loads(cache.read_text(encoding="utf-8"))
        else:
            say(f"Your director and cinematographer are breaking down scene {i} of {len(scenes)}")
            text = sc["heading"] + "\n" + "\n".join((f"{e['character']}: " if e["type"] == "dialogue" else "") + e["text"] for e in sc["elements"])
            d = ask(SCENE_PROMPT.format(n=i, of=len(scenes), types=", ".join(SHOT_TYPES), heights=", ".join(HEIGHTS), moves=", ".join(MOVES),
                                        transitions=", ".join(TRANSITIONS), seconds=round(sc["seconds"]), rules=rules, people=people(book),
                                        scene=text + f"\nBLOCK: {json.dumps(sc['block'], ensure_ascii=False)}"),
                    ["director", "cinematographer", "editor"], f"shot list: scene {i}", check_scene_reply)
            cache.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        out_scenes.append({"id": sc["id"], "heading": sc["heading"], "breakdown": {k: str(d["breakdown"][k]) for k in ("intent", "emotional_beat", "blocking", "performance")},
                           "shots": [clean_shot(s, n) for n, s in enumerate(d["shots"], 1)], "target_seconds": sc["seconds"]})
    data = {"scenes": out_scenes, "target_seconds": round(settings["target_minutes"] * 60, 1), "checks": {}}
    say("Your script supervisor is checking continuity")
    data["checks"]["continuity"] = continuity_check(data, book, ask)
    say("Your editor is checking the pacing")
    data["checks"]["pacing"] = pace(data)
    save(pdir, data)
    say(f"Done: {sum(len(s['shots']) for s in out_scenes)} shots in {len(out_scenes)} scenes, {round(load(pdir)['runtime_seconds'] / 60, 1)} minutes.")
    return load(pdir)


def continuity_check(data: dict, book: dict, ask: Ask) -> list[dict]:
    """The Script Supervisor's continuity notes; a note with scene, shot, field and value is applied as a fix (text fields only)."""
    listing = "\n".join(f"scene {sc['id']} shot {s['n']}: {s['type']} | chars {', '.join(s['characters'])} | props {', '.join(s['props'])} | {s['action']} | "
                        f"light: {s['lighting']}" for sc in data["scenes"] for s in sc["shots"])
    d = ask("Check this shot list for continuity against the continuity book: wardrobe, props, injuries, time of day, screen direction, who is "
            "in frame. For each problem give the scene id, the shot number, the field to change (one of " + ", ".join(TEXT_FIELDS) + ") and its "
            'new text. Reply as JSON: {"issues": [{"scene": "S001", "shot": 2, "issue": "...", "field": "action", "value": "..."}]}\n\n'
            f"CONTINUITY BOOK:\n{people(book)}\nLocations: " + "; ".join(f"{x['name']}: {x['token']}" for x in book.get("locations", []))
            + "\nProps: " + "; ".join(f"{x['name']}: {x['token']}" for x in book.get("props", [])) + f"\n\nSHOT LIST:\n{listing}",
            "script_supervisor", "shot list: continuity check", check_continuity_reply)
    notes = []
    for i in d["issues"]:
        fixed = False
        sc = next((x for x in data["scenes"] if x["id"] == str(i.get("scene", ""))), None)
        shot = next((s for s in sc["shots"] if s["n"] == int(i.get("shot", 0) or 0)), None) if sc else None
        if shot is not None and i.get("field") in TEXT_FIELDS and str(i.get("value", "")).strip():
            shot[i["field"]] = " ".join(str(i["value"]).split())[:600]
            fixed = True
        notes.append({"scene": i.get("scene", ""), "shot": i.get("shot", 0), "issue": str(i["issue"]), "fixed": fixed})
    return notes


def pace(data: dict) -> dict:
    """The Editor's pacing check: when the runtime is more than 10% off the target, every shot's length is scaled (within 1.5-12 s; the
    priority-3 shots give or take the most), and the note says by how much."""
    shots = [s for sc in data["scenes"] for s in sc["shots"]]
    runtime = sum(s["seconds"] for s in shots)
    target = data["target_seconds"]
    if not shots or not target or abs(runtime - target) <= PACE_TOLERANCE * target:
        return {"runtime": round(runtime, 1), "target": target, "changed": 0, "note": "The pacing fits the target length."}
    planned = runtime
    for _ in range(4):
        runtime = sum(s["seconds"] for s in shots)
        if abs(runtime - target) <= PACE_TOLERANCE * target / 2:
            break
        factor = target / runtime
        for s in shots:
            weight = {1: 0.6, 2: 1.0, 3: 1.4}[s["priority"]]
            s["seconds"] = round(min(MAX_SECONDS, max(MIN_SECONDS, s["seconds"] * (1 + (factor - 1) * weight))), 1)
    after = round(sum(s["seconds"] for s in shots), 1)
    word = "trimmed" if after < planned else "lengthened"
    return {"runtime": after, "target": target, "changed": len(shots),
            "note": f"The editor {word} the shots to fit: {round(planned)} s planned, {round(after)} s now, {round(target)} s wanted."
                    + ("" if abs(after - target) <= PACE_TOLERANCE * target else " Add or cut scenes to get closer (each shot is kept between 1.5 and 12 s).")}


# ---------------------------------------------------------------------------------------------- editing by hand
def _scene(d: dict, sid: str) -> dict:
    sc = next((s for s in d.get("scenes", []) if s["id"] == sid), None)
    if sc is None:
        raise ShotListError(f"no scene {sid}")
    return sc


def _renumber(sc: dict) -> None:
    for i, s in enumerate(sc["shots"], 1):
        s["n"] = i


def edit_shot(pdir: Path, sid: str, n: int, fields: dict) -> dict:
    d = load(pdir)
    sc = _scene(d, sid)
    if not 1 <= n <= len(sc["shots"]):
        raise ShotListError(f"scene {sid} has no shot {n}")
    new = {**sc["shots"][n - 1], **{k: v for k, v in fields.items() if k in EDITABLE}}
    try:
        sc["shots"][n - 1] = clean_shot(new, n)
    except ValueError as e:
        raise ShotListError(str(e)) from e
    save(pdir, d)
    return sc["shots"][n - 1]


def move_shot(pdir: Path, sid: str, n: int, to: int) -> list[dict]:
    d = load(pdir)
    sc = _scene(d, sid)
    if not (1 <= n <= len(sc["shots"]) and 1 <= to <= len(sc["shots"])):
        raise ShotListError("no such shot position")
    sc["shots"].insert(to - 1, sc["shots"].pop(n - 1))
    _renumber(sc)
    save(pdir, d)
    return sc["shots"]


def delete_shot(pdir: Path, sid: str, n: int) -> list[dict]:
    d = load(pdir)
    sc = _scene(d, sid)
    if len(sc["shots"]) <= 1:
        raise ShotListError("a scene keeps at least one shot")
    if not 1 <= n <= len(sc["shots"]):
        raise ShotListError(f"scene {sid} has no shot {n}")
    sc["shots"].pop(n - 1)
    _renumber(sc)
    save(pdir, d)
    return sc["shots"]


def add_shot(pdir: Path, sid: str, after: int) -> list[dict]:
    """A copy of shot `after` (to change), placed after it."""
    d = load(pdir)
    sc = _scene(d, sid)
    if not 1 <= after <= len(sc["shots"]):
        raise ShotListError(f"scene {sid} has no shot {after}")
    sc["shots"].insert(after, dict(sc["shots"][after - 1]))
    _renumber(sc)
    save(pdir, d)
    return sc["shots"]


def gate_data(d: dict) -> list:
    """What the approval covers: every scene's shots (not the computed runtime or the notes)."""
    return [[sc["id"], sc["shots"]] for sc in d.get("scenes", [])]


def fake_ask(pdir: Path) -> Ask:
    def ask(prompt: str, roles, step: str, validate: Callable[[dict], None]) -> dict:
        if "continuity check" in step:
            first = prompt.split("SHOT LIST:\n", 1)[-1].split(" ", 4)
            d: dict = {"issues": [{"scene": first[1], "shot": 1, "issue": "The lamp is lit in the next shot: keep it lit.", "field": "lighting",
                                   "value": "warm lamplight from the brass lamp, cold moonlight through the window"}]}
        else:
            people_ = [ln[2:].split(":")[0] for ln in prompt.split("THE CHARACTERS (from the continuity book):\n", 1)[-1].split("\n") if ln.startswith("- ")][:1]
            d = {"breakdown": {"intent": "show her resolve", "emotional_beat": "dread to resolve", "blocking": "she crosses to the window",
                               "performance": "slow, sure steps, rubs the scar"},
                 "shots": [{"type": t, "lens_mm": lens, "height": "eye", "angle": "straight", "movement": mv, "composition": "rule of thirds",
                            "lighting": "low-key, practical lamp", "blocking": "at the window", "action": a, "expression": "set jaw", "dialogue": "",
                            "sound": "wind, sea", "seconds": 4, "transition": "cut", "priority": p, "characters": people_, "props": ["the lamp"], "source": "ai"}
                           for t, lens, mv, a, p in (("WS", 24, "static", "She climbs the last stairs.", 1), ("MCU", 50, "push in", "She lights the lamp.", 1),
                                                     ("CU", 85, "static", "Her eyes on the sea.", 3))]}
        validate(d)
        return d
    return ask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex", "hf", "local", "fake"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    from layout import project_dir
    pdir = project_dir(a.project, "book")
    if not pdir.is_dir():
        print(f"no book called {a.project}", flush=True)
        return 1
    if a.engine == "fake":
        ask = fake_ask(pdir)
    else:
        import bookkit

        def ask(prompt, roles, step, validate):
            return bookkit.llm_json(prompt, crew.system(roles, pdir, step), model=a.model, engine=a.engine, validate=validate)
    try:
        write(pdir, ask, lambda t: print(t, flush=True), force=a.force)
    except (ShotListError, RuntimeError) as e:
        print(f"The shot list was not made: {e}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
