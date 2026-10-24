# synera-agent

Industrial Agents Hackathon 2026, Track 01 "Talk to Your Building". Kit README: `README.md` (read sections 3, 4, 6 first).

## Start here (every session, both people)
1. `git pull`, then read `docs/specs/core-2d.md` (the contract: question kinds, signatures, rules, file ownership) and `docs/STATUS.md` (who works on what).
2. Work only on your own files and your claimed rows. Ownership: Leonie `geometry.py`, `queries.py` (floor_area_total, shared_walls_count, largest_room, straight_line_3d, room_stacked, wide_delivery_count); Jennifer `queries_routing.py`, `tools.py`, `agent.py`, `directions.py`, `registry.py` (errand done, what_if_door).
3. Tests are the contract: add `tests/test_<kind>.py` using `labelled_questions(kind)` from `tests/conftest.py` (example: `tests/test_errand.py`). No merge without a test.

## Principle
Every fact comes from deterministic Python (`building_agent/queries.py`), the LLM only picks tools and phrases the reply.
Replies must end with exactly one `Answer:` line (the scorer reads only that).

## Layout
- `starter_agent/`, `benchmark/`: kit code, do not edit. Reuse `BuildingMap` (routing model is already correct).
- `building_agent/`: our code. `geometry.py`, `queries.py`, `tools.py`, `agent.py`.
- `tests/`: one test per question kind against dev/train answers, no API calls.
- `data/`: kit data, git-ignored (get it with `scripts/get_data.sh`).
- `docs/STATUS.md`: who works on what, file ownership, priorities.

## Setup (new machine or fresh worktree)
1. `uv sync`
2. `scripts/get_data.sh` (fetches the git-ignored `data/` from the kit repo, skips if it exists)
3. `cp .env.example .env`. The person types her own `ANTHROPIC_API_KEY` into `.env`. Never ask for, invent or print the key; only check that `.env` exists and is not tracked by git.
4. `uv run pytest` must be green before any work.
5. Claim a task in `docs/STATUS.md`, commit, push, then create `feat/q-<kind>` from `main`.

## Commands
- `uv sync`
- `uv run pytest`
- `uv run --env-file .env python -m benchmark.evaluate data/dev --agent building_agent.agent:answer --per-kind 3`

## Teamwork (two people, each with her own Claude session)
- At session start: `git pull`, then read `docs/STATUS.md`.
- Before working on a task: claim it in `docs/STATUS.md` (name, status, branch), commit and push first.
- One branch per task (`feat/q-<kind>`), small merges to `main`, `uv run pytest` green before merging.
- Parallel sessions only in separate worktrees (`claude -w <name>`).
- File ownership: Leonie `queries.py`, `geometry.py`; Jennifer `tools.py`, `agent.py`, `directions.py`, `queries_routing.py`. Do not edit the other person's files without asking in chat.
- One query function per question kind, signature stays stable.
- Use `labelled_questions(kind)` from `tests/conftest.py` to test a kind against train/dev answers (see `tests/test_errand.py`).
- Only one person uploads submissions, agree in chat first.

## Rules
- No hard-coding to test buildings, the Sunday building is new.
- Never upload a worse submission over a better one.
- Secrets only in `.env`.
