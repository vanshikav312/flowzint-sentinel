"""
database/db.py
Lightweight SQLite persistence layer for tickets, incidents, and KB drafts.

Uses stdlib sqlite3 only — no extra dependencies.
DB file lives at backend/database/sentinel.db (gitignored).

Tables
------
tickets   — one row per escalated ticket (Stage 2)
incidents — one row per detected incident cluster (Stage 3)
kb_drafts — one row per pending/approved/rejected KB draft (Stage 5)
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
from contextlib import contextmanager

_DB_PATH = pathlib.Path(__file__).parent / "sentinel.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row          # rows behave like dicts
    conn.execute("PRAGMA journal_mode=WAL") # safe for concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist. Called once at startup."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id    TEXT PRIMARY KEY,
                query        TEXT NOT NULL,
                confidence   REAL NOT NULL,
                status       TEXT NOT NULL DEFAULT 'open',
                sources      TEXT NOT NULL DEFAULT '[]',   -- JSON array
                query_embedding TEXT DEFAULT NULL,          -- JSON array of floats
                resolution   TEXT DEFAULT NULL,
                kb_draft_id  TEXT DEFAULT NULL,
                created_at   TEXT NOT NULL,
                resolved_at  TEXT DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS incidents (
                incident_id          TEXT PRIMARY KEY,
                topic                TEXT NOT NULL,
                ticket_ids           TEXT NOT NULL,   -- JSON array of ticket_id strings
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

