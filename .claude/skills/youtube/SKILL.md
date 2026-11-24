---
name: youtube
description: Get a finished Studio film ready for YouTube, and publish it if the user asks. Makes the YouTube export (1080p, 4K or a vertical Short) with subtitle tracks, then writes the title, description, chapters, tags and thumbnail, checks them, and uploads only after the user says yes. Use when the user says "put this on YouTube", "upload my film", "YouTube title/description/thumbnail", "make a Short", "youtube agent", or /youtube.
---

# YouTube agent

Takes one film from `projects/books/<book>/films/` to a YouTube-ready package, and uploads it if the user asks.
Each step leads to the next. Keep messages short.

## Rules
- **Never upload, publish, change a live video or reply to comments without a clear "yes" from the user for that action.**
  Uploads are **private** unless the user names another visibility.
- Works on Windows and macOS: use `uv run ...` and forward-slash paths. Nothing here is macOS-only.
- Do not write the word "bible" anywhere unless the user typed it. Say "continuity book".
- Results are a checklist reading. Never promise views.

## Step 1: Pick the film
- List `projects/books/*/films/*.mp4`. If more than one fits, recommend the newest and go ahead with it unless the user picks another.
- Note the matching `.srt` (captions) and `projects/books/<book>/credits.json` if they exist.

## Step 2: Export
Run from the project root:
```
uv run --with imageio-ffmpeg python scripts/export_film.py --project <book> --film <film>.mp4 --preset youtube_1080p [--languages es,fr] [--title "<title>"]
```
- `youtube_4k` only if the user wants 4K. Say plainly that clips smaller than 4K are just scaled up (upscale them first for real detail).
- `vertical_short` for a Short (9:16 centre crop). Keep Shorts at 60 s or less; if the film is longer, suggest a scene for the Short.
- Result: `films/<name>_<preset>.mp4` plus its `.srt` files. If it fails, show the error and stop.

## Step 3: Write the metadata
Write `films/<name>_youtube.md` with:
- **Title**: 3 choices, 60 characters or fewer, the best one first.
- **Description**: two hook lines first, then the story in a few lines, then credits. Build the credits from `credits.json`
  and `scripts/credits.py` (`lines()`), which includes the "Made with" lines for the AI models used.
- **Chapters**: from the film's scenes or `.srt` timing. The first one is `0:00`, at least 3 chapters, each 10 s or longer.
- **Tags**: 10 to 15, 500 characters in all.
- **Altered or synthetic content**: say **Yes** (the film is AI-made). The user ticks this when uploading.
- **Made for kids**: ask the user. Never guess this.
- **Rights**: copy the `rights` note from `credits.json`. Flag any music or text that is not public domain or the user's own.

Use the yt-* tools for the checks (on Windows type `python` instead of `python3`):
- Chapters: `python3 .claude/skills/yt-chapters/chapters.py films/<name>.srt --target 8`, then retitle every line.
- Title + thumbnail text: put the 3 titles in a file and run `python3 .claude/skills/yt-package/title.py <file> --thumb "<words>"`.
- Short: find the moment with `/yt-shorts`; score its first line with `.claude/skills/yt-script/hookscore.py --hook "..."`.
- Description and tags: follow `/yt-seo`.

## Step 4: Thumbnail
- Pick 3 strong frames (faces, high contrast, not blurred) with ffmpeg, saved as 1280x720 JPGs under 2 MB:
  `uv run --with imageio-ffmpeg python -c "import imageio_ffmpeg,subprocess,sys;subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-ss',sys.argv[1],'-i',sys.argv[2],'-frames:v','1','-vf','scale=1280:720','-y',sys.argv[3]],check=True)" <seconds> <film> films/<name>_thumb1.jpg`
- Recommend one, with the title text (3 to 5 words) to put on it.

## Step 5: Check (optional, if the tools are connected)
Use whatever is connected; skip a step if its tool is not there, and say so in one line.
- **vidIQ** (`mcp__claude_ai_vidIQ__*`): `vidiq_keyword_research` for tags, `vidiq_score_title`, `vidiq_score_thumbnail`,
  `vidiq_generate_video_chapters`. Update `_youtube.md` with what helps.
- **Video Hook Check** (`mcp__claude_ai_Video_Hook_Check__*`): for a Short, `upload_video` then `check_hook`; add its three rewritten openings to the notes.

## Step 6: Gate
Show the user, in a short list: the export file, the chosen title, the thumbnail, and anything flagged.
Ask: **"Upload now (private), or keep the files?"** Recommend keeping it private first.

## Step 7: Upload (only after "yes")
- With vidIQ connected: `vidiq_video_upload` (private), then `vidiq_update_video` with the title, description, chapters and tags,
  then `vidiq_update_video_thumbnail`. If the channel is not linked, run `vidiq_connect_youtube_channel` and wait for the user.
- Without vidIQ: tell the user to upload at studio.youtube.com and paste the fields from `_youtube.md`.
- Finish with the video link (or the files list) and what is still left for the user to do (for example, ticking "altered content", turning on public).
