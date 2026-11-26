"""Project discovery: book list, project info, prompt sets, global (positive/negative) parameters."""
import csv
import json
from typing import Any
from pathlib import Path
from bookkit import continuity_file, build_movies, read_json, slugify
import character_tokens
import layout
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from schemas import clean_global_params

from .adapt import summary as adaptation_summary

from .config import AUDIO_KINDS, BOOK_EXTS, IMAGE_MODELS, LEGACY, LIBRARY, MODEL_RE, VIDEO_MODELS, get_character_series


# ---------------------------------------------------------------- project discovery
def count_files(folder, pattern):
    return len(list(folder.glob(pattern))) if folder.exists() else 0


def library_files():
    LIBRARY.mkdir(exist_ok=True)
    return sorted(p.name for p in LIBRARY.iterdir() if p.is_file() and p.suffix.lower() in BOOK_EXTS)


def pdf_choices(slug):
    """PDFs a project can be read from: the matching file in books/ first, then PDFs already copied to its source/."""
    out = [{"value": f"books/{f}", "label": f"books/{f}"} for f in library_files() if slugify(Path(f).stem) == slug]
    out += [{"value": f"books/{f}", "label": f"books/{f} (other)"} for f in library_files() if slugify(Path(f).stem) != slug]
    src = pdir(slug) / "source"
    out += [{"value": p.name, "label": f"{layout.rel(slug)}/source/{p.name}"} for p in sorted(src.iterdir()) if p.suffix.lower() in BOOK_EXTS] if src.exists() else []
    return out


def project_info(slug, *, sync: bool = False):
    """Read-only project status summary (mutating sync/movie-build only runs when `sync=True`)."""
    d = pdir(slug)
    chapters = read_json(d / "chapters.json", {})
    if sync and (d / "all_shots.csv").exists() and not (d / "movies.json").exists():
        build_movies(d, 10)
    movies = read_json(d / "movies.json", {})

    series = get_character_series(slug)
    if sync:
        character_tokens.sync_characters_from_project(slug)
    char_list = character_tokens.list_characters(series)

    return {
        "slug": slug, "legacy": slug in LEGACY, "not_started": not d.exists(), "pdf_choices": pdf_choices(slug),
        "pdfs": sorted(p.name for p in (d / "source").iterdir() if p.suffix.lower() in BOOK_EXTS) if (d / "source").exists() else [],
        "chapters": len(chapters.get("chapters", [])), "split_method": chapters.get("method"),
        "adaptation": adaptation_summary(d) if slug not in LEGACY else {"exists": False},
        "continuity": continuity_file(d).exists(), "scripts": count_files(d / "scripts", "chapter-*.json"),
        "built": (d / "all_shots.csv").exists(),
        "character_series": series,
        "characters": char_list,
        "movies": {"shots": movies.get("shots", []), "chapters": movies.get("chapters", [])},
        "have": {
            **{f"videos/{m}": count_files(d / "videos" / m, "shot-*.mp4") for m in VIDEO_MODELS},
            **{f"videos/{m}_chapters": count_files(d / "videos" / f"{m}_chapters", "shot-*.mp4") for m in VIDEO_MODELS},
            **{f"audio/{k}": count_files(d / "audio" / k, "*.wav") for k in AUDIO_KINDS},
            **{f"audio/{k}_chapters": count_files(d / "audio" / f"{k}_chapters", "*.wav") for k in AUDIO_KINDS},
            **{f"keyframes/{m}": n for m in IMAGE_MODELS if (n := count_files(d / "images" / f"{m}_keyframes", "image-*.png"))},
            "films": count_files(d / "films", "*.mp4"),
        },
    }


FCC_CATALOG = Path.home() / ".fcc" / "codex-model-catalog.json"
NOT_CHAT = ("guard", "safety", "embed", "parse", "translate", "topic-control", "calibration", "diffusion")


def codex_models():
    """Model names from the Free Claude Code catalog that look like chat/text models (suggestions for codex engines)."""
    try:
        data = json.loads(FCC_CATALOG.read_text())
        items = data["models"] if isinstance(data, dict) else data
        slugs = [m["slug"] for m in items if isinstance(m, dict) and MODEL_RE.match(m.get("slug", ""))]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return [x for x in slugs if not any(k in x.lower() for k in NOT_CHAT)]


def is_promptset(slug):
    d = layout.find_dir(slug)
    return d is not None and (d / "promptset.json").exists()


def promptset_info(slug):
    d = pdir(slug, "prompts")
    return {"slug": slug, "video_rows": len(read_csv_rows(d / "all_shots.csv")), "image_rows": len(read_csv_rows(d / "all_images.csv")),
            "have": {**{f"videos/{m}": count_files(d / "videos" / m, "shot-*.mp4") for m in VIDEO_MODELS},
                     **{f"images/{m}": count_files(d / "images" / m, "image-*.png") for m in IMAGE_MODELS}}}


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    try:
        with open(path, newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


# ---- Global Parameters ----
GLOBAL_PARAMS_FILE = "global_params.json"

def load_global_params(project: str) -> dict[str, Any]:
    """Load global parameters for a project ({"schema_version", "positives", "negatives"}; empty text when missing or unreadable)."""
    path = pdir(project) / GLOBAL_PARAMS_FILE
    try:
        return clean_global_params(json.loads(path.read_text()))
    except (OSError, ValueError):
        return clean_global_params({})

def save_global_params(
    project: str,
    positives: str,
    negatives: str,
    look: str = "",
    motion_cadence: str = "",
    hybrid_mode: dict[str, Any] | None = None,
) -> None:
    """Save global parameters for a project (preserving optional look / motion_cadence / hybrid_mode)."""
    path = pdir(project) / GLOBAL_PARAMS_FILE
    pdir(project).mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except (OSError, ValueError):
            existing = {}
    doc = clean_global_params({"positives": positives, "negatives": negatives})
    eff_look = str(look or existing.get("look") or "").strip()
    eff_motion = str(motion_cadence or existing.get("motion_cadence") or "").strip()
    if eff_look:
        doc["look"] = eff_look
    if eff_motion:
        doc["motion_cadence"] = eff_motion
    if isinstance(hybrid_mode, dict):
        doc["hybrid_mode"] = {
            "enabled": bool(hybrid_mode.get("enabled", False)),
            "world_style": str(hybrid_mode.get("world_style") or "live_action").strip(),
            "live_style": str(hybrid_mode.get("live_style") or "live_action").strip(),
            "cartoon_style": str(hybrid_mode.get("cartoon_style") or "vintage_1940s_2d").strip(),
            "animate_on_twos": bool(hybrid_mode.get("animate_on_twos", True)),
        }
    elif isinstance(existing.get("hybrid_mode"), dict):
        doc["hybrid_mode"] = existing["hybrid_mode"]
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
