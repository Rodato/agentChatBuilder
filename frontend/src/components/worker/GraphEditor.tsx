"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  Connection,
  Edge,
  Node,
  NodeProps,
  NodeTypes,
  Handle,
  Position,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Trash2 } from "lucide-react";
import { GraphDefinition, GraphNodeData, agentsApi, AgentRow } from "@/lib/api";

const MODEL_OPTIONS = [
  { value: "google/gemini-2.5-flash", label: "Gemini 2.5 Flash" },
  { value: "google/gemini-2.5-flash-lite", label: "Gemini 2.5 Flash Lite" },
  { value: "openai/gpt-4o-mini", label: "GPT-4o Mini" },
  { value: "anthropic/claude-sonnet-4.6", label: "Claude Sonnet 4.6" },
  { value: "anthropic/claude-haiku-4.5", label: "Claude Haiku 4.5" },
  { value: "mistralai/mistral-small-creative", label: "Mistral Small Creative" },
];

let _nodeCounter = 0;
function newNodeId(prefix: string): string {
  _nodeCounter += 1;
  return `${prefix}_${Date.now().toString(36)}_${_nodeCounter}`;
}

// ── Custom nodes ────────────────────────────────────────────────────────────

type NType = "orchestrator" | "subagent" | "synthesizer" | "worker_ref";

function nodeStyles(type: NType, selected?: boolean) {
  const base = "min-w-[180px] rounded-lg border bg-white shadow-sm";
  const sel = selected ? "ring-2 ring-offset-1" : "";
  if (type === "orchestrator") return `${base} border-purple-500 ${selected ? "ring-purple-300" : ""} ${sel}`;
  if (type === "synthesizer") return `${base} border-emerald-500 ${selected ? "ring-emerald-300" : ""} ${sel}`;
  if (type === "worker_ref") return `${base} border-cyan-500 ${selected ? "ring-cyan-300" : ""} ${sel}`;
  return `${base} border-blue-400 ${selected ? "ring-blue-300" : ""} ${sel}`;
}

function headerStyles(type: NType) {
  if (type === "orchestrator") return "bg-purple-100 text-purple-900";
  if (type === "synthesizer") return "bg-emerald-100 text-emerald-900";
  if (type === "worker_ref") return "bg-cyan-100 text-cyan-900";
  return "bg-blue-50 text-blue-900";
}

function NodeView({ data, selected, type }: NodeProps & { type?: NType }) {
  const d = (data || {}) as GraphNodeData;
  const t: NType = (type as NType) || (d.type as NType) || "subagent";
  return (
    <div className={nodeStyles(t, selected)}>
      {t !== "orchestrator" && (
        <Handle type="target" position={Position.Left} className="!bg-gray-500 !w-3 !h-3" />
      )}
      <div className={`px-3 py-2 border-b ${headerStyles(t)} text-xs font-semibold uppercase tracking-wide`}>
        {t}
      </div>
      <div className="p-3">
        <div className="text-sm font-medium">{d.label || d.system_prompt?.slice(0, 40) || "(sin nombre)"}</div>
        {d.model && <div className="text-xs text-gray-500 mt-0.5">{d.model}</div>}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-gray-500 !w-3 !h-3" />
    </div>
  );
}

const NODE_TYPES: NodeTypes = {
  orchestrator: (props) => <NodeView {...props} type="orchestrator" />,
  subagent: (props) => <NodeView {...props} type="subagent" />,
  synthesizer: (props) => <NodeView {...props} type="synthesizer" />,
  worker_ref: (props) => <NodeView {...props} type="worker_ref" />,
};

// ── Editor component ────────────────────────────────────────────────────────

interface Props {
  value: GraphDefinition | null | undefined;
  onChange: (next: GraphDefinition) => void;
  botId?: string; // when set, enables worker_ref dropdown with sibling workers
  selfAgentId?: string; // exclude self from the dropdown to prevent direct recursion
}

function GraphEditorInner({ value, onChange, botId, selfAgentId }: Props) {
  const [siblingWorkers, setSiblingWorkers] = useState<AgentRow[]>([]);
  useEffect(() => {
    if (!botId) return;
    let cancelled = false;
    agentsApi
      .list(botId)
      .then((rows) => {
        if (cancelled) return;
        setSiblingWorkers(rows.filter((r) => r.agent_id !== selfAgentId && r.enabled));
      })
      .catch(() => setSiblingWorkers([]));
    return () => {
      cancelled = true;
    };
  }, [botId, selfAgentId]);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [entryNodeId, setEntryNodeId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const { screenToFlowPosition } = useReactFlow();
  const initialized = useRef(false);

  // Initialize from incoming value once.
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    if (!value || !value.nodes || value.nodes.length === 0) {
      // Seed with a default orchestrator + subagent + synthesizer.
      const orchId = newNodeId("orch");
      const subId = newNodeId("sub");
      const synthId = newNodeId("synth");
      const seedNodes: Node[] = [
        { id: orchId, type: "orchestrator", position: { x: 40, y: 100 },
          data: { label: "Orquestador", system_prompt: "Decide a qué sub-agente delegar.", model: "google/gemini-2.5-flash-lite", temperature: 0.2 } },
        { id: subId, type: "subagent", position: { x: 320, y: 40 },
          data: { label: "Investigador", system_prompt: "Eres un investigador que responde con base en documentos.", model: "google/gemini-2.5-flash", temperature: 0.3, tools: { rag_search: true, user_memory: false, trigger_flow: false, human_handoff: false, external_api: false } } },
        { id: synthId, type: "synthesizer", position: { x: 600, y: 100 },
          data: { label: "Sintetizador", system_prompt: "Sintetiza los outputs en una respuesta final clara.", model: "google/gemini-2.5-flash", temperature: 0.4 } },
      ];
      const seedEdges: Edge[] = [
        { id: `e_${orchId}_${subId}`, source: orchId, target: subId, markerEnd: { type: MarkerType.ArrowClosed } },
        { id: `e_${subId}_${synthId}`, source: subId, target: synthId, markerEnd: { type: MarkerType.ArrowClosed } },
      ];
      setNodes(seedNodes);
      setEdges(seedEdges);
      setEntryNodeId(orchId);
      onChange({ version: 1, entry_node_id: orchId, nodes: toNodesPayload(seedNodes), edges: toEdgesPayload(seedEdges) });
      return;
    }
    const nNodes: Node[] = value.nodes.map((n) => ({
      id: n.id,
      type: n.type,
      position: n.position,
      data: n.data as Record<string, unknown>,
    }));
    const nEdges: Edge[] = value.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.label,
      markerEnd: { type: MarkerType.ArrowClosed },
    }));
    setNodes(nNodes);
    setEdges(nEdges);
    setEntryNodeId(value.entry_node_id ?? nNodes[0]?.id ?? null);
  }, [value, setNodes, setEdges, onChange]);

  // Push state up whenever nodes/edges change.
  useEffect(() => {
    if (!initialized.current) return;
    onChange({
      version: 1,
      entry_node_id: entryNodeId ?? nodes[0]?.id ?? null,
      nodes: toNodesPayload(nodes),
      edges: toEdgesPayload(edges),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, entryNodeId]);

  const onConnect = useCallback(
    (conn: Connection) => {
      setEdges((eds) =>
        addEdge(
          {
            ...conn,
            id: `e_${conn.source}_${conn.target}`,
            markerEnd: { type: MarkerType.ArrowClosed },
          },
          eds
        )
      );
    },
    [setEdges]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const type = event.dataTransfer.getData("application/worker-graph-node") as NType;
      if (!type) return;
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const id = newNodeId(type);
      const data: GraphNodeData =
        type === "orchestrator"
          ? { label: "Orquestador", system_prompt: "Decide a qué sub-agente delegar.", model: "google/gemini-2.5-flash-lite", temperature: 0.2 }
          : type === "synthesizer"
          ? { label: "Sintetizador", system_prompt: "Sintetiza los outputs en una respuesta final.", model: "google/gemini-2.5-flash", temperature: 0.4 }
          : type === "worker_ref"
          ? { label: "Delegar a worker", target_worker_id: siblingWorkers[0]?.agent_id }
          : { label: "Sub-agente", system_prompt: "", model: "google/gemini-2.5-flash-lite", temperature: 0.5 };
      const newNode: Node = { id, type, position, data: data as Record<string, unknown> };
      setNodes((ns) => ns.concat(newNode));
      setSelectedId(id);
    },
    [screenToFlowPosition, setNodes]
  );

  const updateNodeData = useCallback(
    (id: string, patch: Partial<GraphNodeData>) => {
      setNodes((ns) =>
        ns.map((n) => (n.id === id ? { ...n, data: { ...(n.data as object), ...patch } } : n))
      );
    },
    [setNodes]
  );

  const removeNode = useCallback(
    (id: string) => {
      setNodes((ns) => ns.filter((n) => n.id !== id));
      setEdges((es) => es.filter((e) => e.source !== id && e.target !== id));
      setEntryNodeId((prev) => (prev === id ? null : prev));
      setSelectedId(null);
    },
    [setNodes, setEdges]
  );

  const selectedNode = useMemo(() => nodes.find((n) => n.id === selectedId) || null, [nodes, selectedId]);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-3 space-y-2">
          <Card>
            <CardHeader className="py-3">
              <CardTitle className="text-sm">Paleta</CardTitle>
              <CardDescription className="text-xs">Arrastra al canvas</CardDescription>
            </CardHeader>
            <CardContent className="space-y-1.5 pt-0">
              {(["orchestrator", "subagent", "synthesizer", "worker_ref"] as NType[]).map((t) => (
                <div
                  key={t}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData("application/worker-graph-node", t);
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  className={`cursor-grab active:cursor-grabbing rounded-md border px-2 py-1.5 text-sm ${
                    t === "orchestrator"
                      ? "border-purple-400 bg-purple-50 text-purple-900"
                      : t === "synthesizer"
                      ? "border-emerald-400 bg-emerald-50 text-emerald-900"
                      : t === "worker_ref"
                      ? "border-cyan-400 bg-cyan-50 text-cyan-900"
                      : "border-blue-400 bg-blue-50 text-blue-900"
                  }`}
                  title={
                    t === "worker_ref"
                      ? "Delega la respuesta a otro Worker top-level del bot"
                      : undefined
                  }
                >
                  {t === "worker_ref" ? "delegate" : t}
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        <div className="col-span-6">
          <div
            ref={wrapperRef}
            className="h-[400px] rounded-lg border bg-gray-50 overflow-hidden"
            onDragOver={handleDragOver}
            onDrop={handleDrop}
          >
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onSelectionChange={(s) => setSelectedId(s.nodes[0]?.id ?? null)}
              nodeTypes={NODE_TYPES}
              fitView
              proOptions={{ hideAttribution: true }}
              deleteKeyCode={["Backspace", "Delete"]}
            >
              <Background gap={16} />
              <Controls showInteractive={false} />
              <MiniMap pannable zoomable />
            </ReactFlow>
          </div>
        </div>

        <div className="col-span-3">
          <Card>
            <CardHeader className="py-3">
              <CardTitle className="text-sm">Inspector</CardTitle>
              <CardDescription className="text-xs">
                {selectedNode ? `${selectedNode.type}` : "Selecciona un nodo"}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {selectedNode ? (
                <NodeInspector
                  node={selectedNode}
                  isEntry={entryNodeId === selectedNode.id}
                  siblingWorkers={siblingWorkers}
                  onChange={(p) => updateNodeData(selectedNode.id, p)}
                  onSetEntry={() => setEntryNodeId(selectedNode.id)}
                  onDelete={() => removeNode(selectedNode.id)}
                />
              ) : (
                <p className="text-xs text-gray-500">Click un nodo del canvas para editarlo.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
      <p className="text-xs text-gray-500">
        El orquestador decide a qué sub-agente delegar respondiendo con un JSON{" "}
        <code>{`{"route":"<id>"}`}</code>. Los sub-agentes responden y, si conectas un sintetizador
        downstream, éste combina los outputs en la respuesta final.
      </p>
    </div>
  );
}

interface InspectorProps {
  node: Node;
  isEntry: boolean;
  siblingWorkers: AgentRow[];
  onChange: (patch: Partial<GraphNodeData>) => void;
  onSetEntry: () => void;
  onDelete: () => void;
}

function NodeInspector({ node, isEntry, siblingWorkers, onChange, onSetEntry, onDelete }: InspectorProps) {
  const data = (node.data || {}) as GraphNodeData;
  const isWorkerRef = node.type === "worker_ref";
  return (
    <>
      <div className="flex items-center justify-between gap-2">
        {isEntry ? (
          <span className="text-xs text-gray-500">Nodo de entrada</span>
        ) : (
          <Button variant="outline" size="sm" onClick={onSetEntry}>
            Marcar como entrada
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={onDelete}>
          <Trash2 className="w-4 h-4 text-red-600" />
        </Button>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Etiqueta</Label>
        <Input value={data.label ?? ""} onChange={(e) => onChange({ label: e.target.value })} />
      </div>

      {isWorkerRef && (
        <div className="space-y-1">
          <Label className="text-xs">Worker destino</Label>
          <select
            value={data.target_worker_id ?? ""}
            onChange={(e) => onChange({ target_worker_id: e.target.value })}
            className="w-full rounded-md border border-input bg-background px-2 py-1 text-xs"
          >
            <option value="">(selecciona un worker)</option>
            {siblingWorkers.map((w) => (
              <option key={w.agent_id} value={w.agent_id}>
                {w.name}
                {w.is_custom ? " (custom)" : ""}
              </option>
            ))}
          </select>
          <p className="text-xs text-gray-500">
            Cuando este nodo se ejecuta, delega al worker seleccionado y usa su respuesta como output.
          </p>
        </div>
      )}

      {!isWorkerRef && (
      <div className="space-y-1">
        <Label className="text-xs">System prompt</Label>
        <Textarea
          rows={4}
          value={data.system_prompt ?? ""}
          onChange={(e) => onChange({ system_prompt: e.target.value })}
        />
      </div>
      )}
      {!isWorkerRef && (
      <div className="space-y-1">
        <Label className="text-xs">Modelo</Label>
        <select
          value={data.model ?? "google/gemini-2.5-flash-lite"}
          onChange={(e) => onChange({ model: e.target.value })}
          className="w-full rounded-md border border-input bg-background px-2 py-1 text-xs"
        >
          {MODEL_OPTIONS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </div>
      )}
      {!isWorkerRef && (
      <div className="space-y-1">
        <Label className="text-xs">Temperatura: {(data.temperature ?? 0.5).toFixed(1)}</Label>
        <input
          type="range"
          min={0}
          max={1}
          step={0.1}
          value={data.temperature ?? 0.5}
          onChange={(e) => onChange({ temperature: parseFloat(e.target.value) })}
          className="w-full accent-blue-600"
        />
      </div>
      )}
      {node.type === "subagent" && (
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={Boolean(data.tools?.rag_search)}
            onChange={(e) =>
              onChange({
                tools: {
                  user_memory: false,
                  trigger_flow: false,
                  human_handoff: false,
                  external_api: false,
                  ...(data.tools || {}),
                  rag_search: e.target.checked,
                },
              })
            }
          />
          RAG en este sub-agente
        </label>
      )}
    </>
  );
}

function toNodesPayload(nodes: Node[]) {
  return nodes.map((n) => ({
    id: n.id,
    type: (n.type as "orchestrator" | "subagent" | "synthesizer") || "subagent",
    position: { x: n.position.x, y: n.position.y },
    data: (n.data || {}) as GraphNodeData,
  }));
}

function toEdgesPayload(edges: Edge[]) {
  return edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: typeof e.label === "string" ? e.label : undefined,
  }));
}

export function GraphEditor(props: Props) {
  return (
    <ReactFlowProvider>
      <GraphEditorInner {...props} />
    </ReactFlowProvider>
  );
}
