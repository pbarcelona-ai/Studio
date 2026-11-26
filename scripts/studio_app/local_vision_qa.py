"""Free local Ollama Vision QA (Qwen2.5-VL / Gemma 3 / Llama 3.2 Vision / LLaVA) for Step 17 keyframes.

Replaces paid Gemini Vision QA with zero-cost local visual inspection for:
1. Solid-object physics & anatomical clipping errors.
2. Room/background & character wardrobe continuity drift against a reference frame.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("studio.local_vision_qa")

# Vision-capable local Ollama model prefixes, ranked best-first for visual QA
_VISION_MODEL_PATTERNS: tuple[str, ...] = (
    "qwen2.5vl",
    "qwen2.5-vl",
    "qwen3-vl",
    "qwen3vl",
    "gemma3",
    "llama3.2-vision",
    "minicpm-v",
    "pixtral",
    "llava",
    "moondream",
)


def ollama_base_url() -> str:
    """Resolve local Ollama HTTP base URL (defaults to http://127.0.0.1:11434)."""
    explicit = os.environ.get("OLLAMA_URL", "").strip() or os.environ.get("OLLAMA_HOST", "").strip()
    if explicit:
        if not explicit.startswith(("http://", "https://")):
            explicit = f"http://{explicit}"
        return explicit.rstrip("/")
    local_llm = os.environ.get("LOCAL_LLM_URL", "").strip()
    if local_llm and "11434" in local_llm:
        return local_llm.split("/v1", 1)[0].rstrip("/")
    return "http://127.0.0.1:11434"


def detect_ollama_vision_models(timeout: float = 1.5) -> dict[str, Any]:
    """Probe local Ollama for installed vision-capable models without ever blocking offline machines."""
    base = ollama_base_url()
    url = f"{base}/api/tags"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.debug("Ollama probe skipped/unavailable at %s: %s", url, e)
        return {"running": False, "base_url": base, "vision_models": [], "best_model": ""}

    all_names = [
        str(m.get("name") or "").strip()
        for m in (data.get("models") or [])
        if isinstance(m, dict) and m.get("name")
    ]

    def _rank(name: str) -> int:
        low = name.lower()
        for idx, pat in enumerate(_VISION_MODEL_PATTERNS):
            if pat in low:
                return idx
        return 999

    vision = sorted((n for n in all_names if _rank(n) < 999), key=_rank)
    return {
        "running": True,
        "base_url": base,
        "vision_models": vision,
        "best_model": vision[0] if vision else "",
    }


def _extract_json_obj(raw_text: str) -> dict[str, Any]:
    txt = str(raw_text or "").strip()
    if not txt:
        return {}
    try:
        parsed = json.loads(txt)
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        pass
    m = re.search(r"\{[\s\S]*\}", txt)
    if m:
        try:
            parsed = json.loads(m.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            pass
    return {}


def inspect_keyframe_with_ollama(
    png_path: Path,
    prompt: str,
    *,
    ref_image: Path | None = None,
    model_name: str = "",
    timeout: float = 35.0,
) -> dict[str, Any] | None:
    """Inspect a rendered keyframe using a free local Ollama Vision model.

    Returns ``None`` if Ollama or a vision model is not available (caller falls back
    gracefully to local sanity checks without erroring).
    """
    if not (png_path.is_file() and png_path.stat().st_size > 100):
        return {"passed": False, "issues": ["Generated image file is missing or empty"], "engine": "local_sanity"}

    chosen = model_name.strip()
    base = ollama_base_url()
    if not chosen:
        probe = detect_ollama_vision_models(timeout=1.5)
        if not probe.get("running") or not probe.get("best_model"):
            return None
        chosen = str(probe["best_model"])
        base = str(probe["base_url"])

    images_b64: list[str] = [base64.b64encode(png_path.read_bytes()).decode("ascii")]
    has_ref = bool(ref_image and ref_image.is_file() and ref_image.stat().st_size > 100 and ref_image != png_path)
    if has_ref and ref_image is not None:
        images_b64.append(base64.b64encode(ref_image.read_bytes()).decode("ascii"))

    continuity_clause = (
        "Image 1 is the newly rendered keyframe and Image 2 is the reference frame from the same scene. "
        "Also check if the room layout, furniture, lighting, or character clothing drifted noticeably from Image 2. "
        if has_ref
        else ""
    )
    qa_prompt = (
        "You are a strict film storyboard continuity & physics QA inspector. "
        f"{continuity_clause}"
        "Inspect Image 1 for:\n"
        "1. Solid-object clipping, limbs/tails/toys passing through furniture or bodies, extra/fused limbs, floating objects.\n"
        "2. Major character wardrobe or room-layout contradictions vs the shot description.\n"
        "Respond ONLY with valid JSON: "
        '{"passed": true/false, "issues": ["short specific issue"], "continuity_issues": ["short room/wardrobe drift"]}. '
        "Set passed=false ONLY for clear visible errors (ignore tiny stylistic quirks).\n\n"
        f"Shot description: {prompt[:500]}"
    )

    payload = json.dumps(
        {
            "model": chosen,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
            "messages": [
                {
                    "role": "user",
                    "content": qa_prompt,
                    "images": images_b64,
                }
            ],
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{base}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = str((data.get("message") or {}).get("content") or "")
        parsed = _extract_json_obj(content)
        issues = [str(x).strip() for x in (parsed.get("issues") or []) if str(x).strip()]
        cont_issues = [str(x).strip() for x in (parsed.get("continuity_issues") or []) if str(x).strip()]
        all_issues = issues + [ci for ci in cont_issues if ci not in issues]
        passed = bool(parsed.get("passed", not issues))
        return {
            "passed": passed,
            "issues": all_issues[:6],
            "continuity_issues": cont_issues[:4],
            "engine": f"ollama:{chosen}",
        }
    except Exception as e:
        log.debug("Ollama vision QA failed on %s: %s", chosen, e)
        return None
