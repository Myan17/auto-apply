"""SQLite database for tracking applications."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .config import DATA_DIR

DB_PATH = DATA_DIR / "auto_apply.db"


def get_connection() -> sqlite3.Connection:
    """Get a database connection, creating the DB if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            company TEXT,
            role TEXT,
            portal_type TEXT,
            description TEXT,
            application_email TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            method TEXT,
            resume_path TEXT,
            cover_letter_path TEXT,
            screenshot_path TEXT,
            error_message TEXT,
            applied_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url);
        CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);
    """)
    conn.commit()
    conn.close()


def upsert_job(url: str, company: str = "", role: str = "",
               portal_type: str = "", description: str = "",
               application_email: str = "") -> int:
    """Insert or update a job. Returns the job ID."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM jobs WHERE url = ?", (url,))
    row = cursor.fetchone()

    if row:
        job_id = row["id"]
        cursor.execute("""
            UPDATE jobs SET company=?, role=?, portal_type=?,
                           description=?, application_email=?
            WHERE id=?
        """, (company, role, portal_type, description, application_email, job_id))
    else:
        cursor.execute("""
            INSERT INTO jobs (url, company, role, portal_type, description, application_email)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (url, company, role, portal_type, description, application_email))
        job_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return job_id


def record_application(job_id: int, status: str, method: str = "",
                       resume_path: str = "", cover_letter_path: str = "",
                       screenshot_path: str = "", error_message: str = "") -> int:
    """Record an application attempt. Returns the application ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO applications (job_id, status, method, resume_path,
                                  cover_letter_path, screenshot_path, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (job_id, status, method, resume_path, cover_letter_path,
          screenshot_path, error_message))
    app_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return app_id


def has_successful_application(url: str) -> bool:
    """Check if we've already successfully applied to this URL."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id FROM applications a
        JOIN jobs j ON a.job_id = j.id
        WHERE j.url = ? AND a.status = 'applied'
        LIMIT 1
    """, (url,))
    result = cursor.fetchone() is not None
    conn.close()
    return result


def get_stats() -> dict:
    """Get application statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}
    cursor.execute("SELECT COUNT(*) as total FROM jobs")
    stats["total_jobs"] = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM applications
        GROUP BY status
    """)
    stats["by_status"] = {row["status"]: row["count"] for row in cursor.fetchall()}

    cursor.execute("""
        SELECT method, COUNT(*) as count
        FROM applications
        WHERE status = 'applied'
        GROUP BY method
    """)
    stats["by_method"] = {row["method"]: row["count"] for row in cursor.fetchall()}

    cursor.execute("""
        SELECT COUNT(*) as count FROM applications
        WHERE applied_at >= date('now', '-1 day')
    """)
    stats["last_24h"] = cursor.fetchone()["count"]

    conn.close()
    return stats
