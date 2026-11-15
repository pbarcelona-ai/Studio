"""Storyboard and takes: re-take a shot, pick the take to keep."""
import csv
import os
import re
import shutil
import time
import clip_length
import critic
import review
import screenplay
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
    cards: list[dict] = []
    for n in range(start, end + 1):
        r, a = shots[n - 1], (audio[n - 1] if n <= len(audio) else {})
        cards.append({"n": n, "chapter": r.get("chapter", ""), "shot": r.get("shot", ""), "prompt": r.get("prompt", ""),
                      "seconds": r.get("seconds", ""), "spoken": clip_length.spoken_seconds(a),
                      "characters": [c for c in (r.get("characters") or "").split("|") if c],
                      "narration": a.get("narration", ""),
                      "keyframes": {k.name.removesuffix("_keyframes"): f"images/{k.name}/image-{n:04d}.png" for k in kdirs if (k / f"image-{n:04d}.png").is_file()},
                      "clips": {v.name: f"videos/{v.name}/shot-{n:04d}.mp4" for v in vdirs if (v / f"shot-{n:04d}.mp4").is_file()},
                      "takes": {**{f"clip:{v.name}": take_files(v, "shot", n, ".mp4", d) for v in vdirs},
                                **{f"keyframe:{k.name.removesuffix('_keyframes')}": take_files(k, "image", n, ".png", d) for k in kdirs}}})
    for c in cards:
        c["takes"] = {k: v for k, v in c["takes"].items() if v}
        files = [*c["keyframes"].values(), *c["clips"].values(), *(f for v in c["takes"].values() for f in v)]
        c["ver"] = {f: file_version(d / f) for f in files}   # changes whenever a file is swapped, so the page never shows an old copy
    faces = (read_json(d / FACE_CHECK_FILE, {}) or {}).get("rows", {})
    verdicts = review.load(d)
    for c in cards:
        c["face"] = faces.get(str(c["n"]))
        c["key"] = review.shot_key(shots[c["n"] - 1])
        c["review"] = verdicts.get(c["key"]) or {"status": "pending", "note": ""}
    return {"rows": len(shots), "start": start, "end": end, "cards": cards,
            "keyframe_models": [k.name.removesuffix("_keyframes") for k in kdirs], "review": review.summary(verdicts, shots[start - 1:end]),
            "storyline_changed": screenplay.storyline_changed(d)}


def file_version(path) -> str:
    """Size and modification time of a file ('' when it is gone): a picture swapped in from a take keeps its old time but the pair still changes."""
    try:
        st = path.stat()
    except OSError:
        return ""
    return f"{st.st_size}-{st.st_mtime_ns}"


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


def review_action(body):
    """POST /api/review {project, action: set | approve_range | reroll_rejected, ...}
    set:            {keys: ["<chapter>#<shot>", ...], status: approved|rejected|pending, note}
    approve_range:  {start, end}: approve every still-pending shot of those rows
    reroll_rejected: {start, end, kind: keyframe|clip, model}: retake every rejected shot of those rows (see retake); each goes back to pending"""
    slug, action = body.get("project", ""), body.get("action")
    d = pdir(slug)
    if not SLUG_RE.match(slug or "") or not d.is_dir():
        raise PlanError("pick a book first")
    rows = read_csv_rows(d / "all_shots.csv")
    if not rows:
        raise PlanError("no shots yet: build the CSVs first")
    valid = {review.shot_key(r) for r in rows}
    try:
        if action == "set":
            review.set_status(d, body.get("keys"), body.get("status"), body.get("note", ""), valid)
        elif action in ("approve_range", "reroll_rejected"):
            start, end = body.get("start"), body.get("end")
            if not (isinstance(start, int) and isinstance(end, int) and 1 <= start <= end <= len(rows)):
                raise PlanError("bad row range")
            keys = [review.shot_key(r) for r in rows[start - 1:end]]
            verdicts = review.load(d)
            if action == "approve_range":
                todo = [k for k in keys if k not in verdicts]
                if todo:
                    review.set_status(d, todo, "approved", "", valid)
            else:
                done, skipped = [], []
                for n, k in enumerate(keys, start=start):
                    if (verdicts.get(k) or {}).get("status") == "rejected":
                        try:
                            retake({"project": slug, "kind": body.get("kind"), "model": body.get("model"), "n": n})
                            done.append(k)
                        except PlanError as e:
                            skipped.append(f"shot {n}: {e}")
                if not done:
                    raise PlanError(skipped[0] if skipped else "no rejected shots in those rows")
                review.set_status(d, done, "pending", "", valid)
                return {"review": review.summary(review.load(d), rows), "rerolled": len(done), "skipped": skipped}
        else:
            raise PlanError("unknown review action")
    except review.ReviewError as e:
        raise PlanError(str(e)) from e
    return {"review": review.summary(review.load(d), rows)}


def critic_action(body):
    """POST /api/critic {project, flag?: true}: run the critic pass over the book's shots (and, with flag, reject the shots it found a high problem in)."""
    from .media import media_seconds
    slug = body.get("project", "")
    d = pdir(slug)
    if not SLUG_RE.match(slug or "") or not d.is_dir():
        raise PlanError("pick a book first")
    try:
        cs = float(body.get("clip_seconds") or 4)
        res = critic.run(d, cs, media_seconds)
    except ValueError as e:
        raise PlanError(str(e)) from e
    flagged = critic.flag_in_review(d, res) if body.get("flag") else 0
    rows, audio = read_csv_rows(d / "all_shots.csv"), read_csv_rows(d / "audio_shots.csv")
    lengths = {}                                           # each shot a finding is about: its clip length and how long its words take (for the same controls as the cards)
    for f in res["findings"]:
        n = f.get("n")
        if n and 1 <= n <= len(rows) and str(n) not in lengths:
            lengths[str(n)] = {"seconds": rows[n - 1].get("seconds", ""), "spoken": clip_length.spoken_seconds(audio[n - 1] if n <= len(audio) else {})}
    return {**res, "flagged_in_review": flagged, "lengths": lengths}      # "shots" stays the critic's count of shots


def lipsync_candidates(slug, include_medium=False):
    """GET /api/lipsync_candidates: the shots where a character speaks in a close-up (see critic.lipsync_rows)."""
    d = pdir(slug)
    if not SLUG_RE.match(slug or "") or not d.is_dir():
        raise PlanError("pick a book first")
    try:
        return critic.lipsync_rows(d, include_medium)
    except ValueError as e:
        raise PlanError(str(e)) from e


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


def reset_storyboard(body):
    """POST /api/storyboard_reset {project}: after the shots were rewritten from a new storyline, move every old still and clip (and their takes) into
    replaced/<time>/ and forget the verdicts and the saved prompt edits (they belong to the old shots), so the storyboard starts empty and the next run makes pictures for the new shots. Nothing is deleted."""
    from .jobs import JOB
    slug = body.get("project", "")
    d = pdir(slug)
    if not SLUG_RE.match(slug or "") or not d.is_dir():
        raise PlanError("pick a book first")
    if JOB.running:
        raise PlanError("a job is running: wait for it to finish (or stop it) first")
    import picture_record
    picture_record.record_new(d)                           # so a picture set aside can still be matched to its shot later
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = d / "replaced" / stamp
    moved = 0

    def put(src, rel):
        nonlocal moved
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(target))
        moved += 1

    for top, pattern in (("images", "image-*.png"), ("videos", "shot-*.mp4")):
        base = d / top
        for folder in sorted(base.iterdir()) if base.is_dir() else []:
            if not folder.is_dir() or folder.name.endswith("_chapters") or (top == "images" and not folder.name.endswith("_keyframes")):
                continue
            for f in sorted(folder.glob(pattern)):
                put(f, f"{top}/{folder.name}/{f.name}")
            if (folder / "takes").is_dir():
                put(folder / "takes", f"{top}/{folder.name}/takes")
    for name in ("review.json", "critic.json", "face_check.json", "prompt_edits.json", "feedback.json"):
        if (d / name).is_file():
            put(d / name, name)
    if moved and (d / "all_shots.csv").is_file():          # what each old picture showed, so it can be found and used again (old_pictures.py)
        shutil.copy2(d / "all_shots.csv", dest / "all_shots.csv")
    return {"moved": moved, "folder": f"replaced/{stamp}" if moved else ""}
