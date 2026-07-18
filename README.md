# FlowZint Sentinel

A self-healing AI support system that combines hybrid retrieval-augmented generation, confidence-based escalation, automated incident detection, and a human-in-the-loop self-learning knowledge base — built entirely on local embeddings with no paid vector or embedding APIs.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Problem Statement](#problem-statement)
- [Solution Overview](#solution-overview)
- [Key Features](#key-features)
- [Technology Stack](#technology-stack)
- [System Architecture](#system-architecture)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Environment Variables](#environment-variables)
- [Running the Project](#running-the-project)
- [Build Instructions](#build-instructions)
- [Development Workflow](#development-workflow)
- [API Documentation](#api-documentation)
- [Database](#database)
- [Security](#security)
- [Logging](#logging)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Project Overview

FlowZint Sentinel is an AI-powered customer support system designed around the Razorpay payments ecosystem. It answers customer queries using a hybrid retrieval pipeline over a domain-specific knowledge base, automatically escalates low-confidence queries to human agents, clusters related escalations into named incidents, and feeds human resolutions back into the knowledge base so the system improves over time without retraining.

The entire retrieval stack — embeddings, vector search, and keyword matching — runs locally. The only external API call is to Groq for natural language generation, which is available on a free tier.

---

## Problem Statement

Traditional customer support systems treat every unanswered query as an independent ticket. When a payment provider experiences a systemic issue — such as a UPI gateway outage — dozens of customers may submit similar queries within minutes. Without pattern recognition, agents work these in isolation, unaware that they represent a single underlying cause. This wastes agent time, delays resolution, and degrades the customer experience.

A simple FAQ chatbot does not solve this. It either answers everything (hallucinating when knowledge is absent) or escalates everything (defeating the purpose of automation).

---

## Solution Overview

FlowZint Sentinel addresses this through a five-stage pipeline:

1. **Hybrid RAG Answer** — Retrieve relevant knowledge base chunks using both dense semantic search (sentence-transformers + ChromaDB) and sparse keyword search (BM25), fuse the results, and generate a grounded answer via an LLM.

2. **Confidence Router** — Blend the LLM's self-reported confidence with the retrieval similarity score. Answers above a calibrated threshold are returned to the customer. Answers below it are escalated.

3. **Incident Detection** — Escalated queries are clustered using centroid-based cosine similarity over stored embeddings. When a cluster of similar queries exceeds a minimum size within a rolling time window, an incident is automatically raised and surfaced to the operations team.

4. **Human Resolution** — Agents resolve tickets through the admin dashboard. Resolutions are immediately stored and used to generate a knowledge base draft article.

5. **Self-Learning Loop** — Approved KB draft articles are chunked, embedded, and upserted into both ChromaDB (dense retrieval) and the BM25 index (sparse retrieval) at runtime, with no server restart required. The system improves with every resolved ticket.

---

## Key Features

- Hybrid retrieval combining dense vector search and BM25 keyword matching, fused with Reciprocal Rank Fusion (RRF)
- Confidence blending that combines LLM self-assessment with retrieval similarity, reducing over-confident LLM responses
- Centroid-based iterative clustering for incident detection, which improves over seed-only greedy approaches by expanding clusters as the centroid shifts
- Incident deduplication using a 50% ticket-overlap rule to prevent the same event from generating multiple incident records
- Stage 3.5 pre-ticket matching: queries that match an open incident's centroid are absorbed without creating a new ticket
- Live knowledge base updates without server restart via BM25 index rebuild and LRU cache invalidation
- SQLite with WAL mode for safe concurrent read/write without a separate database server
- Fully local embeddings using `sentence-transformers` — no paid embedding API required
- Interactive admin dashboard with 15-second auto-refresh, optimistic UI for draft status, and per-item in-flight state management
- Persistent chat state with visual escalation indicators and confidence badges

---

## Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`) | Local, CPU-only, 384-dimensional output |
| Vector store | ChromaDB | Local persistence with cosine similarity (HNSW) |
| Sparse retrieval | `rank-bm25` (`BM25Okapi`) | Keyword matching, rebuilt on KB updates |
| LLM | Groq API (`llama-3.1-8b-instant`) | Answer generation and KB article drafting only |
| Backend framework | FastAPI 0.116.x + Uvicorn | Synchronous routes with ASGI lifespan hooks |
| Frontend framework | Next.js 16.2 + React 19 | App Router, TypeScript, Tailwind CSS v4 |
| Database | SQLite (stdlib `sqlite3`) | WAL journal mode, no external server |
| LangChain | `langchain`, `langchain-community`, `langchain-huggingface` | Document loaders, text splitters, embeddings wrapper |

> All embeddings are generated locally. There is no dependency on OpenAI, Cohere, or any other paid embedding provider.

---

## System Architecture

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
|  (+ 3.5)  |  Pre-ticket: match query to open incident centroid (Stage 3.5)        |
|           |  Post-ticket: centroid-based iterative clustering of recent tickets    |
|           |  Window: configurable rolling time window (default 30 minutes)        |
|           |  Deduplication: 50% ticket-overlap rule prevents duplicate incidents   |
+------------------------------------------------------------------------------------+
|  Stage 4  |  Human Resolution                                                      |
|           |  Agent resolves ticket via /admin dashboard                             |
|           |  Resolution stored as pending KB draft (LLM polishing attempted)      |
+------------------------------------------------------------------------------------+
|  Stage 5  |  Self-Learning Loop                                                    |
|           |  Admin approves draft -> chunked, embedded, upserted into ChromaDB    |
|           |  BM25 index rebuilt in-process; LRU cache cleared for next request    |
+------------------------------------------------------------------------------------+
```

### Request Flow

```
Customer query
    |
    v
POST /api/chat/
    |-- Dense retrieve (ChromaDB, top-10)
    |-- Sparse retrieve (BM25, top-10)
    |-- RRF fusion (top-5)
    |-- Embed query (384-dim, reused for stages 2+3)
    |-- LLM generation + self-reported confidence (Groq)
    |-- Confidence blending
    |
    +-- blended >= 40 --> Return answer to customer
    |
    +-- blended < 40  --> Stage 3.5: match open incident centroid?
                              |
                              +-- Match --> Attach report, return "known issue"
                              |
                              +-- No match --> Create ticket (SQLite)
                                               Auto-trigger incident scan
                                               Return escalation message
```

---

## Project Structure

```
flowzint-sentinel/
|
+-- backend/                        Python FastAPI server
|   |
|   +-- main.py                     Application entry point; registers all routers
|   +-- requirements.txt            Python dependencies (pinned where required)
|   +-- .env.example                Environment variable template
|   |
|   +-- routers/                    One file per domain
|   |   +-- chat.py                 Stage 1 + 2: RAG pipeline and confidence router
|   |   +-- tickets.py              Stage 2 + 4: ticket lifecycle and resolution
|   |   +-- incidents.py            Stage 3: incident detection and acknowledgement
|   |   +-- kb.py                   Stage 5: KB draft management and self-learning
|   |   +-- __init__.py
|   |
|   +-- database/
|   |   +-- db.py                   SQLite connection manager, schema, migrations
|   |   +-- sentinel.db             SQLite database file (gitignored, generated at runtime)
|   |   +-- razorpay_db/            ChromaDB vector store (gitignored, generated by ingest)
|   |   +-- bm25_index.pkl          Serialised BM25Okapi index (gitignored)
|   |   +-- bm25_meta.json          Chunk metadata parallel to BM25 index (gitignored)
|   |
|   +-- data/
|       +-- ingest_docs.py          One-time KB ingestion pipeline (filter, chunk, embed)
|       +-- _raw_docs/              Cloned Razorpay markdown corpus (gitignored)
|
+-- frontend/                       Next.js 16 application
|   +-- src/app/
|   |   +-- layout.tsx              Root layout with persistent top navigation bar
|   |   +-- page.tsx                Landing page with pipeline overview
|   |   +-- globals.css             Global Tailwind CSS v4 styles
|   |   +-- TopNav.tsx              Client-side nav component with active-link detection
|   |   +-- chat/
|   |   |   +-- page.tsx            Customer chat interface
|   |   +-- admin/
|   |       +-- page.tsx            Operations dashboard (tickets, incidents, KB drafts)
|   +-- package.json
|
+-- .gitignore
+-- README.md
```

---

## Prerequisites

- Python 3.9 or later
- Node.js 18 or later
- Git
- A free Groq API key from [console.groq.com](https://console.groq.com)

No GPU, Docker, or external database server is required.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/vanshikav312/flowzint-sentinel.git
cd flowzint-sentinel
```

### 2. Create and activate a Python virtual environment

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

> The first install downloads the `all-MiniLM-L6-v2` model weights (~85 MB) and ChromaDB binaries. Subsequent runs use the local cache.

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and set the required values. See [Environment Variables](#environment-variables) for details.

### 5. Build the knowledge base

The knowledge base is built from the public [Razorpay markdown-docs](https://github.com/razorpay/markdown-docs) corpus.

```bash
# Clone the raw documentation corpus (one-time)
git clone https://github.com/razorpay/markdown-docs.git data/_raw_docs

# Run the ingestion pipeline (5–15 minutes depending on hardware)
python data/ingest_docs.py

# Optional: preview which files pass the filter without embedding anything
python data/ingest_docs.py --dry-run
```

The pipeline produces three artefacts inside `backend/database/`:

| Artefact | Description |
|---|---|
| `razorpay_db/` | ChromaDB vector store with embedded document chunks |
| `bm25_index.pkl` | Serialised BM25Okapi sparse retrieval index |
| `bm25_meta.json` | Chunk metadata used for BM25 result reconstruction |

### 6. Install frontend dependencies

```bash
cd ../frontend
npm install
```

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and configure the following variables:

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | Yes | — | API key from [console.groq.com](https://console.groq.com). Used only for LLM answer generation (Stage 1) and KB article drafting (Stage 5). |
| `GROQ_MODEL` | No | `llama-3.1-8b-instant` | Groq model identifier. Alternatives: `llama-3.3-70b-versatile`. |
| `CHROMA_DB_PATH` | No | `./database` | Override the ChromaDB persistence directory. |
| `INCIDENT_WINDOW_MINUTES` | No | `30` | Rolling time window for incident detection clustering. |

> Embeddings are generated entirely locally by `sentence-transformers`. No embedding API key is needed.

---

## Running the Project

### Backend

```bash
# From backend/ with the virtual environment activated
uvicorn main:app --reload --reload-exclude "database/*" --port 8000
```

On startup, the server:
1. Calls `init_db()` to create SQLite tables if they do not exist
2. Pre-loads the embedding model, ChromaDB, BM25 index, and Groq client via the `lifespan` hook

Interactive API documentation is available at `http://localhost:8000/docs`.

### Frontend

```bash
# From frontend/ in a separate terminal
npm run dev
# Accessible at http://localhost:3000
```

The frontend expects the backend at `http://localhost:8000`. CORS is configured to allow `http://localhost:3000` only.

---

## Build Instructions

### Frontend production build

```bash
cd frontend
npm run build
npm run start
```

### Backend

FastAPI with Uvicorn does not require a separate build step. For production deployment, replace `--reload` with worker configuration:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

> Use a single worker. The embedding model, ChromaDB connection, and BM25 index are loaded as module-level singletons using `@lru_cache`. Multiple workers would each load their own copy, causing excessive memory use and potential ChromaDB file contention.

---

## Development Workflow

### Adding new knowledge base documents

1. Place new Markdown files under `backend/data/_raw_docs/` or extend the filter rules in `data/ingest_docs.py`.
2. Re-run `python data/ingest_docs.py` to rebuild ChromaDB and the BM25 index.
3. Restart the backend server to reload the updated indices.

Alternatively, for single articles, resolve a ticket through the admin dashboard and approve the generated KB draft. This upserts the article at runtime without a full re-ingestion.

### Changing the escalation threshold

Edit the `ESCALATION_THRESHOLD` constant in `backend/routers/chat.py` (default: `40`). Lower values escalate more aggressively; higher values answer more queries directly.

### Changing the incident detection threshold

Edit `SIMILARITY_THRESHOLD` in `backend/routers/incidents.py` (default: `0.50`). This is the minimum cosine similarity for two queries to be considered part of the same cluster, calibrated for `all-MiniLM-L6-v2` on payment support queries.

### Changing the incident time window

Set `INCIDENT_WINDOW_MINUTES` in `.env` (default: `30`).

---

## API Documentation

Interactive Swagger UI is available at `http://localhost:8000/docs` when the backend is running.

### Health

| Method | Path | Description |
|---|---|---|
| GET | `/` | Returns `{"status": "ok", "service": "FlowZint Sentinel"}` |

### Chat

| Method | Path | Description |
|---|---|---|
| POST | `/api/chat/` | Main pipeline endpoint. Accepts `{"query": "string"}`. Returns answer, confidence score, escalation flag, ticket ID, incident ID, and source references. |

### Tickets

| Method | Path | Description |
|---|---|---|
| GET | `/api/tickets/` | List all tickets, newest first. Embeddings excluded from response. |
| GET | `/api/tickets/stats` | Aggregate counts: open, resolved, total, average confidence. |
| GET | `/api/tickets/{ticket_id}` | Retrieve a single ticket including its stored embedding. |
| POST | `/api/tickets/` | Manually create a ticket. Also triggers incident detection. |
| PATCH | `/api/tickets/{ticket_id}/resolve` | Resolve a ticket with a resolution string. Automatically creates a KB draft. Returns 409 if already resolved, 400 if resolution is empty. |

> The `/stats` route is registered before `/{ticket_id}` to prevent FastAPI from matching the literal string `stats` as a ticket ID.

### Incidents

| Method | Path | Description |
|---|---|---|
| GET | `/api/incidents/` | List all incidents, newest first. |
| POST | `/api/incidents/detect` | Manually trigger a detection scan. Returns scan summary and any new or updated incidents. |
| GET | `/api/incidents/{incident_id}` | Retrieve a single incident. |
| PATCH | `/api/incidents/{incident_id}/acknowledge` | Acknowledge an open incident. Returns 409 if already acknowledged or resolved. |

### Knowledge Base

| Method | Path | Description |
|---|---|---|
| GET | `/api/kb/drafts` | List all KB drafts, newest first. |
| GET | `/api/kb/drafts/{draft_id}` | Retrieve a single KB draft. |
| POST | `/api/kb/drafts/{draft_id}/approve` | Approve a pending draft. Chunks, embeds, and upserts content into ChromaDB and BM25 before flipping status to `approved`. Returns 503 if the upsert fails (draft stays `pending` for retry). |
| DELETE | `/api/kb/drafts/{draft_id}` | Reject a pending draft. Sets status to `rejected`. Returns 409 if already approved or rejected. |

---

## Database

### Engine

SQLite 3 via Python's standard library `sqlite3` module. No external database server is required. The database file lives at `backend/database/sentinel.db` and is gitignored.

### Configuration

All connections use:
- `PRAGMA journal_mode=WAL` — Write-Ahead Logging allows one concurrent writer and multiple concurrent readers, eliminating "database is locked" errors under typical FastAPI concurrency.
- `PRAGMA foreign_keys=ON` — Enforces foreign key constraints.
- `row_factory = sqlite3.Row` — Rows are accessible by column name in addition to index.

### Schema

**tickets**

| Column | Type | Description |
|---|---|---|
| `ticket_id` | TEXT PK | Format: `TK-` + 8 uppercase hex characters |
| `query` | TEXT | Customer's original query |
| `confidence` | REAL | Blended confidence score at time of escalation (0–100) |
| `status` | TEXT | `open` or `resolved` |
| `sources` | TEXT | JSON array of source chunk references |
| `query_embedding` | TEXT | JSON array of 384 floats; stored at creation, reused by incident detection |
| `resolution` | TEXT | Human agent's resolution text |
| `kb_draft_id` | TEXT | Reference to the associated KB draft |
| `created_at` | TEXT | ISO-8601 UTC timestamp |
| `resolved_at` | TEXT | ISO-8601 UTC timestamp, null until resolved |

**incidents**

| Column | Type | Description |
|---|---|---|
| `incident_id` | TEXT PK | Format: `INC-` + 8 uppercase hex characters |
| `topic` | TEXT | Seed ticket query used as the incident label |
| `ticket_ids` | TEXT | JSON array of member ticket IDs |
| `ticket_count` | INTEGER | Total count including extra reports |
| `severity` | TEXT | `low` (2–4), `medium` (5–7), `high` (8–14), `critical` (15+) |
| `status` | TEXT | `open`, `acknowledged`, or `resolved` |
| `detected_at` | TEXT | ISO-8601 UTC timestamp |
| `updated_at` | TEXT | ISO-8601 UTC timestamp of last modification |
| `similarity_threshold` | REAL | Threshold in effect when the incident was created |
| `extra_reports` | INTEGER | Queries absorbed without creating a new ticket (Stage 3.5) |

**kb_drafts**

| Column | Type | Description |
|---|---|---|
| `draft_id` | TEXT PK | Format: `KB-` + 8 uppercase hex characters |
| `title` | TEXT | Article title (LLM-generated or raw fallback) |
| `content` | TEXT | Article body |
| `source_ticket_id` | TEXT | Reference to the ticket that triggered this draft |
| `status` | TEXT | `pending`, `approved`, or `rejected` |
| `created_at` | TEXT | ISO-8601 UTC timestamp |
| `reviewed_at` | TEXT | ISO-8601 UTC timestamp when approved or rejected |

### Migrations

The `init_db()` function uses `CREATE TABLE IF NOT EXISTS` for initial schema creation and an explicit `ALTER TABLE ... ADD COLUMN` wrapped in a `try/except OperationalError` block for additive column migrations. This pattern handles databases created before a column was added without requiring a migration framework.

---

## Security

### Secrets management

- The `.env` file is gitignored. Never commit `GROQ_API_KEY` or any other secret to version control.
- The `.env.example` file documents required variables with placeholder values only.

### CORS

The backend restricts cross-origin requests to `http://localhost:3000` only. For production deployment, update the `allow_origins` list in `main.py` to the actual frontend domain.

### Input validation

All request bodies are validated by Pydantic models before reaching route handlers. Empty or whitespace-only query strings are rejected with HTTP 400 before any retrieval or LLM call is made.

### No authentication

The current implementation does not include authentication or authorisation. All endpoints are publicly accessible on the local network. For any non-local deployment, add an authentication layer (e.g. Bearer token middleware or an API gateway) before exposing the admin endpoints.

---

## Logging

The backend uses Python's standard `logging` module. Each router configures a named logger:

| Logger name | Router |
|---|---|
| `chat` | `routers/chat.py` |
| `tickets` | `routers/tickets.py` |
| `incidents` | `routers/incidents.py` |
| `kb` | `routers/kb.py` |
| `ingest` | `data/ingest_docs.py` |

Log output is written to stdout. Uvicorn's access log records every HTTP request. To adjust verbosity, set the `--log-level` flag when starting Uvicorn:

```bash
uvicorn main:app --log-level warning --port 8000
```

No structured logging or centralised log aggregation is configured in the current version.

---

## Testing

The test suite is located in the `backend/` directory.

> Note: The test files were removed from the main branch after the latest refactor. If they are present in your working tree, run them as follows.

### Stage 3 integration test (`test_stage3.py`)

Runs against the real application stack including the actual SQLite database and embedding model. Uses FastAPI's `TestClient` (no network required).

```bash
# From backend/ with the virtual environment activated
python test_stage3.py
```

Covers:
- Ticket creation and storage
- Automatic incident detection after ticket creation
- Deduplication (repeated scans do not create duplicate incidents)
- Centroid expansion pulling in tickets that fall below the seed similarity threshold
- Time-window filtering
- SQLite persistence verification
- Stored embedding reuse

### Stage 4 unit test suite (`test_stage4.py`)

Uses `unittest.TestCase` with an in-memory SQLite database. Heavy ML components (embedding model, ChromaDB) are stubbed out. Runs in under 10 seconds with no model downloads required.

```bash
python test_stage4.py
```

Covers:
- Ticket resolution (valid, already resolved, empty resolution, non-existent)
- KB draft auto-creation on resolution
- Ticket statistics aggregation
- Draft approval and rejection with appropriate HTTP status codes (409 on duplicate)

---

## Troubleshooting

**Backend fails to start with `ModuleNotFoundError`**

Ensure the virtual environment is activated before running Uvicorn:
```bash
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

**`database is locked` errors**

This occurs when multiple Uvicorn workers share the same SQLite file without WAL mode. Ensure you are running with `--workers 1`. WAL mode is enabled on every connection but does not fully protect against concurrent writers in separate processes.

**`chromadb` or `razorpay_db` not found**

The knowledge base ingestion script must be run at least once before starting the server:
```bash
python data/ingest_docs.py
```

**`GROQ_API_KEY` not set or invalid**

The server starts without the key but LLM calls will fail at request time. Check that `backend/.env` exists and contains a valid key from [console.groq.com](https://console.groq.com).

**Frontend shows "Backend unreachable"**

Ensure the backend is running on port 8000 and that no firewall is blocking `localhost:8000`. The frontend hardcodes `http://localhost:8000` as the API base URL.

**`groq` version conflicts**

The project pins `groq==1.5.0`. Installing a newer version may cause API compatibility issues. If you have a different version installed, reinstall from `requirements.txt`:
```bash
pip install -r requirements.txt --force-reinstall
```

**Low confidence scores across all queries**

If all queries return low confidence scores, the ChromaDB collection may be empty or the BM25 index may not exist. Re-run the ingestion script. Use `--dry-run` first to confirm the file filter is selecting documents.

**KB draft approval returns 503**

The upsert into ChromaDB or BM25 failed. Check the backend logs for the specific error. The draft status remains `pending`, so approval can be retried after resolving the underlying issue.



## License

This project was developed as a hackathon submission. No explicit open-source license has been applied. All rights are reserved by the authors unless a license file is added to the repository.
