#!/usr/bin/env python3
"""Check that scanned-page reading works on this computer: draws a known sentence into a picture-only PDF, reads it with the engine the
Studio would use (tesseract if installed, else rapidocr) and says how many words came back.

  python3 check_ocr.py
  uv run --python ">=3.11,<3.14" --with pillow --with pypdf --with rapidocr --with onnxruntime python check_ocr.py     # no tesseract installed

Exit 0 when at least 80 % of the words are read, 1 otherwise (or when there is no engine at all).
"""
import re
import sys
import tempfile
from pathlib import Path
from typing import Callable

import book_formats as bf

SENTENCES = ["In the beginning God created the heaven and the earth.",
             "And the earth was without form and void and darkness was upon the face of the deep.",
             "And God said let there be light and there was light."]


def make_scan(path: Path, lines: list[str]) -> None:
    """A one-page PDF that holds only a picture of the text (no text layer), like a scan."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1700, 400 + 90 * len(lines)), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=44)
    for i, ln in enumerate(lines):
        d.text((80, 120 + 90 * i), ln, fill="black", font=font)
    img.save(path, "PDF", resolution=150)


def words_of(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


def check(engine: Callable | None = None, lines: list[str] = SENTENCES) -> tuple[str, int, int]:
    """(engine name, words found, words expected). `engine` overrides the one the Studio would pick (tests)."""
    name = "given" if engine else (bf.ocr_engine_name() or "none")
    if name == "none":
        return name, 0, len(words_of(" ".join(lines)))
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "scan.pdf"
        make_scan(pdf, lines)
        book = bf.read_book(pdf, engine=engine)
    got = set(words_of(" ".join(book.pages)))
    want = words_of(" ".join(lines))
    return name, sum(1 for w in want if w in got), len(want)


def main() -> int:
    name, found, total = check()
    if name == "none":
        print("No OCR engine here. Install tesseract (macOS: `brew install tesseract`, or `sudo port install tesseract tesseract-eng`), or run this through uv with rapidocr (see the top of this file).")
        return 1
    print(f"engine: {name}; {found} of {total} words read")
    return 0 if found >= 0.8 * total else 1


if __name__ == "__main__":
    sys.exit(main())
