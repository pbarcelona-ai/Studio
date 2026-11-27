"""Regression tests for photo import style conversion (Step 08 Cast & Step 11 Sets)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from studio_app import routes_post  # noqa: E402


def test_sd_cli_skips_double_lock_init_image_for_flux2_style_conversion(tmp_path: Path):
    ref_img = tmp_path / "kitchen_ref.jpg"
    ref_img.write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 512)
    out_png = tmp_path / "kitchen_out.png"

    captured_specs: list[dict] = []

    def _fake_run(spec: dict) -> dict:
        captured_specs.append(dict(spec))
        out_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 256)
        return {"ok": True, "model": "flux2-klein-4b", "output_path": str(out_png)}

    with mock.patch("local_runners.sd_cli_runner.SdCliRunner.is_installed", return_value=True), \
         mock.patch("local_runners.sd_cli_runner.SdCliRunner.ready_models", return_value=["flux2-klein-4b"]), \
         mock.patch("local_runners.sd_cli_runner.SdCliRunner.run", side_effect=_fake_run):
        # 1. Style conversion (>= 0.55) with same photo as ref & init MUST NOT pass init_image/strength
        model = routes_post._try_sd_cli_image(
            "3d animated feature film style conversion",
            out_png,
            aspect_ratio="16:9",
            ref_images=[ref_img],
            init_image=ref_img,
            init_strength=0.72,
            prefer_edit=True,
        )
        assert model == "sd_cli:flux2-klein-4b"
        assert captured_specs[0]["ref_images"] == [str(ref_img)]
        assert "init_image" not in captured_specs[0]
        assert "strength" not in captured_specs[0]

        # 2. Tight img2img lock (< 0.55) SHOULD keep init_image and strength
        routes_post._try_sd_cli_image(
            "tiny lighting tweak",
            out_png,
            aspect_ratio="16:9",
            ref_images=[ref_img],
            init_image=ref_img,
            init_strength=0.40,
            prefer_edit=True,
        )
        assert captured_specs[1]["init_image"] == str(ref_img)
        assert captured_specs[1]["strength"] == 0.40


def test_resolve_set_film_style_infers_look_from_global_params_positives(tmp_path: Path):
    for positives, expected_look in (
        ("plasticine claymation stop-motion handmade sets", "claymation"),
        ("japanese anime clean line art cel shading", "anime"),
        ("watercolour storybook soft washes paper texture", "watercolour"),
        ("3d animated feature film style soft rounded shapes", "pixar_3d"),
    ):
        pd = tmp_path / expected_look
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "global_params.json").write_text(
            json.dumps({"schema_version": 1, "positives": positives, "negatives": "photorealistic"}),
            encoding="utf-8",
        )
        look, pos, _neg, is_photo = routes_post._resolve_set_film_style(pd)
        assert look == expected_look
        assert pos
        assert is_photo is False


def test_set_import_converts_as_is_without_old_prompt_and_updates_prompt_via_vision(tmp_path: Path):
    import base64
    from studio_app import set_vision_sync, workflow_sync

    pd = tmp_path / "demo_book"
    pd.mkdir(parents=True, exist_ok=True)
    (pd / "global_params.json").write_text(
        json.dumps({"positives": "3d animated feature film style, soft rounded shapes", "negatives": "photorealistic"}),
        encoding="utf-8",
    )
    (pd / "adaptation").mkdir(parents=True, exist_ok=True)
    (pd / "adaptation" / "adaptation.json").write_text(
        json.dumps({"scenes": [{"id": "S001", "location": "Kitchen", "title": "Morning Kitchen", "summary": "Mom makes toast."}]}),
        encoding="utf-8",
    )
    (pd / "demo_book.json").write_text(
        json.dumps({
            "title": "Demo",
            "characters": [],
            "locations": [{"name": "Kitchen", "token": "OLD_YELLOW_WALLS_NEVER_USE"}],
            "props": [],
        }),
        encoding="utf-8",
    )
    (pd / "sets_custom.json").write_text(
        json.dumps({"kitchen": {"name": "Kitchen", "description": "OLD_YELLOW_WALLS_NEVER_USE", "lighting": "OLD_NEON_LIGHTING"}}),
        encoding="utf-8",
    )
    (pd / "shots").mkdir(parents=True, exist_ok=True)
    (pd / "shots" / "shotlist.json").write_text(
        json.dumps({
            "scenes": [{
                "id": "S001",
                "heading": "INT. KITCHEN - DAY",
                "shots": [{
                    "n": 1, "type": "WS", "lens_mm": 35, "height": "eye", "angle": "straight", "movement": "static",
                    "composition": "Wide view of the old yellow kitchen.", "lighting": "flat", "blocking": "", "action": "Mom pours tea.",
                    "characters": [], "props": [],
                }],
            }]
        }),
        encoding="utf-8",
    )
    (pd / "keyframes_v2.json").write_text(json.dumps({"prompts": {"S001-01": "OLD_YELLOW_WALLS_NEVER_USE"}, "locked": []}), encoding="utf-8")

    # Valid PNG > 100 bytes so size sanity check passes
    import io
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (120, 160, 130)).save(buf, format="PNG")
    png_bytes = buf.getvalue()
    b64 = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
    captured_prompts: list[str] = []

    def _fake_render(prompt: str, out_png: Path, *args, **kwargs) -> str:
        captured_prompts.append(prompt)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        out_png.write_bytes(png_bytes * 2)
        return "sd_cli:flux2-klein-4b"

    def _fake_vision(prompt: str, image_path: Path | None = None, *, timeout: float = 40.0):
        return (
            {
                "description": "Sage green kitchen with white microwave hutch, oak cabinets, red bread box, and granite counters.",
                "lighting": "Bright natural window daylight with warm under-cabinet lights.",
                "layout_anchors": ["left: white microwave hutch", "center: oak cabinets and red bread box"],
            },
            "ollama:qwen2.5vl",
        )

    with mock.patch.object(routes_post, "pdir", return_value=pd), \
         mock.patch.object(routes_post, "_render_keyframe_local_or_gemini", side_effect=_fake_render), \
         mock.patch.object(set_vision_sync, "_call_ollama_vision_json", side_effect=_fake_vision):
        res = routes_post._v2_set_ref_upload(
            routes_post.Request(
                query={},
                body={
                    "project": "demo_book",
                    "name": "Kitchen",
                    "view_id": "main",
                    "image_base64": b64,
                    "convert_now": True,
                    "description": "OLD_YELLOW_WALLS_NEVER_USE",
                    "lighting": "OLD_NEON_LIGHTING",
                },
            )
        )

    assert res["status"] == "ok"
    assert len(captured_prompts) == 1
    # Must convert image AS-IS without injecting the original pre-import prompt OR unrelated room/kitchen nouns
    assert "OLD_YELLOW_WALLS_NEVER_USE" not in captured_prompts[0]
    assert "OLD_NEON_LIGHTING" not in captured_prompts[0]
    low_prompt = captured_prompts[0].lower()
    for forbidden_noun in ("cabinet", "countertop", "appliance", "floor tile", "window", "furniture", "googly", "stickers"):
        assert forbidden_noun not in low_prompt, f"Subject-agnostic style prompt must not inject '{forbidden_noun}'"
    # Image-to-text automatically updated sets_custom.json and Continuity Book!
    assert res["vision_sync"]["ok"] is True
    assert "Sage green kitchen" in res["description"]
    sc = json.loads((pd / "sets_custom.json").read_text(encoding="utf-8"))
    assert "Sage green kitchen" in sc["kitchen"]["description"]
    cb = json.loads((pd / "demo_book.json").read_text(encoding="utf-8"))
    assert "Sage green kitchen" in cb["locations"][0]["token"]
    # Bi-directional update queued from earliest inception of Kitchen (Step 05 Beats)
    assert res["earliest_inception_step"] == 5
    q = workflow_sync.load_queue(pd)
    assert q["active"] is True
    q_steps = [it["step"] for it in q["items"]]
    assert 5 in q_steps and 7 in q_steps and 11 in q_steps
    # Step 17 unlocked keyframe prompt automatically updated with the new Sage green kitchen prompt!
    kf_set = json.loads((pd / "keyframes_v2.json").read_text(encoding="utf-8"))
    assert "Sage green kitchen" in kf_set["prompts"]["S001-01"]


def test_character_import_converts_as_is_and_updates_prompt_via_vision(tmp_path: Path):
    import base64
    import character_tokens
    from studio_app import set_vision_sync, workflow_sync

    # Place pd inside a fake projects/books/<slug> layout so relative_to(repo_root) works cleanly
    repo_root = tmp_path / "repo"
    pd = repo_root / "projects" / "books" / "demo_book"
    pd.mkdir(parents=True, exist_ok=True)
    (pd / "global_params.json").write_text(
        json.dumps({"positives": "3d animated feature film style, soft rounded shapes", "negatives": "photorealistic"}),
        encoding="utf-8",
    )
    (pd / "readin").mkdir(parents=True, exist_ok=True)
    (pd / "readin" / "coverage.json").write_text(
        json.dumps({"logline": "Tommy explores space.", "characters": [{"name": "Tommy", "role": "protagonist", "description": "Boy"}]}),
        encoding="utf-8",
    )
    (pd / "demo_book.json").write_text(
        json.dumps({
            "title": "Demo",
            "characters": [{"name": "TOMMY", "token": "OLD_RED_HAIR_GREEN_SHIRT_PROMPT"}],
            "locations": [],
            "props": [],
        }),
        encoding="utf-8",
    )
    (pd / "shots").mkdir(parents=True, exist_ok=True)
    (pd / "shots" / "shotlist.json").write_text(
        json.dumps({
            "scenes": [{
                "id": "S001",
                "heading": "INT. LIVING ROOM - DAY",
                "shots": [{
                    "n": 1, "type": "MS", "lens_mm": 35, "height": "eye", "angle": "straight", "movement": "static",
                    "composition": "Tommy sits on the rug.", "lighting": "soft", "blocking": "", "action": "Tommy smiles.",
                    "characters": ["TOMMY"], "props": [],
                }],
            }]
        }),
        encoding="utf-8",
    )
    (pd / "keyframes_v2.json").write_text(json.dumps({"prompts": {"S001-01": "OLD_RED_HAIR_GREEN_SHIRT_PROMPT"}, "locked": []}), encoding="utf-8")

    import io
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (80, 110, 160)).save(buf, format="PNG")
    png_bytes = buf.getvalue()
    b64 = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
    captured_prompts: list[str] = []
    saved_dossiers: list[dict] = []

    def _fake_render(prompt: str, out_png: Path, *args, **kwargs) -> str:
        captured_prompts.append(prompt)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        out_png.write_bytes(png_bytes * 2)
        return "sd_cli:flux2-klein-4b"

    def _fake_vision(prompt: str, image_path: Path | None = None, *, timeout: float = 40.0):
        return (
            {
                "description": "Photorealistic 5-year-old boy with curly brown hair wearing a navy hoodie and jeans.",
                "token": "5-year-old boy, curly brown hair, warm brown eyes, solid navy hoodie, blue jeans",
            },
            "ollama:qwen2.5vl",
        )

    with mock.patch.object(routes_post, "pdir", return_value=pd), \
         mock.patch.object(routes_post, "_render_keyframe_local_or_gemini", side_effect=_fake_render), \
         mock.patch.object(character_tokens, "load_character", return_value={"project": "demo_book", "name": "TOMMY", "description": "OLD_RED_HAIR_GREEN_SHIRT_PROMPT"}), \
         mock.patch.object(character_tokens, "save_character", side_effect=lambda rec: saved_dossiers.append(dict(rec))), \
         mock.patch.object(set_vision_sync, "_call_ollama_vision_json", side_effect=_fake_vision):
        res = routes_post._v2_character_ref_upload(
            routes_post.Request(
                query={},
                body={
                    "project": "demo_book",
                    "character": "TOMMY",
                    "image_base64": b64,
                    "convert_now": True,
                    "style_notes": "OLD_RED_HAIR_GREEN_SHIRT_PROMPT",
                },
            )
        )

    assert res["status"] == "ok"
    assert len(captured_prompts) == 1
    # Conversion prompt converts AS-IS without following old prompt or forcing full-body studio backdrop
    assert "OLD_RED_HAIR_GREEN_SHIRT_PROMPT" not in captured_prompts[0]
    assert "AS-IS" in captured_prompts[0]
    # Image-to-text updated Step 08 dossier & Step 07 Continuity Book (and stripped 'Photorealistic')
    assert res["vision_sync"]["ok"] is True
    assert "photorealistic" not in res["description"].lower()
    assert "navy hoodie" in res["token"].lower()
    assert any("navy hoodie" in str(d.get("visual_token") or "").lower() for d in saved_dossiers)
    cb = json.loads((pd / "demo_book.json").read_text(encoding="utf-8"))
    assert "navy hoodie" in cb["characters"][0]["token"].lower()
    # Bi-directional update queued from earliest inception of Tommy (Step 03 Coverage)
    assert res["earliest_inception_step"] == 3
    q = workflow_sync.load_queue(pd)
    assert q["active"] is True
    q_steps = [it["step"] for it in q["items"]]
    assert 3 in q_steps and 7 in q_steps and 8 in q_steps
    # Prompts automatically propagated to Step 03 Coverage AND Step 17 Keyframes!
    cov_after = json.loads((pd / "readin" / "coverage.json").read_text(encoding="utf-8"))
    assert "navy hoodie" in cov_after["characters"][0]["description"].lower()
    kf_char = json.loads((pd / "keyframes_v2.json").read_text(encoding="utf-8"))
    assert "navy hoodie" in kf_char["prompts"]["S001-01"].lower()

