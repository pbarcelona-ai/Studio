#!/usr/bin/env python3
"""book2screen: the whole pipeline from a terminal (BOOK_TO_SCREEN_BUILD.md Section 11, milestone M15). No server or page needed.

  python scripts/book2screen.py make <source> [--name NAME] [--recipe vertical_microdrama] [--style claymation --style realistic]
                                [--product film --product audiobook] [--minutes 3] [--stop-at shotlist] [--engine claude|fake]
                                [--service kaggle --gpu NvidiaTeslaT4 --kaggle-user U] [--confirm-spend]
  python scripts/book2screen.py status NAME

<source> is a file (a book, a screenplay, pictures, video or sound), a web address (http/https) or, in quotes, an idea. By using it you confirm
you have the right to use it (the same rights tick as the page). `make` creates the book, adds the source, chooses the format, products and
styles, then runs Autopilot (autopilot.py) to the downloads, stopping where --stop-at says. Running it again with the same --name carries on.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import autopilot  # noqa: E402
import crew  # noqa: E402
import layout  # noqa: E402
import ledger  # noqa: E402
import production  # noqa: E402
import sources  # noqa: E402


def is_file(source: str) -> bool:
    """Is the source a file on this computer? (An idea is long text: on some systems asking about it as a path raises "name too long".)"""
    if len(source) > 1000 or "\n" in source:
        return False
    try:
        return Path(source).expanduser().is_file()
    except (OSError, ValueError):
        return False


def name_for(source: str) -> str:
    base = Path(source).stem if is_file(source) else (re.sub(r"^https?://(www\.)?", "", source).split("/")[0] if source.startswith(("http://", "https://")) else source)
    slug = re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_")[:40] or "film"
    return slug if len(slug) >= 2 else f"{slug}_film"


def add_source(pdir: Path, source: str) -> dict:
    if source.startswith(("http://", "https://")):
        with tempfile.TemporaryDirectory(prefix="b2s-web-") as t:
            doc, files = sources.from_url(source, Path(t))
            return sources.store(pdir, doc, True, files)
    p = Path(source).expanduser() if is_file(source) else None
    if p is not None:
        import shutil
        with tempfile.TemporaryDirectory(prefix="b2s-src-") as t:      # a copy: the source moves into the book, the original stays
            tmp = Path(t) / p.name
            shutil.copy2(p, tmp)
            return sources.store(pdir, sources.from_file(tmp), True, [tmp])
    return sources.store(pdir, sources.from_idea(source), True)


def make(a: argparse.Namespace) -> int:
    name = a.name or name_for(a.source)
    if not layout.SLUG_RE.match(name):
        print("--name is 2-40 lowercase letters, digits or _", flush=True)
        return 1
    pdir = layout.project_dir(name, "book")
    fresh = not pdir.is_dir() or not sources.load_index(pdir)
    pdir.mkdir(parents=True, exist_ok=True)
    try:
        if fresh:
            e = add_source(pdir, a.source)
            print(f"{name}: source {e['id']} ({e['kind']}: {e['title']})", flush=True)
            if a.recipe:
                crew.set_recipe(pdir, a.recipe.replace("-", "_"))
            settings = {}
            if a.product:
                settings["products"] = [p.replace("-", "_") for p in a.product]
            if a.style:
                settings["styles"] = [{"id": s.replace("-", "_")} for s in a.style]
            if a.minutes:
                settings["target_minutes"] = a.minutes
            st, notes = production.save(pdir, {**production.load(pdir), **settings})
            for n in notes:
                print(n, flush=True)
            est = production.estimate(st)
            print(f"About {est['shots']} shots, {est['gpu_hours']} GPU hours, ${est['dollars']:.2f}.", flush=True)
    except (sources.SourceError, ValueError) as e:
        print(f"Could not start: {e}", flush=True)
        return 1
    argv = [name, "--engine", a.engine] + (["--model", a.model] if a.model else []) + (["--stop-at", ",".join(a.stop_at)] if a.stop_at else [])
    argv += ["--service", a.service, "--gpu", a.gpu] + (["--kaggle-user", a.kaggle_user] if a.kaggle_user else []) + (["--confirm-spend"] if a.confirm_spend else [])
    return autopilot.main(argv)


def status(a: argparse.Namespace) -> int:
    pdir = layout.find_dir(a.name) if layout.SLUG_RE.match(a.name) else None
    if pdir is None:
        print(f"no project called {a.name}", flush=True)
        return 1
    import gates
    g = gates._load(pdir)
    ex = pdir / "exports"
    print(json.dumps({"project": pdir.name, "approved": sorted(g), "exports": sorted(p.name for p in ex.rglob("*") if p.is_file()) if ex.is_dir() else [],
                      "cost": ledger.report(pdir)}, indent=1), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="book2screen", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("source")
    m.add_argument("--name", default="")
    m.add_argument("--recipe", default="")
    m.add_argument("--style", action="append", default=[])
    m.add_argument("--product", action="append", default=[])
    m.add_argument("--minutes", type=float, default=0)
    m.add_argument("--stop-at", action="append", default=[], choices=list(autopilot.STOPS))
    m.add_argument("--engine", default="claude")
    m.add_argument("--model", default=None)
    m.add_argument("--service", default="kaggle", choices=[k for k in autopilot.LIMITS if k != "fake"])
    m.add_argument("--gpu", default="NvidiaTeslaT4")
    m.add_argument("--kaggle-user", default="")
    m.add_argument("--confirm-spend", action="store_true")
    s = sub.add_parser("status")
    s.add_argument("name")
    a = ap.parse_args(argv)
    return make(a) if a.cmd == "make" else status(a)


if __name__ == "__main__":
    sys.exit(main())
