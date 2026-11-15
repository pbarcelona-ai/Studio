"""Locked cast, costume and location per scene.

  projects/books/<book>/cast_lock.json
    {"scenes": {"S003": {"characters": {"Eve": {"token": "Eve: ... exact look in this scene ...", "reference": "projects/characters/main/references/eve/ref_02.png"}},
                         "location": {"reference": "projects/books/<book>/location_refs/cave.png"}}}}

`token` replaces the character's description from the continuity book in every shot of that scene (a costume change, an injury, an older face);
`reference` is the picture that steers the keyframes of that scene instead of the character's usual one. The location reference does the same for the place.
Scenes come from the adaptation plan (adaptation.py); a shot's scene is adaptation.shot_scene().
"""
import json
import os
from pathlib import Path

import adaptation as ad
import bookkit
from bookkit import read_json

PICTURE = (".png", ".jpg", ".jpeg", ".webp")
TOKEN_MAX = 400


class LockError(ValueError):
    """A readable reason a lock change is not acceptable."""


def lock_file(pdir: Path) -> Path:
    return Path(pdir) / "cast_lock.json"


def load(pdir: Path) -> dict:
    d = read_json(lock_file(pdir), {})
    return d.get("scenes", {}) if isinstance(d, dict) and isinstance(d.get("scenes"), dict) else {}


def _save(pdir: Path, scenes: dict) -> None:
    f = lock_file(pdir)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"scenes": scenes}, indent=1, ensure_ascii=False))
    os.replace(tmp, f)


def check_reference(ref: str) -> str:
    """A reference must be a picture inside projects/ (the Studio's own folder), given relative to the repository root."""
    root = bookkit.ROOT
    p = (root / ref).resolve()
    try:
        p.relative_to((root / "projects").resolve())
    except ValueError as e:
        raise LockError("a reference picture must be inside the projects folder") from e
    if p.suffix.lower() not in PICTURE or not p.is_file():
        raise LockError(f"{ref} is not a picture that exists")
    return p.relative_to(root).as_posix()


def set_lock(pdir: Path, plan: dict, scene: str, kind: str, name: str = "", token: str = "", reference: str = "") -> dict:
    """Lock one character (kind "character", name) or the place (kind "location") in a scene. Empty token and reference remove the lock."""
    if scene not in {s["id"] for s in plan["scenes"]}:
        raise LockError(f"there is no scene {scene}")
    if kind not in ("character", "location"):
        raise LockError("kind must be character or location")
    if kind == "character" and not str(name).strip():
        raise LockError("say which character")
    token = " ".join(str(token or "").split())
    if len(token) > TOKEN_MAX:
        raise LockError(f"a costume description is at most {TOKEN_MAX} characters")
    entry: dict = {}
    if token:
        entry["token"] = token
    if reference:
        entry["reference"] = check_reference(reference)
    if kind == "location" and token:
        raise LockError("a location is locked by its reference picture only")
    scenes = load(pdir)
    sc = scenes.setdefault(scene, {})
    if kind == "character":
        chars = sc.setdefault("characters", {})
        if entry:
            chars[str(name).strip()] = entry
        else:
            chars.pop(str(name).strip(), None)
    elif entry:
        sc["location"] = entry
    else:
        sc.pop("location", None)
    if not sc.get("characters"):
        sc.pop("characters", None)
    if not sc:
        scenes.pop(scene, None)
    _save(pdir, scenes)
    return scenes


def token_overrides(lock: dict, scene: str | None) -> dict[str, str]:
    """{lower-case character name: description} for the characters locked in this scene."""
    if not scene:
        return {}
    return {n.lower(): e["token"] for n, e in (lock.get(scene, {}).get("characters") or {}).items() if e.get("token")}


def reference_for(lock: dict, scene: str | None, character: str | None = None) -> Path | None:
    """The locked picture for a character (or, with character=None, for the place) in this scene, or None."""
    if not scene or scene not in lock:
        return None
    entry = (lock[scene].get("characters") or {}).get(character) if character else lock[scene].get("location")
    if not entry and character:
        entry = next((e for n, e in (lock[scene].get("characters") or {}).items() if n.lower() == character.lower()), None)
    ref = (entry or {}).get("reference")
    if not ref:
        return None
    p = bookkit.ROOT / ref
    return p if p.is_file() else None


def summary(lock: dict, plan: dict | None) -> dict:
    return {"scenes": len(lock), "characters": sum(len(v.get("characters") or {}) for v in lock.values()),
            "locations": sum(1 for v in lock.values() if v.get("location")),
            "orphans": sorted(set(lock) - {s["id"] for s in (plan or {}).get("scenes", [])})}


def shot_context(pdir: Path):
    """A function (chapter, shot_n, n_shots_in_chapter) -> scene id for a book with a plan, else a function that always answers None."""
    plan = ad.load(pdir)
    if not plan or plan.get("stale"):
        return lambda chapter, shot, n: None
    return lambda chapter, shot, n: ad.shot_scene(plan, chapter, shot, n)
