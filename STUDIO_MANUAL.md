# Pistachio's Studio — Complete User Manual

Welcome to **Pistachio's Studio**, a local-first AI Book-to-Film Production Studio. Everything runs on your own computer (with optional cloud GPU or API acceleration), turning books, stories, scripts, and ideas into continuity-locked screenplays, storyboards, 3D previs, voiced dialogue, musical score, video clips, timelines, and finished films.

---

## 1. Getting Started & First-Time Setup

### Launching Studio
- **Windows:** Double-click `run_studio.bat` in the Studio folder (or run `.venv\Scripts\python.exe scripts\studio.py`).
- **macOS / Linux:** Run `./run_studio.sh`.
- Studio starts a local server on `127.0.0.1` (default port `8765`), automatically starts local **ComfyUI** if installed in `.local_ai/ComfyUI`, and opens your browser with a one-time session token.

### Setup Window (`⚙` in the top-right header)
1. **Local GPU (Recommended if you have an NVIDIA GPU):** Select **Local GPU** in Step 13 or the Models tab to run `sd-cli`, ComfyUI, Wan 2.2 / Wan2GP, Kokoro-82M TTS, and Ollama Vision QA at \$0 cost.
2. **Free Local Vision QA & Prompt Writing (Ollama):** With Ollama running and `qwen2.5vl:7b` / `gemma3:12b` pulled, Studio checks keyframe physics and room continuity locally with no paid Vision API needed.
3. **Optional Cloud Providers:** Paste keys in **Setup (`⚙`)** for Kaggle (free weekly GPUs), Hugging Face, Gemini API, or Fal.ai. Keys stay strictly on your own computer in `~/.pistachios_studio/settings.json`.

---

## 2. Projects & the Menu Bar

The desktop-style **Menu Bar** sits at the very top of Studio and gives you single-click and keyboard-shortcut control over projects, editing, views, and help.

### File Menu
- **New Project (`Ctrl+N`):** Opens the **New Project** dialog. Enter any custom **Project Name** (e.g., *Saturn Rocket Director's Cut*) and associate it with a **Book / Source Input** (choose a book from `books/`, or type/paste a new story). Studio creates an isolated folder under `projects/books/<slug>/` with a `project.json` manifest linking the project to its source book.
- **Open Project (`Ctrl+O`):** Opens a searchable list of all named projects and library books. Selecting a project automatically loads it, associates its linked input book, restores its last active step, and updates the active project indicator on the menu bar.
- **Save (`Ctrl+S`):** Saves your current project metadata (`project.json`), active step, and creates a timestamped project history snapshot (`history/moments.json`) so you can safely undo/redo later.
- **Save As (`Ctrl+Shift+S`):** Duplicates your current project (screenplay, continuity book, shots, look development, edits, and assets) under a new custom Project Name without overwriting the original. Great for alternate cuts, alternate visual styles, or darker/lighter endings.
- **Exit (`Ctrl+Q`):** Prompts for confirmation, cleanly stops running jobs, shuts down managed local ComfyUI and the Studio server, and displays a safe-to-close confirmation screen.

### Edit Menu
- **Undo (`Ctrl+Z`):** Context-aware. Inside any text box or editor, performs standard text undo. Outside text fields, steps backward one snapshot in Studio's project history.
- **Redo (`Ctrl+Y` or `Ctrl+Shift+Z`):** Context-aware text redo inside text fields, or steps forward through Studio's project snapshots.
- **Copy (`Ctrl+C`) / Paste (`Ctrl+V`):** Copies selected text to your clipboard or pastes clipboard text into the focused input field.
- **Goto Step (`Ctrl+G`):** Opens the **Goto Step** dialog showing all 22 pipeline steps grouped by phase. Type a step number (`1`–`22`) or keyword and press **Enter** to jump straight there.

### View Menu
- **Pipeline (`Ctrl+1`):** Returns to the 22-step guided Book-to-Film pipeline view.
- **Creative Workbench ▸:** Opens any of the 5 Creative Workbench panels directly:
  - **ComfyUI Apps Gallery** — 120 local GPU workflows (`apps/`)
  - **Canvas & Compare View** — Mask inpainting painter and side-by-side model comparison
  - **Models & Hardware** — Local GPU VRAM monitor, model catalog, and cloud providers
  - **Single Prompts** — Standalone text-to-image and text-to-video prompt runner
  - **Prompt Library** — Saved prompt presets and style recipes

### Help Menu
- **Manual (`F1`):** Opens this searchable, moveable **Studio Manual** dialog (with an **Open in New Tab** option).
- **About Pistachio's Studio:** Shows Studio version, installed open-source tool count, and project info.

### Keyboard Shortcuts Reference

| Shortcut | Action |
|---|---|
| `Ctrl+N` | File → New Project |
| `Ctrl+O` | File → Open Project |
| `Ctrl+S` | File → Save (snapshot + metadata) |
| `Ctrl+Shift+S` | File → Save As (clone project) |
| `Ctrl+Q` | File → Exit Studio cleanly |
| `Ctrl+Z` | Edit → Undo (text or project snapshot) |
| `Ctrl+Y` / `Ctrl+Shift+Z` | Edit → Redo (text or project snapshot) |
| `Ctrl+C` / `Ctrl+V` | Edit → Copy / Paste |
| `Ctrl+G` | Edit → Goto Step (1–22) |
| `Ctrl+1` | View → 22-Step Pipeline |
| `F1` | Help → Studio Manual |
| `Ctrl+K` | Command Palette |
| `Esc` | Close active menu or popup |

> **Tip — Moveable Popups:** Every modal, dialog, manual window, and floating panel in Studio can be dragged anywhere on screen by its title bar. **Double-click** any popup's header to snap it back to its default centered position.

---

## 3. The 22-Step Guided Production Pipeline

Studio is organized into **6 Production Phases** containing **22 sequential steps**. Each step has an approval/next dock at the bottom and keeps downstream steps synchronized whenever you revise earlier work.

### Phase 1: Story & Script (Steps 01–06)
1. **Step 01 — Ingest & Source:**
   - Choose or create a Project (`File → New Project` or select from the Library dropdown).
   - Write/paste story text directly, select a book from `books/`, or upload a `.pdf`, `.epub`, `.docx`, `.txt`, `.fountain`, or `.fdx` file.
   - Optional: Use **Firecrawl MCP Research** for comparable films or script structure notes, or press **Make Full Film (1-Click Autopilot)** to run the entire pipeline automatically.
2. **Step 02 — Check & Split Chapters:**
   - Inspect how your source book was divided into chapters. Rename chapters, drop front/back matter (cover, contents, acknowledgments), merge sections, or click inside text and press **Split** to adjust chapter boundaries.
3. **Step 03 — Coverage & Logline:**
   - Generate studio script coverage, logline, synopsis, tone notes, and audience rating. Resolve any flagged `[Needs Decision]` items using **Resolve Decisions**.
4. **Step 04 — Format & Runtime Scope:**
   - Choose your target format (Feature Film, Short Film, Vertical Microdrama, Illustrated Book, Animatic, Trailer, Audiobook, Music Video), aspect ratio (`16:9`, `2.39:1`, `9:16`, `4:3`, `1:1`), and target runtime.
5. **Step 05 — Story Structure & Beats:**
   - Review the Act-by-Act beat sheet and scene pacing derived from your book. Edit beats or resolve continuity advisories before drafting the script.
6. **Step 06 — Screenplay Editor & Trelby Round-Trip:**
   - Edit individual scenes or view all scenes together. Use **Humanize Script & Dialogue** to polish natural speech and **Audit Screenplay Continuity** to catch prop/location contradictions early.
   - **Trelby Integration:** Click **Open in Trelby** to auto-export `.fdx` and `.fountain` and launch local **Trelby** for dedicated screenplay editing. When finished, click **Import .fdx / .fountain** to bring your revisions straight back into Studio.

### Phase 2: Cast & World (Steps 07–11)
7. **Step 07 — Continuity, World Rules & Props/Backdrops:**
   - Define immutable **Project Rules** (e.g., *"Eve never wears red"*, *"No modern cars"*) that every AI crew member obeys.
   - Extract, edit, or upload visual references for dynamic **Props & Backdrops** (hand props, vehicles, sky/viewscreen backdrops). Imported photos trigger bi-directional visual prompt sync.
8. **Step 08 — Cast & Characters:**
   - Lock visual character tokens (age, build, hair, wardrobe, distinguishing features) and optional life stages.
   - Click **3D Cast Scale Lineup (Blender)** to render a true-to-scale height reference of adults, children, pets, and props.
9. **Step 09 — Art Direction & Style Recipe:**
   - Select or customize your film's visual style (e.g., *Pixar 3D*, *Live Action 35mm*, *Claymation*, *Anime*, *Oil Painting*) with positive and negative style keywords applied consistently across every render.
10. **Step 10 — Look Development & Turnarounds:**
    - Generate 4-angle character turnaround sheets (Front, 3/4, Profile, Back) and lock each character's canonical face/identity.
    - Use **3D Turnaround Guides (Blender)** or **Launch Blender Live** for true-scale 3D sculpting/blocking.
11. **Step 11 — Static Sets:**
    - Lock every permanent room and environment. Render consistent **5-angle 3D Set Plates** (Wide, Reverse, Corner, Over-the-Shoulder, Top-Down) from one Blender 3D room so backgrounds stay coherent across cuts.

### Phase 3: Camera & Compute (Steps 12–13)
12. **Step 12 — Shot List & Cinematography:**
    - Review and refine every scene's shot-by-shot camera plan (framing, lens, movement, duration, transitions).
    - Render **3D Previs (Blender)** stills or a **3D Animatic MP4** to verify camera blocking before generating AI visuals.
13. **Step 13 — Hardware & Where to Run:**
    - Choose between **This Computer (Local GPU)** (`ComfyUI`, `sd-cli`, `Wan 2.2`, `Wan2GP`, `Kokoro-82M`, `FFmpeg`) or cloud compute (Kaggle, Colab, Hugging Face Spaces, Gemini API, Fal.ai).

### Phase 4: Audio & Voices (Steps 14–16)
14. **Step 14 — Voice Casting & Dialects:**
    - Assign distinct voices, accents, and delivery notes to every speaking character and narrator (local **Kokoro-82M** or optional **F5-TTS** voice cloning).
15. **Step 15 — Spoken Dialogue Delivery:**
    - Render individual dialogue WAV tracks, audition each line, adjust pacing or pronunciation, and re-render single lines cleanly.
16. **Step 16 — Score & Foley Sound Design:**
    - Generate per-scene or per-chapter musical score cues and foley/ambient sound effects (local **MusicGen**, **ACE-Step 1.5**, or cloud audio).

### Phase 5: Visuals & Motion (Steps 17–19)
17. **Step 17 — Storyboard Keyframes:**
    - Generate locked keyframes per shot using character turnarounds, set plates, and optional **Blender 3D Scale & Depth Guides**.
    - Use **Free Local Engines** (`FLUX.1 Kontext Dev`, `FLUX.2 Klein`, **Ollama Vision QA**, **ComfyUI Angles**) and **Mask Inpaint** (in Canvas Studio) for pixel-identical background edits.
18. **Step 18 — Motion & Video Synthesis:**
    - Animate keyframes into video clips using **Wan 2.2 Diffusers**, **Wan2GP**, **ComfyUI**, **Gemini API**, or motion animatics.
    - Render optional 3D extruded title cards via Blender or programmatic graphics via **Remotion** / **HyperFrames**.
19. **Step 19 — Lip-Sync & Polish:**
    - Configure lip-sync synchronization (cloud or local **LatentSync**), AI upscaling (**Real-ESRGAN**, **FlashVSR**, **SeedVR2**), and temporal deflickering.

### Phase 6: Post & Premiere (Steps 20–22)
20. **Step 20 — Sequence Timeline Assembly:**
    - Review video, dialogue, and score/foley tracks, set crossfade durations, run **Pre-Render QA Check**, and assemble cuts using **FFmpeg**, **Remotion**, **HyperFrames + Ink Theater**, or **Blender 3D World**.
21. **Step 21 — Audio Stem Mix (`-16 LUFS`):**
    - Balance Dialogue, Foley, and Score levels with sliders, toggle automatic music ducking under speech, and normalize to broadcast loudness (`-14` / `-16` LUFS).
22. **Step 22 — Cinema Premiere & Multi-Format Export:**
    - Watch your assembled film in the Cinema Theater player.
    - Export **16:9 Master MP4**, **9:16 Vertical Shorts** (with Face-Tracked Auto-Reframe, Silence Cutter, and Frame-Snapped Safe-Zone Captions), **Master Audio WAV**, **Fountain Screenplay**, **Pitch Deck (`.pptx`)**, and **Production Breakdown (`.xlsx`)**.
    - Open the **Pro Studio NLE, Open-Source Tools & Stems Console** to export **Kdenlive (`.kdenlive`)**, **OpenTimelineIO (`.otio`)**, **CMX 3600 EDL**, and uncompressed **WAV Stems ZIP**, or launch installed open-source tools directly.

---

## 4. Creative Workbench

Access via **View → Creative Workbench** (or the workbench dropdown):
- **ComfyUI Apps Gallery:** Browse, search, and run 120 pre-configured local GPU ComfyUI workflows (camera angles, relighting, character swap, VFX clean plates, upscaling, posters) and send outputs straight into your active project.
- **Canvas & Compare View:** Paint precise inpainting masks over keyframes to change only one region while keeping the rest pixel-identical, or rate model outputs side by side.
- **Models & Hardware:** Monitor GPU VRAM, verify installed local models, and manage cloud API tokens.
- **Single Prompts & Prompt Library:** Run quick one-off experiments and save reusable prompts.

---

## 5. Open-Source External Tools & GitHub Auto-Updates

Studio automatically detects and integrates your installed open-source suite (visible in Step 22's **Installed Open-Source Studio Tools** panel):
- **Screenplay & Docs:** Trelby (`.fdx`/`.fountain`), Pandoc, Calibre
- **3D & Art:** Blender 5.4 (headless & Live MCP), Krita (works with local ComfyUI), Darktable
- **Video & Subtitles:** Kdenlive (`.kdenlive`), OpenTimelineIO (`.otio`), FFmpeg, HandBrake CLI, Subtitle Edit, WhisperX
- **Audio & Voice:** Audacity, Demucs, Kokoro-82M, F5-TTS, ACE-Step 1.5
- **Local AI Engines:** ComfyUI, `stable-diffusion.cpp` (`sd-cli`), Wan2GP, LatentSync, Ollama

### GitHub Update Notifications
- Studio tracks all installed GitHub repositories (`.local_ai/ComfyUI`, `Wan2GP`, `ACE-Step-1.5`, `LatentSync`, and any future clones) plus GitHub-released tools (`Pandoc`, `HandBrake CLI`, `Audacity`, `Darktable`, `Subtitle Edit`, `Calibre`, `Ollama`, `Trelby`, `sd-cli`).
- When an update is available, a moveable popup notifies you (**"There is an update for `<Name>`"**) with **Update**, **Don't Update**, and **Update All** actions.
- Toggle **🔔 GitHub Update Notifications** ON or OFF anytime inside the popup or in the Step 22 tools bar; click **🔄 Check GitHub Updates** to force a fresh check at any time.

---

## 6. Producer Chat, History & Troubleshooting

- **Producer Chat (bottom-right floating panel):** Ask for creative changes in plain language—nothing executes until you approve. Drag its title bar to move it out of the way.
- **History & Undo/Redo:** Every `File → Save` (`Ctrl+S`) and approval creates a lightweight snapshot in `projects/books/<slug>/history/`. Use `Ctrl+Z` / `Ctrl+Y` to step backward and forward safely.
- **Troubleshooting:**
  - *Page says "Forbidden":* Reopen the tokenized URL printed in the terminal when Studio launched.
  - *Ollama Vision QA shows offline:* Start Ollama (`ollama serve` or launch the Ollama app) so `127.0.0.1:11434` responds.
  - *Out of GPU VRAM:* Switch heavy video models to `Wan2GP` or quantized GGUF `sd-cli` models, or pause other GPU apps.
  - *Popup dragged near screen edge:* Double-click its header to re-center it immediately.
