"""Tests for Step 12 editable Camera & Motion / Subject & Action fields and Steps 03-07 & 12 early AI prompt continuity audits."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import adaptation  # noqa: E402
import continuity_book  # noqa: E402
import continuity_sync  # noqa: E402
import screenplay  # noqa: E402
import shot_list  # noqa: E402
from studio_app import early_prompt_audit  # noqa: E402


def _seed_project(tmp_path: Path) -> Path:
    pd = tmp_path / "test_book"
    pd.mkdir(parents=True, exist_ok=True)
    # Step 02 chapters.json (30 chapters so 6 min target triggers Step 04 tight-runtime advisory)
    (pd / "chapters.json").write_text(
        json.dumps({"chapters": [{"n": i, "title": f"Ch {i}", "words": 1200} for i in range(1, 31)]}),
        encoding="utf-8",
    )
    # Step 03 readin/coverage.json
    (pd / "readin").mkdir(parents=True, exist_ok=True)
    (pd / "readin" / "coverage.json").write_text(
        json.dumps({
            "logline": "A boy and his dog build a cardboard spaceship.",
            "genre": "family",
            "tone": "warm",
            "themes": ["imagination"],
            "characters": [
                {"name": "TOMMY", "role": "protagonist", "description": "Boy"},
                {"name": "JUDAH", "role": "supporting", "description": "Friendly yellow Labrador dog"},
            ],
            "key_events": ["Tommy sits on the rug.", "They blast off."],
            "length": "right",
        }),
        encoding="utf-8",
    )
    # Step 04 production.json (6 min for 30 chapters triggers Step 04 advisory)
    (pd / "production.json").write_text(
        json.dumps({"target_minutes": 6.0, "aspect": "16:9", "rating": "G", "faithfulness": "close", "recipe": ""}),
        encoding="utf-8",
    )
    # Step 05 adaptation/adaptation.json
    adaptation.save(
        pd,
        {
            "version": 1,
            "logline": "A boy and his dog build a spaceship.",
            "premise": "A rainy afternoon turns into a space adventure.",
            "ending": "They return home for cocoa.",
            "runtime_minutes": 10.0,
            "clip_seconds": 4.0,
            "n_chapters": 2,
            "acts": [{"name": "Act I", "purpose": "Setup", "share": 1.0, "seconds": 60, "first_chapter": 1, "last_chapter": 2}],
            "scenes": [
                {
                    "id": "S001",
                    "act": "Act I",
                    "title": "Rainy Living Room",
                    "summary": "Tommy and Judah look outside.",
                    "chapters": [1],
                    "anchor": "",
                    "importance": 4.0,
                    "keep": "full",
                    "location": "living room",
                    "characters": ["TOMMY", "JUDAH"],
                    "time_of_day": "afternoon",
                    "clips": 5,
                    "seconds": 20,
                },
                {
                    "id": "S002",
                    "act": "Act I",
                    "title": "Still in Living Room",
                    "summary": "Mom brings tea.",
                    "chapters": [1],
                    "anchor": "",
                    "importance": 3.0,
                    "keep": "full",
                    "location": "living room",
                    "characters": ["TOMMY", "MOM"],
                    "time_of_day": "",
                    "clips": 5,
                    "seconds": 20,
                },
            ],
            "cut": [],
            "stale": False,
        },
    )
    # Step 06 screenplay/scene-S001.json with deliberate early contradictions
    screenplay.save_scene(
        pd,
        "S001",
        {
            "heading": "INT. LIVING ROOM - AFTERNOON",
            "elements": [
                {"type": "action", "text": "An empty coat hook sits by the door, with the rain coat hanging on it."},
                {"type": "action", "text": "Judah the dog fills the frame beside Mom while his dog bowl sits on the carpet."},
                {"type": "dialogue", "character": "TOMMY", "text": "Let's go to Saturn!"},
            ],
        },
        edited=False,
    )
    # Step 07 Continuity Book with style buzzword + missing relative heights
    (pd / "test_book.json").write_text(
        json.dumps({
            "title": "Test Book",
            "setting": "Suburban home",
            "visual_style": "",
            "music_theme": "whimsical",
            "characters": [
                {
                    "name": "TOMMY",
                    "token": "3D Pixar 5-year-old boy with curly hair wearing a striped red shirt and jeans",
                    "voice": "male",
                    "personality": dict.fromkeys(continuity_book.PERSONALITY, "curious"),
                },
                {
                    "name": "JUDAH",
                    "token": "Yellow Labrador dog with floppy ears and warm brown eyes",
                    "voice": "narrator",
                    "personality": dict.fromkeys(continuity_book.PERSONALITY, "loyal"),
                },
            ],
            "locations": [{"name": "Living Room", "token": "Cozy living room with sofa and wooden dining table"}],
            "props": [{"name": "tea mug", "token": "white ceramic tea mug"}],
            "style_neutral": True,
        }),
        encoding="utf-8",
    )
    # Step 11 sets_custom.json
    (pd / "sets_custom.json").write_text(
        json.dumps({
            "living room": {
                "description": "Warm beige living room with dark brown sofa, round wooden dining table, and wall-mounted TV. No coffee table.",
                "lighting": "Soft warm ceiling lamp light.",
            }
        }),
        encoding="utf-8",
    )
    # Step 12 shots/shotlist.json
    shot_list.save(
        pd,
        {
            "scenes": [
                {
                    "id": "S001",
                    "heading": "INT. LIVING ROOM - AFTERNOON",
                    "breakdown": {"intent": "open", "emotional_beat": "cozy", "blocking": "on rug", "performance": "calm"},
                    "target_seconds": 12.0,
                    "shots": [
                        {
                            "n": 1,
                            "type": "WS",
                            "lens_mm": 24,
                            "height": "eye",
                            "angle": "straight",
                            "movement": "static",
                            "composition": "Wide view of the living room with the empty coat hook, with the rain coat hanging on it.",
                            "lighting": "soft overcast daylight",
                            "blocking": "room establishing",
                            "action": "Rain patters outside past the bare hook.",
                            "expression": "",
                            "dialogue": "",
                            "sound": "rain",
                            "seconds": 4.0,
                            "transition": "cut",
                            "priority": 1,
                            "characters": [],
                            "props": ["empty coat hook"],
                            "source": "ai",
                        },
                        {
                            "n": 2,
                            "type": "MS",
                            "lens_mm": 35,
                            "height": "eye",
                            "angle": "straight",
                            "movement": "static",
                            "composition": "Tea mug resting on the coffee table beside the sofa.",
                            "lighting": "soft interior lamp",
                            "blocking": "table foreground",
                            "action": "Steam curls from the mug.",
                            "expression": "",
                            "dialogue": "",
                            "sound": "quiet",
                            "seconds": 4.0,
                            "transition": "cut",
                            "priority": 2,
                            "characters": [],
                            "props": ["tea mug"],
                            "source": "ai",
                        },
                    ],
                }
            ],
            "target_seconds": 12.0,
            "checks": {},
        },
    )
    # Step 17 keyframes_v2.json (S001-01 unlocked, S001-02 locked)
    (pd / "keyframes_v2.json").write_text(
        json.dumps({
            "prompts": {"S001-01": "Old prompt 1", "S001-02": "Locked prompt 2"},
            "locked": ["S001-02"],
        }),
        encoding="utf-8",
    )
    return pd


def test_step12_edit_camera_motion_and_subject_action_syncs_step17(tmp_path: Path):
    pd = _seed_project(tmp_path)

    # 1. Edit Camera & Motion with natural descriptive wording — must NOT fail clean_shot validation
    updated = shot_list.edit_shot(
        pd,
        "S001",
        1,
        {"camera_motion": "low, slow push in across the rug, warm table lamp glow"},
    )
    assert updated["height"] == "low"
    assert updated["movement"] == "push in"
    assert "warm table lamp glow" in updated["lighting"]
    assert updated["camera_notes"] == "low, slow push in across the rug, warm table lamp glow"

    # 2. Edit Subject & Action together — updates both composition and action
    updated2 = shot_list.edit_shot(
        pd,
        "S001",
        1,
        {"subject_action": "Subject: Low-angle living room view with Tommy on the rug.\nAction: Tommy opens his space sketchbook."},
    )
    assert updated2["composition"] == "Low-angle living room view with Tommy on the rug."
    assert updated2["action"] == "Tommy opens his space sketchbook."

    # 3. Sync unlocked shot edit to Step 17 keyframes_v2.json; locked shot stays untouched
    rep1 = continuity_sync.sync_shot_edit(
        pd,
        "test_book",
        scene_id="S001",
        shot_n=1,
        fields={"camera_motion": updated["camera_notes"], "subject_action": "updated"},
    )
    assert any("Step 17" in s for s in rep1["updated_steps"])
    kf = json.loads((pd / "keyframes_v2.json").read_text(encoding="utf-8"))
    assert "Tommy opens his space sketchbook" in kf["prompts"]["S001-01"]

    rep2 = continuity_sync.sync_shot_edit(
        pd,
        "test_book",
        scene_id="S001",
        shot_n=2,
        fields={"camera_motion": "high, crane, dramatic backlighting"},
    )
    assert rep2["preserved"]
    kf2 = json.loads((pd / "keyframes_v2.json").read_text(encoding="utf-8"))
    assert kf2["prompts"]["S001-02"] == "Locked prompt 2"


def test_step12_scene_set_and_props_context_injects_baselined_set(tmp_path: Path):
    pd = _seed_project(tmp_path)
    book = continuity_book.load(pd)
    ctx_txt = shot_list.scene_set_and_props_context(
        pd,
        {"heading": "INT. LIVING ROOM - AFTERNOON", "block": {"location": "living room"}},
        book,
    )
    assert "LOCKED BASELINED SET" in ctx_txt
    assert "round wooden dining table" in ctx_txt
    assert "No coffee table" in ctx_txt
    assert "tea mug" in ctx_txt


def test_early_prompt_audit_deterministic_all_steps(tmp_path: Path):
    pd = _seed_project(tmp_path)
    res = early_prompt_audit.audit_all_early_steps(
        pd,
        "test_book",
        use_llm=False,
        auto_apply=True,
        record_bidirectional=False,
    )
    assert res["ok"] is True
    steps = res["steps"]

    # Step 03 flags brief "Boy" description
    assert steps["3"]["issues_count"] >= 1
    # Step 04 flags tight 2 min runtime for 12 chapters
    assert steps["4"]["issues_count"] >= 1
    # Step 05 inherits blank time_of_day from S001 ("afternoon")
    assert steps["5"]["fixes_applied"] >= 1
    plan = adaptation.load(pd)
    assert plan is not None
    assert plan["scenes"][1]["time_of_day"] == "afternoon"
    # Step 06 fixes bare hook coat contradiction + dog "fills the frame" + flags living room dog bowl
    assert steps["6"]["fixes_applied"] >= 2
    s1 = screenplay.load_scene(pd, "S001")
    assert s1 is not None
    assert "coat hanging on it" not in s1["elements"][0]["text"].lower()
    assert "fills the frame" not in s1["elements"][1]["text"].lower()
    # Step 07 strips "3D Pixar" and appends dog/child relative height cues + flags "striped"
    assert steps["7"]["fixes_applied"] >= 3
    book = continuity_book.load(pd)
    tommy_tok = next(c["token"] for c in book["characters"] if c["name"] == "TOMMY")
    judah_tok = next(c["token"] for c in book["characters"] if c["name"] == "JUDAH")
    assert "pixar" not in tommy_tok.lower()
    assert "waist-high" in tommy_tok.lower()
    assert "knee-high" in judah_tok.lower()
    # Step 12 fixes bare hook & nonexistent coffee table via shot_continuity_audit
    assert steps["12"]["fixes_applied"] >= 2
    sl = shot_list.load(pd)
    assert "coat hanging on it" not in sl["scenes"][0]["shots"][0]["composition"].lower()
    assert "dining table" in sl["scenes"][0]["shots"][1]["composition"].lower()

    # Persisted report exists with all audited steps
    saved = early_prompt_audit.load_reports(pd)
    for k in ("3", "4", "5", "6", "7", "12"):
        assert k in saved["steps"]


def test_early_prompt_audit_ai_fixes_applied_and_persisted(tmp_path: Path):
    pd = _seed_project(tmp_path)

    def _fake_ai(prompt: str, *, use_llm: bool = True, timeout: float = 40.0):
        if "Step 03 (Coverage)" in prompt:
            return (
                {
                    "issues": [
                        {
                            "target": "TOMMY",
                            "field": "description",
                            "issue": "Clarify Tommy's age and height.",
                            "value": "5-year-old human boy (~3'6\" tall, waist-high to adults) with curly brown hair.",
                        }
                    ]
                },
                "gemini:gemini-3.8-flash",
            )
        if "Step 07 (Continuity Book)" in prompt:
            return (
                {
                    "fixes": [
                        {
                            "kind": "characters",
                            "name": "TOMMY",
                            "issue": "Replace striped shirt with solid red t-shirt.",
                            "token": "5-year-old human boy (~3'6\" tall, waist-high to adults), curly brown hair, solid red t-shirt, blue jeans, white sneakers",
                        }
                    ]
                },
                "gemini:gemini-3.8-flash",
            )
        return ({}, "gemini:gemini-3.8-flash")

    with mock.patch.object(early_prompt_audit, "_call_ai_json", side_effect=_fake_ai):
        r3 = early_prompt_audit.audit_step(pd, "test_book", 3, use_llm=True, auto_apply=True, record_bidirectional=False)
        r7 = early_prompt_audit.audit_step(pd, "test_book", 7, use_llm=True, auto_apply=True, record_bidirectional=False)

    assert r3["engine"] == "gemini:gemini-3.8-flash"
    assert r3["fixes_applied"] == 1
    cov = json.loads((pd / "readin" / "coverage.json").read_text(encoding="utf-8"))
    assert "5-year-old human boy" in cov["characters"][0]["description"]

    assert r7["engine"] == "gemini:gemini-3.8-flash"
    book = continuity_book.load(pd)
    tommy_tok = next(c["token"] for c in book["characters"] if c["name"] == "TOMMY")
    assert "solid red t-shirt" in tommy_tok


def test_auditor_scorecard_severity_ambiguity_guard_and_blind_spots(tmp_path: Path):
    pd = _seed_project(tmp_path)

    # Mock AI returning an AMBIGUOUS critical issue alongside a concrete minor fix:
    # the ambiguous item MUST NOT overwrite the original text even when auto_apply=True!
    def _fake_ai_amb(prompt: str, *, use_llm: bool = True, timeout: float = 40.0):
        return (
            {
                "fixes": [
                    {
                        "idx": 2,
                        "severity": "minor",
                        "issue": "Polish dialogue contraction.",
                        "risk": "Slightly stiff line.",
                        "ambiguous": False,
                        "text": "Let's head to Saturn!",
                    },
                    {
                        "idx": 0,
                        "severity": "critical",
                        "issue": "Unclear whether the coat was hung up before the scene began.",
                        "risk": "Could contradict prior scene intent.",
                        "ambiguous": True,
                        "text": "SHOULD NEVER BE APPLIED BECAUSE AMBIGUOUS",
                    },
                ],
                "blind_spots": ["Prior scene wardrobe handoff was not provided."],
            },
            "gemini:gemini-3.8-flash",
        )

    with mock.patch.object(early_prompt_audit, "_call_ai_json", side_effect=_fake_ai_amb):
        rep = early_prompt_audit.audit_step(pd, "test_book", 6, use_llm=True, auto_apply=True, record_bidirectional=False)

    assert rep["ok"] is True
    assert rep["ambiguous_count"] >= 1
    assert isinstance(rep["scorecard"], list) and len(rep["scorecard"]) >= 3
    assert all(c["rating"] in ("Pass", "Needs Work", "Fail") for c in rep["scorecard"])
    assert any("wardrobe handoff" in b.lower() for b in rep["blind_spots"])

    # Verify ambiguous replacement was NOT applied, while non-ambiguous fix WAS applied
    s1 = screenplay.load_scene(pd, "S001")
    assert s1 is not None
    assert "SHOULD NEVER BE APPLIED" not in s1["elements"][0]["text"]
    assert s1["elements"][2]["text"] == "Let's head to Saturn!"

    # Verify ambiguous/critical items sort to the top of issues
    assert rep["issues"][0]["ambiguous"] is True


def test_youtube_explainer_recipe_and_screenwriter_drafting_rules():
    import crew
    import read_it_in

    recipes = {r["name"]: r for r in crew.recipes()}
    assert "youtube_explainer" in recipes
    yt = recipes["youtube_explainer"]
    assert crew.recipe_problems(yt) == []
    assert "Hook -> Shock -> Validate -> Tease" in yt["prompt_rules"]["screenwriter"]
    assert "single-sentence CTA" in yt["prompt_rules"]["screenwriter"]

    # Anti-cliché natural dialogue rules are baked into first-draft screenplay generation
    assert "NATURAL HUMAN DIALOGUE" in read_it_in.ReadItIn.SCREEN_RULES
    assert "embarking" in read_it_in.ReadItIn.SCREEN_RULES

