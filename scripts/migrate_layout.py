#!/usr/bin/env python3
"""One-time move of the old flat layout into the new one (see layout.py). Safe to run again: it only moves what is still in the old place.

  OLD                                       NEW
  projects/adam_eve, enoch, book_of_jasher  projects/books/<book>/
  projects/char_adam, char_eve, ...         projects/characters/char_<name>/        (generated character image sets)
  projects/xv, <any other prompt set>       projects/prompts/<set>/
  characters/<series>/  (token files)       projects/characters/<series>/
  projects/adam_eve/references/<character>  projects/characters/bible/references/<character>   (references belong to the characters)
  scripts/projects/<name>/...               merged into that project's folder (output of runs started from the wrong folder)

and it rewrites the "projects/..." paths stored inside the character token files.

  python3 scripts/migrate_layout.py            show what would happen (changes nothing)
  python3 scripts/migrate_layout.py --apply    do it
  python3 scripts/migrate_layout.py --root DIR work on another copy of the repository (for a rehearsal)
Nothing is overwritten. The only things deleted are empty folders, .DS_Store files and a file that is byte-for-byte identical to the one already at
the destination (a duplicate). A file that differs from the one at the destination stays where it is and is listed as a conflict.
"""
import argparse
import filecmp
import json
import os
import re
import shutil
import sys
from pathlib import Path

BOOK_REFERENCE_SERIES = {"adam_eve": "bible"}       # which character series a book's old references/ folder belongs to
KNOWN_BOOKS = {"adam_eve", "enoch"}                   # imported books (they have no chapters.json)
SLUG_RE = re.compile(r"^[a-z0-9_]{2,40}$")


class Mover:
    def __init__(self, apply):
        self.apply, self.moved, self.conflicts, self.duplicates, self.notes = apply, [], [], [], []

    def move(self, src: Path, dst: Path):
        """Move a file or folder. If dst exists: folders are merged item by item, files are left alone and reported."""
        if not src.exists():
            return
        if dst.exists():
            if src.is_dir() and dst.is_dir():
                for child in sorted(src.iterdir()):
                    if child.name == ".DS_Store":
                        continue
                    self.move(child, dst / child.name)
                self.prune(src)
            elif src.is_file() and dst.is_file() and filecmp.cmp(src, dst, shallow=False):
                self.duplicates.append((src, dst))              # identical copy: nothing is lost by dropping it
                if self.apply:
                    src.unlink()
            else:
                self.conflicts.append((src, dst))
            return
        self.moved.append((src, dst))
        if self.apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

    def prune(self, d: Path):
        """Remove a folder that only has .DS_Store files / empty folders left."""
        if not self.apply or not d.is_dir():
            return
        for child in list(d.iterdir()):
            if child.name == ".DS_Store":
                child.unlink()
            elif child.is_dir():
                self.prune(child)
        if not any(d.iterdir()):
            d.rmdir()


def classify(d: Path) -> str:
    """'book', 'character-set', 'prompts' or '?' for an old-style folder directly under projects/."""
    if (d / "promptset.json").exists():
        return "character-set" if d.name.startswith("char_") else "prompts"
    if (d / "chapters.json").exists() or (d / "production_bible").is_dir() or d.name in KNOWN_BOOKS:
        return "book"
    return "?"


def rewrite_paths(text: str, rules) -> str:
    for old, new in rules:
        text = text.replace(old, new)
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="really move things (default: only show what would happen)")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="repository root (default: this one)")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    projects = root / "projects"
    books, chars, prompts = projects / "books", projects / "characters", projects / "prompts"
    m = Mover(args.apply)
    kinds = {}                                             # slug -> kind, for the path rewrite

    # 1. folders directly under projects/ that are not the three new folders
    if projects.exists():
        for d in sorted(p for p in projects.iterdir() if p.is_dir() and p.name not in ("books", "characters", "prompts")):
            kind = classify(d)
            kinds[d.name] = kind
            if kind == "book":
                m.move(d, books / d.name)
            elif kind == "character-set":
                m.move(d, chars / d.name)
            elif kind == "prompts":
                m.move(d, prompts / d.name)
            else:
                m.notes.append(f"left alone (not a book or a prompt set): projects/{d.name}")

    # 2. character token series: characters/<series>/ -> projects/characters/<series>/
    old_chars = root / "characters"
    if old_chars.is_dir():
        for child in sorted(old_chars.iterdir()):
            if child.name == ".DS_Store":
                continue
            m.move(child, chars / child.name)
        m.prune(old_chars)

    # 3. a book's reference images belong to the characters
    for book, series in BOOK_REFERENCE_SERIES.items():
        refs = (books / book / "references") if (books / book / "references").is_dir() else (projects / book / "references")
        if refs.is_dir():
            for child in sorted(refs.iterdir()):
                if child.name != ".DS_Store":
                    m.move(child, chars / series / "references" / child.name)
            m.prune(refs)

    # 4. runs started from the wrong folder wrote into scripts/projects/<name>/...
    stray = root / "scripts" / "projects"
    if stray.is_dir():
        for proj in sorted(p for p in stray.iterdir() if p.is_dir()):
            slug = proj.name
            kind = kinds.get(slug) or ("book" if (books / slug).is_dir() else "character-set" if (chars / slug).is_dir() else "prompts" if (prompts / slug).is_dir() else None)
            if kind is None:
                m.notes.append(f"left alone (no matching project): scripts/projects/{slug}")
                continue
            base = {"book": books, "character-set": chars, "prompts": prompts}[kind]
            for child in sorted(proj.iterdir()):
                if child.name != ".DS_Store":
                    m.move(child, base / slug / child.name)
            m.prune(proj)
        m.prune(stray)

    # 5. rewrite "projects/<old place>/..." inside the character token files (the references moved)
    rules = [("projects/" + book + "/references/", f"projects/characters/{series}/references/") for book, series in BOOK_REFERENCE_SERIES.items()]
    for slug, kind in kinds.items():
        new = {"book": "books", "character-set": "characters", "prompts": "prompts"}.get(kind)
        if new:
            rules.append((f"projects/{slug}/", f"projects/{new}/{slug}/"))
    changed_files = []
    token_roots = [chars] if args.apply else [chars, old_chars]
    for tr in token_roots:
        if not tr.is_dir():
            continue
        for series in sorted(p for p in tr.iterdir() if p.is_dir() and not (p / "promptset.json").exists()):
            for f in sorted(series.glob("*.json")):
                try:
                    text = f.read_text()
                except OSError:
                    continue
                new_text = rewrite_paths(text, rules) if "projects/" in text else text
                if new_text != text:
                    changed_files.append(f)
                    if args.apply:
                        json.loads(new_text)               # never write a broken file
                        f.write_text(new_text)

    # report
    mode = "APPLIED" if args.apply else "DRY RUN (nothing changed)"
    print(f"== {mode}  root={root}")
    for src, dst in m.moved:
        print(f"  move  {src.relative_to(root)}  ->  {dst.relative_to(root)}")
    for src, dst in m.duplicates:
        print(f"  duplicate (identical, dropped)  {src.relative_to(root)}  =  {dst.relative_to(root)}")
    for src, dst in m.conflicts:
        print(f"  CONFLICT (kept both)  {src.relative_to(root)}  and  {dst.relative_to(root)}")
    for f in changed_files:
        print(f"  paths rewritten in  {f.relative_to(root)}")
    for n in m.notes:
        print("  note:", n)
    print(f"== {len(m.moved)} move(s), {len(m.duplicates)} identical duplicate(s), {len(m.conflicts)} conflict(s), {len(changed_files)} file(s) with rewritten paths")
    if not args.apply and (m.moved or changed_files):
        print("   run again with --apply to do it")


if __name__ == "__main__":
    sys.exit(main())
