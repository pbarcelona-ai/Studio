"""Tests for Studio's bi-directional workflow sync queue, strict two-phase completion, and persistent top banner."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))


def _make_stub_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 256)


def test_bidirectional_sync_requires_tool_run_and_approval_all_the_way_back_to_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from studio_app import routes_get, routes_post

    slug = "bidir_demo"
    pd = tmp_path / "projects" / "books" / slug
    pd.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(routes_get, "pdir", lambda s, kind="book": tmp_path / "projects" / "books" / s)
    monkeypatch.setattr(routes_post, "pdir", lambda s, kind="book": tmp_path / "projects" / "books" / s)

    # Seed existing project artifacts for Steps 7, 9, 10, 11, 12, and 17 (NOT 18..22!)
    (pd / f"{slug}.json").write_text(json.dumps({"title": "Demo"}), encoding="utf-8")
    (pd / "global_params.json").write_text(json.dumps({"look": "pixar_3d"}), encoding="utf-8")
    _make_stub_png(pd / "assets" / "turnarounds" / "tommy_front.png")
    _make_stub_png(pd / "assets" / "sets" / "living_room.png")
    (pd / "shots").mkdir(parents=True, exist_ok=True)
    (pd / "shots" / "shotlist.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
    _make_stub_png(pd / "keyframes" / "S001-01.png")

    class _Post:
        def __init__(self, body: dict[str, Any]) -> None:
            self.body = body

    class _Get:
        def __init__(self, cur: int) -> None:
            self._cur = cur

        def q(self, key: str) -> str:
            return slug if key == "project" else (str(self._cur) if key == "current_step" else "")

    # 1. User modifies Step 09 (Visual Style) after already reaching Step 17 -> queues Steps [10, 11, 17] (NOT 18!)
    m_res = routes_post._v2_workflow_sync_event(
        _Post(
            {
                "project": slug,
                "action": "modify",
                "step": 9,
                "current_step": 9,
                "origin_step": 17,
                "summary": "Changed film style to 3D Pixar",
            }
        )
    )  # type: ignore[arg-type]
    queued_steps = [it["step"] for it in m_res["queue"]["items"]]
    assert queued_steps == [10, 11, 17]
    assert m_res["queue"]["origin_step"] == 17
    assert m_res["banner"]["active"] is True
    assert m_res["banner"]["phase"] == "go_to_step"
    assert m_res["banner"]["target_step"] == 10

    # 2. User navigates to Step 10 -> banner tells them to run Step 10's tool
    g10 = routes_get._v2_workflow_sync(_Get(10))  # type: ignore[arg-type]
    assert g10["banner"]["phase"] == "needs_run"
    assert "Turnarounds" in g10["banner"]["instruction"]

    # 3. Trying to click Approve BEFORE running Step 10's tool MUST BE BLOCKED and state the specific Step 10 action!
    blk = routes_post._v2_workflow_sync_event(
        _Post({"project": slug, "action": "approve", "step": 10, "current_step": 10})
    )  # type: ignore[arg-type]
    assert blk["blocked_needs_run"] is True
    assert blk["advanced"] is False
    assert blk["queue"]["active"] is True
    assert "Generate" in blk["required_action"] and "Restyle" in blk["required_action"]

    # 4. User runs Step 10 tool -> transitions to `needs_approve` and tells user to hit the Approval button!
    td10 = routes_post._v2_workflow_sync_event(
        _Post({"project": slug, "action": "tool_done", "step": 10, "current_step": 10, "tool_label": "Re-rendered Turnaround"})
    )  # type: ignore[arg-type]
    assert td10["banner"]["phase"] == "needs_approve"
    assert "Approve" in td10["banner"]["instruction"]

    # 5. User clicks Approve on Step 10 -> marks Step 10 done and advances to Step 11!
    ap10 = routes_post._v2_workflow_sync_event(
        _Post({"project": slug, "action": "approve", "step": 10, "current_step": 10})
    )  # type: ignore[arg-type]
    assert ap10["advanced"] is True
    assert ap10["completed"] is False
    assert ap10["next_step"] == 11

    # 6. Mid-catchup nested modification: user edits Step 15 dialogue requiring upstream Step 06 -> merges cleanly!
    (pd / "screenplay").mkdir(parents=True, exist_ok=True)
    (pd / "screenplay" / "scene-S001.json").write_text("{}", encoding="utf-8")
    nested = routes_post._v2_workflow_sync_event(
        _Post(
            {
                "project": slug,
                "action": "modify",
                "step": 15,
                "current_step": 15,
                "origin_step": 15,
                "include_upstream": True,
                "summary": "Edited spoken dialogue line in Step 15",
            }
        )
    )  # type: ignore[arg-type]
    # Must preserve original origin_step=17 AND prepend upstream Step 06 + Step 15 before remaining [11, 17]!
    assert nested["queue"]["origin_step"] == 17
    pending_steps = [it["step"] for it in nested["queue"]["items"] if it["status"] != "done"]
    assert pending_steps == [6, 11, 15, 17]

    # 7. Run & approve every remaining step in order (6 -> 11 -> 15 -> 17); queue ONLY clears on the final approval!
    for idx, st_num in enumerate(pending_steps):
        routes_post._v2_workflow_sync_event(
            _Post({"project": slug, "action": "tool_done", "step": st_num, "current_step": st_num})
        )  # type: ignore[arg-type]
        ap = routes_post._v2_workflow_sync_event(
            _Post({"project": slug, "action": "approve", "step": st_num, "current_step": st_num})
        )  # type: ignore[arg-type]
        assert ap["advanced"] is True
        if idx < len(pending_steps) - 1:
            assert ap["completed"] is False
            assert ap["queue"]["active"] is True
        else:
            assert ap["completed"] is True
            assert ap["queue"]["active"] is False
            assert ap["banner"]["active"] is False
            assert ap["origin_step"] == 17


def test_transitive_upstream_chain_and_roadmap_popup_for_step17_to_12_to_7(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from studio_app import routes_post

    slug = "transitive_demo"
    pd = tmp_path / "projects" / "books" / slug
    pd.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(routes_post, "pdir", lambda s, kind="book": tmp_path / "projects" / "books" / s)

    # Project has Step 07 Continuity, Step 12 Shot List, and Step 17 Keyframes
    (pd / f"{slug}.json").write_text(json.dumps({"title": "Demo"}), encoding="utf-8")
    (pd / "shots").mkdir(parents=True, exist_ok=True)
    (pd / "shots" / "shotlist.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
    _make_stub_png(pd / "keyframes" / "S001-01.png")

    class _Post:
        def __init__(self, body: dict[str, Any]) -> None:
            self.body = body

    # Previewing a Step 17 change referencing Step 12 MUST transitively discover Step 07 (12 depends on 7)
    # and produce the exact ordered roadmap: 1. Step 07 -> 2. Step 12 -> 3. Return to Step 17!
    prev = routes_post._v2_workflow_sync_event(
        _Post(
            {
                "project": slug,
                "action": "preview",
                "step": 17,
                "current_step": 17,
                "origin_step": 17,
                "upstream_steps": [12],
                "summary": "Edited keyframe prompt in Step 17",
            }
        )
    )  # type: ignore[arg-type]

    steps = [it["step"] for it in prev["queue"]["items"]]
    assert steps == [7, 12, 17]
    assert "Step 07" in prev["plan_chain"]
    assert "Step 12" in prev["plan_chain"]
    assert "Step 17" in prev["plan_chain"]
    assert len(prev["plan_lines"]) == 3
    assert "Step 07" in prev["plan_lines"][0] and "Step 12 depends on Step 07" in prev["plan_lines"][0]
    assert "Step 12" in prev["plan_lines"][1]
    assert "Return to Step 17" in prev["plan_lines"][2]
    # Preview must be read-only (does NOT persist workflow_sync_queue.json yet!)
    assert not (pd / "workflow_sync_queue.json").exists()

