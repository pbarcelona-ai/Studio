"""Loads the real page in jsdom against a live server: every script must load without errors and every tab must open.
Needs node and `npm install` in tests/js (CI does both); skipped otherwise."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import TOKEN

JS = Path(__file__).resolve().parent / "js"


@pytest.mark.skipif(not shutil.which("node") or not (JS / "node_modules" / "jsdom").is_dir(), reason="node or jsdom is not installed (cd tests/js && npm install)")
def test_page_loads_and_every_tab_opens(server):
    r = subprocess.run(["node", "smoke.js", f"http://127.0.0.1:{server.port}/?t={TOKEN}"], cwd=JS, capture_output=True, text=True, timeout=90)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["errors"] == [], out
    assert out["tabs"] >= 8 and r.returncode == 0
