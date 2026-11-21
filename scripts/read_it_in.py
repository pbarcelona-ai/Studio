#!/usr/bin/env python3
"""READ IT IN (BOOK_TO_SCREEN_BUILD.md Section 5, milestone M3): any source -> a professional, scene-by-scene shooting script.

  python3 read_it_in.py <project> [--engine claude|codex|fake ...] [--model M] [--force]

One background job, with live progress ("Your story analyst is reading chapter 7 of 31"):
  5.1 ingest        the sources (sources.py), or the book's chapters
  5.2 coverage      Story Analyst. Long sources in two passes: chapter summaries (best dialogue word for word), then coverage over
                    the summaries plus the full text of the key chapters
  5.3 development   Development Executive, only for thin sources, when coverage says the story is too short, or for episodes
  5.4 plan          Screenwriter: which events are kept, merged or cut and why, sized to the length, recipe and faithfulness; the ending
                    is never rushed
  5.5 beat sheet    Screenwriter: acts (or per episode: hook, rising stakes, cliffhanger) with numbered beats
  5.6 treatment     Screenwriter: 1-3 pages of present-tense prose
  5.7 screenplay    Screenwriter, one act per call, with the previous act's last scene for continuity. Each scene also gets a hidden
                    block: characters present, location, time of day, props, wardrobe changes, emotional beat, screen time
  5.8 critique      Script Doctor + Director notes and scores; the Screenwriter revises; at most the recipe's rounds (2) or until both >= 8
  5.9 result        projects/books/<book>/readin/ (coverage.json, development.json, plan.json, beats.json, treatment.md, screenplay.json,
                    critique.json) and the Studio's own plan + screenplay (adaptation/, screenplay/), so every later step reads it
An existing screenplay source skips 5.2-5.7: it is parsed into scenes and only critiqued and polished.

Every finished stage is remembered (readin/state.json): running again carries on, unless the sources or the settings changed. `--engine
fake` writes a short, made-up but well-formed script without any AI (demo runs and tests).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptation  # noqa: E402
import crew  # noqa: E402
import production  # noqa: E402
import screenplay  # noqa: E402
import sources  # noqa: E402

STAGES = ("ingest", "coverage", "development", "plan", "beats", "treatment", "screenplay", "critique", "result")
TWO_PASS_TOKENS = 15000
SUMMARY_TOKENS = 12000          # a chapter or chunk larger than this is summarised in pieces
THIN_WORDS = 1500
KEY_CHAPTER_WORDS = 4000
BLOCK_KEYS = ("characters", "location", "time_of_day", "props", "wardrobe", "emotional_beat", "seconds")
FILM_BEATS = ("opening image", "inciting incident", "midpoint", "low point", "climax", "final image")
EPISODE_BEATS = ("hook", "rising stakes", "cliffhanger")
Ask = Callable[[str, str, str, Callable[[dict], None]], dict]          # (prompt, role, step, validate) -> reply


class ReadError(RuntimeError):
    """Read it in cannot go on; the message says why in plain words."""


def words(t: str) -> int:
    return len(t.split())


def tokens(t: str) -> int:
    return int(words(t) * 1.33)


def folder(pdir: Path) -> Path:
    return pdir / "readin"


def read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


# ---------------------------------------------------------------------------------------------- validators (the reply must have this shape)
def _need(d, keys: dict[str, type]) -> None:
    if not isinstance(d, dict):
        raise ValueError("reply with one JSON object")
    for k, t in keys.items():
        if not isinstance(d.get(k), t) or (t is str and not d[k].strip()) or (t is list and not d[k]):
            raise ValueError(f"'{k}' is missing or empty (it must be {t.__name__})")


def check_summary(d) -> None:
    _need(d, {"summary": str})
    if not isinstance(d.get("key_dialogue", []), list):
        raise ValueError("'key_dialogue' must be a list of the best lines, word for word")


def check_coverage(d) -> None:
    _need(d, {"logline": str, "genre": str, "tone": str, "themes": list, "characters": list, "key_events": list})
    if d.get("length") not in ("too_short", "right", "too_long"):
        raise ValueError("'length' must be too_short, right or too_long (is the story enough for the target length?)")
    for c in d["characters"]:
        if not isinstance(c, dict) or not str(c.get("name", "")).strip():
            raise ValueError("every character needs a 'name'")


def check_development(d) -> None:
    _need(d, {"story": str, "inciting_incident": str, "climax": str, "resolution": str})


def check_plan(d) -> None:
    _need(d, {"kept": list, "ending": str})
    for k in ("kept", "merged", "cut"):
        for e in d.get(k, []):
            if not isinstance(e, dict) or not str(e.get("event", "")).strip() or not str(e.get("reason", "")).strip():
                raise ValueError(f"every item of '{k}' needs 'event' and 'reason'")


def beats_checker(series: bool) -> Callable[[dict], None]:
    def check(d) -> None:
        _need(d, {"acts": list})
        names = []
        for a in d["acts"]:
            if not isinstance(a, dict) or not str(a.get("name", "")).strip() or not isinstance(a.get("beats"), list) or not a["beats"]:
                raise ValueError("every act needs a 'name' and a list of 'beats'")
            if not isinstance(a.get("share"), (int, float)) or a["share"] <= 0:
                raise ValueError("every act needs a 'share' of the runtime above 0")
            for b in a["beats"]:
                if not isinstance(b, dict) or not str(b.get("name", "")).strip() or not str(b.get("description", "")).strip():
                    raise ValueError("every beat needs 'name' and 'description'")
                names.append(b["name"].lower())
        missing = [n for n in (EPISODE_BEATS if series else FILM_BEATS) if not any(n in x for x in names)]
        if missing:
            raise ValueError(f"the beat sheet must name these beats: {', '.join(missing)}")
    return check


def check_treatment(d) -> None:
    _need(d, {"treatment": str})
    if words(d["treatment"]) < 120:
        raise ValueError("the treatment must be 1-3 pages of present-tense prose (at least a few paragraphs)")


def check_block(b) -> None:
    if not isinstance(b, dict):
        raise ValueError("every scene needs a 'block' object")
    for k in BLOCK_KEYS:
        if k not in b:
            raise ValueError(f"the scene block needs '{k}'")
    if not isinstance(b["characters"], list) or not isinstance(b["props"], list) or not isinstance(b["wardrobe"], list):
        raise ValueError("block characters, props and wardrobe are lists")
    if not isinstance(b["seconds"], (int, float)) or not 1 <= b["seconds"] <= 1200:
        raise ValueError("block 'seconds' is the scene's screen time in seconds")


def check_scenes(d) -> None:
    _need(d, {"scenes": list})
    for s in d["scenes"]:
        screenplay.check_scene(s)
        if not re.match(r"^(INT|EXT|INT\./EXT|EXT\./INT|I/E)[\.\s]", str(s["heading"]).strip(), re.I):
            raise ValueError("every scene heading starts with INT. or EXT. (e.g. 'INT. KITCHEN - NIGHT')")
        check_block(s.get("block"))


def check_notes(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("notes"), list):
        raise ValueError("reply with a JSON object with 'score' and a list of 'notes' (it may be empty)")
    if not isinstance(d.get("score"), (int, float)) or not 1 <= d["score"] <= 10:
        raise ValueError("'score' is a number from 1 to 10")
    for n in d["notes"]:
        if not isinstance(n, dict) or not str(n.get("note", "")).strip():
            raise ValueError("every note needs 'note' (and 'scene': its number, or 0 for the whole script)")


# ---------------------------------------------------------------------------------------------- the job
class ReadItIn:
    def __init__(self, pdir: Path, ask: Ask, say: Callable[[str], None] = print) -> None:
        self.pdir, self.ask, self._say = pdir, ask, say
        self.dir = folder(pdir)
        self.settings = production.load(pdir)
        self.recipe = crew.recipe(self.settings["recipe"]) if self.settings["recipe"] else {}
        self.series = bool(self.recipe.get("series"))
        crit = self.recipe.get("critique", {})
        self.min_score, self.max_rounds = float(crit.get("min_score", 8)), int(crit.get("max_rounds", 2))
        self.state = read_json(self.dir / "state.json", {}) or {}

    # ---- progress and state
    def say(self, stage: str, text: str) -> None:
        n = STAGES.index(stage) + 1
        write_json(self.dir / "progress.json", {"stage": stage, "step": n, "steps": len(STAGES), "text": text, "at": time.time()})
        self._say(f"[{n}/{len(STAGES)}] {text}")

    def done(self, stage: str) -> bool:
        return stage in self.state.get("done", []) and self.state.get("stamp") == self.stamp

    def finish(self, stage: str) -> None:
        self.state = {"stamp": self.stamp, "done": [*[s for s in self.state.get("done", []) if self.state.get("stamp") == self.stamp], stage]}
        write_json(self.dir / "state.json", self.state)

    def rules(self) -> str:
        s = self.settings
        return (f"Target length: about {s['target_minutes']} minutes. Rating: {production.RATINGS[s['rating']]} (keep every scene within it). "
                f"Faithfulness to the source: {production.FAITHFULNESS[s['faithfulness']]}. Aspect ratio {s['aspect']}."
                + (" The story is told in episodes." if self.series else ""))

    # ---- 5.1 ingest
    def ingest(self) -> dict:
        items = sources.load_index(self.pdir)
        if items:
            text = sources.merged_text(self.pdir)
            parts = [(f"{s['kind']}: {s['title']}", sources.document(self.pdir, s["id"]).text) for s in items]
            scripts = [s for s in items if s["kind"] == "screenplay"]
            thin = all(s["kind"] in ("idea", "picture", "comic", "website", "media") for s in items) or words(text) < THIN_WORDS
        else:
            idx = read_json(self.pdir / "chapters.json", {}) or {}
            parts = [(c.get("title") or f"Chapter {c['n']}", (self.pdir / "chapters" / f"chapter-{c['n']:03d}.txt").read_text(encoding="utf-8"))
                     for c in idx.get("chapters", []) if (self.pdir / "chapters" / f"chapter-{c['n']:03d}.txt").is_file()]
            text = "\n\n".join(f"=== {t} ===\n{b}" for t, b in parts)
            scripts, thin = [], words(text) < THIN_WORDS
        if words(text) < 1:
            raise ReadError("There is nothing to read yet: add a source (a book, an idea, pictures with their description ...) first.")
        if any(not s.get("described", True) for s in items):
            raise ReadError("Some pictures have no description yet: press Describe on them in the Sources card first.")
        pieces: list[tuple[str, str]] = []
        for title, body in parts:                           # pieces small enough for one summary call each
            cs = sources.chunks(body, SUMMARY_TOKENS, 300) if tokens(body) > SUMMARY_TOKENS else [body]
            pieces += [(title if len(cs) == 1 else f"{title} (part {i + 1})", c) for i, c in enumerate(cs) if c.strip()]
        self.stamp = hashlib.sha256(json.dumps([text, self.settings, crew.read_rules(self.pdir)["body"]], sort_keys=True).encode()).hexdigest()[:16]
        return {"text": text, "pieces": pieces, "thin": thin, "screenplay_only": bool(scripts) and len(scripts) == len(items), "scripts": scripts}

    # ---- 5.2 coverage
    def coverage(self, src: dict) -> dict:
        text, pieces = src["text"], src["pieces"]
        material = text
        if tokens(text) > TWO_PASS_TOKENS:
            sums = []
            for i, (title, body) in enumerate(pieces, 1):
                self.say("coverage", f"Your story analyst is reading chapter {i} of {len(pieces)}")
                key = hashlib.sha256(body.encode()).hexdigest()[:16]
                cache = self.dir / "summaries" / f"{key}.json"
                d = read_json(cache)
                if not d:
                    d = self.ask(f"Summarise this part of the source ({title}) for a film adaptation in about 150-300 words: what happens, who, "
                                 "where, and what changes. Keep the best lines of dialogue WORD FOR WORD in 'key_dialogue'. Rate how important "
                                 'this part is to the whole story (1-5). Reply as JSON: {"summary": "...", "key_dialogue": ["..."], "importance": 3}'
                                 f"\n\n{title}\n{body}", "story_analyst", "read it in: chapter summary", check_summary)
                    write_json(cache, d)
                sums.append((title, body, d))
            key_parts = sorted(range(len(sums)), key=lambda i: -float(sums[i][2].get("importance", 3)))[:2]
            material = "\n\n".join(f"=== {t} (summary) ===\n{d['summary']}" + (("\nKey dialogue:\n" + "\n".join(f'"{q}"' for q in d.get("key_dialogue", [])))
                                   if d.get("key_dialogue") else "") for t, _, d in sums)
            material += "\n\n" + "\n\n".join(f"=== {sums[i][0]} (full text: a key chapter) ===\n{' '.join(sums[i][1].split()[:KEY_CHAPTER_WORDS])}" for i in key_parts)
            write_json(self.dir / "summaries.json", [{"title": t, **d} for t, _, d in sums])
        self.say("coverage", "Your story analyst is writing the coverage")
        return self.ask("Write professional script coverage of this source for a film. " + self.rules() +
                        ' Reply as JSON: {"logline": "...", "genre": "...", "tone": "...", "themes": ["..."], "characters": [{"name": "...", '
                        '"role": "protagonist|antagonist|supporting", "description": "..."}], "key_events": ["..."], "filmable": "what can be shown '
                        'on screen, what needs inventing", "length": "too_short|right|too_long", "notes": "..."}\n\nSOURCE:\n' + material,
                        "story_analyst", "read it in: coverage", check_coverage)

    # ---- 5.3 development
    def development(self, src: dict, cov: dict) -> dict | None:
        if not (src["thin"] or cov.get("length") == "too_short" or self.series):
            return None
        self.say("development", "Your development executive is growing the story")
        eps = ' "episodes": [{"n": 1, "title": "...", "summary": "..."}],' if self.series else ""
        return self.ask("This source is thin for the target length" + (" or must be told in episodes" if self.series else "") + ". Expand it into a "
                        "full story with an inciting incident, rising stakes, a climax and a resolution, sized to the target length. Keep "
                        "everything the source gives; note what you invented. " + self.rules() +
                        f' Reply as JSON: {{"story": "the full story in prose",{eps} "inciting_incident": "...", "climax": "...", "resolution": "...", '
                        f'"invented": ["..."]}}\n\nCOVERAGE:\n{json.dumps(cov, ensure_ascii=False)}\n\nSOURCE:\n{src["text"][:60000]}',
                        "development_executive", "read it in: development", check_development)

    def _story(self, src: dict, cov: dict, dev: dict | None) -> str:
        sums = read_json(self.dir / "summaries.json")
        body = "\n".join(f"- {s['title']}: {s['summary']}" for s in sums) if sums else src["text"][:40000]
        return (f"COVERAGE:\n{json.dumps(cov, ensure_ascii=False)}\n\n" + (f"DEVELOPED STORY:\n{json.dumps(dev, ensure_ascii=False)}\n\n" if dev else "")
                + f"THE SOURCE (summarised when long):\n{body}")

    # ---- 5.4 - 5.6
    def plan(self, story: str) -> dict:
        self.say("plan", "Your screenwriter is planning the adaptation")
        return self.ask("Plan the adaptation: which events are kept, merged or cut, each with a reason, sized to the target length, the format and the "
                        "faithfulness setting. Never rush the ending: give it room. " + self.rules() +
                        ' Reply as JSON: {"kept": [{"event": "...", "reason": "..."}], "merged": [{"event": "...", "reason": "..."}], '
                        '"cut": [{"event": "...", "reason": "..."}], "ending": "how the film ends, and the time it gets"}\n\n' + story,
                        "screenwriter", "read it in: adaptation plan", check_plan)

    def beats(self, story: str, plan: dict) -> dict:
        self.say("beats", "Your screenwriter is writing the beat sheet")
        need = ", ".join(EPISODE_BEATS if self.series else FILM_BEATS)
        shape = "one act per episode, each with a hook, rising stakes and a cliffhanger" if self.series else "three acts"
        return self.ask(f"Write the beat sheet: {shape}, with numbered beats. It must name these beats: {need}. Give each act a 'share' of the "
                        "runtime (the shares add up to 1). " + self.rules() +
                        ' Reply as JSON: {"acts": [{"n": 1, "name": "Act One", "purpose": "...", "share": 0.25, "beats": [{"n": 1, "name": '
                        f'"Opening image", "description": "..."}}]}}]}}\n\nADAPTATION PLAN:\n{json.dumps(plan, ensure_ascii=False)}\n\n{story}',
                        "screenwriter", "read it in: beat sheet", beats_checker(self.series))

    def treatment(self, story: str, beats: dict) -> dict:
        self.say("treatment", "Your screenwriter is writing the treatment")
        return self.ask("Write the treatment: 1-3 pages of present-tense prose telling the whole film, beat by beat. " + self.rules() +
                        f' Reply as JSON: {{"treatment": "..."}}\n\nBEAT SHEET:\n{json.dumps(beats, ensure_ascii=False)}\n\n{story}',
                        "screenwriter", "read it in: treatment", check_treatment)

    # ---- 5.7 screenplay
    SCENE_SCHEMA = ('{"scenes": [{"heading": "INT. KITCHEN - NIGHT", "elements": [{"type": "action", "text": "..."}, {"type": "dialogue", '
                    '"character": "MARA", "note": "whispering", "text": "..."}, {"type": "transition", "text": "CUT TO:"}], "block": {"characters": '
                    '["MARA"], "location": "kitchen", "time_of_day": "night", "props": ["lamp"], "wardrobe": ["Mara: wet raincoat"], "emotional_beat": '
                    '"dread", "seconds": 45}}]}')
    SCREEN_RULES = ("Standard screenplay format: scene headings INT./EXT. LOCATION - TIME; present-tense action lines that describe only what can be "
                    "SEEN or HEARD (turn thoughts into things the camera can see and hear); a character's name in CAPS on first appearance in "
                    "the action; dialogue with the speaker; a short parenthetical as 'note' only when needed; (V.O.) in the character name for the "
                    "inner voice the source needs; transitions only where they matter. Each scene also gets the hidden 'block'. "
                    "EXACT COSTUME CONTINUITY: In every scene's block.wardrobe and action lines, specify each character's exact, singular full costume "
                    "with exact solid colours for top, bottoms, footwear, and accessories (e.g. 'solid brown t-shirt, blue jeans, white socks' — NEVER vague "
                    "patterns like 'striped shirt'). Carry that EXACT costume verbatim into every subsequent scene unless the story explicitly changes the "
                    "character's clothes in a new scene. "
                    "EXACT SCENE & LOCATION CONTINUITY: Keep the exact same location heading, spatial layout, key furniture, props, and lighting across "
                    "consecutive scenes in the same place unless the story explicitly transitions characters to a new location. "
                    "SMOOTH SCENE-BY-SCENE & MULTI-STORYLINE FLOW: Every scene must flow seamlessly into the next with strong narrative momentum; "
                    "jumps between separate storylines or subplots within the overall story are allowed, but must use smooth, motivated transitions "
                    "(visual match, sound bridge, thematic echo, or clean establishing handoff) so the story always reads and plays effortlessly.")

    def act_scenes(self, act: dict, n: int, of: int, treatment: str, plan: dict, cov: dict, prev: dict | None, seconds: float) -> list[dict]:
        self.say("screenplay", f"Your screenwriter is writing act {n} of {of}" + (" (episode)" if self.series else ""))
        cont = f"\n\nTHE PREVIOUS ACT'S LAST SCENE (continue from it):\n{json.dumps(prev, ensure_ascii=False)}" if prev else ""
        d = self.ask(f"Write the screenplay of act {n} ({act['name']}), about {round(seconds)} seconds of screen time in total, covering these beats in "
                     f"order. {self.SCREEN_RULES} " + self.rules() + f" Reply as JSON: {self.SCENE_SCHEMA}\n\nTHIS ACT:\n{json.dumps(act, ensure_ascii=False)}"
                     f"\n\nCHARACTERS:\n{json.dumps(cov.get('characters', []), ensure_ascii=False)}\n\nADAPTATION PLAN:\n{json.dumps(plan, ensure_ascii=False)}"
                     f"\n\nTREATMENT:\n{treatment}{cont}", "screenwriter", f"read it in: screenplay act {n}", check_scenes)
        return [{**screenplay.clean_scene(s), "block": s["block"], "act": n} for s in d["scenes"]]

    # ---- 5.8 critique
    def critique(self, scenes: list[dict], acts: list[dict], rounds_done: list[dict]) -> tuple[list[dict], list[dict]]:
        rounds = list(rounds_done)
        while len(rounds) < self.max_rounds:
            r = len(rounds) + 1
            script = script_text(scenes)
            self.say("critique", f"Your script doctor is reading draft {r}")
            doctor = self.ask("Critique this screenplay draft: structure, pacing, dialogue, and how clearly everything is VISUAL. Give a score from 1 to "
                              "10 and specific notes, each with its scene number (0 for the whole script). " + self.rules() +
                              ' Reply as JSON: {"score": 7, "notes": [{"scene": 3, "note": "..."}]}\n\n' + script, "script_doctor",
                              f"read it in: critique round {r}", check_notes)
            self.say("critique", f"Your director is reading draft {r}")
            director = self.ask("As the director, give notes on this draft: can every scene be shot, is the emotional line clear, are the "
                                "characters playable? Score 1-10 and notes with scene numbers (0 = whole script). " + self.rules() +
                                ' Reply as JSON: {"score": 7, "notes": [{"scene": 3, "note": "..."}]}\n\n' + script, "director",
                                f"read it in: critique round {r}", check_notes)
            rounds.append({"round": r, "doctor": doctor, "director": director})
            write_json(self.dir / "critique.json", rounds)
            if doctor["score"] >= self.min_score and director["score"] >= self.min_score:
                break
            scenes = self.revise(scenes, acts, doctor, director, r)
            write_json(self.dir / "screenplay.json", {"scenes": scenes})
        return scenes, rounds

    def revise(self, scenes: list[dict], acts: list[dict], doctor: dict, director: dict, r: int) -> list[dict]:
        out: list[dict] = []
        numbered = list(enumerate(scenes, 1))
        acts_used = sorted({s.get("act", 1) for s in scenes})
        for a in acts_used:
            mine = [(i, s) for i, s in numbered if s.get("act", 1) == a]
            nums = {i for i, _ in mine}
            notes = [{"from": who, **n} for who, d in (("script doctor", doctor), ("director", director)) for n in d["notes"]
                     if int(n.get("scene", 0) or 0) in nums or not n.get("scene")]
            if not notes:
                out += [s for _, s in mine]
                continue
            self.say("critique", f"Your screenwriter is revising act {a} of {len(acts_used)} (round {r})")
            d = self.ask(f"Revise these scenes of act {a} using the notes. Keep what works; keep the scene blocks accurate. {self.SCREEN_RULES} "
                         + self.rules() + f" Reply with the whole revised act as JSON: {self.SCENE_SCHEMA}\n\nNOTES:\n{json.dumps(notes, ensure_ascii=False)}"
                         f"\n\nSCENES (numbered as in the whole script):\n" + json.dumps([{"number": i, **s} for i, s in mine], ensure_ascii=False),
                         "screenwriter", f"read it in: revision round {r}", check_scenes)
            out += [{**screenplay.clean_scene(s), "block": s["block"], "act": a} for s in d["scenes"]]
        return out

    # ---- 5.9 result: the Studio's plan + screenplay files, so every later step works from this script
    def result(self, scenes: list[dict], cov: dict, acts: list[dict], plan: dict, treatment: str) -> dict:
        self.say("result", "Your producer is putting the script on your desk")
        clip = 4.0
        n_ch = max(1, len(read_json(self.pdir / "chapters.json", {}).get("chapters", []) if (self.pdir / "chapters.json").is_file() else []))
        plan_scenes = []
        for i, s in enumerate(scenes, 1):
            b = s["block"]
            action = " ".join(e["text"] for e in s["elements"] if e["type"] == "action")
            seconds = max(clip, float(b["seconds"]))
            plan_scenes.append({"id": f"S{i:03d}", "act": next((a["name"] for a in acts if a.get("n") == s.get("act")), str(s.get("act", 1))),
                                "title": s["heading"][:80], "summary": " ".join(action.split()[:60]) or s["heading"], "chapters": [min(n_ch, 1 + (i - 1) * n_ch // len(scenes))],
                                "anchor": "", "importance": 3.0, "keep": "full", "location": str(b.get("location", "")), "characters": [str(c) for c in b["characters"]],
                                "time_of_day": str(b.get("time_of_day", "")), "clips": max(1, round(seconds / clip)), "seconds": round(max(1, round(seconds / clip)) * clip)})
        runtime = max(adaptation.MIN_MINUTES, min(adaptation.MAX_MINUTES, self.settings["target_minutes"]))
        total = sum(float(a.get("share", 1)) for a in acts) or 1.0
        plan_acts = [{"name": a["name"], "purpose": a.get("purpose", ""), "share": round(float(a.get("share", 1)) / total, 4),
                      "seconds": round(float(a.get("share", 1)) / total * runtime * 60), "first_chapter": 1, "last_chapter": n_ch} for a in acts]
        aplan = {"version": 1, "logline": cov["logline"], "premise": treatment.split("\n\n")[0][:600], "ending": plan.get("ending", ""), "runtime_minutes": runtime,
                 "clip_seconds": clip, "n_chapters": n_ch, "acts": plan_acts, "scenes": plan_scenes, "cut": [{"scene": c["event"], "reason": c["reason"]} for c in plan.get("cut", [])],
                 "stale": False, "pilot": {"kind": "none"}, "source": "read_it_in"}
        screenplay.discard(self.pdir)
        adaptation.save(self.pdir, aplan)
        for ps, s in zip(plan_scenes, scenes, strict=True):
            screenplay.save_scene(self.pdir, ps["id"], {"heading": s["heading"], "elements": s["elements"]}, edited=False)
        return aplan

    # ---- the whole job
    def run(self, force: bool = False) -> dict:
        self.say("ingest", "Your producer is gathering the sources")
        src = self.ingest()
        if force:
            self.state = {}
        if self.state.get("stamp") != self.stamp:
            self.state = {"stamp": self.stamp, "done": []}
        self.finish("ingest")
        if src["screenplay_only"]:
            return self.run_existing(src)
        cov = self.stage("coverage", lambda: self.coverage(src))
        grown = self.stage("development", lambda: self.development(src, cov) or {"skipped": True})
        story = self._story(src, cov, None if grown.get("skipped") else grown)
        plan = self.stage("plan", lambda: self.plan(story))
        beats = self.stage("beats", lambda: self.beats(story, plan))
        treat = self.stage("treatment", lambda: self.treatment(story, beats))
        (self.dir / "treatment.md").write_text(treat["treatment"].strip() + "\n", encoding="utf-8")
        acts = beats["acts"]
        for i, a in enumerate(acts, 1):
            a.setdefault("n", i)
        scenes = self.stage("screenplay", lambda: self.write_acts(acts, treat["treatment"], plan, cov))["scenes"]
        return self.finish_up(scenes, cov, acts, plan, treat["treatment"])

    def write_acts(self, acts: list[dict], treatment: str, plan: dict, cov: dict) -> dict:
        total = sum(float(a["share"]) for a in acts) or 1.0
        partial = read_json(self.dir / "screenplay.partial.json", {}) or {}
        scenes: list[dict] = partial.get("scenes", []) if partial.get("stamp") == self.stamp else []
        written = {s["act"] for s in scenes}
        for i, a in enumerate(acts, 1):
            if a["n"] in written:
                continue
            prev = next((s for s in reversed(scenes)), None)
            scenes += self.act_scenes(a, i, len(acts), treatment, plan, cov, prev, float(a["share"]) / total * self.settings["target_minutes"] * 60)
            write_json(self.dir / "screenplay.partial.json", {"stamp": self.stamp, "scenes": scenes})      # a stopped job carries on per act
        (self.dir / "screenplay.partial.json").unlink(missing_ok=True)
        return {"scenes": scenes}

    def finish_up(self, scenes: list[dict], cov: dict, acts: list[dict], plan: dict, treatment: str) -> dict:
        if self.done("critique"):
            data = read_json(self.dir / "screenplay.json", {})
            scenes, rounds = data["scenes"], read_json(self.dir / "critique.json", [])
        else:
            scenes, rounds = self.critique(scenes, acts, [])
            self.finish("critique")
        write_json(self.dir / "screenplay.json", {"title": cov.get("logline", ""), "scenes": scenes})
        aplan = self.result(scenes, cov, acts, plan, treatment)
        self.finish("result")
        last = rounds[-1] if rounds else {}
        summary = {"scenes": len(scenes), "minutes": round(sum(float(s["block"]["seconds"]) for s in scenes) / 60, 1), "rounds": len(rounds),
                   "scores": {"script_doctor": last.get("doctor", {}).get("score"), "director": last.get("director", {}).get("score")},
                   "plan_scenes": len(aplan["scenes"])}
        write_json(self.dir / "summary.json", summary)
        self._say(f"Done: {summary['scenes']} scenes, about {summary['minutes']} minutes, {summary['rounds']} critique round(s).")
        return summary

    def run_existing(self, src: dict) -> dict:
        """An existing screenplay: its scenes are used as they are (with blocks worked out), then only critiqued and polished."""
        scenes: list[dict] = []
        for s in src["scripts"]:
            for sc in sources.document(self.pdir, s["id"]).metadata.get("scenes", []):
                els = []
                for e in sc["elements"]:
                    if e["type"] == "dialogue":
                        els.append({"type": "dialogue", "character": e.get("character") or "VOICE", "text": e["text"]})
                    elif e["type"] == "parenthetical" and els:
                        continue
                    elif e["type"] in ("action", "transition"):
                        els.append({"type": e["type"], "text": e["text"]})
                if not els or not re.match(r"^(INT|EXT|I/E)", sc["heading"] or "", re.I):
                    continue
                who = sorted({e["character"] for e in els if e["type"] == "dialogue"})
                where = re.sub(r"^(?:INT|EXT|I/E)[\./\s]+", "", sc["heading"]).split(" - ")
                scenes.append({**screenplay.clean_scene({"heading": sc["heading"], "elements": els}), "act": 1,
                               "block": {"characters": who, "location": where[0].strip().lower(), "time_of_day": (where[1] if len(where) > 1 else "").strip().lower(),
                                         "props": [], "wardrobe": [], "emotional_beat": "", "seconds": max(8, round(words(" ".join(e["text"] for e in els)) / 2.5))}})
        if not scenes:
            raise ReadError("The screenplay has no scenes with INT. / EXT. headings.")
        cov = self.stage("coverage", lambda: self.coverage(src))
        acts = [{"n": 1, "name": "The screenplay", "purpose": "as written", "share": 1, "beats": []}]
        (self.dir / "treatment.md").write_text("(An existing screenplay was read in; no treatment was written.)\n", encoding="utf-8")
        return self.finish_up(scenes, cov, acts, {"kept": [], "ending": "as written"}, "")

    def stage(self, name: str, fn: Callable[[], dict]) -> dict:
        if self.done(name) and (self.dir / f"{name}.json").is_file():
            return read_json(self.dir / f"{name}.json", {})
        d = fn()
        write_json(self.dir / f"{name}.json", d)
        self.finish(name)
        return d


def script_text(scenes: list[dict]) -> str:
    out = []
    for i, s in enumerate(scenes, 1):
        out.append(f"{i}. {s['heading']}")
        for e in s["elements"]:
            if e["type"] == "dialogue":
                out.append(f"    {e['character']}" + (f" ({e['note']})" if e.get("note") else "") + f": {e['text']}")
            else:
                out.append(("    >> " if e["type"] == "transition" else "") + e["text"])
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------- engines
def llm_ask(pdir: Path, engine: str, model: str | None) -> Ask:
    import bookkit

    def ask(prompt: str, role: str, step: str, validate: Callable[[dict], None]) -> dict:
        return bookkit.llm_json(prompt, crew.system(role, pdir, step), model=model, engine=engine, validate=validate)
    return ask


def fake_ask(pdir: Path) -> Ask:
    """A made-up but well-formed reply for every step, from the source's own words (no AI). For demo runs and tests."""
    try:
        text = sources.merged_text(pdir) or "\n".join(p.read_text(encoding="utf-8") for p in sorted((pdir / "chapters").glob("chapter-*.txt")))
    except OSError:
        text = ""

    def sentences(n: int, prompt: str) -> list[str]:
        body = text or prompt.split("SOURCE", 1)[-1]
        found = [s.strip() for s in re.split(r"(?<=[.!?])\s+", re.sub(r"===.*?===", " ", body)) if 4 <= words(s) <= 40]
        return (found or ["Someone wants something and must risk everything to get it."]) * (n // max(1, len(found)) + 1)

    def ask(prompt: str, role: str, step: str, validate: Callable[[dict], None]) -> dict:
        s = sentences(12, prompt)
        if "chapter summary" in step:
            d: dict = {"summary": " ".join(s[:3]), "key_dialogue": [], "importance": 3}
        elif "coverage" in step:
            d = {"logline": s[0], "genre": "drama", "tone": "warm", "themes": ["hope"], "characters": [{"name": "MARA", "role": "protagonist", "description": "the hero"}],
                 "key_events": s[:3], "filmable": "all of it", "length": "right", "notes": ""}
        elif "development" in step:
            d = {"story": " ".join(s[:6]), "inciting_incident": s[1], "climax": s[2], "resolution": s[3], "invented": [],
                 "episodes": [{"n": 1, "title": "One", "summary": s[0]}]}
        elif "adaptation plan" in step:
            d = {"kept": [{"event": s[0], "reason": "the heart of the story"}], "merged": [], "cut": [], "ending": "a quiet ending with time to breathe"}
        elif "beat sheet" in step:
            names = list(EPISODE_BEATS if "hook" in prompt.split("It must name these beats:")[-1][:80] else FILM_BEATS)
            d = {"acts": [{"n": i + 1, "name": f"Act {i + 1}", "purpose": "move the story", "share": 1 / 3,
                           "beats": [{"n": j + 1, "name": names[(i * 2 + j) % len(names)].capitalize(), "description": s[j]} for j in range(2)]} for i in range(3)]}
        elif "treatment" in step:
            d = {"treatment": ("\n\n".join(" ".join(s[i:i + 4]) for i in range(0, 12, 4)) + " ") * 4}
        elif "revision" in step:                                 # the fake screenwriter keeps the scenes as they are
            given = json.loads(prompt.split("SCENES (numbered as in the whole script):\n", 1)[1])
            d = {"scenes": [{k: v for k, v in sc.items() if k in ("heading", "elements", "block")} for sc in given]}
        elif "screenplay act" in step:
            n = re.search(r"act (\d+)", step)
            k = int(n.group(1)) if n else 1
            d = {"scenes": [{"heading": f"{'INT' if k % 2 else 'EXT'}. PLACE {k} - DAY", "elements": [{"type": "action", "text": s[k % len(s)]},
                             {"type": "dialogue", "character": "MARA", "text": "We go now."}], "block": {"characters": ["MARA"], "location": f"place {k}",
                             "time_of_day": "day", "props": [], "wardrobe": [], "emotional_beat": "resolve", "seconds": 30}}]}
        elif "critique" in step:
            d = {"score": 8 if "round 2" in step or role == "director" else 7, "notes": [{"scene": 1, "note": "Make the opening more visual."}]}
        else:
            raise ReadError(f"the fake engine has no reply for {step!r}")
        validate(d)
        return d
    return ask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex", "hf", "local", "fake"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--force", action="store_true", help="start again from the coverage, even if nothing changed")
    a = ap.parse_args(argv)
    from layout import project_dir
    try:
        pdir = project_dir(a.project, "book")
    except ValueError as e:
        print(e, flush=True)
        return 1
    if not pdir.is_dir():
        print(f"no book called {a.project}", flush=True)
        return 1
    ask = fake_ask(pdir) if a.engine == "fake" else llm_ask(pdir, a.engine, a.model)
    try:
        ReadItIn(pdir, ask, lambda t: print(t, flush=True)).run(force=a.force)
    except (ReadError, sources.SourceError, adaptation.AdaptationError, screenplay.ScreenplayError) as e:
        print(f"Read it in stopped: {e}", flush=True)
        return 1
    except RuntimeError as e:
        print(f"Read it in stopped: the AI could not answer ({e}). Press Read it in again to carry on where it stopped.", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
