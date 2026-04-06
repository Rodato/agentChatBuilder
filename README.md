# Agent Chat Builder

Plataforma para construir chatbots con arquitectura de agentes especializados.

## Stack Tecnológico

- **Backend**: FastAPI + Python 3.11
- **Vector DB**: MongoDB Atlas
- **User DB**: Supabase (PostgreSQL)
- **LLM Gateway**: OpenRouter
- **Embeddings**: OpenAI ada-002
- **Channels**: WhatsApp (Twilio), Telegram, Web

## Estructura del Proyecto

```
agentChatBuilder/
├── core/           # Orquestador y estado
├── agents/         # Agentes especializados
├── llm/            # Clientes LLM
├── rag/            # Sistema RAG
├── memory/         # Sistema de memoria
├── channels/       # Canales (WhatsApp, Telegram, Web)
├── api/            # API REST para UI
├── config/         # Configuraciones
├── scripts/        # Scripts utilitarios
└── tests/          # Tests
```

## Setup

```bash
# Crear virtual environment
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# Ejecutar en desarrollo
uvicorn api.main:app --reload --port 8000
```

## Documentación

- [Arquitectura y Aprendizajes](./docs/ARCHITECTURE.md)
- [Guía de Agentes](./docs/AGENTS.md)
- [API Reference](./docs/API.md)
