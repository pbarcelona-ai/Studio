"""Shared helpers for the notebook writers (make_video.py, make_image.py, make_audio.py, make_tpu.py): cells, notebook JSON, output folder."""
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def output_root() -> Path:
    """Where generated notebooks and scripts are written: $STUDIO_GEN_DIR (the run scripts use a throw-away folder), else the repository root."""
    gen = os.environ.get("STUDIO_GEN_DIR")
    return Path(gen) if gen else ROOT


def md(text: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip().splitlines(True)}


def code(text: str) -> dict[str, Any]:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": text.strip().splitlines(True)}


def notebook_dict(cells: list, metadata: dict) -> dict[str, Any]:
    return {"cells": cells, "metadata": metadata, "nbformat": 4, "nbformat_minor": 0}


def write_notebook(path: Path, nb: dict) -> None:
    with open(path, "w") as f:
        json.dump(nb, f, indent=1)
