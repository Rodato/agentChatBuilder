"use client";

import { memo } from "react";
import { Handle, Position, NodeProps } from "@xyflow/react";
import type { WorkflowNodeData } from "@/lib/workflowApi";

type CaptureNodeData = Pick<WorkflowNodeData, "var_name" | "prompt" | "skip_if_present" | "label">;

function CaptureNodeImpl({ data, selected }: NodeProps) {
  const d = (data || {}) as CaptureNodeData;
  return (
    <div
      className={`min-w-[240px] rounded-lg border bg-white shadow-sm ${selected ? "border-amber-500 ring-2 ring-amber-200" : "border-gray-200"}`}
    >
      <Handle type="target" position={Position.Top} className="!bg-amber-500 !w-4 !h-4 !border-2 !border-white hover:!bg-amber-600" />
      <div className="px-3 py-2 border-b bg-amber-50 text-amber-900 text-xs font-semibold uppercase tracking-wide">
        Captura {d.skip_if_present && <span className="ml-1 normal-case font-normal text-amber-700">· skip si existe</span>}
      </div>
      <div className="p-3 space-y-1">
        <div className="text-sm font-medium">
          {d.var_name ? (
            <span className="text-amber-700">{`{{${d.var_name}}}`}</span>
          ) : (
            <span className="text-gray-400 italic">sin variable</span>
          )}
        </div>
        <div className="text-xs text-gray-600 line-clamp-3">
          {d.prompt || <span className="italic text-gray-400">(sin prompt)</span>}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-amber-500 !w-4 !h-4 !border-2 !border-white hover:!bg-amber-600" />
    </div>
  );
}

export const CaptureNode = memo(CaptureNodeImpl);
