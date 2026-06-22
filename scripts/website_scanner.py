from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from bs4 import BeautifulSoup

from scripts.company_search import normalize_domain
from scripts.contact_extractor import extract_public_contacts, visible_text_from_html
from scripts.database import generate_lead_id, record_error, utc_now
from scripts.models import EmailStatus, LeadStatus, ScanResult
from scripts.website_fetcher import fetch_site_pages


def text_lines(text: str) -> list[str]:
    return [line.strip() for line in re.split(r"[\n\r]+", text or "") if line.strip()]


def snippet_evidence(text: str, needle: str, radius: int = 180) -> str:
    if not text:
        return ""
    lower = text.lower()
    index = lower.find((needle or "").lower())
    if index < 0:
        return re.sub(r"\s+", " ", text[: radius * 2]).strip()
    start = max(0, index - radius)
    end = min(len(text), index + len(needle) + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def first_meaningful_paragraph(html: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return str(meta["content"]).strip()
    for tag in soup.find_all(["p", "h1", "h2"]):
        value = tag.get_text(" ", strip=True)
        if len(value) >= 40:
            return value
    _, text = visible_text_from_html(html)
    lines = text_lines(text)
    return max(lines, key=len) if lines else ""


def infer_industry(text: str, config) -> tuple[str, str]:
    haystack = (text or "").lower()
    for industry in config.target.get("industries", []) or []:
        if industry and industry.lower() in haystack:
            return industry, snippet_evidence(text, industry)
    product = config.business.get("product", "")
    if product and product.lower() in haystack:
        return product, snippet_evidence(text, product)
    return "", ""


def infer_country(text: str, fallback: str, config) -> str:
    haystack = (text or "").lower()
    for country in config.target.get("countries", []) or []:
        if country and country.lower() in haystack:
            return country
    return fallback or ""


def scan_company_website(company: dict[str, Any], config) -> ScanResult:
    website = company["website"]
    domain = company.get("domain") or normalize_domain(website)
    max_pages = min(int(config.limits.get("websites_per_run", 10)), 10)
    fetch_results = fetch_site_pages(website, config, max_pages=max_pages)
    errors = [result.error for result in fetch_results if result.error]
    successful_pages = [result for result in fetch_results if result.text and 200 <= result.status_code < 400]

    if not successful_pages:
        return ScanResult(
            company_name=company["company_name"],
            website=website,
            domain=domain,
            country=company.get("country", ""),
            source_url=company.get("source_url", website),
            errors=errors or ["No readable public pages found."],
        )

    combined_text_parts: list[str] = []
    summary = ""
    source_url = successful_pages[0].final_url
    contacts = []
    for page in successful_pages:
        _, text = visible_text_from_html(page.text)
        combined_text_parts.append(text)
        if not summary:
            summary = first_meaningful_paragraph(page.text)
        contacts.extend(extract_public_contacts(page.text, page.final_url, domain))

    combined_text = "\n".join(combined_text_parts)
    industry, industry_evidence = infer_industry(combined_text, config)
    evidence_text = industry_evidence or summary or snippet_evidence(combined_text, company["company_name"])
    country = infer_country(combined_text, company.get("country", ""), config)

    return ScanResult(
        company_name=company["company_name"],
        website=website,
        domain=domain,
        country=country,
        industry=industry,
        company_summary=summary[:1000],
        evidence_text=evidence_text[:1000],
        source_url=source_url,
        contacts=contacts,
        errors=errors,
    )


def upsert_scan_result(conn: sqlite3.Connection, company: sqlite3.Row, result: ScanResult, task_id: int | None = None) -> int:
    now = utc_now()
    conn.execute(
        """
        UPDATE companies
        SET status = ?, country = ?, evidence_text = ?, updated_at = ?
        WHERE company_id = ?
        """,
        (LeadStatus.SCANNED.value, result.country, result.evidence_text, now, company["company_id"]),
    )

    inserted_or_updated = 0
    if result.contacts:
        for contact in result.contacts:
            normalized_email = contact.email.lower() if contact.email else None
            cursor = conn.execute(
                """
                INSERT INTO contacts(
                    company_id, contact_name, job_title, email, normalized_email, email_status,
                    phone, whatsapp, source_url, evidence_text, confidence, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(normalized_email) DO UPDATE SET
                    contact_name = COALESCE(NULLIF(excluded.contact_name, ''), contacts.contact_name),
                    job_title = COALESCE(NULLIF(excluded.job_title, ''), contacts.job_title),
                    email_status = excluded.email_status,
                    phone = COALESCE(NULLIF(excluded.phone, ''), contacts.phone),
                    whatsapp = COALESCE(NULLIF(excluded.whatsapp, ''), contacts.whatsapp),
                    source_url = excluded.source_url,
                    evidence_text = excluded.evidence_text,
                    updated_at = excluded.updated_at
                """,
                (
                    company["company_id"],
                    contact.contact_name,
                    contact.job_title,
                    contact.email,
                    normalized_email,
                    contact.status.value,
                    contact.phone,
                    contact.whatsapp,
                    contact.source_url,
                    contact.evidence_text,
                    0.9 if contact.status == EmailStatus.PUBLIC_CONFIRMED else 0.6,
                    now,
                    now,
                ),
            )
            if normalized_email:
                contact_id_row = conn.execute(
                    "SELECT contact_id FROM contacts WHERE normalized_email = ?",
                    (normalized_email,),
                ).fetchone()
                contact_id = contact_id_row["contact_id"] if contact_id_row else cursor.lastrowid
            else:
                contact_id = cursor.lastrowid
            lead_id = generate_lead_id(result.domain, contact.email or contact.whatsapp or contact.phone)
            conn.execute(
                """
                INSERT INTO leads(
                    lead_id, task_id, company_id, contact_id, company_name, website, domain,
                    country, industry, company_summary, contact_name, job_title, email,
                    email_status, phone, whatsapp, source_url, evidence_text, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(domain, email) DO UPDATE SET
                    company_name = excluded.company_name,
                    website = excluded.website,
                    country = excluded.country,
                    industry = excluded.industry,
                    company_summary = excluded.company_summary,
                    contact_name = excluded.contact_name,
                    job_title = excluded.job_title,
                    email_status = excluded.email_status,
                    phone = COALESCE(NULLIF(excluded.phone, ''), leads.phone),
                    whatsapp = COALESCE(NULLIF(excluded.whatsapp, ''), leads.whatsapp),
                    source_url = excluded.source_url,
                    evidence_text = excluded.evidence_text,
                    updated_at = excluded.updated_at,
                    status = CASE
                        WHEN leads.status IN ('SENT', 'SEND_UNKNOWN', 'REPLIED', 'DO_NOT_CONTACT') THEN leads.status
                        ELSE excluded.status
                    END
                """,
                (
                    lead_id,
                    task_id,
                    company["company_id"],
                    contact_id,
                    result.company_name,
                    result.website,
                    result.domain,
                    result.country,
                    result.industry,
                    result.company_summary,
                    contact.contact_name,
                    contact.job_title,
                    contact.email or None,
                    contact.status.value,
                    contact.phone,
                    contact.whatsapp,
                    contact.source_url,
                    contact.evidence_text,
                    LeadStatus.SCANNED.value,
                    now,
                    now,
                ),
            )
            inserted_or_updated += 1
    else:
        lead_id = generate_lead_id(result.domain, "")
        conn.execute(
            """
            INSERT INTO leads(
                lead_id, task_id, company_id, company_name, website, domain, country,
                industry, company_summary, email, email_status, source_url, evidence_text,
                phone, whatsapp, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(lead_id) DO UPDATE SET
                country = excluded.country,
                industry = excluded.industry,
                company_summary = excluded.company_summary,
                source_url = excluded.source_url,
                evidence_text = excluded.evidence_text,
                phone = excluded.phone,
                whatsapp = excluded.whatsapp,
                updated_at = excluded.updated_at
            """,
            (
                lead_id,
                task_id,
                company["company_id"],
                result.company_name,
                result.website,
                result.domain,
                result.country,
                result.industry,
                result.company_summary,
                "",
                EmailStatus.UNKNOWN.value,
                result.source_url,
                result.evidence_text,
                "",
                "",
                LeadStatus.REVIEW_REQUIRED.value,
                now,
                now,
            ),
        )
        inserted_or_updated = 1
    return inserted_or_updated


def scan_pending_companies(conn: sqlite3.Connection, config, *, task_id: int | None = None) -> tuple[int, list[str]]:
    limit = int(config.limits.get("websites_per_run", 10))
    companies = conn.execute(
        """
        SELECT * FROM companies
        WHERE status IN ('DISCOVERED', 'NEW', 'ERROR')
        ORDER BY company_id
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    processed = 0
    errors: list[str] = []
    for company in companies:
        try:
            result = scan_company_website(dict(company), config)
            if result.errors and not result.evidence_text:
                message = "; ".join(result.errors)
                conn.execute(
                    "UPDATE companies SET status = ?, updated_at = ? WHERE company_id = ?",
                    (LeadStatus.ERROR.value, utc_now(), company["company_id"]),
                )
                record_error(
                    conn,
                    task_id=task_id,
                    company_id=company["company_id"],
                    action="scan",
                    error_type="FetchError",
                    message=message,
                    source_url=company["website"],
                )
                errors.append(f"{company['company_name']}: {message}")
            else:
                upsert_scan_result(conn, company, result, task_id=task_id)
            conn.commit()
            processed += 1
        except Exception as exc:
            conn.rollback()
            message = f"{company['company_name']}: {type(exc).__name__}: {exc}"
            errors.append(message)
            existing_company = conn.execute(
                "SELECT company_id FROM companies WHERE company_id = ?",
                (company["company_id"],),
            ).fetchone()
            existing_task = (
                conn.execute("SELECT task_id FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
                if task_id is not None
                else None
            )
            record_error(
                conn,
                task_id=task_id if existing_task else None,
                company_id=company["company_id"] if existing_company else None,
                action="scan",
                error_type=type(exc).__name__,
                message=str(exc),
                source_url=company["website"],
            )
            if existing_company:
                conn.execute(
                    "UPDATE companies SET status = ?, updated_at = ? WHERE company_id = ?",
                    (LeadStatus.ERROR.value, utc_now(), company["company_id"]),
                )
            conn.commit()
    return processed, errors


def score_details_json(details: dict[str, Any]) -> str:
    return json.dumps(details, ensure_ascii=False)
