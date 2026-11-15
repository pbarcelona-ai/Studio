"""Move a shot one place earlier or later in the storyboard, also across into the chapter before or after.

Everything that belongs to the shot goes with it: its row in all_shots.csv and audio_shots.csv (the chapter and shot number stay with the place),
its entry in the chapter's script (so a rebuild keeps the new order), its keyframe stills, clips, sound files and their takes, its verdict, its
saved prompt edit and its face check. The critic's list is out of date afterwards and is removed (run the critic again).
"""
import csv
import json
import os
import re
from pathlib import Path

from bookkit import read_json

NUMBERED = re.compile(r"^(shot|image|narration|sfx|music)-(\d{4})(.*)$")
PLACE = ("chapter", "shot")                   # these stay with the row's place; every other column moves with the shot


class MoveError(ValueError):
    """A readable reason the shot cannot be moved."""


def _rows(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames or []), list(r)


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def _swap_payload(rows: list[dict], a: int, b: int) -> None:
    ra, rb = rows[a - 1], rows[b - 1]
    for k in set(ra) | set(rb):
        if k not in PLACE:
            ra[k], rb[k] = rb.get(k, ""), ra.get(k, "")


def _swap_files(pdir: Path, a: int, b: int) -> int:
    """Swap the numbered output files of rows a and b in every per-shot folder (not the one-clip-per-chapter ones), takes included."""
    moved = 0
    folders = []
    for top in ("images", "videos", "audio"):
        base = pdir / top
        for f in sorted(base.iterdir()) if base.is_dir() else []:
            if f.is_dir() and not f.name.endswith("_chapters"):
                folders += [f] + ([f / "takes"] if (f / "takes").is_dir() else [])
    for folder in folders:
        pairs = []
        for f in folder.iterdir():
            m = NUMBERED.match(f.name)
            if f.is_file() and m and int(m.group(2)) in (a, b):
                other = b if int(m.group(2)) == a else a
                pairs.append((f, folder / f"{m.group(1)}-{other:04d}{m.group(3)}"))
        tmps = []
        for src, dst in pairs:                       # two steps, so a file never lands on one that has not moved yet
            t = src.with_name(src.name + ".moving")
            os.replace(src, t)
            tmps.append((t, dst))
        for t, dst in tmps:
            os.replace(t, dst)
            moved += 1
    return moved


def _swap_keys(path: Path, top: str | None, ka: str, kb: str, fix=None) -> None:
    data = read_json(path, None)
    if not isinstance(data, dict):
        return
    box = data.get(top) if top else data
    if not isinstance(box, dict):
        return
    va, vb = box.pop(ka, None), box.pop(kb, None)
    if va is not None:
        box[kb] = fix(va, kb) if fix else va
    if vb is not None:
        box[ka] = fix(vb, ka) if fix else vb
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    os.replace(tmp, path)


def _edit_at(v, key: str):
    """A saved prompt edit that moved to another place: it now names that place's chapter and shot number."""
    if not isinstance(v, dict):
        return v
    chapter, shot = key.rsplit("#", 1)
    return {**v, "chapter": chapter, "shot": int(shot) if shot.isdigit() else shot}


def _script_file(pdir: Path, chapter: str) -> Path | None:
    num = re.search(r"(\d+)$", chapter or "")
    f = pdir / "scripts" / f"chapter-{int(num.group(1)):03d}.json" if num else None
    return f if f and f.is_file() else None


def _swap_in_scripts(pdir: Path, ra: dict, rb: dict) -> None:
    """Swap the two shots in the chapter scripts too (one script, or two when the move crosses into the next chapter), so that "Build CSVs"
    keeps the new order. Each place keeps its own shot number."""
    fa, fb = _script_file(pdir, ra.get("chapter", "")), _script_file(pdir, rb.get("chapter", ""))
    if not fa or not fb:
        return
    da = read_json(fa, {})
    db = da if fb == fa else read_json(fb, {})
    sa_list, sb_list = da.get("shots", []), db.get("shots", [])
    ia = next((i for i, x in enumerate(sa_list) if str(x.get("n")) == str(ra.get("shot"))), None)
    ib = next((i for i, x in enumerate(sb_list) if str(x.get("n")) == str(rb.get("shot"))), None)
    if ia is None or ib is None:
        return
    a, b = sa_list[ia], sb_list[ib]
    sa_list[ia], sb_list[ib] = {**b, "n": a.get("n")}, {**a, "n": b.get("n")}
    for f, d in {fa: da, fb: db}.items():
        tmp = f.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False))
        os.replace(tmp, f)


def move(pdir: Path, n: int, direction: int) -> int:
    """Swap shot row n with the one before (direction -1) or after (+1) it. Returns the row the shot is now on."""
    pdir = Path(pdir)
    if direction not in (-1, 1):
        raise MoveError("direction must be -1 or 1")
    fields, rows = _rows(pdir / "all_shots.csv")
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(rows):
        raise MoveError("there is no such shot")
    m = n + direction
    if not 1 <= m <= len(rows):
        raise MoveError("it is already the " + ("first" if direction < 0 else "last") + " shot")
    ka, kb = (f"{rows[i - 1].get('chapter', '')}#{rows[i - 1].get('shot', '')}" for i in (n, m))
    _swap_payload(rows, n, m)
    _write(pdir / "all_shots.csv", fields, rows)
    if (pdir / "audio_shots.csv").is_file():
        af, arows = _rows(pdir / "audio_shots.csv")
        if len(arows) >= max(n, m):
            _swap_payload(arows, n, m)
            _write(pdir / "audio_shots.csv", af, arows)
    _swap_in_scripts(pdir, rows[n - 1], rows[m - 1])
    _swap_files(pdir, n, m)
    _swap_keys(pdir / "review.json", "shots", ka, kb)
    _swap_keys(pdir / "prompt_edits.json", None, ka, kb, fix=_edit_at)
    _swap_keys(pdir / "face_check.json", "rows", str(n), str(m))
    _swap_keys(pdir / "clip_lengths.json", None, ka, kb)        # a length set on the storyboard goes with its shot (the CSV column already did)
    (pdir / "critic.json").unlink(missing_ok=True)
    return m
