# Talk to Your Building: technical explanation

Track 01 entry. Run instructions: `BENCHMARK.md`. State of `main` at commit fe67dc3 (24 Oct 2026).

## Idea

Every fact comes from deterministic Python. The model does not compute. It picks tools, asks only what is missing, shows what it understood and phrases the reply. A wrong sentence can only come from a wrong tool call, and the tools are tested against labelled answers.

## Architecture

- **Core** (`building_agent/`): a graph of rooms, doors, stairs and lifts. Routes use the kit 1.1.0 model: door to door, 15 cm clearance from walls, stairs 2 m per metre climbed, a lift 15 m per ride plus 1 m per metre, no route through the outside (`building_agent/routing.py`). One file per question kind in `building_agent/kinds/` (9 kinds).
- **Parser fast path** (`building_agent/question_parser.py`): the benchmark questions follow sentence templates. If a whole sentence matches and every name resolves uniquely, a kind function answers with no API call. Everything else goes to the agent.
- **Session agent** (`agent.py`, `guide_tools.py`): Claude with tool use. Finds rooms, assets and lifts, routes, gives directions with landmarks (3 steps per turn), answers "what changes if X is closed", edits the building.
- **Changes** (close a lift, add or widen a door, move an asset) first show a card with the effect on the current route. `confirm_change` refuses unless the person's own later message is a clear yes.
- **Interaction**: position ("I'm at the lift"), nearest search, guided walking with Auto-Pace (an estimated time per step, then a short check-in; no positioning), spoken-reply rules for voice. Speech in via the browser, speech out via ElevenLabs. Campus endpoints for several buildings (`web/campus_api.py`).
- **Level 4** (`building_agent/level4/`): Claude vision reads a plan image, a colour detector finds door markers, the converter snaps doors to walls, a validator flags rooms with no way out, door suggestions are proposals only.

Stack: Python 3.12, uv, shapely, networkx, Claude API (Sonnet 5.5), stdlib `http.server`, plain JS and SVG, ElevenLabs.

## What we measured

"Estimate" means our own reading of the scoring rule, not the organisers' scorer.

| Measure | Result | Source |
|---|---|---|
| Warm-up oracle | 369 of 369 | `uv run python -m starter_agent.evaluate data/dev --oracle` |
| Our routing vs the 1.1.0 labels (route, step-free, closure, tour; 1338 cases) | full marks 100 %, worst length ratio 0.9991 | `uv run python scripts/eval_warmup.py data/train data/dev --routes` |
| Parser on all labelled train and dev benchmark questions | 648 of 655 correct, 0 wrong; 7 fall through to the model (4 of 7 correct there, see note) | own script: parser, then `benchmark/score.py`, over `data/{train,dev}/*/questions.jsonl` |
| Test file `data/test` | 145 of 145 answered by the parser, file valid, 17 s, no key | `BENCHMARK.md` |
| Independent re-implementation of the 145 test answers by a separate agent (not our kind code) | errand 20/20, wide delivery 18/18, what-if 3/3, shared walls 26/26, stacked 9/9, areas and straight line 69/69 | session scratch scripts, not in the repo |
| Offline tests | 3392 passed, 4 skipped, 2 failed. Both failures are wall-clock limits, measured at machine load 11 (one passes alone, the 40 s sweep took 52 s). Lint clean. | `scripts/check.sh`, 14 min 27 s |
| Live suite | 54 tests exist (`pytest -m live --collect-only`). Last recorded run: 20 passed, 2 failed (older, 22-test suite). Not rerun for this document (costs money). | session log |
| Level 4, 5 clean floors (medians) | recall 1.00, precision 1.00, door recall 1.00, area error 0.6 %; 8 floors: 10.9 s and 0.023 USD per floor (list price) | `docs/eval-log.md`, run 2026-10-24 |

Note on the 4 of 7: that figure comes from the team's earlier run and is not in a repo file. Treat it as unverified.

## Levels

- **1 Locate**: done in the agent (groups, "east lift", ambiguity asks back). Hits are not yet drawn from chat on the page.
- **2 Route**: done (step-free, closures, tours, turn hints). Forklift routes are rough.
- **3 Scale**: several floors done. Campus format, adapters and routing exist, but the format is our own invention.
- **4 Build**: plan image to building through vision, validation, saving. Clean plans good, dense plans weak.

## Limits

- Door widths and equipment are not in a plan, so Level 4 estimates them (every built door is 0.9 m wide, so wide-delivery questions fail on built buildings). Room types from a plan are partial.
- Level 4 on Swiss and OSM plans: recall 0.79 and 0.86, door recall 0.31 and 0.67. Route quality there is low: 6 % and 3 % of room pairs at full points on the two Swiss floors (`docs/eval-log.md`, judge metric). The agent warns and proposes doors, a person confirms.
- Plans carry no scale bar, so the agent asks for one known length. A wrong scale makes every length wrong, the graph stays right.
- No positioning: the person says where they are. No time-bound closures yet.
- Several page parts are not on `main` yet: blue position dot, Auto-Pace timer, mobile layout, hands-free "Hey Wanda" (`docs/STATUS.md`). The server side exists for position and Auto-Pace.
