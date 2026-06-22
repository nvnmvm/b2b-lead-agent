---
name: b2b-lead-agent
description: Discover B2B leads from public web sources, scan company websites, extract public business emails/phones/WhatsApp numbers with evidence, qualify leads, and generate reviewable outreach drafts. Use when the user asks for Apollo-like public lead discovery/enrichment, industry/company prospecting, B2B contact tables, or draft-only outreach workflows.
---

# B2B Lead Agent

Run the bundled CLI from this directory with the current platform's command executor. If commands cannot run, stop and report the missing permission. Use `python` or `python3`; do not name platform-private tools, Gmail, or a fixed browser.

## Guardrails

- Public websites/contact data only.
- No captcha/login/paywall/rate-limit bypass, proxy pools, forged fingerprints, LinkedIn scraping/auto-connect, Sales Navigator scraping, private profile scraping, or SMTP probing.
- Treat LinkedIn only as a user-provided URL/list or public search-result clue. Do not automate logged-in LinkedIn browsing or collect hidden personal contact data.
- Keep evidence text + source URL for conclusions, scoring, and personalization.
- Guessed emails are never valid or sendable.
- Real send requires one explicit `lead_id` plus a second confirmation; default mode is draft-only.

## CLI

Every command returns JSON. Treat `success:false` or non-empty `errors` as review-needed.

```bash
python -m scripts.cli init
python -m scripts.cli search --config config.yaml
python -m scripts.cli search --config config.yaml --input-csv data/companies.csv
python -m scripts.cli <scan|score|draft> --config config.yaml
python -m scripts.cli <export|status|retry-errors>
python -m scripts.cli approve-send --lead-id LEAD_ID [--confirm]
```

## Flow

1. `init`, fill `config.yaml` target fields. `search` without CSV runs public web discovery; `search --input-csv` imports known companies with columns `company_name,website,country,source_url`.
2. Run `search -> scan -> score -> draft -> export`; use `status` between steps.
3. Inspect exported `email`, `phone`, `whatsapp`, `source_url`, and `evidence_text`. Empty or mismatch fields require review.
4. Use `approve-send` only for a user-specified `lead_id`; first call previews, `--confirm` records approval in draft-only mode.

## Reference Routing

- Workflow/recovery: `references/workflow.md`
- Scoring changes: `references/scoring-rules.md`
- New sources, browser automation, send adapters: `references/compliance.md`
- Draft/approval changes: `references/email-rules.md`
- Failures/locked exports: `references/troubleshooting.md`
