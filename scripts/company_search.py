from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from scripts.database import utc_now


REQUIRED_CSV_COLUMNS = ("company_name", "website", "country", "source_url")


def normalize_domain(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    if value.startswith("/") or Path(value).expanduser().exists():
        return Path(value).expanduser().resolve().stem.lower()
    if "://" not in value and not value.startswith("file:"):
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme == "file":
        return Path(parsed.path).stem.lower()
    host = parsed.netloc or parsed.path
    host = host.split("@")[-1].split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host.rstrip("/")


def normalize_website(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    if value.startswith("file:"):
        return value
    if value.startswith("/") or Path(value).exists():
        return str(Path(value).expanduser().resolve())
    if "://" not in value:
        return "https://" + value.rstrip("/")
    return value.rstrip("/")


def load_companies_csv(csv_path: str | Path) -> list[dict[str, str]]:
    path = Path(csv_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        missing = [column for column in REQUIRED_CSV_COLUMNS if column not in fieldnames]
        if missing:
            raise ValueError(f"CSV is missing required column(s): {', '.join(missing)}")

        companies: list[dict[str, str]] = []
        for row_number, row in enumerate(reader, start=2):
            company_name = (row.get("company_name") or "").strip()
            website = normalize_website(row.get("website") or "")
            country = (row.get("country") or "").strip()
            source_url = (row.get("source_url") or "").strip()
            domain = normalize_domain(website)
            if not company_name or not website or not domain:
                raise ValueError(f"CSV row {row_number} must include company_name and website.")
            companies.append(
                {
                    "company_name": company_name,
                    "website": website,
                    "domain": domain,
                    "country": country,
                    "source_url": source_url or website,
                    "status": "DISCOVERED",
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                }
            )
    return companies


def upsert_company(conn: sqlite3.Connection, company: dict[str, str]) -> str:
    try:
        cursor = conn.execute(
            """
            INSERT INTO companies(company_name, website, domain, country, source_url, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
                company_name = excluded.company_name,
                website = excluded.website,
                country = COALESCE(NULLIF(excluded.country, ''), companies.country),
                source_url = COALESCE(NULLIF(excluded.source_url, ''), companies.source_url),
                updated_at = excluded.updated_at
            """,
            (
                company["company_name"],
                company["website"],
                company["domain"],
                company.get("country", ""),
                company.get("source_url", company["website"]),
                company.get("status", "DISCOVERED"),
                company.get("created_at", utc_now()),
                company.get("updated_at", utc_now()),
            ),
        )
        return "inserted" if cursor.rowcount == 1 else "updated"
    except sqlite3.IntegrityError:
        now = utc_now()
        country = company.get("country", "")
        existing = conn.execute(
            """
            SELECT company_id FROM companies
            WHERE lower(company_name) = lower(?) AND COALESCE(country, '') = COALESCE(?, '')
            """,
            (company["company_name"], country),
        ).fetchone()
        if not existing:
            raise
        conn.execute(
            """
            UPDATE companies
            SET website = ?, domain = ?, source_url = COALESCE(NULLIF(?, ''), source_url), updated_at = ?
            WHERE company_id = ?
            """,
            (company["website"], company["domain"], company.get("source_url", ""), now, existing["company_id"]),
        )
        return "updated"


def import_companies_csv(conn: sqlite3.Connection, csv_path: str | Path, *, limit: int | None = None) -> int:
    companies = load_companies_csv(csv_path)
    selected = companies[:limit] if limit is not None else companies
    processed = 0
    for company in selected:
        upsert_company(conn, company)
        processed += 1
    return processed


def build_search_queries(config: dict) -> list[str]:
    product = config.get("business", {}).get("product", "").strip()
    countries = config.get("target", {}).get("countries", []) or [""]
    industries = config.get("target", {}).get("industries", []) or [product]
    queries: list[str] = []
    for country in countries:
        for industry in industries:
            phrase = " ".join(part for part in (industry or product, country) if part).strip()
            if phrase:
                queries.append(f'"{phrase}" distributor')
                queries.append(f'"{phrase}" supplier')
                if country:
                    queries.append(f'site:.{country[:2].lower()} "{product}"')
    return list(dict.fromkeys(queries))

