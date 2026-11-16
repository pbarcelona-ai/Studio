# Book to Screen — build instructions (v3)

Hand everything inside the fence below to an AI coding assistant or a developer.
Fill in the `[brackets]` in Section 0 first.

**What changed in v3**

- "Start over" (keep old pictures and their prompts for reuse), project history (restore an earlier moment) and branching.
- Permission to reorganise Studio's tabs and cards (Section 2, rule 10).
- Capabilities that competing tools have and Studio didn't, from a review of Flova, Story.com, Creatorwood and
  Inkitt on 2026-11-15. They're marked ★ and listed in Appendix A.
  - a Producer chat with stop/continue, and notes on shots
  - format recipes
  - footage, music and audio sources
  - a three-track timeline editor
  - episodes and vertical formats
  - audiobook and marketing-kit outputs
  - dollar estimates including regenerations, and draft/final quality tiers
  - an MCP server
- Wording fixes: "style card", and "Step N of M" with no numbers on the cards.
- 2026-11-15 architecture check: Section 8 storage rules (folders as the truth plus a rebuildable SQLite index,
  immutable asset files, rev checks, cents) and progress checkboxes on the milestones.

## Progress

Preparation (outside the build):

- [x] v1–v3 build instructions written (2026-11-15, commit `d4ffcc0`)
- [x] Capability review of Flova, Story.com, Creatorwood and Inkitt (Appendix A)
- [x] Flova recon map and feature matrix: `replica/recon.md`, `replica/features.csv` (2026-11-15, commit `ca92d1b`)
- [x] Architecture check of Section 8: `replica/architecture.md`, `replica/schema.sql` (2026-11-15). The fixes are in Section 8.0
- [x] Fill in Section 0 for the Studio upgrade (recommended answers used, see the Decisions log)
- [x] Approve starting M1 (owner: "proceed with the upgrade", 2026-11-15)

Build milestones: tick them in Section 17 inside the build prompt as each one is approved.

## Decisions log

How decisions are made (owner, 2026-11-15): Claude always proposes a recommendation. If the owner doesn't answer within
about 3 minutes, the recommendation is used and the build continues. Each one is recorded here and summarised at the end
of the upgrade. Anything destructive or that spends money still waits for a real yes.

| # | date | decision | source |
|---|---|---|---|
| D1 | 2026-11-15 | Section 0 filled in with the recommended Studio answers (below) | assumed — not answered |
| D2 | 2026-11-15 | Studio must work on **Windows as well as macOS** (Section 2, rule 11; milestone MW) | owner |
| D3 | 2026-11-15 | Crew role files live in `prompts/crew/`, recipes in `recipes/` (repo root, next to `scripts/`) | assumed — not answered |
| D4 | 2026-11-15 | FAKE providers: tests keep using the existing stubs; a `fake` engine for demo runs is added in M3, when Read it in runs end to end | assumed — not answered |
| D5 | 2026-11-15 | README.md and ARCHITECTURE.md were emptied in commit `252cb89` (130 and 48 lines removed, no reason given). Restored from `252cb89^` and updated, because M1 asks for a README | assumed — not answered |
| D7 | 2026-11-15 | Package Studio as installers for **Windows and macOS** with progress bars that name each task (Section 2, rule 12; milestone MI) | owner |
| D8 | 2026-11-15 | MW: the shell scripts keep their names in steps and saved jobs; `steps.script_argv` runs their Python ports (`scripts/*.py`) on every system, so Mac and Windows run the same code. The `.sh` files stay as 4-line wrappers for old terminal commands. `kaggle_names.sh` is gone (Python `cksum` gives the same names, so old runs are still recognised). The remote GPU scripts (`make_*.py`) stay Linux-only: they run on Kaggle/Colab | assumed — not answered |
| D9 | 2026-11-15 | MW: Windows install is `install.bat` → `install.ps1` (a progress bar naming each task) until the MI installers exist; `run_studio.bat` starts it | assumed — not answered |
| D10 | 2026-11-15 | MW: the Studio always runs in Python's UTF-8 mode (studio.py restarts itself with -X utf8 on Windows; job steps get PYTHONUTF8=1), so text files read the same on every system. Paths sent to the page use forward slashes | assumed — not answered |
| D11 | 2026-11-15 | MI: both installers bring python-build-standalone 3.12 (fetched with `uv python install` at build time), also on Windows: the python.org embeddable build has no pip, venv or tkinter | assumed — not answered |
| D12 | 2026-11-15 | MI: the progress screen is a local browser page (`web/setup_progress.html` + `progress.js`, served by `scripts/install_studio.py`); the same component draws the Setup window's installs. Inno Setup / the .dmg only copy files; install_studio.py makes .venv with uv into `.venv.partial` and swaps it in when complete | assumed — not answered |
| D13 | 2026-11-15 | MI: the macOS app carries the Studio and copies it on first open (and after an update) to `~/Library/Application Support/Pistachios Studio`, where projects live, so dragging a newer app over the old one keeps them; no Dock icon (LSUIElement). Separate arm64 and x86_64 .dmg files. Windows installs per user to `%LOCALAPPDATA%\Programs\Pistachios Studio` | assumed — not answered |
| D14 | 2026-11-15 | MI: no signing identity exists yet, so builds are unsigned (Windows) / ad-hoc signed (macOS); CI signs and notarises automatically once `WIN_SIGN_CMD` or `MAC_SIGN_ID` + `MAC_NOTARY_PROFILE` secrets are added. The README says how to open an unsigned app | assumed — not answered |
| D15 | 2026-11-15 | MI: the only optional part today is the 3D depth view; "local GPU models" get a tick box (`install_studio.OPTIONAL`) when a milestone adds them | assumed — not answered |
| D16 | 2026-11-15 | M2: sources live in `projects/books/<book>/sources/` (index.json + one folder per source). "Use these sources as the chapters" turns them into the normal chapters (a document's own sections, one chapter per idea / web page / picture set, one per screenplay scene), so every later step works for any source today; M3's Read it in reads the merged, source-labelled text | assumed — not answered |
| D17 | 2026-11-15 | M2: the format recipe stays on the M1 Format card (crew.js); the new products / length / aspect / rating / faithfulness / quality / styles controls sit in the same card. Choosing a new recipe resets those settings to the recipe's, keeping the chosen styles | assumed — not answered |
| D18 | 2026-11-15 | M2: cost model for the estimate: 4 s per shot (2.5 s microdrama / music video, 2 s trailer); free GPUs cost $0 and are shown as GPU hours and weeks of the 30-hour Kaggle weekly quota; paid prices (only shown when a paid service is used) are placeholders in `production.PAID_DOLLARS` until M15's cost ledger | assumed — not answered |
| D19 | 2026-11-15 | M2: picture and comic descriptions run when the person presses Describe (one AI call per picture, Story Analyst role); website pictures (up to 8) are downloaded through the same SSRF-safe fetch | assumed — not answered |
| D20 | 2026-11-15 | M3: Read it in hands its result to the Studio's existing plan + screenplay files (`adaptation/adaptation.json`, `screenplay/scene-S*.json`), so the screenplay approval gate, the shot writer and every later step use it unchanged; the full Section 5 outputs live in `readin/` | assumed — not answered |
| D21 | 2026-11-15 | M3: the `fake` engine (D4) is `read_it_in.py --engine fake`: a short, well-formed script made from the source's own sentences, for demo runs and tests; it never calls an AI | assumed — not answered |
| D22 | 2026-11-15 | M3: the screenplay PDF uses the PDF's built-in Courier (no font file to embed, works the same on Windows and macOS); characters outside Windows-1252 print as "?" in the PDF only (Fountain, Word and Final Draft keep them) | assumed — not answered |
| D23 | 2026-11-15 | M4: the continuity book is still the book's `<book>.json` (so every existing step reads it); M4 adds personality profiles, props and `style_neutral: true`, and keeps the old file as `.bak`. Rendering words are refused in tokens; identity words such as "clay pot" or "felt hat" are allowed | assumed — not answered |
| D24 | 2026-11-15 | M4: the shot list lives in `shots/shotlist.json`; M6 turns it into the picture prompts. The Script Supervisor's fixes change text fields only; the Editor's pacing fit scales shot lengths (1.5-12 s, nice-to-have shots change most). The shot list can only be written after the continuity book is approved | assumed — not answered |
| D25 | 2026-11-15 | M5: style cards are written by the Production Designer (as Art Director) and the Colorist; style translations by the Casting Director (as Character Designer) and the Production Designer: the crew files have no separate art_director / character_designer roles (the Section 3.2 roster pairs them) | assumed — not answered |
| D26 | 2026-11-15 | M5: look development renders as a Single Prompts set `projects/prompts/<book>_ld_<style>/` with the usual image runners (Kaggle, Colab, Hugging Face, this computer), using the GPU and keyframe image model chosen in Make the Movie; 4 variants per sheet with their own seeds | assumed — not answered |
| D27 | 2026-11-15 | M6: pictures render as a prompt set `projects/prompts/<book>_px_<style>/` (row N = shot N of the shot list), steered by the look-development picks (front sheet of each character, the location key art) through the runners' existing `refs` column; each shot's seed is fixed from book + scene + shot, so every style uses the same seed | assumed — not answered |
| D28 | 2026-11-15 | M6: a shot layout saves the seed, the size, an edge map (Pillow) and a depth map when the optional depth model is installed; pose skeletons and character boxes are recorded as empty until a pose model is added (M7) | assumed — not answered |
| D29 | 2026-11-15 | M7: the structure lock uses the provider's reference feature (7.4b): the approved master frame is the first reference picture, with the same seed and an instruction to keep its layout; it works with the reference-image model (FLUX.2 klein). For other image models the img2img settings (master frame, strength 0.55, 7.4c) are written to the prompt CSV, but the current Kaggle / Colab notebooks do not start from a picture yet, so pick FLUX.2 klein for the other styles | assumed — not answered |
| D30 | 2026-11-15 | M7: the consistency loop runs one round per click ("Render the failed ones again" = render those rows + check again), up to 3 tries, then the shot is flagged; adding a style takes the look-development approval away (its card and sheets must be approved too) | assumed — not answered |
| D31 | 2026-11-15 | M8: every picture and clip is stored once by its contents in `<book>/assets/objects/` (read-only), with `aliases.json` recording every content a path has had, so replaced takes, reset storyboards and archived attempts stay findable; the library's thumbnails come from these copies | assumed — not answered |
| D32 | 2026-11-15 | M8: "N old pictures could fit" is scored in code (same characters 3, location 2, action 3, camera 1, style 1 = 10), with no AI call per picture per shot (that would cost a call for every pair); the vision check stays available through the consistency check (M7). Auto-fill skips pictures marked "may not match the continuity book" | assumed — not answered |
| D33 | 2026-11-15 | M8: Start over keeps sources, settings and styles by default (as the plan's checklist shows); restoring an attempt first archives the current version as a new attempt, keeping in place what the restored attempt did not archive | assumed — not answered |
| D34 | 2026-11-15 | M9: the sound plan writes the Studio's own audio CSVs (audio_shots.csv one row per shot of the approved shot list, audio_scenes.csv, and a new audiobook.csv), so the existing narration / effects / music runners and the mixer make the sound; the CSVs they replace are kept as .csv.bak. Voices are Kokoro voices (on this computer, no GPU) | assumed — not answered |
| D35 | 2026-11-15 | M9: the audiobook narrator reads the screenplay's action lines and the characters speak their own lines; its cover is the first approved master picture until the marketing kit makes the poster (M14) | assumed — not answered |
| D36 | 2026-11-15 | M10: the EDL lives in `edit/edl.json` with named alternative cuts; clips are referred to by scene and shot, so one cut renders in every style. Voice and effects ride on their clip (they move and delete with it); music spans its scene. Renders run through `render_cut.py` (ffmpeg graph in a file, so long films work on Windows) | assumed — not answered |
| D37 | 2026-11-15 | M10: the style card's colour grade is mapped to the nearest grade.py preset by its words (noir, warm, cool, desaturated, vivid, faded, night) | assumed — not answered |
| D38 | 2026-11-15 | M11: each style's clips render from its picture set as an image-to-video set (all_shots.csv + images/pictures_keyframes) with the usual runners and KEYFRAME_MODEL=pictures; the motion prompt is shared, prefixed with the style card's prefix. Clips are checked by the owner against the Animation Supervisor's checklist (no morphing, no identity drift, the right motion); an automatic vision check of clips is for M15 | assumed — not answered |
| D39 | 2026-11-15 | M12: open notes go into the addressed role's system prompt (crew.system) and are resolved when that step is approved; "Add information" is a project note every role reads. Every approval and every accepted chat plan makes a history moment; going back saves the current state first; a branch copies the pictures (no generation) and gets its own prompt sets | assumed — not answered |
| D40 | 2026-11-15 | M12: the conflict prompt guards the shot list, the continuity book and the edit: an edit while the running step writes the same thing answers 409, and the page asks whether to keep the owner's change (sent again with force) or the job's | assumed — not answered |
| D41 | 2026-11-15 | M13: transcription uses faster-whisper ("small", on the processor) through the job's own uv environment; without it the video is still understood from its pictures. Shots are found with ffmpeg's scene score (0.3). The Story Analyst sees one contact sheet of the key frames (one vision call per video) | assumed — not answered |
| D42 | 2026-11-15 | M13: "Make a story from my clips" writes a new shot list of real shots (the old one is saved as a history moment first); a real shot's clip is the same footage in every style; an uploaded track becomes one music item under the whole film, its tempo estimated in plain Python | assumed — not answered |
| D43 | 2026-11-15 | M14: an episode is a book of its own (<book>_e01 ...) made from its part of the source; the series' continuity book, style cards and look development, settings, rules and voice cast are copied into it (sync), with the series' approvals of them, so the series stays the one place to edit them | assumed — not answered |
| D44 | 2026-11-15 | M14: the marketing kit is planned by the Trailer Editor with the producer as Marketing Lead and cut from the style's approved clips by the film's renderer; the poster and thumbnail are drawn with Pillow on the chosen shot's picture | assumed — not answered |
| D45 | 2026-11-15 | M15: Autopilot is `autopilot.py`, one job that calls the same step modules as Review mode, approves the gates not ticked under "Stop for my review at", picks the first rendered look-development variant, renders styles in parallel up to the service's limit (Kaggle 2, Colab / Hugging Face / this computer 1), and stops before any paid call over the spending limit ($0 by default) unless confirmed | assumed — not answered |
| D46 | 2026-11-15 | M15: the automation API is `/api/v1/...` with the book named in the body or query (the Studio's router has no path parameters), the page's own token, and server-sent events at `/api/v1/events`; the CLI is `python scripts/book2screen.py`; the MCP server (`scripts/mcp_server.py`, stdio) calls that API with the same token. Actual cost is counted from what is on disk (pictures, versions, clips), plus paid calls recorded in ledger.json | assumed — not answered |
| D6 | 2026-11-15 | Milestones don't stop for approval: each is committed, reported and the next one starts (owner: proceed; per D-rule above) | owner |

~~~
=====================================================================
BUILD PROMPT: "Book to Screen"  (v3)
Turns ANY source (a book, an idea, a picture, a website, footage, music,
a document) into a professional screenplay, then into a storyboard, an
illustrated book, an animatic, a film, an audiobook and a marketing kit,
in one or more visual styles (realistic, claymation, Pixar-style 3D,
anime ...) that all tell exactly the same story shot for shot.
=====================================================================

You are a senior full-stack engineer. Build the website described below.
Work in the MILESTONES listed in Section 17. After each one, stop, tell me
what you built and how to test it, and wait for my OK before you start the
next. Don't skip steps or combine milestones.

The three requirements that matter most are Sections 3, 5 and 7:
  (1) the "Read it in" button produces a real screenplay, not just stored text;
  (2) every AI and GPU prompt is written by the right Hollywood crew member;
  (3) one project can be rendered in many styles with the same result.
If a later instruction seems to conflict with these, these win.

---------------------------------------------------------------------
SECTION 0 — MY CHOICES (fill these in before you start)
---------------------------------------------------------------------
- Site name: [e.g. Book to Screen]
- Build target: [new site from scratch / upgrade the existing Studio app]
- Who uses it: [just me / my team / the public]
- Hosting: [local only / Vercel / Render / my own server]
- Tech stack: [let the AI choose / Next.js + TypeScript / Python FastAPI + HTMX
               / keep Studio's existing Python server + plain JS]
- Text + vision AI: [Claude: claude-opus-5-5 for writing and directing,
                     claude-sonnet-5-5 for checks, extraction and critiques]
- Image AI: [Runway / Krea / Hugging Face / local ComfyUI + Stable Diffusion]
  It must support at least one of: reference images, seed control,
  structure control (depth / pose / edge maps). Needed by Section 7.
- Video AI: [Runway / Krea / LTX / Wan / none]
- Voice AI: [ElevenLabs / OpenAI TTS / local TTS / none]
- Music AI: [provider / upload only / none]                          ★
- Transcription (for video/audio sources): [Whisper / provider / none]
- Default mode: [Autopilot / Review each step]
- Default format recipe: [Feature film / Vertical microdrama / Picture book] ★
- Monthly spending limit on AI calls: [$__]
- Operating systems: Windows 10/11 AND macOS (both required)       ★

If anything here is blank, pick a sensible default, tell me which one you
picked, and keep going.

Studio upgrade answers (D1 — recommended, used because no answer came):
- Site name: Pistachio's Studio (unchanged)
- Build target: upgrade the existing Studio app
- Who uses it: just me (single user, local), designed so accounts can
  be added later
- Hosting: local only (python scripts/studio.py, on Windows or macOS)
- Tech stack: keep Studio's existing Python server + plain JS
- Text + vision AI: Studio's existing engines (claude / codex / hf /
  local); claude-opus-5-5 for writing and directing, claude-sonnet-5-5 for
  checks, when the claude engine is used
- Image AI: Studio's existing catalogue (Kaggle / Colab / Hugging Face /
  this computer); structure lock uses the models with depth/pose control
- Video AI: Studio's existing catalogue (LTX, Wan, Hunyuan, SkyReels ...)
- Voice AI: Studio's existing local TTS (Kokoro, Chatterbox, Qwen3 TTS)
- Music AI: Studio's existing MusicGen, plus upload
- Transcription: Whisper (local), added in M13
- Default mode: Review each step (Autopilot available)
- Default format recipe: Feature film
- Monthly spending limit: $0 by default (free GPUs only); paid calls are
  refused until the owner sets a limit
- Operating systems: Windows 10/11 and macOS

---------------------------------------------------------------------
SECTION 1 — WHAT THE SITE DOES
---------------------------------------------------------------------
1. The user adds one or more SOURCES (Section 4). A source can be a whole
   book, a one-line idea, a picture, a web page or their own footage.
2. They press READ IT IN. The crew reads the sources and turns them into
   a discrete, scene-by-scene SHOOTING SCRIPT, the way a professional
   screenwriter would (Section 5). This always happens; it is the core
   of the product.
3. They pick a FORMAT RECIPE (Section 6d), the OUTPUT PRODUCTS, and one
   or more STYLES.
4. The crew takes the script through production, one ordered path of
   steps, each step run by the right professional (Section 3). The user
   can talk to the crew at any time through the Producer chat
   (Section 3.5).
5. Every style produces the same story, shots, framing, timing and edit;
   only the look changes (Section 7).

Output products (checkboxes; any combination):
  A. Screenplay        → PDF (industry format) + .fountain + .docx
  B. Storyboard        → one image per shot, grid view, PDF
  C. Illustrated book  → one image per page with the story text, PDF
  D. Animatic          → storyboard frames timed to dialogue/narration, MP4
  E. Film              → image-to-video clips + sound + music, MP4
                         (one film, or a series of episodes, Section 6e)
  F. ★ Audiobook       → the narration and character voices as M4B/MP3
                         with chapter markers (no pictures needed)
  G. ★ Marketing kit   → trailer (30–90 s), poster, thumbnail, three
                         vertical 9:16 teaser clips, logline and
                         social-post captions
  Each of B–E and G is made once PER SELECTED STYLE (e.g. "Film –
  Claymation", "Film – Realistic").

Dependencies (the site enforces these and explains them in plain words):
  - A always comes first; it is made by READ IT IN.
  - B, D, E and G need the shot list. D, E and G need B in the same style.
  - C needs the continuity book and the page plan.
  - F needs A and the voices from Step 8; it doesn't need any pictures.
  - G needs E (the trailer is cut from the film's clips).
  - A second style never re-runs the writing or planning steps. It
    reuses them (Section 7).

---------------------------------------------------------------------
SECTION 2 — DESIGN RULES
---------------------------------------------------------------------
1. ONE PATH. The project page is a single ordered list of steps that a
   10-year-old can follow. It shows "Step N of M" as the step counter,
   with no numbers on the cards themselves. Each step shows: a
   plain-English title, the crew member doing it ("Your screenwriter is
   writing scene 4 of 22"), a status (Not started / Working / Needs your
   review / Done / Out of date), and one normal-sized main button with
   the right options already set. Other settings are folded under
   "More settings". "What to do now" is always visible.
2. GATES. A step can't start until the steps it depends on are Done.
   Locked steps say why.
3. LOOP-BACKS. Any Done step can be reopened. Reopening it marks the later
   steps that depend on it Out of date and offers to redo them. Changes
   made in a later step that affect an earlier one (e.g. a storyboard
   change that alters the screenplay) are flagged on that earlier step
   with a red outline, and the user walks the steps again in order.
   Nothing is deleted without asking.
4. TWO MODES.
   - AUTOPILOT: one button ("Make my film") runs every step from source
     to final download with no clicks. The user can tick "Stop for my
     review at: [ ] script [ ] continuity book [ ] shot list [ ] pictures
     [ ] final cut". Each automatic step still runs its crew critique
     (Section 3.3) before moving on.
   - REVIEW: stops at every review gate.
   Both modes use the same steps, prompts and data. Autopilot is just
   Review mode with the gates approved automatically.
5. REVIEW BEFORE SPENDING. Before the first paid image/video call (in
   Autopilot, before the run starts), show the estimated cost (Section
   10.2) and ask for confirmation. Never go over the spending limit.
6. PLAIN WORDS. No jargon in the interface (the crew can use jargon inside
   their prompts). Say "continuity book", "style card", "scene", "shot",
   "picture", "clip".
7. NOTHING LOST. Every AI result is saved as a version and can be
   switched back to. Starting over archives the project; it never
   deletes it (Section 6b).
8. RESUMABLE. Jobs run in the background, survive a closed browser or a
   restart, and continue from the last finished item. Two browser tabs
   on the same project never start the same job twice.
9. ACCESSIBLE. WCAG 2.1 AA: labels, keyboard use, visible focus, alt text
   on every generated image (the shot's action line), contrast ≥ 4.5:1,
   works at phone width with no sideways scrolling, light and dark mode.
10. FREEDOM TO REORGANISE STUDIO (when the build target is the existing
    Studio app)
    - You may ADD, DELETE, MERGE, SPLIT, RENAME and REORDER tabs, cards,
      panels and buttons in web/index.html and the web/static/js/ modules
      (flow.js, nav.js, shell.js ...), and the routes behind them, to fit
      the step path in Section 6.
    - The old layout is not a constraint. Choose the layout that makes
      the one ordered path clearest.
    - Limits that still apply:
      a) The SINGLE PROMPTS tab stays (data-tab="prompts",
         #panel-prompts, with its prompt-set flow and gallery). It may be
         moved or restyled, but not removed, merged into another tab, or
         lose any of its features.
      b) No working feature disappears. If a card or tab is deleted, its
         function moves to the right step of the path or to an
         "Advanced" area, unless it's replaced by something that does
         the same job better (say which).
      c) Never delete user data, projects, pictures, clips, takes or
         replaced/ archives because of a layout change.
      d) Rule 1 (one path, gates, loop-backs, step counter, normal-sized
         buttons, "continuity book") still applies.
      e) Saved links, API routes used by scripts or tests, and saved
         project files must keep working. Rename or move them with a
         redirect or alias, and update the tests.
    - Every milestone report includes a "Layout changes" table showing
      each tab/card added, moved, merged or removed, where its features
      went, and why.
11. WINDOWS AND MAC. Everything must work the same on Windows 10/11 and
    macOS (and Linux where it already does).
    - Python only for anything the Studio runs on the owner's computer:
      no bash scripts in the Studio's own path. The remote GPU notebooks
      (Kaggle/Colab, which are Linux) may keep shell steps.
    - pathlib for every path, os.replace for atomic saves, encoding="utf-8"
      on every text file, argument lists for subprocess (never shell=True),
      no POSIX-only modules (fcntl, os.fork, signals other than SIGTERM).
    - Launchers for both: run_studio.sh / install.sh (macOS) and
      run_studio.bat / install.ps1 (Windows). The virtualenv's tools are
      in .venv/bin on macOS and .venv\Scripts on Windows.
    - CI runs the test suite on windows-latest and macos-latest as well as
      ubuntu-latest.

12. INSTALLING. Studio is packaged so a non-programmer can install it on
    Windows 10/11 and macOS by double-clicking one file.
    - Windows: a signed .exe installer (Inno Setup or NSIS) that installs
      per user (no admin rights needed), adds Start-menu and desktop
      shortcuts and an uninstaller. macOS: a .dmg with
      Pistachio's Studio.app (drag to Applications), signed and notarised
      when a developer ID is available.
    - The installer brings its own Python (python.org embeddable build on
      Windows, python-build-standalone on macOS) and makes .venv with uv,
      so nothing has to be installed first.
    - PROGRESS: one overall bar (step N of M with a percentage) and one bar
      for the current task, with the task named in plain words:
      "Installing Python 3.12", "Installing the Studio's tools (uv)",
      "Downloading the picture tools: 145 of 610 MB", "Installing ffmpeg",
      "Setting up Kaggle", "Checking everything works". Downloads show
      size, speed and time left. A "Show details" area shows the live log.
    - Cancel at any time leaves nothing half-installed; a failed step says
      what went wrong in plain words, offers Retry, and has a "Copy the
      log" button. Running the installer again resumes where it stopped.
    - Optional parts (the 3D tools, local GPU models) are tick boxes with
      their download size, off by default.
    - Updates install over the top and never touch projects/, books/ or
      the saved settings. Uninstall asks before removing projects.
    - The same progress screen is used by the Studio's own Setup window
      when it installs or updates a tool later.
    - CI builds both installers on every release tag (windows-latest,
      macos-latest) and runs a smoke test: install, start the Studio,
      open the page, uninstall.

---------------------------------------------------------------------
SECTION 3 — THE CREW (every AI and GPU prompt comes from a crew member)
---------------------------------------------------------------------
3.1 Rule
Every call to a text, vision, image, video, voice or music model is
written by a named CREW ROLE. Each role has a role file
/prompts/crew/<role>.md containing:
  - who they are: "You are a [role] with 20 years of experience on
    feature films and animated features"
  - what they're responsible for in this step, and what they must not
    change (owned by other roles)
  - the professional vocabulary and standards they work to
  - the exact output JSON schema for the step
  - a self-check list they apply before answering
The text model plays the role and writes the output. For image, video,
voice and music models, the right crew member WRITES the generation
prompt in their professional language (lens in mm, lighting setup,
blocking, performance direction, tempo and instrumentation), and that is
what the GPU model receives. Image models never receive raw book text.

3.2 Roster (role → step → what they produce)
  Producer (orchestrator) → all steps → runs Autopilot and the Producer
      chat (3.5): calls the roles in order, routes critiques and notes,
      decides when a step is good enough
  Story Analyst / Script Reader → Read it in → coverage: logline,
      genre, tone, themes, characters, key events, what's filmable
  Development Executive → Read it in (thin sources: idea, picture,
      short post, footage) → expands the source into a full story with
      an inciting incident, rising stakes, climax and resolution, sized
      to the target length; splits long books into episodes (6e)
  Screenwriter → Read it in → beat sheet → treatment → screenplay;
      later: rewrites from notes. Turns thoughts and descriptions
      into things the camera can see and hear
  Script Doctor → critiques the draft (structure, pacing, dialogue,
      clarity of what is visual) and sends notes to the Screenwriter
  Script Supervisor → continuity book; checks every later prompt
      for continuity (wardrobe, props, injuries, time of day, screen
      direction)
  Casting Director + Character Designer → character identity tokens
      (style-neutral, Section 7), ★ character personality profiles
      (temperament, motivation, speech patterns, mannerisms, how they
      move), and per-style character sheets
  Production Designer / Art Director → locations, props, palette,
      period; the per-style set look
  Director → director's breakdown per scene: intent, emotional beat,
      blocking, performance notes (using the personality profiles);
      approves the shot list and frames
  Cinematographer (DP) → shot type, lens, camera height and angle,
      movement, composition, lighting setup; writes the camera and
      lighting half of every image prompt
  Storyboard Artist → final image prompt per shot (combining the
      Director's, DP's and Script Supervisor's input); reviews each
      generated frame
  Illustrator / Book Designer → page plan and page images for the
      illustrated book
  Animation / VFX Supervisor → motion prompts for image-to-video;
      picks the shots that need simplifying; ★ matches AI shots to
      the user's real footage (4.2); checks clips
  Voice Director → casts voices from the personality profiles and
      writes delivery notes per line; ★ audiobook narration direction
  Sound Designer → effects and ambience per shot
  Composer / Music Supervisor → music cues: mood, tempo,
      instrumentation, where they start and end
  Editor → assembly and final cut: order, trims, transitions,
      pacing, the edit decision list (EDL); ★ the timeline editor's
      suggestions; ★ auto-edit of raw footage (4.2)
  Colorist → per-style colour grade notes, so all shots match
  ★ Trailer Editor + Marketing Lead → the marketing kit (product G):
      trailer cut, poster and thumbnail composition, teaser clips,
      captions
  Line Producer → cost estimates including regenerations, quality
      tier choices, call budgeting, retry decisions

3.3 Critique loops (automatic in both modes)
  - Screenplay: Screenwriter draft → Script Doctor notes → Director notes
    → Screenwriter revision. At most 2 rounds, or until both rate it ≥ 8/10.
  - Shot list: Director + DP draft → Script Supervisor continuity check
    → Editor pacing check (runtime vs. target) → fix.
  - Pictures: Storyboard Artist + Script Supervisor (vision model) review
    each frame against its shot and the continuity book: right
    characters, count, wardrobe, framing, no extra limbs, no stray text.
    Failed frames are regenerated (max 3 tries), then flagged for the user.
  - Clips: the Animation Supervisor checks for morphing, identity drift
    and wrong motion.
  Every critique is saved and shown in a "Crew notes" panel on the step.

3.4 Notes on anything ★
  The user can attach a NOTE to any screenplay scene, shot, page,
  picture, clip, character card or timeline region (click → "Add a
  note"). A note is addressed to a crew role (chosen automatically, and
  the user can change it). It goes into that role's next revision, the
  same way real production notes are passed on, and is marked resolved
  when the revision is approved. Notes can be dragged into the Producer
  chat to discuss them.

3.5 The Producer chat ★
  - A chat panel is available on every step (it can be collapsed and
    never hides the step path). The user can write what they want ("make
    the villain scarier", "give me a 3-minute vertical version") and the
    Producer turns it into a plan: which steps re-run, which roles act,
    and an estimated cost. Nothing is spent until the user accepts.
  - The chat shows which crew member is working and on what, live.
  - STOP / ADD INFORMATION / CONTINUE: the user can stop any running job
    from the chat, add information, and continue from where it stopped.
  - Simple requests (e.g. regenerate one shot) run directly without a
    plan.
  - The chat never replaces the step path. Everything it does shows up
    as step status changes, versions and crew notes, so the path stays
    the single source of truth.

---------------------------------------------------------------------
SECTION 4 — SOURCES (anything the AI can turn into a story)
---------------------------------------------------------------------
4.1 Story sources
Build a SourceAdapter per type. Each one outputs a normalised
SourceDocument { kind, title, text, images[], media[], metadata,
rights_note }.
  - Book/document: .txt .md .docx .pdf .epub .rtf .odt; clean it,
    detect chapters, chunk at about 15k tokens with overlap
  - Idea: free text, from one line to several pages
  - Picture(s): .jpg .png .webp; the vision model (as Story Analyst)
    describes characters, setting, mood and an implied story; the
    images are kept as visual references for the Character Designer
    and Production Designer
  - Website URL: server-side fetch with a timeout and size limit, main
    content extracted with a readability tool, images collected;
    robots.txt respected; only http/https; private/internal IP ranges
    blocked (SSRF protection)
  - Comic/manga (images with text): the vision model reads the panels
    in order
  - Existing screenplay (.fountain .fdx .pdf): parsed straight into
    scenes; Read it in then runs only the critique and polish
4.2 Media sources ★
  - Video/audio (.mp4 .mov .mp3 .wav .m4a, or a URL the user has rights
    to): transcribe it, detect shots/scenes, and extract keyframes. The
    Story Analyst describes what happens.
  - MEDIA UNDERSTANDING: any uploaded video, music or audio can be used
    as a reference. The user (or the agent) can extract a clip, a key
    frame or an audio segment and bind it to a character, location, shot
    or music cue.
  - REAL FOOTAGE + AI SHOTS: the user's own footage can be placed into
    the shot list as real shots. The Animation / VFX Supervisor plans AI
    shots that match its look (lens, lighting, colour) so the two can be
    cut together.
  - RAW FOOTAGE AUTO-EDIT: "Make a story from my clips". The Editor picks
    the best moments, orders them into a story with smart cuts and
    transitions, and the Screenwriter writes narration to tie them
    together.
  - Music: an uploaded track can be the film's score; the Editor cuts to
    its beats.
4.3 Mixed sources
  Several sources in one project (e.g. a book + photos of the real
  places + an idea for a new ending + a song) are merged by the
  Development Executive, who notes which source each element came from.
Limits: 20 MB per document, 2 GB per video, 400k words in total. A rights
checkbox is required and stored with a timestamp.

---------------------------------------------------------------------
SECTION 5 — "READ IT IN" (book → professional shooting script)
---------------------------------------------------------------------
Pressing READ IT IN runs this pipeline as one background job, with live
progress ("Your story analyst is reading chapter 7 of 31"):

  5.1 Ingest — the SourceAdapters build the SourceDocuments.
  5.2 Coverage — Story Analyst. Long sources are done in two passes:
      chapter summaries (best dialogue kept word for word), then
      coverage over the summaries plus the full key chapters.
  5.3 Development — Development Executive. Only for thin sources, when
      coverage says the story is too short or unclear for the target
      length, or when the format recipe asks for episodes.
  5.4 Adaptation plan — Screenwriter: which events are kept, merged or
      cut, with reasons, sized to the target length, the format recipe
      and the faithfulness setting; the ending is never rushed.
  5.5 Beat sheet — Screenwriter: 3 acts (or per episode: hook, rising
      stakes, cliffhanger), with numbered beats (opening image, inciting
      incident, midpoint, low point, climax, final image).
  5.6 Treatment — Screenwriter: 1–3 pages of present-tense prose.
  5.7 Screenplay — Screenwriter, one act (or episode) per call, with the
      previous act's last scene included for continuity. Standard format:
      numbered scene headings (INT./EXT. LOCATION – TIME), present-tense
      action lines that describe only what can be SEEN or HEARD, CAPS
      character names on first appearance, dialogue, parentheticals,
      (V.O.) for the inner voice the book needs, transitions. Each scene
      also gets a hidden structured block: characters present, location,
      time of day, props, wardrobe changes, emotional beat, estimated
      screen time.
  5.8 Critique loop — Script Doctor + Director (Section 3.3).
  5.9 Result — the user sees the screenplay with coverage, beat sheet and
      treatment in tabs. Product A can be exported immediately.
      In Autopilot the job continues straight into the next steps.

The screenplay and its structured scene blocks are the ONLY input for all
later steps. Later steps never read the raw source again, except the
Script Supervisor checking facts and the Character/Production Designers
using source pictures and media as references.

---------------------------------------------------------------------
SECTION 6 — THE STEP PATH (what the user sees, in order)
---------------------------------------------------------------------
Step  Add your sources                   (Section 4)
Step  Choose a format and what to make
      - FORMAT RECIPE (Section 6d), which fills in sensible settings.
      - Products A–G; target length; aspect ratio (16:9, 9:16, 1:1,
        4:3); rating (All ages / 8+ / 13+ / Adult); faithfulness
        (Strict / Balanced / Free); quality tier (Draft / Final,
        Section 10.2).
      - STYLES: multi-select from presets (Realistic live action,
        Claymation, Pixar-style 3D, Anime, Watercolour storybook, Comic
        ink, Stop-motion felt, Noir black-and-white) or a custom style
        (text + optional example image). One style is marked MASTER
        (default: the first one picked).
      - Live estimate of shots, calls and dollars per style, including
        expected regenerations.
      - Buttons: "Read it in" (Review mode) / "Make everything" (Autopilot).
Step  Read it in → screenplay            Screenwriter team (Section 5)
      REVIEW GATE. Notes per scene and for the whole script.
Step  Continuity book                    Script Supervisor, Casting,
                                         Production Designer
      Style-neutral identity cards (Section 7.2) with personality
      profiles. Editable. REVIEW GATE.
Step  Director's breakdown + shot list   Director, DP, Editor
      Per scene: the director's intent, then the shots (number, shot
      type, lens, camera height/angle/movement, blocking, action,
      expression, dialogue, sound, duration, transition, priority,
      characters and props in frame, real-footage or AI). Illustrated
      book: Illustrator page plan. Editable table with drag (and
      keyboard) reordering; runtime vs. target. When old pictures
      exist, each shot shows "N old pictures could fit" (Section 6b).
      REVIEW GATE.
Step  Look development, per style        Character Designer, Art
                                         Director, Colorist
      For each style: a style card (medium, materials, rendering,
      lighting language, palette, grade), character sheets
      (front/side/face), and location key art. The user picks the best
      of 4 or regenerates. REVIEW GATE.
Step  Pictures, master style first       Storyboard Artist, DP,
                                         Script Supervisor
      Then the other styles are made from the master layouts
      (Section 7.4). A grid per style, a side-by-side "Compare styles"
      view, and Regenerate / Edit prompt / Versions / Approve / Note on
      each tile. Pictures can be swapped between shots by drag and drop
      (with keyboard buttons as well). REVIEW GATE → Products B and C
      per style.
Step  Voices, sound and music            Voice Director, Sound Designer,
                                         Composer
      Made ONCE and shared by every style. REVIEW GATE → Product F
      (the audiobook) can be exported now.
Step  Clips, per style                   Animation / VFX Supervisor
      Same motion prompts and durations for every style. REVIEW GATE.
Step  Edit                               Editor
      ★ TIMELINE EDITOR: three tracks (video, voice/dialogue, music +
      effects). Drag to reorder and trim; volume per clip and per
      track; ducking music under speech; snap to music beats; split and
      ripple delete; a preview player with a style switcher. The Editor
      role suggests cuts and pacing fixes as notes the user can accept
      in one click. Every timeline change is written to ONE edit
      decision list (EDL), which is reused for every style. REVIEW GATE.
Step  Colour and finish, per style       Colorist
      Grade per style card, ffmpeg render → Products D and E per style.
Step  Marketing kit ★                    Trailer Editor, Marketing Lead
      Trailer, poster, thumbnail, vertical teasers and captions, per
      style → Product G.
Step  Download
      Cards per product per style, plus "Download everything (.zip)",
      including the continuity book and style cards (PDF + JSON).

---------------------------------------------------------------------
SECTION 6b — START OVER (keep old pictures and their prompts for reuse)
---------------------------------------------------------------------
6b.1 The button
  - Every project has a "Start over" button at the top of the step path.
  - It opens a short checklist: "Keep: [x] my sources [x] my settings
    [x] my styles [ ] continuity book [ ] screenplay". Everything not
    ticked starts again from the right step.
  - Nothing is deleted. Everything made so far (screenplay versions,
    continuity book, shot list, pictures, clips, audio, EDL, crew notes)
    is moved into an ARCHIVE named with the date and time, e.g.
    "Attempt 2 – 15 Nov 2026 14:05".
  - It can't run while a job is running; the user is told to wait for
    the job or stop it.
  - Archives can be viewed read-only, and any one can be restored as the
    current version (the current version is archived first).
  - In Studio: build on the existing storyboard reset (replaced/<time>/,
    takes.py reset_storyboard) and old-pictures code (old_pictures.py,
    picture_record.py) instead of replacing them.

6b.2 The picture library
  Every picture and clip ever made in the project (current, earlier
  takes, archived attempts, every style) goes into a PICTURE LIBRARY.
  Each library item keeps:
    file, thumbnail, kind (image|clip), style, provider + model, seed,
    the full prompt split into its parts (Section 7.3), negative prompt,
    the shot it was made for (scene, shot number, action, characters,
    location, camera, lens), its shot layout maps (Section 7.4), its
    consistency score, the user's verdict (liked / approved / rejected),
    ★ a purpose label (keyframe / final / reference), which attempt it
    came from, and its cost.
  ★ ASSETS AND VERSIONS: pictures that serve one creative purpose (e.g.
  "Eve, front view" or "shot 12 keyframe") are grouped as one asset with
  several versions. The LIKED version is the default and is listed
  first; the rest are listed newest first. One asset can be used in
  several shots. A version can be dragged onto another asset, or turned
  into an asset of its own.
  The library is searchable by text, character, location, style, purpose
  and attempt. A "Show all my projects" switch searches every project the
  user owns.

6b.3 Reuse
  - When a new shot list is made, the Storyboard Artist (text model) +
    Script Supervisor (vision model) score every library picture against
    every new shot: same characters, location, action, camera and style.
    Each shot then shows "N old pictures could fit" with the best first.
  - Three ways to reuse:
      a) "Use this picture": copied onto the shot (the original stays
         in the library) and recorded as reused from item X.
      b) "Use its prompt": the old prompt parts, seed and layout are
         loaded into the shot, ready to edit and regenerate (this also
         works in a different style).
      c) "Use its layout only": the old shot layout is used as the
         structure control for a fresh picture.
  - A "Fill matching shots automatically" button, plus an Autopilot
    setting: "Reuse an old picture when its match score is ≥ [8]/10
    instead of paying for a new one." The cost estimate shows the saving.
  - A reused picture whose characters' or location's continuity tokens
    have changed since it was made is marked "May not match the
    continuity book" and offered for checking or regenerating.

6b.4 API
  POST /api/projects/{id}/start_over  { keep: [...] } → attempt_id
  GET  /api/projects/{id}/attempts    POST .../attempts/{a}/restore
  GET  /api/picture_library?project=&q=&style=&character=&purpose=&all_projects=
  GET  /api/projects/{id}/shots/{n}/matches
  POST /api/projects/{id}/shots/{n}/reuse  { item_id, how: picture|prompt|layout }
  POST /api/projects/{id}/auto_reuse  { min_score }

---------------------------------------------------------------------
SECTION 6c — HISTORY AND BRANCHES ★
---------------------------------------------------------------------
  - Every approval, Producer-chat request and Autopilot step creates a
    MOMENT in the project history (a timestamped snapshot of the project
    records; files are referenced, not copied).
  - "Back to this moment" restores the project to any moment. The
    current state is saved as a moment first, so nothing is lost.
  - "Branch from here" copies the project at any moment into a new
    project, e.g. to try a darker ending or a different style.
    Branches share the picture library, so pictures aren't paid for
    twice.
  - A "Compare branches" view shows two branches side by side (script
    diff, storyboard grid, timeline).
  - If the user edits something while a job is changing the same thing,
    a conflict prompt shows both versions and asks which to keep.

---------------------------------------------------------------------
SECTION 6d — FORMAT RECIPES AND PROJECT RULES ★
---------------------------------------------------------------------
  - A FORMAT RECIPE is a saved file /recipes/<name>.json that describes
    how one kind of video is made: the product set, aspect ratio,
    target length, episode structure, step order and which optional
    steps are skipped, models per step, quality tier, prompt rules per
    crew role, the critique thresholds, and the delivery specification.
  - Built-in recipes: Feature film (16:9), Short film (16:9, ≤ 15 min),
    Vertical microdrama series (9:16, 60–120 s episodes, a cliffhanger
    every episode), Picture book (product C only), Animatic pitch,
    Trailer only, Audiobook only, Music video (cut to an uploaded track).
  - "Save as recipe" saves the current project's settings and prompt
    rules as a new recipe. Recipes can be exported and imported as files
    to share them.
  - PROJECT RULES: each project has a rules document (e.g. "Eve never
    wears red", "no gore", "British spelling", "always end scenes on a
    close-up") that every crew role reads on every call. The user edits
    it on the project page, or the Producer adds to it from the chat
    when the user says "always ..." or "never ...".

---------------------------------------------------------------------
SECTION 6e — EPISODES AND SERIES ★
---------------------------------------------------------------------
  - Any project can be a SERIES. The Development Executive splits the
    book into episodes of the recipe's length, each with its own hook,
    arc and cliffhanger, and a "previously on" recap if wanted.
  - The continuity book, style cards, voices and picture library are
    shared by all episodes. Each episode has its own screenplay, shot
    list, clips and EDL.
  - The step path shows the episode picker at the top. "Make next
    episode" runs Autopilot on the next one.
  - PRODUCTION QUEUE: several projects or episodes can be queued to run
    one after another (or in parallel up to the provider limits), with
    the queue's total cost and an estimated finish time.

---------------------------------------------------------------------
SECTION 7 — SAME FILM, DIFFERENT STYLES
---------------------------------------------------------------------
Goal: Realistic, Claymation and Pixar-style versions must have the same
scenes, shots, framing, character positions, actions, expressions,
timing, audio and edit. Only the rendering style may differ.

7.1 Split WHAT from HOW
  - WHAT (shared, style-neutral): screenplay, continuity identity tokens,
    personality profiles, shot list, blocking, camera, lens,
    composition, action, expression, duration, seeds, audio, EDL.
  - HOW (per style): style card, the style version of each character and
    location sheet, materials, rendering, colour grade.

7.2 Style-neutral identity tokens
  Character tokens describe identity, not rendering: age, build, height
  relative to the others, face shape, hair shape and colour, eye colour,
  skin tone, outfit cut and colours, one distinctive feature. Never use
  words like "photorealistic", "clay" or "3D" in them. The Character
  Designer then writes a STYLE TRANSLATION per style ("in Claymation:
  plasticine skin with faint fingerprints, oversized hands, felt coat").

7.3 Prompt assembly (code, not AI, so it's identical for every style)
  image_prompt = style_card.prefix
               + shot.composition_and_camera      (DP, shared)
               + shot.action_and_expression       (Director, shared)
               + for each character in frame: identity_token + style_translation
               + location.identity_token + location.style_translation
               + shot.lighting_intent             (DP, shared)
               + style_card.lighting_language + style_card.suffix
  negative_prompt = style_card.negative + global negative (text, extra
                    limbs, watermarks)
  Store every part separately so the Script Supervisor can check it, and
  the picture library can reuse it (Section 6b).

7.4 Structure lock across styles
  a) Render the MASTER style first. When a frame is approved, extract and
     save its SHOT LAYOUT: depth map, pose skeletons, edge/line map,
     character bounding boxes, and the seed.
  b) Render each other style with: the same seed, the shot layout as a
     structure control (ControlNet-style depth + pose, or the provider's
     structure/reference feature), that style's character sheets as
     reference images, and the assembled prompt from 7.3.
  c) If the provider has no structure control, fall back to img2img from
     the master frame at a configurable strength (default 0.55), plus
     the style reference images.
  d) Consistency check (vision model, Script Supervisor role): compare
     each variant with its master frame for character count and
     position, pose, framing, key props, and the same visible action.
     Score 0–10; below 7 → regenerate (max 3 tries), then flag.
  e) Clips: the same motion prompt, duration and seed; the start frame is
     the style variant. If the video provider supports video-to-video
     restyling, offer "restyle the master clip" as an option.
  f) Audio and EDL are shared, so every style's cut is identical in
     timing, frame for frame.

7.5 Adding a style later
  The "Add another style" button runs only Look development, Pictures,
  Clips, Colour and finish, and the Marketing kit for the new style. It
  never re-runs writing, planning, audio or the edit.

---------------------------------------------------------------------
SECTION 8 — DATA MODEL
---------------------------------------------------------------------
8.0 Storage rules (checked against the Flova recon on 2026-11-15; details
    in replica/architecture.md, index schema in replica/schema.sql)
  - In Studio, the project folders under projects/ stay the SOURCE OF
    TRUTH. Map each entity onto the existing file where there is one
    (all_shots.csv, cast_lock.json, grading.json, shares.json ...) and add
    the rest as JSON. Don't migrate for the sake of it.
  - One SQLite file, projects/studio_index.db, holds only what can be
    REBUILT from the folders (picture-library search, moments, cost
    ledger, queue, job locks). It is rebuilt after every job. If it
    disagrees with the folders, the folders win.
  - ASSET FILES ARE IMMUTABLE. Every version gets its own file name, and
    "current" is a pointer (is_selected), never a rename or overwrite,
    so moments, archives and branches can reference files safely. Old
    takes/ and replaced/ paths are mapped through a path_alias table.
  - Every editable record carries a rev number. A save sends the rev it
    read; a mismatch returns 409 and opens the conflict prompt (6c).
  - Money is integer cents + a currency. Times are UTC. Every entity has
    created_at / updated_at.
  - Hard constraints: one selected asset per (owner, style, kind); one
    current EDL per (project, episode); one master style per project;
    one job lock per (project, episode, step, style).
  - Studio's own JOB runner (one job + a queue) stays for GPU notebooks;
    provider API calls get a small worker pool guarded by the job locks.
  - Naming: AssetGroup = one creative purpose (Flova's "asset"); Asset =
    one file version (Flova's "resource"). The new picture-library route
    is /api/picture_library (Studio's /api/library is the gallery).

Project      id, slug, title, settings(json), recipe_id, selected_products[],
             mode, master_style_id, is_series, parent_project_id
             (branch), branched_from_moment_id, owner_id, created_at,
             updated_at
Source       id, project_id, kind, title, text, image_asset_ids[],
             media_asset_ids[], metadata(json), rights_ack_at
Episode      id, project_id, number, title, logline, status
Step         project_id, episode_id, style_id (null = shared step), key,
             status, updated_at
CrewRole     key, display_name, prompt_file, model, temperature
CrewNote     id, project_id, parent_id (threads), step, role, target_type,
             target_id, author(user|role), body, round, score,
             resolved_at, created_at
Conversation id, project_id, title, closed_at, created_at
ChatMessage  id, conversation_id, author(user|producer), body, refs[],
             plan(json), accepted, moment_id, created_at
ProjectRules project_id, body, rev
Recipe       id, name, owner_id, body(json), built_in
Moment       id, project_id, label, snapshot_path, created_at, cause
Attempt      id, project_id, number, label, archived_at, kept[], snapshot_path
Coverage     project_id, logline, genre, tone, themes, characters, events
BeatSheet    project_id, episode_id, beats(json)
Treatment    project_id, episode_id, text, version
Scene        id, project_id, episode_id, number, heading, fountain,
             meta(json), rev
ContinuityItem id, project_id, kind(character|location|prop),
             name, identity_token, personality(json), invented_fields[], rev
StyleProfile id, project_id, name, is_master, style_card(json:
             prefix, suffix, negative, lighting_language, palette,
             grade_lut), example_asset_id, rev
StyleTranslation continuity_item_id, style_id, text, sheet_asset_id
Shot         id, scene_id, number, order, source(ai|footage),
             shot_type, lens_mm, camera, blocking, action, expression,
             dialogue, sound, duration_s, transition, priority,
             lighting_intent, composition, motion_prompt, seed,
             footage_asset_id, rev
ShotContinuity shot_id, continuity_item_id        (who/what is in frame)
ShotLayout   shot_id, depth_asset_id, pose_asset_id, edge_asset_id,
             boxes(json), master_asset_id
Page         id, project_id, number, text, composition, seed, rev
AssetGroup   id, owner_id, project_id, name, purpose, liked_asset_id
ShotAsset    shot_id, group_id, purpose     (one group used in many shots)
Asset        id, project_id, group_id, owner_type, owner_id, style_id
             (nullable = shared), attempt_id, kind, path (immutable),
             content_hash, version, is_selected, purpose, verdict, provider,
             model, params(json), references(json), prompt_parts(json),
             seed, consistency_score, continuity_hash, quality_tier,
             cost_cents, currency, reused_from_asset_id, created_at
PathAlias    old_path, asset_id         (takes/ and replaced/ files)
AudioLine    id, shot_id, character, text, voice_id, delivery_note, asset_id
MusicCue     id, project_id, episode_id, start_shot_id, end_shot_id,
             mood, tempo, asset_id
EDL          id, project_id, episode_id, name ("Main cut", alternative
             cuts), is_current, rev, tracks(json: video, voice, music+fx
             — each entry: asset_id, in, out, volume, fade, transition)
Job          id, project_id, episode_id, step, style_id, status,
             progress, items_total, items_done, error, retry_count,
             timestamps
JobLock      project_id, episode_id, step, style_id, job_id
QueueItem    id, owner_id, project_id, episode_id, order, status
CostLedger   id, owner_id, project_id, style_id, provider, model, units,
             quality_tier, is_regeneration, cost_cents, currency,
             idempotency_key, created_at

---------------------------------------------------------------------
SECTION 9 — PROMPT TEMPLATES
---------------------------------------------------------------------
- /prompts/crew/<role>.md holds the role definitions (Section 3.1).
- /prompts/steps/<step>.md holds the step instructions, with {{placeholders}}.
- /prompts/styles/<style>.json holds the preset style cards.
- /recipes/<recipe>.json holds the format recipes (Section 6d).
- Each call = role file + step file + recipe prompt rules + project rules
  + data. It returns JSON validated against a schema; on failure, retry
  once with the error, then show it.
- Every call is logged with its role, prompt version and model, so a
  result can be reproduced.
- A settings page lets the user edit role, style and recipe files, with a
  "reset to default" button.

---------------------------------------------------------------------
SECTION 10 — PROVIDERS AND COST
---------------------------------------------------------------------
10.1 Providers
- Adapters: TextProvider, VisionProvider, ImageProvider.generate(prompt,
  negative, aspect, seed, reference_images[], structure_controls{},
  init_image, strength, tier), VideoProvider.animate(start_image,
  motion_prompt, duration, seed, tier), VideoProvider.restyle(clip,
  style) (optional), VoiceProvider.speak(text, voice_id, delivery),
  MusicProvider.compose(mood, tempo, duration) (optional), Transcriber,
  ShotDetector.
- Each adapter declares its capabilities (seed, reference, structure,
  restyle, tiers), and Section 7.4 picks the best available method.
- A FAKE provider for every kind, so the whole site runs for free in tests.
- A queue with a concurrency limit, retries with backoff on 429/5xx
  (max 3), and a hard stop at the spending limit.
- API keys only in a server-side .env; never sent to the browser or
  logged.
10.2 Cost ★
- QUALITY TIERS: Draft (cheaper/faster models, lower resolution, used
  for previews) and Final. Any shot can be "promoted" from Draft to
  Final, keeping its seed and layout.
- The estimate is shown in DOLLARS per product, per style and per
  episode, and includes an expected-regeneration allowance (from this
  user's history, default +30%). It's also shown as GPU hours and free
  quota when free GPU services (Kaggle/Colab) are used.
- The CostLedger records actual spend, regenerations separately. The
  project page shows estimate vs. actual.

---------------------------------------------------------------------
SECTION 11 — AUTOMATION API, CLI AND MCP
---------------------------------------------------------------------
So the whole pipeline can run without the web page:
  POST /api/projects             { sources[], recipe, products[], styles[],
                                   settings, mode:"autopilot",
                                   stop_at[] } → project_id
  POST /api/projects/{id}/sources  add a file / URL / text / image / media
  POST /api/projects/{id}/run      start or resume Autopilot
  POST /api/projects/{id}/stop     stop the running job
  POST /api/projects/{id}/chat     send a Producer-chat message
  POST /api/projects/{id}/styles   add a style (runs Section 7.5)
  POST /api/projects/{id}/branch   { moment_id } → new project_id
  GET  /api/projects/{id}          status of every step and job
  GET  /api/projects/{id}/events   SSE progress stream
  GET  /api/projects/{id}/exports  download links
  POST /api/queue                  queue projects/episodes
  plus the Section 6b.4 routes.
CLI: `book2screen make <source> --recipe vertical-microdrama --style
claymation --style realistic --product film --product audiobook`.
★ MCP server: the same actions exposed as MCP tools, so an AI assistant
can drive the site. It uses the same API tokens and permission checks.
API tokens are per user, and the same security rules apply.

---------------------------------------------------------------------
SECTION 12 — BACKGROUND JOBS
---------------------------------------------------------------------
- Every AI step is a Job in a worker (RQ/Celery/arq, BullMQ, or Studio's
  existing jobs module). Work is saved after each item, so a restart
  continues where it stopped.
- The Producer role sequences the jobs in Autopilot; style variants and
  queued episodes can run in parallel up to the provider limits.
- One lock per project + episode + step + style, so two tabs never start
  the same job twice.
- Progress through SSE (polling every 3 s as a fallback). Stop, retry and
  continue buttons, which are also available from the Producer chat.

---------------------------------------------------------------------
SECTION 13 — EXPORTS
---------------------------------------------------------------------
- Screenplay: PDF (Courier 12pt, standard margins, scene numbers, title
  page), .fountain, .docx, .fdx. Coverage, beat sheet and treatment as PDF.
- Storyboard PDF per style: 6 frames per page with shot number, lens,
  action and dialogue. Plus a "style comparison" PDF: one row per shot,
  one column per style.
- Illustrated book PDF per style (print-ready, with bleed option) and EPUB.
- Animatic / Film MP4 per style and episode: ffmpeg from the shared
  EDL, 1080p (4K option), H.264 + AAC, Ken Burns move on stills, music
  ducked 12 dB under speech, crossfades on dissolves, colour grade from
  the style card, burned-in subtitles optional, plus .srt in every
  translated language.
- ★ Audiobook: M4B with chapter markers + MP3 per chapter, with a cover
  image from the poster.
- ★ Marketing kit: trailer MP4 (16:9 and 9:16), poster PNG (2:3), thumbnail
  (16:9), three teaser clips (9:16, ≤ 30 s, with burned-in captions),
  captions.txt.
- Continuity book and style cards as PDF + JSON. EDL as .edl/.fcpxml/
  .otio for professional editors.
- Private preview links that expire (Studio already has shares.py).

---------------------------------------------------------------------
SECTION 14 — SECURITY AND SAFETY
---------------------------------------------------------------------
- Accounts if more than one user, with every query filtered by owner.
- Check uploads by their contents, not only the extension, and parse
  them in a size- and time-limited worker. Fetch URLs with SSRF
  protection.
- Escape all user and AI text before showing it. Strict CSP, CSRF
  protection, and POST for every change.
- The rating is applied to every crew prompt. Provider refusals are shown
  as a friendly message.
- Data goes only to the providers in Section 0. Imported recipes are
  data, never code: validate them against a schema.

---------------------------------------------------------------------
SECTION 15 — TESTING
---------------------------------------------------------------------
- Unit tests:
  - each SourceAdapter, chunking, shot detection, schema validation
  - prompt assembly (7.3) is byte-identical across styles except for the
    style parts
  - gate and out-of-date logic, the cost estimate with tiers and the
    regeneration allowance
  - EDL reuse, recipe validation and project rules injection
- Start over and history:
  - start over keeps exactly the ticked items, and the file count before
    equals the archive plus what was kept (nothing lost)
  - restoring an archive or a moment brings back the same files and records
  - after start over + a new shot list, a shot identical to an old one
    is matched to its old picture with a score ≥ 8 and reused at no cost
  - "Use its prompt" in another style keeps the seed and layout and only
    changes the style parts
  - a changed continuity token marks the reused pictures for checking
  - a branch shares the library and doesn't duplicate any file
- Integration (FAKE providers): a 1,500-word story, a one-line idea, a
  single picture, a URL and a 30-second video each go through Autopilot
  to all seven products in TWO styles, and as a 3-episode vertical
  series. Assert:
  - the same shot count, durations and EDL for both styles
  - every crew role was called with its role file and the project rules
  - stop → add information → continue resumes without redoing finished
    items
- Real-provider smoke test (opt-in): 3 shots in Realistic + Claymation,
  with a consistency score ≥ 7 on each.
- Browser (Playwright):
  - the full path in Review mode, and Autopilot with one stop
  - the Producer chat plan → accept, and a note on a shot → revision
  - timeline drag/trim/volume, and Back to this moment
  - keyboard only, and phone width
  - a reopened step marks later steps Out of date
  - closing the tab mid-job → the job continues
  - Studio only: the Single Prompts tab still works
- Sample sources in /samples.

---------------------------------------------------------------------
SECTION 16 — STUDIO UPGRADE NOTES (when the build target is Studio)
---------------------------------------------------------------------
Studio already has these. Extend them, don't rebuild them:
  - book ingest (epub/docx/pdf)
  - the adaptation plan, screenplay, continuity book, character tokens and
    cast lock (adaptation.py, book_adapt.py, book_screenplay.py,
    book_continuity.py, character_tokens.py, cast_lock.py)
  - director's notes (studio_app/direction.py)
  - keyframes, clips, voices, mixing, grade, animatic and subtitles
    (make_*.py, mix_film.py, grade.py, make_animatic.py, export_film.py)
  - the critic pass and face check (critic.py, face_check.py)
  - takes/versions, the storyboard reset to replaced/<time>/, and
    old-picture reuse and swap (studio_app/takes.py, old_pictures.py,
    picture_record.py)
  - the budget preview (budget.py), private preview links (shares.py),
    resumable jobs (studio_app/jobs.py, resume.py), and the Kaggle /
    Colab / Hugging Face / local GPU runners
Follow the project's CLAUDE.md review rules for every changed source file.

---------------------------------------------------------------------
SECTION 17 — MILESTONES (stop after each one)
---------------------------------------------------------------------
Tick a box ([ ] → [x]) and add the date and commit only when that
milestone's tests pass, the review (CLAUDE.md) shows PASS, and I've
approved it. A partly done milestone stays unticked. Add a line under it
saying what's left.

[x] M1 (2026-11-15, 8223bc2)  Skeleton (or, for Studio, the new step path layout), FAKE
        providers, crew role files, project rules, recipes, gates,
        the studio_index.db index + reindex, rev checks (Section 8.0).
        README.
[x] MW (2026-11-15, 11ec094..7c78839; CI green on Windows, macOS, Linux) Windows support (rule 11): port the shell scripts the Studio
        calls (run_kaggle_model.sh, run_colab_model.sh, run_hf_space.sh,
        fetch_kaggle_run.sh, kaggle_names.sh) to Python; run_studio.bat and
        install.ps1; .venv\Scripts on the tool path; CI on windows-latest
        and macos-latest.
[x] MI (2026-11-15, 34bf0eb; CI builds, installs and uninstalls both) Installers for Windows and macOS (rule 12): a Windows installer
        (.exe, Start-menu and desktop shortcuts, uninstaller) and a macOS
        app (.dmg with Pistachio's Studio.app). Each shows a progress bar
        for the whole install and for the current task, with the task
        named in plain words ("Installing Python 3.12 (2 of 7)",
        "Downloading the picture tools: 145 of 610 MB", "Checking
        Kaggle"), a details log, a Cancel button that leaves nothing
        half-installed, a clear message and a "copy the log" button when
        a step fails, and a resume after a failed or cancelled install.
        Updates install over the top and keep every project.
[x] M2 (2026-11-15) Sources: every story SourceAdapter + the format/products/styles
        step.
[x] M3 (2026-11-15) READ IT IN: the full Section 5 pipeline with critique loop;
        screenplay exports (Product A complete for any source).
[x] M4 (2026-11-15) Continuity book (style-neutral, with personalities) + director's
        breakdown + shot list.
[x] M5 (2026-11-15) Style system: style cards, translations, prompt assembly, look dev.
[x] M6 (2026-11-15) Pictures in the master style + shot layouts; storyboard and
        illustrated book exports (Products B and C).
[x] M7 (2026-11-15) Other styles via structure lock + consistency check + comparison
        view.
[x] M8 (2026-11-15) Immutable asset files + path aliases for old takes/replaced
        files; start over + picture library (asset groups, versions,
        liked default, purpose labels) + reuse (Section 6b).
[x] M9 (2026-11-15) Voices, sound, music, audiobook export (Product F).
[x] M10 (2026-11-15) Timeline editor + EDL (alternative cuts) + animatic export
        (Product D, all styles).
[x] M11 (2026-11-15) Clips per style + film export (Product E, all styles).
[x] M12 (2026-11-15) Producer chat (stop / add information / continue), notes on
        anything (threads), history moments, branches, conflict prompt
        (Sections 3.4, 3.5, 6c).
[x] M13 (2026-11-15) Media sources: video/audio understanding, real footage + AI shots,
        raw-footage auto-edit, cut to music (Section 4.2).
[x] M14 (2026-11-15) Episodes, series and production queue (Section 6e); marketing kit
        (Product G).
[x] M15 (2026-11-15) Autopilot polish, cost tiers and estimate vs. actual, worker pool +
        job locks for parallel styles, automation API, CLI, MCP server.
[ ] M16 Accounts (if needed), security hardening, accessibility pass, all
        tests passing, deployment.

---------------------------------------------------------------------
SECTION 18 — DONE MEANS
---------------------------------------------------------------------
- Pressing READ IT IN on a book, an idea, a picture, a URL or a video
  gives a properly formatted, scene-numbered screenplay that a
  professional would recognise, with coverage, beat sheet and treatment.
- The log shows that every AI/GPU call was written by its crew role, with
  the project rules applied.
- One Autopilot click turns the sample story into a film in Realistic
  AND Claymation. The two films have the same shots, framing, timing,
  audio and cut, and the comparison PDF shows matching frames side by side.
- Adding a third style later re-renders only the pictures and clips.
- Start over keeps every old picture with its prompt, and the new shot
  list reuses the matching ones at no cost.
- The same book can be made as a feature, a vertical microdrama series,
  a picture book and an audiobook just by switching recipes.
- Every step can be reopened, and any moment restored or branched,
  without losing versions. All tests pass.
~~~

## Appendix A — where the ★ items came from (review of 2026-11-15)

Flova's details come from its documentation. The other three come from press releases and directory
listings, so treat them as claims.

| Capability added | Seen in | Section |
|---|---|---|
| Chat agent that plans, shows its current step, stop / add information / continue | Flova | 3.5 |
| Notes on a shot, scene or asset, referenced in the chat | Flova | 3.4 |
| Back to an earlier moment; branch to compare directions; conflict prompt | Flova | 6c |
| Reusable format recipes ("Skills") and per-project rules | Flova | 6d |
| Assets with versions, a liked version as default, purpose labels, one asset in many shots | Flova | 6b.2 |
| Understanding uploaded video/music/audio; extracting clips, frames and audio as references | Flova | 4.2 |
| AI shots added to real footage | Flova | 4.2 |
| Three-track timeline editor (video, voice, music) | Flova, Story.com | 6 (Edit) |
| Raw footage → story with smart cuts | Story.com (Instamovies) | 4.2 |
| Storybook output, vertical/social formats | Story.com | 1, 6d, 13 |
| Draft/final quality tiers | Story.com | 10.2 |
| Characters with personalities | Story.com (Character Studio, announced) | 3.2, 8 |
| Dollar estimate for a whole book, including regenerations | Creatorwood | 10.2 |
| Episodes / series | Creatorwood, Inkitt | 6e |
| Volume production queue for microdrama series | Inkitt | 6e |
| Audiobook from the same book | Inkitt | 1 (F), 13 |
| Marketing assets (trailer, poster, teasers) | Inkitt (AI influencer framework, announced) | 1 (G), 13 |
| MCP server for creators | Inkitt | 11 |

Left out on purpose: a streaming storefront with payments and revenue share (Creatorwood, Inkitt), fan
crowdfunding of compute (Inkitt), predicting hit stories from reader data (Inkitt ReadRank), and team workspaces.

Sources: [Flova – How Flova Works](https://flova.ai/docs/en/How_Flova_Works),
[Flova – Agent](https://flova.ai/docs/en/features/agent),
[Flova – Project content editing](https://flova.ai/docs/en/features/project-content-editing),
[Indie Author Magazine – Creatorwood.TV](https://indieauthormagazine.com/creatorwood-tv-revolutionizing-storytelling-with-ai-generated-films/),
[EveryDev – Story.com](https://www.everydev.ai/tools/story-com/llms.txt),
[TechFinancials – Inkitt launches Ironblood](https://techfinancials.co.za/2026/07/15/inkitt-launches-ironblood-proving-ai-can-now-produce-hollywood-grade-spectacle-at-streaming-speed/),
[VentureBeat – Inkitt's custom AI video harness](https://venturebeat.com/technology/should-your-enterprise-build-a-custom-ai-harness-inkitt-did-for-ai-video-5-key-takeaways).
