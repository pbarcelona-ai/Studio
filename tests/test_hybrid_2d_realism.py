"""Tests for expanded 45+ visual styles, 65+ character archetypes, 3-Panel Pro Character Sheets,
Step 11 Set Gap Planning, Step 17 Two-Pass 2D-Meets-Realism Keyframes, Step 18 Two-Pass Video Prompts,
and Multi-Reference Single Prompts."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import character_tokens
import character_types_registry as ctr
import pytest
from PIL import Image
from studio_app import projects as studio_projects
from studio_app import routes_get, routes_post
from studio_app.api import Request


def _png_bytes(color: tuple[int, int, int] = (120, 160, 200)) -> bytes:
    img = Image.new("RGB", (128, 128), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _req(body: dict | None = None, query: dict | None = None) -> Request:
    q = {k: ([v] if isinstance(v, str) else list(v)) for k, v in (query or {}).items()}
    return Request(query=q, body=body or {}, path="/test")


class TestExpandedCatalog:
    def test_styles_and_archetypes_counts(self):
        styles = ctr.list_styles()
        archetypes = ctr.list_archetypes()
        assert len(styles) >= 45
        assert len(archetypes) >= 65
        style_ids = {s["id"] for s in styles}
        for needed in (
            "vintage_1940s_2d",
            "hybrid_2d_live_action",
            "chalkboard_doodle",
            "golden_neon_sketch",
            "line_diagram",
            "soft_3d_explainer",
            "cinematic_moody_3d",
            "pixel_8bit_hud",
            "ghibli_2d",
            "spiderverse_3d",
        ):
            assert needed in style_ids

        arch_ids = {a["id"] for a in archetypes}
        for needed_a in ("vintage_cartoon_sidekick", "woodland_critter", "talking_songbird", "drawn_prop", "noir_detective", "wizard_mage"):
            assert needed_a in arch_ids
            assert character_tokens.CharacterArchetype(needed_a) in character_tokens.ARCHETYPE_CONFIG

        # Every built-in style exposes a canned animated GIF sample in web/static/img/style_samples/
        for st in styles:
            if not st.get("custom"):
                url = st.get("sample_url") or ""
                assert url.startswith("/static/img/style_samples/") and url.endswith(".gif"), f"Missing sample for {st['id']}"


class TestHybrid2DRealismPipeline:
    def test_3panel_pro_sheet_from_uploaded_photo_and_2d_cast(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        fake_root = tmp_path / "repo"
        book_dir = fake_root / "projects" / "books" / "tavern_film"
        (book_dir / "assets" / "cast_refs").mkdir(parents=True)
        (book_dir / "assets" / "cast_refs" / "alex_ref.png").write_bytes(_png_bytes((200, 150, 120)))

        monkeypatch.setattr(routes_post, "pdir", lambda slug, kind="book": fake_root / "projects" / "books" / slug)
        monkeypatch.setattr(routes_get, "pdir", lambda slug, kind="book": fake_root / "projects" / "books" / slug)
        monkeypatch.setattr(studio_projects, "pdir", lambda slug, kind="book": fake_root / "projects" / "books" / slug)
        monkeypatch.setattr(character_tokens, "CHARACTERS_ROOT", fake_root / "projects" / "characters")

        # Enable Hybrid Mode via Step 09 global_params
        routes_post._global_params(
            _req({
                "project": "tavern_film",
                "look": "hybrid_2d_live_action",
                "positives": "35mm live action + vintage 1940s 2D",
                "negatives": "3d cgi",
                "hybrid_mode": {
                    "enabled": True,
                    "world_style": "live_action",
                    "live_style": "live_action",
                    "cartoon_style": "vintage_1940s_2d",
                    "animate_on_twos": True,
                },
            })
        )

        calls: list[dict] = []

        def _fake_render(prompt, out_path, **kwargs):
            calls.append({"prompt": prompt, "kwargs": kwargs})
            Path(out_path).write_bytes(_png_bytes((80, 120, 190)))
            return "local:sd-cli:flux2-klein-4b"

        monkeypatch.setattr(routes_post, "_render_keyframe_local_or_gemini", _fake_render)

        # 1. Realistic 3-panel sheet from uploaded Step 08 human photo
        res_real = routes_post._v2_turnaround_sheet(
            _req({"project": "tavern_film", "character": "Alex", "sheet_mode": "realistic", "desc": "dark wool coat"})
        )
        assert res_real["status"] == "ok"
        assert res_real["used_reference"] is True
        assert res_real["style_id"] == "live_action"
        assert calls[-1]["kwargs"]["aspect_ratio"] == "4:3"
        assert calls[-1]["kwargs"]["require_ref"] is True
        assert "3-panel side-by-side" in calls[-1]["prompt"]

        # 2. 2D Cartoon 3-panel sheet using locked shared 1940s style line
        res_2d = routes_post._v2_turnaround_sheet(
            _req({"project": "tavern_film", "character": "Bear", "sheet_mode": "2d", "desc": "friendly bear in red wool coat and green felt hat"})
        )
        assert res_2d["status"] == "ok"
        assert res_2d["style_id"] == "vintage_1940s_2d"
        assert "1940s hand-drawn 2D" in calls[-1]["prompt"]

        # Verify GET /api/v2_cast_references exposes both 3-Panel Sheets
        refs = routes_get._v2_cast_references(_req(query={"project": "tavern_film"}))["references"]
        assert any(r["source"] == "Step 10 3-Panel Sheet" and r["character"] == "BEAR" for r in refs)

    def test_step11_set_gap_planning_and_step17_two_pass_hybrid(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        fake_root = tmp_path / "repo"
        book_dir = fake_root / "projects" / "books" / "tavern_film"
        (book_dir / "assets" / "turnarounds").mkdir(parents=True)
        (book_dir / "assets" / "turnarounds" / "bear_sheet.png").write_bytes(_png_bytes((150, 90, 70)))
        (book_dir / "assets" / "turnarounds" / "otter_sheet.png").write_bytes(_png_bytes((90, 140, 120)))

        monkeypatch.setattr(routes_post, "pdir", lambda slug, kind="book": fake_root / "projects" / "books" / slug)
        monkeypatch.setattr(routes_get, "pdir", lambda slug, kind="book": fake_root / "projects" / "books" / slug)
        monkeypatch.setattr(routes_post, "ROOT", fake_root)

        calls: list[dict] = []

        def _fake_render(prompt, out_path, **kwargs):
            calls.append({"prompt": prompt, "kwargs": kwargs})
            Path(out_path).write_bytes(_png_bytes((180, 130, 80)))
            return "local:sd-cli:flux2-klein-4b"

        monkeypatch.setattr(routes_post, "_render_keyframe_local_or_gemini", _fake_render)

        # Step 11 Set with Reserve 2D Gaps
        save_res = routes_post._v2_set_save(
            _req({
                "project": "tavern_film",
                "name": "Cozy Wooden Tavern",
                "description": "long rustic table, roast turkey, candles",
                "lighting": "warm fireplace glow",
                "reserve_2d_gaps": True,
                "gap_notes": "empty chair on right, open tabletop foreground",
            })
        )
        assert save_res["reserve_2d_gaps"] is True

        set_res = routes_post._v2_set_render(
            _req({
                "project": "tavern_film",
                "name": "Cozy Wooden Tavern",
                "description": "long rustic table, roast turkey, candles",
                "reserve_2d_gaps": True,
                "gap_notes": "empty chair on right, open tabletop foreground",
            })
        )
        assert set_res["status"] == "ok"
        assert "empty chair on right" in calls[-1]["prompt"]
        assert "No people" in calls[-1]["prompt"]

        # Step 17 Pass 1 (Live Plate with Gaps)
        p1 = routes_post._v2_keyframe_hybrid_pass(
            _req({
                "project": "tavern_film",
                "id": "S001-01",
                "pass_num": 1,
                "prompt": "Alex eating Christmas dinner at the tavern table",
                "gap_notes": "empty chair on right for Bear, table foreground for Otter",
            })
        )
        assert p1["pass_num"] == 1
        assert (book_dir / "keyframes" / "S001-01_pass1.png").is_file()
        assert "NO CARTOONS YET" in calls[-1]["prompt"]

        # Step 17 Pass 2 (Bring 2D Cast In using Pass 1 + Bear & Otter sheets)
        p2 = routes_post._v2_keyframe_hybrid_pass(
            _req({
                "project": "tavern_film",
                "id": "S001-01",
                "pass_num": 2,
                "prompt": "Bear laughs in chair while Otter eats croissant on table",
                "cartoon_refs": ["assets/turnarounds/bear_sheet.png", "assets/turnarounds/otter_sheet.png"],
            })
        )
        assert p2["pass_num"] == 2
        assert p2["cartoon_ref_count"] == 2
        assert (book_dir / "keyframes" / "S001-01.png").is_file()
        assert calls[-1]["kwargs"]["require_ref"] is True
        # Pass 1 plate + 2 cartoon sheets = 3 multi-ref inputs!
        assert len(calls[-1]["kwargs"]["ref_images"]) == 3

    def test_step18_hybrid_video_prompts_and_single_prompts_multiref(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        fake_root = tmp_path / "repo"
        book_dir = fake_root / "projects" / "books" / "tavern_film"
        (book_dir / "shots").mkdir(parents=True)
        (book_dir / "assets" / "turnarounds").mkdir(parents=True)
        (book_dir / "assets" / "sets").mkdir(parents=True)
        (book_dir / "assets" / "turnarounds" / "alex_sheet.png").write_bytes(_png_bytes((200, 160, 140)))
        (book_dir / "assets" / "turnarounds" / "bear_sheet.png").write_bytes(_png_bytes((150, 90, 70)))
        (book_dir / "assets" / "sets" / "tavern.png").write_bytes(_png_bytes((100, 80, 60)))
        (book_dir / "shots" / "shotlist.json").write_text(
            json.dumps({
                "scenes": [{
                    "id": "S001",
                    "heading": "INT. COZY TAVERN - NIGHT",
                    "shots": [{"n": 1, "type": "MS", "lens_mm": 35, "movement": "static", "seconds": 4, "action": "Alex smiles across the table"}],
                }]
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(routes_post, "pdir", lambda slug, kind="book": fake_root / "projects" / "books" / slug)
        monkeypatch.setattr(routes_post, "ROOT", fake_root)
        monkeypatch.setattr(character_tokens, "CHARACTERS_ROOT", fake_root / "projects" / "characters")

        # Save 1 realistic actor + 1 vintage 2D cartoon character
        c_real = character_tokens.create_character_from_description("tavern_film", "Alex", "man in wool coat", "alex_tok")
        c_real["style_override"] = "live_action"
        character_tokens.save_character(c_real)
        c_2d = character_tokens.create_character_from_description("tavern_film", "Bear", "friendly bear", "bear_tok")
        c_2d["style_override"] = "vintage_1940s_2d"
        character_tokens.save_character(c_2d)

        # Step 18 Two-Pass Video Prompts
        vp = routes_post._v2_hybrid_video_prompts(
            _req({"project": "tavern_film", "scene_id": "S001", "gap_notes": "empty chair on right for @bear"})
        )
        assert vp["status"] == "ok"
        assert "PASS 1" in vp["pass1_prompt"]
        assert "PASS 2" in vp["pass2_prompt"]
        assert "@video1" in vp["pass2_prompt"]
        assert "on twos" in vp["pass2_prompt"]
        assert "@bear" in vp["pass2_prompt"]

        # Single Prompts Multi-Ref (combining 2 rel paths + 1 uploaded base64 = 3 refs)
        captured: dict = {}

        def _fake_render(prompt, out_path, **kwargs):
            captured["prompt"] = prompt
            captured["kwargs"] = kwargs
            Path(out_path).write_bytes(_png_bytes((50, 180, 120)))
            return "local:sd-cli:flux2-klein-4b"

        monkeypatch.setattr(routes_post, "_render_keyframe_local_or_gemini", _fake_render)
        b64 = "data:image/png;base64," + base64.b64encode(_png_bytes((220, 40, 80))).decode("ascii")
        sp = routes_post._v2_single_prompt_render(
            _req({
                "set": "hybrid_tests",
                "mode": "image",
                "prompt": "Alex having dinner with Bear in the cozy tavern",
                "style_id": "hybrid_2d_live_action",
                "image_base64": b64,
                "ref_paths": [
                    "projects/books/tavern_film/assets/turnarounds/bear_sheet.png",
                    "projects/books/tavern_film/assets/sets/tavern.png",
                ],
            })
        )
        assert sp["status"] == "ok"
        assert sp["reference_count"] == 3
        assert len(captured["kwargs"]["ref_images"]) == 3
        assert captured["kwargs"]["require_ref"] is True
