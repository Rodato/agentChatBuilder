-- Persistencia de mensajes individuales para analytics y debugging.
-- Hasta hoy solo persistíamos el estado de la conversación (workflow_stack,
-- captured_vars, mode), no los mensajes. Esta tabla soporta el tab
-- "Analytics" del Agente.
-- Ejecutar tras 006_worker_graphs.sql.

create table if not exists chat_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  bot_id uuid not null references bots(id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system')),
  content text not null,
  agent_used text,
  intent text,
  mode text check (mode in ('workflow', 'agentic') or mode is null),
  processing_time_ms integer,
  created_at timestamptz not null default now()
);

create index if not exists chat_messages_bot_created_idx
  on chat_messages (bot_id, created_at desc);
create index if not exists chat_messages_conversation_idx
  on chat_messages (conversation_id, created_at);
