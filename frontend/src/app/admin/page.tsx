export const metadata = {
  title: "Admin Dashboard | FlowZint Sentinel",
  description: "Admin view for tickets, incident alerts, and knowledge base self-learning controls.",
};

const MOCK_TICKETS = [
  { id: "TK-001", query: "Payment not processed", status: "Open", confidence: "12%", created: "2m ago" },
  { id: "TK-002", query: "Cannot reset password", status: "Open", confidence: "34%", created: "8m ago" },
  { id: "TK-003", query: "Refund not received", status: "Resolved", confidence: "21%", created: "1h ago" },
];

const MOCK_INCIDENTS = [
  { id: "INC-001", topic: "Payment failures", count: 14, severity: "High", detected: "5m ago" },
  { id: "INC-002", topic: "Login issues", count: 7, severity: "Medium", detected: "22m ago" },
];

const MOCK_KB_DRAFTS = [
  { id: "KB-001", title: "How to retry a failed payment", source: "INC-001", status: "Pending" },
  { id: "KB-002", title: "Password reset troubleshooting steps", source: "TK-002", status: "Pending" },
];

const severityColor: Record<string, string> = {
  High: "bg-red-500/20 text-red-300 border-red-500/30",
  Medium: "bg-amber-500/20 text-amber-300 border-amber-500/30",
};

const statusColor: Record<string, string> = {
  Open: "bg-indigo-500/20 text-indigo-300",
  Resolved: "bg-emerald-500/20 text-emerald-300",
  Pending: "bg-amber-500/20 text-amber-300",
};

export default function AdminPage() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white px-6 py-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-white to-violet-300 bg-clip-text text-transparent">
              Admin Dashboard
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Tickets · Incidents · Knowledge Base Self-Learning
            </p>
          </div>
          <span className="text-xs px-3 py-1 rounded-full bg-slate-700 border border-slate-600 text-slate-300">
            🔴 Placeholder UI — backend coming soon
          </span>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
          {[
            { label: "Open Tickets", value: "2", icon: "🎫" },
            { label: "Active Incidents", value: "2", icon: "🚨" },
            { label: "KB Drafts Pending", value: "2", icon: "📝" },
            { label: "Avg Confidence", value: "22%", icon: "📊" },
          ].map((s) => (
            <div
              key={s.label}
              className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-4"
            >
              <div className="text-2xl mb-1">{s.icon}</div>
              <div className="text-2xl font-bold">{s.value}</div>
              <div className="text-xs text-slate-400 mt-0.5">{s.label}</div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Tickets */}
          <section className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">
              🎫 Escalated Tickets
            </h2>
            <div className="flex flex-col gap-3">
              {MOCK_TICKETS.map((t) => (
                <div
                  key={t.id}
                  className="flex items-center justify-between bg-slate-700/40 rounded-xl px-4 py-3"
                >
                  <div>
                    <p className="text-sm font-medium text-white">{t.query}</p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {t.id} · confidence {t.confidence} · {t.created}
                    </p>
                  </div>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${statusColor[t.status]}`}
                  >
                    {t.status}
                  </span>
                </div>
              ))}
            </div>
          </section>

          {/* Incidents */}
          <section className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">
              🚨 Detected Incidents
            </h2>
            <div className="flex flex-col gap-3">
              {MOCK_INCIDENTS.map((i) => (
                <div
                  key={i.id}
                  className="flex items-center justify-between bg-slate-700/40 rounded-xl px-4 py-3"
                >
                  <div>
                    <p className="text-sm font-medium text-white">{i.topic}</p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {i.id} · {i.count} queries · {i.detected}
                    </p>
                  </div>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full border ${severityColor[i.severity]}`}
                  >
                    {i.severity}
                  </span>
                </div>
              ))}
            </div>
          </section>

          {/* KB Drafts — full width */}
          <section className="lg:col-span-2 bg-slate-800/50 border border-slate-700/50 rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">
              📝 KB Drafts Awaiting Approval (Self-Learning Loop)
            </h2>
            <div className="flex flex-col gap-3">
              {MOCK_KB_DRAFTS.map((d) => (
                <div
                  key={d.id}
                  className="flex items-center justify-between bg-slate-700/40 rounded-xl px-4 py-3"
                >
                  <div>
                    <p className="text-sm font-medium text-white">{d.title}</p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {d.id} · Generated from {d.source}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button className="text-xs px-3 py-1 rounded-lg bg-emerald-600/30 hover:bg-emerald-600/50 border border-emerald-500/40 text-emerald-300 transition">
                      ✅ Approve
                    </button>
                    <button className="text-xs px-3 py-1 rounded-lg bg-red-600/20 hover:bg-red-600/40 border border-red-500/30 text-red-300 transition">
                      ✕ Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
