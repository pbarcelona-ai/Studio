#!/usr/bin/env python3
"""Episodes and series (BOOK_TO_SCREEN_BUILD.md Section 6e, milestone M14).

  python3 series.py <project> [--episodes N] [--engine claude|... |fake] [--model M]       split the book into episodes

Any book can be a SERIES. The Development Executive splits it into episodes of the recipe's length, each with its own hook, arc and cliffhanger
and a "previously on" recap. Each episode is a book of its own, <book>_e01, <book>_e02 ... (its own screenplay, shot list, clips and edit),
made from its part of the source. The continuity book, style cards, voices and the format settings are the SERIES' and are shared: sync()
copies them from the series to an episode (the series stays the one to edit), and the picture library of the whole series is searched together.

  projects/books/<book>/series/episodes.json   {"episodes": [{n, slug, title, summary, hook, cliffhanger, recap, parts}]}
  projects/books/<book>_eNN/series.json         {"series": <book>, "n": N}
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crew  # noqa: E402
import layout  # noqa: E402
import production  # noqa: E402
import sources  # noqa: E402
from bookkit import continuity_file  # noqa: E402

MAX_EPISODES = 40
Ask = Callable[[str, str | list[str], str, Callable[[dict], None]], dict]


class SeriesError(RuntimeError):
    """The series step cannot be done as asked."""


def episodes_file(pdir: Path) -> Path:
    return pdir / "series" / "episodes.json"


def load(pdir: Path) -> dict:
    try:
        return json.loads(episodes_file(pdir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def series_of(pdir: Path) -> Path | None:
    """The series book an episode belongs to (or None)."""
    try:
        name = json.loads((pdir / "series.json").read_text(encoding="utf-8"))["series"]
    except (OSError, ValueError, KeyError):
        return None
    found = layout.find_dir(name) if layout.SLUG_RE.match(str(name)) else None
    return found


def slug_of(pdir: Path, n: int) -> str:
    return f"{pdir.name[:36]}_e{n:02d}"


def check_split(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("episodes"), list) or not d["episodes"]:
        raise ValueError('reply with {"episodes": [{"title": "...", "summary": "...", "hook": "...", "cliffhanger": "...", "recap": "...", "parts": [1, 2]}]}')
    if len(d["episodes"]) > MAX_EPISODES:
        raise ValueError(f"at most {MAX_EPISODES} episodes")
    for e in d["episodes"]:
        if not isinstance(e, dict) or not all(str(e.get(k, "")).strip() for k in ("title", "summary", "hook", "cliffhanger")):
            raise ValueError("every episode needs title, summary, hook and cliffhanger")
        if not isinstance(e.get("parts", []), list):
            raise ValueError("'parts' lists the chapter numbers (or source parts) the episode is made from")


def _parts(pdir: Path) -> list[tuple[str, str]]:
    """The source, in numbered parts (its chapters when it has them, else pieces of the merged sources)."""
    idx = pdir / "chapters.json"
    if idx.is_file():
        chs = json.loads(idx.read_text(encoding="utf-8")).get("chapters", [])
        out = [(c.get("title", f"Chapter {c['n']}"), (pdir / "chapters" / f"chapter-{c['n']:03d}.txt").read_text(encoding="utf-8"))
               for c in chs if (pdir / "chapters" / f"chapter-{c['n']:03d}.txt").is_file()]
        if out:
            return out
    return [(f"Part {i + 1}", c) for i, c in enumerate(sources.chunks(sources.merged_text(pdir), 3000, 0))]


def split(pdir: Path, ask: Ask, episodes: int = 0, say: Callable[[str], None] = print) -> dict:
    parts = _parts(pdir)
    if not parts:
        raise SeriesError("Add a source first: there is nothing to split into episodes.")
    st = production.load(pdir)
    say("Your development executive is splitting the story into episodes")
    listing = "\n".join(f"{i}. {t}: {' '.join(b.split()[:120])}" for i, (t, b) in enumerate(parts, 1))
    d = ask(f"Split this story into {'about ' + str(episodes) if episodes else 'the right number of'} episodes of about {st['target_minutes']} minutes "
            "each. Each episode has its own hook, arc and cliffhanger, and a short 'previously on' recap of what came before (empty for the first). "
            "Say which numbered parts of the source each episode is made from. Reply as JSON: {\"episodes\": [{\"title\": \"...\", \"summary\": \"...\", "
            "\"hook\": \"...\", \"cliffhanger\": \"...\", \"recap\": \"...\", \"parts\": [1, 2]}]}\n\n" + listing,
            "development_executive", "series: episodes", check_split)
    out = []
    for n, e in enumerate(d["episodes"], 1):
        slug = slug_of(pdir, n)
        ed = layout.find_dir(slug) or layout.new_dir(slug, "book")
        ed.mkdir(parents=True, exist_ok=True)
        (ed / "series.json").write_text(json.dumps({"series": pdir.name, "n": n}), encoding="utf-8")
        picked = [parts[i - 1] for i in e.get("parts", []) if isinstance(i, int) and 1 <= i <= len(parts)]
        text = "\n\n".join(filter(None, [f"Previously: {e['recap']}" if e.get("recap") else "", f"This episode: {e['summary']}",
                                         f"It opens on: {e['hook']}. It ends on: {e['cliffhanger']}."] + [f"=== {t} ===\n{b}" for t, b in picked]))
        if not sources.load_index(ed):
            sources.store(ed, sources.SourceDocument("idea", f"Episode {n}: {e['title']}", text, rights_note="part of the series' own sources"), True)
        sync(ed)
        out.append({"n": n, "slug": slug, **{k: str(e.get(k, "")) for k in ("title", "summary", "hook", "cliffhanger", "recap")},
                    "parts": [i for i in e.get("parts", []) if isinstance(i, int)]})
    data = {"episodes": out}
    episodes_file(pdir).parent.mkdir(parents=True, exist_ok=True)
    episodes_file(pdir).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return data


SHARED = ("production.json", "recipe.json", "project_rules.json")
SHARED_DIRS = ("styles",)


def sync(ep: Path) -> list[str]:
    """Copy the series' shared parts (format settings, rules, continuity book, style cards and look development, the voice cast) into an episode."""
    s = series_of(ep)
    if s is None:
        raise SeriesError("this book is not an episode of a series")
    done = []
    for name in SHARED:
        if (s / name).is_file():
            shutil.copy2(s / name, ep / name)
            done.append(name)
    if continuity_file(s).is_file():
        shutil.copy2(continuity_file(s), continuity_file(ep))
        done.append("continuity book")
    for name in SHARED_DIRS:
        if (s / name).is_dir():
            shutil.rmtree(ep / name, ignore_errors=True)
            shutil.copytree(s / name, ep / name)
            done.append(name)
    try:                                                      # the series' approvals of the shared parts hold for the episode too
        g = json.loads((s / "gates.json").read_text(encoding="utf-8"))
        mine = json.loads((ep / "gates.json").read_text(encoding="utf-8")) if (ep / "gates.json").is_file() else {}
        mine.update({k: v for k, v in g.items() if k in ("continuity", "lookdev")})
        (ep / "gates.json").write_text(json.dumps(mine, indent=1), encoding="utf-8")
    except (OSError, ValueError):
        pass
    plan = s / "sound" / "plan.json"
    if plan.is_file():                                        # the voices are the series': the cast and narrator, not the episode's lines
        cast = {k: v for k, v in json.loads(plan.read_text(encoding="utf-8")).items() if k in ("cast", "narrator")}
        (ep / "sound").mkdir(exist_ok=True)
        (ep / "sound" / "series_cast.json").write_text(json.dumps(cast, indent=1, ensure_ascii=False), encoding="utf-8")
        done.append("voices")
    return done


def next_episode(pdir: Path) -> dict | None:
    """The first episode without a screenplay yet (for "Make next episode")."""
    for e in load(pdir).get("episodes", []):
        d = layout.find_dir(e["slug"])
        if d is None or not (d / "readin" / "summary.json").is_file():
            return e
    return None


def fake_ask() -> Ask:
    def ask(prompt: str, roles, step: str, validate: Callable[[dict], None]) -> dict:
        import re
        nums = [int(m) for m in re.findall(r"^(\d+)\. ", prompt, re.M)] or [1]
        half = max(1, len(nums) // 2)
        groups = [nums[:half], nums[half:]] if len(nums) > 1 else [nums]
        d = {"episodes": [{"title": f"Part {i + 1}", "summary": f"what happens in part {i + 1}", "hook": "a door in the sea", "cliffhanger": "the door closes",
                           "recap": "" if i == 0 else "Mara found the door.", "parts": g} for i, g in enumerate(groups)]}
        validate(d)
        return d
    return ask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--episodes", type=int, default=0)
    ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex", "hf", "local", "fake"])
    ap.add_argument("--model", default=None)
    a = ap.parse_args(argv)
    pdir = layout.project_dir(a.project, "book")
    if a.engine == "fake":
        ask = fake_ask()
    else:
        import bookkit

        def ask(prompt, roles, step, validate):
            return bookkit.llm_json(prompt, crew.system(roles, pdir, step), model=a.model, engine=a.engine, validate=validate)
    try:
        d = split(pdir, ask, max(0, min(MAX_EPISODES, a.episodes)), lambda t: print(t, flush=True))
        print(f"Done: {len(d['episodes'])} episodes ({', '.join(e['slug'] for e in d['episodes'])}).", flush=True)
    except (SeriesError, sources.SourceError, RuntimeError, ValueError) as e:
        print(f"The series was not split: {e}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
