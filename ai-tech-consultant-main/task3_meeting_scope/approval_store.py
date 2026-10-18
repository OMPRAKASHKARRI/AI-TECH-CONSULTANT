"""Persistent human approval records for client-facing scope artifacts."""
from __future__ import annotations
import json
import os
import sqlite3
from pathlib import Path

DB_PATH = os.getenv("DATABASE_PATH", "data/jd4.sqlite3")
SCOPE_DECISIONS = {"approved", "rejected", "needs_changes"}


def save_scope_decision(scope: dict, decision: str, reviewer: str) -> int:
    if decision not in SCOPE_DECISIONS:
        raise ValueError("Invalid scope decision")
    if not isinstance(scope, dict):
        raise ValueError("A generated scope object is required.")
    project_summary = scope.get("project_summary")
    if not isinstance(project_summary, str) or not project_summary.strip():
        raise ValueError("The scope must have a project summary before review.")
    if not isinstance(reviewer, str):
        raise ValueError("Reviewer identifier must be text.")
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("Enter a reviewer identifier before saving a decision.")
    if len(reviewer) > 120 or any(ord(char) < 32 for char in reviewer):
        raise ValueError("Reviewer identifier must be at most 120 printable characters.")

    recorded_scope = dict(scope)
    recorded_scope["review_status"] = decision
    recorded_scope["approval_required"] = decision != "approved"
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS scope_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_summary TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            decision TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        cursor = conn.execute(
            "INSERT INTO scope_approvals(project_summary, scope_json, decision, reviewer) VALUES (?, ?, ?, ?)",
            (
                project_summary.strip(),
                json.dumps(recorded_scope, ensure_ascii=False),
                decision,
                reviewer,
            ),
        )
        return int(cursor.lastrowid)


def list_scope_decisions(limit: int = 25) -> list[dict]:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE IF NOT EXISTS scope_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_summary TEXT NOT NULL,
            scope_json TEXT NOT NULL, decision TEXT NOT NULL, reviewer TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        rows = conn.execute("SELECT id, project_summary, decision, reviewer, created_at FROM scope_approvals ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]


def get_latest_approved_scope() -> dict | None:
    """Load the latest explicitly approved scope as the change-control baseline."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS scope_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_summary TEXT NOT NULL,
            scope_json TEXT NOT NULL, decision TEXT NOT NULL, reviewer TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        row = conn.execute("SELECT scope_json FROM scope_approvals WHERE decision='approved' ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return None
