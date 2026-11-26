"""Tests for automatic shot-to-shot continuity, prop persistence, grounded surface, and scale auditing."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def test_deterministic_shot_continuity_fixes_contradictions_surfaces_and_scale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import character_tokens
    from studio_app import routes_post, shot_continuity_audit

    slug = "audit_demo"
    pd = tmp_path / "projects" / "books" / slug
    (pd / "shots").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(character_tokens, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(character_tokens, "CHARACTERS_ROOT", tmp_path / "projects" / "characters")
    monkeypatch.setattr(routes_post, "pdir", lambda s, kind="book": tmp_path / "projects" / "books" / s)

    (pd / f"{slug}.json").write_text(
        json.dumps(
            {
                "title": "Demo",
                "characters": [
                    {"name": "MOM", "token": "Average woman in mid-30s wearing black apron"},
                    {"name": "JUDAH", "token": "Adult black Labrador dog, red collar"},
                ],
                "locations": [
                    {
                        "name": "LIVING ROOM",
                        "token": "Open living room with teal sofa, floral rug, round wooden dining table on left, oak TV console on right.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (pd / "sets_custom.json").write_text(
        json.dumps(
            {
                "living room": {
                    "name": "LIVING ROOM",
                    "description": "Open living room with teal sofa, floral rug, round wooden dining table on left, oak TV console on right.",
                }
            }
        ),
        encoding="utf-8",
    )
    (pd / "shots" / "shotlist.json").write_text(
        json.dumps(
            {
                "scenes": [
                    {
                        "id": "S001",
                        "heading": "INT. LIVING ROOM - DAY",
                        "shots": [
                            {
                                "n": 3,
                                "type": "INSERT",
                                "lens_mm": 65,
                                "characters": [],
                                "props": ["empty coat hook by front door"],
                                "composition": "INSERT on the single brass coat hook, with the plain tan adult coat hanging on it, holding a beat.",
                                "blocking": "No action",
                                "action": "The bare hook, holding a beat",
                            },
                            {
                                "n": 5,
                                "type": "MCU",
                                "lens_mm": 50,
                                "characters": [],
                                "props": ["chipped white mug"],
                                "composition": "Tilts down to the coffee table, landing on the chipped white mug.",
                                "blocking": "No action",
                                "action": "Tea bag string hangs still",
                            },
                            {
                                "n": 7,
                                "type": "MS",
                                "lens_mm": 28,
                                "characters": ["JUDAH", "MOM"],
                                "props": ["steel dog bowl"],
                                "composition": "The steel bowl rests on the floor; Judah lunges in and fills the frame beside Mom.",
                                "blocking": "Judah enters",
                                "action": "Judah gulps twice",
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (pd / "keyframes").mkdir(parents=True, exist_ok=True)
    (pd / "keyframes" / "S001-05.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"kf" * 100)
    (pd / "keyframes_v2.json").write_text(
        json.dumps({"locked": [], "prompts": {"S001-03": "old", "S001-05": "old", "S001-07": "old"}}),
        encoding="utf-8",
    )

    class _Post:
        def __init__(self, body: dict[str, Any]) -> None:
            self.body = body

    res = routes_post._v2_shot_continuity_audit(
        _Post({"project": slug, "scene": "S001", "use_llm": False, "record_bidirectional": True})
    )  # type: ignore[arg-type]

    assert res["ok"] is True
    assert res["fixes_applied"] >= 4
    assert res["keyframes_updated"] == 3

    sl_after = json.loads((pd / "shots" / "shotlist.json").read_text(encoding="utf-8"))
    shots_by_n = {s["n"]: s for s in sl_after["scenes"][0]["shots"]}
    # S001-03: bare hook self-contradiction fixed
    assert "coat hanging" not in shots_by_n[3]["composition"].lower()
    assert "bare and empty" in shots_by_n[3]["composition"].lower()
    # S001-05: nonexistent coffee table relocated to dining table + 4-inch mug scale anchored
    assert "coffee table" not in shots_by_n[5]["composition"].lower()
    assert "dining table" in shots_by_n[5]["composition"].lower()
    assert "4-inch" in shots_by_n[5]["composition"].lower()
    # S001-07: 'fills the frame' replaced with natural knee-high scale + 8-inch bowl anchored
    assert "fills the frame" not in shots_by_n[7]["composition"].lower()
    assert "knee-high" in shots_by_n[7]["composition"].lower()
    assert "8-inch" in shots_by_n[7]["composition"].lower()

    # Step 17 prompts rebuilt AND bidirectional sync queue updated!
    kf_after = json.loads((pd / "keyframes_v2.json").read_text(encoding="utf-8"))
    assert "dining table" in kf_after["prompts"]["S001-05"].lower()
    assert (pd / "workflow_sync_queue.json").is_file()

    # Also verify offline sanity helper used by shot_list.write() on new book imports
    sanity_data = {
        "scenes": [
            {
                "id": "S001",
                "heading": "INT. LIVING ROOM - DAY",
                "shots": [
                    {
                        "n": 1,
                        "props": ["empty coat hook"],
                        "composition": "Hook on wall, with a tan coat hanging on it.",
                        "action": "Empty hook",
                    }
                ],
            }
        ]
    }
    auto = shot_continuity_audit.run_deterministic_shot_sanity(sanity_data, pd)
    assert len(auto) == 1
    assert "coat hanging" not in sanity_data["scenes"][0]["shots"][0]["composition"].lower()
