-- Sistema de Workflows: definición + ejecución persistente.
-- Ejecutar en Supabase SQL editor.

create table if not exists workflows (
  id uuid primary key default gen_random_uuid(),
  bot_id uuid not null references bots(id) on delete cascade,
  name text not null default 'Default',
  definition jsonb not null default '{"nodes":[],"edges":[],"version":1}'::jsonb,
  entry_node_id text,
  is_active boolean not null default false,
  version int not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists workflows_bot_active_unique
  on workflows (bot_id) where is_active;

create index if not exists workflows_bot_id_idx on workflows (bot_id);

create table if not exists conversations (
  id uuid primary key default gen_random_uuid(),
  bot_id uuid not null references bots(id) on delete cascade,
  workflow_id uuid references workflows(id) on delete set null,
  workflow_version int,
  user_id text,
  current_node_id text,
  captured_vars jsonb not null default '{}'::jsonb,
  pending_capture jsonb,
  status text not null default 'active' check (status in ('active','completed','aborted')),
  last_activity_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create index if not exists conversations_bot_status_idx on conversations (bot_id, status);
create index if not exists conversations_workflow_idx on conversations (workflow_id);

alter table bots add column if not exists workflow_mode text not null default 'free'
  check (workflow_mode in ('free','workflow'));
