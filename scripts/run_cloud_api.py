#!/usr/bin/env python3
"""Run rows of a prompt CSV via Direct Serverless Cloud APIs (Fal.ai, Replicate) and save results into the project.

Works on macOS, Windows, and Linux. No GPU or Kaggle account required.
Results land in images/<model>, videos/<model>, or audio/<kind>, matching Kaggle/local runs.

Usage:
  [PROJECT=my_book] [SHOTS_CSV=all_images.csv] python3 scripts/run_cloud_api.py MODEL START END

Keys:
  FAL_KEY or REPLICATE_API_TOKEN in environment, or ~/.pistachios_studio/cloud_keys.json
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout  # noqa: E402
from runner_common import RunError, base_dir, default_csv, mode_of, project_folder  # noqa: E402

CLOUD_KEYS_FILE = Path.home() / ".pistachios_studio" / "cloud_keys.json"

# Endpoint maps: studio model -> (provider, endpoint_id)
FAL_IMAGE_MODELS = {
    "flux1_schnell": "fal-ai/flux/schnell",
    "flux1_dev": "fal-ai/flux/dev",
    "flux2_klein_4b": "fal-ai/flux/schnell",
    "sdxl": "fal-ai/fast-sdxl",
    "sdxl_turbo": "fal-ai/fast-sdxl",
    "sdxl_lightning": "fal-ai/fast-sdxl",
    "sd35_large": "fal-ai/stable-diffusion-v35-large",
    "sd35_large_turbo": "fal-ai/stable-diffusion-v35-large",
    "qwen_image_21": "fal-ai/qwen-image",
}

FAL_VIDEO_MODELS = {
    "ltx_video": ("fal-ai/ltx-video", False),
    "ltx_video_i2v": ("fal-ai/ltx-video/image-to-video", True),
    "ltx_video_fast_i2v": ("fal-ai/ltx-video/image-to-video", True),
    "wan": ("fal-ai/wan/text-to-video", False),
    "wan22_ti2v_5b": ("fal-ai/wan/text-to-video", False),
    "wan22_ti2v_5b_i2v": ("fal-ai/wan/image-to-video", True),
    "wan21_i2v_14b": ("fal-ai/wan/image-to-video", True),
    "pika_h3_flex_i2v": ("fal-ai/minimax/video-01/image-to-video", True),
}


def load_api_keys() -> dict[str, str]:
    """Retrieve Cloud API keys from environment or ~/.pistachios_studio/cloud_keys.json."""
    keys: dict[str, str] = {}
    if os.environ.get("FAL_KEY"):
        keys["fal"] = os.environ["FAL_KEY"].strip()
    if os.environ.get("REPLICATE_API_TOKEN"):
        keys["replicate"] = os.environ["REPLICATE_API_TOKEN"].strip()
    if CLOUD_KEYS_FILE.is_file():
        try:
            data = json.loads(CLOUD_KEYS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if not keys.get("fal") and data.get("fal_key"):
                    keys["fal"] = str(data["fal_key"]).strip()
                if not keys.get("replicate") and data.get("replicate_token"):
                    keys["replicate"] = str(data["replicate_token"]).strip()
        except (OSError, ValueError):
            pass
    return keys


def save_api_keys(fal_key: str = "", replicate_token: str = "") -> None:
    CLOUD_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    current = {}
    if CLOUD_KEYS_FILE.is_file():
        try:
            current = json.loads(CLOUD_KEYS_FILE.read_text(encoding="utf-8")) or {}
        except Exception:
            current = {}
    if fal_key:
        current["fal_key"] = fal_key
    if replicate_token:
        current["replicate_token"] = replicate_token
    CLOUD_KEYS_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")


def call_fal_api(endpoint: str, payload: dict[str, Any], api_key: str, timeout: int = 120) -> dict[str, Any]:
    """Send request to Fal.ai queue/sync endpoint and return JSON response."""
    url = f"https://fal.run/{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Key {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "PistachiosStudio/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def download_file(url: str, dest: Path) -> Path:
    """Download binary asset from URL to local destination."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    req = urllib.request.Request(url, headers={"User-Agent": "PistachiosStudio/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as fh:
        while chunk := resp.read(65536):
            fh.write(chunk)
    tmp.replace(dest)
    return dest


def file_to_data_uri(path: Path) -> str:
    """Encode an image as a base64 data URI for API payloads."""
    import base64
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def generate_row(
    model: str,
    row: dict[str, Any],
    row_idx: int,
    out_dir: Path,
    keys: dict[str, str],
    keyframe_dir: Path | None = None,
    refs_dir: Path | None = None,
) -> Path:
    """Generate image or video for a single row and save to disk."""
    clean_model = model.removeprefix("image_")
    prompt = row.get("prompt", "")
    seed = int(row.get("seed", row_idx)) if row.get("seed") not in (None, "") else row_idx
    w = int(row.get("width", 1024)) if row.get("width") not in (None, "") else 1024
    h = int(row.get("height", 1024)) if row.get("height") not in (None, "") else 1024
    negative = row.get("negative") or ""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Image models
    if clean_model in FAL_IMAGE_MODELS or model.startswith("image_"):
        endpoint = FAL_IMAGE_MODELS.get(clean_model, "fal-ai/flux/schnell")
        out_file = out_dir / f"image-{row_idx:04d}.png"
        if out_file.is_file():
            return out_file

        if not keys.get("fal"):
            raise RunError("Fal.ai API key is missing. Set FAL_KEY in your environment or ~/.pistachios_studio/cloud_keys.json")

        payload: dict[str, Any] = {
            "prompt": prompt,
            "image_size": {"width": w, "height": h},
            "num_inference_steps": int(row.get("steps", 4 if "schnell" in endpoint else 28)),
            "seed": seed,
            "enable_safety_checker": False,
        }
        if negative and "flux" not in endpoint:
            payload["negative_prompt"] = negative

        # Character reference / Structure image conditioning
        ref_path: Path | None = None
        if row.get("init_image") and refs_dir:
            cand = refs_dir / str(row["init_image"])
            if cand.is_file():
                ref_path = cand
        elif row.get("refs") and refs_dir and refs_dir.is_dir():
            ref_names = [n for n in str(row["refs"]).split("|") if n.strip()]
            for rname in ref_names:
                for cand in refs_dir.glob(f"*{rname}*"):
                    if cand.is_file():
                        ref_path = cand
                        break
                if ref_path:
                    break

        if ref_path and ref_path.is_file():
            payload["image_url"] = file_to_data_uri(ref_path)
            payload["strength"] = float(row.get("strength") or 0.65)
            if "flux" in endpoint and not endpoint.endswith("/image-to-image"):
                endpoint = f"{endpoint}/image-to-image"
            elif "fast-sdxl" in endpoint and not endpoint.endswith("/image-to-image"):
                endpoint = f"{endpoint}/image-to-image"

        res = call_fal_api(endpoint, payload, keys["fal"])
        images = res.get("images") or []
        if not images or not images[0].get("url"):
            raise RunError(f"No image returned from {endpoint}: {res}")
        download_file(images[0]["url"], out_file)
        return out_file

    # Video models
    if clean_model in FAL_VIDEO_MODELS or clean_model.endswith("_i2v"):
        endpoint_info = FAL_VIDEO_MODELS.get(clean_model, ("fal-ai/ltx-video/image-to-video", True))
        endpoint, is_i2v = endpoint_info
        out_file = out_dir / f"shot-{row_idx:04d}.mp4"
        if out_file.is_file():
            return out_file

        if not keys.get("fal"):
            raise RunError("Fal.ai API key is missing. Set FAL_KEY in your environment or ~/.pistachios_studio/cloud_keys.json")

        payload: dict[str, Any] = {"prompt": prompt, "seed": seed}
        if is_i2v:
            if not keyframe_dir:
                raise RunError(f"Keyframe directory required for image-to-video model {clean_model}")
            kf = keyframe_dir / f"image-{row_idx:04d}.png"
            if not kf.is_file():
                raise RunError(f"Missing keyframe for row {row_idx}: {kf}")
            payload["image_url"] = file_to_data_uri(kf)

        res = call_fal_api(endpoint, payload, keys["fal"], timeout=180)
        video_url = (res.get("video") or {}).get("url") or res.get("video_url")
        if not video_url:
            raise RunError(f"No video returned from {endpoint}: {res}")
        download_file(video_url, out_file)
        return out_file

    # Local audio fallback for kokoro
    if clean_model == "kokoro" or model == "audio_kokoro":
        from local_audio import narration
        narration(out_dir.parent.parent if out_dir.name == "kokoro" else out_dir.parent)
        out_file = out_dir / f"narration-{row_idx:04d}.wav"
        if out_file.is_file():
            return out_file
        raise RunError(f"Local audio generation failed for row {row_idx}")

    raise RunError(f"Model '{model}' is not currently configured for direct cloud API execution.")


def main() -> None:
    if len(sys.argv) < 4:
        sys.exit(__doc__)

    model = sys.argv[1]
    start = int(sys.argv[2])
    end = int(sys.argv[3])

    project_slug = os.environ.get("PROJECT", "").strip()
    if not project_slug:
        raise RunError("PROJECT environment variable is required")

    pd = project_folder(project_slug)
    shots_csv = os.environ.get("SHOTS_CSV", "").strip()
    clean_model = model.removeprefix("image_").removeprefix("audio_")
    if not shots_csv:
        if clean_model in FAL_IMAGE_MODELS and (pd / "all_images.csv").is_file():
            shots_csv = "all_images.csv"
        else:
            shots_csv = default_csv(model)
    csv_file = pd / shots_csv
    if not csv_file.is_file():
        raise RunError(f"Prompt CSV not found: {csv_file}")

    rows = list(csv.DictReader(open(csv_file, newline="", encoding="utf-8")))
    if not rows:
        raise RunError(f"Empty prompt CSV: {csv_file}")

    start = max(1, start)
    end = min(len(rows), end)

    mode = mode_of(shots_csv)
    folder_name = f"{model.removeprefix('image_').removeprefix('audio_')}{('_' + mode) if mode else ''}"
    if model.startswith("audio_") or model == "kokoro":
        out_dir = pd / "audio" / folder_name
    elif model.startswith("image_") or any(m in model for m in ("sdxl", "flux", "sd35", "qwen")):
        out_dir = pd / "images" / folder_name
    else:
        out_dir = pd / "videos" / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)

    # Keyframes directory for image-to-video
    kf_dir: Path | None = None
    if "_i2v" in model or model in FAL_VIDEO_MODELS:
        named = os.environ.get("KEYFRAME_MODEL", "").strip()
        if named:
            kf_dir = pd / "images" / f"{named}_keyframes"
        else:
            candidates = sorted(
                (p for p in (pd / "images").glob("*_keyframes") if p.is_dir()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            kf_dir = candidates[0] if candidates else None

    refs_dir = pd / "keyframe_refs" if (pd / "keyframe_refs").is_dir() else (csv_file.parent / "keyframe_refs")
    keys = load_api_keys()
    print(f"== Cloud API generation: {model} rows {start}-{end} into {out_dir}", flush=True)

    failed = []
    for i in range(start, end + 1):
        t0 = time.time()
        try:
            generate_row(model, rows[i - 1], i, out_dir, keys, kf_dir, refs_dir)
            print(f"[{i}/{end}] ok ({time.time() - t0:.1f}s)", flush=True)
        except Exception as e:
            failed.append(i)
            print(f"[{i}/{end}] FAILED: {e}", flush=True)

    if failed:
        if len(failed) == end - start + 1:
            raise RunError(f"All {len(failed)} items failed to generate via Cloud API.")
        print(f"Warning: {len(failed)} item(s) failed: {failed}", flush=True)
    else:
        print("== All items completed successfully.", flush=True)


if __name__ == "__main__":
    main()
