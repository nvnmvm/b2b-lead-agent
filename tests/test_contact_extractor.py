from __future__ import annotations

from pathlib import Path

from scripts.contact_extractor import extract_public_emails, is_valid_public_email
from scripts.models import EmailStatus


def test_email_extraction_filters_static_and_examples() -> None:
    html = Path("tests/fixtures/acme.html").read_text(encoding="utf-8")
    contacts = extract_public_emails(html, "fixture://acme", "acmepumps.test")
    emails = {contact.email: contact for contact in contacts}

    assert "anna.weber@acmepumps.test" in emails
    assert "sales@external-mail.test" in emails
    assert "email@2x.png" not in emails
    assert "example@example.com" not in emails
    assert "sample@example.com" not in emails
    assert emails["anna.weber@acmepumps.test"].status == EmailStatus.PUBLIC_CONFIRMED
    assert emails["sales@external-mail.test"].status == EmailStatus.PUBLIC_DOMAIN_MISMATCH
    assert "Procurement Manager" in emails["anna.weber@acmepumps.test"].job_title
    assert emails["anna.weber@acmepumps.test"].evidence_text


def test_invalid_email_filter() -> None:
    assert not is_valid_public_email("email@2x.png")
    assert not is_valid_public_email("user@localhost")
    assert not is_valid_public_email("example@example.com")
    assert is_valid_public_email("sales@real-company.test")


