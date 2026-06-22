# Workflow

Run `init`, fill `config.yaml`, run public discovery with `search` or import CSV with `search --input-csv`, then run `scan`, `score`, `draft`, `export`. Use `status` after stages and `retry-errors` only after reviewing unresolved errors.

CSV input is the stable first path for user-supplied company lists, trade-show lists, or manually exported LinkedIn/Sales Navigator company lists. Automatic search uses public web search queries generated from `business.product`, `target.industries`, `target.countries`, and `target.customer_types`; live sources must stop on captcha, login, paywall, 429, or explicit access restrictions.

Exports include `email`, `phone`, `whatsapp`, `source_url`, and `evidence_text`. Treat missing WhatsApp/email and domain mismatches as review-needed, not verified contact data.
