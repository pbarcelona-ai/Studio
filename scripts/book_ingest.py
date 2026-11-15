#!/usr/bin/env python3
"""Step 1 of a new book: read the book file and split it into chapters.

  uv run --with pypdf --with pillow python book_ingest.py <project_name> <path/to/book>

The book can be a .pdf (scans are read with OCR), .epub, .docx, .html or a .txt / .md text file (see book_formats.py).
Creates projects/<project_name>/ with source/<file>, source_text.txt, chapters/chapter-NNN.txt and chapters.json.
EPUB, DOCX and HTML files are split on their own chapter divisions. Otherwise chapters are found from headings
("CHAPTER 5", "Psalm 23", "BOOK II", a lone roman numeral ...). If no usable headings exist the text is cut into sections
of about 2,500 words. Cover, copyright and contents pages go to front_matter.txt, notes and licences to back_matter.txt.
Check chapters.json afterwards; the Chapters card in the Studio can merge, split, rename and drop chapters, and you can
also edit it by hand and then rerun the later steps.
"""
import argparse
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from book_formats import BookReadError, read_book
from bookkit import project_dir, slugify, words, write_json

ap = argparse.ArgumentParser()
ap.add_argument("project")
ap.add_argument("pdf", help="the book: a .pdf, .epub, .docx, .html, or a .txt / .md text file")
ap.add_argument("--section-words", type=int, default=2500, help="size of sections when no headings are found")
ap.add_argument("--no-ocr", action="store_true", help="do not read scanned PDF pages with OCR")
args = ap.parse_args()

pdir = project_dir(slugify(args.project))
src = Path(args.pdf).expanduser()
if not src.exists():
    sys.exit(f"PDF not found: {src}")      # (also said for other book files; studio.py looks for this text)
(pdir / "source").mkdir(parents=True, exist_ok=True)
dest = pdir / "source" / src.name
if src.resolve() != dest.resolve():
    shutil.copy2(src, dest)

try:
    book = read_book(dest, ocr=not args.no_ocr, progress=lambda m: print(m, flush=True))
except BookReadError as e:
    sys.exit(str(e))
pages = book.pages
is_text = book.kind != "pdf"                                     # only a PDF has running headers and page numbers to strip
for note in book.notes:
    print("note:", note)

# running headers/footers: short lines that repeat on many pages
line_counts = Counter(l.strip() for p in pages for l in set(p.splitlines()) if 0 < len(l.strip()) < 70)
repeated = set() if is_text else {l for l, c in line_counts.items() if c > max(5, len(pages) * 0.25) and not re.search(r"(?i)chapter|psalm|book", l)}
clean_pages = []
for p in pages:
    lines = [l for l in p.splitlines() if l.strip() not in repeated and (is_text or not re.fullmatch(r"\s*\d{1,4}\s*", l))]
    clean_pages.append("\n".join(lines))
text = "\n\n".join(clean_pages)
text = re.sub(r"[ \t]+", " ", text)
text = re.sub(r"(?<=\w)-\n(?=[a-z])", "", text)                  # hyphenated line breaks
(pdir / "source_text.txt").write_text(text)

ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def to_int(s):
    if s.isdigit():
        return int(s)
    total, prev = 0, 0
    for ch in reversed(s.upper()):
        v = ROMAN.get(ch, 0)
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


PATTERNS = {
    "chapter": r"(?im)^\s*(?:CHAPTER|CHAP\.)\s+([0-9]+|[IVXLCDM]+)\b[^\n]*$",
    "psalm": r"(?im)^\s*PSALM\s+(\d+)\b[^\n]*$",
    "part": r"(?im)^\s*(?:BOOK|PART|SECTION)\s+([0-9]+|[IVXLCDM]+)\b[^\n]*$",
    "roman": r"(?m)^\s*([IVXLCDM]{1,7})\.?\s*$",
}


def best_run(pattern):
    """Longest-text run of increasing numbers (the table of contents is a run of tiny sections; the body is not)."""
    ms = list(re.finditer(pattern, text))
    if len(ms) < 3:
        return []
    runs: list = []
    cur: list = []
    prev = 0
    for m in ms:
        n = to_int(m.group(1))
        if cur and n <= prev:
            runs.append(cur); cur = []
        cur.append(m); prev = n
    runs.append(cur)

    def span(run):
        end = ms[ms.index(run[-1]) + 1].start() if ms.index(run[-1]) + 1 < len(ms) else len(text)
        return end - run[0].start()
    run = max(runs, key=span)
    return run if len(run) >= 3 else []


heads: list = []
method = "sections"
for name, pat in PATTERNS.items():
    run = best_run(pat)
    if len(run) > len(heads) and (len(text) / len(run)) > 400:      # skip patterns that match tiny scraps
        method, heads = name, run

for stale in ("front_matter.txt", "back_matter.txt"):                # from an earlier run
    (pdir / stale).unlink(missing_ok=True)
chapters = []
if book.sections and len(book.sections) >= 3:                        # the file's own divisions (EPUB files, Word styles, HTML headings)
    method = "structure"
    if book.front:
        (pdir / "front_matter.txt").write_text(book.front)
    chapters = [(t, b) for t, b in book.sections]
elif heads:
    front = text[: heads[0].start()].strip()
    if front:
        (pdir / "front_matter.txt").write_text(front)
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.end():end].strip()
        chapters.append((m.group(0).strip(), body))
else:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    cur, count = [], 0
    for p in paras:
        cur.append(p); count += words(p)
        if count >= args.section_words:
            chapters.append((f"Section {len(chapters) + 1}", "\n\n".join(cur))); cur, count = [], 0
    if cur:
        chapters.append((f"Section {len(chapters) + 1}", "\n\n".join(cur)))

cdir = pdir / "chapters"
shutil.rmtree(cdir, ignore_errors=True)
cdir.mkdir()
index = []
for n, (title, body) in enumerate(chapters, start=1):
    body = re.sub(r"\s*\n\s*", " ", re.sub(r"\n\s*\n", "\n\n", body)).strip()      # unwrap lines, keep paragraph gaps as spaces
    (cdir / f"chapter-{n:03d}.txt").write_text(body)
    index.append({"n": n, "title": title[:80], "words": words(body), "chars": len(body)})
if book.back:
    (pdir / "back_matter.txt").write_text(book.back)
write_json(pdir / "chapters.json", {"method": method, "pdf": dest.name, "format": book.kind, "ocr_pages": book.ocr_pages, "pages": len(pages), "chapters": index})

tiny = [c["n"] for c in index if c["words"] < 40]
print(f"{dest.name}: {len(pages)} pages, {words(text):,} words -> {len(index)} chapters (split by: {method})")
print(f"words per chapter: min {min(c['words'] for c in index)}, median {sorted(c['words'] for c in index)[len(index)//2]}, "
      f"max {max(c['words'] for c in index)}")
if method == "sections":
    print("note: no chapter headings were found, so the book was cut into ~%d-word sections." % args.section_words)
if tiny:
    print(f"warning: chapters with under 40 words (check the split): {tiny[:15]}")
