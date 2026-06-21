# Agent Notes

Use this project through `python -m scripts.cli` only. Do not call platform-specific private tools from the skill instructions.

Before running lead workflows:

1. Confirm `config.yaml` exists and required business fields are filled.
2. Confirm the input CSV contains `company_name,website,country,source_url`.
3. Keep command output as JSON for downstream parsing.
4. Stop the current source on captcha, login wall, paywall, 429, or repeated access errors.
5. Never treat guessed emails as sendable contacts.
6. Never send real emails without a single explicit `lead_id` and a second confirmation step.


