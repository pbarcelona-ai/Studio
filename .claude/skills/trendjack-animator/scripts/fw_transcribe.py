#!/usr/bin/env python3
# Changelog: 2026-11-10 New. Local transcript with word times via faster-whisper (the shared ~/.venvs/agentchad python).
"""Transcribe one video or audio file locally with faster-whisper, word times included.

Usage: <python with faster-whisper> -I -B fw_transcribe.py <file> <out folder> [--model small] [--language xx]
Writes <out>/<file stem>.json (same shape as the whisper command: text, language, segments with words) and
<out>/<file stem>.txt. The model downloads once on first use (small: about 500 MB, a few minutes) and is cached.
prep_refs.py calls this with AGENTCHAD_PY (default ~/.venvs/agentchad/bin/python3). Free, runs on your computer.
"""
import argparse
import json
import sys
from pathlib import Path

try:
    from faster_whisper import WhisperModel
except ImportError:
    sys.exit("faster-whisper is not installed in this python. Install the shared venv: "
             "python3.12 -m venv ~/.venvs/agentchad && ~/.venvs/agentchad/bin/pip install numpy scipy soundfile pillow faster-whisper 'av<19' yt-dlp")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--model", default="small")
    ap.add_argument("--language", default=None)
    a = ap.parse_args()
    model = WhisperModel(a.model, device="cpu", compute_type="int8")
    segs, info = model.transcribe(str(a.file), language=a.language, word_timestamps=True, vad_filter=False)
    out = {"text": "", "language": info.language, "segments": []}
    lines = []
    for s in segs:
        words = [{"word": w.word, "start": round(w.start, 3), "end": round(w.end, 3),
                  "probability": round(w.probability, 3)} for w in (s.words or [])]
        out["segments"].append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text, "words": words})
        lines.append(s.text.strip())
    out["text"] = " ".join(lines)
    a.out.mkdir(parents=True, exist_ok=True)
    stem = a.file.stem
    (a.out / f"{stem}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (a.out / f"{stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {stem}.json ({sum(len(s['words']) for s in out['segments'])} words, language {info.language})")


if __name__ == "__main__":
    main()
