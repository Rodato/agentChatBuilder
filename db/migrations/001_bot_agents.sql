-- Persistencia de configs de agentes por bot.
-- Ejecutar en Supabase SQL editor.

create table if not exists bot_agents (
  bot_id uuid not null references bots(id) on delete cascade,
  agent_id text not null,
  name text not null,
  objective text not null default '',
  system_prompt text not null default '',
  model text not null default 'google/gemini-2.5-flash-lite',
  temperature float not null default 0.7,
  tools jsonb not null default '{}'::jsonb,
  enabled boolean not null default true,
  is_custom boolean not null default false,
  position int not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (bot_id, agent_id)
);

create index if not exists bot_agents_bot_id_idx on bot_agents (bot_id);
