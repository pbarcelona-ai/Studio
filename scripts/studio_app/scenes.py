"""Scene prompts: look at them, add details, get suggestions, save and revert."""
import re
import time
from bookkit import EDIT_FIELDS, continuity_file, SLUG_RE, llm_json, read_json, set_scene_field, write_json
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .cleanup import OUTPUT_PATTERN
from .common import PlanError, num
from .projects import read_csv_rows
from .steps import engine_args


# ---------------------------------------------------------------- scene prompts: look at them, add your own details, get suggestions, save
FIELD_LIMITS = {"prompt": 1500, "narration": 600, "sfx": 600, "music": 600}
FIELD_TITLES = {"prompt": "video prompt", "narration": "narration", "sfx": "sound-effects prompt", "music": "music prompt"}


def _scene_tables(slug):
    d = pdir(slug)
    if not SLUG_RE.match(slug) or not d.is_dir():
        raise PlanError("pick a book or prompt set first")
    shots = read_csv_rows(d / "all_shots.csv")
    if not shots:
        raise PlanError("this project has no video prompts yet (build the prompt files first)")
    return d, shots, read_csv_rows(d / "audio_shots.csv")


def _audio_row(shots, audio, i):
    if i < len(audio) and audio[i]["chapter"] == shots[i]["chapter"] and str(audio[i]["shot"]) == str(shots[i]["shot"]):
        return audio[i]
    return {}


def scene_data(slug, chapter=""):
    d, shots, audio = _scene_tables(slug)
    edits = read_json(d / "prompt_edits.json", {})
    order, counts, edited = [], {}, {}
    for r in shots:
        if r["chapter"] not in counts:
            order.append(r["chapter"]); counts[r["chapter"]] = 0; edited[r["chapter"]] = 0
        counts[r["chapter"]] += 1
    for e in edits.values():
        if e.get("chapter") in edited:
            edited[e["chapter"]] += 1
    chapter = chapter if chapter in counts else order[0]
    existing: dict = {}                                           # which downloaded files already exist, per row (shot-mode folders only)
    for top, pattern in (("videos", "shot-{:04d}.mp4"), ("audio", None)):
        for sub in sorted((d / top).glob("*")) if (d / top).is_dir() else []:
            if sub.is_dir() and not sub.name.endswith("_chapters"):
                for f in sub.iterdir():
                    m = OUTPUT_PATTERN.match(f.name)
                    if m and m.group(1) != "image":
                        existing.setdefault(int(m.group(2)), []).append(f"{top}/{sub.name}/{f.name}")
    items = []
    for i, r in enumerate(shots):
        if r["chapter"] != chapter:
            continue
        a = _audio_row(shots, audio, i)
        mine = edits.get(f"{chapter}#{r['shot']}", {}).get("fields", {})
        items.append({"shot": int(r["shot"]), "row": i + 1, "prompt": r["prompt"], "narration": a.get("narration", ""),
                      "sfx": a.get("sfx", ""), "music": a.get("music", ""), "has_audio": bool(a),
                      "edited": {k: v["original"] for k, v in mine.items()}, "clips": sorted(existing.get(i + 1, []))})
    return {"chapters": [{"chapter": c, "shots": counts[c], "edited": edited[c]} for c in order], "chapter": chapter, "shots": items}


def _check_scene_args(opt):
    slug = str(opt.get("project", ""))
    d, shots, audio = _scene_tables(slug)
    chapter, field = str(opt.get("chapter", "")), str(opt.get("field", "prompt"))
    try:
        shot = int(opt.get("shot"))
    except (TypeError, ValueError):
        raise PlanError("choose a shot") from None
    if field not in EDIT_FIELDS:
        raise PlanError("unknown field")
    idx = next((i for i, r in enumerate(shots) if r["chapter"] == chapter and str(r["shot"]) == str(shot)), None)
    if idx is None:
        raise PlanError("that scene does not exist in this project")
    if field != "prompt" and not _audio_row(shots, audio, idx):
        raise PlanError("this project has no narration/sound/music prompts to edit")
    return slug, d, shots, audio, idx, chapter, shot, field


def _current(shots, audio, idx, field):
    return shots[idx]["prompt"] if field == "prompt" else _audio_row(shots, audio, idx).get(field, "")


def prompt_save(opt):
    slug, d, shots, audio, idx, chapter, shot, _ = _check_scene_args({**opt, "field": "prompt"})
    fields = opt.get("fields") or {}
    if not isinstance(fields, dict) or not fields:
        raise PlanError("nothing to save")
    edits = read_json(d / "prompt_edits.json", {})
    key = f"{chapter}#{shot}"
    entry = edits.setdefault(key, {"chapter": chapter, "shot": shot, "fields": {}})
    saved, reverted = [], []
    for field, new in fields.items():
        if field not in EDIT_FIELDS:
            raise PlanError(f"unknown field {field!r}")
        if field != "prompt" and not _audio_row(shots, audio, idx):
            raise PlanError("this project has no narration/sound/music prompts to edit")
        new = " ".join(str(new).split())
        if not new or len(new) > FIELD_LIMITS[field]:
            raise PlanError(f"the {FIELD_TITLES[field]} must be 1 to {FIELD_LIMITS[field]} characters")
        cur = _current(shots, audio, idx, field)
        orig = entry["fields"].get(field, {}).get("original", cur)
        if new == orig:                                      # back to the original text: the same as reverting
            entry["fields"].pop(field, None); reverted.append(field)
        else:
            entry["fields"][field] = {"original": orig, "edited": new}; saved.append(field)
        set_scene_field(d, chapter, shot, field, new)
    if not entry["fields"]:
        edits.pop(key, None)
    else:
        entry["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_json(d / "prompt_edits.json", edits)
    return {"saved": saved, "reverted": reverted, "row": idx + 1}


def prompt_revert(opt):
    slug, d, shots, audio, idx, chapter, shot, _ = _check_scene_args({**opt, "field": "prompt"})
    edits = read_json(d / "prompt_edits.json", {})
    entry = edits.get(f"{chapter}#{shot}")
    if not entry:
        raise PlanError("this scene has no saved edits")
    only = opt.get("field")
    for field in [f for f in list(entry["fields"]) if not only or f == only]:
        set_scene_field(d, chapter, shot, field, entry["fields"][field]["original"])
        del entry["fields"][field]
    if not entry["fields"]:
        edits.pop(f"{chapter}#{shot}", None)
    write_json(d / "prompt_edits.json", edits)
    return {"row": idx + 1}


def prompt_suggest(opt):
    slug, d, shots, audio, idx, chapter, shot, field = _check_scene_args(opt)
    hint = " ".join(str(opt.get("hint") or "").split())
    if not hint or len(hint) > 1500:
        raise PlanError("write your idea or hint first (up to 1500 characters)")
    count = num(opt, "count", 3, int, 1, 4)
    current = " ".join(str(opt.get("current") or "").split()) or _current(shots, audio, idx, field)
    a = _audio_row(shots, audio, idx)
    same = [i for i, r in enumerate(shots) if r["chapter"] == chapter]
    before = shots[idx - 1]["prompt"][:350] if idx - 1 in same else ""
    after = shots[idx + 1]["prompt"][:350] if idx + 1 in same else ""
    source = ""
    mm = re.match(rf"^{re.escape(slug)}-(\d+)$", chapter)
    if mm:
        sc = read_json(d / "scripts" / f"chapter-{int(mm.group(1)):03d}.json", {})
        sh = (sc.get("shots") or [])
        source = (sh[shot - 1].get("slice") or "")[:900] if 0 < shot <= len(sh) else ""
    continuity = read_json(continuity_file(d), {})
    chars = "; ".join(f"{c['name']}: {c['token']}" for c in continuity.get("characters", []))[:1800]
    rules = {
        "prompt": ("a text-to-video prompt for ONE continuous shot of about 4 seconds: shot size, camera movement, subject, action, setting, light. "
                   "No on-screen text, nothing out of place for the book's era and world. When a face shows, frame the person from a medium shot to a close-up, because video models garble small faces. Keep any fixed character descriptions (like NAME: description) and any trailing style/quality "
                   "phrases exactly as they are in the current prompt. At most 900 characters.", 900),
        "narration": ("one line the narrator speaks over the shot, at most 14 words, in the same voice as the current line.", 200),
        "sfx": ("a description of ambience and sound effects to hear in the shot, at most 25 words, no speech or music.", 300),
        "music": ("a description of the score for the shot (instruments, mood, tempo), at most 25 words.", 300),
    }
    rule, limit = rules[field]
    prompt = (f"A director is refining ONE scene of a film adapted from a book. They want to change the {FIELD_TITLES[field]}.\n\n"
              f"CURRENT {FIELD_TITLES[field].upper()}:\n{current}\n\n"
              + (f"THE BOOK TEXT FOR THIS SHOT:\n{source}\n\n" if source else "")
              + (f"WHAT IS SPOKEN OVER THIS SHOT: {a.get('narration', '')}\n\n" if a.get("narration") and field != "narration" else "")
              + (f"PREVIOUS SHOT'S PROMPT (for continuity): {before}\n" if before else "") + (f"NEXT SHOT'S PROMPT: {after}\n" if after else "")
              + (f"\nCHARACTERS (keep their descriptions unchanged): {chars}\n" if chars and field == "prompt" else "")
              + f"\nTHE DIRECTOR'S IDEA OR HINT (include it, even though the book text does not mention it; be creative about how):\n{hint}\n\n"
              f"Write {count} different versions of the {FIELD_TITLES[field]} that work the idea in. Each must be {rule}\n"
              f'Reply with one JSON object: {{"suggestions": ["...", ...]}} with exactly {count} strings.')

    def check(data):
        sug = data.get("suggestions")
        if not isinstance(sug, list) or len(sug) != count or not all(isinstance(x, str) and 10 < len(x.strip()) <= limit + 100 for x in sug):
            raise ValueError(f"'suggestions' must be {count} strings, each at most {limit} characters")

    args = engine_args(opt)
    data = llm_json(prompt, "You are a film director and prompt writer. You reply with a single JSON object and nothing else.",
                    model=(args[3] if len(args) > 3 else None), engine=args[1], validate=check)
    return [x.strip() for x in data["suggestions"]]
