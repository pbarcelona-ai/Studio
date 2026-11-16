"""History and branches (BOOK_TO_SCREEN_BUILD.md Section 6c, milestone M12).

Every approval, Producer-chat request and Autopilot step makes a MOMENT: a timestamped snapshot of the book's records (its JSON, CSV, Markdown
and text files: plan, screenplay, shot list, styles, sound, edit, approvals, sources list ...). Record files are stored once by contents in
history/blobs/; pictures and clips are referenced, not copied (by their content hash in the book's asset store, assets.py).

  history/moments.json   [{id, at, label, kind, files: {path: blob}, media: {path: sha}}]
  back_to(moment)        the current state is saved as a moment first, then the records (and any picture whose content differs) come back
  branch(moment, name)   a new book from a moment, e.g. to try a darker ending or another style; its pictures are copies of the same files
                         (nothing is generated, so nothing is paid for twice) and it remembers which book and moment it came from
  compare(a, b)          two books side by side: the screenplay's differences, the pictures of each shot, the edit's length
"""
from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import time
from pathlib import Path

import assets
import layout

RECORD_EXTS = (".json", ".csv", ".md", ".txt", ".jsonl", ".fountain")
SKIP_DIRS = {"history", "assets", "attempts", "exports", "images", "videos", "audio", "films", "replaced", "logs", "cache", ".thumbs", ".depth", "source"}
MEDIA_DIRS = ("pictures", "images", "videos", "audio")
MAX_RECORD = 8 * 2**20


class HistoryError(RuntimeError):
    """A history step cannot be done as asked; the message says why."""


def folder(pdir: Path) -> Path:
    return pdir / "history"


def moments(pdir: Path) -> list[dict]:
    try:
        d = json.loads((folder(pdir) / "moments.json").read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(pdir: Path, ms: list[dict]) -> None:
    folder(pdir).mkdir(parents=True, exist_ok=True)
    tmp = folder(pdir) / "moments.json.tmp"
    tmp.write_text(json.dumps(ms, indent=0, ensure_ascii=False), encoding="utf-8")
    tmp.replace(folder(pdir) / "moments.json")


def records(pdir: Path) -> list[Path]:
    """The book's record files (not pictures, clips, sounds, archives or caches)."""
    out = []
    for p in sorted(pdir.rglob("*")):
        rel = p.relative_to(pdir)
        if not p.is_file() or rel.parts[0] in SKIP_DIRS or any(part in ("cache", ".thumbs", ".depth") for part in rel.parts):
            continue
        if p.suffix.lower() in RECORD_EXTS and not p.name.endswith((".tmp", ".bak")) and p.stat().st_size <= MAX_RECORD:
            out.append(p)
    return out


def _blob(pdir: Path, data: bytes) -> str:
    h = hashlib.sha256(data).hexdigest()
    f = folder(pdir) / "blobs" / h[:2] / h
    if not f.is_file():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    return h


def create(pdir: Path, label: str, kind: str = "manual") -> dict:
    """A moment of the book now. Pictures and clips are stored by content first, so the moment can always bring them back."""
    files = {p.relative_to(pdir).as_posix(): _blob(pdir, p.read_bytes()) for p in records(pdir)}
    media: dict[str, str] = {}
    for top in MEDIA_DIRS:
        base = pdir / top
        for f in sorted(base.rglob("*")) if base.is_dir() else []:
            if f.is_file() and f.suffix.lower() in assets.MEDIA_EXTS:
                media[f.relative_to(pdir).as_posix()] = assets.ingest(pdir, f)
    for name, sdir in _sets(pdir):                          # the pictures of the book's prompt sets (pictures, look development)
        for f in sorted((sdir / "images").rglob("*")) if (sdir / "images").is_dir() else []:
            if f.is_file() and f.suffix.lower() in assets.MEDIA_EXTS:
                key = f"sets/{name}/{f.relative_to(sdir).as_posix()}"
                media[key] = assets.ingest(pdir, f, key)
    ms = moments(pdir)
    m = {"id": f"m{len(ms) + 1:04d}-{time.strftime('%Y%m%d%H%M%S')}", "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "label": " ".join(label.split())[:200],
         "kind": kind, "files": files, "media": media}
    if ms and ms[-1]["files"] == files and ms[-1]["media"] == media:
        return ms[-1]                                       # nothing changed since the last moment
    ms.append(m)
    _save(pdir, ms)
    return m


def _sets(pdir: Path) -> list[tuple[str, Path]]:
    out = []
    for sub, fname in (("pictures", "shots.json"), ("styles", "lookdev.json")):
        for d in sorted((pdir / sub).iterdir()) if (pdir / sub).is_dir() else []:
            try:
                name = str(json.loads((d / fname).read_text(encoding="utf-8"))["set"])
            except (OSError, ValueError, KeyError):
                continue
            found = layout.find_dir(name) if layout.SLUG_RE.match(name) else None
            if found is not None:
                out.append((name, found))
    return out


def _media_target(pdir: Path, rel: str) -> Path | None:
    if ".." in Path(rel).parts:
        return None
    if rel.startswith("sets/"):
        _, name, rest = rel.split("/", 2)
        found = layout.find_dir(name) if layout.SLUG_RE.match(name) else None
        return found / rest if found is not None else None
    return pdir / rel


def get(pdir: Path, mid: str) -> dict:
    m = next((x for x in moments(pdir) if x["id"] == mid), None)
    if m is None:
        raise HistoryError(f"no moment {mid}")
    return m


def _write_records(src: Path, dest: Path, m: dict) -> None:
    for rel, blob in m["files"].items():
        if ".." in Path(rel).parts:
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes((folder(src) / "blobs" / blob[:2] / blob).read_bytes())
        tmp.replace(target)


def back_to(pdir: Path, mid: str) -> dict:
    """Restore the book to a moment. The current state is saved as a moment first, so nothing is lost."""
    m = get(pdir, mid)
    saved = create(pdir, f"before going back to {m['label']}", "restore")
    keep = set(m["files"])
    for p in records(pdir):                                 # records made after that moment leave (they are in the moment just saved)
        if p.relative_to(pdir).as_posix() not in keep:
            p.unlink()
    _write_records(pdir, pdir, m)
    for rel, sha in m["media"].items():                      # pictures whose content changed come back from the asset store
        f = _media_target(pdir, rel)
        if f is None:
            continue
        if not f.is_file() or assets.sha_of(f) != sha:
            assets.copy_out(pdir, sha, f)
    return {"restored": m["label"], "saved_as": saved["id"]}


def _rename_sets(dest: Path, old: str, new: str) -> None:
    """Copy the book's picture and look-development prompt sets to the branch's own names, and point the branch's records at them."""
    for sub, fname in (("pictures", "shots.json"), ("styles", "lookdev.json")):
        for d in sorted((dest / sub).iterdir()) if (dest / sub).is_dir() else []:
            f = d / fname
            if not f.is_file():
                continue
            data = json.loads(f.read_text(encoding="utf-8"))
            name = str(data.get("set", ""))
            if not layout.SLUG_RE.match(name):
                continue
            src = layout.find_dir(name)
            kind = "_px_" if sub == "pictures" else "_ld_"
            sid = name.split(kind, 1)[1] if kind in name else d.name
            new_name = f"{new[:40 - 4 - len(sid)]}{kind}{sid}"[:40]
            target = layout.new_dir(new_name, "prompts")
            if src is not None and src.is_dir() and not target.exists():
                shutil.copytree(src, target)
            data["set"] = new_name
            f.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def branch(pdir: Path, mid: str, name: str) -> Path:
    """A new book from a moment. Its pictures and clips are copies of the same files (no generation, nothing paid twice)."""
    m = get(pdir, mid)
    if not layout.SLUG_RE.match(name):
        raise HistoryError("a book's name is 2-40 lowercase letters, digits or _")
    if layout.find_dir(name) is not None:
        raise HistoryError(f"there is already a project called {name}")
    dest = layout.new_dir(name, "book")
    dest.mkdir(parents=True)
    _write_records(pdir, dest, m)
    old_cb, new_cb = dest / f"{pdir.name}.json", dest / f"{name}.json"      # the continuity book is named after its book
    if old_cb.is_file():
        old_cb.rename(new_cb)
    _rename_sets(dest, pdir.name, name)                     # copies the prompt sets (their pictures included) under the branch's names
    for rel, sha in m["media"].items():
        if ".." not in Path(rel).parts and not rel.startswith("sets/"):
            assets.copy_out(pdir, sha, dest / rel)
    (dest / "branch.json").write_text(json.dumps({"from": pdir.name, "moment": mid, "label": m["label"], "at": time.strftime("%Y-%m-%dT%H:%M:%S")}), encoding="utf-8")
    create(dest, f"branched from {pdir.name}: {m['label']}", "branch")
    return dest


def _script(pdir: Path) -> list[str]:
    try:
        import read_it_in
        sp = json.loads((pdir / "readin" / "screenplay.json").read_text(encoding="utf-8"))
        return read_it_in.script_text(sp["scenes"]).split("\n")
    except (OSError, ValueError, KeyError):
        return []


def compare(a: Path, b: Path) -> dict:
    """Two books side by side: the screenplay diff, each shot's master picture, and the edit's length."""
    import edl
    import pictures
    diff = list(difflib.unified_diff(_script(a), _script(b), a.name, b.name, lineterm="", n=1))[:2000]
    pa, pb = pictures.status(a), pictures.status(b)
    rows = []
    for i in range(max(len(pa["shots"]), len(pb["shots"]))):
        x = pa["shots"][i] if i < len(pa["shots"]) else None
        y = pb["shots"][i] if i < len(pb["shots"]) else None
        rows.append({"row": i + 1, "a": {"set": pa["set"], "image": x["image"]} if x else None, "b": {"set": pb["set"], "image": y["image"]} if y else None})

    def runtime(p: Path) -> float | None:
        e = edl.load(p)
        return edl.timeline(edl.cut(e))["total"] if e else None
    return {"a": a.name, "b": b.name, "script_diff": diff, "storyboard": rows, "runtime": {"a": runtime(a), "b": runtime(b)}}
