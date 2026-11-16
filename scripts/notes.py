"""Notes on anything (BOOK_TO_SCREEN_BUILD.md Section 3.4, milestone M12).

The owner attaches a NOTE to a screenplay scene, a shot, a page, a picture, a clip, a character card or a timeline region. A note is addressed
to a crew role (chosen from what it is on; the owner can change it) and is a thread: replies can follow. Open notes go into that role's next
AI call (crew.system adds them), the way real production notes are passed on, and are marked resolved when that step's work is approved
(gates.approve calls resolve_for_step).

  projects/books/<book>/notes/notes.json   [{id, target: {kind, ref}, role, status: open | resolved, messages: [{who, text, at}], created}]
"""
from __future__ import annotations

import json
import time
from pathlib import Path

KINDS = {"scene": "screenwriter", "shot": "director", "page": "illustrator", "picture": "storyboard_artist", "clip": "animation_supervisor",
         "character": "casting_director", "location": "production_designer", "timeline": "editor", "sound": "sound_designer", "music": "composer",
         "voice": "voice_director", "project": "producer"}
STEP_ROLES = {"continuity": {"script_supervisor", "casting_director", "production_designer"}, "shotlist": {"director", "cinematographer", "editor"},
              "lookdev": {"production_designer", "colorist", "casting_director"}, "pictures": {"storyboard_artist"}, "sound": {"voice_director", "sound_designer", "composer"},
              "clips": {"animation_supervisor"}, "edit": {"editor"}, "screenplay": {"screenwriter", "script_doctor"}}


class NoteError(ValueError):
    """A note cannot be made or changed as asked."""


def path(pdir: Path) -> Path:
    return pdir / "notes" / "notes.json"


def load(pdir: Path) -> list[dict]:
    try:
        d = json.loads(path(pdir).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(pdir: Path, notes: list[dict]) -> None:
    path(pdir).parent.mkdir(parents=True, exist_ok=True)
    tmp = path(pdir).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(notes, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path(pdir))


def _roles() -> set[str]:
    import crew
    return set(crew.roles())


def add(pdir: Path, kind: str, ref: str, text: str, role: str = "", who: str = "owner") -> dict:
    if kind not in KINDS:
        raise NoteError(f"a note is on one of: {', '.join(KINDS)}")
    text = " ".join(text.split())
    if not text or len(text) > 4000:
        raise NoteError("a note is 1-4000 characters")
    role = role or KINDS[kind]
    if role not in _roles():
        raise NoteError(f"unknown crew role {role!r}")
    notes = load(pdir)
    n = {"id": f"n{len(notes) + 1:04d}", "target": {"kind": kind, "ref": str(ref)[:80]}, "role": role, "status": "open",
         "messages": [{"who": who, "text": text, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}], "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    notes.append(n)
    _save(pdir, notes)
    return n


def _find(notes: list[dict], nid: str) -> dict:
    n = next((x for x in notes if x["id"] == nid), None)
    if n is None:
        raise NoteError(f"no note {nid}")
    return n


def reply(pdir: Path, nid: str, text: str, who: str = "owner") -> dict:
    notes = load(pdir)
    n = _find(notes, nid)
    text = " ".join(text.split())
    if not text or len(text) > 4000:
        raise NoteError("a reply is 1-4000 characters")
    n["messages"].append({"who": who, "text": text, "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    n["status"] = "open"
    _save(pdir, notes)
    return n


def set_role(pdir: Path, nid: str, role: str) -> dict:
    if role not in _roles():
        raise NoteError(f"unknown crew role {role!r}")
    notes = load(pdir)
    n = _find(notes, nid)
    n["role"] = role
    _save(pdir, notes)
    return n


def set_status(pdir: Path, nid: str, status: str) -> dict:
    if status not in ("open", "resolved"):
        raise NoteError("status is open or resolved")
    notes = load(pdir)
    n = _find(notes, nid)
    n["status"] = status
    _save(pdir, notes)
    return n


def open_for(pdir: Path, roles: list[str] | tuple[str, ...]) -> list[dict]:
    return [n for n in load(pdir) if n["status"] == "open" and (n["role"] in roles or n["role"] == "producer")]


def prompt_text(pdir: Path, roles: list[str] | tuple[str, ...]) -> str:
    """The open notes for these roles, as a section of their system prompt ("" when there are none)."""
    ns = open_for(pdir, roles)
    if not ns:
        return ""
    lines = [f"- On {n['target']['kind']} {n['target']['ref']}: " + " / ".join(m["text"] for m in n["messages"]) for n in ns[:40]]
    return "## Notes from the owner (address each one in this revision)\n" + "\n".join(lines)


def resolve_for_step(pdir: Path, step: str) -> int:
    """Approving a step resolves the open notes addressed to its roles. Returns how many."""
    roles = STEP_ROLES.get(step.split("_", 1)[0], set())
    notes = load(pdir)
    n = 0
    for x in notes:
        if x["status"] == "open" and x["role"] in roles:
            x["status"], n = "resolved", n + 1
    if n:
        _save(pdir, notes)
    return n
