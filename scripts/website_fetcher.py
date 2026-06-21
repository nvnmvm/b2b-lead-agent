from __future__ import annotations

import random
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse


@dataclass
class FetchResult:
    url: str
    status_code: int
    text: str
    final_url: str
    error: str = ""
    used_browser: bool = False


PRIORITY_PATHS = (
    "/",
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/team",
    "/leadership",
    "/management",
    "/company",
    "/imprint",
    "/news",
)
BLOCKING_TERMS = ("captcha", "verify you are human", "login required", "sign in to continue", "paywall")


def is_local_resource(url: str) -> bool:
    value = str(url or "")
    return value.startswith("file:") or Path(value).expanduser().exists()


def read_local_resource(url: str) -> FetchResult:
    value = str(url)
    path = Path(urlparse(value).path if value.startswith("file:") else value).expanduser().resolve()
    if path.is_dir():
        path = path / "index.html"
    try:
        text = path.read_text(encoding="utf-8")
        return FetchResult(url=str(path), status_code=200, text=text, final_url=str(path))
    except UnicodeDecodeError:
        text = path.read_text(encoding="latin-1")
        return FetchResult(url=str(path), status_code=200, text=text, final_url=str(path))
    except Exception as exc:
        return FetchResult(url=str(path), status_code=0, text="", final_url=str(path), error=str(exc))


def page_text_is_too_thin(html: str) -> bool:
    visible = " ".join((html or "").split())
    return len(visible) < 240 or ("<script" in html.lower() and len(visible) < 800)


def contains_blocking_terms(text: str) -> bool:
    lower = (text or "").lower()
    return any(term in lower for term in BLOCKING_TERMS)


def polite_delay(config) -> None:
    min_seconds = int(config.limits.get("request_interval_min_seconds", 0))
    max_seconds = int(config.limits.get("request_interval_max_seconds", 0))
    if max_seconds <= 0:
        return
    time.sleep(random.uniform(min_seconds, max_seconds))


def load_requests_module():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import requests

    return requests


def fetch_with_requests(url: str, config) -> FetchResult:
    requests = load_requests_module()
    timeout = int(config.limits.get("request_timeout_seconds", 30))
    retry_count = int(config.limits.get("retry_count", 2))
    headers = {"User-Agent": "b2b-lead-agent/0.1 (+public business contact review)"}
    last_error = ""

    for attempt in range(retry_count + 1):
        if attempt:
            time.sleep(min(2 ** attempt, 8))
        try:
            response = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
            status_code = response.status_code
            text = response.text or ""
            result = FetchResult(url=url, status_code=status_code, text=text, final_url=response.url)
            if status_code == 429:
                result.error = "HTTP 429 rate limit; stopped current source."
                return result
            if status_code in {401, 403}:
                result.error = f"HTTP {status_code} access restricted."
                return result
            if status_code == 404:
                result.error = "HTTP 404 not found."
                return result
            if status_code >= 500:
                last_error = f"HTTP {status_code} server error."
                continue
            if contains_blocking_terms(text):
                result.error = "Access restriction or captcha detected; stopped current source."
                return result
            if page_text_is_too_thin(text) and config.browser.get("use_playwright_fallback") is True:
                browser_result = fetch_with_playwright(url, config)
                if browser_result.text:
                    return browser_result
            return result
        except requests.RequestException as exc:
            last_error = str(exc)

    return FetchResult(url=url, status_code=0, text="", final_url=url, error=last_error or "Unknown fetch error.")


def fetch_with_playwright(url: str, config) -> FetchResult:
    browser = None
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=bool(config.browser.get("headless", True)))
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=int(config.limits.get("request_timeout_seconds", 30)) * 1000)
            text = page.content()
            return FetchResult(url=url, status_code=200, text=text, final_url=page.url, used_browser=True)
    except Exception as exc:
        return FetchResult(url=url, status_code=0, text="", final_url=url, error=f"Playwright fallback failed: {exc}")
    finally:
        if browser is not None:
            browser.close()


def fetch_url(url: str, config) -> FetchResult:
    if is_local_resource(url):
        return read_local_resource(url)
    polite_delay(config)
    return fetch_with_requests(url, config)


def build_priority_urls(website: str) -> list[str]:
    if is_local_resource(website):
        return [website]
    parsed = urlparse(website)
    base = website if parsed.scheme else "https://" + website
    urls = [urljoin(base.rstrip("/") + "/", path.lstrip("/")) for path in PRIORITY_PATHS]
    return list(dict.fromkeys(urls))


def fetch_site_pages(website: str, config, *, max_pages: int | None = None) -> list[FetchResult]:
    urls = build_priority_urls(website)
    if max_pages is not None:
        urls = urls[:max_pages]
    results: list[FetchResult] = []
    for url in urls:
        result = fetch_url(url, config)
        results.append(result)
        if result.status_code == 429 or "captcha" in (result.error or "").lower():
            break
    return results

