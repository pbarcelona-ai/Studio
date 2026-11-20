#!/usr/bin/env python3
"""Generate, extend, and conversationally edit video clips with synchronized native audio
using Gemini Omni 1.2 Flash (gemini-omni-1.2-flash) via the official google-genai Interactions API.

Supports:
  - Text-to-video (3s-15s, 360p/720p/1080p/4k, 16:9 or 9:16)
  - First-frame-to-video (3s-15s) and first+last-frame transitions (3s-10s)
  - Multi-reference-to-video (up to 6 character turnaround / set keycard images)
  - Video extensions (3s-10s per turn, up to 30s total)
  - Conversational multi-turn editing ("Edit by Talking") via --previous-interaction-id

API Key:
  Reads GEMINI_API_KEY from the environment or ~/.pistachios_studio/cloud_keys.json.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "gemini-omni-1.2-flash"
VALID_RESOLUTIONS = ("360p", "720p", "1080p", "4k")
VALID_ASPECTS = ("16:9", "9:16")
MIN_DURATION = 3
MAX_DURATION = 15
MAX_INTERP_OR_EXTEND = 10
MAX_REF_IMAGES = 6
CLOUD_KEYS_FILE = Path.home() / ".pistachios_studio" / "cloud_keys.json"


def get_gemini_api_key() -> str:
    """Return GEMINI_API_KEY (or GOOGLE_API_KEY) from environment or ~/.pistachios_studio/cloud_keys.json."""
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        env_key = (os.environ.get(var) or "").strip()
        if env_key:
            return env_key
    if CLOUD_KEYS_FILE.is_file():
        try:
            data = json.loads(CLOUD_KEYS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("gemini_api_key"):
                return str(data["gemini_api_key"]).strip()
        except (OSError, ValueError):
            pass
    return ""


def save_gemini_api_key(api_key: str) -> None:
    """Persist GEMINI_API_KEY into ~/.pistachios_studio/cloud_keys.json."""
    CLOUD_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    if CLOUD_KEYS_FILE.is_file():
        try:
            current = json.loads(CLOUD_KEYS_FILE.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError):
            current = {}
    current["gemini_api_key"] = api_key.strip()
    CLOUD_KEYS_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")


def sdk_available() -> bool:
    """Return True if the official google-genai SDK is importable."""
    try:
        from google import genai  # noqa: F401
        return True
    except ImportError:
        return False


def sanitize_error(err: Any) -> str:
    """Redact API keys and tokens from error strings before returning or logging."""
    s = str(err or "")
    key = get_gemini_api_key()
    if key and len(key) >= 8:
        s = s.replace(key, "[REDACTED_KEY]")
    s = re.sub(r"AIza[0-9A-Za-z_\-]{25,}", "[REDACTED_KEY]", s)
    s = re.sub(r"AQ\.[0-9A-Za-z_\-]{20,}", "[REDACTED_KEY]", s)
    s = re.sub(r"([?&](?:key|api_key|apiKey|access_token|token)=)[^&\s\"'<>()]+", r"\1[REDACTED]", s)
    return s[:500]


def validate_duration(seconds: int | str | None, capped_10: bool = False) -> str | None:
    """Validate and format integer duration as 'Ns'."""
    if seconds is None or str(seconds).strip() == "":
        return None
    raw = str(seconds).strip().lower().rstrip("s")
    val = int(float(raw))
    hi = MAX_INTERP_OR_EXTEND if capped_10 else MAX_DURATION
    if val < MIN_DURATION or val > hi:
        raise ValueError(f"Duration must be between {MIN_DURATION} and {hi} seconds (got {val}).")
    return f"{val}s"


def validate_resolution(res: str | None) -> str:
    r = (res or "720p").strip().lower()
    if r not in VALID_RESOLUTIONS:
        raise ValueError(f"Resolution must be one of {', '.join(VALID_RESOLUTIONS)} (got {res}).")
    return r


def validate_aspect(aspect: str | None) -> str:
    a = (aspect or "16:9").strip()
    return a if a in VALID_ASPECTS else "16:9"


def _upload_and_wait(client: Any, file_path: str | Path, strip_audio: bool = False) -> tuple[str, str]:
    """Upload a local image or video via the Gemini Files API and poll until ACTIVE."""
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"Asset not found: {file_path}")

    upload_target = p
    temp_stripped: Path | None = None
    try:
        if strip_audio:
            temp_stripped = p.parent / f".tmp_noaudio_{uuid.uuid4().hex}{p.suffix}"
            proc = subprocess.run(
                ["ffmpeg", "-y", "-i", str(p), "-c:v", "copy", "-an", str(temp_stripped)],
                capture_output=True, text=True
            )
            if proc.returncode != 0:
                raise RuntimeError(f"ffmpeg strip-audio failed: {sanitize_error(proc.stderr)}")
            upload_target = temp_stripped

        uploaded = client.files.upload(file=str(upload_target))
        name = uploaded.name
        while True:
            meta = client.files.get(name=name)
            state = getattr(meta.state, "name", str(meta.state)).upper()
            if state == "ACTIVE":
                mime = getattr(meta, "mime_type", None) or mimetypes.guess_type(str(p))[0] or "application/octet-stream"
                return meta.uri, mime
            if state == "FAILED":
                raise RuntimeError(f"Gemini Files API processing failed for {p.name}")
            time.sleep(2)
    finally:
        if temp_stripped and temp_stripped.exists():
            try:
                temp_stripped.unlink()
            except OSError:
                pass


def generate_omni_video(
    prompt: str,
    output_path: str | Path,
    *,
    model: str = DEFAULT_MODEL,
    aspect_ratio: str = "16:9",
    duration: int | None = 10,
    resolution: str = "720p",
    first_frame: str | None = None,
    last_frame: str | None = None,
    reference_images: list[str] | None = None,
    video_path: str | None = None,
    extend_video: str | None = None,
    strip_audio: bool = False,
    previous_interaction_id: str | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    """Run Gemini Omni 1.2 Flash via the google-genai Interactions API and download the MP4."""
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it in Step 13 (Hardware) or export GEMINI_API_KEY.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("google-genai SDK is not installed. Run: pip install -U google-genai") from exc

    if last_frame and not first_frame:
        raise ValueError("last_frame requires first_frame.")

    refs = [r for r in (reference_images or []) if r][:MAX_REF_IMAGES]
    capped_10 = bool((first_frame and last_frame) or extend_video)
    dur_str = validate_duration(duration, capped_10=capped_10) if duration is not None else None
    res_str = validate_resolution(resolution)
    asp_str = validate_aspect(aspect_ratio)

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=max(60, int(timeout)) * 1000))

    input_parts: list[dict[str, Any]] = []
    if first_frame:
        uri, mime = _upload_and_wait(client, first_frame)
        input_parts.append({"type": "image", "uri": uri, "mime_type": mime})
    if last_frame:
        uri, mime = _upload_and_wait(client, last_frame)
        input_parts.append({"type": "image", "uri": uri, "mime_type": mime})
    for ref in refs:
        uri, mime = _upload_and_wait(client, ref)
        input_parts.append({"type": "image", "uri": uri, "mime_type": mime})
    if extend_video:
        uri, mime = _upload_and_wait(client, extend_video, strip_audio=strip_audio)
        input_parts.append({"type": "video", "uri": uri, "mime_type": mime})
    elif video_path:
        uri, mime = _upload_and_wait(client, video_path, strip_audio=strip_audio)
        input_parts.append({"type": "video", "uri": uri, "mime_type": mime})

    input_parts.append({"type": "text", "text": prompt})

    video_config: dict[str, Any] = {
        "type": "video",
        "aspect_ratio": asp_str,
        "resolution": res_str,
    }
    if dur_str:
        video_config["duration"] = dur_str

    create_kwargs: dict[str, Any] = {
        "model": model,
        "input": input_parts,
        "response_format": video_config,
    }
    if previous_interaction_id:
        create_kwargs["previous_interaction_id"] = previous_interaction_id

    try:
        interaction = client.interactions.create(**create_kwargs)
    except Exception as exc:
        raise RuntimeError(f"Gemini Omni API error: {sanitize_error(exc)}") from exc

    output_video = getattr(interaction, "output_video", None)
    if not output_video or not getattr(output_video, "uri", None):
        raise RuntimeError("Gemini Omni returned no video output (note: video uploads/edits have regional restrictions).")

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    video_bytes = client.files.download(file=output_video.uri)
    out_p.write_bytes(video_bytes)

    interaction_id = getattr(interaction, "id", None)
    return {
        "status": "ok",
        "model": model,
        "output": str(out_p),
        "bytes": len(video_bytes),
        "interaction_id": interaction_id,
        "resolution": res_str,
        "aspect_ratio": asp_str,
        "duration": dur_str or "10s",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate or edit video using Gemini Omni 1.2 Flash.")
    ap.add_argument("prompt", help="Text prompt or conversational edit instruction")
    ap.add_argument("--output", "-o", required=True, help="Output MP4 file path")
    ap.add_argument("--duration", type=int, default=10, help="Clip duration in seconds (3-15, default 10)")
    ap.add_argument("--resolution", default="720p", choices=VALID_RESOLUTIONS)
    ap.add_argument("--aspect-ratio", default="16:9", choices=VALID_ASPECTS)
    ap.add_argument("--first-frame", help="Starting keyframe image path")
    ap.add_argument("--last-frame", help="Ending keyframe image path (requires --first-frame)")
    ap.add_argument("--image", action="append", default=[], help="Reference image path (up to 6)")
    ap.add_argument("--video", help="Source video path to edit")
    ap.add_argument("--extend", help="Source video path to extend (3-10s)")
    ap.add_argument("--strip-audio", action="store_true", help="Strip original audio before editing")
    ap.add_argument("--previous-interaction-id", help="Previous interaction ID for conversational turn-by-turn edits")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args(argv)

    res = generate_omni_video(
        prompt=args.prompt,
        output_path=args.output,
        aspect_ratio=args.aspect_ratio,
        duration=args.duration,
        resolution=args.resolution,
        first_frame=args.first_frame,
        last_frame=args.last_frame,
        reference_images=args.image,
        video_path=args.video,
        extend_video=args.extend,
        strip_audio=args.strip_audio,
        previous_interaction_id=args.previous_interaction_id,
        timeout=args.timeout,
    )
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
