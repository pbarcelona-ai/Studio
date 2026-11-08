#!/usr/bin/env bash
# One-time setup for Pistachio's Studio on macOS or Linux:   ./install.sh        (add --3d for the optional 3D depth view)
# Makes a private Python environment in .venv, installs what the Studio needs into it, and tells you what to do next.
# It changes nothing outside this folder. It never asks for or stores any key; the Studio's Setup window does that.
set -euo pipefail
cd "$(dirname "$0")"

# The Kaggle program needs Python 3.11 or newer (the Python that ships with macOS is older), so look for a suitable one.
ok_py() { command -v "$1" >/dev/null 2>&1 && "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; }
PY=""
for c in ${PYTHON:-} python3.13 python3.12 python3.11 python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  [ -n "$c" ] && ok_py "$c" && { PY=$c; break; }
done
if [ -z "$PY" ]; then
  echo "Python 3.11 or newer was not found (the Kaggle program needs it)."
  echo "Install it from https://www.python.org/downloads/ (or: brew install python@3.12), then run this again."
  echo "If it is installed somewhere unusual:  PYTHON=/path/to/python3 ./install.sh"
  exit 1
fi
echo "Using $($PY --version 2>&1) at $(command -v "$PY")"

echo "== Making the private Python environment (.venv)"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  .venv/bin/python -m ensurepip --upgrade >/dev/null 2>&1 || true
fi
if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  rm -rf .venv
  echo "This Python could not set up pip inside a virtual environment ($($PY --version 2>&1) at $(command -v "$PY"))."
  echo "Install the standard Python from https://www.python.org/downloads/ (or: brew install python) and run again with:  PYTHON=/path/to/python3 ./install.sh"
  exit 1
fi
.venv/bin/python -m pip install --quiet --upgrade pip

echo "== Installing the Studio's requirements"
.venv/bin/python -m pip install --quiet -r requirements.txt

if [ "${1:-}" = "--3d" ]; then
  echo "== Installing the optional 3D depth view (large; this can take several minutes)"
  .venv/bin/python -m pip install --quiet -r requirements-3d.txt
fi

chmod +x run_studio.sh create_app_bundle.sh scripts/*.sh 2>/dev/null || true
echo
echo "Done. Start the Studio with:   ./run_studio.sh"
[ "$(uname)" = "Darwin" ] && echo "On a Mac you can also make a double-clickable app with:   ./create_app_bundle.sh"
echo "The first time it opens, the Setup window asks for your free Kaggle API token (kaggle.com > Settings > API)."
