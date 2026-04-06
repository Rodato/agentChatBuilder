"use client";

import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Pencil } from "lucide-react";

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
}

const TOOL_LABELS: Record<string, string> = {
  rag_search: "RAG",
  user_memory: "Memory",
  trigger_flow: "Flow",
  human_handoff: "Handoff",
  external_api: "API",
};

interface AgentCardProps {
  agent: Agent;
  onToggle: (id: string) => void;
  onEdit: (agent: Agent) => void;
}

export function AgentCard({ agent, onToggle, onEdit }: AgentCardProps) {
  const activeTools = Object.entries(agent.tools)
    .filter(([, active]) => active)
    .map(([key]) => key);

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
            {activeTools.map((tool) => (
              <Badge key={tool} variant="outline" className="text-xs">
                {TOOL_LABELS[tool] ?? tool}
              </Badge>
            ))}
          </div>
          <p className="text-sm text-gray-500 truncate">{agent.objective}</p>
        </div>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onEdit(agent)}
        className="ml-2 shrink-0"
      >
        <Pencil className="w-4 h-4" />
      </Button>
    </div>
  );
}
