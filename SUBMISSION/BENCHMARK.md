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
sentence template are answered by plain Python without an API call; on `data/test` that is all 145, so the file is
reproducible without the model. Other questions go to Claude; finished model replies are cached, so a re-run after an
interruption only asks what is missing.

## Run on an unseen building (your secret building)

```bash
git clone https://github.com/jennifoofoo/synera-agent && cd synera-agent
export ANTHROPIC_API_KEY=...        # or put ANTHROPIC_API_KEY=... into a .env file in this folder
./run_benchmark.sh <split_dir | building_dir | questions_file> [out_dir]
```

That is all: it runs `uv sync`, answers every question without stopping (one failed question never stops the
others), and writes `<out_dir>/answers.json` and `<out_dir>/answers.csv` (default `benchmark_out/`), then checks
them. No `data/` download is needed for a new building. Tested on a fresh clone with the key as an environment
variable and with a `.env` file.

The same as one command, if you prefer:

```bash
uv run --env-file .env python -m building_agent.submission <input> --csv answers.csv --json answers.json
```

Accepted inputs: a split directory (like `data/test`), one building directory (with its `building.json`, plan images
and `questions.jsonl`, the kit format), or a questions file (`questions.jsonl` as in the kit, `questions.csv` with
`question_id,building_id,kind,question`, or `questions.json` as a list or `{"questions": [...]}` with `id` and
`text`). Use `--root DIR` if the questions file is not next to the building folders, `--workers N` for parallel
questions (default 4).

Level 4: per the organisers (Discord, 25.10.) the secret building comes in the same format as the kit (plans plus
`building.json` with the scale), so the command above covers it. Building a building from plan images alone is
also in the app: start it (`scripts/build_twin.sh`, then `uv run python -m web`), building menu, "New building",
add the plan images; after the confirm card it is saved under `agent_output/buildings/<id>/`, a normal building
directory for the command above.

## Format of `answers.json`

A list of dictionaries with the keys `question_id` and `answer`, as the organisers asked (Discord, 25.10. 11:16):

```json
[
  {"question_id": "osm-way363805324-H01",
   "answer": "The largest one is Generic room 1.02 with 162.33 square metres.\nAnswer: Generic room 1.02, 162.33 m²"}
]
```

`answer` is the full reply, exactly as in the kit's submission CSV. The official scorer (`benchmark/score.py`) reads the
last line starting with `Answer:` from it. All 145 entries have exactly such a line, and `answer` is the same text as in
`team_synera.csv`.

## Check without a key

```bash
uv run python -m building_agent.submission data/test --csv team_synera.csv --check
```

## How it works (short)

Every fact comes from deterministic Python over the kit's `BuildingMap` and routing model (door to door, 15 cm wall
clearance, stairs and lifts as in kit 1.1.0); the LLM (Claude) only picks tools and phrases the reply. Details:
`docs/submission/TECHNICAL_EXPLANATION.md` and the repo `README.md`.
