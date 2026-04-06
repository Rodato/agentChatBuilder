"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { botsApi } from "@/lib/api";

export default function NewBotPage() {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [personality, setPersonality] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const bot = await botsApi.create({ name, description, personality });
      router.push(`/bots/${bot.id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error al crear el bot");
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b">
        <div className="container mx-auto px-4 py-4">
          <Link href="/dashboard" className="text-sm text-gray-600 hover:text-gray-900">
            ← Volver al Dashboard
          </Link>
        </div>
      </header>

      {/* Main */}
      <main className="container mx-auto px-4 py-8 max-w-2xl">
        <Card>
          <CardHeader>
            <CardTitle className="text-2xl">Crear un nuevo bot</CardTitle>
            <CardDescription>
              Configura los ajustes básicos de tu bot. Podrás agregar documentos y ajustar los agentes después.
            </CardDescription>
          </CardHeader>
          <form onSubmit={handleCreate}>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="name">Nombre del bot *</Label>
                <Input
                  id="name"
                  placeholder="Bot de Soporte al Cliente"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Descripción</Label>
                <Input
                  id="description"
                  placeholder="Un asistente útil para responder preguntas de clientes"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="personality">Personalidad / System Prompt</Label>
                <Textarea
                  id="personality"
                  rows={4}
                  placeholder="Eres un asistente amable y profesional. Responde de forma concisa y clara."
                  value={personality}
                  onChange={(e) => setPersonality(e.target.value)}
                />
                <p className="text-sm text-gray-500">
                  Define cómo debe comportarse y responder tu bot.
                </p>
              </div>

              {error && (
                <p className="text-sm text-red-500">{error}</p>
              )}

              <div className="p-4 bg-blue-50 rounded-lg">
                <h4 className="font-medium text-blue-900 mb-2">¿Qué sigue?</h4>
                <ul className="text-sm text-blue-800 space-y-1">
                  <li>• Sube documentos para construir tu base de conocimiento</li>
                  <li>• Configura qué agentes están activos</li>
                  <li>• Prueba tu bot en el chat</li>
                  <li>• Conéctalo a WhatsApp, Telegram o incorpóralo a tu web</li>
                </ul>
              </div>
            </CardContent>

            <CardFooter className="flex justify-end gap-4">
              <Link href="/dashboard">
                <Button variant="outline" type="button">
                  Cancelar
                </Button>
              </Link>
              <Button type="submit" disabled={loading || !name}>
                {loading ? "Creando..." : "Crear Bot"}
              </Button>
            </CardFooter>
          </form>
        </Card>
      </main>
    </div>
  );
}
