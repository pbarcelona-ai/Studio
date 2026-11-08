"""Write keyframes.csv for a book: one still-image prompt per shot, the first frame of each clip.

Usage: python3 scripts/make_keyframes_csv.py BOOK --width 1600 --height 640 [--refs SERIES] [--max-refs 2]

Rows match all_shots.csv one for one (row N here is row N there), so the image run's image-NNNN.png is the keyframe for shot row N.
The size is chosen by the Studio from the video model's shape (for example 2.4:1 for LTX-Video) and the image model's usual pixel
count, so the image-to-video run only trims a little. Existing keyframes are not touched; re-running only rewrites the CSV.

--refs SERIES: steer each keyframe with pictures of the characters in that shot, taken from the character series (the Characters
tab). The pictures are shrunk and copied to <book>/keyframe_refs/ref-<character>.png (the run uploads them next to the CSV) and each
row's "refs" column lists the ones it uses. Only image models that take reference pictures use them (FLUX.2 klein); others ignore them.
Which characters are in a shot: the "characters" column of all_shots.csv (written by book_build.py), or, for older CSVs, each
character's token label (for example "ADAM:") found in the shot's prompt.
"""
import argparse
import csv
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout  # noqa: E402  (project-local: finds projects/books/<book>)

ROOT = Path(__file__).resolve().parent.parent
# A video prompt describes motion; a keyframe is one still. This lead-in steers the image model to a single, sharp frame.
LEAD = "Film still, the opening frame of this shot, sharp focus, cinematic composition: "
NEGATIVE = "blurry, motion blur, text, subtitles, watermark, logo, frame border, collage, split screen, deformed, extra limbs"
PICTURE = (".png", ".jpg", ".jpeg", ".webp")
REF_SIDE = 448            # longest side of a reference picture: each one adds about (side/16)^2 tokens, and a T4 has little room to spare


def ref_picture(ct, series, name):
    """The first reference picture that exists for this character: its saved reference list, then its references/ folder."""
    char = ct.load_character(series, name) or {}
    for r in char.get("reference_images") or []:
        p = Path(r) if Path(r).is_absolute() else ROOT / r
        if p.is_file() and p.suffix.lower() in PICTURE:
            return p
    folder = ct.get_reference_dir(series, name)
    pics = sorted(x for x in folder.iterdir() if x.suffix.lower() in PICTURE) if folder.is_dir() else []
    return pics[0] if pics else None


def save_small(src, dst):
    """Copy a reference picture, shrunk to REF_SIDE on its longest side (plain copy if Pillow is missing or the file is unreadable)."""
    try:
        from PIL import Image
        img = Image.open(src).convert("RGB")
        img.thumbnail((REF_SIDE, REF_SIDE))
        img.save(dst, "PNG")
    except Exception:          # no Pillow, or a picture Pillow cannot read: the run resizes it instead
        shutil.copyfile(src, dst)


def shot_characters(row, labels):
    """Character names in this shot: the characters column if the CSV has one, else the token labels found in the prompt."""
    listed = [n.strip() for n in (row.get("characters") or "").split("|") if n.strip()]
    if listed or "characters" in row:
        return listed
    prompt = row.get("prompt") or ""
    return [name for name, label in labels.items() if re.search(r"(?<![A-Za-z])" + re.escape(label) + r":", prompt)]


def build_refs(d, shots, series, max_refs):
    """Fill each shot's refs and copy the pictures to <book>/keyframe_refs/. Returns (refs per row, characters used, characters without a picture)."""
    import character_tokens as ct            # project-local; only needed with --refs
    labels = {}
    for c in ct.list_characters(series):
        name = c.get("name") or ""
        token = (ct.load_character(series, name) or c).get("visual_token") or ""
        if name and ":" in token:
            labels[name] = token.split(":", 1)[0].strip()
    out_dir = d / "keyframe_refs"
    if out_dir.is_dir():
        shutil.rmtree(out_dir)                # only this run's pictures, so a renamed or removed character leaves nothing stale
    out_dir.mkdir()
    picked, missing, per_row = {}, set(), []
    for row in shots:
        names = []
        for name in shot_characters(row, labels):
            if len(names) >= max_refs:           # the first characters named are the ones the shot is about
                break
            if name not in picked and name not in missing:
                src = ref_picture(ct, series, name)
                if src is None:
                    missing.add(name)
                else:
                    fname = f"ref-{ct.slugify(name)}.png"
                    save_small(src, out_dir / fname)
                    picked[name] = fname
            if name in picked and picked[name] not in names:
                names.append(picked[name])
        per_row.append("|".join(names))
    return per_row, picked, missing


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("book")
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--refs", metavar="SERIES", help="character series whose pictures steer the keyframes")
    ap.add_argument("--max-refs", type=int, default=2, help="pictures per shot (1-3; each one costs GPU memory)")
    a = ap.parse_args(argv)
    if not (256 <= a.width <= 2048 and 256 <= a.height <= 2048):
        sys.exit("width and height must be 256-2048")
    if not 1 <= a.max_refs <= 3:
        sys.exit("--max-refs must be 1-3")
    if a.refs and not layout.SLUG_RE.match(a.refs):          # same naming rule as projects: it is a folder name
        sys.exit(f"bad series name {a.refs!r}: use 2-40 lowercase letters, digits or underscores")
    try:
        d = layout.find_dir(a.book)
    except ValueError as e:              # not a valid project name
        sys.exit(str(e))
    if d is None:
        sys.exit(f"no such book: {a.book}")
    src = d / "all_shots.csv"
    if not src.exists():
        sys.exit(f"{src} not found: build the CSVs first")
    with open(src, newline="", encoding="utf-8") as fh:
        shots = list(csv.DictReader(fh))
    if not shots:
        sys.exit(f"{src} has no rows")
    refs = [""] * len(shots)
    if a.refs:
        refs, picked, missing = build_refs(d, shots, a.refs, a.max_refs)
        print(f"reference pictures: {len(picked)} character(s) from series '{a.refs}', used in {sum(1 for r in refs if r)} of {len(shots)} shots")
        if missing:
            print("   no picture yet for: " + ", ".join(sorted(missing)) + " (add one on the Characters tab)")
    elif (d / "keyframe_refs").is_dir():
        shutil.rmtree(d / "keyframe_refs")   # refs switched off: do not upload old pictures
    rows = [{"chapter": r.get("chapter", ""), "shot": r.get("shot", ""), "prompt": LEAD + (r.get("prompt") or "").strip(),
             "negative": NEGATIVE, "width": a.width, "height": a.height, "seed": r.get("seed", ""), "refs": ref}
            for r, ref in zip(shots, refs)]
    out = d / "keyframes.csv"
    tmp = out.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    tmp.replace(out)                    # whole file or nothing: a run never sees half a CSV
    print(f"keyframes.csv: {len(rows)} rows at {a.width}x{a.height} -> {out}")


if __name__ == "__main__":
    main()
