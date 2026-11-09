# ADR 0004 – Notebook templates keep their shell lines
Status: accepted

**Context.** `make_video.py`, `make_audio.py`, `make_tpu.py` and `make_image.py` write notebooks/scripts that run on throw-away Kaggle/Colab machines. Their `sh(...)` helpers use `shell=True` because the recipes use `&&`, pipes, `export PATH=…` and environment prefixes.

**Decision.** On **this computer** nothing uses a shell: `jobs.py` runs argv lists, `run_local_model.py` refuses install lines that need a shell (`pip_argv`) and runs the rest of a notebook's `sh()` through `bash -c` only when a line truly needs it. In the **remote** templates the shell lines are static text written by us; request data never reaches them (models and sizes go in as validated numbers/ids through CSV rows).

**Consequences.** Do not interpolate user text into a template's shell line. Shared notebook helpers live in `scripts/nbkit.py`; `tests`/CI should keep the generated notebooks stable (the refactor was verified byte-identical).
