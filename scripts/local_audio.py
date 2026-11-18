#!/usr/bin/env python3
"""Make a book's narration or music on this computer's processor: no GPU, so no GPU hours.

  uv run --python 3.11 --with kokoro --with soundfile --with "numpy<2" --with pip python local_audio.py BOOK kokoro
  uv run --python 3.11 --with "transformers<4.50" --with "numpy<2" --with scipy --with accelerate python local_audio.py BOOK musicgen

kokoro:   every row of audio_shots.csv -> audio/kokoro/narration-NNNN.wav. audiobook: every row of audiobook.csv -> audio/kokoro_audiobook/. Measured on an Intel Mac: about 3 s for each line.
musicgen: one 28 s cue for every row of audio_chapters.csv -> audio/musicgen_chapters/music-NNNN.wav. Measured on an Intel Mac: about 7 minutes for each.
musicgen_scenes: the same for audio_scenes.csv (one cue per scene of the film plan) -> audio/musicgen_scenes/music-NNNN.wav.
Files already there are kept, so running it again carries on. The same voices and music as the GPU runs (make_audio.py holds the Kokoro worker).
"""
import ast
import csv
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout  # noqa: E402


def kokoro_worker():
    """The Kokoro worker's source: a constant in make_audio.py, which writes notebooks if imported, so it is read rather than imported."""
    tree = ast.parse((Path(__file__).resolve().parent / "make_audio.py").read_text())
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "KOKORO_WORKER")


def narration(d, csv_name="audio_shots.csv", folder="kokoro", force=False):
    d = Path(d)
    rows_data = list(csv.DictReader(open(d / csv_name, newline="", encoding="utf-8")))
    out = d / "audio" / folder
    out.mkdir(parents=True, exist_ok=True)

    import json
    active_rows: list[int] = []
    for i, r in enumerate(rows_data, 1):
        # Check for lines_json (new format with dialogue/narration lines)
        try:
            lines = json.loads(r.get("lines_json") or "[]")
        except Exception:
            lines = []
        if lines:
            active_rows.append(i)
        elif r.get("narration"):
            # Backward compatibility: if no lines_json but narration column has content, treat as active
            active_rows.append(i)
        else:
            # Clean up stale audio file for silent / line-free shots (e.g. in dialect-only mode)
            stale = out / f"narration-{i:04d}.wav"
            if stale.is_file():
                stale.unlink()

    if force:
        for i in active_rows:
            f = out / f"narration-{i:04d}.wav"
            if f.is_file():
                f.unlink()

    missing = [n for n in active_rows if not (out / f"narration-{n:04d}.wav").is_file()]
    if not missing:
        print(f"narration: all {len(active_rows)} active audio line(s) are here")
        return
    with tempfile.TemporaryDirectory() as tmp:
        worker = Path(tmp) / "kokoro_worker.py"
        worker.write_text(kokoro_worker())
        for lo, hi in spans(missing):
            subprocess.run([sys.executable, str(worker), str(d / csv_name), str(lo), str(hi), str(out)], check=True)


def spans(rows):
    """[1, 2, 3, 7] -> [(1, 3), (7, 7)]"""
    out: list[list[int]] = []
    for n in rows:
        if out and out[-1][1] == n - 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return [tuple(x) for x in out]


def music(d, scenes=False):
    rows = list(csv.DictReader(open(d / ("audio_scenes.csv" if scenes else "audio_chapters.csv"), newline="", encoding="utf-8")))
    out = d / "audio" / ("musicgen_scenes" if scenes else "musicgen_chapters")
    out.mkdir(parents=True, exist_ok=True)
    todo = [(i, r) for i, r in enumerate(rows, 1) if not (out / f"music-{i:04d}.wav").is_file()]
    if not todo:
        print(f"music: all {len(rows)} cue(s) are here")
        return
    import numpy as np
    import scipy.io.wavfile as wavfile
    from transformers import AutoProcessor, MusicgenForConditionalGeneration
    processor = AutoProcessor.from_pretrained("facebook/musicgen-small")
    model = MusicgenForConditionalGeneration.from_pretrained("facebook/musicgen-small")
    rate = model.config.audio_encoder.sampling_rate
    for i, r in todo:
        t = time.time()
        audio = model.generate(**processor(text=[r["music"]], padding=True, return_tensors="pt"), do_sample=True, guidance_scale=3.0, max_new_tokens=28 * 50)
        path = out / f"music-{i:04d}.wav"
        wavfile.write(str(path.with_suffix(".tmp.wav")), rate, audio[0, 0].numpy().astype(np.float32))
        path.with_suffix(".tmp.wav").replace(path)              # whole file or nothing, so an interrupted cue is made again
        print(f"cue {i}/{len(rows)}: {time.time() - t:.0f} s", flush=True)


def main():
    if len(sys.argv) != 3 or sys.argv[2] not in ("kokoro", "audiobook", "musicgen", "musicgen_scenes"):
        sys.exit(__doc__)
    try:
        d = layout.find_dir(sys.argv[1])
    except ValueError as e:
        sys.exit(str(e))
    if d is None:
        sys.exit(f"no such book: {sys.argv[1]}")
    if sys.argv[2] == "kokoro":
        narration(d)
    elif sys.argv[2] == "audiobook":                    # the audiobook: one row per scene of audiobook.csv (sound_design.py)
        narration(d, "audiobook.csv", "kokoro_audiobook")
    else:
        music(d, scenes=sys.argv[2] == "musicgen_scenes")


if __name__ == "__main__":
    main()
