#!/usr/bin/env python3
"""Run one model on THIS computer's NVIDIA GPU: the same notebook Kaggle runs, with no website or account involved.

Usage:  PROJECT=<book or set> [SHOTS_CSV=...] [KEYFRAME_MODEL=...] [UPSCALE_SOURCE=...] python3 scripts/run_local_model.py MODEL START END
        (the same models, rows and settings as scripts/run_kaggle_model.sh; the Studio's "This computer" choice calls this)

What it does, in order:
  1. Puts the files a Kaggle run would upload (the prompt CSVs, character pictures, keyframes kf-NNNN.png, clips to upscale
     in-NNNN.mp4) in a fresh run folder: <run>/input. Outputs are written to <run>/working, as /kaggle/working would be.
  2. Turns the Kaggle notebook into a plain Python script: /kaggle/input and /kaggle/working point at those folders, the
     "!pip ..." lines are taken out (step 3 runs them once), and "apt-get" lines only check that the program is there.
  3. Runs it with a Python environment of its own (.gpu_envs/<recipe>/ at the repository root), made the first time a model
     with that install recipe runs: Python 3.11, PyTorch for CUDA, the packages a Kaggle notebook has to begin with, then the
     notebook's own "!pip" lines. Later runs reuse it, so only the first run of each kind installs anything.
  4. Moves the clips, images or sounds into the project (videos/<model>, images/<model>, audio/<kind>, as the Kaggle runner
     does) and keeps the log in <project>/logs/local-<run>.log.

Needs: Linux (or Windows through WSL 2) with an NVIDIA GPU and driver (nvidia-smi), uv (install.sh installs it) and git.
FlashVSR also needs the CUDA compiler (nvcc). Model weights download from Hugging Face the first time and are kept in its cache
(~/.cache/huggingface), so later runs work offline (set HF_HUB_OFFLINE=1 to make sure nothing is fetched).

Settings (environment):  STUDIO_GPU_PYTHON=/path/to/python   use an existing Python that already has CUDA PyTorch (no environment is made;
                                                             the notebook's pip lines still run in it)
                         STUDIO_GPU_ENVS=/some/folder          where the environments go (default .gpu_envs in the repository)
                         STUDIO_TORCH_INDEX=https://download.pytorch.org/whl/cu128   which PyTorch build to install (default: PyPI's, CUDA on Linux)
                         HF_TOKEN=...                          passed through to the run (gated models, faster downloads)
"""
import csv
import hashlib
import json
import os
import re
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout  # noqa: E402  (project-local: finds projects/books/<book>)

ROOT = Path(__file__).resolve().parent.parent
MODEL_RE = re.compile(r"^[a-z0-9_]{2,60}$")
PY_VERSION = "3.11"                   # what Kaggle's notebooks run on; every generator here is tested with it
# What a Kaggle notebook has before its first line runs; the generators count on these being there.
BASE_PACKAGES = ["numpy", "pillow", "scipy", "pandas", "imageio", "imageio-ffmpeg", "soundfile", "tqdm", "einops", "requests",
                 "huggingface_hub", "safetensors", "transformers", "accelerate", "sentencepiece", "protobuf", "opencv-python-headless", "uv"]
OUTPUT_GLOBS = ("shot-*.mp4", "*.wav", "image-*.png")


def die(msg):
    print("!! " + msg, flush=True)
    sys.exit(1)


def gpu_info():
    """[(name, GB, compute capability)] for each NVIDIA GPU, from nvidia-smi; [] if there is none or no driver."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "--query-gpu=name,memory.total,compute_cap", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            try:
                gpus.append((parts[0], round(float(parts[1]) / 1024, 1), parts[2] if len(parts) > 2 else ""))
            except ValueError:
                continue
    return gpus


def csv_rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return len(list(csv.DictReader(fh)))


def find_notebook(model, tmp):
    """The Kaggle notebook for this model: the repository's copy, else one generated into tmp (as the Kaggle runner does)."""
    nb = ROOT / f"Studio_Kaggle_{model}.ipynb"
    if nb.is_file():
        return nb
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_all.py")], env={**os.environ, "STUDIO_GEN_DIR": str(tmp)},
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    nb = Path(tmp) / f"Studio_Kaggle_{model}.ipynb"
    if not nb.is_file():
        die(f"no such model: {model} (no Studio_Kaggle_{model}.ipynb)")
    return nb


def to_script(nb_path, start, end, csv_name, inp, work):
    """(script text, pip lines): the notebook's code cells as one script for this computer, and its "!pip ..." commands."""
    nb = json.loads(Path(nb_path).read_text(encoding="utf-8"))
    pip, lines = [], []
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        for raw in "".join(cell.get("source", [])).splitlines():
            stripped = raw.lstrip()
            indent = raw[: len(raw) - len(stripped)]
            if stripped.startswith("!"):
                cmd = stripped[1:].strip()
                if re.match(r"(pip|pip3)\s", cmd):
                    pip.append(cmd)                  # installed into the environment before the run (see make_env)
                    lines.append(indent + "pass  # " + cmd[:80].replace("\\", "/"))
                else:
                    lines.append(indent + f"_studio_sh({cmd!r})")
                continue
            if stripped.startswith("%"):
                lines.append(indent + "pass")          # notebook magics mean nothing in a script
                continue
            if raw.startswith("START, END = "):
                raw = f"START, END = {start}, {end}"
            elif raw.startswith("CSV_NAME = "):
                raw = f"CSV_NAME = {csv_name!r}"
            raw = raw.replace("/kaggle/input", inp.as_posix()).replace("/kaggle/working", work.as_posix())
            raw = re.sub(r"""\bsh\((f?["'])apt-get""", r"_studio_apt(\1apt-get", raw)
            lines.append(raw)
        lines.append("")
    prelude = f'''# Generated by run_local_model.py from {Path(nb_path).name}: runs on this computer's GPU.
import os as _os, shutil as _shutil, subprocess as _subprocess
_os.chdir({work.as_posix()!r})


def _studio_sh(cmd):
    _subprocess.run(cmd, shell=True, check=True)


def _studio_apt(cmd):
    """Kaggle installs system programs with apt-get; here they must already be installed (it needs root). Warn and go on."""
    pkgs = [p for p in cmd.split() if p not in ("apt-get", "-qq", "-y", "update", "install", "&&", ">", "/dev/null", "-q")]
    missing = [p for p in pkgs if not _shutil.which(p)]
    if missing:
        print("!! not installed on this computer: " + ", ".join(missing) + " (install with your package manager, for example sudo apt install " + " ".join(missing) + "); going on without", flush=True)


import torch as _torch
if not _torch.cuda.is_available():
    raise SystemExit("PyTorch in this environment cannot see a CUDA GPU (check the NVIDIA driver, or set STUDIO_TORCH_INDEX to a PyTorch build for your CUDA)")
'''
    return prelude + "\n".join(lines) + "\n", pip


def run_logged(argv, log, **kw):
    """Run, printing and logging each line as it comes. Returns the exit code."""
    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, **kw) as p:
        for line in p.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
        return p.wait()


def keep_torch(cmd):
    """A notebook's pip line without torch / torchvision / torchaudio: Kaggle upgrades them over its old build, but here the
    environment already has the CUDA build chosen for this computer, which a plain PyPI upgrade could replace."""
    if not re.match(r"pip3?\s+install\s", cmd):
        return cmd
    words = [w for w in cmd.split() if w not in ("torch", "torchvision", "torchaudio")]
    return " ".join(words) if any(not w.startswith("-") for w in words[2:]) else ""


def make_env(pip_lines, log):
    """The Python for this recipe: STUDIO_GPU_PYTHON, or .gpu_envs/<hash of the pip lines>/, made once."""
    pip_lines = [c for c in (keep_torch(x) for x in pip_lines) if c]
    own = os.environ.get("STUDIO_GPU_PYTHON", "").strip()
    if own:
        py = Path(own)
        if not py.is_file():
            die(f"STUDIO_GPU_PYTHON={own} does not exist")
        for cmd in pip_lines:
            if run_logged(f"{shlex_quote(py)} -m {cmd}", log, shell=True) != 0:
                die(f"failed: {cmd}")
        return py
    index = os.environ.get("STUDIO_TORCH_INDEX", "").strip()
    recipe = json.dumps({"py": PY_VERSION, "base": BASE_PACKAGES, "torch_index": index, "pip": pip_lines})
    key = hashlib.sha1(recipe.encode()).hexdigest()[:12]
    envs = Path(os.environ.get("STUDIO_GPU_ENVS") or ROOT / ".gpu_envs")
    env = envs / key
    py = env / "bin" / "python"
    if (env / ".studio_ready").is_file() and py.is_file():
        print(f"== Python environment {env} (made earlier)", flush=True)
        return py
    uv = shutil.which("uv") or shutil.which("uv", path=f"{Path.home()}/.local/bin:{ROOT / '.venv' / 'bin'}")
    if not uv:
        die("uv is not installed (run ./install.sh, or: curl -LsSf https://astral.sh/uv/install.sh | sh)")
    if env.exists():
        shutil.rmtree(env)                    # a half-made environment from a run that stopped: start it again
    envs.mkdir(parents=True, exist_ok=True)
    print(f"== making the Python environment {env} (first run of this kind only: several GB, a few minutes)", flush=True)
    (envs / "README.txt").write_text("Python environments for running the models on this computer (scripts/run_local_model.py).\n"
                                     "Each folder is one install recipe; delete any of them to free space, it is made again when needed.\n")
    steps = [[uv, "venv", "-q", "--python", PY_VERSION, "--seed", str(env)],
             [uv, "pip", "install", "-q", "--python", str(py), "torch", "torchvision", "torchaudio"] + (["--index-url", index] if index else []),
             [uv, "pip", "install", "-q", "--python", str(py)] + BASE_PACKAGES]
    for argv in steps:
        if run_logged(argv, log) != 0:
            die("could not make the environment: " + " ".join(argv[:4]))
    for cmd in pip_lines:                      # the notebook's own installs, as Kaggle would run them
        print("== " + cmd, flush=True)
        if run_logged(f"{shlex_quote(py)} -m {cmd}", log, shell=True) != 0:
            die(f"failed: {cmd}")
    (env / "recipe.json").write_text(recipe)
    (env / ".studio_ready").write_text(time.strftime("%Y-%m-%d %H:%M"))
    return py


def shlex_quote(p):
    return shlex.quote(str(p))


def main(argv=None):
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))     # the Studio's Stop button: still remove the run folder on the way out
    args = (argv if argv is not None else sys.argv[1:])
    if len(args) != 3:
        sys.exit(__doc__)
    model, start, end = args[0], args[1], args[2]
    if not MODEL_RE.match(model):
        die(f"bad model name {model!r}")
    try:
        start, end = int(start), int(end)
    except ValueError:
        die("START and END must be row numbers")
    if not 1 <= start <= end:
        die("rows must be 1 or more, END not before START")
    if model.startswith(("tpu_", "image_tpu_")):
        die(f"{model} runs only on Kaggle's TPU")
    project = os.environ.get("PROJECT", "")
    try:
        pd = layout.find_dir(project)
    except ValueError as e:
        die(str(e))
    if pd is None:
        die(f"no such project: {project}")
    kind = "audio" if model.startswith("audio_") else "image" if model.startswith("image_") else "video"
    shots_csv = os.environ.get("SHOTS_CSV") or {"audio": "audio_shots.csv", "image": "all_images.csv"}.get(kind, "all_shots.csv")
    if not re.fullmatch(r"[a-z_]{3,40}\.csv", shots_csv) or not (pd / shots_csv).is_file():
        die(f"{pd / shots_csv} not found: build the CSVs first")
    have = csv_rows(pd / shots_csv)
    if have < end:
        die(f"{shots_csv} has {have} rows, the run asks for rows up to {end}")

    gpus = gpu_info()
    if not gpus:
        die("no NVIDIA GPU found on this computer (nvidia-smi is missing or lists none). Use Kaggle, Colab or Hugging Face instead.")
    print("== GPU: " + "; ".join(f"{n} ({gb:g} GB)" for n, gb, _ in gpus), flush=True)

    base = {"audio": pd / "audio" / model.removeprefix("audio_"), "image": pd / "images" / model.removeprefix("image_")}.get(kind, pd / "videos" / model)
    outdir, mode = base, ""
    if "chapters" in shots_csv:
        outdir, mode = Path(f"{base}_chapters"), "-chapters"
    elif shots_csv.startswith("keyframes"):
        outdir, mode = Path(f"{base}_keyframes"), "-keyframes"
    rows = range(start, end + 1)
    copies = []                                       # (source file, name in the input folder)
    if model.endswith("_i2v"):                         # image-to-video: each row's keyframe, as kf-NNNN.png
        if shots_csv != "all_shots.csv":
            die(f"{model} works per shot (all_shots.csv), not with {shots_csv}")
        kfm = os.environ.get("KEYFRAME_MODEL", "")
        if kfm:
            if not MODEL_RE.match(kfm):
                die(f"bad KEYFRAME_MODEL {kfm!r}")
            kfdir = pd / "images" / f"{kfm}_keyframes"
        else:
            sets = sorted((pd / "images").glob("*_keyframes"), key=lambda p: p.stat().st_mtime, reverse=True)
            kfdir = sets[0] if sets else None
        if not kfdir or not kfdir.is_dir():
            die(f"{model} needs keyframes: make them first (no images/<model>_keyframes folder in {pd})")
        missing = [n for n in rows if not (kfdir / f"image-{n:04d}.png").is_file()]
        if missing:
            die(f"no keyframe in {kfdir} for row(s): {' '.join(map(str, missing))} - make keyframes for these rows first")
        copies += [(kfdir / f"image-{n:04d}.png", f"kf-{n:04d}.png") for n in rows]
        print(f"== keyframes from {kfdir}", flush=True)
    if model.startswith("upscale_"):                   # upscalers: the clips already made, as in-NNNN.mp4
        if shots_csv != "all_shots.csv":
            die(f"{model} works per shot (all_shots.csv), not with {shots_csv}")
        src = os.environ.get("UPSCALE_SOURCE", "")
        if not re.fullmatch(r"[a-z0-9_]{2,60}", src):
            die("set UPSCALE_SOURCE to the video folder to upscale (for example ltx_video_i2v)")
        updir = pd / "videos" / src
        if not updir.is_dir():
            die(f"no clips folder {updir}")
        missing = [n for n in rows if not (updir / f"shot-{n:04d}.mp4").is_file()]
        if missing:
            die(f"no clip in {updir} for row(s): {' '.join(map(str, missing))}")
        copies += [(updir / f"shot-{n:04d}.mp4", f"in-{n:04d}.mp4") for n in rows]
        outdir = pd / "videos" / f"{src}_{model.removeprefix('upscale_')}"
        print(f"== upscaling clips from {updir} into {outdir}", flush=True)

    slug = f"{project.replace('_', '-')}-{model.replace('_', '-')}{mode}-{start}-{end}"
    (pd / "logs").mkdir(exist_ok=True)
    log_path = pd / "logs" / f"local-{slug}.log"
    with tempfile.TemporaryDirectory(prefix="studio-run-") as tmp, open(log_path, "w", encoding="utf-8") as log:
        tmp = Path(tmp)
        inp, work = tmp / "input" / "dataset", tmp / "working"
        inp.mkdir(parents=True)
        work.mkdir()
        for f in ("all_shots.csv", "all_chapters.csv", "audio_shots.csv", "audio_chapters.csv", "all_images.csv", "keyframes.csv"):
            if (pd / f).is_file():
                shutil.copyfile(pd / f, inp / f)
        if shots_csv == "keyframes.csv" and (pd / "keyframe_refs").is_dir():      # character pictures (make_keyframes_csv.py --refs)
            for p in (pd / "keyframe_refs").glob("ref-*.png"):
                shutil.copyfile(p, inp / p.name)
        for src_file, name in copies:
            shutil.copyfile(src_file, inp / name)

        script, pip_lines = to_script(find_notebook(model, tmp), start, end, shots_csv, tmp / "input", work)
        (tmp / "run.py").write_text(script, encoding="utf-8")
        py = make_env(pip_lines, log)
        cache = Path(os.environ.get("STUDIO_GPU_ENVS") or ROOT / ".gpu_envs") / "cache"     # programs the upscalers install, kept between runs
        cache.mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV")}
        env.update({"PYTHONUNBUFFERED": "1", "STUDIO_CACHE": str(cache), "MPLBACKEND": "Agg"})
        print(f"== running {model} rows {start}-{end} on this computer (log: {log_path})", flush=True)
        t = time.time()
        code = run_logged([str(py), str(tmp / "run.py")], log, cwd=str(work), env=env)
        print(f"== finished in {(time.time() - t) / 60:.1f} min" + ("" if code == 0 else f" with errors (exit {code}); keeping whatever was made"), flush=True)

        outdir.mkdir(parents=True, exist_ok=True)
        moved = 0
        for pattern in OUTPUT_GLOBS:
            for f in work.rglob(pattern):
                shutil.move(str(f), str(outdir / f.name))
                moved += 1
    print(f"{'✅' if code == 0 else '!!'} {moved} file(s) now in {outdir}", flush=True)
    sys.exit(0 if code == 0 else 1)


if __name__ == "__main__":
    main()
