from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from scripts.database import utc_now
from scripts.models import BLOCKED_RESEND_STATUSES, EmailStatus, LeadStatus


def normalize_words(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", (value or "").lower()) if len(word) > 2}


def contains_any(haystack: str, needles: list[str]) -> tuple[bool, str]:
    lower = (haystack or "").lower()
    for needle in needles:
        if needle and needle.lower() in lower:
            return True, needle
    return False, ""


def product_relevance_score(text: str, product: str, product_description: str) -> tuple[int, str]:
    product_words = normalize_words(product) | normalize_words(product_description)
    text_words = normalize_words(text)
    if not product_words:
        return 0, "No product keywords configured."
    overlap = product_words & text_words
    ratio = len(overlap) / max(len(product_words), 1)
    if product and product.lower() in (text or "").lower():
        return 15, f"Product phrase matched: {product}."
    if ratio >= 0.35:
        return 12, f"Product keyword overlap: {', '.join(sorted(overlap))}."
    if overlap:
        return 6, f"Some product keywords matched: {', '.join(sorted(overlap))}."
    return 0, "No product relevance evidence found."


def score_level(total: int) -> str:
    if total >= 80:
        return "HIGH"
    if total >= 70:
        return "QUALIFIED"
    if total >= 50:
        return "REVIEW"
    return "REJECTED"


def next_status_for_score(total: int, config) -> str:
    minimum = int(config.scoring.get("minimum_qualified_score", 70))
    if total >= minimum:
        return LeadStatus.QUALIFIED.value
    if total >= 50:
        return LeadStatus.REVIEW_REQUIRED.value
    return LeadStatus.REJECTED.value


def score_lead(lead: dict[str, Any], config) -> dict[str, Any]:
    text = " ".join(
        str(lead.get(field) or "")
        for field in ("industry", "company_summary", "evidence_text", "job_title", "country")
    )
    reasons: list[str] = []

    industry_match, industry_value = contains_any(text, config.target.get("industries", []))
    industry_score = 30 if industry_match else 0
    reasons.append(f"Industry matched: {industry_value}." if industry_match else "No target industry evidence found.")

    customer_match, customer_value = contains_any(text, config.target.get("customer_types", []))
    customer_type_score = 20 if customer_match else 0
    reasons.append(f"Customer type matched: {customer_value}." if customer_match else "No target customer type evidence found.")

    target_countries = config.target.get("countries", [])
    country = str(lead.get("country") or "")
    country_score = 15 if not target_countries or country.lower() in {item.lower() for item in target_countries} else 0
    reasons.append(f"Country matched: {country}." if country_score else f"Country did not match target list: {country}.")

    product_score, product_reason = product_relevance_score(
        text,
        str(config.business.get("product", "")),
        str(config.business.get("product_description", "")),
    )
    reasons.append(product_reason)

    size_match, size_value = contains_any(text, config.target.get("company_sizes", []))
    company_size_score = 10 if size_match else (5 if not config.target.get("company_sizes") else 0)
    reasons.append(f"Company size matched: {size_value}." if size_match else "No company size evidence found.")

    title_match, title_value = contains_any(str(lead.get("job_title") or ""), config.target.get("preferred_titles", []))
    title_score = 5 if title_match else 0
    reasons.append(f"Preferred title matched: {title_value}." if title_match else "No preferred title evidence found.")

    email_status = str(lead.get("email_status") or "")
    if email_status == EmailStatus.PUBLIC_CONFIRMED.value:
        contact_score = 5
        reasons.append("Email is publicly confirmed on the company domain.")
    elif email_status == EmailStatus.PUBLIC_DOMAIN_MISMATCH.value:
        contact_score = 3
        reasons.append("Email is public but domain differs from the company website.")
    else:
        contact_score = 0
        reasons.append("No sendable public company-domain email found.")

    total = sum(
        [
            industry_score,
            customer_type_score,
            country_score,
            product_score,
            company_size_score,
            title_score,
            contact_score,
        ]
    )
    return {
        "industry_score": industry_score,
        "customer_type_score": customer_type_score,
        "country_score": country_score,
        "product_relevance_score": product_score,
        "company_size_score": company_size_score,
        "title_score": title_score,
        "contact_score": contact_score,
        "total": total,
        "level": score_level(total),
        "reasons": reasons,
    }


def score_pending_leads(conn: sqlite3.Connection, config) -> tuple[int, int, list[str]]:
    rows = conn.execute(
        """
        SELECT * FROM leads
        WHERE status IN ('SCANNED', 'REVIEW_REQUIRED', 'QUALIFIED', 'REJECTED')
        ORDER BY created_at
        """
    ).fetchall()
    processed = 0
    qualified = 0
    errors: list[str] = []
    for row in rows:
        lead = dict(row)
        try:
            if lead["status"] in BLOCKED_RESEND_STATUSES:
                continue
            details = score_lead(lead, config)
            status = next_status_for_score(details["total"], config)
            if status == LeadStatus.QUALIFIED.value:
                qualified += 1
            conn.execute(
                """
                UPDATE leads
                SET score = ?, score_level = ?, score_details = ?, status = ?, updated_at = ?
                WHERE lead_id = ?
                """,
                (
                    details["total"],
                    details["level"],
                    json.dumps(details, ensure_ascii=False),
                    status,
                    utc_now(),
                    lead["lead_id"],
                ),
            )
            processed += 1
        except Exception as exc:
            errors.append(f"{lead.get('lead_id')}: {type(exc).__name__}: {exc}")
    return processed, qualified, errors

