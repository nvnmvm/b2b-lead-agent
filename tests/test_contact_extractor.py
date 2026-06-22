from __future__ import annotations

from pathlib import Path

from scripts.contact_extractor import (
    decode_cloudflare_email,
    extract_public_contacts,
    extract_public_emails,
    is_valid_public_email,
)
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
    assert emails["anna.weber@acmepumps.test"].phone == "+493012345678"


def test_invalid_email_filter() -> None:
    assert not is_valid_public_email("email@2x.png")
    assert not is_valid_public_email("user@localhost")
    assert not is_valid_public_email("example@example.com")
    assert is_valid_public_email("sales@real-company.test")


def test_contact_extraction_captures_whatsapp_and_protected_email() -> None:
    encoded = "".join([format(ord("k") ^ ord(ch), "02x") for ch in "sales@toyfactory.test"])
    html = f"""
    <html>
      <body>
        <section>
          <p>CEO: Allen</p>
          <p>Email: <a class="__cf_email__" data-cfemail="{format(ord('k'), '02x')}{encoded}">[email protected]</a></p>
          <p>WhatsApp: <a href="https://wa.me/8617318897189">+86 17318897189</a></p>
        </section>
      </body>
    </html>
    """

    contacts = extract_public_contacts(html, "fixture://toy", "toyfactory.test")
    by_email = {contact.email: contact for contact in contacts if contact.email}

    assert decode_cloudflare_email(f"{format(ord('k'), '02x')}{encoded}") == "sales@toyfactory.test"
    assert by_email["sales@toyfactory.test"].whatsapp == "+8617318897189"
    assert by_email["sales@toyfactory.test"].job_title == "CEO: Allen"
