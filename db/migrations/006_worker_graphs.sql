-- Workers como grafos LangGraph-style.
-- Un Worker puede ser un agente individual (kind='agent', default) o un mini-
-- grafo (kind='graph') con orchestrator + sub-agentes que el usuario diseña
-- visualmente. Para 'graph', graph_definition contiene nodes y edges.
-- Ejecutar tras 005_custom_agent_intents.sql.

alter table bot_agents
  add column if not exists kind text not null default 'agent'
    check (kind in ('agent', 'graph')),
  add column if not exists graph_definition jsonb;
