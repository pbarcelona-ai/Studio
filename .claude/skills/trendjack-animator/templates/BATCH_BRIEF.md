<!-- 2026-11-12  clientRequestId 16+ characters (date suffix); stills made with the shot's plates attached. -->
<!-- 2026-11-12  Build types (full / pair / still-only), no names, fixed constraint line. -->
# <AD NAME> - production brief for one batch of shots

> Template for long ads (40+ shots) that are split across several background helpers. Before use: replace the ad
> name, the ad folder path, the look line, the hero description and the Starpop ids below with this ad's own.
> The user has already said yes to the full estimate for every shot in this batch; the helper never asks again
> and never spends outside the list.

You produce stills and animated clips for a list of shots of an animated ad in the look
"<LOOK LINE FROM ad.json>", in the language <LANGUAGE>, using the Starpop MCP tools (load them with ToolSearch:
`select:mcp__starpop__create_image,mcp__starpop__create_video,mcp__starpop__wait_for_job,mcp__starpop__get_job`).

## Fixed scope (use exactly this in every Starpop call)

- organizationId `<<FILL>>`
- brandId `<<FILL>>`
- projectId `<<FILL>>`
- sessionId `<<FILL>>`
- productRef null, folderId null

## Inputs

- Your shot list: `batches/<batch>.json` in the ad folder `<AD FOLDER>` (the full path of this ad's project folder).
  Each shot has `id`, `still` (the full image prompt), `refs` (names), `ref_ids` (the `image:` references in the
  same order, attach them in that order), `motion` (the camera + action for the clip), `build` and optionally
  `clip_model`.
- `build` (from the cut grid): `full` = still + clip; `pair1` = still + one clip whose `motion` holds two timed shots
  (that clip also serves the next shot); `pair2` = nothing to make (it uses the pair1 clip); `still` = still only, no
  clip (the push is added in the edit); `long` = still + clip `<id>_a`, then clip `<id>_b` with firstFrame = the
  last frame of `<id>_a` (extract it with ffmpeg, upload it) continuing the action. Never make more than the build
  asks for.
- Scene base stills are made before the batches; for a later shot of a scene, its `ref_ids` already hold that
  base still (the shot's `still` prompt is an edit of it).
- Prompts describe people; they never contain a name. If you find a name in a prompt, replace it with the person's
  description from the scene block and note it.

## For every shot, in this order

A `pair2` shot: make nothing; write its line in the done file with the pair1 shot's refs and `"note": "pair2"`.

1. **Still:** `create_image` with model `nano-banana-2.1`, aspectRatio `9:16`, resolution `1K`, quality null,
   background null, enhancePromptMode null, outputCount 1, prompt = `still`, references = `ref_ids`.
   clientRequestId = `<CODE>.<n>-still-<id>-v1-<yyyymmdd>` (at least 16 characters, Starpop refuses shorter ones; `-v2-` for a retake, the same id for a retry of the same request). The still is made with the plates listed in the shot's `refs` attached.
   If the call goes to the background or returns status running, use `wait_for_job` with the jobId.
2. **Download** the still at once (links expire after 15 minutes) with curl to `stills/<id>.png` in the ad folder.
   If the link has expired, call `get_job` for a fresh one.
3. **Check it** (Read the png): the right people (the hero's face stays the same person: <HERO DESCRIPTION, e.g.
   dark wavy shoulder-length hair, light-brown eyes>), right clothes for the shot, no extra or missing fingers, no
   readable text except the product label, the action matches the prompt. If clearly wrong, regenerate ONCE with a
   sharpened prompt; if still wrong, keep the better one and note it.
4. **Clip** (only for `full`, `pair1` and `long`): `create_video` with model = the shot's `clip_model` if set, else `minimax-h3-max-turbo`, resolution
   `768p`, aspectRatio `9:16`, durationSeconds = the shot's `seconds` (5 if missing), outputCount 1, multiPrompt null,
   guidance `{"type":"frames","firstFrame":"<the still's image: ref>","lastFrame":null}`, prompt:

   ```
   Style: <LOOK LINE FROM ad.json>, filmic grade.

   Camera: <the 'Camera:' sentence from motion>
   <the rest of motion: the action>

   Constraints: Nobody talks or sings. No captions, no text. Same characters, clothes and set as the first frame.
   ```

   For `pair1`, put the shot's `motion` in place of the Camera and action lines as it is (it already holds Shot 1,
   Hard cut, Shot 2); if it ends with its own Constraints line, drop that one so the line appears once. For `long`,
   clip `b` uses `motion_b` and the last frame of clip `a` as firstFrame.
   Another video engine (start image only): same steps with that engine's own call and clip length; the start image
   is always the shot's still.
   clientRequestId = `<CODE>.<n>-clip-<id>-v1-<yyyymmdd>` (16+ characters). Wait for it, then download to `clips/<id>.mp4` at once.

5. Append one line per shot to `batches/<batch>_done.jsonl`:
   `{"id": ..., "still_ref": "image:...", "clip_ref": "video:...", "note": "..."}`

Run 3 shots in parallel at most (Starpop queues heavy load). `wait_for_job` may need to be called several times for one job.

## Rules

- Spend only on these shots: max 2 stills and 1 clip per shot (2 clips for `long`, none for `pair2`, no clip for
  `still`).
- The firstFrame is always the shot's own still, never a character sheet. Never generate audio or music.
- Never print or store anything except into the ad folder files above. Do not edit ad.json.
- Report back in under 150 words: done count, retries, any shot you are unhappy with and why.
- Never ask the user anything; decide within these rules and note doubts in your report.
- A download that returns 403 or a non-image file means the link expired: call `get_job` for a fresh link and retry.
