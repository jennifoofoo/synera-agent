# Submission documents

What Synera asks for (`SYNERA_RULES.md`): the repo link, a 2-minute video and a short technical explanation in the
form, plus the `SUBMISSION/` folder for the benchmark.

| File | What |
|---|---|
| `SYNERA_RULES.md` | The organisers' submission rules from Discord (Saturday 24.10.) |
| `FORM_TECH_TEXT.md` | The short technical explanation, ready to paste into the form (about 350 words) |
| `TECHNICAL_EXPLANATION.md` | The longer version: architecture, what is new, measured numbers with sources, limits |
| `VIDEO_2MIN.md` | Leonie's video notes; the full storyboard is `VIDEO_STORYBOARD.md` on `feat/video-storyboard` |
| `DEMO_SCRIPT.md` | Older shot table, pitch outline and Q&A answers (Leonie) |
| `../../SUBMISSION/BENCHMARK.md` | How `answers.json` was made and how to run it on a new building |
| `../../SUBMISSION/answers.json` | Our 145 answers for `data/test` |
| `../../BENCHMARK.md` | The same run instructions, short, for the repo root |

The kit `README.md` at the repo root is the organisers' text and stays as it is.

## How to run

```bash
uv sync                                          # install Python dependencies
scripts/get_data.sh                              # fetch the git-ignored data/ folder (skips if present)
cp .env.example .env                             # then type your own keys into .env, never commit it
scripts/check.sh                                 # format check, lint, tests (no API key needed)
scripts/build_twin.sh                            # build the page (twin/, React and three.js) into twin/dist, needs Node 20+
scripts/install_demo_buildings.sh                # copy the Munich Urban Colab demo building, shows up as user/plan-89323a15
uv run python -m web                             # the page at http://127.0.0.1:8765 (reads .env by default)
uv run python -m web --port 8798 --env-file .env # same, other port or env file
uv run --env-file .env python -m building_agent.submission data/test --csv team_synera.csv --json SUBMISSION/answers.json   # answers (template questions need no API call)
uv run python -m building_agent.submission data/test --csv team_synera.csv --check           # check the file, no API call
uv run --env-file .env python -m benchmark.evaluate data/dev --agent building_agent.agent:answer --per-kind 3   # dev self-check (calls the API)
uv run python scripts/preflight.py data/dev/<building_id>        # check an unseen building, no API call
```

Keys in `.env`: `ANTHROPIC_API_KEY` (chat and agent), `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` (Wanda's voice).
Without the Anthropic key the page still shows the building, routes and notes; only the chat is off.
For the phone (the mic needs https): `scripts/tunnel.sh`.
