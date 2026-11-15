"""The screenplay of a book: one file per scene of the adaptation plan, edited by hand, and the approval that unlocks generation.

  projects/books/<book>/screenplay/scene-S001.json   {scene, heading, elements: [{type: action|dialogue|transition, text, character?, note?}], edited}
  projects/books/<book>/screenplay/approval.json     {approved_at, scene_ids, hashes: {S001: <hash of the scene's text>}}

A screenplay counts as approved only while every scene of the plan has a file whose text still matches the approved hash, so any later edit
(or a new plan) takes the approval away. gate() is what the Studio asks before it writes shots or makes pictures from a book that has a plan.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path

import adaptation as ad
from bookkit import read_json, words

TYPES = ("action", "dialogue", "transition")
HEADING_MAX, TEXT_MAX, NAME_MAX = 120, 2000, 60


class ScreenplayError(ValueError):
    """A readable reason a screenplay edit is not acceptable."""


def sp_dir(pdir: Path) -> Path:
    return Path(pdir) / "screenplay"


def scene_file(pdir: Path, sid: str) -> Path:
    if not re.fullmatch(r"S\d{3,6}", sid or ""):
        raise ScreenplayError("bad scene id")
    return sp_dir(pdir) / f"scene-{sid}.json"


def check_scene(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("heading"), str) or not d["heading"].strip() or len(d["heading"]) > HEADING_MAX:
        raise ValueError(f"'heading' must be a scene heading of up to {HEADING_MAX} characters, such as 'INT. CAVE - NIGHT'")
    els = d.get("elements")
    if not isinstance(els, list) or not els:
        raise ValueError("'elements' must be a list with at least one element")
    for e in els:
        if not isinstance(e, dict) or e.get("type") not in TYPES:
            raise ValueError(f"every element needs a 'type' of {', '.join(TYPES)}")
        t = e.get("text")
        if not isinstance(t, str) or not t.strip() or len(t) > TEXT_MAX:
            raise ValueError(f"every element needs 'text' of up to {TEXT_MAX} characters")
        if e["type"] == "dialogue":
            c = e.get("character")
            if not isinstance(c, str) or not c.strip() or len(c) > NAME_MAX:
                raise ValueError("every dialogue element needs a 'character' name")
            if e.get("note") is not None and (not isinstance(e["note"], str) or len(e["note"]) > 120):
                raise ValueError("'note' (the parenthetical, e.g. 'whispering') must be short text")


def clean_scene(d: dict) -> dict:
    """Only the known keys, with whitespace tidied (what is stored)."""
    els = []
    for e in d["elements"]:
        item = {"type": e["type"], "text": " ".join(e["text"].split())}
        if e["type"] == "dialogue":
            item["character"] = " ".join(e["character"].split()).upper()[:NAME_MAX]
            if e.get("note"):
                item["note"] = " ".join(e["note"].split())[:120]
        els.append(item)
    return {"heading": " ".join(d["heading"].split()).upper()[:HEADING_MAX], "elements": els}


def content_hash(scene: dict) -> str:
    return hashlib.sha1(json.dumps([scene.get("heading"), scene.get("elements")], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def load_scene(pdir: Path, sid: str) -> dict | None:
    d = read_json(scene_file(pdir, sid))
    return d if isinstance(d, dict) and d.get("elements") else None


def save_scene(pdir: Path, sid: str, d: dict, edited: bool) -> dict:
    try:
        check_scene(d)
    except ValueError as e:
        raise ScreenplayError(str(e)) from e
    scene = {"scene": sid, **clean_scene(d), "edited": bool(edited)}
    f = scene_file(pdir, sid)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(scene, indent=1, ensure_ascii=False))
    os.replace(tmp, f)
    return scene


def clear_approval(pdir: Path) -> None:
    (sp_dir(pdir) / "approval.json").unlink(missing_ok=True)


def discard(pdir: Path) -> int:
    """Delete the whole screenplay folder (a new plan makes the old scenes meaningless). Returns how many scene files were removed."""
    import shutil
    n = len(list(sp_dir(pdir).glob("scene-*.json"))) if sp_dir(pdir).is_dir() else 0
    shutil.rmtree(sp_dir(pdir), ignore_errors=True)
    return n


def _active(plan: dict) -> list[dict]:
    return ad.active_scenes(plan)


def status(pdir: Path, plan: dict | None) -> dict:
    """{exists, total, written, missing[], approved, approved_at, changed[]} for the scenes the film is made from now."""
    if not plan:
        return {"exists": False, "total": 0, "written": 0, "missing": [], "approved": False, "changed": []}
    scenes = _active(plan)
    have = {s["id"]: load_scene(pdir, s["id"]) for s in scenes}
    ap = read_json(sp_dir(pdir) / "approval.json", {}) or {}
    hashes = ap.get("hashes", {})
    changed = [sid for sid, sc in have.items() if sc and sid in hashes and hashes[sid] != content_hash(sc)]
    missing = [sid for sid, sc in have.items() if not sc]
    reordered = bool(ap) and sorted(ap.get("scene_ids", [])) == sorted(have) and list(ap.get("scene_ids", [])) != list(have)
    approved = bool(ap) and not missing and not changed and all(sid in hashes for sid in have) and list(ap.get("scene_ids", [])) == list(have)  # the order counts too
    return {"exists": True, "total": len(scenes), "written": len(scenes) - len(missing), "missing": missing, "approved": approved,
            "approved_at": ap.get("approved_at") if approved else None, "changed": changed, "reordered": reordered}


def approve(pdir: Path, plan: dict | None) -> dict:
    if not plan:
        raise ScreenplayError("there is no adaptation plan to approve a screenplay for")
    st = status(pdir, plan)
    if st["missing"]:
        raise ScreenplayError(f"{len(st['missing'])} scene(s) have no screenplay yet ({', '.join(st['missing'][:5])}): write them first")
    scenes = _active(plan)
    hashes = {s["id"]: content_hash(load_scene(pdir, s["id"]) or {}) for s in scenes}
    f = sp_dir(pdir) / "approval.json"
    f.write_text(json.dumps({"approved_at": time.strftime("%Y-%m-%d %H:%M:%S"), "scene_ids": [s["id"] for s in scenes], "hashes": hashes}, indent=1))
    return status(pdir, plan)


def gate(pdir: Path) -> str | None:
    """None when generation may go ahead, else the reason it may not. Books without an adaptation plan are not gated."""
    plan = ad.load(pdir)
    if plan is None:
        return None
    if plan.get("stale"):
        return "The chapters were changed after the film was planned. Run the Adapt step again (or discard the plan) before writing shots."
    st = status(pdir, plan)
    if st["missing"]:
        return f"The screenplay is not written for every scene yet ({st['written']} of {st['total']}). Write it and approve it first."
    if not st["approved"]:
        return "The screenplay has not been approved (or was changed after it was). Read it, then press Approve before any shots or pictures are made."
    return None


def to_text(pdir: Path, plan: dict, scene_ids: list[str] | None = None) -> str:
    """The screenplay as readable plain text (Fountain-style): heading, action, centred-ish dialogue."""
    out = []
    for s in _active(plan):
        if scene_ids is not None and s["id"] not in scene_ids:
            continue
        sc = load_scene(pdir, s["id"])
        out.append(f"{sc['heading']}   [{s['id']}, about {s['seconds']:g} s]" if sc else f"[{s['id']} {s['title']}: not written yet]")
        for e in (sc or {}).get("elements", []):
            if e["type"] == "dialogue":
                out.append(f"\n        {e['character']}" + (f"\n    ({e['note']})" if e.get("note") else "") + f"\n    {e['text']}")
            elif e["type"] == "transition":
                out.append(f"\n{e['text'].upper()}")
            else:
                out.append(f"\n{e['text']}")
        out.append("\n")
    return "\n".join(out).strip() + "\n"


def chapter_brief(pdir: Path, plan: dict, n: int) -> str:
    """The screenplay of the scenes taken from chapter n, as text for the shot-writing prompt ('' when there is none)."""
    parts = []
    for s in ad.scenes_of_chapter(plan, n):
        sc = load_scene(pdir, s["id"])
        if sc:
            parts.append(to_text(pdir, {"scenes": [s], "pilot": {"kind": "none"}}).strip())
    return "\n\n".join(parts)


def dialogue_words(sc: dict) -> int:
    return sum(words(e["text"]) for e in sc.get("elements", []) if e["type"] == "dialogue")


# ---- is the film's shot list still made from the approved screenplay?
STAMP_FILE = "shots_from.json"


def fingerprint(pdir: Path) -> str | None:
    """A short hash of the screenplay as it reads now (which scenes, and their text), or None when the book has no film plan."""
    plan = ad.load(pdir)
    if not plan:
        return None
    blob = json.dumps([[s["id"], content_hash(sc) if (sc := load_scene(pdir, s["id"])) else ""] for s in _active(plan)])     # in plan order: moving a scene changes it
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def stamp_shots(pdir: Path) -> None:
    """Called when the shot list is built: remember which approved screenplay it came from (nothing is written for a book without a film plan)."""
    f = Path(pdir) / STAMP_FILE
    fp = fingerprint(pdir)
    if fp is None:
        f.unlink(missing_ok=True)
        return
    f.write_text(json.dumps({"fingerprint": fp, "at": time.strftime("%Y-%m-%d %H:%M:%S")}))


def storyline_changed(pdir: Path) -> bool:
    """True when the shots were built from a screenplay that has since been edited or replaced. False when unknown (an older book)."""
    stamp = read_json(Path(pdir) / STAMP_FILE, {}) or {}
    return bool(stamp.get("fingerprint")) and stamp["fingerprint"] != fingerprint(pdir)
