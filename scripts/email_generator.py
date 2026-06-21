from __future__ import annotations

import re
import sqlite3
from typing import Any

from scripts.database import utc_now
from scripts.models import EmailStatus, LeadStatus


SENDABLE_DRAFT_EMAIL_STATUSES = {
    EmailStatus.PUBLIC_CONFIRMED.value,
    EmailStatus.PUBLIC_DOMAIN_MISMATCH.value,
}


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def clean_sentence(value: str, fallback: str = "") -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    if not text:
        return fallback
    text = text.strip(" .")
    return text[:260]


def contact_greeting(lead: dict[str, Any]) -> str:
    name = clean_sentence(str(lead.get("contact_name") or ""))
    if name:
        return f"Hi {name.split()[0]},"
    return "Hi team,"


def build_personalization_sentence(lead: dict[str, Any]) -> tuple[str, str]:
    summary = clean_sentence(str(lead.get("company_summary") or ""))
    evidence = summary or clean_sentence(str(lead.get("evidence_text") or ""))
    if "@" in evidence and summary:
        evidence = summary
    elif "@" in evidence:
        evidence = ""
    if evidence:
        sentence = f"I noticed this on your website: {evidence}"
        return clean_sentence(sentence), evidence
    return "", ""


def generate_email_draft(lead: dict[str, Any], config) -> dict[str, str]:
    personalization, personalization_evidence = build_personalization_sentence(lead)
    company_name = clean_sentence(str(lead.get("company_name") or "your company"), "your company")
    sender_name = clean_sentence(str(config.business.get("sender_name", "")), "The export team")
    sender_title = clean_sentence(str(config.business.get("sender_title", "")), "Export")
    sender_company = clean_sentence(str(config.business.get("company_name", "")), "our company")
    sender_email = clean_sentence(str(config.business.get("sender_email", "")))
    product_description = clean_sentence(
        str(config.business.get("product_description") or config.business.get("product") or "relevant supply support")
    )
    advantages = [clean_sentence(str(item)) for item in config.business.get("advantages", []) if clean_sentence(str(item))]
    advantage_text = f", especially around {', '.join(advantages[:2])}" if advantages else ""

    if personalization:
        opener = personalization + "."
    else:
        opener = f"I found {company_name} while reviewing public business websites in your sector."

    body = (
        f"{contact_greeting(lead)}\n\n"
        f"{opener} I am {sender_name}, {sender_title} at {sender_company}. "
        f"We support business customers with {product_description}{advantage_text}. "
        "If supplier options or product information are useful for your team, I would be glad to send a concise overview for review. "
        "No pressure either way; this is only a careful first contact based on public information. "
        "If this is not relevant, please reply and I will not follow up.\n\n"
        f"Best regards,\n{sender_name}\n{sender_title}\n{sender_email}"
    )

    if word_count(body) < 80:
        body = body.replace(
            "If supplier options or product information are useful for your team,",
            "If supplier options, replacement planning, or product information are useful for your team,",
        )
    if word_count(body) > 150:
        body = (
            f"{contact_greeting(lead)}\n\n"
            f"{opener} I am {sender_name}, {sender_title} at {sender_company}. "
            f"We support business customers with {product_description}. "
            "If this is relevant, I can send a concise overview for review. "
            "If not, please reply and I will not follow up.\n\n"
            f"Best regards,\n{sender_name}\n{sender_email}"
        )

    return {
        "subject": f"Quick question about {company_name}",
        "body": body,
        "personalization_sentence": personalization,
        "personalization_evidence": personalization_evidence,
        "source_url": str(lead.get("source_url") or ""),
    }


def draft_pending_leads(conn: sqlite3.Connection, config) -> tuple[int, list[str]]:
    limit = int(config.limits.get("drafts_per_run", 5))
    minimum_score = int(config.scoring.get("minimum_draft_score", 75))
    rows = conn.execute(
        """
        SELECT * FROM leads
        WHERE status = ?
          AND score >= ?
          AND email IS NOT NULL
          AND email != ''
          AND email_status IN (?, ?)
          AND lead_id NOT IN (SELECT lead_id FROM email_drafts)
        ORDER BY score DESC, created_at
        """,
        (
            LeadStatus.QUALIFIED.value,
            minimum_score,
            EmailStatus.PUBLIC_CONFIRMED.value,
            EmailStatus.PUBLIC_DOMAIN_MISMATCH.value,
        ),
    ).fetchall()

    processed = 0
    errors: list[str] = []
    drafted_emails = {
        row["email"].lower()
        for row in conn.execute(
            """
            SELECT leads.email AS email
            FROM leads
            JOIN email_drafts ON email_drafts.lead_id = leads.lead_id
            WHERE leads.email IS NOT NULL AND leads.email != ''
            """
        ).fetchall()
    }

    for row in rows:
        if processed >= limit:
            break
        lead = dict(row)
        email = str(lead.get("email") or "").lower()
        if email in drafted_emails:
            continue
        if lead.get("email_status") == EmailStatus.GUESSED.value:
            errors.append(f"{lead['lead_id']}: guessed email cannot be drafted.")
            continue
        try:
            draft = generate_email_draft(lead, config)
            if draft["personalization_sentence"] and not draft["personalization_evidence"]:
                errors.append(f"{lead['lead_id']}: personalization sentence has no evidence.")
                continue
            now = utc_now()
            conn.execute(
                """
                INSERT INTO email_drafts(
                    lead_id, subject, body, personalization_sentence,
                    personalization_evidence, source_url, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead["lead_id"],
                    draft["subject"],
                    draft["body"],
                    draft["personalization_sentence"],
                    draft["personalization_evidence"],
                    draft["source_url"],
                    now,
                ),
            )
            conn.execute(
                "UPDATE leads SET status = ?, draft_created_at = ?, updated_at = ? WHERE lead_id = ?",
                (LeadStatus.DRAFTED.value, now, now, lead["lead_id"]),
            )
            drafted_emails.add(email)
            processed += 1
        except Exception as exc:
            errors.append(f"{lead.get('lead_id')}: {type(exc).__name__}: {exc}")
    return processed, errors
