#!/usr/bin/env bash
# The Python version, scripts/run_colab_model.py, does the work on every system (Windows too); this stays so old commands keep working. Usage: see that file.
cd "$(dirname "$0")/.." || exit 1
command -v kaggle >/dev/null || export PATH="$HOME/.local/bin:$PATH"
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" scripts/run_colab_model.py "$@"
