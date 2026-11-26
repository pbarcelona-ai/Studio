"""Tests for surgical, bidirectional real-time continuity sync across Studio V2 steps."""
from __future__ import annotations

import json
from pathlib import Path

import adaptation as ad
import cast_lock
import character_tokens
import continuity_book
import continuity_sync as cs


def _seed_full_book(tmp_path: Path, slug: str = "saturn_book") -> Path:
    pd = tmp_path / "projects" / "books" / slug
    (pd / "adaptation").mkdir(parents=True)
    (pd / "screenplay").mkdir(parents=True)
    (pd / "shots").mkdir(parents=True)
    (pd / "readin").mkdir(parents=True)

    # Step 03 Coverage
    (pd / "readin" / "coverage.json").write_text(
        json.dumps({
            "logline": "A boy and his dog fly a cardboard rocket to Saturn.",
            "characters": [
                {"name": "Tommy", "description": "5-year-old boy in brown t-shirt"},
                {"name": "Judah", "description": "big black labrador dog"},
            ],
        }),
        encoding="utf-8",
    )

    # Step 05 Adaptation plan (2 scenes)
    (pd / "adaptation" / "adaptation.json").write_text(
        json.dumps({
            "logline": "A boy and his dog fly a cardboard rocket.",
            "scenes": [
                {"id": "S001", "title": "Kitchen Prep", "location": "Kitchen", "time_of_day": "DAY", "chapters": [1], "characters": ["Tommy", "Judah"], "seconds": 20, "summary": "Tommy eats lunch.", "act": 1},
                {"id": "S005", "title": "Saturn Launch", "location": "Cardboard Rocket", "time_of_day": "NIGHT", "chapters": [2], "characters": ["Tommy", "Judah"], "seconds": 30, "summary": "Tommy blasts off.", "act": 2},
            ],
        }),
        encoding="utf-8",
    )

    # Step 06 Screenplay
    (pd / "screenplay" / "scene-S001.json").write_text(
        json.dumps({
            "heading": "INT. KITCHEN - DAY",
            "elements": [
                {"type": "action", "text": "Tommy sits at the kitchen table."},
                {"type": "dialogue", "character": "Tommy", "note": "excited", "text": "We are going to Saturn!"},
            ],
        }),
        encoding="utf-8",
    )
    (pd / "screenplay" / "scene-S005.json").write_text(
        json.dumps({
            "heading": "INT. CARDBOARD ROCKET - NIGHT",
            "elements": [
                {"type": "action", "text": "Tommy grips the cardboard controls."},
                {"type": "dialogue", "character": "Tommy", "note": "commanding", "text": "Engage thrusters!"},
            ],
        }),
        encoding="utf-8",
    )

    # Step 07 Continuity Book
    cb_path = continuity_book.continuity_file(pd)
    cb_path.parent.mkdir(parents=True, exist_ok=True)
    cb_path.write_text(
        json.dumps({
            "characters": [
                {"name": "Tommy", "token": "5-year-old boy in brown t-shirt", "voice": "af_sky", "personality": {}},
                {"name": "Judah", "token": "big black labrador dog", "voice": "am_michael", "personality": {}},
            ],
            "locations": [
                {"name": "Kitchen", "token": "bright sunny family kitchen"},
                {"name": "Cardboard Rocket", "token": "brown cardboard spaceship"},
            ],
            "props": [],
        }),
        encoding="utf-8",
    )

    # Step 12 Shot List
    (pd / "shots" / "shotlist.json").write_text(
        json.dumps({
            "scenes": [
                {
                    "id": "S001",
                    "title": "Kitchen Prep",
                    "heading": "INT. KITCHEN - DAY",
                    "shots": [
                        {"n": 1, "type": "wide", "composition": "Tommy sits in the bright sunny family kitchen with Judah", "action": "Tommy waves", "characters": ["Tommy", "Judah"], "seconds": 4},
                    ],
                },
                {
                    "id": "S005",
                    "title": "Saturn Launch",
                    "heading": "INT. CARDBOARD ROCKET - NIGHT",
                    "shots": [
                        {"n": 1, "type": "medium", "composition": "Tommy stands at the cardboard console wearing brown t-shirt", "action": "Tommy pulls lever", "characters": ["Tommy"], "seconds": 4},
                        {"n": 2, "type": "close", "composition": "Tommy smiles as engines roar", "action": "Tommy grins", "characters": ["Tommy"], "seconds": 4},
                        {"n": 3, "type": "medium", "composition": "Judah barks happily near the hatch", "action": "Judah wags tail", "characters": ["Judah"], "seconds": 4},
                    ],
                },
            ],
        }),
        encoding="utf-8",
    )

    # Step 15 Dialogue Lines
    (pd / "dialogue_lines.json").write_text(
        json.dumps({
            "lines": [
                {"id": "S001-L01", "scene": "S001", "character": "Tommy", "text": "We are going to Saturn!", "note": "excited", "voice": "af_sky"},
                {"id": "S005-L01", "scene": "S005", "character": "Tommy", "text": "Engage thrusters!", "note": "commanding", "voice": "af_sky"},
            ],
        }),
        encoding="utf-8",
    )

    # Step 17 Keyframes (S005-02 is LOCKED!)
    (pd / "keyframes_v2.json").write_text(
        json.dumps({
            "locked": ["S005-02"],
            "prompts": {
                "S001-01": "Wide shot of Tommy (5-year-old boy in brown t-shirt) in the bright sunny family kitchen",
                "S005-01": "Medium shot of Tommy at the cardboard console",
                "S005-02": "Locked close-up of Tommy grinning",
                "S005-03": "Medium shot of Judah barking happily",
            },
        }),
        encoding="utf-8",
    )

    return pd


def test_scene_wardrobe_sync_is_surgical_and_preserves_untouched_and_locked(tmp_path):
    pd = _seed_full_book(tmp_path)

    # Change Tommy's wardrobe ONLY in S005 from Step 08
    rep = cs.sync_scene_wardrobe(
        pd,
        "saturn_book",
        character="Tommy",
        scene_spec="S005",
        location="Cardboard Rocket",
        wardrobe_text="gold captain tunic and black boots",
        source_step="step08",
    )
    assert "Step 07 (Scene Continuity Locks)" in rep["updated_steps"]
    assert "Step 12 (Shot List)" in rep["updated_steps"]
    assert "Step 17 (Storyboard Keyframes)" in rep["updated_steps"]
    assert any("S005-02" in p for p in rep["preserved"])

    # Step 07 cast_lock updated ONLY for Tommy in S005 — S001 and Judah untouched
    lock = cast_lock.load(pd)
    assert lock["S005"]["characters"]["Tommy"]["token"] == "gold captain tunic and black boots"
    assert "S001" not in lock
    assert "Judah" not in lock["S005"]["characters"]

    # Step 12 shotlist updated ONLY S005 Tommy shots — S001 and S005-03 (Judah) untouched
    sl = json.loads((pd / "shots" / "shotlist.json").read_text(encoding="utf-8"))
    s1_comp = sl["scenes"][0]["shots"][0]["composition"]
    s5_sh1, s5_sh2, s5_sh3 = sl["scenes"][1]["shots"]
    assert "gold captain tunic" not in s1_comp
    assert "gold captain tunic and black boots" in s5_sh1["composition"]
    assert "gold captain tunic and black boots" in s5_sh2["composition"]
    assert "gold captain tunic" not in s5_sh3["composition"]

    # Step 17 keyframes updated ONLY unlocked S005-01; locked S005-02, S001-01, and Judah S005-03 untouched!
    kf = json.loads((pd / "keyframes_v2.json").read_text(encoding="utf-8"))
    assert "gold captain tunic and black boots" in kf["prompts"]["S005-01"]
    assert kf["prompts"]["S005-02"] == "Locked close-up of Tommy grinning"
    assert "gold captain tunic" not in kf["prompts"]["S001-01"]
    assert "gold captain tunic" not in kf["prompts"]["S005-03"]

    # Reverse direction: editing S005 Tommy lock in Step 07 syncs back to Step 08 wardrobe_states.json!
    rep2 = cs.sync_scene_wardrobe(
        pd,
        "saturn_book",
        character="Tommy",
        scene_ids=["S005"],
        wardrobe_text="silver space suit with red cape",
        old_wardrobe="gold captain tunic and black boots",
        source_step="step07",
    )
    assert "Step 08 (Cast Wardrobe) & Step 10 (Turnarounds)" in rep2["updated_steps"]
    ws = json.loads((pd / "wardrobe_states.json").read_text(encoding="utf-8"))
    assert ws["Tommy"][0]["scenes"] == "S005"
    assert ws["Tommy"][0]["wardrobe"] == "silver space suit with red cape"
    # And S005-01 replaced the old wardrobe tag cleanly without duplicating tags!
    kf2 = json.loads((pd / "keyframes_v2.json").read_text(encoding="utf-8"))
    assert "silver space suit with red cape" in kf2["prompts"]["S005-01"]
    assert "gold captain tunic" not in kf2["prompts"]["S005-01"]


def test_character_profile_sync_preserves_unmodified_fields(tmp_path, monkeypatch):
    pd = _seed_full_book(tmp_path)
    monkeypatch.setattr(character_tokens, "CHARACTERS_ROOT", tmp_path / "projects" / "characters")
    character_tokens.save_character({
        "name": "Tommy",
        "series": "saturn_book",
        "visual_token": "5-year-old boy in brown t-shirt",
        "voice": "af_sky",
        "consistency_notes": "Always wears a bright grin",
        "reference_images": ["ref1.png"],
        "lora": {"repo": "user/tommy", "trained": True},
    })

    # Edit Tommy's visual token from Step 07 (leaving voice untouched)
    rep = cs.sync_character_profile(
        pd,
        "saturn_book",
        name="Tommy",
        old_token="5-year-old boy in brown t-shirt",
        new_token="5-year-old boy in striped red sweater",
        source_step="step07",
    )
    assert "Step 08 (Cast) & Step 10 (Turnarounds)" in rep["updated_steps"]
    assert "Step 03 (Coverage)" in rep["updated_steps"]
    assert "Step 17 (Storyboard Keyframes)" in rep["updated_steps"]

    # Step 08 dossier updated visual_token ONLY — lora, consistency_notes, voice, reference_images preserved!
    ch = character_tokens.load_character("saturn_book", "Tommy")
    assert ch is not None
    assert ch["visual_token"] == "5-year-old boy in striped red sweater"
    assert ch["voice"] == "af_sky"
    assert ch["consistency_notes"] == "Always wears a bright grin"
    assert ch["reference_images"] == ["ref1.png"]
    assert ch["lora"] == {"repo": "user/tommy", "trained": True}

    # Step 03 coverage updated Tommy ONLY — logline and Judah untouched!
    cov = json.loads((pd / "readin" / "coverage.json").read_text(encoding="utf-8"))
    assert cov["logline"] == "A boy and his dog fly a cardboard rocket to Saturn."
    assert cov["characters"][0]["description"] == "5-year-old boy in striped red sweater"
    assert cov["characters"][1]["description"] == "big black labrador dog"

    # Step 17 prompt replaced exact old phrase in S001-01 ONLY
    kf = json.loads((pd / "keyframes_v2.json").read_text(encoding="utf-8"))
    assert "5-year-old boy in striped red sweater" in kf["prompts"]["S001-01"]
    assert kf["prompts"]["S005-02"] == "Locked close-up of Tommy grinning"


def test_screenplay_and_location_and_shot_edits_propagate_surgically(tmp_path):
    pd = _seed_full_book(tmp_path)

    # 1. Step 06 Screenplay edit on S001: new location + new speaker + changed dialogue
    rep_sp = cs.sync_scene_edit(
        pd,
        "saturn_book",
        scene_id="S001",
        heading="INT. BACKYARD PATIO - MORNING",
        elements=[
            {"type": "dialogue", "character": "Tommy", "note": "grinning", "text": "Pack the snacks!"},
            {"type": "dialogue", "character": "Mom", "note": "warmly", "text": "Don't forget your helmet!"},
        ],
        source_step="step06",
    )
    assert "Step 05 (Story Breakdown) & Step 11 (Sets)" in rep_sp["updated_steps"]
    assert "Step 12 (Shot List)" in rep_sp["updated_steps"]
    assert "Step 15 (Spoken Dialogue)" in rep_sp["updated_steps"]

    # Step 05 S001 updated location & added Mom without removing Judah or touching S005!
    plan = ad.load(pd)
    assert plan is not None
    s1, s5 = plan["scenes"]
    assert s1["location"] == "BACKYARD PATIO"
    assert s1["time_of_day"] == "MORNING"
    assert "Mom" in s1["characters"] and "Judah" in s1["characters"]
    assert s5["location"] == "Cardboard Rocket"

    # Step 15 dialogue updated S001 lines ONLY — S005 line and S001 voice preserved!
    dlg = json.loads((pd / "dialogue_lines.json").read_text(encoding="utf-8"))
    s1_lines = [x for x in dlg["lines"] if x["scene"] == "S001"]
    s5_lines = [x for x in dlg["lines"] if x["scene"] == "S005"]
    assert [x["text"] for x in s1_lines] == ["Pack the snacks!", "Don't forget your helmet!"]
    assert s1_lines[0]["voice"] == "af_sky"
    assert s5_lines == [{"id": "S005-L01", "scene": "S005", "character": "Tommy", "text": "Engage thrusters!", "note": "commanding", "voice": "af_sky"}]

    # 2. Step 11 Location edit updates Step 07 Continuity Book & matching shots ONLY
    rep_loc = cs.sync_location_change(
        pd,
        "saturn_book",
        name="Kitchen",
        old_desc="bright sunny family kitchen",
        new_desc="cozy tiled yellow kitchen",
        lighting="warm morning sunlight",
        source_step="step11",
    )
    assert "Step 07 (Continuity Book)" in rep_loc["updated_steps"]
    cb = continuity_book.load(pd)
    k_loc = next(x for x in cb["locations"] if x["name"] == "Kitchen")
    r_loc = next(x for x in cb["locations"] if x["name"] == "Cardboard Rocket")
    assert "cozy tiled yellow kitchen" in k_loc["token"]
    assert r_loc["token"] == "brown cardboard spaceship"

    # 3. Step 12 Shot edit respects Step 17 locked keyframes
    rep_locked = cs.sync_shot_edit(pd, "saturn_book", scene_id="S005", shot_n=2, fields={"action": "Tommy jumps"})
    assert rep_locked["updated_steps"] == []
    assert any("S005-02" in p for p in rep_locked["preserved"])

    # Unlocked shot S005-01 DOES sync cleanly to Step 17
    sl = json.loads((pd / "shots" / "shotlist.json").read_text(encoding="utf-8"))
    sl["scenes"][1]["shots"][0]["action"] = "Tommy flips the red launch switch"
    (pd / "shots" / "shotlist.json").write_text(json.dumps(sl, indent=1), encoding="utf-8")
    rep_unlocked = cs.sync_shot_edit(pd, "saturn_book", scene_id="S005", shot_n=1, fields={"action": "Tommy flips the red launch switch"})
    assert "Step 17 (Storyboard Keyframes)" in rep_unlocked["updated_steps"]
    kf = json.loads((pd / "keyframes_v2.json").read_text(encoding="utf-8"))
    assert "Tommy flips the red launch switch" in kf["prompts"]["S005-01"]
    assert kf["prompts"]["S005-02"] == "Locked close-up of Tommy grinning"
