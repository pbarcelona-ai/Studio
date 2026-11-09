"""Write keyframes.csv for a book: one still-image prompt per shot, the first frame of each clip.

Usage: python3 scripts/make_keyframes_csv.py BOOK --width 1600 --height 640 [--refs SERIES] [--max-refs 2] [--look claymation]

Rows match all_shots.csv one for one (row N here is row N there), so the image run's image-NNNN.png is the keyframe for shot row N.
The size is chosen by the Studio from the video model's shape (for example 2.4:1 for LTX-Video) and the image model's usual pixel
count, so the image-to-video run only trims a little. Existing keyframes are not touched; re-running only rewrites the CSV.

--refs SERIES: steer each keyframe with pictures of the characters in that shot, taken from the character series (the Characters
tab). The pictures are shrunk and copied to <book>/keyframe_refs/ref-<character>.png (the run uploads them next to the CSV) and each
row's "refs" column lists the ones it uses. Only image models that take reference pictures use them (FLUX.2 klein); others ignore them.
Which characters are in a shot: the "characters" column of all_shots.csv (written by book_build.py), or, for older CSVs, each
character's token label (for example "ADAM:") found in the shot's prompt.

Life stages: in a realistic film (--look live_action or none) a character with stages in the continuity book uses the pictures for the stage the
shot's chapter falls in: references/<character>/<stage label>/ in the series, else the character's usual pictures.
Locations: a picture at <book>/location_refs/<location name>.png (any picture type, name in lower case with underscores) steers the shots at that
location, when the character pictures leave room within --max-refs.

--look LOOK: the film's look (model_advisor.LOOKS: live_action, claymation, pixar_3d, pixar_disney). Each keyframe prompt then starts with that
look's words and its negatives are added, so the stills (and the clips animated from them) take the look even if the book's prompts were
written for another one. Without it the keyframes use the plain film-still lead below.
"""
import argparse
import csv
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bookkit  # noqa: E402  (project-local: life stages and the continuity book)
import layout  # noqa: E402  (project-local: finds projects/books/<book>)
import model_advisor  # noqa: E402  (project-local: the looks and their style words)

ROOT = Path(__file__).resolve().parent.parent
# A video prompt describes motion; a keyframe is one still. This lead-in steers the image model to a single, sharp frame.
LEAD = "Film still, the opening frame of this shot, sharp focus, cinematic composition: "
NEGATIVE = "blurry, motion blur, text, subtitles, watermark, logo, frame border, collage, split screen, deformed, extra limbs"
PICTURE = (".png", ".jpg", ".jpeg", ".webp")
REF_SIDE = 448            # longest side of a reference picture: each one adds about (side/16)^2 tokens, and a T4 has little room to spare


def save_small(src, dst):
    """Copy a reference picture, shrunk to REF_SIDE on its longest side (plain copy if Pillow is missing or the file is unreadable)."""
    try:
        from PIL import Image
        img = Image.open(src).convert("RGB")
        img.thumbnail((REF_SIDE, REF_SIDE))
        img.save(dst, "PNG")
    except (ImportError, OSError, ValueError):          # no Pillow, or a picture Pillow cannot read: the run resizes it instead
        shutil.copyfile(src, dst)


def shot_characters(row, labels):
    """Character names in this shot: the characters column if the CSV has one, else the token labels found in the prompt."""
    listed = [n.strip() for n in (row.get("characters") or "").split("|") if n.strip()]
    if listed or "characters" in row:
        return listed
    prompt = row.get("prompt") or ""
    return [name for name, label in labels.items() if re.search(r"(?<![A-Za-z])" + re.escape(label) + r":", prompt)]


def chapter_number(row):
    """The chapter number of a row: its chapter column is <book>-NNN. None if it is written some other way."""
    m = re.search(r"(\d+)$", str(row.get("chapter") or ""))
    return int(m.group(1)) if m else None


def location_picture(d, name):
    """The picture of a location in <book>/location_refs/, or None."""
    folder = d / "location_refs"
    slug = re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_")
    if not slug or not folder.is_dir():
        return None
    return next((x for x in sorted(folder.iterdir()) if x.stem.lower() == slug and x.suffix.lower() in PICTURE), None)


def build_refs(d, shots, series, max_refs, look=""):
    """Fill each shot's refs and copy the pictures to <book>/keyframe_refs/. Returns (refs per row, characters used, characters without a picture)."""
    import character_tokens as ct            # project-local; only needed with --refs
    book = {str(c.get("name", "")).lower(): c for c in (bookkit.read_json(bookkit.continuity_file(d), {}) or {}).get("characters", []) if isinstance(c, dict)}
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
    picked, tried, missing, per_row = {}, set(), set(), []
    for row in shots:
        names = []
        for name in shot_characters(row, labels):
            if len(names) >= max_refs:           # the first characters named are the ones the shot is about
                break
            stage = bookkit.stage_for(book.get(name.lower(), {}), chapter_number(row), look)
            key = (name, stage["label"]) if stage else (name, "")
            if key not in tried:
                tried.add(key)
                src = ct.first_reference(series, name, stage["label"] if stage else "")
                aged = bool(src) and bool(stage) and src.parent.name == ct.slugify(str(stage["label"]))
                if src is None:
                    missing.add(name)
                else:
                    fname = f"ref-{ct.slugify(name)}" + (f"-{ct.slugify(str(stage['label']))}" if aged else "") + ".png"
                    save_small(src, out_dir / fname)
                    picked[key] = fname
            if key in picked and picked[key] not in names:
                names.append(picked[key])
        if len(names) < max_refs:                # a place fits only after the people
            src = location_picture(d, row.get("location"))
            if src:
                fname = f"ref-place-{src.stem.lower()}.png"
                if not (out_dir / fname).exists():
                    save_small(src, out_dir / fname)
                names.append(fname)
        per_row.append("|".join(names))
    return per_row, picked, missing


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("book")
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--refs", metavar="SERIES", help="character series whose pictures steer the keyframes")
    ap.add_argument("--max-refs", type=int, default=2, help="pictures per shot (1-3; each one costs GPU memory)")
    ap.add_argument("--look", choices=sorted(model_advisor.LOOKS), help="the film's look: its words lead every keyframe prompt")
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
        refs, picked, missing = build_refs(d, shots, a.refs, a.max_refs, a.look or "")
        print(f"reference pictures: {len(picked)} character picture(s) from series '{a.refs}', used in {sum(1 for r in refs if r)} of {len(shots)} shots")
        if missing:
            print("   no picture yet for: " + ", ".join(sorted(missing)) + " (add one on the Characters tab)")
    elif (d / "keyframe_refs").is_dir():
        shutil.rmtree(d / "keyframe_refs")   # refs switched off: do not upload old pictures
    lead, negative = LEAD, NEGATIVE
    if a.look:
        lead = f"{model_advisor.lead(a.look)}, the opening frame of this shot, sharp focus, cinematic composition: "
        negative = f"{model_advisor.STYLE[a.look]['negatives']}, {NEGATIVE}"
        print(f"look: {model_advisor.LOOKS[a.look][0]}")
    rows = [{"chapter": r.get("chapter", ""), "shot": r.get("shot", ""), "prompt": lead + (r.get("prompt") or "").strip(),
             "negative": negative, "width": a.width, "height": a.height, "seed": r.get("seed", ""), "refs": ref}
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
