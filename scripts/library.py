"""The picture library and reuse (BOOK_TO_SCREEN_BUILD.md Section 6b.2-6b.3, milestone M8).

Every picture and clip ever made in a book goes into its library: the current pictures of every style (pictures/<style>/), their earlier
versions, the look-development sheets, the storyboard keyframes and their takes, pictures set aside by an earlier storyboard reset
(replaced/<time>/), every archived attempt (attempts/<id>/), and the clips. refresh() rebuilds the index (assets/library.json); what the owner
decides (liked version, verdict, purpose label, moving a version to another asset) is kept apart in assets/library_user.json, so a refresh
never loses it. Each file is also stored by its contents (assets.py), so the library never points at a file that has gone.

An item: {id (content hash), file (path under the book), kind image|clip, style, model, seed, prompt, parts, negative, shot {scene, shot,
action, characters, location, camera, lens}, layout, score, verdict liked|approved|rejected|"", purpose keyframe|final|reference, attempt, cost}.
ASSETS AND VERSIONS: items serving one purpose ("MARA, front view (claymation)", "S001 shot 2 (anime)") are one asset (group); the LIKED
version comes first, the rest newest first; a version can move to another asset or become an asset of its own.

Reuse: matches() scores every library picture against a shot (same characters, location, action, camera and style; 0-10), reuse() puts one
on a shot as a picture, as a prompt (parts, seed) or as a layout only, and auto_reuse() fills every empty shot whose best match scores >= 8.
A reused picture whose characters' or location's continuity tokens have changed since it was made is marked "may not match".
"""
from __future__ import annotations

import csv
import difflib
import json
import re
import shutil
import time
from pathlib import Path

import assets
import continuity_book
import layout
import pictures
import production
import shot_list

PURPOSES = ("keyframe", "final", "reference")
VERDICTS = ("liked", "approved", "rejected", "")
IMG = (".png", ".jpg", ".jpeg", ".webp")


def _idx(pdir: Path) -> Path:
    return assets.root(pdir) / "library.json"


def _user(pdir: Path) -> Path:
    return assets.root(pdir) / "library_user.json"


def _read(p: Path, default):
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, type(default)) else default
    except (OSError, ValueError):
        return default


def _write(p: Path, d) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(d, indent=0, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def user_data(pdir: Path) -> dict:
    u = _read(_user(pdir), {})
    for k in ("liked", "verdict", "purpose", "group"):
        u.setdefault(k, {})
    return u


# ---------------------------------------------------------------------------------------------- building the index
def _item(pdir: Path, f: Path, **kw) -> dict:
    sha = assets.ingest(pdir, f, kw.pop("alias", ""))
    rel = assets._rel(pdir, f)
    base = {"id": sha, "file": rel, "kind": "clip" if f.suffix.lower() in (".mp4", ".mov", ".webm") else "image", "style": "", "model": "", "seed": None,
            "prompt": "", "parts": None, "negative": "", "shot": None, "layout": "", "score": None, "verdict": "", "purpose": "keyframe",
            "attempt": "current", "cost": 0.0, "group": "", "group_name": "", "made": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f.stat().st_mtime))}
    base.update(kw)
    return base


def _style_items(pdir: Path, pic_root: Path, sets_root: Path | None, attempt: str) -> list[dict]:
    """The pictures (and earlier versions) of every style under pic_root (pictures/), whose prompt sets are in sets_root (or found by name)."""
    out: list[dict] = []
    sl = shot_list.load(pdir) if attempt == "current" else _read(pic_root.parent / "shots" / "shotlist.json", {})
    by = {(sc["id"], s["n"]): (sc, s) for sc in sl.get("scenes", []) for s in sc["shots"]}
    for sd in sorted(pic_root.iterdir()) if pic_root.is_dir() else []:
        data = _read(sd / "shots.json", {})
        if not data.get("shots"):
            continue
        setdir = (sets_root / data["set"]) if sets_root else layout.find_dir(data["set"])
        if setdir is None or not setdir.is_dir():
            continue
        review = _read(sd / "review.json", {})
        checks = _read(sd / "consistency.json", {})
        for s in data["shots"]:
            sc, shot = by.get((s["scene"], s["shot"]), ({"heading": ""}, {}))
            info = {"scene": s["scene"], "shot": s["shot"], "action": shot.get("action", ""), "characters": [c["name"] for c in (s.get("parts") or {}).get("characters", [])],
                    "location": ((s.get("parts") or {}).get("location") or {}).get("name", "") or pictures.location_of(sc.get("heading", "")),
                    "camera": shot.get("type", ""), "lens": shot.get("lens_mm", "")}
            rv = review.get(str(s["row"]), {})
            lay = sd / "layouts" / f"{s['scene']}-{s['shot']:03d}" / "layout.json"
            common = {"style": sd.name, "seed": s["seed"], "prompt": rv.get("prompt") or s["prompt"], "parts": s.get("parts"), "negative": s.get("negative", ""),
                      "shot": info, "layout": assets._rel(pdir, lay) if lay.is_file() else "", "score": (checks.get(str(s["row"])) or {}).get("score"),
                      "attempt": attempt, "group": f"{attempt}:{sd.name}:{s['scene']}:{s['shot']}" if attempt != "current" else f"{sd.name}:{s['scene']}:{s['shot']}",
                      "group_name": f"{s['scene']} shot {s['shot']} ({sd.name})" + ("" if attempt == "current" else f", {attempt}")}
            img = pictures._image(setdir, s["row"])
            if img is not None:
                out.append(_item(pdir, img, verdict="approved" if rv.get("approved") else "", purpose="keyframe", row=s["row"], **common))
            for v in rv.get("versions", []):
                vf = setdir / v
                if vf.is_file():
                    out.append(_item(pdir, vf, purpose="keyframe", row=s["row"], **common))
    return out


def _lookdev_items(pdir: Path, styles_root: Path, attempt: str) -> list[dict]:
    out: list[dict] = []
    for sd in sorted(styles_root.iterdir()) if styles_root.is_dir() else []:
        ld = _read(sd / "lookdev.json", {})
        setdir = layout.find_dir(ld["set"]) if ld.get("set") else None
        if not setdir:
            continue
        picks = _read(sd / "picks.json", {})
        items = {it["key"]: it for it in ld.get("items", [])}
        for x in ld.get("index", []):
            img = pictures._image(setdir, x["row"])
            it = items.get(x["key"], {})
            if img is None:
                continue
            out.append(_item(pdir, img, style=sd.name, prompt=it.get("prompt", ""), purpose="reference", attempt=attempt,
                             verdict="liked" if picks.get(x["key"]) == x["row"] else "",
                             shot={"scene": "", "shot": 0, "action": "", "characters": [it["name"]] if it.get("kind") == "character" else [],
                                   "location": it["name"] if it.get("kind") == "location" else "", "camera": it.get("view", ""), "lens": ""},
                             group=f"ref:{sd.name}:{x['key']}", group_name=f"{it.get('name', '')}, {it.get('view', '')} ({sd.name})"))
    return out


def _old_keyframes(pdir: Path) -> list[dict]:
    """The storyboard's keyframes and their takes, and pictures set aside by a storyboard reset (replaced/<time>/), with the prompt each was made from."""
    import picture_record
    out: list[dict] = []
    rec = picture_record.load(pdir)
    roots = [(pdir / "images", "current")]
    if (pdir / "replaced").is_dir():
        roots += [(r / "images", f"replaced {r.name}") for r in sorted((pdir / "replaced").iterdir()) if r.is_dir()]
    for base, attempt in roots:
        for f in sorted(base.rglob("image-*.png")) if base.is_dir() else []:
            m = re.match(r"image-(\d{4})", f.name)
            model = f.relative_to(base).parts[0] if len(f.relative_to(base).parts) > 1 else ""
            out.append(_item(pdir, f, model=model, prompt=picture_record.prompt_of(pdir, f, rec) or "", attempt=attempt, purpose="keyframe",
                             shot={"scene": "", "shot": int(m.group(1)) if m else 0, "action": "", "characters": [], "location": "", "camera": "", "lens": ""},
                             group=f"storyboard:{int(m.group(1)) if m else 0}", group_name=f"storyboard shot {int(m.group(1)) if m else 0}"))
    return out


def _clips(pdir: Path) -> list[dict]:
    out: list[dict] = []
    for f in sorted((pdir / "videos").rglob("*.mp4")) if (pdir / "videos").is_dir() else []:
        if "takes" in f.parts or f.name.startswith("_"):
            continue
        m = re.search(r"(\d{3,4})", f.stem)
        out.append(_item(pdir, f, model=f.parent.name, purpose="final", group=f"clip:{f.parent.name}:{m.group(1) if m else f.stem}",
                         group_name=f"clip {m.group(1) if m else f.stem} ({f.parent.name})"))
    return out


def refresh(pdir: Path) -> dict:
    """Rebuild the library index from everything in the book (and its archived attempts)."""
    items: list[dict] = []
    items += _style_items(pdir, pdir / "pictures", None, "current")
    items += _lookdev_items(pdir, pdir / "styles", "current")
    items += _old_keyframes(pdir)
    items += _clips(pdir)
    for a in sorted((pdir / "attempts").iterdir()) if (pdir / "attempts").is_dir() else []:
        meta = _read(a / "meta.json", {})
        label = meta.get("label", a.name)
        items += _style_items(pdir, a / "pictures", a / "sets", label) if (a / "pictures").is_dir() else []
    unique: dict[str, dict] = {}
    for it in items:
        key = f"{it['id']}|{it['group']}"
        if key not in unique:
            unique[key] = it
    idx = {"built": time.strftime("%Y-%m-%dT%H:%M:%S"), "items": list(unique.values())}
    _write(_idx(pdir), idx)
    return idx


def index(pdir: Path) -> list[dict]:
    """The items with the owner's decisions applied (verdict, purpose, liked, moved to another asset)."""
    idx = _read(_idx(pdir), {}) or refresh(pdir)
    u = user_data(pdir)
    out = []
    for it in idx.get("items", []):
        it = dict(it)
        key = f"{it['id']}|{it['group']}"
        it["key"] = key
        if key in u["group"]:
            it["group"], it["group_name"] = u["group"][key]["group"], u["group"][key]["name"]
        it["verdict"] = u["verdict"].get(key, it["verdict"])
        it["purpose"] = u["purpose"].get(key, it["purpose"])
        out.append(it)
    return out


def groups(pdir: Path, items: list[dict] | None = None) -> list[dict]:
    """Assets: {group, name, versions: [items, the LIKED one first, then newest first], liked}."""
    items = items if items is not None else index(pdir)
    u = user_data(pdir)
    by: dict[str, list[dict]] = {}
    for it in items:
        by.setdefault(it["group"], []).append(it)
    out = []
    for g, vs in by.items():
        liked = u["liked"].get(g) or next((v["key"] for v in vs if v["verdict"] == "liked"), None)
        vs.sort(key=lambda v: (v["key"] != liked, v["made"]), reverse=False)
        rest = sorted([v for v in vs if v["key"] != liked], key=lambda v: v["made"], reverse=True)
        first = [v for v in vs if v["key"] == liked]
        out.append({"group": g, "name": vs[0]["group_name"], "liked": liked, "versions": first + rest, "style": vs[0]["style"], "purpose": vs[0]["purpose"]})
    return sorted(out, key=lambda g: g["name"])


def search(pdir: Path, q: str = "", style: str = "", character: str = "", location: str = "", purpose: str = "", attempt: str = "",
           all_projects: bool = False) -> list[dict]:
    """Assets whose versions match every filter given (text in the prompt or the asset's name)."""
    books = [pdir] + ([b for b in sorted(layout.BOOKS.iterdir()) if b.is_dir() and b != pdir and (b / "assets" / "library.json").is_file()] if all_projects else [])
    out = []
    for b in books:
        items = [it for it in index(b) if _matches(it, q, style, character, location, purpose, attempt)]
        for g in groups(b, items):
            g["project"] = b.name
            out.append(g)
    return out


def _matches(it: dict, q: str, style: str, character: str, location: str, purpose: str, attempt: str) -> bool:
    sh = it.get("shot") or {}
    if style and it["style"] != style:
        return False
    if purpose and it["purpose"] != purpose:
        return False
    if attempt and it["attempt"] != attempt:
        return False
    if character and character.lower() not in [c.lower() for c in sh.get("characters", [])]:
        return False
    if location and location.lower() not in str(sh.get("location", "")).lower():
        return False
    return not q or q.lower() in (it["prompt"] + " " + it["group_name"]).lower()


# ---------------------------------------------------------------------------------------------- the owner's decisions
def _key_of(pdir: Path, key: str) -> dict:
    it = next((x for x in index(pdir) if x["key"] == key), None)
    if it is None:
        raise ValueError("no such library item")
    return it


def set_verdict(pdir: Path, key: str, verdict: str) -> None:
    if verdict not in VERDICTS:
        raise ValueError(f"verdict is one of {', '.join(v for v in VERDICTS if v)} (or empty)")
    it = _key_of(pdir, key)
    u = user_data(pdir)
    u["verdict"][key] = verdict
    if verdict == "liked":
        u["liked"][it["group"]] = key                      # one liked version per asset: it becomes the default
    _write(_user(pdir), u)


def set_purpose(pdir: Path, key: str, purpose: str) -> None:
    if purpose not in PURPOSES:
        raise ValueError(f"purpose is one of {', '.join(PURPOSES)}")
    _key_of(pdir, key)
    u = user_data(pdir)
    u["purpose"][key] = purpose
    _write(_user(pdir), u)


def move_version(pdir: Path, key: str, to_group: str = "") -> str:
    """Move a version onto another asset, or (no group given) make it an asset of its own."""
    it = _key_of(pdir, key)
    u = user_data(pdir)
    if to_group:
        target = next((g for g in groups(pdir) if g["group"] == to_group), None)
        if target is None:
            raise ValueError("no such asset")
        u["group"][key] = {"group": to_group, "name": target["name"]}
    else:
        u["group"][key] = {"group": f"own:{it['id'][:12]}", "name": f"{it['group_name']} (own)"}
    if u["liked"].get(it["group"]) == key:
        del u["liked"][it["group"]]
    _write(_user(pdir), u)
    return u["group"][key]["group"]


# ---------------------------------------------------------------------------------------------- reuse
def stale(pdir: Path, it: dict) -> bool:
    """True when a character's or the location's continuity token changed since the picture was made (its prompt parts kept the old one)."""
    parts = it.get("parts") or {}
    book = continuity_book.load(pdir)
    now = {c["name"]: c["token"] for c in book.get("characters", [])} | {x["name"]: x["token"] for x in book.get("locations", [])}
    used = [(c["name"], c["identity"]) for c in parts.get("characters", [])] + ([(parts["location"]["name"], parts["location"]["identity"])] if parts.get("location") else [])
    return any(name in now and now[name] != token for name, token in used)


def score(it: dict, shot: dict, location: str, style: str) -> float:
    """0-10: the same characters (3), location (2), action (3), camera (1) and style (1)."""
    sh = it.get("shot") or {}
    want, have = {c.lower() for c in shot.get("characters", [])}, {c.lower() for c in sh.get("characters", [])}
    s = 3.0 * (len(want & have) / len(want | have)) if (want or have) else 1.5
    loc_a, loc_b = location.lower(), str(sh.get("location", "")).lower()
    s += 2.0 if loc_a and loc_b and (loc_a in loc_b or loc_b in loc_a) else 0.0
    s += 3.0 * difflib.SequenceMatcher(None, shot.get("action", "").lower(), str(sh.get("action", "") or it.get("prompt", "")).lower()).ratio()
    s += 1.0 if shot.get("type") and shot.get("type") == sh.get("camera") else 0.0
    s += 1.0 if style and it.get("style") == style else 0.0
    return round(min(10.0, s), 1)


def matches(pdir: Path, style: str, scene: str, n: int, limit: int = 12) -> list[dict]:
    """The library pictures that could fit a shot of the shot list, the best first, each with its score and a "may not match" flag."""
    sl = shot_list.load(pdir)
    sc = next((s for s in sl.get("scenes", []) if s["id"] == scene), None)
    if sc is None or not 1 <= n <= len(sc["shots"]):
        raise ValueError("no such shot")
    shot, loc = sc["shots"][n - 1], pictures.location_of(sc["heading"])
    out = []
    for it in index(pdir):
        if it["kind"] != "image" or it["verdict"] == "rejected" or (it["attempt"] == "current" and it.get("style") == style and (it.get("shot") or {}).get("scene") == scene
                                                                    and (it.get("shot") or {}).get("shot") == n):
            continue
        out.append({**it, "match": score(it, shot, loc, style), "may_not_match": stale(pdir, it)})
    return sorted(out, key=lambda x: -x["match"])[:limit]


def _row_of(pdir: Path, style: str, scene: str, n: int) -> int:
    data = pictures._read(pictures.pdir_of(pdir, style) / "shots.json")
    if not data:
        raise ValueError("make this style's picture prompts first")
    row = next((s["row"] for s in data["shots"] if s["scene"] == scene and s["shot"] == n), None)
    if row is None:
        raise ValueError("no such shot in this style's pictures")
    return row


def reuse(pdir: Path, style: str, scene: str, n: int, key: str, how: str) -> dict:
    """picture: copy the item onto the shot (the original stays in the library); prompt: load its prompt and seed, ready to edit and render;
    layout: use its picture as the structure reference of a fresh picture."""
    it = _key_of(pdir, key)
    row = _row_of(pdir, style, scene, n)
    setdir = pictures.set_dir(pdir, style)
    review, rv = pictures._review(pdir, style, row)
    if how == "picture":
        old = pictures._image(setdir, row)
        if old is not None:
            vdir = setdir / "versions"
            vdir.mkdir(exist_ok=True)
            dest = vdir / f"image-{row:04d}.v{len(rv.get('versions', [])) + 1}.png"
            shutil.move(str(old), dest)
            rv.setdefault("versions", []).append(dest.relative_to(setdir).as_posix())
        assets.copy_out(pdir, it["id"], setdir / "images" / "reused" / f"image-{row:04d}.png")
        rv["approved"] = False
    elif how == "prompt":
        rv["prompt"] = it["prompt"]
        rv["approved"] = False
        pictures._rewrite_row(pdir, style, row, prompt=it["prompt"], seed=it["seed"] if isinstance(it.get("seed"), int) else None)
    elif how == "layout":
        ref = f"layout-{row:04d}.png"
        assets.copy_out(pdir, it["id"], setdir / "keyframe_refs" / ref)
        f = setdir / "all_images.csv"
        rows = list(csv.DictReader(open(f, newline="", encoding="utf-8")))
        refs = [r for r in (rows[row - 1].get("refs") or "").split("|") if r and not r.startswith(("layout-", "master-"))]
        rows[row - 1]["refs"] = "|".join([ref, *refs])
        if not rows[row - 1]["prompt"].startswith(pictures.LOCK_TEXT):
            rows[row - 1]["prompt"] = f"{pictures.LOCK_TEXT}. {rows[row - 1]['prompt']}"
        with open(f, "w", newline="", encoding="utf-8") as fh:
            wr = csv.DictWriter(fh, list(rows[0]))
            wr.writeheader()
            wr.writerows(rows)
        rv["approved"] = False
    else:
        raise ValueError("how is picture, prompt or layout")
    rv["reused_from"] = {"item": it["id"], "how": how, "file": it["file"], "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "may_not_match": stale(pdir, it)}
    pictures._write(pictures.pdir_of(pdir, style) / "review.json", review)
    return rv


def auto_reuse(pdir: Path, style: str, min_score: float = 8.0) -> dict:
    """Fill every shot that has no picture with its best library match when it scores >= min_score. The saving is shown in GPU time
    (and in dollars when a paid service is used)."""
    st = pictures.status(pdir, style)
    used = []
    for s in st["shots"]:
        if s["image"]:
            continue
        best = next(iter(matches(pdir, style, s["scene"], s["shot"], 1)), None)
        if best and best["match"] >= min_score and not best["may_not_match"]:
            reuse(pdir, style, s["scene"], s["shot"], best["key"], "picture")
            used.append({"row": s["row"], "item": best["id"], "match": best["match"]})
    tier = production.load(pdir)["tier"]
    return {"reused": used, "gpu_seconds_saved": len(used) * production.GPU_SECONDS[tier]["picture"],
            "dollars_saved_if_paid": round(len(used) * production.PAID_DOLLARS[tier]["picture"], 2)}
