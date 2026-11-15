#!/usr/bin/env python3
"""Budget preview: how many clips a film needs, how many GPU hours they take, what that costs and how many days of free quota it uses.

  python3 budget.py <project> [--model ltx_video_fast_i2v] [--service kaggle] [--gpu NvidiaTeslaT4] [--minutes 10] [--pilot none|trailer|chapters]

Uses the adaptation plan when there is one (its active scenes, so a pilot is priced as a pilot), otherwise the runtime. The rates are in
budget_rates.json and are mostly assumptions; the answer says which. Prints a readable table; the Studio page calls estimate().
"""
import argparse
import json
import math
import sys
from pathlib import Path

import adaptation as ad
from bookkit import CLIP_SECONDS, project_dir, read_json

RATES = json.loads((Path(__file__).resolve().parent / "budget_rates.json").read_text())


def _rate(table: dict, key: str) -> float:
    v = table.get(key)
    return float(table["default"] if v is None else v)


def price(clips: int, model: str, service: str, gpu: str, clip_seconds: float = CLIP_SECONDS, keyframes: bool = True) -> dict:
    """Hours, money and days for `clips` clips. Everything is per clip of 4 seconds in the table, so longer clips scale linearly."""
    speed = _rate(RATES["gpu_speed_vs_t4"], gpu)
    per_clip_min = _rate(RATES["clip_minutes_on_t4"], model) * (clip_seconds / 4.0)
    video_h = clips * per_clip_min / speed / 60
    key_h = clips * float(RATES["keyframe_minutes_on_t4"]) / speed / 60 if keyframes else 0.0
    gpu_h = video_h + key_h
    free = RATES["free_weekly_gpu_hours"].get(service)
    paid = service in RATES["paid_services"]
    usd = gpu_h * _rate(RATES["gpu_usd_per_hour"], gpu) if paid else 0.0
    days = math.ceil(gpu_h / (float(free) / 7)) if free else None
    return {"clips": clips, "gpu_hours": round(gpu_h, 2), "video_hours": round(video_h, 2), "keyframe_hours": round(key_h, 2), "usd": round(usd, 2),
            "free_weekly_hours": free, "days_of_quota": days, "paid": paid,
            "measured": model == "ltx_video_fast_i2v" and gpu in ("NvidiaTeslaT4", "T4"),
            "note": ("Video time measured on a Kaggle T4 for this model; the rest is an assumption." if model == "ltx_video_fast_i2v" and gpu in ("NvidiaTeslaT4", "T4")
                     else "All rates here are assumptions (budget_rates.json); run one clip and replace them with what you measure.")}


def estimate(pdir: Path | None, model: str, service: str, gpu: str, minutes: float | None = None, clip_seconds: float | None = None,
             llm_calls: int | None = None) -> dict:
    """{"basis", "full": price, "pilot": price|None, "llm_calls", "llm_usd", "scenes", "minutes"} for a book (its plan if it has one) or a runtime."""
    plan = ad.load(pdir) if pdir else None
    chapters = (read_json(Path(pdir) / "chapters.json", {}) or {}).get("chapters", []) if pdir else []
    if plan:
        cs = float(plan["clip_seconds"])
        full_clips = ad.total_clips(plan, active_only=False)
        pilot = plan.get("pilot") or {}
        pilot_clips = ad.total_clips(plan) if pilot.get("kind", "none") != "none" else None
        calls = llm_calls if llm_calls is not None else len(chapters) + len(plan["acts"]) + 1 + len(plan["scenes"]) + len(chapters) // 2
        out = {"basis": "plan", "scenes": len(plan["scenes"]), "minutes": ad.plan_runtime(plan)["minutes"], "clip_seconds": cs, "pilot_kind": pilot.get("kind", "none")}
    else:
        cs = float(clip_seconds or CLIP_SECONDS)
        if not minutes:
            raise ad.AdaptationError("say how many minutes the film should run")
        full_clips = max(1, round(minutes * 60 / cs))
        pilot_clips = None
        calls = llm_calls if llm_calls is not None else len(chapters) * 2 + 1
        out = {"basis": "runtime", "scenes": None, "minutes": minutes, "clip_seconds": cs, "pilot_kind": "none"}
    out["full"] = price(full_clips, model, service, gpu, cs)
    out["pilot"] = price(pilot_clips, model, service, gpu, cs) if pilot_clips else None
    out["llm_calls"] = calls
    out["llm_usd"] = round(calls * float(RATES["llm_usd_per_call"]), 2)
    return out


def describe(e: dict) -> str:
    def line(label, p):
        money = f"${p['usd']:.2f}" if p["paid"] else "$0 (free service)"
        days = f", {p['days_of_quota']} day(s) of the weekly free quota" if p["days_of_quota"] else ""
        return f"{label}: {p['clips']} clips, {p['gpu_hours']:g} GPU hours ({p['video_hours']:g} video + {p['keyframe_hours']:g} keyframes), {money}{days}"
    rows = [f"Film: about {e['minutes']:g} minutes in clips of {e['clip_seconds']:g} s" + (f", {e['scenes']} scenes" if e["scenes"] else ""), line("Whole film", e["full"])]
    if e["pilot"]:
        rows.append(line(f"Pilot ({e['pilot_kind']})", e["pilot"]))
    rows.append(f"AI writing calls: about {e['llm_calls']} (about ${e['llm_usd']:.2f} at list price when the engine charges per call)")
    rows.append(e["full"]["note"])
    return "\n".join(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--model", default="ltx_video_fast_i2v")
    ap.add_argument("--service", default="kaggle", choices=["kaggle", "colab", "huggingface", "computer", "cloud"])
    ap.add_argument("--gpu", default="NvidiaTeslaT4")
    ap.add_argument("--minutes", type=float, default=None, help="only used when the book has no adaptation plan")
    a = ap.parse_args()
    try:
        print(describe(estimate(project_dir(a.project), a.model, a.service, a.gpu, a.minutes)))
    except ad.AdaptationError as err:
        sys.exit(str(err))
