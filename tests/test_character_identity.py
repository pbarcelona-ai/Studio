"""Tests for character identity control: canonical matching, costume refs, and twin/non-twin rules."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import character_identity as ci
from studio_app import routes_post as rp


def test_canonical_character_key_groups_titles_and_scene_variants():
    cast = [
        "TOMMY",
        "CAPTAIN TOMMY",
        "TOMMY (CRAYON-MARKED)",
        "JUDAH",
        "FIRST OFFICER JUDAH",
        "Dad (offstage)",
        "Mom",
        "Tommy's Mom",
        "Mr. Smith",
        "Mrs. Smith",
        "King Arthur",
        "Queen Guinevere",
    ]
    assert ci.canonical_character_key("TOMMY", known_names=cast) == "tommy"
    assert ci.canonical_character_key("CAPTAIN TOMMY", known_names=cast) == "tommy"
    assert ci.canonical_character_key("TOMMY (CRAYON-MARKED)", known_names=cast) == "tommy"
    assert ci.same_character("TOMMY", "CAPTAIN TOMMY", known_names=cast) is True
    assert ci.same_character("TOMMY", "TOMMY (CRAYON-MARKED)", known_names=cast) is True

    assert ci.canonical_character_key("JUDAH", known_names=cast) == "judah"
    assert ci.canonical_character_key("FIRST OFFICER JUDAH", known_names=cast) == "judah"
    assert ci.same_character("JUDAH", "FIRST OFFICER JUDAH", known_names=cast) is True

    # Must NEVER merge distinct people (possessives, gendered titles, family relations)
    assert ci.same_character("TOMMY", "Tommy's Mom", known_names=cast) is False
    assert ci.same_character("TOMMY", "Mom", known_names=cast) is False
    assert ci.same_character("Mr. Smith", "Mrs. Smith", known_names=cast) is False
    assert ci.same_character("King Arthur", "Queen Guinevere", known_names=cast) is False
    assert ci.same_character("TOMMY", "JUDAH", known_names=cast) is False


def test_manual_identity_overrides_link_and_unlink(tmp_path):
    # Link completely different alias names ("Bruce Wayne" -> "Batman")
    links = ci.save_identity_override(tmp_path, "Batman", "Bruce Wayne")
    assert ci.same_character("Batman", "Bruce Wayne", overrides=links) is True

    # Force two normally-linked names to stay independent via "__self__"
    links = ci.save_identity_override(tmp_path, "CAPTAIN TOMMY", "__self__")
    assert ci.same_character("TOMMY", "CAPTAIN TOMMY", overrides=links) is False

    # Reset back to Auto
    links = ci.save_identity_override(tmp_path, "CAPTAIN TOMMY", "")
    assert ci.same_character("TOMMY", "CAPTAIN TOMMY", overrides=links) is True


def test_explicit_twin_relationship_requires_explicit_twin_text():
    # Two boys with similar descriptions but NO mention of twins -> NOT twins
    assert ci.explicit_twin_relationship(
        "TOMMY", "5-year-old boy with brown hair and brown eyes",
        "SAMMY", "5-year-old boy with brown hair and brown eyes",
    ) is False

    # Explicitly mentions twin + sibling name -> twins allowed
    assert ci.explicit_twin_relationship(
        "ALEX", "8-year-old boy with freckles",
        "MAX", "Alex's identical twin brother wearing a green hoodie",
    ) is True

    # Both descriptions explicitly say they are twins -> twins allowed
    assert ci.explicit_twin_relationship(
        "LUNA", "10-year-old twin girl in blue dress",
        "STELLA", "10-year-old twin girl in yellow dress",
    ) is True

    # Mentioning "twin" for a DIFFERENT character does not make unrelated characters twins
    assert ci.explicit_twin_relationship(
        "ALEX", "8-year-old boy, twin brother of Max",
        "MOM", "adult woman with dark hair in apron",
    ) is False


def test_find_canonical_character_refs_uses_existing_variant_picture(tmp_path):
    t_dir = tmp_path / "assets" / "turnarounds"
    t_dir.mkdir(parents=True)
    cap_front = t_dir / "captain_tommy_front.png"
    cap_front.write_bytes(b"\x89PNG\r\n\x1a\n" + b"captain-tommy" * 30)
    bits_front = t_dir / "bits_front.png"
    bits_front.write_bytes(b"\x89PNG\r\n\x1a\n" + b"bits" * 30)

    cast = ["TOMMY", "CAPTAIN TOMMY", "TOMMY (CRAYON-MARKED)", "BITS"]
    refs = ci.find_canonical_character_refs(t_dir, "TOMMY", known_names=cast)
    assert len(refs) == 1
    assert refs[0][0] == cap_front
    assert refs[0][1] == "CAPTAIN TOMMY"

    # Must NEVER leak another distinct character's picture
    refs_judah = ci.find_canonical_character_refs(t_dir, "JUDAH", known_names=cast + ["JUDAH"])
    assert refs_judah == []


def test_turnaround_render_uses_existing_character_picture_for_costume_change(tmp_path, monkeypatch):
    proj_dir = tmp_path / "saturn_book"
    t_dir = proj_dir / "assets" / "turnarounds"
    t_dir.mkdir(parents=True)
    cap_front = t_dir / "captain_tommy_front.png"
    cap_front.write_bytes(b"\x89PNG\r\n\x1a\n" + b"captain-tommy" * 40)

    monkeypatch.setattr(rp, "pdir", lambda slug, kind="book": proj_dir)
    monkeypatch.setattr(
        rp,
        "_load_project_cast_profiles",
        lambda slug, pd: [
            {"name": "CAPTAIN TOMMY", "desc": "5-year-old boy in gold tunic"},
            {"name": "TOMMY", "desc": "5-year-old boy in brown t-shirt and jeans"},
            {"name": "TOMMY (CRAYON-MARKED)", "desc": "5-year-old boy with red crayon smudge"},
        ],
    )

    seen: list[dict] = []

    def fake_render(prompt, out_png, aspect_ratio="1:1", ref_images=None, engine="auto", **kw):
        seen.append({"prompt": prompt, "ref_images": list(ref_images or []), **kw})
        out_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"tommy-jeans" * 40)
        return "sd_cli:flux2-klein-4b"

    monkeypatch.setattr(rp, "_render_keyframe_local_or_gemini", fake_render)

    req = SimpleNamespace(body={
        "project": "saturn_book",
        "character": "TOMMY",
        "view": "front",
        "desc": "5-year-old boy, brown t-shirt, blue jeans, white socks",
    })
    res = rp._v2_turnaround_render(req)  # type: ignore[arg-type]
    assert res["status"] == "ok"
    assert res["refs_used"] == 1
    assert res["character_control"]["canonical_id"] == "tommy"
    assert res["character_control"]["reference_reason"] == "same_character_costume_change"
    assert res["character_control"]["reference_source"] == "CAPTAIN TOMMY"
    assert seen[0]["ref_images"] == [cap_front]
    assert seen[0]["require_ref"] is True


def test_turnaround_render_non_twin_distinctness_triggers_retry_when_too_similar(tmp_path, monkeypatch):
    import cv2
    import numpy as np

    proj_dir = tmp_path / "demo_book"
    t_dir = proj_dir / "assets" / "turnarounds"
    t_dir.mkdir(parents=True)

    # Create a synthetic portrait for ALICE on a light-gray studio backdrop
    def _make_portrait(path: Path, face_bgr: tuple[int, int, int], hair_bgr: tuple[int, int, int], square: bool = False) -> None:
        img = np.full((256, 256, 3), 220, dtype=np.uint8)
        if square:
            cv2.rectangle(img, (84, 34), (172, 118), face_bgr, -1)
            cv2.rectangle(img, (80, 24), (176, 56), hair_bgr, -1)
        else:
            cv2.circle(img, (128, 76), 40, face_bgr, -1)
            cv2.ellipse(img, (128, 48), (44, 24), 0, 180, 360, hair_bgr, -1)
        cv2.circle(img, (112, 74), 5, (20, 20, 20), -1)
        cv2.circle(img, (144, 74), 5, (20, 20, 20), -1)
        cv2.rectangle(img, (92, 120), (164, 230), (180, 80, 40), -1)
        ok, buf = cv2.imencode(".png", img)
        assert ok
        path.write_bytes(buf.tobytes())

    alice_front = t_dir / "alice_front.png"
    _make_portrait(alice_front, face_bgr=(165, 195, 235), hair_bgr=(45, 70, 110), square=False)

    monkeypatch.setattr(rp, "pdir", lambda slug, kind="book": proj_dir)
    monkeypatch.setattr(
        rp,
        "_load_project_cast_profiles",
        lambda slug, pd: [
            {"name": "ALICE", "desc": "8-year-old girl"},
            {"name": "BETH", "desc": "8-year-old girl"},  # NOT described as a twin!
        ],
    )

    attempts = {"n": 0}

    def fake_render(prompt, out_png, aspect_ratio="1:1", ref_images=None, engine="auto", **kw):
        attempts["n"] += 1
        assert not ref_images  # Must NEVER use non-twin Alice as reference!
        assert "twin" in str(kw.get("extra_negative", ""))
        if attempts["n"] == 1:
            # First render accidentally looks identical to Alice
            _make_portrait(out_png, face_bgr=(165, 195, 235), hair_bgr=(45, 70, 110), square=False)
        else:
            # Auto-diversified retry produces a visibly different character
            _make_portrait(out_png, face_bgr=(95, 125, 175), hair_bgr=(25, 25, 30), square=True)
        return "sd_cli:z-image-turbo"

    monkeypatch.setattr(rp, "_render_keyframe_local_or_gemini", fake_render)

    req = SimpleNamespace(body={
        "project": "demo_book",
        "character": "BETH",
        "view": "front",
        "desc": "8-year-old girl in green sweater",
    })
    res = rp._v2_turnaround_render(req)  # type: ignore[arg-type]
    assert res["status"] == "ok"
    assert res["refs_used"] == 0
    assert attempts["n"] == 2
    assert res["character_control"]["distinctness"]["diversified_retry"] is True
    assert res["character_control"]["distinctness"]["distinct"] is True


def test_turnaround_render_allows_explicit_twin_likeness(tmp_path, monkeypatch):
    proj_dir = tmp_path / "twin_book"
    t_dir = proj_dir / "assets" / "turnarounds"
    t_dir.mkdir(parents=True)
    alex_front = t_dir / "alex_front.png"
    alex_front.write_bytes(b"\x89PNG\r\n\x1a\n" + b"alex-twin" * 40)

    monkeypatch.setattr(rp, "pdir", lambda slug, kind="book": proj_dir)
    monkeypatch.setattr(
        rp,
        "_load_project_cast_profiles",
        lambda slug, pd: [
            {"name": "ALEX", "desc": "8-year-old boy with curly red hair, twin brother of Max"},
            {"name": "MAX", "desc": "8-year-old identical twin brother of Alex, wearing green jacket"},
        ],
    )

    seen: list[dict] = []

    def fake_render(prompt, out_png, aspect_ratio="1:1", ref_images=None, engine="auto", **kw):
        seen.append({"ref_images": list(ref_images or []), **kw})
        out_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"max-twin" * 40)
        return "sd_cli:flux2-klein-4b"

    monkeypatch.setattr(rp, "_render_keyframe_local_or_gemini", fake_render)

    req = SimpleNamespace(body={
        "project": "twin_book",
        "character": "MAX",
        "view": "front",
        "desc": "8-year-old identical twin brother of Alex, wearing green jacket",
    })
    res = rp._v2_turnaround_render(req)  # type: ignore[arg-type]
    assert res["status"] == "ok"
    assert res["character_control"]["reference_reason"] == "explicit_twin"
    assert res["character_control"]["twin_allowed_with"] == ["ALEX"]
    assert seen[0]["ref_images"] == [alex_front]
    assert seen[0]["require_ref"] is True
