"use client";

import { useState, useRef, useEffect, KeyboardEvent } from "react";

const API_BASE = "http://localhost:8000";

interface Message {
  role: "user" | "bot";
  text: string;
  confidence?: number;
  escalated?: boolean;
  ticket_id?: string;
  incident_id?: string;
}

function ConfidenceBadge({ score }: { score: number }) {
  const color =
    score >= 40
      ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
      : score >= 20
      ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
      : "bg-red-500/20 text-red-300 border-red-500/40";
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${color}`}>
      {score.toFixed(0)}% confidence
    </span>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "bot",
      text: "Hi! I'm FlowZint Sentinel. Ask me anything — I'll search the knowledge base and route your question to the right answer.",
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  async function sendMessage() {
    const query = inputValue.trim();
    if (!query || isLoading) return;

    setInputValue("");
    setMessages((prev) => [...prev, { role: "user", text: query }]);
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data = await res.json();

      const botMsg: Message = {
        role: "bot",
        text: data.answer ?? "Sorry, I couldn't get a response.",
        confidence: data.confidence,
        escalated: data.escalate,
        ticket_id: data.ticket_id,
        incident_id: data.incident_id,
      };

      setMessages((prev) => [...prev, botMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text: "⚠️ Couldn't reach the backend. Make sure the server is running on port 8000.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex flex-col items-center justify-center px-4 text-white">
      <div className="w-full max-w-2xl flex flex-col h-[85vh] rounded-2xl border border-indigo-500/30 bg-slate-800/50 backdrop-blur overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-slate-700/50 bg-slate-800/80">
          <div className="w-9 h-9 rounded-full bg-indigo-600 flex items-center justify-center text-lg">
            🤖
          </div>
          <div>
            <p className="font-semibold text-white text-sm">FlowZint Sentinel</p>
            <p className="text-xs text-emerald-400 flex items-center gap-1">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400" />
              Online · Hybrid RAG active
            </p>
          </div>
        </div>

        {/* Message area */}
        <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-4">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex items-start gap-3 ${
                msg.role === "user" ? "flex-row-reverse self-end max-w-[80%]" : "max-w-[85%]"
              }`}
            >
              {/* Avatar */}
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-sm shrink-0 ${
                  msg.role === "user" ? "bg-violet-600" : "bg-indigo-600"
                }`}
              >
                {msg.role === "user" ? "👤" : "🤖"}
              </div>

              {/* Bubble */}
              <div
                className={`rounded-2xl px-4 py-3 text-sm ${
                  msg.role === "user"
                    ? "bg-violet-600/30 rounded-tr-sm text-violet-100"
                    : "bg-slate-700/70 rounded-tl-sm text-slate-200"
                }`}
              >
                <p className="whitespace-pre-wrap leading-relaxed">{msg.text}</p>

                {/* Confidence badge */}
                {msg.confidence !== undefined && (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <ConfidenceBadge score={msg.confidence} />
                  </div>
                )}

                {/* Escalation notice — new ticket opened */}
                {msg.escalated && msg.ticket_id && (
                  <div className="mt-2 flex items-center gap-2 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
                    <span className="text-amber-400 text-xs">⚠️</span>
                    <p className="text-xs text-amber-300">
                      Escalated to human agent · Ticket ID:{" "}
                      <span className="font-mono font-semibold">{msg.ticket_id}</span>
                      {msg.incident_id && (
                        <>
                          {" "}· linked to investigation{" "}
                          <span className="font-mono font-semibold">{msg.incident_id}</span>
                        </>
                      )}
                    </p>
                  </div>
                )}

                {/* Known-issue notice — report absorbed by an existing incident */}
                {msg.escalated && !msg.ticket_id && msg.incident_id && (
                  <div className="mt-2 flex items-center gap-2 bg-sky-500/10 border border-sky-500/30 rounded-lg px-3 py-2">
                    <span className="text-sky-400 text-xs">🛠️</span>
                    <p className="text-xs text-sky-300">
                      Known issue — our team is already on it · Ref:{" "}
                      <span className="font-mono font-semibold">{msg.incident_id}</span>
                    </p>
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Loading indicator */}
          {isLoading && (
            <div className="flex items-start gap-3 max-w-[85%]">
              <div className="w-7 h-7 rounded-full bg-indigo-600 flex items-center justify-center text-sm shrink-0">
                🤖
              </div>
              <div className="bg-slate-700/70 rounded-2xl rounded-tl-sm px-4 py-3">
                <div className="flex gap-1.5 items-center h-4">
                  <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce [animation-delay:-0.3s]" />
                  <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce [animation-delay:-0.15s]" />
                  <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" />
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div className="px-4 py-3 border-t border-slate-700/50 bg-slate-800/80 flex gap-3">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your question…"
            disabled={isLoading}
            className="flex-1 bg-slate-700/60 border border-slate-600/50 rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/60 disabled:opacity-50"
          />
          <button
            onClick={sendMessage}
            disabled={isLoading || !inputValue.trim()}
            className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 transition text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isLoading ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              "Send"
            )}
          </button>
        </div>
      </div>

      <p className="mt-4 text-xs text-slate-500">
        Powered by local embeddings · sentence-transformers · ChromaDB · Groq
      </p>
    </main>
  );
}
