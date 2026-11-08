"""Write keyframes.csv for a book: one still-image prompt per shot, the first frame of each clip.

Usage: python3 scripts/make_keyframes_csv.py BOOK --width 1600 --height 640

Rows match all_shots.csv one for one (row N here is row N there), so the image run's image-NNNN.png is the keyframe for shot row N.
The size is chosen by the Studio from the video model's shape (for example 2.4:1 for LTX-Video) and the image model's usual pixel
count, so the image-to-video run only trims a little. Existing keyframes are not touched; re-running only rewrites the CSV.
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout  # noqa: E402  (project-local: finds projects/books/<book>)

# A video prompt describes motion; a keyframe is one still. This lead-in steers the image model to a single, sharp frame.
LEAD = "Film still, the opening frame of this shot, sharp focus, cinematic composition: "
NEGATIVE = "blurry, motion blur, text, subtitles, watermark, logo, frame border, collage, split screen, deformed, extra limbs"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("book")
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    a = ap.parse_args(argv)
    if not (256 <= a.width <= 2048 and 256 <= a.height <= 2048):
        sys.exit("width and height must be 256-2048")
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
    rows = [{"chapter": r.get("chapter", ""), "shot": r.get("shot", ""), "prompt": LEAD + (r.get("prompt") or "").strip(),
             "negative": NEGATIVE, "width": a.width, "height": a.height, "seed": r.get("seed", "")} for r in shots]
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
