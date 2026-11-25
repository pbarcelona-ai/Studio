#!/usr/bin/env python3
"""Zero-GPU SFX backend for Pistachio's Studio: Openverse Audio API (CC0/commercial real recordings) + Earshot procedural synth.

  python3 scripts/sfx_local.py <project> [--mode auto|openverse|earshot] [--license cc0|commercial] [--duration 4.0] [--force]

Reads shot SFX cues from `audio_shots.csv` (or `sound/plan.json` + `shots/shotlist.json`) and writes 44.1 kHz stereo WAVs to
`projects/books/<book>/audio/<folder>/sfx-NNNN.wav`, which `render_cut.py` picks up automatically.

  auto       uses Earshot procedural synthesis for motion-graphics/UI/transition cues (whoosh, riser, click, chime, impact)
             and Openverse real recordings for foley/ambience, automatically falling back to Earshot if offline or unmatched
  openverse  searches https://api.openverse.org/v1/audio/ (no API key needed), filters by license, converts via ffmpeg,
             and logs every attribution in credits.json + credits.txt
  earshot    100% offline deterministic procedural SFX synthesizer (and optional external `earshot` CLI when installed)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout  # noqa: E402
import shot_list  # noqa: E402
import sound_design  # noqa: E402

OPENVERSE_API = "https://api.openverse.org/v1/audio/"
USER_AGENT = "PistachiosStudio/0.1 (+https://github.com/pbarcelona-ai/Studio)"
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
SR = 44100
MODES = ("auto", "openverse", "earshot")
LICENSE_MODES = ("cc0", "commercial")

# Procedural SFX keyword routing (order matters: more specific transient/UI cues before broad ambience)
RECIPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("whoosh", ("whoosh", "swoosh", "swish", "whip", "swipe", "flyby", "pass by", "transition", "wipe")),
    ("riser", ("riser", "swell", "build", "crescendo", "sweep up", "tension rise", "reverse cymbal")),
    ("click", ("click", "tick", "pop", "ui", "button", "switch", "toggle", "latch", "snap", "beep", "typewriter")),
    ("chime", ("chime", "bell", "ding", "sparkle", "shimmer", "ping", "notification", "magic", "twinkle")),
    ("impact", ("impact", "hit", "thud", "boom", "slam", "punch", "crash", "drop", "knock", "stomp", "bang")),
    ("ambience", ("ambience", "ambient", "room tone", "wind", "rain", "storm", "fire", "ocean", "waves", "forest", "hum", "drone")),
)
PROCEDURAL_FIRST_RECIPES = {"whoosh", "riser", "click", "chime"}

_STOPWORDS = {"a", "an", "the", "of", "in", "on", "at", "to", "for", "with", "and", "or", "soft", "gentle", "distant", "quiet", "loud", "sound", "sfx", "effect"}

# Fetcher(query, license_mode) -> list[dict] (Openverse API results; injectable for tests)
OpenverseFetcher = Callable[[str, str], list[dict[str, Any]]]


class SFXError(RuntimeError):
    """Raised when SFX generation cannot proceed."""


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:
        raise SFXError("No ffmpeg found (install ffmpeg or imageio-ffmpeg)") from e


def clean_query(prompt: str) -> str:
    """Distill a verbose shot SFX description into concise search keywords for Openverse."""
    tokens = re.findall(r"[a-zA-Z0-9]+", prompt.lower())
    kept = [t for t in tokens if len(t) > 1 and t not in _STOPWORDS]
    if not kept:
        kept = tokens[:4]
    return " ".join(kept[:5])


def match_recipe(prompt: str) -> str:
    """Pick the best procedural Earshot recipe name for a natural-language SFX prompt."""
    low = prompt.lower()
    for recipe, words in RECIPE_KEYWORDS:
        if any(w in low for w in words):
            return recipe
    return "ambience"


def _seed_for(prompt: str, row: int) -> int:
    digest = hashlib.sha256(f"{row}:{prompt}".encode()).digest()
    return int.from_bytes(digest[:4], "little")


# ---------------------------------------------------------------------------------------------- Earshot procedural SFX
def _write_stereo_wav(dest: Path, samples: list[float], sample_rate: int = SR) -> Path:
    """Normalize safely below clipping (-1 dB headroom) and write a 16-bit stereo PCM WAV."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    peak = max((abs(x) for x in samples), default=0.0)
    scale = (0.88 / peak) if peak > 1e-6 else 0.0
    n = len(samples)
    fade = min(int(sample_rate * 0.015), n // 4)
    interleaved: list[int] = []
    for i, s in enumerate(samples):
        env = 1.0
        if fade > 0:
            if i < fade:
                env = i / fade
            elif i >= n - fade:
                env = (n - 1 - i) / fade
        v = int(max(-32767, min(32767, round(s * scale * env * 32767))))
        interleaved.append(v)
        interleaved.append(v)
    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(interleaved)}h", *interleaved))
    return dest


def synthesize_earshot(prompt: str, dest: Path, duration: float = 2.0, recipe: str = "", seed: int = 0) -> dict[str, Any]:
    """Synthesize a deterministic procedural sound effect inspired by Earshot sound kits."""
    chosen = recipe or match_recipe(prompt)
    dur = max(0.25, min(15.0, float(duration)))
    if chosen == "click":
        dur = min(dur, 0.35)
    elif chosen in ("whoosh", "impact"):
        dur = min(dur, 1.8)
    elif chosen in ("chime", "riser"):
        dur = min(dur, 3.0)

    rng = random.Random(seed or _seed_for(prompt, 1))
    n = max(1, int(SR * dur))
    buf = [0.0] * n
    lp = 0.0
    lp2 = 0.0

    if chosen == "whoosh":
        for i in range(n):
            p = i / n
            env = math.sin(math.pi * p) ** 1.7
            alpha = 0.04 + 0.35 * (math.sin(math.pi * p) ** 2)
            noise = rng.uniform(-1.0, 1.0)
            lp += alpha * (noise - lp)
            hp = noise - lp
            lp2 += (alpha * 0.5) * (hp - lp2)
            tone = 0.25 * math.sin(2 * math.pi * (140 + 420 * math.sin(math.pi * p)) * (i / SR))
            buf[i] = env * (lp2 * 1.4 + tone)
    elif chosen == "riser":
        phase = 0.0
        for i in range(n):
            p = i / n
            env = (p ** 2.1) * (1.0 - max(0.0, (p - 0.92) / 0.08))
            freq = 110.0 * (2.0 ** (3.0 * p))
            phase += 2 * math.pi * freq / SR
            noise = rng.uniform(-1.0, 1.0)
            alpha = 0.03 + 0.45 * p
            lp += alpha * (noise - lp)
            buf[i] = env * (0.55 * math.sin(phase) + 0.25 * math.sin(2.0 * phase) + 0.5 * (noise - lp))
    elif chosen == "impact":
        phase = 0.0
        for i in range(n):
            t = i / SR
            sub_freq = 38.0 + 130.0 * math.exp(-t * 16.0)
            phase += 2 * math.pi * sub_freq / SR
            sub = math.sin(phase) * math.exp(-t * 4.5)
            crack = rng.uniform(-1.0, 1.0) * math.exp(-t * 48.0)
            lp += 0.25 * (crack - lp)
            buf[i] = 0.85 * sub + 0.65 * lp
    elif chosen == "click":
        base_f = 900.0 + rng.uniform(-120.0, 260.0)
        for i in range(n):
            t = i / SR
            pulse = math.sin(2 * math.pi * base_f * t) * math.exp(-t * 75.0)
            overtone = 0.45 * math.sin(2 * math.pi * (base_f * 2.4) * t) * math.exp(-t * 110.0)
            tick = rng.uniform(-1.0, 1.0) * math.exp(-t * 180.0)
            buf[i] = pulse + overtone + 0.35 * tick
    elif chosen == "chime":
        base_f = 587.33 * (1.0 + 0.08 * (rng.random() - 0.5))
        ratios = ((1.0, 1.0, 2.2), (2.756, 0.45, 3.6), (5.404, 0.22, 5.5))
        for i in range(n):
            t = i / SR
            s = sum(amp * math.sin(2 * math.pi * base_f * r * t) * math.exp(-t * dec) for r, amp, dec in ratios)
            buf[i] = s * min(1.0, t / 0.008)
    else:  # ambience (gentle filtered noise bed)
        b0 = b1 = b2 = 0.0
        for i in range(n):
            t = i / SR
            w = rng.uniform(-1.0, 1.0)
            b0 = 0.997 * b0 + w * 0.029
            b1 = 0.985 * b1 + w * 0.032
            b2 = 0.950 * b2 + w * 0.048
            sway = 0.78 + 0.22 * math.sin(2 * math.pi * 0.25 * t)
            buf[i] = (b0 + b1 + b2) * sway

    _write_stereo_wav(dest, buf, SR)
    return {
        "source": "earshot",
        "recipe": chosen,
        "duration": round(dur, 3),
        "license": "MIT (synthesized locally)",
        "attribution": f"Procedural Earshot synth ({chosen})",
    }


def try_external_earshot(prompt: str, dest: Path, duration: float = 2.0) -> dict[str, Any] | None:
    """If the optional `earshot` CLI is installed on PATH, render via it; else return None."""
    exe = shutil.which("earshot")
    if not exe:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([exe, "render", "--prompt", prompt, "--duration", f"{duration:.2f}", "--out", str(dest)],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30)
    if r.returncode == 0 and dest.is_file() and dest.stat().st_size > 128:
        return {"source": "earshot_cli", "recipe": "external", "duration": round(duration, 3),
                "license": "MIT", "attribution": "Rendered via local earshot CLI"}
    return None


# ---------------------------------------------------------------------------------------------- Openverse Audio API
def search_openverse(query: str, license_mode: str = "cc0", page_size: int = 10, timeout: int = 15) -> list[dict[str, Any]]:
    """Query the keyless Openverse Audio API (`api.openverse.org/v1/audio/`) for openly licensed SFX."""
    q = clean_query(query)
    if not q:
        return []
    params: dict[str, str] = {"q": q, "page_size": str(page_size)}
    if license_mode == "cc0":
        params["license"] = "cc0,pdm"
    else:
        params["license_type"] = "commercial"
    url = OPENVERSE_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (OSError, ValueError, urllib.error.URLError):
        return []
    results = data.get("results")
    return results if isinstance(results, list) else []


def pick_openverse_candidate(results: list[dict[str, Any]], max_ms: int = 45_000) -> dict[str, Any] | None:
    """Choose the best sound-effect candidate: valid http(s) URL, prefers short clips and CC0/PDM licenses."""
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url.startswith(("https://", "http://")):
            continue
        dur_ms = int(item.get("duration") or 0)
        if dur_ms > max_ms:
            continue
        lic = str(item.get("license") or "").lower()
        score = 0
        if lic in ("cc0", "pdm"):
            score += 20
        elif lic == "by":
            score += 10
        if 300 <= dur_ms <= 15_000:
            score += 10
        if str(item.get("source") or "").lower() == "freesound":
            score += 5
        scored.append((score, item))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1]


def download_and_convert(url: str, dest: Path, duration: float = 4.0, ffmpeg_bin: str | None = None, timeout: int = 30) -> Path:
    """Download an Openverse audio asset safely and convert it to a normalized 44.1 kHz stereo WAV trimmed to `duration`."""
    if not url.startswith(("https://", "http://")):
        raise SFXError("refusing non-HTTP audio URL")
    ff = ffmpeg_bin or find_ffmpeg()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with tempfile.TemporaryDirectory(prefix="studio-sfx-") as tmp_:
        raw = Path(tmp_) / "source.bin"
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(MAX_DOWNLOAD_BYTES + 1)
        if len(data) > MAX_DOWNLOAD_BYTES or not data:
            raise SFXError("downloaded audio is empty or exceeds 25 MB limit")
        raw.write_bytes(data)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dur = max(0.3, min(30.0, float(duration)))
        fade_out_start = max(0.0, dur - 0.05)
        af = f"atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.02,afade=t=out:st={fade_out_start:.3f}:d=0.05"
        r = subprocess.run(
            [ff, "-y", "-loglevel", "error", "-i", str(raw), "-vn", "-af", af,
             "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s16le", str(dest)],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=45,
        )
        if r.returncode != 0 or not dest.is_file():
            raise SFXError("ffmpeg conversion failed: " + r.stderr.strip()[-300:])
    return dest


# ---------------------------------------------------------------------------------------------- book runner
def sfx_rows(pdir: Path) -> list[tuple[int, str]]:
    """[(1-based row, sfx prompt)] from audio_shots.csv, or sound/plan.json + shots/shotlist.json."""
    csv_path = pdir / "audio_shots.csv"
    if csv_path.is_file():
        rows: list[tuple[int, str]] = []
        with open(csv_path, newline="", encoding="utf-8") as fh:
            for i, r in enumerate(csv.DictReader(fh), 1):
                txt = (r.get("sfx") or "").strip()
                if txt:
                    rows.append((i, txt))
        if rows:
            return rows
    plan = sound_design.load(pdir)
    sl = shot_list.load(pdir)
    out: list[tuple[int, str]] = []
    row = 0
    for sc in sl.get("scenes", []):
        fx_by_shot = {int(e["n"]): str(e.get("sfx", "")).strip() for e in plan.get("effects", {}).get(sc["id"], []) if isinstance(e, dict)}
        for s in sc["shots"]:
            row += 1
            txt = fx_by_shot.get(int(s["n"]), "")
            if txt:
                out.append((row, txt))
    return out


def _write_credits(out_dir: Path, credits_list: list[dict[str, Any]]) -> None:
    (out_dir / "credits.json").write_text(json.dumps(credits_list, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Sound Effects Credits (Openverse / Earshot)", ""]
    for c in credits_list:
        lines.append(f"- sfx-{c['row']:04d}.wav [{c['source']}] ({c.get('license', '')}): {c.get('attribution', '')}")
    (out_dir / "credits.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_book_sfx(
    pdir: Path,
    mode: str = "auto",
    license_mode: str = "cc0",
    duration: float = 4.0,
    force: bool = False,
    fetcher: OpenverseFetcher | None = None,
    downloader: Callable[[str, Path, float], Path] | None = None,
    say: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Generate/fetch SFX WAVs for every shot in `pdir` using Openverse and/or Earshot."""
    if mode not in MODES:
        raise SFXError(f"mode must be one of {', '.join(MODES)}")
    if license_mode not in LICENSE_MODES:
        raise SFXError(f"license must be one of {', '.join(LICENSE_MODES)}")
    rows = sfx_rows(pdir)
    folder = "earshot" if mode == "earshot" else "openverse"
    out_dir = pdir / "audio" / folder
    out_dir.mkdir(parents=True, exist_ok=True)
    fetch = fetcher or search_openverse
    dl = downloader or download_and_convert

    credits_list: list[dict[str, Any]] = []
    rendered = skipped = openverse_n = earshot_n = missed = 0

    for row, prompt in rows:
        dest = out_dir / f"sfx-{row:04d}.wav"
        if dest.is_file() and not force:
            skipped += 1
            continue
        recipe = match_recipe(prompt)
        prefer_procedural = (mode == "earshot") or (mode == "auto" and recipe in PROCEDURAL_FIRST_RECIPES)
        meta: dict[str, Any] | None = None

        if not prefer_procedural and mode in ("auto", "openverse"):
            cand = pick_openverse_candidate(fetch(prompt, license_mode))
            if cand is not None:
                try:
                    dl(str(cand["url"]), dest, duration)
                    lic = str(cand.get("license") or license_mode).upper()
                    ver = str(cand.get("license_version") or "").strip()
                    creator = str(cand.get("creator") or "Unknown").strip()
                    title = str(cand.get("title") or clean_query(prompt)).strip()
                    landing = str(cand.get("foreign_landing_url") or cand.get("url") or "")
                    attr = str(cand.get("attribution") or f'"{title}" by {creator} ({lic} {ver}) {landing}').strip()
                    meta = {
                        "source": "openverse",
                        "title": title,
                        "creator": creator,
                        "license": f"{lic} {ver}".strip(),
                        "url": landing,
                        "attribution": attr,
                    }
                    openverse_n += 1
                    say(f"[sfx-{row:04d}] Openverse: {title} ({meta['license']})")
                except SFXError as e:
                    say(f"[sfx-{row:04d}] Openverse download failed ({e}); falling back")

        if meta is None and mode in ("auto", "earshot"):
            meta = try_external_earshot(prompt, dest, duration) or synthesize_earshot(prompt, dest, duration, recipe=recipe, seed=_seed_for(prompt, row))
            earshot_n += 1
            say(f"[sfx-{row:04d}] Earshot ({meta['recipe']}): {prompt[:50]}")

        if meta is not None:
            rendered += 1
            credits_list.append({"row": row, "prompt": prompt, **meta})
        else:
            missed += 1
            say(f"[sfx-{row:04d}] no Openverse match for: {prompt[:60]}")

    if credits_list:
        _write_credits(out_dir, credits_list)
    return {
        "folder": folder,
        "mode": mode,
        "total": len(rows),
        "rendered": rendered,
        "skipped": skipped,
        "openverse": openverse_n,
        "earshot": earshot_n,
        "missed": missed,
        "credits": str(out_dir / "credits.txt") if credits_list else "",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "Local SFX (Openverse + Earshot)")
    ap.add_argument("project")
    ap.add_argument("--mode", default="auto", choices=MODES)
    ap.add_argument("--license", default="cc0", choices=LICENSE_MODES, dest="license_mode")
    ap.add_argument("--duration", type=float, default=4.0)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    pdir = layout.project_dir(a.project, "book")
    try:
        res = render_book_sfx(pdir, mode=a.mode, license_mode=a.license_mode, duration=a.duration, force=a.force)
    except SFXError as e:
        print(f"SFX error: {e}", file=sys.stderr)
        return 1
    print(f"Done: {res['rendered']}/{res['total']} SFX ready (openverse={res['openverse']}, earshot={res['earshot']}, skipped={res['skipped']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
