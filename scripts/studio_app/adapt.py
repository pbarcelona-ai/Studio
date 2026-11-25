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
def _reference_options(
    series: str,
    name: str,
    *,
    project_dir: Path | None = None,
    known_names: list[str] | None = None,
    overrides: dict[str, str] | None = None,
) -> list[str]:
    import character_identity
    import character_tokens as ct

    out: list[str] = []
    seen: set[str] = set()
    if project_dir is not None:
        t_dir = project_dir / "assets" / "turnarounds"
        repo_root = project_dir.parent.parent.parent
        for p, _src in character_identity.find_canonical_character_refs(
            t_dir, name, known_names=known_names, overrides=overrides, limit=12,
        ):
            try:
                rel = p.relative_to(repo_root).as_posix()
            except ValueError:
                continue
            if rel not in seen:
                seen.add(rel)
                out.append(rel)
    try:
        for item in ct.reference_pictures(series, name):
            if item.get("exists") and item.get("path") and item["path"] not in seen:
                seen.add(item["path"])
                out.append(item["path"])
    except (OSError, ValueError, KeyError):
        pass
    return out


def cast_lock_data(slug) -> dict:
    """Per scene of the plan: the characters (with the description now used for them, the locked one if any, and the pictures to choose from) and the place."""
    from bookkit import character_token, continuity_file
    import character_identity
    from .config import get_character_series
    d = _book(slug)
    plan = ad.load(d)
    if not plan:
        raise PlanError("this book has no film plan yet")
    lock = cast_lock.load(d)
    cont = read_json(continuity_file(d), {}) or {}
    chars = {c["name"].lower(): c for c in cont.get("characters", []) if isinstance(c, dict) and c.get("name")}
    series = get_character_series(slug)
    repo_root = d.parent.parent.parent
    overrides = character_identity.load_identity_overrides(d)
    known_names = [c["name"] for c in chars.values()]

    place_pics: list[str] = []
    seen_place: set[str] = set()
    for pdir_cand in (d / "assets" / "sets", d / "location_refs"):
        if pdir_cand.is_dir():
            for p in sorted(pdir_cand.iterdir()):
                if p.is_file() and p.suffix.lower() in cast_lock.PICTURE:
                    rel = p.relative_to(repo_root).as_posix()
                    if rel not in seen_place:
                        seen_place.add(rel)
                        place_pics.append(rel)

    scenes = []
    for s in ad.active_scenes(plan):
        sl = lock.get(s["id"], {})
        locked_chars = sl.get("characters") or {}
        people = []
        seen_names: set[str] = set()
        raw_scene_names = [str(nm or "").strip() for nm in s.get("characters", [])] + [str(lnm or "").strip() for lnm in locked_chars]
        for raw_nm in raw_scene_names:
            if not raw_nm:
                continue
            c = chars.get(raw_nm.lower())
            cname = c["name"] if c else raw_nm
            key = cname.lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            locked: dict = locked_chars.get(cname) or next(
                (v for k, v in locked_chars.items() if str(k).lower() == key),
                {},
            )
            cur_tok = character_token(c, min(s["chapters"])) if (c and s.get("chapters")) else str((c or {}).get("token") or "")
            people.append({
                "name": cname,
                "current": locked.get("token") or cur_tok,
                "locked": locked,
                "references": _reference_options(series, cname, project_dir=d, known_names=known_names, overrides=overrides),
            })

        scenes.append({"id": s["id"], "title": s["title"], "location": s.get("location", ""), "characters": people,
                       "place": {"locked": sl.get("location") or {}, "references": place_pics}})
    return {
        "scenes": scenes,
        "summary": cast_lock.summary(lock, plan),
        "series": series,
        "all_characters": [
            {
                "name": c["name"],
                "token": str(c.get("token") or ""),
                "references": _reference_options(series, c["name"], project_dir=d, known_names=known_names, overrides=overrides),
            }
            for c in chars.values()
        ],
    }


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
