"""HyperFrames HTML/CSS/SVG/GSAP & Ink Theater composition adapter."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _probe_node_major(node_bin: str | None) -> tuple[int, str]:
    if not node_bin:
        return 0, ""
    try:
        proc = subprocess.run([node_bin, "--version"], capture_output=True, text=True, timeout=5)
        raw = (proc.stdout or proc.stderr or "").strip()
        m = re.search(r"v?(\d+)\.(\d+)", raw)
        if m:
            return int(m.group(1)), raw
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0, ""
    return 0, ""


def hyperframes_status() -> dict[str, Any]:
    node_bin = shutil.which("node")
    npx_bin = shutil.which("npx")
    major, ver_str = _probe_node_major(node_bin)
    available = bool(node_bin and npx_bin and major >= 22)
    hint = ""
    if not node_bin or not npx_bin:
        hint = "Install Node.js >= 22 and npx to enable HyperFrames"
    elif major < 22:
        hint = f"HyperFrames requires Node.js >= 22 (found {ver_str or 'unknown'})"
    return {
        "available": available,
        "node_path": node_bin,
        "npx_path": npx_bin,
        "node_major": major,
        "node_version": ver_str,
        "ink_theater_bundled": (_REPO_ROOT / "ink-theater" / "ink-theater.js").is_file(),
        "hint": hint,
    }


def _scaffold_hyperframes_html(workspace_path: Path, spec: dict[str, Any]) -> Path:
    workspace_path.mkdir(parents=True, exist_ok=True)
    index_html = workspace_path / "index.html"
    raw_ed = spec.get("edit_decisions")
    edit_decisions: dict[str, Any] = raw_ed if isinstance(raw_ed, dict) else {}
    cuts = edit_decisions.get("cuts") or spec.get("cuts") or []
    duration_s = 5.0
    for c in cuts:
        if isinstance(c, dict):
            duration_s = max(duration_s, float(c.get("out_seconds", 0) or 0))
    fps = int(spec.get("fps", 30) or 30)
    use_ink = bool(spec.get("ink_theater"))

    ink_dir = _REPO_ROOT / "ink-theater"
    if use_ink and ink_dir.is_dir():
        dst_ink = workspace_path / "ink-theater"
        if not dst_ink.exists():
            shutil.copytree(ink_dir, dst_ink)

    ink_scripts = (
        '<script src="./ink-theater/ink-puppet.js"></script>\n'
        '<script src="./ink-theater/ink-theater.js"></script>\n'
        if use_ink
        else ""
    )
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>HyperFrames Composition</title>
  <style>
    html, body {{ margin: 0; padding: 0; width: 1920px; height: 1080px; overflow: hidden; background: #0d1117; color: #f0f6fc; }}
    #stage {{ width: 1920px; height: 1080px; position: relative; }}
  </style>
</head>
<body>
  <div id="stage" data-composition-id="root" data-width="1920" data-height="1080" data-fps="{fps}" data-duration="{duration_s}">
    <svg id="ink-canvas" viewBox="0 0 1920 1080" width="1920" height="1080"></svg>
  </div>
  {ink_scripts}
  <script>
    window.__timelines = window.__timelines || {{}};
    window.__editDecisions = {json.dumps(edit_decisions)};
  </script>
</body>
</html>
"""
    index_html.write_text(html_doc, encoding="utf-8")
    return index_html


def render_hyperframes(spec: dict[str, Any]) -> dict[str, Any]:
    st = hyperframes_status()
    if not st["available"]:
        raise RuntimeError(st["hint"] or "HyperFrames runtime is not available")

    output_str = str(spec.get("output_path") or "").strip()
    if not output_str:
        raise ValueError("output_path is required for HyperFrames render")
    output_path = Path(output_str)

    ws_raw = spec.get("workspace_path")
    workspace_path = Path(str(ws_raw)) if ws_raw else output_path.parent / "hyperframes_ws"
    index_html = workspace_path / "index.html"
    if not index_html.is_file() or spec.get("ink_theater") or spec.get("edit_decisions"):
        _scaffold_hyperframes_html(workspace_path, spec)

    npx_bin = str(st["npx_path"])
    operation = str(spec.get("operation") or "render").strip()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        npx_bin,
        "hyperframes",
        operation,
        str(workspace_path),
        "--output",
        str(output_path),
    ]
    proc = subprocess.run(cmd, cwd=str(workspace_path), capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"HyperFrames {operation} failed (exit {proc.returncode}): {(proc.stderr or proc.stdout).strip()}")
    if operation == "render" and (not output_path.is_file() or output_path.stat().st_size == 0):
        raise RuntimeError("HyperFrames render exited 0 without producing output file")

    return {
        "ok": True,
        "success": True,
        "runtime": "hyperframes",
        "operation": operation,
        "workspace_path": str(workspace_path),
        "output_path": str(output_path),
    }
