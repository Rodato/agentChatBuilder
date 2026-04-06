# Agent Chat Builder - Documento de Aprendizajes y Arquitectura Base

> Documento de referencia basado en los aprendizajes del proyecto **Puddle Assistant** (2026-01)
> Para usar como punto de partida en el desarrollo de una plataforma de construcción de chatbots con agentes.

---

## 1. Resumen Ejecutivo

### Lo que funcionó en Puddle Assistant
- **Arquitectura de agentes especializados** con orquestador central
- **Intent routing** con 6 categorías claras (GREETING, FACTUAL, PLAN, IDEATE, SENSITIVE, AMBIGUOUS)
- **Multi-LLM strategy** optimizando costo/calidad por tipo de tarea
- **Arquitectura async non-blocking** para evitar timeouts
- **Memory hierarchy** con scoring de importancia
- **Filter-first search** para optimizar búsquedas semánticas

### Problemas resueltos que debes anticipar
1. **Timeouts de webhooks** → Respuesta inmediata + procesamiento en background
2. **Un solo agente no sirve para todo** → Intent router + agentes especializados
3. **Detección de idioma con keywords falla** → Usar LLM para detection
4. **RAG sin filtros devuelve ruido** → Filter detection antes de búsqueda semántica
5. **Mensajes duplicados** → Orquestador centralizado maneja flujo completo

---

## 2. Arquitectura de Agentes Recomendada

### 2.1 Patrón: Orquestador + Agentes Especializados

```
┌─────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │ Language │→ │ Filters  │→ │  Intent  │→ │ Specialized Agent│ │
│  │ Detector │  │ Detector │  │  Router  │  │                  │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼           ▼           ▼           ▼           ▼       ▼
   ┌────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌────────┐ ┌────────┐
   │Greeting│ │   RAG   │ │Workshop │ │Brainstorm│ │SafeEdge│ │Fallback│
   │ Agent  │ │  Agent  │ │  Agent  │ │  Agent   │ │ Agent  │ │ Agent  │
   └────────┘ └─────────┘ └─────────┘ └──────────┘ └────────┘ └────────┘
```

### 2.2 Estado Compartido (GraphState)

```python
from typing import TypedDict, Optional, List, Dict, Any

class GraphState(TypedDict):
    # Input
    user_input: str
    user_id: Optional[str]
    conversation_id: Optional[str]

    # Detection results
    language: str  # es, en, pt
    language_config: Dict[str, Any]
    detected_filters: Dict[str, Any]  # program, category, audience

    # Routing
    intent: str  # GREETING, FACTUAL, PLAN, IDEATE, SENSITIVE, AMBIGUOUS
    intent_confidence: float  # 0.0 - 1.0

    # Agent output
    response: str
    sources: List[Dict[str, Any]]
    agent_used: str

    # Debug
    debug_info: Dict[str, Any]
    processing_time_ms: int
```

### 2.3 Base Agent Pattern

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class AgentState:
    user_input: str
    language: str
    language_config: dict
    mode: str  # intent
    context: str
    response: str
    sources: list
    metadata: dict
    debug_info: dict

class BaseAgent(ABC):
    """Clase base para todos los agentes especializados."""

    def __init__(self, name: str, llm_client: Any):
        self.name = name
        self.llm = llm_client

    @abstractmethod
    def process(self, state: AgentState) -> AgentState:
        """Procesa el estado y retorna estado modificado."""
        pass

    def should_process(self, state: AgentState) -> bool:
        """Validación antes de procesar."""
        return True

    def log_processing(self, state: AgentState):
        """Logging consistente."""
        print(f"[{self.name}] Processing: {state.user_input[:50]}...")

    def add_debug_info(self, state: AgentState, info: Dict[str, Any]):
        """Agregar info de debug."""
        state.debug_info[self.name] = info
        return state
```

---

## 3. Intent Router - El Corazón del Sistema

### 3.1 Categorías de Intent Recomendadas

| Intent | Descripción | Agente | LLM Recomendado |
|--------|-------------|--------|-----------------|
| **GREETING** | Saludos simples | Welcome Message | N/A (template) |
| **FACTUAL** | Información específica | RAG Agent | Mistral-8b |
| **PLAN** | Cómo implementar/adaptar | Workshop Agent | GPT-4o-mini |
| **IDEATE** | Ideas creativas nuevas | Brainstorming Agent | Gemini 2.5-flash |
| **SENSITIVE** | Temas delicados | Safe Edge Agent | GPT-4o-mini |
| **AMBIGUOUS** | Input poco claro | Fallback Agent | Mistral-8b |

### 3.2 Prompt para Intent Detection

```python
INTENT_DETECTION_PROMPT = """You are an intent classifier. Classify the user message into ONE of these categories:

GREETING - Simple greetings, hellos, hi, good morning, etc.
FACTUAL - Questions seeking specific information, facts, data, "what is", "how many"
PLAN - Requests to adapt, implement, plan, schedule, organize activities
IDEATE - Requests for new ideas, creativity, brainstorming, innovation
SENSITIVE - Topics involving trauma, religion, family conflict, identity crisis
AMBIGUOUS - Unclear intent, too vague, needs clarification

User message: "{user_input}"
Language: {language}

Respond ONLY with a JSON object:
{{"intent": "CATEGORY", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}
"""
```

### 3.3 Lección Aprendida: LLM > Keywords

```python
# ❌ MAL - Keywords fallan con variaciones
def detect_greeting_bad(text):
    greetings = ["hola", "hello", "hi", "buenos días"]
    return any(g in text.lower() for g in greetings)

# ✅ BIEN - LLM entiende contexto
def detect_greeting_good(text, llm_client):
    response = llm_client.complete(
        f"Is this a greeting? '{text}' Answer: yes/no"
    )
    return "yes" in response.lower()
```

---

## 4. Sistema RAG Optimizado

### 4.1 Arquitectura RAG con Filtros

```
┌───────────────────────────────────────────────────────────┐
│                     RAG PIPELINE                          │
│                                                           │
│  Query → Filter Detection → MongoDB Query Builder         │
│              │                    │                       │
│              │                    ▼                       │
│              │            ┌──────────────┐                │
│              │            │   Filters    │                │
│              │            │ - program    │                │
│              │            │ - category   │                │
│              │            │ - audience   │                │
│              │            └──────┬───────┘                │
│              │                   │                        │
│              ▼                   ▼                        │
│        ┌──────────┐      ┌──────────────┐                 │
│        │ Embedding│  +   │ MongoDB $and │                 │
│        │  Query   │      │   Filters    │                 │
│        └────┬─────┘      └──────┬───────┘                 │
│             │                   │                         │
│             └─────────┬─────────┘                         │
│                       ▼                                   │
│              ┌────────────────┐                           │
│              │ Vector Search  │                           │
│              │ + Pre-filters  │                           │
│              └────────┬───────┘                           │
│                       │                                   │
│                       ▼                                   │
│              ┌────────────────┐                           │
│              │   Top-K Docs   │                           │
│              └────────┬───────┘                           │
│                       │                                   │
│                       ▼                                   │
│              ┌────────────────┐                           │
│              │ LLM Answer Gen │                           │
│              └────────────────┘                           │
└───────────────────────────────────────────────────────────┘
```

### 4.2 Estructura de Documento para MongoDB

```json
{
  "_id": "ObjectId",
  "document_name": "Manual de Facilitación",
  "document_category": "manual",
  "target_audiences": ["educators", "facilitators"],
  "program_name": "Program H",
  "section_header": "2.1 Fundamentos",
  "content": "Texto del chunk...",
  "embedding": [0.123, -0.456, ...],
  "metadata": {
    "page_number": 15,
    "chunk_index": 42,
    "language": "es",
    "created_at": "2026-01-10T00:00:00Z"
  }
}
```

### 4.3 Lección: Filtrar ANTES de Buscar

```python
# ❌ MAL - Buscar todo y luego filtrar (lento, ruidoso)
def search_bad(query, collection):
    results = vector_search(query, top_k=100)
    filtered = [r for r in results if r['program'] == 'Program H']
    return filtered[:5]

# ✅ BIEN - Construir query con filtros (eficiente)
def search_good(query, collection, filters):
    pipeline = [
        {
            "$vectorSearch": {
                "queryVector": get_embedding(query),
                "path": "embedding",
                "numCandidates": 100,
                "limit": 5,
                "filter": {
                    "program_name": {"$eq": filters.get("program")},
                    "document_category": {"$in": filters.get("categories", [])}
                }
            }
        }
    ]
    return collection.aggregate(pipeline)
```

---

## 5. Arquitectura Async para Webhooks

### 5.1 El Problema del Timeout

```
Twilio/WhatsApp webhook timeout: 15 segundos
RAG + LLM processing time: 20-25 segundos
Resultado: ❌ Timeout, mensaje perdido
```

### 5.2 La Solución: Async Non-Blocking

```python
from fastapi import FastAPI, BackgroundTasks
from twilio.rest import Client
import asyncio
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=10)
twilio_client = Client(ACCOUNT_SID, AUTH_TOKEN)

@app.post("/webhook/whatsapp")
async def webhook(request: Request):
    data = await request.form()
    message = data.get("Body")
    from_number = data.get("From")

    # 1. Responder INMEDIATAMENTE a Twilio (200 OK vacío)
    # 2. Procesar en background
    asyncio.create_task(process_and_respond(message, from_number))

    # Twilio recibe 200 OK antes de timeout
    return Response(content="", media_type="text/xml")

async def process_and_respond(message: str, to_number: str):
    """Procesamiento en background."""
    try:
        # Ejecutar en thread pool (CPU-bound)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            executor,
            process_with_aly,  # Tu función de procesamiento
            message
        )

        # Enviar respuesta ACTIVAMENTE vía Twilio API
        twilio_client.messages.create(
            body=response,
            from_=TWILIO_NUMBER,
            to=to_number
        )
    except Exception as e:
        logger.error(f"Error processing: {e}")
        # Enviar mensaje de error genérico
        twilio_client.messages.create(
            body="Lo siento, hubo un error. Por favor intenta de nuevo.",
            from_=TWILIO_NUMBER,
            to=to_number
        )
```

### 5.3 Diagrama de Flujo Async

```
Usuario envía mensaje
        │
        ▼
┌───────────────┐
│ Twilio Webhook│ ──────────────────────────────┐
└───────┬───────┘                               │
        │                                       │
        ▼                                       │
┌───────────────┐                               │
│ 200 OK (vacío)│ ← Respuesta inmediata         │
└───────────────┘                               │
                                                │
        ┌───────────────────────────────────────┘
        │ Background Task
        ▼
┌───────────────┐
│ ThreadPool    │
│ Executor      │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ ALY Pipeline  │
│ (20-25 seg)   │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ Twilio API    │
│ send_message()│
└───────┬───────┘
        │
        ▼
Usuario recibe respuesta
```

---

## 6. Sistema de Memoria

### 6.1 Jerarquía de Memoria

```
┌─────────────────────────────────────────────┐
│            CONTEXT WINDOW                   │
│  ┌───────────────────────────────────────┐  │
│  │ Últimos 3-5 mensajes de conversación  │  │
│  │ (memoria corto plazo)                 │  │
│  └───────────────────────────────────────┘  │
│                    +                        │
│  ┌───────────────────────────────────────┐  │
│  │ Top 5 memorias por importancia        │  │
│  │ (memoria largo plazo filtrada)        │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

### 6.2 Scoring de Importancia

```python
IMPORTANCE_SCORES = {
    "safe_edge": 0.9,      # Temas sensibles - máxima prioridad
    "workshop": 0.8,       # Implementaciones - alta prioridad
    "plan": 0.7,           # Planes discutidos
    "ideate": 0.7,         # Ideas generadas
    "rag": 0.5,            # Información general
    "greeting": 0.1,       # Saludos - baja prioridad
    "fallback": 0.3,       # Clarificaciones
}

def calculate_memory_importance(agent_type: str, content: str) -> float:
    base_score = IMPORTANCE_SCORES.get(agent_type, 0.5)

    # Bonus por contenido sensible detectado
    sensitive_keywords = ["trauma", "abuse", "crisis", "conflict"]
    if any(kw in content.lower() for kw in sensitive_keywords):
        base_score = min(1.0, base_score + 0.2)

    return base_score
```

### 6.3 Schema de Base de Datos (Supabase/PostgreSQL)

```sql
-- Usuarios
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number TEXT UNIQUE NOT NULL,
    preferred_language TEXT DEFAULT 'es',
    first_interaction_at TIMESTAMPTZ DEFAULT NOW(),
    last_interaction_at TIMESTAMPTZ DEFAULT NOW(),
    total_messages INTEGER DEFAULT 0,
    user_context JSONB DEFAULT '{}'
);

-- Conversaciones
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    session_started_at TIMESTAMPTZ DEFAULT NOW(),
    session_ended_at TIMESTAMPTZ,
    message_count INTEGER DEFAULT 0,
    detected_topics TEXT[],
    session_language TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

-- Mensajes
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    user_id UUID REFERENCES users(id),
    user_message TEXT NOT NULL,
    bot_response TEXT NOT NULL,
    agent_type TEXT,
    detected_language TEXT,
    detected_intent TEXT,
    response_time_ms INTEGER,
    sources_used JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Memoria conversacional
CREATE TABLE conversation_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    user_id UUID REFERENCES users(id),
    memory_type TEXT, -- context, preference, goal, sensitive_topic
    memory_content TEXT,
    memory_summary TEXT,
    importance_score FLOAT DEFAULT 0.5,
    reference_count INTEGER DEFAULT 0,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '30 days'),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index para búsquedas rápidas
CREATE INDEX idx_memory_importance ON conversation_memory(user_id, importance_score DESC);
CREATE INDEX idx_memory_active ON conversation_memory(user_id, is_active) WHERE is_active = TRUE;
```

---

## 7. Multi-LLM Strategy

### 7.1 Recomendación de LLMs por Tarea

| Tarea | LLM Recomendado | Razón | Costo Relativo |
|-------|-----------------|-------|----------------|
| Language Detection | Mistral-8b | Rápido, suficiente | $ |
| Intent Classification | Mistral-8b | Rápido, suficiente | $ |
| RAG Answer Generation | Mistral-8b | Balance costo/calidad | $ |
| Workshop/Planning | GPT-4o-mini | Análisis profundo | $$ |
| Brainstorming | Gemini 2.5-flash | Creatividad | $$ |
| Sensitive Topics | GPT-4o-mini | Precisión, cuidado | $$ |
| Embeddings | OpenAI ada-002 | Estándar industria | $ |

### 7.2 Wrapper Multi-LLM

```python
from enum import Enum
from typing import Optional

class LLMProvider(Enum):
    OPENROUTER_MISTRAL = "mistralai/mistral-7b-instruct"
    OPENROUTER_GPT4O = "openai/gpt-4o-mini"
    OPENROUTER_GEMINI = "google/gemini-2.5-flash"
    OPENAI_DIRECT = "gpt-4o-mini"

class MultiLLMClient:
    def __init__(self, openrouter_key: str, openai_key: str):
        self.openrouter_key = openrouter_key
        self.openai_key = openai_key

    def complete(
        self,
        prompt: str,
        provider: LLMProvider,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> str:
        if provider.name.startswith("OPENROUTER"):
            return self._call_openrouter(prompt, provider.value, temperature, max_tokens)
        else:
            return self._call_openai(prompt, provider.value, temperature, max_tokens)

    def get_provider_for_task(self, task: str) -> LLMProvider:
        """Selecciona el mejor LLM para cada tarea."""
        task_mapping = {
            "detection": LLMProvider.OPENROUTER_MISTRAL,
            "rag": LLMProvider.OPENROUTER_MISTRAL,
            "workshop": LLMProvider.OPENROUTER_GPT4O,
            "brainstorm": LLMProvider.OPENROUTER_GEMINI,
            "sensitive": LLMProvider.OPENROUTER_GPT4O,
        }
        return task_mapping.get(task, LLMProvider.OPENROUTER_MISTRAL)
```

---

## 8. Personalidad del Bot (Configurable)

### 8.1 Estructura de Configuración

```python
BOT_PERSONALITY = {
    "name": "ALY",
    "role": "Educational Assistant",

    "core_identity": """
    You are ALY, a knowledgeable and supportive assistant specialized in
    [DOMAIN]. You have extensive experience working with [TARGET_USERS].
    """,

    "personality_traits": [
        "Warm and approachable",
        "Professional but not cold",
        "Encouraging without being patronizing",
        "Clear and simple language",
        "Culturally sensitive"
    ],

    "interaction_modes": {
        "factual": {
            "style": "Direct, evidence-based",
            "temperature": 0.3,
            "focus": "Accuracy over creativity"
        },
        "workshop": {
            "style": "Methodological, step-by-step",
            "temperature": 0.5,
            "focus": "Practical implementation"
        },
        "brainstorming": {
            "style": "Creative, lateral thinking",
            "temperature": 0.7,
            "focus": "Innovation and possibilities"
        }
    },

    "response_guidelines": [
        "Keep responses concise for chat format",
        "Use bullet points for lists",
        "Avoid jargon unless necessary",
        "Always validate user's context",
        "End with actionable next step when appropriate"
    ],

    "forbidden_actions": [
        "Never give medical/legal/therapeutic advice",
        "Never speculate on sensitive topics",
        "Never break character",
        "Never share personal opinions on controversial topics"
    ]
}
```

### 8.2 Welcome Messages (Multi-idioma)

```python
WELCOME_MESSAGES = {
    "es": """
¡Hola! Soy {bot_name}, tu asistente de {domain}.

Puedo ayudarte con:
• Información sobre nuestros programas
• Ideas para actividades
• Adaptación de materiales
• Responder tus preguntas

¿En qué puedo ayudarte hoy?
""",
    "en": """
Hi! I'm {bot_name}, your {domain} assistant.

I can help you with:
• Information about our programs
• Activity ideas
• Material adaptation
• Answering your questions

How can I help you today?
""",
    "pt": """
Olá! Sou {bot_name}, seu assistente de {domain}.

Posso te ajudar com:
• Informações sobre nossos programas
• Ideias para atividades
• Adaptação de materiais
• Responder suas perguntas

Como posso te ajudar hoje?
"""
}
```

---

## 9. Estructura de Proyecto Recomendada

```
agent-chat-builder/
├── README.md
├── CLAUDE.md                    # Memoria del proyecto
├── requirements.txt
├── .env.example
│
├── core/                        # Núcleo del sistema
│   ├── __init__.py
│   ├── orchestrator.py          # Orquestador principal
│   ├── state.py                 # GraphState definitions
│   └── config.py                # Configuración global
│
├── agents/                      # Agentes especializados
│   ├── __init__.py
│   ├── base_agent.py            # Clase base
│   ├── language_agent.py
│   ├── intent_router.py
│   ├── rag_agent.py
│   ├── workshop_agent.py
│   ├── brainstorming_agent.py
│   ├── safe_edge_agent.py
│   └── fallback_agent.py
│
├── llm/                         # Clientes LLM
│   ├── __init__.py
│   ├── multi_llm_client.py
│   ├── openrouter_client.py
│   └── openai_client.py
│
├── rag/                         # Sistema RAG
│   ├── __init__.py
│   ├── vector_store.py          # MongoDB/Pinecone abstraction
│   ├── embeddings.py
│   ├── filter_detection.py
│   └── answer_generator.py
│
├── memory/                      # Sistema de memoria
│   ├── __init__.py
│   ├── memory_manager.py
│   ├── supabase_client.py
│   └── context_builder.py
│
├── channels/                    # Canales de comunicación
│   ├── __init__.py
│   ├── whatsapp/
│   │   ├── __init__.py
│   │   ├── webhook.py
│   │   └── twilio_client.py
│   ├── telegram/
│   │   └── ...
│   └── web/
│       └── ...
│
├── api/                         # API REST para UI
│   ├── __init__.py
│   ├── main.py                  # FastAPI app
│   ├── routes/
│   │   ├── bots.py
│   │   ├── agents.py
│   │   ├── analytics.py
│   │   └── users.py
│   └── schemas/
│       └── ...
│
├── ui/                          # Frontend (si aplica)
│   └── ...
│
├── config/                      # Configuraciones
│   ├── personalities/           # Personalidades de bots
│   ├── prompts/                 # Prompts templates
│   └── languages/               # Traducciones
│
├── scripts/                     # Scripts utilitarios
│   ├── upload_documents.py
│   ├── test_agents.py
│   └── migrate_db.py
│
└── tests/
    ├── test_agents/
    ├── test_rag/
    └── test_channels/
```

---

## 10. Checklist para Nuevo Proyecto

### Setup Inicial
- [ ] Crear estructura de carpetas
- [ ] Configurar virtual environment
- [ ] Instalar dependencias base
- [ ] Configurar variables de entorno
- [ ] Setup MongoDB Atlas (o alternativa)
- [ ] Setup Supabase (o PostgreSQL)

### Core Development
- [ ] Implementar GraphState
- [ ] Implementar BaseAgent
- [ ] Implementar Orchestrator
- [ ] Implementar Language Detection
- [ ] Implementar Intent Router
- [ ] Implementar al menos 3 agentes especializados

### RAG System
- [ ] Configurar vector store
- [ ] Implementar pipeline de embeddings
- [ ] Implementar filter detection
- [ ] Implementar búsqueda semántica
- [ ] Implementar answer generation

### Channels
- [ ] Implementar webhook base
- [ ] Implementar arquitectura async
- [ ] Integrar Twilio/WhatsApp
- [ ] Testing end-to-end

### Memory System
- [ ] Crear schema de base de datos
- [ ] Implementar memory manager
- [ ] Implementar context builder
- [ ] Implementar cleanup automático

### UI (Agent Builder)
- [ ] Diseñar wireframes
- [ ] Implementar CRUD de bots
- [ ] Implementar configurador de agentes
- [ ] Implementar dashboard de analytics
- [ ] Implementar testing/preview

---

## 11. Errores a Evitar

### 1. No usar arquitectura async desde el inicio
```python
# ❌ Webhook síncrono = timeouts garantizados
@app.post("/webhook")
def webhook(request):
    response = process_slowly(request)  # 20 segundos
    return response  # Twilio ya hizo timeout

# ✅ Async desde día 1
@app.post("/webhook")
async def webhook(request):
    asyncio.create_task(process_in_background(request))
    return Response(status_code=200)  # Inmediato
```

### 2. Un solo agente para todo
```python
# ❌ Un agente genérico = respuestas mediocres
response = generic_agent.process(any_query)

# ✅ Routing inteligente = respuestas especializadas
intent = intent_router.classify(query)
agent = agent_registry[intent]
response = agent.process(query)
```

### 3. RAG sin filtros
```python
# ❌ Buscar en todo = ruido
results = vector_search(query, all_documents)

# ✅ Filtrar primero = relevancia
filters = detect_filters(query)  # programa, categoría, audiencia
results = vector_search(query, documents, filters=filters)
```

### 4. Keywords para detección de idioma/intent
```python
# ❌ Keywords fallan con variaciones
if "hola" in text.lower():
    language = "es"

# ✅ LLM entiende contexto
language = llm.detect_language(text)  # "qué tal?" → es
```

### 5. No manejar errores en background tasks
```python
# ❌ Error silencioso = usuario nunca recibe respuesta
async def process():
    response = aly.process(message)  # Puede fallar
    send_message(response)

# ✅ Siempre manejar errores
async def process():
    try:
        response = aly.process(message)
        send_message(response)
    except Exception as e:
        logger.error(f"Error: {e}")
        send_message("Lo siento, hubo un error. Intenta de nuevo.")
```

---

## 12. Stack Tecnológico Validado

| Componente | Tecnología | Alternativas |
|------------|------------|--------------|
| **Backend** | FastAPI + Python 3.11 | Flask, Django |
| **Async** | asyncio + ThreadPoolExecutor | Celery |
| **Vector DB** | MongoDB Atlas | Pinecone, Weaviate, Qdrant |
| **User DB** | Supabase (PostgreSQL) | Firebase, raw PostgreSQL |
| **LLM Gateway** | OpenRouter | LiteLLM, direct APIs |
| **Embeddings** | OpenAI ada-002 | Cohere, local models |
| **WhatsApp** | Twilio | MessageBird, Vonage |
| **Orchestration** | LangGraph | Custom, LangChain |
| **Deployment** | VPS + Docker | Railway, Render, AWS |

---

## 13. Métricas a Trackear

```python
METRICS_TO_TRACK = {
    # Performance
    "response_time_ms": "Tiempo total de respuesta",
    "llm_latency_ms": "Latencia de llamadas LLM",
    "rag_search_time_ms": "Tiempo de búsqueda vectorial",

    # Quality
    "intent_confidence": "Confianza del intent router",
    "rag_similarity_score": "Score de similitud RAG",
    "user_satisfaction": "Feedback explícito (si aplica)",

    # Usage
    "messages_per_user": "Mensajes por usuario",
    "sessions_per_user": "Sesiones por usuario",
    "agent_distribution": "% uso por tipo de agente",
    "language_distribution": "% por idioma",

    # Errors
    "error_rate": "% de errores",
    "timeout_rate": "% de timeouts",
    "fallback_rate": "% que llega a fallback agent",
}
```

---

## 14. Próximos Pasos para Agent Chat Builder

1. **Definir MVP**: ¿Qué funcionalidades mínimas necesita la plataforma?
2. **Diseñar UI/UX**: Wireframes del builder de agentes
3. **Arquitectura multi-tenant**: ¿Cómo aislar bots de diferentes usuarios?
4. **Sistema de templates**: Personalidades y agentes pre-configurados
5. **Marketplace de agentes**: ¿Permitir compartir configuraciones?
6. **Pricing model**: ¿Por mensajes? ¿Por bot? ¿Por features?

---

*Documento generado el 2026-02-01 basado en aprendizajes de Puddle Assistant*
