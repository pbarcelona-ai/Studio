"""Put the shots in the order of the film plan's scenes (the screenplay order), not in chapter order, and keep what was made for each shot.

A scene can come before an earlier chapter (a flashback, or a scene you moved up in the plan). Each shot belongs to a scene (adaptation.shot_scene);
the shot list follows the scenes in plan order, and inside a scene the book's order. When the order changes, the pictures, clips and sounds already
made are renumbered to follow their shots, so nothing has to be made again. Files whose shot was rewritten (a different prompt) are set aside in
replaced/<time>/ instead, because they no longer show that shot.
"""
import json
import os
import re
import time
from pathlib import Path

import adaptation as ad

NUMBERED = re.compile(r"^(shot|image|narration|sfx|music)-(\d{4})(.*)$")


def _chapter_no(label: str) -> int | None:
    m = re.search(r"(\d+)$", label or "")
    return int(m.group(1)) if m else None


def scenes_of(plan: dict, rows: list[dict]) -> list[str | None]:
    """The plan scene of every row (None for a chapter no scene uses)."""
    per: dict[str, int] = {}
    for r in rows:
        per[r.get("chapter", "")] = per.get(r.get("chapter", ""), 0) + 1
    out: list[str | None] = []
    for r in rows:
        ch = _chapter_no(r.get("chapter", ""))
        try:
            shot = int(r.get("shot") or 0)
        except (TypeError, ValueError):
            shot = 0
        out.append(ad.shot_scene(plan, ch, shot, per[r.get("chapter", "")]) if ch is not None and shot else None)
    return out


def order(plan: dict, rows: list[dict]) -> list[int]:
    """The new order of the rows (indexes into rows): scenes in plan order, the book's order inside a scene. Rows of no scene keep their place
    after the scene of the row before them."""
    pos = {s["id"]: i for i, s in enumerate(ad.active_scenes(plan))}
    scenes = scenes_of(plan, rows)
    keys, last = [], -1.0
    for i, sid in enumerate(scenes):
        p = pos.get(sid) if sid else None
        last = float(p) if p is not None else last
        keys.append((last, i))
    return [i for _, i in sorted(keys)]


def out_of_order(pdir: Path, rows: list[dict]) -> str:
    """'' when the shot list follows the screenplay's scene order, else a sentence saying where it does not."""
    plan = ad.load(pdir)
    if not plan or not rows:
        return ""
    want = order(plan, rows)
    if want == list(range(len(rows))):
        return ""
    first = next(i for i, j in enumerate(want) if i != j)
    sid = scenes_of(plan, rows)[want[first]]
    return f"the shots are not in the screenplay's scene order (scene {sid} should start at shot {first + 1})"


def same_shot(a: str, b: str) -> bool:
    """Is it still the same shot? The prompt may be tidied (prompt rules, a locked costume) without the shot changing: half the words in common."""
    wa, wb = set(re.findall(r"[a-z]+", (a or "").lower())), set(re.findall(r"[a-z]+", (b or "").lower()))
    return not wa and not wb or bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.5


def _key(r: dict) -> str:
    return f"{r.get('chapter', '')}#{r.get('shot', '')}"


def follow(pdir: Path, old_rows: list[dict], new_rows: list[dict]) -> dict:
    """After the shot list was rewritten: renumber each shot's files (pictures, clips, sounds and their takes) from its old row to its new one.
    A shot that was rewritten (see same_shot), or that is gone, has its files set aside in replaced/<time>/. Returns {"moved", "set_aside"}."""
    pdir = Path(pdir)
    old_at = {_key(r): (i + 1, r.get("prompt", "")) for i, r in enumerate(old_rows)}
    new_at = {_key(r): (i + 1, r.get("prompt", "")) for i, r in enumerate(new_rows)}
    where: dict[int, int | None] = {}                   # old row -> new row (None: set aside)
    for k, (n_old, p_old) in old_at.items():
        hit = new_at.get(k)
        where[n_old] = hit[0] if hit and same_shot(hit[1], p_old) else None
    if all(v == k for k, v in where.items()):
        return {"moved": 0, "set_aside": 0}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    moved = aside = 0
    plans = []
    for top in ("images", "videos", "audio"):
        base = pdir / top
        for f in sorted(base.iterdir()) if base.is_dir() else []:
            if not f.is_dir() or f.name.endswith("_chapters") or (top == "images" and not f.name.endswith("_keyframes")):
                continue
            for folder in [f] + ([f / "takes"] if (f / "takes").is_dir() else []):
                for x in folder.iterdir():
                    m = NUMBERED.match(x.name)
                    if not (x.is_file() and m):
                        continue
                    n = int(m.group(2))
                    if n not in where:
                        continue                         # beyond the old list: not ours to touch
                    to = where[n]
                    if to == n:
                        continue
                    dst = folder / f"{m.group(1)}-{to:04d}{m.group(3)}" if to else pdir / "replaced" / stamp / x.relative_to(pdir)
                    plans.append((x, dst))
    tmps = []
    for src, dst in plans:                               # two steps, so no file lands on one that has not moved yet
        t = src.with_name(src.name + ".moving")
        os.replace(src, t)
        tmps.append((t, dst))
    for t, dst in tmps:
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(t, dst)
        if dst.is_relative_to(pdir / "replaced"):
            aside += 1
        else:
            moved += 1
    if aside:                                            # what each set-aside picture showed, so it can be found and used again (old_pictures.py)
        import csv
        with open(pdir / "replaced" / stamp / "all_shots.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(old_rows[0]))
            w.writeheader()
            w.writerows(old_rows)
    fc = pdir / "face_check.json"                        # its rows are numbered by row: renumber them too
    try:
        data = json.loads(fc.read_text())
        rows_fc = data.get("rows", {})
        data["rows"] = {str(where[int(k)]): v for k, v in rows_fc.items() if k.isdigit() and where.get(int(k))}
        fc.write_text(json.dumps(data, indent=1))
    except (OSError, ValueError, AttributeError):
        pass
    (pdir / "critic.json").unlink(missing_ok=True)       # its row numbers are stale; run the critic again
    return {"moved": moved, "set_aside": aside}
