# Benchmark run

One command produces the answers file and checks it. Verified on a fresh clone of `origin/main` (fe67dc3) on 24 Oct 2026.

## Fresh clone to answers file

```bash
git clone git@github.com:jennifoofoo/synera-agent.git && cd synera-agent
uv sync                      # installs dependencies (11 s on a warm cache)
scripts/get_data.sh          # fetches the git-ignored data/ from the kit repo, skips if present (11 s)
uv run python -m building_agent.submission data/test --csv team_synera.csv
```

Measured: 17 to 25 s for the 145 test questions, ending with `team_synera.csv: ready to submit (11 kB)`. For the 145 questions in `data/test`, every question matched a known sentence template, so the run needs no `ANTHROPIC_API_KEY` and makes no API call (run with the key unset). The `--env-file .env` form is only needed when a question does not match a template: that question goes to the Claude agent, which needs the key. (Not tested without a key, because no test question falls through.)

With the key, for a building or questions with unseen wording:

```bash
uv run --env-file .env python -m building_agent.submission data/test --csv team_synera.csv
```

The command answers every question, writes `team_synera.csv` (`question_id,answer`, README section 6), then checks the file the way the judge app reads it: UTF-8, header row, every question id exactly once, under 5 MB, an `Answer:` line in every reply. It exits non-zero if anything is off. Finished model replies are cached, so a re-run after an interruption only asks what is missing.

## Check an existing file

No agent call, no key.

```bash
uv run python -m building_agent.submission data/test --csv team_synera.csv --check
```

Prints `145 questions in 38 buildings` and `ready to submit`. Exit code 0.

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
- `--json answers.json` also writes the brief's answers.json (id, `Answer:` line, full reply). Verified: it is written next to the CSV.
- `--workers N` questions answered in parallel (default 4)

Before the run, `uv run python scripts/preflight.py <building_dir>` checks a new building in seconds, no key.

## Self-check on dev

Needs the key (it uses the agent for questions the parser does not take). Prints the score per question kind.

```bash
uv run --env-file .env python -m benchmark.evaluate data/dev --agent building_agent.agent:answer --per-kind 3
```

## Notes

- `team_*.csv` is git-ignored. Add the answers file to the submission explicitly.
- `uv sync` currently adds about 100 lines to `uv.lock` (the lock file on main is behind `pyproject.toml`). Harmless, do not commit it.
- The parser answers 648 of 655 labelled train and dev benchmark questions correctly and none wrong. The other 7 need the model. Checked by running the parser and then `benchmark/score.py` over `data/train` and `data/dev`.
