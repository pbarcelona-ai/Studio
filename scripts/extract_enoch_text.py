#!/usr/bin/env python3
"""Extract the 1 Enoch verse text (R. H. Charles translation) from the PDF into enoch_verses.json.

Run once:  uv run --with pypdf python extract_enoch_text.py
Output: {"1": {"verses": ["The words of the blessing of Enoch ...", ...], "text": "..."}, ...}  (keys are chapter numbers)

Charles reorders chapters 91-93 (order in the book: 90, 92, 91 part 1, 93, 91 part 2, 94); both parts of 91
are joined under chapter 91. The editor's critical marks (⌈ ⌉ [ ] < > †) are removed and ALL-CAPS divine
names (GOD, HE, THE LORD) become normal capitalisation so a speech model does not spell them out.
"""
import json
import re
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
import layout
ENOCH_DIR = layout.project_dir("enoch")
PDF = ENOCH_DIR / "source" / "Book-of-Enoch-1-Enoch-Free-PDF-Download.pdf"
text = "\n".join((p.extract_text() or "") for p in PdfReader(PDF).pages)
text = re.sub(r"(?m)^\s*\d{1,3}\s*$", "", text)                 # bare page numbers

heads = list(re.finditer(r"(?im)^CHAPTER\s+(\d+)\b\.?[^\n]*$", text))
chapters: dict = {}
for i, m in enumerate(heads):
    n = int(m.group(1))
    body = text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
    chapters[n] = chapters.get(n, "") + "\n" + body          # chapter 91 appears twice; parts are joined

def caps_to_title(m):
    w = m.group(0)
    if w in {"AND", "OF", "OR"}:
        return w.lower()
    return w if len(w) < 2 or w in {"II", "III", "IV", "VI"} else w[0] + w[1:].lower()

def clean(s):
    s = re.sub(r"[⌈⌉†]", "", s)
    s = re.sub(r"[\[\]<>]", "", s)
    s = s.replace("--", " — ").replace("’", "'")
    s = re.sub(r"\b[A-Z]{2,}\b", caps_to_title, s)
    return re.sub(r"\s+", " ", s).strip()

out = {}
for n in range(1, 109):
    body = chapters.get(n, "")
    parts = re.split(r"(?m)^\s*(\d{1,3})\.\s+", body)       # verse numbers at line starts
    verses = []
    if len(parts) > 1:
        lead = clean(parts[0])
        if lead:
            verses.append(lead)
        verses += [clean(v) for v in parts[2::2] if clean(v)]
    elif clean(body):
        verses = [clean(body)]                               # chapters printed without verse numbers
    out[str(n)] = {"verses": verses, "text": " ".join(verses)}
json.dump(out, open(ENOCH_DIR / "enoch_verses.json", "w"), indent=1, ensure_ascii=False)
empty = [n for n, v in out.items() if not v["text"]]
print(f"{len(out)} chapters, {sum(len(v['verses']) for v in out.values())} verses, {sum(len(v['text']) for v in out.values())} characters; empty: {empty or 'none'}")
