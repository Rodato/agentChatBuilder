"use client";

import { useState, useEffect } from "react";
import { Agent } from "./AgentCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ArrowLeft } from "lucide-react";
import { workflowApi, WorkflowSummary } from "@/lib/workflowApi";
import { IntentKey, GraphDefinition, WorkerKind } from "@/lib/api";
import { GraphEditor } from "@/components/worker/GraphEditor";

const MODEL_GROUPS = [
  {
    group: "Google",
    models: [
      { value: "google/gemini-2.5-flash", label: "Gemini 2.5 Flash" },
      { value: "google/gemini-2.5-flash-lite", label: "Gemini 2.5 Flash Lite" },
      { value: "google/gemini-3.1-pro-preview", label: "Gemini 3.1 Pro Preview" },
      { value: "google/gemini-3.1-flash-lite-preview", label: "Gemini 3.1 Flash Lite Preview" },
      { value: "google/gemini-3-pro-preview", label: "Gemini 3 Pro Preview" },
    ],
  },
  {
    group: "OpenAI",
    models: [
      { value: "openai/gpt-4o-mini", label: "GPT-4o Mini" },
      { value: "openai/gpt-4.1-mini", label: "GPT-4.1 Mini" },
      { value: "openai/gpt-5.4", label: "GPT-5.4" },
      { value: "openai/gpt-4o", label: "GPT-4o" },
    ],
  },
  {
    group: "Anthropic",
    models: [
      { value: "anthropic/claude-sonnet-4.6", label: "Claude Sonnet 4.6" },
      { value: "anthropic/claude-opus-4.6", label: "Claude Opus 4.6" },
      { value: "anthropic/claude-haiku-4.5", label: "Claude Haiku 4.5" },
      { value: "anthropic/claude-3.7-sonnet:thinking", label: "Claude 3.7 Sonnet (Thinking)" },
    ],
  },
  {
    group: "Mistral",
    models: [
      { value: "mistralai/mistral-small-2603", label: "Mistral Small 2603" },
      { value: "mistralai/mistral-small-creative", label: "Mistral Small Creative" },
      { value: "mistralai/mistral-small-3.2-24b-instruct", label: "Mistral Small 3.2 24B" },
    ],
  },
  {
    group: "MiniMax",
    models: [
      { value: "minimax/minimax-m2.7", label: "MiniMax M2.7" },
    ],
  },
  {
    group: "DeepSeek",
    models: [
      { value: "deepseek/deepseek-r1-distill-qwen-7b", label: "DeepSeek R1 Qwen 7B" },
      { value: "deepseek/deepseek-r1-distill-qwen-14b", label: "DeepSeek R1 Qwen 14B" },
      { value: "deepseek/deepseek-r1-0528", label: "DeepSeek R1 0528" },
      { value: "deepseek/deepseek-r1-distill-qwen-32b", label: "DeepSeek R1 Qwen 32B" },
    ],
  },
];

const TOOL_LABELS: Record<keyof Agent["tools"], string> = {
  rag_search: "Búsqueda en documentos (RAG)",
  user_memory: "Memoria de usuario",
  trigger_flow: "Disparar flujo",
  human_handoff: "Transferir a humano",
  external_api: "API externa",
};

const INTENT_OPTIONS: { value: IntentKey; label: string; description: string }[] = [
  { value: "GREETING", label: "Saludo", description: "Hola, buenos días, hi…" },
  { value: "FACTUAL", label: "Informativo (RAG)", description: "Preguntas sobre los documentos" },
  { value: "PLAN", label: "Planificación", description: "Crear planes, pasos, estrategia" },
  { value: "IDEATE", label: "Lluvia de ideas", description: "Brainstorm, creatividad" },
  { value: "SENSITIVE", label: "Sensible", description: "Temas delicados con cuidado" },
  { value: "AMBIGUOUS", label: "Ambiguo / Fallback", description: "Cuando nada más calza" },
];

function temperatureLabel(t: number): string {
  if (t <= 0.3) return "Conservador";
  if (t >= 0.7) return "Creativo";
  return "Balanceado";
}

interface AgentEditPanelProps {
  agent: Agent | null;
  botId: string;
  onSave: (updated: Agent) => void;
  onClose: () => void;
}

export function AgentEditPanel({ agent, botId, onSave, onClose }: AgentEditPanelProps) {
  const [draft, setDraft] = useState<Agent | null>(null);
  const [manualWorkflows, setManualWorkflows] = useState<WorkflowSummary[]>([]);

  useEffect(() => {
    if (agent) {
      setDraft({
        ...agent,
        tools: { ...agent.tools },
        trigger_flows: [...(agent.trigger_flows ?? [])],
        intents: [...(agent.intents ?? [])],
        kind: agent.kind ?? "agent",
        graph_definition: agent.graph_definition ?? null,
      });
    } else {
      setDraft(null);
    }
  }, [agent]);

  useEffect(() => {
    if (!agent) return;
    workflowApi
      .list(botId)
      .then((list) => setManualWorkflows(list.filter((w) => w.trigger_type === "manual")))
      .catch(() => setManualWorkflows([]));
  }, [agent, botId]);

  if (!agent || !draft) return null;

  const updateField = <K extends keyof Agent>(key: K, value: Agent[K]) =>
    setDraft((prev) => prev ? { ...prev, [key]: value } : prev);

  const updateTool = (tool: keyof Agent["tools"], value: boolean) =>
    setDraft((prev) =>
      prev ? { ...prev, tools: { ...prev.tools, [tool]: value } } : prev
    );

  const toggleTriggerFlow = (workflowId: string, checked: boolean) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const current = new Set(prev.trigger_flows ?? []);
      if (checked) current.add(workflowId);
      else current.delete(workflowId);
      return { ...prev, trigger_flows: Array.from(current) };
    });
  };

  const toggleIntent = (intent: IntentKey, checked: boolean) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const current = new Set<IntentKey>(prev.intents ?? []);
      if (checked) current.add(intent);
      else current.delete(intent);
      return { ...prev, intents: Array.from(current) };
    });
  };

  const setKind = (kind: WorkerKind) =>
    setDraft((prev) => (prev ? { ...prev, kind } : prev));

  const setGraphDefinition = (def: GraphDefinition) =>
    setDraft((prev) => (prev ? { ...prev, graph_definition: def } : prev));

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button variant="outline" size="sm" onClick={onClose}>
              <ArrowLeft className="w-4 h-4 mr-1" /> Volver
            </Button>
            <div>
              <CardTitle>{draft.is_custom ? "Editando Worker" : "Editando Worker (builtin)"}</CardTitle>
              <CardDescription>
                {draft.is_custom
                  ? "Diseña este worker — su prompt, modelo, herramientas y, si es un grafo, sus sub-agentes."
                  : "Worker builtin del sistema. Puedes editar su prompt y modelo, pero no su intent ni eliminarlo."}
              </CardDescription>
            </div>
          </div>
          <Button onClick={() => onSave(draft)}>Guardar cambios</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-6 py-2">
          {/* TIPO DE WORKER — solo para customs */}
          {draft.is_custom && (
            <section className="space-y-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
                Tipo de Worker
              </h3>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setKind("agent")}
                  className={`flex-1 rounded-md border px-3 py-2 text-sm transition ${
                    draft.kind !== "graph"
                      ? "border-blue-500 bg-blue-50 text-blue-900 font-medium"
                      : "border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  Agente único
                  <div className="text-xs font-normal mt-0.5">Un LLM con prompt y tools.</div>
                </button>
                <button
                  type="button"
                  onClick={() => setKind("graph")}
                  className={`flex-1 rounded-md border px-3 py-2 text-sm transition ${
                    draft.kind === "graph"
                      ? "border-purple-500 bg-purple-50 text-purple-900 font-medium"
                      : "border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  Grafo de sub-agentes
                  <div className="text-xs font-normal mt-0.5">Orquestador + workers internos.</div>
                </button>
              </div>
            </section>
          )}

          {/* GRAFO — editor visual cuando kind=graph */}
          {draft.is_custom && draft.kind === "graph" && (
            <section className="space-y-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
                Diseño del grafo
              </h3>
              <GraphEditor
                value={draft.graph_definition}
                onChange={setGraphDefinition}
              />
            </section>
          )}

          {/* NAME — siempre visible (también para grafos) */}
          <section className="space-y-2">
            <div className="space-y-1">
              <Label>Nombre</Label>
              <Input
                value={draft.name}
                disabled={!draft.is_custom}
                onChange={(e) => updateField("name", e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label>Objetivo</Label>
              <Input
                value={draft.objective}
                onChange={(e) => updateField("objective", e.target.value)}
                placeholder="Describe brevemente el objetivo de este worker"
              />
            </div>
          </section>

          {/* BRAIN — solo si NO es grafo (en grafos cada sub-nodo tiene su propio cerebro) */}
          {draft.kind !== "graph" && (
          <section className="space-y-4">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              Cerebro (Brain)
            </h3>

            <div className="space-y-1">
              <Label>Instrucciones (System Prompt)</Label>
              <Textarea
                rows={5}
                value={draft.system_prompt}
                onChange={(e) => updateField("system_prompt", e.target.value)}
                placeholder="Describe cómo debe comportarse el agente..."
              />
            </div>

            <div className="space-y-1">
              <Label>Modelo</Label>
              <select
                value={draft.model}
                onChange={(e) => updateField("model", e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {MODEL_GROUPS.map((group) => (
                  <optgroup key={group.group} label={group.group}>
                    {group.models.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <Label>Estilo de respuesta</Label>
                <span className="text-sm font-medium text-gray-600">
                  {temperatureLabel(draft.temperature)}
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.1}
                value={draft.temperature}
                onChange={(e) => updateField("temperature", parseFloat(e.target.value))}
                className="w-full accent-blue-600"
              />
              <div className="flex justify-between text-xs text-gray-400">
                <span>Conservador</span>
                <span>Creativo</span>
              </div>
            </div>
          </section>
          )}

          {/* INTENTS — solo para custom */}
          {draft.is_custom && (
            <section className="space-y-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
                Se activa para estos intents
              </h3>
              <p className="text-xs text-gray-500">
                Marca cuándo el router agéntico debe preferir este worker sobre el builtin.
                Si no marcas ninguno, solo se invoca desde un nodo de Workflow.
              </p>
              <div className="space-y-1.5">
                {INTENT_OPTIONS.map((opt) => {
                  const checked = (draft.intents ?? []).includes(opt.value);
                  return (
                    <label key={opt.value} className="flex items-start gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => toggleIntent(opt.value, e.target.checked)}
                        className="w-4 h-4 mt-0.5 rounded accent-purple-600"
                      />
                      <span className="text-sm">
                        <span className="font-medium">{opt.label}</span>
                        <span className="text-gray-500 ml-2">{opt.description}</span>
                      </span>
                    </label>
                  );
                })}
              </div>
            </section>
          )}

          {/* BODY */}
          <section className="space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              Cuerpo (Tools)
            </h3>
            {(Object.keys(draft.tools) as Array<keyof Agent["tools"]>).map((tool) => (
              <label key={tool} className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={draft.tools[tool]}
                  onChange={(e) => updateTool(tool, e.target.checked)}
                  className="w-4 h-4 rounded accent-blue-600"
                />
                <span className="text-sm">{TOOL_LABELS[tool]}</span>
              </label>
            ))}

            {draft.tools.trigger_flow && (
              <div className="mt-3 rounded-md border border-blue-200 bg-blue-50/50 p-3 space-y-2">
                <p className="text-sm font-medium text-blue-900">Flujos que este agente puede disparar</p>
                <p className="text-xs text-blue-800">
                  Marca los workflows manuales que el agente podrá iniciar. Si no marcas ninguno, el
                  agente verá todos los workflows manuales del bot.
                </p>
                {manualWorkflows.length === 0 ? (
                  <p className="text-xs italic text-blue-700">
                    No hay workflows manuales configurados en este bot.
                  </p>
                ) : (
                  <div className="space-y-1">
                    {manualWorkflows.map((wf) => {
                      const checked = (draft.trigger_flows ?? []).includes(wf.id);
                      return (
                        <label key={wf.id} className="flex items-center gap-2 cursor-pointer text-sm">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) => toggleTriggerFlow(wf.id, e.target.checked)}
                            className="w-4 h-4 rounded accent-blue-600"
                          />
                          <span>{wf.name}</span>
                          {!wf.enabled && <span className="text-xs text-gray-500">(deshabilitado)</span>}
                        </label>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </section>
        </div>

        <div className="flex justify-end gap-2 pt-4 border-t mt-6">
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={() => onSave(draft)}>Guardar cambios</Button>
        </div>
      </CardContent>
    </Card>
  );
}
