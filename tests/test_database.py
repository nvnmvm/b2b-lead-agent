from __future__ import annotations

from pathlib import Path

from scripts.company_search import import_companies_csv, normalize_domain, upsert_company
from scripts.config_loader import AppConfig
from scripts.database import create_task, db_session, finish_task, init_db, status_counts
from scripts.website_scanner import scan_pending_companies


def test_database_initializes_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "leads.sqlite"
    init_db(db_path)
    with db_session(db_path) as conn:
        task_id = create_task(conn, "test")
        finish_task(conn, task_id)
        counts = status_counts(conn)
    assert counts["tasks"] == 1
    assert counts["companies"] == 0


def scanner_config(tmp_path: Path) -> AppConfig:
    raw = {
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
    }
    return AppConfig(path=tmp_path / "config.yaml", raw=raw)


def test_scan_pending_company_writes_contacts_and_leads(tmp_path: Path) -> None:
    db_path = tmp_path / "leads.sqlite"
    init_db(db_path)
    fixture = Path("tests/fixtures/acme.html").resolve()
    config = scanner_config(tmp_path)
    with db_session(db_path) as conn:
        conn.execute(
            """
            INSERT INTO companies(company_name, website, domain, country, source_url, status, created_at, updated_at)
            VALUES ('Acme Pump Systems', ?, 'acmepumps.test', 'Germany', ?, 'DISCOVERED', 'now', 'now')
            """,
            (str(fixture), str(fixture)),
        )
        processed, errors = scan_pending_companies(conn, config)
        counts = status_counts(conn)
        company = conn.execute("SELECT status, evidence_text FROM companies").fetchone()
        lead = conn.execute(
            "SELECT email, email_status, phone, whatsapp, industry, source_url, evidence_text FROM leads WHERE email = ?",
            ("anna.weber@acmepumps.test",),
        ).fetchone()

    assert processed == 1
    assert errors == []
    assert counts["contacts"] == 2
    assert counts["leads"] == 2
    assert company["status"] == "SCANNED"
    assert "industrial pumps" in company["evidence_text"]
    assert lead["email_status"] == "PUBLIC_CONFIRMED"
    assert lead["phone"] == "+493012345678"
    assert lead["whatsapp"] == ""
    assert lead["industry"] == "industrial pumps"
    assert lead["source_url"]
    assert lead["evidence_text"]


def test_domain_normalization_removes_scheme_www_path_and_query() -> None:
    assert normalize_domain("https://www.example.com/path/to/page?x=1") == "example.com"
    assert normalize_domain("http://example.com/") == "example.com"


def test_company_dedup_by_domain_and_company_country(tmp_path: Path) -> None:
    db_path = tmp_path / "leads.sqlite"
    init_db(db_path)
    now = "2026-01-01T00:00:00Z"
    with db_session(db_path) as conn:
        upsert_company(
            conn,
            {
                "company_name": "Acme Pump Systems",
                "website": "https://www.acme.test",
                "domain": "acme.test",
                "country": "Germany",
                "source_url": "source-a",
                "status": "DISCOVERED",
                "created_at": now,
                "updated_at": now,
            },
        )
        upsert_company(
            conn,
            {
                "company_name": "Acme Pump Systems",
                "website": "https://acme.test/contact",
                "domain": "acme.test",
                "country": "Germany",
                "source_url": "source-b",
                "status": "DISCOVERED",
                "created_at": now,
                "updated_at": now,
            },
        )
        upsert_company(
            conn,
            {
                "company_name": "Acme Pump Systems",
                "website": "https://different-domain.test",
                "domain": "different-domain.test",
                "country": "Germany",
                "source_url": "source-c",
                "status": "DISCOVERED",
                "created_at": now,
                "updated_at": now,
            },
        )
        count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        company = conn.execute("SELECT domain, source_url FROM companies").fetchone()
    assert count == 1
    assert company["domain"] == "different-domain.test"
    assert company["source_url"] == "source-c"


def test_csv_import_and_scan_resume(tmp_path: Path) -> None:
    db_path = tmp_path / "leads.sqlite"
    init_db(db_path)
    acme = Path("tests/fixtures/acme.html").resolve()
    beta = Path("tests/fixtures/beta.html").resolve()
    csv_path = tmp_path / "companies.csv"
    csv_path.write_text(
        "\n".join(
            [
                "company_name,website,country,source_url",
                f"Acme Pump Systems,{acme},Germany,fixture://acme",
                f"Beta Water Technology,{beta},Germany,fixture://beta",
            ]
        ),
        encoding="utf-8",
    )
    config = scanner_config(tmp_path)
    config.raw["limits"]["websites_per_run"] = 1

    with db_session(db_path) as conn:
        imported = import_companies_csv(conn, csv_path)
        first_processed, first_errors = scan_pending_companies(conn, config)
        second_processed, second_errors = scan_pending_companies(conn, config)
        statuses = {
            row["status"]: row["count"]
            for row in conn.execute("SELECT status, COUNT(*) AS count FROM companies GROUP BY status")
        }

    assert imported == 2
    assert first_processed == 1
    assert second_processed == 1
    assert first_errors == []
    assert second_errors == []
    assert statuses == {"SCANNED": 2}
