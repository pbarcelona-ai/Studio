"""Strict base64 decoding and binary magic-byte validation for uploaded media files."""
from __future__ import annotations

import base64
import binascii

from .common import PlanError


def _strip_data_url(b64: str) -> str:
    s = str(b64 or "").strip()
    if "," in s and s.startswith("data:"):
        s = s.split(",", 1)[1].strip()
    return "".join(s.split())


def detect_image_format(raw: bytes) -> str:
    """Return canonical image extension ('.png', '.jpg', '.webp', '.gif') or '' if unrecognized."""
    if len(raw) < 12:
        return ""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if raw.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return ".webp"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return ""


def detect_audio_format(raw: bytes) -> str:
    """Return canonical audio extension ('.wav', '.mp3', '.ogg', '.flac', '.m4a', '.aiff') or ''."""
    if len(raw) < 12:
        return ""
    if raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
        return ".wav"
    if raw[:4] == b"FORM" and raw[8:12] in (b"AIFF", b"AIFC"):
        return ".aiff"
    if raw.startswith(b"ID3") or (raw[0] == 0xFF and (raw[1] & 0xE0) == 0xE0):
        return ".mp3"
    if raw.startswith(b"OggS"):
        return ".ogg"
    if raw.startswith(b"fLaC"):
        return ".flac"
    if raw[4:8] == b"ftyp":
        return ".m4a"
    return ""


def detect_video_format(raw: bytes) -> str:
    """Return canonical video extension ('.mp4', '.webm', '.mkv', '.avi') or ''."""
    if len(raw) < 12:
        return ""
    if raw[4:8] == b"ftyp":
        return ".mp4"
    if raw[:4] == b"\x1a\x45\xdf\xa3":
        return ".webm"
    if raw[:4] == b"RIFF" and raw[8:12] == b"AVI ":
        return ".avi"
    return ""


def decode_verified_base64(
    raw_b64: str,
    *,
    kind: str,
    min_bytes: int = 32,
    max_bytes: int = 64 * 1024 * 1024,
) -> tuple[bytes, str]:
    """Strictly decode base64 (`validate=True`) and verify magic bytes match `kind` ('image' | 'audio' | 'video')."""
    cleaned = _strip_data_url(raw_b64)
    if not cleaned:
        raise PlanError(f"uploaded {kind} data is empty")
    try:
        raw = base64.b64decode(cleaned, validate=True)
    except (binascii.Error, ValueError) as e:
        raise PlanError(f"invalid base64 {kind} payload") from e
    if len(raw) < min_bytes:
        raise PlanError(f"uploaded {kind} file is empty or too small")
    if len(raw) > max_bytes:
        raise PlanError(f"uploaded {kind} file exceeds {max_bytes // (1024 * 1024)} MB limit")

    if kind == "image":
        ext = detect_image_format(raw)
        if not ext:
            raise PlanError("uploaded file is not a valid PNG, JPEG, WebP, or GIF image")
        return raw, ext
    if kind == "audio":
        ext = detect_audio_format(raw)
        if not ext:
            raise PlanError("uploaded file is not a valid WAV, MP3, OGG, FLAC, M4A, or AIFF audio file")
        return raw, ext
    if kind == "video":
        ext = detect_video_format(raw)
        if not ext:
            raise PlanError("uploaded file is not a valid MP4, MOV, WebM, MKV, or AVI video file")
        return raw, ext
    raise PlanError(f"unsupported upload media kind: {kind}")
