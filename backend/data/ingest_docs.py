"""
FlowZint Sentinel — Knowledge Base Ingestion Pipeline
======================================================
Clones razorpay/markdown-docs (already done into _raw_docs/),
filters support-relevant content, chunks by markdown headers,
embeds locally with sentence-transformers, persists to ChromaDB,
and builds a BM25 keyword index.

100% free — zero paid API calls.

Usage:
    python backend/data/ingest_docs.py
"""

import os
import sys
import json
import pickle
import pathlib
import logging
from typing import List, Tuple

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest")

# ── Paths (relative to this script's directory) ───────────────────────────────
SCRIPT_DIR   = pathlib.Path(__file__).parent.resolve()
RAW_DOCS_DIR = SCRIPT_DIR / "_raw_docs"
DB_DIR       = SCRIPT_DIR.parent / "database"
CHROMA_DIR   = DB_DIR / "razorpay_db"
BM25_PKL     = DB_DIR / "bm25_index.pkl"
BM25_META    = DB_DIR / "bm25_meta.json"

DB_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# 1.  FILTER DEFINITION
#     Based on real folder structure of razorpay/markdown-docs (inspected live).
#     ALLOW  → top-level or second-level paths that are customer-support relevant
#     DENY   → paths that are SDK/plugin-config/non-customer topics
# ─────────────────────────────────────────────────────────────────────────────

# Top-level folders to include entirely (or with per-subdir control below)
ALLOWED_TOP = {
    "errors",          # errors/payments, errors/x
    "webhooks",        # webhook docs are customer-support relevant
    "announcements",   # RBI mandates, TLS changes — compliance/support relevant
    "security",        # whitelisting IPs — common support question
}

# payments/* sub-folders to include (excludes SDK-heavy / POS / payroll paths)
ALLOWED_PAYMENTS_SUBS = {
    "payment-gateway",       # includes rainy-day/errors, troubleshooting-faqs
    "payment-links",
    "payment-methods",
    "payment-pages",
    "payment-button",
    "payments",              # payments/payments (failure-analysis, faqs)
    "refunds",
    "disputes",
    "settlements",
    "orders",
    "invoices",
    "subscriptions",
    "recurring-payments",
    "smart-collect",
    "qr-codes",
    "international-payments",
    "offers",
    "wallet",
    "whatsapp",
    "widgets",
    "dashboard",             # dashboard faqs
    "mobile-app",            # mobile app faqs
    "route",                 # route/faqs — payout routing
    "faqs.md",               # payments/faqs.md (top-level file in payments/)
}

# api/* sub-folders to include (REST API reference for customer-support context)
ALLOWED_API_SUBS = {
    "payments",
    "refunds",
    "disputes",
    "orders",
    "settlements",
    "customers",
    "qr-codes",
}

# Platform names for custom integration check
PLATFORMS = {"android", "ios", "flutter", "react-native", "cordova", "capacitor"}

# Filename patterns that qualify ANY file anywhere in the repo (subject to exclusions)
FILENAME_PATTERNS = ["faq", "error", "troubleshoot", "failure", "downtime", "limit", "limits"]

# Explicit deny: top-level folders to skip entirely
DENIED_TOP = {
    "payroll",          # internal HR product
    "pos",              # point-of-sale hardware
    "x",                # RazorpayX banking — different product
    "engage",           # retention engine — not support-facing
    "datasync",         # data-sync plugin
    "mcp-server",       # MCP AI tool
    "razorpay-n8n-node",# n8n automation
    "app-store",        # app marketplace
    "partners",         # partner/aggregator docs
    ".github",          # CI config
}


def category_for_path(rel_path: pathlib.Path) -> str:
    """Return a human-readable category tag for metadata."""
    parts = rel_path.parts
    if not parts:
        return "general"
    top = parts[0]
    if top == "errors":
        return "errors"
    if top == "payments":
        if len(parts) > 1:
            sub = parts[1]
            if sub in ("refunds",):          return "refunds"
            if sub in ("disputes",):         return "disputes"
            if sub in ("settlements",):      return "settlements"
            if sub in ("payment-methods",):  return "payment-methods"
            if sub in ("payment-links",):    return "payment-links"
            if sub in ("recurring-payments", "subscriptions"): return "recurring-payments"
            if sub in ("orders",):           return "orders"
            if sub in ("payment-gateway",):  return "payment-gateway"
        return "payments"
    if top == "api":
        return "api-reference"
    if top == "webhooks":
        return "webhooks"
    if top == "announcements":
        return "announcements"
    if top == "security":
        return "security"
    return top


def passes_filter(md_path: pathlib.Path) -> bool:
    """Return True if this .md file should be ingested based on tightened rules."""
    try:
        rel = md_path.relative_to(RAW_DOCS_DIR)
    except ValueError:
        return False

    parts = rel.parts
    if not parts:
        return False

    top = parts[0]
    fname_lower = md_path.name.lower()

    # Hard deny top-level folders
    if top in DENIED_TOP:
        return False

    # Check Rule 2: Exclusions under payments/ (or anywhere under payments/)
    is_integration_subpath = False
    
    # Check if ANY part of the path or filename contains integration/sdk/plugins/s2s
    for p in parts:
        p_lower = p.lower()
        if (p_lower.endswith("-integration") or 
            "integration" in p_lower or 
            p_lower in ("sdk", "plugins", "ecommerce-plugins", "server-integration") or
            "s2s" in p_lower or 
            "plugin" in p_lower):
            is_integration_subpath = True
            break
            
    # Platform custom integration check
    lower_parts = [p.lower() for p in parts]
    if "custom" in lower_parts and any(plat in lower_parts for plat in PLATFORMS):
        is_integration_subpath = True
        
    if "go-live-checklist" in fname_lower or "integration-noui-mock" in fname_lower:
        is_integration_subpath = True

    # EXCEPTION: if a file has "faq" or "troubleshoot" in filename, do NOT treat it as excluded
    if is_integration_subpath:
        if "faq" in fname_lower or "troubleshoot" in fname_lower:
            is_integration_subpath = False

    # If it is inside an excluded integration sub-path, reject it
    if is_integration_subpath:
        return False

    # Rule 3: Keep entirely (high-value folders)
    # Root files
    if len(parts) == 1:
        if fname_lower in ("errors.md", "faqs.md"):
            return True

    # Entire folders to keep
    HIGH_VALUE_TOP = {"errors", "webhooks", "announcements", "security"}
    if top in HIGH_VALUE_TOP:
        return True

    # Specific payments subfolders
    if top == "payments" and len(parts) > 1:
        sub = parts[1]
        if sub in ("disputes", "refunds", "settlements", "dashboard"):
            return True
        # payments/payment-links/ (top-level pages only: payments/payment-links/filename.md)
        if sub == "payment-links" and len(parts) == 3:
            return True

    # Rule 1: Exclude api/ entirely, except error docs
    if top == "api":
        # Keep api/**/errors.md
        if fname_lower == "errors.md":
            return True
        # Keep directly under api/ with error in filename
        if len(parts) == 2 and "error" in fname_lower:
            return True
        return False

    # Rule 4: Keep filename wildcards (for files not already excluded under Rule 2)
    if any(pat in fname_lower for pat in FILENAME_PATTERNS):
        return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# 2.  COLLECT FILTERED FILES
# ─────────────────────────────────────────────────────────────────────────────

def collect_files() -> List[Tuple[pathlib.Path, str]]:
    """Return list of (abs_path, category) for all passing .md files."""
    if not RAW_DOCS_DIR.exists():
        log.error(
            f"Raw docs directory not found: {RAW_DOCS_DIR}\n"
            "Run: git clone https://github.com/razorpay/markdown-docs.git backend/data/_raw_docs"
        )
        sys.exit(1)

    all_md = list(RAW_DOCS_DIR.rglob("*.md"))
    log.info(f"Total .md files in repo: {len(all_md)}")

    passed = []
    for p in all_md:
        if passes_filter(p):
            rel = p.relative_to(RAW_DOCS_DIR)
            cat = category_for_path(rel)
            passed.append((p, cat))

    passed.sort(key=lambda x: str(x[0]))
    log.info(f"Files passing filter    : {len(passed)}")
    log.info("")
    return passed



# ─────────────────────────────────────────────────────────────────────────────
# 3.  LOAD + CHUNK
# ─────────────────────────────────────────────────────────────────────────────

def load_and_chunk(files: List[Tuple[pathlib.Path, str]]):
    """Load each .md file, split by headers then by size, return all chunks."""
    from langchain_community.document_loaders import TextLoader
    from langchain_text_splitters import (
        MarkdownHeaderTextSplitter,
        RecursiveCharacterTextSplitter,
    )

    headers_to_split_on = [
        ("#",   "h1"),
        ("##",  "h2"),
        ("###", "h3"),
    ]
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False,
    )
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        separators=["\n\n", "\n", " ", ""],
    )

    all_chunks = []
    failed = []

    for abs_path, category in files:
        rel = str(abs_path.relative_to(RAW_DOCS_DIR))
        try:
            loader = TextLoader(str(abs_path), encoding="utf-8", autodetect_encoding=True)
            raw_docs = loader.load()
        except Exception as e:
            log.warning(f"  LOAD FAILED: {rel} — {e}")
            failed.append((rel, str(e)))
            continue

        raw_text = raw_docs[0].page_content if raw_docs else ""
        if not raw_text.strip():
            continue

        # Split by markdown headers first
        try:
            header_chunks = header_splitter.split_text(raw_text)
        except Exception:
            header_chunks = raw_docs  # fallback: treat as single chunk

        # Further split oversized sections
        for chunk in header_chunks:
            # Attach our metadata
            if hasattr(chunk, "metadata"):
                chunk.metadata["source"]   = rel
                chunk.metadata["category"] = category
            sub_chunks = char_splitter.split_documents([chunk])
            for sc in sub_chunks:
                sc.metadata["source"]   = rel
                sc.metadata["category"] = category
            all_chunks.extend(sub_chunks)

    log.info(f"Total chunks created: {len(all_chunks)}")
    log.info(f"Failed files        : {len(failed)}")
    for rel, err in failed:
        log.warning(f"  - {rel}: {err}")

    return all_chunks, failed


# ─────────────────────────────────────────────────────────────────────────────
# 4.  EMBED + PERSIST TO CHROMADB
# ─────────────────────────────────────────────────────────────────────────────

def build_chroma(chunks):
    """Embed chunks with local sentence-transformers and persist to ChromaDB."""
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_community.vectorstores import Chroma

    log.info("Loading embedding model: sentence-transformers/all-MiniLM-L6-v2 ...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    log.info(f"Embedding {len(chunks)} chunks into ChromaDB at: {CHROMA_DIR}")
    BATCH = 500
    vectorstore = None
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i : i + BATCH]
        log.info(f"  Batch {i // BATCH + 1}: chunks {i}–{i + len(batch) - 1}")
        if vectorstore is None:
            vectorstore = Chroma.from_documents(
                documents=batch,
                embedding=embeddings,
                persist_directory=str(CHROMA_DIR),
                collection_name="razorpay_kb",
            )
        else:
            vectorstore.add_documents(batch)

    log.info(f"ChromaDB persisted → {CHROMA_DIR}")
    return vectorstore


# ─────────────────────────────────────────────────────────────────────────────
# 5.  BUILD BM25 KEYWORD INDEX
# ─────────────────────────────────────────────────────────────────────────────

def build_bm25(chunks):
    """Build BM25Okapi index over chunk texts and save pkl + JSON meta."""
    from rank_bm25 import BM25Okapi

    log.info("Building BM25 index ...")
    tokenized = [chunk.page_content.lower().split() for chunk in chunks]
    bm25 = BM25Okapi(tokenized)

    # Save the BM25 object
    with open(BM25_PKL, "wb") as f:
        pickle.dump(bm25, f)
    log.info(f"BM25 index saved       → {BM25_PKL}")

    # Save parallel metadata (index position → source/category/snippet)
    meta = [
        {
            "index":    i,
            "source":   chunk.metadata.get("source", ""),
            "category": chunk.metadata.get("category", ""),
            "snippet":  chunk.page_content[:120].replace("\n", " "),
            # Store raw text so we can reconstruct Document at query time
            "text":     chunk.page_content,
        }
        for i, chunk in enumerate(chunks)
    ]
    with open(BM25_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    log.info(f"BM25 metadata saved    → {BM25_META}  ({len(meta)} entries)")

    return bm25


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("  FlowZint Sentinel — KB Ingestion Pipeline")
    log.info("=" * 60)

    # Simple flag checking
    is_dry_run = "--dry-run" in sys.argv

    # Step 1: Collect filtered files
    files = collect_files()
    if not files:
        log.error("No files passed the filter — check RAW_DOCS_DIR and filter logic.")
        sys.exit(1)

    if is_dry_run:
        log.info("=" * 60)
        log.info("  DRY RUN RESULTS")
        log.info("=" * 60)

        # 1. Group by top-level folder
        top_level_counts = {}
        for p, cat in files:
            rel = p.relative_to(RAW_DOCS_DIR)
            parts = rel.parts
            top_level = parts[0] if parts else "root"
            top_level_counts[top_level] = top_level_counts.get(top_level, 0) + 1

        sorted_top = sorted(top_level_counts.items(), key=lambda x: x[1], reverse=True)
        log.info("Top-Level Folder Breakdown:")
        for folder, count in sorted_top:
            log.info(f"  {folder:20s} : {count} files")

        # 2. Group payments/ by subfolder
        payments_subs = {}
        for p, cat in files:
            rel = p.relative_to(RAW_DOCS_DIR)
            parts = rel.parts
            if parts and parts[0] == "payments":
                sub = parts[1] if len(parts) > 1 else "root"
                payments_subs[sub] = payments_subs.get(sub, 0) + 1

        if payments_subs:
            sorted_pay = sorted(payments_subs.items(), key=lambda x: x[1], reverse=True)
            log.info("")
            log.info("payments/ Subfolders Breakdown:")
            for sub, count in sorted_pay:
                log.info(f"  payments/{sub:25s} : {count} files")

        log.info("=" * 60)
        log.info(f"Dry run complete. Projected total: {len(files)} files.")
        return

    # Step 2: Load + chunk
    log.info("Loading and chunking files ...")
    chunks, failed = load_and_chunk(files)
    if not chunks:
        log.error("No chunks produced — aborting.")
        sys.exit(1)

    # Step 3: Embed + persist ChromaDB
    build_chroma(chunks)

    # Step 4: Build BM25 index
    build_bm25(chunks)

    # ── Final summary ──────────────────────────────────────────────────────
    log.info("")
    log.info("=" * 60)
    log.info("  INGESTION COMPLETE — SUMMARY")
    log.info("=" * 60)
    log.info(f"  Files processed  : {len(files)}")
    log.info(f"  Files failed     : {len(failed)}")
    log.info(f"  Total chunks     : {len(chunks)}")
    log.info(f"  ChromaDB         : {CHROMA_DIR}  ✓")
    log.info(f"  BM25 index       : {BM25_PKL}  ✓")
    log.info(f"  BM25 metadata    : {BM25_META}  ✓")
    log.info("=" * 60)

    if failed:
        log.info("")
        log.info("Failed files:")
        for rel, err in failed:
            log.info(f"  - {rel}: {err}")


if __name__ == "__main__":
    main()
