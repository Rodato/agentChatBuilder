"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Plus, Pencil, Trash2 } from "lucide-react";
import {
  workflowApi,
  WorkflowSummary,
  TriggerType,
  IntentKey,
  INTENT_LABELS,
} from "@/lib/workflowApi";

const TRIGGER_LABELS: Record<TriggerType, string> = {
  on_start: "Al inicio",
  on_intent: "Por intención",
  manual: "Manual (agente)",
};

const TRIGGER_COLORS: Record<TriggerType, string> = {
  on_start: "bg-emerald-100 text-emerald-800",
  on_intent: "bg-blue-100 text-blue-800",
  manual: "bg-gray-100 text-gray-800",
};

interface Props {
  botId: string;
  onSelect: (workflowId: string) => void;
}

export function WorkflowList({ botId, onSelect }: Props) {
  const [items, setItems] = useState<WorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await workflowApi.list(botId);
      setItems(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error cargando workflows");
    } finally {
      setLoading(false);
    }
  }, [botId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleToggle = async (wf: WorkflowSummary, enabled: boolean) => {
    try {
      await workflowApi.toggle(botId, wf.id, enabled);
      setItems((prev) => prev.map((w) => (w.id === wf.id ? { ...w, enabled } : w)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cambiar el estado.");
    }
  };

  const handleDelete = async (wf: WorkflowSummary) => {
    if (!confirm(`¿Eliminar el workflow "${wf.name}"? Esta acción no se puede deshacer.`)) return;
    try {
      await workflowApi.delete(botId, wf.id);
      setItems((prev) => prev.filter((w) => w.id !== wf.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo eliminar.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex justify-between items-start">
          <div>
            <CardTitle>Workflows</CardTitle>
            <CardDescription>
              Diseña los flujos deterministas que componen este Agente: onboarding, captura de datos,
              cobranza, agendamiento, etc. Cada workflow tiene un disparador (al iniciar, por intención
              detectada, o manual desde un worker) y se reusa en el Mapa para ensamblar el comportamiento
              del bot.
            </CardDescription>
          </div>
          <Button onClick={() => setCreateOpen(true)} size="sm">
            <Plus className="w-4 h-4 mr-1" /> Nuevo workflow
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {error && (
          <div className="mb-4 p-3 rounded-md bg-red-50 text-sm text-red-700 border border-red-200">
            {error}
          </div>
        )}
        {loading ? (
          <p className="text-sm text-gray-500">Cargando…</p>
        ) : items.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <p>Aún no hay workflows.</p>
            <p className="text-sm">Crea uno para empezar — por ejemplo un onboarding al iniciar.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((wf) => (
              <div
                key={wf.id}
                className="flex items-center justify-between p-4 border rounded-lg hover:bg-gray-50 transition"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h4 className="font-medium">{wf.name}</h4>
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${TRIGGER_COLORS[wf.trigger_type]}`}
                    >
                      {TRIGGER_LABELS[wf.trigger_type]}
                      {wf.trigger_type === "on_intent" && wf.trigger_value && (
                        <>: {INTENT_LABELS[wf.trigger_value as IntentKey] ?? wf.trigger_value}</>
                      )}
                    </span>
                    {!wf.enabled && <Badge variant="secondary" className="text-xs">Deshabilitado</Badge>}
                  </div>
                  <p className="text-xs text-gray-500 mt-1">v{wf.version}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Switch
                    checked={wf.enabled}
                    onCheckedChange={(v) => handleToggle(wf, v)}
                    aria-label="Habilitar"
                  />
                  <Button variant="ghost" size="sm" onClick={() => onSelect(wf.id)}>
                    <Pencil className="w-4 h-4" />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => handleDelete(wf)}>
                    <Trash2 className="w-4 h-4 text-red-600" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>

      <CreateWorkflowDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        botId={botId}
        onCreated={(id) => {
          setCreateOpen(false);
          refresh();
          onSelect(id);
        }}
      />
    </Card>
  );
}

// ── Dialog ───────────────────────────────────────────────────────────────────

interface CreateDialogProps {
  open: boolean;
  onClose: () => void;
  botId: string;
  onCreated: (workflowId: string) => void;
}

function CreateWorkflowDialog({ open, onClose, botId, onCreated }: CreateDialogProps) {
  const [name, setName] = useState("");
  const [triggerType, setTriggerType] = useState<TriggerType>("manual");
  const [triggerValue, setTriggerValue] = useState<IntentKey>("FACTUAL");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName("");
      setTriggerType("manual");
      setTriggerValue("FACTUAL");
      setError(null);
    }
  }, [open]);

  const handleCreate = async () => {
    if (!name.trim()) {
      setError("El nombre es obligatorio.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const row = await workflowApi.create(botId, {
        name: name.trim(),
        trigger_type: triggerType,
        trigger_value: triggerType === "on_intent" ? triggerValue : null,
        enabled: true,
      });
      onCreated(row.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error creando workflow.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo workflow</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <Label>Nombre</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ej: Onboarding, Agendamiento, Checkout"
              autoFocus
            />
          </div>
          <div className="space-y-1">
            <Label>Disparador</Label>
            <select
              value={triggerType}
              onChange={(e) => setTriggerType(e.target.value as TriggerType)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="on_start">Al inicio de la conversación (onboarding)</option>
              <option value="on_intent">Cuando se detecta una intención</option>
              <option value="manual">Manual — disparado por un agente</option>
            </select>
            <p className="text-xs text-gray-500">
              {triggerType === "on_start" && "Se ejecuta automáticamente al abrir el chat. Solo uno por bot."}
              {triggerType === "on_intent" && "Se ejecuta cuando el router clasifica el mensaje con esta intención."}
              {triggerType === "manual" && "Un agente puede iniciarlo emitiendo una señal en su respuesta."}
            </p>
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
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancelar
          </Button>
          <Button onClick={handleCreate} disabled={submitting}>
            {submitting ? "Creando…" : "Crear y editar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
