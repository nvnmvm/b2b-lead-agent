from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts import config_loader
from scripts.approval import approve_send
from scripts.company_search import import_companies_csv, import_discovered_companies
from scripts.database import (
    DEFAULT_DB_PATH,
    create_task,
    db_session,
    finish_task,
    init_db,
    record_error,
    reset_processing_errors,
    status_counts,
)
from scripts.models import CommandResult
from scripts.email_generator import draft_pending_leads
from scripts.exporter import export_results
from scripts.lead_scorer import score_pending_leads
from scripts.website_scanner import scan_pending_companies


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def emit(result: CommandResult) -> int:
    print(json.dumps(result.to_json_dict(), ensure_ascii=False, indent=2))
    return 0 if result.success else 1


def init_command(args: argparse.Namespace) -> CommandResult:
    for folder in ("data", "output", "logs"):
        (PROJECT_ROOT / folder).mkdir(parents=True, exist_ok=True)
    init_db(DEFAULT_DB_PATH)
    copied = config_loader.copy_example_config(PROJECT_ROOT / "config.yaml")
    return CommandResult(
        success=True,
        action="init",
        processed=1,
        data={"database": str(DEFAULT_DB_PATH), "config_created": copied},
    )


def search_command(args: argparse.Namespace) -> CommandResult:
    config = config_loader.load_config(args.config, validate_business=False)
    init_db(DEFAULT_DB_PATH)
    errors: list[str] = []
    processed = 0
    csv_path = args.input_csv or args.csv
    if csv_path is None:
        default_csv = PROJECT_ROOT / "data" / "companies.csv"
        csv_path = default_csv if default_csv.exists() else None

    with db_session(DEFAULT_DB_PATH) as conn:
        task_id = create_task(conn, "search", {"csv_path": str(csv_path) if csv_path else None})
        try:
            if csv_path is None:
                processed, errors = import_discovered_companies(conn, config, limit=int(config.limits["companies_per_run"]))
            else:
                processed = import_companies_csv(conn, csv_path, limit=int(config.limits["companies_per_run"]))
            finish_task(conn, task_id, "DONE" if not errors else "PARTIAL", {"processed": processed, "errors": errors})
        except Exception as exc:
            record_error(conn, action="search", error_type=type(exc).__name__, message=str(exc), task_id=task_id)
            finish_task(conn, task_id, "ERROR")
            raise

    return CommandResult(success=not errors, action="search", processed=processed, errors=errors)


def status_command(args: argparse.Namespace) -> CommandResult:
    init_db(DEFAULT_DB_PATH)
    with db_session(DEFAULT_DB_PATH) as conn:
        counts = status_counts(conn)
    return CommandResult(success=True, action="status", processed=1, data=counts)


def scan_command(args: argparse.Namespace) -> CommandResult:
    config = config_loader.load_config(args.config, validate_business=False)
    init_db(DEFAULT_DB_PATH)
    with db_session(DEFAULT_DB_PATH) as conn:
        if args.website:
            from scripts.company_search import normalize_domain, normalize_website, upsert_company
            from scripts.database import utc_now

            website = normalize_website(args.website)
            domain = normalize_domain(website)
            company_name = args.company_name or domain
            now = utc_now()
            upsert_company(
                conn,
                {
                    "company_name": company_name,
                    "website": website,
                    "domain": domain,
                    "country": args.country or "",
                    "source_url": args.source_url or website,
                    "status": "DISCOVERED",
                    "created_at": now,
                    "updated_at": now,
                },
            )
        task_id = create_task(conn, "scan")
        conn.commit()
        processed, errors = scan_pending_companies(conn, config, task_id=task_id)
        finish_task(conn, task_id, "DONE" if not errors else "PARTIAL", {"processed": processed, "errors": errors})
    return CommandResult(success=not errors, action="scan", processed=processed, errors=errors)


def score_command(args: argparse.Namespace) -> CommandResult:
    config = config_loader.load_config(args.config)
    init_db(DEFAULT_DB_PATH)
    with db_session(DEFAULT_DB_PATH) as conn:
        task_id = create_task(conn, "score")
        processed, qualified, errors = score_pending_leads(conn, config)
        finish_task(conn, task_id, "DONE" if not errors else "PARTIAL", {"processed": processed, "errors": errors})
    return CommandResult(success=not errors, action="score", processed=processed, qualified=qualified, errors=errors)


def draft_command(args: argparse.Namespace) -> CommandResult:
    config = config_loader.load_config(args.config)
    init_db(DEFAULT_DB_PATH)
    with db_session(DEFAULT_DB_PATH) as conn:
        task_id = create_task(conn, "draft")
        processed, errors = draft_pending_leads(conn, config)
        finish_task(conn, task_id, "DONE" if not errors else "PARTIAL", {"processed": processed, "errors": errors})
    return CommandResult(success=not errors, action="draft", processed=processed, errors=errors)


def export_command(args: argparse.Namespace) -> CommandResult:
    init_db(DEFAULT_DB_PATH)
    with db_session(DEFAULT_DB_PATH) as conn:
        task_id = create_task(conn, "export")
        data = export_results(conn)
        finish_task(conn, task_id, "DONE", data.get("summary"))
    return CommandResult(
        success=True,
        action="export",
        processed=int(data["summary"]["exported_leads"]),
        data={key: value for key, value in data.items() if key != "summary"},
    )


def approve_send_command(args: argparse.Namespace) -> CommandResult:
    init_db(DEFAULT_DB_PATH)
    with db_session(DEFAULT_DB_PATH) as conn:
        result = approve_send(conn, args.lead_id, confirm=args.confirm)
    return CommandResult(
        success=bool(result["success"]),
        action="approve-send",
        processed=int(result["processed"]),
        requires_approval=bool(result["requires_approval"]),
        errors=list(result["errors"]),
        data=dict(result["data"]),
    )


def retry_errors_command(args: argparse.Namespace) -> CommandResult:
    init_db(DEFAULT_DB_PATH)
    with db_session(DEFAULT_DB_PATH) as conn:
        processed = reset_processing_errors(conn)
    return CommandResult(success=True, action="retry-errors", processed=processed)


def not_implemented_command(action: str) -> CommandResult:
    return CommandResult(success=False, action=action, errors=[f"{action} is not implemented yet."])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init")

    search = subparsers.add_parser("search")
    search.add_argument("--config", required=True)
    search.add_argument("--input-csv")
    search.add_argument("--csv")

    scan = subparsers.add_parser("scan")
    scan.add_argument("--config", required=True)
    scan.add_argument("--website")
    scan.add_argument("--company-name")
    scan.add_argument("--country")
    scan.add_argument("--source-url")

    for command in ("score", "draft"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--config", required=True)

    subparsers.add_parser("export")
    subparsers.add_parser("status")
    subparsers.add_parser("retry-errors")

    approve = subparsers.add_parser("approve-send")
    approve.add_argument("--lead-id", required=True)
    approve.add_argument("--confirm", action="store_true")
    return parser


def run(argv: list[str] | None = None) -> CommandResult:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command
    try:
        if command == "init":
            return init_command(args)
        if command == "search":
            return search_command(args)
        if command == "status":
            return status_command(args)
        if command == "retry-errors":
            return retry_errors_command(args)
        if command == "scan":
            return scan_command(args)
        if command == "score":
            return score_command(args)
        if command == "draft":
            return draft_command(args)
        if command == "export":
            return export_command(args)
        if command == "approve-send":
            return approve_send_command(args)
        return not_implemented_command(command)
    except config_loader.ConfigError as exc:
        return CommandResult(success=False, action=command, errors=[str(exc)])
    except Exception as exc:
        return CommandResult(success=False, action=command, errors=[f"{type(exc).__name__}: {exc}"])


def main(argv: list[str] | None = None) -> int:
    return emit(run(argv))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
