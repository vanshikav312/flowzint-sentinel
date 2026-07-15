export const metadata = {
  title: "Chat | FlowZint Sentinel",
  description: "AI-powered customer support chat with hybrid RAG and confidence routing.",
};

export default function ChatPage() {
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
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              Online · Hybrid RAG active
            </p>
          </div>
        </div>

        {/* Message area */}
        <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-4">
          {/* Bot welcome bubble */}
          <div className="flex items-start gap-3 max-w-[80%]">
            <div className="w-7 h-7 rounded-full bg-indigo-600 flex items-center justify-center text-sm shrink-0">
              🤖
            </div>
            <div className="bg-slate-700/70 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-slate-200">
              Hi! I&apos;m FlowZint Sentinel. Ask me anything — I&apos;ll search
              the knowledge base and route your question to the right answer.
              <p className="mt-2 text-xs text-indigo-300 italic">
                [Placeholder UI — chat backend coming in next sprint]
              </p>
            </div>
          </div>
        </div>

        {/* Input bar */}
        <div className="px-4 py-3 border-t border-slate-700/50 bg-slate-800/80 flex gap-3">
          <input
            type="text"
            placeholder="Type your question…"
            className="flex-1 bg-slate-700/60 border border-slate-600/50 rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/60"
          />
          <button className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 transition text-sm font-semibold">
            Send
          </button>
        </div>
      </div>

      <p className="mt-4 text-xs text-slate-500">
        Powered by local embeddings · sentence-transformers · ChromaDB · Groq
      </p>
    </main>
  );
}
