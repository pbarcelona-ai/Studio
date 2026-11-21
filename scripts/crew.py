"""The film crew: every AI call is written by a named crew member, and every call follows the project's rules and format recipe.

  prompts/crew/<role>.md        who the crew member is, their job, their limits, their vocabulary and their self-check (one file per role)
  recipes/<name>.json           built-in format recipes (Feature film, Vertical microdrama, Picture book ...): products, aspect, length,
                                and extra prompt rules per crew role
  <book>/project_rules.json     {"body": "...", "rev": n, "updated": "..."}: the owner's rules ("Eve never wears red"), read on every call
  <book>/recipe.json            {"name": "<recipe>"}: the recipe this book is made with
  <book>/crew_log.jsonl         one line per AI call: time, role(s), step, a short hash of the role file(s), so a result can be traced

system(roles, book_dir, step) builds the system prompt for one call: the role file(s), then the step's own instructions, then the recipe's
rules for those roles, then the project rules, then "reply with JSON". The text it returns knows its roles; bookkit.llm_json calls its
record() once per call to write the crew log.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CREW_DIR = ROOT / "prompts" / "crew"
RECIPES_DIR = ROOT / "recipes"
ROLE_RE = re.compile(r"^[a-z][a-z_]{1,40}$")
RULES_MAX = 20_000
JSON_REPLY = "You reply with a single JSON object and nothing else."
STUDIO_CRAFT_STANDARDS = (
    "## Studio Craft & Narrative Flow Standards (apply to every department)\n"
    "- Act as a world-class film industry expert in your specific discipline.\n"
    "- Seamless Scene-by-Scene Flow: Ensure the story's translation from book to film flows smoothly and organically from scene to scene and shot to shot, with clear cause-and-effect, emotional momentum, and visual rhythm.\n"
    "- Parallel Storyline Jumps: Cutting between different storylines or subplots within the overall story is allowed whenever the narrative calls for it, provided every jump uses a smooth, motivated bridge (visual match-cut, audio L-cut/J-cut, dialogue/thematic echo, or clear establishing handoff) so the cut feels effortless rather than jarring.\n"
    "- Continuity Discipline: Keep character costumes exact and singular unless a scene explicitly changes wardrobe, keep matching locations consistent unless transitioning, and obey solid-object physics."
)
_RULES_LOCK = threading.Lock()                         # the server is threaded: check-then-write must not interleave


class RevConflict(Exception):
    """A save was based on an older version than the one on disk. Answered to the page as HTTP 409 (the conflict prompt)."""

    def __init__(self, current: int):
        super().__init__(f"this was changed since you opened it (now version {current}); reload to see the new version")
        self.current = current


# ---------------------------------------------------------------- roles
def roles() -> list[str]:
    """Every crew role that has a role file."""
    return sorted(p.stem for p in CREW_DIR.glob("*.md")) if CREW_DIR.is_dir() else []


def role_text(role: str) -> str:
    if not ROLE_RE.match(role or ""):
        raise ValueError(f"bad crew role name: {role!r}")
    path = CREW_DIR / f"{role}.md"
    if not path.is_file():
        raise ValueError(f"no crew role file for {role!r} (looked in prompts/crew/)")
    return path.read_text(encoding="utf-8").strip()


def role_title(role: str) -> str:
    """The role's display name: the first heading of its file."""
    first = role_text(role).splitlines()[0]
    return first.lstrip("# ").strip() or role


# ---------------------------------------------------------------- small file helpers
def _read(path: Path, default: dict) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else dict(default)
    except (OSError, ValueError):
        return dict(default)


def _write(path: Path, data: dict) -> None:
    """Write through a temp file so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------- project rules
def read_rules(book_dir: Path) -> dict:
    d = _read(Path(book_dir) / "project_rules.json", {"body": "", "rev": 0})
    try:
        rev = max(0, int(d.get("rev", 0) or 0))
    except (TypeError, ValueError):
        rev = 0
    return {"body": str(d.get("body", "")), "rev": rev, "updated": str(d.get("updated", ""))}


def write_rules(book_dir: Path, body: str, rev: int) -> dict:
    """Save the project rules. `rev` is the version the page read; if the file has moved on since, RevConflict (nothing is written)."""
    if not isinstance(body, str):
        raise ValueError("rules must be text")
    if len(body) > RULES_MAX:
        raise ValueError(f"the project rules are too long (at most {RULES_MAX} characters)")
    with _RULES_LOCK:
        cur = read_rules(book_dir)
        if int(rev) != cur["rev"]:
            raise RevConflict(cur["rev"])
        new = {"body": body.strip(), "rev": cur["rev"] + 1, "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        _write(Path(book_dir) / "project_rules.json", new)
    return new


# ---------------------------------------------------------------- recipes
def recipes() -> list[dict]:
    """The built-in recipes, each {"name", "title", "about", ...}, in a fixed order (feature film first)."""
    out = []
    for p in sorted(RECIPES_DIR.glob("*.json")) if RECIPES_DIR.is_dir() else []:
        d = _read(p, {})
        if d.get("name") == p.stem and d.get("title") and not recipe_problems(d):
            out.append(d)
    order = ["feature_film", "short_film", "vertical_microdrama", "picture_book", "animatic_pitch", "trailer_only", "audiobook_only", "music_video"]
    return sorted(out, key=lambda d: (order.index(d["name"]) if d["name"] in order else len(order), d["name"]))


RECIPE_PRODUCTS = {"screenplay", "storyboard", "illustrated_book", "animatic", "film", "audiobook", "marketing"}


def recipe_problems(d: dict) -> list[str]:
    """What is wrong with a recipe (Section 14: recipes are data, never code, checked against this schema). [] = it can be used."""
    out = []
    if not isinstance(d, dict):
        return ["a recipe is a JSON object"]
    for k in ("name", "title", "about", "aspect"):
        if not isinstance(d.get(k), str) or not d[k].strip():
            out.append(f"{k} must be text")
    if d.get("aspect") not in ("16:9", "9:16", "1:1", "4:3"):
        out.append("aspect must be 16:9, 9:16, 1:1 or 4:3")
    prods = d.get("products")
    if not isinstance(prods, list) or not prods or any(p not in RECIPE_PRODUCTS for p in prods):
        out.append(f"products must be some of {', '.join(sorted(RECIPE_PRODUCTS))}")
    tm = d.get("target_minutes")
    if not isinstance(tm, (int, float)) or isinstance(tm, bool) or not (tm == 0 or 0.5 <= tm <= 600):
        out.append("target_minutes must be 0 (the length follows the book) or a number from 0.5 to 600")
    if not isinstance(d.get("series", False), bool):
        out.append("series must be true or false")
    if d.get("quality_tier", "final") not in ("draft", "final"):
        out.append("quality_tier must be draft or final")
    rules = d.get("prompt_rules", {})
    if not isinstance(rules, dict) or any(not isinstance(k, str) or not isinstance(v, str) or len(v) > 2000 for k, v in rules.items()):
        out.append("prompt_rules maps a crew role to a short text")
    crit = d.get("critique", {})
    if not isinstance(crit, dict) or any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in crit.values()):
        out.append("critique holds numbers (min_score, max_rounds)")
    allowed = {"name", "title", "about", "aspect", "products", "target_minutes", "series", "quality_tier", "prompt_rules", "critique", "episode_minutes", "notes"}
    extra = sorted(set(d) - allowed)
    if extra:
        out.append(f"unknown keys: {', '.join(extra)}")
    return out


def recipe(name: str) -> dict:
    for d in recipes():
        if d["name"] == name:
            return d
    raise ValueError(f"no recipe called {name!r}")


def project_recipe(book_dir: Path) -> str:
    """The recipe name chosen for this book, or '' (none chosen: the Studio's normal film path)."""
    name = str(_read(Path(book_dir) / "recipe.json", {}).get("name", ""))
    return name if name in {d["name"] for d in recipes()} else ""


def set_recipe(book_dir: Path, name: str) -> dict:
    if name:
        recipe(name)                                      # refuses an unknown name
    _write(Path(book_dir) / "recipe.json", {"name": name})
    return {"name": name}


# ---------------------------------------------------------------- the system prompt
class CrewPrompt(str):
    """A system prompt that remembers which crew role(s) wrote it, for the crew log."""

    roles: tuple[str, ...]
    step: str
    book_dir: Path | None
    digest: str

    def record(self) -> None:
        """Append one line to <book>/crew_log.jsonl. Never raises: a log that cannot be written must not stop the call."""
        if not self.book_dir:
            return
        line = {"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "roles": list(self.roles), "step": self.step, "role_version": self.digest}
        try:
            with open(Path(self.book_dir) / "crew_log.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line) + "\n")
        except OSError:
            pass


def system(roles_: str | list[str], book_dir: Path | None = None, step: str = "", instructions: str = "", json_reply: bool = True) -> CrewPrompt:
    """The system prompt for one AI call written by `roles_` (one role, or several working together)."""
    names = [roles_] if isinstance(roles_, str) else list(roles_)
    if not names:
        raise ValueError("an AI call needs at least one crew role")
    texts = [role_text(r) for r in names]
    parts = []
    if len(names) > 1:
        parts.append("You are this film crew, working together on one task. Each member keeps to their own job:")
    parts += texts
    parts.append(STUDIO_CRAFT_STANDARDS)
    if instructions.strip():
        parts.append("## This task\n" + instructions.strip())
    if book_dir:
        name = project_recipe(Path(book_dir))
        if name:
            rec = recipe(name)
            rules = [f"- {rec['prompt_rules'][r]}" for r in names if rec.get("prompt_rules", {}).get(r)]
            parts.append(f"## Format: {rec['title']}\n{rec['about']} Aspect ratio {rec['aspect']}." + ("\n" + "\n".join(rules) if rules else ""))
        try:                                                # the rating is applied to every crew prompt (Section 14)
            rating = json.loads((Path(book_dir) / "production.json").read_text(encoding="utf-8")).get("rating", "")
        except (OSError, ValueError, AttributeError):
            rating = ""
        if rating:
            word = {"all": "All ages", "8": "8+", "13": "13+", "adult": "Adult"}.get(str(rating), "")
            if word:
                parts.append(f"## Rating\nThe film is rated {word}. Keep everything you write within that rating.")
        body = read_rules(Path(book_dir))["body"]
        if body:
            parts.append("## Project rules (the owner's; always follow them, and they win over anything above)\n" + body)
        try:
            import notes                                    # the owner's open notes for these roles (Section 3.4)
            text = notes.prompt_text(Path(book_dir), names)
        except (OSError, ValueError):
            text = ""
        if text:
            parts.append(text)
    if json_reply:
        parts.append(JSON_REPLY)
    out = CrewPrompt("\n\n".join(parts))
    out.roles = tuple(names)
    out.step = step
    out.book_dir = Path(book_dir) if book_dir else None
    out.digest = hashlib.sha256("\n".join(texts).encode()).hexdigest()[:12]
    return out


def log_tail(book_dir: Path, n: int = 50) -> list[dict]:
    """The last n crew-log lines (newest last)."""
    try:
        lines = (Path(book_dir) / "crew_log.jsonl").read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out
