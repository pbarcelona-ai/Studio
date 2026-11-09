"""Data contracts for the files the Studio and its scripts share: what a valid file looks like, a schema_version, and migrations.

Files covered
  global_params.json   {"schema_version": 1, "positives": str, "negatives": str}
  <book>.json          the continuity book: title, setting, visual_style, music_theme, characters[], locations[]
  prompt CSVs          VIDEO_COLS / IMAGE_COLS are the required header columns of the video and image shot files

Reading is tolerant (old files without schema_version are version 0 and are upgraded in memory by `upgrade`); writing always stamps the
current version. Validators return a list of problems (empty = valid) so callers can show every problem at once.
"""
import re
from collections.abc import Callable, Iterable
from typing import Any

SCHEMA_VERSION = 1

VIDEO_COLS = ["chapter", "shot", "prompt", "negative", "width", "height", "frames", "steps", "guidance", "seed"]
IMAGE_COLS = ["chapter", "shot", "prompt", "negative", "width", "height", "steps", "guidance", "seed"]

# (kind, from_version) -> function(data) -> data at from_version + 1
MIGRATIONS: dict[tuple[str, int], Callable[[dict], dict]] = {}


def upgrade(kind: str, data: dict) -> dict:
    """Bring a loaded file up to SCHEMA_VERSION using MIGRATIONS (a file without schema_version is version 0). Never mutates the input."""
    data = dict(data)
    version = data.get("schema_version", 0)
    if not isinstance(version, int) or version > SCHEMA_VERSION:
        raise ValueError(f"{kind}: schema_version {version!r} is newer than this Studio understands ({SCHEMA_VERSION})")
    while version < SCHEMA_VERSION:
        step = MIGRATIONS.get((kind, version))
        if step is not None:
            data = step(data)
        version += 1
        data["schema_version"] = version
    return data


def stamp(data: dict) -> dict:
    """A copy of `data` marked with the current schema_version (for writing)."""
    return {"schema_version": SCHEMA_VERSION, **{k: v for k, v in data.items() if k != "schema_version"}}


# ---- global_params.json
def clean_global_params(raw: Any) -> dict[str, Any]:
    """Whatever was in global_params.json -> {"schema_version", "positives": str, "negatives": str}; anything malformed becomes empty text."""
    d = upgrade("global_params", raw) if isinstance(raw, dict) else {}
    text = lambda v: v if isinstance(v, str) else ""          # noqa: E731
    return stamp({"positives": text(d.get("positives")), "negatives": text(d.get("negatives"))})


# ---- continuity book
_STAGE_CHAPTERS = re.compile(r"\d+(-\d*)?")


def validate_continuity(d: Any) -> list[str]:
    """Problems in a continuity book (empty list = valid)."""
    if not isinstance(d, dict):
        return ["the continuity book must be a JSON object"]
    out = [f"{k} must be text" for k in ("title", "setting", "visual_style", "music_theme") if k in d and not isinstance(d[k], str)]
    chars = d.get("characters")
    if not isinstance(chars, list):
        out.append("characters must be a list")
        chars = []
    for i, c in enumerate(chars):
        where = f"characters[{i}]"
        if not isinstance(c, dict):
            out.append(f"{where} must be an object")
            continue
        for k in ("name", "token"):
            if not isinstance(c.get(k), str) or not c[k].strip():
                out.append(f"{where}.{k} must be non-empty text")
        for j, st in enumerate(c.get("stages") or []):
            if (not isinstance(st, dict) or not st.get("label") or not st.get("token")
                    or not _STAGE_CHAPTERS.fullmatch(str(st.get("chapters") or ""))):
                out.append(f"{where}.stages[{j}] needs a label, a token and chapters like '1-12'")
    locs = d.get("locations", [])
    if not isinstance(locs, list):
        out.append("locations must be a list")
    else:
        out += [f"locations[{i}] needs a name and a token" for i, loc in enumerate(locs)
                if not isinstance(loc, dict) or not loc.get("name") or not loc.get("token")]
    return out


# ---- prompt CSVs
def missing_columns(fieldnames: Iterable[str] | None, required: Iterable[str]) -> list[str]:
    """Required columns that a CSV header lacks."""
    have = set(fieldnames or [])
    return [c for c in required if c not in have]
