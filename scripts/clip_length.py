"""How long each shot's clip is: a length you set per shot (or "match the narration"), kept across rebuilds and written into all_shots.csv as a
"seconds" column. The video notebooks turn seconds into the number of frames their model can make (make_video.py, opt()).

clip_lengths.json in the book's folder: {"<chapter>#<shot>": seconds}. A blank or missing length means the video model's own length.
"""
import csv
import json
import os
import re
from pathlib import Path

from bookkit import WORDS_PER_SECOND, read_json, words

FILE = "clip_lengths.json"
LEAST, STEP = 1.0, 0.5                          # no longest clip: as long as you like
PAD = 0.4                                       # a breath after the last word


class ClipLengthError(ValueError):
    """A readable reason the length cannot be set."""


def load(pdir: Path) -> dict[str, float]:
    d = read_json(Path(pdir) / FILE, {}) or {}
    return {k: float(v) for k, v in d.items() if isinstance(v, (int, float))}


def _save(pdir: Path, d: dict) -> None:
    f = Path(pdir) / FILE
    if not d:
        f.unlink(missing_ok=True)
        return
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=1, sort_keys=True))
    os.replace(tmp, f)


def snap(seconds: float) -> float:
    """Round to the half second, at least LEAST."""
    return max(LEAST, round(float(seconds) / STEP) * STEP)


def spoken_seconds(audio_row: dict) -> float:
    """How long the words of a shot take to say: its narration, or all its dialogue lines."""
    text = audio_row.get("narration", "") or ""
    try:
        lines = json.loads(audio_row.get("lines_json") or "[]")
        said = " ".join(str(ln[1]) for ln in lines if isinstance(ln, list) and len(ln) > 1)
        if words(said) > words(text):
            text = said
    except (ValueError, TypeError):
        pass
    n = words(text)
    return round(n / WORDS_PER_SECOND + PAD, 2) if n else 0.0


def fit_narration(audio_row: dict, now: float | None = None) -> float:
    """The clip length that fits the words (up to the next half second), never shorter than the length the clip has now (`now`)."""
    s = spoken_seconds(audio_row)
    fit = snap(-(-s // STEP) * STEP) if s else LEAST
    return max(fit, snap(now)) if now else fit


def _rows(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames or []), list(r)


def apply(pdir: Path) -> int:
    """Write the saved lengths into all_shots.csv (a "seconds" column; blank for the model's own length). Returns how many rows have one."""
    pdir = Path(pdir)
    f = pdir / "all_shots.csv"
    if not f.is_file():
        return 0
    lengths = load(pdir)
    fields, rows = _rows(f)
    if not lengths and "seconds" not in fields:
        return 0
    if "seconds" not in fields:
        fields.append("seconds")
    n = 0
    for r in rows:
        v = lengths.get(f"{r.get('chapter', '')}#{r.get('shot', '')}")
        r["seconds"] = f"{v:g}" if v else ""
        n += bool(v)
    tmp = f.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, f)
    return n


def save_all(pdir: Path, lengths: dict[str, float]) -> None:
    """Save every length at once and write them into the CSV."""
    _save(pdir, {k: snap(v) for k, v in lengths.items() if v})
    apply(pdir)


def set_length(pdir: Path, key: str, seconds: float | None) -> float | None:
    """Save one shot's length (None: back to the model's own) and write it into the CSV. Returns the length saved."""
    if not re.fullmatch(r"[^#]{1,120}#\d{1,5}", key or ""):
        raise ClipLengthError("say which shot")
    d = load(pdir)
    if seconds is None:
        d.pop(key, None)
        value = None
    else:
        try:
            value = snap(seconds)
        except (TypeError, ValueError):
            raise ClipLengthError(f"a clip is at least {LEAST:g} second") from None
        d[key] = value
    _save(pdir, d)
    apply(pdir)
    return value
