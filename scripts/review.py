"""Shot review for the storyboard: approve or reject each shot, with a note, and re-roll the rejected ones.

  projects/books/<book>/review.json   {"shots": {"<chapter label>#<shot>": {"status": "approved"|"rejected", "note": "...", "at": "..."}}}

A shot with no entry is "pending". The key is the chapter label and shot number of all_shots.csv (not the row number), so the verdicts survive a rebuild of the CSVs
as long as the shot keeps its place in its chapter. Re-rolling a shot (takes.retake) puts it back to pending.
"""
import json
import os
import time
from pathlib import Path

from bookkit import read_json

STATUSES = ("approved", "rejected", "pending")


class ReviewError(ValueError):
    """A readable reason a review change is not acceptable."""


def review_file(pdir: Path) -> Path:
    return Path(pdir) / "review.json"


def shot_key(row: dict) -> str:
    return f"{row.get('chapter', '')}#{row.get('shot', '')}"


def load(pdir: Path) -> dict:
    d = read_json(review_file(pdir), {})
    return d.get("shots", {}) if isinstance(d, dict) and isinstance(d.get("shots"), dict) else {}


def _save(pdir: Path, shots: dict) -> None:
    f = review_file(pdir)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"shots": shots}, indent=1, ensure_ascii=False))
    os.replace(tmp, f)


def set_status(pdir: Path, keys: list[str], status: str, note: str = "", valid: set[str] | None = None) -> dict:
    """Give the shots a verdict ("pending" removes it). `valid` is the set of keys that exist; others are refused."""
    if status not in STATUSES:
        raise ReviewError(f"status must be one of {', '.join(STATUSES)}")
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and "#" in k for k in keys):
        raise ReviewError("say which shots")
    if valid is not None and not set(keys) <= valid:
        raise ReviewError(f"unknown shot: {sorted(set(keys) - valid)[0]}")
    note = " ".join(str(note or "").split())[:300]
    shots = load(pdir)
    for k in keys:
        if status == "pending":
            shots.pop(k, None)
        else:
            shots[k] = {"status": status, "note": note, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _save(pdir, shots)
    return shots


def summary(shots: dict, rows: list[dict]) -> dict:
    """{total, approved, rejected, pending, ready} for the given all_shots.csv rows; ready = every shot approved."""
    counts = {"approved": 0, "rejected": 0, "pending": 0}
    for r in rows:
        counts[(shots.get(shot_key(r)) or {}).get("status", "pending")] += 1
    return {"total": len(rows), **counts, "ready": bool(rows) and counts["approved"] == len(rows)}
