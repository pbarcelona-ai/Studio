import csv
import subprocess
import sys
import webbrowser
from prompts import SERVICES

# Usage: python3 web_batch.py [project] [all_shots.csv | all_chapters.csv]      (default project: adam_eve)
PROJECT = sys.argv[1] if len(sys.argv) > 1 else "adam_eve"
import layout
CSV = layout.project_dir(PROJECT) / (sys.argv[2] if len(sys.argv) > 2 else "all_shots.csv")
PROGRESS = f".batch_progress_{PROJECT}_{CSV.stem}"   # separate resume point per project and CSV

with open(CSV) as f:
    shots = list(csv.DictReader(f))

try:
    start_idx = int(open(PROGRESS).read().strip())
except (OSError, ValueError):
    start_idx = 0

print(f"Total shots: {len(shots)} | Resuming from: {start_idx + 1}")

service_idx = 0
shot_idx = start_idx

while shot_idx < len(shots):
    service_name, daily_limit, url = SERVICES[service_idx % len(SERVICES)]
    chunk_end = min(shot_idx + daily_limit, len(shots))

    print(f"\n{'='*50}\n🎬 {service_name.upper()}: shots {shot_idx+1}–{chunk_end}\n   {url}\n{'='*50}")
    webbrowser.open(url)

    for i in range(shot_idx, chunk_end):
        shot = shots[i]
        prompt = shot["prompt"]
        print(f"\n--- Shot {i+1}/{len(shots)} | {shot['chapter']} shot {shot['shot']} ---")
        print(prompt[:300] + ("..." if len(prompt) > 300 else ""))
        subprocess.run(["pbcopy"], input=prompt.encode())
        print("📋 Copied!")
        input("   → Paste, generate, download, press Enter...")
        with open(PROGRESS, "w") as f:
            f.write(str(i + 1))

    shot_idx = chunk_end
    service_idx += 1
    if shot_idx < len(shots):
        input("\n⏸️  Daily limit. Press Enter for next service...")

print("\n✅ ALL DONE!")
