from pathlib import Path

downloads = Path.home() / "Downloads"
import sys
project = sys.argv[1] if len(sys.argv) > 1 else "adam_eve"      # python3 rename_sequential.py [project]
import layout
videos = layout.project_dir(project) / "videos"
videos.mkdir(exist_ok=True)

# Continue numbering after any shots already collected; oldest download first = story order.
count = len(list(videos.glob("shot-*.mp4"))) + 1
start = count
for vid in sorted(downloads.glob("*.mp4"), key=lambda p: p.stat().st_mtime):
    if "test" in vid.name.lower():
        continue
    new_name = f"shot-{count:04d}.mp4"
    vid.rename(videos / new_name)
    print(f"{vid.name} → {new_name}")
    count += 1

print(f"\n✅ {count - start} videos moved (shot-{start:04d} … shot-{count - 1:04d}) into {videos}")
