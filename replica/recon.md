# Recon map: Flova (web)

Scope: the core loop: idea/script/media → Agent plan → storyboard (groups, sequences, assets) → media generation → Edit timeline → export.
Teams, billing internals, Flova TV and the community network are only noted.
For: Studio (the book-to-film app in this repo). The goal is to bring the matching capabilities into the v3 build plan
(`BOOK_TO_SCREEN_BUILD.md`) as Studio's own design. Nothing of Flova's code, assets, wording or visuals is copied.
Date: 2026-11-15
Method: public documentation, pricing pointers and the changelog only. No login, no account, no scraping, no network or
bundle inspection. No screenshots were taken (no account and no browser session), so `replica/screens/` is empty. Layout
details below come from the docs' wording, not from seeing the screens, and their confidence is marked.

## Sources

| # | source | URL | notes |
| --- | --- | --- | --- |
| 1 | docs: how Flova works | https://flova.ai/docs/en/How_Flova_Works | concepts, inputs, planning, Skills |
| 2 | docs: the Agent | https://flova.ai/docs/en/features/agent | agent abilities, restore, branch, conflict panel |
| 3 | docs: quick guide | https://flova.ai/docs/en/tutorials/quick-guide | chat right, manual left, both run in parallel |
| 4 | docs: create your first video | https://flova.ai/en/docs/introduction/quick-start/ | the happy path, export |
| 5 | docs: project content editing (older) | https://flova.ai/docs/en/features/project-content-editing | storyboard cards, canvas, preview list, versions |
| 6 | docs: groups and sequences | https://flova.ai/en/docs/features/project/groups-sequences/ | containers, nesting |
| 7 | docs: assets | https://flova.ai/en/docs/features/project/assets/ | asset vs resource, likes, move |
| 8 | docs: documents | https://flova.ai/en/docs/features/project/documents/ | docs, AGENTS.md |
| 9 | docs: edits | https://flova.ai/en/docs/features/project/editing/ | timeline, alternative cuts |
| 10 | docs: quick generation | https://flova.ai/en/docs/features/generation/quick/ | manual generation panel and settings |
| 11 | docs: generate with the Agent | https://flova.ai/en/docs/features/generation/agent/ | @-references, confirmations |
| 12 | docs: multiple conversations | https://flova.ai/en/docs/features/agent/multi-session/ | conversation tabs, history |
| 13 | docs: Skills | https://flova.ai/en/docs/features/skill/use/ | community, Mine, invocation, sharing |
| 14 | docs: export | https://flova.ai/en/docs/features/editing/export/ | video, CapCut draft, project files |
| 15 | docs: subscriptions and credits | https://flova.ai/en/docs/account-billing/subscription-credits/ | what plans gate |
| 16 | changelog | https://flova.ai/en/docs/changelog/ | 2026-04 → 2026-11-09 |

## Core loop

Describe a video (or bring a script, image, track or Skill). The Agent plans it and generates it into a structured project
of assets. You refine it by chat, comments or manual generation, assemble it on a timeline, and export.

## Screens

Confidence: **high** = described step by step in the docs; **med** = named with some detail; **low** = only named.

| ID | screen | route / how to reach | purpose | key components | states seen |
| --- | --- | --- | --- | --- | --- |
| S01 | Home / creation entry | `/en/` | start a project from a prompt | big prompt box, + attach, Skill picker, example projects | empty, filled (high) |
| S02 | Login | `/en/?open_login=1` | sign in | email/OAuth | (low) |
| S03 | Project list + folders | home, after login | open and organise projects | project cards, folders, Move to Folder, copy to team, cover from frame | filled (med) |
| S04 | Workspace shell (four panels) | open a project | the whole project in one page | top bar (Export, Recent Downloads, Usage), Navigation, Project Files, Preview, Agent chat | loading, filled (med) |
| S05 | Project Files: List view | workspace centre, List | tree of groups, sequences, assets, docs, edits | + menu (Generate Media, Upload File, New Empty Group/Sequence/Document/Edit), collapse, context menus | empty, filled (high) |
| S06 | Canvas view | workspace centre, Canvas | free-form board of cards and unsorted media | cards, drag, right-click menu, comments on cards, drag-box multi-select | filled (med) |
| S07 | Grid view | workspace centre, Grid | browse media | square / masonry toggle | filled (low) |
| S08 | Navigation panel | workspace left | jump through the project hierarchy | tree, right-click Generate Media | filled (med) |
| S09 | Preview panel | workspace | play/view the selected item | player, version strip (liked first), Open Edit | filled (med) |
| S10 | Agent chat | workspace right | plan, generate, revise | conversation tabs (+, rename, close), @ and Add to Chat references, + upload, Skill picker, voice input, progress lines, clarifying question cards, confirm cards, stop, queue, next-message suggestions (Tab), turn navigation | idle, working, awaiting confirmation, stopped (med) |
| S11 | Conversation history | chat top bar | reopen closed conversations | list | (low) |
| S12 | Quick Generation panel | + → Generate Media, right-click, or Generate on an empty card | manual generation without the Agent | media type, reference area (first/last frame, image, video, audio), prompt, model picker, per-model settings (aspect, resolution, duration), cost estimate, settings history and compare, drafts | filled, submitting (high) |
| S13 | Doodle editor | on an image/video | mark where to change it | brush/annotation, prompt | (low) |
| S14 | Media tools | on an asset | crop, trim, rotate, background removal, LUTs, subtitle removal, upscale, audio extraction | tool list | (low) |
| S15 | Edit timeline | Open Edit, at the bottom of Canvas | assemble the final video | tracks (video, voice-over, music), playhead, split, replace, delete, mirror/rotate, volume, mute track, fade-in, undo/redo, several timelines per Edit | filled (high) |
| S16 | Document editor | select a doc | scripts, character settings, delivery specification, AGENTS.md | Markdown editor, rename/move, change comparison | filled (med) |
| S17 | Conflict panel | parallel edit clash | choose which version to keep | two versions side by side, keep buttons | (low) |
| S18 | Export dialog | top bar → Export | deliver | type: Video File / Video Draft (CapCut) / Project Files; multi-select edits or files | filled (high) |
| S19 | Recent Downloads | top bar | export job status | job rows, status, download link | running, done, failed (high) |
| S20 | Skill Community | `/en/skill/` | find Skills | Featured (by category, search, usage counts), Mine (All, Created by me, Historical usage, Drafts) | filled (high) |
| S21 | Skill detail | a Skill card | read and use a Skill | Use Skill, Save to My Skills, Share (link/code, revoke), invocation toggle | filled (high) |
| S22 | Skill create/edit | Mine or ask the Agent | write a Skill | steps, review criteria, templates, referenced media, folders, change comparison | draft (med) |
| S23 | Asset Library | chat references, or save from a project | cross-project reuse | organised library, add to project | filled (low) |
| S24 | Manage Account: credits | account menu / Usage | balance and history | Credit Details, Pricing Details, Model Price List | (med) |
| S25 | Pricing | `/en/pricing/` | plans | personal and team plans | (low) |
| S26 | Team management | account | seats and credit allocation | members (up to 100), allocation | (low) |
| S27 | Quick Chat window | subscribers | chat outside a project | paste screenshots | (low) |
| S28 | Agent access (MCP / CLI) | account | connect external AI tools and CLI | authorisation, six-digit Skill passcodes | (low) |

## Flows

```
F01 First video from a prompt
    S01 type prompt -> send -> S04/S10 Agent creates the project and works
    -> (optional) confirm card: aspect ratio / direction -> S09 play result
    -> S10 describe one change -> new version, compare, pick -> S18 Export -> S19 download
    happy path clicks: ~6
    edge: Agent asks a question, credits run out mid-task (authorise extra or stop), generation fails (credits returned)

F02 Short film from an idea
    S10 "expand this into a short film" -> shot plan in chat (confirm) or review in S05/S06
    -> Agent generates the shots -> S15 assembled edit -> S10 notes on specific shots -> S18
    happy path clicks: ~8
    edge: changes to the same content in parallel -> S17 conflict panel

F03 Manual quick generation of one shot
    S06 right-click (or Generate on an empty card) -> S12 type, references, prompt, model, settings -> submit
    -> result becomes an asset in S05 -> S09 Like the best version
    happy path clicks: ~6

F04 Comment-driven revision
    S06 comment on a card/shot/asset -> multi-turn thread -> Agent regenerates -> new version -> Like
    happy path clicks: ~4

F05 Assemble and cut
    S05 right-click a Sequence -> Add to Editing Project -> S15 trim/split/volume/fade -> S18
    happy path clicks: ~5
    edge: missing media blocks export

F06 Start from a Skill
    S20 -> S21 Use Skill -> S01 creation entry with the Skill -> add goal + material -> S10
    happy path clicks: ~4

F07 Back to a moment / branch
    S10 message menu -> "back to this moment" (project restored) or branch -> a new project to compare
    happy path clicks: ~2

F08 Reuse across projects
    S05 asset -> save to S23 Asset Library -> in another project, reference it from S10 or S12

F09 Sample, then final (Seedance)
    S12/S10 sample mode -> review the sample -> confirm the quote -> 1080p final

F10 Drive Flova from another AI tool
    S28 authorise -> MCP/CLI creates spaces, runs Skills
```

## Components

| component | variants | states | used on |
| --- | --- | --- | --- |
| Prompt composer | home, chat, quick chat | empty, typing, with attachments, sending, queued | S01, S10, S27 |
| Attachment / reference chip | file, project item (@), Asset Library item, Skill | added, removed | S01, S10, S12 |
| Agent message | text, progress line, clarifying question card, confirmation card, result card | streaming, done, stopped | S10 |
| Conversation tab | — | active, renamed, closed | S10, S11 |
| Tree row | group, sequence, asset, document, edit | collapsed, expanded, selected, drag | S05, S08 |
| Card | element, shot, audio layer, asset, document | empty position ("Generate"), generating, filled, commented, selected | S06 |
| Context menu | per item type | — | S05, S06, S08 |
| Version strip | — | liked (first), others newest first | S09 |
| Media player | image, video, audio | loading, playing | S09, S15 |
| Model picker + settings form | image, video, audio, music | changes per model | S12 |
| Cost estimate | — | shown before submit | S12, S24 |
| Timeline | video, voice-over, music tracks; clip | selected, muted, split, faded | S15 |
| Markdown editor | doc, AGENTS.md, Skill | read-only (uploaded), editable, compare | S16, S22 |
| Comment thread | on a card / shot / scene / asset | open, multi-turn | S06 |
| Conflict picker | — | two versions | S17 |
| Job row | export, generation | running, done, failed, download | S19 |
| Tabs / filters | Featured / Mine; All / Created / Historical / Drafts | — | S20 |
| Share dialog | link, code | active, revoked | S21 |
| Toast / restriction message | info, error ("generation restricted") | — | all |

## Inferred data model

```
Workspace   id, kind (personal | team), seats, credit_pool
            evidence: S26, changelog 2026-07-09/2026-08-31   confidence: med
Project     id, workspace_id, folder_id, title, cover_asset_id, permission_mode, agent_preferences
            evidence: S03, changelog 2026-08-10/2026-11-06   confidence: med
Node        id, project_id, parent_id, kind (group | sequence | asset | document | edit), name, order
            evidence: S05, src 6 (nesting, order matters only in sequences)   confidence: high
Asset       node_id, media_type (image | video | audio | music), liked_resource_id
            evidence: src 7   confidence: high
Resource    id, asset_id, file, version, created_at, liked, purpose (keyframe | final video | reference),
            generation_settings (model, prompt, references, params)
            evidence: src 5, 7, 10; changelog "settings history"   confidence: high (purpose: med)
Binding     resource/asset ↔ storyboard element | shot | audio layer
            evidence: src 2, 3, 5   confidence: med
Document    node_id, markdown, read_only (uploaded), is_agents_md
            evidence: src 8   confidence: high
Edit        node_id, timelines[] (tracks[] → clips[]: resource_id, in, out, volume, fade, mirror, rotate)
            evidence: src 9, 14   confidence: high
Conversation id, project_id, title, open | closed
Message     id, conversation_id, role, body, references[], cards[] (question | confirm), moment_id
            evidence: src 2, 12; changelog   confidence: med
Moment      id, project_id, message_id, snapshot   ("back to this moment", branch)
            evidence: src 2   confidence: guess (mechanism not documented)
Comment     id, target_node_id, thread[]   evidence: src 5 (old doc), changelog 2026-08-17   confidence: med
Skill       id, owner_id, name, category, steps, review_criteria, templates, referenced_media[], folder,
            invocation (default | not default), draft, share_code, usage_count
            evidence: src 13   confidence: high
LibraryItem id, owner_id, node_ref   evidence: S23   confidence: low
ExportJob   id, project_id, type (video | capcut_draft | project_files), edit_ids[], status, download_url
            evidence: src 14   confidence: high
CreditLedger id, workspace_id, source (subscription | invite | exploration | event | purchase), amount, expires_at,
            model_restricted
            evidence: src 15   confidence: high
```

Relationships: Workspace 1-n Project; Project 1-n Node (a tree); Asset 1-n Resource; Edit 1-n Timeline 1-n Track 1-n Clip
→ Resource; Project 1-n Conversation 1-n Message; Message 0-1 Moment; Node 1-n Comment; User 1-n Skill.

## Feature matrix

See `features.csv` (the `notes` column says what Studio already has, and the v3 section that covers it).
Must: 18, should: 20, could: 11, skip: 6.

## Out of scope (cannot or should not be cloned)

- Flova's model deals and hosted models (Seedance, Kling, Wan, OmniHuman, MiniMax, GPT Image access). Studio uses its own
  providers.
- The Skill Community's content and its users, and Flova TV's channels and audience (that's their network).
- Their credit and billing system, plans and refunds. Studio has a budget preview, not a store.
- The CapCut draft format (CapCut's private format). Export .fcpxml / .otio / .edl for editors instead.
- Their branding, layout look, icons, copy and example projects.

## Size

Screens 28, flows 10, entities 17. Hard parts:

1. **The Agent loop.** Planning with question and confirmation cards, permission modes, stop/queue/continue, and running
   alongside the user's manual edits with conflict detection.
2. **History.** Restoring to any message's moment and branching into a new project, cheaply (snapshots that reference
   files, not copies).
3. **Canvas + timeline.** A free-form canvas with cards and comments, and a multi-track timeline editor (split, trim,
   volume, fades, several timelines per Edit) in plain JS.

Size: **L** for the full slice. For Studio, most of the media pipeline already exists, so the gap (features marked
must/should in `features.csv`) is closer to **M**. This matches milestones M8, M10, M12 and M15 in the v3 build plan.
