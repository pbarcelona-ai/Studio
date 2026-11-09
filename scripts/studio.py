#!/usr/bin/env python3
"""Local control page for the Pistachio's Studio pipeline.

    cd <the Studio folder> && python3 scripts/studio.py        (or double-click the app, or run ./run_studio.sh)

Opens http://127.0.0.1:8765/?t=<token>. Pick a book (project), optionally upload a new PDF, tick what to do, and the
server runs the project's own scripts one after another (see ARCHITECTURE.md for the module map).
Safety: listens on 127.0.0.1 only, every API call needs the random token printed at start-up, and only whitelisted
scripts with validated arguments can run (no shell, no free-form commands).

The code lives in the studio_app package. This file stays as the command (run_studio.sh and the app call it) and re-exports
the names other scripts use (regress_kaggle.py imports them as `studio`).
"""
import sys

if sys.version_info < (3, 11):  # noqa: UP036  (a runtime guard for people who start it with an old python3)
    sys.exit("Pistachio's Studio needs Python 3.11 or newer (run ./install.sh, which makes .venv with a suitable Python).")

from studio_app.common import PlanError  # noqa: E402, F401
from studio_app.config import AUDIO_MODELS, IMAGE_MODELS, MODEL_DEFAULTS, VIDEO_MODELS, clean_env  # noqa: F401
from studio_app.server import main
from studio_app.single_prompts import prompt_plan  # noqa: F401

if __name__ == "__main__":
    main()
