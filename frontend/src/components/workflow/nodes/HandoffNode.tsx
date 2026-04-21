"use client";

import { memo } from "react";
import { Handle, Position, NodeProps } from "@xyflow/react";
import type { WorkflowNodeData } from "@/lib/workflowApi";

type HandoffNodeData = Pick<WorkflowNodeData, "target" | "target_workflow_id" | "farewell" | "label">;

function HandoffNodeImpl({ data, selected }: NodeProps) {
  const d = (data || {}) as HandoffNodeData;
  const target = d.target || "agentic";
  return (
    <div
      className={`min-w-[240px] rounded-lg border bg-white shadow-sm ${selected ? "border-gray-500 ring-2 ring-gray-300" : "border-gray-300"}`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-gray-500 !w-4 !h-4 !border-2 !border-white"
      />
      <div className="px-3 py-2 border-b bg-gray-100 text-gray-800 text-xs font-semibold uppercase tracking-wide">
        Handoff
      </div>
      <div className="p-3 space-y-1">
        <div className="text-sm font-medium">
          {target === "agentic" ? (
            <span className="text-purple-700">→ Sistema agéntico</span>
          ) : (
            <span className="text-indigo-700">→ Otro workflow</span>
          )}
        </div>
        {d.farewell && (
          <div className="text-xs text-gray-600 line-clamp-3 italic">&ldquo;{d.farewell}&rdquo;</div>
        )}
      </div>
      {/* Nodo terminal: sin handle source */}
    </div>
  );
}

export const HandoffNode = memo(HandoffNodeImpl);
