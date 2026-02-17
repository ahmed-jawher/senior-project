# logconsolidator

Internal producer-consumer log pipeline with bounded queues.

Run locally:

```bash
python3 main.py
```

Config lives at `config/sources/*.json` (one file per log source).
Processed records are written to `data/processed.jsonl`.
Startup fails fast if any configured source `path` is missing or unreadable.
