"""Cost: estimate against actual (BOOK_TO_SCREEN_BUILD.md Section 10.2, milestone M15).

The CostLedger counts what was really made, from the files on disk (so nothing has to be remembered by hand): every picture of every style,
every earlier version (a regeneration), the look-development sheets, every clip, the audiobook and the renders. It prices them with the same
units as the estimate (production.GPU_SECONDS for free GPUs as GPU time, production.PAID_DOLLARS when a paid service is used), and keeps the
regenerations apart, so the project page shows estimate vs. actual. ledger.json in the book adds paid calls the Studio was told about.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import clips
import layout
import pictures
import production
import styles


def _setdir(name: str) -> Path | None:
    return layout.find_dir(name) if name and layout.SLUG_RE.match(name) else None


def actual(pdir: Path) -> dict:
    st = production.load(pdir)
    tier = st["tier"]
    gpu, paid = production.GPU_SECONDS[tier], production.PAID_DOLLARS[tier]
    per_style = []
    for s in st["styles"]:
        sid = s["id"]
        ps = pictures.status(pdir, sid)
        made = sum(1 for x in ps["shots"] if x["image"])
        regen = sum(len(x["versions"]) for x in ps["shots"])
        ld = styles.lookdev_status(pdir, sid) if (pdir / "styles" / sid / "lookdev.json").is_file() else {"rendered": 0}
        cl = clips.status(pdir, sid)["clips"] if ps["shots"] else []
        n_clips = sum(1 for c in cl if c["clip"] and not c["clip"].startswith("footage/"))
        pics = made + regen + int(ld.get("rendered", 0) or 0)
        secs = pics * gpu["picture"] + n_clips * gpu["clip"]
        per_style.append({"style": sid, "pictures": made, "regenerations": regen, "lookdev": int(ld.get("rendered", 0) or 0), "clips": n_clips,
                          "gpu_hours": round(secs / 3600, 2), "dollars_if_paid": round(pics * paid["picture"] + n_clips * paid["clip"], 2)})
    extra = ledger(pdir)
    return {"styles": per_style, "gpu_hours": round(sum(x["gpu_hours"] for x in per_style), 2),
            "regenerations": sum(x["regenerations"] for x in per_style), "paid_dollars": round(sum(e["dollars"] for e in extra), 2), "paid_calls": len(extra)}


def ledger(pdir: Path) -> list[dict]:
    try:
        d = json.loads((pdir / "ledger.json").read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def record(pdir: Path, step: str, dollars: float, regeneration: bool = False, note: str = "") -> dict:
    """A paid call (a paid image / video service): what it cost, and whether it was a regeneration."""
    if not 0 <= dollars <= 10000:
        raise ValueError("dollars is 0-10000")
    items = ledger(pdir)
    e = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "step": step[:80], "dollars": round(float(dollars), 4), "regeneration": bool(regeneration), "note": note[:200]}
    items.append(e)
    (pdir / "ledger.json").write_text(json.dumps(items, indent=1), encoding="utf-8")
    return e


def report(pdir: Path) -> dict:
    """Estimate vs. actual for the page and the API."""
    st = production.load(pdir)
    est = production.estimate(st)
    act = actual(pdir)
    return {"estimate": {"gpu_hours": est["gpu_hours"], "dollars": est["dollars"], "calls": sum(s["calls"] for s in est["styles"])}, "actual": act,
            "over_estimate": act["gpu_hours"] > est["gpu_hours"] * 1.0001 if est["gpu_hours"] else False, "spend_limit": float(st.get("spend_limit", 0) or 0)}
