"use client";

import { useState, useEffect } from "react";
import { Agent } from "./AgentCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";

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

function temperatureLabel(t: number): string {
  if (t <= 0.3) return "Conservador";
  if (t >= 0.7) return "Creativo";
  return "Balanceado";
}

interface AgentEditPanelProps {
  agent: Agent | null;
  open: boolean;
  onSave: (updated: Agent) => void;
  onClose: () => void;
}

export function AgentEditPanel({ agent, open, onSave, onClose }: AgentEditPanelProps) {
  const [draft, setDraft] = useState<Agent | null>(null);

  useEffect(() => {
    if (agent) setDraft({ ...agent, tools: { ...agent.tools } });
  }, [agent]);

  if (!draft) return null;

  const updateField = <K extends keyof Agent>(key: K, value: Agent[K]) =>
    setDraft((prev) => prev ? { ...prev, [key]: value } : prev);

  const updateTool = (tool: keyof Agent["tools"], value: boolean) =>
    setDraft((prev) =>
      prev ? { ...prev, tools: { ...prev.tools, [tool]: value } } : prev
    );

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Editar Agente</DialogTitle>
        </DialogHeader>

        <div className="space-y-6 py-2">
          {/* BRAIN */}
          <section className="space-y-4">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              Cerebro (Brain)
            </h3>

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
                placeholder="Describe brevemente el objetivo de este agente"
              />
            </div>

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
          </section>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={() => onSave(draft)}>Guardar cambios</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
