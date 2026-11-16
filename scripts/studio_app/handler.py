"""HTTP transport: host/origin check, token authentication, security headers, body limits, media streaming and the web page.
The JSON API itself lives in api.py + routes_get.py / routes_post.py."""
import hashlib
import json
import mimetypes
import os
import re
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import shares
from bookkit import SLUG_RE, slugify
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from . import breakdown_routes, clips_routes, collab_routes, crew_routes, edit_routes, library_routes, media_routes, pictures_routes, readin_routes, routes_get, routes_post, setup_install, sound_routes, sources_routes, styles_routes  # noqa: F401  (importing them registers the routes)
from .api import ROUTES, Request, dispatch
from .config import BOOK_EXTS, LIBRARY, MAX_JSON_BODY, MAX_UPLOAD, WEB
from .gallery import make_depth, make_thumb
from .log import get_logger
from .session import SESSION

log = get_logger("http")
COOKIE = "studio_token"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data: blob:; media-src 'self' blob:; "
       "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
MEDIA = {".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg", ".wav": "audio/wav", ".srt": "text/plain; charset=utf-8"}
DOWNLOADS = {".pdf": "application/pdf", ".fountain": "text/plain; charset=utf-8", ".fdx": "application/xml",
             ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".zip": "application/zip", ".json": "application/json",
             ".epub": "application/epub+zip", ".m4b": "audio/mp4", ".mp3": "audio/mpeg"}


def safe_project_file(prefix: str, path: str, allowed: tuple[str, ...]) -> Path | None:
    """/<prefix>/<project>/<path under it> -> the real file, only if it is inside that project's folder and has an allowed suffix."""
    parts = path[len(prefix):].split("/", 1)
    if len(parts) != 2 or not SLUG_RE.match(parts[0]):
        return None
    base = pdir(parts[0]).resolve()
    target = (base / parts[1]).resolve()
    if base not in target.parents or target.suffix.lower() not in allowed or not target.is_file():
        return None
    return target


class Handler(BaseHTTPRequestHandler):
    server: ThreadingHTTPServer
    server_version = "PistachiosStudio"
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):
        log.debug("%s " + fmt, self.address_string(), *args)

    # ------------------------------------------------------------ checks
    def _host_ok(self) -> bool:
        host, origin, port = self.headers.get("Host", ""), self.headers.get("Origin"), self.server.server_port
        return host in (f"127.0.0.1:{port}", f"localhost:{port}") and (
            origin is None or origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"))

    def _cookie_token(self) -> str:
        jar = SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
        except CookieError:
            return ""
        return jar[COOKIE].value if COOKIE in jar else ""

    def _authed(self, query: dict | None = None) -> bool:
        """The right Host/Origin plus the token: in the X-Studio-Token header, the cookie, or (media tags only) ?t=."""
        if not self._host_ok():
            return False
        candidates = [self.headers.get("X-Studio-Token", ""), self._cookie_token()]
        if query is not None:
            candidates.append(query.get("t", [""])[0])
        return any(c and SESSION.matches(c) for c in candidates)

    # ------------------------------------------------------------ responses
    def _headers(self, code: int, ctype: str, length: int, cache: str = "no-store", extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _send(self, code, body, ctype="application/json", cache="no-store", extra=None):
        data = body if isinstance(body, bytes) else body.encode()
        self._headers(code, ctype, len(data), cache, extra)
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj))

    def _redirect(self, location: str, extra: dict) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()

    # ------------------------------------------------------------ GET
    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path.startswith("/watch/"):
            return self._watch(url)
        if url.path == "/":
            return self._index(query)
        if url.path.startswith("/static/"):
            return self._static(url.path)
        if url.path.startswith(("/file/", "/thumb/", "/depth/", "/download/")):
            if not self._authed(query):
                return self._json(403, {"error": "forbidden"})
            if url.path.startswith("/file/"):
                return self._file(url)
            if url.path.startswith("/download/"):
                return self._download(url)
            return self._derived(url)
        if not self._authed():
            return self._json(403, {"error": "forbidden"})
        code, obj = dispatch("GET", url.path, Request(query=query))
        self._json(code, obj)

    def do_HEAD(self):
        self.do_GET()

    def _index(self, query):
        """The page. A link with ?t=<token> sets the cookie and redirects to the clean address (the token leaves the address bar)."""
        if not self._host_ok():
            return self._send(403, "Open the link printed by studio.py (it contains the token).", "text/plain")
        given = query.get("t", [""])[0]
        if given and SESSION.matches(given):
            cookie = f"{COOKIE}={SESSION.token}; Path=/; HttpOnly; SameSite=Strict"
            return self._redirect("/", {"Set-Cookie": cookie})
        if not SESSION.matches(self._cookie_token()):
            return self._send(403, "Open the link printed by studio.py (it contains the token).", "text/plain")
        page = (WEB / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", SESSION.token)
        self._send(200, page, "text/html; charset=utf-8")

    def _static(self, path: str):
        """The page's own CSS/JS from web/static/ (nothing secret in them: the token is injected into index.html only)."""
        if not self._host_ok():
            return self._json(403, {"error": "forbidden"})
        root = (WEB / "static").resolve()
        target = (root / path[len("/static/"):]).resolve()
        if root not in target.parents or not target.is_file():
            return self._json(404, {"error": "not found"})
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in (".js", ".css"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype, cache="no-cache")

    def _derived(self, url):
        """/thumb/... (small JPEG of a picture or clip) and /depth/... (depth map of a picture), cached under the project."""
        kind = "thumb" if url.path.startswith("/thumb/") else "depth"
        allowed = (".png", ".jpg", ".mp4") if kind == "thumb" else (".png", ".jpg")
        target = safe_project_file(f"/{kind}/", url.path, allowed)
        if target is None:
            return self._json(404, {"error": "not found"})
        base = pdir(url.path.split("/")[2]).resolve()
        ext, make, ctype = (".jpg", make_thumb, "image/jpeg") if kind == "thumb" else (".png", make_depth, "image/png")
        dest = base / f".{kind}s" if kind == "thumb" else base / ".depth"
        try:
            # keyed by the file's size and time too: a take swapped in (os.replace keeps its older time) gets its own thumbnail, not the last one's
            st = target.stat()
            dest = dest / (hashlib.sha1(f"{target.relative_to(base).as_posix()}:{st.st_size}:{st.st_mtime_ns}".encode()).hexdigest()[:24] + ext)
            if not dest.exists():
                make(target, dest)
            data = dest.read_bytes()
        except Exception as e:                       # no PIL/torch, no internet for the first model download, or an unreadable picture
            log.info("no %s for %s: %s", kind, target.name, e)
            code = 404 if kind == "thumb" else 500
            return self._json(code, {"error": f"no thumbnail: {e}" if kind == "thumb" else f"could not make a depth map: {e}"})
        self._send(200, data, ctype, cache="private, max-age=3600")

    def _file(self, url):
        """Stream a result file with Range support: /file/<project>/<path under it>. Only media inside projects/<project>/."""
        target = safe_project_file("/file/", url.path, tuple(MEDIA))
        if target is None:
            return self._json(404, {"error": "not found"})
        self._serve(target, MEDIA[target.suffix.lower()])

    def _download(self, url):
        """An export to save: /download/<project>/exports/<file> (screenplay PDF / Fountain / Word / Final Draft, notes, zips), as an attachment."""
        target = safe_project_file("/download/", url.path, tuple(DOWNLOADS))
        if target is None or target.parent.name != "exports":
            return self._json(404, {"error": "not found"})
        self._serve(target, DOWNLOADS[target.suffix.lower()], {"Content-Disposition": f'attachment; filename="{target.name}"'})

    def _serve(self, target: Path, ctype: str, extra_headers: dict | None = None):
        """Send a file with Range support (a 206 for a partial request)."""
        size = target.stat().st_size
        start, end, code = 0, size - 1, 200
        rng = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if rng and (rng.group(1) or rng.group(2)):
            if rng.group(1):
                start = int(rng.group(1))
                end = int(rng.group(2)) if rng.group(2) else end
            else:
                start = max(size - int(rng.group(2)), 0)
            end = min(end, size - 1)
            if start > end:
                return self._headers(416, "text/plain", 0, extra={"Content-Range": f"bytes */{size}"})
            code = 206
        extra = {"Accept-Ranges": "bytes", **(extra_headers or {})}
        if code == 206:
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        self._headers(code, ctype, end - start + 1, extra=extra)
        if self.command == "HEAD":
            return
        with open(target, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    # ------------------------------------------------------------ private preview links (shares.py)
    def _watch_host_ok(self) -> bool:
        """A watch link works for the Studio's own address and for the hosts named in STUDIO_WATCH_HOSTS (comma separated, e.g. a tunnel's name)."""
        host, port = self.headers.get("Host", ""), self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"} | {h.strip().lower() for h in os.environ.get("STUDIO_WATCH_HOSTS", "").split(",") if h.strip()}
        return host.lower() in allowed

    def _watch(self, url):
        """/watch/<book>/<token> (the page), /watch/<book>/<token>/film.mp4 and /captions.vtt. No Studio token; only the film the link names is reachable."""
        parts = url.path.split("/")                       # ['', 'watch', book, token, (what)]
        gone = lambda: self._send(404, "This link does not work any more.", "text/plain; charset=utf-8", extra={"X-Robots-Tag": "noindex"})   # noqa: E731
        if not self._watch_host_ok() or len(parts) not in (4, 5) or not SLUG_RE.match(parts[2]) or not re.fullmatch(r"[A-Za-z0-9_-]{20,80}", parts[3]):
            return gone()
        base = pdir(parts[2])
        info = shares.lookup(base, parts[3], count_view=len(parts) == 4)
        if info is None:
            return gone()
        film = (base / "films" / info["film"]).resolve()
        if (base / "films").resolve() not in film.parents:
            return gone()
        what = parts[4] if len(parts) == 5 else ""
        noindex = {"X-Robots-Tag": "noindex"}
        if what == "film.mp4":
            return self._serve(film, "video/mp4", noindex)
        if what == "captions.vtt":
            srt = film.with_suffix(".srt")
            return self._send(200, shares.srt_to_vtt(srt.read_text(encoding="utf-8")) if srt.is_file() else "WEBVTT\n", "text/vtt; charset=utf-8", extra=noindex) if film.exists() else gone()
        if what:
            return gone()
        title = info["title"] or film.stem.replace("_", " ")
        esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")   # noqa: E731
        base_url = f"/watch/{parts[2]}/{parts[3]}"
        track = f'<track kind="captions" src="{base_url}/captions.vtt" srclang="en" label="Captions" default>' if film.with_suffix(".srt").is_file() else ""
        page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">'
                f'<title>{esc(title)}</title><style>body{{margin:0;background:#111;color:#eee;font:16px system-ui,sans-serif}}main{{max-width:1100px;margin:0 auto;padding:1rem}}'
                f'video{{width:100%;max-height:80vh;background:#000}}h1{{font-size:1.2rem;font-weight:600}}</style></head><body><main><h1>{esc(title)}</h1>'
                f'<video controls preload="metadata" src="{base_url}/film.mp4">{track}Your browser cannot play this video.</video>'
                f'<p>A private preview. Please do not share the link.</p></main></body></html>')
        self._send(200, page, "text/html; charset=utf-8", extra=noindex)

    # ------------------------------------------------------------ POST
    def _content_length(self) -> int | None:
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            return None
        return n if n >= 0 else None

    def do_POST(self):
        if not self._authed():
            return self._json(403, {"error": "forbidden"})
        url = urlparse(self.path)
        if url.path == "/api/upload":
            return self._upload(url)
        if url.path == "/api/source_upload":
            return self._source_upload(url)
        if url.path not in ROUTES["POST"]:
            return self._json(404, {"error": "not found"})
        size = self._content_length()
        if size is None:
            return self._json(400, {"error": "bad Content-Length"})
        if size > MAX_JSON_BODY:
            return self._json(413, {"error": f"request too large (limit {MAX_JSON_BODY // 2**20} MB)"})
        try:
            body = json.loads(self.rfile.read(size) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("the request body must be a JSON object")
        except ValueError as e:
            return self._json(400, {"error": f"bad request: {e}"})
        code, obj = dispatch("POST", url.path, Request(query=parse_qs(url.query), body=body))
        self._json(code, obj)

    @staticmethod
    def _check_book_file(path: Path, fname: str) -> tuple[bool, str]:
        """Is the saved upload really the kind of file its name says? (ok, description for the error message)"""
        ext = Path(fname).suffix.lower()
        if ext == ".pdf":
            with open(path, "rb") as f:
                return f.read(5) == b"%PDF-", "a complete PDF file"
        if ext == ".rtf":
            with open(path, "rb") as f:
                return f.read(64).lstrip().startswith(b"{\\rtf"), "an RTF file"
        if ext in (".epub", ".docx", ".odt"):
            import zipfile
            want = {".epub": "META-INF/container.xml", ".docx": "word/document.xml", ".odt": "content.xml"}[ext]
            try:
                with zipfile.ZipFile(path) as z:
                    return want in z.namelist(), f"a valid {ext[1:].upper()} file"
            except (zipfile.BadZipFile, OSError):
                return False, f"a valid {ext[1:].upper()} file"
        try:                                                         # text and HTML: must be readable with real words in it
            from book_formats import decode
            text = decode(path.read_bytes())
            ok = "\x00" not in text and len(text.split()) >= 5
        except OSError:
            ok = False
        return ok, "readable text of at least a few words"

    def _source_upload(self, url):
        """A story source file (document, screenplay, picture, video / audio) streamed into the book's sources (sources.py, M2)."""
        import tempfile

        import sources
        q = parse_qs(url.query)
        one = lambda k, d="": q.get(k, [d])[0]                     # noqa: E731
        fname = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(one("filename", "source")).name).strip()[:120]
        if not fname.lower().endswith(sources.ACCEPTED) or len(fname) < 3:
            return self._json(400, {"error": "that kind of file cannot be used as a source"})
        try:
            book = pdir(one("project"), "book")
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        if one("rights") != "1":
            return self._json(400, {"error": "Tick the box to confirm you have the right to use this source."})
        limit = sources.MAX_VIDEO if fname.lower().endswith(sources.MEDIA_EXTS) else sources.MAX_DOC
        size = self._content_length() or 0
        if size <= 0 or size > limit:
            return self._json(400, {"error": f"the file must be 1 byte to {limit // 2**20} MB"})
        book.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="studio-src-", dir=book) as t:
            tmp = Path(t) / "upload.part"
            left = size
            with open(tmp, "wb") as f:
                while left:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            if left:
                return self._json(400, {"error": "the upload stopped before the end; try again"})
            from .sources_routes import upload
            try:
                entry = upload(book, tmp, fname, True, one("comic") == "1", one("title")[:120], one("note")[:500])
            except sources.SourceError as e:
                return self._json(400, {"error": str(e)})
        return self._json(200, {"added": entry, **sources.summary(book)})

    def _upload(self, url):
        q = parse_qs(url.query)
        fname = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(q.get("filename", ["book.pdf"])[0]).name).strip()
        if not fname.lower().endswith(BOOK_EXTS) or len(fname) < 5:
            return self._json(400, {"error": "only .pdf, .epub, .docx, .odt, .rtf, .html, .txt or .md files"})
        if not SLUG_RE.match(slugify(Path(fname).stem)):
            return self._json(400, {"error": "that file name has no letters or digits to name the book from"})
        size = self._content_length() or 0
        if size <= 0 or size > MAX_UPLOAD:
            return self._json(400, {"error": f"file must be 1 byte to {MAX_UPLOAD // 2**20} MB"})
        LIBRARY.mkdir(exist_ok=True)
        tmp = LIBRARY / (fname + ".part")
        left = size
        with open(tmp, "wb") as f:
            while left:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        ok, what = self._check_book_file(tmp, fname)
        if left or not ok:
            tmp.unlink(missing_ok=True)
            return self._json(400, {"error": f"that is not {what}"})
        tmp.replace(LIBRARY / fname)
        return self._json(200, {"filename": fname, "project": slugify(Path(fname).stem), "bytes": size})
