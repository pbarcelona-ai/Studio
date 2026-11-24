"""Pre-render composition validator checking cuts, asset files, and audio/video duration sync."""
from __future__ import annotations

import contextlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any
import wave


def _ffmpeg_bin() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return None


def probe_media_duration(path: Path) -> float | None:
    """Return media duration in seconds using wave (for WAV), ffprobe, or ffmpeg -i."""
    if not path.is_file():
        return None
    if path.suffix.lower() == ".wav":
        with contextlib.suppress(Exception), wave.open(str(path), "rb") as wf:
            rate = wf.getframerate()
            if rate > 0:
                return wf.getnframes() / float(rate)
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        with contextlib.suppress(Exception):
            proc = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return float(proc.stdout.strip().splitlines()[0])
    ffmpeg = _ffmpeg_bin()
    if ffmpeg:
        with contextlib.suppress(Exception):
            proc = subprocess.run([ffmpeg, "-i", str(path)], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
            m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", proc.stderr or "")
            if m:
                return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return None


def _resolve_asset(src: str, assets_root: Path, comp_parent: Path) -> Path:
    p = Path(src)
    if p.is_absolute():
        return p
    cand = assets_root / p
    if cand.exists():
        return cand
    alt = comp_parent / p
    if alt.exists():
        return alt
    return cand


def validate_composition(
    composition_path: str | Path | dict[str, Any],
    *,
    assets_root: str | Path | None = None,
    render_runtime: str | None = None,
) -> dict[str, Any]:
    """Validate a composition JSON file before rendering."""
    start = time.time()
    if isinstance(composition_path, dict):
        inputs = composition_path
        comp_path_raw = inputs.get("composition_path", "")
        assets_root = inputs.get("assets_root", assets_root)
        render_runtime = inputs.get("render_runtime", render_runtime)
    else:
        comp_path_raw = composition_path

    comp_path = Path(str(comp_path_raw))
    if not comp_path.is_file():
        return {
            "success": False,
            "valid": False,
            "passed": False,
            "error": f"Composition not found: {comp_path}",
            "errors": [f"Composition not found: {comp_path}"],
            "warnings": [],
            "info": [],
            "error_count": 1,
            "warning_count": 0,
            "duration_seconds": round(time.time() - start, 2),
        }

    try:
        comp = json.loads(comp_path.read_text(encoding="utf-8"))
        if not isinstance(comp, dict):
            raise ValueError("Composition JSON must be an object")
    except Exception as exc:
        return {
            "success": False,
            "valid": False,
            "passed": False,
            "error": f"Invalid JSON: {exc}",
            "errors": [f"Invalid JSON: {exc}"],
            "warnings": [],
            "info": [],
            "error_count": 1,
            "warning_count": 0,
            "duration_seconds": round(time.time() - start, 2),
        }

    runtime = str(render_runtime or comp.get("render_runtime") or "").strip().lower()
    root_dir = Path(str(assets_root)) if assets_root else None
    if root_dir is None or not root_dir.is_dir():
        if runtime == "hyperframes":
            candidate = comp_path
            resolved = None
            for _ in range(5):
                candidate = candidate.parent
                hf_assets = candidate / "hyperframes" / "assets"
                if hf_assets.is_dir():
                    resolved = hf_assets
                    break
                local_assets = candidate / "assets"
                if local_assets.is_dir() and (candidate / "index.html").is_file():
                    resolved = local_assets
                    break
            root_dir = resolved or comp_path.parent
        elif runtime == "ffmpeg":
            root_dir = comp_path.parent
        else:
            candidate = comp_path
            resolved = None
            for _ in range(5):
                candidate = candidate.parent
                public = candidate / "remotion-composer" / "public"
                if public.is_dir():
                    resolved = public
                    break
            root_dir = resolved or comp_path.parent

    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    cuts = comp.get("cuts")
    if not isinstance(cuts, list) or not cuts:
        errors.append("No cuts defined in composition")
        return _build_result(errors, warnings, info, start)

    video_duration = 0.0
    for cut in cuts:
        if not isinstance(cut, dict):
            errors.append("Invalid cut entry")
            continue
        out_s = float(cut.get("out_seconds", 0) or 0)
        if out_s > video_duration:
            video_duration = out_s

    info.append(f"Video duration: {video_duration}s ({len(cuts)} cuts)")
    info.append(f"Render runtime: {runtime or 'default (remotion)'}; assets root: {root_dir}")

    sorted_cuts = sorted(
        [c for c in cuts if isinstance(c, dict)],
        key=lambda c: float(c.get("in_seconds", 0) or 0),
    )
    prev_out: float | None = None
    for i, cut in enumerate(sorted_cuts):
        in_s = float(cut.get("in_seconds", 0) or 0)
        out_s = float(cut.get("out_seconds", 0) or 0)
        if out_s <= in_s:
            errors.append(f"Cut '{cut.get('id', i)}': out_seconds ({out_s}) <= in_seconds ({in_s})")
        if prev_out is not None and in_s < prev_out - 1e-6:
            errors.append(f"Cut '{cut.get('id', i)}' overlaps previous cut: in_seconds ({in_s}) < previous out_seconds ({prev_out})")
        prev_out = max(prev_out or 0.0, out_s)

    for cut in sorted_cuts:
        source = str(cut.get("source") or "").strip()
        if source:
            asset_path = _resolve_asset(source, root_dir, comp_path.parent)
            if not asset_path.exists():
                errors.append(f"Missing asset: {source} (looked in {root_dir})")
        bg_img = str(cut.get("backgroundImage") or cut.get("background") or "").strip()
        if bg_img:
            bg_path = _resolve_asset(bg_img, root_dir, comp_path.parent)
            if not bg_path.exists():
                errors.append(f"Missing background image: {bg_img}")

    raw_audio = comp.get("audio")
    audio: dict[str, Any] = raw_audio if isinstance(raw_audio, dict) else {}
    raw_narration = audio.get("narration")
    narration: dict[str, Any] = raw_narration if isinstance(raw_narration, dict) else {}
    narration_src = str(narration.get("src") or narration.get("source") or "").strip()
    if narration_src:
        narration_path = _resolve_asset(narration_src, root_dir, comp_path.parent)
        if not narration_path.exists():
            errors.append(f"Missing narration audio: {narration_src}")
        else:
            narration_dur = (
                float(narration["duration_seconds"])
                if isinstance(narration.get("duration_seconds"), (int, float))
                else probe_media_duration(narration_path)
            )
            if narration_dur is not None:
                info.append(f"Narration duration: {narration_dur:.1f}s")
                overshoot = narration_dur - video_duration
                if overshoot > 1.0:
                    errors.append(
                        f"Narration ({narration_dur:.1f}s) exceeds video ({video_duration}s) by {overshoot:.1f}s — audio will be cut off"
                    )
                elif overshoot > 0:
                    warnings.append(
                        f"Narration ({narration_dur:.1f}s) slightly exceeds video ({video_duration}s) by {overshoot:.1f}s"
                    )
            else:
                warnings.append(f"Could not probe narration duration: {narration_src}")

    raw_music = audio.get("music")
    music: dict[str, Any] = raw_music if isinstance(raw_music, dict) else {}
    music_src = str(music.get("src") or music.get("source") or "").strip()
    if music_src:
        music_path = _resolve_asset(music_src, root_dir, comp_path.parent)
        if not music_path.exists():
            errors.append(f"Missing music audio: {music_src}")
        else:
            music_dur = (
                float(music["duration_seconds"])
                if isinstance(music.get("duration_seconds"), (int, float))
                else probe_media_duration(music_path)
            )
            if music_dur is not None:
                info.append(f"Music duration: {music_dur:.1f}s")
                if music_dur < video_duration:
                    warnings.append(f"Music ({music_dur:.1f}s) is shorter than video ({video_duration}s) — will end early")

    if not narration_src and not music_src:
        warnings.append("No audio configured (no narration or music)")

    return _build_result(errors, warnings, info, start)


def _build_result(errors: list[str], warnings: list[str], info: list[str], start: float) -> dict[str, Any]:
    passed = len(errors) == 0
    summary = "; ".join(errors[:3])
    return {
        "success": passed,
        "valid": passed,
        "passed": passed,
        "error": f"Composition has {len(errors)} error(s): {summary}" if not passed else None,
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "duration_seconds": round(time.time() - start, 2),
    }


validate = validate_composition
run_composition_validator = validate_composition


class CompositionValidator:
    """Object wrapper matching OpenMontage BaseTool.execute() contract."""

    name = "composition_validator"
    version = "0.1.0"

    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return validate_composition(
            inputs.get("composition_path", ""),
            assets_root=inputs.get("assets_root"),
            render_runtime=inputs.get("render_runtime"),
        )
