-- Workflows + sistema agéntico híbrido.
-- Ejecutar en Supabase SQL editor tras 001_bot_agents.sql y 002_workflows.sql.

-- workflows: añadir triggers y flag enabled
alter table workflows
  add column if not exists trigger_type text not null default 'manual'
    check (trigger_type in ('on_start','on_intent','manual')),
  add column if not exists trigger_value text,
  add column if not exists enabled boolean not null default true;

-- Migrar el estado actual: los que estaban is_active se vuelven on_start.
update workflows set trigger_type = 'on_start', enabled = true
  where is_active = true and trigger_type = 'manual';

-- Índice único: un solo on_start por bot
drop index if exists workflows_bot_active_unique;
create unique index if not exists workflows_bot_onstart_unique
  on workflows (bot_id) where trigger_type = 'on_start' and enabled = true;

-- Índice por bot_id + trigger para queries del ChatEngine
create index if not exists workflows_bot_trigger_idx on workflows (bot_id, trigger_type, enabled);

-- conversations: stack de workflows + modo
alter table conversations
  add column if not exists workflow_stack jsonb not null default '[]'::jsonb,
  add column if not exists mode text not null default 'agentic'
    check (mode in ('workflow','agentic'));

-- bot_agents: metadata libre para trigger_flows permitidos por agente
alter table bot_agents
  add column if not exists metadata jsonb not null default '{}'::jsonb;
