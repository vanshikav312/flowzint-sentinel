"""
Router: /api/incidents
Stage 3 — Incident Detection

Purpose
-------
Detect *emerging support incidents* by semantically clustering the low-confidence
escalation tickets produced by Stage 2's confidence router.

An "incident" in this platform is a group of semantically similar support queries
that the knowledge base could not answer confidently.  When several customers
independently phrase the same underlying question and all get routed to human
agents, that signals a gap in the knowledge base — or a real product issue —
that an admin should be aware of proactively.

This module is company-agnostic: it works identically regardless of which
knowledge base corpus is loaded (Razorpay docs, internal docs, any other).

Algorithm (Centroid-Based Cosine-Similarity Clustering)
--------------------------------------------------------
1.  Pull every *open* ticket created within the rolling INCIDENT_WINDOW_MINUTES
    window from SQLite.  Older tickets are excluded so incidents represent recent
    bursts, not accumulated history.
2.  Reuse the query_embedding already stored per ticket (written by Stage 2
    at escalation time).  For any ticket without a stored embedding (e.g.
    manual creations), compute it on the fly and persist it to the DB so
    subsequent scans are free.
3.  Run a centroid-based iterative clustering sweep:
        • Pick the first unassigned ticket as a cluster seed.
        • Compute the cluster centroid = L2-normalized mean of all current
          member embeddings.
        • Sweep all unassigned tickets; add those whose cosine similarity to
          the centroid meets or exceeds SIMILARITY_THRESHOLD.
        • After each expansion round, recompute the centroid and sweep again
          until no new tickets join (stable cluster).
        • Repeat from the next unassigned ticket as a new seed.
4.  Any cluster with >= MIN_CLUSTER_SIZE tickets becomes an Incident.
5.  Deduplication: if an existing open Incident in the database already covers
    the majority of a cluster's tickets (>= 50% overlap), the existing incident
    is updated in-place rather than creating a duplicate.

Why centroid-based over seed-only greedy?
    • Seed-only: a ticket is admitted only if similar to the *first* ticket
      picked.  If the seed is an edge case, nearby tickets are incorrectly
      excluded (e.g. "transaction failed" excluded from a payment cluster
      because seed similarity = 0.489 < threshold).
    • Centroid-based: after each admission the centroid shifts toward the true
      cluster center, pulling in tickets that are similar to the group as a
      whole even if they were not close to the original seed.
    • The centroid is the mean of *all* current member embeddings, so a single
      drifting member cannot drag the centroid far off-topic.
    • Still O(n² × passes); passes ≈ 1–2 in practice, well within budget for
      support ticket volumes (n << 1000).

Persistence
-----------
Incidents are stored in the `incidents` SQLite table defined in database/db.py.
They survive server restarts and scale with the same durability guarantees as
tickets and KB drafts.

Endpoints exposed
-----------------
    GET  /api/incidents/          — list all detected incidents (newest first)
    POST /api/incidents/detect    — manually trigger a detection scan
    GET  /api/incidents/{id}      — fetch a single incident by ID

Auto-trigger
------------
    detect_incidents_internal() is imported and called directly by
    create_ticket_internal() in tickets.py immediately after every new ticket
    is persisted, so the admin dashboard stays current without requiring a
    manual /detect call.  Any ticket creation path (RAG escalation, Groq
    failure, empty context, manual dashboard creation) automatically triggers
    a scan.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database.db import get_db

log = logging.getLogger("incidents")

router = APIRouter()

# ── Detection thresholds ──────────────────────────────────────────────────────
# Calibrated for the hackathon demo against all-MiniLM-L6-v2.
# Change these constants to tune detection sensitivity.

SIMILARITY_THRESHOLD = 0.50   # Cosine similarity required to group two tickets
                               # into the same cluster.  Range: 0.0 (anything
                               # groups) to 1.0 (only identical queries group).
                               # Calibrated against all-MiniLM-L6-v2: semantically
                               # related support queries typically score 0.49-0.75;
                               # unrelated queries score below 0.30.

MIN_CLUSTER_SIZE = 2           # Minimum number of tickets in a cluster for it
                               # to be promoted to an Incident.  Set to 2 for
                               # the demo; 3-5 is more realistic for production.

INCIDENT_WINDOW_MINUTES: int
try:
    INCIDENT_WINDOW_MINUTES = max(1, int(os.getenv("INCIDENT_WINDOW_MINUTES", "30")))
except ValueError:
    INCIDENT_WINDOW_MINUTES = 30
    log.warning(
        "INCIDENT_WINDOW_MINUTES env var is not a valid integer — defaulting to 30 minutes."
    )
                               # Rolling time window: only tickets created within
                               # this many minutes are eligible for clustering.
                               # Override via INCIDENT_WINDOW_MINUTES env var.
                               # 30 min is the default for the hackathon demo;
                               # 60-240 min is more typical for production.
                               # Values <= 0 are clamped to 1 minute.


# ── Schema ────────────────────────────────────────────────────────────────────

class Incident(BaseModel):
    """
    Represents a detected support incident: a cluster of semantically similar
    low-confidence tickets that collectively signal an emerging issue.
    """
    incident_id:          str
    topic:                str        # Seed ticket query — human-readable incident title
    ticket_ids:           list[str]  # All ticket IDs in this cluster
    ticket_count:         int        # Convenience field; equals len(ticket_ids)
    severity:             Literal["low", "medium", "high", "critical"]
    status:               Literal["open", "acknowledged", "resolved"] = "open"
    detected_at:          str        # ISO-8601 UTC timestamp of first detection
    updated_at:           str | None = None  # ISO-8601 UTC timestamp of last update
    similarity_threshold: float      # Threshold used when this incident was detected


class DetectResponse(BaseModel):
    """Response body for POST /api/incidents/detect."""
    scanned_tickets:    int
    incidents_detected: int
    incidents:          list[Incident]


# ── DB helpers ────────────────────────────────────────────────────────────────

def _row_to_incident(row) -> Incident:
    """Convert a sqlite3.Row from the incidents table to an Incident model."""
    return Incident(
        incident_id          = row["incident_id"],
        topic                = row["topic"],
        ticket_ids           = json.loads(row["ticket_ids"]),
        ticket_count         = row["ticket_count"],
        severity             = row["severity"],
        status               = row["status"],
        detected_at          = row["detected_at"],
        updated_at           = row["updated_at"],
        similarity_threshold = row["similarity_threshold"],
    )


# ── Private helpers ───────────────────────────────────────────────────────────

def _embed_texts(texts: list[str]) -> np.ndarray:
    """
    Embed a list of text strings using the sentence-transformers model that is
    already loaded and LRU-cached in chat.py.

    We import _get_embeddings() lazily (inside this function) to:
        a) Avoid a circular import at module load time.
        b) Guarantee we reuse the singleton — no second model is initialised.

    Returns a 2D float32 numpy array of shape (len(texts), embedding_dim).
    Because HuggingFaceEmbeddings is initialised with normalize_embeddings=True,
    every returned vector is already L2-normalised.
    """
    from routers.chat import _get_embeddings          # reuse the cached singleton
    model = _get_embeddings()
    vectors = model.embed_documents(texts)
    return np.array(vectors, dtype=np.float32)


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cosine similarity between two 1D vectors.

    Because the embedding model sets normalize_embeddings=True, both vectors
    are already unit-length, so cosine similarity reduces to a plain dot product.
    This avoids the division step and keeps the function fast.
    """
    return float(np.dot(a, b))


def _severity(ticket_count: int) -> str:
    """
    Map the size of an incident's ticket cluster to a human-readable severity
    level for the admin dashboard.

        2-4  tickets -> low
        5-7  tickets -> medium
        8-14 tickets -> high
        15+  tickets -> critical
    """
    if ticket_count >= 15:
        return "critical"
    if ticket_count >= 8:
        return "high"
    if ticket_count >= 5:
        return "medium"
    return "low"


def _centroid_cluster(embeddings: np.ndarray) -> list[list[int]]:
    """
    Centroid-based iterative clustering over a list of embedding vectors.

    Improvement over seed-only greedy:
        Seed-only compares every candidate against the *first* ticket in the
        cluster, which may sit at the semantic edge of the group.  Centroid-based
        computes the normalized mean of all current cluster members after each
        expansion round, then sweeps again.  This allows tickets that are
        similar to the cluster *as a whole* — but not to the original seed —
        to join correctly.

    Algorithm per cluster:
        1. Seed with ticket i.  Centroid = embeddings[i].
        2. Sweep all unassigned tickets; collect those >= SIMILARITY_THRESHOLD
           against the current centroid.
        3. If new members were found: add them, recompute centroid, go to 2.
        4. If no new members: cluster is stable; move to the next seed.

    Complexity: O(n² × passes_per_cluster).  In practice passes ≈ 1-2,
    making the overall cost barely distinguishable from O(n²).

    Returns
    -------
    list[list[int]]
        A list of clusters.  Each cluster is a list of indices into the
        `embeddings` array (and correspondingly into the `valid_tickets` list
        passed to the caller).
    """
    n = len(embeddings)
    assigned = [False] * n
    clusters: list[list[int]] = []

    for i in range(n):
        if assigned[i]:
            continue  # already belongs to a cluster seeded by an earlier ticket

        cluster = [i]
        assigned[i] = True

        # Iteratively expand until the cluster is stable
        while True:
            # Recompute normalised centroid from all current members
            centroid = embeddings[cluster].mean(axis=0)
            norm = np.linalg.norm(centroid)
            if norm > 0:
                centroid = centroid / norm

            # Sweep unassigned tickets against the updated centroid
            new_members: list[int] = []
            for j in range(n):
                if assigned[j]:
                    continue
                sim = _cosine_sim(centroid, embeddings[j])
                if sim >= SIMILARITY_THRESHOLD:
                    new_members.append(j)

            if not new_members:
                break  # no change — cluster is stable

            for j in new_members:
                cluster.append(j)
                assigned[j] = True
            # centroid will be recomputed at the top of the next iteration

        clusters.append(cluster)

    return clusters


def _find_existing_incident(
    ticket_ids_set: frozenset,
    open_incident_rows: list,
) -> Incident | None:
    """
    Search a pre-fetched list of open incident rows for one whose ticket set
    overlaps significantly with the newly detected cluster.

    Overlap criterion: if >= 50% of the cluster's tickets are already tracked
    in an existing open incident, we treat them as the same incident (the
    cluster has simply grown since the last detection run).

    Receives pre-fetched rows so the caller can avoid opening a new DB
    connection on every cluster in the loop.
    """
    for row in open_incident_rows:
        existing_set = frozenset(json.loads(row["ticket_ids"]))
        overlap = len(ticket_ids_set & existing_set)
        if overlap >= len(ticket_ids_set) * 0.5:
            return _row_to_incident(row)

    return None


# ── Core detection logic ──────────────────────────────────────────────────────

def detect_incidents_internal() -> list[Incident]:
    """
    Run a full incident detection scan over the current open ticket store.

    This is the **central Stage 3 function**.  It is:
        * Called automatically by tickets.py after every ticket creation
          (via create_ticket_internal), covering all escalation paths.
        * Also callable manually via POST /api/incidents/detect.

    The function is intentionally synchronous and lightweight.  For tickets
    escalated via the chat pipeline, query_embedding is already stored in
    SQLite by Stage 2 — no model call is needed.  The embedding model is
    only invoked for manually created tickets that lack a stored embedding.

    Returns
    -------
    list[Incident]
        Newly created or updated Incident objects from this scan.
        Returns an empty list if there are fewer open tickets than MIN_CLUSTER_SIZE
        or if embedding fails for any reason.
    """
    # _row_to_ticket is imported lazily here (not at module level) to break the
    # circular import chain: incidents.py is imported by tickets.py at runtime,
    # and tickets.py is imported by incidents.py — a top-level import on either
    # side would cause an ImportError at startup.
    from routers.tickets import _row_to_ticket

    # ── Step 1: Pull recent open tickets from SQLite ─────────────────────────
    # Only tickets within the rolling INCIDENT_WINDOW_MINUTES window are
    # considered.  This ensures incidents represent current surges, not tickets
    # accumulated over days or weeks.
    window_start = (
        datetime.now(timezone.utc) - timedelta(minutes=INCIDENT_WINDOW_MINUTES)
    ).isoformat()

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tickets
             WHERE status = 'open'
               AND created_at >= ?
            """,
            (window_start,),
        ).fetchall()
    open_tickets = [_row_to_ticket(r) for r in rows]

    if len(open_tickets) < MIN_CLUSTER_SIZE:
        log.debug(
            f"Incident scan skipped: only {len(open_tickets)} open ticket(s) "
            f"in the last {INCIDENT_WINDOW_MINUTES} min, need >= {MIN_CLUSTER_SIZE}"
        )
        return []

    log.info(
        f"Stage 3 — scanning {len(open_tickets)} open ticket(s) "
        f"from the last {INCIDENT_WINDOW_MINUTES} min …"
    )

    # ── Step 2: Resolve embeddings ────────────────────────────────────────────
    # For tickets escalated via the RAG pipeline, query_embedding is already
    # stored in the DB (written by chat.py at retrieval time).  We use those
    # directly — zero model inference for the common path.
    #
    # For tickets without a stored embedding (e.g. manually created via the
    # dashboard), we compute the embedding on the fly and write it back to the
    # DB so subsequent scans remain free for those tickets too.
    embeddings_list: list[tuple[int, np.ndarray]] = []
    need_embed_indices: list[int] = []
    need_embed_texts: list[str]   = []

    for i, t in enumerate(open_tickets):
        if t.query_embedding:
            embeddings_list.append((i, np.array(t.query_embedding, dtype=np.float32)))
        else:
            need_embed_indices.append(i)
            need_embed_texts.append(t.query)

    if need_embed_texts:
        try:
            computed_vectors = _embed_texts(need_embed_texts)
            with get_db() as conn:
                for idx, vector in zip(need_embed_indices, computed_vectors):
                    vector_list = vector.tolist()
                    open_tickets[idx].query_embedding = vector_list
                    conn.execute(
                        "UPDATE tickets SET query_embedding = ? WHERE ticket_id = ?",
                        (json.dumps(vector_list), open_tickets[idx].ticket_id),
                    )
                    embeddings_list.append((idx, vector))
        except Exception as exc:
            log.warning(f"Stage 3 embedding fallback failed — detection skipped: {exc}")
            return []

    # Build ordered valid_tickets / embeddings arrays (exclude any ticket whose
    # embedding could not be obtained)
    embeddings_list.sort(key=lambda x: x[0])
    valid_tickets: list["Ticket"] = []
    valid_embeddings: list[np.ndarray] = []
    for idx, emb in embeddings_list:
        valid_tickets.append(open_tickets[idx])
        valid_embeddings.append(emb)

    if len(valid_tickets) < MIN_CLUSTER_SIZE:
        log.debug(
            f"Incident scan skipped: only {len(valid_tickets)} ticket(s) with embeddings, "
            f"need >= {MIN_CLUSTER_SIZE}"
        )
        return []

    embeddings = np.array(valid_embeddings, dtype=np.float32)

    # ── Step 3: Centroid-based clustering ────────────────────────────────────
    clusters = _centroid_cluster(embeddings)

    # Fetch all open incidents once before the cluster loop to avoid opening
    # a new DB connection on every cluster (Bug B2 fix).
    with get_db() as conn:
        open_incident_rows = conn.execute(
            "SELECT * FROM incidents WHERE status = 'open'"
        ).fetchall()

    now = datetime.now(timezone.utc).isoformat()
    affected: list[Incident] = []

    # ── Steps 4 & 5: Promote clusters → Incidents, with deduplication ─────────
    for cluster_indices in clusters:
        if len(cluster_indices) < MIN_CLUSTER_SIZE:
            continue  # cluster too small — not an incident

        cluster_tickets = [valid_tickets[i] for i in cluster_indices]
        ticket_ids      = sorted(t.ticket_id for t in cluster_tickets)
        ticket_ids_set  = frozenset(ticket_ids)

        existing = _find_existing_incident(ticket_ids_set, open_incident_rows)

        if existing:
            # ── Update existing incident in SQLite ────────────────────────────
            merged_ids    = sorted(ticket_ids_set | frozenset(existing.ticket_ids))
            new_count     = len(merged_ids)
            new_severity  = _severity(new_count)

            with get_db() as conn:
                conn.execute(
                    """
                    UPDATE incidents
                       SET ticket_ids   = ?,
                           ticket_count = ?,
                           severity     = ?,
                           updated_at   = ?
                     WHERE incident_id  = ?
                    """,
                    (
                        json.dumps(merged_ids),
                        new_count,
                        new_severity,
                        now,
                        existing.incident_id,
                    ),
                )

            # Build the updated Incident from known data — avoids a redundant
            # SELECT round-trip after the UPDATE (B2 fix).
            updated = Incident(
                incident_id          = existing.incident_id,
                topic                = existing.topic,
                ticket_ids           = merged_ids,
                ticket_count         = new_count,
                severity             = new_severity,
                status               = existing.status,
                detected_at          = existing.detected_at,
                updated_at           = now,
                similarity_threshold = existing.similarity_threshold,
            )

            log.info(
                f"Incident {updated.incident_id} updated — "
                f"{updated.ticket_count} tickets, severity={updated.severity}"
            )
            affected.append(updated)

        else:
            # ── Insert new incident into SQLite ───────────────────────────────
            seed_query  = cluster_tickets[0].query
            incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
            severity    = _severity(len(ticket_ids))

            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO incidents
                        (incident_id, topic, ticket_ids, ticket_count,
                         severity, status, detected_at, similarity_threshold)
                    VALUES (?, ?, ?, ?, ?, 'open', ?, ?)
                    """,
                    (
                        incident_id,
                        seed_query,
                        json.dumps(ticket_ids),
                        len(ticket_ids),
                        severity,
                        now,
                        SIMILARITY_THRESHOLD,
                    ),
                )

            incident = Incident(
                incident_id          = incident_id,
                topic                = seed_query,
                ticket_ids           = ticket_ids,
                ticket_count         = len(ticket_ids),
                severity             = severity,
                detected_at          = now,
                similarity_threshold = SIMILARITY_THRESHOLD,
            )

            log.info(
                f"New incident {incident_id} detected — "
                f"{len(ticket_ids)} tickets, severity={severity}, "
                f"topic: {seed_query!r}"
            )
            affected.append(incident)

    log.info(
        f"Stage 3 scan complete — "
        f"{len(clusters)} clusters found, {len(affected)} incident(s) created/updated"
    )
    return affected


# ── HTTP endpoints ─────────────────────────────────────────────────────────────

@router.get("/", response_model=list[Incident])
async def list_incidents():
    """
    Return all detected incidents, newest first.

    This is the primary feed for the admin dashboard's Incidents panel.
    Both open and acknowledged incidents are returned; resolved incidents
    are included for audit purposes.
    """
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM incidents ORDER BY detected_at DESC"
        ).fetchall()
    return [_row_to_incident(r) for r in rows]


@router.post("/detect", response_model=DetectResponse)
async def run_detection():
    """
    Stage 3: Manually trigger an incident detection scan.

    While detection is also triggered automatically after each ticket creation,
    this endpoint is useful for:
        * Forcing a fresh scan at any time from the admin dashboard.
        * Testing the detection logic during development.
        * Re-evaluating incidents after tickets are resolved.

    Returns a summary of how many tickets were scanned and how many
    incidents were created or updated.
    """
    window_start = (
        datetime.now(timezone.utc) - timedelta(minutes=INCIDENT_WINDOW_MINUTES)
    ).isoformat()
    with get_db() as conn:
        open_count = conn.execute(
            """
            SELECT COUNT(*) as count FROM tickets
             WHERE status = 'open'
               AND created_at >= ?
            """,
            (window_start,),
        ).fetchone()["count"]

    affected = detect_incidents_internal()

    return DetectResponse(
        scanned_tickets    = open_count,
        incidents_detected = len(affected),
        incidents          = affected,
    )


@router.get("/{incident_id}", response_model=Incident)
async def get_incident(incident_id: str):
    """
    Return a single incident by its ID.

    Useful for the admin dashboard detail view — shows which specific
    tickets constitute the incident cluster.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM incidents WHERE incident_id = ?",
            (incident_id,),
        ).fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Incident {incident_id} not found.",
        )
    return _row_to_incident(row)
