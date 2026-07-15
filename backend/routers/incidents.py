"""
Router: /api/incidents
Incident detection via query clustering — fires alerts when repeated
low-confidence topics spike above threshold.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_incidents():
    """Return all detected incidents. TODO: Implement clustering logic."""
    return {"incidents": [], "message": "incidents router stub — coming soon"}


@router.post("/detect")
async def run_detection():
    """
    Stage 3: Trigger manual incident detection scan.
    Normally runs on a schedule or after each ticket escalation.
    """
    return {"message": "incident detection stub — coming soon"}
