"use client";

import { memo } from "react";
import { Handle, Position, NodeProps } from "@xyflow/react";
import type { WorkflowNodeData } from "@/lib/workflowApi";

function MessageNodeImpl({ data, selected }: NodeProps) {
  const d = (data || {}) as WorkflowNodeData;
  const preview = (d.text || "").slice(0, 80);
  return (
    <div
      className={`min-w-[220px] rounded-lg border bg-white shadow-sm ${
        selected ? "border-yellow-500 ring-2 ring-yellow-300" : "border-yellow-300"
      }`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-yellow-500 !w-4 !h-4 !border-2 !border-white"
      />
      <div className="px-3 py-2 border-b bg-yellow-50 text-yellow-900 text-xs font-semibold uppercase tracking-wide">
        💬 Mensaje
      </div>
      <div className="p-3 space-y-1">
        <div className="text-sm text-gray-700 line-clamp-3 italic">
          {preview ? `"${preview}${(d.text || "").length > 80 ? "…" : ""}"` : "(sin texto)"}
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-yellow-500 !w-4 !h-4 !border-2 !border-white"
      />
    </div>
  );
}

export const MessageNode = memo(MessageNodeImpl);
