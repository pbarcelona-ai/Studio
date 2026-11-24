"""Where models can run: this computer, free external services and (unproven) paid ones. Data lives in providers.json."""
import json
from pathlib import Path
from typing import Any

from .gpus import gpu_profile, legacy_cloud_enabled

_NAME = "providers.json"          # looked up beside this file at call time (a module-level Path would be re-rooted by the tests)
_GROUPS = ("computer", "free", "paid")


def providers_data() -> dict[str, Any]:
    """{computer: [...], free: [...], paid: [...], legacy_cloud: bool, gpu_profile: {...}}.
    Legacy cloud groups ('free', 'paid') are hidden unless STUDIO_LEGACY_CLOUD=1.
    Paid providers are always reported as not proven and not selectable."""
    path = Path(__file__).with_name(_NAME)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise RuntimeError(f"{_NAME}: unsupported schema_version {raw.get('schema_version')!r}")
    legacy = legacy_cloud_enabled()
    out: dict[str, Any] = {}
    for g in _GROUPS:
        if g in ("free", "paid") and not legacy:
            out[g] = []
            continue
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
    out["legacy_cloud"] = legacy
    out["gpu_profile"] = gpu_profile()
    return out
