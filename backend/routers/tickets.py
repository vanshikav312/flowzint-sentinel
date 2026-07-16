"""
Router: /api/tickets
Stage 2 — Confidence Router feeds into this module.

Persistence: SQLite via database/db.py (survives --reload and server restarts).

Each ticket stores:
  - query embedding (list[float]) — captured at creation for Stage 3 clustering
  - confidence (float 0-100)      — blended retrieval + LLM score from chat.py
  - sources (list[dict])          — top RRF chunks that informed the answer
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database.db import get_db

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class Ticket(BaseModel):
    ticket_id:       str
    query:           str
    confidence:      float
    status:          Literal["open", "resolved"] = "open"
    sources:         list[dict] = []
    query_embedding: list[float] | None = None   # for Stage 3 clustering
    resolution:      str | None = None
    kb_draft_id:     str | None = None
    created_at:      str = ""
    resolved_at:     str | None = None


class ResolveBody(BaseModel):
    resolution: str


# ── Row → Ticket ──────────────────────────────────────────────────────────────

def _row_to_ticket(row) -> Ticket:
    embedding_raw = row["query_embedding"]
    return Ticket(
        ticket_id       = row["ticket_id"],
        query           = row["query"],
        confidence      = row["confidence"],
        status          = row["status"],
        sources         = json.loads(row["sources"]),
        query_embedding = json.loads(embedding_raw) if embedding_raw else None,
        resolution      = row["resolution"],
        kb_draft_id     = row["kb_draft_id"],
        created_at      = row["created_at"],
        resolved_at     = row["resolved_at"],
    )


# ── Internal helper (called by chat.py confidence router) ─────────────────────

def create_ticket_internal(
    query: str,
    confidence: float,
    sources: list[dict],
    query_embedding: list[float] | None = None,
) -> Ticket:
    """
    Persist a ticket from a low-confidence escalation.
    query_embedding is captured in chat.py at retrieval time (free — model already loaded).
    """
    ticket_id  = f"TK-{uuid.uuid4().hex[:8].upper()}"
    created_at = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO tickets
                (ticket_id, query, confidence, status, sources, query_embedding, created_at)
            VALUES (?, ?, ?, 'open', ?, ?, ?)
            """,
            (
                ticket_id,
                query,
                confidence,
                json.dumps(sources),
                json.dumps(query_embedding) if query_embedding is not None else None,
                created_at,
            ),
        )

    return Ticket(
        ticket_id       = ticket_id,
        query           = query,
        confidence      = confidence,
        sources         = sources,
        query_embedding = query_embedding,
        created_at      = created_at,
    )


# ── HTTP endpoints ─────────────────────────────────────────────────────────────

@router.get("/", response_model=list[Ticket])
async def list_tickets():
    """Return all tickets (open + resolved), newest first."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tickets ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_ticket(r) for r in rows]


@router.get("/{ticket_id}", response_model=Ticket)
async def get_ticket(ticket_id: str):
    """Return a single ticket by ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")
    return _row_to_ticket(row)


@router.post("/", response_model=Ticket)
async def create_ticket(body: dict):
    """Manually create a ticket (e.g. from admin dashboard)."""
    query = str(body.get("query", "")).strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required.")
    confidence = float(body.get("confidence", 0))
    sources    = body.get("sources", [])
    return create_ticket_internal(query, confidence, sources)


@router.patch("/{ticket_id}/resolve", response_model=Ticket)
async def resolve_ticket(ticket_id: str, body: ResolveBody):
    """
    Stage 4: Mark ticket as resolved.
    Auto-creates a KB draft for the self-learning loop (Stage 5).
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")
        if row["status"] == "resolved":
            raise HTTPException(status_code=409, detail="Ticket is already resolved.")

        resolution  = body.resolution.strip()
        if not resolution:
            raise HTTPException(status_code=400, detail="resolution text cannot be empty.")

        resolved_at = datetime.now(timezone.utc).isoformat()

        # Stage 5: create KB draft
        from routers.kb import create_draft_internal
        ticket = _row_to_ticket(row)
        draft = create_draft_internal(
            title            = f"Resolution: {ticket.query[:60]}",
            content          = f"Q: {ticket.query}\n\nA: {resolution}",
            source_ticket_id = ticket_id,
        )

        conn.execute(
            """
            UPDATE tickets
               SET status = 'resolved',
                   resolution = ?,
                   kb_draft_id = ?,
                   resolved_at = ?
             WHERE ticket_id = ?
            """,
            (resolution, draft.draft_id, resolved_at, ticket_id),
        )

    return await get_ticket(ticket_id)
