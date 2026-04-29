"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";
import { analyticsApi, BotAnalytics } from "@/lib/analyticsApi";

interface Props {
  botId: string;
}

const RANGES = [
  { value: 7, label: "7 días" },
  { value: 14, label: "14 días" },
  { value: 30, label: "30 días" },
];

export function AnalyticsView({ botId }: Props) {
  const [data, setData] = useState<BotAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState(7);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await analyticsApi.get(botId, range);
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar analytics.");
    } finally {
      setLoading(false);
    }
  }, [botId, range]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const maxDaily = useMemo(() => {
    if (!data) return 1;
    return Math.max(1, ...data.daily.map((d) => d.user + d.assistant));
  }, [data]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex justify-between items-start">
            <div>
              <CardTitle>Analytics</CardTitle>
              <CardDescription>
                Observa cómo se está comportando tu Agente en los últimos días: cuántos mensajes
                recibe, qué workers responden con más frecuencia, qué intenciones detecta el router
                y cuánto tarda en responder. Útil para detectar workers infrautilizados o cuellos
                de botella.
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <select
                value={range}
                onChange={(e) => setRange(Number(e.target.value))}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
              >
                {RANGES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
              <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
                <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} />
                Actualizar
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {error && (
            <div className="mb-4 p-3 rounded-md bg-red-50 text-sm text-red-700 border border-red-200">
              {error}
            </div>
          )}
          {!data && loading && (
            <p className="text-sm text-gray-500">Cargando…</p>
          )}
          {data && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Stat label="Mensajes totales" value={data.totals.messages.toLocaleString()} />
              <Stat label="Conversaciones" value={data.totals.conversations.toLocaleString()} />
              <Stat label="De usuarios" value={data.totals.user_messages.toLocaleString()} />
              <Stat
                label="Latencia promedio"
                value={`${data.avg_processing_ms.toLocaleString()} ms`}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {data && data.totals.messages === 0 && (
        <Card>
          <CardContent className="py-12 text-center text-sm text-gray-500">
            Aún no hay mensajes. Conversa con tu Agente en la tab Chat de prueba para empezar a ver datos aquí.
          </CardContent>
        </Card>
      )}

      {data && data.totals.messages > 0 && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Mensajes por día</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-1">
                {data.daily.map((d) => {
                  const total = d.user + d.assistant;
                  const pct = (total / maxDaily) * 100;
                  return (
                    <div key={d.date} className="flex items-center gap-2 text-xs">
                      <span className="w-20 text-gray-500 shrink-0">{d.date}</span>
                      <div className="flex-1 bg-gray-100 rounded h-5 relative overflow-hidden">
                        {total > 0 && (
                          <div
                            className="absolute left-0 top-0 bottom-0 bg-blue-200 rounded"
                            style={{ width: `${pct}%` }}
                          />
                        )}
                        {d.assistant > 0 && (
                          <div
                            className="absolute left-0 top-0 bottom-0 bg-blue-500 rounded"
                            style={{ width: `${(d.assistant / maxDaily) * 100}%` }}
                          />
                        )}
                      </div>
                      <span className="w-12 text-right text-gray-700">{total}</span>
                    </div>
                  );
                })}
              </div>
              <div className="mt-3 flex gap-4 text-xs text-gray-500">
                <span className="flex items-center gap-1">
                  <span className="inline-block w-3 h-3 rounded-sm bg-blue-500" /> Bot
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block w-3 h-3 rounded-sm bg-blue-200" /> Usuario
                </span>
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <DistributionCard
              title="Por especialista (Worker)"
              items={data.by_agent.map((a) => ({ key: a.agent, value: a.count }))}
            />
            <DistributionCard
              title="Por intención"
              items={data.by_intent.map((a) => ({ key: a.intent, value: a.count }))}
            />
            <DistributionCard
              title="Modo (agentic vs workflow)"
              items={data.by_mode.map((a) => ({ key: a.mode, value: a.count }))}
            />
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-white p-4">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
    </div>
  );
}

function DistributionCard({
  title,
  items,
}: {
  title: string;
  items: { key: string; value: number }[];
}) {
  const total = items.reduce((acc, it) => acc + it.value, 0) || 1;
  return (
    <Card>
      <CardHeader className="py-3">
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-xs text-gray-400 italic">Sin datos</p>
        ) : (
          <div className="space-y-1.5">
            {items.map((it) => {
              const pct = (it.value / total) * 100;
              return (
                <div key={it.key} className="text-xs">
                  <div className="flex justify-between mb-0.5">
                    <span className="font-medium">{it.key}</span>
                    <span className="text-gray-500">{it.value} · {pct.toFixed(0)}%</span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded overflow-hidden">
                    <div className="h-full bg-blue-500 rounded" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
