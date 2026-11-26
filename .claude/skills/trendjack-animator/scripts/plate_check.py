#!/usr/bin/env python3
# Library v2, 2026-11-12 - new: plates first. Every scene still must be made from approved plates (one per character,
# one per product from real product photos, one per recurring place), and the log says which plates each still used.
# From a buyer's first run: scene photos drawn from text gave the main character 6 different faces and the product
# a garbled label. Same file in reality-drama-engine and trendjack-animator.
# 2026-11-12b Real buyer test: a product plate that is the real phone photo (.jpg, which the skills allow) next to
# .png stills crashed the sheet ("sheet failed"); every photo is now made into a same-size PNG tile first.
"""Plate check: the plates are approved, every still lists the plates it was made from, and one sheet per plate
shows the plate next to every still that used it. Free (ffmpeg only, no Pillow).

Usage:
  python3 -I -B plate_check.py plates.json [out_dir] [--stills-dir stills] [--ad ad.json]

  --ad ad.json  (trendjack-animator) take the still log from the shots: stills/<shot id>.png made from the plates
                listed in that shot's "refs". A shot with no recurring person, product or place lists "none".

plates.json (paths relative to the file):
{
  "plates": {
    "woman45": {"kind": "character", "label": "the woman about 45 with a grey bob", "file": "plates/woman45.png",
                "approved": true},
    "bottle":  {"kind": "product", "label": "the bottle, 24 cm, cap on", "file": "plates/bottle.png",
                "real_photos": ["products/bottle_front.jpg"], "approved": true},
    "kitchen": {"kind": "location", "label": "the small white kitchen", "file": "plates/kitchen.png", "approved": true}
  },
  "stills": {
    "stills/s1_c01.png": ["woman45", "kitchen"],
    "stills/s2_c05.png": ["woman45", "bottle"]
  }
}

A still with no recurring person, product or place in it is logged as ["none"].
FAIL (exit 1) when: a plate file is missing; a plate is not "approved": true (a new or changed plate needs the user's
approval again, also under "accept everything"); a product plate has no real product photo; a still is not in the log,
lists no plate, or lists a plate that does not exist; more than 4 character plates (warning: needs the long-mode line).
Writes <out_dir>/plate_<id>.jpg (default out_dir: plate_sheets/ next to plates.json): the plate first, then every
still made from it. Claude opens every sheet: same face and hair, same product and label, same room. Remake drifting
stills FROM THE PLATE before any clip. Pass --stills-dir stills to also FAIL on image files in that folder that are
not in the log.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TILE_W, TILE_H, PER_ROW, MAX_PEOPLE = 300, 533, 6, 4
IMAGES = {".png", ".jpg", ".jpeg", ".webp"}


def sheet(photos, out):
    rows = -(-len(photos) // PER_ROW)
    cols = min(PER_ROW, len(photos))
    with tempfile.TemporaryDirectory(prefix="plate_sheet_") as tmp:
        tiles = []
        for k, ph in enumerate(photos):   # each photo to a same-size PNG tile first: jpg and png can be mixed
            t = Path(tmp) / f"t{k:03d}.png"
            p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(ph), "-vf",
                                f"scale={TILE_W}:{TILE_H}:force_original_aspect_ratio=decrease,"
                                f"pad={TILE_W}:{TILE_H}:(ow-iw)/2:(oh-ih)/2:color=0x202020,setsar=1,format=rgb24",
                                "-frames:v", "1", str(t)], capture_output=True, text=True)
            if p.returncode != 0:
                return f"sheet {out.name} failed on {Path(ph).name}: {p.stderr.strip()[-200:]}"
            tiles.append(t)
        p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", str(Path(tmp) / "t%03d.png"),
                            "-vf", f"tile={cols}x{rows}:padding=8:margin=8:color=0x101010",
                            "-frames:v", "1", "-q:v", "3", str(out)], capture_output=True, text=True)
        if p.returncode != 0:
            return f"sheet {out.name} failed: {p.stderr.strip()[-300:]}"
    return None


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) > 1 else 1
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = {k: argv[argv.index(k) + 1] for k in ("--stills-dir", "--ad") if k in argv and argv.index(k) + 1 < len(argv)}
    args = [a for a in args if a not in opt.values()]
    stills_dir = opt.get("--stills-dir")
    cfg_path = Path(args[0]).resolve()
    base = cfg_path.parent
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    plates, stills = cfg.get("plates") or {}, dict(cfg.get("stills") or {})
    if opt.get("--ad"):
        ad_path = Path(opt["--ad"]).resolve()
        for shot in json.loads(ad_path.read_text(encoding="utf-8")).get("shots", []):
            f = ad_path.parent / "stills" / f"{shot['id']}.png"
            if f.exists():
                # an empty refs list in ad.json = nothing recurring in the shot (B-roll); checked below as a WARN
                stills[str(f.relative_to(base)) if f.is_relative_to(base) else str(f)] = shot.get("refs") or ["none?"]
    out_dir = Path(args[1]).resolve() if len(args) > 1 else base / "plate_sheets"
    fails, warns = [], []
    if not plates:
        fails.append("no plates: make and approve the plates before any scene still (plates first)")
    for pid, p in plates.items():
        f = base / p.get("file", "")
        if not p.get("file") or not f.exists():
            fails.append(f"plate {pid}: file missing ({p.get('file')})")
        if p.get("approved") is not True:
            fails.append(f"plate {pid}: not approved. Show it to the user; a new or changed plate is approved again")
        if p.get("kind") == "product":
            reals = [base / r for r in p.get("real_photos") or []]
            if not reals or not all(r.exists() for r in reals):
                fails.append(f"plate {pid}: a product plate is built from real product photos (real_photos missing)")
        if p.get("kind") not in ("character", "product", "location"):
            fails.append(f"plate {pid}: kind must be character, product or location")
    chars = [k for k, p in plates.items() if p.get("kind") == "character"]
    if len(chars) > MAX_PEOPLE:
        warns.append(f"{len(chars)} character plates: over {MAX_PEOPLE} needs the user's long-mode line (plan_gate.py)")
    for s, used in stills.items():
        if not (base / s).exists():
            fails.append(f"still {s}: file missing")
        if not used:
            fails.append(f"still {s}: made without any plate (plates first: remake it with its plates attached; "
                         "a shot with no recurring person, product or place is logged as [\"none\"])")
        if used == ["none?"]:
            warns.append(f"still {s}: no plate in its shot's refs. Fine only if no recurring person, product or place "
                         "is in it (then write [\"none\"]); otherwise remake it with its plates attached")
            continue
        for pid in [u for u in used or [] if u != "none"]:
            if pid not in plates:
                fails.append(f"still {s}: uses unknown plate {pid}")
    if stills_dir:
        logged = {str((base / s).resolve()) for s in stills}
        for f in sorted((base / stills_dir).glob("*")):
            if f.suffix.lower() in IMAGES and str(f.resolve()) not in logged:
                fails.append(f"still {f.relative_to(base)}: not in the plate log (which plates was it made from?)")
    out_dir.mkdir(parents=True, exist_ok=True)
    for pid, p in plates.items():
        used_by = [base / s for s, u in stills.items() if pid in (u or []) and (base / s).exists()]
        if not (base / p.get("file", "")).exists():
            continue
        err = sheet([base / p["file"]] + used_by, out_dir / f"plate_{pid}.jpg")
        if err:
            fails.append(err)
        else:
            print(f"plate_{pid}.jpg: {p.get('kind')} '{p.get('label', pid)}' + {len(used_by)} still(s)")
    for w in warns:
        print("WARN: " + w)
    if fails:
        print("FAIL:\n  " + "\n  ".join(fails))
        return 1
    print(f"PASS: {len(plates)} approved plates, {len(stills)} stills, every still made from its plates. "
          "Now open every sheet and compare each still with its plate.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
