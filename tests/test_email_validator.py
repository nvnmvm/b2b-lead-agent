from __future__ import annotations

from pathlib import Path

from scripts.approval import approve_send
from scripts.database import db_session, init_db, utc_now
from scripts.email_validator import is_sendable_email_status, validate_approval_candidate


def seed_draft(conn, *, lead_id: str = "lead-acme", email_status: str = "PUBLIC_CONFIRMED", status: str = "DRAFTED") -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO leads(
            lead_id, company_name, website, domain, country, industry, company_summary,
            contact_name, job_title, email, email_status, source_url, evidence_text,
            score, score_level, status, created_at, updated_at, draft_created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            lead_id,
            "Acme Pump Systems",
            "https://acmepumps.test",
            "acmepumps.test",
            "Germany",
            "industrial pumps",
            "Industrial pumps distributor.",
            "Anna Weber",
            "Procurement Manager",
            "anna.weber@acmepumps.test",
            email_status,
            "https://acmepumps.test/contact",
            "Acme Pump Systems is an industrial pumps distributor in Germany.",
            90,
            "HIGH",
            status,
            now,
            now,
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO email_drafts(
            lead_id, subject, body, personalization_sentence,
            personalization_evidence, source_url, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            lead_id,
            "Quick question about Acme Pump Systems",
            "Hi Anna,\n\nReviewable draft body.\n\nBest regards,\nJane",
            "I noticed this on your website: Acme Pump Systems is an industrial pumps distributor in Germany.",
            "Acme Pump Systems is an industrial pumps distributor in Germany.",
            "https://acmepumps.test/contact",
            now,
        ),
    )


def test_sendable_email_status_rules() -> None:
    assert is_sendable_email_status("PUBLIC_CONFIRMED")
    assert is_sendable_email_status("PUBLIC_DOMAIN_MISMATCH")
    assert not is_sendable_email_status("GUESSED")
    assert not is_sendable_email_status("INVALID")


def test_validate_approval_candidate_blocks_guessed_email() -> None:
    errors = validate_approval_candidate({"email": "anna@acme.test", "email_status": "GUESSED", "status": "DRAFTED"})
    assert any("Guessed emails" in error for error in errors)


def test_approve_send_requires_second_confirmation(tmp_path: Path) -> None:
    db_path = tmp_path / "leads.sqlite"
    init_db(db_path)
    with db_session(db_path) as conn:
        seed_draft(conn)
        result = approve_send(conn, "lead-acme", confirm=False, output_dir=tmp_path / "output")
        row = conn.execute("SELECT status FROM leads WHERE lead_id = 'lead-acme'").fetchone()

    assert result["success"] is True
    assert result["requires_approval"] is True
    assert result["processed"] == 0
    assert result["data"]["recipient"] == "anna.weber@acmepumps.test"
    assert row["status"] == "DRAFTED"


def test_approve_send_confirm_records_approval_without_sending(tmp_path: Path) -> None:
    db_path = tmp_path / "leads.sqlite"
    output_dir = tmp_path / "output"
    init_db(db_path)
    with db_session(db_path) as conn:
        seed_draft(conn)
        result = approve_send(conn, "lead-acme", confirm=True, output_dir=output_dir)
        lead = conn.execute("SELECT status, approved_at, sent_at FROM leads WHERE lead_id = 'lead-acme'").fetchone()
        approvals = conn.execute("SELECT provider, result_status FROM send_approvals").fetchone()

    assert result["success"] is True
    assert result["requires_approval"] is False
    assert result["processed"] == 1
    assert lead["status"] == "APPROVED"
    assert lead["approved_at"]
    assert lead["sent_at"] is None
    assert approvals["provider"] == "draft_only"
    assert approvals["result_status"] == "APPROVED_DRAFT_ONLY"
    assert all(Path(path).exists() for path in result["data"]["review_files"])


def test_approve_send_blocks_guessed_email(tmp_path: Path) -> None:
    db_path = tmp_path / "leads.sqlite"
    init_db(db_path)
    with db_session(db_path) as conn:
        seed_draft(conn, lead_id="lead-guessed", email_status="GUESSED")
        result = approve_send(conn, "lead-guessed", confirm=True, output_dir=tmp_path / "output")
        approvals = conn.execute("SELECT COUNT(*) FROM send_approvals").fetchone()[0]

    assert result["success"] is False
    assert approvals == 0
    assert any("Guessed emails" in error for error in result["errors"])

