# Workflow

Run `init`, fill `config.yaml`, import CSV with `search`, then run `scan`, `score`, `draft`, `export`. Use `status` after stages and `retry-errors` only after reviewing unresolved errors.

CSV input is the stable first path. Automatic search may generate queries, but live sources must stop on captcha, login, paywall, 429, or explicit access restrictions.

