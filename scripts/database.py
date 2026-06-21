from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from scripts.models import LeadStatus


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "leads.sqlite"


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session(db_path: str | Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    with db_session(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                details TEXT
            );

            CREATE TABLE IF NOT EXISTS companies (
                company_id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                website TEXT NOT NULL,
                domain TEXT NOT NULL,
                country TEXT,
                source_url TEXT,
                status TEXT NOT NULL DEFAULT 'DISCOVERED',
                evidence_text TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(domain),
                UNIQUE(company_name, country)
            );

            CREATE TABLE IF NOT EXISTS contacts (
                contact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                contact_name TEXT,
                job_title TEXT,
                email TEXT,
                normalized_email TEXT,
                email_status TEXT NOT NULL,
                phone TEXT,
                source_url TEXT,
                evidence_text TEXT,
                confidence REAL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
                UNIQUE(normalized_email)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_name_company
            ON contacts(contact_name, company_id)
            WHERE contact_name IS NOT NULL AND contact_name != '';

            CREATE TABLE IF NOT EXISTS leads (
                lead_id TEXT PRIMARY KEY,
                task_id INTEGER,
                company_id INTEGER,
                contact_id INTEGER,
                company_name TEXT NOT NULL,
                website TEXT NOT NULL,
                domain TEXT NOT NULL,
                country TEXT,
                industry TEXT,
                company_summary TEXT,
                contact_name TEXT,
                job_title TEXT,
                email TEXT,
                email_status TEXT,
                source_url TEXT,
                evidence_text TEXT,
                score INTEGER DEFAULT 0,
                score_level TEXT,
                score_details TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                draft_created_at TEXT,
                approved_at TEXT,
                sent_at TEXT,
                error_message TEXT,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id),
                FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE SET NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(contact_id) ON DELETE SET NULL,
                UNIQUE(domain, email)
            );

            CREATE TABLE IF NOT EXISTS email_drafts (
                draft_id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                personalization_sentence TEXT,
                personalization_evidence TEXT,
                source_url TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(lead_id) REFERENCES leads(lead_id) ON DELETE CASCADE,
                UNIQUE(lead_id)
            );

            CREATE TABLE IF NOT EXISTS send_approvals (
                approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id TEXT NOT NULL,
                approved_by TEXT,
                approved_at TEXT NOT NULL,
                provider TEXT,
                provider_message_id TEXT,
                result_status TEXT NOT NULL,
                FOREIGN KEY(lead_id) REFERENCES leads(lead_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS errors (
                error_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                company_id INTEGER,
                lead_id TEXT,
                action TEXT NOT NULL,
                error_type TEXT NOT NULL,
                message TEXT NOT NULL,
                source_url TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                resolved INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id),
                FOREIGN KEY(company_id) REFERENCES companies(company_id),
                FOREIGN KEY(lead_id) REFERENCES leads(lead_id)
            );

            CREATE TABLE IF NOT EXISTS do_not_contact (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                normalized_email TEXT,
                domain TEXT,
                reason TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(normalized_email),
                UNIQUE(domain)
            );
            """
        )


def create_task(conn: sqlite3.Connection, action: str, details: dict[str, Any] | None = None) -> int:
    now = utc_now()
    cursor = conn.execute(
        "INSERT INTO tasks(action, status, started_at, details) VALUES (?, ?, ?, ?)",
        (action, "RUNNING", now, json.dumps(details or {}, ensure_ascii=False)),
    )
    return int(cursor.lastrowid)


def finish_task(conn: sqlite3.Connection, task_id: int, status: str = "DONE", details: dict[str, Any] | None = None) -> None:
    conn.execute(
        "UPDATE tasks SET status = ?, finished_at = ?, details = COALESCE(?, details) WHERE task_id = ?",
        (status, utc_now(), json.dumps(details, ensure_ascii=False) if details is not None else None, task_id),
    )


def record_error(
    conn: sqlite3.Connection,
    *,
    action: str,
    error_type: str,
    message: str,
    task_id: int | None = None,
    company_id: int | None = None,
    lead_id: str | None = None,
    source_url: str | None = None,
) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO errors(task_id, company_id, lead_id, action, error_type, message, source_url, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (task_id, company_id, lead_id, action, error_type, message, source_url, now, now),
    )


def status_counts(conn: sqlite3.Connection) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    for table in ("tasks", "companies", "contacts", "leads", "email_drafts", "errors", "do_not_contact"):
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    counts["lead_statuses"] = {
        row["status"]: row["count"]
        for row in conn.execute("SELECT status, COUNT(*) AS count FROM leads GROUP BY status").fetchall()
    }
    counts["unresolved_errors"] = conn.execute("SELECT COUNT(*) FROM errors WHERE resolved = 0").fetchone()[0]
    return counts


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def generate_lead_id(domain: str, email: str | None = None) -> str:
    safe_domain = "".join(ch if ch.isalnum() else "-" for ch in domain.lower()).strip("-")
    safe_email = "".join(ch if ch.isalnum() else "-" for ch in normalize_email(email)).strip("-")
    suffix = safe_email[:40] if safe_email else "no-email"
    return f"lead-{safe_domain[:48]}-{suffix}"


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def reset_processing_errors(conn: sqlite3.Connection) -> int:
    rows = conn.execute("UPDATE errors SET resolved = 1, updated_at = ? WHERE resolved = 0", (utc_now(),))
    conn.execute(
        "UPDATE leads SET status = ?, updated_at = ? WHERE status = ?",
        (LeadStatus.DISCOVERED.value, utc_now(), LeadStatus.ERROR.value),
    )
    return int(rows.rowcount or 0)

