"""Tests for Step 11 Reference Photo Import, Film-Style Conversion, Multi-View Sets, and Baseline Locking."""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))


def _make_png_bytes(color: tuple[int, int, int]) -> bytes:
    from PIL import Image

    im = Image.new("RGB", (128, 128), color)
    for y in range(16, 40):
        for x in range(16, 40):
            im.putpixel((x, y), ((x * 7 + color[0]) % 255, (y * 11 + color[1]) % 255, color[2]))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_step11_import_real_photo_convert_to_3d_pixar_multiview_and_baseline_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import character_tokens
    import run_gemini_omni
    from studio_app import keyframe_context, routes_get, routes_post

    slug = "test_step11_sets"
    pd = tmp_path / "projects" / "books" / slug
    pd.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(character_tokens, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(character_tokens, "CHARACTERS_ROOT", tmp_path / "projects" / "characters")
    monkeypatch.setattr(run_gemini_omni, "get_gemini_api_key", lambda: "")
    monkeypatch.setattr(routes_get, "pdir", lambda s, kind="book": tmp_path / "projects" / "books" / s)
    monkeypatch.setattr(routes_post, "pdir", lambda s, kind="book": tmp_path / "projects" / "books" / s)

    # Step 09 global_params.json: 3D Pixar animated film style (NOT live action!)
    (pd / "global_params.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "positives": "3d animated feature film style, pixar stylized shapes, subsurface scattering, warm global illumination",
                "negatives": "photorealistic, live action, photograph, real people",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    calls: list[dict[str, Any]] = []

    def _fake_render(
        prompt: str,
        out_png: Path,
        aspect_ratio: str = "16:9",
        ref_images: list[Path] | None = None,
        engine: str = "auto",
        **kwargs: Any,
    ) -> str:
        calls.append(
            {
                "prompt": prompt,
                "out_png": out_png.name,
                "ref_images": [p.name for p in (ref_images or [])],
                "init_image": kwargs["init_image"].name if kwargs.get("init_image") else "",
                "init_strength": kwargs.get("init_strength"),
                "extra_negative": kwargs.get("extra_negative") or "",
                "prefer_edit": kwargs.get("prefer_edit"),
            }
        )
        out_png.parent.mkdir(parents=True, exist_ok=True)
        out_png.write_bytes(_make_png_bytes((30, 140, 210)))
        return "sd_cli:flux1-kontext-dev"

    monkeypatch.setattr(routes_post, "_render_keyframe_local_or_gemini", _fake_render)

    class _FakePost:
        def __init__(self, body: dict[str, Any]) -> None:
            self.body = body

    class _FakeGet:
        def q(self, key: str) -> str:
            return slug if key == "project" else ""

    # 1. Import a real living-room reference photo & associate with "the living room" (Establishing View) + convert to 3D Pixar!
    real_photo_b64 = "data:image/png;base64," + base64.b64encode(_make_png_bytes((180, 120, 80))).decode("ascii")
    up_res = routes_post._v2_set_ref_upload(
        _FakePost(
            {
                "project": slug,
                "name": "the living room",
                "view_id": "main",
                "view_label": "Establishing View",
                "filename": "real_living_room.png",
                "image_base64": real_photo_b64,
                "description": "Cozy living room with beige walls, blue rug, sofa, and rain-streaked window",
                "lighting": "Cool overcast daylight",
                "convert_now": True,
            }
        )
    )  # type: ignore[arg-type]

    assert up_res["ref_url"].endswith("/assets/sets/refs/the_living_room_main_ref.png")
    assert up_res["converted_url"].endswith("/assets/sets/the_living_room.png")
    assert len(calls) == 1
    c0 = calls[0]
    assert "STYLE CONVERSION FROM IMPORTED REFERENCE PHOTO" in c0["prompt"]
    assert "3d animated feature film style" in c0["prompt"]
    assert "raw photograph" in c0["extra_negative"]
    assert c0["ref_images"] == ["the_living_room_main_ref.png"]
    assert c0["init_image"] == "the_living_room_main_ref.png"
    assert c0["init_strength"] == 0.68

    # 2. Add a second view ("Kitchen Doorway") to the SAME location WITHOUT importing a reference photo
    routes_post._v2_set_view_save(
        _FakePost(
            {
                "project": slug,
                "name": "the living room",
                "label": "Kitchen Doorway",
                "notes": "Looking from the rug toward the doorway into the kitchen",
            }
        )
    )  # type: ignore[arg-type]

    # 3. Pin the converted "Establishing View" as the location's Baseline!
    base_res = routes_post._v2_set_baseline(
        _FakePost({"project": slug, "name": "the living room", "view_id": "main"})
    )  # type: ignore[arg-type]
    assert base_res["baseline_view_id"] == "main"
    assert base_res["baseline_url"].endswith("/assets/sets/the_living_room_baseline.png")

    # 4. Generate the second view ("Kitchen Doorway", which has NO imported photo) -> MUST use the baselined image!
    ren_v2 = routes_post._v2_set_render(
        _FakePost(
            {
                "project": slug,
                "name": "the living room",
                "view_id": "kitchen_doorway",
                "description": "Living room doorway leading to pale yellow kitchen",
                "lighting": "Overcast window key with warm kitchen spill",
            }
        )
    )  # type: ignore[arg-type]
    assert ren_v2["used_ref_photo"] is False
    assert ren_v2["used_baseline"] is True
    assert ren_v2["converted_url"].endswith("/assets/sets/the_living_room__view_kitchen_doorway.png")
    c1 = calls[1]
    assert c1["ref_images"] == ["the_living_room_baseline.png"]
    assert "SAME-LOCATION BASELINE CONTINUITY" in c1["prompt"]

    # 5. Re-run generation on the main view itself (with ref photo + active baseline) -> MUST attach BOTH ref photo AND baselined snapshot!
    ren_rerun = routes_post._v2_set_render(
        _FakePost(
            {
                "project": slug,
                "name": "the living room",
                "view_id": "main",
                "description": "Cozy living room, slightly warmer lamp glow",
            }
        )
    )  # type: ignore[arg-type]
    assert ren_rerun["used_ref_photo"] is True
    assert ren_rerun["used_baseline"] is True
    c2 = calls[2]
    assert "the_living_room_main_ref.png" in c2["ref_images"]
    assert "the_living_room_baseline.png" in c2["ref_images"]
    assert "BASELINE STYLE & PALETTE LOCK" in c2["prompt"]

    # 6. Verify GET /api/v2_sets_hidden returns BOTH imported photo & converted plate, both views, and baseline flag
    hid = routes_get._v2_sets_hidden(_FakeGet())  # type: ignore[arg-type]
    lr = hid["set_views"]["the living room"]
    assert lr["baseline_view_id"] == "main"
    by_vid = {v["id"]: v for v in lr["views"]}
    assert by_vid["main"]["has_ref"] is True
    assert by_vid["main"]["has_converted"] is True
    assert by_vid["main"]["is_baseline"] is True
    assert by_vid["kitchen_doorway"]["has_ref"] is False
    assert by_vid["kitchen_doorway"]["has_converted"] is True
    assert by_vid["kitchen_doorway"]["is_baseline"] is False

    # 7. Verify Step 17 context resolver automatically picks up the baselined Step 11 set plate!
    kf_ctx = keyframe_context.load_keyframe_project_context(slug, pd)
    assert kf_ctx["set_plates_count"] >= 1
    assert kf_ctx["set_images"]["living room"].name == "the_living_room_baseline.png"

    # 8. Delete ONLY the generated image of the second view ("kitchen_doorway") — preserves main view, baseline & set!
    del_v2 = routes_post._v2_set_image_delete(
        _FakePost({"project": slug, "name": "the living room", "view_id": "kitchen_doorway"})
    )  # type: ignore[arg-type]
    assert del_v2["removed"] >= 1
    assert del_v2["cleared_baseline"] is False
    assert not (pd / "assets" / "sets" / "the_living_room__view_kitchen_doorway.png").exists()
    assert (pd / "assets" / "sets" / "the_living_room.png").is_file()

    # 9. Delete ONLY the generated image of main view — preserves the imported reference photo & clears baseline snapshot!
    del_main = routes_post._v2_set_image_delete(
        _FakePost({"project": slug, "name": "the living room", "view_id": "main"})
    )  # type: ignore[arg-type]
    assert del_main["removed"] >= 1
    assert del_main["cleared_baseline"] is True
    assert not (pd / "assets" / "sets" / "the_living_room.png").exists()
    assert not (pd / "assets" / "sets" / "the_living_room_baseline.png").exists()
    # Imported reference photo MUST still be intact!
    assert (pd / "assets" / "sets" / "refs" / "the_living_room_main_ref.png").is_file()


def test_step11_set_conversion_strips_character_and_eye_terms_from_style(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import run_gemini_omni
    from studio_app import routes_post

    slug = "test_box_no_eyes"
    pd = tmp_path / "projects" / "books" / slug
    pd.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(run_gemini_omni, "get_gemini_api_key", lambda: "")
    monkeypatch.setattr(routes_post, "pdir", lambda s, kind="book": tmp_path / "projects" / "books" / s)

    # Real global_params.json containing character & eye descriptors
    (pd / "global_params.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "positives": "3d animated feature film style, stylised characters with large expressive eyes, soft rounded shapes, subsurface scattering, warm global illumination, rich saturated colour",
                "negatives": "photorealistic, live action, photograph",
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    def _fake_render(prompt: str, out_png: Path, **kwargs: Any) -> str:
        captured["prompt"] = prompt
        captured["extra_negative"] = kwargs.get("extra_negative") or ""
        out_png.parent.mkdir(parents=True, exist_ok=True)
        out_png.write_bytes(_make_png_bytes((200, 160, 120)))
        return "comfyui:flux2-klein-4b"

    monkeypatch.setattr(routes_post, "_render_keyframe_local_or_gemini", _fake_render)

    class _FakePost:
        def __init__(self, body: dict[str, Any]) -> None:
            self.body = body

    photo_b64 = "data:image/png;base64," + base64.b64encode(_make_png_bytes((190, 150, 110))).decode("ascii")
    routes_post._v2_set_ref_upload(
        _FakePost(
            {
                "project": slug,
                "name": "Box",
                "view_id": "main",
                "filename": "cardboard_box.png",
                "image_base64": photo_b64,
                "convert_now": True,
            }
        )
    )  # type: ignore[arg-type]

    prompt_low = captured["prompt"].lower()
    assert "3d animated feature film style" in prompt_low
    assert "warm global illumination" in prompt_low
    assert "large expressive eyes" not in prompt_low
    assert "stylised characters" not in prompt_low
    assert "window/door" not in prompt_low
    assert "strict fidelity" in prompt_low
    assert "googly eyes" in captured["extra_negative"].lower()

    # Also verify built-in minifigure / puppet / plush styles strip anatomy terms
    clean_lego = routes_post._sanitize_style_for_environment(
        "macro toy-brick miniature construction, glossy interlocking ABS plastic bricks, articulated plastic minifigure with molded hairpiece, printed expressive face, C-shaped hands, bright daylight specular highlights"
    )
    assert "glossy interlocking ABS plastic bricks" in clean_lego
    assert "minifigure" not in clean_lego.lower()
    assert "face" not in clean_lego.lower()
    assert "hands" not in clean_lego.lower()


def test_step11_baseline_image_to_text_syncs_steps_07_11_12_and_17(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import character_tokens
    from studio_app import routes_post, set_vision_sync

    slug = "vision_sync_book"
    pd = tmp_path / "projects" / "books" / slug
    (pd / "assets" / "sets").mkdir(parents=True, exist_ok=True)
    (pd / "shots").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(character_tokens, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(character_tokens, "CHARACTERS_ROOT", tmp_path / "projects" / "characters")
    monkeypatch.setattr(routes_post, "pdir", lambda s, kind="book": tmp_path / "projects" / "books" / s)

    # Seed Step 07 Continuity Book, Step 11 baselined image, Step 12 Shot List, and Step 17 Keyframes (with 1 locked!)
    (pd / f"{slug}.json").write_text(
        json.dumps(
            {
                "title": "Demo",
                "locations": [{"name": "the living room", "token": "Old tall window on left with beige curtains"}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (pd / "global_params.json").write_text(
        json.dumps({"positives": "3d animated feature film style, warm global illumination"}),
        encoding="utf-8",
    )
    (pd / "assets" / "sets" / "living_room.png").write_bytes(_make_png_bytes((90, 140, 180)))
    (pd / "sets_views.json").write_text(
        json.dumps(
            {
                "sets": {
                    "living room": {
                        "name": "LIVING ROOM",
                        "baseline_view_id": "",
                        "baseline_snapshot": "",
                        "views": [{"id": "main", "label": "Establishing View", "converted_image": "assets/sets/living_room.png"}],
                    }
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
                                "n": 1,
                                "type": "WS",
                                "composition": "Tall window on the left third with beige curtains, empty room.",
                                "action": "Rain patters on the glass.",
                                "lighting": "Cool gray light from left window",
                            },
                            {
                                "n": 2,
                                "type": "MS",
                                "composition": "Locked hero shot already approved.",
                                "action": "Tommy looks at the box.",
                                "lighting": "Warm interior",
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (pd / "keyframes_v2.json").write_text(
        json.dumps(
            {
                "locked": ["S001-02"],
                "prompts": {
                    "S001-01": "Old prompt with tall window on the left",
                    "S001-02": "LOCKED PROMPT MUST NOT CHANGE",
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        set_vision_sync,
        "describe_set_image",
        lambda img, name, **kw: {
            "ok": True,
            "engine": "gemini:gemini-2.5-flash",
            "description": "Open dining nook with wood ceiling on left, blue-gray sofa with peach pillows on a maroon floral rug in center, wood-trimmed window and flat-screen TV on right.",
            "lighting": "Warm golden interior lamp glow mixed with soft daylight from the right-wall window.",
            "layout_anchors": ["left: dining nook", "center: blue-gray sofa on floral rug", "right: TV and window"],
        },
    )
    monkeypatch.setattr(
        set_vision_sync,
        "reconcile_shot_compositions_with_set",
        lambda name, desc, light, payload, **kw: (
            {
                "S001-01": {
                    "composition": "Wide view showing the wood-trimmed right-wall window with rain streaks, blue-gray sofa on the maroon floral rug in center, and open dining nook on the left.",
                    "lighting": "Soft overcast daylight through the right-wall window.",
                }
            },
            "gemini:gemini-2.5-flash",
        ),
    )

    class _FakePost:
        def __init__(self, body: dict[str, Any]) -> None:
            self.body = body

    res = routes_post._v2_set_baseline(_FakePost({"project": slug, "name": "LIVING ROOM", "view_id": "main"}))  # type: ignore[arg-type]
    vs = res["vision_sync"]
    assert vs["ok"] is True
    assert vs["shots_reconciled"] == 1
    assert vs["keyframes_updated"] == 1
    assert vs["keyframes_skipped_locked"] == 1

    # Verify Step 07 Continuity Book updated
    cb_after = json.loads((pd / f"{slug}.json").read_text(encoding="utf-8"))
    assert "blue-gray sofa" in cb_after["locations"][0]["token"]

    # Verify Step 11 sets_custom.json updated
    sc_after = json.loads((pd / "sets_custom.json").read_text(encoding="utf-8"))
    assert "maroon floral rug" in sc_after["living room"]["description"]

    # Verify Step 12 Shot List reconciled
    sl_after = json.loads((pd / "shots" / "shotlist.json").read_text(encoding="utf-8"))
    assert "right-wall window" in sl_after["scenes"][0]["shots"][0]["composition"]

    # Verify Step 17 Keyframe S001-01 rebuilt with new set text AND locked S001-02 preserved untouched!
    kf_after = json.loads((pd / "keyframes_v2.json").read_text(encoding="utf-8"))
    assert "blue-gray sofa" in kf_after["prompts"]["S001-01"]
    assert "right-wall window" in kf_after["prompts"]["S001-01"]
    assert kf_after["prompts"]["S001-02"] == "LOCKED PROMPT MUST NOT CHANGE"

