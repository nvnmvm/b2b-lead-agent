from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from scripts.database import utc_now
from scripts.email_validator import validate_approval_candidate
from scripts.exporter import OUTPUT_DIR, write_draft_review_files
from scripts.models import LeadStatus


def fetch_approval_record(conn: sqlite3.Connection, lead_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            leads.lead_id,
            leads.company_name,
            leads.email,
            leads.email_status,
            leads.status,
            email_drafts.subject,
            email_drafts.body,
            email_drafts.source_url
        FROM leads
        LEFT JOIN email_drafts ON email_drafts.lead_id = leads.lead_id
        WHERE leads.lead_id = ?
        """,
        (lead_id,),
    ).fetchone()
    return dict(row) if row else None


def body_preview(body: str, limit: int = 320) -> str:
    text = " ".join((body or "").split())
    return text[:limit] + ("..." if len(text) > limit else "")


def approve_send(
    conn: sqlite3.Connection,
    lead_id: str,
    *,
    confirm: bool = False,
    approved_by: str = "human",
    output_dir: str | Path = OUTPUT_DIR,
) -> dict[str, Any]:
    record = fetch_approval_record(conn, lead_id)
    if not record:
        return {"success": False, "requires_approval": False, "processed": 0, "errors": [f"Lead not found: {lead_id}"], "data": {}}
    if not record.get("subject") or not record.get("body"):
        return {
            "success": False,
            "requires_approval": False,
            "processed": 0,
            "errors": [f"Lead has no draft to approve: {lead_id}"],
            "data": {},
        }

    validation_errors = validate_approval_candidate(record)
    if validation_errors:
        return {"success": False, "requires_approval": False, "processed": 0, "errors": validation_errors, "data": {}}

    preview = {
        "lead_id": record["lead_id"],
        "recipient": record["email"],
        "subject": record["subject"],
        "body_preview": body_preview(record["body"]),
        "mode": "draft_only",
    }

    if not confirm:
        return {
            "success": True,
            "requires_approval": True,
            "processed": 0,
            "errors": [],
            "data": preview,
        }

    now = utc_now()
    conn.execute(
        """
        INSERT INTO send_approvals(lead_id, approved_by, approved_at, provider, provider_message_id, result_status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (lead_id, approved_by, now, "draft_only", "", "APPROVED_DRAFT_ONLY"),
    )
    conn.execute(
        "UPDATE leads SET status = ?, approved_at = ?, updated_at = ? WHERE lead_id = ?",
        (LeadStatus.APPROVED.value, now, now, lead_id),
    )
    files = write_draft_review_files(
        [
            {
                "lead_id": record["lead_id"],
                "email": record["email"],
                "subject": record["subject"],
                "body": record["body"],
                "source_url": record["source_url"],
            }
        ],
        Path(output_dir),
    )
    preview["review_files"] = files
    preview["result_status"] = "APPROVED_DRAFT_ONLY"
    return {"success": True, "requires_approval": False, "processed": 1, "errors": [], "data": preview}

