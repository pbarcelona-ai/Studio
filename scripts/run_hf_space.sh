#!/usr/bin/env bash
# Usage: PROJECT=<set> [SHOTS_CSV=all_images.csv] [HF_TOKEN=...] scripts/run_hf_space.sh MODEL START END
# Runs rows START..END of the project's prompt CSV on a public Hugging Face Space (see scripts/hf_spaces.py). Needs uv (installs gradio_client by itself).
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null || export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || { echo "uv not found: install it from https://docs.astral.sh/uv/"; exit 1; }
exec env -u PYTHONHOME uv run --quiet --with gradio_client --with pillow scripts/run_hf_space.py "$@"
