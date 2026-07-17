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

Algorithm (Greedy Cosine-Similarity Clustering)
------------------------------------------------
1.  Pull every *open* ticket from the shared in-memory ticket store.
2.  Embed each ticket's query using the sentence-transformers model that is
    already loaded and LRU-cached by the chat router (Stage 1).  No second
    model instance is created.
3.  Run a greedy single-pass clustering sweep:
        • Pick the first unassigned ticket as a cluster seed.
        • Collect every other unassigned ticket whose cosine similarity to the
          seed exceeds SIMILARITY_THRESHOLD.
        • Mark all collected tickets as assigned and form a cluster.
        • Repeat until all tickets have been visited.
4.  Any cluster with >= MIN_CLUSTER_SIZE tickets becomes an Incident.
5.  Deduplication: if an existing open Incident already covers the majority of
    a cluster's tickets (>= 50% overlap), the existing incident is updated in
    place rather than creating a duplicate.

Why greedy clustering?
    • k-means requires knowing k in advance — we don't.
    • DBSCAN adds a sklearn dependency and is overkill at this scale.
    • Greedy single-pass is O(n²) which is perfectly fine for a support ticket
      store of tens to hundreds of tickets, and is easy to explain during judging.
    • Zero extra dependencies — numpy is already a transitive dep of
      sentence-transformers.

Endpoints exposed
-----------------
    GET  /api/incidents/          — list all detected incidents (newest first)
    POST /api/incidents/detect    — manually trigger a detection scan
    GET  /api/incidents/{id}      — fetch a single incident by ID

Auto-trigger
------------
    detect_incidents_internal() is also imported and called directly by
    chat.py immediately after Stage 2 creates a ticket, so the admin dashboard
    stays current without requiring a manual /detect call.
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger("incidents")

router = APIRouter()

# ── Detection thresholds ──────────────────────────────────────────────────────
# Lowered from the conservative production defaults to hackathon-demo values
# so that incidents are easy to trigger with a handful of test queries.
# Change these constants to tune detection sensitivity.

SIMILARITY_THRESHOLD = 0.50   # Cosine similarity required to group two tickets
                               # into the same cluster.  Range: 0.0 (anything
                               # groups) to 1.0 (only identical queries group).
                               # Calibrated against all-MiniLM-L6-v2: semantically
                               # related support queries typically score 0.49-0.75;
                               # unrelated queries score below 0.30.

MIN_CLUSTER_SIZE = 2           # Minimum number of tickets in a cluster for it
                               # to be promoted to an Incident.  Set to 2 for
                               # the demo; 3–5 is more realistic for production.

# ── In-memory incident store ──────────────────────────────────────────────────
# Mirrors the _TICKETS and _DRAFTS pattern used in tickets.py and kb.py.
# Dict maps incident_id -> Incident.
_INCIDENTS: dict[str, "Incident"] = {}


# ── Schema ────────────────────────────────────────────────────────────────────

class Incident(BaseModel):
    """
    Represents a detected support incident: a cluster of semantically similar
    low-confidence tickets that collectively signal an emerging issue.
    """
    incident_id:          str
    topic:                str                              # Query text from the seed (first) ticket in the cluster — used as the human-readable incident title
    ticket_ids:           list[str]                        # All ticket IDs belonging to this cluster
    ticket_count:         int                              # Convenience field; equals len(ticket_ids)
    severity:             Literal["low", "medium", "high", "critical"]
    status:               Literal["open", "acknowledged", "resolved"] = "open"
    detected_at:          str                              # ISO-8601 UTC timestamp of first detection
    updated_at:           str | None = None                # ISO-8601 UTC timestamp of last update (new tickets joined)
    similarity_threshold: float                            # Threshold value used when this incident was detected — useful for audit/debugging


class DetectResponse(BaseModel):
    """Response body for POST /api/incidents/detect."""
    scanned_tickets:    int
    incidents_detected: int
    incidents:          list[Incident]


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
    # embed_documents returns list[list[float]]; convert to numpy for vectorised ops
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

        2–4  tickets → low
        5–7  tickets → medium
        8–14 tickets → high
        15+  tickets → critical
    """
    if ticket_count >= 15:
        return "critical"
    if ticket_count >= 8:
        return "high"
    if ticket_count >= 5:
        return "medium"
    return "low"


def _greedy_cluster(embeddings: np.ndarray) -> list[list[int]]:
    """
    Greedy single-pass clustering over a list of embedding vectors.

    For each unassigned ticket (used as the cluster *seed*), this function
    sweeps all remaining unassigned tickets and groups those whose cosine
    similarity to the seed meets or exceeds SIMILARITY_THRESHOLD.

    Complexity: O(n²) — acceptable for support ticket volumes (n << 1000).

    Returns
    -------
    list[list[int]]
        A list of clusters.  Each cluster is a list of indices into the
        `embeddings` array (and, correspondingly, into the `open_tickets` list
        passed to the caller).
    """
    n = len(embeddings)
    assigned = [False] * n
    clusters: list[list[int]] = []

    for i in range(n):
        if assigned[i]:
            continue  # already belongs to a cluster seeded by an earlier ticket

        # Start a new cluster using ticket i as the seed
        cluster = [i]
        assigned[i] = True

        for j in range(i + 1, n):
            if assigned[j]:
                continue
            sim = _cosine_sim(embeddings[i], embeddings[j])
            if sim >= SIMILARITY_THRESHOLD:
                cluster.append(j)
                assigned[j] = True

        clusters.append(cluster)

    return clusters


def _find_existing_incident(ticket_ids_set: frozenset) -> Incident | None:
    """
    Look for an existing *open* incident whose ticket set overlaps significantly
    with the newly detected cluster.

    Overlap criterion: if >= 50% of the cluster's tickets are already tracked
    in an existing open incident, we treat them as the same incident (the
    cluster has simply grown since the last detection run).

    This prevents duplicate incidents accumulating across repeated /detect calls.
    """
    for incident in _INCIDENTS.values():
        if incident.status != "open":
            continue  # only merge into open incidents

        existing_set = frozenset(incident.ticket_ids)
        overlap = len(ticket_ids_set & existing_set)

        # Majority overlap → same underlying issue
        if overlap >= len(ticket_ids_set) * 0.5:
            return incident

    return None


# ── Core detection logic ──────────────────────────────────────────────────────

def detect_incidents_internal() -> list[Incident]:
    """
    Run a full incident detection scan over the current open ticket store.

    This is the **central Stage 3 function**.  It is:
        • Called automatically by chat.py after every Stage 2 ticket creation.
        • Also callable manually via POST /api/incidents/detect.

    The function is intentionally synchronous and lightweight — embedding a
    few dozen ticket queries takes well under a second on CPU.

    Returns
    -------
    list[Incident]
        Newly created or updated Incident objects from this scan.
        Returns an empty list if there are fewer open tickets than MIN_CLUSTER_SIZE
        or if embedding fails for any reason.
    """
    # ── Step 1: Pull open tickets ─────────────────────────────────────────────
    from database.db import get_db
    from routers.tickets import _row_to_ticket
    import json

    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tickets WHERE status = 'open'"
        ).fetchall()
    open_tickets = [_row_to_ticket(r) for r in rows]

    if len(open_tickets) < MIN_CLUSTER_SIZE:
        # Not enough data to form any incident — exit early
        log.debug(
            f"Incident scan skipped: only {len(open_tickets)} open ticket(s), "
            f"need >= {MIN_CLUSTER_SIZE}"
        )
        return []

    log.info(f"Stage 3 — scanning {len(open_tickets)} open tickets for incidents …")

    # ── Step 2: Embed all open ticket queries ─────────────────────────────────
    # If the database already has the embedding stored, use it.
    # Otherwise, compute it on the fly and save it.
    embeddings_list = []
    need_embed_indices = []
    need_embed_texts = []

    for i, t in enumerate(open_tickets):
        if t.query_embedding:
            embeddings_list.append((i, np.array(t.query_embedding, dtype=np.float32)))
        else:
            need_embed_indices.append(i)
            need_embed_texts.append(t.query)

    if need_embed_texts:
        try:
            computed_vectors = _embed_texts(need_embed_texts)
            # Store computed embeddings back to the SQLite DB to avoid re-embedding
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

    # Sort embeddings by their original ticket index to match open_tickets order
    embeddings_list.sort(key=lambda x: x[0])
    valid_tickets = []
    valid_embeddings = []
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

    # ── Step 3: Greedy clustering ─────────────────────────────────────────────
    clusters = _greedy_cluster(embeddings)

    now = datetime.now(timezone.utc).isoformat()
    affected: list[Incident] = []

    # ── Step 4 & 5: Promote clusters → Incidents, with deduplication ──────────
    for cluster_indices in clusters:
        if len(cluster_indices) < MIN_CLUSTER_SIZE:
            continue  # cluster too small to be an incident

        cluster_tickets = [valid_tickets[i] for i in cluster_indices]
        ticket_ids      = sorted(t.ticket_id for t in cluster_tickets)
        ticket_ids_set  = frozenset(ticket_ids)

        # Deduplication: check if an existing open incident already covers
        # the majority of these tickets (cluster grew since last scan)
        existing = _find_existing_incident(ticket_ids_set)

        if existing:
            # ── Update existing incident in-place ─────────────────────────
            # Merge new ticket IDs into the existing set (union) so the
            # incident accurately reflects all affected tickets over time.
            merged_ids           = sorted(ticket_ids_set | frozenset(existing.ticket_ids))
            existing.ticket_ids  = merged_ids
            existing.ticket_count = len(merged_ids)
            existing.severity    = _severity(existing.ticket_count)
            existing.updated_at  = now
            _INCIDENTS[existing.incident_id] = existing

            log.info(
                f"Incident {existing.incident_id} updated — "
                f"{existing.ticket_count} tickets, severity={existing.severity}"
            )
            affected.append(existing)

        else:
            # ── Create new incident ───────────────────────────────────────
            # Use the seed ticket's query as the human-readable topic label.
            # The seed is the first ticket encountered in the sweep — it is
            # representative of the cluster but not necessarily the "best"
            # label.  Admins can rename incidents in a future UI iteration.
            seed_query = cluster_tickets[0].query

            incident = Incident(
                incident_id          = f"INC-{uuid.uuid4().hex[:8].upper()}",
                topic                = seed_query,
                ticket_ids           = ticket_ids,
                ticket_count         = len(ticket_ids),
                severity             = _severity(len(ticket_ids)),
                detected_at          = now,
                similarity_threshold = SIMILARITY_THRESHOLD,
            )
            _INCIDENTS[incident.incident_id] = incident

            log.info(
                f"New incident {incident.incident_id} detected — "
                f"{incident.ticket_count} tickets, severity={incident.severity}, "
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
    return sorted(
        _INCIDENTS.values(),
        key=lambda inc: inc.detected_at,
        reverse=True,
    )


@router.post("/detect", response_model=DetectResponse)
async def run_detection():
    """
    Stage 3: Manually trigger an incident detection scan.

    While detection is also triggered automatically after each Stage 2
    escalation, this endpoint is useful for:
        • Forcing a fresh scan at any time from the admin dashboard.
        • Testing the detection logic during development.
        • Re-evaluating incidents after tickets are resolved.

    Returns a summary of how many tickets were scanned and how many
    incidents were created or updated.
    """
    from database.db import get_db
    with get_db() as conn:
        open_count = conn.execute(
            "SELECT COUNT(*) as count FROM tickets WHERE status = 'open'"
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
    incident = _INCIDENTS.get(incident_id)
    if not incident:
        raise HTTPException(
            status_code=404,
            detail=f"Incident {incident_id} not found."
        )
    return incident
