"""
Router: /api/tickets
CRUD operations for support tickets created on low-confidence escalations.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_tickets():
    """Return all open tickets. TODO: Implement with DB layer."""
    return {"tickets": [], "message": "tickets router stub — coming soon"}


@router.post("/")
async def create_ticket(body: dict):
    """Create a new support ticket from an escalated chat query."""
    return {"message": "create ticket stub — coming soon"}


@router.patch("/{ticket_id}/resolve")
async def resolve_ticket(ticket_id: str, body: dict):
    """
    Stage 4: Mark ticket resolved + store resolution as KB draft
    for the self-learning loop (Stage 5).
    """
    return {"ticket_id": ticket_id, "message": "resolve stub — coming soon"}
