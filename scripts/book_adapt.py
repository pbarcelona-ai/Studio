#!/usr/bin/env python3
"""Step 2 of a new book (optional): turn the chapters into a plan for a film of a chosen length: logline, treatment, acts and a scene list.

  python3 book_adapt.py <project> --minutes 10 [--clip-seconds 4] [--focus "follow Eve"] [--engine claude] [--model sonnet]
        [--workers 2] [--force-summaries] [--fit-only]

1. each chapter is summarised (cached in adaptation/summaries/, so only new or changed chapters cost a call),
2. one call writes the logline, premise, ending and acts (each act has a share of the runtime and a range of chapters),
3. one call per act chooses its scenes, with chapters, a starting phrase copied from the book, importance and seconds,
4. plain code fits the scenes to the runtime in whole clips,
5. adaptation/adaptation.json and adaptation/treatment.md are written.
--fit-only reuses the summaries AND the saved act/scene proposals and only refits them to a new --minutes (no AI calls).
Writing a new plan removes the old screenplay (its scenes no longer exist).
See adr/0005-adaptation-stage.md.
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import adaptation as ad
import screenplay as sp
import crew
from bookkit import CLIP_SECONDS, COST, cost_note, llm_json, project_dir, read_json, write_json

ap = argparse.ArgumentParser()
ap.add_argument("project")
ap.add_argument("--minutes", type=float, default=10.0, help="length of the finished film")
ap.add_argument("--clip-seconds", type=float, default=CLIP_SECONDS, help="length of one clip from the chosen video model")
ap.add_argument("--focus", default="", help="a character, thread or chapter range the film must follow")
ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex"])
ap.add_argument("--model", default=None)
ap.add_argument("--workers", type=int, default=2)
ap.add_argument("--force-summaries", action="store_true")
ap.add_argument("--fit-only", action="store_true", help="refit the saved scene proposals to --minutes without calling the AI")
args = ap.parse_args()
if not ad.MIN_MINUTES <= args.minutes <= ad.MAX_MINUTES:
    sys.exit(f"--minutes must be {ad.MIN_MINUTES:g} to {ad.MAX_MINUTES}")
if not 1 <= args.clip_seconds <= 30:
    sys.exit("--clip-seconds must be 1-30")

pdir = project_dir(args.project)
index = read_json(pdir / "chapters.json")
if not index:
    sys.exit("run book_ingest.py first (no chapters.json)")
chapters = index["chapters"]
N = len(chapters)
target = args.minutes * 60
focus = " ".join(args.focus.split())[:300]
SUMMARY_SYSTEM = crew.system("story_analyst", pdir, "adapt-summary", "Write coverage of each chapter so the film can be planned from it.")
SHAPE_SYSTEM = crew.system(["development_executive", "screenwriter"], pdir, "adapt-shape", "Shape the book into a film of the target length: acts and how much of the book each one covers.")
SCENES_SYSTEM = crew.system("screenwriter", pdir, "adapt-scenes", "Turn the planned part of the book into a list of scenes.")
EXCERPT_WORDS = 5000


def chapter_text(n):
    return (pdir / "chapters" / f"chapter-{n:03d}.txt").read_text()


def excerpt(text):
    """A very long chapter is shown as its beginning, middle and end so one call stays inside the model's context."""
    w = text.split()
    if len(w) <= EXCERPT_WORDS:
        return text
    part = EXCERPT_WORDS // 3
    mid = len(w) // 2
    return " ".join(w[:part]) + "\n[...]\n" + " ".join(w[mid - part // 2: mid + part // 2]) + "\n[...]\n" + " ".join(w[-part:])


def summarise(c):
    f = ad.summary_file(pdir, c["n"])
    old = read_json(f)
    if old and not args.force_summaries and old.get("words") == c.get("words"):
        return c["n"], False
    prompt = f"""Book chapter {c['n']} "{c['title']}" ({c.get('words', 0)} words):

{excerpt(chapter_text(c['n']))}

Return ONE JSON object: {{"summary": "2-4 sentences of what happens", "characters": ["names of people who matter in it"],
"beats": ["3-6 short story beats in order"], "locations": ["places"], "importance": 1-5 (5 = the story cannot be told without it; 1 = could be cut unnoticed)}}"""
    d = llm_json(prompt, SUMMARY_SYSTEM, model=args.model, engine=args.engine, validate=ad.check_summary)
    f.parent.mkdir(parents=True, exist_ok=True)
    write_json(f, {"n": c["n"], "title": c["title"], "words": c.get("words"), **{k: d.get(k) for k in ("summary", "characters", "beats", "locations", "importance")}})
    return c["n"], True


def listing(lo, hi, limit=45):
    rows = []
    for c in chapters:
        if lo <= c["n"] <= hi:
            s = read_json(ad.summary_file(pdir, c["n"]), {})
            rows.append(f"{c['n']}. {c['title']} [importance {s.get('importance', '?')}, {c.get('words', 0)} words]: {' '.join(str(s.get('summary', '')).split()[:limit])}")
    return "\n".join(rows)


saved = ad.load(pdir) or {}
proposals = read_json(ad.adapt_dir(pdir) / "proposals.json", {})
if args.fit_only:
    if not proposals.get("shape") or not proposals.get("scenes"):
        sys.exit("nothing to refit: run the adaptation once without --fit-only first")
    shape, scene_lists = proposals["shape"], proposals["scenes"]
else:
    todo = list(chapters)
    print(f"adapting {args.project}: {N} chapters to about {args.minutes:g} minutes ({args.engine}/{args.model or 'default model'})", flush=True)
    failed = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {ex.submit(summarise, c): c for c in todo}
        for f in as_completed(futs):
            try:
                n, fresh = f.result()
                if fresh:
                    print(f"chapter {n}: summarised ({COST['calls']} calls{cost_note()} so far)", flush=True)
            except Exception as e:                       # one failed chapter must not hide the others' errors
                failed.append(futs[f]["n"])
                print(f"chapter {futs[f]['n']}: FAILED - {e}", flush=True)
    if failed:
        sys.exit(f"could not summarise chapters {sorted(failed)}; run again (finished ones are kept)")

    shape_prompt = f"""We are adapting the book "{index.get('pdf', args.project)}" into a film of about {args.minutes:g} minutes ({round(target / args.clip_seconds)} clips of
{args.clip_seconds:g} seconds). Here are its {N} chapters:

{listing(1, N)}
{('The film must follow: ' + focus) if focus else ''}
Return ONE JSON object: {{"logline": "one sentence", "premise": "2-3 sentences", "ending": "how the film ends, 1-2 sentences",
"acts": [{{"name": "Act I: ...", "purpose": "what this act does for the story", "share": 0.25 (its share of the runtime; shares sum to 1),
"first_chapter": 1, "last_chapter": 6}}]}}
Rules: 3 to 5 acts for a film over 20 minutes, 1 to 3 below that. Acts follow the book's order and together cover chapters 1-{N} without overlap. Give long
or crucial parts a larger share. Base the structure on the story, not on equal numbers of chapters."""
    shape = llm_json(shape_prompt, SHAPE_SYSTEM, model=args.model, engine=args.engine, validate=lambda d: ad.check_shape(d, N))
    acts = ad.normalise_acts(shape["acts"], N, target)
    scene_lists = []
    for a in acts:
        lo, hi = a["first_chapter"], a["last_chapter"]
        clips = max(1, round(a["seconds"] / args.clip_seconds))
        scene_prompt = f"""Film: {shape['logline']}
Act "{a['name']}": {a['purpose']}
This act must run about {a['seconds']} seconds ({clips} clips of {args.clip_seconds:g} s) and is taken from chapters {lo} to {hi}:

{listing(lo, hi)}
{('The film must follow: ' + focus) if focus else ''}
Choose the scenes of this act in story order. Return ONE JSON object: {{"scenes": [{{"title": "short", "summary": "what happens, 1-3 sentences, visible action",
"chapters": [chapter numbers it is taken from, within {lo}-{hi}], "anchor": "3-12 words copied EXACTLY from the book where the scene starts",
"seconds": proposed running time, "importance": 1-5, "keep": "full" (played out) | "condensed" | "montage" (many chapters compressed),
"location": "place", "characters": ["names"], "time_of_day": "dawn|day|dusk|night|unknown"}}]}}
Rules: the scene seconds should add up to about {a['seconds']}; each scene at least {args.clip_seconds:g} s; leave out what the film does not need
(chapters of low importance); do not invent events that are not in the book."""
        d = llm_json(scene_prompt, SCENES_SYSTEM, model=args.model, engine=args.engine, validate=lambda d, lo=lo, hi=hi: ad.check_scenes(d, lo, hi))
        scene_lists.append(d["scenes"])
        print(f"{a['name']}: {len(d['scenes'])} scenes ({COST['calls']} calls{cost_note()} so far)", flush=True)
    (ad.adapt_dir(pdir)).mkdir(parents=True, exist_ok=True)
    write_json(ad.adapt_dir(pdir) / "proposals.json", {"shape": shape, "scenes": scene_lists})

try:
    plan = ad.build_plan(shape, scene_lists, args.minutes, args.clip_seconds, N, meta={"focus": focus, "engine": args.engine, "model": args.model or ""})
except ad.AdaptationError as e:
    sys.exit(str(e))
texts = {c["n"]: chapter_text(c["n"]) for c in chapters}
missing = [s["id"] for s in plan["scenes"] if not ad.anchor_found(s.get("anchor", ""), [texts[c] for c in s["chapters"] if c in texts])]
for s in plan["scenes"]:
    s["anchor_found"] = s["id"] not in missing
if saved.get("pilot", {}).get("kind", "none") != "none":
    print("note: the earlier pilot choice was cleared by the new plan.")
ad.save(pdir, plan)
gone = sp.discard(pdir)
if gone:
    print(f"note: the old screenplay ({gone} scenes) belonged to the old plan and was removed.")
rt = ad.plan_runtime(plan)
print(f"done: {len(plan['scenes'])} scenes, {ad.total_clips(plan)} clips, {rt['minutes']:g} min (target {args.minutes:g}); {len(plan['cut'])} things left out; "
      f"{COST['calls']} AI calls{cost_note()}")
if missing:
    print(f"warning: the starting phrase of scenes {', '.join(missing)} was not found in the book text (paraphrased by the AI); check those scenes.")
print(f"treatment written to {ad.adapt_dir(pdir).name}/treatment.md")
