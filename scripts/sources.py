"""Story sources (BOOK_TO_SCREEN_BUILD.md Section 4, milestone M2): anything the crew can turn into a story.

Every source becomes a SourceDocument {kind, title, text, images[], media[], metadata, rights_note}:

  document    .txt .md .docx .pdf .epub .rtf .odt .html   (book_formats.py; chapters from the file's own divisions)
  idea        free text, from one line to several pages
  picture     .jpg .png .webp; the Story Analyst describes characters, setting, mood and an implied story (describe()); the
              pictures stay as visual references for the Character Designer and Production Designer
  comic       pictures with text (a comic or manga page); the Story Analyst reads the panels in order
  website     an http(s) address: fetched on the Studio's computer with a timeout and a size limit, robots.txt respected,
              private and internal addresses refused (no SSRF), the main text kept and its pictures collected
  screenplay  .fountain .fdx (or a PDF / text laid out as a screenplay): parsed straight into scenes; Read it in then only critiques
              and polishes it

A project keeps its sources in projects/books/<book>/sources/: index.json (the list, each with its rights tick and when it was given) and
<id>/ (the original file, text.txt, pictures, scenes.json). Several sources can be mixed in one project; merged_text() labels every
part with the source it came from, so the Development Executive can note where each element came from.
Limits: 20 MB per document, 2 GB per video, 400,000 words in total. A source is only added with the rights box ticked.
"""
from __future__ import annotations

import html
import http.client
import ipaddress
import json
import re
import shutil
import socket
import ssl
import threading
import time
import urllib.robotparser
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import book_formats
from book_formats import BookReadError, _safe_xml

MAX_DOC = 20 * 2**20
MAX_VIDEO = 2 * 2**30
MAX_WORDS = 400_000
MAX_PAGE = 20 * 2**20             # a web page
MAX_PAGE_IMAGES = 8
MAX_IMAGE = 8 * 2**20
FETCH_TIMEOUT = 20
USER_AGENT = "PistachiosStudio/1.0 (+local story importer)"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
SCREENPLAY_EXTS = (".fountain", ".fdx")
MEDIA_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".mp3", ".wav", ".m4a", ".flac", ".ogg")
KINDS = ("document", "idea", "picture", "comic", "website", "screenplay", "media")
ID_RE = re.compile(r"^s\d{3}$")
_LOCK = threading.RLock()                 # two adds at once must not get the same id (the server answers requests in threads)


class SourceError(ValueError):
    """A source cannot be added as asked; the message says what to do (shown to the person as it is)."""


@dataclass
class SourceDocument:
    kind: str
    title: str
    text: str = ""
    images: list[str] = field(default_factory=list)           # paths relative to the project folder
    media: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    rights_note: str = ""


def words(text: str) -> int:
    return len(text.split())


# ---------------------------------------------------------------------------------------------- the project's list of sources
def folder(pdir: Path) -> Path:
    return pdir / "sources"


def load_index(pdir: Path) -> list[dict]:
    try:
        data = json.loads((folder(pdir) / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [s for s in data.get("sources", []) if isinstance(s, dict) and ID_RE.match(str(s.get("id", "")))] if isinstance(data, dict) else []


def _save_index(pdir: Path, items: list[dict]) -> None:
    folder(pdir).mkdir(parents=True, exist_ok=True)
    tmp = folder(pdir) / "index.json.tmp"
    tmp.write_text(json.dumps({"sources": items}, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(folder(pdir) / "index.json")


def _next_id(items: list[dict]) -> str:
    used = {int(s["id"][1:]) for s in items}
    return f"s{(max(used) + 1 if used else 1):03d}"


def _rights(agreed: bool, note: str = "") -> dict:
    if agreed is not True:
        raise SourceError("Tick the box to confirm you have the right to use this source.")
    return {"agreed": True, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "note": note.strip()[:500]}


def total_words(pdir: Path) -> int:
    return sum(int(s.get("words", 0)) for s in load_index(pdir))


def store(pdir: Path, doc: SourceDocument, agreed: bool, files: list[Path] | None = None) -> dict:
    """Add a source to the project (with its rights tick and time) and return its index entry. Files are moved into its folder."""
    with _LOCK:
        return _store(pdir, doc, agreed, files)


def _store(pdir: Path, doc: SourceDocument, agreed: bool, files: list[Path] | None) -> dict:
    rights = _rights(agreed, doc.rights_note)
    if total_words(pdir) + words(doc.text) > MAX_WORDS:
        raise SourceError(f"All the sources together may hold at most {MAX_WORDS:,} words; this one would go over. Remove a source or use a shorter part.")
    items = load_index(pdir)
    sid = _next_id(items)
    d = folder(pdir) / sid
    d.mkdir(parents=True, exist_ok=False)
    kept: list[str] = []
    for f in files or []:
        dest = d / f.name
        shutil.move(str(f), dest)
        kept.append(dest.relative_to(pdir).as_posix())
    doc.images = [p for p in kept if p.lower().endswith(IMAGE_EXTS)] + doc.images
    doc.media = [p for p in kept if p.lower().endswith(MEDIA_EXTS)] + doc.media
    (d / "text.txt").write_text(doc.text, encoding="utf-8")
    if doc.metadata.get("scenes"):
        (d / "scenes.json").write_text(json.dumps(doc.metadata.pop("scenes"), indent=1, ensure_ascii=False), encoding="utf-8")
        doc.metadata["has_scenes"] = True
    if doc.metadata.get("section_text"):                       # a document's own chapters: kept beside the text, not in the index
        (d / "sections.json").write_text(json.dumps(doc.metadata.pop("section_text"), ensure_ascii=False), encoding="utf-8")
    entry = {"id": sid, "kind": doc.kind, "title": doc.title[:120], "words": words(doc.text), "images": doc.images, "media": doc.media,
             "metadata": doc.metadata, "rights": rights, "added": rights["at"], "files": kept, "described": doc.kind not in ("picture", "comic")}
    items.append(entry)
    _save_index(pdir, items)
    return entry


def get(pdir: Path, sid: str) -> dict:
    for s in load_index(pdir):
        if s["id"] == sid:
            return s
    raise SourceError(f"no source {sid}")


def document(pdir: Path, sid: str) -> SourceDocument:
    s = get(pdir, sid)
    d = folder(pdir) / sid
    meta = dict(s.get("metadata", {}))
    if (d / "scenes.json").is_file():
        meta["scenes"] = json.loads((d / "scenes.json").read_text(encoding="utf-8"))
    if (d / "sections.json").is_file():
        meta["section_text"] = json.loads((d / "sections.json").read_text(encoding="utf-8"))
    text = (d / "text.txt").read_text(encoding="utf-8") if (d / "text.txt").is_file() else ""
    return SourceDocument(s["kind"], s["title"], text, list(s.get("images", [])), list(s.get("media", [])), meta, s.get("rights", {}).get("note", ""))


def remove(pdir: Path, sid: str) -> None:
    with _LOCK:
        _remove(pdir, sid)


def _remove(pdir: Path, sid: str) -> None:
    items = load_index(pdir)
    keep = [s for s in items if s["id"] != sid]
    if len(keep) == len(items):
        raise SourceError(f"no source {sid}")
    shutil.rmtree(folder(pdir) / sid, ignore_errors=True)
    _save_index(pdir, keep)


def set_text(pdir: Path, sid: str, text: str, described: bool = True, extra: dict | None = None) -> dict:
    items = load_index(pdir)
    for s in items:
        if s["id"] == sid:
            (folder(pdir) / sid / "text.txt").write_text(text, encoding="utf-8")
            s["words"], s["described"] = words(text), described
            s.setdefault("metadata", {}).update(extra or {})
            _save_index(pdir, items)
            return s
    raise SourceError(f"no source {sid}")


# ---------------------------------------------------------------------------------------------- adapters
def from_idea(text: str, title: str = "") -> SourceDocument:
    text = text.strip()
    if words(text) < 1:
        raise SourceError("Write the idea first: one line is enough.")
    return SourceDocument("idea", title.strip() or " ".join(text.split()[:6]), text)


def looks_like_screenplay(text: str) -> bool:
    """Scene headings (INT. / EXT.) on their own lines, and enough of them for the length."""
    heads = len(re.findall(r"(?m)^\s*(?:\d+\s+)?(?:INT|EXT|INT\./EXT|I/E|EST)[\.\s]", text))
    return heads >= 3 and heads * 400 >= words(text) / 3


def from_document(path: Path, ocr: bool = True) -> SourceDocument:
    if path.stat().st_size > MAX_DOC:
        raise SourceError(f"{path.name} is larger than {MAX_DOC // 2**20} MB; split it or use a smaller file.")
    try:
        book = book_formats.read_book(path, ocr=ocr)
    except BookReadError as e:
        raise SourceError(str(e)) from e
    text = "\n\n".join(book.pages).strip()
    if looks_like_screenplay(text):
        return from_screenplay_text(text, path.stem)
    sections = [{"title": t[:80], "words": words(b)} for t, b in (book.sections or [])]
    meta = {"format": book.kind, "file": path.name, "sections": sections, "ocr_pages": book.ocr_pages, "notes": book.notes}
    if book.sections:
        meta["section_text"] = [b for _, b in book.sections]
    return SourceDocument("document", path.stem.replace("_", " "), text, metadata=meta)


def from_pictures(paths: list[Path], comic: bool = False, title: str = "") -> SourceDocument:
    if not paths:
        raise SourceError("Choose at least one picture.")
    for p in paths:
        if p.suffix.lower() not in IMAGE_EXTS:
            raise SourceError(f"{p.name}: pictures must be .jpg, .png or .webp")
        if p.stat().st_size > MAX_DOC:
            raise SourceError(f"{p.name} is larger than {MAX_DOC // 2**20} MB")
        head = p.read_bytes()[:12]
        if not (head.startswith(b"\xff\xd8") or head.startswith(b"\x89PNG") or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")):
            raise SourceError(f"{p.name} is not a picture")
    kind = "comic" if comic else "picture"
    return SourceDocument(kind, title.strip() or paths[0].stem.replace("_", " "), "", metadata={"pictures": len(paths)})


def from_media(path: Path) -> SourceDocument:
    """A video or audio file kept as a reference (transcription and shot detection come in M13)."""
    if path.stat().st_size > MAX_VIDEO:
        raise SourceError(f"{path.name} is larger than 2 GB")
    return SourceDocument("media", path.stem.replace("_", " "), "", metadata={"file": path.name, "transcribed": False})


# ---------------------------------------------------------------------------------------------- screenplays
_HEADING = re.compile(r"^(?:\d+\s+)?((?:INT|EXT|EST|INT\./EXT|INT/EXT|I/E)[\.\s].*?)(?:\s+\d+)?$", re.I)
_TRANSITION = re.compile(r"^[A-Z\s]+TO:$|^(?:FADE (?:IN|OUT)\.?|FADE TO BLACK\.?)$")
_CUE = re.compile(r"^(?:@)?([A-Z0-9][A-Z0-9 .'\-]{0,40}?)(\s*\((?:V\.O\.|O\.S\.|O\.C\.|CONT'D|CONTD|[A-Z.' ]+)\))*\s*\^?$")


def parse_fountain(text: str) -> list[dict]:
    """Fountain (and plain screenplay text) to scenes: [{heading, elements: [{type, text, character?}]}]. Types: action, character, dialogue,
    parenthetical, transition, note."""
    text = re.sub(r"/\*.*?\*/", "", text.replace("\r\n", "\n"), flags=re.S)          # boneyard
    lines = text.split("\n")
    if lines and re.match(r"^\s*Title\s*:", lines[0], re.I):                          # title page: up to the first blank line
        while lines and lines[0].strip():
            lines.pop(0)
    scenes: list[dict] = []
    cur: dict = {"heading": "", "elements": []}
    speaker = ""
    prev_blank = True
    for raw in lines:
        line = raw.strip()
        if not line:
            speaker, prev_blank = "", True
            continue
        forced_heading = line.startswith(".") and not line.startswith("..")
        m = _HEADING.match(line)
        if prev_blank and (forced_heading or m):
            if cur["heading"] or cur["elements"]:
                scenes.append(cur)
            cur = {"heading": (line[1:] if forced_heading else m.group(1) if m else line).strip().upper(), "elements": []}
            prev_blank = False
            continue
        if speaker:
            if line.startswith("(") and line.endswith(")"):
                cur["elements"].append({"type": "parenthetical", "text": line, "character": speaker})
            else:
                cur["elements"].append({"type": "dialogue", "text": line, "character": speaker})
        elif line.startswith("[[") and line.endswith("]]"):
            cur["elements"].append({"type": "note", "text": line[2:-2].strip()})
        elif (prev_blank and _TRANSITION.match(line)) or line.startswith(">") and not line.endswith("<"):
            cur["elements"].append({"type": "transition", "text": line.lstrip("> ").strip()})
        elif prev_blank and (line.startswith("@") or (_CUE.match(line) and line.upper() == line and any(c.isalpha() for c in line))):
            speaker = re.sub(r"\s*\(.*\)\s*$", "", line.lstrip("@").rstrip("^ ")).strip()
            cur["elements"].append({"type": "character", "text": line.lstrip("@").rstrip("^ ").strip()})
        else:
            cur["elements"].append({"type": "action", "text": line.lstrip("!")})
        prev_blank = False
    if cur["heading"] or cur["elements"]:
        scenes.append(cur)
    return [s for s in scenes if s["heading"] or any(e["type"] != "note" for e in s["elements"])]


def parse_fdx(data: bytes) -> list[dict]:
    """Final Draft (.fdx) XML to the same scenes as parse_fountain."""
    try:
        root = _safe_xml(data)
    except BookReadError as e:
        raise SourceError(str(e)) from e
    kinds = {"scene heading": "heading", "action": "action", "character": "character", "dialogue": "dialogue", "parenthetical": "parenthetical",
             "transition": "transition", "shot": "action", "general": "action"}
    scenes: list[dict] = []
    cur: dict = {"heading": "", "elements": []}
    speaker = ""
    for p in root.iter("Paragraph"):
        kind = kinds.get((p.get("Type") or "").lower(), "action")
        text = re.sub(r"\s+", " ", "".join("".join(t.itertext()) for t in p.iter("Text"))).strip()
        if not text:
            continue
        if kind == "heading":
            if cur["heading"] or cur["elements"]:
                scenes.append(cur)
            cur, speaker = {"heading": text.upper(), "elements": []}, ""
            continue
        el = {"type": kind, "text": text}
        if kind == "character":
            speaker = re.sub(r"\s*\(.*\)\s*$", "", text).strip()
        elif kind in ("dialogue", "parenthetical"):
            el["character"] = speaker
        else:
            speaker = ""
        cur["elements"].append(el)
    if cur["heading"] or cur["elements"]:
        scenes.append(cur)
    return scenes


def scenes_to_text(scenes: list[dict]) -> str:
    """Screenplay text in the usual layout (headings, action, CHARACTER, dialogue)."""
    out = []
    for n, s in enumerate(scenes, 1):
        out.append(f"{n}  {s['heading']}" if s["heading"] else "")
        for e in s["elements"]:
            t = e["type"]
            out.append({"character": f"\t\t\t{e['text'].upper()}", "dialogue": f"\t\t{e['text']}", "parenthetical": f"\t\t  {e['text']}",
                        "transition": f"\t\t\t\t\t{e['text']}", "note": f"[[{e['text']}]]"}.get(t, e["text"]))
        out.append("")
    return "\n".join(out).strip() + "\n"


def from_screenplay_text(text: str, title: str) -> SourceDocument:
    scenes = parse_fountain(text)
    if not scenes:
        raise SourceError("No scenes were found: a screenplay needs scene headings such as INT. KITCHEN - NIGHT.")
    return SourceDocument("screenplay", title.replace("_", " "), scenes_to_text(scenes), metadata={"scenes": scenes, "scene_count": len(scenes)})


def from_screenplay(path: Path) -> SourceDocument:
    if path.stat().st_size > MAX_DOC:
        raise SourceError(f"{path.name} is larger than {MAX_DOC // 2**20} MB")
    if path.suffix.lower() == ".fdx":
        scenes = parse_fdx(path.read_bytes())
        if not scenes:
            raise SourceError("No scenes were found in that Final Draft file.")
        return SourceDocument("screenplay", path.stem.replace("_", " "), scenes_to_text(scenes), metadata={"scenes": scenes, "scene_count": len(scenes)})
    return from_screenplay_text(book_formats.decode(path.read_bytes()), path.stem)


def from_file(path: Path, comic: bool = False, ocr: bool = True) -> SourceDocument:
    ext = path.suffix.lower()
    if ext in SCREENPLAY_EXTS:
        return from_screenplay(path)
    if ext in IMAGE_EXTS:
        return from_pictures([path], comic=comic)
    if ext in MEDIA_EXTS:
        return from_media(path)
    if ext in book_formats.BOOK_EXTS:
        return from_document(path, ocr=ocr)
    raise SourceError(f"{path.name}: this kind of file cannot be used. Use a document ({', '.join(book_formats.BOOK_EXTS)}), "
                      f"a screenplay (.fountain, .fdx), pictures (.jpg, .png, .webp) or video / audio.")


ACCEPTED = (*book_formats.BOOK_EXTS, *SCREENPLAY_EXTS, *IMAGE_EXTS, *MEDIA_EXTS)


# ---------------------------------------------------------------------------------------------- websites (SSRF-safe fetch)
def _public_ips(host: str, port: int) -> list[str]:
    """Every address the name points to; refused if ANY of them is private, loopback, link-local, multicast or reserved."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise SourceError(f"{host} could not be found ({e.strerror or e}).") from e
    ips = sorted({str(i[4][0]) for i in infos})
    for ip in ips:
        a = ipaddress.ip_address(ip.split("%")[0])
        mapped = getattr(a, "ipv4_mapped", None)
        if mapped is not None:
            a = mapped
        if not a.is_global or a.is_multicast or a.is_reserved:
            raise SourceError(f"{host} points to a private or internal address ({ip}); only public websites can be read.")
    if not ips:
        raise SourceError(f"{host} could not be found.")
    return ips


class _PinnedHTTPS(http.client.HTTPSConnection):
    """HTTPS to an address that was checked, with the certificate checked for the real name (no DNS rebinding in between)."""

    def __init__(self, host: str, ip: str, port: int, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self) -> None:
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)  # type: ignore[attr-defined]


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host: str, ip: str, port: int, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


def check_url(url: str) -> tuple[str, str, int, str]:
    """(scheme, host, port, path+query) of an http(s) address, or SourceError."""
    u = urlsplit(url.strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise SourceError("Only http:// and https:// web addresses can be read.")
    if u.username or u.password:
        raise SourceError("Web addresses with a user name or password are not used.")
    port = u.port or (443 if u.scheme == "https" else 80)
    return u.scheme, u.hostname, port, (u.path or "/") + (f"?{u.query}" if u.query else "")


def safe_get(url: str, limit: int = MAX_PAGE, timeout: float = FETCH_TIMEOUT, redirects: int = 5) -> tuple[str, str, bytes]:
    """GET a public web address: (final url, content type, body). Redirects are followed (each one checked again), at most `limit` bytes."""
    for _ in range(redirects + 1):
        scheme, host, port, path = check_url(url)
        ip = _public_ips(host, port)[0]
        conn: http.client.HTTPConnection = (_PinnedHTTPS if scheme == "https" else _PinnedHTTP)(host, ip, port, timeout)
        try:
            conn.request("GET", path, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,image/*;q=0.8,*/*;q=0.5"})
            r = conn.getresponse()
            if r.status in (301, 302, 303, 307, 308) and r.getheader("Location"):
                url = urljoin(url, r.getheader("Location") or "")
                continue
            if r.status != 200:
                raise SourceError(f"The website answered {r.status} {r.reason}.")
            if int(r.getheader("Content-Length") or 0) > limit:
                raise SourceError(f"That page is larger than {limit // 2**20} MB.")
            body = r.read(limit + 1)
            if len(body) > limit:
                raise SourceError(f"That page is larger than {limit // 2**20} MB.")
            return url, (r.getheader("Content-Type") or "").lower(), body
        except (OSError, http.client.HTTPException) as e:
            raise SourceError(f"The website could not be read ({e}).") from e
        finally:
            conn.close()
    raise SourceError("The website redirected too many times.")


def robots_allow(url: str, get: Callable[..., tuple[str, str, bytes]] = safe_get) -> bool:
    scheme, host, port, _ = check_url(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        _, _, body = get(f"{scheme}://{host}:{port}/robots.txt", limit=512 * 1024)
    except SourceError:
        return True                                      # no robots.txt (or it cannot be read): allowed, as for browsers and crawlers
    rp.parse(body.decode("utf-8", errors="replace").splitlines())
    return rp.can_fetch(USER_AGENT.split("/")[0], url)


class _Article(HTMLParser):
    """Readability-style main text: the paragraphs inside <article> / <main> when the page has them, else every paragraph block that is
    not navigation, header, footer, a form or an aside. Also the page title and the pictures (src, alt)."""
    SKIP = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg", "button", "select", "template", "iframe"}
    BLOCK = {"p", "div", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "td", "figcaption", "section", "br"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.og_title = ""
        self.images: list[tuple[str, str]] = []
        self.main: list[str] = []
        self.other: list[str] = []
        self._skip = 0
        self._in_main = 0
        self._in_title = False
        self._buf: list[str] = []

    def _flush(self) -> None:
        t = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        self._buf = []
        if t:
            (self.main if self._in_main else self.other).append(t)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta" and (a.get("property") or "").lower() == "og:title":
            self.og_title = a.get("content") or ""
        elif tag in self.SKIP:
            self._skip += 1
        elif tag in ("article", "main"):
            self._flush()
            self._in_main += 1
        elif tag == "img" and not self._skip and a.get("src"):
            self.images.append((a.get("src") or "", a.get("alt") or ""))
        elif tag in self.BLOCK:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in ("article", "main"):
            self._flush()
            self._in_main = max(0, self._in_main - 1)
        elif tag in self.BLOCK:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip:
            self._buf.append(data)

    def text(self) -> str:
        self._flush()
        main = [b for b in self.main if words(b) >= 3]
        if words(" ".join(main)) >= 50:
            return "\n\n".join(main)
        return "\n\n".join(b for b in self.other + self.main if words(b) >= 8 or b.endswith((".", "!", "?", '"')))


def extract_article(page: str, base_url: str) -> tuple[str, str, list[tuple[str, str]]]:
    """(title, main text, [(absolute picture address, alt text)]) from a web page."""
    p = _Article()
    p.feed(page)
    p.close()
    images, seen = [], set()
    for src, alt in p.images:
        absu = urljoin(base_url, html.unescape(src))
        if urlsplit(absu).scheme in ("http", "https") and absu not in seen and not re.search(r"(?i)(sprite|pixel|logo|icon|avatar|spacer)", absu):
            seen.add(absu)
            images.append((absu, alt))
    return (p.og_title or p.title).strip(), p.text(), images


def from_url(url: str, dest: Path, get: Callable[..., tuple[str, str, bytes]] = safe_get) -> tuple[SourceDocument, list[Path]]:
    """Read a public web page: its main text and up to MAX_PAGE_IMAGES of its pictures (saved into dest). Returns (document, picture files)."""
    if not robots_allow(url, get):
        raise SourceError("That website asks programs not to read this page (robots.txt), so the Studio does not.")
    final, ctype, body = get(url)
    if "html" not in ctype and not body.lstrip()[:200].lower().startswith((b"<!doctype html", b"<html")):
        raise SourceError(f"That address is not a web page ({ctype or 'unknown type'}).")
    title, text, imgs = extract_article(book_formats.decode(body), final)
    if words(text) < 20:
        raise SourceError("No readable story text was found on that page.")
    dest.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    for n, (src, _alt) in enumerate(imgs[: MAX_PAGE_IMAGES * 2]):
        if len(files) >= MAX_PAGE_IMAGES:
            break
        try:
            _, ict, data = get(src, limit=MAX_IMAGE)
        except SourceError:
            continue
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(ict.split(";")[0].strip())
        if ext and len(data) > 2000:
            f = dest / f"web-{n + 1:02d}{ext}"
            f.write_bytes(data)
            files.append(f)
    meta = {"url": final, "fetched": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "image_urls": [i[0] for i in imgs[:40]]}
    return SourceDocument("website", title or urlsplit(final).hostname or final, text, metadata=meta), files


# ---------------------------------------------------------------------------------------------- pictures: the Story Analyst looks at them
def _check_description(d: dict) -> None:
    if not isinstance(d, dict) or not str(d.get("story", "")).strip():
        raise ValueError('reply with a JSON object that has at least "story" (and "characters", "setting", "mood")')


def _check_panels(d: dict) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("panels"), list) or not d["panels"]:
        raise ValueError('reply with a JSON object {"panels": [{"n", "text", "action"}], "story": "..."}')


def describe(pdir: Path, sid: str, llm: Callable[..., dict], system: Callable[..., object], engine: str = "claude") -> dict:
    """Pictures: characters, setting, mood and an implied story. Comic pages: the panels in reading order (text and action), then the story.
    `llm` is bookkit.llm_json, `system` crew.system (so the Story Analyst's role text is used)."""
    s = get(pdir, sid)
    if s["kind"] not in ("picture", "comic"):
        raise SourceError("only pictures and comic pages are described")
    parts: list[str] = []
    found: dict[str, list] = {"characters": [], "settings": []}
    for n, rel in enumerate(s["images"], 1):
        img = pdir / rel
        if s["kind"] == "comic":
            prompt = (f"This is page {n} of {len(s['images'])} of a comic. Read the panels in reading order. For each panel give its number, "
                      'the words in it (speech, captions, sound effects) and what happens. Then "story": what happens on this page in plain prose. '
                      'Reply as JSON: {"panels": [{"n": 1, "text": "...", "action": "..."}], "story": "...", "characters": [{"name": "...", "look": "..."}]}')
            d = llm(prompt, system("story_analyst", pdir, "sources: read a comic page"), engine=engine, validate=_check_panels, image=str(img))
            lines = [f"Panel {p.get('n', i + 1)}: {p.get('action', '')}" + (f' — "{p.get("text")}"' if p.get("text") else "") for i, p in enumerate(d["panels"])]
            parts.append(f"Page {n}\n" + "\n".join(lines) + f"\n\n{d.get('story', '')}")
        else:
            prompt = ("Look at this picture as a story analyst. Describe the characters (name them if the picture does, else give each a short label; "
                      "their look), the setting, the mood, and the story the picture implies: what happened just before, what is happening, "
                      'what might happen next. Reply as JSON: {"characters": [{"name": "...", "look": "..."}], "setting": "...", "mood": "...", "story": "..."}')
            d = llm(prompt, system("story_analyst", pdir, "sources: describe a picture"), engine=engine, validate=_check_description, image=str(img))
            parts.append(f"Picture {n}. Setting: {d.get('setting', '')}. Mood: {d.get('mood', '')}.\n{d.get('story', '')}")
            found["settings"].append(d.get("setting", ""))
        found["characters"] += [c for c in d.get("characters", []) if isinstance(c, dict)]
    return set_text(pdir, sid, "\n\n".join(parts), described=True, extra={"characters": found["characters"][:40], "settings": found["settings"][:40]})


# ---------------------------------------------------------------------------------------------- using the sources
def merged_text(pdir: Path) -> str:
    """All sources in one text, each part labelled with where it came from (for the Development Executive and the Story Analyst)."""
    out = []
    for s in load_index(pdir):
        doc = document(pdir, s["id"])
        if doc.text.strip():
            out.append(f"=== SOURCE {s['id']} ({s['kind']}: {s['title']}) ===\n{doc.text.strip()}")
    return "\n\n".join(out)


def chunks(text: str, max_tokens: int = 15000, overlap_tokens: int = 500) -> list[str]:
    """Pieces of about max_tokens (1 word ~ 1.33 tokens), cut at paragraph ends, each starting with the last ~overlap_tokens of the one before."""
    max_w, over_w = max(50, int(max_tokens / 1.33)), int(overlap_tokens / 1.33)
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    cur: list[str] = []
    n = 0
    for p in paras:
        pw = words(p)
        if cur and n + pw > max_w:
            out.append("\n\n".join(cur))
            tail = " ".join(" ".join(cur).split()[-over_w:]) if over_w else ""
            cur, n = ([tail] if tail else []), words(tail)
        if pw > max_w:                                   # one huge paragraph: cut it by words
            ws = p.split()
            for i in range(0, len(ws), max_w - over_w):
                out.append(" ".join(ws[i:i + max_w]))
            cur, n = [], 0
            continue
        cur.append(p)
        n += pw
    if cur and (not out or words("\n\n".join(cur)) > over_w):
        out.append("\n\n".join(cur))
    return out


def chapters_from_sources(pdir: Path) -> list[tuple[str, str]]:
    """(title, body) chapters for the Studio's chapter step: a document's own sections, one chapter per other source, one per screenplay scene."""
    out: list[tuple[str, str]] = []
    for s in load_index(pdir):
        doc = document(pdir, s["id"])
        if s["kind"] == "document" and doc.metadata.get("section_text"):
            out += [(t["title"], b) for t, b in zip(doc.metadata["sections"], doc.metadata["section_text"], strict=False)]
        elif s["kind"] == "screenplay" and doc.metadata.get("scenes"):
            for sc in doc.metadata["scenes"]:
                body = scenes_to_text([sc])
                out.append((sc["heading"][:80] or s["title"], body))
        elif s["kind"] == "document":
            out += [(f"{s['title']} part {i + 1}", c) for i, c in enumerate(chunks(doc.text, 3300, 0))]
        elif doc.text.strip():
            out.append((s["title"][:80], doc.text))
    return out


def write_chapters(pdir: Path) -> int:
    """Make chapters/ and chapters.json from the sources (as book_ingest.py does for one book file). Returns the number of chapters."""
    chs = chapters_from_sources(pdir)
    if not chs:
        raise SourceError("Add a source with some text first (pictures need their description: press Describe).")
    cdir = pdir / "chapters"
    shutil.rmtree(cdir, ignore_errors=True)
    cdir.mkdir(parents=True)
    index = []
    for n, (title, body) in enumerate(chs, 1):
        (cdir / f"chapter-{n:03d}.txt").write_text(body.strip(), encoding="utf-8")
        index.append({"n": n, "title": title[:80], "words": words(body), "chars": len(body)})
    (pdir / "source_text.txt").write_text(merged_text(pdir), encoding="utf-8")
    (pdir / "chapters.json").write_text(json.dumps({"method": "sources", "pdf": "", "format": "sources", "ocr_pages": 0, "pages": 0, "chapters": index},
                                                   indent=1, ensure_ascii=False), encoding="utf-8")
    return len(index)


def summary(pdir: Path) -> dict:
    items = load_index(pdir)
    return {"sources": [{k: s.get(k) for k in ("id", "kind", "title", "words", "images", "media", "rights", "added", "described")}
                        | {"url": s.get("metadata", {}).get("url", ""), "scenes": s.get("metadata", {}).get("scene_count", 0)} for s in items],
            "total_words": sum(int(s.get("words", 0)) for s in items), "max_words": MAX_WORDS,
            "needs_description": [s["id"] for s in items if not s.get("described")], "accepted": list(ACCEPTED)}


def as_dict(doc: SourceDocument) -> dict:
    return asdict(doc)
