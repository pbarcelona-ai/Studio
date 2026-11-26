"""Tests for expanded Character Types / Visual Styles registry, Step 08 Cast Reference uploads,
Step 10 One-Click Restyle, and Single Prompts Reference-Conditioned Image & Video Generation."""
from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import patch

import character_tokens
import character_types_registry as ctr
import production
import pytest
from studio_app import routes_get, routes_post
from studio_app.api import Request


def _make_png_bytes(width: int = 32, height: int = 32, color: tuple[int, int, int] = (200, 120, 60)) -> bytes:
    """Create a real >100-byte valid PNG using Pillow (or OpenCV fallback)."""
    import io

    from PIL import Image

    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    # Ensure >100 bytes even for tiny solid images
    if len(data) <= 100:
        img = Image.new("RGB", (128, 128), color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
    return data


def _req(body: dict | None = None, query: dict | None = None) -> Request:
    q = {k: ([v] if isinstance(v, str) else list(v)) for k, v in (query or {}).items()}
    return Request(query=q, body=body or {}, path="/test")


class TestCharacterTypesRegistry:
    def test_builtin_styles_include_all_ten_from_character_types_txt(self):
        styles = ctr.list_styles()
        assert len(styles) >= 30
        by_id = {s["id"]: s for s in styles}
        required_ids = {
            "claymation",
            "anime",
            "pixel_art_16bit",
            "flat_vector",
            "comic_ink",
            "pixar_3d",
            "cartoon_2d",
            "retro_low_poly",
            "watercolour",
            "toy_bricks",
            "live_action",
        }
        assert required_ids.issubset(by_id.keys())
        for sid in required_ids:
            assert by_id[sid]["positives"].strip()
            assert by_id[sid]["motion_cadence"].strip()
            assert by_id[sid]["restyle_prompt"].strip()

    def test_builtin_archetypes_expanded_and_backwards_compatible(self):
        archetypes = ctr.list_archetypes()
        assert len(archetypes) >= 42
        # All original enum values remain valid
        for old_val in ("human", "child", "creature", "robot", "supernatural", "human_prophet", "angel_messenger", "divine_presence", "fallen_angel"):
            enum_member = character_tokens.CharacterArchetype(old_val)
            assert enum_member in character_tokens.ARCHETYPE_CONFIG
        # Expanded enum values also registered
        for new_val in ("minifigure", "rag_doll", "action_figure", "chibi", "mecha", "astronaut", "winged_dragon", "anthro_animal"):
            enum_member = character_tokens.CharacterArchetype(new_val)
            assert enum_member in character_tokens.ARCHETYPE_CONFIG

    def test_custom_style_and_archetype_persistence(self, tmp_path: Path):
        custom_file = tmp_path / "custom_character_types.json"
        saved_style = ctr.save_custom_style(
            {
                "name": "Papercraft Shadowbox",
                "category": "Custom",
                "positives": "layered paper-cut diorama, warm backlit shadows",
                "negatives": "photorealistic, glossy plastic",
                "motion_cadence": "stepped 12-fps sliding cardstock layers",
            },
            custom_path=custom_file,
        )
        assert saved_style["id"] == "papercraft_shadowbox"
        assert ctr.get_style("papercraft_shadowbox", custom_path=custom_file) is not None

        saved_arch = ctr.save_custom_archetype(
            {"name": "Clockwork Owl", "category": "Toys & Objects", "hint": "brass gears, ticking eyes"},
            custom_path=custom_file,
        )
        assert saved_arch["id"] == "clockwork_owl"
        all_arch_ids = {a["id"] for a in ctr.list_archetypes(custom_path=custom_file)}
        assert "clockwork_owl" in all_arch_ids

        # Sync into production.STYLES
        prod_styles = ctr.production_styles_dict(custom_path=custom_file)
        assert "papercraft_shadowbox" in prod_styles
        assert "claymation" in prod_styles
        assert "realistic" in prod_styles

    def test_production_refresh_styles_syncs_all(self):
        styles = production.refresh_styles()
        assert len(styles) >= 30
        assert "claymation" in production.STYLES
        assert "pixel_art_16bit" in production.STYLES
        assert "toy_bricks" in production.STYLES


class TestCastRefUploadAndTurnaroundRestyle:
    def test_upload_list_and_delete_cast_ref(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        # Redirect project root & character storage into tmp_path
        fake_root = tmp_path / "repo"
        book_dir = fake_root / "projects" / "books" / "demo_book"
        book_dir.mkdir(parents=True)
        monkeypatch.setattr(routes_post, "pdir", lambda slug, kind="book": fake_root / "projects" / "books" / slug)
        monkeypatch.setattr(routes_get, "pdir", lambda slug, kind="book": fake_root / "projects" / "books" / slug)
        monkeypatch.setattr(character_tokens, "CHARACTERS_ROOT", fake_root / "projects" / "characters")

        # Create character dossier first
        char = character_tokens.create_character_from_description("demo_book", "Captain Tommy", "7-year-old explorer", "tommy_tok")
        character_tokens.save_character(char)

        png_bytes = _make_png_bytes(64, 64, (40, 120, 210))
        b64_uri = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")

        res = routes_post._v2_character_ref_upload(
            _req({"project": "demo_book", "character": "Captain Tommy", "image_base64": b64_uri, "set_as_front": True})
        )
        assert res["status"] == "ok"
        assert res["seeded_front"] is True
        assert (book_dir / "assets" / "cast_refs" / "captain_tommy_ref.png").is_file()
        assert (book_dir / "assets" / "turnarounds" / "captain_tommy_front.png").is_file()

        # Verify character dossier updated with reference_images
        loaded = character_tokens.load_character("demo_book", "Captain Tommy")
        assert loaded is not None
        assert any("captain_tommy_ref.png" in x for x in loaded.get("reference_images", []))

        # Verify GET /api/v2_cast_references returns both Step 08 ref and Step 10 Front View
        listed = routes_get._v2_cast_references(_req(query={"project": "demo_book"}))
        sources = {r["source"] for r in listed["references"]}
        assert "Step 08 Reference" in sources
        assert "Step 10 Front View" in sources

        # Delete Step 08 ref
        del_res = routes_post._v2_character_ref_delete(_req({"project": "demo_book", "character": "Captain Tommy"}))
        assert del_res["removed"] == 1
        assert not (book_dir / "assets" / "cast_refs" / "captain_tommy_ref.png").is_file()

    def test_turnaround_restyle_requires_front_and_uses_ref(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        fake_root = tmp_path / "repo"
        book_dir = fake_root / "projects" / "books" / "demo_book"
        t_dir = book_dir / "assets" / "turnarounds"
        t_dir.mkdir(parents=True)
        front_png = t_dir / "judah_front.png"
        front_png.write_bytes(_make_png_bytes(64, 64, (90, 180, 110)))

        monkeypatch.setattr(routes_post, "pdir", lambda slug, kind="book": fake_root / "projects" / "books" / slug)

        captured: dict = {}

        def _fake_render(prompt, out_path, **kwargs):
            captured["prompt"] = prompt
            captured["kwargs"] = kwargs
            Path(out_path).write_bytes(_make_png_bytes(64, 64, (220, 90, 40)))
            return "local:sd-cli:flux2-klein-4b"

        monkeypatch.setattr(routes_post, "_render_keyframe_local_or_gemini", _fake_render)

        res = routes_post._v2_turnaround_restyle(
            _req({"project": "demo_book", "character": "Judah", "style_id": "toy_bricks"})
        )
        assert res["status"] == "ok"
        assert res["style_id"] == "toy_bricks"
        assert captured["kwargs"]["require_ref"] is True
        assert len(captured["kwargs"]["ref_images"]) == 1
        assert "ABS plastic bricks" in captured["prompt"]
        assert captured["kwargs"]["extra_negative"]


class TestSinglePromptReferenceRender:
    def test_single_prompt_image_with_uploaded_ref_and_style(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(routes_post, "ROOT", tmp_path)
        png_bytes = _make_png_bytes(64, 64, (180, 50, 90))
        b64_uri = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")

        captured: dict = {}

        def _fake_render(prompt, out_path, **kwargs):
            captured["prompt"] = prompt
            captured["out_path"] = Path(out_path)
            captured["kwargs"] = kwargs
            Path(out_path).write_bytes(_make_png_bytes(64, 64, (60, 200, 120)))
            return "local:sd-cli:flux2-klein-4b"

        monkeypatch.setattr(routes_post, "_render_keyframe_local_or_gemini", _fake_render)

        res = routes_post._v2_single_prompt_render(
            _req({
                "set": "cast_tests",
                "mode": "image",
                "prompt": "standing on Titan looking at Saturn's rings",
                "style_id": "claymation",
                "aspect_ratio": "16:9",
                "image_base64": b64_uri,
            })
        )
        assert res["status"] == "ok"
        assert res["mode"] == "image"
        assert res["used_reference"] is True
        assert res["image_url"].startswith("/file/cast_tests/images/single_")
        assert captured["kwargs"]["require_ref"] is True
        assert len(captured["kwargs"]["ref_images"]) == 1
        assert "plasticine clay" in captured["prompt"]

    def test_single_prompt_video_with_cast_ref_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(routes_post, "ROOT", tmp_path)
        cast_ref = tmp_path / "projects" / "books" / "mybook" / "assets" / "cast_refs" / "tommy_ref.png"
        cast_ref.parent.mkdir(parents=True)
        cast_ref.write_bytes(_make_png_bytes(128, 128, (30, 80, 190)))

        def _fake_render(prompt, out_path, **kwargs):
            Path(out_path).write_bytes(_make_png_bytes(128, 128, (30, 120, 220)))
            return "local:sd-cli:flux2-klein-4b"

        monkeypatch.setattr(routes_post, "_render_keyframe_local_or_gemini", _fake_render)

        # Force deterministic fast FFmpeg fallback without attempting heavy diffusers load
        with patch("local_runners.wan_diffusers_runner.WanDiffusersRunner.is_installed", return_value=False), \
             patch("local_runners.wan2gp_runner.Wan2GPRunner.is_installed", return_value=False):
            res = routes_post._v2_single_prompt_render(
                _req({
                    "set": "cast_vids",
                    "mode": "video",
                    "prompt": "waves hello inside a cozy spaceship",
                    "style_id": "pixel_art_16bit",
                    "duration": 2,
                    "ref_path": "projects/books/mybook/assets/cast_refs/tommy_ref.png",
                })
            )
        assert res["status"] == "ok"
        assert res["mode"] == "video"
        assert res["used_reference"] is True
        assert res["video_url"].startswith("/file/cast_vids/videos/single_")
        assert res["start_frame_url"].startswith("/file/cast_vids/images/single_")
        vid_files = list((tmp_path / "projects" / "prompts" / "cast_vids" / "videos").glob("single_*.mp4"))
        assert len(vid_files) == 1
        assert vid_files[0].stat().st_size > 1000
