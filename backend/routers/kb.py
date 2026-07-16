"""
Router: /api/kb
Stage 5 — Self-Learning Loop

When a ticket is resolved (Stage 4), a KB draft is automatically created here.
An admin can then approve it → the draft gets embedded and upserted into ChromaDB,
closing the self-learning loop.

create_draft_internal() is called directly by tickets.py (no HTTP round-trip).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# ── In-memory store ───────────────────────────────────────────────────────────
_DRAFTS: dict[str, "KBDraft"] = {}


# ── Schema ────────────────────────────────────────────────────────────────────

class KBDraft(BaseModel):
    draft_id:         str
    title:            str
    content:          str
    source_ticket_id: str | None = None
    status:           Literal["pending", "approved", "rejected"] = "pending"
    created_at:       str = ""
    reviewed_at:      str | None = None


# ── Internal helper (called by tickets.py Stage 4) ────────────────────────────

def create_draft_internal(
    title: str,
    content: str,
    source_ticket_id: str | None = None,
) -> KBDraft:
    """
    Create a pending KB draft from a resolved ticket resolution.
    Called directly by tickets.py — not an HTTP endpoint.
    """
    draft = KBDraft(
        draft_id=f"KB-{uuid.uuid4().hex[:8].upper()}",
        title=title,
        content=content,
        source_ticket_id=source_ticket_id,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _DRAFTS[draft.draft_id] = draft
    return draft


# ── HTTP endpoints ─────────────────────────────────────────────────────────────

@router.get("/drafts", response_model=list[KBDraft])
async def list_drafts():
    """Return all KB drafts (pending, approved, rejected), newest first."""
    return sorted(
        _DRAFTS.values(),
        key=lambda d: d.created_at,
        reverse=True,
    )


@router.get("/drafts/{draft_id}", response_model=KBDraft)
async def get_draft(draft_id: str):
    """Return a single KB draft by ID."""
    draft = _DRAFTS.get(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")
    return draft


@router.post("/drafts/{draft_id}/approve", response_model=KBDraft)
async def approve_draft(draft_id: str):
    """
    Stage 5: Approve a KB draft.
    Embeds the content and upserts it into ChromaDB (self-learning loop).
    Full embedding logic implemented in Stage 5.
    """
    draft = _DRAFTS.get(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")
    if draft.status != "pending":
        raise HTTPException(status_code=409, detail=f"Draft is already {draft.status}.")

    draft.status      = "approved"
    draft.reviewed_at = datetime.now(timezone.utc).isoformat()
    _DRAFTS[draft_id] = draft

    # Stage 5: upsert into ChromaDB will go here
    return draft


@router.delete("/drafts/{draft_id}", response_model=KBDraft)
async def reject_draft(draft_id: str):
    """Reject and discard a KB draft."""
    draft = _DRAFTS.get(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")
    if draft.status != "pending":
        raise HTTPException(status_code=409, detail=f"Draft is already {draft.status}.")

    draft.status      = "rejected"
    draft.reviewed_at = datetime.now(timezone.utc).isoformat()
    _DRAFTS[draft_id] = draft
    return draft
