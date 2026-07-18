# FlowZint Sentinel

A self-healing AI support system that combines hybrid retrieval-augmented generation, confidence-based escalation, automated incident detection, and a human-in-the-loop self-learning knowledge base — built entirely on local embeddings with no paid vector or embedding APIs.

📹 **Video demo:** [Google Drive folder](https://drive.google.com/drive/folders/1Z8BvsZ4QJiRSqps7YjkpiRzUwdHq0w-V)

---

## The Demo Loop (3 minutes)

One continuous story, every stage of the pipeline on screen:

1. **Known question** — customer asks "my payment failed but money was deducted" → instant, grounded answer with cited sources.
2. **Unknown question** — a query the docs don't cover → the bot refuses to bluff, escalates, and a ticket appears on the admin dashboard.
3. **Two more similar complaints** (different wording) → the system connects the dots: an **incident** is raised automatically with severity and all linked tickets.
4. **A fourth similar complaint** → no new ticket. The customer is told *"this issue is already known — our team is on it (ref: INC-…)"* and the report is counted under the incident.
5. **Human resolution** — an agent resolves the ticket in one sentence; the LLM rewrites it into a clean documentation article.
6. **Approve** — one click; the article is chunked, embedded, and added to both retrieval indexes live (no restart).
7. **Ask the original question again** — instant, confident answer, citing the article the system just wrote for itself.

---

## Problem

Traditional support systems treat every unanswered query as an independent ticket. When a platform-wide issue hits — a UPI gateway outage, a checkout bug — dozens of customers report the same problem in different words within minutes. Agents work them in isolation, unaware they share one root cause. And a plain FAQ chatbot doesn't help: it either hallucinates when knowledge is missing, or escalates everything.

## Solution — Five-Stage Pipeline

1. **Hybrid RAG Answer** — dense semantic search (sentence-transformers + ChromaDB) and sparse keyword search (BM25) run in parallel, fused with Reciprocal Rank Fusion; the LLM answers only from retrieved context.
2. **Confidence Router** — blends LLM self-reported confidence with retrieval similarity (`0.4 × LLM + 0.6 × top_similarity × 100`). Above 40: answer. Below: escalate — the bot never bluffs.
3. **Incident Detection** — escalated queries are clustered by centroid-based cosine similarity over stored embeddings within a rolling 30-minute window. A cluster crossing the threshold raises an incident. New queries matching an open incident are absorbed without creating duplicate tickets.
4. **Human Resolution** — agents resolve tickets on the admin dashboard; each resolution is rewritten by the LLM into a documentation-style KB draft.
5. **Self-Learning Loop** — approved drafts are chunked, embedded, and upserted into ChromaDB **and** the BM25 index at runtime. The system answers that question itself from then on.

---

## Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`) | Local, CPU-only, 384-dim |
| Vector store | ChromaDB | Local persistence, cosine/HNSW |
| Sparse retrieval | `rank-bm25` (`BM25Okapi`) | Rebuilt live on KB updates |
| LLM | Groq API (`llama-3.1-8b-instant`) | Answer generation + article drafting only |
| Backend | FastAPI + Uvicorn | Blocking ML routes run in the threadpool |
| Frontend | Next.js 16 + React 19 + Tailwind v4 | App Router, TypeScript |
| Database | SQLite (stdlib) | WAL mode, no external server |

> All embeddings are generated locally. The only external API is Groq's free tier.

---

## Architecture

```
+------------------------------------------------------------------------------------+
|  Stage 1  |  Hybrid RAG Answer                                                     |
|           |  Dense retrieval  : sentence-transformers + ChromaDB (cosine/HNSW)     |
|           |  Sparse retrieval : BM25Okapi over tokenised chunk corpus              |
|           |  Fusion           : Reciprocal Rank Fusion (RRF, k=60), top-5 chunks  |
|           |  Generation       : Groq LLM conditioned on fused context              |
+------------------------------------------------------------------------------------+
|  Stage 2  |  Confidence Router                                                     |
|           |  blended = 0.4 * LLM_confidence + 0.6 * top_dense_similarity * 100   |
|           |  blended >= 40  ->  return answer to customer                          |
|           |  blended <  40  ->  escalate                                           |
+------------------------------------------------------------------------------------+
|  Stage 3  |  Incident Detection                                                    |
|  (+ 3.5)  |  Pre-ticket: match query to open incident centroid -> absorb report   |
|           |  Post-ticket: centroid-based iterative clustering of recent tickets    |
|           |  Rolling window (default 30 min) + 50% overlap deduplication          |
+------------------------------------------------------------------------------------+
|  Stage 4  |  Human Resolution                                                      |
|           |  Agent resolves ticket via /admin -> LLM drafts a KB article          |
+------------------------------------------------------------------------------------+
|  Stage 5  |  Self-Learning Loop                                                    |
|           |  Approve -> chunk, embed, upsert into ChromaDB + rebuild BM25 (live)  |
+------------------------------------------------------------------------------------+
```

---

## Project Structure

```
flowzint-sentinel/
+-- backend/                  FastAPI server
|   +-- main.py               Entry point, router registration, startup warmup
|   +-- routers/
|   |   +-- chat.py           Stage 1+2: RAG pipeline and confidence router
|   |   +-- tickets.py        Stage 2+4: ticket lifecycle and resolution
|   |   +-- incidents.py      Stage 3: incident detection and acknowledgement
|   |   +-- kb.py             Stage 5: KB drafts and self-learning upsert
|   +-- database/db.py        SQLite schema, connections, migrations
|   +-- data/ingest_docs.py   One-time KB ingestion (filter, chunk, embed)
|   +-- test_stage3.py        Stage 3 integration tests (real stack)
|   +-- test_stage4.py        Stage 4 unit tests (isolated, in-memory DB)
+-- frontend/src/app/         Next.js: landing page, /chat widget, /admin dashboard
```

---

## Quick Start

**Prerequisites:** Python 3.9+, Node.js 18+, Git, a free Groq API key from [console.groq.com](https://console.groq.com). No GPU, Docker, or external database needed.

```bash
# 1. Clone
git clone https://github.com/vanshikav312/flowzint-sentinel.git
cd flowzint-sentinel/backend

# 2. Python environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure (set GROQ_API_KEY in .env)
cp .env.example .env

# 4. Build the knowledge base (one-time, ~5-15 min)
git clone https://github.com/razorpay/markdown-docs.git data/_raw_docs
python data/ingest_docs.py        # add --dry-run to preview the file filter

# 5. Run the backend
uvicorn main:app --reload --reload-exclude "database/*" --port 8000

# 6. Run the frontend (separate terminal)
cd ../frontend
npm install
npm run dev                       # -> http://localhost:3000
```

Interactive API docs: `http://localhost:8000/docs`. On startup the server pre-loads the embedding model, ChromaDB, BM25 index, and Groq client, so the first question answers instantly.

> Run the backend with a **single worker** — the model, ChromaDB, and BM25 index are in-process singletons.

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | Yes | — | Used only for answer generation and KB article drafting |
| `GROQ_MODEL` | No | `llama-3.1-8b-instant` | Alternative: `llama-3.3-70b-versatile` |
| `INCIDENT_WINDOW_MINUTES` | No | `30` | Rolling window for incident clustering |

Tuning constants live in code: `ESCALATION_THRESHOLD` (chat.py, default 40) and `SIMILARITY_THRESHOLD` (incidents.py, default 0.50).

---

## API Overview

Full interactive documentation at `http://localhost:8000/docs`.

| Method | Path | Description |
|---|---|---|
| POST | `/api/chat/` | Main pipeline: query → answer or escalation (returns confidence, ticket/incident refs, sources) |
| GET | `/api/tickets/` | List tickets (embeddings excluded) |
| GET | `/api/tickets/stats` | Open / resolved / total counts, average confidence |
| PATCH | `/api/tickets/{id}/resolve` | Resolve a ticket → auto-creates an LLM-drafted KB article |
| GET | `/api/incidents/` | List detected incidents |
| POST | `/api/incidents/detect` | Manually trigger a detection scan |
| PATCH | `/api/incidents/{id}/acknowledge` | Acknowledge an open incident |
| GET | `/api/kb/drafts` | List KB drafts |
| POST | `/api/kb/drafts/{id}/approve` | Approve → chunk, embed, upsert into both indexes (503 keeps it pending for retry) |
| DELETE | `/api/kb/drafts/{id}` | Reject a pending draft |

**Storage:** SQLite with three tables — `tickets` (including a stored 384-dim query embedding per ticket), `incidents` (cluster members, severity, extra absorbed reports), and `kb_drafts`. WAL journal mode; additive column migrations via guarded `ALTER TABLE`.

---

## Testing

```bash
# From backend/ with the venv active:
python test_stage4.py    # 10 unit tests, isolated in-memory DB, no ML loaded, <10s
python test_stage3.py    # end-to-end integration: real model, clustering, persistence
```

> ⚠️ `test_stage3.py` clears all tickets, incidents, and drafts from the local dev database by design. Don't run it right before a demo.

---

## Troubleshooting

- **`razorpay_db` not found / all confidences near zero** — run `python data/ingest_docs.py` once before starting the server.
- **LLM calls fail at request time** — `GROQ_API_KEY` missing or invalid in `backend/.env`; the server still boots without it.
- **`ModuleNotFoundError` on startup** — activate the virtual environment first.
- **Frontend shows "backend unreachable"** — the backend must be on port 8000; CORS allows `http://localhost:3000` only.
- **`groq` install fails on Python 3.9** — requirements use `groq>=1.0,<2` because groq ≥ 1.1 requires Python ≥ 3.10; the range resolves correctly on both.

---

## Security Notes

- Secrets live only in the gitignored `.env`; `.env.example` contains placeholders.
- No authentication is implemented — all endpoints are open on the local network. Add an auth layer before any non-local deployment.
- All request bodies are validated with Pydantic; empty queries are rejected before any model call.

---

## License

Hackathon submission — all rights reserved by the authors unless a license file is added.
