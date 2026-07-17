"""
test_stage4.py — Stage 4 Human Resolution Test Suite
=====================================================

10 test cases covering:
  1.  Create ticket + resolve with valid resolution
  2.  Resolve same ticket again → 409 Conflict
  3.  Resolve with empty string "" → 400 Bad Request
  4.  Resolve non-existent ticket ID → 404 Not Found
  5.  Resolve with whitespace-only string "   " → 400 Bad Request
  6.  KB draft auto-created with correct source_ticket_id and status=pending
  7.  Stats endpoint: open/resolved counts match actual ticket state
  8.  Approve KB draft → status=approved, reviewed_at set
  9.  Approve same draft again → 409 Conflict
  10. Reject a pending draft → status=rejected

Run:
    D:\\Downloads\\Python\\Python311\\python.exe test_stage4.py
    # or: python test_stage4.py  (from backend/)

Uses an isolated in-memory SQLite DB so it never touches sentinel.db.
The embedding model and ChromaDB are NOT loaded.
"""

from __future__ import annotations

import os
import sys
import sqlite3
import pathlib
import unittest
import warnings
from contextlib import contextmanager
from unittest.mock import patch

# Silence the httpx → httpx2 deprecation warning — it's cosmetic
warnings.filterwarnings("ignore", category=DeprecationWarning)

# ── Make sure "backend/" is on sys.path ──────────────────────────────────────
HERE = pathlib.Path(__file__).parent.resolve()
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# ── Stub out heavy ML modules BEFORE any app import ──────────────────────────
# This prevents sentence-transformers / chromadb from loading during tests.
import types

from fastapi import APIRouter as _APIRouter

_fake_chat = types.ModuleType("routers.chat")
_fake_chat.router = _APIRouter()            # type: ignore[attr-defined]
_fake_chat._get_embeddings = lambda: None   # type: ignore[attr-defined]
_fake_chat.warmup = lambda: None            # type: ignore[attr-defined]
sys.modules["routers.chat"] = _fake_chat

# ── Build a shared in-memory SQLite connection ───────────────────────────────
# We CANNOT use the normal get_db() context manager because its finally-block
# calls conn.close(), which permanently destroys an in-memory database.
# Instead we patch the entire get_db() function with one that yields the
# shared connection but never closes it.

_INMEM_CONN: sqlite3.Connection = sqlite3.connect(":memory:", check_same_thread=False)
_INMEM_CONN.row_factory = sqlite3.Row
_INMEM_CONN.execute("PRAGMA journal_mode=WAL")
_INMEM_CONN.execute("PRAGMA foreign_keys=ON")
_INMEM_CONN.commit()


@contextmanager
def _fake_get_db():
    """Yield the shared in-memory connection; commit on success, rollback on error."""
    try:
        yield _INMEM_CONN
        _INMEM_CONN.commit()
    except Exception:
        _INMEM_CONN.rollback()
        raise
    # No conn.close() — the shared in-memory DB must stay alive for the whole run


# Patch get_db everywhere before importing application code
_patcher = patch("database.db.get_db", _fake_get_db)
_patcher.start()

# ── Bootstrap the schema in the in-memory DB ─────────────────────────────────
# We execute the CREATE TABLE statements directly rather than calling init_db()
# (which would also use get_db() and could be patched into a race).
_INMEM_CONN.executescript("""
    CREATE TABLE IF NOT EXISTS tickets (
        ticket_id    TEXT PRIMARY KEY,
        query        TEXT NOT NULL,
        confidence   REAL NOT NULL,
        status       TEXT NOT NULL DEFAULT 'open',
        sources      TEXT NOT NULL DEFAULT '[]',
        query_embedding TEXT DEFAULT NULL,
        resolution   TEXT DEFAULT NULL,
        kb_draft_id  TEXT DEFAULT NULL,
        created_at   TEXT NOT NULL,
        resolved_at  TEXT DEFAULT NULL
    );

    CREATE TABLE IF NOT EXISTS incidents (
        incident_id          TEXT PRIMARY KEY,
        topic                TEXT NOT NULL,
        ticket_ids           TEXT NOT NULL,
        ticket_count         INTEGER NOT NULL,
        severity             TEXT NOT NULL,
        status               TEXT NOT NULL DEFAULT 'open',
        detected_at          TEXT NOT NULL,
        updated_at           TEXT DEFAULT NULL,
        similarity_threshold REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS kb_drafts (
        draft_id         TEXT PRIMARY KEY,
        title            TEXT NOT NULL,
        content          TEXT NOT NULL,
        source_ticket_id TEXT DEFAULT NULL,
        status           TEXT NOT NULL DEFAULT 'pending',
        created_at       TEXT NOT NULL,
        reviewed_at      TEXT DEFAULT NULL
    );
""")
_INMEM_CONN.commit()

# ── Import FastAPI app (after patching, after schema creation) ────────────────
# Disable main.py's startup init_db() call — schema is already created above.
with patch("database.db.init_db", lambda: None):
    from main import app

# Suppress the lifespan warmup (would load embedding model + ChromaDB)
from contextlib import asynccontextmanager

@asynccontextmanager
async def _noop_lifespan(_app):
    yield

app.router.lifespan_context = _noop_lifespan  # type: ignore[assignment]

from fastapi.testclient import TestClient

client = TestClient(app, raise_server_exceptions=True)

# ── Demo ticket queries (UPI-themed) ──────────────────────────────────────────
UPI_QUERIES = [
    "My UPI payment failed but money was deducted from my account",
    "UPI transaction showing failed but amount got debited",
    "Money deducted via UPI but payment not completed",
]


def _create_ticket(query: str = UPI_QUERIES[0], confidence: float = 15.0) -> dict:
    """Create a ticket via POST /api/tickets/ and return the JSON body."""
    res = client.post("/api/tickets/", json={"query": query, "confidence": confidence})
    assert res.status_code == 200, f"Ticket creation failed ({res.status_code}): {res.text}"
    return res.json()


# ─────────────────────────────────────────────────────────────────────────────
# Test cases
# ─────────────────────────────────────────────────────────────────────────────

class TestStage4(unittest.TestCase):

    # ── Test 1 ─────────────────────────────────────────────────────────────────
    def test_01_resolve_valid(self):
        """Create a ticket then resolve it with valid resolution text."""
        ticket = _create_ticket(UPI_QUERIES[0])
        tid = ticket["ticket_id"]

        res = client.patch(
            f"/api/tickets/{tid}/resolve",
            json={"resolution": "The UPI transaction will auto-reverse within 3–5 business days."},
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["status"], "resolved")
        self.assertIsNotNone(data["resolution"])
        self.assertIsNotNone(data["kb_draft_id"])
        self.assertIsNotNone(data["resolved_at"])
        self.assertEqual(data["ticket_id"], tid)

    # ── Test 2 ─────────────────────────────────────────────────────────────────
    def test_02_resolve_already_resolved_409(self):
        """Resolving the same ticket a second time must return 409 Conflict."""
        ticket = _create_ticket(UPI_QUERIES[1])
        tid = ticket["ticket_id"]

        r1 = client.patch(
            f"/api/tickets/{tid}/resolve",
            json={"resolution": "Auto-reverse will happen within 3 business days."},
        )
        self.assertEqual(r1.status_code, 200, r1.text)

        r2 = client.patch(
            f"/api/tickets/{tid}/resolve",
            json={"resolution": "Trying to resolve again."},
        )
        self.assertEqual(r2.status_code, 409, r2.text)

    # ── Test 3 ─────────────────────────────────────────────────────────────────
    def test_03_resolve_empty_string_400(self):
        """Empty resolution string must return 400 Bad Request."""
        ticket = _create_ticket(UPI_QUERIES[2])
        tid = ticket["ticket_id"]

        res = client.patch(
            f"/api/tickets/{tid}/resolve",
            json={"resolution": ""},
        )
        self.assertEqual(res.status_code, 400, res.text)

    # ── Test 4 ─────────────────────────────────────────────────────────────────
    def test_04_resolve_nonexistent_404(self):
        """Resolving a non-existent ticket ID must return 404 Not Found."""
        res = client.patch(
            "/api/tickets/TK-DOESNOTEXIST/resolve",
            json={"resolution": "This should not work."},
        )
        self.assertEqual(res.status_code, 404, res.text)

    # ── Test 5 ─────────────────────────────────────────────────────────────────
    def test_05_resolve_whitespace_only_400(self):
        """Whitespace-only resolution must return 400 Bad Request."""
        ticket = _create_ticket("UPI payment stuck in pending state")
        tid = ticket["ticket_id"]

        res = client.patch(
            f"/api/tickets/{tid}/resolve",
            json={"resolution": "   "},
        )
        self.assertEqual(res.status_code, 400, res.text)

    # ── Test 6 ─────────────────────────────────────────────────────────────────
    def test_06_kb_draft_auto_created(self):
        """Resolving a ticket must create a KB draft with correct source_ticket_id and status=pending."""
        ticket = _create_ticket("How do I check my UPI transaction status?")
        tid = ticket["ticket_id"]

        resolve_res = client.patch(
            f"/api/tickets/{tid}/resolve",
            json={"resolution": "Open your UPI app, go to History, and check the transaction status."},
        )
        self.assertEqual(resolve_res.status_code, 200, resolve_res.text)
        draft_id = resolve_res.json()["kb_draft_id"]
        self.assertIsNotNone(draft_id)

        draft_res = client.get(f"/api/kb/drafts/{draft_id}")
        self.assertEqual(draft_res.status_code, 200, draft_res.text)
        draft = draft_res.json()

        self.assertEqual(draft["draft_id"], draft_id)
        self.assertEqual(draft["source_ticket_id"], tid)
        self.assertEqual(draft["status"], "pending")

    # ── Test 7 ─────────────────────────────────────────────────────────────────
    def test_07_stats_match_actual_state(self):
        """Stats endpoint open/resolved/total counts must match actual ticket state."""
        pre = client.get("/api/tickets/stats").json()
        pre_open     = pre["open"]
        pre_resolved = pre["resolved"]
        pre_total    = pre["total"]

        t1 = _create_ticket("UPI VPA not found error")
        t2 = _create_ticket("UPI payment declined by bank")
        # suppress unused variable warning
        _ = t2

        client.patch(
            f"/api/tickets/{t1['ticket_id']}/resolve",
            json={"resolution": "VPA lookup issue — ask the sender to re-verify the UPI ID."},
        )

        stats = client.get("/api/tickets/stats").json()

        self.assertEqual(stats["total"],    pre_total    + 2)
        self.assertEqual(stats["open"],     pre_open     + 1)
        self.assertEqual(stats["resolved"], pre_resolved + 1)
        self.assertIsInstance(stats["avg_confidence"], float)

    # ── Test 8 ─────────────────────────────────────────────────────────────────
    def test_08_approve_draft(self):
        """Approving a pending KB draft must flip status to approved and set reviewed_at."""
        ticket = _create_ticket("UPI collect request expired before I could pay")
        tid = ticket["ticket_id"]

        resolve_res = client.patch(
            f"/api/tickets/{tid}/resolve",
            json={"resolution": "UPI collect requests expire after 30 minutes. Ask the sender to retry."},
        )
        self.assertEqual(resolve_res.status_code, 200, resolve_res.text)
        draft_id = resolve_res.json()["kb_draft_id"]

        approve_res = client.post(f"/api/kb/drafts/{draft_id}/approve")
        self.assertEqual(approve_res.status_code, 200, approve_res.text)

        draft = approve_res.json()
        self.assertEqual(draft["status"], "approved")
        self.assertIsNotNone(draft["reviewed_at"])

    # ── Test 9 ─────────────────────────────────────────────────────────────────
    def test_09_approve_already_approved_409(self):
        """Approving an already-approved draft must return 409 Conflict."""
        ticket = _create_ticket("How long does a UPI refund take?")
        tid = ticket["ticket_id"]

        resolve_res = client.patch(
            f"/api/tickets/{tid}/resolve",
            json={"resolution": "UPI refunds typically take 3–5 business days depending on the bank."},
        )
        self.assertEqual(resolve_res.status_code, 200, resolve_res.text)
        draft_id = resolve_res.json()["kb_draft_id"]

        r1 = client.post(f"/api/kb/drafts/{draft_id}/approve")
        self.assertEqual(r1.status_code, 200, r1.text)

        r2 = client.post(f"/api/kb/drafts/{draft_id}/approve")
        self.assertEqual(r2.status_code, 409, r2.text)

    # ── Test 10 ────────────────────────────────────────────────────────────────
    def test_10_reject_pending_draft(self):
        """Rejecting a pending KB draft must flip status to rejected."""
        ticket = _create_ticket("UPI payment pending for more than 24 hours")
        tid = ticket["ticket_id"]

        resolve_res = client.patch(
            f"/api/tickets/{tid}/resolve",
            json={"resolution": "Pending UPI payments that exceed 24 hours will auto-reverse."},
        )
        self.assertEqual(resolve_res.status_code, 200, resolve_res.text)
        draft_id = resolve_res.json()["kb_draft_id"]

        reject_res = client.delete(f"/api/kb/drafts/{draft_id}")
        self.assertEqual(reject_res.status_code, 200, reject_res.text)

        draft = reject_res.json()
        self.assertEqual(draft["status"], "rejected")
        self.assertIsNotNone(draft["reviewed_at"])


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    loader = unittest.TestLoader()
    loader.sortTestMethodsUsing = None   # run in definition order
    suite  = loader.loadTestsFromTestCase(TestStage4)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
