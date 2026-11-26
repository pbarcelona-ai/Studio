#!/usr/bin/env python3
# Changelog: 2026-11-22: default rate 1.25 credits/s (Omni Flash 1.2 at 1080p).
# Library v2, 2026-11-12 - new: length and cast gate before any plan (same file in reality-drama-engine, chad-swipe
# and trendjack-animator). From a buyer's first run: a 7-minute, 8-person reference went through skills built for
# 15-45 s and 1-3 people, on an ambiguous "yes".
"""Length and cast gate: run it BEFORE planning a clone. Free and local (ffprobe, Python standard library).

Usage:
  python3 -I -B plan_gate.py <reference.mp4> --people N [--rate 1.25] [--still 1]
  python3 -I -B plan_gate.py --seconds 434 --people 8

  --people  speaking or featured people in the reference (count them on the frame grid)
  --rate    credits per second of generated video (default 1.25: Omni Flash 1.2 at 1080p on Starpop)
  --still   credits per still (default 1)

Answers (exit code):
  GO    (0)  up to 90 s and up to 4 people: plan as usual (over 45 s: one hook first, see the skill's long-ad notes)
  STOP  (2)  over 90 s or more than 4 people. Claude stops and offers, in this order:
             1. a 15-45 s cut-down of the reference first (the hook, the turn, the payoff; 1-3 people), or
             2. long-ad mode, which needs the user to type the exact line this script prints, with the cost in it.
             "yes", "go", "do everything", "accept everything" or "make the whole video" are NOT that answer.
"""
import json
import subprocess
import sys

MAX_SECONDS, MAX_PEOPLE, TESTED = 90, 4, 45


def seconds_of(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
                       capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"cannot read {path}: {p.stderr.strip()[:200]}")
    return float(json.loads(p.stdout)["format"]["duration"])


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(argv) > 1 else 1
    opts = {"--people": None, "--rate": "1.25", "--still": "1", "--seconds": None}
    ref, i = None, 1
    while i < len(argv):
        if argv[i] in opts and i + 1 < len(argv):
            opts[argv[i]] = argv[i + 1]
            i += 2
        else:
            ref, i = argv[i], i + 1
    if opts["--people"] is None:
        sys.exit("give --people N (speaking or featured people in the reference)")
    secs = float(opts["--seconds"]) if opts["--seconds"] else seconds_of(ref) if ref else sys.exit("give a video or --seconds")
    people, rate, still = int(opts["--people"]), float(opts["--rate"]), float(opts["--still"])
    shots = max(1, round(secs / 2.5))
    video_cr = secs * rate * 1.15
    still_cr = (people + shots) * still * 1.15
    total = video_cr + still_cr
    print(f"reference {secs:.0f} s, {people} people; tested range: 15-{TESTED} s and 1-3 people")
    print(f"rough cost of one full-length version: ~{total:.0f} credits (video ~{video_cr:.0f} + stills ~{still_cr:.0f}, "
          f"15 % retakes included; estimate_generation gives the real number)")
    reasons = []
    if secs > MAX_SECONDS:
        reasons.append(f"{secs:.0f} s is over {MAX_SECONDS} s")
    if people > MAX_PEOPLE:
        reasons.append(f"{people} people is over {MAX_PEOPLE}: faces drift between scenes and every extra person "
                       "needs its own approved photo and voice")
    if not reasons:
        if secs > TESTED:
            print(f"GO, with care: over {TESTED} s. One hook first; scene plan; every person approved once.")
        else:
            print("GO")
        return 0
    print("STOP: " + "; ".join(reasons) + ".")
    print("Offer first: a 15-45 s cut-down of this reference (its hook, the turn and the payoff, 1-3 people). "
          "It shows whether the idea works for a fraction of the cost.")
    print(f"Long-ad mode only if the user types this line back exactly: "
          f"\"yes, long mode, about {total:.0f} credits\"")
    print("Then: one scene as a paid pilot, the plates approved, and the rest only after the pilot is approved.")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
