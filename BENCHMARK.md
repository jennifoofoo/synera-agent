# Benchmark run

One command, no manual steps. Needs `ANTHROPIC_API_KEY` in `.env` (copy `.env.example`).

```bash
uv sync
uv run --env-file .env python -m building_agent.submission data/test --csv team_synera.csv
```

It answers every question, writes `team_synera.csv` (`question_id,answer`, README section 6), then checks the file the way
the judge app reads it: UTF-8, header row, every question id exactly once, under 5 MB, an `Answer:` line in every reply.
It exits non-zero if anything is off. Questions that match a known sentence template are answered by plain Python
without an API call. Finished model replies are cached, so a re-run after an interruption only asks what is missing.

## Unseen building (Sunday)

Same command, pointed at whatever arrives.

```bash
uv run --env-file .env python -m building_agent.submission <building_dir_or_questions_file> --csv team_synera.csv --json answers.json
```

Accepted inputs:
- a split directory (`data/test`), one building directory, or a questions file
- `questions.jsonl` (kit), `questions.csv` (`question_id,building_id,kind,question`), or `questions.json` (the challenge brief: a list or `{"questions": [...]}` with `id` and `text`)

Options:
- `--root DIR` if the questions file is not next to the building folders
- `--json answers.json` also writes the brief's answers.json (id, `Answer:` line, full reply)
- `--workers N` questions answered in parallel (default 4)

## Check an existing file

No agent call, no key needed.

```bash
uv run python -m building_agent.submission data/test --csv team_synera.csv --check
```

## Self-check on dev

Prints the score per question kind.

```bash
uv run --env-file .env python -m benchmark.evaluate data/dev --agent building_agent.agent:answer --per-kind 3
```

Note: `team_*.csv` is git-ignored. Add the answers file to the submission explicitly.
