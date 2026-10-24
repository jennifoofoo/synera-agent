# Benchmark run

One command, no manual steps. Needs `ANTHROPIC_API_KEY` in `.env`.

```bash
uv sync
uv run --env-file .env python -m building_agent.submission data/test --csv team_synera.csv
```

It answers every question, writes `question_id,answer` (README section 6), then checks the file the way the judge app reads it
(UTF-8, header, every id once, under 5 MB, an `Answer:` line in every reply) and exits non-zero if anything is off.
Finished replies are cached, so re-running after an interruption only asks the missing questions.

Sunday building: same command, pointed at whatever arrives. Accepted inputs:
- a split directory (`data/test`), one building directory, or a questions file;
- `questions.jsonl` (kit format), `questions.csv` (`question_id,building_id,kind,question`), or `questions.json`
  (challenge brief: a list or `{"questions": [...]}` with `id` and `text`);
- `--root DIR` if the questions file is not next to the building folders;
- `--json answers.json` to also write the brief's answers.json (id, Answer line, full reply).

```bash
uv run --env-file .env python -m building_agent.submission <building_dir_or_questions_file> --csv team_synera.csv --json answers.json
```

Check an existing file without calling the agent:

```bash
uv run python -m building_agent.submission data/test --csv team_synera.csv --check
```

Self-check on dev (prints the score per question kind):

```bash
uv run --env-file .env python -m benchmark.evaluate data/dev --agent building_agent.agent:answer --per-kind 3
```
