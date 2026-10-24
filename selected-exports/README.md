# Selected exports

Static dashboard snapshots worth keeping, committed on purpose. (`export/` is the scratch output and stays gitignored.)

Open any `*/index.html` in a browser; no server needed.

| Folder | Runs |
|---|---|
| `2026-10-23-ledgerly-and-cookd/` | 3 Ledgerly validation runs (recall 40% → 70% → 80% as harness bugs were fixed) and the first 4-persona Cookd run |

To add one: `.venv/bin/python -m agenticritic.cli export <run_id ...> --out selected-exports/<name>`
