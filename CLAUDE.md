# CLAUDE.md - Agent Chat Builder

## Proyecto

**Nombre**: Agent Chat Builder
**Tipo**: Plataforma SaaS para construir chatbots con agentes y RAG sin código
**Inicio**: 2026-02-01
**Basado en**: Aprendizajes de Puddle Assistant
**Fase actual**: MVP - Frontend conectado al backend real con Supabase
**Repo**: https://github.com/Rodato/agentChatBuilder

---

## Estado Actual (2026-04-05)

### ✅ Completado

**Backend (Python/FastAPI):**
- [x] Estructura de proyecto completa
- [x] Core orchestrator con pipeline LangGraph
- [x] GraphState y AgentState definidos
- [x] 6 agentes especializados (greeting, rag, plan, ideate, sensitive, fallback)
- [x] Language Agent (detección ES/EN/PT)
- [x] Intent Router (6 categorías)
- [x] Multi-LLM Client (OpenRouter)
- [x] Vector Store structure (MongoDB)
- [x] Memory Manager structure (Supabase)
- [x] WhatsApp webhook async (Twilio)
- [x] API REST completa
- [x] `db/supabase_client.py` — singleton cliente Supabase
- [x] `api/routes/bots.py` — CRUD completo (GET/POST/PUT/DELETE)
- [x] `api/routes/agents.py` — GET/PUT config de agentes por bot
- [x] Virtual environment configurado
- [x] Dependencias instaladas

**Frontend (Next.js 16 + React + TypeScript):**
- [x] Proyecto Next.js inicializado
- [x] shadcn/ui configurado
- [x] Tailwind CSS v4
- [x] Landing page
- [x] Dashboard conectado a API real (GET /api/bots)
- [x] Crear bot conectado a API real (POST /api/bots)
- [x] Detalle de bot con 4 tabs:
  - Settings → guarda en Supabase (PUT /api/bots/{id})
  - Agents (toggle + edit panel)
  - Documents (lista — upload pendiente)
  - Test Chat → conectado al orchestrator real (POST /chat)
- [x] `src/lib/api.ts` — cliente HTTP para el backend
- [x] Toda la UI en español

**Infraestructura:**
- [x] Supabase configurado — tablas `bots` y `documents` creadas
- [x] MongoDB Atlas configurado — DB `agent_chat_builder` (se crea automáticamente al primer insert)
- [x] `.env` con todas las variables necesarias

### ⏳ Pendiente (MVP)

- [ ] Upload de documentos + procesamiento RAG
- [ ] Embeddings con OpenRouter (model: `openai/text-embedding-ada-002` o `google/gemini-embedding-001`)
- [ ] LLM real funcionando en el chat (OpenRouter key ya configurada)

### 📋 Backlog (Post-MVP)

- [ ] Auth con Supabase
- [ ] Multi-tenancy (organizaciones)
- [ ] WhatsApp channel por bot
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
│  /api/bots  /api/bots/{id}/agents  /chat                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│  Supabase   │   │  MongoDB    │   │  OpenRouter │
│  (Bots,     │   │  (Vectors,  │   │  (LLM +     │
│   Docs)     │   │   RAG)      │   │  Embeddings)│
└─────────────┘   └─────────────┘   └─────────────┘
```

### Pipeline de Agentes

```
Input → Language Detection → Intent Router → Specialized Agent → Output
```

### Intents Soportados
- **GREETING**: Saludos → Welcome Message
- **FACTUAL**: Información → RAG Agent
- **PLAN**: Implementar/adaptar → Workshop Agent
- **IDEATE**: Ideas creativas → Brainstorming Agent
- **SENSITIVE**: Temas delicados → Safe Edge Agent
- **AMBIGUOUS**: Poco claro → Fallback Agent

---

## Estructura del Proyecto

```
agentChatBuilder/
├── frontend/                    # Next.js 16 + React
│   ├── src/app/
│   │   ├── page.tsx            # Landing
│   │   ├── dashboard/          # Lista de bots (API real)
│   │   ├── bots/new/           # Crear bot (API real)
│   │   └── bots/[id]/          # Detalle bot (4 tabs, API real)
│   ├── src/components/
│   │   ├── AgentCard.tsx
│   │   └── AgentEditPanel.tsx
│   └── src/lib/
│       └── api.ts              # Cliente HTTP centralizado
│
├── db/
│   └── supabase_client.py      # Singleton cliente Supabase
│
├── core/                        # Orchestrator + State
├── agents/                      # 6 agentes especializados
├── llm/                         # Multi-LLM client (OpenRouter)
├── rag/                         # Vector store + Embeddings
├── memory/                      # Supabase memory manager
├── channels/                    # WhatsApp, Telegram, Web
├── api/
│   ├── main.py
│   └── routes/
│       ├── bots.py             # CRUD bots
│       └── agents.py           # Config agentes por bot
└── .env                         # Variables de entorno
```

---

## Variables de Entorno (.env)

```
SUPABASE_URL=https://lroiqesjdmocmawtazhd.supabase.co
SUPABASE_KEY=<anon key>
OPENROUTER_API_KEY=<key>
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/agent_chat_builder?retryWrites=true&w=majority
```

- **NO usar OpenAI** para embeddings — usar OpenRouter con `openai/text-embedding-ada-002` o `google/gemini-embedding-001`
- MongoDB crea la DB `agent_chat_builder` automáticamente al primer insert

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

---

## Stack Tecnológico

| Capa | Tecnología |
|------|------------|
| Frontend | Next.js 16 + React + TypeScript |
| UI Components | shadcn/ui + Tailwind CSS v4 |
| Backend | FastAPI (Python 3.11) |
| User DB | Supabase (PostgreSQL) — tablas: bots, documents |
| Vector DB | MongoDB Atlas — DB: agent_chat_builder |
| LLM Gateway | OpenRouter |
| Embeddings | OpenRouter (`openai/text-embedding-ada-002` o `google/gemini-embedding-001`) |
| Auth | Supabase Auth (pendiente) |
| Channels | Twilio (WhatsApp), Telegram |

---

## Notas Técnicas

- **Sin auth por ahora**: MVP enfocado en funcionalidad core
- **Arquitectura async**: Webhooks responden inmediato, procesan en background
- **Filter-first RAG**: Detectar programa/categoría antes de buscar
- **Multi-LLM via OpenRouter**: Mistral (rápido), GPT-4o-mini (análisis), Gemini (creativo)
- **Frontend API base URL**: `NEXT_PUBLIC_API_URL` (default: `http://localhost:8000`)

---

## Próxima Sesión

1. Verificar que backend + frontend arrancan sin errores
2. Upload de documentos funcional (tab Documents)
3. Pipeline RAG: chunking → embeddings (OpenRouter) → MongoDB
4. Test chat con LLM real via OpenRouter
