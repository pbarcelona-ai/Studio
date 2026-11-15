-- Studio v3 index schema (SQLite). Derived from the project folders; rebuildable with scripts/reindex.py.
-- The folders under projects/ stay the source of truth. Times are UTC ISO-8601 text; money is integer cents.
-- ids are text (uuid4 hex). Access: one authorisation check per request in the handler (no RLS in SQLite).
pragma foreign_keys = on;

create table project (
  id text primary key, slug text not null unique, owner_id text not null, title text not null,
  recipe_id text references recipe(id) on delete set null,
  mode text not null default 'review' check (mode in ('review','autopilot')),
  master_style_id text, is_series integer not null default 0,
  parent_project_id text references project(id) on delete set null,
  branched_from_moment_id text,
  settings text not null default '{}', selected_products text not null default '[]',
  created_at text not null default (datetime('now')), updated_at text not null default (datetime('now'))
);
create index project_owner on project(owner_id, updated_at);

create table source (
  id text primary key, project_id text not null references project(id) on delete cascade,
  kind text not null check (kind in ('document','idea','picture','url','comic','screenplay','video','audio','music')),
  title text, path text, metadata text not null default '{}', rights_ack_at text not null,
  created_at text not null default (datetime('now'))
);
create index source_project on source(project_id);

create table episode (
  id text primary key, project_id text not null references project(id) on delete cascade,
  number integer not null, title text, logline text,
  status text not null default 'planned' check (status in ('planned','in_progress','done')),
  created_at text not null default (datetime('now')), unique (project_id, number)
);

create table step (
  project_id text not null references project(id) on delete cascade,
  episode_id text references episode(id) on delete cascade,
  style_id text references style_profile(id) on delete cascade,
  key text not null,
  status text not null default 'not_started'
    check (status in ('not_started','working','needs_review','done','out_of_date')),
  updated_at text not null default (datetime('now')),
  unique (project_id, episode_id, style_id, key)
);

create table recipe (
  id text primary key, owner_id text, name text not null, body text not null, built_in integer not null default 0,
  created_at text not null default (datetime('now')), updated_at text not null default (datetime('now'))
);

create table project_rules (
  project_id text primary key references project(id) on delete cascade,
  body text not null default '', rev integer not null default 1, updated_at text not null default (datetime('now'))
);

create table conversation (
  id text primary key, project_id text not null references project(id) on delete cascade,
  title text, closed_at text, created_at text not null default (datetime('now'))
);

create table chat_message (
  id text primary key, conversation_id text not null references conversation(id) on delete cascade,
  author text not null check (author in ('user','producer')), body text not null,
  refs text not null default '[]', plan text, accepted integer, moment_id text references moment(id) on delete set null,
  created_at text not null default (datetime('now'))
);
create index chat_conv on chat_message(conversation_id, created_at);

create table crew_note (
  id text primary key, project_id text not null references project(id) on delete cascade,
  parent_id text references crew_note(id) on delete cascade,
  step_key text, role text not null,
  target_type text not null check (target_type in ('project','scene','shot','page','asset','continuity','edl')),
  target_id text, author text not null check (author in ('user','role')), body text not null,
  round integer, score real, resolved_at text, created_at text not null default (datetime('now'))
);
create index note_target on crew_note(project_id, target_type, target_id);

create table moment (
  id text primary key, project_id text not null references project(id) on delete cascade,
  label text not null, cause text not null check (cause in ('approval','chat','autopilot','manual','start_over','restore')),
  snapshot_path text not null, created_at text not null default (datetime('now'))
);
create index moment_project on moment(project_id, created_at);

create table attempt (
  id text primary key, project_id text not null references project(id) on delete cascade,
  number integer not null, label text not null, kept text not null default '[]', snapshot_path text not null,
  archived_at text not null default (datetime('now')), unique (project_id, number)
);

create table scene (
  id text primary key, project_id text not null references project(id) on delete cascade,
  episode_id text references episode(id) on delete cascade,
  number integer not null, heading text not null, fountain text not null, meta text not null default '{}',
  rev integer not null default 1, updated_at text not null default (datetime('now'))
);
create index scene_project on scene(project_id, episode_id, number);

create table continuity_item (
  id text primary key, project_id text not null references project(id) on delete cascade,
  kind text not null check (kind in ('character','location','prop')), name text not null,
  identity_token text not null, personality text not null default '{}', invented_fields text not null default '[]',
  rev integer not null default 1, updated_at text not null default (datetime('now')), unique (project_id, kind, name)
);

create table style_profile (
  id text primary key, project_id text not null references project(id) on delete cascade,
  name text not null, is_master integer not null default 0, style_card text not null,
  example_asset_id text, rev integer not null default 1, updated_at text not null default (datetime('now')),
  unique (project_id, name)
);
create unique index one_master_style on style_profile(project_id) where is_master = 1;

create table style_translation (
  continuity_item_id text not null references continuity_item(id) on delete cascade,
  style_id text not null references style_profile(id) on delete cascade,
  text text not null, sheet_asset_id text, primary key (continuity_item_id, style_id)
);

create table shot (
  id text primary key, scene_id text not null references scene(id) on delete cascade,
  number integer not null, ord integer not null, source text not null default 'ai' check (source in ('ai','footage')),
  shot_type text, lens_mm integer, camera text, blocking text, action text, expression text, dialogue text, sound text,
  duration_s real not null check (duration_s > 0), transition text, priority integer, lighting_intent text,
  composition text, motion_prompt text, seed integer, footage_asset_id text,
  rev integer not null default 1, updated_at text not null default (datetime('now'))
);
create index shot_scene on shot(scene_id, ord);

create table shot_continuity (
  shot_id text not null references shot(id) on delete cascade,
  continuity_item_id text not null references continuity_item(id) on delete cascade,
  primary key (shot_id, continuity_item_id)
);

create table shot_layout (
  shot_id text primary key references shot(id) on delete cascade,
  depth_asset_id text, pose_asset_id text, edge_asset_id text, boxes text not null default '[]', master_asset_id text
);

create table page (
  id text primary key, project_id text not null references project(id) on delete cascade,
  number integer not null, text text not null, composition text, seed integer,
  rev integer not null default 1, unique (project_id, number)
);

create table asset_group (
  id text primary key, owner_id text not null, project_id text references project(id) on delete set null,
  name text not null, purpose text check (purpose in ('keyframe','final','reference','sheet','layout','audio','music')),
  liked_asset_id text, created_at text not null default (datetime('now'))
);
create index group_owner on asset_group(owner_id, project_id);

create table shot_asset (
  shot_id text not null references shot(id) on delete cascade,
  group_id text not null references asset_group(id) on delete cascade,
  purpose text not null, primary key (shot_id, group_id, purpose)
);

-- one row per immutable file version (Flova's "resource")
create table asset (
  id text primary key, project_id text not null references project(id) on delete cascade,
  group_id text references asset_group(id) on delete set null,
  attempt_id text references attempt(id) on delete set null,
  owner_type text not null check (owner_type in ('shot','page','continuity','style','source','episode','project')),
  owner_id text not null,
  style_id text references style_profile(id) on delete set null,          -- null = shared by every style
  kind text not null check (kind in ('image','video','audio','music','pdf','mp4','m4b','zip','doc')),
  path text not null unique,                                              -- never renamed or overwritten
  content_hash text not null, version integer not null,                  -- sha1 of the file (picture_record.py)
  is_selected integer not null default 0,
  purpose text, verdict text check (verdict in ('liked','approved','rejected')),
  provider text, model text, params text not null default '{}', references_json text not null default '[]',
  prompt_parts text not null default '{}', seed integer,
  consistency_score real, continuity_hash text,
  quality_tier text check (quality_tier in ('draft','final')),
  cost_cents integer not null default 0, currency text not null default 'USD',
  reused_from_asset_id text references asset(id) on delete set null,
  created_at text not null default (datetime('now'))
);
create index asset_owner on asset(project_id, owner_type, owner_id, style_id);
create index asset_group_idx on asset(group_id);
create unique index one_selected on asset(owner_type, owner_id, coalesce(style_id,''), kind) where is_selected = 1;

-- old file paths (takes/, replaced/) → asset, so existing books keep working while files stay where they are
create table path_alias (old_path text primary key, asset_id text not null references asset(id) on delete cascade);

create virtual table asset_search using fts5(asset_id unindexed, prompt, action, characters, location, style);

create table audio_line (
  id text primary key, shot_id text not null references shot(id) on delete cascade,
  character text, text text not null, voice_id text, delivery_note text, asset_id text references asset(id)
);

create table music_cue (
  id text primary key, project_id text not null references project(id) on delete cascade,
  episode_id text references episode(id) on delete cascade,
  start_shot_id text references shot(id) on delete set null, end_shot_id text references shot(id) on delete set null,
  mood text, tempo integer, asset_id text references asset(id)
);

create table edl (
  id text primary key, project_id text not null references project(id) on delete cascade,
  episode_id text references episode(id) on delete cascade,
  name text not null default 'Main cut', is_current integer not null default 1,
  tracks text not null, rev integer not null default 1, updated_at text not null default (datetime('now'))
);
create unique index one_current_edl on edl(project_id, coalesce(episode_id,'')) where is_current = 1;

create table job (
  id text primary key, project_id text references project(id) on delete cascade,
  episode_id text, step_key text, style_id text,
  status text not null check (status in ('queued','running','stopped','failed','done')),
  progress integer not null default 0 check (progress between 0 and 100),
  items_total integer, items_done integer, error text, retry_count integer not null default 0,
  started_at text, finished_at text
);
create index job_project on job(project_id, status);

create table job_lock (
  project_id text not null, episode_id text not null default '', step_key text not null, style_id text not null default '',
  job_id text not null references job(id) on delete cascade, primary key (project_id, episode_id, step_key, style_id)
);

create table queue_item (
  id text primary key, owner_id text not null, project_id text not null references project(id) on delete cascade,
  episode_id text, ord integer not null,
  status text not null default 'waiting' check (status in ('waiting','running','done','failed','cancelled'))
);

create table cost_ledger (
  id text primary key, owner_id text not null, project_id text references project(id) on delete set null,
  style_id text, provider text not null, model text, units real not null, quality_tier text,
  is_regeneration integer not null default 0, cost_cents integer not null, currency text not null default 'USD',
  idempotency_key text unique, created_at text not null default (datetime('now'))
);
create index cost_project on cost_ledger(project_id, created_at);
