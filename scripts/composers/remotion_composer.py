"""Remotion multi-family React/TypeScript video composer adapter."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_composer_dir(composer_dir: str | Path | None = None) -> Path:
    if composer_dir:
        return Path(str(composer_dir))
    env_dir = os.environ.get("REMOTION_COMPOSER_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    return _REPO_ROOT / "remotion-composer"


def remotion_status(composer_dir: str | Path | None = None) -> dict[str, Any]:
    cdir = resolve_composer_dir(composer_dir)
    npx_bin = shutil.which("npx")
    pkg_ok = (cdir / "package.json").is_file()
    nm_ok = (cdir / "node_modules").is_dir()
    available = bool(npx_bin and pkg_ok and nm_ok)
    hint = ""
    if not npx_bin:
        hint = "Install Node.js / npx to enable Remotion composer"
    elif not pkg_ok:
        hint = f"Missing remotion-composer package.json at {cdir}"
    elif not nm_ok:
        hint = f"Run 'npm install' inside {cdir} to install Remotion dependencies"
    return {
        "available": available,
        "composer_dir": str(cdir),
        "npx_path": npx_bin,
        "has_package_json": pkg_ok,
        "has_node_modules": nm_ok,
        "hint": hint,
    }


def render_remotion(spec: dict[str, Any]) -> dict[str, Any]:
    cdir = resolve_composer_dir(spec.get("composer_dir"))
    st = remotion_status(cdir)
    if not st["available"]:
        raise RuntimeError(st["hint"] or "Remotion runtime is not available")

    output_str = str(spec.get("output_path") or "").strip()
    if not output_str:
        raise ValueError("output_path is required for Remotion render")
    output_path = Path(output_str)

    cuts = spec.get("cuts")
    if isinstance(cuts, list) and len(cuts) == 0 and not spec.get("props_path") and not spec.get("composition_path"):
        raise ValueError("cuts must be non-empty for Remotion render")

    comp_id = str(spec.get("composition_id") or spec.get("renderer_family") or "Explainer").strip()
    props_path_raw = spec.get("props_path") or spec.get("composition_path")
    if props_path_raw:
        props_file = Path(str(props_path_raw))
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        props_file = output_path.with_suffix(".remotion.props.json")
        props_payload = {
            "renderer_family": spec.get("renderer_family", "explainer"),
            "cuts": cuts or [],
            "scenes": spec.get("scenes") or [],
            "audio": spec.get("audio") or {},
        }
        props_file.write_text(json.dumps(props_payload, indent=2), encoding="utf-8")

    npx_bin = str(st["npx_path"])
    cmd = [
        npx_bin,
        "remotion",
        "render",
        "src/index.ts",
        comp_id,
        f"--props={props_file}",
        str(output_path),
    ]
    proc = subprocess.run(cmd, cwd=str(cdir), capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"Remotion render failed (exit {proc.returncode}): {(proc.stderr or proc.stdout).strip()}")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("Remotion render exited 0 without producing output file")

    return {
        "ok": True,
        "success": True,
        "runtime": "remotion",
        "output_path": str(output_path),
        "composition_id": comp_id,
    }
