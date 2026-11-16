"""The Producer chat (BOOK_TO_SCREEN_BUILD.md Section 3.5, milestone M12).

The owner writes what they want ("make the villain scarier", "give me a 3-minute vertical version"); the Producer turns it into a PLAN: which
steps run again, which crew roles act, notes for them, settings to change, and an estimate. Nothing runs or is spent until the owner accepts.
Simple requests (regenerate one picture) are done directly. STOP / ADD INFORMATION / CONTINUE: a running job can be stopped from the chat,
information added (it becomes a note every crew role reads), and the job continued (each step carries on where it stopped).
The chat never replaces the step path: everything it does is an ordinary step, note, setting or version, and each accepted plan makes a
moment in the history.

  projects/books/<book>/chat/chat.json   [{id, at, who: owner | producer, text, plan?: {...}, status?: proposed | accepted | dismissed | done}]
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

import notes
import production

STEPS = {   # the steps a plan may run again: (the program the job runs, what it does)
    "read_it_in": ("read_it_in.py", "Read it in again (coverage to screenplay)"),
    "continuity": ("continuity_book.py", "Write the continuity book again"),
    "shot_list": ("shot_list.py", "Write the shot list again"),
    "styles": ("styles.py", "Write the style cards and translations again"),
    "sound": ("sound_design.py", "Write the voices, sound and music again"),
    "motion": ("clips.py", "Write the motion prompts again"),
}
SETTINGS = ("target_minutes", "aspect", "rating", "faithfulness", "tier", "products")
Ask = Callable[[str, str | list[str], str, Callable[[dict], None]], dict]


class ChatError(ValueError):
    """The chat cannot do this as asked."""


def path(pdir: Path) -> Path:
    return pdir / "chat" / "chat.json"


def load(pdir: Path) -> list[dict]:
    try:
        d = json.loads(path(pdir).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(pdir: Path, msgs: list[dict]) -> None:
    path(pdir).parent.mkdir(parents=True, exist_ok=True)
    tmp = path(pdir).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(msgs[-500:], indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path(pdir))


def _add(pdir: Path, msg: dict) -> dict:
    msgs = load(pdir)
    msg = {"id": f"c{len(msgs) + 1:04d}", "at": time.strftime("%Y-%m-%dT%H:%M:%S"), **msg}
    msgs.append(msg)
    _save(pdir, msgs)
    return msg


def check_plan(d) -> None:
    if not isinstance(d, dict) or not str(d.get("reply", "")).strip():
        raise ValueError('reply with {"reply": "...", "simple": false, "steps": [...], "notes": [...], "settings": {...}, "regenerate": [...]}')
    for s in d.get("steps", []):
        if s not in STEPS:
            raise ValueError(f"steps are some of {', '.join(STEPS)}")
    for n in d.get("notes", []):
        if not isinstance(n, dict) or n.get("kind") not in notes.KINDS or not str(n.get("text", "")).strip():
            raise ValueError(f"every note has a kind ({', '.join(notes.KINDS)}), a ref and its text")
        n["role"] = notes.role_for(n["kind"], str(n.get("role") or ""))      # "writer" is the screenwriter; an unknown role goes to the kind's owner
    if not isinstance(d.get("settings", {}), dict) or any(k not in SETTINGS for k in d.get("settings", {})):
        raise ValueError(f"settings may change only {', '.join(SETTINGS)}")
    for r in d.get("regenerate", []):
        if not isinstance(r, dict) or not isinstance(r.get("row"), int):
            raise ValueError('regenerate lists pictures as {"style": "...", "row": 3}')


PROMPT = """You are the producer. The owner wrote: "{text}"
Turn it into a plan the owner can accept. You can: run steps again ({steps}); write notes to the crew (kinds: {kinds}; each note says on what,
e.g. kind "character", ref "MARA"; "role" is one of: {roles}, or "" for the usual one); change settings ({settings}); regenerate single pictures (style, row). A request for one small thing
(regenerate one picture) is "simple": true and has no steps. Estimate what it costs (GPU time; free GPUs are $0). Say it in plain words.
Reply as JSON: {{"reply": "what you will do, for the owner", "simple": false, "steps": ["shot_list"], "notes": [{{"kind": "character", "ref": "MARA",
"role": "", "text": "..."}}], "settings": {{}}, "regenerate": [], "estimate": "..."}}

THE PROJECT NOW: {state}"""


def state(pdir: Path) -> str:
    st = production.load(pdir)
    have = [p.name for p in (pdir / "readin", pdir / "shots", pdir / "pictures", pdir / "sound", pdir / "edit") if p.is_dir()]
    return json.dumps({"settings": {k: st[k] for k in SETTINGS if k in st}, "styles": [s["id"] for s in st["styles"]], "made": have}, ensure_ascii=False)


def ask_producer(pdir: Path, text: str, ask: Ask) -> dict:
    text = " ".join(text.split())
    if not text or len(text) > 4000:
        raise ChatError("write a request of 1-4000 characters")
    _add(pdir, {"who": "owner", "text": text})
    d = ask(PROMPT.format(text=text, steps=", ".join(STEPS), kinds=", ".join(notes.KINDS), roles=", ".join(notes._roles_sorted()), settings=", ".join(SETTINGS), state=state(pdir)),
            "producer", "producer chat", check_plan)
    plan = {k: d.get(k) for k in ("steps", "notes", "settings", "regenerate", "estimate", "simple")}
    return _add(pdir, {"who": "producer", "text": str(d["reply"]), "plan": plan, "status": "proposed"})


def decide(pdir: Path, cid: str, accept: bool, run_steps: Callable[[list[str]], None], regenerate: Callable[[str, int], None]) -> dict:
    """Accept (do it) or dismiss a proposed plan. run_steps starts the steps as one job; regenerate redoes one picture."""
    msgs = load(pdir)
    m = next((x for x in msgs if x["id"] == cid and x.get("plan")), None)
    if m is None or m.get("status") != "proposed":
        raise ChatError("that plan is not waiting for an answer")
    if not accept:
        m["status"] = "dismissed"
        _save(pdir, msgs)
        return m
    p = m["plan"]
    for n in p.get("notes") or []:
        notes.add(pdir, n["kind"], str(n.get("ref", "")), n["text"], notes.role_for(n["kind"], str(n.get("role") or "")), who="producer")
    if p.get("settings"):
        cur = production.load(pdir)
        production.save(pdir, {**cur, **p["settings"]})
    for r in p.get("regenerate") or []:
        regenerate(str(r.get("style", "")), int(r["row"]))
    if p.get("steps"):
        run_steps(list(p["steps"]))
    m["status"] = "accepted"
    _save(pdir, msgs)
    try:
        import history
        history.create(pdir, f"producer chat: {m['text'][:80]}", "chat")
    except (OSError, ValueError, RuntimeError):
        pass
    return m


def add_information(pdir: Path, text: str) -> dict:
    """ADD INFORMATION: a note every crew role reads in its next call (addressed to the producer, which every role's prompt includes)."""
    n = notes.add(pdir, "project", "everything", text, "producer")
    _add(pdir, {"who": "owner", "text": f"(added information) {n['messages'][0]['text']}"})
    return n


def say(pdir: Path, text: str) -> dict:
    return _add(pdir, {"who": "producer", "text": text})


def fake_ask() -> Ask:
    def ask(prompt: str, roles, step: str, validate: Callable[[dict], None]) -> dict:
        text = prompt.split('The owner wrote: "', 1)[1].split('"\n', 1)[0].lower()
        if "regenerate" in text:
            d: dict = {"reply": "I will make that picture again.", "simple": True, "steps": [], "notes": [], "settings": {}, "regenerate": [{"style": "", "row": 1}],
                       "estimate": "about 15 GPU seconds"}
        else:
            d = {"reply": "The director will rethink the villain's shots, then the shot list is written again.", "simple": False, "steps": ["shot_list"],
                 "notes": [{"kind": "character", "ref": "MARA", "role": "", "text": text}], "settings": {}, "regenerate": [], "estimate": "a few writing calls, $0"}
        validate(d)
        return d
    return ask
