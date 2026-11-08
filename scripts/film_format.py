#!/usr/bin/env python3
"""Set a book's film format: the shape of its clips and whether shots that continue the action start from the shot before.

  python3 film_format.py <book> [--aspect 16:9|2.39:1|4:3|1:1|9:16|model] [--chain on|off]

Saved in film_format.json and written into all_shots.csv and all_chapters.csv (aspect and chain columns), which the video notebooks read. "model" means
each video model's own shape. An option left out stays as it was.
"""
import argparse, sys
from bookkit import ASPECTS, apply_film_format, project_dir

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("book")
ap.add_argument("--aspect", choices=[*ASPECTS, "model"])
ap.add_argument("--chain", choices=["on", "off"])
a = ap.parse_args()
try:
    pdir = project_dir(a.book)
except ValueError as e:
    sys.exit(str(e))
if not pdir.is_dir():
    sys.exit(f"no such book: {a.book}")
fmt = apply_film_format(pdir, aspect=None if a.aspect is None else ("" if a.aspect == "model" else a.aspect),
                        chain=None if a.chain is None else a.chain == "on")
print(f"film shape: {fmt['aspect'] or 'each model its own'}; continue shots from the one before: {'on' if fmt['chain'] else 'off'}")
