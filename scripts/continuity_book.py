#!/usr/bin/env python3
"""The continuity book from the screenplay (BOOK_TO_SCREEN_BUILD.md Sections 6 and 7.2, milestone M4).

  python3 continuity_book.py <project> [--engine claude|... |fake] [--model M]

The Script Supervisor, the Casting Director and the Production Designer read the screenplay that Read it in wrote (readin/screenplay.json:
scenes and their hidden blocks) and the coverage, and write the continuity book into the book's <book>.json (the file every later step reads):

  characters  {name, token, voice, personality: {temperament, motivation, speech, mannerisms, movement}, stages?}
  locations   {name, token}        props {name, token}
Tokens are STYLE-NEUTRAL: identity only (age, build, height relative to the others, face shape, hair shape and colour, eye colour, skin tone,
outfit cut and colours, one distinctive feature), never rendering words ("photorealistic", "clay", "3D" ...): each style's look is added
later by its style card (M5). The previous file is kept as <book>.json.bak. The owner then reviews and approves it (gates.py).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crew  # noqa: E402
from bookkit import VOICE_MAP, continuity_file  # noqa: E402

TOKEN_MAX = 260
PERSONALITY = ("temperament", "motivation", "speech", "mannerisms", "movement")
STYLE_WORDS = re.compile(r"(?i)\b(photo-?realistic|photoreal|hyper-?realistic|claymation|plasticine|3d|cgi|pixar|anime|manga|cartoon\w*|"
                         r"watercolou?r|oil[- ]painting|illustrat\w*|render\w*|cel[- ]shad\w*|stop[- ]motion|noir|black[- ]and[- ]white|comic[- ]book|"
                         r"sketch\w*|storybook|unreal engine|octane)\b")   # rendering words only: "a clay pot" or "a felt hat" are identity
Ask = Callable[[str, str | list[str], str, Callable[[dict], None]], dict]


class ContinuityError(RuntimeError):
    """The continuity book cannot be written; the message says why."""


def style_words(text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in STYLE_WORDS.finditer(text or "")})


def check(d) -> None:
    if not isinstance(d, dict):
        raise ValueError("reply with one JSON object")
    chars = d.get("characters")
    if not isinstance(chars, list) or not chars:
        raise ValueError("'characters' must list every character who appears")
    for kind in ("characters", "locations", "props"):
        for c in d.get(kind, []) or []:
            if not isinstance(c, dict) or not str(c.get("name", "")).strip() or not str(c.get("token", "")).strip():
                raise ValueError(f"every item of '{kind}' needs a name and a token")
            if len(c["token"]) > TOKEN_MAX:
                raise ValueError(f"the token of {c['name']} is too long ({len(c['token'])} characters; keep it under 200)")
            bad = style_words(c["token"])
            if bad:
                raise ValueError(f"the token of {c['name']} uses rendering words ({', '.join(bad)}): describe identity only, the style is added later")
    for c in chars:
        if c.get("voice") not in VOICE_MAP:
            raise ValueError(f"the voice of {c['name']} must be one of {', '.join(sorted(VOICE_MAP))}")
        p = c.get("personality")
        if not isinstance(p, dict) or any(not str(p.get(k, "")).strip() for k in PERSONALITY):
            raise ValueError(f"{c['name']} needs a personality with {', '.join(PERSONALITY)}")


def material(pdir: Path) -> str:
    rd = pdir / "readin"
    try:
        sp = json.loads((rd / "screenplay.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ContinuityError("There is no screenplay yet: press Read it in first.") from None
    try:
        cov = json.loads((rd / "coverage.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cov = {}
    lines = []
    for i, s in enumerate(sp.get("scenes", []), 1):
        b = s.get("block", {})
        lines.append(f"{i}. {s['heading']} | characters: {', '.join(b.get('characters', []))} | props: {', '.join(b.get('props', []))} | "
                     f"wardrobe: {'; '.join(b.get('wardrobe', []))} | {b.get('time_of_day', '')}")
        lines += [("  " + e.get("character", "") + ": " if e["type"] == "dialogue" else "  ") + e["text"] for e in s["elements"]][:14]
    return f"COVERAGE:\n{json.dumps(cov, ensure_ascii=False)}\n\nSCREENPLAY (with each scene's block):\n" + "\n".join(lines)


PROMPT = """Write the continuity book for this film from its screenplay: every character who appears, every location and every prop that
matters, described so they look the same in every picture of every style.
Tokens describe IDENTITY, never rendering: age, build, height relative to the others, face shape, hair shape and colour, eye colour, skin tone,
outfit cut and colours, one distinctive feature. Never use words such as photorealistic, clay, 3D, anime, cartoon, painted: the style is
added later. Each token is self-contained (it is pasted into prompts on its own), under 200 characters.
Every character also gets a personality profile (temperament, motivation, speech patterns, mannerisms, how they move) for the director, the
actors and the voice director, and a narration voice: one of {voices}. Add "stages" only for a character who visibly ages.
Reply as JSON: {{"title": "...", "setting": "era, region, world", "music_theme": "instruments, mood, tempo",
 "characters": [{{"name": "MARA", "token": "...", "voice": "female", "personality": {{"temperament": "...", "motivation": "...", "speech": "...",
   "mannerisms": "...", "movement": "..."}}}}],
 "locations": [{{"name": "the lighthouse", "token": "..."}}], "props": [{{"name": "the brass lamp", "token": "..."}}]}}

{material}"""


def write(pdir: Path, ask: Ask) -> dict:
    d = ask(PROMPT.format(voices=", ".join(sorted(VOICE_MAP)), material=material(pdir)), ["script_supervisor", "casting_director", "production_designer"],
            "continuity book", check)
    f = continuity_file(pdir)
    old: dict = {}
    if f.is_file():
        shutil.copy2(f, f.with_suffix(".json.bak"))
        try:
            old = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            old = {}
    book = {**old, "title": d.get("title") or old.get("title", ""), "setting": d.get("setting", old.get("setting", "")),
            "music_theme": d.get("music_theme", old.get("music_theme", "")), "visual_style": old.get("visual_style", ""),
            "characters": [{k: v for k, v in c.items() if k in ("name", "token", "voice", "personality", "stages")} for c in d["characters"]],
            "locations": [{"name": c["name"], "token": c["token"]} for c in d.get("locations", [])],
            "props": [{"name": c["name"], "token": c["token"]} for c in d.get("props", [])], "style_neutral": True}
    f.write_text(json.dumps(book, indent=1, ensure_ascii=False), encoding="utf-8")
    return book


def load(pdir: Path) -> dict:
    try:
        return json.loads(continuity_file(pdir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def edit(pdir: Path, kind: str, name: str, fields: dict) -> dict:
    """Change one character / location / prop by hand (token, voice, personality ...); the same checks apply."""
    book = load(pdir)
    if kind not in ("characters", "locations", "props"):
        raise ValueError("kind is characters, locations or props")
    items = book.get(kind, [])
    item = next((c for c in items if c.get("name") == name), None)
    if item is None:
        raise ValueError(f"no {kind[:-1]} called {name!r}")
    allowed = {"token", "voice", "personality"} if kind == "characters" else {"token"}
    new = {**item, **{k: v for k, v in fields.items() if k in allowed}}
    check({"characters": [new]} if kind == "characters" else {"characters": [_dummy()], kind: [new]})
    items[items.index(item)] = new
    continuity_file(pdir).write_text(json.dumps(book, indent=1, ensure_ascii=False), encoding="utf-8")
    return new


def _dummy() -> dict:
    return {"name": "x", "token": "x", "voice": "narrator", "personality": dict.fromkeys(PERSONALITY, "x")}


def _clean_token(text: str, fallback: str) -> str:
    cleaned = STYLE_WORDS.sub("", str(text or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-")
    if not cleaned:
        cleaned = fallback
    return cleaned[:195]


def bootstrap_from_readin(pdir: Path) -> dict:
    """Instantly build a valid, style-neutral continuity book from existing readin/coverage.json & screenplay.json."""
    rd = pdir / "readin"
    cov = {}
    sp = {}
    try:
        cov = json.loads((rd / "coverage.json").read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        cov = {}
    try:
        sp = json.loads((rd / "screenplay.json").read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        sp = {}

    chars_by_key: dict[str, dict] = {}
    for c in cov.get("characters", []) or []:
        if not isinstance(c, dict) or not str(c.get("name", "")).strip():
            continue
        name = str(c["name"]).strip()
        desc = str(c.get("description") or c.get("role") or name)
        low = desc.lower()
        voice = "female" if any(w in low for w in ("woman", "girl", "mom", "mother", "she ", "her ")) else "male"
        if voice not in VOICE_MAP:
            voice = "narrator"
        chars_by_key[name.lower()] = {
            "name": name,
            "token": _clean_token(desc, f"{name}, distinctive character"),
            "voice": voice,
            "personality": {
                "temperament": str(c.get("role") or "expressive, consistent"),
                "motivation": "follows the story arc",
                "speech": "natural dialogue",
                "mannerisms": "characteristic posture and gestures",
                "movement": "clear, purposeful movement",
            },
        }

    locs_by_key: dict[str, dict] = {}
    props_by_key: dict[str, dict] = {}
    for s in sp.get("scenes", []) or []:
        heading = str(s.get("heading") or "").strip()
        if heading:
            m = re.match(r"^(?:INT\.\/EXT\.|EXT\.\/INT\.|INT\.|EXT\.)\s*(.+?)(?:\s*-\s*(.+))?$", heading, re.I)
            loc_name = (m.group(1).strip() if m else heading)[:80]
            if loc_name and loc_name.lower() not in locs_by_key:
                tod = (m.group(2).strip() if m and m.group(2) else "")
                locs_by_key[loc_name.lower()] = {
                    "name": loc_name,
                    "token": _clean_token(f"{loc_name}, {tod}" if tod else loc_name, loc_name),
                }
        blk = s.get("block") or {}
        for cname in blk.get("characters", []) or []:
            cn = str(cname).strip()
            if cn and cn.lower() not in chars_by_key:
                chars_by_key[cn.lower()] = {
                    "name": cn,
                    "token": _clean_token(f"{cn}, recurring character", cn),
                    "voice": "narrator",
                    "personality": dict.fromkeys(PERSONALITY, "consistent with screenplay"),
                }
        for pname in blk.get("props", []) or []:
            pn = str(pname).strip()
            if pn and pn.lower() not in props_by_key:
                props_by_key[pn.lower()] = {"name": pn, "token": _clean_token(pn, pn)}

    if not chars_by_key:
        raise ContinuityError("No characters found in readin/coverage.json or screenplay.json yet. Run Read it in first.")

    book = {
        "title": pdir.name.replace("_", " ").title(),
        "setting": _clean_token(str(cov.get("genre") or cov.get("tone") or "story world"), "story world"),
        "music_theme": _clean_token(str(cov.get("tone") or "cinematic score"), "cinematic score"),
        "visual_style": "",
        "characters": list(chars_by_key.values()),
        "locations": list(locs_by_key.values()),
        "props": list(props_by_key.values()),
        "style_neutral": True,
    }
    check(book)
    f = continuity_file(pdir)
    if f.is_file():
        shutil.copy2(f, f.with_suffix(".json.bak"))
    f.write_text(json.dumps(book, indent=1, ensure_ascii=False), encoding="utf-8")
    return book


def fake_ask(pdir: Path) -> Ask:
    def ask(prompt: str, roles, step: str, validate: Callable[[dict], None]) -> dict:
        names = sorted({n for n in re.findall(r"characters: ([^|]+)", prompt) for n in [x.strip() for x in n.split(",")] if n}) or ["MARA"]
        places = sorted({m.strip().lower() for m in re.findall(r"\d+\. (?:INT|EXT)\.? ([^|]+?) -", prompt)}) or ["the lighthouse"]
        d = {"title": pdir.name.replace("_", " ").title(), "setting": "a northern coast, today", "music_theme": "solo cello, slow",
             "characters": [{"name": n, "token": f"{n.title()}, a woman in her thirties, tall and lean, oval face, short black hair, grey eyes, "
                             "olive skin, navy wool coat, a thin scar on the chin", "voice": "female",
                             "personality": {"temperament": "quiet, stubborn", "motivation": "keep the light burning", "speech": "few words, dry",
                                             "mannerisms": "rubs the scar when thinking", "movement": "slow, sure steps"}} for n in names],
             "locations": [{"name": p, "token": f"{p}: white stone walls, narrow stairs, salt-stained windows"} for p in places],
             "props": [{"name": "the lamp", "token": "a brass oil lamp with a green glass chimney"}]}
        validate(d)
        return d
    return ask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex", "hf", "local", "fake"])
    ap.add_argument("--model", default=None)
    a = ap.parse_args(argv)
    from layout import project_dir
    pdir = project_dir(a.project, "book")
    if not pdir.is_dir():
        print(f"no book called {a.project}", flush=True)
        return 1
    if a.engine == "fake":
        ask = fake_ask(pdir)
    else:
        import bookkit

        def ask(prompt, roles, step, validate):
            return bookkit.llm_json(prompt, crew.system(roles, pdir, step), model=a.model, engine=a.engine, validate=validate)
    try:
        print("Your script supervisor, casting director and production designer are writing the continuity book", flush=True)
        book = write(pdir, ask)
    except (ContinuityError, RuntimeError) as e:
        print(f"The continuity book was not written: {e}", flush=True)
        return 1
    print(f"Done: {len(book['characters'])} characters, {len(book['locations'])} locations, {len(book['props'])} props.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
