"""The film path: every step from book to finished film, in order, with whether it is done, whether the next step may start, and what to do now.

GET  /api/path?project=        -> {steps: [{id, title, done, ok, todo}], revisit: [...], alerts: [...], facts: {...}}
POST /api/path_confirm {project, step}      the step that is next in the walk back (after a storyboard change) was looked at: go on
POST /api/shot_move {project, n, direction} move a shot one place earlier (-1) or later (+1), also into the next or previous chapter
POST /api/feedback_keep {project, scene}    keep a flagged screenplay scene as it is
"""
import re

import adaptation as ad
import feedback
import review
import screenplay as sp
import shot_move
import shot_order
from bookkit import SLUG_RE, continuity_file, read_json
from layout import project_dir as pdir

from .common import PlanError
from .projects import read_csv_rows

# id, title (plain words: the page is meant to be easy enough for a child)
STEPS = [
    ("read", "Read the book"), ("chapters", "Check the chapters"), ("plan", "Plan the film"), ("screenplay", "Write and approve the screenplay"),
    ("continuity", "Make the story notes"), ("cast", "Pick the cast"), ("look", "Choose the look and voices"), ("write", "Write the shots"),
    ("build", "Get the shots ready"), ("where", "Choose the computer"), ("keyframes", "Make the pictures"), ("storyboard", "Check every picture"),
    ("video", "Make the video"), ("audio", "Make the sound"), ("cut", "Put the film together"), ("premiere", "Share your film"),
]
STEP_IDS = [s for s, _ in STEPS]


def _book(slug):
    d = pdir(slug)
    if not SLUG_RE.match(slug or "") or not d.is_dir():
        raise PlanError("pick a book first")
    return d


def _numbered(folder_glob, d, prefix, total):
    """Which shot rows (1..total) have a file <prefix>-NNNN.* in any folder that matches."""
    have = set()
    for f in d.glob(folder_glob):
        if f.is_dir() and not f.name.endswith("_chapters"):
            for x in f.glob(f"{prefix}-*"):
                m = re.match(rf"{prefix}-(\d{{4}})\.\w+$", x.name)
                if m and 1 <= int(m.group(1)) <= total:
                    have.add(int(m.group(1)))
    return have


def facts(d) -> dict:
    """Everything the steps are judged on, read from the book's folder."""
    chapters = (read_json(d / "chapters.json", {}) or {}).get("chapters", [])
    plan = ad.load(d)
    spst = sp.status(d, plan) if plan else {"exists": False, "approved": False, "missing": [], "total": 0, "written": 0}
    need = sorted(ad.chapter_clips(plan)) if plan else [c.get("n") for c in chapters if isinstance(c, dict)]
    scripted = {int(m.group(1)) for f in (d / "scripts").glob("chapter-*.json") if (m := re.match(r"chapter-(\d+)\.json$", f.name))} if (d / "scripts").is_dir() else set()
    import picture_record
    try:
        picture_record.record_new(d)                     # what each picture shows, the first time it is seen (cheap after that)
    except OSError:                                      # a folder being changed right now must not break the page; it is tried again next time
        pass
    rows = read_csv_rows(d / "all_shots.csv")
    total = len(rows)
    kf = _numbered("images/*_keyframes", d, "image", total)
    clips = _numbered("videos/*", d, "shot", total)
    sound = _numbered("audio/*", d, "narration", total)
    verdicts = review.load(d)
    keys = [review.shot_key(r) for r in rows]
    status = [(verdicts.get(k) or {}).get("status", "pending") for k in keys]
    flags = feedback.open_flags(d)
    return {
        "chapters": len(chapters), "plan": bool(plan), "plan_stale": bool(plan and plan.get("stale")), "screenplay": spst,
        "continuity": continuity_file(d).exists(), "chapters_needed": len(need), "chapters_written": len(set(need) & scripted),
        "shots": total, "keyframes": len(kf), "clips": len(clips), "narration": len(sound),
        "approved": status.count("approved"), "rejected": status.count("rejected"),
        "unreviewed_with_picture": sum(1 for i, s in enumerate(status, 1) if s == "pending" and i in kf),
        "rejected_with_picture": sum(1 for i, s in enumerate(status, 1) if s == "rejected" and i in kf),
        "storyline_changed": sp.storyline_changed(d), "flags": {k: len(v) for k, v in flags.items()}, "out_of_order": shot_order.out_of_order(d, rows),
        "films": len(list((d / "films").glob("*.mp4"))) if (d / "films").is_dir() else 0,
    }


def facts_empty() -> dict:
    return {"chapters": 0, "plan": False, "plan_stale": False, "screenplay": {"exists": False, "approved": False, "missing": [], "total": 0, "written": 0},
            "continuity": False, "chapters_needed": 0, "chapters_written": 0, "shots": 0, "keyframes": 0, "clips": 0, "narration": 0,
            "approved": 0, "rejected": 0, "unreviewed_with_picture": 0, "rejected_with_picture": 0, "storyline_changed": False, "flags": {}, "films": 0,
            "out_of_order": ""}


def judge(f: dict) -> dict[str, tuple[bool, bool, str]]:
    """step id -> (done, ok to go on, what to do now)."""
    sp_ = f["screenplay"]
    flagged = sum(f["flags"].values())
    out: dict[str, tuple[bool, bool, str]] = {}
    read = f["chapters"] > 0
    out["read"] = (read, read, "" if read else "Choose your book, then press \"Read the book\".")
    out["chapters"] = (read, read, "" if read else "Read the book first.")
    plan_ok = f["plan"] and not f["plan_stale"]
    out["plan"] = (plan_ok, plan_ok, "" if plan_ok else ("The chapters changed. Press \"Plan the film\" again." if f["plan_stale"] else "Choose how long your film is, then press \"Plan the film\"."))
    if flagged:
        todo = f"The storyboard changed {flagged} shot(s). Fix the scenes with a red outline (or press \"Keep it\"), then press \"Approve the screenplay\"."
    elif sp_.get("missing"):
        todo = f"Press \"Write the screenplay\" ({sp_.get('written', 0)} of {sp_.get('total', 0)} scenes written)."
    elif sp_.get("reordered"):
        todo = "You changed the order of the scenes after approving. Read it once more, then press \"Approve the screenplay\"."
    elif not sp_.get("approved"):
        todo = "Read the screenplay, change what you like, then press \"Approve the screenplay\"."
    else:
        todo = ""
    sp_ok = bool(sp_.get("approved")) and not flagged
    out["screenplay"] = (sp_ok, sp_ok, todo)
    out["continuity"] = (f["continuity"], f["continuity"], "" if f["continuity"] else "Press \"Make the story notes\" (who is in the story and what they look like).")
    out["cast"] = (True, True, "")
    out["look"] = (True, True, "")
    w = f["chapters_needed"] > 0 and f["chapters_written"] >= f["chapters_needed"]
    out["write"] = (w, w, "" if w else f"Press \"Write the shots\" ({f['chapters_written']} of {f['chapters_needed']} chapters done).")
    b = f["shots"] > 0 and not f["storyline_changed"] and not f["out_of_order"]
    if f["out_of_order"]:
        btodo = ("The scenes are in a new order. Press \"Get the shots ready\" to put the shots in that order "
                 "(pictures already made move with their shots, so nothing is made again).")
    elif f["storyline_changed"]:
        btodo = "The screenplay changed after the shots were made. Go to \"Check every picture\" and press \"Update storyboard from the storyline\"."
    else:
        btodo = "" if b else "Press \"Get the shots ready\"."
    out["build"] = (b, b, btodo)
    out["where"] = (True, True, "")                     # judged in the page: which computer and account are chosen
    k = f["shots"] > 0 and f["keyframes"] >= f["shots"]
    if f["unreviewed_with_picture"]:
        ktodo = f"{f['unreviewed_with_picture']} picture(s) are waiting for you. Say yes or no to each one in \"Check every picture\" before making more."
    elif f["rejected_with_picture"]:
        ktodo = f"You said no to {f['rejected_with_picture']} picture(s). Press \"Make the pictures\" to make new ones for them."
    elif not k:
        ktodo = f"Press \"Make the pictures\" ({f['keyframes']} of {f['shots']} made)."
    else:
        ktodo = ""
    out["keyframes"] = (k, f["keyframes"] > 0, ktodo)      # with some pictures made, the next step (checking them) may start
    s_ok = k and f["approved"] >= f["shots"] and not f["storyline_changed"] and not flagged and not f["out_of_order"]
    if f["storyline_changed"]:
        stodo = "The screenplay changed. Press \"Update storyboard from the storyline\"."
    elif flagged:
        stodo = "You changed the storyboard. Go back to the screenplay and approve it again."
    elif not k:
        stodo = "Make the pictures first."
    elif f["approved"] < f["shots"]:
        stodo = f"Say yes or no to every picture ({f['approved']} of {f['shots']} said yes). Pictures you said no to are made again."
    else:
        stodo = ""
    out["storyboard"] = (s_ok, s_ok, stodo)
    v = f["shots"] > 0 and f["clips"] >= f["shots"]
    out["video"] = (v, v, "" if v else f"Press \"Make the video\" ({f['clips']} of {f['shots']} clips made).")
    a = f["narration"] > 0
    out["audio"] = (a, a, "" if a else "Press \"Make the sound\".")
    c = f["films"] > 0
    out["cut"] = (c, c, "" if c else "Press \"Put the film together\".")
    out["premiere"] = (c, True, "")
    return out


def path_data(slug) -> dict:
    if not SLUG_RE.match(slug or ""):
        raise PlanError("pick a book first")
    found = pdir(slug)
    d = found if found.is_dir() else None                # a book in the books folder that has not been read yet: everything is still to do
    f = facts(d) if d else facts_empty()
    j = judge(f)
    revisit = feedback.load(d)["revisit"] if d else []
    steps = [{"id": sid, "title": title, "done": j[sid][0], "ok": j[sid][1], "todo": j[sid][2]} for sid, title in STEPS]
    alerts = []
    if revisit:
        alerts.append({"step": revisit[0], "text": f"Something changed in the storyboard. Go through the steps again, starting at \"{dict(STEPS)[revisit[0]]}\"."})
    if f["storyline_changed"]:
        alerts.append({"step": "storyboard", "text": "The screenplay changed after the shots were made. Update the storyboard so it matches."})
    if f["out_of_order"]:
        alerts.append({"step": "build", "text": "The shots are not in the screenplay's new scene order yet. Press \"Get the shots ready\" (nothing is made again)."})
    if f["unreviewed_with_picture"]:
        alerts.append({"step": "storyboard", "text": f"{f['unreviewed_with_picture']} picture(s) are waiting for a yes or a no."})
    return {"steps": steps, "revisit": revisit, "alerts": alerts, "facts": f}


def path_confirm(b: dict) -> dict:
    slug, step = b.get("project", ""), b.get("step", "")
    d = _book(slug)
    if step not in STEP_IDS:
        raise PlanError("unknown step")
    rev = feedback.load(d)["revisit"]
    if not rev or rev[0] != step:
        return path_data(slug)
    ok = judge(facts(d))[step]
    if not ok[1]:
        raise PlanError(ok[2] or "finish this step first")
    if step == "screenplay":
        sp.stamp_shots(d)          # the screenplay now agrees with the storyboard it was fixed from: the shots are not out of date
    feedback.confirm(d, step)
    return path_data(slug)


def shot_move_action(b: dict) -> dict:
    from .jobs import JOB
    d = _book(b.get("project", ""))
    if JOB.running:
        raise PlanError("wait until the running job is finished")
    import picture_record
    picture_record.record_new(d)
    n, direction = b.get("n"), b.get("direction")
    if not isinstance(n, int) or not isinstance(direction, int) or isinstance(n, bool) or isinstance(direction, bool):
        raise PlanError("say which shot and which way (-1 or 1)")
    try:
        now = shot_move.move(d, n, direction)
    except shot_move.MoveError as e:
        raise PlanError(str(e)) from e
    rows = read_csv_rows(d / "all_shots.csv")
    feedback.record(d, rows, now, "moved", "order", f"was shot {n}", f"now shot {now}")
    return {"n": now, "path": path_data(b.get("project", ""))}


def feedback_keep(b: dict) -> dict:
    d = _book(b.get("project", ""))
    scene = str(b.get("scene", ""))
    if not re.fullmatch(r"S\d{3,6}", scene):
        raise PlanError("bad scene id")
    return {"cleared": feedback.resolve(d, scene)}


def check_pictures_reviewed(slug) -> None:
    """Before more keyframe stills are made. A run only makes the pictures that are missing, so while any shot has no picture it may go ahead
    (pictures waiting for a yes or a no are not made again). With every shot pictured, a run would only make sense for pictures you said no to,
    and only after they were re-rolled: say so instead of spending GPU time on nothing. Raises PlanError with what to do."""
    d = pdir(slug)
    if not d.is_dir():
        return
    f = facts(d)
    if f["shots"] > f["keyframes"]:
        return
    if f["unreviewed_with_picture"]:
        raise PlanError(f"Every shot has a picture. {f['unreviewed_with_picture']} of them are waiting for a yes or a no on the storyboard: say no to the ones to make again.")
    if f["rejected_with_picture"]:
        raise PlanError(f"You said no to {f['rejected_with_picture']} picture(s). Press \"Re-roll rejected\" on the storyboard (or \"Make the keyframes\") so they are made again.")
    raise PlanError("Every shot already has a picture you said yes to: nothing to make.")
