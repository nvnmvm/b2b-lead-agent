from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output"
TEMPLATE_COLUMNS_PATH = PROJECT_ROOT / "templates" / "output-columns.json"


def timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value or "lead").strip("_")[:120] or "lead"


def output_columns() -> list[str]:
    return json.loads(TEMPLATE_COLUMNS_PATH.read_text(encoding="utf-8"))


def score_match_reason(score_details: str | None) -> str:
    if not score_details:
        return ""
    try:
        details = json.loads(score_details)
    except json.JSONDecodeError:
        return ""
    return "; ".join(details.get("reasons", []))


def fetch_export_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            leads.lead_id,
            leads.company_name,
            leads.website,
            leads.country,
            leads.industry,
            leads.company_summary,
            leads.contact_name,
            leads.job_title,
            leads.email,
            leads.email_status,
            leads.score,
            leads.score_level,
            leads.score_details,
            leads.source_url,
            leads.status,
            email_drafts.subject AS email_subject,
            email_drafts.body AS email_body
        FROM leads
        LEFT JOIN email_drafts ON email_drafts.lead_id = leads.lead_id
        ORDER BY leads.created_at, leads.lead_id
        """
    ).fetchall()
    exported = []
    columns = output_columns()
    for row in rows:
        item = dict(row)
        item["match_reason"] = score_match_reason(item.pop("score_details", None))
        exported.append({column: item.get(column, "") for column in columns})
    return exported


def safe_to_excel(df: pd.DataFrame, path: Path) -> Path:
    try:
        df.to_excel(path, index=False)
        return path
    except PermissionError:
        alternate = path.with_name(f"{path.stem}_{datetime.utcnow().strftime('%H%M%S_%f')}{path.suffix}")
        df.to_excel(alternate, index=False)
        return alternate


def write_json(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def fetch_draft_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            leads.lead_id,
            leads.email,
            leads.contact_name,
            leads.company_name,
            email_drafts.subject,
            email_drafts.body,
            email_drafts.source_url
        FROM email_drafts
        JOIN leads ON leads.lead_id = email_drafts.lead_id
        ORDER BY email_drafts.created_at
        """
    ).fetchall()
    return [dict(row) for row in rows]


def write_draft_review_files(drafts: list[dict[str, Any]], output_dir: Path) -> list[str]:
    files: list[str] = []
    drafts_dir = output_dir / "draft_review"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    for draft in drafts:
        base = safe_filename(str(draft["lead_id"]))
        txt_path = drafts_dir / f"{base}.txt"
        eml_path = drafts_dir / f"{base}.eml"
        txt_path.write_text(
            f"To: {draft.get('email', '')}\n"
            f"Subject: {draft.get('subject', '')}\n"
            f"Source: {draft.get('source_url', '')}\n\n"
            f"{draft.get('body', '')}\n",
            encoding="utf-8",
        )

        message = EmailMessage()
        message["To"] = draft.get("email", "")
        message["Subject"] = draft.get("subject", "")
        message["From"] = ""
        message.set_content(draft.get("body", ""))
        eml_path.write_text(message.as_string(), encoding="utf-8")
        files.extend([str(txt_path), str(eml_path)])
    return files


def run_summary(conn: sqlite3.Connection, exported_count: int, draft_count: int) -> dict[str, Any]:
    statuses = {
        row["status"]: row["count"]
        for row in conn.execute("SELECT status, COUNT(*) AS count FROM leads GROUP BY status").fetchall()
    }
    return {
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "exported_leads": exported_count,
        "exported_drafts": draft_count,
        "lead_statuses": statuses,
        "unresolved_errors": conn.execute("SELECT COUNT(*) FROM errors WHERE resolved = 0").fetchone()[0],
    }


def export_results(conn: sqlite3.Connection, output_dir: str | Path = OUTPUT_DIR) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    stamp = timestamp()

    lead_rows = fetch_export_rows(conn)
    draft_rows = fetch_draft_rows(conn)
    lead_df = pd.DataFrame(lead_rows, columns=output_columns())
    draft_df = pd.DataFrame(draft_rows)

    leads_xlsx = safe_to_excel(lead_df, output_path / f"leads_{stamp}.xlsx")
    drafts_xlsx = safe_to_excel(draft_df, output_path / f"drafts_{stamp}.xlsx")
    leads_json = write_json(output_path / f"leads_{stamp}.json", lead_rows)
    review_files = write_draft_review_files(draft_rows, output_path)
    summary = run_summary(conn, len(lead_rows), len(draft_rows))
    summary_json = write_json(output_path / f"run_summary_{stamp}.json", summary)

    return {
        "leads_xlsx": str(leads_xlsx),
        "drafts_xlsx": str(drafts_xlsx),
        "leads_json": str(leads_json),
        "summary_json": str(summary_json),
        "review_files": review_files,
        "summary": summary,
    }

