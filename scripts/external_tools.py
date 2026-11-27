"""Open-source external application discovery, safe launch handoffs, and NLE timeline export (OpenTimelineIO / Kdenlive MLT XML).

Supports Windows, macOS, and Linux without shell invocation (argv-only subprocess calls).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_AI_DIR = REPO_ROOT / ".local_ai"


def _win_program_roots() -> list[Path]:
    if sys.platform != "win32":
        return []
    roots: list[Path] = []
    for env_key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        val = os.environ.get(env_key, "").strip()
        if val:
            roots.append(Path(val))
            if env_key == "LOCALAPPDATA":
                roots.append(Path(val) / "Programs")
    return roots


def _find_first_file(candidates: list[Path]) -> Path | None:
    for cand in candidates:
        try:
            if cand.is_file():
                return cand
        except OSError:
            continue
    return None


def _which_any(names: tuple[str, ...]) -> Path | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _find_desktop_binary(
    which_names: tuple[str, ...],
    win_rel_paths: tuple[str, ...] = (),
    extra_paths: tuple[Path, ...] = (),
) -> Path | None:
    found = _which_any(which_names)
    if found is not None:
        return found
    cands: list[Path] = list(extra_paths)
    for root in _win_program_roots():
        for rel in win_rel_paths:
            cands.append(root / rel)
    return _find_first_file(cands)


def _find_venv_entry(base_dir: Path, exe_names: tuple[str, ...]) -> Path | None:
    if not base_dir.is_dir():
        return None
    sub = "Scripts" if sys.platform == "win32" else "bin"
    cands: list[Path] = []
    for venv_dir in (base_dir / ".venv", base_dir / "venv", base_dir):
        for name in exe_names:
            cands.append(venv_dir / sub / name)
    return _find_first_file(cands)


def _has_python_module(mod_name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(mod_name) is not None
    except (ImportError, ValueError):
        return False


def _tool_entry(
    tool_id: str,
    name: str,
    category: str,
    installed: bool,
    path: Path | str | None,
    integration: str,
    *,
    launchable: bool = False,
    detail: str = "",
) -> dict[str, Any]:
    return {
        "id": tool_id,
        "name": name,
        "category": category,
        "installed": bool(installed),
        "path": str(path) if path else "",
        "integration": integration,
        "launchable": bool(launchable and installed),
        "detail": detail,
    }


def find_trelby_executable() -> Path | None:
    """Locate Trelby screenplay editor executable (substituting for Final Draft)."""
    env_bin = os.environ.get("TRELBY_BIN", "").strip()
    extra = (Path(env_bin),) if env_bin else ()
    return _find_desktop_binary(
        ("trelby", "trelby.exe"),
        win_rel_paths=(
            "Trelby/trelby.exe",
            "Trelby/Trelby.exe",
        ),
        extra_paths=extra,
    )


def _find_in_local_apps(local_ai: Path, patterns: tuple[str, ...]) -> list[Path]:
    apps_dir = local_ai / "apps"
    if not apps_dir.is_dir():
        return []
    out: list[Path] = []
    for pat in patterns:
        out.extend(sorted(apps_dir.glob(pat)))
    return out


def _find_in_winget_packages(patterns: tuple[str, ...]) -> list[Path]:
    if sys.platform != "win32":
        return []
    lad = os.environ.get("LOCALAPPDATA", "").strip()
    if not lad:
        return []
    pkg_dir = Path(lad) / "Microsoft" / "WinGet" / "Packages"
    if not pkg_dir.is_dir():
        return []
    out: list[Path] = []
    for pat in patterns:
        out.extend(sorted(pkg_dir.glob(pat)))
    return out


def detect_all_tools(repo_root: Path | None = None) -> dict[str, Any]:
    """Detect all supported open-source creative, NLE, document, and local AI tools."""
    root = repo_root or REPO_ROOT
    local_ai = root / ".local_ai"
    tools_dir = local_ai / "tools"

    trelby = find_trelby_executable()
    kdenlive = _find_desktop_binary(
        ("kdenlive", "kdenlive.exe"),
        win_rel_paths=("kdenlive/bin/kdenlive.exe", "Kdenlive/bin/kdenlive.exe"),
        extra_paths=tuple(_find_in_local_apps(local_ai, ("Kdenlive/**/kdenlive.exe", "Kdenlive/bin/kdenlive.exe"))),
    )
    krita = _find_desktop_binary(
        ("krita", "krita.exe"),
        win_rel_paths=("Krita (x64)/bin/krita.exe", "Krita/bin/krita.exe"),
        extra_paths=tuple(_find_in_local_apps(local_ai, ("Krita/**/bin/krita.exe", "Krita/bin/krita.exe"))),
    )
    audacity = _find_desktop_binary(
        ("audacity", "audacity.exe", "Audacity", "Audacity.exe"),
        win_rel_paths=(
            "Audacity/Audacity.exe",
            "Audacity/audacity.exe",
            "Microsoft/WinGet/Links/Audacity.exe",
            "Microsoft/WinGet/Links/audacity.exe",
        ),
        extra_paths=tuple(
            _find_in_local_apps(local_ai, ("Audacity/**/Audacity.exe",))
            + _find_in_winget_packages(("Audacity.Audacity*/**/Audacity.exe",))
        ),
    )
    darktable = _find_desktop_binary(
        ("darktable-cli", "darktable", "darktable-cli.exe", "darktable.exe"),
        win_rel_paths=("darktable/bin/darktable-cli.exe", "darktable/bin/darktable.exe"),
        extra_paths=tuple(_find_in_local_apps(local_ai, ("darktable/**/darktable-cli.exe", "darktable/**/darktable.exe"))),
    )
    handbrake = _find_desktop_binary(
        ("HandBrakeCLI", "HandBrakeCLI.exe", "HandBrake", "HandBrake.exe"),
        win_rel_paths=("HandBrake/HandBrakeCLI.exe", "HandBrake/HandBrake.exe"),
        extra_paths=tuple(_find_in_local_apps(local_ai, ("HandBrake/**/HandBrakeCLI.exe", "HandBrake/**/HandBrake.exe"))),
    )
    subtitle_edit = _find_desktop_binary(
        ("SubtitleEdit", "SubtitleEdit.exe"),
        win_rel_paths=("Subtitle Edit/SubtitleEdit.exe", "SubtitleEdit/SubtitleEdit.exe"),
        extra_paths=tuple(_find_in_local_apps(local_ai, ("SubtitleEdit/SubtitleEdit.exe", "SubtitleEdit/**/SubtitleEdit.exe"))),
    )
    pandoc = _find_desktop_binary(
        ("pandoc", "pandoc.exe"),
        win_rel_paths=("Pandoc/pandoc.exe",),
        extra_paths=tuple(_find_in_local_apps(local_ai, ("Pandoc/**/pandoc.exe",))),
    )
    calibre = _find_desktop_binary(
        ("ebook-convert", "ebook-convert.exe", "calibre", "calibre.exe"),
        win_rel_paths=("Calibre2/ebook-convert.exe", "Calibre/ebook-convert.exe"),
        extra_paths=tuple(
            _find_in_local_apps(
                local_ai,
                ("CalibrePortable/**/ebook-convert.exe", "CalibrePortable/Calibre/ebook-convert.exe", "CalibrePortable/calibre-portable.exe"),
            )
        ),
    )
    blender = _find_desktop_binary(
        ("blender", "blender.exe"),
        win_rel_paths=(
            "Blender Foundation/Blender 5.4/blender.exe",
            "Blender Foundation/Blender 5.3/blender.exe",
            "Blender Foundation/Blender 5.0/blender.exe",
            "Blender Foundation/Blender 4.5/blender.exe",
        ),
        extra_paths=(
            local_ai / "blender" / ("blender.exe" if sys.platform == "win32" else "blender"),
        ),
    )
    ffmpeg = _which_any(("ffmpeg", "ffmpeg.exe"))
    ollama = _find_desktop_binary(
        ("ollama", "ollama.exe"),
        win_rel_paths=("Ollama/ollama.exe",),
    )
    comfy_main = local_ai / "ComfyUI" / "main.py"
    sd_cli = _find_first_file([
        local_ai / "bin" / ("sd-cli.exe" if sys.platform == "win32" else "sd-cli"),
    ])

    otio_ok = _has_python_module("opentimelineio")

    wgp_dir = Path(os.environ["WAN2GP_DIR"]) if os.environ.get("WAN2GP_DIR") else (local_ai / "Wan2GP")
    wgp_py = _find_venv_entry(wgp_dir, ("python.exe", "python"))
    wgp_ok = (wgp_dir / "wgp.py").is_file() and wgp_py is not None

    demucs_exe = _find_venv_entry(tools_dir / "demucs", ("demucs.exe", "demucs")) or _which_any(("demucs", "demucs.exe"))
    whisperx_exe = _find_venv_entry(tools_dir / "whisperx", ("whisperx.exe", "whisperx")) or _which_any(("whisperx", "whisperx.exe"))
    f5_tts_exe = _find_venv_entry(
        tools_dir / "f5-tts",
        ("f5-tts_infer-cli.exe", "f5-tts_infer-cli", "f5-tts_infer-gradio.exe"),
    ) or _which_any(("f5-tts_infer-cli", "f5-tts_infer-cli.exe"))

    acestep_dir = local_ai / "ACE-Step-1.5"
    acestep_exe = _find_venv_entry(acestep_dir, ("acestep.exe", "acestep", "python.exe", "python"))
    acestep_ok = acestep_dir.is_dir() and acestep_exe is not None

    latentsync_dir = local_ai / "LatentSync"
    latentsync_py = _find_venv_entry(latentsync_dir, ("python.exe", "python"))
    latentsync_ok = latentsync_dir.is_dir() and latentsync_py is not None

    items = [
        _tool_entry("trelby", "Trelby", "screenplay", trelby is not None, trelby, "Step 06 .fdx/.fountain round-trip", launchable=True),
        _tool_entry("blender", "Blender", "3d", blender is not None, blender, "Headless 3D previs, depth guides & Live MCP", launchable=True),
        _tool_entry("kdenlive", "Kdenlive", "nle", kdenlive is not None, kdenlive, "Step 22 .kdenlive MLT XML & EDL timeline", launchable=True),
        _tool_entry("opentimelineio", "OpenTimelineIO", "nle", otio_ok, "python:opentimelineio" if otio_ok else "", "Universal .otio & NLE timeline interchange"),
        _tool_entry("krita", "Krita", "art", krita is not None, krita, "Painting, storyboards & ComfyUI AI Diffusion", launchable=True),
        _tool_entry("darktable", "Darktable", "color", darktable is not None, darktable, "Batch look/color grading CLI & XMP", launchable=True),
        _tool_entry("audacity", "Audacity", "audio", audacity is not None, audacity, "Dialogue cleanup & WAV stem editing", launchable=True),
        _tool_entry("handbrake", "HandBrake", "video", handbrake is not None, handbrake, "Hardware-accelerated delivery transcoding", launchable=True),
        _tool_entry("subtitle_edit", "Subtitle Edit", "captions", subtitle_edit is not None, subtitle_edit, "Visual .srt QA & timing polish", launchable=True),
        _tool_entry("pandoc", "Pandoc", "docs", pandoc is not None, pandoc, "Universal book & script document conversion"),
        _tool_entry("calibre", "Calibre", "docs", calibre is not None, calibre, "E-book ingest & Illustrated Book EPUB export"),
        _tool_entry("ffmpeg", "FFmpeg", "video", ffmpeg is not None, ffmpeg, "Core timeline mix, LUFS, silence cut & reframe"),
        _tool_entry("ollama", "Ollama", "ai_llm", ollama is not None, ollama, "Local LLM writing & free Vision QA"),
        _tool_entry("comfyui", "ComfyUI", "ai_media", comfy_main.is_file(), comfy_main if comfy_main.is_file() else None, "120 local workflows & Qwen-Image-Edit angles"),
        _tool_entry("sd_cli", "stable-diffusion.cpp", "ai_media", sd_cli is not None, sd_cli, "Local CUDA GGUF FLUX image generation"),
        _tool_entry("wan2gp", "Wan2GP", "ai_video", wgp_ok, wgp_dir if wgp_ok else None, "Local GPU T2V/I2V (Wan 2.1/2.2, Hunyuan, LTX)"),
        _tool_entry("demucs", "Demucs", "ai_audio", demucs_exe is not None, demucs_exe, "Stem separation for imported media"),
        _tool_entry("whisperx", "WhisperX", "ai_audio", whisperx_exe is not None, whisperx_exe, "Word-level forced alignment & diarization"),
        _tool_entry("f5_tts", "F5-TTS", "ai_audio", f5_tts_exe is not None, f5_tts_exe, "Zero-shot local character voice cloning"),
        _tool_entry("ace_step", "ACE-Step 1.5", "ai_audio", acestep_ok, acestep_dir if acestep_ok else None, "Local 48 kHz stereo music generation"),
        _tool_entry("latentsync", "LatentSync", "ai_video", latentsync_ok, latentsync_dir if latentsync_ok else None, "Step 19 local diffusion lip-sync"),
    ]
    by_id = {it["id"]: it for it in items}
    installed_count = sum(1 for it in items if it["installed"])
    return {
        "tools": items,
        "by_id": by_id,
        "installed_count": installed_count,
        "total_count": len(items),
    }


def _detached_popen_kwargs() -> dict[str, Any]:
    if sys.platform == "win32":
        return {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def launch_trelby(screenplay_path: Path | None = None) -> dict[str, Any]:
    """Launch locally installed Trelby GUI (optionally passing an exported screenplay file)."""
    exe = find_trelby_executable()
    if exe is None:
        return {
            "launched": False,
            "installed": False,
            "executable": "",
            "error": "Trelby is not installed or not found on PATH / Program Files.",
        }
    argv = [str(exe)]
    # Trelby CLI opens .trelby files directly; for .fdx/.fountain pass the file or open Trelby GUI cleanly
    if screenplay_path is not None and screenplay_path.is_file() and screenplay_path.suffix.lower() == ".trelby":
        argv.append(str(screenplay_path))
    cwd = str(screenplay_path.parent) if screenplay_path is not None and screenplay_path.parent.is_dir() else str(exe.parent)
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **_detached_popen_kwargs(),
    )
    return {
        "launched": True,
        "installed": True,
        "executable": str(exe),
        "pid": proc.pid,
        "file": str(screenplay_path) if screenplay_path else "",
    }


_LAUNCHABLE_GUI_IDS = frozenset({"trelby", "kdenlive", "krita", "audacity", "darktable", "handbrake", "subtitle_edit", "blender"})


def launch_external_tool(tool_id: str, target_path: Path | None = None) -> dict[str, Any]:
    """Launch an allow-listed local GUI application with an optional file path (no shell)."""
    tid = str(tool_id or "").strip().lower()
    if tid not in _LAUNCHABLE_GUI_IDS:
        raise ValueError(f"Unsupported or non-launchable tool id: {tid!r}")
    if tid == "trelby":
        return launch_trelby(target_path)

    info = detect_all_tools()["by_id"].get(tid)
    if not info or not info.get("installed") or not info.get("path"):
        return {"launched": False, "installed": False, "tool": tid, "error": f"{tid} is not installed."}

    exe = Path(str(info["path"]))
    # Prefer GUI binary for tools that also have CLI binaries
    if tid == "darktable" and exe.name.lower().startswith("darktable-cli"):
        gui_cand = exe.with_name("darktable.exe" if sys.platform == "win32" else "darktable")
        if gui_cand.is_file():
            exe = gui_cand
    elif tid == "handbrake" and exe.name.lower().startswith("handbrakecli"):
        gui_cand = exe.with_name("HandBrake.exe" if sys.platform == "win32" else "ghb")
        if gui_cand.is_file():
            exe = gui_cand

    argv = [str(exe)]
    if target_path is not None and target_path.exists():
        argv.append(str(target_path))
    cwd = str(target_path.parent) if target_path is not None and target_path.parent.is_dir() else str(exe.parent)
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **_detached_popen_kwargs(),
    )
    return {"launched": True, "installed": True, "tool": tid, "executable": str(exe), "pid": proc.pid}


def _collect_timeline_clips(book_dir: Path, slug: str) -> list[dict[str, Any]]:
    """Collect ordered shot entries from shots/shotlist.json or edit/edl.json for NLE export."""
    clips: list[dict[str, Any]] = []
    sl_path = book_dir / "shots" / "shotlist.json"
    if sl_path.is_file():
        try:
            sl = json.loads(sl_path.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError):
            sl = {}
        idx = 1
        for sc in sl.get("scenes") or []:
            sid = str(sc.get("id") or f"S{idx:03d}")
            for sh in sc.get("shots") or []:
                n = int(sh.get("n") or idx)
                dur = max(0.5, float(sh.get("seconds") or 4.0))
                name = f"{sid}-{n:02d}"
                # Attach rendered video or keyframe if present
                media_path = ""
                for cand in (
                    book_dir / "videos" / "gemini_omni_12_flash" / f"{name}.mp4",
                    book_dir / "videos" / f"{name}.mp4",
                    book_dir / "keyframes" / f"{name}.png",
                ):
                    if cand.is_file():
                        media_path = str(cand.resolve())
                        break
                clips.append({"name": name, "scene": sid, "shot": n, "seconds": dur, "media_path": media_path})
                idx += 1
    if not clips:
        edl_path = book_dir / "edit" / "edl.json"
        if edl_path.is_file():
            try:
                ed = json.loads(edl_path.read_text(encoding="utf-8")) or {}
                cur = str(ed.get("current") or "main")
                vids = ((ed.get("cuts") or {}).get(cur) or {}).get("tracks", {}).get("video") or []
                for idx, v in enumerate(vids, start=1):
                    sid = str(v.get("scene") or "S001")
                    sh_n = int(v.get("shot") or idx)
                    clips.append({
                        "name": f"{sid}-{sh_n:02d}",
                        "scene": sid,
                        "shot": sh_n,
                        "seconds": max(0.5, float(v.get("seconds") or 4.0)),
                        "media_path": "",
                    })
            except (OSError, ValueError):
                pass
    if not clips:
        clips.append({"name": f"{slug}_clip_01", "scene": "S001", "shot": 1, "seconds": 4.0, "media_path": ""})
    return clips


def export_otio_and_kdenlive(book_dir: Path, slug: str, *, fps: int = 24) -> dict[str, Any]:
    """Export the project timeline to both OpenTimelineIO (.otio) and Kdenlive MLT XML (.kdenlive)."""
    exp_dir = book_dir / "exports"
    exp_dir.mkdir(parents=True, exist_ok=True)
    clips = _collect_timeline_clips(book_dir, slug)
    mix_wav = book_dir / "audio" / "mix" / "master_mix.wav"
    audio_path = str(mix_wav.resolve()) if mix_wav.is_file() else ""

    otio_path = exp_dir / f"{slug}.otio"
    kdenlive_path = exp_dir / f"{slug}.kdenlive"

    # 1. OpenTimelineIO (.otio)
    used_otio_lib = False
    try:
        import importlib

        otio = importlib.import_module("opentimelineio")

        tl = otio.schema.Timeline(name=f"{slug} — Pistachio's Studio")
        vtrack = otio.schema.Track(name="Video 1", kind=otio.schema.TrackKind.Video)
        for c in clips:
            frames = max(1, int(round(float(c["seconds"]) * fps)))
            tr = otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(0, fps),
                duration=otio.opentime.RationalTime(frames, fps),
            )
            mref = (
                otio.schema.ExternalReference(target_url=Path(c["media_path"]).as_uri(), available_range=tr)
                if c["media_path"]
                else otio.schema.MissingReference()
            )
            vtrack.append(otio.schema.Clip(name=c["name"], media_reference=mref, source_range=tr))
        tl.tracks.append(vtrack)

        if audio_path:
            atrack = otio.schema.Track(name="Master Audio", kind=otio.schema.TrackKind.Audio)
            tot_frames = max(1, sum(max(1, int(round(float(c["seconds"]) * fps))) for c in clips))
            atr = otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(0, fps),
                duration=otio.opentime.RationalTime(tot_frames, fps),
            )
            atrack.append(
                otio.schema.Clip(
                    name="master_mix.wav",
                    media_reference=otio.schema.ExternalReference(target_url=Path(audio_path).as_uri(), available_range=atr),
                    source_range=atr,
                )
            )
            tl.tracks.append(atrack)
        otio.adapters.write_to_file(tl, str(otio_path))
        used_otio_lib = True
    except Exception:
        # Pure-JSON OTIO schema fallback when opentimelineio isn't installed
        otio_doc = {
            "OTIO_SCHEMA": "Timeline.1",
            "name": f"{slug} — Pistachio's Studio",
            "tracks": {
                "OTIO_SCHEMA": "Stack.1",
                "name": "tracks",
                "children": [
                    {
                        "OTIO_SCHEMA": "Track.1",
                        "name": "Video 1",
                        "kind": "Video",
                        "children": [
                            {
                                "OTIO_SCHEMA": "Clip.1",
                                "name": c["name"],
                                "source_range": {
                                    "OTIO_SCHEMA": "TimeRange.1",
                                    "start_time": {"OTIO_SCHEMA": "RationalTime.1", "rate": fps, "value": 0},
                                    "duration": {
                                        "OTIO_SCHEMA": "RationalTime.1",
                                        "rate": fps,
                                        "value": max(1, int(round(float(c["seconds"]) * fps))),
                                    },
                                },
                                "media_reference": (
                                    {"OTIO_SCHEMA": "ExternalReference.1", "target_url": Path(c["media_path"]).as_uri()}
                                    if c["media_path"]
                                    else {"OTIO_SCHEMA": "MissingReference.1"}
                                ),
                            }
                            for c in clips
                        ],
                    }
                ],
            },
        }
        otio_path.write_text(json.dumps(otio_doc, indent=2), encoding="utf-8")

    # 2. Kdenlive / Shotcut MLT XML (.kdenlive)
    producers: list[str] = []
    entries: list[str] = []
    total_frames = 0
    for idx, c in enumerate(clips, start=1):
        frames = max(1, int(round(float(c["seconds"]) * fps)))
        total_frames += frames
        pid = f"producer_{idx}"
        res = escape(c["media_path"] or "color:#0f172a")
        producers.append(
            f'  <producer id="{pid}" in="0" out="{frames - 1}">\n'
            f'    <property name="resource">{res}</property>\n'
            f'    <property name="kdenlive:clipname">{escape(c["name"])}</property>\n'
            f"  </producer>"
        )
        entries.append(f'    <entry producer="{pid}" in="0" out="{frames - 1}" />')

    audio_producer = ""
    audio_playlist = '  <playlist id="playlist_audio" />'
    if audio_path:
        audio_producer = (
            f'  <producer id="producer_audio" in="0" out="{max(0, total_frames - 1)}">\n'
            f'    <property name="resource">{escape(audio_path)}</property>\n'
            f'    <property name="kdenlive:clipname">master_mix.wav</property>\n'
            f"  </producer>\n"
        )
        audio_playlist = (
            '  <playlist id="playlist_audio">\n'
            f'    <entry producer="producer_audio" in="0" out="{max(0, total_frames - 1)}" />\n'
            "  </playlist>"
        )

    mlt_xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<mlt LC_NUMERIC="C" version="7.28.0" title="Pistachio Studio Timeline">\n'
        f'  <profile description="HD 1080p {fps} fps" width="1920" height="1080" progressive="1" '
        f'sample_aspect_num="1" sample_aspect_den="1" display_aspect_num="16" display_aspect_den="9" '
        f'frame_rate_num="{fps}" frame_rate_den="1" colorspace="709" />\n'
        + "\n".join(producers)
        + "\n"
        + audio_producer
        + '  <playlist id="playlist_video">\n'
        + "\n".join(entries)
        + "\n  </playlist>\n"
        + audio_playlist
        + "\n"
        + f'  <tractor id="main_tractor" in="0" out="{max(0, total_frames - 1)}">\n'
        + '    <property name="kdenlive:projectName">' + escape(slug) + "</property>\n"
        + '    <track producer="playlist_video" />\n'
        + '    <track producer="playlist_audio" />\n'
        + "  </tractor>\n"
        + "</mlt>\n"
    )
    kdenlive_path.write_text(mlt_xml, encoding="utf-8")

    return {
        "otio_path": otio_path,
        "kdenlive_path": kdenlive_path,
        "clip_count": len(clips),
        "used_otio_lib": used_otio_lib,
    }
