"use client";

import { memo } from "react";
import { Handle, Position, NodeProps } from "@xyflow/react";
import type { WorkflowNodeData } from "@/lib/workflowApi";

type AgentNodeData = Pick<WorkflowNodeData, "agent_id" | "system_prompt_override" | "label">;

const AGENT_LABELS: Record<string, string> = {
  greeting: "Saludo",
  factual: "Informativo (RAG)",
  plan: "Planificación",
  ideate: "Lluvia de ideas",
  sensitive: "Sensible",
  fallback: "Fallback",
};

function AgentNodeImpl({ data, selected }: NodeProps) {
  const d = (data || {}) as AgentNodeData;
  const agentLabel = d.agent_id ? AGENT_LABELS[d.agent_id] ?? d.agent_id : "(sin agente)";
  return (
    <div
      className={`min-w-[240px] rounded-lg border bg-white shadow-sm ${selected ? "border-blue-500 ring-2 ring-blue-200" : "border-gray-200"}`}
    >
      <Handle type="target" position={Position.Top} className="!bg-blue-500 !w-4 !h-4 !border-2 !border-white hover:!bg-blue-600" />
      <div className="px-3 py-2 border-b bg-blue-50 text-blue-900 text-xs font-semibold uppercase tracking-wide">
        Agente
      </div>
      <div className="p-3 space-y-1">
        <div className="text-sm font-medium text-blue-700">{agentLabel}</div>
        <div className="text-xs text-gray-600 line-clamp-3">
          {d.system_prompt_override || <span className="italic text-gray-400">(usa prompt por defecto del agente)</span>}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-blue-500 !w-4 !h-4 !border-2 !border-white hover:!bg-blue-600" />
    </div>
  );
}

export const AgentNode = memo(AgentNodeImpl);
