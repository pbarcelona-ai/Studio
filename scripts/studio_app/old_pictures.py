"""Old keyframe pictures, and putting one on a shot of the current storyboard.

Old pictures are the ones set aside when the storyboard was made again (replaced/<time>/images/<model>_keyframes/, with the shot list of that time
in replaced/<time>/all_shots.csv), the earlier takes of every shot (images/<model>_keyframes/takes/), and the pictures of other picture makers.
GET  /api/old_pictures?project=&n=     every old picture, the ones most like shot n first: {pictures: [{path, source, model, was_shot, prompt, score}]}
POST /api/assign_picture {project, n, path, model?}   copy that picture onto shot n (the picture it had is kept as a take; its verdict starts again)
POST /api/auto_assign_pictures {project, model?}     do that by itself for every shot with no picture, when an old picture of the same shot exists
POST /api/match_pictures {project, model?}           check every shot: each gets the picture that shows it best (pictures in the wrong place move)
POST /api/swap_pictures {project, a, b, model}       shots a and b trade pictures (drag and drop on the storyboard)
"""
import csv
import os
import re
import shutil
from pathlib import Path

import review
from bookkit import SLUG_RE, read_json, write_json
from layout import project_dir as pdir

from .common import PlanError
from .projects import read_csv_rows
from .takes import next_take_number

PIC = re.compile(r"^image-(\d{4})(?:-t(\d+))?\.png$")
MAX = 600


def _book(slug):
    d = pdir(slug)
    if not SLUG_RE.match(slug or "") or not d.is_dir():
        raise PlanError("pick a book first")
    return d


def _prompts(csv_path: Path) -> list[str]:
    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            return [r.get("prompt", "") for r in csv.DictReader(fh)]
    except OSError:
        return []


def _score(a: str, b: str) -> float:
    wa, wb = set(re.findall(r"[a-z]+", (a or "").lower())), set(re.findall(r"[a-z]+", (b or "").lower()))
    return round(len(wa & wb) / len(wa | wb), 3) if wa and wb else 0.0


def old_pictures(slug, n: int | None = None) -> dict:
    d = _book(slug)
    rows = read_csv_rows(d / "all_shots.csv")
    now = [r.get("prompt", "") for r in rows]
    target = now[n - 1] if n and 1 <= n <= len(now) else ""
    found: list[dict] = []

    def add(f: Path, source: str, model: str, prompts: list[str]):
        m = PIC.match(f.name)
        if not m:
            return
        was = int(m.group(1))
        prompt = prompts[was - 1] if 1 <= was <= len(prompts) else ""
        found.append({"path": f.relative_to(d).as_posix(), "source": source, "model": model, "was_shot": was, "take": int(m.group(2)) if m.group(2) else None,
                      "prompt": prompt, "score": _score(prompt, target) if target else 0.0})

    # earlier takes, and the pictures of other picture makers (same shot list as now)
    for k in sorted((d / "images").glob("*_keyframes")) if (d / "images").is_dir() else []:
        model = k.name.removesuffix("_keyframes")
        for f in sorted((k / "takes").glob("image-*.png")) if (k / "takes").is_dir() else []:
            add(f, "earlier take", model, now)
        for f in sorted(k.glob("image-*.png")):
            add(f, f"made by {model}", model, now)
    # set aside when the storyboard was made again
    for stamp in sorted((d / "replaced").iterdir(), reverse=True) if (d / "replaced").is_dir() else []:
        if not stamp.is_dir():
            continue
        prompts = _prompts(stamp / "all_shots.csv")
        when = re.sub(r"^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})$", r"\1-\2-\3 \4:\5", stamp.name)
        for k in sorted((stamp / "images").glob("*_keyframes")) if (stamp / "images").is_dir() else []:
            model = k.name.removesuffix("_keyframes")
            for f in sorted(k.rglob("image-*.png")):
                add(f, f"set aside {when}", model, prompts)
    if n:                                                  # the current picture of this very shot is not an "old" one
        found = [p for p in found if not (p["source"].startswith("made by") and p["was_shot"] == n)]
        found.sort(key=lambda p: -p["score"])
    return {"pictures": found[:MAX], "total": len(found), "shot": n, "prompt": target}


def _shown_by(d: Path, src: Path) -> str:
    """What an old picture shows: its record, else the shot list it was set aside with, else the shot list now."""
    import picture_record as pr
    p = pr.prompt_of(d, src)
    if p is not None:
        return p
    m = PIC.match(src.name)
    n = int(m.group(1)) if m else 0
    rel = src.relative_to(d.resolve()) if src.is_relative_to(d.resolve()) else src
    parts = Path(rel).parts
    rows = _prompts(d / "replaced" / parts[1] / "all_shots.csv") if len(parts) > 2 and parts[0] == "replaced" else [r.get("prompt", "") for r in read_csv_rows(d / "all_shots.csv")]
    return rows[n - 1] if 1 <= n <= len(rows) else ""


def assign_picture(b: dict) -> dict:
    from .jobs import JOB
    slug = b.get("project", "")
    d = _book(slug)
    if JOB.running:
        raise PlanError("wait until the running job is finished")
    import picture_record
    picture_record.record_new(d)
    n, rel = b.get("n"), str(b.get("path") or "")
    rows = read_csv_rows(d / "all_shots.csv")
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(rows):
        raise PlanError("there is no such shot")
    src = (d / rel).resolve()
    inside = [(d / "images").resolve(), (d / "replaced").resolve()]
    if ".." in Path(rel).parts or not PIC.match(src.name) or not src.is_file() or not any(src.is_relative_to(x) for x in inside):
        raise PlanError("that is not an old picture of this book")
    model = str(b.get("model") or "")
    if not model:
        m = re.search(r"([a-z0-9_]+)_keyframes", rel)
        model = m.group(1) if m else ""
    if not re.fullmatch(r"[a-z0-9_]{2,60}", model):
        raise PlanError("say which picture maker's folder it goes in")
    folder = d / "images" / f"{model}_keyframes"
    folder.mkdir(parents=True, exist_ok=True)
    dst = folder / f"image-{n:04d}.png"
    kept = None
    if dst.is_file():                                      # the picture the shot has now is kept as a take, never lost
        if dst.resolve() == src:
            raise PlanError("that is already this shot's picture")
        k = next_take_number(folder, "image", n, ".png")
        (folder / "takes").mkdir(exist_ok=True)
        kept = folder / "takes" / f"image-{n:04d}-t{k}.png"
        shutil.move(str(dst), str(kept))
    shutil.copy2(src, dst)
    import picture_record as pr
    pr.remember(d, dst, _shown_by(d, src), model, "put on the shot by hand")
    key = review.shot_key(rows[n - 1])
    if key in review.load(d):
        review.set_status(d, [key], "pending")             # a new picture: say yes or no to it again
    fc = read_json(d / "face_check.json", None)
    if isinstance(fc, dict) and str(n) in (fc.get("rows") or {}):
        fc["rows"].pop(str(n))
        write_json(d / "face_check.json", fc)
    return {"n": n, "path": dst.relative_to(d).as_posix(), "kept_as_take": kept.relative_to(d).as_posix() if kept else None}


def swap_pictures(b: dict) -> dict:
    """POST /api/swap_pictures {project, a, b, model}: shot a gets shot b's picture and b gets a's (dragged on the storyboard). When one of them
    has no picture, the other's moves over. Their takes stay with their shots; both verdicts and face checks start again."""
    from .jobs import JOB
    d = _book(b.get("project", ""))
    if JOB.running:
        raise PlanError("wait until the running job is finished")
    rows = read_csv_rows(d / "all_shots.csv")
    x, y = b.get("a"), b.get("b")
    if not (isinstance(x, int) and isinstance(y, int)) or isinstance(x, bool) or isinstance(y, bool) or not (1 <= x <= len(rows) and 1 <= y <= len(rows)):
        raise PlanError("there is no such shot")
    if x == y:
        raise PlanError("drop the picture on another shot")
    model = str(b.get("model") or "")
    if not re.fullmatch(r"[a-z0-9_]{2,60}", model):
        raise PlanError("say which picture maker's pictures to swap")
    folder = d / "images" / f"{model}_keyframes"
    fa, fb = folder / f"image-{x:04d}.png", folder / f"image-{y:04d}.png"
    if not fa.is_file() and not fb.is_file():
        raise PlanError("neither shot has a picture yet")
    import picture_record
    picture_record.record_new(d)                           # both pictures keep what they show (the record follows the file's contents)
    tmp = folder / f".swap-{x:04d}-{y:04d}.png"
    if fa.is_file():
        os.replace(fa, tmp)
    if fb.is_file():
        os.replace(fb, fa)
    if tmp.is_file():
        os.replace(tmp, fb)
    keys = [review.shot_key(rows[n - 1]) for n in (x, y)]
    verdicts = review.load(d)
    if any(k in verdicts for k in keys):
        review.set_status(d, [k for k in keys if k in verdicts], "pending")      # each shot shows another picture: say yes or no again
    fc = read_json(d / "face_check.json", None)
    if isinstance(fc, dict) and isinstance(fc.get("rows"), dict) and (str(x) in fc["rows"] or str(y) in fc["rows"]):
        fc["rows"].pop(str(x), None)
        fc["rows"].pop(str(y), None)
        write_json(d / "face_check.json", fc)
    return {"a": x, "b": y, "a_has": fa.is_file(), "b_has": fb.is_file()}


AUTO_MIN = 0.5             # how alike an old picture's prompt and the shot's prompt must be (share of words) to be used without asking


def auto_assign(b: dict) -> dict:
    """POST /api/auto_assign_pictures {project, model?, min_score?}: give every shot that has no picture yet the old picture most like it
    (set aside earlier, or an earlier take), each old picture used once, best matches first. Shots with no good match are left for a new picture."""
    from .jobs import JOB
    slug = b.get("project", "")
    d = _book(slug)
    if JOB.running:
        raise PlanError("wait until the running job is finished")
    rows = read_csv_rows(d / "all_shots.csv")
    if not rows:
        raise PlanError("no shots yet: get the shots ready first")
    model = str(b.get("model") or "")
    if model and not re.fullmatch(r"[a-z0-9_]{2,60}", model):
        raise PlanError("bad picture maker name")
    try:
        least = float(b.get("min_score", AUTO_MIN))
    except (TypeError, ValueError):
        least = AUTO_MIN
    least = min(1.0, max(0.2, least))
    have = {int(m.group(1)) for k in (d / "images").glob("*_keyframes") for f in k.glob("image-*.png") if (m := PIC.match(f.name)) and not m.group(2)} \
        if (d / "images").is_dir() else set()
    need = [n for n in range(1, len(rows) + 1) if n not in have]
    pool = [p for p in old_pictures(slug)["pictures"] if not p["source"].startswith("made by")]
    pairs = []
    for n in need:
        for i, p in enumerate(pool):
            s = _score(p["prompt"], rows[n - 1].get("prompt", ""))
            if s >= least:
                pairs.append((s, n, i))
    used_shots: set[int] = set()
    used_pics: set[int] = set()
    done = []
    for s, n, i in sorted(pairs, key=lambda t: (-t[0], t[1])):
        if n in used_shots or i in used_pics:
            continue
        p = pool[i]
        assign_picture({"project": slug, "n": n, "path": p["path"], "model": model or p["model"]})
        used_shots.add(n)
        used_pics.add(i)
        done.append({"n": n, "from": p["path"], "score": s})
    return {"matched": sorted(done, key=lambda x: x["n"]), "still_missing": [n for n in need if n not in used_shots]}


def match_all(b: dict) -> dict:
    """POST /api/match_pictures {project, model?, min_score?}: check EVERY shot. Each shot gets the picture that shows it best, from its own picture,
    the pictures now on other shots (put there in an old order), earlier takes and pictures set aside, each picture used once. A picture that is
    moved off a shot it does not show is kept as a take of that shot; a shot left with no picture that shows it gets a new one on the next run.
    What a picture shows is the prompt it was made from (picture_record.py), so pictures in the wrong place are found."""
    import picture_record as pr
    from .jobs import JOB
    slug = b.get("project", "")
    d = _book(slug)
    if JOB.running:
        raise PlanError("wait until the running job is finished")
    rows = read_csv_rows(d / "all_shots.csv")
    if not rows:
        raise PlanError("no shots yet: get the shots ready first")
    pr.record_new(d)
    rec = pr.load(d)
    model = str(b.get("model") or "")
    if not model:
        dirs = sorted((d / "images").glob("*_keyframes"), key=lambda p: -len(list(p.glob("image-*.png")))) if (d / "images").is_dir() else []
        model = dirs[0].name.removesuffix("_keyframes") if dirs else ""
    if not re.fullmatch(r"[a-z0-9_]{2,60}", model):
        raise PlanError("choose the picture maker first")
    try:
        least = min(1.0, max(0.2, float(b.get("min_score", AUTO_MIN))))
    except (TypeError, ValueError):
        least = AUTO_MIN
    folder = d / "images" / f"{model}_keyframes"
    now = [r.get("prompt", "") for r in rows]
    cands: list[dict] = []                                  # {path, prompt, current_at (shot number when it is a current picture of this maker)}

    def cand(f: Path, fallback: str, current_at: int | None = None):
        p = pr.prompt_of(d, f, rec)
        cands.append({"path": f, "prompt": p if p is not None else fallback, "current_at": current_at, "known": p is not None})

    for f in sorted(folder.glob("image-*.png")) if folder.is_dir() else []:
        m = PIC.match(f.name)
        if m and not m.group(2):
            n = int(m.group(1))
            cand(f, now[n - 1] if n <= len(now) else "", n)
    for k in sorted((d / "images").glob("*_keyframes")) if (d / "images").is_dir() else []:
        for f in sorted(k.glob("takes/image-*.png")) + ([] if k == folder else sorted(k.glob("image-*.png"))):
            m = PIC.match(f.name)
            if m:
                n = int(m.group(1))
                cand(f, now[n - 1] if n <= len(now) else "")
    for stamp in sorted((d / "replaced").iterdir()) if (d / "replaced").is_dir() else []:
        old = _prompts(stamp / "all_shots.csv")
        for f in sorted(stamp.glob("images/*_keyframes/**/image-*.png")):
            m = PIC.match(f.name)
            if m:
                n = int(m.group(1))
                cand(f, old[n - 1] if n <= len(old) else "")
    pairs = []
    for i, c in enumerate(cands):
        for n in range(1, len(rows) + 1):
            s = _score(c["prompt"], now[n - 1])
            if s >= least:
                pairs.append((s + (0.001 if c["current_at"] == n else 0.0), n, i))      # a picture already in the right place stays there
    best: dict[int, int] = {}
    used: set[int] = set()
    for s, n, i in sorted(pairs, key=lambda t: (-t[0], t[1])):
        if n not in best and i not in used:
            best[n] = i
            used.add(i)
    # apply: current pictures that move go to a staging folder first, so nothing is overwritten
    stage = folder / ".matching"
    staged: dict[int, Path] = {}
    for i, c in enumerate(cands):
        n0 = c["current_at"]
        if n0 is not None and best.get(n0) != i:
            stage.mkdir(parents=True, exist_ok=True)
            t = stage / c["path"].name
            os.replace(c["path"], t)
            staged[i] = t
    moved = copied = kept = 0
    changed = []
    for n, i in sorted(best.items()):
        c = cands[i]
        if c["current_at"] == n:
            kept += 1
            continue
        dst = folder / f"image-{n:04d}.png"
        folder.mkdir(parents=True, exist_ok=True)
        if i in staged:
            os.replace(staged.pop(i), dst)
            moved += 1
        else:
            shutil.copy2(c["path"], dst)
            pr.remember(d, dst, c["prompt"], model, "matched from an old picture")
            copied += 1
        changed.append(n)
    takes = 0
    for i, t in staged.items():                             # a picture that shows none of the shots well: a take of the shot it was on
        n0 = cands[i]["current_at"]
        k = next_take_number(folder, "image", n0, ".png")
        (folder / "takes").mkdir(exist_ok=True)
        os.replace(t, folder / "takes" / f"image-{n0:04d}-t{k}.png")
        takes += 1
    if stage.is_dir():
        stage.rmdir()
    verdicts = review.load(d)
    again = [review.shot_key(rows[n - 1]) for n in changed if review.shot_key(rows[n - 1]) in verdicts]
    emptied = [c["current_at"] for i, c in enumerate(cands) if c["current_at"] and c["current_at"] not in best]
    gone = [review.shot_key(rows[n - 1]) for n in emptied if review.shot_key(rows[n - 1]) in verdicts]
    if again or gone:
        review.set_status(d, again + gone, "pending")       # a different picture (or none): say yes or no again
    fc = read_json(d / "face_check.json", None)
    if isinstance(fc, dict) and isinstance(fc.get("rows"), dict):
        for n in changed + emptied:
            fc["rows"].pop(str(n), None)
        write_json(d / "face_check.json", fc)
    pr.record_new(d)
    missing = [n for n in range(1, len(rows) + 1) if not (folder / f"image-{n:04d}.png").is_file()]
    return {"model": model, "kept": kept, "moved": moved, "from_old": copied, "set_aside_as_takes": takes, "changed": changed,
            "still_missing": missing, "unknown": sum(1 for c in cands if c["current_at"] and not c["known"])}
