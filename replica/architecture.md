# Architecture: Studio v3 (the Book to Screen plan, with Flova's core features added)

Purpose of this pass: check **Section 8 (data model)** of `BOOK_TO_SCREEN_BUILD.md` against the Flova recon
(`replica/recon.md`, `replica/features.csv`) and against how Studio actually stores things today. The fixes found here have
been written back into Section 8 of the plan.

Date: 2026-11-15

## Stack (Studio's, kept as-is)

The default replica stack (Next.js, Supabase, Stripe, Vercel) doesn't apply. Studio is a working single-user app, so the
rebuild keeps its stack.

| layer | choice | why |
| --- | --- | --- |
| web | Python stdlib `ThreadingHTTPServer` (`scripts/studio_app/server.py`, `handler.py`, `routes_get.py`, `routes_post.py`) + plain JS modules in `web/static/js/` | already built and tested; no build step |
| storage (source of truth) | project folders under `projects/` (JSON, CSV, Fountain, media files), via `scripts/layout.py` | portable, easy to back up, read by every script and notebook |
| index (new) | one SQLite file, `projects/studio_index.db`, **derived** from the folders and rebuildable at any time | cross-project picture-library search, moments, cost ledger, queue: things files are slow at |
| auth | the Studio token (existing); per-user accounts only if it's ever hosted (v3 §14) | single user today |
| payments | none | not a store (Flova's credits are out of scope) |
| email | none | — |
| jobs | `scripts/studio_app/jobs.py` (one running job + a queue of 10), extended with locks per project/episode/step/style | the existing resume/attach logic is worth keeping |
| GPU | Kaggle / Colab / Hugging Face / local runners (existing) + provider adapters (v3 §10) | already built |
| hosting | local (`python3 scripts/studio.py`) | the owner runs it on their own machine |

**Storage decision.** Section 8 is a logical model, not a requirement to move into a database. Each entity is stored in a
project-folder file. SQLite holds only indexes and logs that can be rebuilt from the folders (`python3 scripts/reindex.py`).
If the index is deleted, nothing is lost. This avoids a risky migration of every existing book.

## Section 8 check: findings and fixes

| # | finding | severity | fix (written into Section 8) |
| --- | --- | --- | --- |
| A1 | Money is stored as `cost_usd` floats | high | `cost_cents integer` + `currency` |
| A2 | Moments "reference files, not copies", but Studio overwrites `image-0001.png` and moves the old one into `takes/`, so a path saved in a moment points at the wrong picture later | **high** | asset files are **immutable**: every version gets its own file name (content hash or `-v<n>`), and the "current" picture is a pointer (`is_selected`), never a rename. Existing take moves keep working through a path alias table during migration |
| A3 | Nothing stops two pictures being "selected" for the same shot and style | high | unique: one selected asset per (owner shot/page, style, kind) |
| A4 | No concurrency guard: the Producer chat (Flova runs agent and manual edits in parallel) and the user can edit the same scene/shot; Section 6c promises a conflict prompt but there's nothing to detect a clash with | high | a `rev integer` on every editable record (Scene, Shot, Page, ContinuityItem, ProjectRules, EDL, StyleProfile); writes send the rev they read, and a mismatch → conflict prompt |
| A5 | `AssetGroup.used_by_shot_ids[]` array: can't index it or keep it consistent when shots are deleted | med | join table `ShotAsset(shot_id, group_id, purpose)`, with `on delete cascade` from Shot |
| A6 | EDL has one timeline per episode; Flova keeps several timelines per Edit (alternative cuts) | med | `EDL.name` + `EDL.is_current`; at most one current EDL per (project, episode) |
| A7 | Notes are flat; Flova has multi-turn threads on a comment | med | `CrewNote.parent_id` |
| A8 | `ChatMessage` has no conversation; multiple conversations per project are on the could-list | low | `Conversation(id, project_id, title, closed_at)`; `ChatMessage.conversation_id` |
| A9 | `Step` has no style, but Look development, Pictures, Clips, Colour and Marketing run once per style | med | `Step.style_id` (null = shared step) |
| A10 | The generation settings aren't fully recorded (model name and params missing), so "settings history with compare" and reproducibility can't work | med | `Asset.model`, `Asset.params(json)`, `Asset.references(json)` |
| A11 | No `created_at` / `updated_at` on most entities | low | added to every entity |
| A12 | An owner only on Project, AssetGroup and Recipe | low (single user) | `owner_id` on Project, Recipe, AssetGroup, QueueItem, CostLedger; everything else is reached through Project. Access = one data-layer check per request (no RLS: there's no Postgres) |
| A13 | Studio's `JOB` runs one job at a time; Section 12 wants locks per project + episode + step + style, and style variants running in parallel | **high (architecture)** | keep `JOB` for GPU notebooks; add a small worker pool for provider API calls, with a lock table `JobLock(project, episode, step, style)` |
| A14 | Name clash: Studio already has `/api/library` (the gallery), and v3 §6b.4 adds `/api/library` for the picture library | low | the picture library goes at `/api/picture_library`; the existing route is kept |
| A15 | Flova's "Asset / Resource" pair = v3's "AssetGroup / Asset" | — | names kept; the mapping is noted in Section 8 to avoid confusion |
| A16 | Groups/Sequences (Flova's generic tree) aren't in Section 8 | — | not needed: Studio's fixed hierarchy (Project → Episode → Scene → Shot) covers it, and the step path stays linear |
| A17 | Statuses are free text | low | check constraints listed in `schema.sql` |

Everything else in Section 8 matched the recon (versions with a liked default, purpose labels, cross-project library,
moments and branches, project rules, recipes, export jobs).

## Schema

Tables: 31 (`replica/schema.sql`, SQLite dialect, all derived/indexable). Access rules: data-layer checks (one
authorisation check per query in the handler). In Studio the folder files are the source of truth, and the SQL is the shape
of the index and of the folder JSON.

Hard constraints:
- one selected asset per (owner, style, kind) — partial unique index
- one current EDL per (project, episode) — partial unique index
- one job lock per (project, episode, step, style) — primary key
- `rev` optimistic concurrency on editable rows

## API

Existing Studio routes stay (85 under `/api/`). New ones, by flow (F-IDs from `recon.md`, plus v3 sections):

| method path | does | who | input | output | flow |
| --- | --- | --- | --- | --- | --- |
| POST /api/sources | add a file / URL / text / image / media to a project | owner | {project, kind, file or url or text} | {source_id} | F01 |
| POST /api/read_it_in | run the §5 pipeline | owner | {project} | {job} | F01 |
| POST /api/autopilot | start or resume Autopilot | owner | {project, stop_at[]} | {job} | F01 |
| POST /api/stop · /api/continue | stop the job; continue it with added information | owner | {project, info?} | {job} | F01, F02 |
| POST /api/chat | Producer-chat message → a plan to accept | owner | {project, conversation?, text, refs[]} | {message, plan} | F02 |
| POST /api/chat_accept | run an accepted plan | owner | {project, message_id} | {job} | F02 |
| POST /api/notes · GET /api/notes | add or list notes on any target | owner | {project, target_type, target_id, role?, body, parent_id?} | {note} | F04 |
| GET /api/moments · POST /api/restore_moment | history and restore | owner | {project, moment_id} | {ok} | F07 |
| POST /api/branch | branch a project from a moment | owner | {project, moment_id} | {project} | F07 |
| POST /api/start_over · GET /api/attempts · POST /api/restore_attempt | v3 §6b.1 | owner | {project, keep[]} | {attempt} | — |
| GET /api/picture_library | search the library (optionally all projects) | owner | q, style, character, purpose, all | {items[]} | F08 |
| GET /api/shot_matches · POST /api/reuse · POST /api/auto_reuse | v3 §6b.3 | owner | {project, n, item_id, how} | {asset} | F08 |
| POST /api/like | set the liked version of an asset group | owner | {group_id, asset_id} | {ok} | F03 |
| POST /api/quick_generate | one manual generation from a shot | owner | {project, shot, type, prompt, refs, model, params, tier} | {job} | F03 |
| GET/POST /api/edl | read or save a timeline (rev-checked) | owner | {project, episode, edl} | {edl, rev} or 409 | F05 |
| POST /api/recipes · GET /api/recipes | save, list, import a recipe | owner | {recipe json} | {recipe} | F06 |
| GET/POST /api/project_rules | read or edit the rules document | owner | {project, body, rev} | {rev} | — |
| POST /api/queue | queue projects/episodes | owner | {items[]} | {queue} | — |
| GET /api/events | SSE progress (polling fallback: /api/status) | owner | project | stream | all |

409 Conflict on any rev mismatch → the conflict prompt (v3 §6c).
Webhooks in: none (providers are polled; Kaggle already is). Webhooks out: none.
Jobs: `reindex` (on start-up and after a job ends), the export ZIP builder, and the existing Kaggle auto-cleanup.
MCP server and CLI: thin wrappers over the routes above (v3 §11).

## The parts that bite

- **Immutable files vs. old layout (A2):** the biggest change to Studio. Migrate with an alias table, never by renaming
  existing books' files in place.
- **Races (A4, A13):** the Producer and the user editing the same thing; two tabs (Studio already fixed one case in
  `2bace7c`); style variants running in parallel. Use rev checks + job locks.
- **Idempotency:** provider calls retried after a timeout can be billed twice. Send an idempotency key where providers
  accept one, and record a call in CostLedger before sending it.
- **Rate limits / free quota:** Kaggle weekly GPU hours and provider 429s; the queue already backs off.
- **File sizes:** 2 GB video sources (v3 §4.2); stream to disk, never read into memory; check by content.
- **Search:** picture-library matching needs text similarity better than `old_pictures._score`'s word overlap. Use SQLite
  FTS5 for text, plus a vision-model check on the top 10 only (cost).
- **Time zones:** timestamps in UTC; shown in local time.
- **Index drift:** SQLite can be out of date after a script writes files directly. Rebuild after every job, and treat the
  folders as the truth on any disagreement.
- **Offline / realtime / email / GDPR:** n/a for single-user local use.

## Build order

1. **Vertical slice** = v3 M1–M3: the step path layout, sources, Read it in → screenplay (S01, S04, S10 analogues; Project,
   Source, Step, Scene, CrewNote; /api/sources, /api/read_it_in, /api/events).
2. **Must-haves** (features.csv "must"): crew roles + project rules (M1), immutable assets + liked versions (M8), notes on
   anything (M12), timeline editor (M10), stop/continue + Producer chat (M12), media sources (M13), restore moment (M12),
   export (existing).
3. **Should-haves:** branches, conflict prompt, recipes, quick generate from a shot, upscale, audio extraction, settings
   history, cross-project library, MCP/CLI (M8, M12, M13, M15).
4. **Could-haves:** canvas view, doodle editing, multiple conversations, media tools, drag-box select.
5. **Fixes from replica-entrepreneur:** not run.
