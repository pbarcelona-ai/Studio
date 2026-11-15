#!/usr/bin/env python3
"""Look at how the Studio reads a book file (EPUB, DOCX, HTML, PDF or text) without making a project.

  python3 check_book_file.py path/to/book.epub

Prints the format, how many sections (chapters) the file's own structure gives, their titles and word counts, what was set aside as front
or back matter, pages read by OCR, and any notes. Nothing is written. Exit 1 when the file cannot be read.
"""
import sys
from pathlib import Path

import book_formats as bf


def describe(path: Path, limit: int = 40) -> tuple[int, list[str]]:
    """(exit code, lines to print)."""
    try:
        book = bf.read_book(path)
    except bf.BookReadError as e:
        return 1, [f"cannot read {path.name}: {e}"]
    words = sum(len(p.split()) for p in book.pages)
    out = [f"{path.name}: {book.kind}, {words:,} words, {len(book.pages)} page(s)/part(s)"]
    if book.sections:
        out.append(f"{len(book.sections)} section(s) from the file's own structure:")
        for i, (title, body) in enumerate(book.sections[:limit], 1):
            out.append(f"  {i:>3}. {title[:60] or '(no title)'}  ({len(body.split()):,} words)")
        if len(book.sections) > limit:
            out.append(f"  ... and {len(book.sections) - limit} more")
    else:
        out.append("no sections in the file itself: the Studio will look for chapter headings in the text")
    out.append(f"front matter set aside: {len(book.front.split()):,} words; back matter: {len(book.back.split()):,} words")
    if book.ocr_pages:
        out.append(f"{book.ocr_pages} page(s) had no text and were read with OCR")
    out += [f"note: {n}" for n in book.notes]
    return 0, out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    code, lines = describe(Path(argv[1]))
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
