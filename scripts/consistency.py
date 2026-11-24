#!/usr/bin/env python3
"""Style consistency check (BOOK_TO_SCREEN_BUILD.md Section 7.4d, milestone M7).

  python3 consistency.py <project> <style> [--engine claude|... |fake] [--model M]

The Script Supervisor (a vision call) compares every picture of a style with its approved master frame: character count and positions, poses,
framing, key props and the same visible action. Score 0-10. Below 7 the picture gets another try (a new seed; the old one is kept as a
version) and is listed for rendering again; after 3 tries it is flagged for the owner. Results: pictures/<style>/consistency.json.
The two pictures are sent as one side-by-side image (master on the left), so any vision engine can compare them.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crew  # noqa: E402
import layout  # noqa: E402
import pictures  # noqa: E402
import production  # noqa: E402

PASS_SCORE = 7
MAX_TRIES = 3
AskImage = Callable[[str, str | list[str], str, Callable[[dict], None], str], dict]


def path(pdir: Path, sid: str) -> Path:
    return pictures.pdir_of(pdir, sid) / "consistency.json"


def load(pdir: Path, sid: str) -> dict:
    return pictures._read(path(pdir, sid), {}) or {}


def check_reply(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("score"), (int, float)) or not 0 <= d["score"] <= 10:
        raise ValueError("'score' is a number from 0 to 10")
    if not isinstance(d.get("differences", []), list):
        raise ValueError("'differences' is a list of what does not match")


def side_by_side(a: Path, b: Path, dest: Path) -> Path:
    from PIL import Image
    with Image.open(a) as ia, Image.open(b) as ib:
        h = 512
        la = ia.convert("RGB").resize((max(1, round(ia.width * h / ia.height)), h))
        lb = ib.convert("RGB").resize((max(1, round(ib.width * h / ib.height)), h))
    out = Image.new("RGB", (la.width + lb.width + 16, h), (255, 255, 255))
    out.paste(la, (0, 0))
    out.paste(lb, (la.width + 16, 0))
    out.save(dest)
    return dest


PROMPT = ("The picture shows two frames side by side: on the LEFT the approved master frame of a film shot, on the RIGHT the same shot in "
          "another style. The styles are meant to differ; everything else must match. Compare: the number of characters and where they are, "
          "their poses and expressions, the framing and camera angle, the key props, and the visible action. Score 0-10 (10 = the same shot "
          'exactly, in another look). Reply as JSON: {"score": 8, "differences": ["..."]}')


def run(pdir: Path, sid: str, ask: AskImage, say: Callable[[str], None] = print) -> dict:
    master = production.load(pdir)["master"]
    if sid == master:
        raise pictures.PictureError("the master style is the reference: check the other styles")
    mst, st = pictures.status(pdir, master), pictures.status(pdir, sid)
    mdir, sdir = layout.find_dir(mst["set"]), layout.find_dir(st["set"]) if st["set"] else None
    if not st["shots"] or sdir is None or mdir is None:
        raise pictures.PictureError("make and render this style's pictures first")
    results = load(pdir, sid)
    todo = [s for s in st["shots"] if s["image"] and str(s["row"]) not in results or (s["image"] and results.get(str(s["row"]), {}).get("pending"))]
    with tempfile.TemporaryDirectory(prefix="studio-cmp-") as t:
        for i, s in enumerate(todo, 1):
            m = mst["shots"][s["row"] - 1]
            if not m["image"]:
                continue
            say(f"Your script supervisor is comparing shot {i} of {len(todo)} with the master frame")
            pair = side_by_side(mdir / m["image"], sdir / s["image"], Path(t) / f"pair-{s['row']}.png")
            d = ask(PROMPT, "script_supervisor", f"style consistency: {sid}", check_reply, str(pair))
            prev = results.get(str(s["row"]), {})
            tries = int(prev.get("tries", 0)) + 1
            r: dict = {"score": float(d["score"]), "differences": [str(x) for x in d.get("differences", [])][:10], "tries": tries,
                 "pending": False, "flagged": False}
            if r["score"] < PASS_SCORE:
                if tries < MAX_TRIES:
                    pictures.prepare_regenerate(pdir, sid, s["row"])
                    r["pending"] = True                     # rendered again with a new seed, then checked again
                else:
                    r["flagged"] = True                     # three tries: the owner decides
            results[str(s["row"])] = r
            pictures._write(path(pdir, sid), results)
    again = sorted(int(k) for k, v in results.items() if v.get("pending"))
    flagged = sorted(int(k) for k, v in results.items() if v.get("flagged"))
    say(f"Done: {len(results)} checked, {len(again)} to render again, {len(flagged)} flagged for you.")
    return {"checked": len(results), "again": again, "flagged": flagged}


def fake_ask(score_of: Callable[[str], float] | None = None) -> AskImage:
    def ask(prompt: str, roles, step: str, validate: Callable[[dict], None], image: str) -> dict:
        d: dict = {"score": score_of(image) if score_of else 8, "differences": []}
        validate(d)
        return d
    return ask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("style")
    ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex", "hf", "local", "fake"])
    ap.add_argument("--model", default=None)
    a = ap.parse_args(argv)
    pdir = layout.project_dir(a.project, "book")
    if not pdir.is_dir():
        print(f"no book called {a.project}", flush=True)
        return 1
    if a.engine == "fake":
        ask = fake_ask()
    else:
        import bookkit

        def ask(prompt, roles, step, validate, image):
            return bookkit.llm_json(prompt, crew.system(roles, pdir, step), model=a.model, engine=a.engine, validate=validate, image=image)
    try:
        print(json.dumps(run(pdir, a.style, ask, lambda t: print(t, flush=True))), flush=True)
    except (pictures.PictureError, RuntimeError, ValueError) as e:
        print(f"The check stopped: {e}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
