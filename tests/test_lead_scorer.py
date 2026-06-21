from __future__ import annotations

import json
from pathlib import Path

from scripts.config_loader import AppConfig
from scripts.database import db_session, init_db, utc_now
from scripts.lead_scorer import score_lead, score_pending_leads


def scoring_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        path=tmp_path / "config.yaml",
        raw={
            "business": {
                "company_name": "Acme Export",
                "product": "industrial pumps",
                "product_description": "pump parts for water treatment systems",
                "advantages": ["stable quality"],
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
                "preferred_titles": ["Owner", "Procurement Manager"],
                "excluded_keywords": ["school"],
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


def matching_lead() -> dict:
    return {
        "lead_id": "lead-acme",
        "company_name": "Acme Pump Systems",
        "country": "Germany",
        "industry": "industrial pumps",
        "company_summary": "Industrial pumps distributor for water treatment equipment and medium-size manufacturers.",
        "job_title": "Procurement Manager",
        "email_status": "PUBLIC_CONFIRMED",
        "evidence_text": "Acme Pump Systems is an industrial pumps distributor in Germany.",
    }


def test_score_lead_saves_component_scores(tmp_path: Path) -> None:
    details = score_lead(matching_lead(), scoring_config(tmp_path))
    assert details["industry_score"] == 30
    assert details["customer_type_score"] == 20
    assert details["country_score"] == 15
    assert details["product_relevance_score"] == 15
    assert details["title_score"] == 5
    assert details["contact_score"] == 5
    assert details["total"] >= 80
    assert details["level"] == "HIGH"
    assert details["reasons"]


def insert_lead(conn, lead_id: str, status: str) -> None:
    now = utc_now()
    lead = matching_lead()
    conn.execute(
        """
        INSERT INTO leads(
            lead_id, company_name, website, domain, country, industry, company_summary,
            contact_name, job_title, email, email_status, source_url, evidence_text,
            status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            lead_id,
            lead["company_name"],
            "https://acmepumps.test",
            "acmepumps.test",
            lead["country"],
            lead["industry"],
            lead["company_summary"],
            "Anna Weber",
            lead["job_title"],
            f"{lead_id}@acmepumps.test",
            lead["email_status"],
            "https://acmepumps.test",
            lead["evidence_text"],
            status,
            now,
            now,
        ),
    )


def test_score_pending_leads_updates_status_and_details(tmp_path: Path) -> None:
    db_path = tmp_path / "leads.sqlite"
    init_db(db_path)
    with db_session(db_path) as conn:
        insert_lead(conn, "lead-acme", "SCANNED")
        processed, qualified, errors = score_pending_leads(conn, scoring_config(tmp_path))
        row = conn.execute("SELECT status, score, score_level, score_details FROM leads WHERE lead_id = 'lead-acme'").fetchone()

    details = json.loads(row["score_details"])
    assert processed == 1
    assert qualified == 1
    assert errors == []
    assert row["status"] == "QUALIFIED"
    assert row["score"] == details["total"]
    assert row["score_level"] == "HIGH"
    assert "industry_score" in details


def test_score_pending_leads_does_not_overwrite_sent_status(tmp_path: Path) -> None:
    db_path = tmp_path / "leads.sqlite"
    init_db(db_path)
    with db_session(db_path) as conn:
        insert_lead(conn, "lead-sent", "SENT")
        processed, qualified, errors = score_pending_leads(conn, scoring_config(tmp_path))
        row = conn.execute("SELECT status, score_details FROM leads WHERE lead_id = 'lead-sent'").fetchone()

    assert processed == 0
    assert qualified == 0
    assert errors == []
    assert row["status"] == "SENT"
    assert row["score_details"] is None

