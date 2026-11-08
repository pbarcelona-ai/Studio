#!/usr/bin/env python3
"""Where things live under projects/. Every script asks this module instead of building projects/<name> itself.

  projects/
    books/<book>/              a book (adam_eve, enoch, ...): chapters, <book>.json, prompt CSVs, clips, audio, films.
                               A movie belongs to a book.
    characters/<series>/       character token files (one .json per character) and references/<character>/ images.
                               Shared between books: the series "bible" is used by Adam and Eve, Enoch, ...
    characters/char_<name>/    image sets generated for one character on the Characters tab (same layout as a prompt set).
    prompts/<set>/             Single Prompts sets (stand-alone text-to-image / text-to-video).
    regression/regtest_*/      the regression test's results (lanes a and b) and the results collected by hand (lane i), plus regtest_ratings.json.

A slug (project name) is looked up in that order, so callers keep using plain names such as "adam_eve" or "char_adam".
A name that does not exist yet goes where its kind says:  kind="book" -> books/,  kind="prompts" -> characters/ for names that start
with "char_", regression/ for names that start with "regtest_", prompts/ for everything else.

Command line (used by the shell scripts):   python3 scripts/layout.py [--kind book|prompts] <slug>
prints the folder relative to the repository root, e.g.  projects/books/adam_eve
"""
import re
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
BOOKS = PROJECTS / "books"
CHARACTERS = PROJECTS / "characters"
PROMPTS = PROJECTS / "prompts"
REGRESSION = PROJECTS / "regression"
REGRESSION_PREFIX = "regtest_"
SLUG_RE = re.compile(r"^[a-z0-9_]{2,40}$")
CHARACTER_SET_PREFIX = "char_"


def _check(slug: str) -> str:
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise ValueError(f"bad project name {slug!r}: use 2-40 lowercase letters, digits or underscores")
    return slug


def find_dir(slug: str) -> Optional[Path]:
    """The existing folder for this name (book, character set or prompt set), or None."""
    _check(slug)
    for base in (BOOKS, CHARACTERS, PROMPTS, REGRESSION):
        if (base / slug).is_dir():
            return base / slug
    return None


def new_dir(slug: str, kind: str = "book") -> Path:
    """Where a folder that does not exist yet should be created."""
    _check(slug)
    if kind == "book":
        return BOOKS / slug
    if kind == "prompts":
        if slug.startswith(REGRESSION_PREFIX):
            return REGRESSION / slug
        return (CHARACTERS if slug.startswith(CHARACTER_SET_PREFIX) else PROMPTS) / slug
    raise ValueError(f"unknown kind {kind!r}")


def project_dir(slug: str, kind: str = "book") -> Path:
    """The folder for this name: where it already is, else where it would be created."""
    return find_dir(slug) or new_dir(slug, kind)


def kind_of(slug: str) -> Optional[str]:
    """'book', 'character' (a character image set), 'prompts', or None if there is no such folder."""
    _check(slug)
    if (BOOKS / slug).is_dir():
        return "book"
    if (CHARACTERS / slug).is_dir():
        return "character"
    if (PROMPTS / slug).is_dir() or (REGRESSION / slug).is_dir():
        return "prompts"
    return None


def rel(slug: str, kind: str = "book") -> str:
    """The folder relative to the repository root, with forward slashes (for messages and for the shell scripts)."""
    return project_dir(slug, kind).relative_to(ROOT).as_posix()


def book_slugs() -> List[str]:
    return sorted(p.name for p in BOOKS.iterdir() if p.is_dir() and SLUG_RE.match(p.name)) if BOOKS.exists() else []


def promptset_slugs() -> List[str]:
    """Single Prompts sets plus the character image sets (a character series folder has no promptset.json, so it is not listed)."""
    out = []
    if PROMPTS.exists():
        out += [p.name for p in PROMPTS.iterdir() if p.is_dir() and SLUG_RE.match(p.name)]
    if CHARACTERS.exists():
        out += [p.name for p in CHARACTERS.iterdir() if p.is_dir() and SLUG_RE.match(p.name) and (p / "promptset.json").exists()]
    return sorted(out)


def regression_slugs() -> List[str]:
    """The regression lanes (regtest_a, regtest_b, regtest_i). They are kept out of promptset_slugs() so they do not show up as Single Prompts sets."""
    return sorted(p.name for p in REGRESSION.iterdir() if p.is_dir() and SLUG_RE.match(p.name)) if REGRESSION.exists() else []


def all_dirs() -> List[Path]:
    """Every book, character set, prompt set and regression lane folder (not the character token series)."""
    return [BOOKS / s for s in book_slugs()] + [project_dir(s, "prompts") for s in promptset_slugs()] + [REGRESSION / s for s in regression_slugs()]


if __name__ == "__main__":
    args = sys.argv[1:]
    kind = "book"
    if args[:1] == ["--kind"] and len(args) >= 2:
        kind, args = args[1], args[2:]
    if len(args) != 1:
        sys.exit(__doc__)
    try:
        print(rel(args[0], kind))
    except ValueError as e:
        sys.exit(str(e))
