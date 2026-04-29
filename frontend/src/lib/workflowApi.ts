/**
 * Workflow editor API client (CRUD plural).
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

export type TriggerType = "on_start" | "on_intent" | "manual";
export type IntentKey = "GREETING" | "FACTUAL" | "PLAN" | "IDEATE" | "SENSITIVE" | "AMBIGUOUS";

export const INTENT_LABELS: Record<IntentKey, string> = {
  GREETING: "Saludo",
  FACTUAL: "Informativo (RAG)",
  PLAN: "Planificación",
  IDEATE: "Lluvia de ideas",
  SENSITIVE: "Sensible",
  AMBIGUOUS: "Ambiguo / Fallback",
};

export interface WorkflowNodeData {
  label?: string;
  // capture
  var_name?: string;
  prompt?: string;
  skip_if_present?: boolean;
  // agent
  agent_id?: string;
  system_prompt_override?: string;
  // handoff
  target?: "agentic" | "workflow";
  target_workflow_id?: string;
  farewell?: string;
  // message (texto fijo del bot, sin esperar input)
  text?: string;
}

export interface WorkflowNode {
  id: string;
  type: "agent" | "capture" | "handoff" | "message";
  position: { x: number; y: number };
  data: WorkflowNodeData;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
}

export interface WorkflowDefinition {
  version: number;
  entry_node_id: string | null;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

export interface WorkflowRow {
  id: string;
  bot_id: string;
  name: string;
  trigger_type: TriggerType;
  trigger_value: string | null;
  enabled: boolean;
  version: number;
  definition: WorkflowDefinition;
  entry_node_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowSummary {
  id: string;
  name: string;
  trigger_type: TriggerType;
  trigger_value: string | null;
  enabled: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface WorkflowCreatePayload {
  name: string;
  trigger_type: TriggerType;
  trigger_value?: string | null;
  enabled?: boolean;
  definition?: WorkflowDefinition;
}

export interface WorkflowUpdatePayload {
  name?: string;
  trigger_type?: TriggerType;
  trigger_value?: string | null;
  enabled?: boolean;
  definition?: WorkflowDefinition;
}

export const workflowApi = {
  list: (botId: string) => request<WorkflowSummary[]>(`/api/bots/${botId}/workflows`),
  create: (botId: string, payload: WorkflowCreatePayload) =>
    request<WorkflowRow>(`/api/bots/${botId}/workflows`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  get: (botId: string, workflowId: string) =>
    request<WorkflowRow>(`/api/bots/${botId}/workflows/${workflowId}`),
  update: (botId: string, workflowId: string, payload: WorkflowUpdatePayload) =>
    request<WorkflowRow>(`/api/bots/${botId}/workflows/${workflowId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  delete: (botId: string, workflowId: string) =>
    request<void>(`/api/bots/${botId}/workflows/${workflowId}`, { method: "DELETE" }),
  toggle: (botId: string, workflowId: string, enabled: boolean) =>
    request<{ status: string; enabled: boolean }>(
      `/api/bots/${botId}/workflows/${workflowId}/toggle`,
      { method: "POST", body: JSON.stringify({ enabled }) }
    ),
};
