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
  NodeTypes,
  ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Trash2, ArrowLeft } from "lucide-react";

import { AgentNode } from "./nodes/AgentNode";
import { CaptureNode } from "./nodes/CaptureNode";
import { HandoffNode } from "./nodes/HandoffNode";
import { MessageNode } from "./nodes/MessageNode";
import {
  workflowApi,
  WorkflowDefinition,
  WorkflowNodeData,
  WorkflowSummary,
  TriggerType,
  IntentKey,
  INTENT_LABELS,
} from "@/lib/workflowApi";
import { agentsApi, AgentRow } from "@/lib/api";

const NODE_TYPES: NodeTypes = {
  agent: AgentNode,
  capture: CaptureNode,
  handoff: HandoffNode,
  message: MessageNode,
};

let _nodeCounter = 0;
function newNodeId(prefix: string): string {
  _nodeCounter += 1;
  return `${prefix}_${Date.now().toString(36)}_${_nodeCounter}`;
}

interface InnerProps {
  botId: string;
  workflowId: string;
  onBack: () => void;
}

function WorkflowEditorInner({ botId, workflowId, onBack }: InnerProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [name, setName] = useState("Workflow");
  const [triggerType, setTriggerType] = useState<TriggerType>("manual");
  const [triggerValue, setTriggerValue] = useState<IntentKey>("FACTUAL");
  const [enabled, setEnabled] = useState(true);
  const [entryNodeId, setEntryNodeId] = useState<string | null>(null);
  const [otherWorkflows, setOtherWorkflows] = useState<WorkflowSummary[]>([]);
  const [agentRows, setAgentRows] = useState<AgentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const rfRef = useRef<ReactFlowInstance | null>(null);
  const { screenToFlowPosition } = useReactFlow();

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      workflowApi.get(botId, workflowId),
      workflowApi.list(botId),
      agentsApi.list(botId),
    ])
      .then(([wf, list, agents]) => {
        if (cancelled) return;
        setName(wf.name || "Workflow");
        setTriggerType(wf.trigger_type);
        setTriggerValue((wf.trigger_value as IntentKey) || "FACTUAL");
        setEnabled(wf.enabled);
        setEntryNodeId(wf.definition?.entry_node_id ?? null);
        setNodes((wf.definition?.nodes || []) as Node[]);
        setEdges((wf.definition?.edges || []) as Edge[]);
        setOtherWorkflows(list.filter((w) => w.id !== workflowId));
        setAgentRows(agents);
      })
      .catch((e) => setMessage(`Error cargando: ${e.message}`))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [botId, workflowId, setEdges, setNodes]);

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) =>
        addEdge({ ...connection, id: `e_${connection.source}_${connection.target}` }, eds)
      );
    },
    [setEdges]
  );

  const handleDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const type = event.dataTransfer.getData("application/workflow-node-type") as
        | "capture"
        | "agent"
        | "handoff"
        | "message";
      if (!type) return;
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const id = newNodeId(type);
      let data: WorkflowNodeData = {};
      if (type === "capture") {
        data = { var_name: "", prompt: "", skip_if_present: false };
      } else if (type === "agent") {
        data = { agent_id: "factual", system_prompt_override: "" };
      } else if (type === "message") {
        data = { text: "" };
      } else {
        data = { target: "agentic", farewell: "" };
      }
      const newNode: Node = {
        id,
        type,
        position,
        data: data as unknown as Record<string, unknown>,
      };
      setNodes((nds) => nds.concat(newNode));
      setEntryNodeId((prev) => prev ?? id);
      setSelectedId(id);
    },
    [screenToFlowPosition, setNodes]
  );

  const updateNodeData = useCallback(
    (nodeId: string, patch: Partial<WorkflowNodeData>) => {
      setNodes((nds) =>
        nds.map((n) => (n.id === nodeId ? { ...n, data: { ...(n.data || {}), ...patch } } : n))
      );
    },
    [setNodes]
  );

  const removeNode = useCallback(
    (nodeId: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== nodeId));
      setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
      setEntryNodeId((prev) => (prev === nodeId ? null : prev));
      setSelectedId(null);
    },
    [setEdges, setNodes]
  );

  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selectedId) || null,
    [nodes, selectedId]
  );

  const availableVars = useMemo(() => {
    return nodes
      .filter((n) => n.type === "capture" && (n.data as WorkflowNodeData)?.var_name)
      .map((n) => (n.data as WorkflowNodeData).var_name as string);
  }, [nodes]);

  const buildDefinition = (): WorkflowDefinition => ({
    version: 1,
    entry_node_id: entryNodeId ?? (nodes[0]?.id ?? null),
    nodes: nodes.map((n) => ({
      id: n.id,
      type: (n.type as "agent" | "capture" | "handoff") ?? "agent",
      position: { x: n.position.x, y: n.position.y },
      data: (n.data || {}) as WorkflowNodeData,
    })),
    edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target })),
  });

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await workflowApi.update(botId, workflowId, {
        name: name || "Workflow",
        trigger_type: triggerType,
        trigger_value: triggerType === "on_intent" ? triggerValue : null,
        enabled,
        definition: buildDefinition(),
      });
      setMessage("Guardado. Conversaciones activas de este bot fueron reiniciadas.");
    } catch (e) {
      setMessage(`Error: ${e instanceof Error ? e.message : "no se pudo guardar"}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-gray-500">Cargando editor…</p>;
  }

  return (
    <div className="space-y-4">
      {/* Toolbar superior */}
      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" onClick={onBack}>
          <ArrowLeft className="w-4 h-4 mr-1" /> Volver
        </Button>
        <span className="text-sm text-gray-600">
          Editando workflow — <span className="font-medium">{name}</span>
        </span>
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* Paleta + configuración */}
        <div className="col-span-12 md:col-span-3 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Paleta</CardTitle>
              <CardDescription>Arrastra al canvas</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              <div
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData("application/workflow-node-type", "message");
                  e.dataTransfer.effectAllowed = "move";
                }}
                className="cursor-grab active:cursor-grabbing rounded-md border border-yellow-300 bg-yellow-50 px-3 py-2 text-sm text-yellow-900"
              >
                💬 Mensaje fijo
              </div>
              <div
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData("application/workflow-node-type", "capture");
                  e.dataTransfer.effectAllowed = "move";
                }}
                className="cursor-grab active:cursor-grabbing rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
              >
                📝 Captura de dato
              </div>
              <div
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData("application/workflow-node-type", "agent");
                  e.dataTransfer.effectAllowed = "move";
                }}
                className="cursor-grab active:cursor-grabbing rounded-md border border-blue-300 bg-blue-50 px-3 py-2 text-sm text-blue-900"
              >
                🤖 Agente
              </div>
              <div
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData("application/workflow-node-type", "handoff");
                  e.dataTransfer.effectAllowed = "move";
                }}
                className="cursor-grab active:cursor-grabbing rounded-md border border-gray-300 bg-gray-50 px-3 py-2 text-sm text-gray-900"
              >
                🚪 Handoff (salir del flujo)
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Configuración</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1">
                <Label>Nombre</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>Disparador</Label>
                <select
                  value={triggerType}
                  onChange={(e) => setTriggerType(e.target.value as TriggerType)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  <option value="on_start">Al inicio de la conversación</option>
                  <option value="on_intent">Por intención detectada</option>
                  <option value="manual">Manual (agente lo dispara)</option>
                </select>
              </div>
              {triggerType === "on_intent" && (
                <div className="space-y-1">
                  <Label>Intención</Label>
                  <select
                    value={triggerValue}
                    onChange={(e) => setTriggerValue(e.target.value as IntentKey)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    {(Object.keys(INTENT_LABELS) as IntentKey[]).map((key) => (
                      <option key={key} value={key}>
                        {INTENT_LABELS[key]}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <label className="flex items-center gap-2 text-sm pt-1">
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                />
                Habilitado
              </label>
              <Button onClick={handleSave} disabled={saving} className="w-full">
                {saving ? "Guardando…" : "Guardar"}
              </Button>
              {message && <p className="text-xs text-gray-600">{message}</p>}
            </CardContent>
          </Card>
        </div>

        {/* Canvas */}
        <div className="col-span-12 md:col-span-6">
          <div
            ref={wrapperRef}
            className="h-[600px] rounded-lg border bg-white overflow-hidden"
            onDragOver={handleDragOver}
            onDrop={handleDrop}
          >
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onInit={(instance) => (rfRef.current = instance)}
              onSelectionChange={(s) => setSelectedId(s.nodes[0]?.id ?? null)}
              nodeTypes={NODE_TYPES}
              fitView
              deleteKeyCode={["Backspace", "Delete"]}
            >
              <Background />
              <Controls />
              <MiniMap pannable zoomable />
            </ReactFlow>
          </div>
        </div>

        {/* Inspector */}
        <div className="col-span-12 md:col-span-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Inspector</CardTitle>
              <CardDescription>
                {selectedNode ? `Editando ${selectedNode.type}` : "Selecciona un nodo"}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {selectedNode ? (
                <NodeInspector
                  node={selectedNode}
                  isEntry={entryNodeId === selectedNode.id}
                  availableVars={availableVars}
                  otherWorkflows={otherWorkflows}
                  agents={agentRows}
                  onChange={(patch) => updateNodeData(selectedNode.id, patch)}
                  onDelete={() => removeNode(selectedNode.id)}
                  onSetEntry={() => setEntryNodeId(selectedNode.id)}
                />
              ) : (
                <p className="text-sm text-gray-500">Haz clic en un nodo del canvas.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

// ── Inspector ────────────────────────────────────────────────────────────────

interface InspectorProps {
  node: Node;
  isEntry: boolean;
  availableVars: string[];
  otherWorkflows: WorkflowSummary[];
  agents: AgentRow[];
  onChange: (patch: Partial<WorkflowNodeData>) => void;
  onDelete: () => void;
  onSetEntry: () => void;
}

function NodeInspector({
  node,
  isEntry,
  availableVars,
  otherWorkflows,
  agents,
  onChange,
  onDelete,
  onSetEntry,
}: InspectorProps) {
  const data = (node.data || {}) as WorkflowNodeData;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        {isEntry ? (
          <Badge>Nodo inicial</Badge>
        ) : (
          <Button variant="outline" size="sm" onClick={onSetEntry}>
            Marcar como inicial
          </Button>
        )}
      </div>

      {node.type === "message" && (
        <>
          <div className="space-y-1">
            <Label>Mensaje del bot</Label>
            <Textarea
              rows={5}
              placeholder="Hola! Soy el asistente de Acme. Hoy te ayudaré a..."
              value={data.text ?? ""}
              onChange={(e) => onChange({ text: e.target.value })}
            />
            <p className="text-xs text-gray-500">
              Texto fijo que el bot envía sin esperar respuesta del usuario. Soporta variables: {availableVars.length ? availableVars.map((v) => `{{${v}}}`).join(" ") : "—"}
            </p>
          </div>
        </>
      )}

      {node.type === "capture" && (
        <>
          <div className="space-y-1">
            <Label>Nombre de la variable</Label>
            <Input
              placeholder="user_name"
              value={data.var_name ?? ""}
              onChange={(e) =>
                onChange({ var_name: e.target.value.replace(/\s+/g, "_").replace(/[^\w]/g, "") })
              }
            />
          </div>
          <div className="space-y-1">
            <Label>Pregunta al usuario</Label>
            <Textarea
              rows={3}
              placeholder="¿Cómo te llamas?"
              value={data.prompt ?? ""}
              onChange={(e) => onChange({ prompt: e.target.value })}
            />
            <p className="text-xs text-gray-500">
              Variables previas:{" "}
              {availableVars.length ? availableVars.map((v) => `{{${v}}}`).join(" ") : "—"}
            </p>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={Boolean(data.skip_if_present)}
              onChange={(e) => onChange({ skip_if_present: e.target.checked })}
            />
            Saltar si la variable ya existe
          </label>
        </>
      )}

      {node.type === "agent" && (
        <>
          <div className="space-y-1">
            <Label>Worker</Label>
            <select
              value={data.agent_id ?? "factual"}
              onChange={(e) => onChange({ agent_id: e.target.value })}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              {!agents.some((a) => a.agent_id === (data.agent_id ?? "factual")) &&
                data.agent_id && (
                  <option value={data.agent_id}>
                    ⚠ {data.agent_id} (no encontrado)
                  </option>
                )}
              {agents.map((a) => (
                <option key={a.agent_id} value={a.agent_id} disabled={!a.enabled}>
                  {a.name}
                  {a.is_custom ? " (custom)" : ""}
                  {!a.enabled ? " — deshabilitado" : ""}
                </option>
              ))}
            </select>
            {data.agent_id && !agents.some((a) => a.agent_id === data.agent_id) && (
              <p className="text-xs text-red-600">
                ⚠️ Este worker ya no existe. Elige otro o el workflow fallará en runtime.
              </p>
            )}
          </div>
          <div className="space-y-1">
            <Label>Instrucción (opcional)</Label>
            <Textarea
              rows={4}
              placeholder="Ayuda a {{user_name}} con su consulta."
              value={data.system_prompt_override ?? ""}
              onChange={(e) => onChange({ system_prompt_override: e.target.value })}
            />
            <p className="text-xs text-gray-500">
              Variables:{" "}
              {availableVars.length ? availableVars.map((v) => `{{${v}}}`).join(" ") : "—"}
            </p>
          </div>
        </>
      )}

      {node.type === "handoff" && (
        <>
          <div className="space-y-1">
            <Label>Destino</Label>
            <select
              value={data.target ?? "agentic"}
              onChange={(e) => onChange({ target: e.target.value as "agentic" | "workflow" })}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="agentic">Sistema agéntico (orchestrator)</option>
              <option value="workflow">Otro workflow</option>
            </select>
          </div>
          {data.target === "workflow" && (
            <div className="space-y-1">
              <Label>Workflow destino</Label>
              <select
                value={data.target_workflow_id ?? ""}
                onChange={(e) => onChange({ target_workflow_id: e.target.value })}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="">(selecciona uno)</option>
                {otherWorkflows.map((wf) => (
                  <option key={wf.id} value={wf.id}>
                    {wf.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="space-y-1">
            <Label>Mensaje de despedida (opcional)</Label>
            <Textarea
              rows={3}
              placeholder="Listo! ¿En qué más puedo ayudarte?"
              value={data.farewell ?? ""}
              onChange={(e) => onChange({ farewell: e.target.value })}
            />
            <p className="text-xs text-gray-500">
              Soporta variables: {availableVars.length ? availableVars.map((v) => `{{${v}}}`).join(" ") : "—"}
            </p>
          </div>
        </>
      )}

      <Button variant="destructive" size="sm" onClick={onDelete} className="w-full">
        <Trash2 className="w-4 h-4 mr-1" /> Eliminar nodo
      </Button>
    </div>
  );
}

export function WorkflowEditor({
  botId,
  workflowId,
  onBack,
}: {
  botId: string;
  workflowId: string;
  onBack: () => void;
}) {
  return (
    <ReactFlowProvider>
      <WorkflowEditorInner botId={botId} workflowId={workflowId} onBack={onBack} />
    </ReactFlowProvider>
  );
}
