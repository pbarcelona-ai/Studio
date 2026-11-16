"""Screenplay exports (BOOK_TO_SCREEN_BUILD.md Section 13, Product A; milestone M3). Standard library only, works on Windows and macOS.

  python3 screenplay_export.py <project> [pdf fountain docx fdx notes]     -> projects/books/<book>/exports/

  screenplay.pdf      industry format: Courier 12 pt, 1.5" left / 1" right / 1" top and bottom margins, scene numbers in both margins,
                      a title page, page numbers top right from page 2, character cues at 3.7", dialogue 2.5"-6", parentheticals 3.1"
  screenplay.fountain plain-text Fountain
  screenplay.docx     Word, with the same layout (Courier New 12, the same indents)
  screenplay.fdx      Final Draft XML
  readin_notes.pdf    coverage, beat sheet and treatment

The scenes come from the Studio's screenplay (screenplay/scene-*.json, so hand edits are exported), in the order of the plan.
"""
from __future__ import annotations

import json
import sys
import textwrap
import zipfile
from collections.abc import Callable
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptation  # noqa: E402
import screenplay  # noqa: E402

FORMATS = ("pdf", "fountain", "docx", "fdx", "notes")
# layout in inches from the left edge of an 8.5 x 11 page, and the line width in Courier characters (10 per inch at 12 pt)
ACTION = (1.5, 60)
CUE = (3.7, 38)
DIALOGUE = (2.5, 35)
PAREN = (3.1, 25)
TRANSITION_RIGHT = 7.5
LINES_PER_PAGE = 54                       # 9" of text at 6 lines per inch


def load(pdir: Path) -> tuple[str, list[dict], dict]:
    """(title, scenes, plan) from the Studio's plan and screenplay files."""
    plan = adaptation.load(pdir) or {}
    scenes = []
    for s in plan.get("scenes", []):
        sc = screenplay.load_scene(pdir, s["id"])
        if sc:
            scenes.append(sc)
    if not scenes:
        raise ValueError("there is no screenplay yet: press Read it in first")
    title = ""
    for name in (f"{pdir.name}.json",):
        try:
            title = json.loads((pdir / name).read_text(encoding="utf-8")).get("title", "")
        except (OSError, ValueError):
            pass
    return title or pdir.name.replace("_", " ").title(), scenes, plan


# ---------------------------------------------------------------------------------------------- Fountain
def to_fountain(title: str, scenes: list[dict], credit: str = "Adapted with Pistachio's Studio") -> str:
    out = [f"Title: {title}", f"Credit: {credit}", ""]
    for n, s in enumerate(scenes, 1):
        out += [f"{s['heading']} #{n}#", ""]
        for e in s["elements"]:
            if e["type"] == "dialogue":
                out.append(e["character"].upper())
                if e.get("note"):
                    out.append(f"({e['note'].strip('()')})")
                out += [e["text"], ""]
            elif e["type"] == "transition":
                out += [f"> {e['text'].upper()}", ""]
            else:
                out += [e["text"], ""]
    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------------------------------------- Final Draft
def to_fdx(title: str, scenes: list[dict]) -> str:
    paras = []

    def p(kind: str, text: str, number: str = "") -> None:
        num = f' Number="{number}"' if number else ""
        paras.append(f'    <Paragraph Type="{kind}"{num}><Text>{escape(text)}</Text></Paragraph>')
    for n, s in enumerate(scenes, 1):
        p("Scene Heading", s["heading"], str(n))
        for e in s["elements"]:
            if e["type"] == "dialogue":
                p("Character", e["character"].upper())
                if e.get("note"):
                    p("Parenthetical", f"({e['note'].strip('()')})")
                p("Dialogue", e["text"])
            else:
                p("Transition" if e["type"] == "transition" else "Action", e["text"])
    return ('<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n<FinalDraft DocumentType="Script" Template="No" Version="5">\n  <Content>\n'
            + "\n".join(paras) + f'\n  </Content>\n  <TitlePage><Content><Paragraph Type="Title"><Text>{escape(title)}</Text></Paragraph></Content></TitlePage>\n</FinalDraft>\n')


# ---------------------------------------------------------------------------------------------- the page lines (shared by PDF and checks)
def page_lines(scenes: list[dict]) -> list[tuple[float, str, str]]:
    """Every printed line: (left inch, text, kind) with '' lines for blanks. Kinds: heading, action, cue, paren, dialogue, transition."""
    out: list[tuple[float, str, str]] = []
    for n, s in enumerate(scenes, 1):
        out.append((ACTION[0], f"{n}|{s['heading'].upper()}", "heading"))
        out.append((0, "", ""))
        for e in s["elements"]:
            if e["type"] == "dialogue":
                out.append((CUE[0], e["character"].upper(), "cue"))
                if e.get("note"):
                    out += [(PAREN[0], ln, "paren") for ln in textwrap.wrap(f"({e['note'].strip('()')})", PAREN[1])]
                out += [(DIALOGUE[0], ln, "dialogue") for ln in textwrap.wrap(e["text"], DIALOGUE[1]) or [""]]
            elif e["type"] == "transition":
                t = e["text"].upper()
                out.append((TRANSITION_RIGHT - len(t) / 10, t, "transition"))
            else:
                out += [(ACTION[0], ln, "action") for ln in textwrap.wrap(e["text"], ACTION[1]) or [""]]
            out.append((0, "", ""))
    return out


def paginate(lines: list[tuple[float, str, str]]) -> list[list[tuple[float, str, str]]]:
    """Pages of at most LINES_PER_PAGE lines; a scene heading never ends a page, and a character cue stays with its first line."""
    pages: list[list[tuple[float, str, str]]] = [[]]
    i = 0
    while i < len(lines):
        page = pages[-1]
        x, t, k = lines[i]
        if not page and not t:
            i += 1
            continue
        keep = 3 if k == "heading" else 2 if k == "cue" else 1
        if len(page) + keep > LINES_PER_PAGE:
            pages.append([])
            continue
        page.append(lines[i])
        i += 1
    return [p for p in pages if p]


# ---------------------------------------------------------------------------------------------- a small PDF writer (built-in Courier, no fonts to embed)
def _pdf_text(t: str) -> str:
    b = t.encode("cp1252", errors="replace").decode("latin-1")
    return b.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[list[tuple[float, float, str, bool]]]) -> bytes:
    """pages of (x inch, y inch from the top, text, bold) -> a PDF file. Letter size, Courier / Courier-Bold 12 pt."""
    objs: list[bytes] = []

    def add(b: bytes) -> int:
        objs.append(b)
        return len(objs)
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold /Encoding /WinAnsiEncoding >>")
    pages_id = len(objs) + 2 * len(pages) + 1
    kids = []
    for pg in pages:
        ops = ["BT"]
        for x, y, text, b in pg:
            ops.append(f"/{'F2' if b else 'F1'} 12 Tf 1 0 0 1 {x * 72:.2f} {(11 - y) * 72:.2f} Tm ({_pdf_text(text)}) Tj")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font} 0 R /F2 {bold} 0 R >> >> "
                        f"/Contents {content} 0 R >>".encode()))
    assert len(objs) + 1 == pages_id
    add(f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode())
    catalog = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def to_pdf(title: str, scenes: list[dict], credit: str = "Adapted with Pistachio's Studio") -> bytes:
    title_page = [(4.25 - len(title.upper()) / 20, 3.5, title.upper(), True), (4.25 - len("written by") / 20, 4.0, "written by", False),
                  (4.25 - len(credit) / 20, 4.5, credit, False)]
    pages = [title_page]
    for n, pg in enumerate(paginate(page_lines(scenes)), 1):
        items: list[tuple[float, float, str, bool]] = [(7.5 - len(f"{n}.") / 10, 0.5, f"{n}.", False)] if n > 1 else []
        for row, (x, text, kind) in enumerate(pg):
            y = 1.0 + row / 6
            if kind == "heading":
                num, head = text.split("|", 1)
                items += [(x - 0.6, y, num, False), (x, y, head, True), (7.6, y, num, False)]
            elif text:
                items.append((x, y, text, False))
        pages.append(items)
    return make_pdf(pages)


def notes_pdf(pdir: Path) -> bytes:
    """Coverage, beat sheet and treatment, one after the other, as plain Courier pages."""
    rd = pdir / "readin"
    lines: list[str] = []

    def load_json(name: str) -> dict:
        try:
            return json.loads((rd / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    cov, beats = load_json("coverage.json"), load_json("beats.json")
    if cov:
        lines += ["COVERAGE", "", f"Logline: {cov.get('logline', '')}", f"Genre: {cov.get('genre', '')}    Tone: {cov.get('tone', '')}",
                  f"Themes: {', '.join(cov.get('themes', []))}", "", "Characters:"]
        lines += [f"- {c.get('name', '')} ({c.get('role', '')}): {c.get('description', '')}" for c in cov.get("characters", [])]
        lines += ["", "Key events:"] + [f"- {e}" for e in cov.get("key_events", [])] + ["", f"Filmable: {cov.get('filmable', '')}", ""]
    if beats:
        lines += ["BEAT SHEET", ""]
        for a in beats.get("acts", []):
            lines.append(f"{a.get('name', '')}: {a.get('purpose', '')}")
            lines += [f"  {b.get('n', '')}. {b.get('name', '')}: {b.get('description', '')}" for b in a.get("beats", [])]
            lines.append("")
    if (rd / "treatment.md").is_file():
        lines += ["TREATMENT", ""] + (rd / "treatment.md").read_text(encoding="utf-8").split("\n")
    wrapped: list[str] = []
    for ln in lines:
        wrapped += textwrap.wrap(ln, 65, subsequent_indent="    ") or [""]
    pages = [wrapped[i:i + LINES_PER_PAGE] for i in range(0, max(1, len(wrapped)), LINES_PER_PAGE)]
    return make_pdf([[(1.0, 1.0 + r / 6, t, t.isupper() and len(t) < 20) for r, t in enumerate(pg) if t] for pg in pages])


# ---------------------------------------------------------------------------------------------- Word
def _w_para(text: str, style: str) -> str:
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def to_docx(title: str, scenes: list[dict]) -> bytes:
    tw = lambda inch: int(inch * 1440)                                             # noqa: E731  twips
    styles = {"Heading": ("", True, 0, 0), "Action": ("", False, 0, 0), "Character": ("", False, tw(CUE[0] - ACTION[0]), 0),
              "Dialogue": ("", False, tw(DIALOGUE[0] - ACTION[0]), tw(1.5)), "Parenthetical": ("", False, tw(PAREN[0] - ACTION[0]), tw(2.0)),
              "Transition": ("right", False, 0, 0), "Title": ("center", True, 0, 0)}
    st = "".join(f'<w:style w:type="paragraph" w:styleId="{k}"><w:name w:val="{k}"/><w:pPr><w:spacing w:after="{0 if k in ("Character", "Parenthetical") else 240}"/>'
                 + (f'<w:jc w:val="{j}"/>' if j else "") + f'<w:ind w:left="{left}" w:right="{right}"/></w:pPr><w:rPr><w:rFonts w:ascii="Courier New" '
                 f'w:hAnsi="Courier New"/>{"<w:b/><w:caps/>" if b else ""}<w:sz w:val="24"/></w:rPr></w:style>' for k, (j, b, left, right) in styles.items())
    body = [_w_para(title.upper(), "Title"), _w_para("Adapted with Pistachio's Studio", "Title"), '<w:p><w:r><w:br w:type="page"/></w:r></w:p>']
    for n, s in enumerate(scenes, 1):
        body.append(_w_para(f"{n}  {s['heading'].upper()}", "Heading"))
        for e in s["elements"]:
            if e["type"] == "dialogue":
                body.append(_w_para(e["character"].upper(), "Character"))
                if e.get("note"):
                    body.append(_w_para(f"({e['note'].strip('()')})", "Parenthetical"))
                body.append(_w_para(e["text"], "Dialogue"))
            else:
                body.append(_w_para(e["text"].upper() if e["type"] == "transition" else e["text"], "Transition" if e["type"] == "transition" else "Action"))
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {w}><w:body>{"".join(body)}'
           f'<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="2160" w:header="720" w:footer="720"/></w:sectPr></w:body></w:document>')
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                   '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("word/document.xml", doc)
        z.writestr("word/styles.xml", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {w}>{st}</w:styles>')
    return buf.getvalue()


def export(pdir: Path, formats: tuple[str, ...] = FORMATS) -> list[Path]:
    title, scenes, _ = load(pdir)
    out = pdir / "exports"
    out.mkdir(exist_ok=True)
    made = []
    for f in formats:
        if f not in FORMATS:
            raise ValueError(f"unknown format {f!r}: use {', '.join(FORMATS)}")
        target = out / ("readin_notes.pdf" if f == "notes" else f"screenplay.{f}")
        makers: dict[str, Callable[[], bytes | str]] = {"pdf": lambda: to_pdf(title, scenes), "fountain": lambda: to_fountain(title, scenes),
                                                        "docx": lambda: to_docx(title, scenes), "fdx": lambda: to_fdx(title, scenes), "notes": lambda: notes_pdf(pdir)}
        data = makers[f]()
        (target.write_bytes(data) if isinstance(data, bytes) else target.write_text(data, encoding="utf-8"))
        made.append(target)
    return made


if __name__ == "__main__":
    from layout import project_dir
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    try:
        for p in export(project_dir(sys.argv[1]), tuple(sys.argv[2:]) or FORMATS):
            print(f"wrote {p}")
    except ValueError as e:
        sys.exit(str(e))
