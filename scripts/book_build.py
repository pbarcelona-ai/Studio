#!/usr/bin/env python3
"""Step 4 of a new book: turn the per-chapter scripts into the CSV files the generators use, and plan the movies.

  python3 book_build.py <project> [--minutes 10]

Reads projects/<project>/scripts/chapter-NNN.json and writes all_shots.csv, all_chapters.csv, audio_shots.csv,
audio_chapters.csv (same row order, row N of audio = row N of video) and movies.json (movies of about --minutes
minutes; each movie ends at the end of a chapter). Chapters without a script yet are left out.
"""
import argparse, csv, json, sys
from bookkit import apply_prompt_edits, apply_voice_cast, continuity_file, build_movies, project_dir, read_json

ap = argparse.ArgumentParser()
ap.add_argument("project")
ap.add_argument("--minutes", type=float, default=10.0)
args = ap.parse_args()

pdir = project_dir(args.project)
continuity = read_json(continuity_file(pdir), {})
prompts, audio = [], []
for f in sorted((pdir / "scripts").glob("chapter-*.json")):
    d = read_json(f)
    label = f"{args.project}-{d['chapter']:03d}"
    for s in d["shots"]:
        prompts.append({"chapter": label, "shot": s["n"], "prompt": s["prompt"],
                        "characters": "|".join(str(c) for c in s.get("characters", []))})     # who is in the shot (keyframe reference pictures)
        line = [s["speaker"], s["narration"]] + ([s["voice"]] if s.get("voice") else [])
        lines = s["lines"] if "lines" in s else [line]          # dialogue mode: one line per quote, none for a silent shot
        audio.append({"chapter": label, "shot": s["n"], "lines_json": json.dumps(lines, ensure_ascii=False),
                      "narration": s["narration"], "sfx": s["sfx"],
                      "music": f"cinematic score, {s['music'].rstrip('. ')}"[:330]})
if not prompts:
    sys.exit("no scripts yet: run book_write.py first")

AUDIO_FIELDS = ["chapter", "shot", "lines_json", "narration", "sfx", "music"]


def write(name, fields, rows):
    with open(pdir / name, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")    # all_chapters.csv leaves out the shots' characters column
        w.writeheader()
        w.writerows(rows)


def first_per_chapter(rows):
    seen, out = set(), []
    for r in rows:
        if r["chapter"] not in seen:
            seen.add(r["chapter"]); out.append(r)
    return out


write("all_shots.csv", ["chapter", "shot", "prompt", "characters"], prompts)
write("all_chapters.csv", ["chapter", "shot", "prompt"], first_per_chapter(prompts))
write("audio_shots.csv", AUDIO_FIELDS, audio)
write("audio_chapters.csv", AUDIO_FIELDS, first_per_chapter(audio))
kept = apply_prompt_edits(pdir)                          # your saved scene edits survive a rebuild
if kept:
    print(f"re-applied {kept} saved prompt edit(s)")
recast = apply_voice_cast(pdir)                          # and so does the voice cast (voice_cast.json)
if recast:
    print(f"voice cast applied to {len(recast)} row(s)")
plan = build_movies(pdir, args.minutes)
chapters = len({r["chapter"] for r in prompts})
print(f"{args.project}: {len(prompts)} shots in {chapters} chapters")
print(f"movies (every-shot mode): {len(plan['shots'])} x ~{args.minutes:g} min; "
      f"(one-clip-per-chapter mode): {len(plan['chapters'])}")
for m in plan["shots"][:8]:
    print(f"  movie {m['id']}: {m['first_chapter']} .. {m['last_chapter']}, rows {m['rows'][0]}-{m['rows'][1]}, "
          f"{m['clips']} clips, about {m['est_seconds'] / 60:.1f} min")
