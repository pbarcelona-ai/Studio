# Pistachio's Studio

A local web studio for turning books and ideas into images, video clips and audio. The pictures and clips are made either on **free GPUs at Kaggle**
(your own account, no graphics card needed) or on **your own NVIDIA GPU** with no website at all (see "Running everything on your own computer").
The Studio itself always runs on your computer; nothing is hosted for you.

## What you need

- A Mac (or Linux) with **Python 3.11 or newer** (the Kaggle program needs it). Windows is not supported yet.
- Either a free **Kaggle account** (kaggle.com): verify your phone number in Kaggle's settings, as Kaggle only gives GPUs to verified accounts.
  Free accounts get roughly 30 GPU hours a week and two GPU sessions at a time.
- Or an **NVIDIA GPU in this computer** (Linux, or Windows through WSL 2): then no Kaggle account is needed.
- Optional: Claude Code or Codex (for the AI prompt writer), or a Hugging Face token (see below).

## Install (about 2 minutes)

```bash
git clone https://github.com/pbarcelona-ai/Studio.git
cd Studio
./install.sh          # makes a private .venv and installs what the Studio needs; add --3d for the optional 3D depth view
./run_studio.sh       # starts the Studio and opens it in your browser
```

On a Mac you can also run `./create_app_bundle.sh` once to get a double-clickable **Pistachio's Studio** app in Applications.

## First run: the Setup window

The first time the page opens it shows **Setup** (reopen it any time with the ⚙ button in the header). It lists what is ready and what is missing.

1. On kaggle.com open **Settings > API > Create New Token** and paste the token into the Setup window. Press **Save**, then **Test Kaggle login**.
2. Your Kaggle username is filled in for you.
3. Optional: paste a Hugging Face token to use the Hugging Face prompt writer.

Your keys are saved only on your own computer, in files only you can read (`~/.kaggle/` and `~/.pistachios_studio/`). They are never sent anywhere
except to Kaggle or Hugging Face themselves, and the page never shows them again. Nobody else, including the person who shared the Studio with you,
can see them or use your Kaggle hours; your generations run in **your** Kaggle account.

## Using it

- **Import** card (first tab): pick a book (PDF or .txt/.md file) or paste some text, and the AI prompt writer turns it into prompts.
- The **Import** tab follows the steps on the rail above the tabs: **Read book**, **Continuity book**, **Write shots** (words per shot, min/max shots,
  an optional shot count for each chapter) and **Build CSVs**; tick the steps you want and press Import in "Run the ticked book steps".
  Each step card has buttons to the previous and next step, with the same names as the rail.
- **Characters** tab: tick characters and press "Send ticked to the book" to copy your edited visual tokens into the book; "Get characters from the book" copies the other way.
- **Single Prompts** tab: type or paste prompts (one per line), pick models, press run. Results land in `projects/` inside this folder.
- **Models** tab: every image, video and audio model, with notes, plus the Studio's regression test that tries one prompt on all models.
- **Compare** tab: view all models' results for the same prompt side by side and rate them.
- **Library** tab: ready-made prompts and samples.
- The AI prompt writer ("Expand my idea") works with Claude Code, Codex, a Hugging Face token (paid per use) or a model server on your own computer.

## Good to know

- The first run of each model downloads it inside Kaggle (a few minutes); later runs are quicker.
- Kaggle may stop a notebook that uses too much memory; the Models tab notes which models are heavy.
- Generated files, notebooks and your projects stay in this folder and are not part of the code (see `.gitignore`).
- To update: `git pull`, then run `./install.sh` again if the requirements changed.

## Running everything on your own computer

With an NVIDIA GPU you can make every picture, clip, sound and upscale here instead of on Kaggle:

1. Use Linux (or Windows with WSL 2) and install the NVIDIA driver, so that `nvidia-smi` lists your GPU. Install `git` too.
2. In the **Models** tab, under "Where to run", choose **This computer**. It shows your GPU and its memory.
3. Run as usual. The first run of each kind of model makes its own Python environment in `.gpu_envs/` (PyTorch plus that model's packages,
   a few GB, a few minutes) and downloads the model weights into the Hugging Face cache (`~/.cache/huggingface`). Later runs reuse both,
   so they work without internet; set `HF_HUB_OFFLINE=1` before starting the Studio to make sure nothing is fetched.

It runs the very same notebooks Kaggle runs (`scripts/run_local_model.py`), so results match. Each model's note in the Models tab says how much
GPU memory it needs. For the AI prompt writer without any website, choose **local (a language model on this computer)** and run a model server on this computer (for example Ollama).

Settings (environment variables, set before starting the Studio): `STUDIO_TORCH_INDEX` picks the PyTorch build (for example
`https://download.pytorch.org/whl/cu128` for a new GPU), `STUDIO_GPU_PYTHON` uses a Python you already set up instead, and `STUDIO_GPU_ENVS`
moves the environments to another disk. `.gpu_envs/` can be deleted at any time; it is made again when needed.

### Upscalers and the GPU memory they need

| Upscaler | GPU memory | Notes |
|---|---|---|
| Real-ESRGAN x2 | about 2-4 GB | Any NVIDIA GPU. Tested on a Kaggle T4: about 40 s per clip. |
| FlashVSR v1.1 | 8 GB minimum (tiled), 16 GB+ recommended | Ampere or newer only (RTX 30/40/50, A100, L4; not a T4). The first run builds a CUDA kernel: 20-60 min, about 32 GB of system RAM, needs `nvcc`. |
| SeedVR2 3B | 24 GB at full speed; 8-16 GB with block swap (slower) | Wants about 32 GB of system RAM when swapping. |
| SeedVR2 7B | 40 GB+ at full speed, 24 GB with its fp8 model; 12-16 GB with block swap (very slow) | Best detail, slowest. Wants 32-64 GB of system RAM when swapping. |

The diffusion upscalers pick their memory-saving settings from your GPU's memory by themselves. FlashVSR and both SeedVR2 models have not been
tested yet; Real-ESRGAN has.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Python 3.11 or newer was not found` | Install it from python.org or `brew install python@3.12`, then `PYTHON=/path/to/python3 ./install.sh` |
| Setup says "Kaggle login" is missing | Paste a token in Setup, or run `.venv/bin/kaggle auth login` |
| "Test Kaggle login" fails | Create a fresh token on kaggle.com and paste it again |
| Page says forbidden | Open the link the Studio printed (it contains a one-time token), or reopen the app |
| Nothing happens when you press run | Look at the log at the bottom of the page; the first lines say what failed |
| The Mac app does nothing | See `~/Library/Logs/Pistachios Studio.log` |
| "This computer" is greyed out | The Studio found no NVIDIA GPU (`nvidia-smi`), or it is running on macOS. Use Kaggle, or move to a Linux/WSL 2 computer with a GPU |
| A run on this computer fails while installing | Read `projects/<book>/logs/local-*.log`; delete the folder in `.gpu_envs/` it names to start that environment again |

Licence: see `LICENSE`.
