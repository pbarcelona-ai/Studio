"""Pictures in the master style, and the shot layouts (BOOK_TO_SCREEN_BUILD.md Sections 6 and 7.4a, milestone M6).

One picture per shot of the approved shot list, prompted by styles.assemble() (code, so every style gets the same structure) and steered by
the look-development picks of the characters and places in the shot. The pictures render as a prompt set
projects/prompts/<book>_px_<style>/ (all_images.csv, keyframe_refs/) with the usual image runners; row N is shot N of the list.

  pictures/<style>/shots.json    [{row, scene, shot, seed, parts, prompt, negative, refs}] (every part kept, for the Script Supervisor and
                                 the picture library)
  pictures/<style>/review.json   {row: {approved, note, prompt (the owner's own wording, if edited), versions}}
  pictures/<style>/layouts/      for each approved frame: the SHOT LAYOUT {seed, size, edges.png, depth.png?} that M7 uses to make the
                                 other styles with the same structure

Each tile can be approved, given a note, re-prompted, regenerated (the old picture is kept as a version) or swapped with another shot.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from pathlib import Path

import continuity_book
import gates
import layout
import production
import shot_list
import styles



class PictureError(RuntimeError):
    """A picture step cannot be done as asked; the message says why."""


def pdir_of(pdir: Path, sid: str) -> Path:
    styles.sdir(pdir, sid)                                   # checks the style id
    return pdir / "pictures" / sid


def set_name(pdir: Path, sid: str) -> str:
    return f"{pdir.name[:40 - 4 - len(sid)]}_px_{sid}"[:40]


def set_dir(pdir: Path, sid: str) -> Path:
    name = set_name(pdir, sid)
    return layout.find_dir(name) or layout.new_dir(name, "prompts")


def _read(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(p: Path, d) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def seed_of(book: str, scene: str, shot: int) -> int:
    """The shot's seed: the same in every style (Section 7.4b) and on every run."""
    return int(hashlib.sha256(f"{book}:{scene}:{shot}".encode()).hexdigest()[:8], 16) % 2_000_000_000


def location_of(heading: str) -> str:
    return re.sub(r"^(?:INT|EXT|I/E|INT\./EXT)[\./\s]+", "", heading, flags=re.I).split(" - ")[0].strip()


def _ref_name(name: str) -> str:
    return "ref-" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") + ".png"


def picked_refs(pdir: Path, sid: str) -> dict[str, Path]:
    """The look-development picks of a style: {character or location name: picture}. Characters use their front sheet."""
    st = styles.lookdev_status(pdir, sid)
    setdir = layout.find_dir(st["set"]) if st["set"] else None
    out: dict[str, Path] = {}
    for it in st["items"]:
        if it["pick"] is None or setdir is None or (it["kind"] == "character" and it["view"] != "front"):
            continue
        c = next((c for c in it["candidates"] if c["row"] == it["pick"] and c["image"]), None)
        if c:
            out[it["name"]] = setdir / c["image"]
    return out


LOCK_TEXT = ("Keep exactly the composition, camera angle, framing, character positions, poses, expressions and action of the first reference "
             "picture; change only the look, to this style")
IMG2IMG_STRENGTH = 0.55                  # Section 7.4c: from the master frame, for image models that take a starting picture


def write_prompts(pdir: Path, sid: str = "") -> dict:
    """The picture prompts of a style from the approved shot list and look development. The master style first; another style (Section 7.4b)
    only after the master's pictures are approved: each row then keeps the shot's seed, puts the approved master frame first among its
    reference pictures (the structure lock: image models that take reference pictures keep its layout), adds that style's own character
    sheets, and names the master frame and a strength for image models that start from a picture (7.4c)."""
    sl = shot_list.load(pdir)
    if not gates.approved(pdir, "shotlist", shot_list.gate_data(sl)):
        raise PictureError("Approve the shot list first: the pictures are made from it.")
    settings = production.load(pdir)
    sid = sid or settings["master"]
    if not gates.approved(pdir, "lookdev", styles.gate_data(pdir)):
        raise PictureError("Approve the look development first: the pictures use its style cards and character sheets.")
    card, tr, book = styles.card_of(pdir, sid), styles.translations_of(pdir, sid), continuity_book.load(pdir)
    refs = picked_refs(pdir, sid)
    master = settings["master"]
    master_frames: dict[int, Path] = {}
    if sid != master:
        if not gates.approved(pdir, "pictures", gate_data(pdir, master)):
            raise PictureError("Approve the master style's pictures first: every other style is made from them (same layout, same seed).")
        mst = status(pdir, master)
        mdir = layout.find_dir(mst["set"])
        master_frames = {s["row"]: mdir / s["image"] for s in mst["shots"] if mdir and s["image"]}
    w, h = styles.SIZES.get(settings["aspect"], styles.SIZES["16:9"])
    out = set_dir(pdir, sid)
    out.mkdir(parents=True, exist_ok=True)
    (out / "promptset.json").write_text(json.dumps({"type": "prompts", "pictures_of": pdir.name, "style": sid}), encoding="utf-8")
    rdir = out / "keyframe_refs"
    shutil.rmtree(rdir, ignore_errors=True)
    rdir.mkdir()
    review = _read(pdir_of(pdir, sid) / "review.json", {}) or {}
    shots: list[dict] = []
    rows: list[dict] = []
    for sc in sl["scenes"]:
        loc = location_of(sc["heading"])
        for s in sc["shots"]:
            a = styles.assemble(s, loc, card, tr, book)
            names = [c["name"] for c in a["parts"]["characters"]] + ([a["parts"]["location"]["name"]] if a["parts"]["location"] else [])
            use: list[str] = []
            row = len(shots) + 1
            init = ""
            if master_frames:
                if row not in master_frames:
                    raise PictureError(f"the master style has no picture for shot {row}")
                init = f"master-{row:04d}.png"
                shutil.copy2(master_frames[row], rdir / init)
                use.append(init)
            for n in names:
                if n in refs and len(use) < 3:
                    shutil.copy2(refs[n], rdir / _ref_name(n))
                    use.append(_ref_name(n))
            own = (review.get(str(row)) or {}).get("prompt")
            seed = seed_of(pdir.name, sc["id"], s["n"])
            prompt = f"{LOCK_TEXT}. {a['prompt']}" if init else a["prompt"]
            shots.append({"row": row, "scene": sc["id"], "shot": s["n"], "seed": seed, "parts": a["parts"], "prompt": prompt, "negative": a["negative"], "refs": use,
                          "structure": {"method": "reference", "master": init, "strength": IMG2IMG_STRENGTH} if init else None})
            rows.append({"prompt": own or prompt, "negative": a["negative"], "width": w, "height": h, "seed": seed, "steps": 30, "guidance": 5, "refs": "|".join(use),
                         "init_image": init, "strength": IMG2IMG_STRENGTH if init else ""})
    with open(out / "all_images.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    _write(pdir_of(pdir, sid) / "shots.json", {"style": sid, "set": out.name, "shots": shots})
    return {"style": sid, "set": out.name, "rows": len(rows)}


def _image(setdir: Path, row: int) -> Path | None:
    for d in sorted((setdir / "images").iterdir()) if (setdir / "images").is_dir() else []:
        f = d / f"image-{row:04d}.png"
        if f.is_file():
            return f
    return None


def status(pdir: Path, sid: str = "") -> dict:
    sid = sid or production.load(pdir)["master"]
    data = _read(pdir_of(pdir, sid) / "shots.json")
    if not data:
        return {"style": sid, "set": "", "shots": [], "approved": 0}
    setdir = layout.find_dir(data["set"])
    review = _read(pdir_of(pdir, sid) / "review.json", {}) or {}
    out = []
    for s in data["shots"]:
        img = _image(setdir, s["row"]) if setdir else None
        rv = review.get(str(s["row"]), {})
        out.append({**{k: s[k] for k in ("row", "scene", "shot", "seed", "prompt", "refs")}, "image": img.relative_to(setdir).as_posix() if img and setdir else "",
                    "approved": bool(rv.get("approved")) and img is not None, "note": rv.get("note", ""), "own_prompt": rv.get("prompt", ""),
                    "versions": rv.get("versions", [])})
    return {"style": sid, "set": data["set"], "shots": out, "approved": sum(1 for s in out if s["approved"])}


def _review(pdir: Path, sid: str, row: int) -> tuple[dict, dict]:
    data = _read(pdir_of(pdir, sid) / "shots.json")
    if not data or not 1 <= row <= len(data["shots"]):
        raise PictureError(f"no picture {row}")
    review = _read(pdir_of(pdir, sid) / "review.json", {}) or {}
    return review, review.setdefault(str(row), {})


def approve(pdir: Path, sid: str, row: int, yes: bool = True) -> dict:
    review, rv = _review(pdir, sid, row)
    setdir = set_dir(pdir, sid)
    img = _image(setdir, row)
    if yes and img is None:
        raise PictureError("that shot has no picture yet: render it first")
    rv["approved"] = yes
    _write(pdir_of(pdir, sid) / "review.json", review)
    if yes and img is not None:
        shot = _read(pdir_of(pdir, sid) / "shots.json")["shots"][row - 1]
        save_layout(img, pdir_of(pdir, sid) / "layouts" / f"{shot['scene']}-{shot['shot']:03d}", shot["seed"])
    return rv


def note(pdir: Path, sid: str, row: int, text: str) -> dict:
    review, rv = _review(pdir, sid, row)
    rv["note"] = " ".join(text.split())[:1000]
    _write(pdir_of(pdir, sid) / "review.json", review)
    return rv


def set_prompt(pdir: Path, sid: str, row: int, text: str) -> dict:
    """The owner's own wording for one picture ("" goes back to the assembled prompt). The next render uses it."""
    review, rv = _review(pdir, sid, row)
    text = " ".join(text.split())
    if len(text) > 2000:
        raise PictureError("a prompt is at most 2000 characters")
    rv["prompt"] = text
    rv["approved"] = False
    _write(pdir_of(pdir, sid) / "review.json", review)
    _rewrite_row(pdir, sid, row, prompt=text or None)
    return rv


def _rewrite_row(pdir: Path, sid: str, row: int, prompt: str | None = None, seed: int | None = None) -> None:
    f = set_dir(pdir, sid) / "all_images.csv"
    rows = list(csv.DictReader(open(f, newline="", encoding="utf-8")))
    shot = _read(pdir_of(pdir, sid) / "shots.json")["shots"][row - 1]
    rows[row - 1]["prompt"] = prompt if prompt else shot["prompt"]
    if seed is not None:
        rows[row - 1]["seed"] = str(seed)
    with open(f, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)


def prepare_regenerate(pdir: Path, sid: str, row: int) -> dict:
    """Before rendering one picture again: the current picture becomes a version, and the row gets a new seed."""
    review, rv = _review(pdir, sid, row)
    setdir = set_dir(pdir, sid)
    img = _image(setdir, row)
    if img is not None:
        vdir = setdir / "versions"
        vdir.mkdir(exist_ok=True)
        n = len(rv.get("versions", [])) + 1
        dest = vdir / f"image-{row:04d}.v{n}.png"
        shutil.move(str(img), dest)
        rv.setdefault("versions", []).append(dest.relative_to(setdir).as_posix())
    rv["approved"] = False
    shot = _read(pdir_of(pdir, sid) / "shots.json")["shots"][row - 1]
    new_seed = (shot["seed"] + 7919 * len(rv.get("versions", [])) + 1) % 2_000_000_000
    _write(pdir_of(pdir, sid) / "review.json", review)
    _rewrite_row(pdir, sid, row, prompt=rv.get("prompt") or None, seed=new_seed)
    return rv


def swap(pdir: Path, sid: str, a: int, b: int) -> None:
    """Swap the pictures of two shots (the owner dragged one onto the other); both lose their approval."""
    if a == b:
        return
    review, ra = _review(pdir, sid, a)
    _, rb = _review(pdir, sid, b)
    rb = review.setdefault(str(b), rb)
    setdir = set_dir(pdir, sid)
    fa, fb = _image(setdir, a), _image(setdir, b)
    if fa is None or fb is None:
        raise PictureError("both shots need a picture to swap")
    tmp = fa.with_name(fa.name + ".swap")
    fa.rename(tmp)
    fb.rename(fa)
    tmp.rename(fb)
    ra["approved"] = rb["approved"] = False
    _write(pdir_of(pdir, sid) / "review.json", review)


def save_layout(img: Path, dest: Path, seed: int) -> dict:
    """The SHOT LAYOUT of an approved frame (Section 7.4a): the seed, the size, an edge / line map and, when the depth model is installed (the
    optional 3D tools), a depth map. Pose skeletons and character boxes are added by M7 when a pose model is available."""
    from PIL import Image, ImageFilter, ImageOps
    dest.mkdir(parents=True, exist_ok=True)
    with Image.open(img) as im:
        size = im.size
        edges = ImageOps.autocontrast(im.convert("L").filter(ImageFilter.FIND_EDGES))
        edges.save(dest / "edges.png")
    depth = ""
    try:
        from studio_app.gallery import make_depth
        make_depth(img, dest / "depth.png")
        depth = "depth.png"
    except Exception:  # noqa: BLE001  the depth model is optional (about 2 GB); the edge map is always there
        depth = ""
    info = {"seed": seed, "size": list(size), "edges": "edges.png", "depth": depth, "pose": None, "boxes": None, "source": img.name}
    _write(dest / "layout.json", info)
    return info


def gate_data(pdir: Path, sid: str = "") -> list:
    st = status(pdir, sid)
    return [[s["row"], s["image"], s["approved"], s["own_prompt"]] for s in st["shots"]]


def gate_step(pdir: Path, sid: str) -> str:
    """The review gate of a style's pictures: "pictures" for the master style, "pictures_<style>" for the others."""
    return "pictures" if sid in ("", production.load(pdir)["master"]) else f"pictures_{sid}"


def approve_all_ready(pdir: Path, sid: str = "") -> dict:
    """The REVIEW GATE of the pictures: every shot has an approved picture."""
    st = status(pdir, sid)
    if not st["shots"]:
        raise PictureError("make the picture prompts first")
    left = [s for s in st["shots"] if not s["approved"]]
    if left:
        raise PictureError(f"{len(left)} picture(s) are not approved yet (the first is scene {left[0]['scene']} shot {left[0]['shot']})")
    return gates.approve(pdir, gate_step(pdir, sid), gate_data(pdir, sid))
