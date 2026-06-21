# Claude Code Adapter

Run the same module commands used by all platforms:

```bash
python -m scripts.cli init
python -m scripts.cli search --config config.yaml --input-csv data/companies.csv
python -m scripts.cli <scan|score|draft> --config config.yaml
python -m scripts.cli export
```

Use `python3` if needed. If command execution is unavailable, stop. Keep approval manual and per lead.

