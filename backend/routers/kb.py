"""
Router: /api/kb
Stage 5 — Self-Learning Loop

KB drafts are created automatically when a ticket is resolved (Stage 4).
An admin approves a draft → content gets embedded and upserted into ChromaDB.

Persistence: SQLite via database/db.py (survives server restarts).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database.db import get_db

log = logging.getLogger("kb")

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


# ── LLM article drafting (Stage 5 polish) ─────────────────────────────────────

ARTICLE_PROMPT = """You are a technical writer for a customer-support knowledge base.
Rewrite the given customer question and support engineer's resolution as a concise
help-center article.

Rules:
- Use ONLY facts stated in the resolution. Do not invent details, menus, or steps.
- Write in clear documentation style: short intro, then numbered steps or short
  paragraphs as appropriate.
- Output format, exactly:
  Line 1: TITLE: <a short descriptive article title>
  Line 2: (blank)
  Then the article body. No other commentary."""


def _polish_article(query: str, resolution: str) -> tuple[str, str] | None:
    """
    Ask the LLM to rewrite a raw Q&A pair as a clean KB article.
    Returns (title, content), or None on ANY failure — the caller then keeps
    the raw Q&A format, so ticket resolution never breaks on LLM errors.
    """
    try:
        from routers.chat import _get_groq_client, GROQ_MODEL

        completion = _get_groq_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": ARTICLE_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Customer question: {query}\n\n"
                        f"Support engineer's resolution: {resolution}"
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=512,
        )
        raw = (completion.choices[0].message.content or "").strip()

        first_line, _, body = raw.partition("\n")
        if not first_line.upper().startswith("TITLE:"):
            log.warning("Article polish: LLM output missing TITLE line — using raw Q&A.")
            return None
        title = first_line.split(":", 1)[1].strip()
        content = body.strip()
        if not title or not content:
            return None
        return title, content
    except Exception as e:
        log.warning(f"Article polish skipped (falling back to raw Q&A): {e}")
        return None


# ── Internal helper (called by tickets.py Stage 4) ────────────────────────────

def create_draft_internal(
    title: str,
    content: str,
    source_ticket_id: str | None = None,
    query: str | None = None,
    resolution: str | None = None,
) -> KBDraft:
    """
    Persist a KB draft. Called directly by tickets.py — not an HTTP endpoint.

    `title`/`content` are the raw Q&A fallback. When `query` and `resolution`
    are provided, the LLM rewrites them into documentation style first; on any
    LLM failure the raw fallback is stored instead.
    """
    if query and resolution:
        polished = _polish_article(query, resolution)
        if polished:
            p_title, p_content = polished
            title = p_title
            content = f"Original Query: {query}\n\n{p_content}"
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


def _upsert_into_kb(draft_id: str, title: str, content: str) -> None:
    """
    Stage 5 core: make an approved article retrievable by BOTH halves of
    hybrid RAG.

    1. Dense side  — split the article with the same chunker the ingest
       pipeline used (RecursiveCharacterTextSplitter, chunk_size=800,
       chunk_overlap=150), then embed each chunk and add to ChromaDB.
       Chunking is critical: storing the full article as a single document
       produces a mean-pooled embedding that is too diffuse to rank in
       dense top-k against the 30k+ fine-grained chunks already in the
       collection.  Matching the ingestion chunk size ensures self-learned
       articles compete on equal footing with existing corpus documents.

    2. Sparse side — append one entry per chunk to bm25_meta.json and
       rebuild the BM25Okapi index.  The lru_cache on _get_bm25 is cleared
       so the next chat request loads the refreshed index immediately
       without a server restart.

    Raises on failure — the caller keeps the draft 'pending' so approval
    can simply be retried.
    """
    import pickle

    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from rank_bm25 import BM25Okapi

    from routers.chat import _get_bm25, _get_vectorstore, _BM25_META, _BM25_PKL

    article_text = f"{title}\n\n{content}"
    source       = f"self-learned/{draft_id}"
    metadata     = {"source": source, "category": "self-learned"}

    # Split into chunks matching the ingestion pipeline (chunk_size=800, overlap=150)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_text(article_text)
    if not chunks:
        chunks = [article_text]

    documents = [
        Document(page_content=chunk, metadata=metadata)
        for chunk in chunks
    ]

    log.info(f"Stage 5 upsert: {len(documents)} chunk(s) for draft {draft_id}")

    # 1. Dense: embed chunks + add to the cached vectorstore singleton
    vs = _get_vectorstore()
    vs.add_documents(documents)
    # persist() is a no-op on chromadb >= 0.4 (auto-persisted) but harmless
    if hasattr(vs, "persist"):
        vs.persist()

    # 2. Sparse: one BM25 entry per chunk, rebuild index, clear lru_cache
    with open(_BM25_META, "r", encoding="utf-8") as f:
        meta = json.load(f)

    for chunk in chunks:
        meta.append(
            {
                "index":    len(meta),
                "source":   source,
                "category": "self-learned",
                "snippet":  chunk[:120].replace("\n", " "),
                "text":     chunk,
            }
        )

    tokenized = [entry["text"].lower().split() for entry in meta]
    bm25 = BM25Okapi(tokenized)

    with open(_BM25_PKL, "wb") as f:
        pickle.dump(bm25, f)
    with open(_BM25_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    _get_bm25.cache_clear()  # next retrieval reloads index + meta from disk


@router.post("/drafts/{draft_id}/approve", response_model=KBDraft)
def approve_draft(draft_id: str):
    """
    Stage 5: Approve a KB draft → embed content → upsert into ChromaDB and
    the BM25 index (self-learning loop).

    Sync endpoint (threadpool): the embedding call and BM25 rebuild are
    blocking, same rationale as the chat route.

    Order matters: the KB upsert runs BEFORE the status flip. If the upsert
    fails the draft stays 'pending' and the admin can retry — there is never
    an 'approved but not learned' state.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM kb_drafts WHERE draft_id = ?", (draft_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Draft is already {row['status']}.")

    try:
        _upsert_into_kb(draft_id, row["title"], row["content"])
    except Exception as e:
        log.error(f"Stage 5 upsert failed for draft {draft_id}: {e}")
        raise HTTPException(
            status_code=503,
            detail=(
                "Draft could not be added to the knowledge base "
                f"(still pending, retry approval): {e}"
            ),
        )

    reviewed_at = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE kb_drafts SET status = 'approved', reviewed_at = ? WHERE draft_id = ?",
            (reviewed_at, draft_id),
        )

    updated = dict(row)
    updated["status"] = "approved"
    updated["reviewed_at"] = reviewed_at
    return KBDraft(**{k: updated[k] for k in KBDraft.model_fields})


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
