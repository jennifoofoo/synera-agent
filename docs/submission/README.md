# Submission documents

| File | What |
|---|---|
| `TECHNICAL_EXPLANATION.md` | Idea, architecture diagram, stack, measured numbers with sources, limits, testing (max 1.5 pages) |
| `DEMO_SCRIPT.md` | 90-second video shot table, 3-minute pitch outline, 8 Q&A answers, recording checklist |
| `../../BENCHMARK.md` | The one command to produce and check the answers file |

The kit `README.md` at the repo root is the organisers' text and stays as it is.

## How to run

```bash
uv sync                                          # install dependencies
scripts/get_data.sh                              # fetch the git-ignored data/ folder (skips if present)
cp .env.example .env                             # then type your own keys into .env, never commit it
scripts/check.sh                                 # format check, lint, tests (no API key needed)
uv run python -m web                             # chat and 2D plan at http://127.0.0.1:8765
uv run --env-file .env python -m building_agent.submission data/test --csv team_synera.csv   # answers file (calls the API)
uv run python -m building_agent.submission data/test --csv team_synera.csv --check           # check the file, no API call
uv run --env-file .env python -m benchmark.evaluate data/dev --agent building_agent.agent:answer --per-kind 3   # dev self-check
uv run python scripts/preflight.py data/dev/<building_id>        # check an unseen building, no API call
```

Keys needed in `.env`: `ANTHROPIC_API_KEY` (agent), `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` (voice out). `uv run --env-file .env python -m web` loads them too (the web page also reads `.env` by default).
