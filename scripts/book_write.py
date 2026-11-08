#!/usr/bin/env python3
"""Step 3 of a new book: Claude writes the shots, narration, sound and music for each chapter.

  python3 book_write.py <project> [--narration condensed|verbatim|dialogue] [--words-per-shot N] [--min-shots 1]
        [--max-shots 12] [--chapters 1-10 | all] [--model sonnet] [--workers 2] [--force] [--dry-run] [--scenes]

How many shots a chapter gets: ceil(chapter words / words-per-shot), clamped to min..max, unless
projects/<project>/overrides.json sets {"5": {"shots": 10}} for that chapter.
Narration:
  condensed  Claude writes a short (<= 12 words) narration line per shot that summarises that part of the chapter.
  verbatim   the book's own words, split into consecutive slices at sentence ends (exact text, written by this script,
             not by Claude); Claude only writes the pictures, sound and music for each slice.
  dialogue   only the words inside double quotes are spoken (exact text, found by this script). Claude only says WHICH
             character speaks each quote. A shot with no quote is silent. A quote that starts in one slice belongs to
             that shot even if it ends in the next.
One resumable Claude call per chapter; finished chapters (scripts/chapter-NNN.json) are skipped unless --force.
--dry-run prints the plan and estimates without calling Claude.
--scenes: one more call per chapter finds where its scenes begin (scripts/outline-NNN.json) and what stays true in each: place, time of day, weather, what
people wear, injuries. Shots are then shared out scene by scene, so no shot straddles two scenes and a new scene never "continues" the shot before it.
"""
import argparse, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from bookkit import (sentences, character_token, continuity_file, shot_negative, CLIP_SECONDS, COST, cost_note, voice_id, WORDS_PER_SECOND, llm_json, compose_prompt, group_chapters,
                     project_dir, read_json, shot_count, slice_text, strip_verse_numbers, words, write_json)
import json

ap = argparse.ArgumentParser()
ap.add_argument("project")
ap.add_argument("--narration", choices=["condensed", "verbatim", "dialogue"], default="condensed")
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
ap.add_argument("--look", default="", help="the film's look (model_advisor.LOOKS): characters only change with age in live_action; blank counts as live action")
ap.add_argument("--scenes", action="store_true", help="find each chapter's scenes first (one more AI call per chapter)")
ap.add_argument("--clip-seconds", type=float, default=CLIP_SECONDS, help="length of one clip from the chosen video model; the shots are written to fit it")
args = ap.parse_args()
if not 1 <= args.clip_seconds <= 30:
    sys.exit("--clip-seconds must be 1-30")
CLIP_SECONDS = args.clip_seconds
NARRATION_WORDS = max(6, round(CLIP_SECONDS * 3))      # about what fits a clip at a natural speaking pace

pdir = project_dir(args.project)
index = read_json(pdir / "chapters.json")
if not index:
    sys.exit("run book_ingest.py first (no chapters.json)")
continuity = read_json(continuity_file(pdir))
if not continuity and not args.dry_run:
    sys.exit(f"run book_continuity.py first (no {pdir.name}.json)")
overrides = read_json(pdir / "overrides.json", {})
wps = args.words_per_shot or (25 if args.narration == "verbatim" else 60)

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

if args.look and not global_positives and not global_negatives:      # no Global Parameters saved: the film's look still decides the style words
    import model_advisor
    if args.look in model_advisor.STYLE:
        global_positives = model_advisor.STYLE[args.look]["positives"]
        global_negatives = model_advisor.STYLE[args.look]["negatives"]

chapters = index["chapters"]
if args.chapters != "all":
    a, _, b = args.chapters.partition("-")
    lo, hi = int(a), int(b or a)
    chapters = [c for c in chapters if lo <= c["n"] <= hi]


def plan_for(c):
    return shot_count(c["words"], wps, args.min_shots, args.max_shots, (overrides.get(str(c["n"])) or {}).get("shots"))


QUOTE_OPEN, QUOTE_CLOSE, QUOTE_MAX_WORDS = "\u201c", "\u201d", 400


def quotes_by_slice(slices):
    """The words inside double quotes (straight "..." or curly), exactly as written, for each slice. A quote belongs to the slice where it
    starts, even if it ends in a later one. A quote that never closes within QUOTE_MAX_WORDS is dropped (it was a stray mark, not speech)."""
    out = [[] for _ in slices]
    cur, start, is_open = [], 0, False
    for i, sl in enumerate(slices):
        for ch in sl:
            if not is_open:
                if ch in ('"', QUOTE_OPEN):
                    is_open, cur, start = True, [], i
            elif ch in ('"', QUOTE_CLOSE):
                text = " ".join("".join(cur).split())
                if words(text) >= 1:
                    out[start].append(text)
                is_open = False
            else:
                cur.append(ch)
                if len(cur) > QUOTE_MAX_WORDS * 8:
                    is_open = False
        if is_open:
            cur.append(" ")
    return out


def est_shot_seconds(c, n):
    if args.narration == "verbatim":
        return max(CLIP_SECONDS, c["words"] / n / WORDS_PER_SECOND + 0.4)
    if args.narration == "dialogue":
        text = strip_verse_numbers((pdir / "chapters" / f"chapter-{c['n']:03d}.txt").read_text())
        spoken = sum(words(q) for qs in quotes_by_slice(slice_text(text, n)) for q in qs)
        return max(CLIP_SECONDS, spoken / n / WORDS_PER_SECOND + 0.4)
    return max(CLIP_SECONDS, NARRATION_WORDS / WORDS_PER_SECOND + 0.4)


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
    print(f"Claude calls: {len(chapters) * (2 if args.scenes else 1)} ({'two' if args.scenes else 'one'} per chapter) + 1 for the continuity book")
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
SYSTEM = ("You are an expert hollywood filmmaker, storyboard artist, and technical prompt engineer. "
          "Translate the following book excerpt into a structured, shot-by-shot video production plan. "
          "Convert interior thoughts, feelings, and abstract descriptions into visible behavior, physical action, and environmental cues. "
          "You are also a sound designer: you adapt the book into short AI-video shots. "
          "You reply with a single JSON object and nothing else.")
(pdir / "scripts").mkdir(exist_ok=True)
char_names = [c["name"] for c in continuity["characters"]]
book_brief = {k: continuity[k] for k in ("setting", "visual_style", "music_theme") if k in continuity}
if continuity.get("creative_direction"):        # optional: only present if the director added one
    book_brief["creative_direction"] = continuity["creative_direction"]
book_brief["locations"] = [{"name": loc["name"], "look": loc["token"]} for loc in continuity.get("locations", [])]
location_names = [loc["name"] for loc in continuity.get("locations", [])]
voice_of = {c["name"].lower(): voice_id(c.get("voice")) for c in continuity["characters"]}   # a voice word (male, elder) or a Kokoro id


OUTLINE_SYSTEM = "You are a script supervisor breaking a book chapter into scenes. You reply with a single JSON object and nothing else."


def outline(c, text):
    """The chapter's scenes: [{"first": sentence number (from 1), "title", "location", "state"}], in order. Kept in scripts/outline-NNN.json."""
    path = pdir / "scripts" / f"outline-{c['n']:03d}.json"
    if path.exists() and not args.force:
        return read_json(path)["scenes"]
    sents = sentences(text)
    shown = "\n".join(f"{i}: {' '.join(s.split()[:14])}" for i, s in enumerate(sents, 1))

    def check(d):
        scenes = d.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            raise ValueError("'scenes' must be a list with at least one scene")
        firsts = [s.get("first") if isinstance(s, dict) else None for s in scenes]
        if not all(isinstance(f, int) and 1 <= f <= len(sents) for f in firsts) or firsts != sorted(set(firsts)) or firsts[0] != 1:
            raise ValueError(f"each 'first' must be a whole sentence number from 1 to {len(sents)}, in rising order, and the first scene must start at 1")

    data = llm_json(f"""CHAPTER {c['n']}: {c['title']}
The sentences of the chapter, numbered (each is cut to its first words):
{shown}

A new scene begins when the place or the time changes, or when the story moves to different people. Return ONE JSON object:
{{"scenes": [{{"first": 1, "title": "a few words", "location": "exact name from this list, or \"\": {location_names}",
 "state": "at most 30 words of what must stay the same in every shot of the scene: time of day, weather, what people wear and carry, injuries, who is present"}}]}}""",
                    OUTLINE_SYSTEM, model=args.model, engine=args.engine, validate=check)
    scenes = [{"first": s["first"], "title": str(s.get("title") or "").strip()[:80], "location": str(s.get("location") or "").strip(), "state": str(s.get("state") or "").strip()[:300]}
              for s in data["scenes"]]
    write_json(path, {"chapter": c["n"], "scenes": scenes})
    return scenes


def share_shots(sizes, n):
    """How many of n shots each scene gets, in proportion to its words, at least one each. When there are more scenes than shots, the caller merges scenes first."""
    total = sum(sizes) or 1
    exact = [n * s / total for s in sizes]
    shares = [max(1, int(x)) for x in exact]
    while sum(shares) > n:
        i = max((k for k in range(len(shares)) if shares[k] > 1), key=lambda k: shares[k] - exact[k])
        shares[i] -= 1
    while sum(shares) < n:
        i = max(range(len(shares)), key=lambda k: exact[k] - shares[k])
        shares[i] += 1
    return shares


def scene_slices(text, n, scenes):
    """(slices, scene of each slice). The chapter is cut at scene starts first and into roughly equal shots inside each scene."""
    sents = sentences(text)
    starts = [s["first"] - 1 for s in scenes]
    parts = [(" ".join(sents[a:b]), sc) for a, b, sc in zip(starts, starts[1:] + [len(sents)], scenes)]
    while len(parts) > max(n, 1):                # more scenes than shots: the shortest scene joins the one before it (or after, for the first)
        i = min(range(len(parts)), key=lambda k: words(parts[k][0]))
        j = i - 1 if i else 1
        a, b = min(i, j), max(i, j)
        parts[a:b + 1] = [(parts[a][0] + " " + parts[b][0], parts[a][1])]
    slices, owner = [], []
    for (part, sc), k in zip(parts, share_shots([words(p) for p, _ in parts], n)):
        cut = slice_text(part, k)
        slices += cut
        owner += [sc] * len(cut)
    return slices, owner


def build_prompt(c, slices, quotes=None, owner=None):
    brief = dict(book_brief, characters=[{"name": x["name"], "look": character_token(x, c["n"], args.look)} for x in continuity["characters"]])   # as they look in this chapter
    condensed = args.narration == "condensed"
    dialogue = args.narration == "dialogue"
    shown = "\n".join(f"[{i}] {' '.join(s.split()[:140])}{' ...' if len(s.split()) > 140 else ''}" for i, s in enumerate(slices, 1))
    if dialogue:
        shown = "\n".join(
            f"[{i}] {' '.join(s.split()[:140])}{' ...' if len(s.split()) > 140 else ''}" +
            "".join(f"\n    quote {i}.{k}: \"{' '.join(q.split()[:60])}\"" for k, q in enumerate(quotes[i - 1], 1))
            for i, s in enumerate(slices, 1))
    fields = ('"n": 1, "visual": "...", "characters": ["Name", ...], ' +
              ('"narration": "...", "speaker": "NARRATOR", ' if condensed else '') +
              ('"speakers": ["Name", ...], ' if dialogue else '') +
              '"sfx": "...", "music": "..."')
    narr_rule = ("- speakers: one entry per listed quote of that slice, in order: the exact character name from the list above who says it, "
                 "or NARRATOR if it is not one of them. Use [] for a slice with no quotes. The spoken words are added for you; do not write them.\n"
                 if dialogue else '') or (
        f"- narration: at most {NARRATION_WORDS} words, spoken by the narrator in the book's register, summarising or quoting that slice; if the "
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
            global_section += f"  Always avoid (do not write these words in a visual): {global_negatives}\n"

    scene_section = ""
    if owner:
        spans = []
        for i, sc in enumerate(owner, 1):
            if spans and spans[-1][2] is sc:
                spans[-1][1] = i
            else:
                spans.append([i, i, sc])
        scene_section = "\nSCENES (keep what each says in every shot of that scene):\n" + "\n".join(
            f"  slices {a}-{b}: {sc['title']}; location: {sc['location'] or 'not named'}; {sc['state']}" for a, b, sc in spans) + "\n"

    return f"""CONTINUITY BOOK (fixed for the whole book): {brief}
{global_section}{scene_section}
CHAPTER {c['n']}: {c['title']}
The chapter is cut into {len(slices)} consecutive slices. Each slice becomes ONE {CLIP_SECONDS:g}-second video clip:
{shown}

Write one shot for each slice, in order. Return ONE JSON object: {{"shots": [{{{fields}, "location": "...", "continues": false}}, ...]}} with exactly {len(slices)} shots.
Rules:
- visual: 30-55 words for a text-to-video model. Give shot size, camera movement, subject, action, setting, light. Describe
  people by appearance and role, never by name; show something concrete that happens in {CLIP_SECONDS:g} seconds; no on-screen text; nothing
  out of place for the book's era and world. Where the text is silent make a sensible cinematic choice.
- characters: exact names from this list who appear in the shot, or []: {char_names}
- location: exact name from this list if the shot happens there, otherwise "": {location_names}
- continues: true only if this shot carries on the same action in the same place from the shot before it, as an unbroken moment (a continuous
  walk, a fall, a fight). A cut to another angle, place or time is false. The first shot of the chapter is false.
{narr_rule}- sfx: at most 25 words of ambience and sound effects to hear in the shot (no speech, no music).
- music: at most 25 words describing the score for the shot (instruments, mood, tempo).
- Keep every shot true to its slice."""


def write_chapter(c):
    text = strip_verse_numbers((pdir / "chapters" / f"chapter-{c['n']:03d}.txt").read_text())
    owner = None
    if args.scenes:
        slices, owner = scene_slices(text, plan_for(c), outline(c, text))
    else:
        slices = slice_text(text, plan_for(c))
    n = len(slices)
    quotes = quotes_by_slice(slices) if args.narration == "dialogue" else None

    def check(d):
        shots = d.get("shots")
        if not isinstance(shots, list) or len(shots) != n:
            raise ValueError(f"'shots' must be a list of exactly {n} items (you gave {len(shots) if isinstance(shots, list) else 'none'})")
        for idx, s in enumerate(shots):
            if not isinstance(s.get("visual"), str) or len(s["visual"]) < 20:
                raise ValueError("every shot needs a visual description")
            if not isinstance(s.get("characters", []), list):
                raise ValueError("characters must be a list")
            if args.narration == "condensed" and (not s.get("narration") or words(s["narration"]) > max(40, NARRATION_WORDS * 2)):
                raise ValueError(f"every shot needs a narration of at most {NARRATION_WORDS} words")
            if quotes is not None:
                sp = s.get("speakers") or []
                want = len(quotes[idx])
                if not isinstance(sp, list) or len(sp) != want or not all(isinstance(x, str) for x in sp):
                    raise ValueError(f"shot {idx + 1} has {want} quote(s): 'speakers' must be a list of exactly {want} name(s)")

    data = llm_json(build_prompt(c, slices, quotes, owner), SYSTEM, model=args.model, engine=args.engine, validate=check)
    out = []
    for i, (s, sl) in enumerate(zip(data["shots"], slices), start=1):
        lines = None
        if quotes is not None:
            who = [(x.strip() if x.strip().lower() in voice_of else "NARRATOR") for x in (s.get("speakers") or [])]
            lines = [[w, q] + ([voice_of[w.lower()]] if w.lower() in voice_of and voice_of[w.lower()] else []) for w, q in zip(who, quotes[i - 1])]
            narration = " ".join(quotes[i - 1])
            s = dict(s, speaker=who[0] if who else "NARRATOR")
        else:
            narration = s["narration"].strip() if args.narration == "condensed" else sl
        speaker = (s.get("speaker") or "NARRATOR").strip()
        known = speaker.lower() in voice_of
        out.append({"n": i, "visual": s["visual"].strip(), "characters": [x for x in s.get("characters", []) if isinstance(x, str)],
                    "narration": narration, "speaker": speaker if known or speaker.upper() == "NARRATOR" else "NARRATOR",
                    "voice": voice_of.get(speaker.lower(), "") if known else "",
                    "sfx": (s.get("sfx") or "quiet ambient sound").strip()[:300],
                    "music": (s.get("music") or continuity["music_theme"]).strip()[:300],
                    "negative": shot_negative(global_negatives), "location": str(s.get("location") or "").strip(), "continues": i > 1 and s.get("continues") is True and not (owner and owner[i - 1] is not owner[i - 2]),
                    **({"scene": owner[i - 1]["title"]} if owner else {}),
                    "prompt": compose_prompt(s["visual"], s.get("characters", []), continuity, global_positives=global_positives, global_negatives=global_negatives,
                                             chapter=c["n"], look=args.look, location=s.get("location") or (owner[i - 1]["location"] if owner else "")), "slice": sl,
                    **({"lines": lines} if lines is not None else {})})
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
