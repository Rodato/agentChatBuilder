/**
 * Bot map API client — top-level topology of agents + workflows.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type EdgeKind =
  | "entry"
  | "intent_route"
  | "intent"
  | "manual_trigger"
  | "handoff"
  | "handoff_agentic";

export interface MapAgent {
  id: string;
  name: string;
  enabled: boolean;
  is_custom: boolean;
  intent: string | null;
  tools: Record<string, boolean>;
  trigger_flows: string[];
}

export interface MapWorkflow {
  id: string;
  name: string;
  trigger_type: "on_start" | "on_intent" | "manual";
  trigger_value: string | null;
  enabled: boolean;
  version: number;
  handoffs: Array<{
    target: "agentic" | "workflow";
    target_workflow_id?: string | null;
    label?: string | null;
  }>;
}

export interface MapEdge {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
  label?: string;
}

export interface BotMap {
  bot_id: string;
  bot_name: string | null;
  agents: MapAgent[];
  workflows: MapWorkflow[];
  edges: MapEdge[];
  entry: { kind: "on_start" | "agentic"; workflow_id?: string };
}

export interface MapEdgeUpdate {
  source: string;
  target: string;
  kind: "entry" | "intent_route" | "intent" | "manual_trigger";
  label?: string | null;
}

export const botMapApi = {
  get: async (botId: string): Promise<BotMap> => {
    const res = await fetch(`${BASE_URL}/api/bots/${botId}/map`);
    if (!res.ok) {
      const error = await res.text();
      throw new Error(error || `HTTP ${res.status}`);
    }
    return res.json();
  },
  update: async (botId: string, edges: MapEdgeUpdate[]): Promise<BotMap> => {
    const res = await fetch(`${BASE_URL}/api/bots/${botId}/map`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ edges }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      const message = body?.detail?.message ?? body?.detail ?? `HTTP ${res.status}`;
      throw new Error(typeof message === "string" ? message : JSON.stringify(message));
    }
    return res.json();
  },
};
