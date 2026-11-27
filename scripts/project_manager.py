"""Named Project lifecycle for Pistachio's Studio: New, Open, Save, Save As, and snapshot Undo/Redo.

Each project lives in its own folder under `projects/books/<slug>/` with a `project.json` manifest
linking the user's custom Project Name to its source book input (file in `books/` or `source/`).
Existing book folders without `project.json` are automatically treated as projects whose name matches
the book name.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import history
import layout
from bookkit import slugify

ROOT = Path(__file__).resolve().parent.parent
BOOKS_LIB = ROOT / "books"
PROJECT_MANIFEST = "project.json"
UNDO_STATE_FILE = "undo_state.json"
BOOK_EXTS = frozenset({".pdf", ".epub", ".docx", ".odt", ".rtf", ".txt", ".md", ".html", ".htm", ".fountain", ".fdx"})


class ProjectError(ValueError):
    """User-fixable project error (bad name, duplicate, missing project)."""


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_slug(name: str) -> str:
    clean = str(name or "").strip()
    if not clean:
        raise ProjectError("Enter a project name first.")
    slug = slugify(clean)[:40].strip("_")
    if len(slug) < 2 or not layout.SLUG_RE.match(slug):
        raise ProjectError("Project name must contain at least 2 letters or numbers (max 40 characters).")
    return slug


def _library_books(books_lib: Path | None = None) -> list[dict[str, str]]:
    lib = books_lib or BOOKS_LIB
    if not lib.is_dir():
        return []
    out: list[dict[str, str]] = []
    for p in sorted(lib.iterdir()):
        if p.is_file() and p.suffix.lower() in BOOK_EXTS:
            out.append({
                "value": f"books/{p.name}",
                "filename": p.name,
                "slug": slugify(p.stem),
                "label": p.name,
            })
    return out


def _detect_book_source(pdir: Path, slug: str, books_lib: Path | None = None) -> str:
    """Find the associated input book file for a project folder (source/ first, then matching books/ file)."""
    src_dir = pdir / "source"
    if src_dir.is_dir():
        for p in sorted(src_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in BOOK_EXTS:
                return f"source/{p.name}"
    for b in _library_books(books_lib):
        if b["slug"] == slug:
            return b["value"]
    return ""


def _read_manifest(pdir: Path, slug: str, books_lib: Path | None = None) -> dict[str, Any]:
    mf = pdir / PROJECT_MANIFEST
    data: dict[str, Any] = {}
    if mf.is_file():
        try:
            raw = json.loads(mf.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except (OSError, ValueError):
            data = {}
    name = str(data.get("name") or slug.replace("_", " ").title()).strip()
    book_source = str(data.get("book_source") or "").strip() or _detect_book_source(pdir, slug, books_lib)
    book_title = str(data.get("book_title") or (Path(book_source).stem.replace("_", " ").title() if book_source else name))
    last_step = int(data.get("last_step") or 1)
    if last_step < 1 or last_step > 22:
        last_step = 1
    mtime_iso = _now_iso()
    if pdir.is_dir():
        try:
            mtime_iso = datetime.fromtimestamp(pdir.stat().st_mtime, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        except OSError:
            pass
    return {
        "schema_version": 1,
        "name": name,
        "slug": slug,
        "book_source": book_source,
        "book_title": book_title,
        "last_step": last_step,
        "created_at": str(data.get("created_at") or mtime_iso),
        "updated_at": str(data.get("updated_at") or mtime_iso),
    }


def _write_manifest(pdir: Path, data: dict[str, Any]) -> dict[str, Any]:
    pdir.mkdir(parents=True, exist_ok=True)
    mf = pdir / PROJECT_MANIFEST
    tmp = mf.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, mf)
    return data


def _read_undo_index(pdir: Path, total: int) -> int:
    if total <= 0:
        return -1
    p = history.folder(pdir) / UNDO_STATE_FILE
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        idx = int(raw.get("index", total - 1))
        return max(0, min(total - 1, idx))
    except (OSError, ValueError, TypeError, AttributeError):
        return total - 1


def _write_undo_index(pdir: Path, index: int) -> None:
    folder = history.folder(pdir)
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / UNDO_STATE_FILE
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"index": index, "updated_at": _now_iso()}), encoding="utf-8")
    os.replace(tmp, p)


def _restore_moment_files(pdir: Path, moment: dict[str, Any]) -> None:
    """Restore record files from a moment snapshot without creating a new moment (preserves redo stack)."""
    want = dict(moment.get("files") or {})
    blobs = history.folder(pdir) / "blobs"
    for rel, sha in want.items():
        if ".." in Path(rel).parts:
            continue
        blob = blobs / sha[:2] / sha
        if blob.is_file():
            dst = pdir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(blob.read_bytes())
    # Remove record files added after this moment (keep project.json so project metadata remains intact)
    for existing in history.records(pdir):
        rel = existing.relative_to(pdir).as_posix()
        if rel == PROJECT_MANIFEST:
            continue
        if rel not in want:
            existing.unlink(missing_ok=True)


def list_projects(
    *,
    books_root: Path | None = None,
    books_lib: Path | None = None,
) -> dict[str, Any]:
    """List all Studio projects (with associated books) plus available library books."""
    broot = books_root or layout.BOOKS
    lib_books = _library_books(books_lib)
    projects: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    if broot.is_dir():
        for d in sorted(broot.iterdir()):
            if not d.is_dir() or not layout.SLUG_RE.match(d.name):
                continue
            seen_slugs.add(d.name)
            rec = _read_manifest(d, d.name, books_lib)
            ms = history.moments(d)
            rec["history_count"] = len(ms)
            rec["has_folder"] = True
            projects.append(rec)

    # Include unstarted books from books/ as openable projects (name == book name)
    for b in lib_books:
        slug = b["slug"]
        if slug in seen_slugs or not layout.SLUG_RE.match(slug):
            continue
        seen_slugs.add(slug)
        title = Path(b["filename"]).stem.replace("_", " ").title()
        projects.append({
            "schema_version": 1,
            "name": title,
            "slug": slug,
            "book_source": b["value"],
            "book_title": title,
            "last_step": 1,
            "created_at": "",
            "updated_at": "",
            "history_count": 0,
            "has_folder": False,
        })

    projects.sort(key=lambda x: (str(x.get("updated_at") or ""), str(x.get("name") or "")), reverse=True)
    return {"projects": projects, "books": lib_books}


def new_project(
    name: str,
    *,
    book_source: str = "",
    story_text: str = "",
    books_root: Path | None = None,
    books_lib: Path | None = None,
) -> dict[str, Any]:
    """Create a new named Project folder, link/copy its input book, and record its initial snapshot."""
    broot = books_root or layout.BOOKS
    lib = books_lib or BOOKS_LIB
    slug = _make_slug(name)
    pdir = broot / slug
    if pdir.exists():
        raise ProjectError(f"A project named {name!r} ({slug}) already exists. Choose another name or use Open Project.")

    pdir.mkdir(parents=True, exist_ok=True)
    src_dir = pdir / "source"
    src_dir.mkdir(parents=True, exist_ok=True)

    linked_source = ""
    book_title = name.strip()
    clean_src = str(book_source or "").strip()

    if clean_src:
        fname = Path(clean_src).name
        if not fname or ".." in clean_src:
            raise ProjectError("Invalid book source file path.")
        cand = (lib / fname) if (lib / fname).is_file() else (ROOT / clean_src)
        if not cand.is_file() or cand.suffix.lower() not in BOOK_EXTS:
            raise ProjectError(f"Book file not found: {clean_src}")
        shutil.copy2(cand, src_dir / cand.name)
        linked_source = f"books/{cand.name}" if cand.parent.resolve() == lib.resolve() else f"source/{cand.name}"
        book_title = cand.stem.replace("_", " ").title()
    elif str(story_text or "").strip():
        lib.mkdir(parents=True, exist_ok=True)
        txt_name = f"{slug}.txt"
        body = str(story_text).strip() + "\n"
        (lib / txt_name).write_text(body, encoding="utf-8")
        (src_dir / txt_name).write_text(body, encoding="utf-8")
        linked_source = f"books/{txt_name}"
        book_title = name.strip()

    now = _now_iso()
    manifest = _write_manifest(
        pdir,
        {
            "schema_version": 1,
            "name": name.strip(),
            "slug": slug,
            "book_source": linked_source,
            "book_title": book_title,
            "last_step": 1,
            "created_at": now,
            "updated_at": now,
        },
    )
    history.create(pdir, f"Created project '{name.strip()}'", kind="manual")
    ms = history.moments(pdir)
    _write_undo_index(pdir, len(ms) - 1)
    return {"project": manifest, "history_count": len(ms)}


def open_project(
    slug: str,
    *,
    books_root: Path | None = None,
    books_lib: Path | None = None,
) -> dict[str, Any]:
    """Open an existing project (or initialize one from an existing book) and auto-associate its input book."""
    broot = books_root or layout.BOOKS
    lib = books_lib or BOOKS_LIB
    clean_slug = str(slug or "").strip()
    if not layout.SLUG_RE.match(clean_slug):
        raise ProjectError(f"Invalid project id: {slug!r}")

    pdir = broot / clean_slug
    manifest = _read_manifest(pdir, clean_slug, lib)

    # Ensure project folder & manifest exist and link matching book file if needed
    pdir.mkdir(parents=True, exist_ok=True)
    src_dir = pdir / "source"
    book_src = manifest["book_source"]
    if book_src.startswith("books/"):
        lib_file = lib / Path(book_src).name
        if lib_file.is_file():
            src_dir.mkdir(parents=True, exist_ok=True)
            dst_src = src_dir / lib_file.name
            if not dst_src.exists():
                shutil.copy2(lib_file, dst_src)
    manifest["updated_at"] = _now_iso()
    _write_manifest(pdir, manifest)

    # Read plain-text preview for Step 01 story box if source is .txt/.md
    story_preview = ""
    if book_src:
        cand = (lib / Path(book_src).name) if book_src.startswith("books/") else (pdir / book_src)
        if cand.is_file() and cand.suffix.lower() in (".txt", ".md"):
            try:
                story_preview = cand.read_text(encoding="utf-8", errors="replace")[:200_000]
            except OSError:
                story_preview = ""

    ms = history.moments(pdir)
    idx = _read_undo_index(pdir, len(ms))
    return {
        "project": manifest,
        "book_source": manifest["book_source"],
        "story_preview": story_preview,
        "history_count": len(ms),
        "can_undo": idx > 0,
        "can_redo": idx >= 0 and idx < len(ms) - 1,
    }


def save_project(
    slug: str,
    *,
    label: str = "Manual Save",
    last_step: int | None = None,
    book_source: str | None = None,
    books_root: Path | None = None,
    books_lib: Path | None = None,
) -> dict[str, Any]:
    """Save project metadata and create a history snapshot (for File → Save & Undo/Redo)."""
    broot = books_root or layout.BOOKS
    lib = books_lib or BOOKS_LIB
    clean_slug = str(slug or "").strip()
    if not layout.SLUG_RE.match(clean_slug):
        raise ProjectError("Pick or create a project first before saving.")
    pdir = broot / clean_slug
    manifest = _read_manifest(pdir, clean_slug, lib)
    if last_step is not None and 1 <= int(last_step) <= 22:
        manifest["last_step"] = int(last_step)
    if book_source:
        manifest["book_source"] = str(book_source).strip()
        manifest["book_title"] = Path(manifest["book_source"]).stem.replace("_", " ").title()
    manifest["updated_at"] = _now_iso()
    _write_manifest(pdir, manifest)

    # If user had undone earlier, trim future redo moments before appending a new save
    ms = history.moments(pdir)
    if ms:
        cur_idx = _read_undo_index(pdir, len(ms))
        if cur_idx < len(ms) - 1:
            trimmed = ms[: cur_idx + 1]
            history._save(pdir, trimmed)

    moment = history.create(pdir, label or "Manual Save", kind="manual")
    ms_after = history.moments(pdir)
    _write_undo_index(pdir, len(ms_after) - 1)
    return {
        "project": manifest,
        "moment": {"id": moment["id"], "at": moment["at"], "label": moment["label"]},
        "history_count": len(ms_after),
        "can_undo": len(ms_after) > 1,
        "can_redo": False,
    }


def save_project_as(
    source_slug: str,
    new_name: str,
    *,
    last_step: int | None = None,
    books_root: Path | None = None,
    books_lib: Path | None = None,
) -> dict[str, Any]:
    """Clone an existing project into a new named project folder (File → Save As)."""
    broot = books_root or layout.BOOKS
    lib = books_lib or BOOKS_LIB
    src_slug = str(source_slug or "").strip()
    if not layout.SLUG_RE.match(src_slug):
        raise ProjectError("Open a project first before using Save As.")
    src_dir = broot / src_slug
    if not src_dir.is_dir():
        raise ProjectError(f"Source project {src_slug!r} does not exist yet.")

    dst_slug = _make_slug(new_name)
    if dst_slug == src_slug:
        raise ProjectError("New project name must be different from the current project.")
    dst_dir = broot / dst_slug
    if dst_dir.exists():
        raise ProjectError(f"A project named {new_name!r} ({dst_slug}) already exists.")

    def _ignore_tmp(_d: str, names: list[str]) -> set[str]:
        return {n for n in names if n.endswith((".tmp", ".bak", ".lock"))}

    shutil.copytree(src_dir, dst_dir, ignore=_ignore_tmp)
    manifest = _read_manifest(src_dir, src_slug, lib)
    now = _now_iso()
    manifest.update({
        "name": new_name.strip(),
        "slug": dst_slug,
        "created_at": now,
        "updated_at": now,
    })
    if last_step is not None and 1 <= int(last_step) <= 22:
        manifest["last_step"] = int(last_step)
    _write_manifest(dst_dir, manifest)

    history.create(dst_dir, f"Saved As '{new_name.strip()}' (from {src_slug})", kind="manual")
    ms = history.moments(dst_dir)
    _write_undo_index(dst_dir, len(ms) - 1)
    return {
        "project": manifest,
        "history_count": len(ms),
        "can_undo": len(ms) > 1,
        "can_redo": False,
    }


def undo_project(slug: str, *, books_root: Path | None = None) -> dict[str, Any]:
    """Step one snapshot backward in project history (Edit → Undo)."""
    broot = books_root or layout.BOOKS
    clean_slug = str(slug or "").strip()
    if not layout.SLUG_RE.match(clean_slug) or not (broot / clean_slug).is_dir():
        raise ProjectError("No active project to undo.")
    pdir = broot / clean_slug
    ms = history.moments(pdir)
    if len(ms) < 2:
        return {"ok": False, "message": "Nothing to undo yet (save a snapshot first).", "can_undo": False, "can_redo": False}

    idx = _read_undo_index(pdir, len(ms))
    # If at tip and working files changed since last moment, snapshot current state first so Redo can bring it back
    if idx == len(ms) - 1:
        before_len = len(ms)
        history.create(pdir, "Auto-snapshot before Undo", kind="undo_tip")
        ms = history.moments(pdir)
        if len(ms) > before_len:
            idx = len(ms) - 1

    if idx <= 0:
        return {"ok": False, "message": "Already at the earliest snapshot.", "can_undo": False, "can_redo": len(ms) > 1}

    new_idx = idx - 1
    target = ms[new_idx]
    _restore_moment_files(pdir, target)
    _write_undo_index(pdir, new_idx)
    return {
        "ok": True,
        "action": "undo",
        "moment_id": target["id"],
        "label": target.get("label") or target["id"],
        "index": new_idx,
        "total": len(ms),
        "can_undo": new_idx > 0,
        "can_redo": new_idx < len(ms) - 1,
        "message": f"Undid to snapshot: {target.get('label') or target['id']}",
    }


def redo_project(slug: str, *, books_root: Path | None = None) -> dict[str, Any]:
    """Step one snapshot forward in project history (Edit → Redo)."""
    broot = books_root or layout.BOOKS
    clean_slug = str(slug or "").strip()
    if not layout.SLUG_RE.match(clean_slug) or not (broot / clean_slug).is_dir():
        raise ProjectError("No active project to redo.")
    pdir = broot / clean_slug
    ms = history.moments(pdir)
    if len(ms) < 2:
        return {"ok": False, "message": "Nothing to redo.", "can_undo": False, "can_redo": False}

    idx = _read_undo_index(pdir, len(ms))
    if idx >= len(ms) - 1:
        return {"ok": False, "message": "Already at the latest snapshot.", "can_undo": idx > 0, "can_redo": False}

    new_idx = idx + 1
    target = ms[new_idx]
    _restore_moment_files(pdir, target)
    _write_undo_index(pdir, new_idx)
    return {
        "ok": True,
        "action": "redo",
        "moment_id": target["id"],
        "label": target.get("label") or target["id"],
        "index": new_idx,
        "total": len(ms),
        "can_undo": new_idx > 0,
        "can_redo": new_idx < len(ms) - 1,
        "message": f"Redid to snapshot: {target.get('label') or target['id']}",
    }


def load_manual_markdown(repo_root: Path | None = None) -> str:
    """Read the Studio step-by-step manual Markdown."""
    root = repo_root or ROOT
    for cand in (root / "STUDIO_MANUAL.md", root / "docs" / "STUDIO_MANUAL.md", root / "README.md"):
        if cand.is_file():
            return cand.read_text(encoding="utf-8")
    return "# Pistachio's Studio Manual\n\nManual file not found."


def _version_from_pyproject(repo_root: Path | None = None) -> str:
    root = repo_root or ROOT
    pp = root / "pyproject.toml"
    if pp.is_file():
        m = re.search(r'^version\s*=\s*"([^"]+)"', pp.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1)
    return "2.0"


def about_info(repo_root: Path | None = None) -> dict[str, Any]:
    """Return structured metadata for Help → About."""
    import external_tools

    ext = external_tools.detect_all_tools(repo_root=repo_root)
    return {
        "name": "Pistachio's Studio",
        "version": _version_from_pyproject(repo_root),
        "tagline": "Local-First AI Book-to-Film Production Studio",
        "tools_installed": ext["installed_count"],
        "tools_total": ext["total_count"],
        "license": "MIT",
    }
