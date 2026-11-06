"""Re-create every generated notebook and script: python3 scripts/make_all.py

Runs make_video, make_audio, make_image and make_tpu. The run_*_model.sh scripts call this by themselves when the
notebook or script they need is missing, and the studio page's "Re-create notebooks" button calls it too.
"""
import runpy
from pathlib import Path

here = Path(__file__).resolve().parent
for name in ("make_video", "make_audio", "make_image", "make_tpu"):
    runpy.run_path(str(here / f"{name}.py"), run_name="__main__")
