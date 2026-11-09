#!/usr/bin/env python3
"""Step 1 of a new book: read a PDF and split it into chapters.

  uv run --with pypdf python book_ingest.py <project_name> <path/to/book.pdf>

Creates projects/<project_name>/ with source/<pdf>, source_text.txt, chapters/chapter-NNN.txt and chapters.json.
Chapters are found from headings ("CHAPTER 5", "Psalm 23", "BOOK II", a lone roman numeral ...). If no usable
headings exist the text is cut into sections of about 2,500 words. Check chapters.json afterwards; you can edit or
re-split it by hand and then rerun the later steps.
"""
import argparse
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from pypdf import PdfReader
from bookkit import project_dir, slugify, words, write_json

ap = argparse.ArgumentParser()
ap.add_argument("project")
ap.add_argument("pdf", help="the book: a .pdf, or a .txt / .md text file")
ap.add_argument("--section-words", type=int, default=2500, help="size of sections when no headings are found")
args = ap.parse_args()

pdir = project_dir(slugify(args.project))
src = Path(args.pdf).expanduser()
if not src.exists():
    sys.exit(f"PDF not found: {src}")      # (also said for text files; studio.py looks for this text)
(pdir / "source").mkdir(parents=True, exist_ok=True)
dest = pdir / "source" / src.name
if src.resolve() != dest.resolve():
    shutil.copy2(src, dest)

is_text = dest.suffix.lower() in (".txt", ".md")
if is_text:                                                      # plain text: one "page" per form feed, else the whole text
    raw = dest.read_text(encoding="utf-8-sig", errors="replace")
    pages = [p for p in raw.split("\f") if p.strip()] or [raw]
else:
    pages = [(p.extract_text() or "") for p in PdfReader(dest).pages]
chars = sum(len(p) for p in pages)
if is_text:
    if len(raw.split()) < 5:
        sys.exit("That text is too short to use: write or paste at least a few words.")
elif chars < 200 * max(len(pages), 1) * 0.2 or chars < 2000:
    sys.exit(f"Almost no text was extracted ({chars} characters from {len(pages)} pages). This looks like a scanned "
             "PDF; it needs OCR first (for example with ocrmypdf) before it can be used.")

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
    runs, cur, prev = [], [], 0
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

chapters = []
if heads:
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
write_json(pdir / "chapters.json", {"method": method, "pdf": dest.name, "pages": len(pages), "chapters": index})

tiny = [c["n"] for c in index if c["words"] < 40]
print(f"{dest.name}: {len(pages)} pages, {words(text):,} words -> {len(index)} chapters (split by: {method})")
print(f"words per chapter: min {min(c['words'] for c in index)}, median {sorted(c['words'] for c in index)[len(index)//2]}, "
      f"max {max(c['words'] for c in index)}")
if method == "sections":
    print("note: no chapter headings were found, so the book was cut into ~%d-word sections." % args.section_words)
if tiny:
    print(f"warning: chapters with under 40 words (check the split): {tiny[:15]}")
