"""scripts/fetch_kaggle_run.py with a stand-in `kaggle` command: results land in the folder the Studio reads (keyframes in <model>_keyframes)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the stand-in kaggle command is a shell script")

ROOT = Path(__file__).resolve().parent.parent
FAKE = """#!/bin/sh
case "$1 $2" in
  "kernels status") echo 'status "KernelWorkerStatus.COMPLETE"' ;;
  "kernels output") d="$5"; mkdir -p "$d/images/flux2_klein_4b" "$d/videos/ltx_video"
                    echo pic > "$d/images/flux2_klein_4b/image-0081.png"; echo clip > "$d/videos/ltx_video/shot-0001.mp4"; echo '[]' > "$d/run.log" ;;
esac
"""


@pytest.mark.parametrize("slug,where", [
    ("demo-image-flux2-klein-4b-keyframes-81-120", "images/flux2_klein_4b_keyframes/image-0081.png"),
    ("demo-image-flux2-klein-4b-81-120", "images/flux2_klein_4b/image-0081.png"),
    ("demo-ltx-video-chapters-1-4", "videos/ltx_video_chapters/shot-0001.mp4"),
    ("demo-ltx-video-1-4", "videos/ltx_video/shot-0001.mp4"),
])
def test_results_land_where_the_studio_looks(tmp_path, slug, where):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "kaggle").write_text(FAKE)
    (bin_ / "kaggle").chmod(0o755)
    dest = tmp_path / "out"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "fetch_kaggle_run.py"), f"pat/{slug}", "--dest", str(dest)], capture_output=True, text=True,
                       env={**os.environ, "PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}"}, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (dest / where).is_file(), sorted(str(p.relative_to(dest)) for p in dest.rglob("*"))
