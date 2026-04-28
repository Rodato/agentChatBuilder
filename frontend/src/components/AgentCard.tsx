"use client";

import { memo } from "react";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Pencil, Trash2 } from "lucide-react";
import { IntentKey } from "@/lib/api";

export interface Agent {
  id: string;
  name: string;
  objective: string;
  system_prompt: string;
  model: string;
  temperature: number;
  tools: {
    rag_search: boolean;
    user_memory: boolean;
    trigger_flow: boolean;
    human_handoff: boolean;
    external_api: boolean;
  };
  enabled: boolean;
  is_custom: boolean;
  trigger_flows?: string[]; // workflow ids seleccionados (si vacío = todos los manuales)
  intents?: IntentKey[]; // intents que maneja un custom (vacío = solo via Workflow)
}

const TOOL_LABELS: Record<string, string> = {
  rag_search: "RAG",
  user_memory: "Memory",
  trigger_flow: "Flow",
  human_handoff: "Handoff",
  external_api: "API",
};

const INTENT_SHORT_LABELS: Record<IntentKey, string> = {
  GREETING: "Saludo",
  FACTUAL: "RAG",
  PLAN: "Plan",
  IDEATE: "Ideas",
  SENSITIVE: "Sensible",
  AMBIGUOUS: "Fallback",
};

interface AgentCardProps {
  agent: Agent;
  onToggle: (id: string) => void;
  onEdit: (agent: Agent) => void;
  onDelete?: (agent: Agent) => void;
}

function AgentCardImpl({ agent, onToggle, onEdit, onDelete }: AgentCardProps) {
  const activeTools = Object.entries(agent.tools)
    .filter(([, active]) => active)
    .map(([key]) => key);

  const intents = agent.intents ?? [];

  return (
    <div className="flex items-center justify-between p-4 border rounded-lg bg-white">
      <div className="flex items-center gap-4 flex-1 min-w-0">
        <Switch
          checked={agent.enabled}
          onCheckedChange={() => onToggle(agent.id)}
        />
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="font-medium">{agent.name}</h4>
            {agent.is_custom && (
              <Badge variant="secondary" className="text-xs">Personalizado</Badge>
            )}
            {agent.is_custom && intents.length > 0 && (
              <span className="text-xs text-purple-700">
                Intents: {intents.map((i) => INTENT_SHORT_LABELS[i] ?? i).join(" · ")}
              </span>
            )}
            {agent.is_custom && intents.length === 0 && (
              <span className="text-xs text-gray-400 italic">solo vía Workflow</span>
            )}
            {activeTools.map((tool) => (
              <Badge key={tool} variant="outline" className="text-xs">
                {TOOL_LABELS[tool] ?? tool}
              </Badge>
            ))}
          </div>
          <p className="text-sm text-gray-500 truncate">{agent.objective}</p>
        </div>
      </div>
      <div className="flex items-center gap-1 ml-2 shrink-0">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onEdit(agent)}
        >
          <Pencil className="w-4 h-4" />
        </Button>
        {agent.is_custom && onDelete && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onDelete(agent)}
            className="text-gray-400 hover:text-red-600"
            aria-label={`Eliminar ${agent.name}`}
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        )}
      </div>
    </div>
  );
}

export const AgentCard = memo(AgentCardImpl);
