#!/usr/bin/env python3
"""The marketing kit, Product G (BOOK_TO_SCREEN_BUILD.md Sections 1, 13; milestone M14), per style.

  python3 marketing.py <project> [--engine ... | fake] [--model M]        the Trailer Editor's plan (shots, words, poster, thumbnail)
  python3 marketing.py <project> --render STYLE                           cut and draw the kit in one style

The Trailer Editor (with the producer as Marketing Lead) chooses the shots for a trailer of 30-90 s, three vertical teasers of at most 30 s with
their captions, the poster's and the thumbnail's picture and words, the logline, a tagline and the social-post captions (marketing/plan.json,
shared by every style). render() cuts them from that style's film clips with the same renderer as the film (render_cut.py), so the kit
looks like the film:
  exports/marketing_<style>/trailer_16x9.mp4, trailer_9x16.mp4, teaser_1.mp4 .. teaser_3.mp4 (9:16, captions burned in),
  poster.png (2:3), thumbnail.png (16:9), captions.txt (logline, tagline, posts)
The kit needs the film (the trailer is cut from its clips): the style's clips must be approved.
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clips  # noqa: E402
import crew  # noqa: E402
import edl  # noqa: E402
import gates  # noqa: E402
import layout  # noqa: E402
import pictures  # noqa: E402
import render_cut  # noqa: E402

Ask = Callable[[str, str | list[str], str, Callable[[dict], None]], dict]


class MarketingError(RuntimeError):
    """The marketing kit cannot be made yet."""


def plan_path(pdir: Path) -> Path:
    return pdir / "marketing" / "plan.json"


def load(pdir: Path) -> dict:
    try:
        return json.loads(plan_path(pdir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _picks(x, rows: int, max_total: float, what: str) -> None:
    if not isinstance(x, list) or not x:
        raise ValueError(f"{what} lists shots as [{{\"row\": 1, \"seconds\": 2.5}}]")
    total = 0.0
    for p in x:
        if not isinstance(p, dict) or not isinstance(p.get("row"), int) or not 1 <= p["row"] <= rows:
            raise ValueError(f"{what}: every pick is a shot row from 1 to {rows}")
        if not isinstance(p.get("seconds"), (int, float)) or not 0.5 <= p["seconds"] <= 15:
            raise ValueError(f"{what}: every pick is 0.5-15 seconds long")
        total += float(p["seconds"])
    if total > max_total:
        raise ValueError(f"{what} is {total:.0f} s: keep it to {max_total:.0f} s")


def checker(rows: int) -> Callable[[dict], None]:
    def check(d) -> None:
        if not isinstance(d, dict):
            raise ValueError("reply with one JSON object")
        for k in ("logline", "tagline", "title"):
            if not str(d.get(k, "")).strip():
                raise ValueError(f"'{k}' is missing")
        _picks(d.get("trailer"), rows, 90, "the trailer")
        if sum(float(p["seconds"]) for p in d["trailer"]) < 30:
            raise ValueError("the trailer runs 30-90 seconds")
        teasers = d.get("teasers")
        if not isinstance(teasers, list) or len(teasers) != 3:
            raise ValueError("three teasers, each {\"shots\": [...], \"caption\": \"...\"}")
        for t in teasers:
            if not isinstance(t, dict) or not str(t.get("caption", "")).strip():
                raise ValueError("every teaser has shots and a caption")
            _picks(t.get("shots"), rows, 30, "a teaser")
        for k in ("poster", "thumbnail"):
            v = d.get(k)
            if not isinstance(v, dict) or not isinstance(v.get("row"), int) or not 1 <= v["row"] <= rows:
                raise ValueError(f"'{k}' is {{\"row\": 3, \"text\": \"...\"}}")
        if not isinstance(d.get("posts", []), list):
            raise ValueError("'posts' is a list of social-post captions")
    return check


def write_plan(pdir: Path, ask: Ask) -> dict:
    e = edl.load(pdir)
    if not e or not gates.approved(pdir, "edit", e["cuts"]):
        raise MarketingError("Approve the edit first: the trailer is cut from the film.")
    c = edl.cut(e, "main")
    vids = c["tracks"]["video"]
    listing = "\n".join(f"row {v['row']}: {v['scene']} shot {v['shot']}, {v['seconds']} s" for v in vids)
    try:
        readin = json.loads((pdir / "readin" / "coverage.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        readin = {}
    d = ask("Cut the marketing kit: a trailer of 30-90 s (pick shots by row, with how long each plays), three vertical teasers of at most 30 s "
            "each with a burned-in caption, the poster's shot and its text, the thumbnail's shot and its text, the title, a logline, a tagline and "
            "three social-post captions. Make people want to see the film, without giving the ending away. "
            'Reply as JSON: {"title": "...", "logline": "...", "tagline": "...", "trailer": [{"row": 1, "seconds": 2.5}], '
            '"teasers": [{"shots": [{"row": 2, "seconds": 3}], "caption": "..."}], "poster": {"row": 3, "text": "..."}, "thumbnail": {"row": 4, "text": "..."}, '
            f'"posts": ["..."]}}\n\nCOVERAGE: {json.dumps(readin, ensure_ascii=False)[:3000]}\n\nTHE FILM\'S SHOTS:\n{listing}',
            ["trailer_editor", "producer"], "marketing kit", checker(len(vids)))
    plan_path(pdir).parent.mkdir(parents=True, exist_ok=True)
    plan_path(pdir).write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    return d


def _cut_from(picks: list[dict], base: dict, name: str) -> dict:
    by_row = {v["row"]: v for v in base["tracks"]["video"]}
    vids = []
    for i, p in enumerate(picks):
        v = by_row[p["row"]]
        secs = min(float(p["seconds"]), float(v["seconds"]))   # never longer than the shot plays in the film (its clip may be no longer)
        vids.append({**v, "id": f"{name}{i:03d}", "seconds": secs, "transition": {"kind": "cut", "seconds": 0.0}})
    first = vids[0]["scene"] if vids else ""
    music = [m for m in base["tracks"]["music"] if m.get("whole")] or [m for m in base["tracks"]["music"] if m["attach"] == first][:1]
    music = [{**m, "whole": True} for m in music]
    return {"name": name, "tracks": {"video": vids, "voice": [], "music": music, "effects": []}, "volumes": {**base["volumes"], "music": 1.0}, "duck_db": 0.0}


def _srt(text: str, seconds: float) -> str:
    return f"1\n00:00:00,300 --> {edl._t(max(0.5, seconds - 0.2))}\n{text}\n"


def _poster(src: Path, dest: Path, size: tuple[int, int], title: str, text: str) -> Path:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    with Image.open(src) as im:
        art = ImageOps.fit(im.convert("RGB"), size)
    draw = ImageDraw.Draw(art)
    w, h = size

    def font(px: int):
        try:
            return ImageFont.load_default(size=px)
        except TypeError:                                    # an old Pillow without sizes
            return ImageFont.load_default()
    shade = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(shade).rectangle([0, int(h * 0.68), w, h], fill=(0, 0, 0, 150))
    art = Image.alpha_composite(art.convert("RGBA"), shade).convert("RGB")
    draw = ImageDraw.Draw(art)
    big = font(max(18, w // 11))
    draw.text((w // 2, int(h * 0.75)), title.upper(), font=big, fill=(255, 255, 255), anchor="mm")
    small = font(max(12, w // 26))
    for i, line in enumerate(textwrap.wrap(text, 34)[:3]):
        draw.text((w // 2, int(h * 0.83) + i * (w // 22)), line, font=small, fill=(235, 235, 235), anchor="mm")
    dest.parent.mkdir(parents=True, exist_ok=True)
    art.save(dest)
    return dest


def render(pdir: Path, sid: str, sizes: dict | None = None) -> dict:
    """Cut and draw the kit in one style. sizes can shrink everything (tests)."""
    p = load(pdir)
    if not p:
        raise MarketingError("Write the marketing plan first.")
    if not gates.approved(pdir, clips.gate_step(pdir, sid), clips.gate_data(pdir, sid)):
        raise MarketingError(f"Approve the {sid} clips first: the kit is cut from the film's clips.")
    sz = {"wide": (1920, 1080), "tall": (1080, 1920), "poster": (1200, 1800), "thumb": (1280, 720), **(sizes or {})}
    base = edl.cut(edl.load(pdir), "main")
    folder = f"marketing_{sid}"
    out = pdir / "exports" / folder
    out.mkdir(parents=True, exist_ok=True)
    made = []
    trailer = _cut_from(p["trailer"], base, "trailer")
    for name, size in (("trailer_16x9.mp4", sz["wide"]), ("trailer_9x16.mp4", sz["tall"])):
        f = render_cut.render(pdir, sid, "film", size=size, cut=trailer, out_name=f"{folder}/{name}", srt_text="")
        made.append(f.name)
    for i, t in enumerate(p["teasers"], 1):
        cut = _cut_from(t["shots"], base, f"teaser{i}")
        secs = sum(v["seconds"] for v in cut["tracks"]["video"])
        f = render_cut.render(pdir, sid, "film", size=sz["tall"], subtitles=True, cut=cut, out_name=f"{folder}/teaser_{i}.mp4", srt_text=_srt(t["caption"], secs))
        made.append(f.name)
    st = pictures.status(pdir, sid)
    setdir = layout.find_dir(st["set"])
    by_row = {s["row"]: s for s in st["shots"]}
    for key, fname, size in (("poster", "poster.png", sz["poster"]), ("thumbnail", "thumbnail.png", sz["thumb"])):
        s = by_row.get(p[key]["row"])
        if s is None or setdir is None or not s["image"]:
            raise MarketingError(f"the {key}'s shot has no picture in this style")
        _poster(setdir / s["image"], out / fname, size, p["title"], p[key].get("text", ""))
        made.append(fname)
    (out / "captions.txt").write_text("\n\n".join([f"TITLE: {p['title']}", f"LOGLINE: {p['logline']}", f"TAGLINE: {p['tagline']}"]
                                                  + [f"TEASER {i}: {t['caption']}" for i, t in enumerate(p["teasers"], 1)]
                                                  + [f"POST {i}: {x}" for i, x in enumerate(p.get("posts", []), 1)]) + "\n", encoding="utf-8")
    made.append("captions.txt")
    return {"folder": f"exports/{folder}", "files": made}


def fake_ask() -> Ask:
    def ask(prompt: str, roles, step: str, validate: Callable[[dict], None]) -> dict:
        import re
        rows = [int(m) for m in re.findall(r"^row (\d+):", prompt, re.M)]
        per = max(0.5, min(15.0, 36.0 / max(1, len(rows))))
        d = {"title": "The Door in the Sea", "logline": "A keeper finds a door.", "tagline": "Some doors should stay shut.",
             "trailer": [{"row": r, "seconds": per} for r in rows], "teasers": [{"shots": [{"row": rows[i % len(rows)], "seconds": 2}], "caption": f"Teaser {i + 1}"} for i in range(3)],
             "poster": {"row": rows[0], "text": "Coming soon"}, "thumbnail": {"row": rows[-1], "text": "Watch now"}, "posts": ["Out now.", "The sea is calling.", "Open the door."]}
        validate(d)
        return d
    return ask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--render", default="")
    ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex", "hf", "local", "fake"])
    ap.add_argument("--model", default=None)
    a = ap.parse_args(argv)
    pdir = layout.project_dir(a.project, "book")
    try:
        if a.render:
            print(f"Your trailer editor is cutting the {a.render} marketing kit", flush=True)
            out = render(pdir, a.render)
        else:
            if a.engine == "fake":
                ask = fake_ask()
            else:
                import bookkit

                def ask(prompt, roles, step, validate):
                    return bookkit.llm_json(prompt, crew.system(roles, pdir, step), model=a.model, engine=a.engine, validate=validate)
            print("Your trailer editor and marketing lead are planning the kit", flush=True)
            out = write_plan(pdir, ask)
        print(f"Done: {json.dumps(out, ensure_ascii=False)[:300]}", flush=True)
    except (MarketingError, render_cut.RenderError, edl.EditError, RuntimeError, ValueError) as e:
        print(f"The marketing kit was not made: {e}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
