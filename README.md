# b2b-lead-agent

Platform-neutral Agent Skill + Python CLI for public B2B lead workflows:

Public web discovery or CSV company list -> website scan -> public email/phone/WhatsApp extraction -> scoring -> reviewable English drafts -> Excel/JSON/TXT/EML export.

Works with Codex, OpenClaw, Claude Code, Windows, macOS, and Linux through the same CLI.

## Safety

No automatic sending, LinkedIn automation/scraping, Sales Navigator scraping, captcha/login/paywall/rate-limit bypass, proxy pools, forged fingerprints, SMTP probing, or guessed-email sending. Every conclusion keeps evidence text and a source URL.

## Install

```bash
python -m pip install -r requirements.txt
python -m scripts.cli init
```

Use `python3` if your system does not expose `python`. Fill the generated `config.yaml`.

## CSV

Use `data/companies.csv` or pass `--input-csv`:

```csv
company_name,website,country,source_url
Example Pumps,https://example.com,Germany,https://expo.example/list
```

Omit `--input-csv` to run public web discovery from `config.yaml` target fields.

## Workflow

```bash
python -m scripts.cli search --config config.yaml
python -m scripts.cli search --config config.yaml --input-csv data/companies.csv
python -m scripts.cli scan --config config.yaml
python -m scripts.cli score --config config.yaml
python -m scripts.cli draft --config config.yaml
python -m scripts.cli export
python -m scripts.cli status
```

All commands return JSON. `approve-send` is two-step and draft-only by default:

```bash
python -m scripts.cli approve-send --lead-id LEAD_ID
python -m scripts.cli approve-send --lead-id LEAD_ID --confirm
```

## Test

```bash
python -m pytest
```

Adapter notes live in `adapters/codex`, `adapters/openclaw`, and `adapters/claude-code`.
