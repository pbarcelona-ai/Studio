# Pistachio's Studio

A local web studio for turning books and ideas into images, video clips and audio. The pictures and clips are made on **free GPUs at Kaggle**
(your own account), so you need no graphics card of your own. Everything runs from your computer; nothing is hosted for you.

## What you need

- A Mac (or Linux) with **Python 3.11 or newer** (the Kaggle program needs it). Windows is not supported yet.
- A free **Kaggle account** (kaggle.com). Verify your phone number in Kaggle's settings; Kaggle only gives GPUs to verified accounts.
  Free accounts get roughly 30 GPU hours a week and two GPU sessions at a time.
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
- **Book Processing** card (also on the first tab): words per shot, min/max shots, and an optional shot count for each chapter, then the Import button.
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

## Troubleshooting

| Problem | Fix |
|---|---|
| `Python 3.11 or newer was not found` | Install it from python.org or `brew install python@3.12`, then `PYTHON=/path/to/python3 ./install.sh` |
| Setup says "Kaggle login" is missing | Paste a token in Setup, or run `.venv/bin/kaggle auth login` |
| "Test Kaggle login" fails | Create a fresh token on kaggle.com and paste it again |
| Page says forbidden | Open the link the Studio printed (it contains a one-time token), or reopen the app |
| Nothing happens when you press run | Look at the log at the bottom of the page; the first lines say what failed |
| The Mac app does nothing | See `~/Library/Logs/Pistachios Studio.log` |

Licence: see `LICENSE`.
