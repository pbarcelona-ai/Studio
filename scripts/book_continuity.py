#!/usr/bin/env python3
"""Step 2 of a new book: Claude reads samples of the book and writes the continuity book (<book name>.json).

  python3 book_continuity.py <project_name> [--model sonnet] [--force]

<book name>.json holds the visual style, the recurring characters (each with one exact visual description that is pasted
into every shot prompt, plus a narration voice) and key locations. You can edit it by hand; later steps reuse it.
"""
import argparse, sys
from bookkit import COST, VOICE_MAP, continuity_file, cost_note, llm_json, project_dir, read_json, write_json

ap = argparse.ArgumentParser()
ap.add_argument("project")
ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex"],
                help="which CLI writes the prompts (fcc-* route through your Free Claude Code proxy)")
ap.add_argument("--model", default=None, help="model name for that engine; blank = the engine's default (sonnet for claude)")
ap.add_argument("--force", action="store_true")
args = ap.parse_args()

pdir = project_dir(args.project)
index = read_json(pdir / "chapters.json")
if not index:
    sys.exit("run book_ingest.py first (no chapters.json)")
BOOK_FILE = continuity_file(pdir)
if BOOK_FILE.exists() and not args.force:
    sys.exit(f"{BOOK_FILE.name} already exists (use --force to rewrite it, or edit it by hand)")

chapters = index["chapters"]
pick = sorted({round(i * (len(chapters) - 1) / 9) for i in range(10)}) if len(chapters) > 10 else range(len(chapters))
samples = []
for i in pick:
    text = (pdir / "chapters" / f"chapter-{chapters[i]['n']:03d}.txt").read_text()
    samples.append(f"--- {chapters[i]['title']} (chapter {chapters[i]['n']}) ---\n{text[:5000]}")
titles = "; ".join(f"{c['n']}: {c['title']}" for c in chapters[:200])

SYSTEM = "You are a film production designer. You reply with a single JSON object and nothing else."
PROMPT = f"""We are adapting the book "{index.get('pdf', args.project)}" into a series of short AI-generated video clips with
narration and music. Read these excerpts and the chapter list, then write the continuity book.

CHAPTER LIST: {titles}

EXCERPTS:
{chr(10).join(samples)}

Return ONE JSON object with exactly these keys:
{{
 "title": "the book's title",
 "setting": "one sentence: era, region, world",
 "visual_style": "one sentence of film look to append to every shot: lighting, palette, lens, mood (no people)",
 "music_theme": "one sentence describing the score: instruments, mood, tempo",
 "characters": [
   {{"name": "Adam", "token": "a COMPLETE, fixed visual description under 200 characters: apparent age, build, skin, hair, beard, clothing, bearing",
     "voice": "one of: {', '.join(sorted(VOICE_MAP))}"}}
 ],
 "locations": [{{"name": "Cave of Treasures", "token": "a fixed visual description under 200 characters"}}]
}}
Rules: at most 12 characters (only those who recur or matter most; include groups such as "the Watchers" if they recur);
descriptions must be consistent with the text, and where the text is silent make a sensible cinematic choice;
each token must be self-contained (it is pasted verbatim into prompts, so do not refer to other characters);
no modern objects; at most 8 locations; "voice" must be one of the listed words.
"""


def check(d):
    for key in ("title", "setting", "visual_style", "music_theme"):
        if not isinstance(d.get(key), str) or not d[key].strip():
            raise ValueError(f"missing text field {key!r}")
    chars = d.get("characters")
    if not isinstance(chars, list):
        raise ValueError("characters must be a list")
    for c in chars:
        if not c.get("name") or not c.get("token"):
            raise ValueError("every character needs a name and a token")
        if len(c["token"]) > 260:
            raise ValueError(f"token for {c['name']} is too long ({len(c['token'])} characters, keep it under 200)")
        if c.get("voice") not in VOICE_MAP:
            raise ValueError(f"voice for {c['name']} must be one of {sorted(VOICE_MAP)}")


continuity = llm_json(PROMPT, SYSTEM, model=args.model, engine=args.engine, validate=check)
continuity.setdefault("locations", [])
write_json(BOOK_FILE, continuity)
print(f"{BOOK_FILE.name} written: {len(continuity['characters'])} characters, {len(continuity['locations'])} locations "
      f"({COST['calls']} call via {args.engine}{cost_note()})")
for c in continuity["characters"]:
    print(f"  {c['name']} [{c['voice']}]: {c['token'][:90]}")
