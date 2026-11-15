"""The Export card: finished films, export presets (export_film.py) and the credits of the film (credits.py)."""
import re

import credits
import export_film
import shares
from bookkit import SLUG_RE
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .common import PlanError
from .media import media_seconds
from .steps import engine_args


def _book(slug):
    slug = str(slug or "")
    if not SLUG_RE.match(slug) or not pdir(slug).is_dir():
        raise PlanError("pick a book first")
    return pdir(slug)


def exports_data(slug) -> dict:
    d = _book(slug)
    films = sorted((p for p in (d / "films").glob("*.mp4") if not p.name.startswith("_")), key=lambda p: p.stat().st_mtime, reverse=True) if (d / "films").is_dir() else []
    return {"films": [{"name": p.name, "seconds": media_seconds(p), "captions": p.with_suffix(".srt").is_file()} for p in films],
            "presets": [{"id": k, "label": v[0], "note": v[8]} for k, v in export_film.PRESETS.items()]}


def export_step(body: dict) -> dict:
    """The job step for POST /api/export {project, film, preset, languages: "es, fr", audio_tracks: [{lang, file}], title, engine, claude_model}."""
    d = _book(body.get("project"))
    film, preset = str(body.get("film") or ""), str(body.get("preset") or "")
    if preset not in export_film.PRESETS:
        raise PlanError("choose a preset")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}\.mp4", film) or not (d / "films" / film).is_file():
        raise PlanError("choose a finished film")
    langs = [x.strip() for x in re.split(r"[,\s]+", str(body.get("languages") or "")) if x.strip()]
    for lang in langs:
        if not export_film.LANG_RE.match(lang):
            raise PlanError(f"{lang!r} is not a language code (for example es or pt-BR)")
    if len(langs) > 8:
        raise PlanError("at most 8 extra languages")
    argv = ["uv", "run", "--with", "imageio-ffmpeg", "python", "export_film.py", "--project", str(body["project"]), "--film", film, "--preset", preset]
    if langs:
        argv += ["--languages", ",".join(langs)] + engine_args(body)
    for t in body.get("audio_tracks") or []:
        lang, rel = str((t or {}).get("lang", "")), str((t or {}).get("file", ""))
        if not export_film.LANG_RE.match(lang) or not rel or ".." in rel or rel.startswith("/"):
            raise PlanError("an extra audio track needs a language code and a file inside the book's folder")
        argv += ["--audio-track", f"{lang}={rel}"]
    title = " ".join(str(body.get("title") or "").split())[:120]
    if title:
        argv += ["--title", title]
    return {"label": f"Export {film} as {export_film.PRESETS[preset][0]}" + (f" with subtitles in {', '.join(langs)}" if langs else ""), "argv": argv, "env": {}}


def credits_get(slug) -> dict:
    d = _book(slug)
    return {"credits": credits.load(d), "ratings": list(credits.RATINGS), "preview": credits.lines(d)}


def credits_set(body: dict) -> dict:
    d = _book(body.get("project"))
    try:
        credits.save(d, body.get("credits") or {})
    except credits.CreditsError as e:
        raise PlanError(str(e)) from e
    return credits_get(body.get("project"))


def shares_data(slug) -> dict:
    d = _book(slug)
    return {"links": [{**x, "path": f"/watch/{slug}/{x['token']}"} for x in shares.listing(d)]}


def share_create(body: dict) -> dict:
    """POST /api/share {project, film, hours (0 = until revoked), title}"""
    d = _book(body.get("project"))
    try:
        link = shares.create(d, str(body.get("film") or ""), body.get("hours", 168), str(body.get("title") or ""))
    except shares.ShareError as e:
        raise PlanError(str(e)) from e
    return {"created": f"/watch/{body['project']}/{link['token']}", **shares_data(body["project"])}


def share_revoke(body: dict) -> dict:
    d = _book(body.get("project"))
    if not shares.revoke(d, str(body.get("token") or "")):
        raise PlanError("that link does not exist (already revoked?)")
    return shares_data(body["project"])
