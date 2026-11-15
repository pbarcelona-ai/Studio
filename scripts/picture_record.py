"""What each keyframe picture shows: the prompt it was made from, remembered by the picture's contents (so the record follows the file
wherever it is moved, renamed, kept as a take or set aside).

made_from.json in the book's folder: {"made": {sha1: {"prompt", "chapter", "shot", "model", "at"}}, "files": {relative path: [size, mtime, sha1]}}

A picture is recorded the first time it is seen in a picture maker's folder (images/<model>_keyframes/image-NNNN.png), with the prompt of row NNNN of
the list it was made from: keyframes.csv when that list is older than the picture (it is written just before each run), else all_shots.csv.
"""
import csv
import hashlib
import json
import os
import re
import time
from pathlib import Path

FILE = "made_from.json"
PIC = re.compile(r"^image-(\d{4})\.png$")


def load(pdir: Path) -> dict:
    try:
        d = json.loads((Path(pdir) / FILE).read_text())
    except (OSError, ValueError):
        d = {}
    return {"made": d.get("made", {}) if isinstance(d.get("made"), dict) else {}, "files": d.get("files", {}) if isinstance(d.get("files"), dict) else {}}


def _save(pdir: Path, d: dict) -> None:
    f = Path(pdir) / FILE
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=0, ensure_ascii=False))
    os.replace(tmp, f)


def sha(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _rows(path: Path) -> list[dict]:
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def file_sha(pdir: Path, path: Path, rec: dict) -> str:
    """The picture's sha1, from the cache when its size and time are unchanged."""
    rel = path.relative_to(pdir).as_posix()
    st = path.stat()
    hit = rec["files"].get(rel)
    if hit and hit[0] == st.st_size and abs(hit[1] - st.st_mtime) < 1e-6:
        return hit[2]
    s = sha(path)
    rec["files"][rel] = [st.st_size, st.st_mtime, s]
    return s


def record_new(pdir: Path) -> int:
    """Record every picture in the picture makers' folders that is not known yet. Returns how many were recorded."""
    pdir = Path(pdir)
    base = pdir / "images"
    if not base.is_dir():
        return 0
    rec = load(pdir)
    before = json.dumps(rec["files"], sort_keys=True)
    kf_csv, shots_csv = pdir / "keyframes.csv", pdir / "all_shots.csv"
    lists: dict[str, list[dict]] = {}
    added = 0
    for folder in sorted(base.glob("*_keyframes")):
        for f in sorted(folder.glob("image-*.png")):
            m = PIC.match(f.name)
            if not m:
                continue
            try:
                s = file_sha(pdir, f, rec)
            except OSError:                                  # it is being moved or copied right now: it is recorded next time
                continue
            if s in rec["made"]:
                continue
            try:
                src = kf_csv if kf_csv.is_file() and kf_csv.stat().st_mtime <= f.stat().st_mtime + 1 else shots_csv
            except OSError:
                continue
            rows = lists.setdefault(src.name, _rows(src))
            n = int(m.group(1))
            r = rows[n - 1] if 1 <= n <= len(rows) else {}
            rec["made"][s] = {"prompt": r.get("prompt", ""), "chapter": r.get("chapter", ""), "shot": r.get("shot", ""),
                              "model": folder.name.removesuffix("_keyframes"), "from": src.name, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            added += 1
    if added or json.dumps(rec["files"], sort_keys=True) != before:
        _save(pdir, rec)
    return added


def remember(pdir: Path, path: Path, prompt: str, model: str = "", how: str = "") -> None:
    """Say what a picture shows (a picture copied onto a shot from an old one keeps what the old one showed)."""
    pdir = Path(pdir)
    rec = load(pdir)
    s = file_sha(pdir, Path(path), rec)
    if s not in rec["made"]:
        rec["made"][s] = {"prompt": prompt, "chapter": "", "shot": "", "model": model, "from": how, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _save(pdir, rec)


def prompt_of(pdir: Path, path: Path, rec: dict | None = None) -> str | None:
    """The prompt a picture was made from, or None when it was never recorded."""
    rec = rec if rec is not None else load(pdir)
    try:
        s = file_sha(Path(pdir), Path(path), rec)
    except OSError:
        return None
    hit = rec["made"].get(s)
    return hit.get("prompt") if hit else None
