"""Early-stage AI & deterministic frame-by-frame / beat-by-beat prompt continuity auditor.

Catches prompt contradictions, prop teleportation, room-boundary leaks, scale drift,
wardrobe drift, and missing surfaces at the EARLIEST generation point of each upstream
piece of a prompt:

  - Step 03 (Coverage / Read-In): character identity/species/age/scale & event continuity
  - Step 04 (Scope & Format): runtime vs chapter/scene budget, pacing, rating alignment
  - Step 05 (Beats / Adaptation): scene-to-scene location, time-of-day, cast & prop flow
  - Step 06 (Screenplay): beat-by-beat & line-by-line action/dialogue/prop/surface continuity
  - Step 07 (Continuity Book): style-neutral character/location/prop tokens, relative scale & rooms
  - Step 12 (Shot List): full frame-by-frame shot continuity & scale (via `shot_continuity_audit`)

Structured around transparent audit principles:
  1. Per-criterion Scorecard (Pass / Needs Work / Fail + one-line reason)
  2. Severity-ordered issues (critical / major / minor) with exact target, field, and risk
  3. Targeted surgical fixes — NEVER auto-applying items flagged as `ambiguous` (flag instead of guessing)
  4. Explicit Blind Spots & Assumptions (e.g., missing Step 11 baselined sets, unspecified heights, offline mode)

Uses local Ollama first, then `gemini-3.8-flash` (fast `thinking_budget=0` JSON mode),
falling back cleanly to deterministic offline checks so automated pipelines & tests never block.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import contextlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("studio.early_prompt_audit")

EARLY_AUDIT_STEPS = (3, 4, 5, 6, 7, 12)
STEP_LABELS: dict[int, str] = {
    3: "Step 03: Coverage & Logline",
    4: "Step 04: Format & Runtime Scope",
    5: "Step 05: Story Structure & Beats",
    6: "Step 06: Screenplay",
    7: "Step 07: Continuity Book",
    12: "Step 12: Shot List",
}
_SEVERITY_RANK: dict[str, int] = {"critical": 0, "major": 1, "minor": 2}
_VALID_RATINGS = ("Pass", "Needs Work", "Fail")

_DOG_WORDS = ("dog", "labrador", "puppy", "hound", "retriever", "terrier", "poodle", "beagle", "canine")
_CHILD_WORDS = ("boy", "girl", "child", "kid", "toddler", "5-year-old", "4-year-old", "3-year-old", "waist-high")
_TOY_WORDS = ("action figure", "rag doll", "stuffed", "plush", "toy", "foot-tall", "doll")
_VAGUE_PATTERN_RE = re.compile(r"\b(striped|plaid|checkered|patterned|polka[- ]dot|multicolou?red)\b", re.IGNORECASE)
_STYLE_BUZZ_RE = re.compile(
    r"(?i)\b(photo-?realistic|photoreal|hyper-?realistic|claymation|plasticine|3d|cgi|pixar|anime|manga|"
    r"cartoon\w*|watercolou?r|oil[- ]painting|illustrat\w*|render\w*|cel[- ]shad\w*|stop[- ]motion|unreal engine|octane)\b"
)

_AUDITOR_RULES_BLOCK = (
    "STRICT AUDITOR RULES:\n"
    "- Be objective and specific; zero vague praise or filler.\n"
    "- Order issues by severity ('critical' | 'major' | 'minor') and state concrete downstream 'risk'.\n"
    "- NEVER invent facts, furniture, props, or character traits not present in the source. "
    "If something is genuinely ambiguous, set '\"ambiguous\": true' and leave replacement text EMPTY so the human decides instead of guessing.\n"
    "- Include a 'blind_spots' list of unverified assumptions or missing context.\n"
)


def _norm_severity(val: Any, default: str = "major") -> str:
    s = str(val or "").strip().lower()
    return s if s in _SEVERITY_RANK else default


def _make_issue(
    target: str,
    field: str,
    issue: str,
    *,
    severity: str = "major",
    risk: str = "",
    fixed: bool = False,
    ambiguous: bool = False,
) -> dict[str, Any]:
    return {
        "target": str(target or "").strip(),
        "field": str(field or "").strip(),
        "severity": _norm_severity(severity, "major"),
        "risk": str(risk or "").strip(),
        "issue": str(issue or "").strip(),
        "fixed": bool(fixed) and not bool(ambiguous),
        "ambiguous": bool(ambiguous),
        "needs_user_decision": bool(ambiguous),
    }


def _sort_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        issues,
        key=lambda x: (
            0 if x.get("ambiguous") else 1,
            _SEVERITY_RANK.get(_norm_severity(x.get("severity")), 1),
            str(x.get("target") or ""),
        ),
    )


def _dedupe_blind_spots(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        s = str(raw or "").strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def _build_scorecard(
    specs: list[tuple[str, tuple[str, ...], str]],
    issues: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Produce a per-criterion Pass / Needs Work / Fail scorecard from severity-tagged issues."""
    cards: list[dict[str, str]] = []
    for criterion, keywords, ok_reason in specs:
        matched = [
            it
            for it in issues
            if any(
                k in f"{it.get('field', '')} {it.get('target', '')} {it.get('issue', '')}".lower()
                for k in keywords
            )
        ]
        unresolved_crit = [it for it in matched if not it.get("fixed") and (it.get("ambiguous") or it.get("severity") == "critical")]
        unresolved_any = [it for it in matched if not it.get("fixed")]
        fixed_any = [it for it in matched if it.get("fixed")]
        if unresolved_crit:
            rating = "Fail"
            reason = f"{len(unresolved_crit)} critical/ambiguous item(s) need attention."
        elif unresolved_any:
            rating = "Needs Work"
            reason = f"{len(unresolved_any)} unresolved item(s) flagged."
        elif fixed_any:
            rating = "Needs Work"
            reason = f"{len(fixed_any)} issue(s) caught and auto-fixed."
        else:
            rating = "Pass"
            reason = ok_reason
        cards.append({"criterion": criterion, "rating": rating, "reason": reason})
    return cards


def _reports_path(pd: Path) -> Path:
    return pd / "early_audit_reports.json"


def load_reports(pd: Path) -> dict[str, Any]:
    p = _reports_path(pd)
    if not p.is_file():
        return {"steps": {}, "updated_at": 0.0}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw.setdefault("steps", {})
            return raw
    except (OSError, ValueError):
        pass
    return {"steps": {}, "updated_at": 0.0}


def save_step_report(pd: Path, step_num: int, report: dict[str, Any]) -> None:
    data = load_reports(pd)
    steps = data.get("steps")
    if not isinstance(steps, dict):
        steps = {}
    steps[str(step_num)] = report
    data["steps"] = steps
    data["updated_at"] = round(time.time(), 2)
    p = _reports_path(pd)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _call_ai_json(prompt: str, *, use_llm: bool = True, timeout: float = 40.0) -> tuple[dict[str, Any], str]:
    if not use_llm or os.environ.get("NEON_SKIP_EARLY_AUDIT_LLM", "").strip() in ("1", "true", "yes"):
        return {}, "deterministic"
    from studio_app import set_vision_sync

    parsed, eng = set_vision_sync._call_ollama_vision_json(prompt, None, timeout=timeout)
    if parsed:
        return parsed, eng
    parsed, eng = set_vision_sync._call_gemini_vision_json(prompt, None, timeout=timeout)
    if parsed:
        return parsed, eng
    return {}, "deterministic"


def _record_sync_if_needed(pd: Path, slug: str, step_num: int, summary: str) -> None:
    with contextlib.suppress(Exception):
        from studio_app import workflow_sync

        workflow_sync.record_modification(pd, slug, step_num, summary)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, data: Any, *, indent: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=indent, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ==============================================================================
# STEP 03: COVERAGE & READ-IN
# ==============================================================================
def _audit_step3(pd: Path, slug: str, *, use_llm: bool, auto_apply: bool, record_bidirectional: bool) -> dict[str, Any]:
    cov_path = pd / "readin" / "coverage.json"
    cov = _read_json(cov_path)
    if not isinstance(cov, dict):
        return {
            "ok": True,
            "step": 3,
            "label": STEP_LABELS[3],
            "skipped": True,
            "engine": "deterministic",
            "issues_count": 0,
            "fixes_applied": 0,
            "ambiguous_count": 0,
            "scorecard": [],
            "blind_spots": ["No readin/coverage.json exists yet — coverage cannot be audited."],
            "issues": [],
            "message": "No readin/coverage.json yet — run Read It In first.",
        }

    issues: list[dict[str, Any]] = []
    blind_spots: list[str] = []
    fixes_applied = 0
    changed = False
    raw_chars = cov.get("characters")
    chars: list[Any] = raw_chars if isinstance(raw_chars, list) else []

    # Deterministic check: ensure every character has non-empty description & clean identity
    for c in chars:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        desc = str(c.get("description") or "").strip()
        if not name:
            continue
        if len(desc) < 12:
            issues.append(
                _make_issue(
                    name,
                    "description",
                    f"Character '{name}' has an overly brief coverage description — downstream prompts may guess wrong age/species/scale.",
                    severity="major",
                    risk="Steps 06, 07, 10, and 17 may invent inconsistent age, species, or height.",
                    fixed=False,
                    ambiguous=False,
                )
            )
            blind_spots.append(f"Character '{name}' lacks explicit age/species/height in Step 03 coverage.")

    engine = "deterministic"
    prompt = (
        "You are a Continuity Script Supervisor auditing Step 03 (Coverage) BEFORE beats, screenplay, or shots are written.\n"
        "Inspect the logline, characters, and key_events for early prompt consistency issues:\n"
        "1. Every recurring character description must unambiguously state species (human/dog/toy/etc.), approximate age, and relative height/size so downstream steps never confuse scale.\n"
        "2. Flag any contradictory traits, duplicate character names, or chronological/location jumps in key_events.\n"
        + _AUDITOR_RULES_BLOCK
        + "Return ONLY valid JSON:\n"
        '{"issues": [{"target": "character name or key_events", "field": "description|logline|key_events", '
        '"severity": "critical|major|minor", "issue": "brief explanation", "risk": "downstream impact", "ambiguous": false, '
        '"value": "optional corrected text (empty if advisory or ambiguous)"}], "blind_spots": ["optional missing context"]}\n'
        "If everything is already clear and consistent, return {\"issues\": [], \"blind_spots\": []}.\n\n"
        f"COVERAGE:\n{json.dumps(cov, ensure_ascii=False)[:14000]}"
    )
    ai_data, eng = _call_ai_json(prompt, use_llm=use_llm)
    if eng:
        engine = eng
    raw_ai_issues = ai_data.get("issues") if isinstance(ai_data, dict) else []
    if isinstance(raw_ai_issues, list):
        for item in raw_ai_issues:
            if not isinstance(item, dict) or not str(item.get("issue") or "").strip():
                continue
            target = str(item.get("target") or "").strip()
            field = str(item.get("field") or "").strip().lower()
            val = str(item.get("value") or "").strip()
            is_amb = bool(item.get("ambiguous") or item.get("needs_user_decision"))
            fixed = False
            if auto_apply and val and not is_amb:
                if field == "logline":
                    cov["logline"] = val[:500]
                    fixed = True
                    changed = True
                    fixes_applied += 1
                elif field == "description" and target:
                    for c in chars:
                        if isinstance(c, dict) and str(c.get("name") or "").strip().lower() == target.lower():
                            c["description"] = val[:400]
                            fixed = True
                            changed = True
                            fixes_applied += 1
                            break
            issues.append(
                _make_issue(
                    target or field,
                    field,
                    str(item["issue"]).strip(),
                    severity=_norm_severity(item.get("severity"), "major"),
                    risk=str(item.get("risk") or "Downstream beats and character tokens inherit coverage ambiguity.").strip(),
                    fixed=fixed,
                    ambiguous=is_amb,
                )
            )
    if isinstance(ai_data, dict) and isinstance(ai_data.get("blind_spots"), list):
        blind_spots.extend(str(x) for x in ai_data["blind_spots"])
    if engine == "deterministic":
        blind_spots.append("Offline deterministic check only — AI semantic review did not run.")

    if changed and auto_apply:
        _write_json(cov_path, cov)
        if record_bidirectional:
            _record_sync_if_needed(pd, slug, 3, f"Early prompt audit fixed {fixes_applied} coverage item(s)")

    sorted_issues = _sort_issues(issues)
    amb_count = sum(1 for it in sorted_issues if it.get("ambiguous"))
    scorecard = _build_scorecard(
        [
            ("Character Identity & Scale", ("description", "character", "species", "age", "height", "scale"), "Characters have clear visual identity and relative scale."),
            ("Premise & Event Flow", ("logline", "key_events", "event", "chronolog"), "Logline and key events flow without contradictions."),
        ],
        sorted_issues,
    )
    return {
        "ok": True,
        "step": 3,
        "label": STEP_LABELS[3],
        "engine": engine,
        "issues_count": len(sorted_issues),
        "fixes_applied": fixes_applied,
        "ambiguous_count": amb_count,
        "scorecard": scorecard,
        "blind_spots": _dedupe_blind_spots(blind_spots),
        "issues": sorted_issues,
        "message": (
            f"Step 03 Coverage audited ({engine}): {len(sorted_issues)} issue(s), {fixes_applied} auto-fixed"
            + (f", {amb_count} need decision." if amb_count else ".")
            if sorted_issues
            else f"Step 03 Coverage clean ({engine}) — no contradictions found."
        ),
    }


# ==============================================================================
# STEP 04: FORMAT & RUNTIME SCOPE
# ==============================================================================
def _audit_step4(pd: Path, slug: str, *, use_llm: bool, auto_apply: bool, record_bidirectional: bool) -> dict[str, Any]:
    import production

    settings = production.load(pd)
    ch_idx = _read_json(pd / "chapters.json") or {}
    raw_chapters = ch_idx.get("chapters") if isinstance(ch_idx, dict) else None
    chapters: list[Any] = raw_chapters if isinstance(raw_chapters, list) else []
    total_words = sum(int(c.get("words") or 0) for c in chapters if isinstance(c, dict))
    n_chapters = len(chapters)
    target_min = float(settings.get("target_minutes") or 10.0)
    issues: list[dict[str, Any]] = []
    blind_spots: list[str] = []

    if n_chapters == 0:
        blind_spots.append("No chapters.json found yet — runtime-to-source pacing ratio could not be verified.")

    # Deterministic pacing/scope checks
    if n_chapters > 0 and target_min < max(2.0, n_chapters * 0.4):
        issues.append(
            _make_issue(
                "target_minutes",
                "target_minutes",
                f"Target runtime ({target_min:g} min) is tight for {n_chapters} chapters ({total_words:,} words); scenes may become overcrowded and cause abrupt prop/location jumps.",
                severity="major",
                risk="Compressing too many chapters into too few minutes causes teleporting locations and rushed transitions.",
                fixed=False,
            )
        )
    if total_words > 0 and total_words < 1500 and target_min > 45:
        issues.append(
            _make_issue(
                "target_minutes",
                "target_minutes",
                f"Target runtime ({target_min:g} min) is very long for {total_words:,} source words; heavy invention may introduce ungrounded settings or props.",
                severity="major",
                risk="Over-expanding thin source text increases hallucinated sets and props downstream.",
                fixed=False,
            )
        )
    aspect = str(settings.get("aspect") or "").strip()
    if aspect not in ("16:9", "2.39:1", "9:16", "4:3", "1:1"):
        issues.append(
            _make_issue(
                "aspect",
                "aspect",
                f"Unusual aspect ratio '{aspect}' — verify framing consistency across Steps 11, 12, and 17.",
                severity="minor",
                risk="Non-standard aspect ratios may crop keyframe composition unexpectedly.",
                fixed=False,
            )
        )

    engine = "deterministic"
    if use_llm:
        cov = _read_json(pd / "readin" / "coverage.json") or {}
        if not cov:
            blind_spots.append("No Step 03 coverage.json yet — rating/tone alignment is unchecked.")
        prompt = (
            "You are a Film Producer auditing Step 04 (Scope & Format) settings against the source book coverage.\n"
            "Check if target_minutes, aspect ratio, rating, and faithfulness align cleanly with the book's scope & tone "
            "so downstream beats/screenplay/shots won't be cramped or padded with inconsistent scenes.\n"
            + _AUDITOR_RULES_BLOCK
            + 'Return ONLY valid JSON: {"issues": [{"target": "target_minutes|rating|aspect|faithfulness", "severity": "critical|major|minor", "issue": "...", "risk": "...", "ambiguous": false}], "blind_spots": ["..."]}\n'
            "If the scope settings fit well, return {\"issues\": [], \"blind_spots\": []}.\n\n"
            f"SETTINGS: {json.dumps(settings, ensure_ascii=False)}\n"
            f"BOOK STATS: {n_chapters} chapters, {total_words} words.\n"
            f"COVERAGE SUMMARY: {json.dumps({'logline': cov.get('logline', ''), 'genre': cov.get('genre', ''), 'tone': cov.get('tone', '')}, ensure_ascii=False)}"
        )
        ai_data, eng = _call_ai_json(prompt, use_llm=use_llm)
        if eng:
            engine = eng
        raw_ai = ai_data.get("issues") if isinstance(ai_data, dict) else []
        if isinstance(raw_ai, list):
            for item in raw_ai:
                if isinstance(item, dict) and str(item.get("issue") or "").strip():
                    issues.append(
                        _make_issue(
                            str(item.get("target") or "scope").strip(),
                            str(item.get("target") or "scope").strip(),
                            str(item["issue"]).strip(),
                            severity=_norm_severity(item.get("severity"), "major"),
                            risk=str(item.get("risk") or "Mismatched scope distorts scene pacing.").strip(),
                            fixed=False,
                            ambiguous=bool(item.get("ambiguous")),
                        )
                    )
        if isinstance(ai_data, dict) and isinstance(ai_data.get("blind_spots"), list):
            blind_spots.extend(str(x) for x in ai_data["blind_spots"])
    else:
        blind_spots.append("Offline deterministic scope check only — tone/rating semantic review did not run.")

    sorted_issues = _sort_issues(issues)
    amb_count = sum(1 for it in sorted_issues if it.get("ambiguous"))
    scorecard = _build_scorecard(
        [
            ("Runtime & Pacing Fit", ("target_minutes", "runtime", "chapter", "pacing"), "Target runtime fits the source length."),
            ("Format & Rating Alignment", ("aspect", "rating", "faithfulness", "scope"), "Aspect ratio, rating, and faithfulness are consistent."),
        ],
        sorted_issues,
    )
    return {
        "ok": True,
        "step": 4,
        "label": STEP_LABELS[4],
        "engine": engine,
        "issues_count": len(sorted_issues),
        "fixes_applied": 0,
        "ambiguous_count": amb_count,
        "scorecard": scorecard,
        "blind_spots": _dedupe_blind_spots(blind_spots),
        "issues": sorted_issues,
        "message": (
            f"Step 04 Scope audited ({engine}): {len(sorted_issues)} advisory note(s)."
            if sorted_issues
            else f"Step 04 Scope clean ({engine}) — runtime, format & rating aligned."
        ),
    }


# ==============================================================================
# STEP 05: STORY STRUCTURE, BEATS & SCENE BREAKDOWN
# ==============================================================================
def _audit_step5(pd: Path, slug: str, *, use_llm: bool, auto_apply: bool, record_bidirectional: bool) -> dict[str, Any]:
    import adaptation as ad

    plan = ad.load(pd)
    if not isinstance(plan, dict) or not isinstance(plan.get("scenes"), list) or not plan["scenes"]:
        return {
            "ok": True,
            "step": 5,
            "label": STEP_LABELS[5],
            "skipped": True,
            "engine": "deterministic",
            "issues_count": 0,
            "fixes_applied": 0,
            "ambiguous_count": 0,
            "scorecard": [],
            "blind_spots": ["No adaptation/adaptation.json scenes exist yet."],
            "issues": [],
            "message": "No adaptation/adaptation.json scenes yet — generate Beats / Read It In first.",
        }

    scenes: list[dict[str, Any]] = [s for s in plan["scenes"] if isinstance(s, dict)]
    issues: list[dict[str, Any]] = []
    blind_spots: list[str] = []
    fixes_applied = 0
    changed = False

    # Deterministic beat-to-beat checks
    for i, sc in enumerate(scenes):
        sid = str(sc.get("id") or f"S{i + 1:03d}")
        loc = str(sc.get("location") or "").strip()
        tod = str(sc.get("time_of_day") or "").strip()
        summary = str(sc.get("summary") or "").strip()
        if not loc:
            issues.append(
                _make_issue(
                    sid,
                    "location",
                    f"Scene {sid} is missing a concrete location.",
                    severity="critical",
                    risk="Screenplay and Step 11 Sets will invent conflicting room names.",
                    fixed=False,
                    ambiguous=True,
                )
            )
        if not tod:
            if auto_apply and i > 0 and str(scenes[i - 1].get("time_of_day") or "").strip():
                sc["time_of_day"] = str(scenes[i - 1]["time_of_day"]).strip()
                changed = True
                fixes_applied += 1
                issues.append(
                    _make_issue(
                        sid,
                        "time_of_day",
                        f"Scene {sid} had blank time_of_day; inherited '{sc['time_of_day']}' from previous scene.",
                        severity="minor",
                        risk="Blank time-of-day causes lighting drift between consecutive scenes.",
                        fixed=True,
                    )
                )
            else:
                issues.append(
                    _make_issue(
                        sid,
                        "time_of_day",
                        f"Scene {sid} is missing time_of_day.",
                        severity="major",
                        risk="Lighting setup in Steps 06, 11, and 12 will be arbitrary.",
                        fixed=False,
                        ambiguous=True,
                    )
                )
        if not summary:
            issues.append(
                _make_issue(
                    sid,
                    "summary",
                    f"Scene {sid} has an empty summary.",
                    severity="critical",
                    risk="Screenwriter has no beat action to adapt.",
                    fixed=False,
                    ambiguous=True,
                )
            )

    # AI scene-by-scene / beat-by-beat continuity check
    compact_scenes = [
        {
            "id": str(s.get("id") or ""),
            "title": str(s.get("title") or ""),
            "location": str(s.get("location") or ""),
            "time_of_day": str(s.get("time_of_day") or ""),
            "characters": list(s.get("characters") or []),
            "summary": str(s.get("summary") or "")[:360],
        }
        for s in scenes
    ]
    engine = "deterministic"
    prompt = (
        "You are a Continuity Script Supervisor auditing Step 05 (Scene Breakdown / Beats) BEFORE the screenplay is written.\n"
        "Inspect consecutive scenes beat-by-beat for:\n"
        "1. Unexplained location teleports or inconsistent room names for the same place (normalize room names cleanly).\n"
        "2. Abrupt time-of-day contradictions between immediately consecutive scenes.\n"
        "3. Characters appearing/disappearing without entrance/exit, or major props appearing in one beat and vanishing in the next.\n"
        + _AUDITOR_RULES_BLOCK
        + "Return ONLY valid JSON:\n"
        '{"fixes": [{"scene": "S002", "field": "location|time_of_day|summary", "severity": "critical|major|minor", '
        '"issue": "brief explanation", "risk": "downstream impact", "ambiguous": false, "value": "corrected text (empty if ambiguous)"}], '
        '"blind_spots": ["optional missing context"]}\n'
        "Only include real continuity issues. If consistent, return {\"fixes\": [], \"blind_spots\": []}.\n\n"
        f"SCENES:\n{json.dumps(compact_scenes, ensure_ascii=False)[:16000]}"
    )
    ai_data, eng = _call_ai_json(prompt, use_llm=use_llm)
    if eng:
        engine = eng
    raw_fixes = ai_data.get("fixes") if isinstance(ai_data, dict) else []
    if isinstance(raw_fixes, list):
        by_id = {str(s.get("id") or "").upper(): s for s in scenes}
        for fx in raw_fixes:
            if not isinstance(fx, dict) or not str(fx.get("issue") or "").strip():
                continue
            sid = str(fx.get("scene") or "").strip().upper()
            field = str(fx.get("field") or "").strip().lower()
            val = str(fx.get("value") or "").strip()
            is_amb = bool(fx.get("ambiguous") or fx.get("needs_user_decision"))
            fixed = False
            sc_obj = by_id.get(sid)
            if auto_apply and not is_amb and sc_obj is not None and field in ("location", "time_of_day", "summary") and val:
                if str(sc_obj.get(field) or "").strip() != val:
                    sc_obj[field] = val[:500]
                    fixed = True
                    changed = True
                    fixes_applied += 1
            issues.append(
                _make_issue(
                    sid or "beats",
                    field,
                    str(fx["issue"]).strip(),
                    severity=_norm_severity(fx.get("severity"), "major"),
                    risk=str(fx.get("risk") or "Screenplay inherits broken location or beat continuity.").strip(),
                    fixed=fixed,
                    ambiguous=is_amb,
                )
            )
    if isinstance(ai_data, dict) and isinstance(ai_data.get("blind_spots"), list):
        blind_spots.extend(str(x) for x in ai_data["blind_spots"])
    if engine == "deterministic":
        blind_spots.append("Offline deterministic check only — AI beat-to-beat continuity audit did not run.")

    if changed and auto_apply:
        try:
            ad.save(pd, plan)
        except Exception:
            _write_json(ad.adapt_dir(pd) / "adaptation.json", plan)
        if record_bidirectional:
            _record_sync_if_needed(pd, slug, 5, f"Early prompt audit fixed {fixes_applied} beat/scene continuity issue(s)")

    sorted_issues = _sort_issues(issues)
    amb_count = sum(1 for it in sorted_issues if it.get("ambiguous"))
    scorecard = _build_scorecard(
        [
            ("Location Continuity", ("location", "room", "teleport"), "Scene locations are named consistently."),
            ("Time-of-Day Flow", ("time_of_day", "lighting", "day", "night"), "Time-of-day progresses cleanly across scenes."),
            ("Cast & Beat Momentum", ("summary", "character", "prop", "beat"), "Cast presence and beat progression flow cleanly."),
        ],
        sorted_issues,
    )
    return {
        "ok": True,
        "step": 5,
        "label": STEP_LABELS[5],
        "engine": engine,
        "issues_count": len(sorted_issues),
        "fixes_applied": fixes_applied,
        "ambiguous_count": amb_count,
        "scorecard": scorecard,
        "blind_spots": _dedupe_blind_spots(blind_spots),
        "issues": sorted_issues,
        "message": (
            f"Step 05 Beats audited ({engine}): {len(sorted_issues)} issue(s), {fixes_applied} auto-fixed"
            + (f", {amb_count} need decision." if amb_count else ".")
            if sorted_issues
            else f"Step 05 Beats clean ({engine}) — scene locations, timing & cast flow consistently."
        ),
    }


# ==============================================================================
# STEP 06: SCREENPLAY (BEAT-BY-BEAT & LINE-BY-LINE)
# ==============================================================================
def _deterministic_screenplay_scene_audit(
    sid: str,
    sc: dict[str, Any],
    *,
    auto_apply: bool,
) -> tuple[list[dict[str, Any]], bool]:
    issues: list[dict[str, Any]] = []
    changed = False
    raw_elements = sc.get("elements")
    elements: list[Any] = raw_elements if isinstance(raw_elements, list) else []
    heading = str(sc.get("heading") or "")
    heading_low = heading.lower()

    action_blob = " ".join(str(e.get("text") or "") for e in elements if isinstance(e, dict) and e.get("type") == "action").lower()
    has_bare_hook = any(p in action_blob for p in ("bare hook", "empty hook", "empty coat hook", "bare coat hook"))

    for idx, el in enumerate(elements):
        if not isinstance(el, dict) or el.get("type") != "action":
            continue
        txt = str(el.get("text") or "")
        low = txt.lower()

        # 1. Self-contradiction: coat hanging on an explicitly bare/empty hook in the same scene
        if has_bare_hook and re.search(r"with\s+(?:the|a)\s+[^,.]*\bcoat\s+hanging\s+on\s+it", txt, re.IGNORECASE):
            fixed = False
            if auto_apply:
                new_txt = re.sub(
                    r",?\s*with\s+(?:the|a)\s+[^,.]*\bcoat\s+hanging\s+on\s+it",
                    ", completely bare and empty",
                    txt,
                    flags=re.IGNORECASE,
                )
                if new_txt != txt:
                    el["text"] = new_txt
                    txt = new_txt
                    fixed = True
                    changed = True
            issues.append(
                _make_issue(
                    f"{sid} line {idx + 1}",
                    "action",
                    "Action line contradicted an explicitly bare/empty coat hook in the same scene.",
                    severity="critical",
                    risk="Step 12 shots and Step 17 keyframes will render conflicting coat/empty-hook states.",
                    fixed=fixed,
                )
            )

        # 2. Room-boundary leak: kitchen dog bowl inside living room action (ambiguous: user decides if moved or at threshold)
        if "living room" in heading_low and "kitchen" not in heading_low:
            if re.search(r"\b(?:dog\s+bowl|food\s+bowl|water\s+bowl)\b", low) and "kitchen" not in low:
                issues.append(
                    _make_issue(
                        f"{sid} line {idx + 1}",
                        "action",
                        "Dog/food bowl mentioned inside LIVING ROOM without placing it at the kitchen threshold.",
                        severity="major",
                        risk="Room-specific prop drifts onto the living room rug and changes size across keyframes.",
                        fixed=False,
                        ambiguous=True,
                    )
                )

        # 3. Scale exaggeration in action text ("fills the frame" on a dog or child)
        if re.search(r"\bfills\s+the\s+frame\b", low) and any(w in low for w in (_DOG_WORDS + _CHILD_WORDS)):
            fixed = False
            if auto_apply:
                new_txt = re.sub(r"\bfills\s+the\s+frame\b", "sits naturally in realistic proportion", txt, flags=re.IGNORECASE)
                if new_txt != txt:
                    el["text"] = new_txt
                    fixed = True
                    changed = True
            issues.append(
                _make_issue(
                    f"{sid} line {idx + 1}",
                    "action",
                    "Replaced scale-distorting 'fills the frame' phrasing for dog/child in screenplay action.",
                    severity="major",
                    risk="Image models render the dog or child larger than nearby adults.",
                    fixed=fixed,
                )
            )

    return issues, changed


def _audit_step6(
    pd: Path,
    slug: str,
    *,
    target_scene: str = "",
    use_llm: bool,
    auto_apply: bool,
    record_bidirectional: bool,
) -> dict[str, Any]:
    import screenplay as sp

    sp_dir = pd / "screenplay"
    scene_files = sorted(sp_dir.glob("scene-*.json")) if sp_dir.is_dir() else []
    if not scene_files:
        return {
            "ok": True,
            "step": 6,
            "label": STEP_LABELS[6],
            "skipped": True,
            "engine": "deterministic",
            "issues_count": 0,
            "fixes_applied": 0,
            "ambiguous_count": 0,
            "scorecard": [],
            "blind_spots": ["No screenplay/scene-*.json files exist yet."],
            "issues": [],
            "message": "No screenplay/scene-*.json files yet — write Screenplay first.",
        }

    scenes_loaded: list[tuple[str, dict[str, Any]]] = []
    for f in scene_files:
        sid = f.stem.removeprefix("scene-")
        if target_scene and sid.upper() != target_scene.strip().upper():
            continue
        sc = _read_json(f)
        if isinstance(sc, dict):
            scenes_loaded.append((sid, sc))

    sets_custom = _read_json(pd / "sets_custom.json")
    sets_map: dict[str, str] = {}
    if isinstance(sets_custom, dict):
        for sk, sv in sets_custom.items():
            if isinstance(sv, dict) and str(sv.get("description") or "").strip():
                sets_map[sk.lower()] = str(sv["description"]).strip()

    all_issues: list[dict[str, Any]] = []
    blind_spots: list[str] = []
    touched_sids: set[str] = set()
    fixes_applied = 0

    for sid, sc in scenes_loaded:
        heading = str(sc.get("heading") or "")
        if not any(k and k in heading.lower() for k in sets_map):
            blind_spots.append(f"{sid} ({heading}): No Step 11 baselined set description yet — furniture surfaces could not be visually verified.")
        det_issues, det_changed = _deterministic_screenplay_scene_audit(sid, sc, auto_apply=auto_apply)
        all_issues.extend(det_issues)
        if det_changed:
            touched_sids.add(sid)
            fixes_applied += sum(1 for x in det_issues if x.get("fixed"))

    engine = "deterministic"
    if use_llm and scenes_loaded:
        def _audit_one_scene(item: tuple[str, dict[str, Any]]) -> tuple[str, list[dict[str, Any]], list[str], bool, str]:
            sid, sc = item
            heading = str(sc.get("heading") or "")
            set_hint = next((v for k, v in sets_map.items() if k and k in heading.lower()), "")
            raw_els = sc.get("elements")
            els: list[Any] = raw_els if isinstance(raw_els, list) else []
            numbered = [
                {"idx": i, "type": str(e.get("type") or ""), "character": str(e.get("character") or ""), "text": str(e.get("text") or "")}
                for i, e in enumerate(els)
                if isinstance(e, dict)
            ]
            prompt = (
                f"You are a Continuity Script Supervisor auditing Step 06 Screenplay Scene {sid} beat-by-beat BEFORE Continuity Book or Step 12 Shot List are written.\n"
                f"HEADING: {heading}\n"
                + (f"LOCKED SET ARCHITECTURE: {set_hint}\n" if set_hint else "")
                + "Check consecutive action/dialogue elements for:\n"
                "1. Self-contradictions within the scene (e.g., an 'empty/bare hook' later having a coat on it).\n"
                "2. Disappearing/random props (e.g., a box or prop mentioned in one beat and vanishing without explanation) or room-boundary leaks (kitchen dog bowl appearing on living room rug).\n"
                "3. Ungrounded props placed on furniture not present in the room, or scale-distorting language.\n"
                "4. Wardrobe contradictions within the same scene or stiff robotic AI dialogue clichés.\n"
                + _AUDITOR_RULES_BLOCK
                + "Return ONLY valid JSON:\n"
                '{"fixes": [{"idx": 0, "severity": "critical|major|minor", "issue": "brief reason", "risk": "downstream impact", '
                '"ambiguous": false, "text": "surgically corrected element text (empty if ambiguous)"}], "blind_spots": ["optional missing context"]}\n'
                "Keep dialogue natural and intact unless it contradicts visual continuity or contains robotic AI filler. If clean, return {\"fixes\": [], \"blind_spots\": []}.\n\n"
                f"ELEMENTS:\n{json.dumps(numbered, ensure_ascii=False)[:14000]}"
            )
            parsed, eng = _call_ai_json(prompt, use_llm=True)
            sc_issues: list[dict[str, Any]] = []
            sc_bs: list[str] = []
            sc_changed = False
            raw_fx = parsed.get("fixes") if isinstance(parsed, dict) else []
            if isinstance(raw_fx, list):
                for fx in raw_fx:
                    if not isinstance(fx, dict) or not str(fx.get("issue") or "").strip():
                        continue
                    try:
                        idx = int(fx.get("idx", -1))
                    except (TypeError, ValueError):
                        idx = -1
                    new_txt = str(fx.get("text") or "").strip()
                    is_amb = bool(fx.get("ambiguous") or fx.get("needs_user_decision"))
                    fixed = False
                    if auto_apply and not is_amb and 0 <= idx < len(els) and isinstance(els[idx], dict) and new_txt:
                        if str(els[idx].get("text") or "").strip() != new_txt:
                            els[idx]["text"] = new_txt[:1200]
                            fixed = True
                            sc_changed = True
                    sc_issues.append(
                        _make_issue(
                            f"{sid} line {idx + 1}" if idx >= 0 else sid,
                            str(els[idx].get("type") or "action") if 0 <= idx < len(els) and isinstance(els[idx], dict) else "action",
                            str(fx["issue"]).strip(),
                            severity=_norm_severity(fx.get("severity"), "major"),
                            risk=str(fx.get("risk") or "Step 12 shots and Step 17 keyframes will inherit this contradiction.").strip(),
                            fixed=fixed,
                            ambiguous=is_amb,
                        )
                    )
            if isinstance(parsed, dict) and isinstance(parsed.get("blind_spots"), list):
                sc_bs.extend(str(x) for x in parsed["blind_spots"])
            return sid, sc_issues, sc_bs, sc_changed, eng

        if len(scenes_loaded) == 1:
            results = [_audit_one_scene(scenes_loaded[0])]
        else:
            with ThreadPoolExecutor(max_workers=min(4, len(scenes_loaded))) as pool:
                results = list(pool.map(_audit_one_scene, scenes_loaded))

        for sid, sc_issues, sc_bs, sc_changed, eng in results:
            if eng and eng != "deterministic":
                engine = eng
            all_issues.extend(sc_issues)
            blind_spots.extend(sc_bs)
            if sc_changed:
                touched_sids.add(sid)
                fixes_applied += sum(1 for x in sc_issues if x.get("fixed"))

    if engine == "deterministic":
        blind_spots.append("Offline deterministic check only — AI beat-by-beat screenplay review did not run.")

    if touched_sids and auto_apply:
        readin_sp_path = pd / "readin" / "screenplay.json"
        readin_sp = _read_json(readin_sp_path)
        readin_scenes = readin_sp.get("scenes") if isinstance(readin_sp, dict) and isinstance(readin_sp.get("scenes"), list) else []
        readin_changed = False
        for sid, sc in scenes_loaded:
            if sid not in touched_sids:
                continue
            sp.save_scene(pd, sid, {"heading": sc.get("heading", ""), "elements": sc.get("elements", [])}, edited=bool(sc.get("edited")))
            m_num = re.search(r"(\d+)", sid)
            if m_num and readin_scenes:
                idx0 = int(m_num.group(1)) - 1
                if 0 <= idx0 < len(readin_scenes) and isinstance(readin_scenes[idx0], dict):
                    readin_scenes[idx0]["elements"] = sc.get("elements", [])
                    readin_changed = True
        if readin_changed and isinstance(readin_sp, dict):
            _write_json(readin_sp_path, readin_sp)
        if record_bidirectional:
            _record_sync_if_needed(
                pd,
                slug,
                6,
                f"Early prompt audit fixed {fixes_applied} screenplay continuity issue(s) across {', '.join(sorted(touched_sids)[:5])}",
            )

    sorted_issues = _sort_issues(all_issues)
    amb_count = sum(1 for it in sorted_issues if it.get("ambiguous"))
    scorecard = _build_scorecard(
        [
            ("Prop & Object Continuity", ("hook", "coat", "prop", "box", "bowl", "vanish"), "Props stay consistent across consecutive action lines."),
            ("Room & Surface Grounding", ("room", "kitchen", "table", "surface", "furniture", "living"), "Props and action respect room boundaries and furniture."),
            ("Scale & Visual Clarity", ("scale", "proportion", "fills the frame", "wardrobe", "dialogue"), "Action phrasing supports true-to-life proportions and natural dialogue."),
        ],
        sorted_issues,
    )
    return {
        "ok": True,
        "step": 6,
        "label": STEP_LABELS[6],
        "engine": engine,
        "scenes_audited": len(scenes_loaded),
        "issues_count": len(sorted_issues),
        "fixes_applied": fixes_applied,
        "ambiguous_count": amb_count,
        "touched_scenes": sorted(touched_sids),
        "scorecard": scorecard,
        "blind_spots": _dedupe_blind_spots(blind_spots),
        "issues": sorted_issues,
        "message": (
            f"Step 06 Screenplay audited ({engine}, {len(scenes_loaded)} scene(s)): {len(sorted_issues)} issue(s), {fixes_applied} auto-fixed"
            + (f", {amb_count} need decision." if amb_count else ".")
            if sorted_issues
            else f"Step 06 Screenplay clean ({engine}, {len(scenes_loaded)} scene(s)) — beat-by-beat continuity verified."
        ),
    }


# ==============================================================================
# STEP 07: CONTINUITY BOOK (CHARACTER, LOCATION & PROP TOKENS)
# ==============================================================================
def _audit_step7(pd: Path, slug: str, *, use_llm: bool, auto_apply: bool, record_bidirectional: bool) -> dict[str, Any]:
    import continuity_book
    from bookkit import continuity_file

    book = continuity_book.load(pd)
    if not isinstance(book, dict) or not book.get("characters"):
        return {
            "ok": True,
            "step": 7,
            "label": STEP_LABELS[7],
            "skipped": True,
            "engine": "deterministic",
            "issues_count": 0,
            "fixes_applied": 0,
            "ambiguous_count": 0,
            "scorecard": [],
            "blind_spots": ["No Continuity Book exists yet."],
            "issues": [],
            "message": "No Continuity Book yet — build Step 07 Continuity Book first.",
        }

    issues: list[dict[str, Any]] = []
    blind_spots: list[str] = []
    fixes_applied = 0
    changed = False

    # 1. Deterministic token checks: style-neutrality, vague patterns, dog/child/toy scale cues
    for kind in ("characters", "locations", "props"):
        items = book.get(kind)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            tok = str(item.get("token") or "").strip()
            if not name or not tok:
                continue

            bad_style = _STYLE_BUZZ_RE.findall(tok)
            if bad_style:
                fixed = False
                if auto_apply:
                    cleaned = re.sub(r"\s{2,}", " ", _STYLE_BUZZ_RE.sub("", tok)).strip(" ,;:-")
                    if cleaned:
                        item["token"] = cleaned[:250]
                        tok = item["token"]
                        fixed = True
                        changed = True
                        fixes_applied += 1
                issues.append(
                    _make_issue(
                        f"{kind[:-1]}:{name}",
                        "token",
                        f"Removed rendering style word(s) ({', '.join(sorted({w.lower() for w in bad_style}))}) from style-neutral token.",
                        severity="major",
                        risk="Hard-coded style words clash with Step 10/11/17 style cards.",
                        fixed=fixed,
                    )
                )

            pat_m = _VAGUE_PATTERN_RE.search(tok) if kind == "characters" else None
            if pat_m:
                issues.append(
                    _make_issue(
                        f"character:{name}",
                        "token",
                        f"Character '{name}' uses vague clothing pattern ({pat_m.group(0)}); pick a specific solid color for frame-to-frame consistency.",
                        severity="major",
                        risk="Image models randomize stripe count and pattern layout on every keyframe.",
                        fixed=False,
                        ambiguous=True,
                    )
                )

            if kind == "characters":
                low = tok.lower()
                if any(w in low for w in _DOG_WORDS) and not any(h in low for h in ("knee-high", "2 ft", "shoulder", "medium-sized", "medium sized")):
                    fixed = False
                    if auto_apply and len(tok) + 42 <= 255:
                        item["token"] = f"{tok.rstrip('. ')}; ~2 ft at shoulder, knee-high to an adult"
                        tok = item["token"]
                        fixed = True
                        changed = True
                        fixes_applied += 1
                    issues.append(
                        _make_issue(
                            f"character:{name}",
                            "token",
                            f"Added explicit relative height cue (~2 ft at shoulder, knee-high to an adult) to dog character '{name}'.",
                            severity="major",
                            risk="Without a relative height anchor, dogs frequently render oversized next to humans.",
                            fixed=fixed,
                        )
                    )
                elif any(w in low for w in _CHILD_WORDS) and not any(h in low for h in ("waist-high", "3'", "3 ft", "short child", "young child")):
                    fixed = False
                    if auto_apply and len(tok) + 34 <= 255:
                        item["token"] = f"{tok.rstrip('. ')}; ~3'6\" tall, waist-high to an adult"
                        tok = item["token"]
                        fixed = True
                        changed = True
                        fixes_applied += 1
                    issues.append(
                        _make_issue(
                            f"character:{name}",
                            "token",
                            f"Added explicit relative height cue (~3'6\" tall, waist-high to an adult) to child character '{name}'.",
                            severity="major",
                            risk="Without a relative height anchor, young children often render adult-sized.",
                            fixed=fixed,
                        )
                    )

    sets_custom = _read_json(pd / "sets_custom.json") or {}
    set_notes = {
        k: str(v.get("description") or "")[:300]
        for k, v in (sets_custom.items() if isinstance(sets_custom, dict) else [])
        if isinstance(v, dict) and str(v.get("description") or "").strip()
    }
    if not set_notes:
        blind_spots.append("No Step 11 baselined set descriptions exist yet — location tokens could not be cross-checked against imported photos.")

    engine = "deterministic"
    prompt = (
        "You are a Continuity Script Supervisor & Production Designer auditing Step 07 (Continuity Book) BEFORE cast portraits, sets, and Step 12 shots are built.\n"
        "Audit every character, location, and prop token:\n"
        "1. CHARACTERS: must state species, age, relative size vs adults (~5'4\"-5'10\" adult, ~3'6\" waist-high child, ~2 ft knee-high dog, ~12-in toy), and a SINGULAR SOLID-COLOR wardrobe (no vague stripes/patterns, no rendering style words like 3D/Pixar/photorealistic).\n"
        "2. LOCATIONS: must state concrete architectural features & real furniture surfaces (aligned with any LOCKED SET DESCRIPTIONS below).\n"
        "3. PROPS: must state realistic physical size (e.g., ~4-inch mug, ~8-inch dog bowl) and home room so props never teleport rooms or change size.\n"
        "Every replacement token MUST be style-neutral and under 220 characters.\n"
        + _AUDITOR_RULES_BLOCK
        + "Return ONLY valid JSON:\n"
        '{"fixes": [{"kind": "characters|locations|props", "name": "exact name", "severity": "critical|major|minor", '
        '"issue": "brief reason", "risk": "downstream impact", "ambiguous": false, "token": "corrected style-neutral token under 220 chars (empty if ambiguous)"}], '
        '"blind_spots": ["optional missing context"]}\n'
        "If all tokens are already rock-solid, return {\"fixes\": [], \"blind_spots\": []}.\n\n"
        + (f"LOCKED SET DESCRIPTIONS (Step 11):\n{json.dumps(set_notes, ensure_ascii=False)}\n\n" if set_notes else "")
        + f"CONTINUITY BOOK:\n{json.dumps({'characters': book.get('characters', []), 'locations': book.get('locations', []), 'props': book.get('props', [])}, ensure_ascii=False)[:14000]}"
    )
    ai_data, eng = _call_ai_json(prompt, use_llm=use_llm)
    if eng:
        engine = eng
    raw_fx = ai_data.get("fixes") if isinstance(ai_data, dict) else []
    if isinstance(raw_fx, list):
        for fx in raw_fx:
            if not isinstance(fx, dict) or not str(fx.get("issue") or "").strip():
                continue
            kind = str(fx.get("kind") or "").strip().lower()
            name = str(fx.get("name") or "").strip()
            new_tok = re.sub(r"\s{2,}", " ", _STYLE_BUZZ_RE.sub("", str(fx.get("token") or ""))).strip(" ,;:-")[:240]
            is_amb = bool(fx.get("ambiguous") or fx.get("needs_user_decision"))
            fixed = False
            if auto_apply and not is_amb and kind in ("characters", "locations", "props") and name and new_tok:
                items = book.get(kind)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and str(item.get("name") or "").strip().lower() == name.lower():
                            if str(item.get("token") or "").strip() != new_tok:
                                item["token"] = new_tok
                                fixed = True
                                changed = True
                                fixes_applied += 1
                            break
            issues.append(
                _make_issue(
                    f"{kind[:-1] if kind.endswith('s') else kind}:{name}",
                    "token",
                    str(fx["issue"]).strip(),
                    severity=_norm_severity(fx.get("severity"), "major"),
                    risk=str(fx.get("risk") or "Inconsistent character/set/prop tokens propagate into Steps 10, 11, 12, and 17.").strip(),
                    fixed=fixed,
                    ambiguous=is_amb,
                )
            )
    if isinstance(ai_data, dict) and isinstance(ai_data.get("blind_spots"), list):
        blind_spots.extend(str(x) for x in ai_data["blind_spots"])
    if engine == "deterministic":
        blind_spots.append("Offline deterministic check only — AI token semantic review did not run.")

    if changed and auto_apply:
        _write_json(continuity_file(pd), book)
        if record_bidirectional:
            _record_sync_if_needed(pd, slug, 7, f"Early prompt audit fixed {fixes_applied} continuity book token(s)")

    sorted_issues = _sort_issues(issues)
    amb_count = sum(1 for it in sorted_issues if it.get("ambiguous"))
    scorecard = _build_scorecard(
        [
            ("Style Neutrality", ("style word", "rendering", "pixar", "3d"), "All tokens are style-neutral."),
            ("Wardrobe & Scale Lock", ("character:", "pattern", "striped", "height", "scale", "wardrobe"), "Characters specify solid wardrobe and relative scale."),
            ("Locations & Props", ("location:", "prop:", "furniture", "room"), "Locations and props state concrete surfaces, sizes, and rooms."),
        ],
        sorted_issues,
    )
    return {
        "ok": True,
        "step": 7,
        "label": STEP_LABELS[7],
        "engine": engine,
        "issues_count": len(sorted_issues),
        "fixes_applied": fixes_applied,
        "ambiguous_count": amb_count,
        "scorecard": scorecard,
        "blind_spots": _dedupe_blind_spots(blind_spots),
        "issues": sorted_issues,
        "message": (
            f"Step 07 Continuity Book audited ({engine}): {len(sorted_issues)} issue(s), {fixes_applied} auto-fixed"
            + (f", {amb_count} need decision." if amb_count else ".")
            if sorted_issues
            else f"Step 07 Continuity Book clean ({engine}) — all character, location & prop tokens verified."
        ),
    }


# ==============================================================================
# STEP 12: SHOT LIST (DELEGATES TO FULL SHOT CONTINUITY & SCALE AUDITOR)
# ==============================================================================
def _audit_step12(
    pd: Path,
    slug: str,
    *,
    target_scene: str = "",
    use_llm: bool,
    auto_apply: bool,
    record_bidirectional: bool,
) -> dict[str, Any]:
    from studio_app import shot_continuity_audit

    res = shot_continuity_audit.run_project_shot_continuity_audit(
        pd,
        slug,
        target_scene=target_scene,
        use_llm=use_llm,
        record_bidirectional=record_bidirectional,
    )
    if not res.get("ok"):
        return {
            "ok": True,
            "step": 12,
            "label": STEP_LABELS[12],
            "skipped": True,
            "engine": "deterministic",
            "issues_count": 0,
            "fixes_applied": 0,
            "ambiguous_count": 0,
            "scorecard": [],
            "blind_spots": [str(res.get("error") or "No shot list yet.")],
            "issues": [],
            "message": str(res.get("error") or "No shot list yet."),
        }
    raw_fixes = res.get("fixes")
    fixes: list[Any] = raw_fixes if isinstance(raw_fixes, list) else []
    raw_amb = res.get("ambiguous")
    ambiguous_list: list[Any] = raw_amb if isinstance(raw_amb, list) else []
    issues: list[dict[str, Any]] = [
        _make_issue(
            str(fx.get("shot") or ""),
            str(fx.get("field") or ",".join(fx.get("fields") or [])),
            str(fx.get("issue") or ""),
            severity=_norm_severity(fx.get("severity"), "major"),
            risk=str(fx.get("risk") or "Visual mismatch across consecutive keyframes.").strip(),
            fixed=True,
            ambiguous=False,
        )
        for fx in fixes
        if isinstance(fx, dict)
    ]
    for am in ambiguous_list:
        if isinstance(am, dict):
            issues.append(
                _make_issue(
                    str(am.get("shot") or ""),
                    str(am.get("field") or ""),
                    str(am.get("issue") or ""),
                    severity=_norm_severity(am.get("severity"), "major"),
                    risk=str(am.get("risk") or "Ambiguous shot continuity needs director decision.").strip(),
                    fixed=False,
                    ambiguous=True,
                )
            )
    sorted_issues = _sort_issues(issues)
    amb_count = len(ambiguous_list)
    raw_sc = res.get("scorecard")
    scorecard: list[Any] = raw_sc if isinstance(raw_sc, list) else []
    raw_bs = res.get("blind_spots")
    blind_spots: list[Any] = raw_bs if isinstance(raw_bs, list) else []
    return {
        "ok": True,
        "step": 12,
        "label": STEP_LABELS[12],
        "engine": str(res.get("engine") or "deterministic"),
        "issues_count": len(sorted_issues),
        "fixes_applied": len(fixes),
        "ambiguous_count": amb_count,
        "keyframes_synced": int(res.get("keyframes_updated") or 0),
        "touched_scenes": list(res.get("scenes_updated") or []),
        "scorecard": scorecard,
        "blind_spots": _dedupe_blind_spots([str(x) for x in blind_spots]),
        "issues": sorted_issues,
        "message": (
            f"Step 12 Shot List audited ({res.get('engine', 'deterministic')}): {len(sorted_issues)} issue(s), {len(fixes)} auto-fixed"
            + (f", {amb_count} need decision." if amb_count else ".")
            if sorted_issues
            else f"Step 12 Shot List clean ({res.get('engine', 'deterministic')}) — shot-to-shot continuity & scale verified."
        ),
    }


# ==============================================================================
# PUBLIC ENTRY POINTS
# ==============================================================================
def audit_step(
    pd: Path,
    slug: str,
    step_num: int,
    *,
    target_scene: str = "",
    use_llm: bool = True,
    auto_apply: bool = True,
    record_bidirectional: bool = True,
) -> dict[str, Any]:
    """Run the prompt continuity audit for a single pipeline step (3, 4, 5, 6, 7, or 12) and persist its report."""
    step = int(step_num)
    if step == 3:
        rep = _audit_step3(pd, slug, use_llm=use_llm, auto_apply=auto_apply, record_bidirectional=record_bidirectional)
    elif step == 4:
        rep = _audit_step4(pd, slug, use_llm=use_llm, auto_apply=auto_apply, record_bidirectional=record_bidirectional)
    elif step == 5:
        rep = _audit_step5(pd, slug, use_llm=use_llm, auto_apply=auto_apply, record_bidirectional=record_bidirectional)
    elif step == 6:
        rep = _audit_step6(
            pd,
            slug,
            target_scene=target_scene,
            use_llm=use_llm,
            auto_apply=auto_apply,
            record_bidirectional=record_bidirectional,
        )
    elif step == 7:
        rep = _audit_step7(pd, slug, use_llm=use_llm, auto_apply=auto_apply, record_bidirectional=record_bidirectional)
    elif step == 12:
        rep = _audit_step12(
            pd,
            slug,
            target_scene=target_scene,
            use_llm=use_llm,
            auto_apply=auto_apply,
            record_bidirectional=record_bidirectional,
        )
    else:
        return {"ok": False, "error": f"Unsupported early prompt audit step: {step}. Valid steps: {EARLY_AUDIT_STEPS}."}

    rep["audited_at"] = round(time.time(), 2)
    with contextlib.suppress(OSError):
        save_step_report(pd, step, rep)
    return rep


def audit_all_early_steps(
    pd: Path,
    slug: str,
    *,
    steps: tuple[int, ...] = EARLY_AUDIT_STEPS,
    target_scene: str = "",
    use_llm: bool = True,
    auto_apply: bool = True,
    record_bidirectional: bool = True,
) -> dict[str, Any]:
    """Run early-stage prompt continuity audits in pipeline order (Steps 3 -> 4 -> 5 -> 6 -> 7 -> 12)."""
    per_step: dict[str, dict[str, Any]] = {}
    total_issues = 0
    total_fixes = 0
    total_ambiguous = 0
    for st in steps:
        rep = audit_step(
            pd,
            slug,
            st,
            target_scene=target_scene,
            use_llm=use_llm,
            auto_apply=auto_apply,
            record_bidirectional=record_bidirectional,
        )
        per_step[str(st)] = rep
        total_issues += int(rep.get("issues_count") or 0)
        total_fixes += int(rep.get("fixes_applied") or 0)
        total_ambiguous += int(rep.get("ambiguous_count") or 0)
    return {
        "ok": True,
        "steps": per_step,
        "total_issues": total_issues,
        "total_fixes": total_fixes,
        "total_ambiguous": total_ambiguous,
        "message": (
            f"Audited steps {', '.join(str(s) for s in steps)}: "
            f"{total_issues} issue(s), {total_fixes} auto-fixed"
            + (f", {total_ambiguous} need user decision." if total_ambiguous else ".")
        ),
    }
