# synera-agent

Industrial Agents Hackathon 2026, Track 01 "Talk to Your Building". Kit README: `README.md` (read sections 3, 4, 6 first).

## Principle
Every fact comes from deterministic Python (`building_agent/queries.py`), the LLM only picks tools and phrases the reply.
Replies must end with exactly one `Answer:` line (the scorer reads only that).

## Layout
- `starter_agent/`, `benchmark/`: kit code, do not edit. Reuse `BuildingMap` (routing model is already correct).
- `building_agent/`: our code. `geometry.py`, `queries.py`, `tools.py`, `agent.py`.
- `tests/`: one test per question kind against dev/train answers, no API calls.
- `data/`: kit data, git-ignored.

## Commands
- `uv sync`
- `uv run pytest`
- `uv run --env-file .env python -m benchmark.evaluate data/dev --agent building_agent.agent:answer --per-kind 3`

## Teamwork (two people, each with her own Claude session)
- At session start: `git pull`, then read `docs/STATUS.md`.
- Before working on a task: claim it in `docs/STATUS.md` (name, status, branch), commit and push first.
- One branch per task (`feat/q-<kind>`), small merges to `main`, `uv run pytest` green before merging.
- Parallel sessions only in separate worktrees (`claude -w <name>`).
- One query function per question kind in `queries.py`, signature stays stable.
- Only one person uploads submissions, agree in chat first.

## Rules
- No hard-coding to test buildings, the Sunday building is new.
- Never upload a worse submission over a better one.
- Secrets only in `.env`.
