"use client";

import { useEffect, useState, KeyboardEvent } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { X } from "lucide-react";
import { documentsApi, Document } from "@/lib/api";

interface Props {
  open: boolean;
  onClose: () => void;
  botId: string;
  doc: Document | null;
  onSaved: (updated: Document) => void;
}

export function DocumentMetadataDialog({ open, onClose, botId, doc, onSaved }: Props) {
  const [summary, setSummary] = useState("");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [keywordInput, setKeywordInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open && doc) {
      setSummary(doc.summary ?? "");
      setKeywords(doc.keywords ?? []);
      setKeywordInput("");
      setError(null);
    }
  }, [open, doc]);

  const addKeyword = (raw: string) => {
    const cleaned = raw.trim().toLowerCase();
    if (!cleaned) return;
    if (keywords.includes(cleaned)) return;
    if (keywords.length >= 30) return;
    setKeywords((prev) => [...prev, cleaned.slice(0, 60)]);
    setKeywordInput("");
  };

  const handleKeywordKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addKeyword(keywordInput);
    } else if (e.key === "Backspace" && !keywordInput && keywords.length) {
      setKeywords((prev) => prev.slice(0, -1));
    }
  };

  const removeKeyword = (kw: string) => {
    setKeywords((prev) => prev.filter((k) => k !== kw));
  };

  const handleSave = async () => {
    if (!doc) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await documentsApi.updateMetadata(botId, doc.id, {
        summary: summary.trim() || null,
        keywords,
      });
      onSaved(updated);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Metadata del documento</DialogTitle>
          <DialogDescription>
            Mejora la búsqueda RAG con un resumen y palabras clave. Las keywords que aparezcan en
            la pregunta del usuario darán un boost al score de los chunks de este documento.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {doc && (
            <p className="text-sm text-gray-500">
              <span className="font-medium text-gray-700">{doc.name}</span>
            </p>
          )}

          <div className="space-y-1">
            <Label htmlFor="doc-summary">Resumen</Label>
            <Textarea
              id="doc-summary"
              rows={4}
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="Describe brevemente de qué trata el documento (se inyecta en el contexto del agente RAG)…"
              maxLength={2000}
            />
            <p className="text-xs text-gray-500">{summary.length} / 2000</p>
          </div>

          <div className="space-y-1">
            <Label htmlFor="doc-keywords">Keywords</Label>
            <div className="flex flex-wrap gap-1.5 min-h-9 rounded-md border border-input bg-background px-2 py-1.5">
              {keywords.map((kw) => (
                <Badge key={kw} variant="secondary" className="gap-1 pr-1">
                  {kw}
                  <button
                    type="button"
                    onClick={() => removeKeyword(kw)}
                    className="hover:text-red-600"
                    aria-label={`Quitar ${kw}`}
                  >
                    <X className="w-3 h-3" />
                  </button>
                </Badge>
              ))}
              <Input
                id="doc-keywords"
                value={keywordInput}
                onChange={(e) => setKeywordInput(e.target.value)}
                onKeyDown={handleKeywordKeyDown}
                onBlur={() => keywordInput && addKeyword(keywordInput)}
                placeholder={keywords.length === 0 ? "ej: facturación, devoluciones, garantía…" : ""}
                className="flex-1 min-w-[140px] border-0 shadow-none focus-visible:ring-0 px-1 py-0 h-7"
              />
            </div>
            <p className="text-xs text-gray-500">
              Enter o coma para añadir. Máx. 30 keywords. Se normalizan a minúsculas.
            </p>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Guardando…" : "Guardar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
