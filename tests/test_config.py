from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.config_loader import ConfigError, load_config


def valid_config() -> dict:
    return {
        "business": {
            "company_name": "Acme Export",
            "product": "industrial pumps",
            "product_description": "pump parts for water treatment systems",
            "advantages": ["stable quality"],
            "sender_name": "Jane Smith",
            "sender_title": "Export Manager",
            "sender_email": "jane@acme.example",
            "company_website": "https://acme.example",
        },
        "target": {
            "countries": ["Germany"],
            "industries": ["industrial pumps"],
            "customer_types": ["distributor"],
            "company_sizes": ["medium"],
            "preferred_titles": ["Owner", "Procurement Manager"],
            "excluded_keywords": ["school"],
        },
        "limits": {
            "companies_per_run": 10,
            "websites_per_run": 10,
            "drafts_per_run": 5,
            "request_interval_min_seconds": 0,
            "request_interval_max_seconds": 0,
            "request_timeout_seconds": 10,
            "retry_count": 2,
        },
        "scoring": {"minimum_qualified_score": 70, "minimum_draft_score": 75},
        "browser": {"headless": True, "use_playwright_fallback": False},
        "email": {"mode": "draft_only", "allow_guessed_email": False, "require_manual_approval": True},
    }


def write_config(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_load_config_success(tmp_path: Path) -> None:
    path = write_config(tmp_path / "config.yaml", valid_config())
    config = load_config(path)
    assert config.business["product"] == "industrial pumps"


def test_load_config_reports_missing_business_field(tmp_path: Path) -> None:
    data = valid_config()
    data["business"]["sender_email"] = ""
    path = write_config(tmp_path / "config.yaml", data)
    with pytest.raises(ConfigError, match="business.sender_email"):
        load_config(path)


def test_load_config_rejects_non_draft_email_mode(tmp_path: Path) -> None:
    data = valid_config()
    data["email"]["mode"] = "send"
    path = write_config(tmp_path / "config.yaml", data)
    with pytest.raises(ConfigError, match="draft_only"):
        load_config(path)


