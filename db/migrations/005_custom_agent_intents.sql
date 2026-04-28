-- Permite que un especialista custom se registre para uno o más intents
-- (GREETING, FACTUAL, PLAN, IDEATE, SENSITIVE, AMBIGUOUS). Cuando un intent
-- llega y existe un custom enabled registrado para él, el orchestrator lo
-- prefiere sobre el builtin.
-- Ejecutar tras 004_doc_metadata.sql.

alter table bot_agents
  add column if not exists intents text[] not null default '{}';

create index if not exists bot_agents_intents_gin_idx
  on bot_agents using gin (intents);
