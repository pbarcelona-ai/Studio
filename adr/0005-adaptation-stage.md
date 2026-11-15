# ADR 0005 – Adaptation stage (logline, treatment, acts, scene list)
Status: accepted, implemented (ROADMAP Phase 1, items 4-6)

**Context.** Today the pipeline goes chapter -> shots (`book_write.py`): every chapter gets shots in proportion to its word count, so a 200,000-word novel
becomes a 200,000-word film. Nothing decides what the story *is*, what can be left out, or how long the film should be. The screenplay (item 5) and the
budget preview (item 6) both need that decision to exist first, as data.

**Decision.** Add a stage between "Read book" and "Continuity book" that turns the chapters into a plan sized to a target runtime.

*Inputs:* `chapters/chapter-NNN.txt` (and the chapter editor's corrections), `runtime_minutes` (default 10; 1-180), `clip_seconds` (default 4), optional
`focus` (a character, a thread or a chapter range the film must follow) and `pilot` (`none` | `trailer` | `chapters:A-B`).

*Outputs, all under `projects/books/<book>/adaptation/` (plain files, per ADR 0002):*
- `summaries/chapter-NNN.json`: per chapter `{summary, characters, locations, beats[], importance 1-5}`. Cached; only changed chapters are redone.
- `adaptation.json`: `{logline, premise, ending, runtime_minutes, acts[{name, purpose, seconds}], scenes[...]}`.
  A scene is `{id, act, title, chapters[n..], source_quote_range, summary, location, characters[], time_of_day, seconds, keep: "full"|"condensed"|"montage"}`.
- `treatment.md`: the same plan as readable prose (about 1 page per 10 minutes), regenerated from `adaptation.json`, never edited directly.

*Script `book_adapt.py <book> --minutes N [--pilot ...] [--engine ... --model ...]`*, same engine plumbing as `book_continuity.py` / `book_write.py`:
1. **Summarise** each chapter (parallel, `--workers`, cached). One call per chapter keeps every call inside the model's context for a long book.
2. **Shape** (one call): from the summaries and chapter word counts, write the logline, premise, ending and three or more acts with a share of the runtime each.
3. **Select scenes** (one call per act): choose scenes in book order, each pointing at real chapters, with `seconds` and a `keep` mode. `montage` is how
   many chapters are compressed into a few shots; dropped chapters are listed with a reason in `adaptation.json["cut"]`.
4. **Fit** (deterministic code, no model): validate and, if the total is more than 10 % off `runtime_minutes * 60`, scale each scene's `seconds`
   by importance, then round to whole clips. Fail with a readable message when a rule cannot be met (scene points at a chapter that does not exist,
   chapters out of order, an act with no scenes). `seconds` always ends as a multiple of `clip_seconds`.
5. **Render** `treatment.md`.

*Relation to the existing pipeline.* When `adaptation.json` exists, `book_write.py` takes its shot count per scene from `seconds / clip_seconds` instead of
`words_per_shot`, and the `--scenes` finder is skipped (the scenes are already known). Without it nothing changes, so existing books keep working.
The continuity book reads the logline and acts as extra context. The screenplay (item 5) is written per scene; the budget preview (item 6) is
`sum(scene.seconds) / clip_seconds` clips times the per-model seconds-per-clip figure.

*Page.* A new "Adapt" card after Read book: runtime and pilot controls, a Run button, then the logline, acts and an editable scene table (reorder,
change seconds, drop, merge). Editing a scene writes `adaptation.json` and marks the screenplay for that scene stale. Approval is item 5's gate.

*API.* `GET /api/adaptation?project=` (the file or `{exists:false}`), `POST /api/adaptation_edit {project, action, ...}` for table edits,
and the run itself is a normal job step (`steps.py`), so the existing job panel, stop button and log are reused.

**Consequences.**
- Cost: roughly one call per chapter plus 1 + acts calls. A 40-chapter novel is about 45 calls once, then free to re-fit when only the runtime changes
  (steps 1-2 are cached; 3-4 rerun).
- Editing chapters (items 1-3) after adapting makes scenes point at the wrong chapters; chapter edits therefore mark `adaptation.json` stale
  (`"stale": true`) and the page asks to re-run step 3 only.
- Quality depends on summaries; very long chapters are summarised in slices of about 6,000 words and merged.
- The model may invent scenes. Every scene must name chapters and a `source_quote_range` (first and last sentence index), and the fit step rejects scenes
  that cite none, so the screenplay stays traceable to the book.

**Open questions.**
1. Should `focus` be a hard filter (drop other threads) or a weighting? Proposed: weighting, with a warning when a chapter's importance is 5 and it was cut.
2. Where does a feature (90 min) split into acts when chapters are 1-2 pages? Proposed: acts are chosen from summaries only, never from chapter numbers.
3. One engine for all steps or a cheaper model for summaries? Proposed: `--summary-model` optional, defaulting to the same model.
4. Trailer pilot: pick scenes by importance only, or require a hook/ending shape? Proposed: importance, plus the first and last scene of the film's act 1.

**As built (differences from the draft above).**
- Code: `scripts/adaptation.py` (checks, fitting, editing, pilots), `book_adapt.py`, `screenplay.py` + `book_screenplay.py` (item 5), `budget.py` + `budget_rates.json`
  (item 6), the page card in `web/static/js/adapt.js`, routes in `studio_app/adapt.py`.
- Very long chapters are summarised from their beginning, middle and end (about 5,000 words in all), not in slices that are merged.
- Scenes out of book order are allowed (flashbacks) and are not an error; chapters out of range, missing anchors and unusable numbers are.
- A scene's starting phrase that is not found in the book text is flagged on the scene (`anchor_found: false`), not rejected, because models paraphrase.
- A new plan deletes the old screenplay (its scenes are gone). Editing the plan keeps the screenplay of scenes that stay and deletes it for dropped and joined scenes.
- Approval is stored as a hash of each scene's text; any edit, a missing scene or a new plan makes `screenplay.gate()` refuse `write`, `build`, `keyframes`, `video`, `audio`,
  `merge` and `mix` (in `studio_app/steps.py`). A book with no plan is not gated, so the old chapter-by-chapter flow still works.
- Planning and generating cannot be in the same run: the approval has to happen between them.
- A trailer pilot takes the most important scenes in story order up to the given seconds and always the first scene; a chapters pilot takes the scenes taken only from that range.
  `book_write.py` writes only the active (pilot) scenes' chapters; the budget prices the pilot and the whole film side by side.
