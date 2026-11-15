"""Colour grading per scene (or for the whole film), beyond mix_film's --match-colour.

  projects/books/<book>/grading.json
    {"default": {"preset": "warm"},
     "scenes": {"S003": {"preset": "night", "exposure": -0.05, "temperature": -0.4}}}

A grade is a preset plus optional numbers that replace the preset's: exposure (-0.5..0.5), contrast (0.5..2), saturation (0..3), temperature (-1 cool..1 warm),
tint (-1 green..1 magenta). mix_film.py --grade turns it into an ffmpeg filter (eq and colorbalance) for every shot, using the scene of each shot
(the `scene` column of audio_shots.csv, written by book_build.py when the book has a film plan). Shots of scenes without a grade get the default, else none.
"""
import csv
import json
import os
import re
from pathlib import Path

from bookkit import read_json

PRESETS = {
    "none": {},
    "warm": {"temperature": 0.25, "saturation": 1.05},
    "cool": {"temperature": -0.25},
    "golden_hour": {"temperature": 0.35, "saturation": 1.15, "contrast": 1.05, "exposure": 0.03},
    "night": {"temperature": -0.3, "exposure": -0.12, "contrast": 1.1, "saturation": 0.85},
    "desaturated": {"saturation": 0.6},
    "noir": {"saturation": 0.0, "contrast": 1.25, "exposure": -0.05},
    "vivid": {"saturation": 1.35, "contrast": 1.08},
    "faded": {"saturation": 0.75, "contrast": 0.88, "exposure": 0.05},
}
LIMITS = {"exposure": (-0.5, 0.5), "contrast": (0.5, 2.0), "saturation": (0.0, 3.0), "temperature": (-1.0, 1.0), "tint": (-1.0, 1.0)}
NEUTRAL = {"exposure": 0.0, "contrast": 1.0, "saturation": 1.0, "temperature": 0.0, "tint": 0.0}


class GradeError(ValueError):
    """A readable reason a grade is not acceptable."""


def check_spec(spec) -> dict:
    """The cleaned grade from the page: {"preset"?, exposure?, contrast?, saturation?, temperature?, tint?}; {} means no grade."""
    if not isinstance(spec, dict):
        raise GradeError("a grade is {preset, exposure, contrast, saturation, temperature, tint}")
    out: dict = {}
    if spec.get("preset"):
        if spec["preset"] not in PRESETS:
            raise GradeError(f"preset must be one of {', '.join(PRESETS)}")
        if spec["preset"] != "none":
            out["preset"] = spec["preset"]
    for key, (lo, hi) in LIMITS.items():
        if spec.get(key) not in (None, ""):
            try:
                v = float(spec[key])
            except (TypeError, ValueError) as e:
                raise GradeError(f"{key} must be a number") from e
            if not lo <= v <= hi:
                raise GradeError(f"{key} must be {lo:g} to {hi:g}")
            out[key] = v
    return out


def values(spec: dict | None) -> dict:
    """The five numbers of a grade: the preset's, replaced by the ones given, over neutral."""
    spec = spec or {}
    v = dict(NEUTRAL)
    v.update(PRESETS.get(spec.get("preset") or "none", {}))
    v.update({k: float(spec[k]) for k in LIMITS if isinstance(spec.get(k), (int, float)) and not isinstance(spec.get(k), bool)})
    return v


def filter_for(spec: dict | None) -> str:
    """An ffmpeg filter chain ending in a comma, to put in front of other video filters; "" when the grade changes nothing."""
    v = values(spec)
    if v == NEUTRAL:
        return ""
    t, g = v["temperature"], v["tint"]
    parts = [f"eq=brightness={v['exposure']:.3f}:contrast={v['contrast']:.3f}:saturation={v['saturation']:.3f}"]
    if t or g:
        rs, bs, rm, bm, rh, bh = (round(x * t, 3) for x in (0.15, -0.15, 0.2, -0.2, 0.1, -0.1))
        gg = round(-0.12 * g, 3)
        parts.append(f"colorbalance=rs={rs}:gs={gg}:bs={bs}:rm={rm}:gm={gg}:bm={bm}:rh={rh}:gh={gg}:bh={bh}")
    return ",".join(parts) + ","


def grading_file(pdir: Path) -> Path:
    return Path(pdir) / "grading.json"


def load(pdir: Path) -> dict:
    d = read_json(grading_file(pdir), {})
    d = d if isinstance(d, dict) else {}
    return {"default": d.get("default") if isinstance(d.get("default"), dict) else {}, "scenes": d.get("scenes") if isinstance(d.get("scenes"), dict) else {}}


def set_grade(pdir: Path, scene: str, spec) -> dict:
    """Save the grade of a scene id ("S003") or of "default". An empty grade removes it."""
    if scene != "default" and not re.fullmatch(r"S\d{3,6}", scene or ""):
        raise GradeError("say which scene (or default)")
    clean = check_spec(spec)
    d = load(pdir)
    if scene == "default":
        d["default"] = clean
    elif clean:
        d["scenes"][scene] = clean
    else:
        d["scenes"].pop(scene, None)
    f = grading_file(pdir)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=1))
    os.replace(tmp, f)
    return d


def row_filters(pdir: Path) -> dict[int, str]:
    """{row of audio_shots.csv: filter} for every shot whose scene (else the default) has a grade."""
    pdir = Path(pdir)
    g = load(pdir)
    default = filter_for(g["default"])
    by_scene = {sid: filter_for(spec) for sid, spec in g["scenes"].items()}
    try:
        with open(pdir / "audio_shots.csv", newline="", encoding="utf-8") as fh:
            scenes = [(r.get("scene") or "").rsplit("-", 1)[-1] for r in csv.DictReader(fh)]
    except OSError:
        scenes = []
    out = {}
    for n, sid in enumerate(scenes, start=1):
        f = by_scene.get(sid, default)
        if f:
            out[n] = f
    return out
