# FlowZint Sentinel

**A self-healing AI support bot with hybrid RAG, confidence routing, incident detection, and a self-learning knowledge loop — powered entirely by local/free embeddings.**

---

## Architecture (5-Stage Pipeline)

```
+---------------------------------------------------------------------------+
|  Stage 1  |  Hybrid RAG Answer                                            |
|           |  Dense (sentence-transformers) + Sparse (BM25) retrieval      |
|           |  fused context -> LLM generates candidate answer              |
+---------------------------------------------------------------------------+
|  Stage 2  |  Confidence Router                                            |
|           |  Score answer confidence. High -> return to user.             |
|           |  Low  -> escalate to human agent / create ticket.             |
+---------------------------------------------------------------------------+
|  Stage 3  |  Incident Detection                                           |
|           |  Cluster repeated low-confidence queries.                     |
|           |  Spike detected -> fire incident alert to admin.              |
+---------------------------------------------------------------------------+
|  Stage 4  |  Human Resolution                                             |
|           |  Agent resolves ticket via /admin dashboard.                  |
|           |  Resolution stored as a pending KB draft.                     |
+---------------------------------------------------------------------------+
|  Stage 5  |  Self-Learning Loop                                           |
|           |  Approved drafts are embedded and upserted into ChromaDB.     |
|           |  Bot improves with every resolved incident.                   |
+---------------------------------------------------------------------------+
```

---

## Project Structure

```
flowzint-sentinel/
├── backend/
│   ├── data/           # Raw docs + ingestion scripts
│   ├── database/       # ChromaDB persistence (gitignored — generated locally)
│   ├── routers/        # FastAPI route handlers
│   │   ├── chat.py
│   │   ├── tickets.py
│   │   ├── incidents.py
│   │   └── kb.py
│   ├── main.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/           # Next.js App Router (chat widget + admin dashboard)
├── .gitignore
└── README.md
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Embeddings | `sentence-transformers` (local, free, no API key) |
| Vector DB | ChromaDB (local persistence) |
| Sparse Retrieval | BM25 via `rank-bm25` |
| LLM (answer gen) | Groq API (free tier) — see `.env.example` |
| Backend | FastAPI + Uvicorn |
| Frontend | Next.js 16 (App Router) + React 19 + Tailwind CSS v4 |

> All embeddings are 100% local. No OpenAI dependency anywhere in the pipeline.

---

## Setup Instructions

### 1. Clone the repo
```bash
git clone https://github.com/vanshikav312/flowzint-sentinel.git
cd flowzint-sentinel
```

### 2. Set up the Python backend
```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env and fill in your GROQ_API_KEY (free tier at console.groq.com)
```

### 4. Download the raw docs and run the knowledge base ingestion script
```bash
# One-time: clone the Razorpay docs corpus that the KB is built from
git clone https://github.com/razorpay/markdown-docs.git data/_raw_docs

# Populates backend/database/ with ChromaDB vectors + BM25 index
# (run once, or after new docs are added; add --dry-run to preview the file filter)
python data/ingest_docs.py
```

### 5. Start the backend server
```bash
uvicorn main:app --reload --reload-exclude "database/*" --port 8000
```

### 6. Start the frontend (separate terminal)
```bash
cd ../frontend
npm install
npm run dev
# -> http://localhost:3000
```

---

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | Yes | LLM answer generation + KB article drafting only |

> Embeddings are generated locally using `sentence-transformers` — no paid API key needed for search/retrieval.

---

## Hackathon Notes

- Vector DB is always regenerated locally via `data/ingest_docs.py` — the `backend/database/` folder is gitignored.
- The self-learning loop writes new KB articles back into ChromaDB automatically after human approval.
- Incident detection is threshold-based clustering, no external service required.
