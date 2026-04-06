import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b">
        <div className="container mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-xl font-bold">Agent Chat Builder</h1>
          <Link href="/dashboard">
            <Button>Ir al Dashboard</Button>
          </Link>
        </div>
      </header>

      {/* Hero */}
      <main className="flex-1 flex items-center justify-center">
        <div className="container mx-auto px-4 text-center">
          <h2 className="text-5xl font-bold mb-6">
            Crea Chatbots con IA
            <br />
            <span className="text-blue-600">Sin Código</span>
          </h2>
          <p className="text-xl text-gray-600 mb-8 max-w-2xl mx-auto">
            Crea chatbots inteligentes con RAG, agentes especializados y
            despliegue multicanal. Conéctalos a WhatsApp, Telegram o incrústalos
            en tu sitio web.
          </p>
          <div className="flex gap-4 justify-center">
            <Link href="/dashboard">
              <Button size="lg">Empezar a Construir</Button>
            </Link>
          </div>

          {/* Features */}
          <div id="features" className="grid md:grid-cols-3 gap-8 mt-20 text-left">
            <div className="p-6 border rounded-lg">
              <h3 className="text-lg font-semibold mb-2">Impulsado por RAG</h3>
              <p className="text-gray-600">
                Sube tus documentos y deja que la IA responda preguntas basándose
                en tu base de conocimiento.
              </p>
            </div>
            <div className="p-6 border rounded-lg">
              <h3 className="text-lg font-semibold mb-2">Agentes Especializados</h3>
              <p className="text-gray-600">
                Configura agentes distintos para cada intención: informativo,
                creativo, planificación y más.
              </p>
            </div>
            <div className="p-6 border rounded-lg">
              <h3 className="text-lg font-semibold mb-2">Multicanal</h3>
              <p className="text-gray-600">
                Despliega en WhatsApp, Telegram o incrusta un widget de chat en
                tu sitio web.
              </p>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t py-8">
        <div className="container mx-auto px-4 text-center text-gray-600">
          <p>Agent Chat Builder — Crea chatbots más inteligentes</p>
        </div>
      </footer>
    </div>
  );
}
