
import os
import sqlite3
from pathlib import Path

DB_PATH = os.getenv("DATABASE_PATH", "data/jd4.sqlite3")


def get_connection():
    """Create a database connection and ensure its directory exists."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    """Create the required tables if they do not exist."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                active INTEGER DEFAULT 1
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ingestion_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL,
                discovered INTEGER NOT NULL DEFAULT 0,
                processed INTEGER NOT NULL DEFAULT 0,
                saved INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                current_url TEXT,
                started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS expert_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                expert_answer TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()


def save_article(url: str, title: str, content: str):
    """Insert or update an article using its URL."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO articles (
                url, title, content, updated_at, active
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, 1)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                content = excluded.content,
                updated_at = CASE
                    WHEN articles.title != excluded.title OR articles.content != excluded.content OR articles.active != 1
                    THEN CURRENT_TIMESTAMP ELSE articles.updated_at END,
                active = 1
            WHERE articles.title != excluded.title
               OR articles.content != excluded.content
               OR articles.active != 1
        """, (url, title, content))
        conn.commit()


def get_articles():
    """Return all active help-center articles."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT url, title, content
            FROM articles
            WHERE active = 1
            ORDER BY title
        """).fetchall()


def find_article_by_url(url: str):
    """Find an active article by its exact URL."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT url, title, content
            FROM articles
            WHERE url = ? AND active = 1
        """, (url,)).fetchone()


def save_expert_feedback(
    question: str,
    expert_answer: str,
) -> int:
    """Save an expert answer pending review and return its ID."""
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO expert_feedback (question, expert_answer)
            VALUES (?, ?)
        """, (question, expert_answer))
        conn.commit()
        return cursor.lastrowid


def get_expert_feedback(status: str = "pending"):
    """Return feedback filtered by review status."""
    allowed_statuses = {"pending", "approved", "rejected"}

    if status not in allowed_statuses:
        raise ValueError(
            "Status must be 'pending', 'approved', or 'rejected'."
        )

    with get_connection() as conn:
        return conn.execute("""
            SELECT id, question, expert_answer, status, created_at
            FROM expert_feedback
            WHERE status = ?
            ORDER BY created_at DESC, id DESC
        """, (status,)).fetchall()


def update_feedback_status(feedback_id: int, status: str) -> bool:
    """Approve or reject feedback and report whether it exists."""
    allowed_statuses = {"pending", "approved", "rejected"}

    if status not in allowed_statuses:
        raise ValueError(
            "Status must be 'pending', 'approved', or 'rejected'."
        )

    with get_connection() as conn:
        cursor = conn.execute("""
            UPDATE expert_feedback
            SET status = ?
            WHERE id = ?
        """, (status, feedback_id))
        conn.commit()
        return cursor.rowcount > 0


def start_ingestion_run(discovered: int) -> int:
    with get_connection() as conn:
        cursor = conn.execute("INSERT INTO ingestion_runs(status, discovered) VALUES ('running', ?)", (discovered,))
        conn.commit()
        return int(cursor.lastrowid)


def update_ingestion_run(run_id: int, *, processed: int, saved: int, failed: int, current_url: str | None = None, status: str = "running") -> None:
    finished = "CURRENT_TIMESTAMP" if status in {"completed", "failed"} else "NULL"
    with get_connection() as conn:
        conn.execute(f"UPDATE ingestion_runs SET processed=?, saved=?, failed=?, current_url=?, status=?, finished_at={finished} WHERE id=?", (processed, saved, failed, current_url, status, run_id))
        conn.commit()


def get_latest_ingestion_run():
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM ingestion_runs ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None
