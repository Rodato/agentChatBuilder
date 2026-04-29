# CLAUDE.md - Agent Chat Builder

## Documentación (Obsidian)
Notas en: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Documentición codigo/agentChatBuilder/`
Actualizar cuando cambien: pipeline de agentes, pipeline RAG, endpoints API, stack, modelos LLM, esquema MongoDB/Supabase.
No actualizar por: bugfixes menores, ajustes de UI, cambios de prompts sin impacto estructural.

## Proyecto

**Nombre**: Agent Chat Builder
**Tipo**: Plataforma SaaS para construir chatbots con agentes y RAG sin código
**Inicio**: 2026-02-01
**Basado en**: Aprendizajes de Puddle Assistant
**Fase actual**: MVP + Workflows + Mapa editable + Workers grafo con delegación + Analytics
**Repo**: https://github.com/Rodato/agentChatBuilder

---

## Estado Actual (2026-04-28 PM tarde — sesión completa)

### Iteración 5 (PM tarde) — UX polish + delegación Worker→Worker

- **Worker→Worker delegation**: nuevo tipo de nodo `worker_ref` en el GraphEditor de Workers grafo. Permite delegar a otro Worker top-level del bot. Backend: `agents/graph_worker.py` invoca el target via `Orchestrator.get_agent(...).process()` con `state.metadata['delegation_depth']` y `MAX_DELEGATION_DEPTH=3` para evitar ciclos. Frontend: dropdown de workers hermanos (excluye self).
- **Mapa: aristas Workflow→Worker (read-only)**: derivadas de los nodos `agent` dentro del `definition` de cada workflow. Edge kind nuevo `workflow_agent` con label "usa", estilo cyan punteado. Permite ver de un vistazo qué workers usa cada flujo. La edición sigue siendo dentro del Workflow editor.
- **Workers en editor inline**: AgentEditPanel deja de ser Dialog modal y pasa a Card inline con botón "← Volver" (patrón consistente con WorkflowList → WorkflowEditor).
- **Capture nodes con tipo de dato**: `text` (default), `number`, `email`, `date`, `boolean`, `phone`. Validación + normalización en backend (`core/workflow_engine.validate_capture_value`). Si el usuario responde inválido, mantiene `pending_capture` y repite la pregunta con un error.
- **Auto-derivar entry node** en workflows: removido el botón "Marcar como inicial" (era redundante). `buildDefinition` calcula el entry como el primer nodo sin aristas entrantes.
- **Descripciones consistentes** en todas las tabs (Configuración, Conocimiento, Workflows, Mapa, Chat de prueba, Analytics).

### Iteración 4 (PM medio) — Nodo message + embeddings rápidos + analytics + docs

- **Nodo `message` en Workflows**: nuevo tipo de nodo que envía texto fijo (con `{{vars}}`) sin esperar input. Encadena con otros message en el mismo turno hasta encontrar un nodo bloqueante (capture / agent / handoff).
- **Embeddings dual-provider**: `EmbeddingClient` soporta OpenAI directo (`text-embedding-3-small`, ~10x más rápido) y OpenRouter (legacy ada-002). Selección via env var `EMBEDDING_PROVIDER` o auto-detect. Compromiso del usuario: `OPENAI_API_KEY` debe configurarse sí o sí cuando se haga deploy.
- **Analytics básico**: tabla `chat_messages` (migración 007), persistencia desde `/chat` y `/chat/start`, endpoint `GET /api/bots/{id}/analytics`, tab Analytics con totales + barras por día + distribuciones (worker / intent / mode) + latencia promedio.

### Iteración 3 (PM temprano) — Reorden UX, Mapa editable, Workers grafo

#### Detalle iteración 3

- **Reorden de tabs (UX)**: Configuración → Conocimiento → Workflows → Workers → Mapa → Chat de prueba → Analytics. Renombrado UI: "Especialistas" → "Workers", "Documentos" → "Conocimiento". Eliminado el campo "Mensaje de bienvenida"; ahora la kickoff message cae a workflow `on_start` → worker `greeting` → fallback hardcoded.
- **Mapa editable (Fase 2)**: el Mapa pasa de read-only a canvas de ensamble. Paleta lateral con Workers + Workflows ya creados → drag al canvas → conectar. Las aristas DEFINEN el routing y se persisten via `PUT /api/bots/{id}/map` que diff'ea contra el estado actual y actualiza `bot_agents.intents`, `bot_agents.tools.trigger_flow`, `bot_agents.metadata.trigger_flows`, `workflows.trigger_type`, `workflows.trigger_value`.
- **Workers como grafos LangGraph-style (Fase 3)**: un Worker custom puede ser `kind='agent'` (default) o `kind='graph'`. Los grafos tienen `graph_definition` con orchestrator + subagents + synthesizer. El runner es `agents/graph_worker.py` (`GraphWorker`); el orchestrator-LLM decide ruta vía JSON `{"route": "<id>"}`. UI: nuevo `frontend/src/components/worker/GraphEditor.tsx` con paleta, canvas y inspector.
- **Nodo `message` en Workflows**: nuevo tipo de nodo que envía texto fijo (con `{{vars}}`) sin esperar input. Encadena con otros `message` y se concatena la respuesta hasta el primer nodo bloqueante (capture / agent / handoff).
- **Embeddings rápidos**: `EmbeddingClient` ahora soporta OpenAI directo (`text-embedding-3-small`, ~10x más rápido) además de OpenRouter (legacy). Selección via env var `EMBEDDING_PROVIDER` o auto-detect: si hay `OPENAI_API_KEY`, usa OpenAI; si no, OpenRouter.
- **Analytics básico**: nueva tabla `chat_messages`, persistencia desde `api/main.py` (best-effort), endpoint `GET /api/bots/{id}/analytics`, tab Analytics con stats (totales, mensajes/día, distribución por worker / intent / mode, latencia promedio).

## Estado anterior (2026-04-28 AM)

### Sesión 2026-04-28 AM — Especialistas universales, RAG en BaseAgent, cleanup completo

- **Renombrado UI**: "bot" → "Agente de IA" en todo lo user-facing. Tab interna "Agentes" → "Especialistas" para evitar el choque conceptual (un Agente de IA contiene varios Especialistas).
- **Mapa del Agente** — nueva tab "Mapa" con React Flow read-only. Backend `GET /api/bots/{id}/map` devuelve agentes + workflows + edges derivadas (entry, intent_route, on_intent, manual_trigger, handoff, handoff_agentic). Componente `BotMapView` en `frontend/src/components/BotMap.tsx`.
- **Metadata de documentos para RAG** — migración 004 añade `summary` y `keywords[]` a `documents`. PATCH `/api/bots/{id}/documents/{doc_id}` para editar. VectorStore aplica boost por overlap de keywords (`+0.05` por match, máx `+0.15`). RAGAgent inyecta resumen del doc + cabecera `[doc_name · p.X]` en cada bloque.
- **Eliminar Agentes de IA** — botón papelera en cada card del dashboard con confirmación. `delete_bot` ahora purga MongoDB `doc_chunks` + `uploads/{bot_id}/` antes del DELETE SQL (cascade Postgres ya cubría `bot_agents`, `documents`, `workflows`, `conversations`).
- **RAG centralizado en BaseAgent** — `BaseAgent.maybe_retrieve(state)` con filtro `bot_id`. Cualquier especialista cuyo `tools.rag_search=true` ahora hace retrieval real (antes solo `factual` y `plan`, este último sin filtro de bot — bug). Pasa `vector_store` a los 6.
- **Especialistas custom alcanzables** — migración 005 añade `intents text[]` a `bot_agents`. Un custom puede registrarse para uno o más de los 6 intents y el dispatch dinámico del Orchestrator lo prefiere sobre el builtin. También invocables desde nodos `agent` de Workflows. Nueva clase `agents/generic_agent.py` para cuerpos custom.
- **Borrado guard 409** — `DELETE /api/bots/{id}/agents/{agent_id}` revisa workflows referenciantes y devuelve 409 con `blocked_by` si están en uso. Frontend muestra dialog con la lista de workflows.
- **WorkflowEditor dropdown dinámico** — eliminó la lista hardcoded `AGENT_OPTIONS`; ahora carga `agentsApi.list()` (incluye customs con badge). Inline warning si el `agent_id` guardado ya no existe.
- **Orchestrator refactor** — `build_agent_configs(rows) → Dict[agent_id, cfg]` + `resolve_agent_for_intent(intent, configs) → agent_id`. Un solo nodo `dispatch` resuelve runtime cuál ejecutar (custom-or-builtin) sin recompilar el grafo.

### Estado 2026-04-21

#### Sistema híbrido Workflows + Agentic (PM)

- **`ChatEngine`** (`core/chat_engine.py`): coordinador top-level por conversación. Mantiene un `workflow_stack` en la tabla `conversations`. Modo derivado: `stack vacío → agentic`, `stack no vacío → workflow`.
- **Múltiples workflows por bot**, cada uno con `trigger_type`:
  - `on_start` — onboarding al iniciar la conversación (solo uno por bot).
  - `on_intent` — se dispara cuando el intent router clasifica un intent específico (GREETING | FACTUAL | PLAN | IDEATE | SENSITIVE | AMBIGUOUS).
  - `manual` — un agente lo dispara emitiendo `{"trigger_flow": "<id-o-name>"}` como respuesta.
- **Nodo `handoff`** nuevo en el editor: sale del workflow actual a `agentic` o salta a otro workflow. Soporta `farewell` con variables.
- **Stack anidado** (max depth 5): un workflow puede invocar otro y volver al terminar.
- **`captured_vars` globales**: viven en la conversación y se inyectan como `state.context` a los agentes también en modo agentic.
- **Function-calling-lite**: agentes con `tools.trigger_flow=true` reciben un bloque al system_prompt listando workflows disponibles. Si el LLM responde con JSON `{"trigger_flow":"..."}`, el ChatEngine empuja ese workflow al stack.
- `AgentEditPanel` expone checkbox-list de workflows manuales cuando se activa el tool; guarda en `bot_agents.metadata.trigger_flows`.
- Tab Workflow del bot: lista (`WorkflowList`) → editor (`WorkflowEditor`) con sidebar de trigger.

#### Agentes persistidos + workflows MVP (AM)

- Agent configs persistidas en Supabase (`bot_agents`); los cambios en UI afectan al Orchestrator real.
- Orchestrator por `bot_id` con cache LRU (TTL 30s) — ya no hay singleton global.
- `/chat` y `/chat/start` con Pydantic; `conversation_id` devuelto siempre.
- Sistema de Workflows MVP: tabla `workflows` + `conversations`, motor `core/workflow_engine.py`, endpoints en `api/routes/workflows.py`, editor visual con React Flow (`@xyflow/react`).
- Chunking RAG por párrafos (1200/150) + metadata enriquecida (`doc_name`, `page`, `processed_at`).
- Saneo general: CORS explícito, no se expone `str(e)` al cliente, `AgentState` unificado.

### Estado anterior (2026-04-09)

### ✅ Completado

**Backend (Python/FastAPI):**
- [x] Core orchestrator con pipeline LangGraph
- [x] 6 agentes especializados (greeting, rag, plan, ideate, sensitive, fallback)
- [x] Language Detection heurística (ES/EN/PT) — sin falsos positivos ("ola" en "hola")
- [x] Intent Router (6 categorías) por heurísticas de keywords
- [x] Multi-LLM Client (OpenRouter) — modelos con IDs válidos (`provider/model`)
- [x] `api/routes/bots.py` — CRUD completo
- [x] `api/routes/agents.py` — GET/PUT config agentes por bot
- [x] `api/routes/documents.py` — upload, listado, borrado
- [x] Pipeline RAG completo y funcional:
  - `rag/processor.py` — extracción de texto (PDF, DOCX, TXT, MD) + chunking
  - `rag/embeddings.py` — embeddings via OpenRouter (`openai/text-embedding-ada-002`)
  - `rag/vector_store.py` — cosine similarity en Python sobre MongoDB (sin Atlas Vector Index)
  - Archivos guardados en `uploads/{bot_id}/`
  - Chunks guardados en MongoDB colección `doc_chunks`
  - Estado del documento actualizado en Supabase (`processing` → `ready` / `error`)
- [x] Chat endpoint async (`asyncio.to_thread`) para no bloquear el event loop

**Frontend (Next.js + React + TypeScript):**
- [x] Dashboard, crear bot, detalle de bot con 4 tabs
- [x] Tab Documentos: upload funcional, listado con polling (3s mientras `processing`), borrado
- [x] Tab Test Chat: conectado al orchestrator real
- [x] Tab Agentes: toggle + panel de edición con 21 modelos OpenRouter
- [x] Tab Settings: guarda en Supabase
- [x] `src/lib/api.ts` — cliente HTTP centralizado (botsApi, documentsApi, chatApi)

**Infraestructura:**
- [x] Supabase — tablas `bots` y `documents`
  - `documents` schema: `id`, `bot_id`, `name`, `status`, `file_size`, `created_at`
- [x] MongoDB Atlas — DB `agent_chat_builder`, colección `doc_chunks`
- [x] OpenRouter — LLM + embeddings funcionando

### 📋 Backlog

- [ ] Auth con Supabase
- [ ] Multi-tenancy (organizaciones)
- [ ] Sistema de Workflows — mezcla agentes + nodos de captura de datos (ver memory)
- [ ] WhatsApp channel por bot (Twilio)
- [ ] Telegram channel
- [ ] Web widget embebible
- [ ] Analytics dashboard
- [ ] Billing/planes

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (Next.js)                       │
│  Landing → Dashboard → Bot Builder → Test Chat              │
└─────────────────────────┬───────────────────────────────────┘
                          │ API Calls (src/lib/api.ts)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI)                        │
│  /api/bots  /api/bots/{id}/documents  /chat                 │
└─────────────────────────┬───────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│  Supabase   │   │  MongoDB    │   │  OpenRouter │
│  (Bots,     │   │  doc_chunks │   │  (LLM +     │
│   Docs)     │   │  cosine sim │   │  Embeddings)│
└─────────────┘   └─────────────┘   └─────────────┘
```

### Pipeline RAG

```
Upload → extract_sections (PDF/DOCX/TXT/MD) → chunk_sections (1200 chars, 150 overlap, respeta párrafos)
       → embed_batch (OpenRouter ada-002) → MongoDB doc_chunks (con doc_name, page, processed_at)
       → Supabase status = "ready"

Query → embed query → cosine similarity vs doc_chunks (filtrado por bot_id)
      → top_k=5 chunks → LLM con contexto → respuesta (con sources = {content, score, doc_name, page})
```

### Pipeline de Agentes (modo libre)

```
Input → Language Detection → Intent Router → Specialized Agent → Output
```

### Pipeline de Workflows (modo workflow)

```
Input → load workflow + conversation (Supabase)
      → si hay pending_capture → guardar var → avanzar
      → while current_node:
          capture: if skip → next, else set pending_capture → responder prompt, break
          agent:   invocar agent con system_prompt_override renderizado → responder, break
      → persistir conversation
```

Un bot opera en modo `free` (Orchestrator con LangGraph) o `workflow` (WorkflowEngine). Campo en `bots.workflow_mode`.

---

## Estructura del Proyecto

```
agentChatBuilder/
├── frontend/src/
│   ├── app/
│   │   ├── page.tsx                  # Landing
│   │   ├── dashboard/page.tsx        # Lista de bots
│   │   ├── bots/new/page.tsx         # Crear bot
│   │   └── bots/[id]/page.tsx        # Detalle bot (5 tabs)
│   ├── components/
│   │   ├── AgentCard.tsx
│   │   ├── AgentEditPanel.tsx
│   │   └── workflow/
│   │       ├── WorkflowEditor.tsx    # Editor visual React Flow
│   │       └── nodes/
│   │           ├── AgentNode.tsx
│   │           └── CaptureNode.tsx
│   └── lib/
│       ├── api.ts                    # botsApi, agentsApi, documentsApi, chatApi
│       └── workflowApi.ts            # workflowApi
│
├── api/
│   ├── main.py                       # FastAPI + /chat, /chat/start, orchestrator cache
│   └── routes/
│       ├── bots.py                   # CRUD bots + seed agentes
│       ├── agents.py                 # bot_agents persistidos en Supabase
│       ├── documents.py              # Upload + RAG processing
│       └── workflows.py              # GET/PUT/activate/deactivate workflow
│
├── core/
│   ├── orchestrator.py               # LangGraph pipeline (modo libre)
│   ├── workflow_engine.py            # Motor turn-based (modo workflow)
│   ├── state.py                      # GraphState + AgentState (único)
│   ├── agent_defaults.py             # Defaults + seed configs
│   └── config.py                     # Settings desde .env
│
├── agents/                           # 6 agentes especializados
├── rag/
│   ├── processor.py                  # extract_sections, chunk_sections (párrafos)
│   ├── embeddings.py                 # OpenRouter ada-002
│   └── vector_store.py               # Cosine similarity + metadata
├── llm/multi_llm_client.py           # 21 modelos via OpenRouter
├── db/
│   ├── supabase_client.py            # Singleton Supabase
│   └── migrations/
│       ├── 001_bot_agents.sql
│       └── 002_workflows.sql
└── uploads/                          # Archivos subidos (por bot_id)
```

---

## Variables de Entorno (.env)

```
SUPABASE_URL=https://lroiqesjdmocmawtazhd.supabase.co
SUPABASE_KEY=<anon key>
OPENROUTER_API_KEY=<key>
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/agent_chat_builder?retryWrites=true&w=majority
```

- Embeddings: `openai/text-embedding-ada-002` via OpenRouter (lento ~90s, funcional)
- MongoDB crea la DB automáticamente al primer insert

---

## Notas Técnicas Importantes

- **Modelos OpenRouter**: siempre usar IDs con prefijo `provider/model`. IDs sin prefijo dan 400.
- **VectorStore sin Atlas Index**: cosine similarity en Python. No requiere config en Atlas.
- **MongoDB colección**: chunks en `doc_chunks` con campos `doc_id, bot_id, chunk_index, content, embedding, doc_name, doc_summary, doc_keywords, page, processed_at`. Al borrar un Agente de IA o un documento, los chunks se purgan explícitamente desde `delete_bot` / `delete_document`.
- **Supabase tablas**: `bots`, `documents` (con `summary`, `keywords[]`), `bot_agents` (con `intents text[]`, `kind`, `graph_definition jsonb`, `metadata jsonb`), `workflows`, `conversations`, `chat_messages`. Schema completo en `db/migrations/` (001..007).
- **bot_id en /chat**: ahora es un campo Pydantic explícito en el body. Se pasa al Orchestrator y al WorkflowEngine.
- **conversation_id**: generado en el cliente (frontend localStorage por bot). El motor de workflows lo usa como PK de estado.
- **Orchestrator por bot**: no es singleton — `api/main.py:get_orchestrator_for_bot(bot_id)` con cache LRU TTL 30s. Se invalida al editar agentes o workflow.
- **workflow_mode**: columna en `bots`. `free` usa Orchestrator, `workflow` usa WorkflowEngine.
- **Prompt injection en workflows**: `captured_vars` se truncan a 500 chars y se reemplazan triple backticks. Endurecimiento pendiente.
- **Embedding latencia**: OpenRouter ada-002 ~90s. Timeout httpx read=180s.
- **Sin auth por ahora**.

---

## Comandos

```bash
# Backend
cd /Users/daniel/Desktop/Dev/agentChatBuilder
source venv/bin/activate
uvicorn api.main:app --reload --port 8000

# Frontend
cd /Users/daniel/Desktop/Dev/agentChatBuilder/frontend
npm run dev
# → http://localhost:3000
```
