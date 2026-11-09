# Pistachio's Studio

A local web studio for turning books and ideas into images, video clips and audio. The pictures and clips are made either on **free GPUs at Kaggle**
(your own account, no graphics card needed) or on **your own NVIDIA GPU** with no website at all (see "Running everything on your own computer").
The Studio itself always runs on your computer; nothing is hosted for you.

## What you need

- A Mac (or Linux) with **Python 3.11 or newer** (the Kaggle program needs it). Windows is not supported yet.
- Either a free **Kaggle account** (kaggle.com): verify your phone number in Kaggle's settings, as Kaggle only gives GPUs to verified accounts.
  Free accounts get roughly 30 GPU hours a week and two GPU sessions at a time.
- Or a **GPU in this computer** (Linux, or Windows through WSL 2): NVIDIA, or AMD with ROCm (experimental). Then no Kaggle account is needed.
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

## Making a film from a book: the choices that matter

- **Look**: the bar at the top. Its style words go in each prompt and what the look must avoid goes in each shot's negative prompt, so a claymation film is not pulled towards a photograph.
- **Film shape**: Movies tab, Video and Audio. 16:9, 2.39:1, 4:3, 1:1 or 9:16, at about the same pixel count as the model's own size, so GPU memory use stays about the same. CogVideoX keeps its own shape.
- **Seconds per clip**: Write shots card. Set it to what your video model makes; the AI writes shots and narration to fit.
- **Choosing a face**: Characters tab. The picture marked "This is the face" stands for the character; press "Use this face" under another picture to change it. With "Keep this face" ticked and FLUX.2 klein ticked on the Models tab, Generate Character starts from that picture, and the Movies tab's keyframes use it too. "Character sheet" makes front, side, back, full body and close-up views.
- **Checking faces**: Storyboard, "Check faces". It runs on this computer's CPU with no GPU, compares each keyframe with the character's picture and marks the shots to look at. It is built for realistic films: the recogniser was trained on photographs.
- **Finding the scenes**: Write shots card. One more AI call per chapter, so no shot straddles two scenes and each scene keeps its time of day, weather and costumes.
- **Between clips**: Final film card. Cut, fade through black or dissolve; "Even out colour" nudges clips of a chapter towards each other.
- **Life stages** (realistic films): Characters tab, one per line as `name | chapters | description`, for example `old | 13- | about 70, stooped, long white hair`. Those chapters use that description. For the keyframes, put pictures in a folder named after the stage inside the character's Reference Images Directory. Send the character to the book, then redo those chapters. Stylised looks keep one design throughout. The face still comes from the description and the picture you supply: nothing here guarantees that two ages look like one person.
- **Locations**: each shot names its location and the location's description goes in the prompt. A picture at `projects/books/<book>/location_refs/<location_name>.png` steers those keyframes when the character pictures leave room.
- **Continue unbroken action** (not yet tested on a GPU): a "from keyframes" clip the AI marked as continuing starts from the last frame of the clip before, within one run. A resumed run uses its keyframe.
- **Sound**: music dips under narration, and the film is set to about -16 LUFS. "One continuous music cue per chapter" replaces per-shot music with one cue per chapter, looped softly. "Natural motion" slows a clip at most 1.25x under long narration, then holds the last frame.

## Good to know

- The first run of each model downloads it inside Kaggle (a few minutes); later runs are quicker.
- Kaggle may stop a notebook that uses too much memory; the Models tab notes which models are heavy.
- Notebooks no longer in use are deleted automatically when the Studio starts and after each job: local generated ones, and on Kaggle the finished ones outside your 3 newest whose results are all on this computer, plus failed runs over 7 days old. Turn it off in the Cleanup card.
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

### AMD graphics cards (experimental)

On Linux with AMD's ROCm installed (so that `rocm-smi` lists the card), "This computer" also offers an AMD GPU, marked experimental. Its Python
environment gets PyTorch's ROCm build (`https://download.pytorch.org/whl/rocm6.4`; set `STUDIO_TORCH_INDEX` to the build for your ROCm
version), which the models use through the same calls as on NVIDIA. Two models need NVIDIA-only parts and are greyed out on AMD:
HunyuanVideo 1.5 (4-bit bitsandbytes) and the FlashVSR upscaler (a CUDA kernel). Nothing has been run on an AMD card yet.

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

## For developers
* Layout and rules: [ARCHITECTURE.md](ARCHITECTURE.md); decisions: [adr/](adr/).
* One-time: `uv venv .venv-dev && uv pip install --python .venv-dev/bin/python -e '.[dev]'`
* Checks (the same ones CI runs): `.venv-dev/bin/ruff check . && .venv-dev/bin/mypy && .venv-dev/bin/pytest`
* The page is `web/index.html` plus `web/static/{css,js}`; the server is `scripts/studio_app/`. Edit the model/GPU lists in `scripts/studio_app/catalog.json`.
* Dependencies are locked in `uv.lock`; `constraints.txt` (made with `uv export`) is what `install.sh` pins to.

