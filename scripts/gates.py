"""Review gates (BOOK_TO_SCREEN_BUILD.md Section 6: "REVIEW GATE"): a step's result counts as approved only while it is unchanged.

  projects/books/<book>/gates.json   {step: {approved_at, hash}}

approve(pdir, step, data) stores a hash of what was approved; approved(pdir, step, data) is True only while `data` still hashes the same, so
any later edit (or a re-run) takes the approval away, as for the screenplay (screenplay.py).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

STEPS = ("continuity", "shotlist", "lookdev", "pictures", "sound", "clips", "edit")


def _file(pdir: Path) -> Path:
    return pdir / "gates.json"


def _load(pdir: Path) -> dict:
    try:
        d = json.loads(_file(pdir).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def digest(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def known(step: str) -> bool:
    """A step, or a step of one style ("pictures_claymation", "clips_anime")."""
    base, _, style = step.partition("_")
    return step in STEPS or (base in STEPS and bool(re.fullmatch(r"[a-z0-9_]{2,30}", style)))


def approve(pdir: Path, step: str, data) -> dict:
    if not known(step):
        raise ValueError(f"unknown step {step!r}")
    d = _load(pdir)
    d[step] = {"approved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "hash": digest(data)}
    tmp = _file(pdir).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
    tmp.replace(_file(pdir))
    return d[step]


def approved(pdir: Path, step: str, data) -> bool:
    g = _load(pdir).get(step) or {}
    return bool(g) and g.get("hash") == digest(data)


def status(pdir: Path, step: str, data) -> dict:
    g = _load(pdir).get(step) or {}
    ok = bool(g) and g.get("hash") == digest(data)
    return {"approved": ok, "approved_at": g.get("approved_at", "") if ok else "", "changed_since": bool(g) and not ok}


def revoke(pdir: Path, step: str) -> None:
    d = _load(pdir)
    if d.pop(step, None) is not None:
        _file(pdir).write_text(json.dumps(d, indent=1), encoding="utf-8")
