#!/usr/bin/env python3
# Changelog: 2026-11-10 `voices` (free list of your voices, previews) and `sample` (one short sample, asks first).
# Changelog: 2026-11-09 Library v2 (agentchad.io). Voiceovers come from ElevenLabs directly, never from Starpop.
"""One continuous ElevenLabs voiceover with word timings, straight into an ad folder.

    elevenlabs_tts.py voices [--previews DIR]               # free: your voices (name, id, labels), characters left;
                                                            #   --previews saves ElevenLabs' own free preview clips
    elevenlabs_tts.py sample VOICE_ID OUT.mp3 "text" [--yes]  # one short sample in your ad language (~150 characters)
    elevenlabs_tts.py check AD_DIR VOICE_ID                 # free: is the voice usable with your key? characters left?
    elevenlabs_tts.py make  AD_DIR VOICE_ID [TAKE] [--yes]  # all voice.lines as ONE take (costs ElevenLabs characters)

Writes AD_DIR/voice/takeN.mp3 and AD_DIR/voice/takeN_transcript.json (word timings from ElevenLabs'
with-timestamps endpoint), ready for `adtool.py words AD_DIR AD_DIR/voice/takeN_transcript.json N`.
Settings come from ad.json "voice": model (default eleven_v4), language_code, stability, similarity_boost, speed.

The API key is read from the environment variable ELEVENLABS_API_KEY, or from the line
`ELEVENLABS_API_KEY=...` in ~/.config/elevenlabs/.env. It is kept in memory and never printed.
Standard library only: any python3 runs it, e.g. python3 -I -B scripts/elevenlabs_tts.py voices
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILE = Path.home() / ".config" / "elevenlabs" / ".env"
API = "https://api.elevenlabs.io/v1"


def key():
    k = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not k and ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ELEVENLABS_API_KEY="):
                k = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not k:
        sys.exit(f"No ElevenLabs key. Put ELEVENLABS_API_KEY=<your key> in {ENV_FILE} (or export it) and run again.")
    return k


def call(path, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body else None,
                                 headers={"xi-api-key": key(), "Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=180).read())
    except urllib.error.HTTPError as e:
        sys.exit(f"ElevenLabs HTTP {e.code}: {e.read().decode()[:400]}")


def words_from_alignment(al):
    """Character alignment -> [{word, start, end}] in seconds."""
    chars, starts, ends = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    out, cur, a, prev_end = [], "", None, None
    for c, s, e in zip(chars, starts, ends):
        if c.isspace():
            if cur:
                out.append({"word": cur, "start": a, "end": prev_end})
            cur, a = "", None
            continue
        if not cur:
            a = s
        cur += c
        prev_end = e
    if cur:
        out.append({"word": cur, "start": a, "end": prev_end})
    return out


def check(ad_dir, voice_id, *_):
    v = call(f"/voices/{voice_id}")
    sub = call("/user/subscription")
    left = sub["character_limit"] - sub["character_count"]
    print(f"voice: {v.get('name')} ({v.get('category')}) - usable")
    print(f"characters left this month: {left:,}")


def voices(*args):
    """Free: list the voices on your account. Prints names, ids and labels only (never the key)."""
    out_dir = Path(args[args.index("--previews") + 1]).expanduser() if "--previews" in args else None
    res = call("/voices").get("voices", [])
    sub = call("/user/subscription")
    print(f"{len(res)} voices. Characters left this month: {sub['character_limit'] - sub['character_count']:,}")
    print("name | voice id | category | labels")
    for v in res:
        labels = ", ".join(f"{k}: {x}" for k, x in (v.get("labels") or {}).items())
        print(f"{v.get('name')} | {v.get('voice_id')} | {v.get('category')} | {labels}")
        if out_dir and v.get("preview_url"):
            out_dir.mkdir(parents=True, exist_ok=True)
            safe = "".join(c if c.isalnum() else "_" for c in v.get("name", "voice"))[:40]
            dst = out_dir / f"{safe}_{v['voice_id'][:8]}_preview.mp3"
            if not dst.exists():
                dst.write_bytes(urllib.request.urlopen(v["preview_url"], timeout=60).read())
    if out_dir:
        print(f"free preview clips saved in {out_dir} (English demo lines; listen yourself, Claude never plays audio)")


def sample(voice_id, out, text, *args):
    """One short sample in your own language, for the owner to approve before a voice goes on an ad."""
    if "--yes" not in args:
        sys.exit(f"Not run. This sample uses {len(text)} ElevenLabs characters. Ask the user; after a yes, add --yes.")
    body = {"text": text, "model_id": "eleven_v4"}   # same model as `make`
    req = urllib.request.Request(f"{API}/text-to-speech/{voice_id}?output_format=mp3_44100_128",
                                 data=json.dumps(body).encode(),
                                 headers={"xi-api-key": key(), "Content-Type": "application/json"})
    try:
        audio = urllib.request.urlopen(req, timeout=120).read()
    except urllib.error.HTTPError as e:
        sys.exit(f"ElevenLabs HTTP {e.code}: {e.read().decode()[:400]}")
    Path(out).expanduser().parent.mkdir(parents=True, exist_ok=True)
    Path(out).expanduser().write_bytes(audio)
    print(f"wrote {out} ({len(text)} characters). Listen yourself; Claude never plays audio.")


def make(ad_dir, voice_id, *args):
    root = Path(ad_dir)
    cfg = json.loads((root / "ad.json").read_text(encoding="utf-8"))
    v = cfg["voice"]
    take = next((int(a) for a in args if a.isdigit()), 1)
    text = "\n\n".join(l.strip() for l in v["lines"] if l.strip())
    if "--yes" not in args:
        sys.exit(f"Not run. Take {take} uses about {len(text)} ElevenLabs characters (monthly quota). "
                 "Show this to the user; after a clear yes, run again with --yes.")
    body = {"text": text, "model_id": v.get("model", "eleven_v4"),
            "voice_settings": {"stability": v.get("stability", 0.5), "similarity_boost": v.get("similarity_boost", 0.75),
                               "speed": v.get("speed", 1.0)}}
    if v.get("language_code"):
        body["language_code"] = v["language_code"]
    r = call(f"/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_192", body)
    d = root / "voice"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"take{take}.mp3").write_bytes(base64.b64decode(r["audio_base64"]))
    words = words_from_alignment(r.get("normalized_alignment") or r["alignment"])
    (d / f"take{take}_transcript.json").write_text(json.dumps({"words": words}, ensure_ascii=False, indent=1),
                                                    encoding="utf-8")
    print(f"wrote voice/take{take}.mp3 and voice/take{take}_transcript.json ({len(words)} words, "
          f"ends {words[-1]['end']:.2f} s)")


STEPS = {"check": check, "make": make, "voices": voices, "sample": sample}
MIN_ARGS = {"check": 2, "make": 2, "voices": 0, "sample": 3}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in STEPS or len(sys.argv) - 2 < MIN_ARGS[sys.argv[1]]:
        sys.exit(__doc__)
    STEPS[sys.argv[1]](*sys.argv[2:])
