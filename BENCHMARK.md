# Benchmark run

One command, no manual steps. Needs `ANTHROPIC_API_KEY` in `.env`.

```bash
uv sync
uv run --env-file .env python -m benchmark.evaluate data/test \
  --agent building_agent.agent:answer --submission-csv team_<name>.csv
```

Sunday building: same command with the directory that holds the new building and its `questions.jsonl`.
Self-check on dev (prints the score per question kind):

```bash
uv run --env-file .env python -m benchmark.evaluate data/dev --agent building_agent.agent:answer --per-kind 3
```
