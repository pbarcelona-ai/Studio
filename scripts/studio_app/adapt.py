"""The Adapt card: the film plan (logline, acts, scenes), the screenplay with its approval, and the budget preview."""
import shutil
from pathlib import Path

import adaptation as ad
import budget
import cast_lock
import feedback
import grade
import screenplay as sp
from bookkit import SLUG_RE, read_json
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .common import PlanError
from .config import LEGACY


def _book(slug) -> Path:
    slug = str(slug or "")
    if not SLUG_RE.match(slug) or slug in LEGACY or not pdir(slug).is_dir():
        raise PlanError("pick a book that has been started")
    return pdir(slug)


def summary(d: Path) -> dict:
    """A few facts for the project list and the step defaults: {exists, scenes, clips, minutes, stale, approved}."""
    plan = ad.load(d)
    if not plan:
        return {"exists": False}
    st = sp.status(d, plan)
    return {"exists": True, "chapters": len(ad.chapter_clips(plan)), "scenes": len(plan["scenes"]), "clips": ad.total_clips(plan), "minutes": ad.plan_runtime(plan)["minutes"],
            "stale": bool(plan.get("stale")), "approved": st["approved"], "written": st["written"], "total": st["total"],
            "pilot": (plan.get("pilot") or {}).get("kind", "none")}


def adaptation_data(slug) -> dict:
    d = _book(slug)
    plan = ad.load(d)
    if not plan:
        return {"exists": False, "chapters": len((read_json(d / "chapters.json", {}) or {}).get("chapters", []))}
    return {"exists": True, "plan": plan, "runtime": ad.plan_runtime(plan), "active_clips": ad.total_clips(plan),
            "screenplay": sp.status(d, plan), "chapter_clips": {str(k): v for k, v in ad.chapter_clips(plan).items()}}


def _remove_scene_files(d: Path, ids) -> None:
    for sid in ids:
        sp.scene_file(d, sid).unlink(missing_ok=True)


def adaptation_edit(b: dict) -> dict:
    """POST body: {project, action: set_clips|drop|merge|move|rename|set_pilot|discard, ...} (see adaptation.edit)."""
    d = _book(b.get("project"))
    if b.get("action") == "discard":
        shutil.rmtree(ad.adapt_dir(d), ignore_errors=True)
        sp.discard(d)
        return {"exists": False}
    plan = ad.load(d)
    if not plan:
        raise PlanError("this book has no film plan yet: run Adapt first")
    before = [s["id"] for s in plan["scenes"]]
    action = b.get("action")
    merged = None
    if action == "merge":
        merged = str(b.get("id", ""))
    try:
        ad.edit(plan, str(action), b)
    except (ad.AdaptationError, ValueError, TypeError) as e:
        raise PlanError(str(e)) from e
    ad.save(d, plan)
    _remove_scene_files(d, set(before) - {s["id"] for s in plan["scenes"]})      # scenes that are gone
    if merged:
        _remove_scene_files(d, [merged])                                         # the joined scene is a new scene: its screenplay is written again
    return adaptation_data(b.get("project"))


def screenplay_data(slug, sid: str = "") -> dict:
    d = _book(slug)
    plan = ad.load(d)
    if not plan:
        raise PlanError("this book has no film plan yet")
    scenes = []
    for s in ad.active_scenes(plan):
        if sid and s["id"] != sid:
            continue
        sc = sp.load_scene(d, s["id"])
        scenes.append({"id": s["id"], "title": s["title"], "seconds": s["seconds"], "summary": s["summary"], "act": s["act"], "screenplay": sc,
                       "dialogue_words": sp.dialogue_words(sc) if sc else 0})
    return {"scenes": scenes, "status": sp.status(d, plan), "text": sp.to_text(d, plan, [sid] if sid else None), "flags": feedback.open_flags(d)}


def screenplay_edit(b: dict) -> dict:
    """POST body: {project, action: save_scene {scene, heading, elements} | approve | unapprove | rewrite_scene {scene, instructions}}"""
    d = _book(b.get("project"))
    plan = ad.load(d)
    if not plan:
        raise PlanError("this book has no film plan yet")
    action = b.get("action")
    try:
        if action == "save_scene":
            sid = str(b.get("scene", ""))
            if sid not in {s["id"] for s in ad.active_scenes(plan)}:
                raise PlanError("that scene is not in the plan")
            sp.save_scene(d, sid, {"heading": b.get("heading"), "elements": b.get("elements")}, edited=True)
            feedback.resolve(d, sid)                         # the scene was updated after a storyboard change: its red outline goes
        elif action == "approve":
            flagged = feedback.open_flags(d)
            if flagged:
                raise PlanError(f"The storyboard changed {sum(len(v) for v in flagged.values())} shot(s) in scene(s) {', '.join(sorted(flagged))}: "
                                "update those scenes (red outline) or press Keep it, then approve.")
            sp.approve(d, plan)
        elif action == "unapprove":
            sp.clear_approval(d)
        elif action == "rewrite_scene":
            sid = str(b.get("scene", ""))
            instructions = str(b.get("instructions", "")).strip()
            if not sid or sid not in {s["id"] for s in ad.active_scenes(plan)}:
                raise PlanError("that scene is not in the plan")
            if not instructions:
                raise PlanError("instructions required for rewrite")
            # Rewrite the scene using AI with additional instructions
            _rewrite_scene_with_ai(d, plan, sid, instructions)
            feedback.resolve(d, sid)                         # the scene was updated: its red outline goes
        else:
            raise PlanError("unknown screenplay action")
    except sp.ScreenplayError as e:
        raise PlanError(str(e)) from e
    return screenplay_data(b.get("project"))


def _rewrite_scene_with_ai(pdir, plan, sid, instructions):
    """Rewrite a single scene using AI with additional instructions."""
    import crew
    from bookkit import continuity_file, llm_json, read_json
    import screenplay as sp
    import adaptation as ad

    # Get the scene from the plan
    scenes = ad.active_scenes(plan)
    s = next((sc for sc in scenes if sc["id"] == sid), None)
    if not s:
        raise PlanError("scene not found in plan")

    # Load existing screenplay
    existing = sp.load_scene(pdir, sid)
    current_text = ""
    if existing and existing.get("elements"):
        current_text = sp.to_text(pdir, plan, [sid])

    # Load continuity for character names
    continuity = read_json(continuity_file(pdir), {})
    names = [c["name"] for c in continuity.get("characters", [])]

    # Build the AI prompt
    LOGLINE = plan["logline"]
    SYSTEM = crew.system("screenwriter", pdir, "screenplay", "Adapt the book into a screenplay, one scene at a time.")

    prompt = f"""Film: {LOGLINE}
Act: {s['act']}. Scene {sid} "{s['title']}" (about {s['seconds']:g} seconds on screen).
What happens: {s['summary']}
Place: {s.get('location') or 'unknown'}. Time: {s.get('time_of_day') or 'unknown'}. People: {', '.join(s.get('characters', [])) or 'unknown'}.
{('Recurring characters: ' + ', '.join(names)) if names else ''}

CURRENT SCREENPLAY:
{current_text if current_text else "(no screenplay yet)"}

ADDITIONAL INSTRUCTIONS FROM USER:
{instructions}

Rewrite the scene as a screenplay incorporating the additional instructions. Return ONE JSON object: {{"heading": "INT. PLACE - TIME", "elements": [
 {{"type": "action", "text": "what we SEE and HEAR, present tense, concrete and filmable"}},
 {{"type": "dialogue", "character": "NAME", "note": "optional: how it is said", "text": "the spoken line"}},
 {{"type": "transition", "text": "CUT TO:"}} ]}}
Rules: show, do not tell (thoughts become behaviour); keep to the book's events and, where you can, its own words for dialogue; all dialogue together at most about {max(10, round(s['seconds'] * 2.5 * 0.8))} words so the scene fits {s['seconds']:g} seconds; 2 to 12 elements; nothing out of place for the book's era and world; no camera angles."""

    d = llm_json(prompt, SYSTEM, validate=sp.check_scene)
    sp.save_scene(pdir, sid, d, edited=True)


def budget_data(b: dict) -> dict:
    """POST body: {project, model, service, gpu, minutes?}"""
    d = _book(b.get("project"))
    try:
        est = budget.estimate(d, str(b.get("model") or "ltx_video_fast_i2v"), str(b.get("service") or "kaggle"), str(b.get("gpu") or "NvidiaTeslaT4"),
                              float(b["minutes"]) if b.get("minutes") else None)
    except (ad.AdaptationError, ValueError, TypeError) as e:
        raise PlanError(str(e)) from e
    return {**est, "text": budget.describe(est)}


# ------------------------------------------------------------------------------------------ locked cast, costume and location per scene
def _reference_options(series: str, name: str) -> list[str]:
    import character_tokens as ct
    try:
        return [p["path"] for p in ct.reference_pictures(series, name) if p.get("exists")]
    except (OSError, ValueError, KeyError):
        return []


def cast_lock_data(slug) -> dict:
    """Per scene of the plan: the characters (with the description now used for them, the locked one if any, and the pictures to choose from) and the place."""
    from bookkit import character_token, continuity_file
    from .config import get_character_series
    d = _book(slug)
    plan = ad.load(d)
    if not plan:
        raise PlanError("this book has no film plan yet")
    lock = cast_lock.load(d)
    cont = read_json(continuity_file(d), {}) or {}
    chars = {c["name"].lower(): c for c in cont.get("characters", []) if isinstance(c, dict) and c.get("name")}
    series = get_character_series(slug)
    place_pics = sorted(p.relative_to(d.parent.parent.parent).as_posix() for p in (d / "location_refs").iterdir()
                        if p.suffix.lower() in cast_lock.PICTURE) if (d / "location_refs").is_dir() else []
    scenes = []
    for s in ad.active_scenes(plan):
        sl = lock.get(s["id"], {})
        people = []
        for nm in s.get("characters", []):
            c = chars.get(str(nm).lower())
            if not c:
                continue
            locked = (sl.get("characters") or {}).get(c["name"]) or {}
            people.append({"name": c["name"], "current": locked.get("token") or character_token(c, min(s["chapters"])), "locked": locked,
                           "references": _reference_options(series, c["name"])})
        scenes.append({"id": s["id"], "title": s["title"], "location": s.get("location", ""), "characters": people,
                       "place": {"locked": sl.get("location") or {}, "references": place_pics}})
    return {"scenes": scenes, "summary": cast_lock.summary(lock, plan), "series": series}


def cast_lock_edit(b: dict) -> dict:
    """POST body: {project, scene, kind: character|location, name?, token?, reference?}: lock (or, with no token and reference, unlock)."""
    d = _book(b.get("project"))
    plan = ad.load(d)
    if not plan:
        raise PlanError("this book has no film plan yet")
    try:
        cast_lock.set_lock(d, plan, str(b.get("scene", "")), str(b.get("kind", "")), str(b.get("name", "")), str(b.get("token", "")), str(b.get("reference", "")))
    except cast_lock.LockError as e:
        raise PlanError(str(e)) from e
    return cast_lock_data(b.get("project"))


# ------------------------------------------------------------------------------------------ colour grade per scene
def grading_data(slug) -> dict:
    d = _book(slug)
    plan = ad.load(d)
    g = grade.load(d)
    return {"presets": list(grade.PRESETS), "limits": grade.LIMITS, "default": g["default"],
            "scenes": [{"id": s["id"], "title": s["title"], "grade": g["scenes"].get(s["id"], {})} for s in (ad.active_scenes(plan) if plan else [])],
            "orphans": sorted(set(g["scenes"]) - {s["id"] for s in (plan or {}).get("scenes", [])})}


def grading_edit(b: dict) -> dict:
    """POST body: {project, scene: "S003" | "default", grade: {preset, exposure, contrast, saturation, temperature, tint}} (an empty grade removes it)."""
    d = _book(b.get("project"))
    try:
        grade.set_grade(d, str(b.get("scene", "")), b.get("grade") or {})
    except grade.GradeError as e:
        raise PlanError(str(e)) from e
    return grading_data(b.get("project"))
