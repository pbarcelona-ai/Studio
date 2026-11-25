#!/usr/bin/env python3
"""TTS audio audit & word-level timing extraction for Pistachio's Studio.

  python3 scripts/tts_audit.py <project> [--folder kokoro] [--max-wer 0.35] [--no-stt]

Audits generated narration WAV files against the expected script lines:
  - Measures true WAV duration, peak level, RMS loudness, clipping, silence, and leading/trailing silence (pure stdlib)
  - Optionally runs local `faster-whisper` with `word_timestamps=True` (when installed, or via an injectable transcriber)
    to compute Word Error Rate (WER) against the expected text and extract word-level timestamps
  - Writes `audio/tts_audit.json` and can generate tight word-timed `.srt` subtitles or sync EDL voice durations
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import struct
import sys
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edl  # noqa: E402
import layout  # noqa: E402
import shot_list  # noqa: E402
import sound_design  # noqa: E402

# Transcriber(wav_path) -> {"text": str, "words": [{"word": str, "start": float, "end": float, "prob": float}]}
WordTranscriber = Callable[[Path], dict[str, Any]]
_WORD_RE = re.compile(r"[a-z0-9']+")


def normalize_words(text: str) -> list[str]:
    """Lowercase alphanumeric tokens for punctuation-insensitive WER comparison."""
    return _WORD_RE.findall(text.lower())


def word_error_rate(expected: str, actual: str) -> float:
    """Token-level Levenshtein WER between expected script text and STT output (0.0 = exact match)."""
    ref = normalize_words(expected)
    hyp = normalize_words(actual)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r_tok in enumerate(ref, 1):
        curr = [i] + [0] * len(hyp)
        for j, h_tok in enumerate(hyp, 1):
            cost = 0 if r_tok == h_tok else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return round(prev[-1] / len(ref), 4)


def wav_stats(wav_path: Path, silence_thresh: float = 0.01) -> dict[str, Any]:
    """Pure-stdlib 16-bit PCM WAV inspection: duration, peak, RMS, clipping, silence, and head/tail silence."""
    with wave.open(str(wav_path), "rb") as wf:
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        sr = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)
    duration = nframes / sr if sr > 0 else 0.0
    if sw != 2 or nframes == 0 or ch == 0:
        return {"duration": round(duration, 3), "sample_rate": sr, "channels": ch,
                "peak": 0.0, "rms": 0.0, "clipped": False, "silent": True,
                "leading_silence": round(duration, 3), "trailing_silence": round(duration, 3)}
    total_samples = nframes * ch
    samples = struct.unpack(f"<{total_samples}h", raw[: total_samples * 2])
    peak_i = 0
    sq_sum = 0.0
    for s in samples:
        a = abs(s)
        if a > peak_i:
            peak_i = a
        sq_sum += s * s
    peak = peak_i / 32768.0
    rms = math.sqrt(sq_sum / total_samples) / 32768.0

    # Measure head/tail silence in 20 ms windows
    win = max(1, int(sr * 0.02)) * ch
    thresh_i = int(silence_thresh * 32768)
    first_active = None
    last_active = None
    for idx in range(0, total_samples, win):
        chunk = samples[idx: idx + win]
        if any(abs(s) >= thresh_i for s in chunk):
            frame_pos = (idx // ch) / sr
            if first_active is None:
                first_active = frame_pos
            last_active = min(duration, ((idx + len(chunk)) // ch) / sr)
    lead = duration if first_active is None else first_active
    trail = duration if last_active is None else max(0.0, duration - last_active)
    return {
        "duration": round(duration, 3),
        "sample_rate": sr,
        "channels": ch,
        "peak": round(peak, 4),
        "rms": round(rms, 4),
        "clipped": peak >= 0.995,
        "silent": rms < 0.002,
        "leading_silence": round(lead, 3),
        "trailing_silence": round(trail, 3),
    }


def whisper_word_transcriber(model_size: str = "small", device: str = "cpu", compute_type: str = "int8") -> WordTranscriber | None:
    """Local faster-whisper transcriber returning word-level timestamps, or None if faster-whisper is not installed."""
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        return None
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def run(wav_path: Path) -> dict[str, Any]:
        segs, _ = model.transcribe(str(wav_path), word_timestamps=True)
        texts: list[str] = []
        words: list[dict[str, Any]] = []
        for seg in segs:
            if seg.text:
                texts.append(seg.text.strip())
            for w in getattr(seg, "words", None) or []:
                tok = str(getattr(w, "word", "")).strip()
                if tok:
                    words.append({
                        "word": tok,
                        "start": round(float(getattr(w, "start", 0.0)), 3),
                        "end": round(float(getattr(w, "end", 0.0)), 3),
                        "prob": round(float(getattr(w, "probability", 1.0)), 3),
                    })
        return {"text": " ".join(texts).strip(), "words": words}

    return run


def audit_clip(wav_path: Path, expected_text: str, transcriber: WordTranscriber | None = None, max_wer: float = 0.35) -> dict[str, Any]:
    """Audit a single TTS WAV clip for audio health and (when `transcriber` is given) transcript accuracy + word timings."""
    if not wav_path.is_file():
        return {"file": str(wav_path), "exists": False, "ok": False, "issues": ["missing wav file"],
                "expected": expected_text, "transcript": "", "wer": None, "words": [], "stats": {}}
    stats = wav_stats(wav_path)
    issues: list[str] = []
    if stats["duration"] <= 0.05:
        issues.append("audio is empty or near-zero length")
    if stats["silent"]:
        issues.append("audio is silent")
    if stats["clipped"]:
        issues.append(f"audio is clipping (peak {stats['peak']:.3f})")

    transcript = ""
    words: list[dict[str, Any]] = []
    wer: float | None = None
    if transcriber is not None and not stats["silent"]:
        res = transcriber(wav_path)
        transcript = str(res.get("text") or "").strip()
        words = list(res.get("words") or [])
        if expected_text.strip():
            wer = word_error_rate(expected_text, transcript)
            if wer > max_wer:
                issues.append(f"transcript mismatch (WER {wer:.2f} > {max_wer:.2f})")

    return {
        "file": str(wav_path),
        "exists": True,
        "ok": not issues,
        "issues": issues,
        "expected": expected_text,
        "transcript": transcript,
        "wer": wer,
        "words": words,
        "stats": stats,
    }


def _expected_rows(pdir: Path) -> list[tuple[int, str]]:
    """[(1-based row, expected narration text)] from audio_shots.csv, or sound_design + shot_list."""
    csv_path = pdir / "audio_shots.csv"
    if csv_path.is_file():
        rows = []
        with open(csv_path, newline="", encoding="utf-8") as fh:
            for i, r in enumerate(csv.DictReader(fh), 1):
                txt = (r.get("narration") or "").strip()
                if not txt and r.get("lines_json"):
                    try:
                        lines = json.loads(r["lines_json"])
                        txt = " ".join(str(x.get("text", "")).strip() for x in lines if isinstance(x, dict)).strip()
                    except ValueError:
                        txt = ""
                if txt:
                    rows.append((i, txt))
        if rows:
            return rows
    plan = sound_design.load(pdir)
    sl = shot_list.load(pdir)
    rows = []
    row = 0
    for sc in sl.get("scenes", []):
        for s in sc["shots"]:
            row += 1
            txt = " ".join(x["text"] for x in plan.get("lines", []) if x["scene"] == sc["id"] and x["shot"] == s["n"]).strip()
            if txt:
                rows.append((row, txt))
    return rows


def audit_book(pdir: Path, transcriber: WordTranscriber | None = None, folder: str = "kokoro",
               max_wer: float = 0.35, write_report: bool = True) -> dict[str, Any]:
    """Audit every expected narration WAV for a book project and optionally write `audio/tts_audit.json`."""
    rows = _expected_rows(pdir)
    aud_dir = pdir / "audio" / folder
    clips: list[dict[str, Any]] = []
    for row, expected in rows:
        wav = aud_dir / f"narration-{row:04d}.wav"
        rep = audit_clip(wav, expected, transcriber=transcriber, max_wer=max_wer)
        clips.append({"row": row, **rep})
    flagged = [c for c in clips if not c["ok"]]
    report = {
        "folder": folder,
        "checked": len(clips),
        "passed": len(clips) - len(flagged),
        "flagged": len(flagged),
        "ok": len(flagged) == 0,
        "clips": clips,
    }
    if write_report:
        out = pdir / "audio" / "tts_audit.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def sync_voice_durations(cut: dict[str, Any], audit_report: dict[str, Any]) -> int:
    """Update voice item durations in an EDL cut from measured WAV durations instead of word-count estimates."""
    by_row = {int(c["row"]): c["stats"].get("duration") for c in audit_report.get("clips", []) if c.get("exists") and c.get("stats")}
    changed = 0
    for a in cut.get("tracks", {}).get("voice", []):
        dur = by_row.get(int(a["ref"]))
        if dur and dur > 0 and abs(float(a["seconds"]) - float(dur)) > 0.05:
            a["seconds"] = round(float(dur), 3)
            changed += 1
    return changed


def word_srt(cut: dict[str, Any], audit_report: dict[str, Any], max_words_per_cue: int = 8) -> str:
    """Build tight phrase-grouped `.srt` subtitles using word-level timestamps from `audit_report` (falls back to clip bounds)."""
    tl = edl.timeline(cut)
    by_row = {int(c["row"]): c for c in audit_report.get("clips", [])}
    out: list[str] = []
    idx = 0
    for a in tl["voice"]:
        clip = by_row.get(int(a["ref"]))
        if not clip:
            continue
        words = clip.get("words") or []
        if words:
            for lo in range(0, len(words), max(1, max_words_per_cue)):
                chunk = words[lo: lo + max(1, max_words_per_cue)]
                t0 = a["start"] + float(chunk[0]["start"])
                t1 = min(a["end"], a["start"] + float(chunk[-1]["end"]))
                if t1 <= t0:
                    t1 = t0 + 0.2
                txt = " ".join(str(w["word"]).strip() for w in chunk if str(w.get("word", "")).strip())
                if txt:
                    idx += 1
                    out.append(f"{idx}\n{edl._t(t0)} --> {edl._t(t1)}\n{txt}\n")
        elif clip.get("expected"):
            idx += 1
            out.append(f"{idx}\n{edl._t(a['start'])} --> {edl._t(a['end'])}\n{clip['expected']}\n")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "TTS audit")
    ap.add_argument("project")
    ap.add_argument("--folder", default="kokoro")
    ap.add_argument("--max-wer", type=float, default=0.35)
    ap.add_argument("--no-stt", action="store_true", help="Skip Whisper STT check; inspect WAV health and duration only")
    a = ap.parse_args(argv)
    pdir = layout.project_dir(a.project, "book")
    transcriber = None if a.no_stt else whisper_word_transcriber()
    rep = audit_book(pdir, transcriber=transcriber, folder=a.folder, max_wer=a.max_wer)
    print(f"TTS audit ({a.folder}): {rep['passed']}/{rep['checked']} passed, {rep['flagged']} flagged")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
