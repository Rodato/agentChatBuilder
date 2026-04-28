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
  Connection,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { RefreshCw, Save, Undo2 } from "lucide-react";
import { botMapApi, BotMap, EdgeKind, MapAgent, MapWorkflow, MapEdgeUpdate } from "@/lib/botMapApi";

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
        Hub Agéntico
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
        <span>Worker</span>
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

const EDGE_STYLE: Record<EdgeKind, { stroke: string; dash?: string }> = {
  entry:            { stroke: "#10b981" },
  intent_route:     { stroke: "#a855f7" },
  intent:           { stroke: "#f59e0b" },
  manual_trigger:   { stroke: "#6366f1", dash: "6 4" },
  handoff:          { stroke: "#4b5563" },
  handoff_agentic:  { stroke: "#9333ea", dash: "6 4" },
};

// Edges of these kinds are managed via the Workflow editor, not the map. The
// map renders them visually but they cannot be created or deleted from here.
const READONLY_KINDS: EdgeKind[] = ["handoff", "handoff_agentic"];

const INTENT_OPTIONS = [
  { value: "GREETING", label: "Saludo" },
  { value: "FACTUAL", label: "Informativo (RAG)" },
  { value: "PLAN", label: "Planificación" },
  { value: "IDEATE", label: "Lluvia de ideas" },
  { value: "SENSITIVE", label: "Sensible" },
  { value: "AMBIGUOUS", label: "Ambiguo / Fallback" },
];

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

function BotMapInner({ botId }: Props) {
  const [data, setData] = useState<BotMap | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [pendingConnection, setPendingConnection] = useState<Connection | null>(null);
  const [intentForConnection, setIntentForConnection] = useState<string>("FACTUAL");

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { screenToFlowPosition } = useReactFlow();

  // Items dropped on canvas that aren't in `data` yet (visible only locally
  // until the user connects them; nodes without edges aren't persisted).
  const [extraNodeIds, setExtraNodeIds] = useState<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await botMapApi.get(botId);
      setData(res);
      setExtraNodeIds(new Set());
      setDirty(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar el mapa.");
    } finally {
      setLoading(false);
    }
  }, [botId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Build canvas from server data + extra nodes the user dropped this session.
  useEffect(() => {
    if (!data) return;
    const { nodes: builtNodes, edges: builtEdges } = buildGraph(data, extraNodeIds);
    setNodes(builtNodes);
    setEdges(builtEdges);
  }, [data, extraNodeIds, setNodes, setEdges]);

  const handleDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const ref = event.dataTransfer.getData("application/bot-map-node");
      if (!ref) return;
      // Track the dropped node so it stays visible until the user wires it.
      setExtraNodeIds((prev) => new Set(prev).add(ref));
      // Snap position close to the drop coordinate so the user sees the node.
      const pos = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      setNodes((prev) => {
        if (prev.some((n) => n.id === ref)) {
          return prev.map((n) => (n.id === ref ? { ...n, position: pos } : n));
        }
        return prev;
      });
    },
    [screenToFlowPosition, setNodes]
  );

  const classifyConnection = useCallback(
    (conn: Connection): EdgeKind | null => {
      const src = conn.source ?? "";
      const tgt = conn.target ?? "";
      if (src === "start" && tgt.startsWith("workflow:")) return "entry";
      if (src === "agentic" && tgt.startsWith("agent:")) return "intent_route";
      if (src === "agentic" && tgt.startsWith("workflow:")) return "intent";
      if (src.startsWith("agent:") && tgt.startsWith("workflow:")) return "manual_trigger";
      return null;
    },
    []
  );

  const onConnect = useCallback(
    (conn: Connection) => {
      const kind = classifyConnection(conn);
      if (!kind) {
        setError("Esa conexión no es válida. Revisa los tipos de nodo permitidos.");
        return;
      }
      if (kind === "intent_route" || kind === "intent") {
        setPendingConnection(conn);
        return;
      }
      // Direct add (entry, manual_trigger).
      addEditableEdge(conn, kind, null);
    },
    [classifyConnection]
  );

  const addEditableEdge = useCallback(
    (conn: Connection, kind: EdgeKind, intent: string | null) => {
      const id = `edge-${kind}-${conn.source}-${conn.target}-${intent ?? ""}`.replace(/[^\w-]/g, "_");
      const style = EDGE_STYLE[kind];
      setEdges((prev) =>
        addEdge(
          {
            ...conn,
            id,
            label: intent || labelForKind(kind),
            data: { kind, intent } as Record<string, unknown>,
            animated: kind === "manual_trigger" || kind === "entry",
            style: { stroke: style.stroke, strokeWidth: 1.5, strokeDasharray: style.dash },
            labelStyle: { fontSize: 10, fill: style.stroke, fontWeight: 600 },
            labelBgStyle: { fill: "#fff", opacity: 0.9 },
            markerEnd: { type: MarkerType.ArrowClosed, color: style.stroke },
          },
          prev
        )
      );
      setDirty(true);
    },
    [setEdges]
  );

  const onEdgesDelete = useCallback(
    (deleted: Edge[]) => {
      const blocked = deleted.find((e) => {
        const k = (e.data as { kind?: EdgeKind } | undefined)?.kind;
        return k && READONLY_KINDS.includes(k);
      });
      if (blocked) {
        setError("Las aristas de handoff se editan dentro del Workflow correspondiente, no aquí.");
        // Restore the edge by reloading. Simpler than computing the inverse.
        refresh();
        return;
      }
      setDirty(true);
    },
    [refresh]
  );

  const handleConfirmIntent = () => {
    if (!pendingConnection) return;
    const kind = classifyConnection(pendingConnection);
    if (kind) addEditableEdge(pendingConnection, kind, intentForConnection);
    setPendingConnection(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      // Translate canvas edges back to API format. Keep only editable kinds.
      const payload: MapEdgeUpdate[] = [];
      for (const e of edges) {
        const meta = e.data as { kind?: EdgeKind; intent?: string | null } | undefined;
        const kind = meta?.kind;
        if (!kind || READONLY_KINDS.includes(kind)) continue;
        payload.push({
          source: e.source,
          target: e.target,
          kind: kind as MapEdgeUpdate["kind"],
          label: meta?.intent ?? null,
        });
      }
      const updated = await botMapApi.update(botId, payload);
      setData(updated);
      setExtraNodeIds(new Set());
      setDirty(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar el mapa.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex justify-between items-start">
          <div>
            <CardTitle>Mapa del Agente</CardTitle>
            <CardDescription>
              Ensambla tu Agente. Arrastra Workers y Workflows desde la paleta y conéctalos al Hub
              Agéntico, al Inicio o entre sí. Las conexiones definen el comportamiento del bot.
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={refresh} disabled={loading || saving}>
              <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} />
              Recargar
            </Button>
            <Button variant="outline" size="sm" onClick={refresh} disabled={!dirty || saving}>
              <Undo2 className="w-4 h-4 mr-1" />
              Descartar
            </Button>
            <Button size="sm" onClick={handleSave} disabled={!dirty || saving}>
              <Save className="w-4 h-4 mr-1" />
              {saving ? "Guardando…" : "Guardar mapa"}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {error && (
          <div className="mb-4 p-3 rounded-md bg-red-50 text-sm text-red-700 border border-red-200">
            {error}
          </div>
        )}

        <Legend />

        <div className="grid grid-cols-12 gap-4 mt-4">
          {/* Paleta */}
          <aside className="col-span-12 md:col-span-3 space-y-4">
            <PaletteSection
              title="Mis Workers"
              description="Agentes definidos en la tab Workers."
              items={(data?.agents ?? []).filter((a) => a.enabled).map((a) => ({
                id: `agent:${a.id}`,
                name: a.name,
                hint: a.is_custom ? "custom" : a.intent ?? "",
              }))}
            />
            <PaletteSection
              title="Mis Workflows"
              description="Flujos definidos en la tab Workflows."
              items={(data?.workflows ?? []).filter((w) => w.enabled).map((w) => ({
                id: `workflow:${w.id}`,
                name: w.name,
                hint: w.trigger_type,
              }))}
            />
          </aside>

          {/* Canvas */}
          <div className="col-span-12 md:col-span-9">
            <div
              className="h-[600px] border rounded-lg bg-gray-50 overflow-hidden"
              onDragOver={handleDragOver}
              onDrop={handleDrop}
            >
              {loading && !data ? (
                <div className="h-full flex items-center justify-center text-gray-500 text-sm">
                  Cargando mapa…
                </div>
              ) : (
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  nodeTypes={NODE_TYPES}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  onConnect={onConnect}
                  onEdgesDelete={onEdgesDelete}
                  fitView
                  proOptions={{ hideAttribution: true }}
                  nodesDraggable
                  nodesConnectable
                  edgesFocusable
                  deleteKeyCode={["Backspace", "Delete"]}
                  defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed } }}
                >
                  <Background gap={20} />
                  <Controls showInteractive={false} />
                  <MiniMap pannable zoomable />
                </ReactFlow>
              )}
            </div>
          </div>
        </div>

        {data && (
          <div className="mt-4 text-xs text-gray-500 flex flex-wrap gap-4">
            <span>{data.agents.filter((a) => a.enabled).length} workers habilitados</span>
            <span>·</span>
            <span>{data.workflows.filter((w) => w.enabled).length} workflows activos</span>
            <span>·</span>
            <span>Entrada: {data.entry.kind === "on_start" ? "Workflow on_start" : "Hub Agéntico"}</span>
          </div>
        )}
      </CardContent>

      {/* Intent picker for new agentic edges */}
      <Dialog open={!!pendingConnection} onOpenChange={(o) => !o && setPendingConnection(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>¿Para qué intención?</DialogTitle>
            <DialogDescription>
              Selecciona la intención que activa esta conexión. Cuando el router agéntico clasifique
              un mensaje con esta intención, dirigirá la conversación al destino seleccionado.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1 py-2">
            <Label>Intención</Label>
            <select
              value={intentForConnection}
              onChange={(e) => setIntentForConnection(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              {INTENT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label} · {opt.value}
                </option>
              ))}
            </select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingConnection(null)}>
              Cancelar
            </Button>
            <Button onClick={handleConfirmIntent}>Crear conexión</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ── Palette ─────────────────────────────────────────────────────────────────

interface PaletteItem {
  id: string;
  name: string;
  hint?: string;
}

function PaletteSection({
  title,
  description,
  items,
}: {
  title: string;
  description: string;
  items: PaletteItem[];
}) {
  return (
    <Card>
      <CardHeader className="py-3">
        <CardTitle className="text-sm">{title}</CardTitle>
        <CardDescription className="text-xs">{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1.5 pt-0">
        {items.length === 0 ? (
          <p className="text-xs text-gray-400 italic">Vacío</p>
        ) : (
          items.map((it) => (
            <div
              key={it.id}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData("application/bot-map-node", it.id);
                e.dataTransfer.effectAllowed = "move";
              }}
              className="cursor-grab active:cursor-grabbing rounded-md border border-gray-200 bg-white px-2 py-1.5 text-sm hover:bg-gray-50"
            >
              <div className="font-medium truncate">{it.name}</div>
              {it.hint && <div className="text-xs text-gray-500">{it.hint}</div>}
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

// ── Legend ──────────────────────────────────────────────────────────────────

function Legend() {
  return (
    <div className="flex flex-wrap gap-2 text-xs">
      <Badge variant="outline" className="border-emerald-400 text-emerald-800">Inicio</Badge>
      <Badge variant="outline" className="border-purple-400 text-purple-800">Hub Agéntico</Badge>
      <Badge variant="outline" className="border-blue-400 text-blue-800">Worker</Badge>
      <Badge variant="outline" className="border-emerald-400 text-emerald-900">Workflow on_start</Badge>
      <Badge variant="outline" className="border-amber-400 text-amber-900">Workflow on_intent</Badge>
      <Badge variant="outline" className="border-indigo-400 text-indigo-900">Workflow manual</Badge>
    </div>
  );
}

// ── Graph builder ───────────────────────────────────────────────────────────

function labelForKind(kind: EdgeKind): string {
  switch (kind) {
    case "entry": return "Inicio";
    case "manual_trigger": return "trigger_flow";
    case "handoff": return "handoff";
    case "handoff_agentic": return "→ agentic";
    default: return "";
  }
}

function buildGraph(data: BotMap, extraNodeIds: Set<string>): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  nodes.push({
    id: "start",
    type: "start",
    position: { x: COL_X.start, y: 280 },
    data: { label: "Inicio del chat" } satisfies NodeData,
    draggable: false,
    deletable: false,
  });

  nodes.push({
    id: "agentic",
    type: "agenticHub",
    position: { x: COL_X.hub, y: 240 },
    data: { label: "Agentic Router" } satisfies NodeData,
    deletable: false,
  });

  // Agents/workflows that participate in any edge OR were dropped this session.
  const referencedNodes = new Set<string>();
  data.edges.forEach((e) => {
    if (e.source !== "start" && e.source !== "agentic") referencedNodes.add(e.source);
    if (e.target !== "agentic") referencedNodes.add(e.target);
  });
  extraNodeIds.forEach((id) => referencedNodes.add(id));

  const enabledAgents = data.agents.filter((a) => a.enabled);
  const visibleAgents = enabledAgents.filter((a) => referencedNodes.has(`agent:${a.id}`));
  visibleAgents.forEach((agent, i) => {
    nodes.push({
      id: `agent:${agent.id}`,
      type: "agent",
      position: { x: COL_X.agent, y: i * 110 },
      data: {
        label: agent.name,
        sublabel: agent.tools?.rag_search ? `RAG · ${agent.intent ?? ""}` : agent.intent ?? "",
        badge: agent.is_custom ? "custom" : agent.intent ?? undefined,
      } satisfies NodeData,
    });
  });

  const visibleWorkflows = data.workflows.filter((wf) => referencedNodes.has(`workflow:${wf.id}`));
  visibleWorkflows.forEach((wf, i) => {
    const variant: NodeData["variant"] =
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
      position: { x: COL_X.workflow, y: i * 130 },
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
      data: { kind: e.kind, intent: e.kind === "intent_route" || e.kind === "intent" ? e.label : null } as Record<string, unknown>,
      animated: e.kind === "entry" || e.kind === "manual_trigger",
      style: { stroke: style.stroke, strokeWidth: 1.5, strokeDasharray: style.dash },
      labelStyle: { fontSize: 10, fill: style.stroke, fontWeight: 600 },
      labelBgStyle: { fill: "#fff", opacity: 0.9 },
      markerEnd: { type: MarkerType.ArrowClosed, color: style.stroke },
      deletable: !READONLY_KINDS.includes(e.kind),
    });
  });

  return { nodes, edges };
}

export function BotMapView({ botId }: { botId: string }) {
  return (
    <ReactFlowProvider>
      <BotMapInner botId={botId} />
    </ReactFlowProvider>
  );
}
