from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from scripts import website_fetcher
from scripts.database import utc_now


REQUIRED_CSV_COLUMNS = ("company_name", "website", "country", "source_url")
EXCLUDED_DISCOVERY_DOMAINS = {
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "youtu.be",
    "x.com",
    "twitter.com",
    "tiktok.com",
    "pinterest.com",
    "reddit.com",
    "wa.me",
    "whatsapp.com",
    "google.com",
    "duckduckgo.com",
    "bing.com",
}


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


def root_website(url: str) -> str:
    value = normalize_website(url)
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return value


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


def raw_config(config) -> dict:
    return getattr(config, "raw", config)


def build_search_queries(config: dict) -> list[str]:
    config = raw_config(config)
    product = (config.get("business", {}).get("product") or "").strip()
    countries = config.get("target", {}).get("countries", []) or [""]
    industries = config.get("target", {}).get("industries", []) or [product]
    customer_types = config.get("target", {}).get("customer_types", []) or ["supplier", "manufacturer", "distributor"]
    queries: list[str] = []
    for country in countries:
        for industry in industries:
            phrase = " ".join(part for part in (industry or product, country) if part).strip()
            if phrase:
                for customer_type in customer_types[:4]:
                    queries.append(f'"{phrase}" "{customer_type}" "contact"')
                queries.append(f'"{phrase}" "Email" "WhatsApp"')
                queries.append(f'"{phrase}" "Contact Us" "manufacturer"')
                if product and country:
                    queries.append(f'"{product}" "{country}" "WhatsApp" "Email"')
    return list(dict.fromkeys(queries))


def unwrap_search_url(url: str) -> str:
    parsed = urlparse(url)
    if ("duckduckgo.com" in parsed.netloc or not parsed.netloc) and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return url


def parse_search_results(html_text: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html_text or "", "lxml")
    parsed: list[dict[str, str]] = []
    blocks = soup.select(".result") or soup.select("li.b_algo") or soup.select("article") or soup.select("div")
    for block in blocks:
        link = block.select_one("a.result__a[href]") or block.select_one("h2 a[href]") or block.select_one("a[href]")
        if not link:
            continue
        href = unwrap_search_url(link.get("href") or "")
        title = link.get_text(" ", strip=True)
        snippet_tag = block.select_one(".result__snippet") or block.select_one("p")
        snippet = snippet_tag.get_text(" ", strip=True) if snippet_tag else ""
        if href and title:
            parsed.append({"title": title, "url": href, "snippet": snippet})
    return parsed


def is_excluded_discovery_domain(domain: str) -> bool:
    return any(domain == excluded or domain.endswith("." + excluded) for excluded in EXCLUDED_DISCOVERY_DOMAINS)


def company_name_from_result(title: str, domain: str) -> str:
    value = re.sub(r"\s+", " ", title or "").strip()
    value = re.sub(r"\s*[\-|–|—|:]\s*(contact us|contacts?|about us|home|official site).*$", "", value, flags=re.I)
    value = re.sub(r"^(contact us|contacts?|about us|home)\s*[\-|–|—|:]\s*", "", value, flags=re.I)
    value = re.split(r"\s*[\-|–|—|:]\s*", value)[0].strip()
    if value and len(value) <= 80:
        return value
    parts = domain.split(".")
    return " ".join(part.capitalize() for part in parts[:1]) or domain


def candidate_from_search_result(result: dict[str, str], config) -> dict[str, str] | None:
    url = result.get("url", "")
    domain = normalize_domain(url)
    if not domain or is_excluded_discovery_domain(domain):
        return None
    parsed = urlparse(normalize_website(url))
    if parsed.scheme not in {"http", "https"}:
        return None
    config = raw_config(config)
    country = ""
    haystack = f"{result.get('title', '')} {result.get('snippet', '')}".lower()
    for item in config.get("target", {}).get("countries", []) or []:
        if item and item.lower() in haystack:
            country = item
            break
    now = utc_now()
    return {
        "company_name": company_name_from_result(result.get("title", ""), domain),
        "website": root_website(url),
        "domain": domain,
        "country": country,
        "source_url": url,
        "status": "DISCOVERED",
        "created_at": now,
        "updated_at": now,
    }


def fetch_search_results(query: str, config) -> list[dict[str, str]]:
    requests = website_fetcher.load_requests_module()
    timeout = min(int(raw_config(config).get("limits", {}).get("request_timeout_seconds", 30)), 10)
    headers = {"User-Agent": "b2b-lead-agent/0.1 (+public business contact review)"}
    errors: list[str] = []
    for url in ("https://html.duckduckgo.com/html/", "https://www.bing.com/search"):
        try:
            response = requests.get(url, params={"q": query}, headers=headers, timeout=timeout)
            response.raise_for_status()
            results = parse_search_results(response.text)
            if results:
                return results
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    if errors:
        raise RuntimeError("; ".join(errors))
    return []


def discover_companies_public_web(config, *, limit: int | None = None) -> tuple[list[dict[str, str]], list[str]]:
    max_companies = limit or int(raw_config(config).get("limits", {}).get("companies_per_run", 10))
    companies: list[dict[str, str]] = []
    errors: list[str] = []
    seen_domains: set[str] = set()
    discovery = raw_config(config).get("discovery", {}) or {}
    max_queries = int(discovery.get("max_search_queries", min(8, max(max_companies * 2, 1))))
    for query in build_search_queries(config)[:max_queries]:
        if len(companies) >= max_companies:
            break
        try:
            results = fetch_search_results(query, config)
        except Exception as exc:
            errors.append(f"{query}: {type(exc).__name__}: {exc}")
            continue
        for result in results:
            candidate = candidate_from_search_result(result, config)
            if not candidate or candidate["domain"] in seen_domains:
                continue
            seen_domains.add(candidate["domain"])
            companies.append(candidate)
            if len(companies) >= max_companies:
                break
    return companies, errors


def import_discovered_companies(conn: sqlite3.Connection, config, *, limit: int | None = None) -> tuple[int, list[str]]:
    companies, errors = discover_companies_public_web(config, limit=limit)
    processed = 0
    for company in companies:
        upsert_company(conn, company)
        processed += 1
    if not processed and not errors:
        errors.append("No public search results produced importable company websites.")
    return processed, errors
