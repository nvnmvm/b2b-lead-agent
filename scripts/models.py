from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LeadStatus(str, Enum):
    NEW = "NEW"
    DISCOVERED = "DISCOVERED"
    SCANNED = "SCANNED"
    QUALIFIED = "QUALIFIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DRAFTED = "DRAFTED"
    APPROVED = "APPROVED"
    SENT = "SENT"
    SEND_UNKNOWN = "SEND_UNKNOWN"
    REPLIED = "REPLIED"
    REJECTED = "REJECTED"
    DO_NOT_CONTACT = "DO_NOT_CONTACT"
    ERROR = "ERROR"


class EmailStatus(str, Enum):
    PUBLIC_CONFIRMED = "PUBLIC_CONFIRMED"
    PUBLIC_DOMAIN_MISMATCH = "PUBLIC_DOMAIN_MISMATCH"
    GUESSED = "GUESSED"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


BLOCKED_RESEND_STATUSES = {
    LeadStatus.SENT.value,
    LeadStatus.SEND_UNKNOWN.value,
    LeadStatus.REPLIED.value,
    LeadStatus.DO_NOT_CONTACT.value,
}


@dataclass
class CommandResult:
    success: bool
    action: str
    processed: int = 0
    qualified: int = 0
    requires_approval: bool = False
    errors: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "success": self.success,
            "action": self.action,
            "processed": self.processed,
            "qualified": self.qualified,
            "requires_approval": self.requires_approval,
            "errors": self.errors,
        }
        if self.data:
            payload["data"] = self.data
        return payload


@dataclass
class ContactCandidate:
    email: str
    status: EmailStatus
    source_url: str
    evidence_text: str
    contact_name: str = ""
    job_title: str = ""
    phone: str = ""


@dataclass
class ScanResult:
    company_name: str
    website: str
    domain: str
    country: str = ""
    industry: str = ""
    company_summary: str = ""
    evidence_text: str = ""
    source_url: str = ""
    contacts: list[ContactCandidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

