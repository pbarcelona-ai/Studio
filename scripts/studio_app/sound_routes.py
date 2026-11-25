"""Voices, sound and music (made once for every style) and the audiobook, for the page (milestone M9).

POST /api/sound_plan {project, engine, claude_model}      the Voice Director, Sound Designer and Composer write the plan and the audio CSVs (a job)
GET  /api/sound?project=                                   {plan, gate, audiobook: {rendered, chapters, file}}
POST /api/sound_cast {project, name, voice?, emotion?}     change one voice by hand (the CSVs are written again)
POST /api/sound_approve {project}                          the REVIEW GATE of the sound
POST /api/audiobook_render {project}                       the audiobook narration on this computer (Kokoro; a job)
POST /api/audiobook_make {project}                         join it into exports/audiobook.m4b + one MP3 per chapter (a job)
POST /api/sfx_render {project, mode?, license?, force?}    fetch CC0 Openverse SFX + Earshot procedural synth (zero GPU; a job)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import gates
import shot_list
import sound_design
from layout import project_dir

from .api import Request, route
from .common import PlanError
from .generation import local_audio_step
from .jobs import JOB
from .steps import engine_args


def _book(slug) -> Path:
    try:
        d = project_dir(str(slug or ""), "book")
    except ValueError as e:
        raise PlanError(str(e)) from e
    if not d.is_dir():
        raise PlanError("pick a book first")
    return d


def _view(d: Path) -> dict:
    rows = sum(1 for _ in csv.DictReader(open(d / "audiobook.csv", newline="", encoding="utf-8"))) if (d / "audiobook.csv").is_file() else 0
    done = len(list((d / "audio" / "kokoro_audiobook").glob("narration-*.wav"))) if (d / "audio" / "kokoro_audiobook").is_dir() else 0
    m4b = d / "exports" / "audiobook.m4b"
    sfx_done = len({f.name for f in (d / "audio").glob("*/sfx-*.wav")}) if (d / "audio").is_dir() else 0
    return {"plan": sound_design.load(d) or None, "gate": gates.status(d, "sound", sound_design.gate_data(d)),
            "audiobook": {"chapters": rows, "rendered": done, "file": f"/download/{d.name}/exports/audiobook.m4b" if m4b.is_file() else ""},
            "sfx": {"rendered": sfx_done},
            "voices": list(sound_design.KOKORO), "emotions": list(sound_design.voices.EMOTIONS)}


@route("POST", "/api/sound_plan")
def _plan(r: Request):
    d = _book(r.body.get("project"))
    if not gates.approved(d, "shotlist", shot_list.gate_data(shot_list.load(d))):
        raise PlanError("approve the shot list first: the sound is planned shot by shot")
    engine = str(r.body.get("engine") or "claude")
    argv = ["python3", "sound_design.py", d.name] + (["--engine", "fake"] if engine == "fake" else engine_args(r.body))
    ahead = JOB.start([{"label": "Write the voices, sound and music", "argv": argv, "env": {}}], r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead}


@route("GET", "/api/sound")
def _get(r: Request):
    try:
        return _view(_book(r.q("project")))
    except PlanError:
        return {"plan": None, "gate": {"approved": False, "approved_at": "", "changed_since": False}, "audiobook": {"chapters": 0, "rendered": 0, "file": ""},
                "voices": [], "emotions": []}


@route("POST", "/api/sound_cast")
def _cast(r: Request):
    d = _book(r.body.get("project"))
    plan = sound_design.load(d)
    name = str(r.body.get("name", ""))
    target = plan.get("narrator") if name == "NARRATOR" else plan.get("cast", {}).get(name)
    if not plan or target is None:
        raise PlanError(f"no voice for {name!r} in the sound plan")
    voice, emotion = r.body.get("voice"), r.body.get("emotion")
    if voice is not None:
        if voice not in sound_design.KOKORO:
            raise PlanError("unknown voice")
        target["voice"] = voice
    if emotion is not None:
        if emotion not in sound_design.voices.EMOTIONS:
            raise PlanError("unknown emotion")
        target["emotion"] = emotion
    sound_design.path(d).write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
    sound_design.write_csvs(d, plan, shot_list.load(d))
    return _view(d)


@route("POST", "/api/sound_approve")
def _approve(r: Request):
    d = _book(r.body.get("project"))
    if not sound_design.load(d):
        raise PlanError("write the sound plan first")
    gates.approve(d, "sound", sound_design.gate_data(d))
    return _view(d)


@route("POST", "/api/audiobook_render")
def _ab_render(r: Request):
    d = _book(r.body.get("project"))
    if not (d / "audiobook.csv").is_file():
        raise PlanError("write the sound plan first (it makes audiobook.csv)")
    ahead = JOB.start([local_audio_step(d.name, "audiobook")], r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead}


@route("POST", "/api/audiobook_make")
def _ab_make(r: Request):
    d = _book(r.body.get("project"))
    if not gates.approved(d, "sound", sound_design.gate_data(d)):
        raise PlanError("approve the voices, sound and music first (Product F is made from the approved sound)")
    ahead = JOB.start([{"label": "Join the audiobook (M4B with chapters, MP3 per chapter)", "argv": ["python3", "sound_design.py", d.name, "--audiobook"], "env": {}}],
                      r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead}


@route("POST", "/api/sfx_render")
def _sfx_render(r: Request):
    d = _book(r.body.get("project"))
    if not (d / "audio_shots.csv").is_file() and not sound_design.load(d):
        raise PlanError("write the sound plan first (it lists the sound effects for each shot)")
    mode = str(r.body.get("mode") or "auto")
    if mode not in ("auto", "openverse", "earshot"):
        raise PlanError("mode must be auto, openverse or earshot")
    lic = str(r.body.get("license") or "cc0")
    if lic not in ("cc0", "commercial"):
        raise PlanError("license must be cc0 or commercial")
    argv = ["python3", "sfx_local.py", d.name, "--mode", mode, "--license", lic]
    if r.body.get("force"):
        argv.append("--force")
    ahead = JOB.start([{"label": f"Make sound effects ({mode}: Openverse / Earshot)", "argv": argv, "env": {}}],
                      r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead}
