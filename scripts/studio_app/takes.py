"""Storyboard and takes: re-take a shot, pick the take to keep."""
import csv
import os
import re
from bookkit import SLUG_RE, read_json
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .common import PlanError
from .projects import read_csv_rows
from .single_prompts import FACE_CHECK_FILE


def storyboard(slug, start, end):
    """One card per shot row start..end: chapter, prompt, narration, and the keyframes and clips that exist for it (paths under the project)."""
    d = pdir(slug)
    if not SLUG_RE.match(slug) or not d.is_dir():
        raise PlanError("pick a book first")
    shots = read_csv_rows(d / "all_shots.csv")
    if not shots:
        raise PlanError("no shots yet: build the CSVs first")
    audio = read_csv_rows(d / "audio_shots.csv")
    start = max(1, start); end = min(len(shots), end, start + 199)         # at most 200 cards at once
    kdirs = sorted(p for p in (d / "images").glob("*_keyframes") if p.is_dir()) if (d / "images").is_dir() else []
    vdirs = sorted(p for p in (d / "videos").glob("*") if p.is_dir() and not p.name.endswith("_chapters")) if (d / "videos").is_dir() else []
    cards = []
    for n in range(start, end + 1):
        r, a = shots[n - 1], (audio[n - 1] if n <= len(audio) else {})
        cards.append({"n": n, "chapter": r.get("chapter", ""), "shot": r.get("shot", ""), "prompt": r.get("prompt", ""),
                      "characters": [c for c in (r.get("characters") or "").split("|") if c],
                      "narration": a.get("narration", ""),
                      "keyframes": {k.name.removesuffix("_keyframes"): f"images/{k.name}/image-{n:04d}.png" for k in kdirs if (k / f"image-{n:04d}.png").is_file()},
                      "clips": {v.name: f"videos/{v.name}/shot-{n:04d}.mp4" for v in vdirs if (v / f"shot-{n:04d}.mp4").is_file()},
                      "takes": {**{f"clip:{v.name}": take_files(v, "shot", n, ".mp4", d) for v in vdirs},
                                **{f"keyframe:{k.name.removesuffix('_keyframes')}": take_files(k, "image", n, ".png", d) for k in kdirs}}})
    for c in cards:
        c["takes"] = {k: v for k, v in c["takes"].items() if v}
    faces = (read_json(d / FACE_CHECK_FILE, {}) or {}).get("rows", {})
    for c in cards:
        c["face"] = faces.get(str(c["n"]))
    return {"rows": len(shots), "start": start, "end": end, "cards": cards,
            "keyframe_models": [k.name.removesuffix("_keyframes") for k in kdirs]}


TAKE_KINDS = {"clip": ("videos", "shot", ".mp4"), "keyframe": ("images", "image", ".png")}


def take_files(folder, stem, n, ext, root):
    """Saved earlier versions (takes) of one shot, oldest first, as paths under the project: <folder>/takes/<stem>-NNNN-tK<ext>."""
    t = folder / "takes"
    if not t.is_dir():
        return []
    found = sorted(t.glob(f"{stem}-{n:04d}-t*{ext}"), key=lambda p: int(p.stem.rsplit("-t", 1)[1] or 0) if p.stem.rsplit("-t", 1)[1].isdigit() else 0)
    return [p.relative_to(root).as_posix() for p in found]


def take_target(body):
    """(project dir, output folder, stem, extension, shot number) for a retake or pick request, with every part validated."""
    slug, kind, model, n = body.get("project", ""), body.get("kind", ""), body.get("model", ""), body.get("n")
    d = pdir(slug)
    if not SLUG_RE.match(slug or "") or not d.is_dir():
        raise PlanError("pick a book first")
    if kind not in TAKE_KINDS:
        raise PlanError("kind must be clip or keyframe")
    if not re.fullmatch(r"[a-z0-9_]{2,60}", model or ""):
        raise PlanError("bad model name")
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 100000:
        raise PlanError("bad shot number")
    top, stem, ext = TAKE_KINDS[kind]
    folder = d / top / (model + "_keyframes" if kind == "keyframe" else model)
    if not folder.is_dir():
        raise PlanError(f"no {kind}s from {model} yet")
    return d, folder, stem, ext, n


def next_take_number(folder, stem, n, ext):
    nums = [int(p.stem.rsplit("-t", 1)[1]) for p in (folder / "takes").glob(f"{stem}-{n:04d}-t*{ext}") if p.stem.rsplit("-t", 1)[1].isdigit()] if (folder / "takes").is_dir() else []
    return max(nums, default=0) + 1


def set_shot_seed(d, n, seed):
    """Write a seed into all_shots.csv for shot n (adds a seed column if the CSV has none), so the next run of that shot differs."""
    path = d / "all_shots.csv"
    rows = read_csv_rows(path)
    if not 1 <= n <= len(rows):
        raise PlanError(f"shot {n} is not in all_shots.csv")
    fields = list(rows[0].keys())
    if "seed" not in fields:
        fields.append("seed")
    for r in rows:
        r.setdefault("seed", "")
    rows[n - 1]["seed"] = str(seed)
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def retake(body):
    """Keep the current version of a shot as a take, clear the slot and give the shot a new seed: running that shot again makes a new version."""
    d, folder, stem, ext, n = take_target(body)
    cur = folder / f"{stem}-{n:04d}{ext}"
    if not cur.is_file():
        raise PlanError("that shot has nothing to retake yet")
    k = next_take_number(folder, stem, n, ext)
    (folder / "takes").mkdir(exist_ok=True)
    os.replace(cur, folder / "takes" / f"{stem}-{n:04d}-t{k}{ext}")
    seed = n + 1000 * k                                   # differs from the first run (seed = shot number) and from every earlier take
    set_shot_seed(d, n, seed)
    return {"saved_as": k, "seed": seed, "next": f"run shot {n} again (rows {n} to {n}) to make a new version"}


def pick_take(body):
    """Make a saved take the current version; the version it replaces is kept as a new take."""
    d, folder, stem, ext, n = take_target(body)
    k = body.get("take")
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise PlanError("bad take number")
    src = folder / "takes" / f"{stem}-{n:04d}-t{k}{ext}"
    if not src.is_file():
        raise PlanError(f"take {k} does not exist")
    cur = folder / f"{stem}-{n:04d}{ext}"
    if cur.is_file():
        os.replace(cur, folder / "takes" / f"{stem}-{n:04d}-t{next_take_number(folder, stem, n, ext)}{ext}")
    os.replace(src, cur)
    return {"current_from_take": k}
