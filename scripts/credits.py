"""The credits of a film: title, source book, cast, crew, the AI models that made it, a content rating and a rights note.

  projects/books/<book>/credits.json
    {"title": "The First Days", "based_on": "The First Book of Adam and Eve", "author": "translated by S. C. Malan", "written_by": "", "directed_by": "",
     "crew": [{"role": "Music supervisor", "name": "A. Person"}], "rating": "PG", "content_notes": "mild peril", "rights": "Text in the public domain."}

lines() builds the text of the credits roll: the fields you filled in, the cast from the continuity book's characters, and "Made with" lines for the AI models
whose output is in the book's folder (so an honest credit costs nothing). mix_film.py --credits draws it after the end title.
"""
import json
import os
import re
from pathlib import Path

from bookkit import continuity_file, read_json

RATINGS = ("", "G", "PG", "PG-13", "R", "NC-17", "TV-Y", "TV-G", "TV-PG", "TV-14", "TV-MA", "NR")
TEXT_FIELDS = {"title": 120, "based_on": 160, "author": 160, "written_by": 160, "directed_by": 160, "content_notes": 300, "rights": 300}
MADE_WITH = {            # folder under audio/ or videos/ or images/ -> (what it did, name shown)
    "audio/kokoro": ("Narration", "Kokoro"), "audio/qwen3_tts": ("Narration", "Qwen3-TTS"), "audio/chatterbox_turbo": ("Narration", "Chatterbox-Turbo"),
    "audio/musicgen": ("Music", "MusicGen"), "audio/musicgen_chapters": ("Music", "MusicGen"), "audio/musicgen_scenes": ("Music", "MusicGen"),
    "audio/mmaudio": ("Sound effects", "MMAudio"), "audio/audioldm2": ("Sound effects", "AudioLDM 2"),
    "images/flux2_klein_4b_keyframes": ("Pictures", "FLUX.2 klein"), "videos/ltx_video_fast_i2v": ("Video", "LTX-Video"), "videos/ltx_video_i2v": ("Video", "LTX-Video"),
    "videos/ltx_video": ("Video", "LTX-Video"), "videos/wan22_ti2v_5b_i2v": ("Video", "Wan 2.2"), "videos/wan": ("Video", "Wan"),
    "videos/pika_h3_flex_i2v": ("Video", "Pika"), "videos/hunyuan_video": ("Video", "HunyuanVideo"), "videos/cogvideox": ("Video", "CogVideoX"),
}


class CreditsError(ValueError):
    """A readable reason the credits are not acceptable."""


def credits_file(pdir: Path) -> Path:
    return Path(pdir) / "credits.json"


def load(pdir: Path) -> dict:
    d = read_json(credits_file(pdir), {})
    d = d if isinstance(d, dict) else {}
    out: dict = {k: str(d.get(k) or "")[:n] for k, n in TEXT_FIELDS.items()}
    out["rating"] = d.get("rating") if d.get("rating") in RATINGS else ""
    raw_crew = d.get("crew")
    crew: list = raw_crew if isinstance(raw_crew, list) else []
    out["crew"] = [{"role": str(c.get("role", ""))[:60], "name": str(c.get("name", ""))[:80]} for c in crew if isinstance(c, dict) and c.get("name")][:40]
    return out


def check(spec) -> dict:
    if not isinstance(spec, dict):
        raise CreditsError("credits are {title, based_on, author, ..., crew, rating}")
    for k, n in TEXT_FIELDS.items():
        if len(str(spec.get(k) or "")) > n:
            raise CreditsError(f"{k} is at most {n} characters")
    if spec.get("rating") not in (None,) + RATINGS:
        raise CreditsError(f"rating must be one of: {', '.join(r or '(none)' for r in RATINGS)}")
    crew = spec.get("crew") or []
    if not isinstance(crew, list) or len(crew) > 40 or not all(isinstance(c, dict) and len(str(c.get("name", ""))) <= 80 and len(str(c.get("role", ""))) <= 60 for c in crew):
        raise CreditsError("crew is a list of up to 40 {role, name}")
    return spec


def save(pdir: Path, spec: dict) -> dict:
    check(spec)
    tmp = credits_file(pdir).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(spec, indent=1, ensure_ascii=False))
    os.replace(tmp, credits_file(pdir))
    return load(pdir)


def made_with(pdir: Path) -> list[tuple[str, str]]:
    """[(what, model name)] for the models that have output in this book's folder, in a steady order, each once."""
    pdir = Path(pdir)
    seen, out = set(), []
    for rel, pair in MADE_WITH.items():
        folder = pdir / rel
        if folder.is_dir() and any(folder.iterdir()) and pair not in seen:
            seen.add(pair)
            out.append(pair)
    return out


def lines(pdir: Path) -> list[str]:
    """The text of the credits roll, one string per line ("" for a gap)."""
    pdir = Path(pdir)
    c = load(pdir)
    cont = read_json(continuity_file(pdir), {}) or {}
    out: list[str] = []
    if c["based_on"]:
        out += ["Based on", c["based_on"] + (f", {c['author']}" if c["author"] else ""), ""]
    for label, key in (("Written by", "written_by"), ("Directed by", "directed_by")):
        if c[key]:
            out += [label, c[key], ""]
    names = [str(x.get("name")) for x in cont.get("characters", []) if isinstance(x, dict) and x.get("name")]
    if names:
        out += ["Characters", *names, ""]
    for member in c["crew"]:
        out += [member["role"] or "With", member["name"], ""]
    made = made_with(pdir)
    if made:
        out += ["Made with artificial intelligence", *[f"{what}: {model}" for what, model in made], ""]
    if c["rights"]:
        out += [c["rights"], ""]
    if c["rating"] or c["content_notes"]:
        out += ["Rated " + c["rating"] if c["rating"] else "Content", *([c["content_notes"]] if c["content_notes"] else []), ""]
    while out and out[-1] == "":
        out.pop()
    return [re.sub(r"[\x00-\x1f\x7f]", " ", x) for x in out]
