from __future__ import annotations

from scripts.company_search import candidate_from_search_result, parse_search_results, unwrap_search_url
from tests.test_config import valid_config


def test_parse_duckduckgo_results_and_candidate() -> None:
    html = """
    <div class="result">
      <a class="result__a" href="/l/?uddg=https%3A%2F%2Fwww.toyfactory.test%2Fcontact-us%2F">Contact Us - Toy Factory</a>
      <a class="result__snippet">Toy manufacturer in Germany. Email and WhatsApp available.</a>
    </div>
    <div class="result">
      <a class="result__a" href="https://www.linkedin.com/company/toyfactory">Toy Factory - LinkedIn</a>
    </div>
    """

    results = parse_search_results(html)
    candidate = candidate_from_search_result(results[0], valid_config())
    excluded = candidate_from_search_result(results[1], valid_config())

    assert results[0]["url"] == "https://www.toyfactory.test/contact-us/"
    assert candidate is not None
    assert candidate["company_name"] == "Toy Factory"
    assert candidate["website"] == "https://www.toyfactory.test"
    assert excluded is None


def test_parse_yahoo_results_unwraps_redirect_and_filters_directories() -> None:
    html = """
    <div class="algo">
      <div class="compTitle">
        <a href="https://r.search.yahoo.com/x/RU=https%3a%2f%2fcorporate.mattel.test%2fcontact-us/RK=2/RS=x">Contact Information | Mattel</a>
      </div>
      <div class="compText">Toy brand contact page.</div>
    </div>
    <div class="algo">
      <div class="compTitle">
        <a href="https://r.search.yahoo.com/x/RU=https%3a%2f%2flists.example%2ftoys-manufacturers-email-list%2f/RK=2/RS=x">Toys Manufacturers Email List</a>
      </div>
      <div class="compText">Buy a database of toy manufacturers.</div>
    </div>
    """

    results = parse_search_results(html)
    candidate = candidate_from_search_result(results[0], valid_config())
    directory = candidate_from_search_result(results[1], valid_config())

    assert results[0]["url"] == "https://corporate.mattel.test/contact-us"
    assert candidate is not None
    assert candidate["website"] == "https://corporate.mattel.test"
    assert directory is None


def test_unwrap_bing_redirect_url() -> None:
    assert unwrap_search_url("https://www.bing.com/ck/a?u=a1aHR0cHM6Ly90b3kuZXhhbXBsZS9jb250YWN0") == "https://toy.example/contact"


def test_company_name_falls_back_to_domain_for_mixed_search_text() -> None:
    result = {
        "title": "leelinetoys.com https://www.leelinetoys.com Plush Toy Manufacturers USA",
        "url": "https://www.leelinetoys.com/plush-toy-manufacturers-usa/",
        "snippet": "Toy manufacturer contact page.",
    }

    candidate = candidate_from_search_result(result, valid_config())

    assert candidate is not None
    assert candidate["company_name"] == "Leelinetoys"


def test_excludes_contact_database_domains() -> None:
    result = {
        "title": "RocketReach Toy Company Profile",
        "url": "https://rocketreach.co/example-profile",
        "snippet": "Find business contacts.",
    }

    assert candidate_from_search_result(result, valid_config()) is None
