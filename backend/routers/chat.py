"""
Router: /api/chat
Stage 1 — Hybrid RAG Answer Pipeline

Flow:
    user query
        ├── Dense retrieval  → ChromaDB (sentence-transformers cosine similarity)
        ├── Sparse retrieval → BM25 keyword index
        ↓
    Reciprocal Rank Fusion  (merges both ranked lists)
        ↓
    Top-k context chunks
        ↓
    Groq LLM  →  natural-language answer
        ↓
    Response  { answer, confidence, sources, escalate }

Stage 2 (confidence routing) stub is included but not wired — that comes next.
"""

from __future__ import annotations

import os
import json
import pickle
import pathlib
import logging
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger("chat")

router = APIRouter()

# ── Paths ─────────────────────────────────────────────────────────────────────
_BACKEND_DIR = pathlib.Path(__file__).parent.parent.resolve()
_DB_DIR      = _BACKEND_DIR / "database"
_CHROMA_DIR  = _DB_DIR / "razorpay_db"
_BM25_PKL    = _DB_DIR / "bm25_index.pkl"
_BM25_META   = _DB_DIR / "bm25_meta.json"

# ── Retrieval config ──────────────────────────────────────────────────────────
DENSE_TOP_K  = 10   # candidates from ChromaDB
SPARSE_TOP_K = 10   # candidates from BM25
FUSION_TOP_K = 5    # final chunks sent to LLM after RRF fusion
RRF_K        = 60   # RRF constant (standard value)

# ── LLM config ────────────────────────────────────────────────────────────────
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

SYSTEM_PROMPT = """You are FlowZint Sentinel, a helpful customer support AI for Razorpay.
Answer the user's question using ONLY the provided context chunks.
If the context does not contain enough information to answer confidently, say so clearly.
Be concise, factual, and friendly. Do not hallucinate.
After your answer, on a new line output exactly: CONFIDENCE: <number 0-100>
where the number reflects how well the context supported your answer (100 = perfect match, 0 = no relevant context)."""


# ── Lazy-loaded singletons ────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_embeddings():
    from langchain_huggingface import HuggingFaceEmbeddings
    log.info("Loading sentence-transformers embedding model …")
    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


@lru_cache(maxsize=1)
def _get_vectorstore():
    from langchain_community.vectorstores import Chroma
    if not _CHROMA_DIR.exists():
        raise RuntimeError(
            f"ChromaDB not found at {_CHROMA_DIR}. "
            "Run: python data/ingest_docs.py"
        )
    log.info(f"Loading ChromaDB from {_CHROMA_DIR} …")
    return Chroma(
        persist_directory=str(_CHROMA_DIR),
        embedding_function=_get_embeddings(),
        collection_name="razorpay_kb",
    )


@lru_cache(maxsize=1)
def _get_bm25() -> tuple[Any, list[dict]]:
    """Returns (BM25Okapi instance, metadata list)."""
    if not _BM25_PKL.exists() or not _BM25_META.exists():
        raise RuntimeError(
            f"BM25 index not found at {_BM25_PKL}. "
            "Run: python data/ingest_docs.py"
        )
    log.info(f"Loading BM25 index from {_BM25_PKL} …")
    with open(_BM25_PKL, "rb") as f:
        bm25 = pickle.load(f)
    with open(_BM25_META, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return bm25, meta


@lru_cache(maxsize=1)
def _get_groq_client():
    from groq import Groq
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set in .env")
    return Groq(api_key=api_key)


def warmup() -> None:
    """
    Pre-load all heavy singletons at server startup so the first chat request
    doesn't pay ~10s of lazy loading. Missing index/key is logged, not fatal —
    the server must still boot before ingestion has been run.
    """
    for loader in (_get_embeddings, _get_vectorstore, _get_bm25, _get_groq_client):
        try:
            loader()
        except Exception as e:
            log.warning(f"Warmup: {loader.__name__} skipped — {e}")


# ── Retrieval helpers ─────────────────────────────────────────────────────────

def _dense_retrieve(query: str) -> list[tuple[str, dict, float]]:
    """
    Query ChromaDB for top DENSE_TOP_K chunks.
    Returns list of (text, metadata, similarity_score).
    Score is cosine similarity — higher is better.
    """
    vs = _get_vectorstore()
    results = vs.similarity_search_with_score(query, k=DENSE_TOP_K)
    # results: list of (Document, score) — score is cosine distance (lower = closer)
    # Convert distance → similarity: similarity = 1 - distance
    return [
        (doc.page_content, doc.metadata, 1.0 - float(score))
        for doc, score in results
    ]


def _sparse_retrieve(query: str) -> list[tuple[str, dict, float]]:
    """
    Query BM25 index for top SPARSE_TOP_K chunks.
    Returns list of (text, metadata, bm25_score).
    """
    bm25, meta = _get_bm25()
    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)

    # Get indices of top-k scores
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:SPARSE_TOP_K]

    results = []
    for idx in top_indices:
        if scores[idx] > 0:
            m = meta[idx]
            results.append((m["text"], {"source": m["source"], "category": m["category"]}, float(scores[idx])))
    return results


def _reciprocal_rank_fusion(
    dense_results: list[tuple[str, dict, float]],
    sparse_results: list[tuple[str, dict, float]],
) -> list[tuple[str, dict, float]]:
    """
    Merge dense and sparse ranked lists using Reciprocal Rank Fusion.
    RRF score = sum of 1 / (k + rank) across all lists a doc appears in.
    Returns top FUSION_TOP_K chunks sorted by RRF score descending.
    """
    rrf_scores: dict[str, float] = {}
    doc_store:  dict[str, tuple[str, dict]] = {}  # text_key → (text, metadata)

    def _key(text: str) -> str:
        # Use first 120 chars as a stable dedup key
        return text[:120].strip()

    # Score from dense list
    for rank, (text, meta, _score) in enumerate(dense_results, start=1):
        k = _key(text)
        rrf_scores[k] = rrf_scores.get(k, 0.0) + 1.0 / (RRF_K + rank)
        doc_store[k] = (text, meta)

    # Score from sparse list
    for rank, (text, meta, _score) in enumerate(sparse_results, start=1):
        k = _key(text)
        rrf_scores[k] = rrf_scores.get(k, 0.0) + 1.0 / (RRF_K + rank)
        doc_store[k] = (text, meta)

    # Sort by fused score
    sorted_keys = sorted(rrf_scores, key=lambda k: rrf_scores[k], reverse=True)

    fused = []
    for k in sorted_keys[:FUSION_TOP_K]:
        text, meta = doc_store[k]
        fused.append((text, meta, rrf_scores[k]))

    return fused


# ── LLM answer generation ─────────────────────────────────────────────────────

def _build_context_block(chunks: list[tuple[str, dict, float]]) -> str:
    """Format retrieved chunks into a readable context block for the LLM."""
    parts = []
    for i, (text, meta, score) in enumerate(chunks, start=1):
        source = meta.get("source", "unknown")
        category = meta.get("category", "")
        parts.append(f"[{i}] (source: {source} | category: {category})\n{text.strip()}")
    return "\n\n---\n\n".join(parts)


def _call_groq(query: str, context: str) -> tuple[str, float]:
    """
    Call Groq LLM with context + query.
    Returns (answer_text, confidence_score 0-100 as float).
    """
    client = _get_groq_client()
    user_message = f"Context:\n{context}\n\nQuestion: {query}"

    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.2,
        max_tokens=512,
    )

    raw = completion.choices[0].message.content or ""

    # Parse CONFIDENCE: <number> from the last line
    # Default is 0.0 (fail-safe): if the LLM omits the line, escalate rather than ship unvetted answer
    confidence: float = 0.0
    answer = raw.strip()

    lines = raw.strip().splitlines()
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.upper().startswith("CONFIDENCE:"):
            try:
                parsed = float(stripped.split(":", 1)[1].strip().split()[0])
                confidence = max(0.0, min(100.0, parsed))
                # Remove that line from the answer
                answer = "\n".join(
                    l for l in lines if not l.strip().upper().startswith("CONFIDENCE:")
                ).strip()
            except (ValueError, IndexError):
                pass
            break

    return answer, confidence


# ── Request / Response schemas ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str


class SourceRef(BaseModel):
    source: str
    category: str
    rrf_score: float


class ChatResponse(BaseModel):
    answer: str
    confidence: float             # 0-100 scale from LLM
    escalate: bool                # True if confidence < 40
    ticket_id: str | None = None  # set when escalated (Stage 2)
    sources: list[SourceRef]


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/", response_model=ChatResponse)
def chat(body: ChatRequest):
    """
    Stage 1: Hybrid RAG answer pipeline.
    Dense (ChromaDB) + Sparse (BM25) → RRF fusion → Groq LLM → response.

    Deliberately sync (no `async`): the embedding model and the Groq HTTP call
    are blocking, so FastAPI must run this in its threadpool to avoid stalling
    the event loop for concurrent users.
    """
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    log.info(f"Query: {query!r}")

    # 1. Retrieve
    try:
        dense_results  = _dense_retrieve(query)
        sparse_results = _sparse_retrieve(query)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    log.info(f"Dense hits: {len(dense_results)} | Sparse hits: {len(sparse_results)}")

    # Capture top dense similarity score for confidence blending (Bug 2 fix)
    # dense_results are (text, meta, similarity) where similarity = 1 - cosine_distance
    top_dense_similarity = dense_results[0][2] if dense_results else 0.0

    # Capture query embedding now (cheapest moment — model already loaded)
    # Used by Stage 3 clustering on tickets
    try:
        query_embedding: list[float] = _get_embeddings().embed_query(query)
    except Exception:
        query_embedding = []

    # 2. Fuse
    fused = _reciprocal_rank_fusion(dense_results, sparse_results)
    log.info(f"Fused top-{FUSION_TOP_K} chunks selected")

    if not fused:
        from routers.tickets import create_ticket_internal
        ticket = create_ticket_internal(
            query           = query,
            confidence      = 0.0,
            sources         = [],
            query_embedding = query_embedding,
        )
        return ChatResponse(
            answer=(
                "I couldn't find any relevant information for your question. "
                f"Your query has been escalated to a human agent (Ticket: {ticket.ticket_id})."
            ),
            confidence=0.0,
            escalate=True,
            ticket_id=ticket.ticket_id,
            sources=[],
        )

    # 3. Build context + call LLM
    context = _build_context_block(fused)
    try:
        answer, confidence = _call_groq(query, context)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        # Groq rate limits (RateLimitError), network failures (APIConnectionError),
        # and other groq.APIError subclasses all land here.
        # Safe failure: escalate rather than surface a raw 500.
        log.warning(f"Groq API error: {e}")
        from routers.tickets import create_ticket_internal
        ticket = create_ticket_internal(
            query           = query,
            confidence      = 0.0,
            sources         = [],
            query_embedding = query_embedding,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"The AI service is temporarily unavailable (rate limit or network error). "
                f"Your query has been escalated (Ticket: {ticket.ticket_id})."
            ),
        )

    log.info(f"LLM confidence: {confidence} | Top dense similarity: {top_dense_similarity:.3f}")

    # Blend: 40% LLM self-reported + 60% retrieval similarity (scaled to 0-100)
    # This prevents small models from faking high confidence on irrelevant queries.
    blended_confidence = round(0.4 * confidence + 0.6 * top_dense_similarity * 100, 1)
    log.info(f"Blended confidence: {blended_confidence}")

    # 4. Build source refs
    sources = [
        SourceRef(
            source=meta.get("source", ""),
            category=meta.get("category", ""),
            rrf_score=round(score, 4),
        )
        for _text, meta, score in fused
    ]

    # ── Stage 2: Confidence Router ────────────────────────────────────────────
    ESCALATION_THRESHOLD = 40
    escalate = blended_confidence < ESCALATION_THRESHOLD

    ticket_id = None
    if escalate:
        from routers.tickets import create_ticket_internal
        ticket = create_ticket_internal(
            query           = query,
            confidence      = blended_confidence,
            sources         = [s.model_dump() for s in sources],
            query_embedding = query_embedding,
        )
        ticket_id = ticket.ticket_id
        log.info(f"Blended confidence {blended_confidence} below threshold — escalated to {ticket_id}")

        # ── Stage 3 hook ──────────────────────────────────────────────────────
        # Auto-trigger incident detection immediately after a new escalation
        # ticket is created (Option A: auto-trigger).  Kept inside a try/except
        # so that any detection failure is logged as a non-fatal warning and
        # the escalation response is always returned to the user.
        try:
            from routers.incidents import detect_incidents_internal
            detect_incidents_internal()
        except Exception as _inc_err:
            log.warning(f"Stage 3 incident detection skipped after ticket creation: {_inc_err}")

        return ChatResponse(
            answer=(
                "I'm not confident enough to answer this accurately. "
                f"Your query has been escalated to a human agent (Ticket: {ticket_id}). "
                "You will receive a response shortly."
            ),
            confidence=blended_confidence,
            escalate=True,
            ticket_id=ticket_id,
            sources=sources,
        )

    return ChatResponse(
        answer=answer,
        confidence=blended_confidence,
        escalate=False,
        ticket_id=None,
        sources=sources,
    )
