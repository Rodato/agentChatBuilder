"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  MarkerType,
  Edge,
  Node,
  NodeProps,
  NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { RefreshCw } from "lucide-react";
import { botMapApi, BotMap, EdgeKind } from "@/lib/botMapApi";

// ── Custom nodes ────────────────────────────────────────────────────────────

type NodeData = {
  label: string;
  sublabel?: string;
  badge?: string;
  enabled?: boolean;
  variant?: "start" | "agentic" | "agent" | "workflow_onstart" | "workflow_intent" | "workflow_manual";
};

function StartNodeImpl({ data }: NodeProps) {
  const d = (data || {}) as NodeData;
  return (
    <div className="rounded-full border-2 border-emerald-500 bg-emerald-50 px-4 py-2 text-emerald-900 shadow-sm">
      <Handle type="source" position={Position.Right} className="!bg-emerald-500 !w-3 !h-3" />
      <span className="text-sm font-semibold">{d.label}</span>
    </div>
  );
}

function AgenticHubNodeImpl({ data }: NodeProps) {
  const d = (data || {}) as NodeData;
  return (
    <div className="min-w-[180px] rounded-xl border-2 border-purple-500 bg-purple-50 shadow-md">
      <Handle type="target" position={Position.Left} className="!bg-purple-500 !w-3 !h-3" />
      <div className="px-3 py-2 border-b border-purple-300 bg-purple-100 text-purple-900 text-xs font-semibold uppercase tracking-wide">
        Sistema Agéntico
      </div>
      <div className="p-3 text-center text-sm text-purple-900">
        {d.label}
        <div className="text-xs text-purple-700 mt-1">Router por intención</div>
      </div>
      <Handle type="source" position={Position.Right} className="!bg-purple-500 !w-3 !h-3" />
    </div>
  );
}

function AgentNodeImpl({ data }: NodeProps) {
  const d = (data || {}) as NodeData;
  const muted = d.enabled === false;
  return (
    <div
      className={`min-w-[180px] rounded-lg border bg-white shadow-sm ${
        muted ? "opacity-50 border-gray-300" : "border-blue-400"
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-blue-500 !w-3 !h-3" />
      <div className="px-3 py-2 border-b bg-blue-50 text-blue-900 text-xs font-semibold uppercase tracking-wide flex items-center justify-between">
        <span>Especialista</span>
        {d.badge && <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-200">{d.badge}</span>}
      </div>
      <div className="p-3">
        <div className="text-sm font-medium">{d.label}</div>
        {d.sublabel && <div className="text-xs text-gray-500 mt-0.5">{d.sublabel}</div>}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-blue-500 !w-3 !h-3" />
    </div>
  );
}

function WorkflowNodeImpl({ data }: NodeProps) {
  const d = (data || {}) as NodeData;
  const muted = d.enabled === false;
  const palette =
    d.variant === "workflow_onstart"
      ? { border: "border-emerald-400", bg: "bg-emerald-50", text: "text-emerald-900", chip: "bg-emerald-200" }
      : d.variant === "workflow_intent"
      ? { border: "border-amber-400", bg: "bg-amber-50", text: "text-amber-900", chip: "bg-amber-200" }
      : { border: "border-indigo-400", bg: "bg-indigo-50", text: "text-indigo-900", chip: "bg-indigo-200" };
  return (
    <div
      className={`min-w-[200px] rounded-lg border-2 bg-white shadow-sm ${palette.border} ${
        muted ? "opacity-50" : ""
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-gray-500 !w-3 !h-3" />
      <div
        className={`px-3 py-2 border-b ${palette.bg} ${palette.text} text-xs font-semibold uppercase tracking-wide flex items-center justify-between`}
      >
        <span>Workflow</span>
        {d.badge && <span className={`text-[10px] px-1.5 py-0.5 rounded ${palette.chip}`}>{d.badge}</span>}
      </div>
      <div className="p-3">
        <div className="text-sm font-medium">{d.label}</div>
        {d.sublabel && <div className="text-xs text-gray-500 mt-0.5">{d.sublabel}</div>}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-gray-500 !w-3 !h-3" />
    </div>
  );
}

const NODE_TYPES: NodeTypes = {
  start: StartNodeImpl,
  agenticHub: AgenticHubNodeImpl,
  agent: AgentNodeImpl,
  workflow: WorkflowNodeImpl,
};

// ── Edge styling ────────────────────────────────────────────────────────────

const EDGE_STYLE: Record<EdgeKind, { stroke: string; dash?: string; label?: string }> = {
  entry:            { stroke: "#10b981" },
  intent_route:     { stroke: "#a855f7" },
  intent:           { stroke: "#f59e0b" },
  manual_trigger:   { stroke: "#6366f1", dash: "6 4" },
  handoff:          { stroke: "#4b5563" },
  handoff_agentic:  { stroke: "#9333ea", dash: "6 4" },
};

// ── Layout ──────────────────────────────────────────────────────────────────

const COL_X = {
  start: 40,
  hub: 280,
  agent: 600,
  workflow: 940,
};

interface Props {
  botId: string;
}

interface InnerProps {
  botId: string;
}

function BotMapInner({ botId }: InnerProps) {
  const [data, setData] = useState<BotMap | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await botMapApi.get(botId);
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar el mapa.");
    } finally {
      setLoading(false);
    }
  }, [botId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const { nodes, edges } = useMemo(() => buildGraph(data), [data]);

  return (
    <Card>
      <CardHeader>
        <div className="flex justify-between items-start">
          <div>
            <CardTitle>Mapa del Agente</CardTitle>
            <CardDescription>
              Vista global: punto de inicio, sistema agéntico, especialistas y workflows con sus conexiones.
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} />
            Actualizar
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {error && (
          <div className="mb-4 p-3 rounded-md bg-red-50 text-sm text-red-700 border border-red-200">
            {error}
          </div>
        )}

        <Legend />

        <div className="h-[600px] mt-4 border rounded-lg bg-gray-50">
          {loading && !data ? (
            <div className="h-full flex items-center justify-center text-gray-500 text-sm">
              Cargando mapa…
            </div>
          ) : (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={NODE_TYPES}
              fitView
              proOptions={{ hideAttribution: true }}
              nodesDraggable
              nodesConnectable={false}
              edgesFocusable={false}
              defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed } }}
            >
              <Background gap={20} />
              <Controls showInteractive={false} />
              <MiniMap pannable zoomable />
            </ReactFlow>
          )}
        </div>

        {data && (
          <div className="mt-4 text-xs text-gray-500 flex flex-wrap gap-4">
            <span>{data.agents.filter((a) => a.enabled).length} especialistas habilitados</span>
            <span>·</span>
            <span>{data.workflows.filter((w) => w.enabled).length} workflows activos</span>
            <span>·</span>
            <span>Entrada: {data.entry.kind === "on_start" ? "Workflow on_start" : "Agentic"}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-2 text-xs">
      <Badge variant="outline" className="border-emerald-400 text-emerald-800">Inicio</Badge>
      <Badge variant="outline" className="border-purple-400 text-purple-800">Sistema agéntico</Badge>
      <Badge variant="outline" className="border-blue-400 text-blue-800">Especialista</Badge>
      <Badge variant="outline" className="border-emerald-400 text-emerald-900">Workflow on_start</Badge>
      <Badge variant="outline" className="border-amber-400 text-amber-900">Workflow on_intent</Badge>
      <Badge variant="outline" className="border-indigo-400 text-indigo-900">Workflow manual</Badge>
    </div>
  );
}

// ── Graph builder ───────────────────────────────────────────────────────────

function buildGraph(data: BotMap | null): { nodes: Node[]; edges: Edge[] } {
  if (!data) return { nodes: [], edges: [] };

  const nodes: Node[] = [];
  const edges: Edge[] = [];

  // Start node
  nodes.push({
    id: "start",
    type: "start",
    position: { x: COL_X.start, y: 280 },
    data: { label: "Inicio del chat" } satisfies NodeData,
    draggable: false,
  });

  // Agentic hub
  nodes.push({
    id: "agentic",
    type: "agenticHub",
    position: { x: COL_X.hub, y: 240 },
    data: { label: "Agentic Router" } satisfies NodeData,
  });

  // Agents column
  const enabledAgents = data.agents.filter((a) => a.enabled);
  const agentSpacing = 110;
  enabledAgents.forEach((agent, i) => {
    nodes.push({
      id: `agent:${agent.id}`,
      type: "agent",
      position: { x: COL_X.agent, y: i * agentSpacing },
      data: {
        label: agent.name,
        sublabel: agent.tools?.rag_search ? "RAG · " + (agent.intent || "") : agent.intent || "",
        badge: agent.is_custom ? "custom" : agent.intent || undefined,
      } satisfies NodeData,
    });
  });
  // Disabled agents (rendered muted, below the enabled ones)
  data.agents.filter((a) => !a.enabled).forEach((agent, i) => {
    nodes.push({
      id: `agent:${agent.id}`,
      type: "agent",
      position: { x: COL_X.agent, y: enabledAgents.length * agentSpacing + i * agentSpacing },
      data: {
        label: agent.name,
        sublabel: "deshabilitado",
        badge: agent.intent || undefined,
        enabled: false,
      } satisfies NodeData,
    });
  });

  // Workflows column
  const wfSpacing = 130;
  data.workflows.forEach((wf, i) => {
    const variant =
      wf.trigger_type === "on_start"
        ? "workflow_onstart"
        : wf.trigger_type === "on_intent"
        ? "workflow_intent"
        : "workflow_manual";
    const triggerLabel =
      wf.trigger_type === "on_start"
        ? "on_start"
        : wf.trigger_type === "on_intent"
        ? `intent: ${wf.trigger_value || "?"}`
        : "manual";
    nodes.push({
      id: `workflow:${wf.id}`,
      type: "workflow",
      position: { x: COL_X.workflow, y: i * wfSpacing },
      data: {
        label: wf.name,
        sublabel: `v${wf.version}`,
        badge: triggerLabel,
        enabled: wf.enabled,
        variant,
      } satisfies NodeData,
    });
  });

  // Edges from API
  data.edges.forEach((e) => {
    const style = EDGE_STYLE[e.kind];
    edges.push({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.label,
      animated: e.kind === "entry" || e.kind === "manual_trigger",
      style: {
        stroke: style.stroke,
        strokeWidth: 1.5,
        strokeDasharray: style.dash,
      },
      labelStyle: { fontSize: 10, fill: style.stroke, fontWeight: 600 },
      labelBgStyle: { fill: "#fff", opacity: 0.9 },
      markerEnd: { type: MarkerType.ArrowClosed, color: style.stroke },
    });
  });

  return { nodes, edges };
}

export function BotMapView({ botId }: Props) {
  return (
    <ReactFlowProvider>
      <BotMapInner botId={botId} />
    </ReactFlowProvider>
  );
}
