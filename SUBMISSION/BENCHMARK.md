# Benchmark: Team Synera Agent (Jennifer Nikolovic, Leonie Merkl)

`SUBMISSION/answers.json` holds our answers to all 145 questions of `data/test` (kit 1.1.0). This file says how it was
made and how to run the same system on a new building.

## Setup

```bash
uv sync
cp .env.example .env          # then put your ANTHROPIC_API_KEY into .env
scripts/get_data.sh           # fetches the kit data into data/ (skips if it exists)
```

## Reproduce `answers.json` (test split)

```bash
uv run --env-file .env python -m building_agent.submission data/test --csv team_synera.csv --json SUBMISSION/answers.json
```

One command, no manual steps. It answers every question, writes the CSV (`question_id,answer`, kit README section 6)
and `answers.json`, then checks the CSV the way the judge app reads it (UTF-8, header row, every id exactly once,
under 5 MB, an `Answer:` line in every reply) and exits non-zero if anything is off. Questions that match a known
sentence template are answered by plain Python without an API call; finished model replies are cached, so a re-run
after an interruption only asks what is missing.

## Run on an unseen building

Same command, pointed at what you hand us:

```bash
uv run --env-file .env python -m building_agent.submission <building_dir | split_dir | questions_file> \
  --csv team_synera.csv --json answers.json
```

Accepted inputs: a split directory (like `data/test`), one building directory, or a questions file
(`questions.jsonl` as in the kit, `questions.csv` with `question_id,building_id,kind,question`, or `questions.json`
as a list or `{"questions": [...]}` with `id` and `text`). Use `--root DIR` if the questions file is not next to the
building folders, `--workers N` for parallel questions (default 4).

Level 4 (a building given as floor plans): put the plan images (with their `.svg` and `building.json` if present) in a
folder and ask in the chat page (`scripts/build_twin.sh`, then `uv run python -m web`), or let the agent convert
them; the converted building is then a normal building directory for the command above.

## Format of `answers.json`

```json
{"answers": [
  {"question_id": "osm-way363805324-H01", "id": "osm-way363805324-H01",
   "answer": "Generic room 1.02, 162.33 m²",
   "reply": "The largest one is Generic room 1.02 with 162.33 square metres.\nAnswer: Generic room 1.02, 162.33 m²"}
]}
```

- `question_id` / `id`: the question id (both names, as in the kit CSV and the challenge brief).
- `answer`: the committed answer, the text after the final `Answer:` line (what the scorer reads).
- `reply`: the full reply the agent gave.

## Check without a key

```bash
uv run python -m building_agent.submission data/test --csv team_synera.csv --check
```

## How it works (short)

Every fact comes from deterministic Python over the kit's `BuildingMap` and routing model (door to door, 15 cm wall
clearance, stairs and lifts as in kit 1.1.0); the LLM (Claude) only picks tools and phrases the reply. Details:
`docs/submission/TECHNICAL_EXPLANATION.md` and the repo `README.md`.
