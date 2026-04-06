"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { botsApi, Bot } from "@/lib/api";

export default function DashboardPage() {
  const [bots, setBots] = useState<Bot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    botsApi
      .list()
      .then(setBots)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b">
        <div className="container mx-auto px-4 py-4 flex justify-between items-center">
          <Link href="/dashboard">
            <h1 className="text-xl font-bold">Agent Chat Builder</h1>
          </Link>
        </div>
      </header>

      {/* Main */}
      <main className="container mx-auto px-4 py-8">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h2 className="text-3xl font-bold">Tus Bots</h2>
            <p className="text-gray-600">Crea y gestiona tus chatbots con IA</p>
          </div>
          <Link href="/bots/new">
            <Button>+ Crear Bot</Button>
          </Link>
        </div>

        {loading && (
          <div className="text-center py-16 text-gray-500">Cargando bots...</div>
        )}

        {error && (
          <div className="text-center py-16 text-red-500">
            Error al cargar bots: {error}
          </div>
        )}

        {!loading && !error && bots.length === 0 && (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16">
              <div className="text-6xl mb-4">🤖</div>
              <h3 className="text-xl font-semibold mb-2">Aún no tienes bots</h3>
              <p className="text-gray-600 mb-6 text-center max-w-md">
                Crea tu primer chatbot y empieza a conectar con tu audiencia
                mediante conversaciones inteligentes.
              </p>
              <Link href="/bots/new">
                <Button>Crear tu primer bot</Button>
              </Link>
            </CardContent>
          </Card>
        )}

        {!loading && !error && bots.length > 0 && (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {bots.map((bot) => (
              <Link key={bot.id} href={`/bots/${bot.id}`}>
                <Card className="hover:shadow-md transition-shadow cursor-pointer h-full">
                  <CardHeader>
                    <div className="flex justify-between items-start">
                      <CardTitle>{bot.name}</CardTitle>
                      <span
                        className={`px-2 py-1 text-xs rounded-full ${
                          bot.is_active
                            ? "bg-green-100 text-green-700"
                            : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {bot.is_active ? "Activo" : "Inactivo"}
                      </span>
                    </div>
                    <CardDescription>{bot.description}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="text-sm text-gray-600">
                      {bot.message_count.toLocaleString()} mensajes
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
