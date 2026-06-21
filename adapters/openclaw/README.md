# OpenClaw Adapter

Use OpenClaw command execution for the shared CLI. If unavailable, stop and request permission.

Sequence:

```bash
python -m scripts.cli init
python -m scripts.cli search --config config.yaml --input-csv data/companies.csv
python -m scripts.cli <scan|score|draft> --config config.yaml
python -m scripts.cli export
```

Use `python3` if needed. Do not replace the CLI with browser-specific search, approval, or send automation.

