"""scripts/studio.py is also imported as a module (`import studio as S`) by regress_kaggle.py: every S.<name> it uses must exist."""
import re
from pathlib import Path

import studio

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def test_names_used_by_regress_kaggle_are_exported():
    used = set(re.findall(r"\bS\.([A-Za-z_][A-Za-z_0-9]*)", (SCRIPTS / "regress_kaggle.py").read_text()))
    assert used, "regress_kaggle.py no longer uses the studio module?"
    assert [n for n in sorted(used) if not hasattr(studio, n)] == []
