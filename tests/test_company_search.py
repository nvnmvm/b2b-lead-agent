from __future__ import annotations

from scripts.company_search import candidate_from_search_result, parse_search_results
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
