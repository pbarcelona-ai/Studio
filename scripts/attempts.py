"""Start over and archived attempts (BOOK_TO_SCREEN_BUILD.md Section 6b.1, milestone M8).

start_over(pdir, keep) moves everything made so far into projects/books/<book>/attempts/<id>/ ("Attempt 2 - 15 Nov 2026 14:05"): nothing is
deleted. The parts ticked in `keep` stay where they are:
  sources     sources/, chapters/, chapters.json, source_text.txt, source/, front_matter.txt, back_matter.txt
  settings    production.json, recipe.json, project_rules.json
  styles      styles/ (style cards, translations, look-development picks) and the look-development prompt sets
  continuity  the continuity book (<book>.json)
  screenplay  readin/, adaptation/, screenplay/
Everything else made by the steps (shot list, pictures and their prompt sets, clips, audio, films, exports, the approvals, crew notes, the old
storyboard and its takes) goes into the archive. Before anything moves, every picture and clip is stored by its contents (assets.py), so the
library and any reused shot still find it. restore() archives the current version first, then brings the attempt back.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import assets
import layout
from bookkit import continuity_file

KEEPABLE = ("sources", "settings", "styles", "continuity", "screenplay")
PARTS = {
    "sources": ["sources", "chapters", "chapters.json", "source_text.txt", "source", "front_matter.txt", "back_matter.txt"],
    "settings": ["production.json", "recipe.json", "project_rules.json"],
    "styles": ["styles"],
    "continuity": [],                                       # the continuity book's file name depends on the book (see _names)
    "screenplay": ["readin", "adaptation", "screenplay"],
}
ALWAYS = ["shots", "pictures", "gates.json", "videos", "audio", "images", "films", "exports", "replaced", "keyframes.csv", "all_shots.csv",
          "all_chapters.csv", "all_images.csv", "audio_shots.csv", "audio_chapters.csv", "audio_scenes.csv", "movies.json", "scripts", "critic.json",
          "crew_log.jsonl", "review.json", "keyframe_refs", "made_from.json", "storyboard.json"]


class AttemptError(RuntimeError):
    """Start over or restore cannot be done as asked; the message says why."""


def folder(pdir: Path) -> Path:
    return pdir / "attempts"


def _names(pdir: Path, part: str) -> list[str]:
    if part == "continuity":
        f = continuity_file(pdir)
        return [f.name, f.name + ".bak", f.with_suffix(".json.bak").name]
    return PARTS[part]


def _sets(pdir: Path, styles_kept: bool) -> list[Path]:
    """This book's prompt sets, by the names its own files record (another book with a similar name is never touched): the pictures of every
    style (always archived) and the look development (archived unless styles are kept)."""
    names: set[str] = set()
    for kind, sub, fname in (("px", "pictures", "shots.json"), ("ld", "styles", "lookdev.json")):
        if kind == "ld" and styles_kept:
            continue
        for d in sorted((pdir / sub).iterdir()) if (pdir / sub).is_dir() else []:
            try:
                names.add(str(json.loads((d / fname).read_text(encoding="utf-8"))["set"]))
            except (OSError, ValueError, KeyError):
                continue
    out = []
    for n in sorted(names):
        found = layout.find_dir(n) if layout.SLUG_RE.match(n) else None
        if found is not None and found.parent == layout.PROMPTS:
            out.append(found)
    return out


def attempts(pdir: Path) -> list[dict]:
    out = []
    for a in sorted(folder(pdir).iterdir()) if folder(pdir).is_dir() else []:
        try:
            meta = json.loads((a / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({**meta, "id": a.name})
    return out


def start_over(pdir: Path, keep: list[str]) -> dict:
    bad = [k for k in keep if k not in KEEPABLE]
    if bad:
        raise AttemptError(f"cannot keep {', '.join(bad)}: choose from {', '.join(KEEPABLE)}")
    sets = _sets(pdir, "styles" in keep)                     # found from the files that are about to move
    for f in ("images", "videos", "audio", "pictures", "films", "replaced", "styles"):
        assets.ingest_tree(pdir, pdir / f)
    for d in sets:
        assets.ingest_tree(pdir, d, prefix=f"sets/{d.name}/")
    n = len(attempts(pdir)) + 1
    now = time.localtime()
    aid = f"{n:03d}-{time.strftime('%Y%m%d-%H%M%S', now)}"
    dest = folder(pdir) / aid
    dest.mkdir(parents=True)
    moved = []
    names = list(ALWAYS) + [x for part in KEEPABLE if part not in keep for x in _names(pdir, part)]
    for name in dict.fromkeys(names):
        src = pdir / name
        if src.exists():
            shutil.move(str(src), str(dest / name))
            moved.append(name)
    for d in sets:
        (dest / "sets").mkdir(exist_ok=True)
        shutil.move(str(d), str(dest / "sets" / d.name))
        moved.append(f"sets/{d.name}")
    label = f"Attempt {n} – {time.strftime('%d %b %Y %H:%M', now).lstrip('0')}"
    meta = {"n": n, "label": label, "at": time.strftime("%Y-%m-%dT%H:%M:%S", now), "keep": sorted(keep), "moved": moved}
    (dest / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return {**meta, "id": aid}


def files_of(pdir: Path, aid: str) -> list[str]:
    """What an archived attempt holds (read-only view): its files, relative to the attempt."""
    a = _attempt(pdir, aid)
    return sorted(p.relative_to(a).as_posix() for p in a.rglob("*") if p.is_file() and p.name != "meta.json")[:5000]


def _attempt(pdir: Path, aid: str) -> Path:
    a = folder(pdir) / aid
    if "/" in aid or "\\" in aid or aid.startswith(".") or not (a / "meta.json").is_file():
        raise AttemptError(f"no attempt {aid}")
    return a


def restore(pdir: Path, aid: str) -> dict:
    """Make an archived attempt the current version again; the current version is archived first (as a new attempt, keeping nothing)."""
    a = _attempt(pdir, aid)
    meta = json.loads((a / "meta.json").read_text(encoding="utf-8"))
    kept = set(meta.get("keep", []))
    keep_now = [k for k in KEEPABLE if k in kept]          # what the attempt did not hold is still the current one's: keep it in place
    saved = start_over(pdir, keep_now)
    for name in meta.get("moved", []):
        src = a / name
        if not src.exists():
            continue
        if name.startswith("sets/"):
            target = layout.PROMPTS / name.split("/", 1)[1]
            if target.exists():
                continue
            layout.PROMPTS.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(target))
        else:
            shutil.move(str(src), str(pdir / name))
    shutil.rmtree(a, ignore_errors=True)
    return {"restored": meta["label"], "archived_current_as": saved["label"]}
