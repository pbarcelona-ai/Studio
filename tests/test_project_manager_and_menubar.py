"""Tests for Studio Menu Bar backend (Project Manager New/Open/Save/Save As, Undo/Redo, Manual, About, Exit) and UI wiring."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import project_manager  # noqa: E402
from studio_app import menu_routes, server  # noqa: E402
from studio_app.api import Request  # noqa: E402


def test_project_lifecycle_new_open_save_save_as_and_undo_redo(tmp_path: Path):
    books_root = tmp_path / "projects" / "books"
    books_lib = tmp_path / "books"
    books_root.mkdir(parents=True)
    books_lib.mkdir(parents=True)
    (books_lib / "saturn_trip.txt").write_text("Chapter 1\nTommy builds a cardboard rocket.\n", encoding="utf-8")

    # 1. New Project with custom name linked to existing book
    created = project_manager.new_project(
        "My Saturn Cut",
        book_source="books/saturn_trip.txt",
        books_root=books_root,
        books_lib=books_lib,
    )
    proj = created["project"]
    assert proj["slug"] == "my_saturn_cut"
    assert proj["name"] == "My Saturn Cut"
    assert proj["book_source"] == "books/saturn_trip.txt"
    assert (books_root / "my_saturn_cut" / "source" / "saturn_trip.txt").is_file()

    # Duplicate name rejected cleanly
    with pytest.raises(project_manager.ProjectError):
        project_manager.new_project("My Saturn Cut", books_root=books_root, books_lib=books_lib)

    # 2. Open Project auto-associates book and loads preview
    opened = project_manager.open_project("my_saturn_cut", books_root=books_root, books_lib=books_lib)
    assert opened["book_source"] == "books/saturn_trip.txt"
    assert "cardboard rocket" in opened["story_preview"]

    # 3. Save snapshots + Undo / Redo
    notes_file = books_root / "my_saturn_cut" / "notes.txt"
    notes_file.write_text("draft v1", encoding="utf-8")
    s1 = project_manager.save_project("my_saturn_cut", label="Draft v1", last_step=6, books_root=books_root, books_lib=books_lib)
    assert s1["can_undo"] is True

    notes_file.write_text("draft v2", encoding="utf-8")
    s2 = project_manager.save_project("my_saturn_cut", label="Draft v2", last_step=8, books_root=books_root, books_lib=books_lib)
    assert s2["project"]["last_step"] == 8

    u = project_manager.undo_project("my_saturn_cut", books_root=books_root)
    assert u["ok"] is True
    assert notes_file.read_text(encoding="utf-8") == "draft v1"
    assert u["can_redo"] is True

    r = project_manager.redo_project("my_saturn_cut", books_root=books_root)
    assert r["ok"] is True
    assert notes_file.read_text(encoding="utf-8") == "draft v2"

    # 4. Save As clones cleanly into a new named project without altering original
    cloned = project_manager.save_project_as("my_saturn_cut", "Saturn Director Cut", last_step=12, books_root=books_root, books_lib=books_lib)
    assert cloned["project"]["slug"] == "saturn_director_cut"
    assert cloned["project"]["name"] == "Saturn Director Cut"
    assert cloned["project"]["book_source"] == "books/saturn_trip.txt"
    assert (books_root / "saturn_director_cut" / "notes.txt").read_text(encoding="utf-8") == "draft v2"

    # 5. List projects includes both named projects and library books
    listed = project_manager.list_projects(books_root=books_root, books_lib=books_lib)
    slugs = {p["slug"] for p in listed["projects"]}
    assert {"my_saturn_cut", "saturn_director_cut", "saturn_trip"}.issubset(slugs)


def test_menu_routes_manual_about_and_shutdown(monkeypatch):
    man = menu_routes._manual(Request())
    assert man["status"] == "ok"
    assert "Step 01" in man["markdown"] and "Step 22" in man["markdown"]
    assert "Ctrl+N" in man["markdown"] and "Trelby" in man["markdown"]

    abt = menu_routes._about(Request())
    assert abt["status"] == "ok"
    assert abt["name"] == "Pistachio's Studio"
    assert abt["tools_total"] >= 15

    called: list[bool] = []
    monkeypatch.setattr(server, "request_shutdown", lambda stop_jobs=True: (called.append(stop_jobs) or True))
    sd = menu_routes._shutdown(Request(body={"stop_jobs": True}))
    assert sd["status"] == "ok" and sd["shutting_down"] is True and called == [True]


def test_menubar_html_css_and_js_structure():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "web" / "static" / "css" / "studio.css").read_text(encoding="utf-8")
    js = (ROOT / "web" / "static" / "js" / "menubar.js").read_text(encoding="utf-8")

    for required in (
        'id="studioMenubar"',
        'data-mb-action="file:new"',
        'data-mb-action="file:open"',
        'data-mb-action="file:save"',
        'data-mb-action="file:save-as"',
        'data-mb-action="file:exit"',
        'data-mb-action="edit:undo"',
        'data-mb-action="edit:redo"',
        'data-mb-action="edit:copy"',
        'data-mb-action="edit:paste"',
        'data-mb-action="edit:goto"',
        'data-mb-action="view:pipeline"',
        'data-mb-action="view:wb:panel-apps"',
        'data-mb-action="view:wb:panel-compare"',
        'data-mb-action="view:wb:panel-models"',
        'data-mb-action="view:wb:panel-prompts"',
        'data-mb-action="view:wb:panel-library"',
        'data-mb-action="help:manual"',
        'data-mb-action="help:about"',
        '/static/js/menubar.js',
    ):
        assert required in html, f"Missing {required} in web/index.html"

    assert ".studio-menubar" in css and ".mb-submenu" in css and "*::-webkit-scrollbar" in css
    assert "/api/studio/project/new" in js and "/api/studio/shutdown" in js
    # Ensure STUDIO_MANUAL.md exists in repo root and covers every step 01..22
    manual_text = (ROOT / "STUDIO_MANUAL.md").read_text(encoding="utf-8")
    for n in range(1, 23):
        assert f"Step {n:02d}" in manual_text, f"Missing Step {n:02d} in STUDIO_MANUAL.md"
    assert json.loads(json.dumps({"ok": True}))["ok"] is True
