#!/usr/bin/env python3
"""Step 3 of a new book (optional, after book_adapt.py): write a screenplay for every scene of the plan.

  python3 book_screenplay.py <project> [--engine claude] [--model sonnet] [--workers 2] [--force] [--scenes S001,S004]

One AI call per scene: a scene heading, action lines and dialogue, taken from the scene's summary and the book text where it starts.
Scenes already written are kept (and scenes you edited are never overwritten, even with --force: delete the file to redo one).
Approval is kept only while no scene has changed; approve the screenplay on the Adapt card once you have read it.
"""
import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import adaptation as ad
import screenplay as sp
import crew
from bookkit import COST, WORDS_PER_SECOND, cost_note, continuity_file, llm_json, project_dir, read_json, words

ap = argparse.ArgumentParser()
ap.add_argument("project")
ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex", "hf", "local"])
ap.add_argument("--model", default=None)
ap.add_argument("--workers", type=int, default=2)
ap.add_argument("--force", action="store_true", help="rewrite scenes that already have a screenplay (except ones you edited)")
ap.add_argument("--scenes", default="", help="only these scene ids, e.g. S001,S004")
args = ap.parse_args()

pdir = project_dir(args.project)
plan = ad.load(pdir)
if not plan:
    sys.exit("run book_adapt.py first (no adaptation plan)")
LOGLINE = plan["logline"]
scenes = ad.active_scenes(plan)
if args.scenes:
    want = {x.strip() for x in args.scenes.split(",") if x.strip()}
    scenes = [s for s in scenes if s["id"] in want]
    if not scenes:
        sys.exit("none of those scenes is in the plan")
continuity = read_json(continuity_file(pdir), {})
names = [c["name"] for c in continuity.get("characters", [])]
SYSTEM = crew.system("screenwriter", pdir, "screenplay", "Adapt the book into a screenplay, one scene at a time.")
SOURCE_WORDS = 3000


def source_text(s):
    """Book text for the scene: from where its starting phrase occurs in each chapter it is taken from, SOURCE_WORDS in all."""
    chapters = sorted(set(s["chapters"]))
    each = max(300, SOURCE_WORDS // len(chapters))
    out = []
    for n in chapters:
        text = (pdir / "chapters" / f"chapter-{n:03d}.txt").read_text()
        start = 0
        words_a = re.findall(r"\w+", s.get("anchor", ""))
        if words_a:
            m = re.search(r"\W+".join(re.escape(w) for w in words_a), text, re.I)
            start = m.start() if m else 0
        out.append(" ".join(text[start:].split()[:each]))
    return "\n[...]\n".join(out)


def write_scene(s):
    existing = sp.load_scene(pdir, s["id"])
    if existing and (existing.get("edited") or not args.force):
        return s["id"], False
    budget = max(10, round(s["seconds"] * WORDS_PER_SECOND * 0.8))
    prompt = f"""Film: {LOGLINE}
Act: {s['act']}. Scene {s['id']} "{s['title']}" (about {s['seconds']:g} seconds on screen, treatment: {s.get('keep', 'condensed')}).
What happens: {s['summary']}
Place: {s.get('location') or 'unknown'}. Time: {s.get('time_of_day') or 'unknown'}. People: {', '.join(s.get('characters', [])) or 'unknown'}.
{('Recurring characters: ' + ', '.join(names)) if names else ''}

BOOK TEXT where the scene starts:
{source_text(s)}

Write the scene as a screenplay. Return ONE JSON object: {{"heading": "INT. PLACE - TIME", "elements": [
 {{"type": "action", "text": "what we SEE and HEAR, present tense, concrete and filmable"}},
 {{"type": "dialogue", "character": "NAME", "note": "optional: how it is said", "text": "the spoken line"}},
 {{"type": "transition", "text": "CUT TO:"}} ]}}
Rules: show, do not tell (thoughts become behaviour); keep to the book's events and, where you can, its own words for dialogue; all dialogue together at most about
{budget} words so the scene fits {s['seconds']:g} seconds; 2 to 12 elements; nothing out of place for the book's era and world; no camera angles."""
    d = llm_json(prompt, SYSTEM, model=args.model, engine=args.engine, validate=sp.check_scene)
    sp.save_scene(pdir, s["id"], d, edited=False)
    return s["id"], True


print(f"writing the screenplay for {len(scenes)} scenes ({args.engine}/{args.model or 'default model'}, {args.workers} at a time)", flush=True)
failed = []
with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
    futs = {ex.submit(write_scene, s): s for s in scenes}
    for f in as_completed(futs):
        s = futs[f]
        try:
            sid, fresh = f.result()
            print(f"scene {sid}: {'written' if fresh else 'kept'} ({COST['calls']} calls{cost_note()} so far)", flush=True)
        except Exception as e:                      # a failed scene must not stop the others
            failed.append(s["id"])
            print(f"scene {s['id']}: FAILED - {e}", flush=True)
total = sum(words(" ".join(e["text"] for e in (sp.load_scene(pdir, s["id"]) or {}).get("elements", []))) for s in scenes)
print(f"done. failed scenes: {sorted(failed) or 'none'}; {total:,} words in all. Read the screenplay on the Adapt card, then approve it.")
sys.exit(1 if failed else 0)
