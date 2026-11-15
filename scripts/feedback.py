"""Changes made in a later step that an earlier step must hear about, and the walk back through the steps that follows.

When a shot is edited or moved on the storyboard, the screenplay scene it came from is flagged (shown with a red outline on the screenplay),
the screenplay must be checked and approved again, and then every step from the screenplay to the storyboard is visited again in order.

feedback.json in the book's folder: {"open": [{"scene", "shot", "n", "kind", "field", "old", "new", "at"}], "revisit": ["screenplay", ...]}
"""
import json
import os
import re
import time
from pathlib import Path

import adaptation as ad
from bookkit import read_json

FILE = "feedback.json"
# The steps visited again, in order, after the storyboard changed (the screenplay is the first one: it must be updated and approved).
REVISIT = ["screenplay", "continuity", "cast", "look", "write", "build", "where", "keyframes", "storyboard"]
TEXT_MAX = 300


def _path(pdir: Path) -> Path:
    return Path(pdir) / FILE


def load(pdir: Path) -> dict:
    d = read_json(_path(pdir), {}) or {}
    return {"open": [e for e in d.get("open", []) if isinstance(e, dict)], "revisit": [s for s in d.get("revisit", []) if s in REVISIT]}


def _save(pdir: Path, d: dict) -> None:
    f = _path(pdir)
    if not d["open"] and not d["revisit"]:
        f.unlink(missing_ok=True)
        return
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    os.replace(tmp, f)


def scene_of_shot(pdir: Path, rows: list[dict], n: int) -> str | None:
    """The plan's scene that shot row n (1-based, all_shots.csv order) was written from, or None (no plan, or no scene uses its chapter)."""
    plan = ad.load(pdir)
    if not plan or not 1 <= n <= len(rows):
        return None
    chapter = rows[n - 1].get("chapter", "")
    m = re.search(r"(\d+)$", chapter)
    if not m:
        return None
    same = [r for r in rows if r.get("chapter") == chapter]
    try:
        shot = int(rows[n - 1].get("shot") or 0)
    except ValueError:
        return None
    return ad.shot_scene(plan, int(m.group(1)), shot, len(same))


def record(pdir: Path, rows: list[dict], n: int, kind: str, field: str = "", old: str = "", new: str = "") -> bool:
    """Note that shot n changed in the storyboard (kind: edited | moved). Returns True when a screenplay scene was flagged.
    A book without a film plan has no screenplay to send the change back to: nothing is recorded."""
    scene = scene_of_shot(pdir, rows, n)
    if not scene:
        return False
    d = load(pdir)
    r = rows[n - 1]
    d["open"].append({"scene": scene, "shot": f"{r.get('chapter', '')}#{r.get('shot', '')}", "n": n, "kind": kind, "field": field,
                      "old": str(old)[:TEXT_MAX], "new": str(new)[:TEXT_MAX], "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    d["revisit"] = list(REVISIT)
    _save(pdir, d)
    return True


def open_flags(pdir: Path) -> dict[str, list[dict]]:
    """{scene id: [changes not yet dealt with]}"""
    out: dict[str, list[dict]] = {}
    for e in load(pdir)["open"]:
        out.setdefault(e.get("scene", ""), []).append(e)
    return out


def resolve(pdir: Path, scene: str) -> int:
    """The screenplay scene was updated (or kept on purpose): its flags are dealt with. Returns how many were cleared."""
    d = load(pdir)
    keep = [e for e in d["open"] if e.get("scene") != scene]
    gone = len(d["open"]) - len(keep)
    d["open"] = keep
    _save(pdir, d)
    return gone


def confirm(pdir: Path, step: str) -> list[str]:
    """The step that is next in the walk back was looked at and is fine: drop it. Returns the steps still to visit."""
    d = load(pdir)
    if d["revisit"] and d["revisit"][0] == step:
        d["revisit"] = d["revisit"][1:]
        _save(pdir, d)
    return d["revisit"]


def clear(pdir: Path) -> None:
    _path(pdir).unlink(missing_ok=True)
