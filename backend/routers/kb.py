"""
Router: /api/kb
Knowledge Base management — list drafts, approve/reject drafts,
trigger embedding upsert into ChromaDB (self-learning loop).
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/drafts")
async def list_drafts():
    """Return all pending KB article drafts awaiting admin approval."""
    return {"drafts": [], "message": "kb drafts stub — coming soon"}


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(draft_id: str):
    """
    Stage 5: Approve a KB draft → embed it → upsert into ChromaDB.
    This closes the self-learning loop.
    """
    return {"draft_id": draft_id, "message": "approve draft stub — coming soon"}


@router.delete("/drafts/{draft_id}")
async def reject_draft(draft_id: str):
    """Reject and discard a KB draft."""
    return {"draft_id": draft_id, "message": "reject draft stub — coming soon"}
