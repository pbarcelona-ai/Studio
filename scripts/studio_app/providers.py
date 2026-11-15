"""Where models can run: this computer, free external services and (unproven) paid ones. Data lives in providers.json."""
import json
from pathlib import Path

_NAME = "providers.json"          # looked up beside this file at call time (a module-level Path would be re-rooted by the tests)
_GROUPS = ("computer", "free", "paid")


def providers_data() -> dict:
    """{computer: [...], free: [...], paid: [...]}. Paid providers are always reported as not proven and not selectable."""
    path = Path(__file__).with_name(_NAME)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise RuntimeError(f"{_NAME}: unsupported schema_version {raw.get('schema_version')!r}")
    out: dict = {}
    for g in _GROUPS:
        rows = []
        for p in raw[g]:
            row = dict(p)
            if g == "paid":
                row["proven"] = False
                row["selectable"] = False
            else:
                row["selectable"] = True
            rows.append(row)
        out[g] = rows
    return out
