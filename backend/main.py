"""
FlowZint Sentinel — FastAPI Entrypoint
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# Initialise SQLite tables (no-op if they already exist)
from database.db import init_db
init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-load the embedding model, ChromaDB, BM25 index and Groq client
    # so the first chat request answers instantly instead of lazy-loading.
    from routers.chat import warmup
    warmup()
    yield


app = FastAPI(
    title="FlowZint Sentinel",
    description="Self-healing AI support bot with hybrid RAG and confidence routing.",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow the Next.js frontend (dev) to talk to the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routers import chat, tickets, incidents, kb

app.include_router(chat.router,      prefix="/api/chat",      tags=["Chat"])
app.include_router(tickets.router,   prefix="/api/tickets",   tags=["Tickets"])
app.include_router(incidents.router, prefix="/api/incidents", tags=["Incidents"])
app.include_router(kb.router,        prefix="/api/kb",        tags=["Knowledge Base"])


@app.get("/", tags=["Health"])
async def health_check():
    """Root health-check — confirms the API is running."""
    return {"status": "ok", "service": "FlowZint Sentinel"}
