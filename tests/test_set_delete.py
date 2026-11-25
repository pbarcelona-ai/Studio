"""Tests for Step 11 location/set deletion, persistence, and restore."""
from __future__ import annotations

import json
from types import SimpleNamespace

import continuity_book
from studio_app import routes_get as rg
from studio_app import routes_post as rp


def test_v2_set_delete_and_restore(tmp_path, monkeypatch):
    proj_dir = tmp_path / "saturn_book"
    proj_dir.mkdir(parents=True)
    # Seed continuity book with two locations
    cb_path = continuity_book.continuity_file(proj_dir)
    cb_path.parent.mkdir(parents=True, exist_ok=True)
    cb_path.write_text(
        json.dumps({
            "characters": [{"name": "Tommy", "token": "boy", "voice": "af_sky", "personality": {}}],
            "locations": [
                {"name": "Kitchen", "token": "bright sunny kitchen"},
                {"name": "Cardboard Rocket", "token": "brown cardboard box spaceship"},
            ],
            "props": [],
        }),
        encoding="utf-8",
    )
    # Seed a rendered set asset image for Kitchen
    sets_dir = proj_dir / "assets" / "sets"
    sets_dir.mkdir(parents=True)
    kitchen_img = sets_dir / "kitchen_wide.png"
    kitchen_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"img" * 40)

    monkeypatch.setattr(rp, "pdir", lambda slug, kind="book": proj_dir)
    monkeypatch.setattr(rg, "pdir", lambda slug, kind="book": proj_dir)

    # Delete "Kitchen"
    del_req = SimpleNamespace(body={"project": "saturn_book", "name": "Kitchen"})
    res = rp._v2_set_delete(del_req)  # type: ignore[arg-type]
    assert res["status"] == "ok"
    assert res["removed_from_continuity"] is True
    assert res["removed_images"] == 1
    assert not kitchen_img.exists()

    # Continuity book only has Cardboard Rocket left
    cb_after = continuity_book.load(proj_dir)
    assert [loc["name"] for loc in cb_after["locations"]] == ["Cardboard Rocket"]

    # Hidden sets endpoint returns "kitchen" so screenplay/cast_lock copies stay hidden
    hid_req = SimpleNamespace(q=lambda k: "saturn_book" if k == "project" else "")
    hid = rg._v2_sets_hidden(hid_req)  # type: ignore[arg-type]
    assert hid["deleted"] == ["kitchen"]

    # Re-adding "Kitchen" via restore unhides it
    rest_req = SimpleNamespace(body={"project": "saturn_book", "name": "Kitchen"})
    rres = rp._v2_set_restore(rest_req)  # type: ignore[arg-type]
    assert rres["deleted"] == []
    hid2 = rg._v2_sets_hidden(hid_req)  # type: ignore[arg-type]
    assert hid2["deleted"] == []


def test_v2_set_insert_between_reorder_and_auto_renumber(tmp_path, monkeypatch):
    proj_dir = tmp_path / "saturn_book"
    proj_dir.mkdir(parents=True)
    cb_path = continuity_book.continuity_file(proj_dir)
    cb_path.parent.mkdir(parents=True, exist_ok=True)
    cb_path.write_text(
        json.dumps({
            "characters": [{"name": "Tommy", "token": "boy", "voice": "af_sky", "personality": {}}],
            "locations": [
                {"name": "Kitchen", "token": "bright sunny kitchen"},
                {"name": "Cardboard Rocket", "token": "brown cardboard box spaceship"},
                {"name": "Titan Surface", "token": "orange hazy moon"},
            ],
            "props": [],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(rp, "pdir", lambda slug, kind="book": proj_dir)
    monkeypatch.setattr(rg, "pdir", lambda slug, kind="book": proj_dir)

    # Insert "Hallway" as Set 2 (between Set 1: Kitchen and Set 2: Cardboard Rocket)
    ins_req = SimpleNamespace(body={
        "project": "saturn_book",
        "order": ["kitchen", "cardboard rocket", "titan surface"],
        "insert_name": "Hallway",
        "position": 2,
    })
    ires = rp._v2_set_order(ins_req)  # type: ignore[arg-type]
    assert ires["order"] == ["kitchen", "hallway", "cardboard rocket", "titan surface"]

    # Deleting Set 2 ("Hallway") automatically shifts remaining sets back to 1..3
    del_req = SimpleNamespace(body={"project": "saturn_book", "name": "Hallway", "order": ires["order"]})
    dres = rp._v2_set_delete(del_req)  # type: ignore[arg-type]
    assert dres["order"] == ["kitchen", "cardboard rocket", "titan surface"]
    assert "hallway" in dres["deleted"]

    # Re-inserting "Hallway" at Set 1 unhides it and puts it first
    reins_req = SimpleNamespace(body={
        "project": "saturn_book",
        "order": dres["order"],
        "insert_name": "Hallway",
        "position": 1,
    })
    rres = rp._v2_set_order(reins_req)  # type: ignore[arg-type]
    assert rres["order"] == ["hallway", "kitchen", "cardboard rocket", "titan surface"]
    assert "hallway" not in rres["deleted"]

    # Reordering continuity book locations stays in sync
    reord_req = SimpleNamespace(body={
        "project": "saturn_book",
        "order": ["titan surface", "kitchen", "cardboard rocket"],
    })
    rp._v2_set_order(reord_req)  # type: ignore[arg-type]
    cb_after = continuity_book.load(proj_dir)
    assert [loc["name"] for loc in cb_after["locations"]] == ["Titan Surface", "Kitchen", "Cardboard Rocket"]

    # GET /api/v2_sets_hidden returns both order and deleted cleanly
    hid = rg._v2_sets_hidden(SimpleNamespace(q=lambda k: "saturn_book" if k == "project" else ""))  # type: ignore[arg-type]
    assert hid["order"] == ["titan surface", "kitchen", "cardboard rocket"]
