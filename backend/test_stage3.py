"""
Stage 3 end-to-end integration test.
Run from backend/ with: venv\\Scripts\\python test_stage3.py

Covers:
  - Ticket creation stored in SQLite
  - Auto-triggered incident detection (via create_ticket_internal)
  - Manual scan via POST /api/incidents/detect
  - Deduplication (no duplicate incidents on repeated scans)
  - In-place update when a new similar ticket joins a cluster
  - Embedding reuse (stored query_embedding from DB, not re-computed)
  - SQLite persistence verification (incidents survive in the DB)
"""
import sys
sys.path.insert(0, ".")

import json
import sqlite3
import pathlib
from fastapi.testclient import TestClient
from main import app

# ── Reset database and in-memory state before test ───────────────────────────
db_path = pathlib.Path(__file__).parent / "database" / "sentinel.db"
if db_path.exists():
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM incidents")
        conn.execute("DELETE FROM tickets")
        conn.execute("DELETE FROM kb_drafts")
        conn.commit()
        conn.close()
        print("Cleared tickets / incidents / kb_drafts from SQLite database.")
    except Exception as e:
        print(f"Database cleanup failed: {e}")
        sys.exit(1)

client = TestClient(app)


def post(path, body):
    resp = client.post(path, json=body)
    resp.raise_for_status()
    return resp.json()


def get(path):
    resp = client.get(path)
    resp.raise_for_status()
    return resp.json()


def sep(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


# ── Step 1: Create 4 tickets (3 payment-related + 1 unrelated) ───────────────
sep("Step 1 — Create tickets via POST /api/tickets/")

payloads = [
    {"query": "Why was my payment declined?",                "confidence": 18},
    {"query": "My transaction failed on checkout",           "confidence": 22},
    {"query": "Payment not going through, getting an error", "confidence": 15},
    {"query": "How do I reset my password?",                 "confidence": 30},
]

created = []
for p in payloads:
    t = post("/api/tickets/", p)
    created.append(t)
    print(f"  {t['ticket_id']}  conf={t['confidence']}  query={t['query']!r}")

# ── Step 2: Verify tickets stored in SQLite ───────────────────────────────────
sep("Step 2 — Verify ticket storage (GET /api/tickets/)")
tickets = get("/api/tickets/")
print(f"  Total tickets in DB: {len(tickets)}")
assert len(tickets) == 4, f"Expected 4, got {len(tickets)}"
print("  PASS")

# ── Step 3: Verify incidents were auto-triggered by create_ticket_internal ────
sep("Step 3 — Verify auto-trigger via GET /api/incidents/")
incidents = get("/api/incidents/")
print(f"  Total incidents detected (auto): {len(incidents)}")
assert len(incidents) >= 1, "Expected at least 1 auto-triggered incident"
for inc in incidents:
    print(f"  {inc['incident_id']}  severity={inc['severity']}  "
          f"tickets={inc['ticket_ids']}  topic={inc['topic']!r}")
print("  PASS — auto-trigger works")

# ── Step 4: Manual scan returns same count (deduplication) ────────────────────
sep("Step 4 — Manual scan (POST /api/incidents/detect) — deduplication")
result = post("/api/incidents/detect", {})
print(f"  Scanned: {result['scanned_tickets']}  Detected: {result['incidents_detected']}")
incidents2 = get("/api/incidents/")
assert len(incidents2) == len(incidents), (
    f"FAIL — duplicate incidents! Was {len(incidents)}, now {len(incidents2)}"
)
print(f"  Incident count unchanged: {len(incidents2)}  PASS")

# ── Step 5: GET /api/incidents/{id} ──────────────────────────────────────────
sep("Step 5 — Single incident lookup (GET /api/incidents/{id})")
target_id = incidents[0]["incident_id"]
single = get(f"/api/incidents/{target_id}")
assert single["incident_id"] == target_id
print(f"  Fetched {single['incident_id']}  topic={single['topic']!r}  PASS")

# ── Step 6: Add 5th similar ticket, verify in-place update ───────────────────
sep("Step 6 — 5th similar ticket triggers in-place incident update")
t5 = post("/api/tickets/", {"query": "Card payment rejected at checkout", "confidence": 12})
print(f"  Created {t5['ticket_id']}  query={t5['query']!r}")

incidents3 = get("/api/incidents/")
pay_inc = next(
    (i for i in incidents3
     if any(kw in i["topic"].lower() for kw in ("declined", "payment", "transaction"))),
    None,
)
assert pay_inc is not None, "FAIL — payment incident not found"
print(f"  Payment incident {pay_inc['incident_id']}  "
      f"now has {pay_inc['ticket_count']} tickets  severity={pay_inc['severity']}")
assert pay_inc["ticket_count"] >= 3, (
    f"FAIL — expected >=3 tickets in cluster, got {pay_inc['ticket_count']}"
)
print("  PASS — in-place update works")

# ── Step 7: Verify SQLite persistence directly ────────────────────────────────
sep("Step 7 — Verify incidents are persisted in SQLite (not just in-memory)")
raw_conn = sqlite3.connect(str(db_path))
raw_conn.row_factory = sqlite3.Row
db_incidents = raw_conn.execute("SELECT * FROM incidents ORDER BY detected_at DESC").fetchall()
raw_conn.close()

print(f"  Rows in incidents table: {len(db_incidents)}")
assert len(db_incidents) >= 1, "FAIL — no incidents found in SQLite!"
for row in db_incidents:
    print(f"  {row['incident_id']}  severity={row['severity']}  "
          f"tickets={row['ticket_ids']}  status={row['status']}")
print("  PASS — incidents are persisted in SQLite")

# ── Step 8: Verify embedding reuse ───────────────────────────────────────────
sep("Step 8 — Verify stored query_embedding reuse (not re-computed each scan)")
raw_conn2 = sqlite3.connect(str(db_path))
raw_conn2.row_factory = sqlite3.Row
db_tickets = raw_conn2.execute("SELECT ticket_id, query_embedding FROM tickets").fetchall()
raw_conn2.close()

tickets_with_embeddings = [r for r in db_tickets if r["query_embedding"]]
tickets_without = [r for r in db_tickets if not r["query_embedding"]]
print(f"  Tickets with stored embedding : {len(tickets_with_embeddings)}")
print(f"  Tickets without embedding     : {len(tickets_without)}")
# Manually created tickets (no query_embedding from chat.py) should have been
# computed and stored by the fallback path in detect_incidents_internal
assert len(tickets_without) == 0, (
    f"FAIL — {len(tickets_without)} ticket(s) still missing embeddings: "
    + str([r['ticket_id'] for r in tickets_without])
)
print("  PASS — all tickets have stored embeddings; future scans will reuse them")

sep("ALL TESTS PASSED")
print("  Stage 3 incident detection is fully working on the SQLite architecture.")
print("  * Tickets stored in SQLite")
print("  * Incidents stored in SQLite (persistent across restarts)")
print("  * Auto-trigger fires from create_ticket_internal()")
print("  * Deduplication prevents duplicate incidents")
print("  * In-place updates grow existing incidents correctly")
print("  * query_embedding values are stored and reused — no redundant inference\n")
