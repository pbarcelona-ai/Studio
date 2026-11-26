"""Tests for Step 17 (Storyboard Keyframes) upstream cast, turnaround, style, set, and shotlist sync."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))


def _make_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Valid minimal >100-byte PNG-like payload so stat().st_size > 100 checks pass
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 256)


def _setup_mock_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    slug = "test_step17_book"
    pd = tmp_path / "projects" / "books" / slug
    pd.mkdir(parents=True, exist_ok=True)

    # Redirect character_tokens & studio_app project dir to tmp_path
    import character_tokens
    import run_gemini_omni
    from studio_app import projects as studio_projects
    from studio_app import routes_get, routes_post

    monkeypatch.setattr(character_tokens, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(character_tokens, "CHARACTERS_ROOT", tmp_path / "projects" / "characters")
    monkeypatch.setattr(run_gemini_omni, "get_gemini_api_key", lambda: "")
    monkeypatch.setattr(studio_projects, "pdir", lambda s, kind="book": tmp_path / "projects" / "books" / s)
    monkeypatch.setattr(routes_get, "pdir", lambda s, kind="book": tmp_path / "projects" / "books" / s)
    monkeypatch.setattr(routes_post, "pdir", lambda s, kind="book": tmp_path / "projects" / "books" / s)

    # Step 09 global_params.json with custom positives & negatives (no explicit "look" key)
    (pd / "global_params.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "positives": "warm storybook 3d animated film still, soft subsurface skin, rich color",
                "negatives": "photorealistic, live action, anime, flat 2d",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Continuity book with "the living room", "the starship bridge", "the Moon flyby", and props
    (pd / f"{slug}.json").write_text(
        json.dumps(
            {
                "title": "Test Adventure",
                "characters": [
                    {
                        "name": "MOM",
                        "token": "Mom, woman in her thirties, mustard cardigan, white t-shirt",
                    }
                ],
                "locations": [
                    {
                        "name": "the living room",
                        "token": "Living room, beige walls, wooden floor, round blue rug, rain-streaked window, dark TV",
                    },
                    {
                        "name": "the starship bridge",
                        "token": "Wide starship bridge, curved silver-gray walls, giant front viewscreen, gold captain's chair",
                    },
                    {
                        "name": "the Moon flyby",
                        "token": "Black starry space, gray cratered Moon filling the right half of frame",
                    },
                ],
                "props": [
                    {
                        "name": "Judah's bowl",
                        "token": "Round shiny steel dog bowl, empty and licked clean, by the kitchen doorframe",
                    },
                    {
                        "name": "the picture book",
                        "token": "Big hardcover blue picture book open to golden ringed Saturn",
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Step 08 character dossiers saved via character_tokens.save_character:
    # - Mom has bare visual_token="mom" + rich description (reproduces real-world bug!)
    # - TOMMY vs CAPTAIN TOMMY, JUDAH vs FIRST OFFICER JUDAH
    dossiers = [
        {
            "name": "Mom",
            "series": slug,
            "visual_token": "mom",
            "description": "Average woman with medium skin tone and dark hair tied back, in a black apron with Chef on the front.",
            "clothing": "",
            "consistency_notes": "Warmly encourages Tommy's play.",
        },
        {
            "name": "TOMMY",
            "series": slug,
            "visual_token": "TOMMY, 5-year-old boy, messy brown hair, solid brown t-shirt, blue jeans, white socks",
            "description": "",
        },
        {
            "name": "CAPTAIN TOMMY",
            "series": slug,
            "visual_token": "CAPTAIN TOMMY, 5-year-old boy, messy brown hair, solid gold tunic, solid black trousers, solid black boots",
            "description": "",
        },
        {
            "name": "JUDAH",
            "series": slug,
            "visual_token": "JUDAH, big black Labrador dog, shiny jet-black coat, solid red collar",
            "description": "",
        },
        {
            "name": "FIRST OFFICER JUDAH",
            "series": slug,
            "visual_token": "FIRST OFFICER JUDAH, big black Labrador dog, solid red collar, solid blue vest, silver star badge",
            "description": "",
        },
    ]
    for d in dossiers:
        character_tokens.save_character(d)

    # Step 10 Turnaround PNGs
    t_dir = pd / "assets" / "turnarounds"
    for fn in (
        "mom_front.png",
        "tommy_front.png",
        "captain_tommy_front.png",
        "judah_front.png",
        "first_officer_judah_front.png",
    ):
        _make_png(t_dir / fn)

    # Step 11 rendered set image for living room
    _make_png(pd / "assets" / "sets" / "living_room.png")

    # Step 12 shotlist.json
    shots_dir = pd / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    (shots_dir / "shotlist.json").write_text(
        json.dumps(
            {
                "scenes": [
                    {
                        "id": "S001",
                        "heading": "INT. LIVING ROOM - DAY",
                        "shots": [
                            {
                                "n": 1,
                                "type": "MS",
                                "lens_mm": 35,
                                "height": "low",
                                "angle": "three-quarter from frame left",
                                "movement": "pan",
                                "composition": "Mom sets the steel bowl by the doorway as Judah rushes in.",
                                "blocking": "Mom crouches beside the kitchen doorway; Judah bounds in from left.",
                                "action": "Judah lunges toward the bowl with wagging tail.",
                                "expression": "Mom fondly amused; Judah delighted",
                                "lighting": "Cool overcast window key from right",
                                "characters": ["MOM", "JUDAH"],
                                "props": ["Judah's bowl"],
                                "seconds": 4.0,
                            }
                        ],
                    },
                    {
                        "id": "S007",
                        "heading": "INT. STARSHIP BRIDGE - DAY",
                        "shots": [
                            {
                                "n": 2,
                                "type": "WS",
                                "lens_mm": 24,
                                "composition": "Cardboard walls expand into the starship bridge.",
                                "blocking": "Tommy sits at center in the chair, still in his solid brown t-shirt, blue jeans and white socks.",
                                "action": "The bridge materializes around him.",
                                "lighting": "Warm console glow",
                                "characters": ["TOMMY", "FIRST OFFICER JUDAH"],
                                "props": [],
                                "seconds": 4.0,
                            }
                        ],
                    },
                    {
                        "id": "S010",
                        "heading": "INT. STARSHIP BRIDGE - MOON FLYBY",
                        "shots": [
                            {
                                "n": 1,
                                "type": "WS",
                                "lens_mm": 28,
                                "composition": "Starship bridge crew watching the Moon outside the viewscreen.",
                                "blocking": "Tommy sits in the captain's chair in his gold tunic; Judah sits at his console.",
                                "action": "Tommy points at the Moon.",
                                "lighting": "Cool silver moonlight through viewscreen",
                                "characters": ["TOMMY", "JUDAH"],
                                "props": [],
                                "seconds": 4.0,
                            }
                        ],
                    },
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Simulate legacy broken saved prompt in keyframes_v2.json ("MOM: mom" + bare "LOCKED LOCATION: INT. LIVING ROOM - DAY.")
    (pd / "keyframes_v2.json").write_text(
        json.dumps(
            {
                "prompts": {
                    "S001-01": "old style, MS shot (35mm lens). LOCKED LOCATION: INT. LIVING ROOM - DAY. Mom sets bowl. LOCKED CHARACTERS & SINGULAR WARDROBE: MOM: mom; JUDAH: big black dog"
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return slug, pd


def test_step17_prompt_uses_full_cast_dossiers_sets_props_style_and_turnarounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug, _pd = _setup_mock_project(tmp_path, monkeypatch)
    from studio_app import routes_get

    class _FakeReq:
        def q(self, key: str) -> str:
            return slug if key == "project" else ""

    res = routes_get._v2_keyframes(_FakeReq())  # type: ignore[arg-type]
    scenes_by_id = {sc["id"]: sc for sc in res["scenes"]}

    # 1. S001-01: auto-heals broken "MOM: mom", uses full Step 08 Mom description,
    # matches "the living room" to "INT. LIVING ROOM - DAY", includes Step 09 positives,
    # includes Step 12 height/angle/blocking/expression + matched prop, and attaches turnarounds & set ref!
    s1_shot = scenes_by_id["S001"]["shots"][0]
    p1 = s1_shot["prompt"]
    assert s1_shot["auto_upgraded"] is True
    assert "warm storybook 3d animated film still" in p1
    assert "MOM: mom" not in p1
    assert "black apron with Chef on the front" in p1
    assert "LOCKED LOCATION (INT. LIVING ROOM - DAY): Living room, beige walls" in p1
    assert "Round shiny steel dog bowl" in p1
    assert "Blocking:" in p1
    assert "Expression: Mom fondly amused" in p1
    assert "low camera height" in p1
    assert "three-quarter from frame left" in p1

    ref_map = {cr["name"]: cr for cr in s1_shot["char_refs"]}
    assert ref_map["MOM"]["has_ref"] is True
    assert ref_map["MOM"]["ref_url"].endswith("/assets/turnarounds/mom_front.png")
    assert ref_map["JUDAH"]["has_ref"] is True
    assert ref_map["JUDAH"]["ref_url"].endswith("/assets/turnarounds/judah_front.png")
    assert s1_shot["set_ref_url"].endswith("/assets/sets/living_room.png")

    # 2. S007-02: pre-transformation shot explicitly says "still in his solid brown t-shirt",
    # so TOMMY stays TOMMY (not prematurely promoted to CAPTAIN TOMMY)!
    s7_shot = scenes_by_id["S007"]["shots"][0]
    assert "TOMMY" in s7_shot["characters"]
    assert "CAPTAIN TOMMY" not in s7_shot["characters"]
    assert "solid brown t-shirt" in s7_shot["prompt"]

    # 3. S010-01: starship bridge Moon flyby promotes TOMMY -> CAPTAIN TOMMY and JUDAH -> FIRST OFFICER JUDAH,
    # attaches captain_tommy_front.png + first_officer_judah_front.png, AND matches BOTH starship bridge & Moon flyby!
    s10_shot = scenes_by_id["S010"]["shots"][0]
    assert s10_shot["characters"] == ["CAPTAIN TOMMY", "FIRST OFFICER JUDAH"]
    p10 = s10_shot["prompt"]
    assert "solid gold tunic" in p10
    assert "solid blue vest" in p10
    assert "Wide starship bridge" in p10
    assert "gray cratered Moon" in p10
    ref_map10 = {cr["name"]: cr for cr in s10_shot["char_refs"]}
    assert ref_map10["CAPTAIN TOMMY"]["ref_url"].endswith("/assets/turnarounds/captain_tommy_front.png")
    assert ref_map10["FIRST OFFICER JUDAH"]["ref_url"].endswith("/assets/turnarounds/first_officer_judah_front.png")


def test_step17_render_attaches_turnarounds_prefers_ref_runner_and_allows_multiple_people(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug, pd = _setup_mock_project(tmp_path, monkeypatch)
    from studio_app import routes_post

    captured: dict[str, Any] = {}

    def _fake_sd_cli(
        prompt: str,
        out_png: Path,
        aspect_ratio: str = "16:9",
        model_id: str | None = None,
        ref_images: list[Path] | None = None,
        seed: int = -1,
        init_strength: float | None = None,
        init_image: Path | None = None,
        mask_image: Path | None = None,
        prefer_edit: bool = False,
        require_ref: bool = False,
        extra_negative: str = "",
        single_subject: bool | None = None,
    ) -> str:
        captured["prompt"] = prompt
        captured["aspect_ratio"] = aspect_ratio
        captured["ref_images"] = [p.name for p in (ref_images or [])]
        captured["seed"] = seed
        captured["init_strength"] = init_strength
        captured["init_image"] = init_image.name if init_image else ""
        captured["mask_image"] = mask_image.name if mask_image else ""
        captured["prefer_edit"] = prefer_edit
        captured["extra_negative"] = extra_negative
        captured["single_subject"] = single_subject
        _make_png(out_png)
        return "sd_cli:flux2-klein-4b"

    comfy_called = {"count": 0}

    def _fake_comfy(*_args: Any, **_kwargs: Any) -> str:
        comfy_called["count"] += 1
        return "comfyui:z-image"

    monkeypatch.setattr(routes_post, "_try_sd_cli_image", _fake_sd_cli)
    monkeypatch.setattr(routes_post, "_try_comfyui_image", _fake_comfy)
    monkeypatch.setattr(routes_post, "_inspect_keyframe_local_qa", lambda _p: {"passed": True, "issues": []})

    class _FakeReq:
        def __init__(self, body: dict[str, Any]) -> None:
            self.body = body

    res = routes_post._v2_keyframe_render(
        _FakeReq(
            {
                "project": slug,
                "id": "S001-01",
                "prompt": "MS shot of Mom and Judah in the living room.",
                "aspect_ratio": "16:9",
                "engine": "auto",
            }
        )
    )  # type: ignore[arg-type]

    # Must have used sd_cli (FLUX.2-klein-4B) FIRST instead of text-only ComfyUI z-image!
    assert res["model"] == "sd_cli:flux2-klein-4b"
    assert comfy_called["count"] == 0
    # Must attach BOTH character turnarounds + Step 11 set ref!
    assert "mom_front.png" in captured["ref_images"]
    assert "judah_front.png" in captured["ref_images"]
    assert "living_room.png" in captured["ref_images"]
    # Must include Reference Image Legend and Step 09 negatives, and NOT single_subject=True!
    assert "ATTACHED VISUAL REFERENCES" in captured["prompt"]
    assert "MOM character turnaround" in captured["prompt"]
    assert "JUDAH character turnaround" in captured["prompt"]
    assert "photorealistic" in captured["extra_negative"]
    assert captured["single_subject"] is False
    assert [c["name"] for c in res["char_refs_used"]] == ["MOM", "JUDAH"]
    assert (pd / "keyframes" / "S001-01.png").is_file()


def test_step17_sync_prompts_updates_unlocked_and_preserves_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug, pd = _setup_mock_project(tmp_path, monkeypatch)
    from studio_app import routes_post

    # Lock S001-01 so sync must preserve it while updating S007-02 and S010-01
    meta_path = pd / "keyframes_v2.json"
    meta_path.write_text(
        json.dumps({"locked": ["S001-01"], "prompts": {"S001-01": "LOCKED CUSTOM PROMPT"}}),
        encoding="utf-8",
    )

    class _FakeReq:
        def __init__(self, body: dict[str, Any]) -> None:
            self.body = body

    res = routes_post._v2_keyframe_sync_prompts(_FakeReq({"project": slug}))  # type: ignore[arg-type]
    assert res["updated"] == 2
    assert res["skipped_locked"] == 1
    saved = json.loads(meta_path.read_text(encoding="utf-8"))
    assert saved["prompts"]["S001-01"] == "LOCKED CUSTOM PROMPT"
    assert "solid gold tunic" in saved["prompts"]["S010-01"]
    assert "Wide starship bridge" in saved["prompts"]["S010-01"]


def test_step17_missing_set_plates_detection_scene_seed_same_angle_anchor_clone_and_mask_inpaint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import Image
    from studio_app import routes_get, routes_post

    slug, pd = _setup_mock_project(tmp_path, monkeypatch)

    # Remove Step 11 set plate to verify Step 17 flags missing set plates
    (pd / "assets" / "sets" / "living_room.png").unlink()

    # Add a second same-angle shot S001-02 and a third cut S001-03 to S001
    sl_path = pd / "shots" / "shotlist.json"
    sl = json.loads(sl_path.read_text(encoding="utf-8"))
    sl["scenes"][0]["shots"].append(
        {
            "n": 2,
            "type": "MS",
            "lens_mm": 35,
            "height": "low",
            "angle": "three-quarter from frame left",
            "movement": "static",
            "composition": "Same angle by the doorway; Judah licks the bowl clean.",
            "blocking": "Mom smiles while Judah licks the steel bowl.",
            "action": "Judah licks the bowl.",
            "expression": "Judah happy",
            "lighting": "Cool overcast window key from right",
            "characters": ["MOM", "JUDAH"],
            "props": ["Judah's bowl"],
            "seconds": 3.0,
        }
    )
    sl["scenes"][0]["shots"].append(
        {
            "n": 3,
            "type": "CU",
            "lens_mm": 85,
            "height": "eye",
            "angle": "reverse angle from kitchen",
            "movement": "static",
            "composition": "Reverse close-up on Mom smiling.",
            "blocking": "Mom looks back into living room.",
            "action": "Mom winks.",
            "expression": "Mom amused",
            "lighting": "Warm kitchen spill",
            "characters": ["MOM"],
            "props": [],
            "seconds": 3.0,
        }
    )
    sl_path.write_text(json.dumps(sl, indent=2), encoding="utf-8")

    class _FakeGet:
        def q(self, key: str) -> str:
            return slug if key == "project" else ""

    class _FakePost:
        def __init__(self, body: dict[str, Any]) -> None:
            self.body = body

    # 1. Missing set plates warning metadata
    kf_get = routes_get._v2_keyframes(_FakeGet())  # type: ignore[arg-type]
    assert kf_get["set_plates_count"] == 0
    assert "the living room" in kf_get["missing_set_plates"]
    s1_shots = kf_get["scenes"][0]["shots"]
    assert s1_shots[1]["camera_match_mode"] == "same_angle"
    assert s1_shots[1]["recommended_strength"] == 0.45
    assert s1_shots[2]["camera_match_mode"] == "scene_cut"

    # Write a real 128x128 PNG (>200 bytes) with deterministic blue pixels at (5,5) and (100,100)
    kf_dir = pd / "keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)
    base_im = Image.new("RGB", (128, 128), (20, 40, 200))
    for y in range(20, 40):
        for x in range(20, 40):
            base_im.putpixel((x, y), ((x * 7) % 255, (y * 11) % 255, 180))
    base_im.save(kf_dir / "S001-01.png", format="PNG")

    # 2. Pin S001-01 as Scene Anchor
    anc_res = routes_post._v2_keyframe_anchor(
        _FakePost({"project": slug, "scene": "S001", "shot_id": "S001-01"})
    )  # type: ignore[arg-type]
    assert anc_res["anchor_shot_id"] == "S001-01"

    # 3. Render S001-02 (same angle!) -> deterministic scene seed + auto img2img lock onto S001-01
    captured: dict[str, Any] = {}

    def _fake_sd_cli(
        prompt: str,
        out_png: Path,
        aspect_ratio: str = "16:9",
        model_id: str | None = None,
        ref_images: list[Path] | None = None,
        seed: int = -1,
        init_strength: float | None = None,
        init_image: Path | None = None,
        mask_image: Path | None = None,
        prefer_edit: bool = False,
        require_ref: bool = False,
        extra_negative: str = "",
        single_subject: bool | None = None,
    ) -> str:
        captured["prompt"] = prompt
        captured["seed"] = seed
        captured["init_strength"] = init_strength
        captured["init_image"] = init_image.name if init_image else ""
        captured["mask_image"] = mask_image.name if mask_image else ""
        captured["prefer_edit"] = prefer_edit
        captured["ref_images"] = [p.name for p in (ref_images or [])]
        # Write a 128x128 red image (>200 bytes) so mask-inpaint test can verify exact pixel compositing!
        red_im = Image.new("RGB", (128, 128), (220, 30, 30))
        for y in range(20, 40):
            for x in range(20, 40):
                red_im.putpixel((x, y), (200, (x * 5) % 255, (y * 9) % 255))
        red_im.save(out_png, format="PNG")
        return "sd_cli:flux2-klein-4b"

    monkeypatch.setattr(routes_post, "_try_sd_cli_image", _fake_sd_cli)
    monkeypatch.setattr(routes_post, "_inspect_keyframe_local_qa", lambda _p: {"passed": True, "issues": []})

    ren2 = routes_post._v2_keyframe_render(
        _FakePost({"project": slug, "id": "S001-02", "prompt": "Judah licks the bowl.", "engine": "auto"})
    )  # type: ignore[arg-type]
    assert ren2["continuity_mode"] == "same_angle"
    assert ren2["init_strength_used"] == 0.45
    assert ren2["seed_used"] > 0
    assert captured["init_image"] == "S001-01.png"
    assert captured["init_strength"] == 0.45
    assert "LOCKED CAMERA / IDENTICAL BACKGROUND" in captured["prompt"]

    # 4. Clone S001-01 into S001-03 (copy-only mode, then locked-camera pixel-identical mask inpaint!)
    cl_res = routes_post._v2_keyframe_clone_edit(
        _FakePost({"project": slug, "id": "S001-03", "source_id": "S001-01", "apply_edit": False})
    )  # type: ignore[arg-type]
    assert cl_res["source_id"] == "S001-01"
    assert cl_res["strength_used"] == 0.0
    assert Image.open(kf_dir / "S001-03.png").getpixel((5, 5)) == (20, 40, 200)

    # 5. Pixel-locked Masked Inpaint on S001-03: mask ONLY bottom-right box (0.5..1.0, 0.5..1.0) with feather=0
    inp_res = routes_post._v2_keyframe_mask_inpaint(
        _FakePost(
            {
                "project": slug,
                "id": "S001-03",
                "prompt": "Mom winks warmly",
                "regions": [{"type": "box", "bbox": {"x": 0.5, "y": 0.5, "width": 0.5, "height": 0.5}}],
                "feather_px": 0,
                "strength": 0.72,
            }
        )
    )  # type: ignore[arg-type]
    assert inp_res["regions_applied"] == 1
    assert inp_res["native_mask_used"] is True
    assert captured["mask_image"] == "S001-03_mask.png"
    assert captured["prefer_edit"] is True
    out_im = Image.open(kf_dir / "S001-03.png")
    # Outside mask (top-left) MUST stay 100% pixel-identical blue (20, 40, 200)!
    assert out_im.getpixel((5, 5)) == (20, 40, 200)
    # Inside mask (bottom-right) MUST receive the generated red (220, 30, 30)!
    assert out_im.getpixel((100, 100)) == (220, 30, 30)


def test_step17_set_plate_never_evicted_is_image_1_and_ignores_locked_dossier_mentions(tmp_path: Path):
    """Step 11 set plate must ALWAYS be reserved a slot (even with 4+ cast), lead as Image 1 on non-CU first shots,
    and never be crowded out by relative mentions like 'waist-high to Mom' inside another character's dossier."""
    from studio_app import keyframe_context

    slug = "set_priority_book"
    pd = tmp_path / "projects" / "books" / slug
    (pd / "assets" / "sets").mkdir(parents=True)
    (pd / "assets" / "turnarounds").mkdir(parents=True)
    (pd / "keyframes").mkdir(parents=True)
    (pd / "shots").mkdir(parents=True)

    _make_png(pd / "assets" / "sets" / "living_room_baseline.png")
    (pd / "sets_views.json").write_text(json.dumps({
        "sets": {
            "living room": {
                "name": "LIVING ROOM",
                "baseline_view_id": "main",
                "baseline_snapshot": "assets/sets/living_room_baseline.png",
                "views": [{"id": "main", "label": "Establishing", "converted_image": "assets/sets/living_room_baseline.png"}],
            }
        }
    }), encoding="utf-8")
    for ch in ("tommy", "judah", "kibble", "bits", "mom"):
        _make_png(pd / "assets" / "turnarounds" / f"{ch}_front.png")

    (pd / f"{slug}.json").write_text(json.dumps({
        "characters": [
            {"name": "TOMMY", "token": "5-year-old boy, waist-high to Mom, brown t-shirt, blue jeans"},
            {"name": "JUDAH", "token": "big black Labrador dog, red collar"},
            {"name": "KIBBLE", "token": "green plastic soldier action figure"},
            {"name": "BITS", "token": "floppy rag doll with blue sailor hat"},
            {"name": "MOM", "token": "woman with dark hair tied back"},
        ],
        "locations": [{"name": "LIVING ROOM", "token": "cozy living room with plaid blanket couch and floral rug"}],
    }), encoding="utf-8")

    sl = {
        "scenes": [{
            "id": "S002",
            "heading": "INT. LIVING ROOM - DAY",
            "shots": [
                {"n": 1, "type": "WS", "lens_mm": 24, "characters": ["TOMMY"], "action": "Tommy sits on the rug"},
                {"n": 2, "type": "WS", "lens_mm": 24, "characters": ["TOMMY", "JUDAH", "KIBBLE", "BITS", "MOM"], "action": "Everyone gathers in the living room"},
            ],
        }]
    }
    ctx = keyframe_context.load_keyframe_project_context(slug, pd)

    # 1. Solo Tommy shot with "waist-high to Mom" in LOCKED CHARACTERS block MUST NOT drag Mom in,
    #    and MUST place living_room_baseline.png as Image 1!
    solo_prompt = (
        "WS shot in the living room. Tommy sits on the rug. "
        "LOCKED CHARACTERS & TURNAROUND WARDROBE: TOMMY: 5-year-old boy, waist-high to Mom, brown t-shirt"
    )
    rp1 = keyframe_context.collect_render_references(ctx, "S002-01", solo_prompt, sl, pd / "keyframes", {})
    assert rp1["resolved_characters"] == ["TOMMY"]
    assert [p.name for p in rp1["ref_imgs"]] == ["living_room_baseline.png", "tommy_front.png"]
    assert rp1["set_ref_used"] is not None and rp1["set_ref_used"]["file"] == "living_room_baseline.png"
    assert "Image 1 = LOCKED STEP 11 SET PLATE" in rp1["ref_legend"]

    # 2. Crowd shot with 5 characters MUST STILL include living_room_baseline.png as Image 1 (never evicted!)
    rp2 = keyframe_context.collect_render_references(ctx, "S002-02", "Everyone gathers in the living room", sl, pd / "keyframes", {})
    assert rp2["ref_imgs"][0].name == "living_room_baseline.png"
    assert len(rp2["ref_imgs"]) == 4
    assert rp2["set_ref_used"] is not None


def test_interior_weather_guard_keeps_rain_outside_window_not_on_camera(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import character_tokens
    from studio_app import keyframe_context

    slug = "dry_interior_demo"
    pd = tmp_path / "projects" / "books" / slug
    (pd / "assets" / "sets").mkdir(parents=True, exist_ok=True)
    (pd / "keyframes").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(character_tokens, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(character_tokens, "CHARACTERS_ROOT", tmp_path / "projects" / "characters")

    _make_png(pd / "assets" / "sets" / "living_room_baseline.png")
    (pd / "sets_views.json").write_text(
        json.dumps({"sets": {"living room": {"name": "LIVING ROOM", "baseline_view_id": "main", "baseline_snapshot": "assets/sets/living_room_baseline.png", "views": []}}}),
        encoding="utf-8",
    )
    sl_data = {
        "scenes": [
            {
                "id": "S001",
                "heading": "INT. LIVING ROOM - DAY",
                "shots": [{"n": 1, "type": "WS", "composition": "Window on right with rain streaks outside.", "action": "Rain runs down the glass."}],
            }
        ]
    }
    ctx = keyframe_context.load_keyframe_project_context(slug, pd)
    pack = keyframe_context.collect_render_references(
        ctx,
        "S001-01",
        "WS shot in living room. Rain streaks on the right window.",
        sl_data,
        pd / "keyframes",
        {},
    )
    assert "DRY INDOOR ROOM & ARCHITECTURE LOCK" in pack["continuity_prefix"]
    assert "rain on camera lens" in pack["style_negatives"]
    assert "rain inside room" in pack["style_negatives"]
    assert "extra windows" in pack["style_negatives"]


def test_step17_breaks_insert_chaining_and_enforces_architectural_character_scale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import character_tokens
    from studio_app import keyframe_context

    slug = "clarity_scale_demo"
    pd = tmp_path / "projects" / "books" / slug
    (pd / "assets" / "sets").mkdir(parents=True, exist_ok=True)
    (pd / "assets" / "turnarounds").mkdir(parents=True, exist_ok=True)
    (pd / "keyframes").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(character_tokens, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(character_tokens, "CHARACTERS_ROOT", tmp_path / "projects" / "characters")

    _make_png(pd / "assets" / "sets" / "living_room_baseline.png")
    _make_png(pd / "assets" / "turnarounds" / "mom_front.png")
    _make_png(pd / "keyframes" / "S001-01.png")
    _make_png(pd / "keyframes" / "S001-02.png")
    _make_png(pd / "keyframes" / "S001-05.png")
    (pd / "sets_views.json").write_text(
        json.dumps({"sets": {"living room": {"name": "LIVING ROOM", "baseline_view_id": "main", "baseline_snapshot": "assets/sets/living_room_baseline.png", "views": []}}}),
        encoding="utf-8",
    )
    (pd / f"{slug}.json").write_text(
        json.dumps({"characters": [{"name": "MOM", "token": "Warm mother in her mid-30s wearing a charcoal apron"}]}),
        encoding="utf-8",
    )
    sl_data = {
        "scenes": [
            {
                "id": "S001",
                "heading": "INT. LIVING ROOM - DAY",
                "shots": [
                    {"n": 1, "type": "WS", "lens_mm": 32, "composition": "Wide view of the living room."},
                    {"n": 2, "type": "MS", "lens_mm": 40, "composition": "Medium view across the sofa and TV."},
                    {"n": 3, "type": "INSERT", "lens_mm": 65, "composition": "Close detail of the folded newspaper on the chair."},
                    {"n": 5, "type": "MCU", "lens_mm": 50, "composition": "Close detail of the empty coat hook."},
                    {"n": 6, "type": "MLS", "lens_mm": 35, "characters": ["MOM"], "composition": "Mom enters from the kitchen holding a bowl."},
                ],
            }
        ]
    }
    ctx = keyframe_context.load_keyframe_project_context(slug, pd)

    # 1. S001-03 (65mm INSERT after 40mm MS) MUST classify as scene_cut (no wide-room init_image smear!) and put crisp Set Plate first
    p3 = keyframe_context.collect_render_references(
        ctx,
        "S001-03",
        "LOCKED LOCATION (INT. LIVING ROOM - DAY): Big room. Close detail of the folded newspaper.",
        sl_data,
        pd / "keyframes",
        {},
    )
    assert p3["continuity_mode"] == "scene_cut"
    assert p3["init_image"] is None
    assert p3["ref_imgs"][0].name == "living_room_baseline.png"

    # 2. S001-06 (MLS introducing MOM after S001-05 MCU) MUST anchor to crisp Set Plate + S001-01 (NOT degraded S001-05!)
    #    AND inject the REAL-WORLD ARCHITECTURAL SCALE rule so MOM is never drawn giant!
    p6 = keyframe_context.collect_render_references(
        ctx,
        "S001-06",
        "MLS shot. Mom steps out of the kitchen doorway holding a mixing bowl.",
        sl_data,
        pd / "keyframes",
        {},
    )
    assert p6["continuity_mode"] == "scene_cut"
    assert p6["ref_imgs"][0].name == "living_room_baseline.png"
    assert "S001-05.png" not in [p.name for p in p6["ref_imgs"]]
    assert "REAL-WORLD ARCHITECTURAL SCALE" in p6["continuity_prefix"]
    assert "1.5–2 feet" in p6["continuity_prefix"]
    assert "giant character" in p6["style_negatives"]


