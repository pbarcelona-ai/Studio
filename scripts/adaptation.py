"""The adaptation plan of a book: logline, acts and a scene list sized to a target runtime (see adr/0005-adaptation-stage.md).

Pure logic, no AI calls: book_adapt.py asks the model for the creative parts and uses this module to check, fit and store them.

  projects/books/<book>/adaptation/adaptation.json     the plan
  projects/books/<book>/adaptation/summaries/          one summary per chapter (cache)
  projects/books/<book>/adaptation/treatment.md        the plan as prose (made from the json, never edited)

A scene is {id, act, title, summary, chapters[], anchor, importance 1-5, keep full|condensed|montage, location, characters[], time_of_day,
clips, seconds}. Time is always whole clips (clips * clip_seconds).
"""
import json
import os
import re
from pathlib import Path

from bookkit import read_json

KEEP = ("full", "condensed", "montage")
MAX_MINUTES = 180
MIN_MINUTES = 0.5


class AdaptationError(ValueError):
    """A readable reason a plan or an edit is not acceptable."""


def adapt_dir(pdir: Path) -> Path:
    return Path(pdir) / "adaptation"


def adapt_file(pdir: Path) -> Path:
    return adapt_dir(pdir) / "adaptation.json"


def load(pdir: Path) -> dict | None:
    d = read_json(adapt_file(pdir))
    return d if isinstance(d, dict) and isinstance(d.get("scenes"), list) else None


def save(pdir: Path, data: dict) -> None:
    f = adapt_file(pdir)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    os.replace(tmp, f)
    (adapt_dir(pdir) / "treatment.md").write_text(treatment_md(data))


def summary_file(pdir: Path, n: int) -> Path:
    return adapt_dir(pdir) / "summaries" / f"chapter-{n:03d}.json"


# ------------------------------------------------------------------------------------------ checking what the model returned
def _num(x, name):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError(f"{name} must be a number")
    return float(x)


def check_summary(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("summary"), str) or len(d["summary"].split()) < 5:
        raise ValueError("'summary' must be a sentence or more")
    if not isinstance(d.get("characters", []), list) or not isinstance(d.get("beats", []), list):
        raise ValueError("'characters' and 'beats' must be lists")
    imp = _num(d.get("importance", 3), "importance")
    if not 1 <= imp <= 5:
        raise ValueError("'importance' must be 1 to 5")


def check_shape(d, n_chapters: int) -> None:
    """The logline/premise/ending/acts reply. Each act has name, purpose, share (of the runtime) and a chapter range first..last."""
    for key in ("logline", "premise", "ending"):
        if not isinstance(d.get(key), str) or not d[key].strip():
            raise ValueError(f"missing text field {key!r}")
    acts = d.get("acts")
    if not isinstance(acts, list) or not acts:
        raise ValueError("'acts' must be a list with at least one act")
    for a in acts:
        if not isinstance(a, dict) or not str(a.get("name", "")).strip() or not str(a.get("purpose", "")).strip():
            raise ValueError("every act needs a name and a purpose")
        if _num(a.get("share"), "share") <= 0:
            raise ValueError("every act needs a share above 0")
        first, last = a.get("first_chapter"), a.get("last_chapter")
        if not (isinstance(first, int) and isinstance(last, int) and 1 <= first <= last <= n_chapters):
            raise ValueError(f"every act needs whole-number first_chapter <= last_chapter within 1-{n_chapters}")


def normalise_acts(acts: list[dict], n_chapters: int, target_seconds: float) -> list[dict]:
    """Make the acts cover chapters 1..N once each, in order (the model's ranges may overlap or leave gaps), and turn shares into seconds."""
    acts = sorted((dict(a) for a in acts), key=lambda a: (a["first_chapter"], a["last_chapter"]))[:max(n_chapters, 1)]    # never more acts than chapters
    pos = 1
    for i, a in enumerate(acts):
        a["first_chapter"] = pos
        a["last_chapter"] = n_chapters if i == len(acts) - 1 else max(pos, min(int(a["last_chapter"]), n_chapters - (len(acts) - 1 - i)))
        pos = a["last_chapter"] + 1
    total = sum(float(a["share"]) for a in acts)
    for a in acts:
        a["share"] = round(float(a["share"]) / total, 4)
        a["seconds"] = round(a["share"] * target_seconds)
    return acts


def check_scenes(d, first: int, last: int) -> None:
    scenes = d.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("'scenes' must be a list with at least one scene")
    for s in scenes:
        if not isinstance(s, dict) or not str(s.get("title", "")).strip() or len(str(s.get("summary", "")).split()) < 4:
            raise ValueError("every scene needs a title and a summary of a sentence or more")
        ch = s.get("chapters")
        if not isinstance(ch, list) or not ch or not all(isinstance(c, int) and not isinstance(c, bool) and first <= c <= last for c in ch):
            raise ValueError(f"every scene needs 'chapters': a list of chapter numbers from {first} to {last} that it is taken from")
        if not str(s.get("anchor", "")).strip():
            raise ValueError("every scene needs an 'anchor': 3-12 words copied exactly from the book where the scene starts")
        if _num(s.get("seconds"), "seconds") <= 0:
            raise ValueError("every scene needs 'seconds' above 0")
        if s.get("keep", "condensed") not in KEEP:
            raise ValueError(f"'keep' must be one of {', '.join(KEEP)}")
        imp = _num(s.get("importance", 3), "importance")
        if not 1 <= imp <= 5:
            raise ValueError("'importance' must be 1 to 5")


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def anchor_found(anchor: str, chapter_texts: list[str]) -> bool:
    a = _norm(anchor)
    return bool(a) and any(a in _norm(t) for t in chapter_texts)


# ------------------------------------------------------------------------------------------ fitting to the runtime
def fit_clips(scenes: list[dict], goal_clips: int, clip_seconds: float) -> tuple[list[dict], list[dict]]:
    """Give each scene a whole number of clips so the total is exactly goal_clips (or the number of scenes if the goal is smaller than that and
    there is nothing left to drop). Starts from the model's proposed seconds, scaled in proportion; the leftovers are added to or taken from
    scenes by importance. Returns (kept scenes in the same order, dropped scenes). Scenes are changed in place only by the keys clips/seconds."""
    if goal_clips < 1:
        raise AdaptationError("the runtime is shorter than one clip")
    scenes = [dict(s) for s in scenes]
    dropped: list[dict] = []
    while len(scenes) > goal_clips:                                  # the goal is smaller than one clip per scene: drop the least important
        i = min(range(len(scenes)), key=lambda k: (float(scenes[k].get("importance", 3)), -k))
        dropped.append(scenes.pop(i))
    want = [max(float(s["seconds"]), clip_seconds) for s in scenes]
    scale = goal_clips * clip_seconds / sum(want)
    counts = [max(1, round(w * scale / clip_seconds)) for w in want]
    guard = 0
    while sum(counts) != goal_clips and guard < 100000:
        guard += 1
        if sum(counts) > goal_clips:                                  # take a clip from the least important scene that has more than one
            cands = [k for k in range(len(scenes)) if counts[k] > 1]
            if not cands:
                break
            k = min(cands, key=lambda k: (float(scenes[k].get("importance", 3)), -counts[k], -k))
            counts[k] -= 1
        else:                                                         # give a clip to the most important scene, the shortest first
            k = max(range(len(scenes)), key=lambda k: (float(scenes[k].get("importance", 3)), -counts[k], -k))
            counts[k] += 1
    for s, c in zip(scenes, counts, strict=True):
        s["clips"], s["seconds"] = c, round(c * clip_seconds, 2)
    return scenes, dropped


def build_plan(shape: dict, scene_lists: list[list[dict]], minutes: float, clip_seconds: float, n_chapters: int,
               meta: dict | None = None) -> dict:
    """Assemble adaptation.json from the shape reply and the scene lists (one per act, in act order). Fits the total to `minutes`."""
    if not MIN_MINUTES <= minutes <= MAX_MINUTES:
        raise AdaptationError(f"the runtime must be {MIN_MINUTES:g} to {MAX_MINUTES} minutes")
    target = minutes * 60
    acts = normalise_acts(shape["acts"], n_chapters, target)
    flat = []
    for ai, scs in enumerate(scene_lists):
        for s in scs:
            flat.append({**s, "act": acts[ai]["name"], "keep": s.get("keep", "condensed"), "importance": float(s.get("importance", 3))})
    if not flat:
        raise AdaptationError("the model returned no scenes")
    goal = max(1, round(target / clip_seconds))
    kept, dropped = fit_clips(flat, goal, clip_seconds)
    for i, s in enumerate(kept, start=1):
        s["id"] = f"S{i:03d}"
    used = {c for s in kept for c in s["chapters"]}
    plan = {"version": 1, "logline": shape["logline"].strip(), "premise": shape["premise"].strip(), "ending": shape["ending"].strip(),
            "runtime_minutes": minutes, "clip_seconds": clip_seconds, "n_chapters": n_chapters, "acts": acts, "scenes": kept,
            "cut": [{"chapter": n, "reason": "not used by any scene"} for n in range(1, n_chapters + 1) if n not in used]
                   + [{"scene": d["title"], "reason": "dropped to fit the runtime"} for d in dropped],
            "stale": False, "pilot": {"kind": "none"}}
    plan.update(meta or {})
    return plan


# ------------------------------------------------------------------------------------------ using the plan
def total_clips(plan: dict, active_only: bool = True) -> int:
    return sum(int(s.get("clips", 0)) for s in (active_scenes(plan) if active_only else plan["scenes"]))


def active_scenes(plan: dict) -> list[dict]:
    """The scenes the film is made from now: all of them, or only the pilot's."""
    pilot = plan.get("pilot") or {}
    ids = pilot.get("scene_ids")
    if pilot.get("kind", "none") != "none" and isinstance(ids, list):
        return [s for s in plan["scenes"] if s["id"] in set(ids)]
    return list(plan["scenes"])


def chapter_clips(plan: dict) -> dict[int, int]:
    """Clips per chapter from the active scenes: a scene's clips are shared evenly between the chapters it is taken from (the first ones get the rest)."""
    out: dict[int, int] = {}
    for s in active_scenes(plan):
        chs = sorted(set(s["chapters"]))
        base, extra = divmod(int(s["clips"]), len(chs))
        for i, c in enumerate(chs):
            out[c] = out.get(c, 0) + base + (1 if i < extra else 0)
    return {c: n for c, n in out.items() if n > 0}


def scenes_of_chapter(plan: dict, n: int) -> list[dict]:
    return [s for s in active_scenes(plan) if n in s["chapters"]]


def pilot_choice(plan: dict, kind: str, seconds: float = 90.0, first: int = 1, last: int | None = None) -> dict:
    """A smaller film to try first. kind: "none"; "trailer" (the most important scenes in story order up to `seconds`, always including the first and last
    scene of the first act); "chapters" (every scene taken only from chapters first..last)."""
    if kind == "none":
        return {"kind": "none"}
    scenes = plan["scenes"]
    cs = float(plan.get("clip_seconds", 4))
    if kind == "trailer":
        if seconds < cs:
            raise AdaptationError("a trailer must be at least one clip long")
        order = sorted(range(len(scenes)), key=lambda i: (-float(scenes[i].get("importance", 3)), i))
        picked: set[int] = set()
        budget = seconds
        first_act = next((s["act"] for s in scenes), None)
        must = [i for i, s in enumerate(scenes) if s["act"] == first_act][:1]
        for i in must + order:
            if i not in picked and scenes[i]["seconds"] <= budget:
                picked.add(i)
                budget -= scenes[i]["seconds"]
        if not picked:                                               # every scene is longer than the trailer: take the shortest
            picked.add(min(range(len(scenes)), key=lambda i: scenes[i]["seconds"]))
        return {"kind": "trailer", "seconds": seconds, "scene_ids": [scenes[i]["id"] for i in sorted(picked)]}
    if kind == "chapters":
        last = last if last is not None else first
        if not (isinstance(first, int) and isinstance(last, int) and 1 <= first <= last <= plan.get("n_chapters", last)):
            raise AdaptationError("pick a chapter range inside the book")
        ids = [s["id"] for s in scenes if all(first <= c <= last for c in s["chapters"])]
        if not ids:
            raise AdaptationError(f"no scene is taken only from chapters {first}-{last}")
        return {"kind": "chapters", "first": first, "last": last, "scene_ids": ids}
    raise AdaptationError("pilot must be none, trailer or chapters")


# ------------------------------------------------------------------------------------------ editing the plan
def _check_id(plan: dict, sid: str) -> int:
    for i, s in enumerate(plan["scenes"]):
        if s["id"] == sid:
            return i
    raise AdaptationError(f"there is no scene {sid}")


def _renumber(plan: dict) -> None:
    """Keep ids stable for scenes that stay: only new scenes (without an id) get one."""
    taken = {s["id"] for s in plan["scenes"] if s.get("id")}
    n = 0
    for s in plan["scenes"]:
        if not s.get("id"):
            while f"S{n + 1:03d}" in taken:
                n += 1
            n += 1
            s["id"] = f"S{n:03d}"
            taken.add(s["id"])
    for s in plan["scenes"]:
        s["seconds"] = round(int(s["clips"]) * float(plan["clip_seconds"]), 2)


def edit(plan: dict, action: str, body: dict) -> dict:
    """Apply one table edit to the plan (changes and returns it). Actions: set_clips {id, clips}, drop {id}, merge {id} (with the next scene),
    move {id, direction -1|1}, rename {id, title, summary?}, set_pilot {kind, seconds?, first?, last?}. A plan that changed is no longer
    fitted to the runtime exactly; plan_runtime() reports the difference."""
    if action == "set_pilot":
        plan["pilot"] = pilot_choice(plan, body.get("kind", "none"), float(body.get("seconds") or 90), int(body.get("first") or 1),
                                     int(body["last"]) if body.get("last") else None)
        return plan
    i = _check_id(plan, str(body.get("id", "")))
    scenes = plan["scenes"]
    if action == "set_clips":
        c = body.get("clips")
        if not isinstance(c, int) or isinstance(c, bool) or not 1 <= c <= 10000:
            raise AdaptationError("clips must be a whole number from 1 up")
        scenes[i]["clips"] = c
    elif action == "drop":
        if len(scenes) == 1:
            raise AdaptationError("a film needs at least one scene")
        gone = scenes.pop(i)
        plan.setdefault("cut", []).append({"scene": gone["title"], "reason": "dropped by you"})
    elif action == "merge":
        if i + 1 >= len(scenes):
            raise AdaptationError("the last scene has no next scene to join")
        a, b = scenes[i], scenes.pop(i + 1)
        a["title"] = f"{a['title']} / {b['title']}"[:100]
        a["summary"] = f"{a['summary']} {b['summary']}".strip()
        a["chapters"] = sorted(set(a["chapters"]) | set(b["chapters"]))
        a["clips"] = int(a["clips"]) + int(b["clips"])
        a["importance"] = max(float(a.get("importance", 3)), float(b.get("importance", 3)))
        a["characters"] = sorted(set(a.get("characters", [])) | set(b.get("characters", [])))
        a["keep"] = "full" if "full" in (a.get("keep"), b.get("keep")) else a.get("keep", "condensed")
    elif action == "move":
        d = body.get("direction")
        if d not in (-1, 1) or not 0 <= i + d < len(scenes):
            raise AdaptationError("that scene cannot move that way")
        scenes[i], scenes[i + d] = scenes[i + d], scenes[i]
    elif action == "rename":
        title = " ".join(str(body.get("title", "")).split())[:100]
        if not title:
            raise AdaptationError("a scene needs a title")
        scenes[i]["title"] = title
        if body.get("summary"):
            scenes[i]["summary"] = " ".join(str(body["summary"]).split())[:1500]
    else:
        raise AdaptationError(f"unknown action {action!r}")
    _renumber(plan)
    pilot = plan.get("pilot") or {}
    if pilot.get("scene_ids"):
        pilot["scene_ids"] = [x for x in pilot["scene_ids"] if any(s["id"] == x for s in scenes)]
    return plan


def plan_runtime(plan: dict) -> dict:
    """{seconds, target_seconds, minutes, difference_seconds} of the whole plan (not only the pilot)."""
    secs = sum(float(s["seconds"]) for s in plan["scenes"])
    target = float(plan["runtime_minutes"]) * 60
    return {"seconds": secs, "target_seconds": target, "minutes": round(secs / 60, 2), "difference_seconds": round(secs - target, 1)}


def scene_music_prompt(scene: dict, theme: str, shot_music: list[str], limit: int = 330) -> str:
    """The MusicGen prompt for one scene's cue: the book's theme, the time of day and treatment, the scene's own words, then what its shots asked for."""
    mood = {"full": "played out, building", "condensed": "steady", "montage": "flowing, passing time"}.get(scene.get("keep", "condensed"), "steady")
    parts = [f"cinematic score, {theme.strip().rstrip('.')}" if theme else "cinematic score"]
    tod = str(scene.get("time_of_day") or "").strip()
    if tod and tod != "unknown":
        parts.append(f"{tod} scene")
    parts.append(mood)
    parts.append(" ".join(str(scene.get("summary", "")).split()[:14]))
    seen: list[str] = []
    for m in shot_music:
        m = " ".join(str(m).split()).rstrip(".")
        if m and m.lower() not in [x.lower() for x in seen]:
            seen.append(m)
        if len(seen) == 2:
            break
    parts += seen
    text = "; ".join(p for p in parts if p)
    return text[:limit].rsplit(" ", 1)[0] if len(text) > limit else text


# ------------------------------------------------------------------------------------------ the treatment as prose
def treatment_md(plan: dict) -> str:
    rt = plan_runtime(plan)
    out = ["# Treatment\n", f"**Logline.** {plan['logline']}\n", f"**Premise.** {plan['premise']}\n", f"**Ending.** {plan['ending']}\n",
           f"Runtime: about {rt['minutes']:g} minutes ({sum(int(s['clips']) for s in plan['scenes'])} clips of {plan['clip_seconds']:g} s).\n"]
    for a in plan["acts"]:
        out.append(f"## {a['name']}\n\n{a['purpose']}\n")
        for s in (s for s in plan["scenes"] if s.get("act") == a["name"]):
            ch = ", ".join(str(c) for c in s["chapters"])
            out.append(f"- **{s['id']} {s['title']}** ({s['seconds']:g} s, chapter {ch}, {s.get('keep', 'condensed')}): {s['summary']}")
        out.append("")
    if plan.get("cut"):
        out.append("## Left out\n")
        for c in plan["cut"]:
            out.append(f"- {'Chapter ' + str(c['chapter']) if 'chapter' in c else 'Scene ' + c['scene']}: {c['reason']}")
        out.append("")
    return "\n".join(out)


def shot_scene(plan: dict, chapter: int, shot: int, n_shots: int) -> str | None:
    """The id of the scene a shot belongs to. A chapter's shots are shared out between the scenes taken from it, in plan order, in proportion to the
    clips each scene gives that chapter. None if no active scene uses the chapter."""
    scenes = scenes_of_chapter(plan, chapter)
    if not scenes or n_shots < 1:
        return None
    weights = []
    for s in scenes:
        chs = sorted(set(s["chapters"]))
        base, extra = divmod(int(s["clips"]), len(chs))
        weights.append(max(1, base + (1 if chs.index(chapter) < extra else 0)))
    total, acc = sum(weights), 0.0
    for s, w in zip(scenes, weights, strict=True):
        acc += w
        if shot <= acc * n_shots / total + 1e-9:
            return s["id"]
    return scenes[-1]["id"]


def _parse_heading_meta(heading: str) -> tuple[str, str, str]:
    """Extract (title, location, time_of_day) from a screenplay slugline like 'INT. LIVING ROOM - AFTERNOON'."""
    h = " ".join(str(heading or "").split()).strip()
    if not h:
        return "Untitled Scene", "", "day"
    stripped = re.sub(r"^(?:INT\.?/EXT\.?|EXT\.?/INT\.?|INT\.?|EXT\.?|I/E\.?)\s+", "", h, flags=re.I).strip()
    parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", stripped) if p.strip()]
    location = parts[0] if parts else stripped
    tod = parts[-1].lower() if len(parts) >= 2 else "day"
    title = location.title()[:80] if location else h[:80]
    return title, location.lower(), tod


def _scene_summary_from_elements(elements: list[dict]) -> tuple[str, list[str], int]:
    """Derive a concise beat summary, speaking character list, and estimated seconds from screenplay elements."""
    actions: list[str] = []
    chars: list[str] = []
    seen_chars: set[str] = set()
    words = 0
    for el in elements or []:
        if not isinstance(el, dict):
            continue
        txt = " ".join(str(el.get("text") or "").split()).strip()
        words += len(txt.split())
        etype = str(el.get("type") or "").lower()
        if etype == "dialogue":
            ch = str(el.get("character") or "").strip().upper()
            if ch and ch not in seen_chars:
                seen_chars.add(ch)
                chars.append(ch)
        elif etype == "action" and txt:
            actions.append(txt)
    if actions:
        summary = " ".join(actions)[:260].strip()
    else:
        first_dlg = next(
            (
                f"{str(e.get('character') or '').upper()}: {str(e.get('text') or '').strip()}"
                for e in (elements or [])
                if isinstance(e, dict) and e.get("type") == "dialogue" and e.get("text")
            ),
            "",
        )
        summary = first_dlg[:260].strip()
    est_sec = max(4, min(180, int(round(max(words / 2.6, 4.0)))))
    return summary, chars, est_sec


def sync_beats_from_screenplay(pdir: Path) -> dict:
    """Reverse-sync Step 06 screenplay scenes into Step 05 Story Outline & Beat Sheet (`adaptation.json` & `readin/beats.json`)."""
    import screenplay as sp

    sp_dir = pdir / "screenplay"
    plan = load(pdir) or {}
    existing_scenes: list[dict] = [
        dict(s) for s in (plan.get("scenes") or []) if isinstance(s, dict) and s.get("id")
    ]
    existing_by_id: dict[str, dict] = {str(s["id"]).strip(): s for s in existing_scenes}

    written_by_id: dict[str, dict] = {}
    extra_written_ids: list[str] = []
    for s in existing_scenes:
        sid = str(s["id"]).strip()
        sc = sp.load_scene(pdir, sid)
        if sc:
            written_by_id[sid] = sc
    if sp_dir.is_dir():
        for sf in sorted(sp_dir.glob("scene-*.json")):
            sid = sf.stem[len("scene-"):]
            if sid and sid not in written_by_id:
                sc = sp.load_scene(pdir, sid)
                if sc:
                    written_by_id[sid] = sc
                    if sid not in existing_by_id:
                        extra_written_ids.append(sid)

    if not written_by_id:
        rd_sp = read_json(pdir / "readin" / "screenplay.json")
        if isinstance(rd_sp, dict) and isinstance(rd_sp.get("scenes"), list):
            for idx, sc in enumerate(rd_sp["scenes"], start=1):
                if isinstance(sc, dict):
                    sid = f"S{idx:03d}"
                    written_by_id[sid] = sc
                    if sid not in existing_by_id:
                        extra_written_ids.append(sid)

    if not written_by_id:
        return {"synced": False, "scenes_synced": 0, "beats_synced": 0}

    clip_sec = float(plan.get("clip_seconds") or 4.0)
    if clip_sec <= 0:
        clip_sec = 4.0
    ordered_ids: list[str] = [str(s["id"]).strip() for s in existing_scenes] + extra_written_ids
    total = len(ordered_ids)

    def _act_for_idx(i0: int) -> str:
        if total <= 2:
            return "Act I"
        frac = i0 / float(total)
        if frac < 0.25:
            return "Act I"
        if frac < 0.75:
            return "Act II"
        return "Act III"

    updated_scenes: list[dict] = []
    for idx0, sid in enumerate(ordered_ids):
        prev = existing_by_id.get(sid, {})
        sc = written_by_id.get(sid)
        if sc is None:
            # Preserve unwritten planned scenes intact so partial Step 06 edits never drop remaining outline scenes.
            updated_scenes.append(prev)
            continue

        heading = str(sc.get("heading") or "")
        raw_elements = sc.get("elements")
        elements: list[dict] = (
            [e for e in raw_elements if isinstance(e, dict)]
            if isinstance(raw_elements, list)
            else []
        )
        h_title, h_loc, h_tod = _parse_heading_meta(heading)
        summary, chars, est_sec = _scene_summary_from_elements(elements)

        clips = int(prev.get("clips") or max(1, int(round(est_sec / clip_sec))))
        secs = round(clips * clip_sec, 1)
        merged = dict(prev)
        merged.update(
            {
                "id": sid,
                "act": str(prev.get("act") or _act_for_idx(idx0)),
                "title": str(prev.get("title") or h_title),
                "summary": summary or str(prev.get("summary") or h_title),
                "chapters": prev.get("chapters") if isinstance(prev.get("chapters"), list) and prev.get("chapters") else [1],
                "anchor": str(prev.get("anchor") or ""),
                "importance": float(prev.get("importance") or 3.0),
                "keep": str(prev.get("keep") or "full"),
                "location": h_loc or str(prev.get("location") or ""),
                "characters": chars or (prev.get("characters") if isinstance(prev.get("characters"), list) else []),
                "time_of_day": h_tod or str(prev.get("time_of_day") or "day"),
                "clips": clips,
                "seconds": secs,
            }
        )
        updated_scenes.append(merged)

    total_sec = sum(float(s.get("seconds") or 0.0) for s in updated_scenes)
    acts = plan.get("acts") if isinstance(plan.get("acts"), list) and plan.get("acts") else [
        {"name": "Act I", "purpose": "Setup", "share": 0.25, "seconds": round(total_sec * 0.25, 1), "first_chapter": 1, "last_chapter": 1},
        {"name": "Act II", "purpose": "Confrontation", "share": 0.50, "seconds": round(total_sec * 0.50, 1), "first_chapter": 1, "last_chapter": 1},
        {"name": "Act III", "purpose": "Climax & Resolution", "share": 0.25, "seconds": round(total_sec * 0.25, 1), "first_chapter": 1, "last_chapter": 1},
    ]

    new_plan = dict(plan)
    new_plan.update(
        {
            "version": int(plan.get("version") or 1),
            "logline": str(plan.get("logline") or f"Synced from screenplay ({total} scene(s))"),
            "premise": str(plan.get("premise") or ""),
            "ending": str(plan.get("ending") or ""),
            "runtime_minutes": float(plan["runtime_minutes"]) if plan.get("runtime_minutes") else round(max(0.5, total_sec / 60.0), 2),
            "clip_seconds": clip_sec,
            "n_chapters": int(plan.get("n_chapters") or 1),
            "acts": acts,
            "scenes": updated_scenes,
            "cut": plan.get("cut") if isinstance(plan.get("cut"), list) else [],
            "stale": bool(plan.get("stale", False)),
            "synced_from_screenplay": True,
        }
    )
    save(pdir, new_plan)

    act_groups: dict[str, list[dict]] = {}
    for s in updated_scenes:
        act_name = str(s.get("act") or "Act I")
        act_groups.setdefault(act_name, []).append(
            {
                "scene_id": s["id"],
                "beat": f"{s['id']} — {s.get('title') or s['id']}",
                "summary": s.get("summary") or "",
            }
        )
    beats_doc = {
        "synced_from_screenplay": True,
        "acts": [{"name": k, "beats": v} for k, v in act_groups.items()],
    }
    rd_dir = pdir / "readin"
    rd_dir.mkdir(parents=True, exist_ok=True)
    beats_path = rd_dir / "beats.json"
    tmp_b = beats_path.with_suffix(".json.tmp")
    tmp_b.write_text(json.dumps(beats_doc, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_b, beats_path)

    return {
        "synced": True,
        "scenes_synced": len(written_by_id),
        "beats_synced": sum(len(v) for v in act_groups.values()),
    }
