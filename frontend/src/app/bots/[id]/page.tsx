"use client";

import { useState, useEffect, useRef, use, useCallback } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Plus } from "lucide-react";
import { AgentCard, Agent } from "@/components/AgentCard";
import { AgentEditPanel } from "@/components/AgentEditPanel";
import { BotMapView } from "@/components/BotMap";
import { DocumentMetadataDialog } from "@/components/DocumentMetadataDialog";
import { WorkflowEditor } from "@/components/workflow/WorkflowEditor";
import { WorkflowList } from "@/components/workflow/WorkflowList";
import {
  botsApi,
  chatApi,
  documentsApi,
  agentsApi,
  AgentRow,
  AgentPatch,
  AgentDeleteBlockedError,
  AgentDeleteBlocker,
  Bot,
  Document,
  IntentKey,
} from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const DEFAULT_TOOLS = {
  rag_search: false,
  user_memory: false,
  trigger_flow: false,
  human_handoff: false,
  external_api: false,
};

function rowToAgent(row: AgentRow): Agent {
  return {
    id: row.agent_id,
    name: row.name,
    objective: row.objective,
    system_prompt: row.system_prompt,
    model: row.model,
    temperature: row.temperature,
    tools: { ...DEFAULT_TOOLS, ...(row.tools || {}) },
    enabled: row.enabled,
    is_custom: row.is_custom,
    trigger_flows: row.metadata?.trigger_flows ?? [],
    intents: (row.intents ?? []) as IntentKey[],
  };
}

function conversationKey(botId: string) {
  return `acb.conversation_id.${botId}`;
}

function getOrCreateConversationId(botId: string): string {
  if (typeof window === "undefined") return "";
  const k = conversationKey(botId);
  let id = window.localStorage.getItem(k);
  if (!id) {
    id = crypto.randomUUID();
    window.localStorage.setItem(k, id);
  }
  return id;
}

export default function BotPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [bot, setBot] = useState<Bot | null>(null);
  const [botLoading, setBotLoading] = useState(true);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [uploadingDoc, setUploadingDoc] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [editPanelOpen, setEditPanelOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<Array<{ role: string; content: string; meta?: string }>>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);
  const [editingDoc, setEditingDoc] = useState<Document | null>(null);
  const [deleteAgentTarget, setDeleteAgentTarget] = useState<Agent | null>(null);
  const [deleteAgentBlockers, setDeleteAgentBlockers] = useState<AgentDeleteBlocker[] | null>(null);
  const [deleteAgentError, setDeleteAgentError] = useState<string | null>(null);
  const [deletingAgent, setDeletingAgent] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    botsApi
      .get(id)
      .then(setBot)
      .catch(() => setBot(null))
      .finally(() => setBotLoading(false));
    documentsApi.list(id).then(setDocuments).catch(() => {});
    agentsApi
      .list(id)
      .then((rows) => setAgents(rows.map(rowToAgent)))
      .catch(() => setAgents([]))
      .finally(() => setAgentsLoading(false));
    const cid = getOrCreateConversationId(id);
    setConversationId(cid);
  }, [id]);

  // Kick off the conversation — runs on_start workflow if configured, else welcome_message.
  const startedRef = useRef(false);
  useEffect(() => {
    if (!conversationId || startedRef.current || chatMessages.length > 0) return;
    startedRef.current = true;
    chatApi
      .start(id, conversationId)
      .then((res) => {
        const metaParts = [res.mode ?? "agentic", res.agent_used, `${res.processing_time_ms ?? 0}ms`].filter(Boolean);
        setChatMessages([{ role: "assistant", content: res.response, meta: metaParts.join(" · ") }]);
      })
      .catch(() => {
        // Ignore — user can still type.
      });
  }, [conversationId, id, chatMessages.length]);

  useEffect(() => {
    const hasProcessing = documents.some((d) => d.status === "processing");
    if (!hasProcessing) return;
    const interval = setInterval(() => {
      documentsApi.list(id).then(setDocuments).catch(() => {});
    }, 3000);
    return () => clearInterval(interval);
  }, [documents, id]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  const handleSendMessage = async () => {
    if (!chatInput.trim() || chatLoading) return;
    const text = chatInput;
    setChatInput("");
    setChatMessages((prev) => [...prev, { role: "user", content: text }]);
    setChatLoading(true);
    try {
      const res = await chatApi.send(id, text, conversationId);
      const metaParts = [
        res.mode ?? "agentic",
        res.agent_used,
        res.intent ?? undefined,
        `${res.processing_time_ms}ms`,
      ].filter(Boolean);
      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.response,
          meta: metaParts.join(" · "),
        },
      ]);
    } catch (e: unknown) {
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${e instanceof Error ? e.message : "sin respuesta del servidor"}` },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleResetConversation = () => {
    window.localStorage.removeItem(conversationKey(id));
    startedRef.current = false;
    setConversationId(getOrCreateConversationId(id));
    setChatMessages([]);
  };

  const handleSaveSettings = async () => {
    if (!bot) return;
    setSaving(true);
    try {
      const updated = await botsApi.update(bot.id, {
        name: bot.name,
        description: bot.description ?? undefined,
        personality: bot.personality ?? undefined,
        welcome_message: bot.welcome_message,
        is_active: bot.is_active,
      });
      setBot(updated);
    } finally {
      setSaving(false);
    }
  };

  const persistAgent = useCallback(
    async (agentId: string, patch: AgentPatch) => {
      try {
        await agentsApi.update(id, agentId, patch);
      } catch (e) {
        console.error("persistAgent", e);
      }
    },
    [id]
  );

  const handleToggleAgent = useCallback(
    (agentId: string) => {
      setAgents((prev) => {
        const next = prev.map((a) => (a.id === agentId ? { ...a, enabled: !a.enabled } : a));
        const updated = next.find((a) => a.id === agentId);
        if (updated) persistAgent(agentId, { enabled: updated.enabled });
        return next;
      });
    },
    [persistAgent]
  );

  const handleEditAgent = useCallback((agent: Agent) => {
    setEditingAgent(agent);
    setEditPanelOpen(true);
  }, []);

  const handleSaveAgent = async (updated: Agent) => {
    const isNew = !agents.some((a) => a.id === updated.id);
    setEditPanelOpen(false);
    setEditingAgent(null);

    if (isNew && updated.is_custom) {
      // Persist as a new custom agent (POST). Replace the temporary local row
      // with whatever the server returns (canonical agent_id, defaults, etc.).
      try {
        const created = await agentsApi.create(id, {
          agent_id: updated.id,
          name: updated.name,
          objective: updated.objective,
          system_prompt: updated.system_prompt,
          model: updated.model,
          temperature: updated.temperature,
          tools: updated.tools,
          enabled: updated.enabled,
          intents: updated.intents,
          metadata: { trigger_flows: updated.trigger_flows ?? [] },
        });
        setAgents((prev) => [...prev, rowToAgent(created)]);
      } catch (e) {
        console.error("create custom agent", e);
      }
      return;
    }

    setAgents((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
    await persistAgent(updated.id, {
      name: updated.name,
      objective: updated.objective,
      system_prompt: updated.system_prompt,
      model: updated.model,
      temperature: updated.temperature,
      tools: updated.tools,
      enabled: updated.enabled,
      intents: updated.is_custom ? updated.intents : undefined,
      metadata: { trigger_flows: updated.trigger_flows ?? [] },
    });
  };

  const handleDeleteAgent = useCallback((agent: Agent) => {
    setDeleteAgentTarget(agent);
    setDeleteAgentBlockers(null);
    setDeleteAgentError(null);
  }, []);

  const handleConfirmDeleteAgent = async () => {
    if (!deleteAgentTarget) return;
    setDeletingAgent(true);
    setDeleteAgentError(null);
    try {
      await agentsApi.delete(id, deleteAgentTarget.id);
      setAgents((prev) => prev.filter((a) => a.id !== deleteAgentTarget.id));
      setDeleteAgentTarget(null);
    } catch (e) {
      if (e instanceof AgentDeleteBlockedError) {
        setDeleteAgentBlockers(e.blockers);
      } else {
        setDeleteAgentError(e instanceof Error ? e.message : "No se pudo eliminar.");
      }
    } finally {
      setDeletingAgent(false);
    }
  };

  const handleUploadClick = () => fileInputRef.current?.click();

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setUploadError(null);
    setUploadingDoc(true);
    try {
      const doc = await documentsApi.upload(id, file);
      setDocuments((prev) => [doc, ...prev]);
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : "sin respuesta del servidor");
    } finally {
      setUploadingDoc(false);
    }
  };

  const handleDeleteDoc = async (docId: string) => {
    await documentsApi.delete(id, docId).catch(() => {});
    setDocuments((prev) => prev.filter((d) => d.id !== docId));
  };

  const handleAddAgent = () => {
    const newAgent: Agent = {
      id: `custom-${Date.now()}`,
      name: "Nuevo Agente",
      objective: "",
      system_prompt: "",
      model: "google/gemini-2.5-flash-lite",
      temperature: 0.7,
      tools: { ...DEFAULT_TOOLS },
      enabled: true,
      is_custom: true,
    };
    setAgents((prev) => [...prev, newAgent]);
    setEditingAgent(newAgent);
    setEditPanelOpen(true);
  };

  if (botLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-500">Cargando agente...</p>
      </div>
    );
  }

  if (!bot) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center gap-4">
        <p className="text-gray-500">Agente no encontrado.</p>
        <Link href="/dashboard"><Button>Volver al Dashboard</Button></Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center gap-4">
            <Link href="/dashboard" className="text-gray-600 hover:text-gray-900">
              ← Volver
            </Link>
            <h1 className="text-xl font-bold">{bot.name}</h1>
            <Badge variant={bot.is_active ? "default" : "secondary"}>
              {bot.is_active ? "Activo" : "Inactivo"}
            </Badge>
            {bot.workflow_mode === "workflow" && (
              <Badge variant="outline">Modo workflow</Badge>
            )}
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="container mx-auto px-4 py-8">
        <Tabs defaultValue="settings" className="space-y-6">
          <TabsList>
            <TabsTrigger value="settings">Configuración</TabsTrigger>
            <TabsTrigger value="map">Mapa</TabsTrigger>
            <TabsTrigger value="agents">Especialistas</TabsTrigger>
            <TabsTrigger value="workflow">Workflow</TabsTrigger>
            <TabsTrigger value="documents">Documentos</TabsTrigger>
            <TabsTrigger value="test">Chat de Prueba</TabsTrigger>
          </TabsList>

          {/* Settings Tab */}
          <TabsContent value="settings">
            <Card>
              <CardHeader>
                <CardTitle>Configuración del Agente</CardTitle>
                <CardDescription>Configura la información básica y personalidad de tu Agente de IA</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-2">
                  <Label htmlFor="name">Nombre del Agente</Label>
                  <Input
                    id="name"
                    value={bot.name}
                    onChange={(e) => setBot({ ...bot, name: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="description">Descripción</Label>
                  <Input
                    id="description"
                    value={bot.description ?? ""}
                    onChange={(e) => setBot({ ...bot, description: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="personality">Personalidad / System Prompt</Label>
                  <Textarea
                    id="personality"
                    rows={4}
                    value={bot.personality ?? ""}
                    onChange={(e) => setBot({ ...bot, personality: e.target.value })}
                    placeholder="Describe cómo debe comportarse el Agente..."
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="welcome">Mensaje de Bienvenida</Label>
                  <Textarea
                    id="welcome"
                    rows={2}
                    value={bot.welcome_message}
                    onChange={(e) => setBot({ ...bot, welcome_message: e.target.value })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <Label>Estado del Agente</Label>
                    <p className="text-sm text-gray-500">Activar o desactivar este Agente</p>
                  </div>
                  <Switch
                    checked={bot.is_active}
                    onCheckedChange={(checked) => setBot({ ...bot, is_active: checked })}
                  />
                </div>
                <Button onClick={handleSaveSettings} disabled={saving}>
                  {saving ? "Guardando..." : "Guardar cambios"}
                </Button>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Bot Map Tab */}
          <TabsContent value="map">
            <BotMapView botId={id} />
          </TabsContent>

          {/* Agents Tab */}
          <TabsContent value="agents">
            <Card>
              <CardHeader>
                <div className="flex justify-between items-start">
                  <div>
                    <CardTitle>Especialistas</CardTitle>
                    <CardDescription>
                      Configura los sub-agentes especializados que componen este Agente de IA
                    </CardDescription>
                  </div>
                  <Button onClick={handleAddAgent} size="sm">
                    <Plus className="w-4 h-4 mr-1" /> Agregar Especialista
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {agentsLoading ? (
                  <p className="text-sm text-gray-500">Cargando especialistas...</p>
                ) : (
                  <div className="space-y-3">
                    {agents.map((agent) => (
                      <AgentCard
                        key={agent.id}
                        agent={agent}
                        onToggle={handleToggleAgent}
                        onEdit={handleEditAgent}
                        onDelete={handleDeleteAgent}
                      />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
            <AgentEditPanel
              agent={editingAgent}
              open={editPanelOpen}
              botId={id}
              onSave={handleSaveAgent}
              onClose={() => { setEditPanelOpen(false); setEditingAgent(null); }}
            />
            <Dialog
              open={!!deleteAgentTarget}
              onOpenChange={(o) => !o && !deletingAgent && setDeleteAgentTarget(null)}
            >
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>
                    {deleteAgentBlockers ? "No se puede eliminar todavía" : "Eliminar especialista"}
                  </DialogTitle>
                  <DialogDescription>
                    {deleteAgentBlockers ? (
                      <>
                        <span className="font-medium text-gray-900">{deleteAgentTarget?.name}</span> está siendo
                        usado por uno o más workflows. Edita esos workflows primero (cambia el nodo `agent` por
                        otro especialista o elimínalo) y vuelve a intentarlo.
                      </>
                    ) : (
                      <>
                        ¿Seguro que quieres eliminar <span className="font-medium text-gray-900">{deleteAgentTarget?.name}</span>?
                        Esta acción no se puede deshacer.
                      </>
                    )}
                  </DialogDescription>
                </DialogHeader>

                {deleteAgentBlockers && (
                  <div className="rounded-md border bg-amber-50 border-amber-200 p-3 space-y-1">
                    <p className="text-xs font-medium text-amber-900">Workflows que lo referencian:</p>
                    <ul className="text-sm text-amber-900 list-disc pl-5">
                      {deleteAgentBlockers.map((b) => (
                        <li key={b.workflow_id}>{b.workflow_name || b.workflow_id}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {deleteAgentError && (
                  <p className="text-sm text-red-600">{deleteAgentError}</p>
                )}

                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => setDeleteAgentTarget(null)}
                    disabled={deletingAgent}
                  >
                    {deleteAgentBlockers ? "Cerrar" : "Cancelar"}
                  </Button>
                  {!deleteAgentBlockers && (
                    <Button
                      variant="destructive"
                      onClick={handleConfirmDeleteAgent}
                      disabled={deletingAgent}
                    >
                      {deletingAgent ? "Eliminando…" : "Eliminar"}
                    </Button>
                  )}
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </TabsContent>

          {/* Workflow Tab */}
          <TabsContent value="workflow">
            {selectedWorkflowId ? (
              <WorkflowEditor
                botId={id}
                workflowId={selectedWorkflowId}
                onBack={() => setSelectedWorkflowId(null)}
              />
            ) : (
              <WorkflowList botId={id} onSelect={setSelectedWorkflowId} />
            )}
          </TabsContent>

          {/* Documents Tab */}
          <TabsContent value="documents">
            <Card>
              <CardHeader>
                <div className="flex justify-between items-start">
                  <div>
                    <CardTitle>Base de Conocimiento</CardTitle>
                    <CardDescription>Sube documentos para respuestas con RAG</CardDescription>
                  </div>
                  <Button onClick={handleUploadClick} disabled={uploadingDoc}>
                    {uploadingDoc ? "Subiendo..." : "+ Subir Documento"}
                  </Button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.txt,.docx,.md"
                    className="hidden"
                    onChange={handleFileChange}
                  />
                </div>
              </CardHeader>
              <CardContent>
                {uploadError && (
                  <div className="mb-4 p-3 rounded-md bg-red-50 text-sm text-red-700 border border-red-200">
                    Error al subir: {uploadError}
                  </div>
                )}
                {documents.length === 0 ? (
                  <div className="text-center py-12 text-gray-500">
                    <p>Aún no hay documentos subidos.</p>
                    <p className="text-sm">Sube archivos PDF, DOCX, TXT o MD para construir tu base de conocimiento.</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {documents.map((doc) => (
                      <div
                        key={doc.id}
                        className="p-4 border rounded-lg space-y-2"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="text-2xl">📄</div>
                            <div className="min-w-0">
                              <h4 className="font-medium truncate">{doc.name}</h4>
                              <p className="text-sm text-gray-500">
                                {doc.status === "ready"
                                  ? `Listo · ${(doc.file_size / 1024).toFixed(1)} KB`
                                  : `Procesando · ${(doc.file_size / 1024).toFixed(1)} KB`}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <Badge
                              variant={
                                doc.status === "ready"
                                  ? "default"
                                  : doc.status === "error"
                                  ? "destructive"
                                  : "secondary"
                              }
                            >
                              {doc.status === "ready" ? "Listo" : doc.status === "error" ? "Error" : "Procesando..."}
                            </Badge>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setEditingDoc(doc)}
                              disabled={doc.status === "processing"}
                            >
                              Metadata
                            </Button>
                            <Button variant="ghost" size="sm" onClick={() => handleDeleteDoc(doc.id)}>
                              Eliminar
                            </Button>
                          </div>
                        </div>
                        {(doc.summary || (doc.keywords && doc.keywords.length > 0)) && (
                          <div className="pl-11 space-y-1.5">
                            {doc.summary && (
                              <p className="text-sm text-gray-600 line-clamp-2">{doc.summary}</p>
                            )}
                            {doc.keywords && doc.keywords.length > 0 && (
                              <div className="flex flex-wrap gap-1">
                                {doc.keywords.map((kw) => (
                                  <Badge key={kw} variant="secondary" className="text-xs">
                                    {kw}
                                  </Badge>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
            <DocumentMetadataDialog
              open={!!editingDoc}
              onClose={() => setEditingDoc(null)}
              botId={id}
              doc={editingDoc}
              onSaved={(updated) =>
                setDocuments((prev) => prev.map((d) => (d.id === updated.id ? updated : d)))
              }
            />
          </TabsContent>

          {/* Test Chat Tab */}
          <TabsContent value="test">
            <Card className="h-[600px] flex flex-col">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle>Probar tu Agente</CardTitle>
                    <CardDescription>Envía mensajes para ver cómo responde tu Agente de IA</CardDescription>
                  </div>
                  <Button variant="ghost" size="sm" onClick={handleResetConversation}>
                    Reiniciar conversación
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="flex-1 flex flex-col">
                {/* Messages */}
                <div className="flex-1 overflow-y-auto space-y-4 mb-4 p-4 bg-gray-100 rounded-lg">
                  {chatMessages.length === 0 ? (
                    <div className="text-center text-gray-500 py-8">
                      <p>Aún no hay mensajes.</p>
                      <p className="text-sm">Inicia una conversación para probar tu Agente.</p>
                    </div>
                  ) : (
                    chatMessages.map((msg, i) => (
                      <div
                        key={i}
                        className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                      >
                        <div className={`max-w-[70%] space-y-1`}>
                          <div
                            className={`p-3 rounded-lg ${
                              msg.role === "user"
                                ? "bg-blue-600 text-white"
                                : "bg-white border"
                            }`}
                          >
                            {msg.content}
                          </div>
                          {msg.meta && (
                            <p className="text-xs text-gray-400 px-1">{msg.meta}</p>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                  {chatLoading && (
                    <div className="flex justify-start">
                      <div className="bg-white border p-3 rounded-lg text-gray-400 text-sm">
                        Pensando...
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>

                {/* Input */}
                <div className="flex gap-2">
                  <Input
                    placeholder="Escribe un mensaje..."
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
                  />
                  <Button onClick={handleSendMessage}>Enviar</Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
