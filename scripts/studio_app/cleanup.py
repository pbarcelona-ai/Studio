"""Clean-up: find old generated files (caches, notebooks, results) and move them to the Trash; list and trash downloaded files of one book."""
import os
import re
import shutil
import time
from pathlib import Path
from bookkit import SLUG_RE
import layout
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .common import PlanError
from .config import ROOT
from .projects import read_csv_rows


# ---------------------------------------------------------------- clean-up: find old generated files, move them to the Trash
CLEAN_CATEGORIES = [   # id, title, ticked by default, what to know
    ("pycache", "Python cache folders", True, "Made automatically by Python; they come back by themselves."),
    ("notebooks", "Old generated notebooks and scripts (the 3 newest notebooks are kept; TPU notebooks are always removed)", True,
     "Written by the scripts in scripts/. They are re-created automatically when a run needs one, or with the Re-create button. "
     "The 3 most recently changed notebooks, and the scripts that go with them, are kept. The TPU notebooks (tpu_wan, tpu_mage_flow, tpu_flux_jax) are always listed and do not use up one of the 3."),
    ("temp", "Temporary and leftover files", True, "Partial uploads, old progress markers, the film selection file and stray logs inside video folders."),
    ("empty", "Empty output folders", True, "Folders in videos/, audio/ and images/ with nothing in them."),
    ("logs", "Kaggle run logs", False, "Kept for troubleshooting failed runs; safe to delete once the run no longer matters."),
    ("stale", "Outputs numbered past the end of the prompt file", False, "Clips, audio or images for rows that no longer exist (left over after the prompts were shortened or re-split)."),
    ("other", "Folders made by other tools", False, "graphify-out is made by your graphify tool, not by this project."),
]
KEEP_NOTEBOOKS = 3                       # clean-up keeps this many of the newest generated notebooks
OUTPUT_PATTERN = re.compile(r"^(shot|image|narration|sfx|music)-(\d{4})(_alt\d)?\.(mp4|png|wav)$")


def _size(path):
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def cleanup_scan():
    found: dict[str, list] = {c[0]: [] for c in CLEAN_CATEGORIES}

    def add(cat, path):
        if path.exists() and not any(i["path"] == str(path.relative_to(ROOT)) for i in found[cat]):
            found[cat].append({"path": str(path.relative_to(ROOT)), "bytes": _size(path), "dir": path.is_dir()})

    for dirpath, dirnames, _ in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "source")]       # never walk into a book's source folder
        if "__pycache__" in dirnames:
            add("pycache", Path(dirpath) / "__pycache__")
            dirnames.remove("__pycache__")
    nb_dirs = [ROOT, ROOT / "notebooks"]
    notebooks = sorted((f for d in nb_dirs if d.is_dir() for f in d.glob("Studio_*.ipynb")), key=lambda f: (f.stat().st_mtime, f.name), reverse=True)
    tpu = [f for f in notebooks if "tpu_" in f.name]            # the TPU experiments (Studio_Kaggle_tpu_wan, Studio_Kaggle_image_tpu_*) are never kept: they are always listed
    notebooks = [f for f in notebooks if f not in tpu]
    kept_keys = {m.group(1) for f in notebooks[:KEEP_NOTEBOOKS] if (m := re.match(r"Studio_(?:Colab|Kaggle)_(.+)\.ipynb$", f.name))}
    for f in notebooks[KEEP_NOTEBOOKS:] + tpu:
        add("notebooks", f)
    for d in nb_dirs:
        for f in (d.glob("colab_generate_*.py") if d.is_dir() else []):
            if f.name[len("colab_generate_"):-3] not in kept_keys:        # keep the script that belongs to a kept notebook
                add("notebooks", f)
    for pat in (".batch_progress*", ".adam_progress", ".enoch_progress", ".generation_progress"):
        for f in ROOT.glob(pat):
            add("temp", f)
    for f in (ROOT / "books").glob("*.part") if (ROOT / "books").exists() else []:
        add("temp", f)
    for proj in layout.all_dirs():
        if not proj.is_dir():
            continue
        for f in list((proj / "source").glob("*.part")) + [proj / "films" / "_selection.json"] + list((proj / "videos").glob("*.log")):
            add("temp", f)
        for f in (proj / "logs").glob("*.log") if (proj / "logs").exists() else []:
            add("logs", f)
        rows = {name: len(read_csv_rows(proj / name)) for name in ("all_shots.csv", "all_chapters.csv", "audio_shots.csv", "audio_chapters.csv", "all_images.csv")}
        for top in ("videos", "audio", "images"):
            for sub in sorted((proj / top).glob("*")) if (proj / top).is_dir() else []:
                if not sub.is_dir():
                    continue
                files = [f for f in sub.iterdir() if f.is_file()]
                if not files:
                    add("empty", sub)
                    continue
                chapters = sub.name.endswith("_chapters")
                csv_name = "all_images.csv" if top == "images" else (("audio_chapters.csv" if chapters else "audio_shots.csv") if top == "audio" else ("all_chapters.csv" if chapters else "all_shots.csv"))
                limit = rows.get(csv_name, 0)
                if not limit:
                    continue                                    # no prompt file to compare with: leave everything alone
                for f in files:
                    m = OUTPUT_PATTERN.match(f.name)
                    if m and int(m.group(2)) > limit:
                        add("stale", f)
    add("other", ROOT / "graphify-out")
    return [{"id": cid, "title": title, "default": default, "note": note, "items": sorted(found[cid], key=lambda i: i["path"]),
             "bytes": sum(i["bytes"] for i in found[cid])} for cid, title, default, note in CLEAN_CATEGORIES]


def move_to_trash(paths, label):
    """Move files/folders (given relative to the project folder) into ~/.Trash/<label>-<time>/, keeping their folder structure."""
    dest = Path.home() / ".Trash" / f"{label}-{time.strftime('%Y%m%d-%H%M%S')}"
    moved, total = 0, 0
    for rel in paths:
        src = (ROOT / rel).resolve()
        if ROOT.resolve() not in src.parents or not src.exists():          # only things inside this project, and only if still there
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        total += _size(src)
        shutil.move(str(src), str(target))
        moved += 1
    return {"moved": moved, "bytes": total, "trash": str(dest) if moved else ""}


def cleanup_delete(categories):
    wanted = {c for c in categories if c in {x[0] for x in CLEAN_CATEGORIES}}
    if not wanted:
        raise PlanError("tick at least one group")
    paths: list = []
    seen: list = []
    for cat in cleanup_scan():                                              # re-scan: only what the server finds itself is ever removed
        if cat["id"] in wanted:
            for item in cat["items"]:
                if not any(item["path"] == p or item["path"].startswith(p + "/") for p in seen):
                    paths.append(item["path"]); seen.append(item["path"])
    return move_to_trash(paths, "pistachio-cleanup")


# ---------------------------------------------------------------- downloaded files: list them, move chosen ones to the Trash (to regenerate)
def files_inventory(slug):
    """Every downloaded clip, audio file, image and film of a project, grouped by folder, with the row it belongs to."""
    d = pdir(slug)
    if not SLUG_RE.match(slug) or not d.is_dir():
        raise PlanError("pick a book or prompt set first")
    tables = {n: read_csv_rows(d / n) for n in ("all_shots.csv", "all_chapters.csv", "audio_shots.csv", "audio_chapters.csv", "all_images.csv")}
    folders = {}
    for top in ("videos", "audio", "images"):
        for sub in sorted((d / top).glob("*")) if (d / top).is_dir() else []:
            files = []
            for f in sorted(sub.iterdir()) if sub.is_dir() else []:
                m = OUTPUT_PATTERN.match(f.name)
                if not m:
                    continue
                n = int(m.group(2))
                chapters = sub.name.endswith("_chapters")
                csv_name = "all_images.csv" if top == "images" else (("audio_chapters.csv" if chapters else "audio_shots.csv") if top == "audio" else ("all_chapters.csv" if chapters else "all_shots.csv"))
                rows = tables.get(csv_name, [])
                row = rows[n - 1] if 0 < n <= len(rows) else None
                text = ""
                if row:
                    text = (f"{row['chapter']}: " + (row.get("prompt") or row.get("narration") or row.get("sfx") or ""))[:100]
                files.append({"name": f.name, "row": n, "bytes": f.stat().st_size, "text": text})
            if files:
                folders[f"{top}/{sub.name}"] = files
    films = [{"name": f.name, "row": 0, "bytes": f.stat().st_size, "text": ""} for f in sorted((d / "films").glob("*.mp4"))] if (d / "films").is_dir() else []
    if films:
        folders["films"] = films
    return folders


def trash_files(slug, folder, names):
    inv = files_inventory(slug)
    if folder not in inv:
        raise PlanError("unknown folder")
    known = {f["name"] for f in inv[folder]}
    chosen = [n for n in names if n in known]
    if not chosen:
        raise PlanError("tick at least one file")
    res = move_to_trash([f"{layout.rel(slug)}/{folder}/{n}" for n in chosen], "pistachio-deleted")
    # a folder emptied by this is tidied away too
    d = pdir(slug) / folder
    try:
        if d.is_dir() and not any(d.iterdir()) and folder != "films":
            d.rmdir()
    except OSError:
        pass
    return res
