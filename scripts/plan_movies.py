#!/usr/bin/env python3
"""Plan movies for a project from its CSVs: python3 plan_movies.py <project> [--minutes 10]

Writes projects/<project>/movies.json. Each movie is about --minutes long and ends at the end of a chapter.
Length is estimated per clip as max(4 s clip, narration length), the same as the 'stretch' mix mode.
"""
import argparse
from bookkit import build_movies, project_dir

ap = argparse.ArgumentParser()
ap.add_argument("project")
ap.add_argument("--minutes", type=float, default=10.0)
args = ap.parse_args()
plan = build_movies(project_dir(args.project), args.minutes)
for mode in ("shots", "chapters"):
    mv = plan.get(mode, [])
    print(f"{mode}: {len(mv)} movies" + (f", {min(m['est_seconds'] for m in mv) / 60:.1f}-{max(m['est_seconds'] for m in mv) / 60:.1f} min each" if mv else ""))
