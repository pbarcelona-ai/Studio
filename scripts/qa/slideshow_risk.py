"""Slideshow risk scorer across 6 dimensions (ported from OpenMontage)."""
from __future__ import annotations

from collections import Counter
from typing import Any


def score_slideshow_risk(
    scenes: list[dict[str, Any]],
    edit_decisions: dict[str, Any] | None = None,
    renderer_family: str | None = None,
    render_runtime: str | None = None,
) -> dict[str, Any]:
    """Score slideshow risk across 6 dimensions (0-5, lower is better)."""
    _ = edit_decisions
    if not scenes:
        return {
            "average": 5.0,
            "verdict": "fail",
            "dimensions": {},
            "render_runtime": render_runtime,
        }

    dimensions = {
        "repetition": _score_repetition(scenes),
        "decorative_visuals": _score_decorative(scenes),
        "weak_motion": _score_weak_motion(scenes),
        "weak_shot_intent": _score_weak_intent(scenes),
        "typography_overreliance": _score_typography(scenes),
        "unsupported_cinematic_claims": _score_cinematic_claims(scenes, renderer_family),
    }

    scores = [float(d["score"]) for d in dimensions.values()]
    average = sum(scores) / len(scores)

    if average < 2.0:
        verdict = "strong"
    elif average < 3.0:
        verdict = "acceptable"
    elif average < 4.0:
        verdict = "revise"
    else:
        verdict = "fail"

    return {
        "average": round(average, 2),
        "verdict": verdict,
        "dimensions": dimensions,
        "render_runtime": render_runtime,
    }


score = score_slideshow_risk


def _score_repetition(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    if len(scenes) < 3:
        return {"score": 0.0, "reason": "Too few scenes to assess repetition"}

    types = Counter(s.get("type", "unknown") for s in scenes)
    most_common_type, most_common_count = types.most_common(1)[0]
    type_ratio = most_common_count / len(scenes)

    descriptions = [str(s.get("description", "")).lower()[:50] for s in scenes]
    unique_desc_ratio = len(set(descriptions)) / len(descriptions)

    sizes = [(s.get("shot_language") or {}).get("shot_size", "none") for s in scenes]
    size_ratio = Counter(sizes).most_common(1)[0][1] / len(scenes)

    score_val = 0.0
    reasons: list[str] = []
    if type_ratio > 0.7:
        score_val += 2.0
        reasons.append(f"Scene type '{most_common_type}' dominates at {type_ratio:.0%}")
    if unique_desc_ratio < 0.6:
        score_val += 1.5
        reasons.append(f"Only {unique_desc_ratio:.0%} unique descriptions")
    if size_ratio > 0.6:
        score_val += 1.5
        reasons.append(f"Same shot size in {size_ratio:.0%} of scenes")

    return {"score": min(5.0, score_val), "reason": "; ".join(reasons) or "Good variety"}


def _score_decorative(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    decorative_count = 0
    for scene in scenes:
        has_info_role = bool(scene.get("information_role"))
        has_narrative_role = bool(scene.get("narrative_role"))
        has_intent = bool(scene.get("shot_intent"))
        if not has_info_role and not has_narrative_role and not has_intent:
            decorative_count += 1

    ratio = decorative_count / len(scenes)
    score_val = min(5.0, ratio * 5.0)
    if ratio > 0.5:
        reason = f"{decorative_count}/{len(scenes)} scenes have no stated purpose (no information_role, narrative_role, or shot_intent)"
    elif ratio > 0.2:
        reason = f"{decorative_count}/{len(scenes)} scenes lack stated purpose"
    else:
        reason = "Most scenes have clear communicative purpose"
    return {"score": round(score_val, 1), "reason": reason}


def _score_weak_motion(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    total_moving = 0
    purposeless_moving = 0
    for scene in scenes:
        sl = scene.get("shot_language") or {}
        movement = sl.get("camera_movement", "static")
        if movement not in ("static", "unspecified", None):
            total_moving += 1
            if not scene.get("shot_intent"):
                purposeless_moving += 1

    if total_moving == 0:
        return {"score": 1.5, "reason": "No camera movement defined (may be intentional for static style)"}

    ratio = purposeless_moving / total_moving
    score_val = min(5.0, ratio * 4.0)
    if ratio > 0.5:
        reason = f"{purposeless_moving}/{total_moving} moving shots lack shot_intent"
    else:
        reason = "Camera movement appears purposeful"
    return {"score": round(score_val, 1), "reason": reason}


def _score_weak_intent(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    with_intent = sum(1 for s in scenes if s.get("shot_intent"))
    ratio = with_intent / len(scenes)
    score_val = min(5.0, (1.0 - ratio) * 5.0)
    if ratio < 0.3:
        reason = f"Only {with_intent}/{len(scenes)} scenes have shot_intent — most shots lack purpose"
    elif ratio < 0.6:
        reason = f"{with_intent}/{len(scenes)} scenes have shot_intent"
    else:
        reason = "Strong shot intent coverage"
    return {"score": round(score_val, 1), "reason": reason}


def _score_typography(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    text_scenes = sum(1 for s in scenes if s.get("type") in ("text_card", "stat_card", "kpi_grid"))
    ratio = text_scenes / len(scenes)
    if ratio > 0.6:
        score_val = 4.0
        reason = f"{text_scenes}/{len(scenes)} scenes are text/stat cards — video feels like animated slides"
    elif ratio > 0.4:
        score_val = 2.5
        reason = f"{text_scenes}/{len(scenes)} scenes are text-based — consider balancing with visual scenes"
    elif ratio > 0.2:
        score_val = 1.0
        reason = "Balanced text and visual content"
    else:
        score_val = 0.0
        reason = "Visual-first approach"
    return {"score": score_val, "reason": reason}


def _score_cinematic_claims(
    scenes: list[dict[str, Any]],
    renderer_family: str | None,
) -> dict[str, Any]:
    is_cinematic = bool(renderer_family and "cinematic" in renderer_family.lower())
    if not is_cinematic:
        return {"score": 0.0, "reason": "Not claiming cinematic treatment"}

    issues: list[str] = []
    hero_count = sum(1 for s in scenes if s.get("hero_moment"))
    if hero_count == 0:
        issues.append("Claims cinematic but has no hero_moment defined")

    has_movement = sum(
        1 for s in scenes
        if (s.get("shot_language") or {}).get("camera_movement", "static") not in ("static", "unspecified", None)
    )
    if has_movement < len(scenes) * 0.3:
        issues.append(f"Claims cinematic but only {has_movement}/{len(scenes)} scenes have camera movement")

    has_lighting = sum(1 for s in scenes if (s.get("shot_language") or {}).get("lighting_key"))
    if has_lighting < len(scenes) * 0.3:
        issues.append(f"Claims cinematic but only {has_lighting}/{len(scenes)} scenes define lighting")

    score_val = min(5.0, len(issues) * 1.8)
    reason = "; ".join(issues) if issues else "Cinematic claims supported by structure"
    return {"score": round(score_val, 1), "reason": reason}
