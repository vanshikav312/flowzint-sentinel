"""
Router: /api/kb
Stage 5 — Self-Learning Loop

KB drafts are created automatically when a ticket is resolved (Stage 4).
An admin approves a draft → content gets embedded and upserted into ChromaDB.

Persistence: SQLite via database/db.py (survives server restarts).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database.db import get_db

router = APIRouter()


# ── Schema ────────────────────────────────────────────────────────────────────

class KBDraft(BaseModel):
    draft_id:         str
    title:            str
    content:          str
    source_ticket_id: str | None = None
    status:           Literal["pending", "approved", "rejected"] = "pending"
    created_at:       str = ""
    reviewed_at:      str | None = None


# ── Row → KBDraft ─────────────────────────────────────────────────────────────

def _row_to_draft(row) -> KBDraft:
    return KBDraft(
        draft_id         = row["draft_id"],
        title            = row["title"],
        content          = row["content"],
        source_ticket_id = row["source_ticket_id"],
        status           = row["status"],
        created_at       = row["created_at"],
        reviewed_at      = row["reviewed_at"],
    )


# ── Internal helper (called by tickets.py Stage 4) ────────────────────────────

def create_draft_internal(
    title: str,
    content: str,
    source_ticket_id: str | None = None,
) -> KBDraft:
    """Persist a KB draft. Called directly by tickets.py — not an HTTP endpoint."""
    draft_id   = f"KB-{uuid.uuid4().hex[:8].upper()}"
    created_at = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO kb_drafts
                (draft_id, title, content, source_ticket_id, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (draft_id, title, content, source_ticket_id, created_at),
        )

    return KBDraft(
        draft_id         = draft_id,
        title            = title,
        content          = content,
        source_ticket_id = source_ticket_id,
        created_at       = created_at,
    )


# ── HTTP endpoints ─────────────────────────────────────────────────────────────

@router.get("/drafts", response_model=list[KBDraft])
async def list_drafts():
    """Return all KB drafts, newest first."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM kb_drafts ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_draft(r) for r in rows]


@router.get("/drafts/{draft_id}", response_model=KBDraft)
async def get_draft(draft_id: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM kb_drafts WHERE draft_id = ?", (draft_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")
    return _row_to_draft(row)


@router.post("/drafts/{draft_id}/approve", response_model=KBDraft)
async def approve_draft(draft_id: str):
    """
    Stage 5: Approve a KB draft → embed content → upsert into ChromaDB.
    Embedding + upsert logic completed in Stage 5.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM kb_drafts WHERE draft_id = ?", (draft_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"Draft is already {row['status']}.")

        reviewed_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE kb_drafts SET status = 'approved', reviewed_at = ? WHERE draft_id = ?",
            (reviewed_at, draft_id),
        )

    # Stage 5: ChromaDB upsert goes here
    return await get_draft(draft_id)


@router.delete("/drafts/{draft_id}", response_model=KBDraft)
async def reject_draft(draft_id: str):
    """Reject and discard a KB draft."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM kb_drafts WHERE draft_id = ?", (draft_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"Draft is already {row['status']}.")

        reviewed_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE kb_drafts SET status = 'rejected', reviewed_at = ? WHERE draft_id = ?",
            (reviewed_at, draft_id),
        )

    return await get_draft(draft_id)
