"use client";

import { useState, useEffect, useRef, use } from "react";
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
import { botsApi, chatApi, Bot } from "@/lib/api";

const MOCK_AGENTS: Agent[] = [
  {
    id: "greeting",
    name: "Saludo",
    objective: "Manejar saludos y mensajes de bienvenida",
    system_prompt: "Eres un asistente amable. Saluda al usuario calurosamente y pregunta cómo puedes ayudarle.",
    model: "google/gemini-2.5-flash-lite",
    temperature: 0.7,
    tools: { rag_search: false, user_memory: false, trigger_flow: false, human_handoff: false, external_api: false },
    enabled: true,
    is_custom: false,
  },
  {
    id: "factual",
    name: "Informativo (RAG)",
    objective: "Responder preguntas desde tus documentos",
    system_prompt: "Eres un asistente bien informado. Responde preguntas con precisión basándote en el contexto proporcionado.",
    model: "google/gemini-2.5-flash",
    temperature: 0.3,
    tools: { rag_search: true, user_memory: false, trigger_flow: false, human_handoff: false, external_api: false },
    enabled: true,
    is_custom: false,
  },
  {
    id: "plan",
    name: "Planificación",
    objective: "Ayudar a los usuarios a planificar y organizar",
    system_prompt: "Eres un asistente de planificación estratégica. Ayuda a crear planes detallados y accionables.",
    model: "anthropic/claude-sonnet-4.6",
    temperature: 0.5,
    tools: { rag_search: true, user_memory: false, trigger_flow: false, human_handoff: false, external_api: false },
    enabled: false,
    is_custom: false,
  },
  {
    id: "ideate",
    name: "Lluvia de Ideas",
    objective: "Generar ideas creativas",
    system_prompt: "Eres un compañero creativo de brainstorming. Genera ideas diversas e innovadoras.",
    model: "mistralai/mistral-small-creative",
    temperature: 0.9,
    tools: { rag_search: false, user_memory: false, trigger_flow: false, human_handoff: false, external_api: false },
    enabled: false,
    is_custom: false,
  },
  {
    id: "sensitive",
    name: "Temas Sensibles",
    objective: "Manejar temas delicados con cuidado",
    system_prompt: "Eres un asistente compasivo y cuidadoso. Maneja temas sensibles con empatía y respeto.",
    model: "anthropic/claude-sonnet-4.6",
    temperature: 0.3,
    tools: { rag_search: false, user_memory: false, trigger_flow: false, human_handoff: true, external_api: false },
    enabled: true,
    is_custom: false,
  },
  {
    id: "fallback",
    name: "Fallback",
    objective: "Manejar consultas poco claras o ambiguas",
    system_prompt: "Eres un asistente útil. Cuando una consulta no está clara, haz preguntas de aclaración.",
    model: "google/gemini-2.5-flash-lite",
    temperature: 0.5,
    tools: { rag_search: false, user_memory: false, trigger_flow: false, human_handoff: false, external_api: false },
    enabled: true,
    is_custom: false,
  },
];

export default function BotPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [bot, setBot] = useState<Bot | null>(null);
  const [botLoading, setBotLoading] = useState(true);
  const [documents] = useState<Array<{ id: string; name: string; status: string; chunks: number }>>([]);
  const [agents, setAgents] = useState<Agent[]>(MOCK_AGENTS);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [editPanelOpen, setEditPanelOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<Array<{ role: string; content: string; meta?: string }>>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    botsApi
      .get(id)
      .then(setBot)
      .catch(() => setBot(null))
      .finally(() => setBotLoading(false));
  }, [id]);

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
      const res = await chatApi.send(text, id);
      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.response,
          meta: `${res.agent_used} · ${res.intent} · ${res.processing_time_ms}ms`,
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

  const handleToggleAgent = (id: string) => {
    setAgents((prev) =>
      prev.map((a) => (a.id === id ? { ...a, enabled: !a.enabled } : a))
    );
  };

  const handleEditAgent = (agent: Agent) => {
    setEditingAgent(agent);
    setEditPanelOpen(true);
  };

  const handleSaveAgent = (updated: Agent) => {
    setAgents((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
    setEditPanelOpen(false);
    setEditingAgent(null);
  };

  const handleAddAgent = () => {
    const newAgent: Agent = {
      id: `custom-${Date.now()}`,
      name: "Nuevo Agente",
      objective: "",
      system_prompt: "",
      model: "google/gemini-2.5-flash-lite",
      temperature: 0.7,
      tools: { rag_search: false, user_memory: false, trigger_flow: false, human_handoff: false, external_api: false },
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
        <p className="text-gray-500">Cargando bot...</p>
      </div>
    );
  }

  if (!bot) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center gap-4">
        <p className="text-gray-500">Bot no encontrado.</p>
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
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="container mx-auto px-4 py-8">
        <Tabs defaultValue="settings" className="space-y-6">
          <TabsList>
            <TabsTrigger value="settings">Configuración</TabsTrigger>
            <TabsTrigger value="agents">Agentes</TabsTrigger>
            <TabsTrigger value="documents">Documentos</TabsTrigger>
            <TabsTrigger value="test">Chat de Prueba</TabsTrigger>
          </TabsList>

          {/* Settings Tab */}
          <TabsContent value="settings">
            <Card>
              <CardHeader>
                <CardTitle>Configuración del Bot</CardTitle>
                <CardDescription>Configura la información básica y personalidad de tu bot</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-2">
                  <Label htmlFor="name">Nombre del bot</Label>
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
                    placeholder="Describe cómo debe comportarse el bot..."
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
                    <Label>Estado del bot</Label>
                    <p className="text-sm text-gray-500">Activar o desactivar este bot</p>
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

          {/* Agents Tab */}
          <TabsContent value="agents">
            <Card>
              <CardHeader>
                <div className="flex justify-between items-start">
                  <div>
                    <CardTitle>Agentes</CardTitle>
                    <CardDescription>Configura, activa y crea agentes especializados</CardDescription>
                  </div>
                  <Button onClick={handleAddAgent} size="sm">
                    <Plus className="w-4 h-4 mr-1" /> Agregar Agente
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {agents.map((agent) => (
                    <AgentCard
                      key={agent.id}
                      agent={agent}
                      onToggle={handleToggleAgent}
                      onEdit={handleEditAgent}
                    />
                  ))}
                </div>
              </CardContent>
            </Card>
            <AgentEditPanel
              agent={editingAgent}
              open={editPanelOpen}
              onSave={handleSaveAgent}
              onClose={() => { setEditPanelOpen(false); setEditingAgent(null); }}
            />
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
                  <Button>+ Subir Documento</Button>
                </div>
              </CardHeader>
              <CardContent>
                {documents.length === 0 ? (
                  <div className="text-center py-12 text-gray-500">
                    <p>Aún no hay documentos subidos.</p>
                    <p className="text-sm">Sube archivos PDF, DOCX o TXT para construir tu base de conocimiento.</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {documents.map((doc) => (
                      <div
                        key={doc.id}
                        className="flex items-center justify-between p-4 border rounded-lg"
                      >
                        <div className="flex items-center gap-3">
                          <div className="text-2xl">📄</div>
                          <div>
                            <h4 className="font-medium">{doc.name}</h4>
                            <p className="text-sm text-gray-500">
                              {doc.status === "ready"
                                ? `${doc.chunks} fragmentos indexados`
                                : "Procesando..."}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge
                            variant={doc.status === "ready" ? "default" : "secondary"}
                          >
                            {doc.status}
                          </Badge>
                          <Button variant="ghost" size="sm">
                            Eliminar
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Test Chat Tab */}
          <TabsContent value="test">
            <Card className="h-[600px] flex flex-col">
              <CardHeader>
                <CardTitle>Probar tu Bot</CardTitle>
                <CardDescription>Envía mensajes para ver cómo responde tu bot</CardDescription>
              </CardHeader>
              <CardContent className="flex-1 flex flex-col">
                {/* Messages */}
                <div className="flex-1 overflow-y-auto space-y-4 mb-4 p-4 bg-gray-100 rounded-lg">
                  {chatMessages.length === 0 ? (
                    <div className="text-center text-gray-500 py-8">
                      <p>Aún no hay mensajes.</p>
                      <p className="text-sm">Inicia una conversación para probar tu bot.</p>
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
