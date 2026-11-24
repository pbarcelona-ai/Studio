"""Headless Blender 4.5 Procedural 3D World & EEVVE/Cycles runner."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

_TEMPLATE_SCRIPT = Path(__file__).resolve().parent / "templates" / "blender-world-runtime.py"


def find_blender_binary() -> str | None:
    env_bin = os.environ.get("BLENDER_PATH", "").strip()
    if env_bin:
        p = Path(env_bin)
        if p.is_file():
            return str(p)
        found_env = shutil.which(env_bin)
        if found_env:
            return found_env
        return None
    return shutil.which("blender")


def blender_status() -> dict[str, Any]:
    bpath = find_blender_binary()
    return {
        "available": bpath is not None,
        "blender_path": bpath,
        "template_present": _TEMPLATE_SCRIPT.is_file(),
    }


def run_blender(inputs: dict[str, Any]) -> dict[str, Any]:
    bpath = find_blender_binary()
    if not bpath:
        return {
            "ok": False,
            "success": False,
            "error": "Blender binary not found (set BLENDER_PATH or add blender to PATH)",
        }

    operation = str(inputs.get("operation") or "render_still").strip()
    if operation == "doctor":
        cmd = [
            bpath,
            "--background",
            "--factory-startup",
            "--python",
            str(_TEMPLATE_SCRIPT),
            "--",
            "--operation",
            "doctor",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        m = re.search(r"OPENMONTAGE_BLENDER=([^\s]+)", stdout)
        version = m.group(1) if m else stdout
        if proc.returncode != 0:
            return {
                "ok": False,
                "success": False,
                "blender_path": bpath,
                "error": stderr or stdout or f"Blender doctor exited with {proc.returncode}",
            }
        return {
            "ok": True,
            "success": True,
            "blender_path": bpath,
            "version": version,
            "version_line": stdout,
        }

    output_str = str(inputs.get("output_path") or "").strip()
    blend_str = str(inputs.get("blend_path") or "").strip()
    world_spec = inputs.get("world_spec")

    if operation in ("render_still", "render_animation") and not output_str:
        raise ValueError(f"output_path is required for Blender {operation}")
    if world_spec is None and not inputs.get("spec_path") and not blend_str:
        raise ValueError("world_spec or blend_path is required for Blender render")

    output_path = Path(output_str) if output_str else None
    blend_path = Path(blend_str) if blend_str else (output_path.with_suffix(".blend") if output_path else Path("world.blend"))
    spec_sidecar = blend_path.with_suffix(".world.json")
    spec_sidecar.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(world_spec, dict):
        spec_sidecar.write_text(json.dumps(world_spec, indent=2), encoding="utf-8")
    elif not spec_sidecar.is_file():
        spec_sidecar.write_text(json.dumps({"seed": 1}), encoding="utf-8")

    start_frame = int(inputs.get("start_frame", 1) or 1)
    end_frame = int(inputs.get("end_frame", 120) or 120)

    if operation == "render_animation" and inputs.get("resume") and output_str:
        actual_start = start_frame
        while actual_start <= end_frame:
            cand = Path(f"{output_str}{actual_start:04d}.png")
            if cand.is_file() and cand.stat().st_size > 0:
                actual_start += 1
            else:
                break
        if actual_start > end_frame:
            return {
                "ok": True,
                "success": True,
                "already_complete": True,
                "runtime": "blender",
                "operation": operation,
                "output_path": output_str,
                "blend_path": str(blend_path),
            }
        start_frame = actual_start

    cmd = [
        bpath,
        "--background",
        "--factory-startup",
        "--python",
        str(_TEMPLATE_SCRIPT),
        "--",
        "--operation",
        operation,
        "--spec",
        str(spec_sidecar),
        "--blend",
        str(blend_path),
    ]
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd.extend(["--output", str(output_path)])
    if operation == "render_animation":
        cmd.extend(["--start-frame", str(start_frame), "--end-frame", str(end_frame)])

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        err_msg = (proc.stderr or proc.stdout or f"Blender exited with code {proc.returncode}").strip()
        return {
            "ok": False,
            "success": False,
            "runtime": "blender",
            "operation": operation,
            "error": err_msg,
        }

    return {
        "ok": True,
        "success": True,
        "runtime": "blender",
        "operation": operation,
        "output_path": str(output_path) if output_path else "",
        "blend_path": str(blend_path),
        "spec_path": str(spec_sidecar),
    }


run = run_blender


class BlenderWorldRunner:
    """Object wrapper matching OpenMontage BaseTool.execute() contract."""

    name = "blender_world"
    version = "0.1.0"

    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return run_blender(inputs)


BlenderWorld = BlenderWorldRunner
