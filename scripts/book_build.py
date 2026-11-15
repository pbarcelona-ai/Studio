#!/usr/bin/env python3
"""Step 4 of a new book: turn the per-chapter scripts into the CSV files the generators use, and plan the movies.

  python3 book_build.py <project> [--minutes 10]

Reads projects/<project>/scripts/chapter-NNN.json and writes all_shots.csv, all_chapters.csv, audio_shots.csv,
audio_chapters.csv (same row order, row N of audio = row N of video) and movies.json (movies of about --minutes
minutes; each movie ends at the end of a chapter). Chapters without a script yet are left out.
"""
import argparse
import csv
import json
import re
import sys
from bookkit import recompose_scripts, apply_film_format, apply_prompt_edits, apply_voice_cast, continuity_file, build_movies, project_dir, read_json

ap = argparse.ArgumentParser()
ap.add_argument("project")
ap.add_argument("--minutes", type=float, default=10.0)
ap.add_argument("--recompose", action="store_true", help="first rewrite every shot's prompt with the current prompt rules (shot description first, fits the model's token window); no AI call")
ap.add_argument("--look", default="", help="the film's look (used with --recompose when the book has no saved Global Parameters)")
args = ap.parse_args()

pdir = project_dir(args.project)
import picture_record
picture_record.record_new(pdir)                          # remember what each picture shows before any of them moves
if args.recompose:
    import cast_lock
    changed, over = recompose_scripts(pdir, args.look, scene_of=cast_lock.shot_context(pdir), lock=cast_lock.load(pdir))
    print(f"prompts rewritten: {changed} changed ({over} were over the token window before)")
continuity = read_json(continuity_file(pdir), {})
prompts, audio = [], []
for f in sorted((pdir / "scripts").glob("chapter-*.json")):
    d = read_json(f)
    label = f"{args.project}-{d['chapter']:03d}"
    for s in d["shots"]:
        prompts.append({"chapter": label, "shot": s["n"], "prompt": s["prompt"], "negative": s.get("negative", ""),
                        "characters": "|".join(str(c) for c in s.get("characters", [])),      # who is in the shot (keyframe reference pictures)
                        "location": s.get("location", ""), "continues": "1" if s.get("continues") else ""})
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


import adaptation
import shot_order
PLAN = adaptation.load(pdir)
PLAN = None if PLAN is not None and PLAN.get("stale") else PLAN
OLD_ROWS = list(csv.DictReader(open(pdir / "all_shots.csv", newline="", encoding="utf-8"))) if (pdir / "all_shots.csv").is_file() else []
if PLAN:                                                   # the film follows the screenplay's scene order, not the chapter order
    new_order = shot_order.order(PLAN, prompts)
    if new_order != list(range(len(prompts))):
        prompts, audio = [prompts[i] for i in new_order], [audio[i] for i in new_order]
        print("shots put in the screenplay's scene order")
write("all_shots.csv", ["chapter", "shot", "prompt", "negative", "characters", "location", "continues"], prompts)
write("all_chapters.csv", ["chapter", "shot", "prompt", "negative"], first_per_chapter(prompts))
scene_rows: list = []
if PLAN:                                                   # music that follows the story: one cue per scene of the film plan (audio_scenes.csv)
    per_chapter: dict = {}
    for r in audio:
        per_chapter[r["chapter"]] = per_chapter.get(r["chapter"], 0) + 1
    by_scene: dict = {}
    for r in audio:
        m = re.search(r"(\d+)$", r["chapter"])
        sid = adaptation.shot_scene(PLAN, int(m.group(1)), int(r["shot"]), per_chapter[r["chapter"]]) if m else None
        r["scene"] = f"{args.project}-{sid}" if sid else ""
        if sid:
            by_scene.setdefault(sid, []).append(r["music"])
    theme = (continuity.get("music_theme") or "").strip().rstrip(".")
    for s in adaptation.active_scenes(PLAN):
        if s["id"] in by_scene:
            scene_rows.append({"chapter": f"{args.project}-{s['id']}", "shot": 1, "lines_json": "[]", "narration": "", "sfx": "",
                               "music": adaptation.scene_music_prompt(s, theme, by_scene[s["id"]])})
write("audio_shots.csv", AUDIO_FIELDS + (["scene"] if PLAN else []), audio)
if scene_rows:
    write("audio_scenes.csv", AUDIO_FIELDS, scene_rows)
else:
    (pdir / "audio_scenes.csv").unlink(missing_ok=True)
# One music cue per chapter: the book's theme first, so every chapter's cue belongs to the same score.
theme = (continuity.get("music_theme") or "").strip().rstrip(".")
write("audio_chapters.csv", AUDIO_FIELDS, [dict(r, music=f"{theme}; {r['music']}"[:330] if theme else r["music"]) for r in first_per_chapter(audio)])
kept = apply_prompt_edits(pdir)                          # your saved scene edits survive a rebuild
if kept:
    print(f"re-applied {kept} saved prompt edit(s)")
recast = apply_voice_cast(pdir)                          # and so does the voice cast (voice_cast.json)
if recast:
    print(f"voice cast applied to {len(recast)} row(s)")
import voices
redirected = voices.apply_direction(pdir)                # and how the lines are delivered (voice_direction.json)
if redirected:
    print(f"voice direction applied to {len(redirected)} row(s)")
apply_film_format(pdir)                                  # and the film's shape (film_format.json)
import clip_length
if clip_length.apply(pdir):                              # and the clip lengths you set on the storyboard (clip_lengths.json)
    print(f"clip lengths applied to {len(clip_length.load(pdir))} shot(s)")
if OLD_ROWS:                                             # pictures, clips and sounds already made follow their shots to their new places
    NEW_ROWS = list(csv.DictReader(open(pdir / "all_shots.csv", newline="", encoding="utf-8")))
    kept = shot_order.follow(pdir, OLD_ROWS, NEW_ROWS)
    if kept["moved"] or kept["set_aside"]:
        print(f"files that follow their shots: {kept['moved']} moved, {kept['set_aside']} set aside (their shot was rewritten; in replaced/)")
plan = build_movies(pdir, args.minutes)
import screenplay
screenplay.stamp_shots(pdir)                           # which approved screenplay these shots come from (the Storyboard card warns when it changes)
chapters = len({r["chapter"] for r in prompts})
print(f"{args.project}: {len(prompts)} shots in {chapters} chapters")
if scene_rows:
    print(f"music cues per scene: {len(scene_rows)} (audio_scenes.csv)")
print(f"movies (every-shot mode): {len(plan['shots'])} x ~{args.minutes:g} min; "
      f"(one-clip-per-chapter mode): {len(plan['chapters'])}")
for m in plan["shots"][:8]:
    print(f"  movie {m['id']}: {m['first_chapter']} .. {m['last_chapter']}, rows {m['rows'][0]}-{m['rows'][1]}, "
          f"{m['clips']} clips, about {m['est_seconds'] / 60:.1f} min")
