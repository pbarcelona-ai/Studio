"""Private preview links: a film in a book's films folder that someone without the Studio's token can watch, until the link expires or is revoked.

  projects/books/<book>/shares.json   {"links": {"<token>": {"film": "cut.mp4", "title": "...", "created": 1760000000, "expires": 1760600000 | null, "views": 3}}}

The address is /watch/<book>/<token>. The token is 192 random bits; only the film named in the link can be played (nothing else in the book is reachable through
it) and revoking deletes the link. The link works only for a Host the person has allowed (the Studio's own address, or STUDIO_WATCH_HOSTS), so the Studio itself
stays closed to everything else. Expiry is checked on every request.
"""
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

from bookkit import read_json

FILM_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}\.mp4$")
MAX_LINKS = 50
MAX_HOURS = 24 * 365


_LOCK = threading.RLock()          # the handler serves requests on threads: a view count must not write back a link that was revoked a moment ago


class ShareError(ValueError):
    """A readable reason a link cannot be made."""


def shares_file(pdir: Path) -> Path:
    return Path(pdir) / "shares.json"


def _load(pdir: Path) -> dict:
    d = read_json(shares_file(pdir), {})
    links = d.get("links") if isinstance(d, dict) else None
    return links if isinstance(links, dict) else {}


def _save(pdir: Path, links: dict) -> None:
    f = shares_file(pdir)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"links": links}, indent=1))
    os.replace(tmp, f)
    try:
        f.chmod(0o600)                       # the tokens are the keys: only this user reads them
    except OSError:
        pass


def create(pdir: Path, film: str, hours: float | None = 168, title: str = "", now: float | None = None) -> dict:
    """A new link for films/<film>. hours = how long it works (None or 0 = until revoked). Returns {"token", ...}."""
    pdir = Path(pdir)
    if not FILM_RE.match(film or "") or not (pdir / "films" / film).is_file():
        raise ShareError("choose a finished film in this book's films folder")
    if hours not in (None, 0):
        try:
            hours = float(hours or 0)
        except (TypeError, ValueError) as e:
            raise ShareError("hours must be a number") from e
        if not 0 < hours <= MAX_HOURS:
            raise ShareError(f"a link lasts 1 hour to {MAX_HOURS} hours (or until revoked)")
    with _LOCK:
        links = _load(pdir)
        if len(links) >= MAX_LINKS:
            raise ShareError(f"at most {MAX_LINKS} links per book: revoke some first")
        now = time.time() if now is None else now
        token = secrets.token_urlsafe(24)
        links[token] = {"film": film, "title": " ".join(str(title or "").split())[:120], "created": int(now), "expires": int(now + hours * 3600) if hours else None, "views": 0}
        _save(pdir, links)
        return {"token": token, **links[token]}


def revoke(pdir: Path, token: str) -> bool:
    with _LOCK:
        links = _load(pdir)
        found = False
        for t in list(links):
            if hmac.compare_digest(t.encode(), str(token).encode()):
                del links[t]
                found = True
        if found:
            _save(pdir, links)
        return found


def lookup(pdir: Path, token: str, now: float | None = None, count_view: bool = False) -> dict | None:
    """The link's details if the token is valid and has not expired (and its film still exists), else None. Constant-time comparison; expired links are removed."""
    pdir = Path(pdir)
    with _LOCK:
        links = _load(pdir)
        now = time.time() if now is None else now
        hit = None
        for t, info in list(links.items()):
            if hmac.compare_digest(t.encode(), str(token).encode()):
                hit = (t, info)
        if hit is None:
            return None
        t, info = hit
        if info.get("expires") and now > info["expires"]:
            del links[t]
            _save(pdir, links)
            return None
        if not (pdir / "films" / str(info.get("film", ""))).is_file():
            return None
        if count_view:
            info["views"] = int(info.get("views", 0)) + 1
            _save(pdir, links)
        return {"token": t, **info}


def listing(pdir: Path, now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    out = [{"token": t, **i, "expired": bool(i.get("expires") and now > i["expires"])} for t, i in _load(pdir).items()]
    return sorted(out, key=lambda x: -x.get("created", 0))


def srt_to_vtt(srt: str) -> str:
    """WebVTT for the browser's captions track, from the film's .srt (the timing separator is the only difference that matters)."""
    body = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", srt.replace("\r\n", "\n"))
    return "WEBVTT\n\n" + body.strip() + "\n"
