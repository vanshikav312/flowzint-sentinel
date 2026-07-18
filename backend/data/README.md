# Data directory

Holds the raw knowledge base corpus and the ingestion pipeline.

## Contents

- `ingest_docs.py` — filters, chunks, embeds (local sentence-transformers), and persists
  the KB into ChromaDB + a BM25 keyword index under `backend/database/`.
- `_raw_docs/` — the Razorpay docs corpus (gitignored). Clone it once:

  ```bash
  git clone https://github.com/razorpay/markdown-docs.git backend/data/_raw_docs
  ```

## Usage

```bash
# From backend/ (with the venv active):
python data/ingest_docs.py            # full ingestion
python data/ingest_docs.py --dry-run  # preview which files pass the filter
```

Re-run after adding or changing raw docs. Outputs in `backend/database/` are gitignored
and always regenerated locally.
