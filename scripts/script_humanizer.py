"""Dialogue & Narration Humanizer for Pistachio's Studio (Steps 06 & 15).

Inspired by `blader/humanizer` (Wikipedia's guide to spotting AI prose):
strips stiff, inflated LLM clichés, unnecessary em-dash clutter, and robotic transitions
from screenplay action/dialogue lines so spoken TTS delivery (Step 15) sounds natural
while keeping plot, character names, and continuity tokens 100% intact.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("studio.script_humanizer")

# Targeted phrase & vocabulary replacements that preserve meaning while sounding spoken & human
_PHRASE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bIt is important to note that\s+", re.IGNORECASE), ""),
    (re.compile(r"\bIt's important to note that\s+", re.IGNORECASE), ""),
    (re.compile(r"\bNeedless to say,\s*", re.IGNORECASE), ""),
    (re.compile(r"\bIn the realm of\b", re.IGNORECASE), "in"),
    (re.compile(r"\bembark on a journey\b", re.IGNORECASE), "set out"),
    (re.compile(r"\bembarks on a journey\b", re.IGNORECASE), "sets out"),
    (re.compile(r"\bdelve into\b", re.IGNORECASE), "dig into"),
    (re.compile(r"\bdelves into\b", re.IGNORECASE), "digs into"),
    (re.compile(r"\bdelving into\b", re.IGNORECASE), "digging into"),
    (re.compile(r"\ba testament to\b", re.IGNORECASE), "proof of"),
    (re.compile(r"\ba tapestry of\b", re.IGNORECASE), "a mix of"),
    (re.compile(r"\ba symphony of\b", re.IGNORECASE), "a wave of"),
    (re.compile(r"\ba beacon of\b", re.IGNORECASE), "a sign of"),
    (re.compile(r"\bin a dance of\b", re.IGNORECASE), "in"),
    (re.compile(r"\bmoreover,\s*", re.IGNORECASE), "and "),
    (re.compile(r"\bfurthermore,\s*", re.IGNORECASE), "plus, "),
    (re.compile(r"\badditionally,\s*", re.IGNORECASE), "also, "),
    (re.compile(r"\bin conclusion,\s*", re.IGNORECASE), "in the end, "),
    (re.compile(r"\bmeticulously\b", re.IGNORECASE), "carefully"),
    (re.compile(r"\beffortlessly\b", re.IGNORECASE), "easily"),
    (re.compile(r"\bunwavering\b", re.IGNORECASE), "steady"),
    (re.compile(r"\bpivotal\b", re.IGNORECASE), "key"),
    (re.compile(r"\bpalpable\b", re.IGNORECASE), "thick"),
    (re.compile(r"\bwhispered softly\b", re.IGNORECASE), "whispered"),
    (re.compile(r"\bsmiled warmly\b", re.IGNORECASE), "smiled"),
    (re.compile(r"\bnodded solemnly\b", re.IGNORECASE), "nodded"),
]

_EM_DASH_SPACED_RE = re.compile(r"\s*[\u2014\u2013]\s*")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;!?])")


def _preserve_case(match_text: str, replacement: str) -> str:
    if not replacement:
        return ""
    if match_text.isupper():
        return replacement.upper()
    if match_text[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def humanize_text(text: str, *, is_dialogue: bool = True) -> tuple[str, list[str]]:
    """Strip AI prose tells from a single line of dialogue or action.

    Returns ``(cleaned_text, applied_reasons)``.
    """
    orig = str(text or "")
    if not orig.strip():
        return orig, []
    cur = orig
    reasons: list[str] = []

    for pat, repl in _PHRASE_RULES:
        def _sub(m: re.Match[str], r: str = repl) -> str:
            return _preserve_case(m.group(0), r)
        nxt = pat.sub(_sub, cur)
        if nxt != cur:
            reasons.append(f"simplified '{pat.pattern}'")
            cur = nxt

    # Replace repeated em-dashes in spoken dialogue (TTS often pauses awkwardly on multiple em-dashes)
    em_count = len(_EM_DASH_SPACED_RE.findall(cur))
    if (is_dialogue and em_count >= 1) or em_count >= 2:
        cur = _EM_DASH_SPACED_RE.sub(", ", cur)
        reasons.append("smoothed em-dash cadence")

    # Normalize spacing & accidental double commas / leading lowercase after stripped intro phrase
    cur = re.sub(r",\s*,+", ", ", cur)
    cur = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cur)
    cur = _MULTI_SPACE_RE.sub(" ", cur).strip()
    if cur and orig.lstrip()[:1].isupper() and cur[:1].islower():
        cur = cur[:1].upper() + cur[1:]

    return cur, reasons


def humanize_project_screenplay(
    slug: str,
    pd: Path,
    *,
    apply_changes: bool = True,
    dialogue_only: bool = False,
) -> dict[str, Any]:
    """Run the Humanizer pass across all `screenplay/scene-*.json` files in a project."""
    sp_dir = pd / "screenplay"
    if not sp_dir.is_dir():
        return {
            "status": "ok",
            "project": slug,
            "scenes_scanned": 0,
            "lines_scanned": 0,
            "lines_changed": 0,
            "applied": apply_changes,
            "examples": [],
        }

    scenes_scanned = 0
    lines_scanned = 0
    lines_changed = 0
    examples: list[dict[str, str]] = []

    for sf in sorted(sp_dir.glob("scene-*.json")):
        try:
            sc = json.loads(sf.read_text(encoding="utf-8"))
        except Exception as e:
            log.debug("skipping unreadable scene %s: %s", sf.name, e)
            continue
        if not isinstance(sc, dict):
            continue
        scenes_scanned += 1
        dirty = False
        for el in sc.get("elements") or []:
            if not isinstance(el, dict):
                continue
            etype = str(el.get("type") or "").lower()
            is_dlg = etype == "dialogue"
            if dialogue_only and not is_dlg:
                continue
            raw_txt = str(el.get("text") or "")
            if not raw_txt.strip():
                continue
            lines_scanned += 1
            cleaned, _reasons = humanize_text(raw_txt, is_dialogue=is_dlg)
            if cleaned != raw_txt:
                lines_changed += 1
                if len(examples) < 12:
                    examples.append({
                        "scene": sf.stem,
                        "speaker": str(el.get("character") or etype.upper()),
                        "before": raw_txt,
                        "after": cleaned,
                    })
                if apply_changes:
                    el["text"] = cleaned
                    dirty = True
        if apply_changes and dirty:
            sf.write_text(json.dumps(sc, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "status": "ok",
        "project": slug,
        "scenes_scanned": scenes_scanned,
        "lines_scanned": lines_scanned,
        "lines_changed": lines_changed,
        "applied": apply_changes,
        "dialogue_only": dialogue_only,
        "examples": examples,
    }
