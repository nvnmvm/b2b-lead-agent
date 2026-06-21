from __future__ import annotations

from pathlib import Path

from scripts.config_loader import AppConfig
from scripts.database import db_session, init_db, utc_now
from scripts.email_generator import draft_pending_leads, generate_email_draft, word_count


def draft_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        path=tmp_path / "config.yaml",
        raw={
            "business": {
                "company_name": "Acme Export",
                "product": "industrial pumps",
                "product_description": "pump parts for water treatment systems",
                "advantages": ["stable quality", "responsive engineering support"],
                "sender_name": "Jane Smith",
                "sender_title": "Export Manager",
                "sender_email": "jane@acme.example",
                "company_website": "https://acme.example",
            },
            "target": {
                "countries": ["Germany"],
                "industries": ["industrial pumps"],
                "customer_types": ["distributor"],
                "company_sizes": ["medium"],
                "preferred_titles": ["Procurement Manager"],
                "excluded_keywords": [],
            },
            "limits": {
                "companies_per_run": 10,
                "websites_per_run": 10,
                "drafts_per_run": 5,
                "request_interval_min_seconds": 0,
                "request_interval_max_seconds": 0,
                "request_timeout_seconds": 10,
                "retry_count": 2,
            },
            "scoring": {"minimum_qualified_score": 70, "minimum_draft_score": 75},
            "browser": {"headless": True, "use_playwright_fallback": False},
            "email": {"mode": "draft_only", "allow_guessed_email": False, "require_manual_approval": True},
        },
    )


def qualified_lead(lead_id: str = "lead-acme", email: str = "anna.weber@acmepumps.test", status: str = "QUALIFIED") -> dict:
    return {
        "lead_id": lead_id,
        "company_name": "Acme Pump Systems",
        "website": "https://acmepumps.test",
        "domain": "acmepumps.test",
        "country": "Germany",
        "industry": "industrial pumps",
        "company_summary": "Industrial pumps distributor for water treatment equipment.",
        "contact_name": "Anna Weber",
        "job_title": "Procurement Manager",
        "email": email,
        "email_status": "PUBLIC_CONFIRMED",
        "source_url": "https://acmepumps.test/contact",
        "evidence_text": "Acme Pump Systems is an industrial pumps distributor in Germany.",
        "score": 90,
        "score_level": "HIGH",
        "status": status,
    }


def test_generate_email_draft_uses_evidence_and_word_limit(tmp_path: Path) -> None:
    draft = generate_email_draft(qualified_lead(), draft_config(tmp_path))
    assert draft["subject"] == "Quick question about Acme Pump Systems"
    assert "Acme Pump Systems is an industrial pumps distributor in Germany" in draft["body"]
    assert draft["personalization_evidence"]
    assert draft["source_url"] == "https://acmepumps.test/contact"
    assert 80 <= word_count(draft["body"]) <= 150
    assert "will not follow up" in draft["body"]


def insert_lead(conn, lead: dict) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO leads(
            lead_id, company_name, website, domain, country, industry, company_summary,
            contact_name, job_title, email, email_status, source_url, evidence_text,
            score, score_level, status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            lead["lead_id"],
            lead["company_name"],
            lead["website"],
            lead["domain"],
            lead["country"],
            lead["industry"],
            lead["company_summary"],
            lead["contact_name"],
            lead["job_title"],
            lead["email"],
            lead["email_status"],
            lead["source_url"],
            lead["evidence_text"],
            lead["score"],
            lead["score_level"],
            lead["status"],
            now,
            now,
        ),
    )


def test_draft_pending_leads_skips_duplicate_email(tmp_path: Path) -> None:
    db_path = tmp_path / "leads.sqlite"
    init_db(db_path)
    first = qualified_lead("lead-one", "anna.weber@acmepumps.test")
    second = qualified_lead("lead-two", "anna.weber@acmepumps.test")
    second["domain"] = "other-domain.test"
    second["website"] = "https://other-domain.test"

    with db_session(db_path) as conn:
        insert_lead(conn, first)
        insert_lead(conn, second)
        processed, errors = draft_pending_leads(conn, draft_config(tmp_path))
        draft_count = conn.execute("SELECT COUNT(*) FROM email_drafts").fetchone()[0]

    assert processed == 1
    assert errors == []
    assert draft_count == 1


def test_draft_pending_leads_does_not_draft_guessed_email(tmp_path: Path) -> None:
    db_path = tmp_path / "leads.sqlite"
    init_db(db_path)
    lead = qualified_lead("lead-guessed", "anna.weber@acmepumps.test")
    lead["email_status"] = "GUESSED"

    with db_session(db_path) as conn:
        insert_lead(conn, lead)
        processed, errors = draft_pending_leads(conn, draft_config(tmp_path))
        draft_count = conn.execute("SELECT COUNT(*) FROM email_drafts").fetchone()[0]

    assert processed == 0
    assert errors == []
    assert draft_count == 0

