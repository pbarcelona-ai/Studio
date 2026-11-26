"""Audio-First Clock, -14 LUFS loudness mastering, and Reels/Shorts safe-zone captions for Studio.

Integrates the proven free/local techniques from Trendjack Animator (`adtool.py`) and
Sama's AI Video Editing Playbook:
- Word-timed clock extraction via local `faster-whisper` (when installed) or structured transcript/script fallback
- Whole-frame cut snapping (`snap_to_frames`) so A/V duration stays within <= 40 ms
- Phone/Reels/Shorts safe-zone caption segmentation (1080x1920 safe bands, >= 56 px font floor,
  orphan small-word prevention, decimal & URL dot preservation like `2.5` and `site.com`)
- Interactive Caption Proofread find-and-replace (fixing misheard proper names before burn-in)
- Two-pass measured `-14 LUFS` loudness normalization + true-peak limiter via FFmpeg
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger("studio.audio_first_clock")

# Reels / TikTok / Shorts safe zone bands on a 1080x1920 vertical frame:
# (y_top, y_bottom, x_left, x_right) — excludes top status bar, bottom caption bar, and right-hand action icons
REELS_SAFE_BANDS: list[tuple[int, int, int, int]] = [
    (347, 867, 71, 1027),
    (868, 1426, 71, 886),
]
MIN_CAPTION_PX = 56
DEFAULT_SMALL_WORDS: set[str] = {
    "the", "a", "an", "and", "to", "of", "in", "on", "for", "with", "but", "or", "at", "by", "so", "is", "it",
}

_DECIMAL_OR_URL_DOT_RE = re.compile(r"(?<=\w)[.,](?=\w)")
_STRIP_PUNCT_RE = re.compile(r'[,"\u201c\u201d\u201e\u00bb\u00ab]+')
_TRAILING_DOT_RE = re.compile(r"\.+$")


def clean_caption_word(word: str) -> str:
    """Strip stray punctuation while keeping dots/commas inside numbers (`2.5`, `10,000`) and URLs (`site.com`)."""
    raw = str(word or "").strip()
    if not raw:
        return ""
    # Protect intra-word dots and commas (numbers & domains) with sentinel tokens
    protected = _DECIMAL_OR_URL_DOT_RE.sub(lambda m: "\x00DOT\x00" if m.group(0) == "." else "\x00COM\x00", raw)
    cleaned = _STRIP_PUNCT_RE.sub("", protected)
    cleaned = _TRAILING_DOT_RE.sub("", cleaned)
    cleaned = cleaned.replace("\x00DOT\x00", ".").replace("\x00COM\x00", ",")
    return cleaned.strip()


def snap_to_frames(seconds: float, fps: int = 24) -> float:
    """Snap a timestamp in seconds to the nearest whole video frame boundary."""
    safe_fps = max(1, int(fps or 24))
    frames = round(max(0.0, float(seconds)) * safe_fps)
    return round(frames / float(safe_fps), 6)


def segment_safe_captions(
    words: list[dict[str, Any]],
    *,
    fps: int = 24,
    max_words: int = 4,
    max_chars: int = 22,
    small_words: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Group word-timed entries into phone-readable, safe-zone-compliant caption cues.

    Rules enforced:
    1. Keep font readable (>= 56 px on 1080x1920): split cues if word count > `max_words` or chars > `max_chars`.
    2. Never leave a trailing small function word (e.g. `the`, `to`, `of`) dangling at the end of a cue.
    3. Avoid orphan 1-word cues at sentence ends by borrowing 1 word from the previous cue when possible.
    4. Preserve decimals (`2.5`, `10,000`) and URLs (`site.com`).
    5. Snap cue start/end times to whole video frames.
    """
    sw = {w.lower() for w in (small_words if small_words is not None else DEFAULT_SMALL_WORDS)}
    cleaned: list[dict[str, Any]] = []
    for item in words:
        if not isinstance(item, dict):
            continue
        txt = clean_caption_word(str(item.get("word") or item.get("text") or ""))
        if not txt:
            continue
        start = float(item.get("start", 0.0) or 0.0)
        end = float(item.get("end", start + 0.25) or (start + 0.25))
        if end <= start:
            end = start + 0.20
        cleaned.append({"word": txt, "start": start, "end": end})

    if not cleaned:
        return []

    groups: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []

    for w in cleaned:
        cand_text = " ".join(x["word"] for x in [*cur, w])
        pause_gap = (w["start"] - cur[-1]["end"]) if cur else 0.0
        if cur and (len(cur) >= max_words or len(cand_text) > max_chars or pause_gap > 0.65):
            # If the current chunk ends on a small word and has > 1 word, carry that small word into the next chunk
            if len(cur) > 1 and cur[-1]["word"].lower() in sw:
                carry = cur.pop()
                groups.append(cur)
                cur = [carry, w]
            else:
                groups.append(cur)
                cur = [w]
        else:
            cur.append(w)
    if cur:
        groups.append(cur)

    # Prevent trailing 1-word orphan when previous group has >= 3 words
    if len(groups) >= 2 and len(groups[-1]) == 1 and len(groups[-2]) >= 3:
        moved = groups[-2].pop()
        groups[-1].insert(0, moved)

    # Estimate font size inside the lower Reels safe band (width = 886 - 71 = 815 px)
    safe_band = REELS_SAFE_BANDS[1]
    band_w = safe_band[3] - safe_band[2]
    max_len = max(len(" ".join(x["word"] for x in g)) for g in groups)
    # Approximate bold uppercase glyph width ~ 0.62 * px
    est_px = int(min(74, max(MIN_CAPTION_PX, band_w / max(1.0, max_len * 0.62))))

    cues: list[dict[str, Any]] = []
    for idx, g in enumerate(groups, start=1):
        st = snap_to_frames(g[0]["start"], fps)
        en = snap_to_frames(g[-1]["end"], fps)
        if en <= st:
            en = snap_to_frames(st + (1.0 / max(1, fps)), fps)
        cues.append({
            "index": idx,
            "start": st,
            "end": en,
            "text": " ".join(x["word"] for x in g),
            "font_px": est_px,
            "safe_band": {"y_top": safe_band[0], "y_bottom": safe_band[1], "x_left": safe_band[2], "x_right": safe_band[3]},
        })
    return cues


def apply_caption_proofread(
    cues: list[dict[str, Any]],
    replacements: dict[str, str],
) -> tuple[list[dict[str, Any]], int]:
    """Apply case-insensitive whole-word proofread replacements (e.g. `{"Cloud": "Claude"}`) to caption cues."""
    rules: list[tuple[re.Pattern[str], str]] = []
    for old, new in (replacements or {}).items():
        o = str(old or "").strip()
        n = str(new or "").strip()
        if o and o != n:
            rules.append((re.compile(rf"\b{re.escape(o)}\b", re.IGNORECASE), n))
    if not rules:
        return [dict(c) for c in cues], 0

    changed = 0
    out: list[dict[str, Any]] = []
    for c in cues:
        item = dict(c)
        txt = str(item.get("text") or "")
        new_txt = txt
        for pat, rep in rules:
            new_txt = pat.sub(rep, new_txt)
        if new_txt != txt:
            changed += 1
            item["text"] = new_txt
        out.append(item)
    return out, changed


def cues_to_srt(cues: list[dict[str, Any]]) -> str:
    """Format caption cues as a standard SubRip (.srt) string."""
    def _ts(sec: float) -> str:
        ms_total = max(0, int(round(float(sec) * 1000)))
        h, rem = divmod(ms_total, 3600_000)
        m, rem = divmod(rem, 60_000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    blocks: list[str] = []
    for idx, c in enumerate(cues, start=1):
        blocks.append(f"{idx}\n{_ts(c['start'])} --> {_ts(c['end'])}\n{c['text']}\n")
    return "\n".join(blocks).strip() + ("\n" if blocks else "")


def transcribe_words_local(audio_path: Path, model_size: str = "small") -> tuple[list[dict[str, Any]], str]:
    """Extract word-level timestamps locally via `faster-whisper` or `openai-whisper` (PyTorch/CUDA + ffmpeg)."""
    if not audio_path.is_file():
        return [], "audio file not found"
    # 1. Try faster-whisper (if installed and its PyAV DLL is permitted by OS policy)
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-not-found,unused-ignore]
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(audio_path), word_timestamps=True)
        words: list[dict[str, Any]] = []
        for seg in segments:
            for w in getattr(seg, "words", None) or []:
                txt = str(getattr(w, "word", "") or "").strip()
                if txt:
                    words.append({
                        "word": txt,
                        "start": round(float(getattr(w, "start", 0.0)), 3),
                        "end": round(float(getattr(w, "end", 0.0)), 3),
                    })
        if words:
            return words, "faster-whisper"
    except Exception as e:
        log.debug("faster-whisper unavailable (%s); trying openai-whisper", e)

    # 2. Fallback to openai-whisper (uses PyTorch CUDA/CPU + ffmpeg.exe directly, zero PyAV dependency)
    try:
        import torch  # type: ignore[import-not-found,unused-ignore]
        import whisper  # type: ignore[import-not-found,unused-ignore]
        device = "cuda" if torch.cuda.is_available() else "cpu"
        wmodel = whisper.load_model(model_size, device=device)
        res = wmodel.transcribe(str(audio_path), word_timestamps=True)
        words = []
        for seg in res.get("segments") or []:
            for w in seg.get("words") or []:
                txt = str(w.get("word") or "").strip()
                if txt:
                    words.append({
                        "word": txt,
                        "start": round(float(w.get("start", 0.0)), 3),
                        "end": round(float(w.get("end", 0.0)), 3),
                    })
        return words, f"openai-whisper ({device})"
    except Exception as e:
        return [], f"local whisper unavailable: {e}"


def _probe_audio_duration(audio_path: Path) -> float:
    ff = shutil.which("ffprobe") or shutil.which("ffmpeg")
    if not ff or not audio_path.is_file():
        return 0.0
    if Path(ff).stem.lower() == "ffprobe":
        p = subprocess.run(
            [ff, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio_path)],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=15,
        )
        try:
            return max(0.0, float((p.stdout or "").strip()))
        except ValueError:
            return 0.0
    p = subprocess.run([ff, "-i", str(audio_path)], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=15)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", p.stderr or "")
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return 0.0


def build_audio_first_clock(
    slug: str,
    pd: Path,
    *,
    fps: int = 24,
    audio_path: Path | None = None,
    use_whisper: bool = True,
) -> dict[str, Any]:
    """Build frame-snapped Audio-First Clock cut timings + Reels safe-zone captions for a book project."""
    target_audio = audio_path
    if target_audio is None:
        for cand in (
            pd / "audio" / "mix" / "master_mix.wav",
            pd / "audio" / "mix" / "master_mix_lufs14.wav",
        ):
            if cand.is_file():
                target_audio = cand
                break

    words: list[dict[str, Any]] = []
    source_engine = "script_estimate"
    if target_audio and target_audio.is_file() and use_whisper:
        words, engine_msg = transcribe_words_local(target_audio)
        if words:
            source_engine = engine_msg

    # Fallback: build paced word timings from rendered Step 15 dialogue / screenplay + shotlist
    if not words:
        sl_path = pd / "shots" / "shotlist.json"
        dlg_lines: list[tuple[str, float]] = []
        sp_dir = pd / "screenplay"
        if sp_dir.is_dir():
            for sf in sorted(sp_dir.glob("scene-*.json")):
                try:
                    sc = json.loads(sf.read_text(encoding="utf-8")) or {}
                except Exception as e:
                    log.debug("skipping unreadable scene %s: %s", sf.name, e)
                    continue
                for el in sc.get("elements") or []:
                    if isinstance(el, dict) and el.get("type") == "dialogue" and str(el.get("text") or "").strip():
                        txt = str(el["text"]).strip()
                        est_dur = max(1.4, len(txt.split()) / 2.6)
                        dlg_lines.append((txt, est_dur))
        if not dlg_lines and sl_path.is_file():
            try:
                sl = json.loads(sl_path.read_text(encoding="utf-8")) or {}
                for sc in sl.get("scenes") or []:
                    for sh in sc.get("shots") or []:
                        if isinstance(sh, dict):
                            txt = str(sh.get("action") or sh.get("composition") or "").strip()
                            if txt:
                                dlg_lines.append((txt, float(sh.get("seconds") or 3.0)))
            except Exception as e:
                log.debug("failed reading shotlist fallback for audio_first_clock: %s", e)
        cur_t = 0.0
        for line_txt, dur in dlg_lines:
            toks = [t for t in line_txt.split() if t.strip()]
            if not toks:
                continue
            step = dur / float(len(toks))
            for tok in toks:
                words.append({"word": tok, "start": round(cur_t, 3), "end": round(cur_t + step * 0.92, 3)})
                cur_t += step
            cur_t += 0.25

    cues = segment_safe_captions(words, fps=fps)
    total_audio_dur = _probe_audio_duration(target_audio) if target_audio else (cues[-1]["end"] if cues else 0.0)
    snapped_total = snap_to_frames(total_audio_dur, fps)

    # Save clock + captions artifacts inside the project
    cap_dir = pd / "exports" / "captions"
    cap_dir.mkdir(parents=True, exist_ok=True)
    clock_json = cap_dir / "audio_first_clock.json"
    srt_path = cap_dir / "safe_captions.srt"

    payload: dict[str, Any] = {
        "status": "ok",
        "project": slug,
        "fps": int(fps),
        "engine": source_engine,
        "audio_duration": round(total_audio_dur, 3),
        "snapped_duration": snapped_total,
        "sync_drift_ms": round(abs(total_audio_dur - snapped_total) * 1000.0, 2),
        "word_count": len(words),
        "cue_count": len(cues),
        "min_caption_px": MIN_CAPTION_PX,
        "cues": cues,
        "srt_url": f"/file/{slug}/exports/captions/safe_captions.srt",
        "clock_url": f"/file/{slug}/exports/captions/audio_first_clock.json",
    }
    clock_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    srt_path.write_text(cues_to_srt(cues), encoding="utf-8")
    return payload


def measure_loudness_lufs(audio_path: Path, ffmpeg_bin: str | None = None) -> dict[str, Any]:
    """Measure integrated loudness (LUFS) and true peak (dBTP) using FFmpeg's `loudnorm` analyzer."""
    ff = ffmpeg_bin or shutil.which("ffmpeg")
    if not ff or not audio_path.is_file():
        return {"ok": False, "error": "ffmpeg or audio file unavailable"}
    cmd = [
        ff, "-hide_banner", "-i", str(audio_path),
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    raw = proc.stderr or ""
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", raw, re.DOTALL)
    if not m:
        return {"ok": False, "error": "loudnorm measurement not found in ffmpeg output"}
    try:
        data = json.loads(m.group(0))
        return {
            "ok": True,
            "integrated_lufs": float(data.get("input_i", -24.0)),
            "true_peak_db": float(data.get("input_tp", -1.0)),
            "lra": float(data.get("input_lra", 7.0)),
            "threshold": float(data.get("input_thresh", -34.0)),
            "target_offset": float(data.get("target_offset", 0.0)),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def normalize_to_lufs(
    src_audio: Path,
    dst_audio: Path,
    *,
    target_lufs: float = -14.0,
    true_peak_db: float = -1.5,
    sample_rate: int = 48000,
    ffmpeg_bin: str | None = None,
) -> dict[str, Any]:
    """Measure integrated loudness and apply exact single-gain + peak-limiter pass to hit `target_lufs` at 48 kHz."""
    ff = ffmpeg_bin or shutil.which("ffmpeg")
    if not ff or not src_audio.is_file():
        return {"ok": False, "error": "ffmpeg or source audio unavailable"}
    meas = measure_loudness_lufs(src_audio, ffmpeg_bin=ff)
    dst_audio.parent.mkdir(parents=True, exist_ok=True)
    if meas.get("ok") and meas["integrated_lufs"] > -65.0:
        gain_db = round(max(-18.0, min(24.0, float(target_lufs) - float(meas["integrated_lufs"]))), 2)
        lim = round(10.0 ** (float(true_peak_db) / 20.0), 4)
        af = f"volume={gain_db}dB,alimiter=limit={lim}:level=disabled,aresample={sample_rate}"
    else:
        af = f"loudnorm=I={target_lufs}:TP={true_peak_db}:LRA=11,aresample={sample_rate}"

    cmd = [ff, "-y", "-v", "error", "-i", str(src_audio), "-af", af, "-ar", str(sample_rate), str(dst_audio)]
    proc = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=90)
    if proc.returncode != 0 or not dst_audio.is_file():
        return {"ok": False, "error": (proc.stderr or "ffmpeg normalize failed")[-250:]}
    post = measure_loudness_lufs(dst_audio, ffmpeg_bin=ff)
    return {
        "ok": True,
        "output_path": str(dst_audio),
        "target_lufs": float(target_lufs),
        "before_lufs": meas.get("integrated_lufs"),
        "after_lufs": post.get("integrated_lufs"),
        "after_true_peak_db": post.get("true_peak_db"),
        "sample_rate": sample_rate,
    }


def cues_to_ass(cues: list[dict[str, Any]], *, is_vertical: bool = True) -> str:
    """Build an ASS subtitle script locked inside the Reels/Shorts safe zone (9:16) or cinema lower-third (16:9)."""
    play_x, play_y = (1080, 1920) if is_vertical else (1920, 1080)
    # Enforce >= 56 px readable bold phone font on 1080x1920 and lock above bottom UI + clear of right action column
    font_px = max(MIN_CAPTION_PX, int((cues[0].get("font_px") if cues else 62) or 62)) if is_vertical else 58
    margin_l = 76 if is_vertical else 120
    margin_r = 200 if is_vertical else 120
    margin_v = 520 if is_vertical else 95

    def _ass_ts(sec: float) -> str:
        cs_total = max(0, int(round(float(sec) * 100)))
        h, rem = divmod(cs_total, 360_000)
        m, rem = divmod(rem, 6_000)
        s, cs = divmod(rem, 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_x}\n"
        f"PlayResY: {play_y}\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: SafeCap,Arial,{font_px},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,4,2,2,{margin_l},{margin_r},{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines: list[str] = [header]
    for c in cues:
        txt = str(c.get("text") or "").replace("\n", "\\N").replace("{", "(").replace("}", ")").strip()
        if not txt:
            continue
        st = _ass_ts(float(c.get("start", 0.0)))
        en = _ass_ts(float(c.get("end", 0.5)))
        lines.append(f"Dialogue: 0,{st},{en},SafeCap,,0,0,0,,{txt}\n")
    return "".join(lines)


def burn_safe_captions_mp4(
    src_mp4: Path,
    dst_mp4: Path,
    cues: list[dict[str, Any]],
    *,
    is_vertical: bool = True,
    ffmpeg_bin: str | None = None,
) -> dict[str, Any]:
    """Burn safe-zone ASS captions directly into an MP4 video via FFmpeg (Windows-safe relative ASS path)."""
    ff = ffmpeg_bin or shutil.which("ffmpeg")
    if not ff or not src_mp4.is_file():
        return {"ok": False, "error": "ffmpeg or source MP4 unavailable"}
    if not cues:
        return {"ok": False, "error": "no caption cues to burn in"}

    dst_mp4.parent.mkdir(parents=True, exist_ok=True)
    ass_name = "_safe_captions_burn.ass"
    ass_path = dst_mp4.parent / ass_name
    ass_path.write_text(cues_to_ass(cues, is_vertical=is_vertical), encoding="utf-8")

    # Run ffmpeg with cwd=dst_mp4.parent so `ass=_safe_captions_burn.ass` has zero Windows drive-colon escaping issues
    cmd = [
        ff, "-y", "-v", "error",
        "-i", str(src_mp4.resolve()),
        "-vf", f"ass={ass_name}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(dst_mp4.resolve()),
    ]
    proc = subprocess.run(cmd, cwd=str(dst_mp4.parent), capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=180)
    ass_path.unlink(missing_ok=True)
    if proc.returncode != 0 or not dst_mp4.is_file() or dst_mp4.stat().st_size == 0:
        return {"ok": False, "error": (proc.stderr or "ffmpeg caption burn-in failed")[-250:]}
    return {"ok": True, "output_path": str(dst_mp4), "cues_burned": len(cues), "is_vertical": is_vertical}
