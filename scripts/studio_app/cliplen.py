"""POST /api/clip_length: how long clips are.
  {project, n, seconds | null}                    one shot's clip (null: back to the video model's own length)
  {project, n, match_narration: true}             one shot's clip made as long as its words take to say (never shorter than it is now)
  {project, start, end, match_narration: true}    every shot of a movie (rows start..end) matched to its words
  {project, start, end, target_seconds, default_seconds}   the movie made about that long: the time is shared out in proportion to each clip's
                                                  length now, and no clip is made shorter than its words take to say
Every answer: {shots: [{n, seconds, spoken}], total, default}.
"""
import clip_length as cl
import review
from bookkit import SLUG_RE
from layout import project_dir as pdir

from .common import PlanError
from .projects import read_csv_rows


def _num(v, what, lo, hi):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise PlanError(f"{what} must be a number") from None
    if not lo <= x <= hi or x != x:
        raise PlanError(f"{what} must be at least {lo:g}" if hi == float("inf") else f"{what} must be {lo:g} to {hi:g}")
    return x


def share_out(bases: list[float], floors: list[float], target: float) -> list[float]:
    """Lengths in proportion to `bases` that add up to about `target`, none below its floor (its words), each a half second (no longest clip).
    A clip that would fall below its floor keeps its floor, and the rest of the time is shared out again among the others."""
    fixed: set[int] = set()
    out = list(floors)
    for _ in range(len(bases) + 1):
        free = [i for i in range(len(bases)) if i not in fixed]
        left = target - sum(floors[i] for i in fixed)
        base_free = sum(bases[i] for i in free)
        if not free or base_free <= 0:
            break
        for i in free:
            out[i] = bases[i] * left / base_free
        low = {i for i in free if out[i] < floors[i]}
        if not low:
            break
        fixed |= low
    return [cl.snap(max(o, f)) for o, f in zip(out, floors, strict=True)]


def clip_length_action(b: dict) -> dict:
    slug = b.get("project", "")
    d = pdir(slug)
    if not SLUG_RE.match(slug or "") or not d.is_dir():
        raise PlanError("pick a book first")
    rows, audio = read_csv_rows(d / "all_shots.csv"), read_csv_rows(d / "audio_shots.csv")
    if not rows:
        raise PlanError("no shots yet: get the shots ready first")
    default = _num(b.get("default_seconds") or 4, "the model's clip length", 0.5, 60)
    if "start" in b or "end" in b:
        a, z = b.get("start"), b.get("end")
        if not (isinstance(a, int) and isinstance(z, int) and 1 <= a <= z <= len(rows)):
            raise PlanError("bad row range")
        targets = list(range(a, z + 1))
    else:
        n = b.get("n")
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(rows):
            raise PlanError("there is no such shot")
        targets = [n]
    saved = cl.load(d)
    key = {n: review.shot_key(rows[n - 1]) for n in targets}
    words = {n: (audio[n - 1] if n <= len(audio) else {}) for n in targets}
    try:
        if b.get("target_seconds") not in (None, ""):
            target = _num(b["target_seconds"], "the movie's length", cl.LEAST * len(targets), float("inf"))
            bases = [saved.get(key[n], default) for n in targets]
            floors = [cl.fit_narration(words[n]) if cl.spoken_seconds(words[n]) else cl.LEAST for n in targets]
            for n, v in zip(targets, share_out(bases, floors, target), strict=True):
                saved[key[n]] = v
        elif b.get("match_narration"):                     # longer when the words need it, never shorter than the clip is now
            for n in targets:
                saved[key[n]] = cl.fit_narration(words[n], saved.get(key[n], default))
        elif b.get("seconds") in (None, ""):
            for n in targets:
                saved.pop(key[n], None)
        else:
            v = cl.snap(_num(b["seconds"], "a clip", cl.LEAST, float("inf")))
            for n in targets:
                saved[key[n]] = v
        cl.save_all(d, saved)
    except cl.ClipLengthError as e:
        raise PlanError(str(e)) from e
    now = cl.load(d)
    shots = [{"n": n, "seconds": now.get(key[n]), "spoken": cl.spoken_seconds(words[n])} for n in targets]
    return {"shots": shots, "total": round(sum(s["seconds"] or default for s in shots), 1), "default": default}
