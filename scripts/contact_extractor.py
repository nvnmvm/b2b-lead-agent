from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from scripts.company_search import normalize_domain
from scripts.models import ContactCandidate, EmailStatus


EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w.+-])", re.IGNORECASE)
PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
WHATSAPP_LABEL_RE = re.compile(r"\b(?:whats\s*app|what'?s\s*app|wa\.me|wechat\s*&\s*whatsapp)\b", re.IGNORECASE)
STATIC_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js", ".ico", ".woff", ".woff2")
INVALID_EXACT_EMAILS = {
    "example@example.com",
    "test@example.com",
    "sample@example.com",
    "user@localhost",
}
RESERVED_DOMAINS = {"example.com", "example.org", "example.net", "localhost"}
TITLE_KEYWORDS = (
    "owner",
    "founder",
    "ceo",
    "chief executive",
    "managing director",
    "procurement",
    "purchasing",
    "sourcing",
    "supply chain",
    "operations",
    "production",
    "sales",
    "business development",
    "export",
)


@dataclass
class ParsedEmail:
    email: str
    evidence_text: str
    source_url: str
    context_text: str


@dataclass
class ParsedPhone:
    phone: str
    evidence_text: str
    source_url: str
    context_text: str
    is_whatsapp: bool = False


def normalize_email_candidate(value: str) -> str:
    value = html.unescape(unquote(value or "")).strip()
    value = value.replace("mailto:", "", 1)
    value = value.split("?")[0]
    return value.strip(" \t\r\n<>()[]{}.,;:'\"")


def normalize_phone_candidate(value: str) -> str:
    value = html.unescape(unquote(value or "")).strip()
    has_plus = value.startswith("+")
    digits = re.sub(r"\D+", "", value)
    if len(digits) < 8:
        return ""
    return f"+{digits}" if has_plus else digits


def decode_cloudflare_email(hex_value: str) -> str:
    try:
        key = int(hex_value[:2], 16)
        return "".join(chr(int(hex_value[index : index + 2], 16) ^ key) for index in range(2, len(hex_value), 2))
    except Exception:
        return ""


def is_valid_public_email(email: str) -> bool:
    normalized = normalize_email_candidate(email).lower()
    if not normalized or normalized in INVALID_EXACT_EMAILS:
        return False
    if any(normalized.endswith(ext) for ext in STATIC_EXTENSIONS):
        return False
    if "@2x." in normalized or normalized.endswith("@localhost"):
        return False
    if not EMAIL_RE.fullmatch(normalized):
        return False
    local, domain = normalized.rsplit("@", 1)
    if not local or not domain or domain in RESERVED_DOMAINS:
        return False
    if local in {"example", "sample", "test", "user", "name", "email"} and domain.startswith("example."):
        return False
    if domain.split(".")[-1].lower() in {"png", "jpg", "jpeg", "gif", "webp", "svg", "css", "js"}:
        return False
    return True


def classify_email_status(email: str, website_domain: str) -> EmailStatus:
    email_domain = email.lower().rsplit("@", 1)[-1]
    website_domain = normalize_domain(website_domain)
    if not website_domain:
        return EmailStatus.UNKNOWN
    if email_domain == website_domain or email_domain.endswith("." + website_domain):
        return EmailStatus.PUBLIC_CONFIRMED
    return EmailStatus.PUBLIC_DOMAIN_MISMATCH


def visible_text_from_html(html_text: str) -> tuple[BeautifulSoup, str]:
    soup = BeautifulSoup(html_text or "", "lxml")
    for tag in soup(["script", "style", "svg", "img", "picture", "source", "link", "meta", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    return soup, text


def snippet_around(text: str, needle: str, radius: int = 160) -> str:
    if not text:
        return needle
    lower = text.lower()
    index = lower.find(needle.lower())
    if index < 0:
        return text[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(text), index + len(needle) + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def extract_mailto_emails(soup: BeautifulSoup, source_url: str) -> list[ParsedEmail]:
    parsed: list[ParsedEmail] = []
    for link in soup.select("a[href^='mailto:']"):
        href = link.get("href") or ""
        email = normalize_email_candidate(href)
        container = link.find_parent(["section", "article", "div", "li", "td"]) or link.parent
        context = container.get_text("\n", strip=True) if container else link.get_text(" ", strip=True)
        parsed.append(
            ParsedEmail(
                email=email,
                evidence_text=snippet_around(context or email, email),
                source_url=source_url,
                context_text=context,
            )
        )
    return parsed


def extract_cloudflare_emails(soup: BeautifulSoup, source_url: str) -> list[ParsedEmail]:
    parsed: list[ParsedEmail] = []
    for tag in soup.select("[data-cfemail]"):
        email = normalize_email_candidate(decode_cloudflare_email(str(tag.get("data-cfemail") or "")))
        if not email:
            continue
        container = tag.find_parent(["section", "article", "div", "li", "td"]) or tag.parent
        context = container.get_text("\n", strip=True) if container else email
        parsed.append(
            ParsedEmail(
                email=email,
                evidence_text=snippet_around(context or email, email),
                source_url=source_url,
                context_text=context,
            )
        )
    return parsed


def extract_text_emails(text: str, source_url: str) -> list[ParsedEmail]:
    parsed: list[ParsedEmail] = []
    for match in EMAIL_RE.finditer(text or ""):
        email = normalize_email_candidate(match.group(1))
        parsed.append(
            ParsedEmail(
                email=email,
                evidence_text=snippet_around(text, email),
                source_url=source_url,
                context_text=snippet_around(text, email, radius=100),
            )
        )
    return parsed


def extract_phone(context_text: str) -> str:
    match = PHONE_RE.search(context_text or "")
    return normalize_phone_candidate(match.group(1)) if match else ""


def whatsapp_from_href(href: str) -> str:
    parsed = urlparse(href or "")
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    query = parse_qs(parsed.query or "")
    if "wa.me" in host:
        return normalize_phone_candidate(path.strip("/").split("/", 1)[0])
    if "whatsapp.com" in host or parsed.scheme == "whatsapp":
        for key in ("phone", "text"):
            for value in query.get(key, []):
                phone = normalize_phone_candidate(value)
                if phone:
                    return phone
    return ""


def extract_whatsapp_numbers(soup: BeautifulSoup, text: str, source_url: str) -> list[ParsedPhone]:
    parsed: list[ParsedPhone] = []
    seen: set[str] = set()

    for link in soup.select("a[href]"):
        href = link.get("href") or ""
        phone = whatsapp_from_href(href)
        if not phone or phone in seen:
            continue
        seen.add(phone)
        container = link.find_parent(["section", "article", "div", "li", "td", "p"]) or link.parent
        context = container.get_text("\n", strip=True) if container else link.get_text(" ", strip=True)
        parsed.append(
            ParsedPhone(
                phone=phone,
                evidence_text=snippet_around(context or href, phone),
                source_url=source_url,
                context_text=context,
                is_whatsapp=True,
            )
        )

    for line in re.split(r"[\n\r]+", text or ""):
        if not WHATSAPP_LABEL_RE.search(line):
            continue
        for match in PHONE_RE.finditer(line):
            phone = normalize_phone_candidate(match.group(1))
            if phone and phone not in seen:
                seen.add(phone)
                parsed.append(
                    ParsedPhone(
                        phone=phone,
                        evidence_text=snippet_around(line, match.group(1)),
                        source_url=source_url,
                        context_text=line,
                        is_whatsapp=True,
                    )
                )
    return parsed


def extract_context_phones(context_text: str, source_url: str) -> list[ParsedPhone]:
    parsed: list[ParsedPhone] = []
    seen: set[str] = set()
    for match in PHONE_RE.finditer(context_text or ""):
        phone = normalize_phone_candidate(match.group(1))
        if phone and phone not in seen:
            seen.add(phone)
            parsed.append(
                ParsedPhone(
                    phone=phone,
                    evidence_text=snippet_around(context_text, match.group(1)),
                    source_url=source_url,
                    context_text=context_text,
                    is_whatsapp=bool(WHATSAPP_LABEL_RE.search(context_text or "")),
                )
            )
    return parsed


def infer_contact_from_context(context_text: str, email: str = "") -> tuple[str, str]:
    return infer_name_and_title(context_text, email or "contact@example.invalid")


def infer_name_and_title(context_text: str, email: str) -> tuple[str, str]:
    lines = [line.strip(" -|:") for line in re.split(r"[\n\r|]+", context_text or "") if line.strip()]
    title = ""
    name = ""
    email_local = email.split("@", 1)[0].replace(".", " ").replace("_", " ").lower()

    for line in lines:
        lowered = line.lower()
        if any(keyword in lowered for keyword in TITLE_KEYWORDS):
            title = line
            break

    for line in lines:
        lowered = line.lower()
        if "@" in line or line == title or any(keyword in lowered for keyword in TITLE_KEYWORDS):
            continue
        words = re.findall(r"[A-Za-z][A-Za-z'-]+", line)
        if 1 <= len(words) <= 4:
            candidate = " ".join(words)
            if candidate.lower() not in {"email", "contact", "sales", "info"} and candidate.lower() not in email_local:
                name = candidate
                break

    return name, title


def extract_public_contacts(html_text: str, source_url: str, domain: str) -> list[ContactCandidate]:
    soup, text = visible_text_from_html(html_text)
    candidates = extract_mailto_emails(soup, source_url) + extract_cloudflare_emails(soup, source_url) + extract_text_emails(text, source_url)
    whatsapp_numbers = extract_whatsapp_numbers(soup, text, source_url)
    contacts: list[ContactCandidate] = []
    seen: set[str] = set()

    for parsed in candidates:
        email = normalize_email_candidate(parsed.email).lower()
        if email in seen or not is_valid_public_email(email):
            continue
        seen.add(email)
        status = classify_email_status(email, domain)
        name, title = infer_name_and_title(parsed.context_text, email)
        context_phones = extract_context_phones(parsed.context_text, source_url)
        phone = context_phones[0].phone if context_phones else ""
        whatsapp = next((item.phone for item in context_phones if item.is_whatsapp), "")
        if not whatsapp and len(whatsapp_numbers) == 1:
            whatsapp = whatsapp_numbers[0].phone
        contacts.append(
            ContactCandidate(
                email=email,
                status=status,
                source_url=source_url,
                evidence_text=parsed.evidence_text or email,
                contact_name=name,
                job_title=title,
                phone=phone,
                whatsapp=whatsapp,
            )
        )
    seen_whatsapp = {contact.whatsapp for contact in contacts if contact.whatsapp}
    seen_phone = {contact.phone for contact in contacts if contact.phone}
    for parsed_phone in whatsapp_numbers:
        if parsed_phone.phone in seen_whatsapp or parsed_phone.phone in seen_phone:
            continue
        name, title = infer_contact_from_context(parsed_phone.context_text)
        contacts.append(
            ContactCandidate(
                email="",
                status=EmailStatus.UNKNOWN,
                source_url=parsed_phone.source_url,
                evidence_text=parsed_phone.evidence_text,
                contact_name=name,
                job_title=title,
                phone=parsed_phone.phone,
                whatsapp=parsed_phone.phone,
            )
        )
    return contacts


def extract_public_emails(html_text: str, source_url: str, domain: str) -> list[ContactCandidate]:
    return [contact for contact in extract_public_contacts(html_text, source_url, domain) if contact.email]


def extract_public_phones(html_text: str) -> list[str]:
    _, text = visible_text_from_html(html_text)
    phones = []
    for match in PHONE_RE.finditer(text):
        phone = normalize_phone_candidate(match.group(1))
        if phone not in phones:
            phones.append(phone)
    return phones
