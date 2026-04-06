# Agent Chat Builder - SaaS Architecture

## Overview

Plataforma SaaS para crear chatbots con agentes y RAG sin código.

```
┌──────────────────────────────────────────────────────────────────┐
│                         USUARIOS                                 │
│                    (Browser / Mobile)                            │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                      FRONTEND (Next.js)                          │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐    │
│  │   Login    │ │ Dashboard  │ │ Bot Builder│ │  Analytics │    │
│  │  Register  │ │   (Bots)   │ │  (Visual)  │ │  (Metrics) │    │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘    │
└──────────────────────────┬───────────────────────────────────────┘
                           │ API Calls
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                      BACKEND (FastAPI)                           │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐    │
│  │  Auth API  │ │  Bots API  │ │  Docs API  │ │ Channels   │    │
│  │ (Supabase) │ │   (CRUD)   │ │  (Upload)  │ │   API      │    │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘    │
└──────────────────────────┬───────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Supabase   │  │   MongoDB    │  │   Channels   │
│  (Users,     │  │   Atlas      │  │  (Twilio,    │
│   Bots,      │  │  (Vectors,   │  │   Telegram,  │
│   Config)    │  │   RAG)       │  │   Web)       │
└──────────────┘  └──────────────┘  └──────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14 + React + TypeScript |
| UI Components | shadcn/ui + Tailwind CSS |
| Auth | Supabase Auth |
| Backend | FastAPI (Python) |
| User Database | Supabase (PostgreSQL) |
| Vector Database | MongoDB Atlas |
| LLM Gateway | OpenRouter |
| File Storage | Supabase Storage |
| Deployment | Vercel (frontend) + Railway/VPS (backend) |

## Database Schema (Supabase)

### Users & Auth (Supabase Auth built-in)
- Managed by Supabase Auth

### Organizations
```sql
organizations (
    id UUID PRIMARY KEY,
    name TEXT,
    owner_id UUID REFERENCES auth.users,
    plan TEXT DEFAULT 'free',  -- free, pro, enterprise
    created_at TIMESTAMPTZ
)
```

### Bots
```sql
bots (
    id UUID PRIMARY KEY,
    organization_id UUID REFERENCES organizations,
    name TEXT,
    description TEXT,
    personality JSONB,        -- Bot personality config
    welcome_message JSONB,    -- Per language
    enabled_intents TEXT[],   -- GREETING, FACTUAL, PLAN, etc.
    llm_config JSONB,         -- Model preferences
    is_active BOOLEAN,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
)
```

### Documents (for RAG)
```sql
documents (
    id UUID PRIMARY KEY,
    bot_id UUID REFERENCES bots,
    name TEXT,
    file_path TEXT,           -- Supabase Storage path
    status TEXT,              -- pending, processing, ready, failed
    chunk_count INTEGER,
    metadata JSONB,
    created_at TIMESTAMPTZ
)
```

### Channels
```sql
channels (
    id UUID PRIMARY KEY,
    bot_id UUID REFERENCES bots,
    type TEXT,                -- whatsapp, telegram, web
    config JSONB,             -- Channel-specific config (API keys, etc.)
    webhook_url TEXT,
    is_active BOOLEAN,
    created_at TIMESTAMPTZ
)
```

### Conversations & Messages
```sql
conversations (
    id UUID PRIMARY KEY,
    bot_id UUID REFERENCES bots,
    channel_id UUID REFERENCES channels,
    external_user_id TEXT,    -- Phone number, telegram ID, etc.
    metadata JSONB,
    created_at TIMESTAMPTZ
)

messages (
    id UUID PRIMARY KEY,
    conversation_id UUID REFERENCES conversations,
    role TEXT,                -- user, assistant
    content TEXT,
    agent_used TEXT,
    intent TEXT,
    response_time_ms INTEGER,
    created_at TIMESTAMPTZ
)
```

### Usage & Analytics
```sql
usage (
    id UUID PRIMARY KEY,
    organization_id UUID REFERENCES organizations,
    bot_id UUID REFERENCES bots,
    month DATE,
    message_count INTEGER,
    token_count INTEGER,
    created_at TIMESTAMPTZ
)
```

## API Endpoints

### Auth (via Supabase)
- `POST /auth/signup` - Register
- `POST /auth/login` - Login
- `POST /auth/logout` - Logout

### Bots
- `GET /api/bots` - List user's bots
- `POST /api/bots` - Create bot
- `GET /api/bots/:id` - Get bot
- `PATCH /api/bots/:id` - Update bot
- `DELETE /api/bots/:id` - Delete bot

### Documents
- `GET /api/bots/:id/documents` - List documents
- `POST /api/bots/:id/documents` - Upload document
- `DELETE /api/bots/:id/documents/:docId` - Delete document
- `POST /api/bots/:id/documents/:docId/process` - Process document (create embeddings)

### Channels
- `GET /api/bots/:id/channels` - List channels
- `POST /api/bots/:id/channels` - Add channel
- `PATCH /api/bots/:id/channels/:channelId` - Update channel
- `DELETE /api/bots/:id/channels/:channelId` - Remove channel

### Chat (webhook endpoints)
- `POST /webhook/:botId/whatsapp` - WhatsApp webhook
- `POST /webhook/:botId/telegram` - Telegram webhook
- `POST /api/bots/:id/chat` - Web chat API

### Analytics
- `GET /api/bots/:id/analytics` - Bot analytics
- `GET /api/organizations/:id/usage` - Organization usage

## Frontend Pages

```
/                       → Landing page
/login                  → Login
/signup                 → Register
/dashboard              → Bots list
/bots/new               → Create bot wizard
/bots/:id               → Bot overview
/bots/:id/builder       → Visual agent builder
/bots/:id/documents     → Document management
/bots/:id/channels      → Channel connections
/bots/:id/analytics     → Bot analytics
/bots/:id/settings      → Bot settings
/bots/:id/test          → Test chat
/settings               → User/org settings
```

## User Flow

1. **Signup/Login** → Supabase Auth
2. **Create Bot** → Name, description, personality
3. **Upload Documents** → PDF, DOCX, TXT for RAG
4. **Configure Agents** → Enable/disable intents, customize responses
5. **Connect Channel** → WhatsApp, Telegram, or Web widget
6. **Test** → Built-in chat for testing
7. **Deploy** → Activate bot
8. **Monitor** → Analytics dashboard

## Multi-tenancy

- Each user belongs to an organization
- Bots are scoped to organizations
- MongoDB collections prefixed with org ID: `org_{id}_documents`
- Row Level Security (RLS) in Supabase for data isolation

## MVP Features

### Phase 1 (MVP)
- [ ] User auth (login/register)
- [ ] Create/edit/delete bots
- [ ] Upload documents for RAG
- [ ] Basic bot configuration (name, personality, welcome message)
- [ ] Web chat widget for testing
- [ ] Simple analytics (message count)

### Phase 2
- [ ] WhatsApp integration
- [ ] Visual agent builder (drag & drop)
- [ ] Advanced analytics
- [ ] Team members

### Phase 3
- [ ] Telegram integration
- [ ] Custom intents
- [ ] Billing/plans
- [ ] API access for developers
