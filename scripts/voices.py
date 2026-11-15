"""A distinct voice for every character, and how each line is delivered (emotion, speed, pause).

  voice_cast.json         {"cast": {"Eve": "af_bella", ...}}                       which Kokoro voice speaks a speaker (bookkit.apply_voice_cast)
  voice_direction.json    {"speakers": {"Eve": {"emotion": "sorrowful", "speed": 0.9, "pause": 0.5}},
                           "lines": {"<chapter>#<shot>#<line number from 1>": {"emotion": "whisper"}}}

Kokoro has no emotion control, so an emotion here means a pace: a speed for the words and a pause after the line (EMOTIONS). apply_direction() writes the
result as the fourth item of each line in audio_shots.csv / audio_chapters.csv: [speaker, text, voice, {"speed": 0.9, "pause": 0.5}], which the Kokoro
worker (make_audio.KOKORO_WORKER) reads. Other speech models ignore it.
"""
import json
import re
from pathlib import Path

from bookkit import KOKORO_VOICES, VOICE_MAP, _write_csv, read_csv, read_json, write_json

NARRATOR_VOICE = VOICE_MAP["narrator"]

DIRECTION_FILE = "voice_direction.json"
# emotion -> (speed multiplier, pause after the line in seconds)
EMOTIONS = {"neutral": (1.0, 0.35), "calm": (0.93, 0.45), "warm": (0.96, 0.4), "solemn": (0.84, 0.6), "sorrowful": (0.86, 0.6), "whisper": (0.88, 0.5),
            "fearful": (1.1, 0.25), "urgent": (1.12, 0.2), "angry": (1.08, 0.25), "excited": (1.15, 0.2)}
SPEED_RANGE, PAUSE_RANGE = (0.6, 1.3), (0.0, 2.0)
NOTE_WORDS = (("whisper", "whisper"), ("soft", "calm"), ("quiet", "calm"), ("gentl", "warm"), ("tender", "warm"), ("sad", "sorrowful"), ("weep", "sorrowful"), ("grie", "sorrowful"),
              ("solemn", "solemn"), ("grave", "solemn"), ("fear", "fearful"), ("afraid", "fearful"), ("terrif", "fearful"), ("urgent", "urgent"), ("hurr", "urgent"),
              ("shout", "angry"), ("angr", "angry"), ("furious", "angry"), ("excit", "excited"), ("joy", "excited"), ("eager", "excited"))
FEMALE_WORDS = re.compile(r"\b(woman|girl|she|her|female|mother|queen|lady|daughter|wife|sister|maiden|goddess)\b", re.I)
MALE_WORDS = re.compile(r"\b(man|boy|he|his|male|father|king|lord|son|husband|brother|youth)\b", re.I)
OLD_WORDS = re.compile(r"\b(old|elder|aged|ancient|grey|gray|white[- ]haired|wrinkled|patriarch|crone)\b", re.I)
YOUNG_WORDS = re.compile(r"\b(child|boy|girl|young|youth|teen|toddler|infant)\b", re.I)
FEMALE_POOL = ["af_bella", "af_nicole", "af_sarah", "af_heart", "af_nova", "af_river", "af_jessica", "af_kore", "af_aoede", "af_alloy", "bf_emma", "bf_isabella", "bf_alice", "bf_lily"]
MALE_POOL = ["am_michael", "am_adam", "am_eric", "am_liam", "am_onyx", "am_echo", "am_fenrir", "bm_daniel", "bm_fable", "bm_lewis", "am_puck"]


def direction_from_note(note: str) -> dict:
    """A screenplay note such as "whispering" or "softly" -> {"emotion": ...}, or {} when nothing matches."""
    n = (note or "").lower()
    for stem, emotion in NOTE_WORDS:
        if stem in n:
            return {"emotion": emotion}
    return {}


def resolve(spec: dict | None) -> dict:
    """{"emotion", "speed", "pause"} -> the {"speed", "pause"} to use (explicit numbers beat the emotion's), clamped; {} when it is the plain default."""
    spec = spec or {}
    speed, pause = EMOTIONS.get(spec.get("emotion") or "neutral", EMOTIONS["neutral"])
    for key, rng in (("speed", SPEED_RANGE), ("pause", PAUSE_RANGE)):
        v = spec.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if key == "speed":
                speed = min(max(float(v), rng[0]), rng[1])
            else:
                pause = min(max(float(v), rng[0]), rng[1])
    speed, pause = round(speed, 2), round(pause, 2)
    return {} if (speed, pause) == EMOTIONS["neutral"] else {"speed": speed, "pause": pause}


def check_spec(spec) -> dict:
    """Validate one direction from the page: {"emotion"?, "speed"?, "pause"?}. Returns the cleaned dict."""
    if not isinstance(spec, dict):
        raise ValueError("a direction is {emotion, speed, pause}")
    out = {}
    if spec.get("emotion"):
        if spec["emotion"] not in EMOTIONS:
            raise ValueError(f"emotion must be one of {', '.join(EMOTIONS)}")
        out["emotion"] = spec["emotion"]
    for key, rng in (("speed", SPEED_RANGE), ("pause", PAUSE_RANGE)):
        if spec.get(key) not in (None, ""):
            try:
                v = float(spec[key])
            except (TypeError, ValueError) as e:
                raise ValueError(f"{key} must be a number") from e
            if not rng[0] <= v <= rng[1]:
                raise ValueError(f"{key} must be {rng[0]:g} to {rng[1]:g}")
            out[key] = v
    return out


def read_direction(pdir: Path) -> dict:
    d = read_json(Path(pdir) / DIRECTION_FILE, {})
    d = d if isinstance(d, dict) else {}
    return {"speakers": d.get("speakers") if isinstance(d.get("speakers"), dict) else {}, "lines": d.get("lines") if isinstance(d.get("lines"), dict) else {}}


def save_direction(pdir: Path, speakers: dict | None = None, lines: dict | None = None) -> dict:
    cur = read_direction(pdir)
    if speakers is not None:
        cur["speakers"] = {str(k).strip()[:60]: check_spec(v) for k, v in speakers.items() if str(k).strip() and check_spec(v)}
    if lines is not None:
        cur["lines"] = {str(k): check_spec(v) for k, v in lines.items() if check_spec(v)}
    write_json(Path(pdir) / DIRECTION_FILE, cur)
    return cur


def apply_direction(pdir: Path) -> list[int]:
    """Write the saved direction into every line of audio_shots.csv and audio_chapters.csv. A line's own direction beats its speaker's. Lines without any keep
    their old shape. Returns the audio_shots.csv row numbers (the narration file numbers) whose lines changed."""
    pdir = Path(pdir)
    d = read_direction(pdir)
    by_speaker = {k.lower(): v for k, v in d["speakers"].items()}
    changed_rows: list[int] = []
    for name in ("audio_shots.csv", "audio_chapters.csv"):
        rows = read_csv(pdir / name)
        hit = False
        for i, r in enumerate(rows, start=1):
            try:
                lines = json.loads(r.get("lines_json") or "[]")
            except ValueError:
                continue
            if not isinstance(lines, list):
                continue
            new = []
            for k, ln in enumerate(lines, start=1):
                if isinstance(ln, list) and len(ln) >= 2:
                    spec = d["lines"].get(f"{r.get('chapter')}#{r.get('shot')}#{k}") or by_speaker.get(str(ln[0]).strip().lower())
                    res = resolve(spec)
                    head = list(ln[:3])
                    if res:
                        ln = head + [""] * (3 - len(head)) + [res]          # [speaker, text, voice, {"speed", "pause"}]; the voice stays empty when none was cast
                    elif len(ln) > 3:                                      # an older direction is removed, and the empty voice slot it needed with it
                        while len(head) > 2 and head[-1] == "":
                            head.pop()
                        ln = head
                new.append(ln)
            if new != lines:
                r["lines_json"] = json.dumps(new, ensure_ascii=False)
                hit = True
                if name == "audio_shots.csv":
                    changed_rows.append(i)
        if hit:
            _write_csv(pdir / name, rows)
    return changed_rows


# ------------------------------------------------------------------------------------------ a distinct voice per character
def guess_traits(text: str) -> dict:
    """{"sex": "f"|"m"|"", "old": bool, "young": bool} from a character's description."""
    f, m = len(FEMALE_WORDS.findall(text or "")), len(MALE_WORDS.findall(text or ""))
    return {"sex": "f" if f > m else "m" if m > f else "", "old": bool(OLD_WORDS.search(text or "")), "young": bool(YOUNG_WORDS.search(text or ""))}


def auto_cast(characters: list[dict], keep: dict[str, str] | None = None) -> dict[str, str]:
    """A different Kokoro voice for each character, in the order given (put the most important first). `keep` (name -> voice) are voices you chose: they stay
    and are not given to anyone else. The narrator keeps NARRATOR_VOICE. Falls back to reusing a voice only when more characters than voices exist."""
    keep = {k: v for k, v in (keep or {}).items() if v in KOKORO_VOICES}
    taken = set(keep.values()) | {NARRATOR_VOICE}
    cast = dict(keep)
    for c in characters:
        name = str(c.get("name") or "").strip()
        if not name or name in cast or name.upper() == "NARRATOR":
            continue
        t = guess_traits(f"{c.get('token', '')} {c.get('voice', '')}")
        sex = t["sex"] or ("f" if str(c.get("voice", "")).lower() in ("female", "girl", "woman") else "m" if str(c.get("voice", "")).lower() in ("male", "boy", "man", "elder") else "")
        pools = [FEMALE_POOL] if sex == "f" else [MALE_POOL] if sex == "m" else [MALE_POOL, FEMALE_POOL]
        prefer: list[str] = []
        if t["old"]:
            prefer = ["bf_isabella", "af_nicole"] if sex == "f" else ["bm_lewis", "bm_fable", "am_onyx"]
        if t["young"]:
            prefer = ["af_nova", "af_heart"] if sex == "f" else ["am_puck", "am_liam"]
        order = prefer + [v for pool in pools for v in pool]
        pick = next((v for v in order if v not in taken), None) or order[len(cast) % len(order)]
        cast[name] = pick
        taken.add(pick)
    return cast
