"""Write the TPU notebooks: python3 scripts/make_tpu.py  ->  Bible_Kaggle_tpu_wan.ipynb (video),
Bible_Kaggle_image_tpu_mage_flow.ipynb and Bible_Kaggle_image_tpu_flux_jax.ipynb (text to image)

EXPERIMENTAL and untested. Runs Wan 2.1 text-to-video on a Kaggle TPU v5e-8 with Google's MaxDiffusion (pure JAX).
Facts used (from MaxDiffusion's README / config / generate_wan.py): config base_wan_14b.yml (the 14B model
Wan-AI/Wan2.1-T2V-14B-Diffusers, there is no 1.3B config), prompt_file = one prompt per line, videos are written as
<output_dir>/<run_name>_<seed>_<index>.mp4, setup.sh wants Python 3.12 and builds a venv when it is older.
"""
import json
from pathlib import Path
import os as _os
root = Path(_os.environ["BIBLE_GEN_DIR"]) if _os.environ.get("BIBLE_GEN_DIR") else Path(__file__).resolve().parent.parent   # BIBLE_GEN_DIR: write somewhere else (the run scripts use a throw-away folder)


def md(t): return {"cell_type": "markdown", "metadata": {}, "source": t.strip().splitlines(True)}
def code(t): return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": t.strip().splitlines(True)}


INTRO = """
# Bible film: Wan 2.1 14B on a Kaggle TPU v5e-8 (EXPERIMENT)

Uses Google's **MaxDiffusion** (JAX). **Nothing here has been run.** The first run is for learning what Kaggle's TPU allows,
so every stage prints what it found and stops with the evidence if it cannot continue.

Set the notebook to **Accelerator = TPU v5e-8** and **Internet = On**, attach the dataset with the prompt CSV, then Run All.

Limits to expect:
- The model is the 14-billion-parameter Wan (about 28 GB of weights in bf16, more on disk). Downloading it every session takes a long time and needs lots of free disk; the diagnostics cell prints how much you have.
- It loads the model once and renders all selected rows, so keep `START, END` small.
- Size, frames and steps are the same for every row in a run (per-row columns are ignored here).
- MaxDiffusion wants Python 3.12 and Ubuntu 22.04; if Kaggle's image is older its setup script builds a virtual environment, which may or may not work on Kaggle.
"""

DIAG = """
import os, platform, shutil, sys
print("python", sys.version.split()[0], "|", platform.platform())
for path in ("/kaggle/working", "/tmp"):
    u = shutil.disk_usage(path)
    print(f"{path}: {u.free // 2**30} GB free of {u.total // 2**30} GB")
print("RAM:", os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // 2**30, "GB")
import glob
print("accelerator device nodes:", sorted(glob.glob('/dev/accel*') + glob.glob('/dev/vfio/*')) or "none found")
print("TPU-related environment:", {k: v for k, v in os.environ.items() if any(t in k.upper() for t in ('TPU', 'PJRT', 'XLA'))} or "none")
try:
    import jax
    print("jax", jax.__version__, "| devices:", jax.devices())
except Exception as e:
    print("jax is not usable in the default environment:", e)
"""

CONFIG = """
import csv, re, subprocess
from pathlib import Path

CSV_NAME = 'all_shots.csv'
CSV_PATH = next(Path('/kaggle/input').rglob(CSV_NAME))
START, END = 1, 1             # CSV rows (1-based). Keep small: the 14B model is loaded once per run.
WIDTH, HEIGHT = 832, 480      # 480p keeps memory use low
NUM_FRAMES = 33               # must be 4*k+1; 33 frames = about 2 s at 16 fps
STEPS = 30
GUIDANCE = 5.0
FPS = 16
OUT = Path('/kaggle/working/videos/tpu_wan')
OUT.mkdir(parents=True, exist_ok=True)
rows = list(csv.DictReader(open(CSV_PATH, newline='')))
sel = rows[START - 1:END]
print(len(sel), 'prompt(s):', [r['prompt'][:60] for r in sel])
"""

INSTALL = """
WORK = Path('/tmp/mdf'); WORK.mkdir(exist_ok=True)

def sh(cmd, cwd=None):
    print('$', cmd[:300])
    r = subprocess.run(cmd, shell=True, cwd=cwd, text=True, capture_output=True, executable='/bin/bash')
    print((r.stdout + r.stderr)[-2500:])
    return r.returncode

if not (WORK / 'maxdiffusion').exists():
    assert sh('git clone --depth 1 https://github.com/AI-Hypercomputer/maxdiffusion.git', cwd=WORK) == 0, 'git clone failed (is Internet on?)'
REPO = WORK / 'maxdiffusion'
VENV = REPO / 'maxdiffusion_venv'

# setup.sh asks two questions when Python is older than 3.12 (create a venv? what name?), creates the venv and exits;
# MaxDiffusion's README says to run it again inside the venv, up to three times in total.
ready = False
for attempt in range(1, 4):
    act = f'source {VENV}/bin/activate && ' if (VENV / 'bin' / 'activate').exists() else ''
    sh(f"{act}printf 'y\\\\nmaxdiffusion_venv\\\\n' | bash setup.sh MODE=stable DEVICE=tpu", cwd=REPO)
    act = f'source {VENV}/bin/activate && ' if (VENV / 'bin' / 'activate').exists() else ''
    if sh(f"{act}python -c \\"import jax, maxdiffusion; print('jax', jax.__version__, jax.devices())\\"", cwd=REPO) == 0:
        ready = True
        break
print('MaxDiffusion ready:', ready)
assert ready, 'setup did not produce a working environment; read the output above (this is the useful result of the experiment)'
"""

RUN = """
pf = WORK / 'prompts.txt'
pf.write_text('\\n'.join(' '.join(r['prompt'].split()) for r in sel))      # one prompt per line
out_dir = WORK / 'out'; out_dir.mkdir(exist_ok=True)
cmd = (f"{act}HF_HUB_CACHE=/tmp/hf_cache python src/maxdiffusion/generate_wan.py src/maxdiffusion/configs/base_wan_14b.yml "
       f"attention=flash num_inference_steps={STEPS} num_frames={NUM_FRAMES} width={WIDTH} height={HEIGHT} guidance_scale={GUIDANCE} "
       f"fps={FPS} flow_shift=5.0 per_device_batch_size=0.125 ici_data_parallelism=2 ici_context_parallelism=4 "      # 8 chips, batch of 1
       f"prompt_file={pf} output_dir={out_dir} run_name=bible seed=0 jax_cache_dir=/tmp/jax_cache")
code_ = sh(cmd, cwd=REPO)
made = sorted(out_dir.glob('*.mp4'), key=lambda p: int(re.search(r'_(\\d+)\\.mp4$', p.name).group(1)))
for p in made:
    idx = int(re.search(r'_(\\d+)\\.mp4$', p.name).group(1))
    dest = OUT / f'shot-{START + idx:04d}.mp4'                 # same numbering as the other video models
    shutil.copy2(p, dest)
    print('saved', dest)
print('exit code', code_, '| videos:', len(made))
assert made, 'no videos were produced; read the output above'
"""


def notebook():
    cells = [md(INTRO), code(DIAG), code(CONFIG), code(INSTALL), code(RUN)]
    return {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "name": "python3"}}, "nbformat": 4, "nbformat_minor": 0}


json.dump(notebook(), open(root / "Bible_Kaggle_tpu_wan.ipynb", "w"), indent=1)
print("wrote Bible_Kaggle_tpu_wan.ipynb")


# ---------------------------------------------------------------------------------------------------------------
# Text-to-image on the TPU. Both are JAX conversions published on Hugging Face; neither has been run by me.
# Facts used: dangkhoa2016/Mage-Flow-Turbo-JAX-TPU-v5e8 model card + its bootstrap/07_generate.py (author reports it was
# verified on Kaggle TPU v5e-8; flags --prompt --resolution {512,768,1024} --topology {1x8,2x4,4x2} --seeds --runtime-site --output;
# writes <output>/vae/seed_<seed>.png, one image per replica = 4 for 4x2; wheels in the support tarball are cp312);
# jcopo/flux_jax model card (FLUX.1-dev in Orbax format, run with the `diffuse` library).
# ---------------------------------------------------------------------------------------------------------------
IMG_COMMON_DIAG = DIAG

MAGE_INTRO = """
# Bible film: Mage-Flow-Turbo (JAX) on a Kaggle TPU v5e-8, text to image

Text to image only. The model is Microsoft's **Mage-Flow-Turbo** converted to JAX by *dangkhoa2016* (MIT and Apache-2.0 parts, see the repo's LICENSES.md):
https://huggingface.co/dangkhoa2016/Mage-Flow-Turbo-JAX-TPU-v5e8 . The author reports generating images with it on a Kaggle TPU v5e-8; **I have not run this notebook.**

Set **Accelerator = TPU v5e-8** and **Internet = On**, attach the dataset with `all_images.csv`, then Run All.

What to expect:
- About 14 GB are downloaded each session. The runner needs **Python 3.12** (its offline wheels are built for it) but Kaggle's TPU image runs 3.13, so the notebook builds a 3.12 environment with `uv` first (needs Internet).
- Each prompt makes **4 images** (4 seeds) in one run on the qualified 4x2 layout. The first becomes `image-NNNN.png`, the others `image-NNNN_alt1.png` ... `_alt3.png`.
- Every prompt starts the model from scratch (the author's runner is a one-shot script), so a row takes minutes; keep `START, END` small.
- Resolution is 512, 768 or 1024 (square); steps are fixed at 4.
"""

MAGE_CONFIG = """
import csv, shlex, shutil, subprocess, sys
from pathlib import Path

CSV_NAME = 'all_images.csv'
CSV_PATH = next(Path('/kaggle/input').rglob(CSV_NAME))
START, END = 1, 1          # CSV rows (1-based)
RESOLUTION = 512           # 512, 768 or 1024 (a row's width/height picks the nearest of these)
TOPOLOGY = '4x2'           # the qualified layout: 4 replicas = 4 seeds per prompt
OUT = Path('/kaggle/working/images/tpu_mage_flow')
OUT.mkdir(parents=True, exist_ok=True)
rows = list(csv.DictReader(open(CSV_PATH, newline='')))
print(len(rows), 'rows;', 'using', START, 'to', min(END, len(rows)))
"""

MAGE_DOWNLOAD = """
from huggingface_hub import snapshot_download
MODEL_ROOT = Path(snapshot_download('dangkhoa2016/Mage-Flow-Turbo-JAX-TPU-v5e8', local_dir='/tmp/mage_model',
                                    ignore_patterns=['assets/*']))
print('downloaded to', MODEL_ROOT)
"""

MAGE_SETUP = """
WORK = Path('/tmp/mage-flow-turbo-jax'); WORK.mkdir(exist_ok=True)
SITE = Path('/tmp/mage_site')

def sh(cmd, cwd=None):
    print('$', cmd[:240])
    r = subprocess.run(cmd, shell=True, cwd=cwd, text=True, capture_output=True, executable='/bin/bash')
    print((r.stdout + r.stderr)[-2500:])
    return r.returncode

if not (WORK / 'bootstrap').exists():
    assert sh(f'tar -xzf {MODEL_ROOT}/mage-flow-tpu-support.tar.gz -C {WORK}') == 0, 'could not unpack the support package'
for name in ('checkpoints', 'text_encoder'):
    link = WORK / name
    if not link.exists():
        link.symlink_to(MODEL_ROOT / name)
# The package's offline wheels are built for Python 3.12, but Kaggle's TPU image runs 3.13 (the first run failed on exactly this:
# "Could not find a version that satisfies the requirement jaxlib==0.10.2"). So build a Python 3.12 environment with uv
# (it downloads Python 3.12, which needs Internet) and use it for the install and for the runner.
assert sh(f'{sys.executable} -m pip install -q uv') == 0, 'could not install uv'
PYENV = Path('/tmp/py312')
if not (PYENV / 'bin' / 'python').exists():
    assert sh(f'{sys.executable} -m uv venv --python 3.12 --seed {PYENV}') == 0, 'could not create a Python 3.12 environment'
PY12 = f'export PATH={PYENV}/bin:$PATH && '
sh(f'{PY12}python3 --version')
# offline install of the exact JAX/Keras/Orbax versions the model was qualified with (wheels are inside the package)
assert sh(f'{PY12}bash {WORK}/install-runtime.sh {SITE}') == 0, 'runtime install failed; read the output above'

# Check for the TPU now, before the slow part, using the same settings the model's runner uses.
TPU_ENV = ('PJRT_DEVICE=TPU TPU_ACCELERATOR_TYPE=v5litepod-8 TPU_CHIPS_PER_HOST_BOUNDS=2,4,1 TPU_HOST_BOUNDS=1,1,1 '
           'TPU_PROCESS_ADDRESSES=local TPU_SKIP_MDS_QUERY=1 TPU_WORKER_HOSTNAMES=localhost TPU_WORKER_ID=0 KERAS_BACKEND=jax')
PROBE = "import jax; print('BACKEND', jax.default_backend(), len(jax.devices()))"
probe = subprocess.run(f"{PY12}env {TPU_ENV} PYTHONPATH={SITE} python3 -c {shlex.quote(PROBE)}",
                       shell=True, text=True, capture_output=True, executable='/bin/bash')
print((probe.stdout + probe.stderr)[-2500:])
assert 'BACKEND tpu 8' in probe.stdout, ('no TPU with 8 devices is visible to JAX. If the first cell showed no /dev/accel* devices, Kaggle did not attach a TPU '
                                         '(check the notebook Accelerator setting and your TPU quota); otherwise read the JAX error above.')
"""

MAGE_RUN = """
def snap_res(row):
    v = max(int(row.get('width') or 0), int(row.get('height') or 0)) or RESOLUTION
    return min((512, 768, 1024), key=lambda r: abs(r - v))

replicas = int(TOPOLOGY.split('x')[0])
total_saved = 0
for i in range(START, min(END, len(rows)) + 1):
    row = rows[i - 1]
    base = int(row.get('seed') or i)
    seeds = [base + k for k in range(replicas)]
    out_dir = Path(f'/tmp/mage_out_{i}')
    prompt = ' '.join(row['prompt'].split())
    code = sh(f"{PY12}python3 {WORK}/bootstrap/07_generate.py --prompt {shlex.quote(prompt)} --resolution {snap_res(row)} "
              f"--topology {TOPOLOGY} --seeds {','.join(map(str, seeds))} --runtime-site {SITE} --output {out_dir}", cwd=WORK)
    made = 0
    for k, sd in enumerate(seeds):
        png = out_dir / 'vae' / f'seed_{sd}.png'
        if png.exists():
            shutil.copy2(png, OUT / (f'image-{i:04d}.png' if k == 0 else f'image-{i:04d}_alt{k}.png'))
            made += 1
    print(f'row {i}: exit {code}, {made}/{replicas} images saved')
    total_saved += made
assert total_saved > 0, 'no images were produced; read the output above'
"""

FLUX_INTRO = """
# Bible film: FLUX.1-dev (JAX, `diffuse`) on a Kaggle TPU, text to image (EXPERIMENT)

Text to image only. `jcopo/flux_jax` is FLUX.1-dev stored in Orbax format for the `diffuse` library:
https://huggingface.co/jcopo/flux_jax . **Not run by me, and the model card does not say which TPU it was tested on.**

Set **Accelerator = TPU v5e-8** and **Internet = On**, attach the dataset with `all_images.csv`, then Run All.

Cautions:
- About 25 GB are downloaded (the transformer alone is 17 GB). A v5e chip has 16 GB, and the model card's example does not shard the model, so this may run out of memory; the cells print what they find so a failure is informative.
- The licence is FLUX.1-dev's (non-commercial terms): read https://huggingface.co/black-forest-labs/FLUX.1-dev before using results.
- `diffuse` is installed from GitHub (https://github.com/jcopo/diffuse) and may change its API or its JAX version requirements.
"""

FLUX_CONFIG = """
import csv, numpy as np
from pathlib import Path

CSV_NAME = 'all_images.csv'
CSV_PATH = next(Path('/kaggle/input').rglob(CSV_NAME))
START, END = 1, 1          # CSV rows (1-based)
WIDTH, HEIGHT = 512, 512   # multiples of 16
STEPS = 20
GUIDANCE = 4.0
OUT = Path('/kaggle/working/images/tpu_flux_jax')
OUT.mkdir(parents=True, exist_ok=True)
rows = list(csv.DictReader(open(CSV_PATH, newline='')))
print(len(rows), 'rows;', 'using', START, 'to', min(END, len(rows)))
"""

FLUX_INSTALL = """
import subprocess, sys
def sh(cmd):
    print('$', cmd)
    r = subprocess.run(cmd, shell=True, text=True, capture_output=True, executable='/bin/bash')
    print((r.stdout + r.stderr)[-2500:])
    return r.returncode
assert sh(f'{sys.executable} -m pip install -q git+https://github.com/jcopo/diffuse.git') == 0, 'installing diffuse failed (is Internet on?)'
import jax
print('jax', jax.__version__, '| devices:', jax.devices())
"""

FLUX_LOAD = """
from huggingface_hub import snapshot_download
checkpoint_dir = Path(snapshot_download(repo_id='jcopo/flux_jax', repo_type='model', local_dir='/tmp/flux_jax'))
from diffuse import FluxModelLoader, FluxTimer, Flow, Predictor, Denoiser
from diffuse.integrators import EulerIntegrator
from diffuse.utils import _latent_shapes
from PIL import Image
loader = FluxModelLoader(checkpoint_dir=checkpoint_dir, verbose=True)
print('model loaded')
"""

FLUX_RUN = """
def generate(row, seed):
    # follows the model card's example, with the prompt, size, steps and guidance taken from the CSV row
    h = int(row.get('height') or HEIGHT); w = int(row.get('width') or WIDTH)
    steps = int(row.get('steps') or STEPS); guidance = float(row.get('guidance') or GUIDANCE)
    conditioned = loader.prepare_conditioned_network(prompt=row['prompt'], negative_prompt=None, guidance_scale=guidance, height=h, width=w)
    _, thw = _latent_shapes(h, w)
    timer = FluxTimer(num_steps=steps, use_dynamic_shift=True)
    timer.set_image_seq_len(thw[0] * thw[1])
    flow = Flow(tf=1.0)
    predictor = Predictor(model=flow, network=conditioned.network_fn, prediction_type='velocity')
    integrator = EulerIntegrator(model=flow, timer=timer)
    denoiser = Denoiser(integrator=integrator, model=flow, predictor=predictor, x0_shape=(thw[0], thw[1], conditioned.in_channels))
    state, _ = denoiser.generate(rng_key=jax.random.PRNGKey(seed), n_steps=steps, n_particles=1, keep_history=False)
    image = loader.decode_latent(state.integrator_state.position)
    return Image.fromarray((np.asarray(image) * 255).astype('uint8'))

import time
saved = 0
for i in range(START, min(END, len(rows)) + 1):
    t = time.time()
    try:
        generate(rows[i - 1], int(rows[i - 1].get('seed') or i)).save(OUT / f'image-{i:04d}.png')
        print(f'row {i}: ok ({time.time() - t:.0f}s)')
        saved += 1
    except Exception as e:
        print(f'row {i}: FAILED: {e}')
assert saved > 0, 'no images were produced; read the output above'
"""


def image_notebook(intro, cells):
    body = [md(intro), code(DIAG)] + [code(c) for c in cells]
    return {"cells": body, "metadata": {"kernelspec": {"display_name": "Python 3", "name": "python3"}}, "nbformat": 4, "nbformat_minor": 0}


json.dump(image_notebook(MAGE_INTRO, [MAGE_CONFIG, MAGE_DOWNLOAD, MAGE_SETUP, MAGE_RUN]),
          open(root / "Bible_Kaggle_image_tpu_mage_flow.ipynb", "w"), indent=1)
json.dump(image_notebook(FLUX_INTRO, [FLUX_CONFIG, FLUX_INSTALL, FLUX_LOAD, FLUX_RUN]),
          open(root / "Bible_Kaggle_image_tpu_flux_jax.ipynb", "w"), indent=1)
print("wrote Bible_Kaggle_image_tpu_mage_flow.ipynb, Bible_Kaggle_image_tpu_flux_jax.ipynb")
