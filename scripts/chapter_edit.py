"""Editing a book's chapters after book_ingest.py has split it: rename, merge, split and drop.

All functions take the book's folder (projects/books/<book>) and return the new chapter list (see `load`). They rewrite
chapters/chapter-NNN.txt and chapters.json so the numbers stay 1..N with no gaps. Text that is dropped is kept in
dropped_text.txt so nothing is lost. Merging, splitting and dropping change the chapter numbers, which everything written later
(shots, scripts, the continuity book's stage ranges) refers to, so they are refused once any of that exists unless `force=True`.
"""
import shutil
from pathlib import Path

from bookkit import read_json, words, write_json

TITLE_MAX = 80
PREVIEW_CHARS = 160


class ChapterEditError(ValueError):
    """A readable reason an edit was not made (shown to the person as it is)."""


def _files(pdir: Path) -> Path:
    return pdir / "chapters"


def _index(pdir: Path) -> dict:
    idx = read_json(pdir / "chapters.json")
    if not idx or not idx.get("chapters"):
        raise ChapterEditError("This book has no chapters yet: run Read book first.")
    return idx


def _read(pdir: Path, n: int) -> str:
    f = _files(pdir) / f"chapter-{n:03d}.txt"
    if not f.is_file():
        raise ChapterEditError(f"chapter {n} has no text file ({f.name})")
    return f.read_text()


def written_downstream(pdir: Path) -> dict:
    """What has already been made from the current chapter numbers."""
    scripts = len(list((pdir / "scripts").glob("chapter-*.json"))) if (pdir / "scripts").is_dir() else 0
    return {"scripts": scripts, "built": (pdir / "all_shots.csv").exists()}


def load(pdir: Path) -> dict:
    """{"chapters": [{n, title, words, preview}], "method", "format", "front_words", "downstream"}"""
    idx = _index(pdir)
    out = []
    for c in idx["chapters"]:
        text = _read(pdir, c["n"])
        out.append({"n": c["n"], "title": c.get("title", ""), "words": words(text), "preview": text[:PREVIEW_CHARS]})
    front = pdir / "front_matter.txt"
    return {"chapters": out, "method": idx.get("method"), "format": idx.get("format"), "ocr_pages": idx.get("ocr_pages", 0),
            "edited": bool(idx.get("edited")), "front_words": words(front.read_text()) if front.is_file() else 0,
            "downstream": written_downstream(pdir)}


def read_chapter(pdir: Path, n: int) -> dict:
    idx = _index(pdir)
    c = next((c for c in idx["chapters"] if c["n"] == n), None)
    if c is None:
        raise ChapterEditError(f"there is no chapter {n}")
    return {"n": n, "title": c.get("title", ""), "text": _read(pdir, n)}


def _items(pdir: Path) -> list[dict]:
    idx = _index(pdir)
    return [{"title": c.get("title", ""), "body": _read(pdir, c["n"])} for c in idx["chapters"]]


def _clean_title(title: str) -> str:
    t = " ".join(str(title).split())[:TITLE_MAX].strip()
    if not t:
        raise ChapterEditError("a chapter needs a title")
    return t


def _guard(pdir: Path, force: bool) -> None:
    d = written_downstream(pdir)
    if (d["scripts"] or d["built"]) and not force:
        what = f"{d['scripts']} chapters already have shots written" if d["scripts"] else "the CSV files are already built"
        raise ChapterEditError(f"{what}, and this edit renumbers the chapters, so that work would no longer match. "
                               "Rename is always safe; for anything else confirm that you will redo the later steps.")


def _save(pdir: Path, items: list[dict]) -> dict:
    """Write items as chapters 1..N (new folder first, then swap) and update chapters.json."""
    if not items:
        raise ChapterEditError("a book needs at least one chapter")
    new, old = pdir / "chapters.new", pdir / "chapters.old"
    shutil.rmtree(new, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)
    new.mkdir()
    index = []
    for n, it in enumerate(items, start=1):
        (new / f"chapter-{n:03d}.txt").write_text(it["body"])
        index.append({"n": n, "title": it["title"][:TITLE_MAX], "words": words(it["body"]), "chars": len(it["body"])})
    cur = _files(pdir)
    if cur.exists():
        cur.rename(old)
    new.rename(cur)
    shutil.rmtree(old, ignore_errors=True)
    idx = read_json(pdir / "chapters.json", {})
    idx.update(chapters=index, edited=True)
    write_json(pdir / "chapters.json", idx)
    _mark_adaptation_stale(pdir)
    return load(pdir)


def _mark_adaptation_stale(pdir: Path) -> None:
    f = pdir / "adaptation" / "adaptation.json"
    data = read_json(f)
    if isinstance(data, dict):
        data["stale"] = True
        write_json(f, data)


def _check_n(items: list[dict], n) -> int:
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(items):
        raise ChapterEditError(f"there is no chapter {n}")
    return n


def rename(pdir: Path, n: int, title: str) -> dict:
    items = _items(pdir)
    items[_check_n(items, n) - 1]["title"] = _clean_title(title)
    return _save(pdir, items)


def merge(pdir: Path, n: int, force: bool = False) -> dict:
    """Join chapter n and the one after it. The result keeps chapter n's title."""
    items = _items(pdir)
    _check_n(items, n)
    if n == len(items):
        raise ChapterEditError("the last chapter has no next chapter to join")
    _guard(pdir, force)
    items[n - 1]["body"] = (items[n - 1]["body"].rstrip() + " " + items[n]["body"].lstrip()).strip()
    del items[n]
    return _save(pdir, items)


def split(pdir: Path, n: int, at: int, title: str | None = None, force: bool = False) -> dict:
    """Cut chapter n in two at character position `at` of its text (as read_chapter returns it). The cut moves back to the start of the
    word it falls in. The second part gets `title`, or "<title> (part 2)"."""
    items = _items(pdir)
    _check_n(items, n)
    if not isinstance(at, int) or isinstance(at, bool):
        raise ChapterEditError("say where to split")
    body = items[n - 1]["body"]
    if not 0 < at < len(body):
        raise ChapterEditError("the split point must be inside the chapter text")
    while at > 0 and not body[at - 1].isspace():
        at -= 1
    first, second = body[:at].rstrip(), body[at:].lstrip()
    if not first or not second:
        raise ChapterEditError("both halves need some text: move the split point away from the start or end")
    _guard(pdir, force)
    second_title = _clean_title(title) if title else f"{items[n - 1]['title']} (part 2)"[:TITLE_MAX]
    items[n - 1]["body"] = first
    items.insert(n, {"title": second_title, "body": second})
    return _save(pdir, items)


def drop(pdir: Path, ns: list[int], force: bool = False) -> dict:
    """Remove chapters (front matter, contents, notes ...). Their text is appended to dropped_text.txt."""
    items = _items(pdir)
    if not isinstance(ns, list) or not ns:
        raise ChapterEditError("pick at least one chapter to drop")
    gone = sorted({_check_n(items, n) for n in ns})
    if len(gone) >= len(items):
        raise ChapterEditError("a book needs at least one chapter: you cannot drop them all")
    _guard(pdir, force)
    with (pdir / "dropped_text.txt").open("a") as f:
        for n in gone:
            f.write(f"## {items[n - 1]['title']}\n\n{items[n - 1]['body']}\n\n")
    return _save(pdir, [it for i, it in enumerate(items, start=1) if i not in gone])
