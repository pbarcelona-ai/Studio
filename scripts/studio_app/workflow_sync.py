"""Bi-directional Studio workflow sync queue and step dependency tracker.

Tracks whenever a user modifies an earlier or later step after downstream or upstream
work already exists, persists the exact ordered queue of steps that must be re-run
and approved in `<project>/workflow_sync_queue.json`, and enforces a two-phase
completion rule per step:
  1. ``needs_run``     -> User must go to that step and run its tool.
  2. ``needs_approve`` -> Tool finished; banner tells user to click the Approve button.
  3. ``done``          -> Approved; advances to the next required step until back at origin.

The queue clears ONLY when every required step has been both run AND approved.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("studio.workflow_sync")

STEP_CATALOG: dict[int, dict[str, str]] = {
    1: {
        "short": "01 Ingest",
        "title": "Story Ingest & Source",
        "action": "Save or re-ingest your updated story source in Step 01",
    },
    2: {
        "short": "02 Chapters",
        "title": "Check & Split Chapters",
        "action": "Review and save chapter splits in Step 02",
    },
    3: {
        "short": "03 Coverage",
        "title": "Coverage & Logline",
        "action": "Regenerate Coverage & Logline in Step 03",
    },
    4: {
        "short": "04 Scope",
        "title": "Format & Runtime Scope",
        "action": "Confirm and save Format & Runtime Scope in Step 04",
    },
    5: {
        "short": "05 Outline",
        "title": "Story Outline & Beat Sheet",
        "action": "Regenerate, sync from screenplay, or save Story Outline & Beat Sheet in Step 05",
    },
    6: {
        "short": "06 Script",
        "title": "Screenplay Editor",
        "action": "Update or regenerate the Screenplay in Step 06",
    },
    7: {
        "short": "07 Continuity",
        "title": "Continuity & World Rules",
        "action": "Click '💾 Save Continuity' or 'Rebuild Continuity Book' in Step 07",
    },
    8: {
        "short": "08 Cast",
        "title": "Cast & Characters",
        "action": "Click '🔄 Sync from Book', '📷 Import Photo', or '💾 Save' on a character in Step 08",
    },
    9: {
        "short": "09 Style",
        "title": "Art Direction & Style Recipe",
        "action": "Click '💾 Apply Style to Book' in Step 09",
    },
    10: {
        "short": "10 Turnaround",
        "title": "Look Development & Turnarounds",
        "action": "Update affected Character Turnarounds in Step 10 by clicking '✨ Generate' / '↺ Re-roll', '🎨 Restyle', or '📷' upload on any character view",
    },
    11: {
        "short": "11 Static Sets",
        "title": "Static Sets",
        "action": "Update affected Static Set Plates in Step 11 by clicking '🎨 Generate / Re-convert', '📷 Import Photo', or '📌 Set Baseline' on any set card",
    },
    12: {
        "short": "12 Shots",
        "title": "Shot List & Cinematography",
        "action": "Click 'Regenerate Shot List' or '💾 Save' on an edited shot in Step 12",
    },
    13: {
        "short": "13 Hardware",
        "title": "Hardware & Where to Run",
        "action": "Confirm your compute settings in Step 13",
    },
    14: {
        "short": "14 Voices",
        "title": "Voice Casting & Dialects",
        "action": "Review and save Voice Casting in Step 14",
    },
    15: {
        "short": "15 Dialogue",
        "title": "Spoken Dialogue Delivery",
        "action": "Re-render affected Spoken Dialogue lines in Step 15",
    },
    16: {
        "short": "16 Score & Foley",
        "title": "Score & Foley Sound Design",
        "action": "Re-render affected Score or Foley SFX cues in Step 16",
    },
    17: {
        "short": "17 Keyframes",
        "title": "Storyboard Keyframes",
        "action": "Click 'Sync Scene/All Prompts' and re-render affected Keyframes in Step 17",
    },
    18: {
        "short": "18 Video",
        "title": "Motion & Video Synthesis",
        "action": "Re-synthesize affected Video Clips in Step 18",
    },
    19: {
        "short": "19 Polish",
        "title": "Lip-Sync & Polish",
        "action": "Re-run Polish / Lip-Sync on updated clips in Step 19",
    },
    20: {
        "short": "20 Timeline",
        "title": "Sequence Timeline Assembly",
        "action": "Rebuild the Sequence Timeline in Step 20",
    },
    21: {
        "short": "21 Audio Mix",
        "title": "Stem Audio Mix",
        "action": "Re-render the Master Audio Stem Mix in Step 21",
    },
    22: {
        "short": "22 Premiere",
        "title": "Premiere & Export",
        "action": "Re-export your final Premiere video in Step 22",
    },
}

# Dependency map: when `source_step` is modified, which earlier (`upstream`) and later (`downstream`)
# steps must be re-run (downstream steps are automatically filtered to steps already built on disk).
DEPENDENCY_MAP: dict[int, dict[str, tuple[int, ...]]] = {
    1: {"upstream": (), "downstream": (2, 3, 5, 6, 7, 8, 10, 11, 12, 15, 16, 17, 18, 20, 21, 22)},
    2: {"upstream": (), "downstream": (3, 5, 6, 7, 12, 15, 16, 17, 18, 20, 22)},
    3: {"upstream": (), "downstream": (5, 6, 7, 12, 17)},
    4: {"upstream": (), "downstream": (5, 6, 12, 17)},
    5: {"upstream": (), "downstream": (6, 7, 11, 12, 15, 16, 17, 18, 20, 22)},
    6: {"upstream": (5,), "downstream": (7, 8, 11, 12, 14, 15, 16, 17, 18, 20, 21, 22)},
    7: {"upstream": (), "downstream": (8, 10, 11, 12, 17, 18, 20, 22)},
    8: {"upstream": (7,), "downstream": (10, 12, 17, 18, 20, 22)},
    9: {"upstream": (), "downstream": (10, 11, 17, 18, 20, 22)},
    10: {"upstream": (8,), "downstream": (17, 18, 20, 22)},
    11: {"upstream": (7,), "downstream": (12, 17, 18, 20, 22)},
    12: {"upstream": (7,), "downstream": (17, 18, 20, 22)},
    14: {"upstream": (), "downstream": (15, 21, 22)},
    15: {"upstream": (6,), "downstream": (20, 21, 22)},
    16: {"upstream": (7,), "downstream": (21, 22)},
    17: {"upstream": (12,), "downstream": (18, 20, 22)},
    18: {"upstream": (17,), "downstream": (19, 20, 22)},
    19: {"upstream": (), "downstream": (20, 22)},
    20: {"upstream": (), "downstream": (21, 22)},
    21: {"upstream": (), "downstream": (22,)},
}


def resolve_transitive_upstream(
    pd: Path,
    slug: str,
    seed_steps: list[int],
    source_step: int,
) -> tuple[list[int], dict[int, int]]:
    """Expand upstream dependencies transitively (e.g. 17 -> 12 -> 7).

    Returns ``(sorted_upstream_steps, child_by_parent_step)`` where ``child_by_parent_step[7] = 12``
    explains *why* Step 7 was pulled in (Step 12 depends on Step 7).
    """
    visited: set[int] = set()
    child_by_parent: dict[int, int] = {}
    queue: list[int] = []
    for s in seed_steps:
        si = int(s)
        if 1 <= si < source_step and si not in visited:
            visited.add(si)
            queue.append(si)

    while queue:
        cur = queue.pop(0)
        for parent in DEPENDENCY_MAP.get(cur, {}).get("upstream", ()):
            pi = int(parent)
            if 1 <= pi < cur and pi not in visited:
                if step_has_existing_artifacts(pd, slug, pi):
                    visited.add(pi)
                    child_by_parent[pi] = cur
                    queue.append(pi)

    return sorted(visited), child_by_parent


def format_action_plan(items: list[dict[str, Any]], origin_step: int) -> dict[str, Any]:
    """Build a human-readable ordered roadmap listing every step the user must perform and approve."""
    pending = [it for it in items if isinstance(it, dict) and it.get("status") != "done"]
    if not pending:
        return {"plan_chain": "", "plan_lines": []}
    chain = " ➔ ".join(f"Step {int(it['step']):02d} ({it['title']})" for it in pending)
    lines: list[str] = []
    for idx, it in enumerate(pending, start=1):
        st_num = int(it["step"])
        dep_note = str(it.get("dep_note") or "").strip()
        prefix = "Return to " if st_num == origin_step and idx == len(pending) and len(pending) > 1 else ""
        why = f" [{dep_note}]" if dep_note else ""
        lines.append(
            f"{idx}. {prefix}Step {st_num:02d} ({it['title']}){why}: {it['action']}, then click Approve & Next."
        )
    return {"plan_chain": chain, "plan_lines": lines}


def _has_files(directory: Path, pattern: str = "*", min_bytes: int = 100) -> bool:
    if not directory.is_dir():
        return False
    return any(p.is_file() and p.stat().st_size >= min_bytes for p in directory.glob(pattern))


def step_has_existing_artifacts(pd: Path, slug: str, step: int) -> bool:
    """Return True if the project already has generated work on disk for `step`."""
    if step == 1:
        return (pd / "source_text.txt").is_file() or _has_files(pd / "source", "*", min_bytes=1)
    if step == 2:
        return (pd / "chapters.json").is_file() or _has_files(pd / "chapters", "*", min_bytes=1)
    if step == 3:
        return (pd / "readin" / "coverage.json").is_file()
    if step == 4:
        return (pd / "adaptation" / "adaptation.json").is_file()
    if step == 5:
        return (pd / "adaptation" / "adaptation.json").is_file() or (pd / "adaptation" / "treatment.md").is_file()
    if step == 6:
        return _has_files(pd / "screenplay", "scene-*.json", min_bytes=2)
    if step == 7:
        return (pd / f"{slug}.json").is_file() or (pd / "continuity.json").is_file()
    if step == 8:
        import character_tokens
        try:
            return bool(character_tokens.list_characters(slug))
        except Exception:
            return (pd / "cast_lock.json").is_file()
    if step == 9:
        return (pd / "global_params.json").is_file()
    if step == 10:
        return _has_files(pd / "assets" / "turnarounds", "*.png")
    if step == 11:
        return _has_files(pd / "assets" / "sets", "*.png") or (pd / "sets_views.json").is_file()
    if step == 12:
        return (pd / "shots" / "shotlist.json").is_file()
    if step == 14:
        return (pd / "voice_cast.json").is_file()
    if step == 15:
        return _has_files(pd / "audio" / "dialogue", "*.wav")
    if step == 16:
        return _has_files(pd / "audio" / "foley", "*.wav") or _has_files(pd / "audio" / "score", "*.wav")
    if step == 17:
        return _has_files(pd / "keyframes", "*.png")
    if step == 18:
        return _has_files(pd / "videos", "*.mp4") or _has_files(pd / "clips", "*.mp4")
    if step == 19:
        return _has_files(pd / "polish", "*.mp4")
    if step == 20:
        return (pd / "edit" / "timeline.json").is_file() or _has_files(pd / "edit", "*.mp4")
    if step == 21:
        return _has_files(pd / "audio" / "mix", "*.wav") or (pd / "audio" / "master_mix.wav").is_file()
    if step == 22:
        return _has_files(pd / "exports", "*.mp4")
    return False


def _queue_path(pd: Path) -> Path:
    return pd / "workflow_sync_queue.json"


def _empty_queue() -> dict[str, Any]:
    return {
        "active": False,
        "origin_step": 0,
        "change_summary": "",
        "updated_at": 0,
        "items": [],
    }


def load_queue(pd: Path) -> dict[str, Any]:
    p = _queue_path(pd)
    if p.is_file():
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and isinstance(doc.get("items"), list):
                # Keep action instructions in sync with latest STEP_CATALOG button labels
                for it in doc["items"]:
                    if isinstance(it, dict) and it.get("step") is not None:
                        meta = STEP_CATALOG.get(int(it["step"]))
                        if meta:
                            it["action"] = meta["action"]
                            it["title"] = meta["title"]
                            it["short"] = meta["short"]
                return doc
        except Exception as e:
            log.debug("workflow_sync_queue.json read failed: %s", e)
    return _empty_queue()


def save_queue(pd: Path, doc: dict[str, Any]) -> dict[str, Any]:
    pd.mkdir(parents=True, exist_ok=True)
    doc["updated_at"] = int(time.time())
    pending = [it for it in (doc.get("items") or []) if isinstance(it, dict) and it.get("status") != "done"]
    doc["active"] = bool(pending)
    if not doc["active"]:
        doc["items"] = []
    _queue_path(pd).write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return doc


def _make_item(step: int, reason: str, *, direction: str) -> dict[str, Any]:
    meta = STEP_CATALOG.get(step, {"short": f"{step:02d}", "title": f"Step {step:02d}", "action": f"Re-run Step {step:02d}"})
    return {
        "step": step,
        "short": meta["short"],
        "title": meta["title"],
        "action": meta["action"],
        "reason": reason,
        "direction": direction,
        "status": "needs_run",
    }


def _compute_modification_queue(
    pd: Path,
    slug: str,
    source_step: int,
    summary: str,
    *,
    origin_step: int | None = None,
    include_upstream: bool = False,
    explicit_upstream: list[int] | None = None,
    explicit_downstream: list[int] | None = None,
) -> dict[str, Any]:
    """Compute the merged transitive queue for a modification without writing to disk."""
    rules = DEPENDENCY_MAP.get(source_step, {"upstream": (), "downstream": ()})
    doc = load_queue(pd)

    prev_origin = int(doc.get("origin_step") or 0) if doc.get("active") else 0
    eff_origin = max(prev_origin, int(origin_step or source_step))

    seed_upstream: list[int] = []
    if explicit_upstream is not None:
        seed_upstream = [int(s) for s in explicit_upstream if 1 <= int(s) < source_step]
    elif include_upstream:
        for us in rules["upstream"]:
            if step_has_existing_artifacts(pd, slug, us):
                seed_upstream.append(us)

    # Always expand upstream transitively (e.g. 17 -> 12 -> 7!)
    req_upstream, child_by_parent = resolve_transitive_upstream(pd, slug, seed_upstream, source_step)

    req_downstream: list[int] = []
    if explicit_downstream is not None:
        req_downstream = [int(s) for s in explicit_downstream if source_step < int(s) <= 22]
    else:
        for ds in rules["downstream"]:
            if step_has_existing_artifacts(pd, slug, ds):
                req_downstream.append(ds)

    to_add: list[tuple[int, str, str]] = []
    for us in req_upstream:
        dep_child = child_by_parent.get(us)
        note = f"Step {dep_child:02d} depends on Step {us:02d}" if dep_child else f"Required upstream of Step {source_step:02d}"
        to_add.append((us, "upstream", note))
    if req_upstream and source_step not in req_downstream:
        to_add.append((source_step, "return", f"Return to where you made the change (Step {source_step:02d})"))
    for ds in req_downstream:
        to_add.append((ds, "downstream", f"Depends on Step {source_step:02d}"))

    if not to_add:
        return doc

    existing_by_step: dict[int, dict[str, Any]] = {}
    for it in doc.get("items") or []:
        if isinstance(it, dict) and isinstance(it.get("step"), int):
            existing_by_step[int(it["step"])] = dict(it)

    clean_summary = str(summary or f"Modified Step {source_step:02d}").strip()
    for st_num, direction, dep_note in to_add:
        prev = existing_by_step.get(st_num)
        if prev is None or prev.get("status") == "done":
            item = _make_item(st_num, clean_summary, direction=direction)
            item["dep_note"] = dep_note
            existing_by_step[st_num] = item
        else:
            prev["status"] = "needs_run"
            prev["reason"] = clean_summary
            if dep_note:
                prev["dep_note"] = dep_note

    sorted_items = [existing_by_step[k] for k in sorted(existing_by_step.keys())]
    doc["active"] = any(it.get("status") != "done" for it in sorted_items)
    doc["origin_step"] = eff_origin
    doc["change_summary"] = clean_summary
    doc["items"] = sorted_items
    return doc


def preview_modification(
    pd: Path,
    slug: str,
    source_step: int,
    summary: str,
    *,
    origin_step: int | None = None,
    include_upstream: bool = False,
    explicit_upstream: list[int] | None = None,
    explicit_downstream: list[int] | None = None,
) -> dict[str, Any]:
    """Read-only preview of the full transitive step chain & roadmap for the popup dialog."""
    doc = _compute_modification_queue(
        pd,
        slug,
        source_step,
        summary,
        origin_step=origin_step,
        include_upstream=include_upstream,
        explicit_upstream=explicit_upstream,
        explicit_downstream=explicit_downstream,
    )
    plan = format_action_plan(doc.get("items") or [], int(doc.get("origin_step") or source_step))
    return {"queue": doc, **plan}


def record_modification(
    pd: Path,
    slug: str,
    source_step: int,
    summary: str,
    *,
    origin_step: int | None = None,
    include_upstream: bool = False,
    explicit_upstream: list[int] | None = None,
    explicit_downstream: list[int] | None = None,
) -> dict[str, Any]:
    """Compute required transitive upstream & downstream steps after a modification and persist to disk."""
    doc = _compute_modification_queue(
        pd,
        slug,
        source_step,
        summary,
        origin_step=origin_step,
        include_upstream=include_upstream,
        explicit_upstream=explicit_upstream,
        explicit_downstream=explicit_downstream,
    )
    if not doc.get("items"):
        return doc
    return save_queue(pd, doc)


def mark_tool_performed(pd: Path, slug: str, step_num: int, tool_label: str = "") -> dict[str, Any]:
    """Transition a queued step from `needs_run` -> `needs_approve` once the user runs its required tool."""
    doc = load_queue(pd)
    if not doc.get("active"):
        return doc
    changed = False
    for it in doc.get("items") or []:
        if isinstance(it, dict) and int(it.get("step") or 0) == int(step_num):
            if it.get("status") == "needs_run":
                it["status"] = "needs_approve"
                if tool_label:
                    it["last_tool"] = tool_label
                changed = True
            break
    return save_queue(pd, doc) if changed else doc


def approve_step(pd: Path, slug: str, step_num: int) -> dict[str, Any]:
    """Mark a `needs_approve` step as `done` when the user clicks Approve & Next.

    Strictly refuses to clear a step that is still `needs_run` (user must perform the required tool first!).
    """
    doc = load_queue(pd)
    if not doc.get("active"):
        return {"queue": doc, "advanced": False, "blocked_needs_run": False, "completed": False, "next_step": 0}

    blocked = False
    advanced = False
    required_action = ""
    origin_step = int(doc.get("origin_step") or 0)

    for it in doc.get("items") or []:
        if isinstance(it, dict) and int(it.get("step") or 0) == int(step_num):
            st = str(it.get("status") or "needs_run")
            if st == "needs_run":
                blocked = True
                meta = STEP_CATALOG.get(int(step_num))
                required_action = str((meta or {}).get("action") or it.get("action") or "")
            elif st == "needs_approve":
                it["status"] = "done"
                advanced = True
            break

    if advanced:
        doc = save_queue(pd, doc)

    pending = [it for it in (doc.get("items") or []) if isinstance(it, dict) and it.get("status") != "done"]
    completed = advanced and len(pending) == 0
    next_step = int(pending[0]["step"]) if pending else (origin_step if completed else 0)
    return {
        "queue": doc,
        "advanced": advanced,
        "blocked_needs_run": blocked,
        "required_action": required_action,
        "completed": completed,
        "next_step": next_step,
        "origin_step": origin_step,
    }


def summarize_banner_state(doc: dict[str, Any], current_step: int) -> dict[str, Any]:
    """Compute exact user-facing top-banner instructions for the current step."""
    items = [it for it in (doc.get("items") or []) if isinstance(it, dict)]
    pending = [it for it in items if it.get("status") != "done"]
    if not doc.get("active") or not pending:
        return {"active": False}

    target = pending[0]
    t_step = int(target["step"])
    t_status = str(target.get("status") or "needs_run")
    done_count = len(items) - len(pending)
    origin_step = int(doc.get("origin_step") or t_step)
    origin_meta = STEP_CATALOG.get(origin_step, {"short": f"{origin_step:02d}", "title": f"Step {origin_step:02d}"})

    # If the user is currently on a later pending step that is already `needs_approve`, honor that step too
    cur_item = next((it for it in pending if int(it["step"]) == int(current_step)), None)
    if cur_item is not None and int(cur_item["step"]) == t_step:
        if t_status == "needs_approve":
            next_after = pending[1] if len(pending) > 1 else None
            next_desc = (
                f"Step {next_after['step']:02d} ({next_after['title']})"
                if next_after
                else f"complete sync & return to Step {origin_step:02d} ({origin_meta['title']})"
            )
            return {
                "active": True,
                "phase": "needs_approve",
                "target_step": t_step,
                "origin_step": origin_step,
                "progress_text": f"Step {done_count + 1} of {len(items)}",
                "headline": f"✅ Step {t_step:02d} ({target['title']}) Updated — Click the Approval Button!",
                "instruction": f"Scroll down and click the 'Approve & Next' button at the bottom of Step {t_step:02d} to proceed to {next_desc}.",
                "reason": str(target.get("reason") or doc.get("change_summary") or ""),
                "items": items,
            }
        return {
            "active": True,
            "phase": "needs_run",
            "target_step": t_step,
            "origin_step": origin_step,
            "progress_text": f"Step {done_count + 1} of {len(items)}",
            "headline": f"⚡ Action Required on Step {t_step:02d}: {target['title']}",
            "instruction": f"{target['action']}. Once finished, click the Approval button at the bottom to move to the next required step.",
            "reason": str(target.get("reason") or doc.get("change_summary") or ""),
            "items": items,
        }

    return {
        "active": True,
        "phase": "go_to_step",
        "target_step": t_step,
        "origin_step": origin_step,
        "progress_text": f"Step {done_count + 1} of {len(items)}",
        "headline": f"🔄 Bi-Directional Update Required — Go to Step {t_step:02d} ({target['title']})",
        "instruction": f"Because of '{doc.get('change_summary') or target.get('reason')}', go to Step {t_step:02d} ({target['title']}), {target['action'].lower()}, and then click the Approval button to work back to Step {origin_step:02d}.",
        "reason": str(target.get("reason") or doc.get("change_summary") or ""),
        "items": items,
    }
