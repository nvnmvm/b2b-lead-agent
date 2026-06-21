from __future__ import annotations

from typing import Any

from scripts.models import BLOCKED_RESEND_STATUSES, EmailStatus


PUBLIC_SENDABLE_STATUSES = {
    EmailStatus.PUBLIC_CONFIRMED.value,
    EmailStatus.PUBLIC_DOMAIN_MISMATCH.value,
}


def is_sendable_email_status(status: str) -> bool:
    return status in PUBLIC_SENDABLE_STATUSES


def validate_approval_candidate(lead: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not lead.get("email"):
        errors.append("Lead has no email address.")
    if not is_sendable_email_status(str(lead.get("email_status") or "")):
        errors.append(f"Email status is not sendable: {lead.get('email_status') or 'UNKNOWN'}.")
    if lead.get("email_status") == EmailStatus.GUESSED.value:
        errors.append("Guessed emails cannot be approved or sent.")
    if lead.get("status") in BLOCKED_RESEND_STATUSES:
        errors.append(f"Lead status blocks resend: {lead.get('status')}.")
    return errors

