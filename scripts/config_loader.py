from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when a config file is missing or invalid."""


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"

REQUIRED_SECTIONS = ("business", "target", "limits", "scoring", "browser", "email")
REQUIRED_BUSINESS_FIELDS = (
    "company_name",
    "product",
    "product_description",
    "sender_name",
    "sender_title",
    "sender_email",
    "company_website",
)
REQUIRED_LIMIT_FIELDS = (
    "companies_per_run",
    "websites_per_run",
    "drafts_per_run",
    "request_interval_min_seconds",
    "request_interval_max_seconds",
    "request_timeout_seconds",
    "retry_count",
)


@dataclass(frozen=True)
class AppConfig:
    path: Path
    raw: dict[str, Any]

    @property
    def business(self) -> dict[str, Any]:
        return self.raw["business"]

    @property
    def target(self) -> dict[str, Any]:
        return self.raw["target"]

    @property
    def limits(self) -> dict[str, Any]:
        return self.raw["limits"]

    @property
    def scoring(self) -> dict[str, Any]:
        return self.raw["scoring"]

    @property
    def browser(self) -> dict[str, Any]:
        return self.raw["browser"]

    @property
    def email(self) -> dict[str, Any]:
        return self.raw["email"]


def load_config(path: str | Path, *, validate_business: bool = True) -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in config file: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a mapping.")

    validate_config(raw, validate_business=validate_business)
    return AppConfig(path=config_path, raw=raw)


def validate_config(raw: dict[str, Any], *, validate_business: bool = True) -> None:
    missing: list[str] = []
    for section in REQUIRED_SECTIONS:
        if section not in raw or not isinstance(raw[section], dict):
            missing.append(section)

    if missing:
        raise ConfigError(f"Missing config section(s): {', '.join(missing)}")

    if validate_business:
        for field in REQUIRED_BUSINESS_FIELDS:
            value = raw["business"].get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(f"business.{field}")

    for field in REQUIRED_LIMIT_FIELDS:
        value = raw["limits"].get(field)
        if value is None:
            missing.append(f"limits.{field}")
        elif not isinstance(value, int) or value < 0:
            raise ConfigError(f"Config field limits.{field} must be a non-negative integer.")

    min_wait = raw["limits"].get("request_interval_min_seconds", 0)
    max_wait = raw["limits"].get("request_interval_max_seconds", 0)
    if isinstance(min_wait, int) and isinstance(max_wait, int) and min_wait > max_wait:
        raise ConfigError("limits.request_interval_min_seconds cannot exceed request_interval_max_seconds.")

    minimum_qualified = raw["scoring"].get("minimum_qualified_score")
    minimum_draft = raw["scoring"].get("minimum_draft_score")
    for name, value in (
        ("scoring.minimum_qualified_score", minimum_qualified),
        ("scoring.minimum_draft_score", minimum_draft),
    ):
        if value is None:
            missing.append(name)
        elif not isinstance(value, int) or not 0 <= value <= 100:
            raise ConfigError(f"Config field {name} must be an integer from 0 to 100.")

    if raw["email"].get("mode") != "draft_only":
        raise ConfigError("Only email.mode=draft_only is supported in this version.")

    if raw["email"].get("require_manual_approval") is not True:
        raise ConfigError("email.require_manual_approval must be true.")

    if raw["email"].get("allow_guessed_email") is not False:
        raise ConfigError("email.allow_guessed_email must be false.")

    if missing:
        raise ConfigError(f"Missing required config value(s): {', '.join(missing)}")


def copy_example_config(destination: Path = DEFAULT_CONFIG_PATH) -> bool:
    destination = destination.resolve()
    if destination.exists():
        return False
    example = PROJECT_ROOT / "config.example.yaml"
    destination.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    return True

