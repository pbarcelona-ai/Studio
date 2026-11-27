"""Tests for Step 11 Static Sets rename, Step 07 Props & Backdrops extraction/prompts/bi-directional import sync, and Step 17 multi-ref attachment."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image

from studio_app import keyframe_context, props_backdrops, routes_get, routes_post, set_vision_sync, workflow_sync

ROOT = Path(__file__).resolve().parents[1]


def _make_png_bytes(color: tuple[int, int, int] = (180, 120, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (48, 48), color=color).save(buf, format="PNG")
    return buf.getvalue()


def _seed_sample_project(tmp_path: Path, slug: str = "space_box_test") -> Path:
    pd = tmp_path / slug
    (pd / "readin").mkdir(parents=True, exist_ok=True)
    (pd / "adaptation").mkdir(parents=True, exist_ok=True)
    (pd / "screenplay").mkdir(parents=True, exist_ok=True)
    (pd / "shots").mkdir(parents=True, exist_ok=True)
    (pd / "assets" / "sets").mkdir(parents=True, exist_ok=True)

    # Step 03 Coverage mentions Saturn and cardboard box
    (pd / "readin" / "coverage.json").write_text(
        json.dumps(
            {
                "logline": "Two kids turn a cardboard box into a spaceship to visit Saturn and its moons.",
                "key_events": ["Tommy unfolds the cardboard box in the living room.", "They fly past the Moon and Saturn."],
                "characters": [{"name": "Tommy", "description": "5-year-old boy"}],
            },
            indent=1,
        ),
        encoding="utf-8",
    )

    # Step 05 Beats
    (pd / "adaptation" / "adaptation.json").write_text(
        json.dumps(
            {
                "scenes": [
                    {"id": "S001", "location": "Living Room", "title": "Box Ship", "summary": "Tommy sets up a cardboard box near the wooden toybox."},
                    {"id": "S002", "location": "SPACE: SATURN", "title": "Saturn Fly-By", "summary": "Saturn and Titan gleam outside the viewscreen."},
                ]
            },
            indent=1,
        ),
        encoding="utf-8",
    )

    # Step 06 Screenplay
    (pd / "screenplay" / "scene-001.json").write_text(
        json.dumps(
            {
                "id": "S001",
                "heading": "INT. LIVING ROOM - DAY",
                "elements": [
                    {"type": "action", "text": "Tommy unfolds a large cardboard box beside the wooden toybox and a stainless steel dog bowl."},
                ],
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    (pd / "screenplay" / "scene-002.json").write_text(
        json.dumps(
            {
                "id": "S002",
                "heading": "EXT. SPACE - SATURN - CONTINUOUS",
                "elements": [
                    {"type": "action", "text": "The ship glides past the Moon, Mars, and golden ringed Saturn toward Titan."},
                ],
            },
            indent=1,
        ),
        encoding="utf-8",
    )

    # Step 07 Continuity Book
    (pd / f"{slug}.json").write_text(
        json.dumps(
            {
                "characters": [{"name": "Tommy", "token": "5-year-old boy in red shirt"}],
                "locations": [
                    {"name": "Living Room", "token": "Cozy family living room"},
                    {"name": "SPACE: SATURN", "token": "Golden ringed planet Saturn in starry deep space"},
                ],
                "props": [
                    {"name": "Cardboard Box", "token": "Large brown corrugated cardboard box", "home_room": "Living Room"},
                ],
            },
            indent=1,
        ),
        encoding="utf-8",
    )

    # Step 12 Shot List
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
                                "composition": "Tommy sits beside the cardboard box in the living room.",
                                "action": "Tommy opens the cardboard box flaps.",
                                "props": ["Cardboard Box", "Wooden Toybox"],
                                "characters": ["Tommy"],
                            }
                        ],
                    },
                    {
                        "id": "S002",
                        "heading": "INT. STARSHIP BRIDGE - CONTINUOUS",
                        "shots": [
                            {
                                "n": 1,
                                "type": "WS",
                                "composition": "Through the viewscreen, Saturn shines bright and golden.",
                                "action": "Tommy gazes at Saturn from the bridge.",
                                "props": ["Saturn & Rings"],
                                "characters": ["Tommy"],
                            }
                        ],
                    },
                ]
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    return pd


def test_step11_labeled_static_sets_across_ui_and_workflow() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "web" / "static" / "js" / "studio_v2.js").read_text(encoding="utf-8")

    assert 'data-step="11" title="Step 11: Static Sets">11 Static Sets</button>' in html
    assert '<h2 id="step11Title">Step 11: Static Sets</h2>' in html
    assert "Approve & Next: Static Sets" in html
    assert 'id="v2PropsGrid"' in html
    assert 'id="bV2PropsExtract"' in html

    assert 'name: "11 Static Sets", title: "Static Sets"' in js
    assert workflow_sync.STEP_CATALOG[11]["short"] == "11 Static Sets"
    assert workflow_sync.STEP_CATALOG[11]["title"] == "Static Sets"


def test_extract_props_and_backdrops_from_script_prepopulates_prompts(tmp_path: Path) -> None:
    slug = "space_box_test"
    pd = _seed_sample_project(tmp_path, slug)

    res = props_backdrops.extract_props_and_backdrops_from_script(pd, slug)
    items = res["items"]
    by_name = {it["name"].lower(): it for it in items}

    # Pulls both physical props AND dynamic scenic backdrops
    assert res["counts"]["props"] >= 3
    assert res["counts"]["backdrops"] >= 3
    assert any("cardboard box" in k for k in by_name)
    assert any("toybox" in k for k in by_name)
    assert any("dog bowl" in k for k in by_name)
    assert any("saturn" in k and it["kind"] == "backdrop" for k, it in by_name.items())
    assert any("moon" in k and it["kind"] == "backdrop" for k, it in by_name.items())
    assert any("mars" in k and it["kind"] == "backdrop" for k, it in by_name.items())

    # Every extracted item has a non-empty pre-populated visual prompt and scene tags
    for it in items:
        assert str(it.get("prompt") or "").strip(), f"Missing pre-populated prompt for {it['name']}"
    saturn_item = next(it for it in items if "saturn" in it["name"].lower())
    assert "S002" in saturn_item["scenes"]

    # Re-extraction preserves user-edited prompts
    props_backdrops.save_prop_backdrop_item(
        pd,
        slug,
        name="Wooden Toybox",
        kind="prop",
        prompt="Custom hand-painted pine toybox with brass hinges",
    )
    res2 = props_backdrops.extract_props_and_backdrops_from_script(pd, slug, merge_existing=True)
    toybox2 = next(it for it in res2["items"] if "toybox" in it["name"].lower())
    assert toybox2["prompt"] == "Custom hand-painted pine toybox with brass hinges"


def test_prop_and_backdrop_import_converts_as_is_updates_prompts_and_triggers_bidirectional_sync(
    tmp_path: Path, monkeypatch: Any
) -> None:
    slug = "space_box_test"
    pd = _seed_sample_project(tmp_path, slug)
    monkeypatch.setattr(routes_post, "pdir", lambda s, kind="book": pd)
    monkeypatch.setattr(routes_get, "pdir", lambda s, kind="book": pd)

    props_backdrops.extract_props_and_backdrops_from_script(pd, slug)

    captured_render: dict[str, Any] = {}

    def _fake_render(prompt: str, out_png: Path, **kwargs: Any) -> str:
        captured_render["prompt"] = prompt
        captured_render["kwargs"] = kwargs
        out_png.parent.mkdir(parents=True, exist_ok=True)
        out_png.write_bytes(_make_png_bytes((220, 175, 110)))
        return "mock:flux2-klein"

    monkeypatch.setattr(routes_post, "_render_keyframe_local_or_gemini", _fake_render)
    monkeypatch.setattr(
        set_vision_sync,
        "describe_prop_or_backdrop_image",
        lambda path, name, kind="prop", existing_prompt="", timeout=40.0: {
            "ok": True,
            "engine": "mock:vision",
            "description": "Flattened corrugated cardboard box with red fragile arrows stamped on the side panel.",
            "token": "Flattened corrugated cardboard box with red fragile arrows stamped on the side panel.",
        },
    )

    b64 = "data:image/png;base64," + base64.b64encode(_make_png_bytes((160, 115, 70))).decode("ascii")
    req = routes_post.Request(
        path="/api/v2_prop_backdrop_upload",
        query={},
        body={
            "project": slug,
            "name": "Cardboard Box",
            "kind": "prop",
            "image_base64": b64,
            "convert_now": True,
            "auto_describe": True,
        },
    )
    out = routes_post._v2_prop_backdrop_upload(req)

    assert out["status"] == "ok"
    assert out["converted_url"].startswith(f"/file/{slug}/assets/props/")
    # Conversion prompt is strictly as-is and subject-agnostic (no leaked room/kitchen nouns)
    p_low = captured_render["prompt"].lower()
    assert "strict as-is conversion" in p_low
    assert "kitchen" not in p_low
    assert "countertop" not in p_low
    assert captured_render["kwargs"]["prefer_edit"] is True
    assert captured_render["kwargs"]["ref_images"]

    # Image-to-text updated Step 07 props_backdrops.json, Continuity Book, AND Step 17 keyframes_v2.json!
    assert out["vision_sync"]["ok"] is True
    assert "red fragile arrows" in out["prompt"]
    cb_after = json.loads((pd / f"{slug}.json").read_text(encoding="utf-8"))
    box_cb = next(p for p in cb_after["props"] if "cardboard box" in p["name"].lower())
    assert "red fragile arrows" in box_cb["token"]
    kf_meta = json.loads((pd / "keyframes_v2.json").read_text(encoding="utf-8"))
    assert "red fragile arrows" in kf_meta["prompts"]["S001-01"]

    # Bi-directional sync queued from earliest inception (Step 03 Coverage mentions cardboard box!)
    assert out["earliest_inception_step"] == 3
    q = workflow_sync.load_queue(pd)
    assert q["active"] is True
    step_nums = [int(s["step"]) for s in q["items"]]
    assert 3 in step_nums and 7 in step_nums
    assert q["origin_step"] == 7


def test_step17_attaches_both_static_set_and_step07_backdrop_or_prop(tmp_path: Path) -> None:
    slug = "space_box_test"
    pd = _seed_sample_project(tmp_path, slug)

    # Create a Step 11 Static Set Plate for Starship Bridge AND a Step 07 Backdrop plate for Saturn & Rings
    bridge_png = pd / "assets" / "sets" / "starship_bridge.png"
    bridge_png.write_bytes(_make_png_bytes((40, 50, 70)))

    props_dir = pd / "assets" / "props"
    props_dir.mkdir(parents=True, exist_ok=True)
    saturn_png = props_dir / "saturn_rings.png"
    saturn_png.write_bytes(_make_png_bytes((230, 190, 110)))

    props_backdrops.save_prop_backdrop_item(
        pd,
        slug,
        name="Saturn & Rings",
        kind="backdrop",
        prompt="Golden ringed Saturn glowing in deep starry space",
    )
    props_backdrops.update_item_assets(
        pd,
        slug,
        name="Saturn & Rings",
        kind="backdrop",
        image_rel="assets/props/saturn_rings.png",
    )

    ctx = keyframe_context.load_keyframe_project_context(slug, pd)
    sl_data = json.loads((pd / "shots" / "shotlist.json").read_text(encoding="utf-8"))
    kf_dir = pd / "keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)
    refs = keyframe_context.collect_render_references(
        ctx,
        "S002-01",
        "Wide shot of the Starship Bridge with Saturn & Rings visible outside the viewscreen.",
        sl_data,
        kf_dir,
        {},
    )

    ref_names = [p.name for p in refs["ref_imgs"]]
    assert "starship_bridge.png" in ref_names
    assert "saturn_rings.png" in ref_names
    assert any(pr["name"] == "Saturn & Rings" and pr["kind"] == "backdrop" for pr in refs["prop_refs_used"])
    assert "LOCKED STEP 07 BACKDROP (Saturn & Rings)" in refs["ref_legend"]
