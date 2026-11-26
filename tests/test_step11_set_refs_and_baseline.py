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

