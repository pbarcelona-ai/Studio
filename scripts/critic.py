"""Critic pass: finds the shots that are likely to need redoing, from the saved scripts, CSVs and results, with no AI call and no GPU.

  python3 critic.py <project> [--clip-seconds 4]

Checks (each finding has a shot, a kind, a severity high|warn|info and a sentence saying what to do):
  runtime      the planned shots add up to more or less than the film plan's runtime
  pacing       narration that is longer than its clip, or a chapter where most narration overruns
  variety      five shots in a row of the same size, a chapter with one size only, or the same shot twice in a row
  continuity   a face check that found a different person, a "continues" shot at another place, a character or place that was dropped from the prompt to
               make it fit the model's window
  clips        a finished clip much shorter or longer than the clip length (a clip that failed half way)
The result is saved as critic.json. flag_in_review() marks shots with a high finding as rejected in the storyboard review (only shots with no verdict yet).
"""
import argparse
import csv
import json
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path

import adaptation as ad
import review
from bookkit import CLIP_SECONDS, WORDS_PER_SECOND, continuity_file, project_dir, read_json, words

SIZES = (("close", r"\b(close[- ]?up|extreme close|macro|tight (shot|on)|insert)\b"), ("medium", r"\b(medium|mid[- ]shot|waist|over[- ]the[- ]shoulder)\b"),
         ("wide", r"\b(wide|establishing|long shot|aerial|landscape|panorama|full[- ]body|full shot|distant)\b"))
FINDING_KINDS = ("runtime", "pacing", "variety", "continuity", "clips")
SPILL = 1.0              # seconds a narration may run past its clip before it counts
RUN = 5                  # shots of one size in a row that are too many
SAME = 0.8               # word overlap that makes two neighbouring shots "the same shot"


def shot_size(text: str) -> str:
    t = (text or "").lower()
    for name, pat in SIZES:
        if re.search(pat, t):
            return name
    return "unknown"


def _overlap(a: str, b: str) -> float:
    x, y = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
    return len(x & y) / len(x | y) if x and y else 0.0


def _read_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(pdir: Path, clip_seconds: float = CLIP_SECONDS, durations: Callable[[Path], float | None] | None = None) -> dict:
    """{"findings": [...], "shots": n, "counts": {high, warn, info}, "flagged": [shot numbers with a high finding], "at": time}"""
    pdir = Path(pdir)
    shots = _read_rows(pdir / "all_shots.csv")
    if not shots:
        raise ValueError("no shots yet: build the CSVs first")
    audio = _read_rows(pdir / "audio_shots.csv")
    plan = ad.load(pdir)
    cont = read_json(continuity_file(pdir), {}) or {}
    names = [c["name"] for c in cont.get("characters", []) if isinstance(c, dict) and c.get("name")]
    places = {str(p.get("name", "")).lower(): p for p in cont.get("locations", []) if isinstance(p, dict)}
    visuals: dict[str, str] = {}
    for script in sorted((pdir / "scripts").glob("chapter-*.json")):
        d = read_json(script) or {}
        for s in d.get("shots", []):
            visuals[f"{d.get('chapter')}#{s.get('n')}"] = s.get("visual", "")
    faces = (read_json(pdir / "face_check.json", {}) or {}).get("rows", {})
    findings: list[dict] = []

    def add(n, kind, severity, message):
        findings.append({"n": n, "key": review.shot_key(shots[n - 1]) if n else "", "kind": kind, "severity": severity, "message": message})

    def clip_of(n: int) -> float:
        """This shot's clip length: the one set on the storyboard, else the model's."""
        try:
            return float(shots[n - 1].get("seconds") or clip_seconds)
        except (ValueError, IndexError):
            return clip_seconds

    spoken = []
    for i, r in enumerate(shots):
        a = audio[i] if i < len(audio) else {}
        spoken.append(words(a.get("narration", "")) / WORDS_PER_SECOND)

    # --- pacing
    by_chapter: dict[str, list[int]] = {}
    for i, r in enumerate(shots, start=1):
        by_chapter.setdefault(r.get("chapter", ""), []).append(i)
    for chapter, nums in by_chapter.items():
        long_ = [n for n in nums if spoken[n - 1] > clip_of(n) + SPILL]
        for n in long_:
            over = spoken[n - 1] - clip_of(n)
            add(n, "pacing", "high" if over > 3 else "warn", f"the narration takes {spoken[n - 1]:.1f} s but the clip is {clip_of(n):g} s: shorten the line, or press \"Match narration\" to make the clip longer")
        if len(nums) >= 4 and len(long_) > len(nums) / 2:
            add(nums[0], "pacing", "warn", f"most narration in {chapter} is longer than its clips: the chapter will feel rushed, lower the words per shot")

    # --- variety
    for chapter, nums in by_chapter.items():
        sizes = [shot_size(visuals.get(review.shot_key(shots[n - 1]), shots[n - 1].get("prompt", ""))) for n in nums]
        run_start = 0
        for k in range(1, len(sizes) + 1):
            if k == len(sizes) or sizes[k] != sizes[run_start]:
                if sizes[run_start] != "unknown" and k - run_start >= RUN:
                    add(nums[run_start + RUN - 1], "variety", "warn", f"{k - run_start} {sizes[run_start]} shots in a row: change the shot size or angle")
                run_start = k
        known = {s for s in sizes if s != "unknown"}
        if len(nums) >= 6 and len(known) == 1:
            add(nums[0], "variety", "info", f"every shot of {chapter} is a {next(iter(known))} shot: mix in other sizes")
        for k in range(1, len(nums)):
            a_, b_ = nums[k - 1], nums[k]
            va = visuals.get(review.shot_key(shots[a_ - 1]), "")
            vb = visuals.get(review.shot_key(shots[b_ - 1]), "")
            if va and vb and _overlap(va, vb) >= SAME and str(shots[b_ - 1].get("continues", "")) != "1":
                add(b_, "variety", "warn", f"almost the same picture as shot {a_}: change it or mark it as continuing")

    # --- continuity
    prev = None
    for n, r in enumerate(shots, start=1):
        face = faces.get(str(n)) or {}
        if face.get("status") == "different":
            add(n, "continuity", "high", "the face check found a different person from the reference picture: retake this shot")
        if str(r.get("continues", "")) == "1" and prev is not None:
            pa, pb = (prev.get("location") or "").strip().lower(), (r.get("location") or "").strip().lower()
            if pa and pb and pa != pb and prev.get("chapter") == r.get("chapter"):
                add(n, "continuity", "warn", f"marked as continuing the shot before, but the place changes ({prev.get('location')} to {r.get('location')})")
        prompt = r.get("prompt", "")
        for nm in [c for c in (r.get("characters") or "").split("|") if c in names]:
            if f"{nm.upper()}:" not in prompt:
                add(n, "continuity", "warn", f"{nm}'s description was cut from the prompt to make it fit: shorten the style words or the shot, or rewrite the prompts")
        loc = (r.get("location") or "").strip().lower()
        if loc in places and places[loc].get("token") and "SETTING:" not in prompt:
            add(n, "continuity", "info", f"the description of {r.get('location')} was cut from the prompt to make it fit")
        prev = r

    # --- runtime against the plan
    if plan:
        total = sum(max(clip_of(i), s) for i, s in enumerate(spoken, 1))
        want = float(plan["runtime_minutes"]) * 60 * (ad.total_clips(plan) / max(ad.total_clips(plan, active_only=False), 1))
        if want and abs(total - want) > 0.15 * want:
            add(0, "runtime", "warn", f"the shots add up to {total / 60:.1f} min but the plan asks for {want / 60:.1f} min ({'longer' if total > want else 'shorter'} by {abs(total - want) / 60:.1f} min)")

    # --- finished clips
    if durations is not None and (pdir / "videos").is_dir():
        for folder in sorted(p for p in (pdir / "videos").iterdir() if p.is_dir() and not p.name.endswith("_chapters")):
            for n in range(1, len(shots) + 1):
                clip = folder / f"shot-{n:04d}.mp4"
                secs = durations(clip) if clip.is_file() else None
                want_s = clip_of(n)
                if secs and abs(secs - want_s) > max(1.0, 0.4 * want_s):
                    add(n, "clips", "high" if secs < want_s * 0.5 else "warn", f"the {folder.name} clip is {secs:.1f} s, not about {want_s:g} s: it may have failed part way, or its length was changed; make it again")

    counts = {"high": 0, "warn": 0, "info": 0}
    for item in findings:
        counts[item["severity"]] += 1
    out = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "shots": len(shots), "clip_seconds": clip_seconds, "counts": counts, "findings": findings,
           "flagged": sorted({x["n"] for x in findings if x["severity"] == "high" and x["n"]})}
    (pdir / "critic.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out


def lipsync_rows(pdir: Path, include_medium: bool = False) -> dict:
    """The shots worth lip-syncing: a character (not the narrator) speaks in the shot and the shot is a close-up (with include_medium also a medium shot),
    so the mouth is big enough to see. {"rows": [{n, chapter, shot, speaker, size, text}], "runs": [[first, last], ...] of neighbouring rows}.
    Lip-syncing a wide shot, or a voice-over over a face that is not speaking, only spoils the picture."""
    pdir = Path(pdir)
    shots, audio = _read_rows(pdir / "all_shots.csv"), _read_rows(pdir / "audio_shots.csv")
    if not shots:
        raise ValueError("no shots yet: build the CSVs first")
    visuals: dict[str, str] = {}
    for script in sorted((pdir / "scripts").glob("chapter-*.json")):
        d = read_json(script) or {}
        for s in d.get("shots", []):
            visuals[f"{d.get('chapter')}#{s.get('n')}"] = s.get("visual", "")
    want = {"close", "medium"} if include_medium else {"close"}
    rows = []
    for n, r in enumerate(shots, start=1):
        a = audio[n - 1] if n <= len(audio) else {}
        try:
            lines = json.loads(a.get("lines_json") or "[]")
        except ValueError:
            continue
        speakers = [ln for ln in lines if isinstance(ln, list) and len(ln) >= 2 and str(ln[0]).strip().upper() != "NARRATOR" and str(ln[1]).strip()]
        size = shot_size(visuals.get(review.shot_key(r), r.get("prompt", "")))
        if speakers and size in want and (r.get("characters") or "").strip():
            rows.append({"n": n, "chapter": r.get("chapter", ""), "shot": r.get("shot", ""), "speaker": str(speakers[0][0]), "size": size, "text": str(speakers[0][1])[:120]})
    runs: list[list[int]] = []
    for x in rows:
        if runs and runs[-1][1] == x["n"] - 1:
            runs[-1][1] = x["n"]
        else:
            runs.append([x["n"], x["n"]])
    return {"rows": rows, "runs": runs}


def flag_in_review(pdir: Path, result: dict | None = None) -> int:
    """Reject, in the storyboard review, every shot that has a high finding and no verdict yet. Returns how many were flagged."""
    pdir = Path(pdir)
    result = result or read_json(pdir / "critic.json", {}) or {}
    shots = _read_rows(pdir / "all_shots.csv")
    have = review.load(pdir)
    todo: dict[str, list[str]] = {}
    for item in result.get("findings", []):
        if item.get("severity") == "high" and item.get("key") and item["key"] not in have:
            todo.setdefault(item["key"], []).append(item["message"])
    valid = {review.shot_key(r) for r in shots}
    for key, msgs in todo.items():
        review.set_status(pdir, [key], "rejected", "critic: " + "; ".join(msgs), valid)
    return len(todo)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--clip-seconds", type=float, default=CLIP_SECONDS)
    ap.add_argument("--flag", action="store_true", help="also reject the shots with a high finding in the storyboard review")
    a = ap.parse_args()
    try:
        res = run(project_dir(a.project), a.clip_seconds)
    except ValueError as e:
        sys.exit(str(e))
    print(f"{res['shots']} shots: {res['counts']['high']} high, {res['counts']['warn']} warnings, {res['counts']['info']} notes")
    for item in res["findings"]:
        print(f"  {item['severity']:5} {('shot ' + str(item['n'])) if item['n'] else 'film':8} {item['kind']:10} {item['message']}")
    if a.flag:
        print(f"flagged {flag_in_review(project_dir(a.project), res)} shot(s) in the storyboard")
