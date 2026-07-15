import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 flex flex-col items-center justify-center px-6 text-white">
      <div className="text-center max-w-2xl">
        {/* Badge */}
        <span className="inline-block mb-4 px-3 py-1 text-xs font-semibold tracking-widest uppercase bg-indigo-600/30 border border-indigo-500/40 rounded-full text-indigo-300">
          Hackathon Project
        </span>

        {/* Title */}
        <h1 className="text-5xl font-bold tracking-tight mb-4 bg-gradient-to-r from-white via-indigo-200 to-indigo-400 bg-clip-text text-transparent">
          FlowZint Sentinel
        </h1>

        {/* One-liner */}
        <p className="text-lg text-slate-400 mb-10">
          A self-healing AI support bot with hybrid RAG, confidence routing,
          incident detection, and a self-learning knowledge loop.
        </p>

        {/* Nav cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Link
            href="/chat"
            className="group p-6 rounded-2xl border border-indigo-500/30 bg-indigo-600/10 hover:bg-indigo-600/20 transition-all hover:scale-[1.02] hover:border-indigo-400/60"
          >
            <div className="text-3xl mb-3">💬</div>
            <h2 className="text-lg font-semibold text-white mb-1">
              Customer Chat
            </h2>
            <p className="text-sm text-slate-400">
              AI-powered support widget with hybrid RAG answers.
            </p>
          </Link>

          <Link
            href="/admin"
            className="group p-6 rounded-2xl border border-violet-500/30 bg-violet-600/10 hover:bg-violet-600/20 transition-all hover:scale-[1.02] hover:border-violet-400/60"
          >
            <div className="text-3xl mb-3">🛡️</div>
            <h2 className="text-lg font-semibold text-white mb-1">
              Admin Dashboard
            </h2>
            <p className="text-sm text-slate-400">
              Tickets, incident alerts & KB self-learning controls.
            </p>
          </Link>
        </div>

        {/* Stage pill row */}
        <div className="mt-10 flex flex-wrap justify-center gap-2 text-xs text-slate-400">
          {[
            "1 · Hybrid RAG",
            "2 · Confidence Router",
            "3 · Incident Detection",
            "4 · Human Resolution",
            "5 · Self-Learning Loop",
          ].map((s) => (
            <span
              key={s}
              className="px-3 py-1 rounded-full bg-slate-800 border border-slate-700"
            >
              {s}
            </span>
          ))}
        </div>
      </div>
    </main>
  );
}
