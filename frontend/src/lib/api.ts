/**
 * API client for the Agent Chat Builder backend.
 * Base URL is configurable via NEXT_PUBLIC_API_URL env var.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(error || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Bot {
  id: string;
  name: string;
  description: string | null;
  personality: string | null;
  welcome_message: string;
  is_active: boolean;
  message_count: number;
  workflow_mode?: "free" | "workflow";
  created_at: string;
  updated_at: string;
}

export interface BotCreate {
  name: string;
  description?: string;
  personality?: string;
  welcome_message?: string;
}

export interface BotUpdate {
  name?: string;
  description?: string;
  personality?: string;
  welcome_message?: string;
  is_active?: boolean;
}

export interface Document {
  id: string;
  bot_id: string;
  name: string;
  status: string;
  file_size: number;
  summary?: string | null;
  keywords?: string[];
  created_at: string;
}

export interface DocumentMetadataPatch {
  summary?: string | null;
  keywords?: string[];
}

export interface AgentTools {
  rag_search: boolean;
  user_memory: boolean;
  trigger_flow: boolean;
  human_handoff: boolean;
  external_api: boolean;
}

export interface AgentMetadata {
  trigger_flows?: string[];
}

export interface AgentRow {
  bot_id: string;
  agent_id: string;
  name: string;
  objective: string;
  system_prompt: string;
  model: string;
  temperature: number;
  tools: Partial<AgentTools>;
  enabled: boolean;
  is_custom: boolean;
  position: number;
  metadata?: AgentMetadata;
}

export interface AgentPatch {
  name?: string;
  objective?: string;
  system_prompt?: string;
  model?: string;
  temperature?: number;
  tools?: Partial<AgentTools>;
  enabled?: boolean;
  position?: number;
  metadata?: AgentMetadata;
}

export interface ChatSource {
  content: string;
  score: number;
  doc_id?: string;
  doc_name?: string;
  page?: number;
}

export interface ChatResponse {
  response: string;
  agent_used: string;
  intent: string | null;
  language: string;
  sources: ChatSource[];
  processing_time_ms: number;
  conversation_id: string;
  mode?: "workflow" | "agentic";
  status?: string;
}

// ── Bots ──────────────────────────────────────────────────────────────────────

export const botsApi = {
  list: () => request<Bot[]>("/api/bots"),
  get: (id: string) => request<Bot>(`/api/bots/${id}`),
  create: (data: BotCreate) =>
    request<Bot>("/api/bots", { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: BotUpdate) =>
    request<Bot>(`/api/bots/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: string) =>
    request<void>(`/api/bots/${id}`, { method: "DELETE" }),
};

// ── Agents ────────────────────────────────────────────────────────────────────

export const agentsApi = {
  list: (botId: string) => request<AgentRow[]>(`/api/bots/${botId}/agents`),
  update: (botId: string, agentId: string, patch: AgentPatch) =>
    request<AgentRow>(`/api/bots/${botId}/agents/${agentId}`, {
      method: "PUT",
      body: JSON.stringify(patch),
    }),
  delete: (botId: string, agentId: string) =>
    request<void>(`/api/bots/${botId}/agents/${agentId}`, { method: "DELETE" }),
};

// ── Documents ────────────────────────────────────────────────────────────────

export const documentsApi = {
  list: (botId: string) => request<Document[]>(`/api/bots/${botId}/documents`),
  upload: (botId: string, file: File): Promise<Document> => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE_URL}/api/bots/${botId}/documents`, {
      method: "POST",
      body: form,
    }).then(async (res) => {
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    });
  },
  delete: (botId: string, docId: string) =>
    request<void>(`/api/bots/${botId}/documents/${docId}`, { method: "DELETE" }),
  updateMetadata: (botId: string, docId: string, patch: DocumentMetadataPatch) =>
    request<Document>(`/api/bots/${botId}/documents/${docId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
};

// ── Chat ──────────────────────────────────────────────────────────────────────

export const chatApi = {
  start: (botId: string, conversationId?: string, userId?: string) =>
    request<ChatResponse>("/chat/start", {
      method: "POST",
      body: JSON.stringify({ bot_id: botId, conversation_id: conversationId, user_id: userId }),
    }),
  send: (botId: string, message: string, conversationId?: string, userId?: string) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({
        bot_id: botId,
        message,
        conversation_id: conversationId,
        user_id: userId,
      }),
    }),
};
