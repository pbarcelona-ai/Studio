"""Reading a book file into text: PDF (scans are read with OCR), EPUB, DOCX, ODT, RTF, HTML and plain text.

  book = read_book(path)        # -> BookText

Used by book_ingest.py. Structured formats (EPUB, DOCX, HTML) also give the book's own chapter divisions in `sections`
so the chapters do not have to be guessed from headings in the text. Only the standard library, pypdf and (for scans) Pillow
plus an OCR engine are used. The OCR engine is the `tesseract` program when it is installed, otherwise the `rapidocr` Python
package with `onnxruntime`; `ocr_packages()` tells `uv run` which of those to add.
"""
import contextlib
import io
import posixpath
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET  # noqa: S405  (untrusted XML is refused if it declares an ENTITY; see _safe_xml)

TEXT_EXTS = (".txt", ".md")
HTML_EXTS = (".html", ".htm", ".xhtml")
BOOK_EXTS = (".pdf", ".epub", ".docx", ".odt", ".rtf", ".html", ".htm", ".txt", ".md")       # what the Studio accepts (.xhtml only appears inside EPUBs)
MAX_MEMBER = 80 * 2**20          # the largest single file read out of an EPUB / DOCX (guards against zip bombs)
MAX_MEMBERS = 20000
MIN_PAGE_CHARS = 25              # a PDF page with less text than this is treated as an image-only page
OCR_TARGET_WORDS = 3             # an OCR result with fewer words than this on a whole book is treated as a failure
# Titles of the pieces that are not story. Matched at the start of a short title only, so a chapter called "The Cover-Up" or "Notes from the Road" stays.
FRONT_RE = re.compile(r"(?i)^\W*(cover|title\s*page|half\s*title|copyright|contents|table of contents|dedication|epigraph|acknowledg\w*|about the author|"
                      r"also by|colophon|imprint|praise for|foreword)\b")
BACK_RE = re.compile(r"(?i)^\W*(notes?|endnotes|appendix|appendices|glossary|index|bibliography|about the author|acknowledg\w*|colophon|licen[cs]e|"
                     r"project gutenberg|afterword|also by|copyright)\W*$|project gutenberg")
TITLE_SHORT = 40
HEADING_RE = re.compile(r"(?i)^(?:heading|title)\s*(\d)?$")


class BookReadError(Exception):
    """A readable reason a file cannot be used (shown to the person as it is)."""


@dataclass
class BookText:
    kind: str                                              # pdf | text | epub | docx | html
    pages: list[str]                                       # the text, one entry per page (PDF) or one for the whole book
    sections: list[tuple[str, str]] | None = None          # (title, body) taken from the file's own structure, or None
    front: str = ""                                        # text before the first section
    back: str = ""                                         # notes, licence, about the author after the last section
    ocr_pages: int = 0                                     # pages that had no text and were read with OCR
    notes: list[str] = field(default_factory=list)         # things worth telling the person


# ---------------------------------------------------------------------------------------------- blocks
@dataclass
class Block:
    level: int        # 0 = paragraph, 1-6 = heading level
    text: str


class _Blocks(HTMLParser):
    """Turns HTML into paragraphs and headings. Scripts, styles, <head> and navigation are skipped."""
    BLOCK = {"p", "div", "li", "blockquote", "tr", "section", "article", "pre", "br", "hr", "dd", "dt", "figcaption", "td", "th", "ul", "ol", "table"}
    SKIP = {"script", "style", "head", "nav", "svg", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self._buf: list[str] = []
        self._level = 0
        self._skip = 0

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        self._buf = []
        if text:
            self.blocks.append(Block(self._level, text))

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self._level = int(tag[1])
        elif tag in self.BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self._level = 0
        elif tag in self.BLOCK:
            self._flush()

    def handle_data(self, data):
        if not self._skip:
            self._buf.append(data)

    def close(self):
        super().close()
        self._flush()


def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def html_blocks(data: bytes | str) -> list[Block]:
    p = _Blocks()
    p.feed(data if isinstance(data, str) else decode(data))
    p.close()
    return p.blocks


def blocks_text(blocks: list[Block]) -> str:
    return "\n\n".join(b.text for b in blocks)


def words(text: str) -> int:
    return len(text.split())


def sections_from_blocks(blocks: list[Block], min_sections: int = 3) -> tuple[str, list[tuple[str, str]]] | None:
    """Split at the shallowest heading level (h1, then h2, then h3) that occurs at least `min_sections` times. (front text, [(title, body)]) or None."""
    for level in (1, 2, 3):
        heads = [i for i, b in enumerate(blocks) if b.level == level]
        if len(heads) < min_sections:
            continue
        front = blocks_text(blocks[: heads[0]])
        out = []
        for k, i in enumerate(heads):
            end = heads[k + 1] if k + 1 < len(heads) else len(blocks)
            body = blocks_text(blocks[i + 1: end])
            out.append((blocks[i].text, body))
        return front, out
    return None


def trim_matter(sections: list[tuple[str, str]], front: str = "") -> tuple[str, list[tuple[str, str]], str]:
    """Move cover/copyright/contents sections at the start into the front matter, and notes/licence at the end into the back matter.
    Only the ends are trimmed; a short chapter in the middle of the book stays."""
    secs = list(sections)
    back_parts: list[str] = []
    front_parts = [front] if front.strip() else []

    def is_front(s):
        return (len(s[0]) <= TITLE_SHORT and bool(FRONT_RE.search(s[0]))) or words(s[1]) < 30

    def is_back(s):
        return (len(s[0]) <= TITLE_SHORT and bool(BACK_RE.search(s[0]))) or words(s[1]) < 30

    while len(secs) > 3 and is_front(secs[0]):
        t, b = secs.pop(0)
        front_parts.append(f"{t}\n\n{b}".strip())
    while len(secs) > 3 and is_back(secs[-1]):
        t, b = secs.pop()
        back_parts.insert(0, f"{t}\n\n{b}".strip())
    return "\n\n".join(front_parts).strip(), secs, "\n\n".join(back_parts).strip()


# ---------------------------------------------------------------------------------------------- zip / xml safety
def _open_zip(path: Path, what: str) -> zipfile.ZipFile:
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise BookReadError(f"That is not a valid {what} file ({e}).") from e
    infos = z.infolist()
    if len(infos) > MAX_MEMBERS:
        raise BookReadError(f"That {what} file has too many parts ({len(infos)}).")
    return z


def _member(z: zipfile.ZipFile, name: str) -> bytes:
    try:
        info = z.getinfo(name)
    except KeyError as e:
        raise BookReadError(f"The file is missing {name}.") from e
    if info.file_size > MAX_MEMBER:
        raise BookReadError(f"{name} is too large to read ({info.file_size // 2**20} MB).")
    with z.open(info) as f:
        return f.read(MAX_MEMBER + 1)


def _safe_xml(data: bytes) -> ET.Element:
    """Parse XML from an untrusted file."""
    if b"<!ENTITY" in data.upper():          # entity-expansion ("billion laughs") attacks need an entity declaration; a plain DOCTYPE is harmless
        raise BookReadError("The file contains XML entity declarations, which are not accepted.")
    try:
        return ET.fromstring(data)  # noqa: S314  (entity declarations were refused above)
    except ET.ParseError as e:
        raise BookReadError(f"The file has damaged XML ({e}).") from e


# ---------------------------------------------------------------------------------------------- plain text, HTML
def read_text_file(path: Path) -> BookText:
    raw = decode(path.read_bytes())
    pages = [p for p in raw.split("\f") if p.strip()] or [raw]
    if len(raw.split()) < 5:
        raise BookReadError("That text is too short to use: write or paste at least a few words.")
    return BookText("text", pages)


def read_html(path: Path) -> BookText:
    blocks = html_blocks(path.read_bytes())
    text = blocks_text(blocks)
    if words(text) < 5:
        raise BookReadError("That web page has no readable text.")
    book = BookText("html", [text])
    found = sections_from_blocks(blocks)
    if found:
        book.front, book.sections, book.back = trim_matter(found[1], found[0])
    return book


# ---------------------------------------------------------------------------------------------- DOCX
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def read_docx(path: Path) -> BookText:
    z = _open_zip(path, "Word (.docx)")
    root = _safe_xml(_member(z, "word/document.xml"))
    blocks: list[Block] = []
    for p in root.iter(_W + "p"):
        parts = []
        for el in p.iter():
            if el.tag == _W + "t" and el.text:
                parts.append(el.text)
            elif el.tag in (_W + "tab", _W + "br"):
                parts.append(" ")
        text = re.sub(r"\s+", " ", "".join(parts)).strip()
        if not text:
            continue
        style = p.find(f"{_W}pPr/{_W}pStyle")
        sid = (style.get(_W + "val") if style is not None else "") or ""
        m = HEADING_RE.match(sid.replace(" ", "").replace("-", ""))
        if m:
            level = int(m.group(1)) if m.group(1) else 1
            blocks.append(Block(min(max(level, 1), 6), text))
        else:
            blocks.append(Block(0, text))
    if words(blocks_text(blocks)) < 5:
        raise BookReadError("That Word document has no readable text.")
    book = BookText("docx", [blocks_text(blocks)])
    found = sections_from_blocks(blocks)
    if found:
        book.front, book.sections, book.back = trim_matter(found[1], found[0])
    return book


# ---------------------------------------------------------------------------------------------- ODT (OpenDocument text)
_TEXT_NS = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


def read_odt(path: Path) -> BookText:
    z = _open_zip(path, "OpenDocument (.odt)")
    root = _safe_xml(_member(z, "content.xml"))
    blocks: list[Block] = []
    for el in root.iter():
        if el.tag not in (_TEXT_NS + "p", _TEXT_NS + "h"):
            continue
        text = re.sub(r"\s+", " ", "".join(el.itertext())).strip()
        if not text:
            continue
        level = int(el.get(_TEXT_NS + "outline-level") or 1) if el.tag == _TEXT_NS + "h" else 0
        blocks.append(Block(min(max(level, 0), 6), text))
    if words(blocks_text(blocks)) < 5:
        raise BookReadError("That OpenDocument file has no readable text.")
    book = BookText("odt", [blocks_text(blocks)])
    found = sections_from_blocks(blocks)
    if found:
        book.front, book.sections, book.back = trim_matter(found[1], found[0])
    return book


# ---------------------------------------------------------------------------------------------- RTF
_RTF_SKIP = {"fonttbl", "colortbl", "stylesheet", "info", "pict", "object", "header", "footer", "headerl", "headerr", "footerl", "footerr",
             "listtable", "listoverridetable", "rsidtbl", "generator", "xmlnstbl", "themedata", "colorschememapping", "datastore", "latentstyles"}

_RTF_CTRL = re.compile(r"\\(?:([a-zA-Z]+)(-?\d+)? ?|'([0-9a-fA-F]{2})|(.))", re.S)


def rtf_to_text(data: str) -> str:
    """Plain text from RTF: paragraphs kept, formatting, font tables, pictures and other hidden groups dropped; hex (backslash-quote-hh) and unicode (backslash-uN) characters decoded."""
    out: list[str] = []
    stack: list[bool] = []
    skip = False
    i, n = 0, len(data)
    uc_skip = 0
    while i < n:
        c = data[i]
        if c == "{":
            stack.append(skip)
            i += 1
        elif c == "}":
            skip = stack.pop() if stack else False
            i += 1
        elif c == "\\":
            m = _RTF_CTRL.match(data, i)
            if not m:
                break
            i = m.end()
            word, arg, hexch, sym = m.groups()
            if hexch:
                if not skip:
                    out.append(bytes([int(hexch, 16)]).decode("cp1252", errors="replace"))
            elif sym:
                if sym == "*":
                    skip = True
                elif not skip and sym in "\\{}":
                    out.append(sym)
                elif not skip and sym == "~":
                    out.append(" ")
            elif word in _RTF_SKIP:
                skip = True
            elif not skip:
                if word in ("par", "line", "sect", "page"):
                    out.append("\n\n" if word != "line" else "\n")
                elif word == "tab":
                    out.append("\t")
                elif word == "u" and arg:
                    code = int(arg)
                    out.append(chr(code + 65536 if code < 0 else code))
                    uc_skip = 1                                # the plain-text stand-in that follows (usually "?")
        else:
            if uc_skip:
                uc_skip -= 1
            elif not skip and c not in "\r\n":
                out.append(c)
            i += 1
    text = "".join(out)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+\n", "\n", text)).strip()


def read_rtf(path: Path) -> BookText:
    raw = path.read_bytes()
    if not raw.lstrip().startswith(b"{\\rtf"):
        raise BookReadError("That is not an RTF file.")
    text = rtf_to_text(raw.decode("latin-1"))
    if words(text) < 5:
        raise BookReadError("That RTF file has no readable text.")
    return BookText("rtf", [text])


# ---------------------------------------------------------------------------------------------- EPUB
def _epub_spine(z: zipfile.ZipFile) -> list[str]:
    container = _safe_xml(_member(z, "META-INF/container.xml"))
    rootfile = next((e.get("full-path") for e in container.iter() if e.tag.endswith("rootfile") and e.get("full-path")), None)
    if not rootfile:
        raise BookReadError("The EPUB has no package file.")
    opf = _safe_xml(_member(z, rootfile))
    base = posixpath.dirname(rootfile)
    manifest = {e.get("id"): (e.get("href"), e.get("media-type", "")) for e in opf.iter() if e.tag.endswith("}item") or e.tag == "item"}
    out = []
    for e in opf.iter():
        if not (e.tag.endswith("itemref") and e.get("idref") in manifest):
            continue
        href, media = manifest[e.get("idref")]
        if href and ("html" in media or href.lower().endswith(HTML_EXTS)):
            out.append(posixpath.normpath(posixpath.join(base, unquote(href.split("#")[0]))))
    return out


def read_epub(path: Path) -> BookText:
    z = _open_zip(path, "EPUB")
    names = set(z.namelist())
    docs: list[tuple[str, list[Block]]] = []
    for name in _epub_spine(z):
        if name in names:
            blocks = html_blocks(_member(z, name))
            if blocks:
                title = next((b.text for b in blocks if 0 < b.level <= 3), "")
                docs.append((title, blocks))
    if not docs:
        raise BookReadError("The EPUB has no readable text.")
    allblocks = [b for _, bl in docs for b in bl]
    book = BookText("epub", [blocks_text(allblocks)])
    if words(book.pages[0]) < 5:
        raise BookReadError("The EPUB has no readable text.")
    if len(docs) >= 3:                                         # one file per chapter is the usual EPUB shape
        secs = []
        for n, (title, blocks) in enumerate(docs, start=1):
            body = blocks_text([b for b in blocks if b.text != title or b.level == 0] if title else blocks)
            secs.append((title or f"Section {n}", body))
        book.front, book.sections, book.back = trim_matter(secs)
    else:                                                      # a single-file EPUB: split on its headings
        found = sections_from_blocks(allblocks)
        if found:
            book.front, book.sections, book.back = trim_matter(found[1], found[0])
    return book


# ---------------------------------------------------------------------------------------------- OCR
OcrFn = Callable[[object], str]            # PIL image -> text


def _tesseract_engine(exe: str) -> OcrFn:
    import os
    lang = os.environ.get("STUDIO_OCR_LANG", "eng")
    if not re.fullmatch(r"[A-Za-z_+]{2,30}", lang):
        lang = "eng"

    def run(img) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "page.png"
            img.save(png)
            try:
                res = subprocess.run([exe, str(png), "stdout", "-l", lang, "--psm", "3"], capture_output=True, text=True, timeout=300)
            except subprocess.TimeoutExpired as e:
                raise BookReadError("tesseract took more than 5 minutes on one page.") from e
        if res.returncode != 0:
            raise BookReadError(f"tesseract failed: {res.stderr.strip()[:200]}")
        return res.stdout
    return run


def _rapidocr_engine() -> OcrFn | None:
    try:
        from rapidocr import RapidOCR
    except ImportError:
        return None
    engine = RapidOCR(params={"Global.log_level": "warning"})      # otherwise it logs a few lines per model at start-up

    def run(img) -> str:
        import numpy as np
        out = engine(np.array(img.convert("RGB")))
        txts = list(getattr(out, "txts", None) or [])
        boxes = getattr(out, "boxes", None)
        if not txts:
            return ""
        if boxes is None or len(boxes) != len(txts):
            return "\n".join(txts)
        items = []                                      # (y centre, height, x left, text)
        for t, b in zip(txts, boxes, strict=True):
            ys = [float(p[1]) for p in b]
            xs = [float(p[0]) for p in b]
            items.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), t))
        items.sort()
        lines: list[list[tuple[float, str]]] = []
        last_y, last_h = None, 1.0
        for y, h, x, t in items:
            if last_y is not None and abs(y - last_y) < 0.6 * max(last_h, h):
                lines[-1].append((x, t))
            else:
                lines.append([(x, t)])
            last_y, last_h = y, h
        return "\n".join(" ".join(t for _, t in sorted(ln)) for ln in lines)
    return run


def ocr_engine_name() -> str | None:
    """"tesseract", "rapidocr" or None: the engine read_pdf would use right now."""
    if shutil.which("tesseract"):
        return "tesseract"
    try:
        import importlib.util
        if importlib.util.find_spec("rapidocr") and importlib.util.find_spec("onnxruntime"):
            return "rapidocr"
    except (ImportError, ValueError):
        pass
    return None


def find_ocr_engine() -> OcrFn | None:
    exe = shutil.which("tesseract")
    if exe:
        return _tesseract_engine(exe)
    return _rapidocr_engine()


def page_images(page, min_side: int = 200) -> list:
    """The pictures on a PDF page (a scan is normally one big picture), as PIL images, skipping tiny ones (logos, rules)."""
    from pypdf.errors import PyPdfError
    _pil_open(b"")                                          # raises BookReadError at once when Pillow is missing, instead of hiding it below
    out = []
    with contextlib.suppress(PyPdfError, ValueError, OSError, KeyError, NotImplementedError, TypeError):    # a damaged picture must not stop the whole book
        for im in page.images:
            pil = _pil_open(im.data)
            if pil is not None and min(pil.size) >= min_side:
                out.append(pil)
    return out


def _pil_open(data: bytes):
    try:
        from PIL import Image
    except ImportError as e:
        raise BookReadError("Reading scanned pages needs the Pillow package (pip install pillow).") from e
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
        return im.convert("RGB") if im.mode not in ("RGB", "L") else im
    except Exception:                                       # noqa: BLE001
        return None


# ---------------------------------------------------------------------------------------------- PDF
def looks_scanned(pages: list[str]) -> bool:
    chars = sum(len(p) for p in pages)
    return chars < 200 * max(len(pages), 1) * 0.2 or chars < 2000


def ocr_packages(path: Path) -> list[str]:
    """Extra Python packages `uv run --with` should add so this book can be read: Pillow always for PDFs, and the OCR packages when the PDF is a
    scan and no tesseract program is installed. Looks at the first pages only."""
    path = Path(path)
    if path.suffix.lower() != ".pdf":
        return []
    pkgs = ["pillow"]
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        sample = [(p.extract_text() or "") for p in reader.pages[:8]]
    except Exception:                                       # unreadable here: let the ingest script report it  # noqa: BLE001
        return pkgs
    if sample and sum(len(s.strip()) for s in sample) < MIN_PAGE_CHARS * len(sample) and not shutil.which("tesseract"):
        pkgs += ["rapidocr", "onnxruntime"]
    return pkgs


def read_pdf(path: Path, ocr: bool = True, engine: OcrFn | None = None, progress: Callable[[str], None] = lambda s: None) -> BookText:
    from pypdf import PdfReader
    try:
        reader = PdfReader(path)
        pages = [(p.extract_text() or "") for p in reader.pages]
    except Exception as e:                                  # noqa: BLE001
        raise BookReadError(f"That PDF could not be read ({e}).") from e
    book = BookText("pdf", pages)
    if not looks_scanned(pages):
        return book
    empty = [i for i, t in enumerate(pages) if len(t.strip()) < MIN_PAGE_CHARS]
    chars = sum(len(p) for p in pages)
    scanned_msg = (f"Almost no text was extracted ({chars} characters from {len(pages)} pages). This looks like a scanned PDF")
    if not ocr:
        raise BookReadError(scanned_msg + " and OCR is switched off.")
    eng = engine or find_ocr_engine()
    if eng is None:
        raise BookReadError(scanned_msg + ", and no OCR engine is installed. Install one of: the tesseract program (brew install tesseract), "
                            "or the Python packages rapidocr and onnxruntime (the Studio adds them for you when it runs this step).")
    done = 0
    for k, i in enumerate(empty, start=1):
        imgs = page_images(reader.pages[i])
        if imgs:
            try:
                pages[i] = "\n".join(eng(im) for im in imgs)
            except BookReadError:
                raise
            except Exception as e:                          # noqa: BLE001  (an engine failure is reported as a reason, not a traceback)
                raise BookReadError(f"OCR failed on page {i + 1}: {e}") from e
            done += 1
        if k % 10 == 0 or k == len(empty):
            progress(f"OCR: page {k}/{len(empty)} of the pages without text")
    book.pages, book.ocr_pages = pages, done
    if not done:
        raise BookReadError(scanned_msg + ", and its pages hold no pictures that could be read with OCR.")
    if words("\n".join(pages)) < OCR_TARGET_WORDS * 10:
        raise BookReadError(scanned_msg + "; OCR found almost no words (are the scans too faint or too small?).")
    book.notes.append(f"{done} of {len(pages)} pages had no text and were read with OCR; check the text for recognition mistakes.")
    return book


# ---------------------------------------------------------------------------------------------- entry point
def read_book(path: Path | str, ocr: bool = True, engine: OcrFn | None = None, progress: Callable[[str], None] = lambda s: None) -> BookText:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return read_pdf(path, ocr=ocr, engine=engine, progress=progress)
    if ext in TEXT_EXTS:
        return read_text_file(path)
    if ext == ".epub":
        return read_epub(path)
    if ext == ".docx":
        return read_docx(path)
    if ext in HTML_EXTS:
        return read_html(path)
    if ext == ".odt":
        return read_odt(path)
    if ext == ".rtf":
        return read_rtf(path)
    raise BookReadError(f"Cannot read {ext or 'this'} files; use PDF, EPUB, DOCX, ODT, RTF, HTML or plain text.")
