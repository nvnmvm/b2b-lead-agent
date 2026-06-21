from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.database import db_session, init_db, utc_now
from scripts.exporter import export_results


def seed_drafted_lead(conn) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO leads(
            lead_id, company_name, website, domain, country, industry, company_summary,
            contact_name, job_title, email, email_status, source_url, evidence_text,
            score, score_level, score_details, status, created_at, updated_at, draft_created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "lead-acme",
            "Acme Pump Systems",
            "https://acmepumps.test",
            "acmepumps.test",
            "Germany",
            "industrial pumps",
            "Industrial pumps distributor.",
            "Anna Weber",
            "Procurement Manager",
            "anna.weber@acmepumps.test",
            "PUBLIC_CONFIRMED",
            "https://acmepumps.test/contact",
            "Acme Pump Systems is an industrial pumps distributor in Germany.",
            90,
            "HIGH",
            json.dumps({"total": 90, "reasons": ["Industry matched: industrial pumps."]}),
            "DRAFTED",
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
            "lead-acme",
            "Quick question about Acme Pump Systems",
            "Hi Anna,\n\nThis is a reviewable draft body.\n\nBest regards,\nJane",
            "I noticed this on your website: Acme Pump Systems is an industrial pumps distributor in Germany.",
            "Acme Pump Systems is an industrial pumps distributor in Germany.",
            "https://acmepumps.test/contact",
            now,
        ),
    )


def test_export_results_creates_excel_json_and_review_files(tmp_path: Path) -> None:
    db_path = tmp_path / "leads.sqlite"
    output_dir = tmp_path / "output"
    init_db(db_path)
    with db_session(db_path) as conn:
        seed_drafted_lead(conn)
        result = export_results(conn, output_dir)

    leads_xlsx = Path(result["leads_xlsx"])
    drafts_xlsx = Path(result["drafts_xlsx"])
    leads_json = Path(result["leads_json"])
    summary_json = Path(result["summary_json"])

    assert leads_xlsx.exists()
    assert drafts_xlsx.exists()
    assert leads_json.exists()
    assert summary_json.exists()
    assert len(result["review_files"]) == 2
    assert all(Path(path).exists() for path in result["review_files"])

    exported = json.loads(leads_json.read_text(encoding="utf-8"))
    summary = json.loads(summary_json.read_text(encoding="utf-8"))
    frame = pd.read_excel(leads_xlsx)
    assert exported[0]["lead_id"] == "lead-acme"
    assert summary["exported_leads"] == 1
    assert frame.loc[0, "email"] == "anna.weber@acmepumps.test"

