---
name: b2b-lead-agent
description: Search public business websites, qualify B2B leads, extract public business contacts, and generate reviewable outreach drafts.
---

# B2B Lead Agent

Run the bundled CLI from this directory with the current platform's command executor. If commands cannot run, stop and report the missing permission. Use `python` or `python3`; do not name platform-private tools, Gmail, or a fixed browser.

## Guardrails

- Public websites/contact data only.
- No captcha/login/paywall/rate-limit bypass, proxy pools, forged fingerprints, LinkedIn scraping/auto-connect, or SMTP probing.
- Keep evidence text + source URL for conclusions, scoring, and personalization.
- Guessed emails are never valid or sendable.
- Real send requires one explicit `lead_id` plus a second confirmation; default mode is draft-only.

## CLI

Every command returns JSON. Treat `success:false` or non-empty `errors` as review-needed.

```bash
python -m scripts.cli init
python -m scripts.cli search --config config.yaml --input-csv data/companies.csv
python -m scripts.cli <scan|score|draft> --config config.yaml
python -m scripts.cli <export|status|retry-errors>
python -m scripts.cli approve-send --lead-id LEAD_ID [--confirm]
```

## Flow

1. `init`, fill `config.yaml`, then provide CSV columns `company_name,website,country,source_url`.
2. Run `search -> scan -> score -> draft -> export`; use `status` between steps.
3. Use `approve-send` only for a user-specified `lead_id`; first call previews, `--confirm` records approval in draft-only mode.

## Reference Routing

- Workflow/recovery: `references/workflow.md`
- Scoring changes: `references/scoring-rules.md`
- New sources, browser automation, send adapters: `references/compliance.md`
- Draft/approval changes: `references/email-rules.md`
- Failures/locked exports: `references/troubleshooting.md`

