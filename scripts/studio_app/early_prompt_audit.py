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
    scene_id: str = "",
    line_index: int = -1,
    element_type: str = "",
    character: str = "",
    current_text: str = "",
    highlight: str = "",
    options: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "target": str(target or "").strip(),
        "field": str(field or "").strip(),
        "severity": _norm_severity(severity, "major"),
        "risk": str(risk or "").strip(),
        "issue": str(issue or "").strip(),
        "fixed": bool(fixed) and not bool(ambiguous),
        "ambiguous": bool(ambiguous),
        "needs_user_decision": bool(ambiguous),
    }
    if scene_id:
        item["scene_id"] = str(scene_id).strip()
    if line_index >= 0:
        item["line_index"] = int(line_index)
    if element_type:
        item["element_type"] = str(element_type).strip()
    if character:
        item["character"] = str(character).strip()
    if current_text:
        item["current_text"] = str(current_text)
    if highlight:
        item["highlight"] = str(highlight)
    clean_opts: list[dict[str, str]] = []
    if isinstance(options, list):
        for opt in options:
            if not isinstance(opt, dict):
                continue
            lbl = str(opt.get("label") or "").strip()
            rep = str(opt.get("replacement_text") or opt.get("text") or opt.get("value") or "").strip()
            summ = str(opt.get("summary") or opt.get("description") or "").strip()
            if lbl and (rep or opt.get("keep_original")):
                clean_opts.append({
                    "label": lbl,
                    "summary": summ,
                    "replacement_text": rep,
                })
    if ambiguous and not clean_opts and current_text:
        clean_opts = _fallback_conflict_options(current_text, highlight, issue)
    if clean_opts:
        item["options"] = clean_opts
    return item


def _fallback_conflict_options(current_text: str, highlight: str, issue: str) -> list[dict[str, str]]:
    """Build concrete starter conflict options when an AI flags ambiguity without explicit options."""
    cur = str(current_text or "").strip()
    hl = str(highlight or "").strip()
    opts: list[dict[str, str]] = []
    if hl and hl.lower() in cur.lower():
        removed = re.sub(re.escape(hl), "", cur, count=1, flags=re.IGNORECASE)
        removed = re.sub(r"\s{2,}", " ", removed).replace(" ,", ",").replace(" .", ".").strip(" ,;-")
        if removed and removed != cur:
            opts.append({
                "label": f"Remove conflicting phrase ('{hl[:36]}')",
                "summary": "Drops the conflicting detail from this line so downstream shots stay consistent.",
                "replacement_text": removed,
            })
    opts.append({
        "label": "Clarify & anchor in scene (edit below)",
        "summary": f"Revise this line directly to resolve: {issue[:120]}",
        "replacement_text": cur,
    })
    return opts


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
                    ambiguous=True,
                    character=name,
                    current_text=desc or f"{name} (no description)",
                    highlight=desc or name,
                    options=[
                        {
                            "label": f"Specify adult human scale & look for {name}",
                            "summary": "Locks species, approximate age, adult height (~5'6\"-5'10\"), and key visual traits.",
                            "replacement_text": f"{desc or name} — adult human (~5'7\" tall), everyday attire, distinctive facial features and hair",
                        },
                        {
                            "label": f"Specify young child scale & look for {name}",
                            "summary": "Locks child age and waist-high height (~3'6\") so downstream shots keep accurate proportions.",
                            "replacement_text": f"{desc or name} — young child (~3'6\" tall, waist-high to adults), expressive face, solid-color casual outfit",
                        },
                        {
                            "label": f"Specify animal / pet scale & breed for {name}",
                            "summary": "Locks species, breed/coloring, and knee-high (~2 ft at shoulder) relative scale.",
                            "replacement_text": f"{desc or name} — friendly pet (~2 ft tall at shoulder, knee-high to adults), distinct coat color",
                        },
                    ],
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
        + "When '\"ambiguous\": true', ALSO include 'highlight' (verbatim offending substring from the current field) and "
        "'options' (2-3 concrete conflicting choices [{\"label\": \"Option A\", \"summary\": \"...\", \"replacement_text\": \"...\"}]).\n"
        + "Return ONLY valid JSON:\n"
        '{"issues": [{"target": "character name or key_events", "field": "description|logline|key_events", '
        '"severity": "critical|major|minor", "issue": "brief explanation", "risk": "downstream impact", "ambiguous": false, '
        '"highlight": "exact offending phrase if ambiguous", '
        '"options": [{"label": "Option A", "summary": "...", "replacement_text": "..."}], '
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
            cur_val = ""
            if field == "logline":
                cur_val = str(cov.get("logline") or "")
            elif field == "key_events" and isinstance(cov.get("key_events"), list):
                cur_val = "\n".join(str(x) for x in cov["key_events"])
            elif field == "description" and target:
                for c in chars:
                    if isinstance(c, dict) and str(c.get("name") or "").strip().lower() == target.lower():
                        cur_val = str(c.get("description") or "")
                        break
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
            raw_opts = item.get("options") if isinstance(item.get("options"), list) else None
            issues.append(
                _make_issue(
                    target or field,
                    field,
                    str(item["issue"]).strip(),
                    severity=_norm_severity(item.get("severity"), "major"),
                    risk=str(item.get("risk") or "Downstream beats and character tokens inherit coverage ambiguity.").strip(),
                    fixed=fixed,
                    ambiguous=is_amb,
                    character=target if field == "description" else "",
                    current_text=cur_val,
                    highlight=str(item.get("highlight") or "").strip(),
                    options=raw_opts,
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
        rec_min = round(min(180.0, max(target_min * 2.0, n_chapters * 0.6)), 1)
        mid_min = round(min(180.0, max(target_min * 1.5, n_chapters * 0.45)), 1)
        issues.append(
            _make_issue(
                "target_minutes",
                "target_minutes",
                f"Target runtime ({target_min:g} min) is tight for {n_chapters} chapters ({total_words:,} words); scenes may become overcrowded and cause abrupt prop/location jumps.",
                severity="major",
                risk="Compressing too many chapters into too few minutes causes teleporting locations and rushed transitions.",
                fixed=False,
                ambiguous=True,
                current_text=f"target_minutes: {target_min:g} (across {n_chapters} chapters / {total_words:,} words)",
                highlight=f"{target_min:g}",
                options=[
                    {
                        "label": f"Expand target runtime to {rec_min:g} min (Recommended)",
                        "summary": "Gives each chapter enough breathing room for smooth transitions and grounded sets.",
                        "replacement_text": f"{rec_min:g}",
                    },
                    {
                        "label": f"Moderate condensed runtime ({mid_min:g} min)",
                        "summary": "Balances tighter pacing while avoiding abrupt room-to-room cuts.",
                        "replacement_text": f"{mid_min:g}",
                    },
                    {
                        "label": f"Keep short highlight cut ({target_min:g} min)",
                        "summary": "Intentionally trims minor chapters to stay within your tight target duration.",
                        "replacement_text": f"{target_min:g}",
                    },
                ],
            )
        )
    if total_words > 0 and total_words < 1500 and target_min > 45:
        rec_short = round(max(3.0, min(20.0, total_words / 120.0)), 1)
        issues.append(
            _make_issue(
                "target_minutes",
                "target_minutes",
                f"Target runtime ({target_min:g} min) is very long for {total_words:,} source words; heavy invention may introduce ungrounded settings or props.",
                severity="major",
                risk="Over-expanding thin source text increases hallucinated sets and props downstream.",
                fixed=False,
                ambiguous=True,
                current_text=f"target_minutes: {target_min:g} (for {total_words:,} source words)",
                highlight=f"{target_min:g}",
                options=[
                    {
                        "label": f"Right-size runtime to {rec_short:g} min (Recommended)",
                        "summary": "Matches runtime tightly to the source word count to prevent invented filler.",
                        "replacement_text": f"{rec_short:g}",
                    },
                    {
                        "label": "Use medium expanded cut (25 min)",
                        "summary": "Allows moderate visual expansion while limiting hallucinated subplots.",
                        "replacement_text": "25",
                    },
                ],
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
                ambiguous=True,
                current_text=f"aspect: {aspect or '(blank)'}",
                highlight=aspect or "(blank)",
                options=[
                    {"label": "Standard Widescreen 16:9 (Recommended)", "summary": "Best compatibility across YouTube, TV, and storyboard generators.", "replacement_text": "16:9"},
                    {"label": "Vertical 9:16 (Shorts / Reels)", "summary": "Portrait framing for mobile-first vertical cinema.", "replacement_text": "9:16"},
                    {"label": "Classic 4:3", "summary": "Traditional animated / storybook framing.", "replacement_text": "4:3"},
                ],
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
            + "When '\"ambiguous\": true', include 'highlight' (offending value) and 'options' (2-3 choices with replacement_text set to the clean new setting value).\n"
            + 'Return ONLY valid JSON: {"issues": [{"target": "target_minutes|rating|aspect|faithfulness", "severity": "critical|major|minor", "issue": "...", "risk": "...", "ambiguous": false, "highlight": "...", "options": [{"label": "...", "summary": "...", "replacement_text": "..."}]}], "blind_spots": ["..."]}\n'
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
                    tgt = str(item.get("target") or "scope").strip()
                    cur_s = str(settings.get(tgt, "")) if tgt in settings else ""
                    raw_opts = item.get("options") if isinstance(item.get("options"), list) else None
                    issues.append(
                        _make_issue(
                            tgt,
                            tgt,
                            str(item["issue"]).strip(),
                            severity=_norm_severity(item.get("severity"), "major"),
                            risk=str(item.get("risk") or "Mismatched scope distorts scene pacing.").strip(),
                            fixed=False,
                            ambiguous=bool(item.get("ambiguous") or item.get("needs_user_decision")),
                            current_text=f"{tgt}: {cur_s}" if cur_s else "",
                            highlight=str(item.get("highlight") or cur_s).strip(),
                            options=raw_opts,
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
            prev_loc = str(scenes[i - 1].get("location") or "").strip() if i > 0 else ""
            loc_opts: list[dict[str, str]] = []
            if prev_loc:
                loc_opts.append({
                    "label": f"Continue in previous location: '{prev_loc}'",
                    "summary": "Keeps continuous spatial flow from the preceding scene.",
                    "replacement_text": prev_loc,
                })
            loc_opts.append({
                "label": f"Set new interior location for {sid}",
                "summary": "Assign a concrete interior room name (edit below before applying).",
                "replacement_text": f"living room ({sc.get('title') or sid})",
            })
            issues.append(
                _make_issue(
                    sid,
                    "location",
                    f"Scene {sid} is missing a concrete location.",
                    severity="critical",
                    risk="Screenplay and Step 11 Sets will invent conflicting room names.",
                    fixed=False,
                    ambiguous=True,
                    scene_id=sid,
                    current_text=f"{sid} ({sc.get('title') or 'Untitled'}) — location: (blank)",
                    highlight="(blank)",
                    options=loc_opts,
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
                        scene_id=sid,
                        current_text=f"{sid} ({sc.get('title') or 'Untitled'}) — time_of_day: (blank)",
                        highlight="(blank)",
                        options=[
                            {"label": "Morning daylight", "summary": "Soft natural morning light.", "replacement_text": "morning"},
                            {"label": "Afternoon daylight", "summary": "Warm balanced afternoon light.", "replacement_text": "afternoon"},
                            {"label": "Evening / golden hour", "summary": "Warm practical lamps / dusk lighting.", "replacement_text": "evening"},
                            {"label": "Night", "summary": "Dark exterior with interior practical lighting.", "replacement_text": "night"},
                        ],
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
                    scene_id=sid,
                    current_text=f"{sid} ({sc.get('title') or 'Untitled'}) — summary: (blank)",
                    highlight="(blank)",
                    options=[
                        {
                            "label": f"Draft beat summary from title '{sc.get('title') or sid}'",
                            "summary": "Write the concrete visual action & emotional turn for this scene below.",
                            "replacement_text": f"In {loc or 'the main setting'}, the characters carry out the key beat of '{sc.get('title') or sid}'.",
                        },
                    ],
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
        + "When '\"ambiguous\": true', include 'highlight' (verbatim offending substring) and 'options' (2-3 conflicting choices [{\"label\": \"Option A\", \"summary\": \"...\", \"replacement_text\": \"...\"}]).\n"
        + "Return ONLY valid JSON:\n"
        '{"fixes": [{"scene": "S002", "field": "location|time_of_day|summary", "severity": "critical|major|minor", '
        '"issue": "brief explanation", "risk": "downstream impact", "ambiguous": false, "highlight": "...", '
        '"options": [{"label": "Option A", "summary": "...", "replacement_text": "..."}], '
        '"value": "corrected text (empty if ambiguous)"}], '
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
            cur_val = str(sc_obj.get(field) or "") if (sc_obj is not None and field) else ""
            if auto_apply and not is_amb and sc_obj is not None and field in ("location", "time_of_day", "summary") and val:
                if cur_val.strip() != val:
                    sc_obj[field] = val[:500]
                    fixed = True
                    changed = True
                    fixes_applied += 1
            raw_opts = fx.get("options") if isinstance(fx.get("options"), list) else None
            issues.append(
                _make_issue(
                    sid or "beats",
                    field,
                    str(fx["issue"]).strip(),
                    severity=_norm_severity(fx.get("severity"), "major"),
                    risk=str(fx.get("risk") or "Screenplay inherits broken location or beat continuity.").strip(),
                    fixed=fixed,
                    ambiguous=is_amb,
                    scene_id=sid,
                    current_text=cur_val,
                    highlight=str(fx.get("highlight") or "").strip(),
                    options=raw_opts,
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
            bowl_m = re.search(r"\b(?:dog\s+bowl|food\s+bowl|water\s+bowl)\b", txt, re.IGNORECASE)
            if bowl_m and "kitchen" not in low:
                hl = bowl_m.group(0)
                relocated = re.sub(
                    r"\b(?:on\s+the\s+(?:carpet|rug|living\s+room\s+floor)|in\s+the\s+living\s+room)\b",
                    "at the kitchen doorway threshold",
                    txt,
                    flags=re.IGNORECASE,
                )
                if relocated == txt:
                    relocated = f"{txt.rstrip('. ')} (kept strictly at the kitchen doorway threshold, off the living room rug)."
                removed_clause = re.sub(
                    r",?\s*(?:while|as|with)\s+[^.]*\b(?:dog|food|water)\s+bowl\b[^.]*",
                    "",
                    txt,
                    flags=re.IGNORECASE,
                ).strip(" ,")
                if not removed_clause or removed_clause == txt:
                    removed_clause = re.sub(r"\b(?:his|her|the|a)?\s*(?:dog|food|water)\s+bowl\b", "", txt, flags=re.IGNORECASE)
                    removed_clause = re.sub(r"\s{2,}", " ", removed_clause).strip(" ,")
                if removed_clause and not removed_clause.endswith((".", "!", "?")):
                    removed_clause += "."
                explicit_moved = f"{txt.rstrip('. ')}, intentionally carried out from the kitchen earlier and kept in the same spot."
                issues.append(
                    _make_issue(
                        f"{sid} line {idx + 1}",
                        "action",
                        "Dog/food bowl mentioned inside LIVING ROOM without placing it at the kitchen threshold.",
                        severity="major",
                        risk="Room-specific prop drifts onto the living room rug and changes size across keyframes.",
                        fixed=False,
                        ambiguous=True,
                        scene_id=sid,
                        line_index=idx,
                        element_type="action",
                        current_text=txt,
                        highlight=hl,
                        options=[
                            {
                                "label": "Keep bowl at kitchen doorway threshold (Recommended)",
                                "summary": "Keeps the dog bowl grounded in its proper kitchen/threshold home instead of the living room rug.",
                                "replacement_text": relocated,
                            },
                            {
                                "label": "Remove bowl from this living room line",
                                "summary": "Omits the kitchen bowl from the living room beat so it never teleports between rooms.",
                                "replacement_text": removed_clause,
                            },
                            {
                                "label": "Keep bowl in living room & establish explicitly",
                                "summary": "Locks an explicit continuity note that the bowl was intentionally brought into the living room.",
                                "replacement_text": explicit_moved,
                            },
                        ],
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
                + "When '\"ambiguous\": true', you MUST ALSO include:\n"
                "  - 'highlight': exact short substring copied verbatim from that element's text showing the conflicting phrase\n"
                "  - 'options': 2-3 concrete conflicting choices [{\"label\": \"Option A\", \"summary\": \"why/tradeoff\", \"replacement_text\": \"full rewritten line\"}]\n"
                "Return ONLY valid JSON:\n"
                '{"fixes": [{"idx": 0, "severity": "critical|major|minor", "issue": "brief reason", "risk": "downstream impact", '
                '"ambiguous": false, "highlight": "exact offending phrase", '
                '"options": [{"label": "Option A", "summary": "...", "replacement_text": "..."}], '
                '"text": "surgically corrected element text (empty if ambiguous)"}], "blind_spots": ["optional missing context"]}\n'
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
                    cur_el = els[idx] if (0 <= idx < len(els) and isinstance(els[idx], dict)) else {}
                    cur_txt = str(cur_el.get("text") or "")
                    el_type = str(cur_el.get("type") or "action")
                    el_char = str(cur_el.get("character") or "")
                    fixed = False
                    if auto_apply and not is_amb and 0 <= idx < len(els) and isinstance(els[idx], dict) and new_txt:
                        if cur_txt.strip() != new_txt:
                            els[idx]["text"] = new_txt[:1200]
                            fixed = True
                            sc_changed = True
                    raw_opts = fx.get("options") if isinstance(fx.get("options"), list) else None
                    sc_issues.append(
                        _make_issue(
                            f"{sid} line {idx + 1}" if idx >= 0 else sid,
                            el_type,
                            str(fx["issue"]).strip(),
                            severity=_norm_severity(fx.get("severity"), "major"),
                            risk=str(fx.get("risk") or "Step 12 shots and Step 17 keyframes will inherit this contradiction.").strip(),
                            fixed=fixed,
                            ambiguous=is_amb,
                            scene_id=sid,
                            line_index=idx,
                            element_type=el_type,
                            character=el_char,
                            current_text=cur_txt,
                            highlight=str(fx.get("highlight") or "").strip(),
                            options=raw_opts,
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
                solid_tok = re.sub(_VAGUE_PATTERN_RE, "solid", tok, count=1)
                issues.append(
                    _make_issue(
                        f"character:{name}",
                        "token",
                        f"Character '{name}' uses vague clothing pattern ({pat_m.group(0)}); pick a specific solid color for frame-to-frame consistency.",
                        severity="major",
                        risk="Image models randomize stripe count and pattern layout on every keyframe.",
                        fixed=False,
                        ambiguous=True,
                        current_text=tok,
                        highlight=pat_m.group(0),
                        options=[
                            {
                                "label": f"Switch '{pat_m.group(0)}' to solid color (Recommended)",
                                "summary": "Locks a single solid garment color so every keyframe matches cleanly.",
                                "replacement_text": solid_tok,
                            },
                            {
                                "label": "Keep exact patterned wording",
                                "summary": "Keeps the current pattern token as written.",
                                "replacement_text": tok,
                            },
                        ],
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
        + "When '\"ambiguous\": true', include 'highlight' (verbatim offending substring from the token) and 'options' (2-3 concrete style-neutral choices under 220 chars).\n"
        + "Return ONLY valid JSON:\n"
        '{"fixes": [{"kind": "characters|locations|props", "name": "exact name", "severity": "critical|major|minor", '
        '"issue": "brief reason", "risk": "downstream impact", "ambiguous": false, "highlight": "...", '
        '"options": [{"label": "Option A", "summary": "...", "replacement_text": "..."}], '
        '"token": "corrected style-neutral token under 220 chars (empty if ambiguous)"}], '
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
            cur_tok = ""
            matched_item: dict[str, Any] | None = None
            if kind in ("characters", "locations", "props") and name:
                items = book.get(kind)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and str(item.get("name") or "").strip().lower() == name.lower():
                            matched_item = item
                            cur_tok = str(item.get("token") or "")
                            break
            fixed = False
            if auto_apply and not is_amb and matched_item is not None and new_tok:
                if cur_tok.strip() != new_tok:
                    matched_item["token"] = new_tok
                    fixed = True
                    changed = True
                    fixes_applied += 1
            raw_opts = fx.get("options") if isinstance(fx.get("options"), list) else None
            issues.append(
                _make_issue(
                    f"{kind[:-1] if kind.endswith('s') else kind}:{name}",
                    "token",
                    str(fx["issue"]).strip(),
                    severity=_norm_severity(fx.get("severity"), "major"),
                    risk=str(fx.get("risk") or "Inconsistent character/set/prop tokens propagate into Steps 10, 11, 12, and 17.").strip(),
                    fixed=fixed,
                    ambiguous=is_amb,
                    character=name if kind == "characters" else "",
                    current_text=cur_tok,
                    highlight=str(fx.get("highlight") or "").strip(),
                    options=raw_opts,
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
def format_shot_audit_report(res: dict[str, Any]) -> dict[str, Any]:
    """Normalize a `shot_continuity_audit.run_project_shot_continuity_audit` result into a standard Step 12 report."""
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
            shot_lbl = str(am.get("shot") or "")
            sc_id = str(am.get("scene_id") or "").strip()
            shot_n = int(am.get("shot_n") or 0)
            if (not sc_id or shot_n <= 0) and shot_lbl:
                m_sh = re.match(r"^(S\d+)-(\d+)$", shot_lbl.strip(), re.IGNORECASE)
                if m_sh:
                    sc_id = sc_id or m_sh.group(1).upper()
                    shot_n = shot_n or int(m_sh.group(2))
            fld = str(am.get("field") or (am.get("fields") or ["composition"])[0] or "composition").strip()
            raw_opts = am.get("options") if isinstance(am.get("options"), list) else None
            issues.append(
                _make_issue(
                    shot_lbl,
                    fld,
                    str(am.get("issue") or ""),
                    severity=_norm_severity(am.get("severity"), "major"),
                    risk=str(am.get("risk") or "Ambiguous shot continuity needs director decision.").strip(),
                    fixed=False,
                    ambiguous=True,
                    scene_id=sc_id,
                    line_index=max(-1, shot_n - 1) if shot_n > 0 else -1,
                    element_type=fld,
                    current_text=str(am.get("current_text") or ""),
                    highlight=str(am.get("highlight") or "").strip(),
                    options=raw_opts,
                )
            )
    sorted_issues = _sort_issues(issues)
    amb_count = sum(1 for it in sorted_issues if it.get("ambiguous"))
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
    return format_shot_audit_report(res)


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


def resolve_audit_decision(
    pd: Path,
    slug: str,
    *,
    step_num: int,
    target: str = "",
    scene_id: str = "",
    line_index: int = -1,
    field: str = "",
    issue_text: str = "",
    replacement_text: str = "",
    keep_original: bool = False,
    option_label: str = "",
    record_bidirectional: bool = True,
) -> dict[str, Any]:
    """Apply a user's resolution for a `[Needs Decision]` audit finding directly to the source artifact and update saved audit reports."""
    step = int(step_num)
    if step == 17:
        step = 12
    new_txt = str(replacement_text or "").strip()
    applied_file = ""

    if not keep_original:
        if step == 3:
            cov_path = pd / "readin" / "coverage.json"
            cov = _read_json(cov_path)
            if not isinstance(cov, dict):
                return {"ok": False, "error": "readin/coverage.json not found."}
            if not new_txt:
                return {"ok": False, "error": "replacement_text cannot be empty unless keep_original=True."}
            fld = (field or "description").strip().lower()
            if fld == "logline":
                cov["logline"] = new_txt[:500]
            elif fld == "key_events":
                cov["key_events"] = [ln.strip("•- \t") for ln in new_txt.splitlines() if ln.strip()]
            else:
                chars = cov.get("characters")
                if not isinstance(chars, list):
                    return {"ok": False, "error": "No characters list found in coverage.json."}
                updated_char = False
                for c in chars:
                    if isinstance(c, dict) and str(c.get("name") or "").strip().lower() == target.strip().lower():
                        c["description"] = new_txt[:400]
                        updated_char = True
                        break
                if not updated_char:
                    return {"ok": False, "error": f"Character '{target}' not found in coverage.json."}
            _write_json(cov_path, cov)
            applied_file = "readin/coverage.json"
            if record_bidirectional:
                _record_sync_if_needed(pd, slug, 3, f"User resolved Step 03 coverage decision for {target or fld}")
        elif step == 4:
            import production

            settings = dict(production.load(pd) or {})
            fld = (field or target or "target_minutes").strip().lower()
            if not new_txt:
                return {"ok": False, "error": "replacement_text cannot be empty unless keep_original=True."}
            if fld == "target_minutes":
                m_num = re.search(r"\d+(?:\.\d+)?", new_txt)
                if not m_num:
                    return {"ok": False, "error": "target_minutes must contain a number of minutes."}
                settings["target_minutes"] = round(max(0.5, min(600.0, float(m_num.group(0)))), 1)
            elif fld in ("aspect", "rating", "faithfulness", "tier"):
                clean_v = new_txt.split(":", 1)[-1].strip() if ":" in new_txt and fld != "aspect" else new_txt.strip()
                if fld == "aspect" and clean_v.lower().startswith("aspect:"):
                    clean_v = clean_v.split(":", 1)[1].strip()
                settings[fld] = clean_v
            else:
                settings[fld] = new_txt[:200]
            _write_json(pd / "production.json", settings)
            applied_file = "production.json"
            if record_bidirectional:
                _record_sync_if_needed(pd, slug, 4, f"User resolved Step 04 scope decision for {fld}")
        elif step == 6:
            import screenplay as sp

            sid = str(scene_id or "").strip()
            idx = int(line_index)
            if (not sid or idx < 0) and target:
                m = re.match(r"^(S\d+)\s+line\s+(\d+)$", target.strip(), re.IGNORECASE)
                if m:
                    sid = sid or m.group(1).upper()
                    idx = idx if idx >= 0 else (int(m.group(2)) - 1)
            if not sid:
                return {"ok": False, "error": "scene_id is required to resolve a Step 06 screenplay finding."}
            sc = sp.load_scene(pd, sid)
            if not isinstance(sc, dict):
                return {"ok": False, "error": f"Screenplay scene {sid} not found."}
            raw_els = sc.get("elements")
            els: list[Any] = raw_els if isinstance(raw_els, list) else []
            if not (0 <= idx < len(els) and isinstance(els[idx], dict)):
                return {"ok": False, "error": f"Line {idx + 1} not found in scene {sid}."}
            if not new_txt:
                return {"ok": False, "error": "replacement_text cannot be empty unless keep_original=True."}
            els[idx]["text"] = new_txt[:1200]
            sp.save_scene(pd, sid, {"heading": sc.get("heading", ""), "elements": els}, edited=True)
            applied_file = f"screenplay/scene-{sid}.json"

            # Mirror into readin/screenplay.json if present
            readin_sp_path = pd / "readin" / "screenplay.json"
            readin_sp = _read_json(readin_sp_path)
            if isinstance(readin_sp, dict) and isinstance(readin_sp.get("scenes"), list):
                m_num = re.search(r"(\d+)", sid)
                if m_num:
                    idx0 = int(m_num.group(1)) - 1
                    if 0 <= idx0 < len(readin_sp["scenes"]) and isinstance(readin_sp["scenes"][idx0], dict):
                        readin_sp["scenes"][idx0]["elements"] = els
                        _write_json(readin_sp_path, readin_sp)
            if record_bidirectional:
                _record_sync_if_needed(pd, slug, 6, f"User resolved Step 06 continuity decision in {sid} line {idx + 1}")
        elif step == 7:
            import continuity_book
            from bookkit import continuity_file

            book = continuity_book.load(pd)
            if not isinstance(book, dict):
                return {"ok": False, "error": "Continuity book not found."}
            if ":" in target:
                k_raw, item_name = target.split(":", 1)
                kind_map = {"character": "characters", "location": "locations", "prop": "props"}
                kind = kind_map.get(k_raw.strip().lower(), k_raw.strip().lower())
            else:
                kind, item_name = "characters", target
            items = book.get(kind)
            if not isinstance(items, list):
                return {"ok": False, "error": f"Section '{kind}' not found in continuity book."}
            cleaned = re.sub(r"\s{2,}", " ", _STYLE_BUZZ_RE.sub("", new_txt)).strip(" ,;:-")[:250]
            updated_item = False
            for it in items:
                if isinstance(it, dict) and str(it.get("name") or "").strip().lower() == item_name.strip().lower():
                    it["token"] = cleaned
                    updated_item = True
                    break
            if not updated_item:
                return {"ok": False, "error": f"Item '{item_name}' not found in {kind}."}
            _write_json(continuity_file(pd), book)
            applied_file = continuity_file(pd).name
            if record_bidirectional:
                _record_sync_if_needed(pd, slug, 7, f"User resolved Step 07 continuity decision for {target}")
        elif step == 5:
            import adaptation as ad

            plan = ad.load(pd)
            if not isinstance(plan, dict) or not isinstance(plan.get("scenes"), list):
                return {"ok": False, "error": "Adaptation plan not found."}
            sid = (scene_id or target).strip().upper()
            fld = (field or "summary").strip().lower()
            found_sc = next((s for s in plan["scenes"] if isinstance(s, dict) and str(s.get("id") or "").upper() == sid), None)
            if found_sc is None:
                return {"ok": False, "error": f"Scene {sid} not found in adaptation plan."}
            found_sc[fld] = new_txt[:500]
            try:
                ad.save(pd, plan)
            except Exception:
                _write_json(ad.adapt_dir(pd) / "adaptation.json", plan)
            applied_file = "adaptation/adaptation.json"
            if record_bidirectional:
                _record_sync_if_needed(pd, slug, 5, f"User resolved Step 05 decision in {sid}.{fld}")
        elif step == 12:
            from studio_app import keyframe_context

            sl_path = pd / "shots" / "shotlist.json"
            sl_data = _read_json(sl_path)
            if not isinstance(sl_data, dict) or not isinstance(sl_data.get("scenes"), list):
                return {"ok": False, "error": "shots/shotlist.json not found."}
            if not new_txt:
                return {"ok": False, "error": "replacement_text cannot be empty unless keep_original=True."}
            sid = str(scene_id or "").strip().upper()
            shot_n = int(line_index) + 1 if int(line_index) >= 0 else 0
            if (not sid or shot_n <= 0) and target:
                m_sh = re.match(r"^(S\d+)-(\d+)$", target.strip(), re.IGNORECASE)
                if m_sh:
                    sid = sid or m_sh.group(1).upper()
                    shot_n = shot_n or int(m_sh.group(2))
            if not sid or shot_n <= 0:
                return {"ok": False, "error": "Shot target (e.g. S001-02) is required to resolve Step 12/17 finding."}
            target_sc = next((s for s in sl_data["scenes"] if isinstance(s, dict) and str(s.get("id") or s.get("scene") or "").upper() == sid), None)
            if target_sc is None:
                return {"ok": False, "error": f"Scene {sid} not found in shotlist.json."}
            raw_sh = target_sc.get("shots")
            shots: list[Any] = raw_sh if isinstance(raw_sh, list) else []
            target_sh = next((sh for idx_i, sh in enumerate(shots, start=1) if isinstance(sh, dict) and int(sh.get("n") or idx_i) == shot_n), None)
            if target_sh is None:
                return {"ok": False, "error": f"Shot {sid}-{shot_n:02d} not found in shotlist.json."}
            fld = (field or "composition").strip().lower()
            if fld not in ("composition", "action", "blocking", "lighting", "props"):
                fld = "composition"
            if fld == "props":
                target_sh["props"] = [p.strip()[:60] for p in new_txt.split(",") if p.strip()]
            else:
                target_sh[fld] = new_txt[:600]
            _write_json(sl_path, sl_data)
            applied_file = "shots/shotlist.json"

            # Sync unlocked Step 17 keyframe prompt for this shot
            meta_path = pd / "keyframes_v2.json"
            meta = _read_json(meta_path)
            if isinstance(meta, dict):
                locked_ids = {str(x) for x in (meta.get("locked") or [])}
                shot_key = f"{sid}-{shot_n:02d}"
                if shot_key not in locked_ids:
                    with contextlib.suppress(Exception):
                        ctx = keyframe_context.load_keyframe_project_context(slug, pd)
                        info = keyframe_context.build_shot_keyframe_info(target_sh, sid, str(target_sc.get("heading") or ""), ctx)
                        prompts = dict(meta.get("prompts") or {})
                        prompts[shot_key] = info["default_prompt"]
                        meta["prompts"] = prompts
                        _write_json(meta_path, meta, indent=2)
            if record_bidirectional:
                _record_sync_if_needed(pd, slug, 12, f"User resolved Step 12/17 shot continuity decision in {sid}-{shot_n:02d}.{fld}")

    # Update persisted report so this finding is marked resolved
    reports = load_reports(pd)
    step_rep = reports.get("steps", {}).get(str(step))
    if isinstance(step_rep, dict) and isinstance(step_rep.get("issues"), list):
        issue_norm = str(issue_text or "").strip().lower()
        def _matches_issue(it: dict[str, Any], *, require_ambiguous: bool) -> bool:
            if require_ambiguous and not (it.get("ambiguous") or it.get("needs_user_decision")):
                return False
            if issue_norm and str(it.get("issue") or "").strip().lower() != issue_norm:
                return False
            same_target = bool(target) and str(it.get("target") or "").strip().lower() == target.strip().lower()
            same_loc = (
                bool(scene_id)
                and str(it.get("scene_id") or "").upper() == scene_id.strip().upper()
                and int(it.get("line_index", -1)) == int(line_index)
            )
            return same_target or same_loc

        matched_it = next(
            (it for it in step_rep["issues"] if isinstance(it, dict) and _matches_issue(it, require_ambiguous=True)),
            None,
        )
        if matched_it is None:
            matched_it = next(
                (it for it in step_rep["issues"] if isinstance(it, dict) and _matches_issue(it, require_ambiguous=False)),
                None,
            )
        if matched_it is not None:
            matched_it["ambiguous"] = False
            matched_it["needs_user_decision"] = False
            matched_it["fixed"] = True
            matched_it["resolved_by"] = "user"
            matched_it["resolution_label"] = option_label or ("Kept original line" if keep_original else "Updated line")
            if not keep_original and new_txt:
                matched_it["current_text"] = new_txt
        remaining_amb = sum(1 for it in step_rep["issues"] if isinstance(it, dict) and it.get("ambiguous"))
        step_rep["ambiguous_count"] = remaining_amb
        step_rep["fixes_applied"] = sum(1 for it in step_rep["issues"] if isinstance(it, dict) and it.get("fixed"))
        save_step_report(pd, step, step_rep)

    return {
        "ok": True,
        "step": step,
        "target": target,
        "scene_id": scene_id,
        "line_index": line_index,
        "applied_file": applied_file,
        "keep_original": bool(keep_original),
        "replacement_text": new_txt,
        "report": step_rep if isinstance(step_rep, dict) else {},
        "message": (
            f"Dismissed {target or scene_id} (kept original text)."
            if keep_original
            else f"Applied resolution to {target or scene_id} ({applied_file})."
        ),
    }
