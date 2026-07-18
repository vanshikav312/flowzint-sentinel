"use client";

import { useState, useRef, useEffect, KeyboardEvent } from "react";
import { Bot, AlertTriangle, Wrench, Send, Loader2 } from "lucide-react";

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
  const style =
    score >= 40
      ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
      : score >= 20
      ? "bg-amber-500/15 text-amber-400 border border-amber-500/30"
      : "bg-red-500/15 text-red-400 border border-red-500/30";
  return (
    <span
      className={`inline-flex items-center gap-1 font-mono text-[10px] px-2 py-0.5 rounded ${style}`}
    >
      {score.toFixed(0)}% confidence
    </span>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "bot",
      text: "Hi, I'm FlowZint Sentinel. Ask me anything — I'll search the knowledge base and route your question to the right answer.",
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

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();

      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text: data.answer ?? "Sorry, I couldn't get a response.",
          confidence: data.confidence,
          escalated: data.escalate,
          ticket_id: data.ticket_id,
          incident_id: data.incident_id,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text: "Could not reach the backend. Make sure the server is running on port 8000.",
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
    <main className="bg-[#0F172A] min-h-screen flex flex-col items-center pt-4 pb-6 px-4">
      {/* Chat panel */}
      <div
        className="w-full max-w-2xl flex flex-col bg-[#1E293B] border border-[#334155] rounded-md overflow-hidden"
        style={{ height: "calc(100vh - 80px)" }}
      >
        {/* Chat header */}
        <div className="h-10 px-4 flex items-center gap-2 border-b border-[#334155] bg-[#0F172A] shrink-0">
          <div className="w-6 h-6 bg-indigo-600 rounded flex items-center justify-center shrink-0">
            <Bot className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="text-[13px] font-medium text-slate-100">FlowZint Sentinel</span>
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 ml-1 shrink-0" />
          <span className="text-[11px] text-slate-400">Online · Hybrid RAG active</span>
        </div>

        {/* Message area */}
        <div className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-3">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
            >
              {msg.role === "user" ? (
                <div className="self-end max-w-[78%] bg-indigo-600 text-slate-100 text-[13px] px-3 py-2 rounded-md">
                  <p className="whitespace-pre-wrap leading-relaxed">{msg.text}</p>
                </div>
              ) : (
                <div className="max-w-[85%] bg-[#0F172A] border border-[#334155] text-slate-200 text-[13px] px-3 py-2 rounded-md">
                  <p className="whitespace-pre-wrap leading-relaxed">{msg.text}</p>

                  {/* Confidence badge */}
                  {msg.confidence !== undefined && (
                    <div className="mt-2">
                      <ConfidenceBadge score={msg.confidence} />
                    </div>
                  )}

                  {/* Escalation notice — new ticket opened */}
                  {msg.escalated && msg.ticket_id && (
                    <div className="bg-amber-500/10 border-l-2 border-amber-500 px-3 py-2 rounded-sm mt-2 flex items-start gap-2">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                      <p className="text-[11px] text-amber-300">
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

                  {/* Known-issue notice — report absorbed by existing incident */}
                  {msg.escalated && !msg.ticket_id && msg.incident_id && (
                    <div className="bg-sky-500/10 border-l-2 border-sky-500 px-3 py-2 rounded-sm mt-2 flex items-start gap-2">
                      <Wrench className="w-3.5 h-3.5 text-sky-400 shrink-0 mt-0.5" />
                      <p className="text-[11px] text-sky-300">
                        Known issue — our team is already on it · Ref:{" "}
                        <span className="font-mono font-semibold">{msg.incident_id}</span>
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {/* Loading indicator */}
          {isLoading && (
            <div className="flex items-start">
              <div className="bg-[#0F172A] border border-[#334155] px-3 py-2 rounded-md">
                <div className="flex gap-1.5 items-center h-4">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-600 animate-bounce [animation-delay:-0.3s]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-600 animate-bounce [animation-delay:-0.15s]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-600 animate-bounce" />
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div className="h-12 px-3 py-2 border-t border-[#334155] bg-[#0F172A] flex gap-2 items-center shrink-0">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your question…"
            disabled={isLoading}
            className="flex-1 bg-[#0F172A] border border-[#334155] rounded text-[13px] text-slate-100 px-3 py-1.5 focus:outline-none focus:border-indigo-500 placeholder:text-slate-600 disabled:opacity-50"
          />
          <button
            onClick={sendMessage}
            disabled={isLoading || !inputValue.trim()}
            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-[12px] font-medium flex items-center gap-1.5 disabled:opacity-40"
            aria-label="Send message"
          >
            {isLoading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Send className="w-3.5 h-3.5" />
            )}
            Send
          </button>
        </div>
      </div>

      <p className="mt-3 text-[11px] text-slate-600 font-mono">
        Powered by local embeddings · sentence-transformers · ChromaDB · Groq
      </p>
    </main>
  );
}
