"""Immutable asset files and path aliases (milestone M8).

Every picture and clip the Studio keeps is stored once by its contents:

  projects/books/<book>/assets/objects/<aa>/<sha256>.<ext>     never changed, never overwritten (read-only on macOS / Linux)
  projects/books/<book>/assets/aliases.json                    {path under the book (or a prompt set): [{sha, at}, ...]}

A path is an ALIAS of the content it had. When a take is replaced, a storyboard is set aside (replaced/<time>/), or an attempt is
archived, the old content is still found by its old path and by its hash (resolve()), so nothing the library or a reused shot points at
ever disappears. ingest() is idempotent: the same content is stored once, however many paths point at it.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

MEDIA_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm", ".wav", ".mp3", ".m4a")
_LOCK = threading.RLock()


def root(pdir: Path) -> Path:
    return pdir / "assets"


def sha_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def object_path(pdir: Path, sha: str, ext: str) -> Path:
    return root(pdir) / "objects" / sha[:2] / f"{sha}{ext.lower()}"


def _aliases_file(pdir: Path) -> Path:
    return root(pdir) / "aliases.json"


def aliases(pdir: Path) -> dict[str, list[dict]]:
    try:
        d = json.loads(_aliases_file(pdir).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_aliases(pdir: Path, d: dict) -> None:
    f = _aliases_file(pdir)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=0, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)


def ingest(pdir: Path, path: Path, alias: str = "") -> str:
    """Store the file's content (once) and record `alias` (default: its path under the book, with forward slashes) as pointing at it."""
    path = Path(path)
    if path.suffix.lower() not in MEDIA_EXTS:
        raise ValueError(f"{path.name}: only pictures, clips and sounds are kept as assets")
    sha = sha_of(path)
    obj = object_path(pdir, sha, path.suffix)
    with _LOCK:
        if not obj.is_file():
            obj.parent.mkdir(parents=True, exist_ok=True)
            tmp = obj.with_name(obj.name + ".part")
            shutil.copyfile(path, tmp)
            os.replace(tmp, obj)
            if sys.platform != "win32":
                obj.chmod(0o444)                          # immutable on disk too
        name = alias or _rel(pdir, path)
        al = aliases(pdir)
        hist = al.setdefault(name, [])
        if not hist or hist[-1]["sha"] != sha:
            hist.append({"sha": sha, "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
            _save_aliases(pdir, al)
    return sha


def _rel(pdir: Path, path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(pdir.resolve()).as_posix()
    except ValueError:
        return Path(path).resolve().as_posix()


def resolve(pdir: Path, alias_or_sha: str, version: int = -1) -> Path | None:
    """The stored file for a path (its latest content, or an earlier version: 0 = the first) or for a hash."""
    s = alias_or_sha
    if len(s) == 64 and all(c in "0123456789abcdef" for c in s):
        hits = list((root(pdir) / "objects" / s[:2]).glob(f"{s}.*")) if (root(pdir) / "objects" / s[:2]).is_dir() else []
        return next((h for h in hits if not h.name.endswith(".part")), None)
    hist = aliases(pdir).get(s, [])
    if not hist:
        return None
    try:
        sha = hist[version]["sha"]
    except IndexError:
        return None
    return resolve(pdir, sha)


def history(pdir: Path, alias: str) -> list[dict]:
    return list(aliases(pdir).get(alias, []))


def ingest_tree(pdir: Path, folder: Path, prefix: str = "") -> int:
    """Ingest every media file under `folder` (aliases are its paths under the book, or `prefix` + its path under the folder)."""
    n = 0
    if not folder.is_dir():
        return 0
    for f in sorted(folder.rglob("*")):
        if f.is_file() and f.suffix.lower() in MEDIA_EXTS and "assets" not in f.relative_to(folder).parts[:1] and not f.name.endswith(".part"):
            ingest(pdir, f, f"{prefix}{f.relative_to(folder).as_posix()}" if prefix else "")
            n += 1
    return n


def copy_out(pdir: Path, sha: str, dest: Path) -> Path:
    """Put a stored file at `dest` (a writable copy: the object itself is never handed out to be changed)."""
    src = resolve(pdir, sha)
    if src is None:
        raise FileNotFoundError(f"no asset {sha[:12]}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dest)
    return dest
