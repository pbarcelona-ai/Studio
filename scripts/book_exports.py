"""Storyboard and illustrated book exports (BOOK_TO_SCREEN_BUILD.md Sections 1 (Products B and C), 13; milestone M6).

  exports/storyboard_<style>.pdf        6 frames per page (2 x 3) with the shot number, lens, action and dialogue; a title page
  exports/illustrated_<style>.pdf       one picture per page with the story text under it (the Illustrator's page plan)
  exports/illustrated_<style>.epub      the same as an EPUB 3 book

The page plan (pictures/<style>/pages.json) is written by the Illustrator / Book Designer (one AI call): which picture goes on each page and
the text on it, from the screenplay. Without it, each scene becomes a page with its first approved picture and its action lines.
Pictures are put into the PDF as JPEG (Pillow); standard library otherwise; works the same on Windows and macOS.
"""
from __future__ import annotations

import html
import io
import json
import textwrap
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path

import layout
import pictures
import production
import screenplay_export
import shot_list

Ask = Callable[[str, str | list[str], str, Callable[[dict], None]], dict]
PAGE_W, PAGE_H = 612, 792                    # Letter, in points


class ExportError(RuntimeError):
    """An export cannot be made yet; the message says why."""


def _jpeg(path: Path, max_side: int = 1400) -> tuple[bytes, int, int]:
    from PIL import Image
    with Image.open(path) as src:
        im = src.convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue(), im.width, im.height


class PDF:
    """Pages of Helvetica text and JPEG pictures."""

    def __init__(self) -> None:
        self.objs: list[bytes] = []
        self.pages: list[tuple[list[str], dict[str, int]]] = []
        self.font = self._add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        self.bold = self._add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

    def _add(self, b: bytes) -> int:
        self.objs.append(b)
        return len(self.objs)

    def page(self) -> None:
        self.pages.append(([], {}))

    def text(self, x: float, y: float, s: str, size: float = 10, bold: bool = False) -> None:
        """x, y in points from the top left."""
        ops, _ = self.pages[-1]
        ops.append(f"BT /{'F2' if bold else 'F1'} {size} Tf 1 0 0 1 {x:.1f} {PAGE_H - y:.1f} Tm ({screenplay_export._pdf_text(s)}) Tj ET")

    def wrapped(self, x: float, y: float, s: str, width_chars: int, size: float = 10, lead: float = 12, max_lines: int = 99) -> float:
        lines = textwrap.wrap(s, width_chars)[:max_lines]
        for i, ln in enumerate(lines):
            self.text(x, y + i * lead, ln, size)
        return y + len(lines) * lead

    def image(self, path: Path, x: float, y: float, w: float, h: float) -> None:
        """Fit the picture inside the box (x, y from the top left), keeping its shape."""
        data, iw, ih = _jpeg(path)
        name = f"Im{len(self.objs) + 1}"
        obj = self._add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n"
                        % (iw, ih, len(data)) + data + b"\nendstream")
        scale = min(w / iw, h / ih)
        dw, dh = iw * scale, ih * scale
        ox, oy = x + (w - dw) / 2, y + (h - dh) / 2
        ops, imgs = self.pages[-1]
        imgs[name] = obj
        ops.append(f"q {dw:.1f} 0 0 {dh:.1f} {ox:.1f} {PAGE_H - oy - dh:.1f} cm /{name} Do Q")

    def rect(self, x: float, y: float, w: float, h: float) -> None:
        self.pages[-1][0].append(f"0.7 G 0.5 w {x:.1f} {PAGE_H - y - h:.1f} {w:.1f} {h:.1f} re S")

    def bytes(self) -> bytes:
        kids = []
        pages_id = len(self.objs) + 2 * len(self.pages) + 1
        for ops, imgs in self.pages:
            stream = "\n".join(ops).encode("latin-1", errors="replace")
            content = self._add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
            xo = " ".join(f"/{k} {v} 0 R" for k, v in imgs.items())
            kids.append(self._add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] /Resources << /Font << /F1 {self.font} 0 R "
                                  f"/F2 {self.bold} 0 R >> /XObject << {xo} >> >> /Contents {content} 0 R >>".encode()))
        self._add(f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode())
        catalog = self._add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, o in enumerate(self.objs, 1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(self.objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
        out += f"trailer\n<< /Size {len(self.objs) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(out)


def _frames(pdir: Path, sid: str) -> list[dict]:
    """Every shot with its approved picture (an absolute path) and its shot-list details."""
    st = pictures.status(pdir, sid)
    if not st["shots"]:
        raise ExportError("There are no pictures yet: make and render the pictures first.")
    setdir = layout.find_dir(st["set"])
    sl = shot_list.load(pdir)
    by = {(sc["id"], s["n"]): (sc, s) for sc in sl.get("scenes", []) for s in sc["shots"]}
    out = []
    for p in st["shots"]:
        sc, s = by.get((p["scene"], p["shot"]), ({"heading": ""}, {}))
        out.append({**p, "path": (setdir / p["image"]) if p["image"] and setdir else None, "heading": sc["heading"], "lens": s.get("lens_mm", ""),
                    "type": s.get("type", ""), "action": s.get("action", ""), "dialogue": s.get("dialogue", "")})
    return out


def storyboard_pdf(pdir: Path, sid: str, title: str) -> bytes:
    frames = _frames(pdir, sid)
    pdf = PDF()
    pdf.page()
    pdf.text(72, 300, title, 24, bold=True)
    pdf.text(72, 330, f"Storyboard - {production.style_name({'id': sid})}", 14)
    pdf.text(72, 350, f"{len(frames)} shots", 11)
    cell_w, cell_h, margin = 234, 212, 54
    for i, f in enumerate(frames):
        if i % 6 == 0:
            pdf.page()
            pdf.text(margin, 36, f"{title} - storyboard ({production.style_name({'id': sid})})", 9)
        col, row = (i % 6) % 2, (i % 6) // 2
        x, y = margin + col * (cell_w + 36), 56 + row * (cell_h + 20)
        if f["path"] is not None and f["path"].is_file():
            pdf.image(f["path"], x, y, cell_w, cell_h * 0.62)
        else:
            pdf.rect(x, y, cell_w, cell_h * 0.62)
            pdf.text(x + 70, y + 60, "(no picture yet)", 9)
        ty = y + cell_h * 0.62 + 12
        pdf.text(x, ty, f"{f['scene']} / shot {f['shot']}   {f['type']} {f['lens']} mm" + ("" if f["approved"] else "   (not approved)"), 9, bold=True)
        ty = pdf.wrapped(x, ty + 12, f["action"], 50, 8, 10, 4)
        if f["dialogue"]:
            pdf.wrapped(x, ty + 2, f'"{f["dialogue"]}"', 50, 8, 10, 2)
    return pdf.bytes()


# ---------------------------------------------------------------------------------------------- the illustrated book
def check_pages(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("pages"), list) or not d["pages"]:
        raise ValueError('reply with {"pages": [{"picture": 1, "text": "..."}]}')
    for p in d["pages"]:
        if not isinstance(p, dict) or not isinstance(p.get("picture"), int) or not str(p.get("text", "")).strip():
            raise ValueError("every page has a picture number and its text")


def page_plan(pdir: Path, sid: str, ask: Ask | None = None) -> list[dict]:
    """[{picture: row, text}] - the Illustrator's plan, or one page per scene (its first picture and its action lines) without an AI."""
    frames = _frames(pdir, sid)
    saved = pictures._read(pictures.pdir_of(pdir, sid) / "pages.json")
    if saved and not ask:
        return saved
    if ask is not None:
        listing = "\n".join(f"picture {f['row']}: {f['heading']} | {f['action']} | {f['dialogue']}" for f in frames)
        d = ask("Plan the illustrated book: choose the pictures that tell the story best (about one per scene, more for big moments) and write the "
                "story text for each page in warm, simple prose for the book's readers, in the past tense, from the screenplay. "
                'Reply as JSON: {"pages": [{"picture": 1, "text": "..."}]}\n\n' + listing, "illustrator", "illustrated book: page plan", check_pages)
        rows = {f["row"] for f in frames}
        pages = [{"picture": p["picture"], "text": " ".join(str(p["text"]).split())} for p in d["pages"] if p["picture"] in rows]
    else:
        pages, seen = [], set()
        for f in frames:
            if f["scene"] not in seen:
                seen.add(f["scene"])
                acts = [x["action"] for x in frames if x["scene"] == f["scene"]]
                pages.append({"picture": f["row"], "text": " ".join(acts)})
    pictures._write(pictures.pdir_of(pdir, sid) / "pages.json", pages)
    return pages


def illustrated_pdf(pdir: Path, sid: str, title: str) -> bytes:
    frames = {f["row"]: f for f in _frames(pdir, sid)}
    pdf = PDF()
    pdf.page()
    pdf.text(72, 320, title, 28, bold=True)
    for p in page_plan(pdir, sid):
        f = frames.get(p["picture"])
        pdf.page()
        if f and f["path"] is not None and f["path"].is_file():
            pdf.image(f["path"], 54, 54, PAGE_W - 108, 430)
        pdf.wrapped(72, 520, p["text"], 80, 12, 16, 14)
    return pdf.bytes()


def illustrated_epub(pdir: Path, sid: str, title: str) -> bytes:
    frames = {f["row"]: f for f in _frames(pdir, sid)}
    pages = page_plan(pdir, sid)
    book_id = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, f'studio:{pdir.name}:{sid}')}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")                    # first and stored, as EPUB requires
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        manifest, spine, nav = [], [], []
        for i, p in enumerate(pages, 1):
            f = frames.get(p["picture"])
            img = ""
            if f and f["path"] is not None and f["path"].is_file():
                data, _, _ = _jpeg(f["path"])
                z.writestr(f"OEBPS/img/p{i:03d}.jpg", data, zipfile.ZIP_DEFLATED)
                manifest.append(f'<item id="img{i}" href="img/p{i:03d}.jpg" media-type="image/jpeg"/>')
                img = f'<img src="img/p{i:03d}.jpg" alt="Picture for page {i}" style="max-width:100%"/>'
            z.writestr(f"OEBPS/p{i:03d}.xhtml", f'<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml" lang="en">'
                       f'<head><title>{html.escape(title)} - page {i}</title></head><body>{img}<p>{html.escape(p["text"])}</p></body></html>', zipfile.ZIP_DEFLATED)
            manifest.append(f'<item id="p{i}" href="p{i:03d}.xhtml" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="p{i}"/>')
            nav.append(f'<li><a href="p{i:03d}.xhtml">Page {i}</a></li>')
        z.writestr("OEBPS/nav.xhtml", '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en">'
                   f'<head><title>{html.escape(title)}</title></head><body><nav epub:type="toc"><ol>{"".join(nav)}</ol></nav></body></html>', zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", f'<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
                   f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">{book_id}</dc:identifier><dc:title>{html.escape(title)}</dc:title>'
                   '<dc:language>en</dc:language><meta property="dcterms:modified">2026-01-01T00:00:00Z</meta></metadata>'
                   f'<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>{"".join(manifest)}</manifest>'
                   f'<spine>{"".join(spine)}</spine></package>', zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def export(pdir: Path, sid: str = "", kinds: tuple[str, ...] = ("storyboard", "illustrated", "epub")) -> list[Path]:
    sid = sid or production.load(pdir)["master"]
    title = screenplay_export.load(pdir)[0] if (pdir / "adaptation").is_dir() else pdir.name.replace("_", " ").title()
    out = pdir / "exports"
    out.mkdir(exist_ok=True)
    made = []
    makers: dict[str, tuple[str, Callable[[], bytes]]] = {
        "storyboard": (f"storyboard_{sid}.pdf", lambda: storyboard_pdf(pdir, sid, title)),
        "illustrated": (f"illustrated_{sid}.pdf", lambda: illustrated_pdf(pdir, sid, title)),
        "epub": (f"illustrated_{sid}.epub", lambda: illustrated_epub(pdir, sid, title))}
    for k in kinds:
        if k not in makers:
            raise ExportError(f"unknown export {k!r}")
        name, make = makers[k]
        (out / name).write_bytes(make())
        made.append(out / name)
    return made


def fake_ask(pdir: Path) -> Ask:
    def ask(prompt: str, roles, step: str, validate: Callable[[dict], None]) -> dict:
        rows = [int(ln.split(":")[0].split()[1]) for ln in prompt.split("\n") if ln.startswith("picture ")]
        d = {"pages": [{"picture": r, "text": f"Page text for picture {r}."} for r in rows[::2] or rows]}
        validate(d)
        return d
    return ask


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print(json.dumps([str(p) for p in export(layout.project_dir(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "")]))
