# synera-agent

Industrial Agents Hackathon 2026, Track 01 "Talk to Your Building". Kit README: `README.md` (read sections 3, 4, 6 first).

## Start here (every session, both people)
1. **Who are you working for?** Check `git config user.name` and `gh api user --jq .login`: `jennifoofoo` is Jennifer, `leoniemerkl` is Leonie. If unclear, ask once ("Jennifer oder Leonie?") and store the answer in `.claude/role` (git-ignored). Work only from that person's list.
2. `git pull`, then read `docs/specs/core-2d.md` (the contract: kinds, signatures, rules, tasks per person) and `docs/STATUS.md` (who owns which kind, blockers).
3. Work only on your own kinds and claimed rows. If you need to change someone else's file, do not: add a line under "Blocker" in `docs/STATUS.md` and continue elsewhere.
4. Tests are the contract. No merge without a test.
5. Parked ideas (not decided, do not build without the team): `docs/IDEAS.md`.

## Principle
Every fact comes from deterministic Python (`building_agent/kinds/`), the LLM only picks tools and phrases the reply.
Replies must end with exactly one `Answer:` line (the scorer reads only that).

## One file per question kind
- `building_agent/kinds/<kind>.py`: the function plus `KIND = Kind(name, fn, description)`. File name equals kind name. First parameter is `bm` (a `BuildingMap`).
- `tests/test_<kind>.py`: use `labelled_questions(kind)` from `tests/conftest.py` (example: `tests/test_errand.py`).
- A row for the kind in `docs/STATUS.md`.
- Nothing else to edit: `building_agent/registry.py` finds the file, `tools.py` builds the tool. `tests/test_registry.py` fails if any of this is missing.
- Shared helpers go into `building_agent/geometry.py`, only when two kinds need them.

## Layout
- `starter_agent/`, `benchmark/`: kit code, do not edit. Reuse `BuildingMap` (routing model is already correct).
- `building_agent/`: our code. `kinds/`, `registry.py`, `geometry.py`, `tools.py`, `agent.py`, `directions.py`.
- `tests/`: one test per kind against dev/train answers, no API calls.
- `data/`: kit data, git-ignored (get it with `scripts/get_data.sh`).
- `docs/STATUS.md`: who works on what. `docs/specs/core-2d.md`: the spec.

## Setup (new machine or fresh worktree)
1. `uv sync`
2. `scripts/get_data.sh` (fetches the git-ignored `data/` from the kit repo, skips if it exists)
3. `cp .env.example .env`. The person types her own `ANTHROPIC_API_KEY` into `.env`. Never ask for, invent or print the key; only check that `.env` exists and is not tracked by git.
4. `uv run pytest` must be green before any work.
5. Claim a task in `docs/STATUS.md`, commit, push, then create `feat/q-<kind>` from `main`.

## Commands
- `uv sync`
- `scripts/check.sh` (ruff format check, ruff lint, tests; run `uv run ruff format .` to fix formatting)
- `uv run pytest`
- `uv run --env-file .env python -m benchmark.evaluate data/dev --agent building_agent.agent:answer --per-kind 3`

## Teamwork (two people, each with her own Claude session)
- Before working on a task: claim it in `docs/STATUS.md` (name, status, branch), commit and push first.
- One branch per task (`feat/q-<kind>`), `git pull --rebase` before push, small merges to `main`, `scripts/check.sh` green before merging.
- Changes to shared code (`tools.py`, `agent.py`, `registry.py`, `geometry.py`, `CLAUDE.md`): before merging, let a fresh review agent (no prior context) read the diff against the spec. Own kind files only need `scripts/check.sh`.
- Parallel sessions only in separate worktrees (`claude -w <name>`).
- Shared files (`CLAUDE.md`, `docs/STATUS.md`, `pyproject.toml`): only after `git pull`, keep changes small.
- At the end of a session: update `docs/STATUS.md`, push, note open points.
- Only one person uploads submissions, agree in chat first.

## Before anything reaches main
- `scripts/check.sh` does not run the live tests, so it cannot see a changed conversation behaviour. For any change that touches the prompt, the tools, `walk.py`, position, voice or the chat layer, run the live suite as well before merging to `main`: `uv run --env-file .env pytest -m live -q` (cached, about 2 minutes, one to two dollars). It must be fully green, and a red live test is fixed or, if the design changed on purpose, the test is updated with a docstring that says why. Never weaken an assertion about safety (no change without a card and a clear yes in the next message).
- Also measure `uv run python scripts/eval_warmup.py data/train data/dev --routes` and the dev benchmark (`benchmark.evaluate data/dev --per-kind 3`) after changes to routing or the question kinds.

## Rules
- No hard-coding to test buildings, the Sunday building is new.
- Never upload a worse submission over a better one.
- Secrets only in `.env`.
