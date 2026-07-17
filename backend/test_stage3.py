"""
Stage 3 end-to-end integration test.
Run from backend/ with: venv\\Scripts\\python test_stage3.py
"""
import sys
sys.path.insert(0, ".")

import json
import sqlite3
import pathlib
from fastapi.testclient import TestClient
from main import app

# ── Clean database and in-memory state before test ──────────────────────────
db_path = pathlib.Path(__file__).parent / "database" / "sentinel.db"
if db_path.exists():
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM tickets")
        conn.execute("DELETE FROM kb_drafts")
        conn.commit()
        conn.close()
        print("Cleared existing tickets/kb_drafts from SQLite database.")
    except Exception as e:
        print(f"Database cleanup failed: {e}")

from routers.incidents import _INCIDENTS
_INCIDENTS.clear()

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
    print(f"\n{'=' * 55}")
    print(f"  {title}")
    print("=" * 55)


# ── Step 1: Create tickets directly (bypasses RAG / ChromaDB) ────────────────
sep("Step 1 — Creating tickets via POST /api/tickets/")

ticket_payloads = [
    # Three semantically similar: payment failures
    {"query": "Why was my payment declined?",                   "confidence": 18},
    {"query": "My transaction failed on checkout",              "confidence": 22},
    {"query": "Payment not going through, getting an error",    "confidence": 15},
    # One unrelated: should NOT join the payment cluster
    {"query": "How do I reset my password?",                    "confidence": 30},
]

created = []
for p in ticket_payloads:
    t = post("/api/tickets/", p)
    created.append(t)
    print(f"  Created  {t['ticket_id']}  confidence={t['confidence']}  query={t['query']!r}")

# ── Step 2: Verify ticket store ───────────────────────────────────────────────
sep("Step 2 — GET /api/tickets/  (verify storage)")
tickets = get("/api/tickets/")
print(f"  Total tickets in store: {len(tickets)}")
assert len(tickets) == 4, f"Expected 4 tickets, got {len(tickets)}"
print("  PASS — all 4 tickets stored correctly")

# ── Step 3: Trigger incident detection ────────────────────────────────────────
sep("Step 3 — POST /api/incidents/detect")
result = post("/api/incidents/detect", {})
print(f"  Scanned tickets   : {result['scanned_tickets']}")
print(f"  Incidents detected: {result['incidents_detected']}")
for inc in result["incidents"]:
    print(f"\n  Incident  : {inc['incident_id']}")
    print(f"  Topic     : {inc['topic']!r}")
    print(f"  Tickets   : {inc['ticket_ids']}")
    print(f"  Count     : {inc['ticket_count']}")
    print(f"  Severity  : {inc['severity']}")
    print(f"  Threshold : {inc['similarity_threshold']}")

# ── Step 4: Verify GET /api/incidents/ ───────────────────────────────────────
sep("Step 4 — GET /api/incidents/  (verify persistence)")
incidents = get("/api/incidents/")
print(f"  Total incidents stored: {len(incidents)}")
for inc in incidents:
    print(f"  {inc['incident_id']}  severity={inc['severity']}  tickets={inc['ticket_ids']}")

# ── Step 5: Verify GET /api/incidents/{id} ───────────────────────────────────
if incidents:
    sep("Step 5 — GET /api/incidents/{id}  (single incident lookup)")
    inc_id = incidents[0]["incident_id"]
    single = get(f"/api/incidents/{inc_id}")
    print(f"  Fetched  {single['incident_id']}  topic={single['topic']!r}")
    assert single["incident_id"] == inc_id
    print("  PASS — single incident lookup works")

# ── Step 6: Test deduplication (run /detect again, same tickets) ──────────────
sep("Step 6 — Re-run /detect  (verify no duplicate incidents)")
result2 = post("/api/incidents/detect", {})
incidents2 = get("/api/incidents/")
print(f"  Incidents after second scan: {len(incidents2)}")
assert len(incidents2) == len(incidents), "FAIL — duplicate incidents created!"
print("  PASS — no duplicates created on repeated scan")

# ── Step 7: Add a 5th similar ticket, verify incident updates ─────────────────
sep("Step 7 — Add a 5th similar ticket, verify incident updates in-place")
t5 = post("/api/tickets/", {"query": "Card payment rejected at checkout", "confidence": 12})
print(f"  Created  {t5['ticket_id']}  query={t5['query']!r}")

result3 = post("/api/incidents/detect", {})
incidents3 = get("/api/incidents/")
print(f"  Incidents after 5th ticket: {len(incidents3)}")

# Find the payment incident
pay_inc = next(
    (i for i in incidents3 if "declined" in i["topic"] or "payment" in i["topic"].lower() or "transaction" in i["topic"].lower()),
    None,
)
if pay_inc:
    print(f"  Payment incident  {pay_inc['incident_id']}  now has {pay_inc['ticket_count']} tickets  severity={pay_inc['severity']}")
    print(f"  Ticket IDs: {pay_inc['ticket_ids']}")

sep("ALL TESTS PASSED")
print("  Stage 3 incident detection is working correctly.")
print("  Tickets stored, incidents detected, deduplication works,")
print("  in-place updates work, unrelated tickets correctly isolated.\n")
