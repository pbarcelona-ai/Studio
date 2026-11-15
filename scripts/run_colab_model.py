#!/usr/bin/env python3
"""Render rows of a project's prompt CSV on a Colab GPU and unpack them into the project. Works on Windows and macOS.

  [PROJECT=adam_eve] python scripts/run_colab_model.py MODEL START END [GPU]        (GPU default T4)
    MODEL = ltx_video | wan | cogvideox (video) | audio_kokoro | audio_musicgen | audio_mmaudio (audio) | image_sdxl_turbo | image_sdxl | ... (images)
  SHOTS_CSV=all_chapters.csv in the environment: one prompt per chapter (results in <folder>_chapters).

The Python version of the old run_colab_model.sh (which now only calls this). The Colab VM is always released at the end, also after an error.
"""
from __future__ import annotations

import os
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runner_common import ROOT, RunError, base_dir, default_csv, generated, mode_of, need_tool, project_folder, run, say  # noqa: E402

PACKAGES = ["diffusers", "transformers", "accelerate", "sentencepiece", "protobuf", "imageio", "imageio-ffmpeg", "ftfy", "gguf", "peft", "safetensors"]


def safe_extract(tar_path: Path, dest: Path) -> None:
    """Unpack a results archive, refusing any member that would land outside dest."""
    root = dest.resolve()
    with tarfile.open(tar_path) as tf:
        for m in tf.getmembers():
            target = (dest / m.name).resolve()
            if not (target == root or root in target.parents) or m.issym() or m.islnk():
                raise RunError(f"refusing a file in the results archive: {m.name}")
        tf.extractall(dest)                                # noqa: S202  every member was checked above


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        say(__doc__ or "")
        return 1
    model, start, end = argv[0], int(argv[1]), int(argv[2])
    gpu = argv[3] if len(argv) > 3 else "T4"
    project = os.environ.get("PROJECT") or "adam_eve"
    pd = project_folder(project)
    shots_csv = os.environ.get("SHOTS_CSV") or default_csv(model)
    if model.startswith(("tpu_", "image_tpu_")):
        raise RunError(f"{model} is Kaggle-only (TPU): use run_kaggle_model")
    mode = mode_of(shots_csv, keyframes=False)
    out_dir = base_dir(pd, model)
    out_dir = out_dir.with_name(out_dir.name + (f"_{mode}" if mode else ""))
    colab = need_tool("colab", "install the Colab CLI and sign in")
    with generated(f"colab_generate_{model}.py") as script:
        if not script.is_file():
            raise RunError(f"no such model: {model} (missing {script.name})")
        session = f"{project.replace('_', '-')}-{model}-{start}-{end}"
        if run([colab, "new", "-s", session, "--gpu", gpu]).returncode != 0:
            raise RunError("could not start a Colab VM")
        try:
            if run([colab, "upload", "-s", session, str(pd / shots_csv), "/content/all_shots.csv"]).returncode != 0:
                raise RunError(f"could not upload {shots_csv}")
            if not model.startswith("audio_"):                 # audio scripts install their own packages
                run([colab, "install", "-s", session, *PACKAGES])
            code = f"START, END = {start}, {end}\n" + script.read_text(encoding="utf-8")
            if run([colab, "exec", "-s", session], input=code).returncode != 0:
                raise RunError("the Colab run failed; read the output above")
            out_dir.mkdir(parents=True, exist_ok=True)
            tar = out_dir / "batch.tar"
            if run([colab, "download", "-s", session, f"/content/batch_{start}_{end}.tar", str(tar)]).returncode != 0:
                raise RunError("could not download the results")
            safe_extract(tar, out_dir)
            tar.unlink(missing_ok=True)
        finally:
            run([colab, "stop", "-s", session])                # always release the VM
    say(f"✅ clips in {out_dir}")
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    try:
        sys.exit(main(sys.argv[1:]))
    except RunError as e:
        say(str(e))
        sys.exit(1)
    except ValueError as e:
        say(f"bad rows: {e}")
        sys.exit(1)
