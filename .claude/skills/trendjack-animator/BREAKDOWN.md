<!-- Library v2, 2026-11-09 -->
<!-- Changelog
2026-11-16  Missing settings: Claude asks for them itself (no Ad Clone setup needed).
-->

# Trendjack Animator: workflow breakdown

A plain-language walk-through of the whole pipeline, for someone who has never touched code. The exact instructions
Claude follows are in `SKILL.md`; this page explains what happens, why, and what you check.

## What it does, end to end

You tell Claude what you sell and which trending animated format you want (a sung drama story, a cartoon story with a
narrator, a 3D "how it works" explainer, a cartoon skeleton, a catchy product song, or an AI remake of a real creator
video) and which look (3D film, claymation, watercolor, paper, felt, anime, collage, motion graphics, phone footage).
Claude writes three script options, you pick one, the audio gets made, and then Claude builds the pictures and clips
around that audio and assembles a finished vertical ad with captions that the phone app does not cover.

You stay in control of money and taste: every paid step shows its cost first and waits for your yes, and you are the
one who listens to the song or voice and picks the take.

## Before the first run

Claude reads your settings (`## agentchad settings` in your project CLAUDE.md; missing: it asks you for the folders,
brand and ad code once and saves them). It runs the brand check first. If your brand pack is missing or thin (no list of what the product never
claims, fewer than 10 real customer quotes, no offer), it stops and offers to run `brand-research` first. Then it
asks its Stage 1 questions in one message (with the format and look cards), checks Starpop and its credits,
ElevenLabs, Suno, the Whisper venv and your product photo, and runs the free dry-run test. Before delivery every
video gets the `motion-and-sfx-kit` pass and the `qa-sniper` check, you review it (Frame.io comments on exact
timestamps, or notes with timestamps in a review file), and Claude asks "Do you want to upload these to Meta, TikTok, Snapchat, Google or AppLovin?".
Full list: "First run" in SKILL.md.

## The one idea that makes it work: the Audio-First Clock

Most AI animated ads are made picture-first, and the voice is squeezed over them afterwards. They feel random.
Here the audio is made first. Its exact word timings are measured, and every shot is cut to start and end on a line
of that audio. So the picture always shows what you are hearing at that moment, the cuts land on words, and nothing
is ever sped up or slowed down to fit.

## The pipeline

```
 You: product, buyer, offer, format, look
            |
            v
 [1] Brief + 3 script options ------------------> brief.md, scripts.md        (free)
            |  you pick one
            v
 [2] Audio first
     song  -> you make it on suno.com, download one take
     voice -> ElevenLabs, one continuous take   --> song/ or voice/ files       (Suno plan / ElevenLabs characters)
            |
            v
 [3] Word timings (Whisper or ElevenLabs)  -----> line start/end times       (free)
            |  = THE CLOCK
            v
 [4] Shot plan: one shot per line --------------> ad.json                     (free)
            |
            v
 [5] Plates (approved) + one still per shot -----> sheets/, stills/, contact.jpg   (Starpop credits)
            |  you approve the contact sheet
            v
 [6] Animated clips (1-2 lip-sync shots) -------> clips/                      (Starpop credits)
            |
            v
 [7] Render: clips cut to the clock + captions -> final/<name>.mp4           (free, on your computer)
            |
            v
 [8] QA sheet, fixes, hand-over ----------------> final/qa_frames.jpg         (free)
```

## What each step gives you

| Step | Output                                                         | You do                                     |
| ---- | -------------------------------------------------------------- | ------------------------------------------ |
| 1    | A brief and three scripts in the format's proven beat order    | Pick a script                              |
| 2    | The song (from Suno) or a voiceover take (from ElevenLabs)     | Make the song in Suno; listen, pick a take |
| 3    | A list of every line with its start and end time               | Nothing                                    |
| 4    | A shot list: what each shot shows, its camera move, its timing | Approve it                                 |
| 5    | Plates (characters, product, places), then one picture per shot | Say yes to the cost; approve the plates    |
| 6    | A few seconds of animation per shot                            | Say yes to the cost                        |
| 7    | The finished 1080x1920 video with captions                     | Watch it                                   |
| 8    | A sheet of frames from the final video, checked for problems   | Final yes                                  |

## Time and cost guide (rough; your plan and prices will differ)

- **Your time:** about 20-40 minutes of decisions and listening per ad. Making the song on suno.com takes a few minutes.
- **Machine time:** stills arrive in seconds to a minute each; clips in a few minutes each; the final render takes
  about as long as the ad.
- **Pictures:** the default mix is about 3.5 Starpop credits per shot, so a 9-shot 15-second ad is roughly 30-35
  credits. Better quality settings cost about 1.6 times that. A photoreal phone-footage clone is about 10 credits a shot.
- **Voice:** ElevenLabs charges about one character per letter of the script; a 30-second voiceover is a few hundred
  characters.
- **Song:** one Suno generation gives two takes.
- **Assembly and checks:** free, on your computer.

Claude asks Starpop for an exact estimate before every paid batch and shows it to you.

## What to check before you trust the result

1. **Every picture shows its line.** Pause on each cut: does the image match what is said or sung?
2. **Same faces, same clothes.** The hero should look like the same person in every shot of a scene.
3. **Your product is right.** Real packaging, caps on, the right size compared to hands and other objects, the label
   readable, never covered by a caption.
4. **Captions.** One line each, same size all the way through, never over a face or the product, never hidden by the
   app's buttons or text (Claude's render refuses anything outside the visible area).
5. **The start.** The first second already has the hook: no silent or instrumental intro, no slow establishing shot.
6. **The audio.** You listen: words clear, the brand name pronounced right, music far under any voice.
7. **Claims.** Nothing said or shown that your product page cannot back up.

## Where things are saved

Each ad gets its own folder: `<MEDIA_DIR>/<BRAND>/ads/<MARKET>/<CODE>.<n>-<slug>/` (by default under
`~/agentchad-media`). It holds the brief, the scripts, the audio, every picture and clip, and the final video, so any
redo can start from where it stopped. A copy of the brief and the path to the final video go into your notes folder
(`<WORKSPACE>/<BRAND>/05_briefs/`).
