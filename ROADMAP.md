# Roadmap: from a personal tool to a usable book-to-film website

Written 2026-11-09 from a review of the code and the one finished project (`projects/books/genesis_film`: 12 clips, about 60 seconds).
The review read the code and its output; it did not run the Studio in a browser. "Untested" below follows the README's own notes.

## Where Studio is today

The back end works end to end: PDF or text, chapters, continuity book, shots, keyframes, video, narration, music, mixed MP4.
It is a single-user tool on localhost, driven by Kaggle's free GPUs, with a developer-style interface. Nobody has made a full short or feature with it.

## Gaps found

| Area | Gap |
|---|---|
| Input | Scanned PDFs are rejected (`book_ingest.py` asks for `ocrmypdf`); no EPUB, DOCX or HTML; chapters found by regex only, no way to fix them in the page |
| Adaptation | No treatment, acts or scene list; no screenplay to read or approve before GPU time; long books cannot be condensed to a target runtime |
| Video | Clips are 4-5 s; about 106 s of T4 time per 4 s clip (about 40 GPU hours for 90 minutes); Pika path is 3-4 clips a day and licence-restricted; continuous action and upscalers untested; prompts truncated at 256 tokens in the sample run |
| Consistency | Two ages of one character not guaranteed; face check works for photoreal looks only; outfits and props rely on text tokens |
| Audio | Voice-over on silent clips, no lip-sync; Chatterbox has one voice for all speakers; SFX experimental; music is 15-28 s looped cues |
| Editing | Basic timeline only (trim, reorder, fades); no multi-track, overlapping audio, credits or grading; no per-shot approve and re-roll workflow; no critic pass |
| Product | Not a website: no accounts, hosting, sharing or watch page; Kaggle, Hugging Face and Claude Code setup; one job at a time (`jobs.JOB`); 8 tabs and 9 steps in developer language |
| Legal | No rights check on the source book; model licences not recorded; no distribution presets |

## Phases

### Phase 1: input and adaptation
- [x] Built-in OCR for scanned PDFs (`scripts/book_formats.py`: page by page, only pages with no text; tesseract if installed, otherwise `rapidocr` + `onnxruntime` added by the Read step; needs Python 3.11-3.13). `scripts/check_ocr.py` self-test: rapidocr read 37 of 38 words here; tesseract is not installed on this Mac, so that path is unrun (install steps in `docs/CHECKING_YOUR_SETUP.md`).
- [x] EPUB, DOCX and HTML input (split on the file's own chapters; cover, copyright and notes set aside). Tested on files built by the tests; a real publisher EPUB is still to be tried (`python3 scripts/check_book_file.py book.epub` shows how it is read).
- [x] Chapter editor in the page: merge, split, rename, drop front matter (Chapters card; `scripts/chapter_edit.py`).
- [x] Adaptation stage: logline, treatment, acts, scene list, with a target runtime that drives how much is kept. Built: `book_adapt.py`, see `adr/0005-adaptation-stage.md`.
- [x] Editable screenplay (scene headings, action, dialogue), approved before any generation (`screenplay.py`, Film plan card; the run plan is refused until it is approved).
- [x] Budget preview for the chosen book and runtime (`budget.py`; only the LTX fast T4 time is measured, the other rates are assumptions in `budget_rates.json`): clips needed, GPU hours, cost, days of quota; "pilot first" option (trailer or one chapter).

### Phase 2: picture quality and review
- [x] Storyboard grid and animatic with approve, reject and re-roll per shot; prompts hidden by default (`scripts/review.py`, Storyboard card; `Run critic` can reject the shots it flags).
- [x] Locked cast, location and costume references per scene (`scripts/cast_lock.py`, Film plan card; used by the prompts and the keyframe pictures).
- [x] Fix prompt truncation: the shot description now comes first and the whole prompt is kept under an estimated 240 tokens (`bookkit.compose_prompt`; `Build CSVs` has a rewrite option for existing books). The estimate is calibrated on the genesis_film log, not on the model's own tokenizer.
- [ ] Test continuous-action chaining, upscalers and the stylised-look face check on a GPU, then mark them supported or remove them. Step-by-step procedure written: `docs/PHASE2_GPU_TESTING.md` (not run: no GPU here).
- [x] Critic pass (`scripts/critic.py`): pacing, shot variety, face check, dropped characters, runtime against the plan, short clips; flags shots in the review. Outfit changes and picture/sound sync are not checked (they need a vision model or audio files).

### Phase 3: sound
- [x] A distinct voice per character with emotion and pacing direction (`scripts/voices.py`; Voice cast panel: "Give everyone a different voice", delivery and speed per speaker). Kokoro has no emotion control, so an emotion is a speed and a pause, not a different tone of voice. Kokoro narration has run on Kaggle before (owner); the per-speaker speed/pause path has not.
- [~] Real SFX and ambience: AudioLDM 2 added next to MMAudio (`make_audio.py`, diffusers `AudioLDM2Pipeline`). Licence CC BY-NC-SA 4.0 (non-commercial). AudioLDM 2's call was run once on a CPU (3 s of sound, 10 steps) and produced audio; neither model has run on a GPU, so MMAudio's "experimental" label stays.
- [x] Scored music that follows scenes instead of looped cues (`audio_scenes.csv`, `mix_film.py --music-scenes`: one cue per scene, crossfaded). MusicGen has run on Kaggle before (owner); the per-scene cue run has not.
- [x] Lip-sync for close-ups: the page ticks only the close-ups where a character speaks (`critic.lipsync_rows`); the lip-sync model (MuseTalk) itself is still untested on a GPU.

### Phase 4: editor and delivery
- [~] Multi-track audio, titles and credits: extra audio tracks laid over the film at any time (`mix_film.py --tracks` / `tracks` in a selection; ambience across a cut, stings, a voice-over spanning shots), music crossfaded between scenes, and a rolling credits sequence (`credits.py`, Export and credits card). The page's timeline itself is still one lane: tracks are given in a file, not dragged.
- [x] Export presets (`scripts/export_film.py`): YouTube 1080p and 4K, festival screener, ProRes 1080p and 4K masters, vertical short, small web copy; soft subtitle tracks (the film's captions plus AI-translated languages, each checked to keep every cue) and dubbed audio tracks you supply. A 4K master from small clips is the same picture scaled up.
- [x] Per-scene colour grading beyond "match colour" (`scripts/grade.py`: presets plus exposure, contrast, saturation, warmth and tint per scene and a default; `mix_film.py --grade`).

### Phase 5: make it a website
- [~] Hosted web app. Accounts and storage are skipped by decision. Built: private preview links and a watch page (`scripts/shares.py`, Export and credits card) and a job queue (jobs wait their turn and share one log; still one at a time). Not built: accounts and storage, and jobs truly in parallel. Design in `adr/0006-hosting-and-gpu-providers.md`.
- [~] GPU backend choice: the Models tab now separates **This computer** (already there), **Free, external** (Kaggle, Colab, Hugging Face) and **Paid, external**, a list of 17 providers marked *unproven* (`studio_app/providers.json`, shown from `/api/providers`). Paid providers cannot be chosen: no adapter exists and none has been tried. Likely route to try first: rent a machine, run the Studio on it and use it as "This computer".
- [x] One project flow: seven guided screens (Book, Plan, Cast and look, Storyboard, Shoot, Cut, Premiere; `web/static/js/flow.js`) each showing only the cards of that stage, with Back/Next and the progress rail wired to them. "All tabs" returns to the classic four-tab layout; Models, Single Prompts, Library and Compare stay under Advanced. Checked in jsdom, and the owner reports the page works in a browser.
- [x] Reconsider the adult-content model groups in the default catalogue: hidden and refused until switched on (Models tab, or `STUDIO_ADULT_MODELS=1`).
- [ ] (Not needed while accounts are skipped.) Keep the existing security model in mind: the localhost-only design (ADR 0003) must be replaced by a real multi-user one before anything is hosted. Not done: ADR 0006 proposes one Studio process per account behind a login gateway. The watch links are the only part meant to face other people, and they open one film each.

### Phase 6: rights and release
- [ ] Ask for the source book's rights status; warn when it is not public domain.
- [ ] Record each model's licence per project and warn before commercial export (Pika H3 already restricts this).
- [ ] Credits and content-rating fields.

## Order of work

1. Phase 1 (nothing else matters if the story is not adapted well).
2. Phase 2 and 3 in parallel.
3. Phase 4, then Phase 5 (hosting is the largest single piece and depends on the others being stable).
4. Phase 6 before any public release.

## Success test

A producer with no developer tools uploads a scanned public-domain novel, approves a screenplay and a budget, reviews a storyboard, and gets back a 10-minute film with distinct voices, music that follows the story and consistent characters, plus a link to share.
