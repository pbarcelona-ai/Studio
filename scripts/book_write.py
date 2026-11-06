#!/usr/bin/env python3
"""Step 3 of a new book: Claude writes the shots, narration, sound and music for each chapter.

  python3 book_write.py <project> [--narration condensed|verbatim] [--words-per-shot N] [--min-shots 1]
        [--max-shots 12] [--chapters 1-10 | all] [--model sonnet] [--workers 2] [--force] [--dry-run]

How many shots a chapter gets: ceil(chapter words / words-per-shot), clamped to min..max, unless
projects/<project>/overrides.json sets {"5": {"shots": 10}} for that chapter.
Narration:
  condensed  Claude writes a short (<= 12 words) narration line per shot that summarises that part of the chapter.
  verbatim   the book's own words, split into consecutive slices at sentence ends (exact text, written by this script,
             not by Claude); Claude only writes the pictures, sound and music for each slice.
One resumable Claude call per chapter; finished chapters (scripts/chapter-NNN.json) are skipped unless --force.
--dry-run prints the plan and estimates without calling Claude.
"""
import argparse, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from bookkit import (CLIP_SECONDS, COST, cost_note, VOICE_MAP, WORDS_PER_SECOND, llm_json, compose_prompt, group_chapters,
                     project_dir, read_json, shot_count, slice_text, strip_verse_numbers, words, write_json)
import json

ap = argparse.ArgumentParser()
ap.add_argument("project")
ap.add_argument("--narration", choices=["condensed", "verbatim"], default="condensed")
ap.add_argument("--words-per-shot", type=int, default=None, help="default 60 (condensed) or 25 (verbatim)")
ap.add_argument("--min-shots", type=int, default=1)
ap.add_argument("--max-shots", type=int, default=12)
ap.add_argument("--chapters", default="all", help="'all' or a range like 3-12")
ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex"],
                help="which CLI writes the prompts (fcc-* route through your Free Claude Code proxy)")
ap.add_argument("--model", default=None, help="model name for that engine; blank = the engine's default (sonnet for claude)")
ap.add_argument("--workers", type=int, default=2)
ap.add_argument("--minutes", type=float, default=10.0, help="movie length used for the estimate")
ap.add_argument("--min-per-clip", type=float, default=3.0, help="ASSUMED GPU minutes per clip, for the estimate only")
ap.add_argument("--weekly-gpu-hours", type=float, default=30.0,
                help="ASSUMED free GPU hours per week (Kaggle is believed to give about 30; not verified), used for the warning")
ap.add_argument("--force", action="store_true")
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()

pdir = project_dir(args.project)
index = read_json(pdir / "chapters.json")
if not index:
    sys.exit("run book_ingest.py first (no chapters.json)")
bible = read_json(pdir / "bible.json")
if not bible and not args.dry_run:
    sys.exit("run book_bible.py first (no bible.json)")
overrides = read_json(pdir / "overrides.json", {})
wps = args.words_per_shot or (60 if args.narration == "condensed" else 25)

# Load global parameters for the project
global_params_path = pdir / "global_params.json"
if global_params_path.exists():
    try:
        global_params = json.loads(global_params_path.read_text())
        global_positives = global_params.get("positives", "")
        global_negatives = global_params.get("negatives", "")
    except Exception:
        global_positives = ""
        global_negatives = ""
else:
    global_positives = ""
    global_negatives = ""

chapters = index["chapters"]
if args.chapters != "all":
    a, _, b = args.chapters.partition("-")
    lo, hi = int(a), int(b or a)
    chapters = [c for c in chapters if lo <= c["n"] <= hi]


def plan_for(c):
    return shot_count(c["words"], wps, args.min_shots, args.max_shots, (overrides.get(str(c["n"])) or {}).get("shots"))


def est_shot_seconds(c, n):
    if args.narration == "verbatim":
        return max(CLIP_SECONDS, c["words"] / n / WORDS_PER_SECOND + 0.4)
    return max(CLIP_SECONDS, 12 / WORDS_PER_SECOND + 0.4)


# ---------------------------------------------------------------- dry run / estimate
if args.dry_run:
    rows, total_shots, total_sec = [], 0, 0.0
    groups = []
    for c in chapters:
        n = plan_for(c)
        sec = n * est_shot_seconds(c, n)
        total_shots += n; total_sec += sec
        rows.append((c["n"], c["title"][:28], c["words"], n, round(sec)))
        groups.append({"label": c["n"], "rows": (0, 0), "seconds": sec})
    print(f"{args.project}: {len(chapters)} chapters, narration={args.narration}, {wps} words per shot, "
          f"{args.min_shots}-{args.max_shots} shots per chapter")
    print(f"{'ch':>4}  {'title':28} {'words':>6} {'shots':>5} {'est sec':>7}")
    for r in rows[:12]:
        print(f"{r[0]:>4}  {r[1]:28} {r[2]:>6} {r[3]:>5} {r[4]:>7}")
    if len(rows) > 12:
        print(f"  ... {len(rows) - 12} more chapters")
    movies = group_chapters(groups, args.minutes * 60)
    print(f"\nTOTAL: {total_shots} clips, about {total_sec / 60:.0f} min of film, {len(movies)} movies of ~{args.minutes:.0f} min "
          f"(each ends at a chapter end)")
    avg = total_sec / max(total_shots, 1)
    if avg > 8:
        need = sum(c["words"] for c in chapters) / (8 * WORDS_PER_SECOND)
        print(f"WARNING: each shot would last about {avg:.0f} s but a clip is only {CLIP_SECONDS:.0f} s, so most of every shot "
              f"is a held frame under the narration. To keep shots near 8 s you need about {need:.0f} shots "
              f"(raise --max-shots), or use condensed narration.")
    print(f"Claude calls: {len(chapters)} (one per chapter) + 1 for the bible")
    gpu_hours = total_shots * args.min_per_clip / 60
    print(f"GPU time (assumption of {args.min_per_clip:g} min/clip, not measured): about {gpu_hours:.0f} hours "
          f"for video, plus audio")
    if gpu_hours > args.weekly_gpu_hours:
        print(f"WARNING: that is about {gpu_hours / args.weekly_gpu_hours:.1f} weeks of a free GPU allowance of {args.weekly_gpu_hours:g} "
              f"hours a week (assumed, not verified), and audio needs more on top. Options: lower --max-shots, raise --words-per-shot, "
              f"use fewer chapters (--chapters 1-10), or make only the first few movies at a time "
              f"(a movie is about {total_shots / max(len(movies), 1):.0f} clips = about "
              f"{total_shots / max(len(movies), 1) * args.min_per_clip / 60:.1f} GPU hours).")
    sys.exit(0)

# ---------------------------------------------------------------- real run
SYSTEM = ("You are a film director and sound designer adapting a book into short AI-video shots. "
          "You reply with a single JSON object and nothing else.")
(pdir / "scripts").mkdir(exist_ok=True)
char_names = [c["name"] for c in bible["characters"]]
bible_brief = {k: bible[k] for k in ("setting", "visual_style", "music_theme") if k in bible}
if bible.get("creative_direction"):        # optional: only present if the director added one
    bible_brief["creative_direction"] = bible["creative_direction"]
bible_brief["characters"] = [{"name": c["name"], "look": c["token"]} for c in bible["characters"]]
bible_brief["locations"] = [{"name": loc["name"], "look": loc["token"]} for loc in bible.get("locations", [])]
voice_of = {c["name"].lower(): VOICE_MAP.get(c.get("voice"), "") for c in bible["characters"]}


def build_prompt(c, slices):
    condensed = args.narration == "condensed"
    shown = "\n".join(f"[{i}] {' '.join(s.split()[:140])}{' ...' if len(s.split()) > 140 else ''}" for i, s in enumerate(slices, 1))
    fields = ('"n": 1, "visual": "...", "characters": ["Name", ...], ' +
              ('"narration": "...", "speaker": "NARRATOR", ' if condensed else '') +
              '"sfx": "...", "music": "..."')
    narr_rule = (
        "- narration: at most 12 words, spoken by the narrator in the book's register, summarising or quoting that slice; if the "
        "slice is a character speaking, you may give a short quoted line and set speaker to that character's exact name; "
        "otherwise speaker is NARRATOR.\n" if condensed else
        "- The narration is the book's own text and is added for you; do not write it.\n")

    # Include global parameters in the prompt to the LLM
    global_section = ""
    if global_positives or global_negatives:
        global_section = "\nGLOBAL PROMPT PARAMETERS (apply to ALL shots):\n"
        if global_positives:
            global_section += f"  Always include: {global_positives}\n"
        if global_negatives:
            global_section += f"  Always avoid: {global_negatives}\n"

    return f"""BIBLE (fixed for the whole book): {bible_brief}
{global_section}
CHAPTER {c['n']}: {c['title']}
The chapter is cut into {len(slices)} consecutive slices. Each slice becomes ONE 4-second video clip:
{shown}

Write one shot for each slice, in order. Return ONE JSON object: {{"shots": [{{{fields}}}, ...]}} with exactly {len(slices)} shots.
Rules:
- visual: 30-55 words for a text-to-video model. Give shot size, camera movement, subject, action, setting, light. Describe
  people by appearance and role, never by name; show something concrete that happens in 4 seconds; no on-screen text; nothing
  modern. Where the text is silent make a sensible cinematic choice.
- characters: exact names from this list who appear in the shot, or []: {char_names}
{narr_rule}- sfx: at most 25 words of ambience and sound effects to hear in the shot (no speech, no music).
- music: at most 25 words describing the score for the shot (instruments, mood, tempo).
- Keep every shot true to its slice."""


def write_chapter(c):
    text = strip_verse_numbers((pdir / "chapters" / f"chapter-{c['n']:03d}.txt").read_text())
    slices = slice_text(text, plan_for(c))
    n = len(slices)

    def check(d):
        shots = d.get("shots")
        if not isinstance(shots, list) or len(shots) != n:
            raise ValueError(f"'shots' must be a list of exactly {n} items (you gave {len(shots) if isinstance(shots, list) else 'none'})")
        for s in shots:
            if not isinstance(s.get("visual"), str) or len(s["visual"]) < 20:
                raise ValueError("every shot needs a visual description")
            if not isinstance(s.get("characters", []), list):
                raise ValueError("characters must be a list")
            if args.narration == "condensed" and (not s.get("narration") or words(s["narration"]) > 40):
                raise ValueError("every shot needs a narration of at most 12 words")

    data = llm_json(build_prompt(c, slices), SYSTEM, model=args.model, engine=args.engine, validate=check)
    out = []
    for i, (s, sl) in enumerate(zip(data["shots"], slices), start=1):
        narration = s["narration"].strip() if args.narration == "condensed" else sl
        speaker = (s.get("speaker") or "NARRATOR").strip()
        known = speaker.lower() in voice_of
        out.append({"n": i, "visual": s["visual"].strip(), "characters": [x for x in s.get("characters", []) if isinstance(x, str)],
                    "narration": narration, "speaker": speaker if known or speaker.upper() == "NARRATOR" else "NARRATOR",
                    "voice": voice_of.get(speaker.lower(), "") if known else "",
                    "sfx": (s.get("sfx") or "quiet ambient sound").strip()[:300],
                    "music": (s.get("music") or bible["music_theme"]).strip()[:300],
                    "prompt": compose_prompt(s["visual"], s.get("characters", []), bible, global_positives=global_positives, global_negatives=global_negatives), "slice": sl})
    write_json(pdir / "scripts" / f"chapter-{c['n']:03d}.json",
               {"chapter": c["n"], "title": c["title"], "narration_mode": args.narration, "shots": out})
    return c["n"], n


todo = [c for c in chapters if args.force or not (pdir / "scripts" / f"chapter-{c['n']:03d}.json").exists()]
print(f"{len(chapters)} chapters selected, {len(chapters) - len(todo)} already written, writing {len(todo)} "
      f"({args.narration}, {wps} words/shot, {args.engine}/{args.model or 'default model'}, {args.workers} at a time)", flush=True)
failed = []
with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
    futs = {ex.submit(write_chapter, c): c for c in todo}
    for f in as_completed(futs):
        c = futs[f]
        try:
            n, shots = f.result()
            print(f"chapter {n}: {shots} shots written ({COST['calls']} calls{cost_note()} so far)", flush=True)
        except Exception as e:
            failed.append(c["n"])
            print(f"chapter {c['n']}: FAILED - {e}", flush=True)
print(f"done. failed chapters: {sorted(failed) or 'none'}")
sys.exit(1 if failed else 0)
