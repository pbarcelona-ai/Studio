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


def test_step6_needs_decision_includes_line_highlight_options_and_resolves(tmp_path: Path):
    pd = _seed_project(tmp_path)
    # Seed readin/screenplay.json to verify mirroring as well
    (pd / "readin" / "screenplay.json").write_text(
        json.dumps(
            {
                "scenes": [
                    {
                        "heading": "INT. LIVING ROOM - AFTERNOON",
                        "elements": [
                            {"type": "action", "text": "An empty coat hook sits by the door, with the rain coat hanging on it."},
                            {"type": "action", "text": "Judah the dog fills the frame beside Mom while his dog bowl sits on the carpet."},
                            {"type": "dialogue", "character": "TOMMY", "text": "Let's go to Saturn!"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    rep = early_prompt_audit.audit_step(pd, "test_book", 6, use_llm=False, auto_apply=True, record_bidirectional=False)
    assert rep["ok"] is True
    pending = [it for it in rep["issues"] if it.get("ambiguous") or it.get("needs_user_decision")]
    assert len(pending) >= 1
    bowl_issue = next(it for it in pending if "dog/food bowl" in it["issue"].lower())
    assert bowl_issue["scene_id"] == "S001"
    assert bowl_issue["line_index"] == 1
    assert "dog bowl" in bowl_issue["current_text"].lower()
    assert bowl_issue["highlight"].lower() == "dog bowl"
    assert len(bowl_issue["options"]) >= 2
    assert all(opt.get("label") and opt.get("replacement_text") for opt in bowl_issue["options"])

    # Apply the first recommended option
    chosen = bowl_issue["options"][0]
    res = early_prompt_audit.resolve_audit_decision(
        pd,
        "test_book",
        step_num=6,
        target=bowl_issue["target"],
        scene_id=bowl_issue["scene_id"],
        line_index=bowl_issue["line_index"],
        field=bowl_issue["field"],
        issue_text=bowl_issue["issue"],
        replacement_text=chosen["replacement_text"],
        option_label=chosen["label"],
        keep_original=False,
        record_bidirectional=False,
    )
    assert res["ok"] is True
    assert res["applied_file"] == "screenplay/scene-S001.json"
    assert res["report"]["ambiguous_count"] == 0

    # Verify screenplay scene file & readin mirror both updated
    s1 = screenplay.load_scene(pd, "S001")
    assert s1 is not None
    assert s1["elements"][1]["text"] == chosen["replacement_text"]
    assert s1.get("edited") is True
    readin_sp = json.loads((pd / "readin" / "screenplay.json").read_text(encoding="utf-8"))
    assert readin_sp["scenes"][0]["elements"][1]["text"] == chosen["replacement_text"]

    # Verify persisted report marks the exact ambiguous finding resolved
    saved = early_prompt_audit.load_reports(pd)
    step6_saved = saved["steps"]["6"]
    assert step6_saved["ambiguous_count"] == 0
    resolved_bowl = next(it for it in step6_saved["issues"] if "dog/food bowl" in it["issue"].lower())
    assert resolved_bowl["ambiguous"] is False
    assert resolved_bowl["fixed"] is True
    assert resolved_bowl["resolved_by"] == "user"


def test_step6_resolve_keep_original_dismisses_without_modifying_line(tmp_path: Path):
    pd = _seed_project(tmp_path)

    def _fake_ai_conflict(prompt: str, *, use_llm: bool = True, timeout: float = 40.0):
        return (
            {
                "fixes": [
                    {
                        "idx": 2,
                        "severity": "major",
                        "issue": "Dialogue mentions Saturn while the beat sheet says Mars.",
                        "risk": "Prop labels and narration could conflict on planet destination.",
                        "ambiguous": True,
                        "highlight": "Saturn",
                        "options": [
                            {
                                "label": "Change destination to Mars",
                                "summary": "Matches Step 05 beat sheet.",
                                "replacement_text": "Let's go to Mars!",
                            },
                            {
                                "label": "Keep Saturn in screenplay",
                                "summary": "Keeps Tommy's line as written and implies updating the beat sheet.",
                                "replacement_text": "Let's go to Saturn!",
                            },
                        ],
                    }
                ],
                "blind_spots": [],
            },
            "gemini:test",
        )

    with mock.patch.object(early_prompt_audit, "_call_ai_json", side_effect=_fake_ai_conflict):
        rep = early_prompt_audit.audit_step(pd, "test_book", 6, use_llm=True, auto_apply=True, record_bidirectional=False)

    saturn_issue = next(it for it in rep["issues"] if "saturn" in it["issue"].lower())
    assert saturn_issue["highlight"] == "Saturn"
    assert saturn_issue["current_text"] == "Let's go to Saturn!"
    assert saturn_issue["character"] == "TOMMY"
    assert len(saturn_issue["options"]) == 2

    res = early_prompt_audit.resolve_audit_decision(
        pd,
        "test_book",
        step_num=6,
        target=saturn_issue["target"],
        scene_id=saturn_issue["scene_id"],
        line_index=saturn_issue["line_index"],
        issue_text=saturn_issue["issue"],
        keep_original=True,
        option_label="Kept original line",
        record_bidirectional=False,
    )
    assert res["ok"] is True
    assert res["keep_original"] is True
    s1 = screenplay.load_scene(pd, "S001")
    assert s1 is not None
    assert s1["elements"][2]["text"] == "Let's go to Saturn!"
    saved = early_prompt_audit.load_reports(pd)
    resolved = next(it for it in saved["steps"]["6"]["issues"] if "saturn" in it["issue"].lower())
    assert resolved["ambiguous"] is False
    assert resolved["resolved_by"] == "user"


def test_all_audit_steps_have_conflict_options_and_resolve_across_steps(tmp_path: Path):
    pd = _seed_project(tmp_path)

    # Step 03 Coverage: brief description "Boy" triggers [Needs Decision] with highlight + options, and resolves cleanly
    r3 = early_prompt_audit.audit_step(pd, "test_book", 3, use_llm=False, auto_apply=True, record_bidirectional=False)
    it3 = next(it for it in r3["issues"] if it.get("ambiguous"))
    assert it3["current_text"] == "Boy"
    assert it3["highlight"] == "Boy"
    assert len(it3["options"]) >= 2
    res3 = early_prompt_audit.resolve_audit_decision(
        pd,
        "test_book",
        step_num=3,
        target=it3["target"],
        field=it3["field"],
        issue_text=it3["issue"],
        replacement_text=it3["options"][1]["replacement_text"],
        option_label=it3["options"][1]["label"],
        record_bidirectional=False,
    )
    assert res3["ok"] is True
    assert res3["report"]["ambiguous_count"] == 0
    cov = json.loads((pd / "readin" / "coverage.json").read_text(encoding="utf-8"))
    assert "child" in cov["characters"][0]["description"].lower()

    # Step 04 Scope: tight runtime triggers [Needs Decision] with highlight + options, and updates production.json
    r4 = early_prompt_audit.audit_step(pd, "test_book", 4, use_llm=False, auto_apply=True, record_bidirectional=False)
    it4 = next(it for it in r4["issues"] if it.get("ambiguous"))
    assert it4["highlight"] in ("6", "10")
    assert len(it4["options"]) >= 2
    res4 = early_prompt_audit.resolve_audit_decision(
        pd,
        "test_book",
        step_num=4,
        target=it4["target"],
        field=it4["field"],
        issue_text=it4["issue"],
        replacement_text=it4["options"][0]["replacement_text"],
        option_label=it4["options"][0]["label"],
        record_bidirectional=False,
    )
    assert res4["ok"] is True
    prod = json.loads((pd / "production.json").read_text(encoding="utf-8"))
    assert float(prod["target_minutes"]) >= 18.0

    # Step 05 Beats: missing location triggers [Needs Decision] and updates adaptation.json
    plan = adaptation.load(pd)
    assert plan is not None
    plan["scenes"][1]["location"] = ""
    adaptation.save(pd, plan)
    r5 = early_prompt_audit.audit_step(pd, "test_book", 5, use_llm=False, auto_apply=True, record_bidirectional=False)
    it5 = next(it for it in r5["issues"] if it.get("ambiguous") and it.get("field") == "location")
    assert it5["scene_id"] == "S002"
    assert len(it5["options"]) >= 2
    res5 = early_prompt_audit.resolve_audit_decision(
        pd,
        "test_book",
        step_num=5,
        target=it5["target"],
        scene_id=it5["scene_id"],
        field=it5["field"],
        issue_text=it5["issue"],
        replacement_text=it5["options"][0]["replacement_text"],
        option_label=it5["options"][0]["label"],
        record_bidirectional=False,
    )
    assert res5["ok"] is True
    plan2 = adaptation.load(pd)
    assert plan2 is not None
    assert plan2["scenes"][1]["location"] == "living room"

    # Step 07 Continuity Book: striped shirt triggers [Needs Decision] and updates continuity book token
    r7 = early_prompt_audit.audit_step(pd, "test_book", 7, use_llm=False, auto_apply=True, record_bidirectional=False)
    it7 = next(it for it in r7["issues"] if it.get("ambiguous"))
    assert it7["highlight"].lower() == "striped"
    res7 = early_prompt_audit.resolve_audit_decision(
        pd,
        "test_book",
        step_num=7,
        target=it7["target"],
        field="token",
        issue_text=it7["issue"],
        replacement_text=it7["options"][0]["replacement_text"],
        option_label=it7["options"][0]["label"],
        record_bidirectional=False,
    )
    assert res7["ok"] is True
    book = continuity_book.load(pd)
    tommy_tok = next(c["token"] for c in book["characters"] if c["name"] == "TOMMY")
    assert "solid" in tommy_tok.lower()

    # Step 12 / Step 17 Shot List: mocked ambiguous shot finding resolves shotlist.json & syncs unlocked keyframes_v2.json
    from studio_app import shot_continuity_audit

    def _fake_shot_llm(prompt: str, img: object = None, timeout: float = 45.0):
        return (
            {
                "fixes": [
                    {
                        "n": 1,
                        "field": "composition",
                        "severity": "major",
                        "issue": "Unclear whether the coat hook is left or right of the front door.",
                        "risk": "Doorway wall flips between shots.",
                        "ambiguous": True,
                        "highlight": "empty coat hook",
                        "options": [
                            {
                                "label": "Place bare hook left of the doorway",
                                "summary": "Matches entry hallway layout.",
                                "replacement_text": "Wide view of the living room with the empty coat hook mounted left of the front door.",
                            },
                            {
                                "label": "Place bare hook right of the doorway",
                                "summary": "Matches staircase wall layout.",
                                "replacement_text": "Wide view of the living room with the empty coat hook mounted right of the front door.",
                            },
                        ],
                    }
                ],
                "blind_spots": [],
            },
            "gemini:test",
        )

    with mock.patch("studio_app.set_vision_sync._call_ollama_vision_json", side_effect=_fake_shot_llm):
        r12 = early_prompt_audit.audit_step(pd, "test_book", 12, use_llm=True, auto_apply=True, record_bidirectional=False)
    it12 = next(it for it in r12["issues"] if it.get("ambiguous"))
    assert it12["target"] == "S001-01"
    assert it12["highlight"] == "empty coat hook"
    assert len(it12["options"]) == 2
    res17 = early_prompt_audit.resolve_audit_decision(
        pd,
        "test_book",
        step_num=17,  # Step 17 maps cleanly onto Step 12 shot list + Step 17 unlocked keyframes
        target=it12["target"],
        scene_id=it12["scene_id"],
        line_index=it12["line_index"],
        field=it12["field"],
        issue_text=it12["issue"],
        replacement_text=it12["options"][0]["replacement_text"],
        option_label=it12["options"][0]["label"],
        record_bidirectional=False,
    )
    assert res17["ok"] is True
    assert res17["applied_file"] == "shots/shotlist.json"
    sl = shot_list.load(pd)
    assert "left of the front door" in sl["scenes"][0]["shots"][0]["composition"]
    kf = json.loads((pd / "keyframes_v2.json").read_text(encoding="utf-8"))
    assert "left of the front door" in kf["prompts"]["S001-01"]
    _ = shot_continuity_audit


def test_step6_save_all_scenes_and_all_resolve_buttons_present_in_html(tmp_path: Path):
    from studio_app import adapt

    pd = _seed_project(tmp_path)
    # Seed a second scene so save_all_scenes saves multiple scripts in one call
    screenplay.save_scene(
        pd,
        "S002",
        {
            "heading": "INT. LIVING ROOM - LATER",
            "elements": [{"type": "dialogue", "character": "MOM", "text": "Tea is ready."}],
        },
        edited=False,
    )
    with mock.patch.object(adapt, "_book", return_value=pd):
        res = adapt.screenplay_edit(
            {
                "project": "test_book",
                "action": "save_all_scenes",
                "scenes": [
                    {
                        "scene": "S001",
                        "heading": "INT. LIVING ROOM - RAINY AFTERNOON",
                        "elements": [{"type": "dialogue", "character": "TOMMY", "text": "Ready for launch!"}],
                    },
                    {
                        "scene": "S002",
                        "heading": "INT. LIVING ROOM - DUSK",
                        "elements": [{"type": "dialogue", "character": "MOM", "text": "Hot cocoa is ready."}],
                    },
                ],
            }
        )
    assert res["saved_count"] == 2
    s1 = screenplay.load_scene(pd, "S001")
    s2 = screenplay.load_scene(pd, "S002")
    assert s1 is not None and s2 is not None
    assert s1["heading"] == "INT. LIVING ROOM - RAINY AFTERNOON"
    assert s1["elements"][0]["text"] == "Ready for launch!"
    assert s2["heading"] == "INT. LIVING ROOM - DUSK"
    assert s2["elements"][0]["text"] == "Hot cocoa is ready."

    html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="v2SpSaveAll"' in html
    assert 'id="v2BeatsSaveAll"' not in html
    for step_id in ("3", "4", "5", "6", "7", "12", "17"):
        assert f'data-resolve-step="{step_id}"' in html



