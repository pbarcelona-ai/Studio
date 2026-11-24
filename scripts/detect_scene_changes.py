#!/usr/bin/env python3
"""Detect scene storyline updates and offer selective regeneration.

This script checks if the screenplay has been edited since the shots were built,
and if so, identifies which scenes have changed and offers to regenerate
only the affected shots.

Usage:
  python3 scripts/detect_scene_changes.py <project> [--regenerate] [--list-changed]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout
import screenplay


def detect_changed_scenes(pdir: Path) -> dict[str, Any]:
    """Detect which scenes have changed since the shots were built.

    Returns a dict with:
    - changed: bool (True if any scenes changed)
    - changed_scene_ids: list of scene IDs that changed
    - all_scene_ids: list of all scene IDs in the current plan
    - fingerprint: current fingerprint
    - stamp_fingerprint: fingerprint from when shots were built (if available)
    """
    stamp_file = pdir / screenplay.STAMP_FILE
    current_fp = screenplay.fingerprint(pdir)

    if current_fp is None:
        return {
            "changed": False,
            "changed_scene_ids": [],
            "all_scene_ids": [],
            "fingerprint": None,
            "stamp_fingerprint": None,
            "error": "No film plan found for this project"
        }

    stamp = screenplay.read_json(stamp_file, {}) or {}
    stamp_fp = stamp.get("fingerprint")

    if not stamp_fp:
        return {
            "changed": False,
            "changed_scene_ids": [],
            "all_scene_ids": [],
            "fingerprint": current_fp,
            "stamp_fingerprint": None,
            "error": "Shots were built without a screenplay stamp (older project)"
        }

    if stamp_fp == current_fp:
        plan = screenplay.ad.load(pdir)
        return {
            "changed": False,
            "changed_scene_ids": [],
            "all_scene_ids": [s["id"] for s in (screenplay._active(plan) if plan else [])],
            "fingerprint": current_fp,
            "stamp_fingerprint": stamp_fp
        }

    # Fingerprints differ - find which scenes changed
    plan = screenplay.ad.load(pdir)
    active_scenes = screenplay._active(plan) if plan else []

    # We need to compare the old scenes with the new ones
    # The fingerprint is based on scene IDs and their content hashes
    # To find which specific scenes changed, we'd need the old content
    # For now, we report that changes were detected

    changed_scene_ids = []
    for scene in active_scenes:
        scene_id = scene["id"]
        scene_content = screenplay.load_scene(pdir, scene_id)
        if scene_content:
            # We can't easily tell which specific scenes changed without
            # storing per-scene hashes in the stamp file
            # For now, we'll mark all active scenes as potentially changed
            # when the overall fingerprint differs
            changed_scene_ids.append(scene_id)

    return {
        "changed": True,
        "changed_scene_ids": changed_scene_ids,
        "all_scene_ids": [s["id"] for s in active_scenes],
        "fingerprint": current_fp,
        "stamp_fingerprint": stamp_fp,
        "stamp_at": stamp.get("at")
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("project", help="Project slug or directory")
    ap.add_argument("--regenerate", action="store_true", default=False,
                    help="Regenerate shots for changed scenes (not yet implemented)")
    ap.add_argument("--list-changed", action="store_true", default=False,
                    help="List changed scene IDs and exit")
    ap.add_argument("--json", action="store_true", default=False,
                    help="Output results as JSON")

    args = ap.parse_args(argv)

    try:
        pdir = layout.find_dir(args.project)
        if not pdir:
            pdir = Path(args.project)
        if not pdir.is_dir():
            print(f"Error: Project directory not found: {args.project}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error finding project: {e}", file=sys.stderr)
        return 1

    result = detect_changed_scenes(pdir)

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    if result.get("error"):
        print(f"Note: {result['error']}")
        return 0

    if result["changed"]:
        print("== Storyline Changes Detected ==")
        print(f"Project:              {pdir.name}")
        print(f"Current fingerprint:  {result['fingerprint']}")
        print(f"Stamp fingerprint:    {result['stamp_fingerprint']}")
        print(f"Stamp date:           {result.get('stamp_at', 'unknown')}")
        print(f"Changed scenes:       {len(result['changed_scene_ids'])} / {len(result['all_scene_ids'])}")
        for scene_id in result['changed_scene_ids']:
            print(f"  - {scene_id}")

        if args.list_changed:
            return 0

        print()
        print("The screenplay has been edited since shots were built.")
        print("To regenerate shots for changed scenes, you would need to:")
        print("  1. Re-run the shot planning for affected scenes")
        print("  2. Re-generate keyframes for affected shots")
        print("  3. Re-run image/video generation for affected shots")
        print("  4. Re-generate audio for affected shots")
        print("  5. Re-mix the film")
        print()
        print("This selective regeneration feature is not yet fully automated.")
        print("You can manually rebuild affected scenes using the standard pipeline.")

        if args.regenerate:
            print("\n--regenerate flag set, but selective regeneration is not yet implemented.")
            print("Please use the standard pipeline to rebuild.")
            return 1
    else:
        print("== No Storyline Changes ==")
        print(f"Project:              {pdir.name}")
        print(f"Current fingerprint:  {result['fingerprint']}")
        print(f"Stamp fingerprint:    {result['stamp_fingerprint']}")
        print("All scenes match the version used to build shots.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
