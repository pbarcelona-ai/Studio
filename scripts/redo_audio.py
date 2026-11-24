#!/usr/bin/env python3
"""Redo audio for a project: switch voices, dialects, or audio modes (dialogue/dialect-only, narration-only, or both).

Usage:
  python3 scripts/redo_audio.py <project> [--mode both|dialogue|narration|none]
                                          [--voice NARRATOR_VOICE]
                                          [--cast SPEAKER=VOICE ...]
                                          [--dialect american|british|default]
                                          [--force] [--remix] [--model VIDEO_MODEL]

Examples:
  # 1. Switch to dialect only (character dialogue only, omit narration):
  python3 scripts/redo_audio.py pretend_spaceship --mode dialogue

  # 2. Switch narrator voice to female (af_bella) and redo:
  python3 scripts/redo_audio.py pretend_spaceship --voice af_bella

  # 3. Change all voices to British dialect:
  python3 scripts/redo_audio.py pretend_spaceship --dialect british

  # 4. Specific character voice cast + dialect-only mode + remix film:
  python3 scripts/redo_audio.py pretend_spaceship --mode dialogue --cast TOMMY=am_puck --remix
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bookkit
import layout
from local_audio import narration

DIALECT_MAP = {
    "american": {
        "bm_george": "am_michael",
        "bm_lewis": "am_adam",
        "bm_daniel": "am_eric",
        "bm_fable": "am_onyx",
        "bf_emma": "af_bella",
        "bf_isabella": "af_nicole",
        "bf_alice": "af_sarah",
        "bf_lily": "af_heart",
    },
    "british": {
        "am_michael": "bm_george",
        "am_adam": "bm_lewis",
        "am_eric": "bm_daniel",
        "am_liam": "bm_george",
        "am_onyx": "bm_fable",
        "am_echo": "bm_daniel",
        "am_fenrir": "bm_lewis",
        "am_puck": "bm_fable",
        "af_bella": "bf_emma",
        "af_nicole": "bf_isabella",
        "af_sarah": "bf_alice",
        "af_heart": "bf_lily",
        "af_sky": "bf_alice",
        "af_nova": "bf_lily",
        "af_river": "bf_emma",
        "af_jessica": "bf_isabella",
        "af_kore": "bf_alice",
        "af_aoede": "bf_lily",
        "af_alloy": "bf_emma",
    },
}


def canonical_mode(mode: str) -> str:
    """Normalize mode string into 'both', 'dialogue', 'narration', or 'none'."""
    m = (mode or "").strip().lower()
    if m in ("dialogue", "dialect", "dialect_only", "dialogue_only", "quotes"):
        return "dialogue"
    if m in ("narration", "narration_only", "narrator", "narrator_only"):
        return "narration"
    if m in ("none", "mute", "silent", "off"):
        return "none"
    return "both"


def ensure_master_csv(csv_path: Path, master_path: Path) -> None:
    """Archive original audio CSV to master so that mode changes are lossless and reversible."""
    if csv_path.is_file() and not master_path.is_file():
        shutil.copy2(csv_path, master_path)


def map_voice_dialect(voice: str, dialect: str | None) -> str:
    """Map a voice to its counterpart in the target dialect ('american' or 'british')."""
    if not dialect or dialect not in DIALECT_MAP:
        return voice
    return DIALECT_MAP[dialect].get(voice, voice)


def apply_audio_reconfiguration(
    pdir: Path,
    mode: str = "both",
    narrator_voice: str | None = None,
    cast: dict[str, str] | None = None,
    dialect: str | None = None,
    rows: list[int] | None = None,
) -> dict[str, Any]:
    """Reconfigure audio_shots.csv and audio_chapters.csv with voice/dialect/mode settings.

    Non-destructive: Uses audio_shots.master.csv as source of truth.
    """
    pdir = Path(pdir)
    shots_csv = pdir / "audio_shots.csv"
    shots_master = pdir / "audio_shots.master.csv"
    chapters_csv = pdir / "audio_chapters.csv"
    chapters_master = pdir / "audio_chapters.master.csv"

    if not shots_csv.is_file() and not shots_master.is_file():
        raise FileNotFoundError(f"No audio_shots.csv found in {pdir}")

    ensure_master_csv(shots_csv, shots_master)
    ensure_master_csv(chapters_csv, chapters_master)

    norm_mode = canonical_mode(mode)
    clean_cast = {k.strip().lower(): v.strip() for k, v in (cast or {}).items() if k.strip() and v.strip()}
    norm_dialect = (dialect or "").strip().lower() if dialect else None

    # Load master rows
    with open(shots_master, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or ["chapter", "shot", "lines_json", "narration", "sfx", "music"]
        master_rows = list(reader)

    active_rows: list[int] = []
    dialogue_count = 0
    narration_count = 0
    updated_rows: list[dict[str, str]] = []

    target_rows = set(rows) if rows else None

    for i, r in enumerate(master_rows, 1):
        if target_rows and i not in target_rows:
            updated_rows.append(dict(r))
            continue

        raw_lines = r.get("lines_json") or "[]"
        try:
            parsed_lines = json.loads(raw_lines)
            if not isinstance(parsed_lines, list):
                parsed_lines = []
        except Exception:
            parsed_lines = []

        filtered_lines: list[Any] = []
        for line in parsed_lines:
            if not isinstance(line, list) or len(line) < 2:
                continue
            speaker = str(line[0]).strip()
            text = str(line[1])
            is_narrator = speaker.upper() == "NARRATOR"

            # Mode filtering
            if norm_mode == "none":
                continue
            if norm_mode == "dialogue" and is_narrator:
                continue
            if norm_mode == "narration" and not is_narrator:
                continue

            if is_narrator:
                narration_count += 1
            else:
                dialogue_count += 1

            # Voice & dialect selection
            v = line[2] if len(line) >= 3 and line[2] else ""
            if is_narrator and narrator_voice:
                v = narrator_voice
            elif not is_narrator and speaker.lower() in clean_cast:
                v = clean_cast[speaker.lower()]

            if norm_dialect:
                v = map_voice_dialect(v, norm_dialect)

            # Preserve line direction dictionary if present
            if len(line) >= 4 and isinstance(line[3], dict):
                filtered_lines.append([speaker, text, v, line[3]])
            elif v:
                filtered_lines.append([speaker, text, v])
            else:
                filtered_lines.append([speaker, text])

        row_copy = dict(r)
        row_copy["lines_json"] = json.dumps(filtered_lines, ensure_ascii=False)
        row_copy["narration"] = " ".join(str(ln[1]) for ln in filtered_lines)
        if filtered_lines:
            active_rows.append(i)
        updated_rows.append(row_copy)

    # Write updated audio_shots.csv
    with open(shots_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(updated_rows)

    # Update audio_chapters.csv if present
    if chapters_master.is_file():
        with open(chapters_master, newline="", encoding="utf-8") as fh:
            creader = csv.DictReader(fh)
            cfields = creader.fieldnames or fields
            chap_rows = list(creader)

        updated_chaps = []
        for cr in chap_rows:
            try:
                clines = json.loads(cr.get("lines_json") or "[]")
                if not isinstance(clines, list):
                    clines = []
            except Exception:
                clines = []

            filt_clines = []
            for line in clines:
                if not isinstance(line, list) or len(line) < 2:
                    continue
                speaker = str(line[0]).strip()
                is_narrator = speaker.upper() == "NARRATOR"
                if norm_mode == "none":
                    continue
                if norm_mode == "dialogue" and is_narrator:
                    continue
                if norm_mode == "narration" and not is_narrator:
                    continue

                v = line[2] if len(line) >= 3 and line[2] else ""
                if is_narrator and narrator_voice:
                    v = narrator_voice
                elif not is_narrator and speaker.lower() in clean_cast:
                    v = clean_cast[speaker.lower()]
                if norm_dialect:
                    v = map_voice_dialect(v, norm_dialect)

                if len(line) >= 4 and isinstance(line[3], dict):
                    filt_clines.append([speaker, line[1], v, line[3]])
                elif v:
                    filt_clines.append([speaker, line[1], v])
                else:
                    filt_clines.append([speaker, line[1]])

            cr_copy = dict(cr)
            cr_copy["lines_json"] = json.dumps(filt_clines, ensure_ascii=False)
            cr_copy["narration"] = " ".join(str(ln[1]) for ln in filt_clines)
            updated_chaps.append(cr_copy)

        with open(chapters_csv, "w", newline="", encoding="utf-8") as fh:
            cwriter = csv.DictWriter(fh, fieldnames=cfields, extrasaction="ignore")
            cwriter.writeheader()
            cwriter.writerows(updated_chaps)

    # Update voice_cast.json if cast or narrator changed
    if clean_cast or narrator_voice:
        cast_file = pdir / bookkit.VOICE_CAST_FILE
        current_cast = {}
        if cast_file.is_file():
            try:
                current_cast = json.loads(cast_file.read_text(encoding="utf-8")).get("cast", {})
            except Exception:
                current_cast = {}
        if narrator_voice:
            current_cast["NARRATOR"] = narrator_voice
        for spk, vc in clean_cast.items():
            current_cast[spk] = vc
        cast_file.write_text(json.dumps({"cast": current_cast}, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "mode": norm_mode,
        "dialect": norm_dialect,
        "narrator_voice": narrator_voice,
        "cast": clean_cast,
        "total_shots": len(master_rows),
        "active_shots": len(active_rows),
        "dialogue_lines": dialogue_count,
        "narration_lines": narration_count,
    }


def redo_audio(
    project: str,
    mode: str = "both",
    narrator_voice: str | None = None,
    cast: dict[str, str] | None = None,
    dialect: str | None = None,
    rows: list[int] | None = None,
    force: bool = True,
    remix: bool = False,
    video_model: str | None = None,
) -> dict[str, Any]:
    """Apply audio reconfiguration, regenerate Kokoro audio clips, and optionally remix film."""
    pdir = layout.find_dir(project)
    if not pdir:
        pdir = Path(project)
    if not pdir.is_dir():
        raise FileNotFoundError(f"Project directory not found: {project}")

    config_res = apply_audio_reconfiguration(
        pdir=pdir,
        mode=mode,
        narrator_voice=narrator_voice,
        cast=cast,
        dialect=dialect,
        rows=rows,
    )

    out_audio_dir = pdir / "audio" / "kokoro"
    out_audio_dir.mkdir(parents=True, exist_ok=True)

    # Regenerate audio wav files
    narration(pdir, csv_name="audio_shots.csv", folder="kokoro", force=force)

    # Count generated files
    rendered_wavs = sorted(out_audio_dir.glob("narration-*.wav"))
    config_res["rendered_audio_files"] = len(rendered_wavs)

    # Optionally re-mix the film with the newly generated audio
    if remix:
        vmodel = video_model
        if not vmodel:
            # Detect existing video model folders
            videos_dir = pdir / "videos"
            candidates = sorted(p for p in videos_dir.iterdir() if p.is_dir() and not p.name.endswith("_chapters")) if videos_dir.is_dir() else []
            vmodel = candidates[0].name if candidates else "ltx_video"

        mix_script = Path(__file__).resolve().parent / "mix_film.py"
        cmd = [sys.executable, str(mix_script), "--project", pdir.name, "--model", vmodel]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            config_res["remix"] = {"ok": True, "model": vmodel, "output": res.stdout[-400:] if res.stdout else ""}
        except subprocess.CalledProcessError as e:
            config_res["remix"] = {"ok": False, "model": vmodel, "error": e.stderr[-400:] if e.stderr else str(e)}

    return config_res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", help="Project slug or directory")
    ap.add_argument("--mode", choices=["both", "dialogue", "dialect", "narration", "none", "all"], default="dialogue",
                    help="Audio mode: 'dialogue' for character dialogue only (default), 'narration' for narrator only, 'both' for both")
    ap.add_argument("--voice", "--narrator-voice", dest="voice", default=None,
                    help="Voice ID for narrator (e.g. bm_george, af_bella)")
    ap.add_argument("--cast", nargs="*", default=[],
                    help="Character voice overrides in NAME=VOICE format (e.g. TOMMY=am_puck)")
    ap.add_argument("--dialect", choices=["american", "british", "default"], default=None,
                    help="Dialect accent conversion ('american' for am/af, 'british' for bm/bf)")
    ap.add_argument("--force", action="store_true", default=True,
                    help="Force re-render of audio files (default True)")
    ap.add_argument("--remix", action="store_true", default=False,
                    help="Re-mix the finished film with the newly rendered audio")
    ap.add_argument("--model", default=None, help="Video model folder to remix with (e.g. ltx_video)")

    args = ap.parse_args(argv)

    cast_dict = {}
    for item in args.cast:
        if "=" in item:
            spk, vc = item.split("=", 1)
            cast_dict[spk.strip()] = vc.strip()

    try:
        res = redo_audio(
            project=args.project,
            mode=args.mode,
            narrator_voice=args.voice,
            cast=cast_dict,
            dialect=args.dialect,
            force=args.force,
            remix=args.remix,
            video_model=args.model,
        )
        print("== Audio Redo Complete ==")
        print(f"Project:         {args.project}")
        print(f"Mode:            {res['mode']}")
        print(f"Active shots:    {res['active_shots']} / {res['total_shots']}")
        print(f"Lines spoken:    {res['dialogue_lines']} dialogue, {res['narration_lines']} narration")
        print(f"Audio files:     {res['rendered_audio_files']} wav file(s) in audio/kokoro/")
        if "remix" in res:
            print(f"Remix:           {'OK' if res['remix'].get('ok') else 'FAILED'} (model: {res['remix'].get('model')})")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
