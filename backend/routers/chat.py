"""
Router: /api/chat
Handles incoming user messages → hybrid RAG → confidence routing → response.
"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/")
async def chat(body: dict):
    """
    Stage 1 + 2: Receive user query, run hybrid RAG retrieval,
    score confidence, route to answer or ticket escalation.
    TODO: Implement in next sprint.
    """
    return {"message": "chat router stub — coming soon"}
