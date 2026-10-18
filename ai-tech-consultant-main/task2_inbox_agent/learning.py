
import os
import sqlite3
from pathlib import Path

DB_PATH = os.getenv("DATABASE_PATH", "data/jd4.sqlite3")


def get_connection():
    """Connect to the shared project database."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_learning_database():
    """Create the email learning table if it does not exist."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS autonomy_streaks (
                category TEXT PRIMARY KEY,
                consecutive_unedited_approvals INTEGER NOT NULL DEFAULT 0,
                eligible INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS email_learning (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                category TEXT NOT NULL,
                urgency TEXT NOT NULL,
                original_draft TEXT NOT NULL,
                reviewed_draft TEXT NOT NULL,
                human_edited INTEGER NOT NULL,
                review_outcome TEXT NOT NULL DEFAULT 'reviewed',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def save_email_review(
    subject: str,
    category: str,
    urgency: str,
    original_draft: str,
    reviewed_draft: str,
    review_outcome: str = "reviewed",
) -> int:
    """Persist the AI draft and the human-reviewed version."""
    initialize_learning_database()

    human_edited = int(
        original_draft.strip() != reviewed_draft.strip()
    )
    if review_outcome not in {"reviewed", "approved", "rejected", "escalated"}:
        raise ValueError("Invalid review outcome")

    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO email_learning (
                subject,
                category,
                urgency,
                original_draft,
                reviewed_draft,
                human_edited,
                review_outcome
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            subject,
            category,
            urgency,
            original_draft,
            reviewed_draft,
            human_edited,
            review_outcome,
        ))
        # Autonomy is eligibility only, never permission to send. The streak
        # counts only consecutive approved drafts that required no human edits.
        row = conn.execute("SELECT consecutive_unedited_approvals FROM autonomy_streaks WHERE category = ?", (category,)).fetchone()
        streak = int(row[0]) if row else 0
        if review_outcome == "approved" and not human_edited:
            streak += 1
        else:
            streak = 0
        conn.execute("""INSERT INTO autonomy_streaks(category, consecutive_unedited_approvals, eligible, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(category) DO UPDATE SET consecutive_unedited_approvals=excluded.consecutive_unedited_approvals,
            eligible=excluded.eligible, updated_at=CURRENT_TIMESTAMP""", (category, streak, int(streak >= 20)))
        conn.commit()
        return cursor.lastrowid


def get_email_reviews(limit: int = 100) -> list[dict]:
    """Retrieve recently saved email review outcomes."""
    initialize_learning_database()

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                id,
                subject,
                category,
                urgency,
                original_draft,
                reviewed_draft,
                human_edited,
                review_outcome,
                created_at
            FROM email_learning
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()

    return [dict(row) for row in rows]


def get_similar_review_examples(
    category: str,
    limit: int = 3,
) -> list[dict]:
    """Retrieve recent human-reviewed drafts from the same category."""
    initialize_learning_database()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                subject,
                category,
                original_draft,
                reviewed_draft,
                human_edited
            FROM email_learning
            WHERE category = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (category, limit),
        ).fetchall()

    return [dict(row) for row in rows]


def get_autonomy_status() -> list[dict]:
    """Return per-category streaks; eligibility never enables auto-send."""
    initialize_learning_database()
    with get_connection() as conn:
        rows = conn.execute("SELECT category, consecutive_unedited_approvals, eligible, updated_at FROM autonomy_streaks ORDER BY category").fetchall()
    return [dict(row) for row in rows]
