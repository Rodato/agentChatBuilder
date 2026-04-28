"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Trash2 } from "lucide-react";
import { botsApi, Bot } from "@/lib/api";

export default function DashboardPage() {
  const [bots, setBots] = useState<Bot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Bot | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    botsApi
      .list()
      .then(setBots)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await botsApi.delete(deleteTarget.id);
      setBots((prev) => prev.filter((b) => b.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "No se pudo eliminar.");
    } finally {
      setDeleting(false);
    }
  };

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
            <h2 className="text-3xl font-bold">Tus Agentes de IA</h2>
            <p className="text-gray-600">Crea y gestiona tus agentes de IA conversacionales</p>
          </div>
          <Link href="/bots/new">
            <Button>+ Crear Agente</Button>
          </Link>
        </div>

        {loading && (
          <div className="text-center py-16 text-gray-500">Cargando agentes...</div>
        )}

        {error && (
          <div className="text-center py-16 text-red-500">
            Error al cargar agentes: {error}
          </div>
        )}

        {!loading && !error && bots.length === 0 && (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16">
              <div className="text-6xl mb-4">🤖</div>
              <h3 className="text-xl font-semibold mb-2">Aún no tienes agentes</h3>
              <p className="text-gray-600 mb-6 text-center max-w-md">
                Crea tu primer Agente de IA y empieza a conectar con tu audiencia
                mediante conversaciones inteligentes.
              </p>
              <Link href="/bots/new">
                <Button>Crear tu primer Agente</Button>
              </Link>
            </CardContent>
          </Card>
        )}

        {!loading && !error && bots.length > 0 && (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {bots.map((bot) => (
              <Card
                key={bot.id}
                className="hover:shadow-md transition-shadow h-full relative group"
              >
                <Link href={`/bots/${bot.id}`} className="absolute inset-0 z-0" aria-label={`Abrir ${bot.name}`} />
                <CardHeader className="relative z-10 pointer-events-none">
                  <div className="flex justify-between items-start gap-2">
                    <CardTitle className="truncate">{bot.name}</CardTitle>
                    <span
                      className={`shrink-0 px-2 py-1 text-xs rounded-full ${
                        bot.is_active
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {bot.is_active ? "Activo" : "Inactivo"}
                    </span>
                  </div>
                  <CardDescription className="line-clamp-2">{bot.description}</CardDescription>
                </CardHeader>
                <CardContent className="relative z-10 flex justify-between items-center">
                  <div className="text-sm text-gray-600 pointer-events-none">
                    {bot.message_count.toLocaleString()} mensajes
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Eliminar ${bot.name}`}
                    className="text-gray-400 hover:text-red-600 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setDeleteTarget(bot);
                    }}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>

      <Dialog open={!!deleteTarget} onOpenChange={(o) => !o && !deleting && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Eliminar Agente de IA</DialogTitle>
            <DialogDescription>
              ¿Seguro que quieres eliminar <span className="font-medium text-gray-900">{deleteTarget?.name}</span>?
              Esta acción borra el agente, sus documentos, workflows y configuraciones especializadas. No se puede deshacer.
            </DialogDescription>
          </DialogHeader>
          {deleteError && (
            <p className="text-sm text-red-600">{deleteError}</p>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleting}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmDelete}
              disabled={deleting}
            >
              {deleting ? "Eliminando…" : "Eliminar definitivamente"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
