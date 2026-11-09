"""Every generated notebook is valid nbformat 4 and each code cell is valid Python once notebook-only lines (! and %) are removed."""
import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("gen")
    r = subprocess.run([sys.executable, str(SCRIPTS / "make_all.py")], env={**os.environ, "STUDIO_GEN_DIR": str(out)}, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    return sorted(out.glob("*.ipynb"))


def test_many_notebooks_are_made(generated):
    assert len(generated) >= 20


def test_nothing_is_written_outside_the_chosen_folder(generated):
    repo = SCRIPTS.parent
    assert not any(p.parent == repo for p in generated)


def test_each_notebook_is_well_formed(generated):
    for nb in generated:
        data = json.loads(nb.read_text())
        assert data["nbformat"] == 4 and data["cells"], nb.name
        assert all(c["cell_type"] in ("code", "markdown") for c in data["cells"]), nb.name


def test_every_code_cell_parses(generated):
    bad = []
    for nb in generated:
        for i, cell in enumerate(json.loads(nb.read_text())["cells"]):
            if cell["cell_type"] != "code":
                continue
            lines = ["" if ln.lstrip().startswith(("!", "%")) else ln for ln in "".join(cell["source"]).splitlines()]
            try:
                ast.parse("\n".join(lines))
            except SyntaxError as e:
                bad.append(f"{nb.name} cell {i}: {e}")
    assert not bad, "\n".join(bad[:10])
