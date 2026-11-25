"""Tests for enriched GET /api/log live job progress metadata."""
from __future__ import annotations

from types import SimpleNamespace

from studio_app import routes_get as rg


def test_api_log_exposes_progress_metadata(tmp_path, monkeypatch):
    exit_file = tmp_path / "step-1.exit"
    exit_file.write_text("0\n", encoding="utf-8")

    fake_job = SimpleNamespace(
        lock=rg.JOB.lock,
        lines=["Your script supervisor is writing the continuity book", "Done: 7 characters, 14 locations, 19 props."],
        running=False,
        current="",
        queue=[],
        state={
            "project": "saturn_book",
            "status": "finished",
            "started": "2026-11-24 22:45:51",
            "ended": "2026-11-24 22:47:17",
            "index": 0,
            "steps": [{"label": "Write the continuity book", "argv": ["python3", "continuity_book.py", "saturn_book"]}],
            "exit": str(exit_file),
        },
    )
    monkeypatch.setattr(rg, "JOB", fake_job)

    req = SimpleNamespace(q=lambda k, d="": "0" if k == "since" else d)
    res = rg._log(req)  # type: ignore[arg-type]
    assert res["running"] is False
    assert res["next"] == 2
    assert len(res["lines"]) == 2
    assert res["project"] == "saturn_book"
    assert res["status"] == "finished"
    assert res["script"] == "continuity_book.py"
    assert res["elapsed_sec"] == 86.0
    assert res["step_index"] == 0
    assert res["step_total"] == 1
    assert res["exit_code"] == 0


def test_cast_lock_data_includes_step10_turnarounds_and_roundtrips_lock(tmp_path, monkeypatch):
    import json
    import bookkit
    from studio_app import adapt

    # Build a fake repo tree under tmp_path/projects/books/demo_book
    proj_dir = tmp_path / "projects" / "books" / "demo_book"
    (proj_dir / "adaptation").mkdir(parents=True)
    (proj_dir / "assets" / "turnarounds").mkdir(parents=True)
    (proj_dir / "assets" / "sets").mkdir(parents=True)

    # Seed adaptation plan, continuity book, Step 10 turnaround, and Step 11 set picture
    (proj_dir / "adaptation" / "adaptation.json").write_text(
        json.dumps({
            "scenes": [
                {"id": "S001", "title": "Kitchen Launch", "location": "Kitchen", "chapters": [1], "characters": ["Tommy"]},
            ],
        }),
        encoding="utf-8",
    )
    (proj_dir / "demo_book.json").write_text(
        json.dumps({
            "characters": [
                {"name": "Tommy", "token": "5-year-old boy in brown t-shirt", "voice": "af_sky", "personality": {}},
                {"name": "Judah", "token": "big black labrador", "voice": "am_michael", "personality": {}},
            ],
            "locations": [{"name": "Kitchen", "token": "bright kitchen"}],
            "props": [],
        }),
        encoding="utf-8",
    )
    cap_png = proj_dir / "assets" / "turnarounds" / "captain_tommy_front.png"
    cap_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"captain" * 40)
    set_png = proj_dir / "assets" / "sets" / "kitchen_wide.png"
    set_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"kitchen" * 40)

    monkeypatch.setattr(bookkit, "ROOT", tmp_path)
    monkeypatch.setattr(adapt, "_book", lambda slug: proj_dir)
    monkeypatch.setattr("studio_app.config.get_character_series", lambda slug: "")

    data = adapt.cast_lock_data("demo_book")
    assert len(data["scenes"]) == 1
    sc = data["scenes"][0]
    assert sc["location"] == "Kitchen"
    # Canonical turnaround variant (captain_tommy_front.png) appears in Tommy's reference dropdown
    assert "projects/books/demo_book/assets/turnarounds/captain_tommy_front.png" in sc["characters"][0]["references"]
    assert "projects/books/demo_book/assets/sets/kitchen_wide.png" in sc["place"]["references"]
    assert len(data["all_characters"]) == 2

    # Lock Tommy's costume + Step 10 turnaround reference in S001
    updated = adapt.cast_lock_edit({
        "project": "demo_book",
        "scene": "S001",
        "kind": "character",
        "name": "Tommy",
        "token": "Tommy wearing gold captain tunic and black boots",
        "reference": "projects/books/demo_book/assets/turnarounds/captain_tommy_front.png",
    })
    assert updated["summary"]["characters"] == 1
    assert updated["scenes"][0]["characters"][0]["locked"]["token"] == "Tommy wearing gold captain tunic and black boots"

    # Unlock Tommy in S001
    unlocked = adapt.cast_lock_edit({"project": "demo_book", "scene": "S001", "kind": "character", "name": "Tommy"})
    assert unlocked["summary"]["characters"] == 0
