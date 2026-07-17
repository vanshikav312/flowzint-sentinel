"use client";

import { useState, useEffect, useCallback } from "react";

const API_BASE = "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────────

interface Ticket {
  ticket_id: string;
  query: string;
  confidence: number;
  status: "open" | "resolved";
  resolution: string | null;
  kb_draft_id: string | null;
  created_at: string;
  resolved_at: string | null;
}

interface Incident {
  incident_id: string;
  topic: string;
  ticket_count: number;
  severity: "low" | "medium" | "high" | "critical";
  status: "open" | "acknowledged" | "resolved";
  detected_at: string;
}

interface KBDraft {
  draft_id: string;
  title: string;
  content: string;
  source_ticket_id: string | null;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  reviewed_at: string | null;
}

interface Stats {
  open: number;
  resolved: number;
  total: number;
  avg_confidence: number;
}

// ── Utility helpers ────────────────────────────────────────────────────────────

function timeAgo(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const severityColor: Record<string, string> = {
  low: "bg-slate-500/20 text-slate-300 border-slate-500/30",
  medium: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  high: "bg-red-500/20 text-red-300 border-red-500/30",
  critical: "bg-red-700/30 text-red-200 border-red-600/50",
};

const incidentStatusColor: Record<string, string> = {
  open: "bg-indigo-500/20 text-indigo-300",
  acknowledged: "bg-amber-500/20 text-amber-300",
  resolved: "bg-emerald-500/20 text-emerald-300",
};

function Spinner({ small }: { small?: boolean }) {
  return (
    <span
      className={`inline-block rounded-full border-2 border-white/30 border-t-white animate-spin ${
        small ? "w-3 h-3" : "w-4 h-4"
      }`}
    />
  );
}

// ── Skeleton loader ────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <div className="flex items-center justify-between bg-slate-700/40 rounded-xl px-4 py-3 animate-pulse">
      <div className="flex flex-col gap-1.5 flex-1">
        <div className="h-3 bg-slate-600/60 rounded w-2/3" />
        <div className="h-2.5 bg-slate-600/40 rounded w-1/3" />
      </div>
      <div className="h-5 w-16 bg-slate-600/40 rounded-full ml-4" />
    </div>
  );
}

function SectionSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <SkeletonRow />
      <SkeletonRow />
      <SkeletonRow />
    </div>
  );
}

// ── Resolve panel (inline slide-down) ─────────────────────────────────────────

interface ResolvePanelProps {
  ticket: Ticket;
  onSuccess: (updated: Ticket) => void;
  onCancel: () => void;
}

function ResolvePanel({ ticket, onSuccess, onCancel }: ResolvePanelProps) {
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    const resolution = text.trim();
    if (!resolution) {
      setError("Resolution text cannot be empty.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/tickets/${ticket.ticket_id}/resolve`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolution }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const updated: Ticket = await res.json();
      onSuccess(updated);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mt-3 bg-slate-800/80 border border-indigo-500/30 rounded-xl p-4 flex flex-col gap-3">
      <p className="text-xs text-slate-400 font-medium uppercase tracking-wide">
        Resolving: <span className="text-slate-200 normal-case font-normal">{ticket.query}</span>
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type your resolution here…"
        rows={3}
        className="bg-slate-700/60 border border-slate-600/50 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/60 resize-none"
      />
      {error && <p className="text-xs text-red-400">{error}</p>}
      <div className="flex gap-2 justify-end">
        <button
          onClick={onCancel}
          disabled={submitting}
          className="text-xs px-3 py-1.5 rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-700 transition disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={submit}
          disabled={submitting || !text.trim()}
          className="text-xs px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
        >
          {submitting && <Spinner small />}
          Submit
        </button>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AdminPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [drafts, setDrafts] = useState<KBDraft[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ticket_id currently showing inline resolve panel
  const [resolvingId, setResolvingId] = useState<string | null>(null);

  // per-item in-flight state: maps id → true while a fetch is running
  const [inFlight, setInFlight] = useState<Record<string, boolean>>({});

  // per-draft display overrides (approved / rejected)
  const [draftStatus, setDraftStatus] = useState<Record<string, KBDraft["status"]>>({});

  // ── Fetch all data ──────────────────────────────────────────────────────────

  const fetchAll = useCallback(async () => {
    try {
      const [tRes, iRes, kRes, sRes] = await Promise.all([
        fetch(`${API_BASE}/api/tickets/`),
        fetch(`${API_BASE}/api/incidents/`),
        fetch(`${API_BASE}/api/kb/drafts`),
        fetch(`${API_BASE}/api/tickets/stats`),
      ]);

      if (!tRes.ok || !iRes.ok || !kRes.ok || !sRes.ok) {
        throw new Error("One or more backend endpoints returned an error.");
      }

      const [t, i, k, s] = await Promise.all([
        tRes.json(),
        iRes.json(),
        kRes.json(),
        sRes.json(),
      ]);

      setTickets(t);
      setIncidents(i);
      setDrafts(k);
      setStats(s);
      setError(null);
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? e.message
          : "Backend unreachable. Make sure the server is running on port 8000."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load + 15-second auto-refresh
  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 15_000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  // ── Resolve ticket ──────────────────────────────────────────────────────────

  function handleResolveSuccess(updated: Ticket) {
    setTickets((prev) =>
      prev.map((t) => (t.ticket_id === updated.ticket_id ? updated : t))
    );
    setResolvingId(null);
    // Refresh drafts so the new KB draft shows up immediately
    fetch(`${API_BASE}/api/kb/drafts`)
      .then((r) => r.json())
      .then(setDrafts)
      .catch(() => {});
    fetch(`${API_BASE}/api/tickets/stats`)
      .then((r) => r.json())
      .then(setStats)
      .catch(() => {});
  }

  // ── Approve draft ───────────────────────────────────────────────────────────

  async function approveDraft(draftId: string) {
    setInFlight((p) => ({ ...p, [draftId]: true }));
    try {
      const res = await fetch(`${API_BASE}/api/kb/drafts/${draftId}/approve`, {
        method: "POST",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      setDraftStatus((p) => ({ ...p, [draftId]: "approved" }));
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to approve draft.");
    } finally {
      setInFlight((p) => ({ ...p, [draftId]: false }));
    }
  }

  // ── Reject draft ────────────────────────────────────────────────────────────

  async function rejectDraft(draftId: string) {
    setInFlight((p) => ({ ...p, [draftId]: true }));
    try {
      const res = await fetch(`${API_BASE}/api/kb/drafts/${draftId}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      setDraftStatus((p) => ({ ...p, [draftId]: "rejected" }));
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to reject draft.");
    } finally {
      setInFlight((p) => ({ ...p, [draftId]: false }));
    }
  }

  // ── Acknowledge incident ────────────────────────────────────────────────────

  async function acknowledgeIncident(incidentId: string) {
    setInFlight((p) => ({ ...p, [incidentId]: true }));
    try {
      const res = await fetch(
        `${API_BASE}/api/incidents/${incidentId}/acknowledge`,
        { method: "PATCH" }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const updated: Incident = await res.json();
      setIncidents((prev) =>
        prev.map((i) => (i.incident_id === incidentId ? updated : i))
      );
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to acknowledge incident.");
    } finally {
      setInFlight((p) => ({ ...p, [incidentId]: false }));
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  const pendingDrafts = drafts.filter((d) => {
    const s = draftStatus[d.draft_id] ?? d.status;
    return s === "pending";
  });
  const activeIncidents = incidents.filter((i) => i.status === "open");

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
          <button
            onClick={() => { setLoading(true); fetchAll(); }}
            className="text-xs px-3 py-1.5 rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-700 transition"
          >
            ↻ Refresh
          </button>
        </div>

        {/* Error banner */}
        {error && (
          <div className="mb-6 flex items-center justify-between bg-red-900/30 border border-red-500/40 rounded-xl px-4 py-3">
            <p className="text-sm text-red-300">⚠️ {error}</p>
            <button
              onClick={() => { setLoading(true); fetchAll(); }}
              className="text-xs px-3 py-1.5 rounded-lg bg-red-600/30 hover:bg-red-600/50 border border-red-500/30 text-red-300 transition"
            >
              Retry
            </button>
          </div>
        )}

        {/* Stats row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
          {[
            {
              label: "Open Tickets",
              value: stats ? String(stats.open) : "—",
              icon: "🎫",
            },
            {
              label: "Active Incidents",
              value: loading ? "—" : String(activeIncidents.length),
              icon: "🚨",
            },
            {
              label: "KB Drafts Pending",
              value: loading ? "—" : String(pendingDrafts.length),
              icon: "📝",
            },
            {
              label: "Avg Confidence",
              value: stats ? `${stats.avg_confidence.toFixed(0)}%` : "—",
              icon: "📊",
            },
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
          {/* ── Tickets panel ──────────────────────────────────────────────── */}
          <section className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">
              🎫 Escalated Tickets
            </h2>

            {loading ? (
              <SectionSkeleton />
            ) : tickets.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-4">No tickets yet.</p>
            ) : (
              <div className="flex flex-col gap-3">
                {tickets.map((t) => (
                  <div key={t.ticket_id}>
                    <div className="flex items-center justify-between bg-slate-700/40 rounded-xl px-4 py-3">
                      <div className="flex-1 min-w-0 mr-3">
                        <p className="text-sm font-medium text-white truncate">{t.query}</p>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {t.ticket_id} · {t.confidence.toFixed(0)}% conf ·{" "}
                          {timeAgo(t.created_at)}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {t.status === "open" ? (
                          <>
                            <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300">
                              Open
                            </span>
                            <button
                              onClick={() =>
                                setResolvingId(
                                  resolvingId === t.ticket_id ? null : t.ticket_id
                                )
                              }
                              className="text-xs px-3 py-1 rounded-lg bg-violet-600/30 hover:bg-violet-600/50 border border-violet-500/40 text-violet-300 transition"
                            >
                              Resolve
                            </button>
                          </>
                        ) : (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300">
                            Resolved
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Inline resolve panel */}
                    {resolvingId === t.ticket_id && (
                      <ResolvePanel
                        ticket={t}
                        onSuccess={handleResolveSuccess}
                        onCancel={() => setResolvingId(null)}
                      />
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* ── Incidents panel ────────────────────────────────────────────── */}
          <section className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">
              🚨 Detected Incidents
            </h2>

            {loading ? (
              <SectionSkeleton />
            ) : incidents.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-4">No incidents detected.</p>
            ) : (
              <div className="flex flex-col gap-3">
                {incidents.map((inc) => (
                  <div
                    key={inc.incident_id}
                    className="flex items-center justify-between bg-slate-700/40 rounded-xl px-4 py-3"
                  >
                    <div className="flex-1 min-w-0 mr-3">
                      <p className="text-sm font-medium text-white truncate">{inc.topic}</p>
                      <p className="text-xs text-slate-400 mt-0.5">
                        {inc.incident_id} · {inc.ticket_count} queries ·{" "}
                        {timeAgo(inc.detected_at)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full border ${
                          severityColor[inc.severity]
                        }`}
                      >
                        {inc.severity}
                      </span>
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full ${
                          incidentStatusColor[inc.status]
                        }`}
                      >
                        {inc.status}
                      </span>
                      {inc.status === "open" && (
                        <button
                          onClick={() => acknowledgeIncident(inc.incident_id)}
                          disabled={!!inFlight[inc.incident_id]}
                          className="text-xs px-3 py-1 rounded-lg bg-amber-600/30 hover:bg-amber-600/50 border border-amber-500/40 text-amber-300 transition disabled:opacity-50 flex items-center gap-1"
                        >
                          {inFlight[inc.incident_id] && <Spinner small />}
                          Acknowledge
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* ── KB Drafts — full width ──────────────────────────────────────── */}
          <section className="lg:col-span-2 bg-slate-800/50 border border-slate-700/50 rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">
              📝 KB Drafts Awaiting Approval (Self-Learning Loop)
            </h2>

            {loading ? (
              <SectionSkeleton />
            ) : drafts.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-4">
                No KB drafts yet. Resolve a ticket to generate one.
              </p>
            ) : (
              <div className="flex flex-col gap-3">
                {drafts.map((d) => {
                  const currentStatus = draftStatus[d.draft_id] ?? d.status;
                  const busy = !!inFlight[d.draft_id];

                  return (
                    <div
                      key={d.draft_id}
                      className={`flex items-center justify-between bg-slate-700/40 rounded-xl px-4 py-3 transition-opacity ${
                        currentStatus === "rejected" ? "opacity-40" : ""
                      }`}
                    >
                      <div className="flex-1 min-w-0 mr-3">
                        <p className="text-sm font-medium text-white truncate">{d.title}</p>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {d.draft_id}
                          {d.source_ticket_id ? ` · from ${d.source_ticket_id}` : ""} ·{" "}
                          {timeAgo(d.created_at)}
                        </p>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {currentStatus === "pending" && (
                          <>
                            <button
                              onClick={() => approveDraft(d.draft_id)}
                              disabled={busy}
                              className="text-xs px-3 py-1 rounded-lg bg-emerald-600/30 hover:bg-emerald-600/50 border border-emerald-500/40 text-emerald-300 transition disabled:opacity-50 flex items-center gap-1"
                            >
                              {busy && <Spinner small />}
                              ✅ Approve
                            </button>
                            <button
                              onClick={() => rejectDraft(d.draft_id)}
                              disabled={busy}
                              className="text-xs px-3 py-1 rounded-lg bg-red-600/20 hover:bg-red-600/40 border border-red-500/30 text-red-300 transition disabled:opacity-50"
                            >
                              ✕ Reject
                            </button>
                          </>
                        )}
                        {currentStatus === "approved" && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300">
                            Queued for KB ✓
                          </span>
                        )}
                        {currentStatus === "rejected" && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-300">
                            Rejected
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
