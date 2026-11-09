#!/usr/bin/env python3
"""Check that what the Studio offers still exists: the Hugging Face models in studio_app/catalog.json and the Spaces in hf_spaces.py.

    python3 scripts/check_catalog.py            # prints one line per id; exit code 1 if any is gone
    python3 scripts/check_catalog.py --offline  # only checks the catalog file itself (no network)

Network access is only to huggingface.co (public metadata, no token needed). Run weekly by .github/workflows/catalog.yml.
"""
import argparse
import sys
import urllib.error
import urllib.request

import hf_spaces
from studio_app.config import CATALOG


def problems_in_catalog(cat: dict) -> list[str]:
    """Structural mistakes in catalog.json (no network)."""
    out = []
    for key in ("kaggle_gpu_gb", "colab_gpu_gb", "claude_models", "hf_models", "hf_vision_models", "gpus", "upscale_models"):
        if not cat.get(key):
            out.append(f"{key} is missing or empty")
    for m in cat.get("hf_vision_models", []):
        if m not in cat.get("hf_models", []):
            out.append(f"vision model {m} is not in hf_models")
    for k, v in cat.get("upscale_models", {}).items():
        if not {"label", "memory", "least_gb", "ampere", "short"} <= set(v):
            out.append(f"upscale model {k} lacks a field")
    for service, gpus in cat.get("gpus", {}).items():
        for g in gpus:
            if len(g) != 2:
                out.append(f"gpu entry {g} of {service} is not [id, label]")
    return out


def exists(url: str) -> bool:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "studio-catalog-check"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status < 400
    except urllib.error.HTTPError as e:
        return e.code not in (404, 410)           # 401/403/429: it exists (or we are rate-limited), do not report it as gone
    except OSError:
        return True                                # offline: not evidence that it is gone


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    bad: list[str] = problems_in_catalog(CATALOG)
    for p in bad:
        print("CATALOG:", p)
    if not a.offline:
        for model in CATALOG["hf_models"]:
            ok = exists(f"https://huggingface.co/api/models/{model}")
            print(("ok   " if ok else "GONE ") + "model " + model)
            bad += [] if ok else [model]
        for key, sp in hf_spaces.SPACES.items():
            space = str(sp["space"])
            ok = exists(f"https://huggingface.co/api/spaces/{space}")
            print(("ok   " if ok else "GONE ") + f"space {space} ({key})")
            bad += [] if ok else [space]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
