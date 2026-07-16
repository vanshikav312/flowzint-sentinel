"""
Router: /api/tickets
Stage 2 — Confidence Router feeds into this module.

When chat.py determines confidence < ESCALATION_THRESHOLD, it calls
create_ticket_internal() directly to create a ticket and returns an
escalation response to the user instead of the low-confidence answer.

Stage 4 (Human Resolution) will use PATCH /{ticket_id}/resolve to
mark a ticket as resolved and store the resolution as a KB draft.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# ── In-memory store (replaced by a real DB in production) ────────────────────
# Dict[ticket_id -> Ticket]
_TICKETS: dict[str, "Ticket"] = {}


# ── Schemas ───────────────────────────────────────────────────────────────────

class Ticket(BaseModel):
    ticket_id:   str
    query:       str
    confidence:  float          # 0-100 scale (matches LLM output); stored as float to avoid truncation
    status:      Literal["open", "resolved"] = "open"
    sources:     list[dict] = []
    resolution:  str | None = None
    kb_draft_id: str | None = None          # set by Stage 5 after approval
    created_at:  str = ""
    resolved_at: str | None = None


class ResolveBody(BaseModel):
    resolution: str


# ── Internal helper (called by chat.py confidence router) ─────────────────────

def create_ticket_internal(
    query: str,
    confidence: float,
    sources: list[dict],
) -> Ticket:
    """
    Create and store a ticket from a low-confidence escalation.
    Called directly by the chat router — not an HTTP endpoint.
    """
    ticket = Ticket(
        ticket_id=f"TK-{uuid.uuid4().hex[:8].upper()}",
        query=query,
        confidence=confidence,
        sources=sources,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _TICKETS[ticket.ticket_id] = ticket
    return ticket


# ── HTTP endpoints ─────────────────────────────────────────────────────────────

@router.get("/", response_model=list[Ticket])
async def list_tickets():
    """Return all tickets (open + resolved), newest first."""
    return sorted(
        _TICKETS.values(),
        key=lambda t: t.created_at,
        reverse=True,
    )


@router.get("/{ticket_id}", response_model=Ticket)
async def get_ticket(ticket_id: str):
    """Return a single ticket by ID."""
    ticket = _TICKETS.get(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")
    return ticket


@router.post("/", response_model=Ticket)
async def create_ticket(body: dict):
    """
    Manually create a ticket (e.g. from admin dashboard).
    For automatic escalation, the chat router calls create_ticket_internal().
    """
    query = str(body.get("query", "")).strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required.")
    confidence = int(body.get("confidence", 0))
    sources = body.get("sources", [])
    ticket = create_ticket_internal(query, confidence, sources)
    return ticket


@router.patch("/{ticket_id}/resolve", response_model=Ticket)
async def resolve_ticket(ticket_id: str, body: ResolveBody):
    """
    Stage 4: Mark ticket as resolved.
    Stores the resolution text as a pending KB draft (Stage 5).
    """
    ticket = _TICKETS.get(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")
    if ticket.status == "resolved":
        raise HTTPException(status_code=409, detail="Ticket is already resolved.")

    resolution = body.resolution.strip()
    if not resolution:
        raise HTTPException(status_code=400, detail="resolution text cannot be empty.")

    ticket.status      = "resolved"
    ticket.resolution  = resolution
    ticket.resolved_at = datetime.now(timezone.utc).isoformat()

    # Stage 5 hook: create a KB draft from this resolution
    from routers.kb import create_draft_internal
    draft = create_draft_internal(
        title=f"Resolution: {ticket.query[:60]}",
        content=f"Q: {ticket.query}\n\nA: {resolution}",
        source_ticket_id=ticket.ticket_id,
    )
    ticket.kb_draft_id = draft.draft_id
    _TICKETS[ticket_id] = ticket

    return ticket
