#!/usr/bin/env python3
"""Run rows of a project's prompt CSV on a Kaggle GPU (or TPU) and bring the results home. Works on Windows and macOS.

  [PROJECT=adam_eve] KAGGLE_USER=yourname python scripts/run_kaggle_model.py MODEL START END
    MODEL = ltx_video | wan | cogvideox (video) | audio_kokoro | audio_musicgen | audio_mmaudio (audio) | image_sdxl_turbo | image_sdxl | ... (images)
  Optional in the environment:
    SHOTS_CSV=audio_shots.csv | all_chapters.csv | keyframes.csv ...    the prompt CSV (default by model kind)
    KAGGLE_ACCELERATOR=NvidiaTeslaT4 | TpuV5E8                           TPU only for tpu_* models
    KEYFRAME_MODEL=sdxl          image-to-video (*_i2v): the keyframe set to animate (default: the newest images/*_keyframes)
    UPSCALE_SOURCE=ltx_video_i2v upscalers (upscale_*): the clip folder to enlarge
    KAGGLE_PREFIX=mine-          put in front of every Kaggle name
    HF_TOKEN=...                 put into this private notebook copy only (faster model downloads); never written anywhere here

Uploads the prompt CSVs as a private dataset, runs the Kaggle notebook, waits, and downloads the results into the project
(videos/<model>, audio/<kind>, images/<model>, with _chapters / _scenes / _keyframes for those CSVs). The Python version of the old
run_kaggle_model.sh (which now only calls this); the Studio's job runner calls this directly.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaggle_names  # noqa: E402
from runner_common import ROOT, RunError, base_dir, csv_rows, default_csv, generated, log_tail, mode_of, need_tool, project_folder, run, say  # noqa: E402

DATA_FILES = ("all_shots.csv", "all_chapters.csv", "audio_shots.csv", "audio_chapters.csv", "audio_scenes.csv", "all_images.csv", "keyframes.csv")
RESULT_RE = re.compile(r"^(shot-.*\.mp4|.*\.wav|image-.*\.png)$")
WAIT_STATUS, WAIT_PUSH, PUSH_TRIES = 60, 120, 45


def _rows(start: int, end: int) -> range:
    return range(start, end + 1)


def check_accelerator(model: str, accel: str) -> None:
    tpu_model, tpu = model.startswith(("tpu_", "image_tpu_")), accel.startswith("Tpu")
    if tpu_model and not tpu:
        raise RunError(f"{model} needs a TPU: set KAGGLE_ACCELERATOR=TpuV5E8")
    if tpu and not tpu_model:
        raise RunError(f"only tpu_* models run on a TPU (got {model} on {accel})")


def keyframe_dir(pd: Path, model: str, shots_csv: str, start: int, end: int) -> Path | None:
    """Image-to-video models start each clip from its keyframe: images/<KEYFRAME_MODEL>_keyframes/image-NNNN.png."""
    if not model.endswith("_i2v"):
        return None
    if shots_csv != "all_shots.csv":
        raise RunError(f"{model} works per shot (all_shots.csv), not with {shots_csv}")
    named = os.environ.get("KEYFRAME_MODEL", "")
    kf: Path | None
    if named and not re.fullmatch(r"[a-z0-9_]{2,60}", named):
        raise RunError(f"bad KEYFRAME_MODEL: {named}")
    if named:
        kf = pd / "images" / f"{named}_keyframes"
    else:
        sets = sorted((p for p in (pd / "images").glob("*_keyframes") if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
        kf = sets[0] if sets else None
    if not kf or not kf.is_dir():
        raise RunError(f"!! {model} needs keyframes: make them first (no images/<model>_keyframes folder in {pd})")
    missing = [n for n in _rows(start, end) if not (kf / f"image-{n:04d}.png").is_file()]
    if missing:
        raise RunError(f"!! no keyframe in {kf} for row(s): {' '.join(map(str, missing))} - make keyframes for these rows first")
    say(f"== keyframes from {kf}")
    return kf


def upscale_dirs(pd: Path, model: str, shots_csv: str, start: int, end: int) -> tuple[Path, Path] | None:
    """Upscalers enlarge clips already made: videos/<UPSCALE_SOURCE>/shot-NNNN.mp4 -> videos/<UPSCALE_SOURCE>_<factor>."""
    if not model.startswith("upscale_"):
        return None
    if shots_csv != "all_shots.csv":
        raise RunError(f"{model} works per shot (all_shots.csv), not with {shots_csv}")
    src = os.environ.get("UPSCALE_SOURCE", "")
    if not src:
        raise RunError("set UPSCALE_SOURCE to the video folder to upscale (for example ltx_video_i2v)")
    if not re.fullmatch(r"[a-z0-9_]{2,60}", src):
        raise RunError(f"bad UPSCALE_SOURCE: {src}")
    up = pd / "videos" / src
    if not up.is_dir():
        raise RunError(f"!! no clips folder {up}")
    missing = [n for n in _rows(start, end) if not (up / f"shot-{n:04d}.mp4").is_file()]
    if missing:
        raise RunError(f"!! no clip in {up} for row(s): {' '.join(map(str, missing))}")
    out = pd / "videos" / f"{src}_{model[len('upscale_'):]}"
    say(f"== upscaling clips from {up} into {out}")
    return up, out


def fill_notebook(src: Path, dst: Path, start: int, end: int, csv_name: str) -> None:
    """A copy of the model's notebook with this run's rows and CSV filled in (and HF_TOKEN, when set, in a first cell)."""
    nb = json.loads(src.read_text(encoding="utf-8"))
    tok = os.environ.get("HF_TOKEN", "").strip()
    if tok:
        first = next(i for i, c in enumerate(nb["cells"]) if c["cell_type"] == "code")
        nb["cells"].insert(first, {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
                                   "source": ["import os\n", "os.environ['HF_TOKEN'] = " + repr(tok)]})
    for c in nb["cells"]:
        new = []
        for line in c["source"]:
            nl = "\n" if line.endswith("\n") else ""
            if line.startswith("START, END = "):
                line = f"START, END = {start}, {end}{nl}"
            elif line.startswith("CSV_NAME = "):
                line = f"CSV_NAME = '{csv_name}'{nl}"
            new.append(line)
        c["source"] = new
    dst.write_text(json.dumps(nb, indent=1), encoding="utf-8")


def upload_dataset(kaggle: str, user: str, ds: str, folder: Path, shots_csv: str, need_rows: int, end: int) -> None:
    (folder / "dataset-metadata.json").write_text(json.dumps({"title": ds.replace("-", " "), "id": f"{user}/{ds}", "licenses": [{"name": "CC0-1.0"}]}),
                                                  encoding="utf-8")
    ref = f"{user}/{ds}"
    if run([kaggle, "datasets", "files", ref], capture_output=True).returncode == 0:
        say(f"== updating dataset {ref}")
        if run([kaggle, "datasets", "version", "-p", str(folder), "-m", "update prompts", "-t", "-q"]).returncode != 0:
            say("(dataset unchanged or update failed; continuing with the existing version)")
    else:
        say(f"== creating private dataset {ref}")
        if run([kaggle, "datasets", "create", "-p", str(folder), "-t", "-q"]).returncode != 0:
            raise RunError(f"could not create the dataset {ref}")
    say("== waiting for dataset to be ready")
    for _ in range(30):
        r = run([kaggle, "datasets", "status", ref], capture_output=True)
        if "ready" in (r.stdout + r.stderr).lower():
            break
        time.sleep(10)
    # "ready" can describe the PREVIOUS version while the new one is still being made, and a notebook that starts then sees the old CSV and
    # does nothing. So wait until Kaggle's copy of the CSV has the rows this run needs.
    if need_rows < end:
        return
    say(f"== checking that Kaggle's copy of {shots_csv} has row {end}")
    with tempfile.TemporaryDirectory(prefix="studio-chk-") as chk:
        for _ in range(30):
            for p in Path(chk).iterdir():
                p.unlink() if p.is_file() else shutil.rmtree(p, ignore_errors=True)
            r = run([kaggle, "datasets", "download", ref, "-f", shots_csv, "-p", chk, "--unzip", "-q"], capture_output=True)
            if r.returncode == 0 and (Path(chk) / shots_csv).is_file():
                have = csv_rows(Path(chk) / shots_csv)
                if have >= end:
                    return
                say(f"   Kaggle has {have} rows, need {end}; waiting 10 s")
            time.sleep(10)
    say(f"!! Kaggle's copy never showed row {end}; continuing anyway (the notebook may find too few rows)")


def push(kaggle: str, folder: Path, accel: str) -> None:
    """`kaggle kernels push` can print an error and still exit 0, so the text is checked. Kaggle runs only 2 GPU sessions at a time: when both
    are busy, wait and try again."""
    text = ""
    for attempt in range(1, PUSH_TRIES + 1):
        r = run([kaggle, "kernels", "push", "-p", str(folder), "--accelerator", accel], capture_output=True)
        text = r.stdout + r.stderr
        say(text.rstrip())
        if "successfully pushed" in text.lower():
            return
        if re.search(r"maximum .*session count", text, re.I):
            say(f"== Kaggle allows only 2 GPU sessions at a time and both are busy; waiting 2 minutes (try {attempt} of {PUSH_TRIES})")
            time.sleep(WAIT_PUSH)
            continue
        break
    raise RunError(f"!! kernel push failed: {' '.join(text.split())[:300]}")


def wait_for(kaggle: str, ref: str) -> tuple[str, bool]:
    """Check every minute until the run ends. (status text, failed?)"""
    while True:
        r = run([kaggle, "kernels", "status", ref], capture_output=True)
        status = (r.stdout + r.stderr).strip()
        say(f"{time.strftime('%H:%M:%S')} {status}")
        low = status.lower()
        if "complete" in low:
            say("== kernel completed")
            return status, False
        if any(w in low for w in ("error", "cancel", "fail")):
            say(f"!! kernel run did not complete successfully (status: {status}); fetching whatever output exists")
            return status, True
        if "not found" in low or "404" in low or "cannot access kernel" in low:
            raise RunError("!! kernel not found on Kaggle (may have been deleted or never created)")
        if "queued" in low:
            say("== kernel is queued, waiting for resources...")
        elif "running" in low:
            say("== kernel is running...")
        time.sleep(WAIT_STATUS)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        say(__doc__ or "")
        return 1
    model, start, end = argv[0], int(argv[1]), int(argv[2])
    project = os.environ.get("PROJECT") or "adam_eve"
    user = os.environ.get("KAGGLE_USER", "")
    if not user:
        raise RunError("set KAGGLE_USER to your Kaggle username (the part after kaggle.com/)")
    pd = project_folder(project)
    shots_csv = os.environ.get("SHOTS_CSV") or default_csv(model)
    accel = os.environ.get("KAGGLE_ACCELERATOR") or "NvidiaTeslaT4"
    check_accelerator(model, accel)
    with generated(f"Studio_Kaggle_{model}.ipynb") as nb:
        if not nb.is_file():
            raise RunError(f"no such model: {model} (missing {nb.name})")
        kaggle = need_tool("kaggle", "uv tool install kaggle")
        mode = mode_of(shots_csv)
        out_dir = base_dir(pd, model).with_name(base_dir(pd, model).name + (f"_{mode}" if mode else ""))
        kf = keyframe_dir(pd, model, shots_csv, start, end)
        up = upscale_dirs(pd, model, shots_csv, start, end)
        if up:
            out_dir = up[1]
        prefix = os.environ.get("KAGGLE_PREFIX", "")
        name = prefix + project.replace("_", "-")
        ds = kaggle_names.fit(name, "-prompts")
        slug = kaggle_names.fit(name, f"-{model.replace('_', '-')}{'-' + mode if mode else ''}-{start}-{end}")
        ref = f"{user}/{slug}"
        with tempfile.TemporaryDirectory(prefix="studio-kaggle-") as work_:
            work = Path(work_)
            # 1. dataset with the prompt CSVs (made once, a new version afterwards), plus this run's pictures or clips, flat beside the CSV
            dsd = work / "ds"
            dsd.mkdir()
            for f in DATA_FILES:
                if (pd / f).is_file():
                    shutil.copy2(pd / f, dsd / f)
            if shots_csv in ("keyframes.csv", "all_images.csv") and (pd / "keyframe_refs").is_dir():
                for ref_pic in (pd / "keyframe_refs").glob("ref-*.png"):
                    shutil.copy2(ref_pic, dsd / ref_pic.name)
            if up:
                for n in _rows(start, end):
                    shutil.copy2(up[0] / f"shot-{n:04d}.mp4", dsd / f"in-{n:04d}.mp4")
                    wav = pd / "audio" / "kokoro" / f"narration-{n:04d}.wav"
                    if model == "upscale_lipsync" and wav.is_file():
                        shutil.copy2(wav, dsd / f"a-{n:04d}.wav")
            if kf:
                for n in _rows(start, end):
                    shutil.copy2(kf / f"image-{n:04d}.png", dsd / f"kf-{n:04d}.png")
            upload_dataset(kaggle, user, ds, dsd, shots_csv, csv_rows(pd / shots_csv), end)
            # 2. notebook copy with this run's rows and CSV
            nbd = work / "nb"
            nbd.mkdir()
            fill_notebook(nb, nbd / f"{slug}.ipynb", start, end, shots_csv)
            gpu = not accel.startswith("Tpu")
            meta = {"id": ref, "title": slug.replace("-", " "), "code_file": f"{slug}.ipynb", "language": "python", "kernel_type": "notebook",
                    "is_private": "true", "enable_gpu": str(gpu).lower(), "enable_tpu": str(not gpu).lower(), "enable_internet": "true",
                    "machine_shape": accel, "dataset_sources": [f"{user}/{ds}"], "competition_sources": [], "kernel_sources": [], "model_sources": []}
            (nbd / "kernel-metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            # 3. push (this also starts the run) and wait
            say(f"== pushing kernel {ref} on {accel}")
            push(kaggle, nbd, accel)
            say(f"== kernel pushed: https://www.kaggle.com/code/{ref}")
            say("== waiting for the run (checks every 60 s; Ctrl-C stops waiting, the run continues on Kaggle)")
            status, failed = wait_for(kaggle, ref)
            # 4. download and flatten into the results folder
            outd = work / "out"
            outd.mkdir()
            out_dir.mkdir(parents=True, exist_ok=True)
            run([kaggle, "kernels", "output", ref, "-p", str(outd), "-o"])
            logs = pd / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            for logf in outd.glob("*.log"):
                shutil.copy2(logf, logs / logf.name)
            if failed:
                say(f"\n----- end of the Kaggle log (full log: {logs / (slug + '.log')}) -----\n{log_tail(logs / (slug + '.log'), 3500)}\n-----")
            got = [p for p in outd.rglob("*") if p.is_file() and RESULT_RE.match(p.name)]
            for p in got:
                shutil.move(str(p), str(out_dir / p.name))
    have = sum(1 for p in out_dir.iterdir() if p.suffix in (".mp4", ".wav", ".png"))
    say(f"✅ {have} files now in {out_dir}")
    say(f"   Log and page: https://www.kaggle.com/code/{ref}   (log saved in {pd / 'logs'})")
    if failed and not got:
        say("!! the run failed and made nothing")          # later steps must not carry on as if it had worked
        return 1
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
