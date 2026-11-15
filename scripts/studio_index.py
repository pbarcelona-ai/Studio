"""The Studio's search index: one SQLite file, projects/studio_index.db, rebuilt from the project folders.

The folders stay the source of truth (BOOK_TO_SCREEN_BUILD.md, Section 8.0). The index only makes them quick to search: every book, and every
keyframe picture it has ever made (the current ones, earlier takes, and the ones set aside in replaced/<time>/) with the prompt it was made
from. Delete the file and nothing is lost: `python scripts/studio_index.py` (or the next Studio start) builds it again.

The schema is studio_index.sql (the full v3 model; most tables fill in as the later milestones land).

  python scripts/studio_index.py              rebuild, print what was indexed
  python scripts/studio_index.py "garden"     rebuild, then search the pictures
"""
from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import layout
import picture_record

SCHEMA = Path(__file__).resolve().parent / "studio_index.sql"
PIC = re.compile(r"^image-(\d{4})(?:-t(\d+))?\.png$")
NS = uuid.UUID("6f1f3c55-2a7e-4c1b-9a59-3f2d5b8e7a10")          # fixed, so the same file always gets the same id
OWNER = "local"
_LOCK = threading.Lock()


def db_path() -> Path:
    return layout.PROJECTS / "studio_index.db"


def _id(*parts: str) -> str:
    return uuid.uuid5(NS, "\x1f".join(parts)).hex


def _prompts(csv_path: Path) -> list[str]:
    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            return [r.get("prompt", "") for r in csv.DictReader(fh)]
    except OSError:
        return []


def _pictures(book: Path):
    """Every keyframe picture of a book: (file, model, shot number, take or None, attempt folder or '', the prompt list to fall back on)."""
    now = _prompts(book / "all_shots.csv")
    for k in sorted((book / "images").glob("*_keyframes")) if (book / "images").is_dir() else []:
        model = k.name.removesuffix("_keyframes")
        for f in sorted(k.glob("image-*.png")):
            yield f, model, "", now
        for f in sorted((k / "takes").glob("image-*.png")) if (k / "takes").is_dir() else []:
            yield f, model, "", now
    for stamp in sorted((book / "replaced").iterdir()) if (book / "replaced").is_dir() else []:
        if not stamp.is_dir():
            continue
        then = _prompts(stamp / "all_shots.csv")
        for k in sorted((stamp / "images").glob("*_keyframes")) if (stamp / "images").is_dir() else []:
            model = k.name.removesuffix("_keyframes")
            for f in sorted(k.rglob("image-*.png")):
                yield f, model, stamp.name, then


def _known_hashes(path: Path) -> dict[str, tuple[int, float, str]]:
    """path -> (size, mtime, hash) from the index being replaced, so an unchanged picture is not read again."""
    if not path.is_file():
        return {}
    try:
        db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            rows = db.execute("select path, params, content_hash from asset").fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        return {}
    out = {}
    for pth, params, h in rows:
        try:
            st = json.loads(params or "{}")
            out[pth] = (int(st["size"]), float(st["mtime"]), h)
        except (ValueError, KeyError, TypeError):
            continue
    return out


def _index_book(db: sqlite3.Connection, book: Path, known: dict[str, tuple[int, float, str]] | None = None) -> int:
    slug = book.name
    pid = _id("project", slug)
    db.execute("insert into project(id, slug, owner_id, title) values (?, ?, ?, ?)", (pid, slug, OWNER, slug))
    rec = picture_record.load(book)
    known = known or {}
    attempts: dict[str, str] = {}
    n_pics = 0
    for f, model, stamp, fallback in _pictures(book):
        m = PIC.match(f.name)
        if not m:
            continue
        shot, take = int(m.group(1)), int(m.group(2)) if m.group(2) else 0
        rel = f.relative_to(book).as_posix()
        try:
            st = f.stat()
            hit = known.get(f"{slug}/{rel}")
            digest = hit[2] if hit and hit[0] == st.st_size and abs(hit[1] - st.st_mtime) < 1e-6 else picture_record.file_sha(book, f, rec)
        except OSError:
            continue
        made = rec["made"].get(digest)                     # picture_record's own record of what this picture was made from
        prompt = made.get("prompt") if isinstance(made, dict) else None
        if prompt is None:
            prompt = fallback[shot - 1] if 1 <= shot <= len(fallback) else ""
        attempt_id = None
        if stamp:
            if stamp not in attempts:
                attempts[stamp] = _id("attempt", slug, stamp)
                db.execute("insert into attempt(id, project_id, number, label, snapshot_path) values (?, ?, ?, ?, ?)",
                           (attempts[stamp], pid, len(attempts), f"Set aside {stamp}", f"replaced/{stamp}"))
            attempt_id = attempts[stamp]
        aid = _id("asset", slug, rel)
        current = not stamp and f.parent.name.endswith("_keyframes")
        db.execute("insert into asset(id, project_id, attempt_id, owner_type, owner_id, kind, path, content_hash, version, is_selected, purpose, provider, "
                   "model, params, prompt_parts) values (?, ?, ?, 'shot', ?, 'image', ?, ?, ?, ?, 'keyframe', ?, ?, ?, ?)",
                   (aid, pid, attempt_id, f"{slug}#{shot}" if not stamp else f"{slug}@{stamp}#{shot}", f"{slug}/{rel}", digest, take,
                    1 if current else 0, model, model, json.dumps({"size": st.st_size, "mtime": st.st_mtime}),
                    json.dumps({"prompt": prompt}, ensure_ascii=False)))
        db.execute("insert into asset_search(asset_id, prompt, action, characters, location, style) values (?, ?, '', '', '', '')", (aid, prompt))
        n_pics += 1
    return n_pics


def rebuild(target: Path | None = None) -> dict:
    """Build the index from scratch into a temp file, then swap it in (readers never see half an index). Returns what was indexed."""
    target = target or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".studio_index.", suffix=".db")
        os.close(fd)
        books = pics = 0
        known = _known_hashes(target)
        try:
            db = sqlite3.connect(tmp)
            try:
                db.executescript(SCHEMA.read_text(encoding="utf-8"))
                for book in sorted(layout.BOOKS.iterdir()) if layout.BOOKS.is_dir() else []:
                    if book.is_dir() and re.fullmatch(r"[a-z0-9_]+", book.name):
                        pics += _index_book(db, book, known)
                        books += 1
                db.commit()
            finally:
                db.close()
            _swap(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    return {"books": books, "pictures": pics, "path": str(target)}


def _swap(tmp: str, target: Path, tries: int = 20) -> None:
    """os.replace is atomic on Windows and macOS, but Windows refuses while a reader has the old file open: wait a moment and retry."""
    for i in range(tries):
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.1)


def rebuild_in_background() -> threading.Thread:
    """Start a rebuild without holding up the caller (the Studio start-up). Errors are printed, never raised."""
    def run():
        try:
            rebuild()
        except Exception as e:                          # an index that cannot be built must never stop the Studio
            print(f"studio index: not rebuilt ({e})", file=sys.stderr)
    t = threading.Thread(target=run, name="studio-index", daemon=True)
    t.start()
    return t


def search_pictures(q: str, project: str | None = None, limit: int = 50, path: Path | None = None) -> list[dict]:
    """Pictures whose prompt matches the words of q (best first): [{project, path, model, shot, current, prompt}]."""
    words = re.findall(r"[A-Za-z0-9]+", q or "")
    p = path or db_path()
    if not words or not p.is_file():
        return []
    match = " ".join(f'"{w}"' for w in words[:12])
    # one fixed query: "?2 = ''" turns the project filter off, so no SQL is ever built from text
    sql = ("select project.slug, asset.path, asset.model, asset.owner_id, asset.is_selected, asset_search.prompt from asset_search "
           "join asset on asset.id = asset_search.asset_id join project on project.id = asset.project_id "
           "where asset_search match ?1 and (?2 = '' or project.slug = ?2) order by bm25(asset_search) limit ?3")
    args = (match, project or "", int(limit))
    db = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    try:
        rows = db.execute(sql, args).fetchall()
    finally:
        db.close()
    return [{"project": s, "path": pth, "model": m, "shot": int(o.rsplit("#", 1)[1]), "current": bool(c), "prompt": pr} for s, pth, m, o, c, pr in rows]


if __name__ == "__main__":
    out = rebuild()
    print(f"indexed {out['books']} books and {out['pictures']} pictures into {out['path']}")
    if len(sys.argv) > 1:
        for hit in search_pictures(" ".join(sys.argv[1:])):
            print(f"{hit['path']}  (shot {hit['shot']}{', current' if hit['current'] else ''})  {hit['prompt'][:90]}")
