"""Shared parts of the GPU runners (run_kaggle_model.py, run_colab_model.py, fetch_kaggle_run.py): finding a command, the project's folder,
the generated notebook or script for a model, where results go, and the end of a run's log. Standard library only; works on Windows and macOS.
"""
from __future__ import annotations

import contextlib
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import layout  # noqa: E402


class RunError(Exception):
    """A run cannot go on; the message says why in plain words. The runner prints it and exits 1."""


def tool(name: str) -> str | None:
    """The full path of a command (kaggle, colab, uv), also looking in uv's tool folder (~/.local/bin) when it is not on PATH."""
    return shutil.which(name) or shutil.which(name, path=str(Path.home() / ".local" / "bin"))


def need_tool(name: str, hint: str) -> str:
    found = tool(name)
    if not found:
        raise RunError(f"{name} CLI not found: {hint}")
    return found


def project_folder(project: str) -> Path:
    """projects/books/<book>, projects/characters/<set> or projects/prompts/<set> (layout.py), which must exist."""
    try:
        pd = layout.project_dir(project)
    except ValueError as e:
        raise RunError(str(e)) from e
    if not pd.is_dir():
        raise RunError(f"no such project: {pd}")
    return pd


def default_csv(model: str) -> str:
    if model.startswith("audio_"):
        return "audio_shots.csv"
    if model.startswith("image_"):
        return "all_images.csv"
    return "all_shots.csv"


def base_dir(pd: Path, model: str) -> Path:
    """Where a model's results live in the project: audio/<kind>, images/<model> or videos/<model>."""
    if model.startswith("audio_"):
        return pd / "audio" / model[len("audio_"):]
    if model.startswith("image_"):
        return pd / "images" / model[len("image_"):]
    return pd / "videos" / model


def mode_of(shots_csv: str, keyframes: bool = True) -> str:
    """'chapters', 'scenes', 'keyframes' or '' from the prompt CSV's name (the results folder gets that ending)."""
    if "chapters" in shots_csv:
        return "chapters"
    if "scenes" in shots_csv:
        return "scenes"
    if keyframes and shots_csv.startswith("keyframes"):
        return "keyframes"
    return ""


@contextlib.contextmanager
def generated(name: str) -> Iterator[Path]:
    """The generated notebook or script for a model (Studio_Kaggle_<model>.ipynb, colab_generate_<model>.py). The clean-up may have deleted it:
    then it is made again in a throw-away folder, so the Studio folder stays clean."""
    here = ROOT / name
    if here.is_file():
        yield here
        return
    with tempfile.TemporaryDirectory(prefix="studio-gen-") as gen:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_all.py")], cwd=ROOT, env={**os.environ, "STUDIO_GEN_DIR": gen},
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        yield Path(gen) / name


def csv_rows(path: Path) -> int:
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return sum(1 for _ in csv.DictReader(fh))
    except (OSError, csv.Error, UnicodeDecodeError):
        return 0


def log_tail(path: Path, chars: int) -> str:
    """The end of a Kaggle log (a JSON list of {"data": ...} or plain text), without colour codes."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(no log was downloaded)"
    try:
        text = "".join(e.get("data", "") for e in json.loads(raw))
    except (ValueError, AttributeError, TypeError):
        text = raw
    return re.sub(r"\x1b\[[0-9;]*m", "", text)[-chars:]


def run(argv: list[str], **kw) -> subprocess.CompletedProcess:
    """Run a command without a shell, text in and out, never raising for a non-zero exit."""
    return subprocess.run(argv, text=True, encoding="utf-8", errors="replace", check=False, **kw)


def say(text: str) -> None:
    print(text, flush=True)
