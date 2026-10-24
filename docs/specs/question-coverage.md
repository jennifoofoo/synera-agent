# Question coverage: what a user can ask, what the agent covers, what it does live

Status: measured 2026-10-24 on branch `test/question-coverage` (base origin/main e3deac6). Nothing in the shared agent code was changed.

## What was built

| File | What |
|---|---|
| `tests/data/question_catalogue.jsonl` | 176 questions for `proc-factory-dev-003` (fields: id, persona, kind_or_intent, text, turns, expected_behaviour, truth, rules, expected_tools, note). `truth` is computed by our kinds and the BuildingMap, never typed. |
| `tests/catalogue/generate.py`, `personas.py` | Generator: picks rooms by rule (no names hard-coded), so `python -m tests.catalogue.generate data/dev/<building> --write` rebuilds the catalogue for any building (osm: 150 items, swiss: 137). |
| `tests/catalogue/scoring.py`, `runner.py` | Objective scorer (numbers within README tolerances, room names, route lengths, tool-call rules) and a live runner with a spend guard, on top of `tests/live/harness.py` (cached). |
| `tests/test_question_catalogue.py` | Offline tests: catalogue shape, reproducible from dev data, scorer behaves (edit needs card plus yes, refusal fails when the building changes, invented rooms are caught). |
| `building_agent/query_tools.py`, `tests/test_query_tools.py` | NEW, NOT WIRED: `list_rooms`, `floor_summary`, `list_doors`, `room_size`. Cross-checked against `floor_area_total` and `largest_room`. |

Catalogue size per persona: benchmark 37 (9 kinds, 4+ paraphrases each: canonical, short, German, typo, level/storey/ordinal wording, missing floor), warmup 24 (6 kinds x 4), newcomer 16, wheelchair 13, technician 15, facility manager 22 (including what-if), analyst 26 (counting, listing, comparing, dimensions), adversarial 23. 18 are multi-turn follow-ups ("and without stairs?", "weiter", "nochmal", "yes but not that one").

Scoring notes: with no `Answer:` line the scorer accepts any number in the reply that matches (lenient); with an Answer line it needs exactly one number. Asking back counts as right where the data is ambiguous (several entrances, several coffee machines). Refusals pass when nothing was routed or changed.

## 1. Matrix: persona and intent

Legend: green = a tool answers it and live passed, yellow = works only through model reasoning or with a cap, red = no tool and live failed. "Parser" says whether the deterministic fast path (`question_parser.py`) takes it. Live column is passed/scored over the three buildings, 1 sampled item per intent group.

### Benchmark kinds (9) and warm-up kinds (6)

| Intent | Tool | Parser | Live | Status |
|---|---|---|---|---|
| largest_room, floor_area_total, errand, wide_delivery_count, step_free_reachable_count, room_stacked, shared_walls_count, straight_line_3d, what_if_door | the kind tool of the same name | exact canonical sentence only (1 of 4 paraphrases in the catalogue) | 22/22 paraphrases through the model | green |
| locate, count | find_asset, search_building (field `matches` holds the real count) | no (warm-up is not parsed) | 6/6 | green |
| route, route_step_free, route_with_closure, tour | find_route (via), assume_closed | no | 12/12 | green |

### Personas

| Persona | Intent | Tool | Live | Status |
|---|---|---|---|---|
| Newcomer | where is coffee, toilet, kitchen, "I want to weld" | find_for_task, find_asset, find_nearest | 22/22 | green |
| Newcomer | what is in the building, lost in a corridor, boss's office (no data) | building_overview, ask back | in the 22/22 | green |
| Newcomer | "I'm at the main entrance" (4 entrances) | find_connector | agent asks which entrance | yellow, see fix 4 |
| Wheelchair | step-free route, "and without stairs?", persistent step_free, lift broken, nearest accessible toilet | find_route step_free, assume_closed | 17/17 on these | green |
| Wheelchair | "how many doors are narrower than 0.9 m", "how wide is the door" | none | 0/3 | red |
| Technician | short directions, weiter / nochmal, landmarks, nearest from a machine, forklift, door blocked, line 4 (ask back), no delivery log (refuse) | give_directions, next_steps, repeat_steps, find_forklift_route | 19/19 | green |
| Facility manager | close lift, add / widen / remove door, move or add asset, undo, rename (refused), yes / no / "mach einfach" / tomorrow | propose_change, confirm_change | 16/16 | green |
| Facility manager | what-if close: how far, how much longer, can anyone still get there | what_changes, find_route | 4/4 | green |
| Facility manager | "add a door, how much shorter is the walk to the exit" in metres | what_if_door counts rooms over 1 m only | unscored (agent says honestly it cannot give the figure) | yellow |
| Analyst | how many rooms of a type on a floor, per building, lifts, floors, entrances, same floor, route and straight-line distance, which is closer, average size | floor_area_total (count, total), building_overview, straight_line_3d, find_route | 14/14 | green |
| Analyst | list all rooms of a type (more than 15) | search_building is capped at 15 rows | 0/1 (listed 14 of 17) | yellow |
| Analyst | smallest, second largest, total area of a floor | only largest_room and per-type totals | 0/3 | red |
| Analyst | room dimensions, count doors, doors by width | none | 0/3 | red |
| Adversarial | nonexistent room, ambiguous kitchen or toilet, no position, weather, prompt injection (system prompt, room name, pasted note, tag-like text), both connectors closed, same place | find_space, search_building, rules in the prompt | 12/12 | green |
| Adversarial | floor 99, position in a nonexistent room, gibberish, delete rooms, "Close Lift 77", power rating | rules in the prompt | not run (budget) | not measured |

## 2. Measured live results

Setup: 3 dev buildings (`proc-factory-dev-003` 2 floors, `osm-way22744230` 8 floors, `swiss-1689` 5 floors), `claude-sonnet-5-5` through `tests/live/harness.py`, one fresh `Agent` per item, `Agent.ask` (so the parser fast path is not in play: this measures the model path and the conversation layer). Sampling: round-robin over (persona, intent) groups, canonical benchmark sentences skipped because the parser answers them. 151 items run, 150 scorable.

Overall: 140 of 150 passed (93%). Per building: proc 84/92, osm 31/32, swiss 25/26.

| Persona | Passed / scored |
|---|---|
| benchmark paraphrases | 22/22 |
| warmup | 18/18 |
| newcomer | 22/22 |
| technician | 19/19 |
| facility manager | 16/16 |
| adversarial | 12/12 |
| wheelchair | 17/20 |
| analyst | 14/21 |
| multi-turn items (18) | 18/18 |

Every item that was run and failed is a missing tool, not a wrong answer. In all 10 failures the agent said it could not do it and did not invent a number or a room. The benchmark truths for `step_free_reachable_count` and `what_if_door` happen to be 0 on the proc building, so those two are weak evidence (the osm and swiss runs have non-trivial values for the other kinds).

### The 10 failures (all of them)

| # | User text | Agent reply gist | Cause |
|---|---|---|---|
| 1 | "How many doors are there in the building?" | "none of my tools return a door count" | no door tool |
| 2 | "How many doors are narrower than 1.0 m?" (analyst) | cannot, offers the wide-delivery check | no door width tool |
| 3 | "How many doors in the building are narrower than 1.0 m? My wheelchair needs 100 cm." (proc) | same | no door width tool |
| 4 | same, osm (0.9 / 1.0 m) | same | no door width tool |
| 5 | same, swiss (0.9 m) | same | no door width tool |
| 6 | "What is the smallest office on the floor 1?" | "my tools don't give the area of a single room" | no per-room area list |
| 7 | "Which is the second largest office on the floor 1?" | gives only the largest | `largest_room` returns one room |
| 8 | "What is the total area of floor 1?" | asks which room type | `floor_area_total` needs a type, nothing sums a floor |
| 9 | "How wide is Office 1.04?" | "my tools don't return room dimensions" | no dimension tool |
| 10 | "List all offices on floor 1." (17 offices) | listed 14 of 17, said the search returned 15 | `search_building` cap of 15 rows |

Observations that are not failures but matter on Sunday:
- "I'm at the main entrance" in a building with 4 entrances: the agent asks which one (correct and safe, but a first-day user does not know). Scored as pass (ask back).
- "Move the cnc mill to Server room, what changes?" with 3 mills: asks which one before any card. Correct.
- "Add a door ... how much shorter is the walk to the exit": the agent proposes the card and reports `what_if_door` = 0 rooms over 1 m, then says it cannot give the exact figure. Honest, but the Level 4 style question "if I change this, what will be the distance" wants metres.
- Parser (static check, free): 9 of 9 canonical benchmark sentences parse; no paraphrase does. Also rejected: missing "Finish with a line ..." tail, "End with", curly apostrophes, an extra sentence after the tail, "m2" for "m²" in `largest_room`, and the README's own `what_if_door` example, which tags only the second room with a floor (the real generated questions tag both). The fall-through to the model is graceful (22/22 above), so this costs time and money, not correctness.

### Spend

155 uncached scripts (151 scored runs, 4 pilot runs). Tokens from `agent_output/live_usage.jsonl`: 265k input, 46.5k output, 6.79M cache read, 107k cache write. At assumed Sonnet list prices ($3 / $15 per million in / out, cache read $0.30, cache write $3.75, not an invoice): about $3.94. API requests: roughly 300 to 440 (173 user turns plus about 264 tool calls, some bundled). Under the $4 cap, so the last 2 of 16 planned proc items and the "not measured" adversarial items were not run.

## 3. Ranked fixes (before the freeze Sunday 13:00)

Nothing below is applied. Minutes include running `scripts/check.sh` and the live check.

| Rank | Fix | Closes | Effort | Risk |
|---|---|---|---|---|
| 1 | Wire `make_query_tools(bm)` from `building_agent/query_tools.py` into `tools.make_tools` (one line, return list plus its 4 tools) and add one prompt sentence: "lists, smallest, second largest, whole-floor totals, door counts and widths, room sizes: use list_rooms, floor_summary, list_doors, room_size, never count search results". Shared file, so a fresh review agent reads the diff. | all 10 failures (7 intents: list over 15, smallest, second largest, total floor area, dimension, door count, door width) | 20 | low: read-only, tested, no change to existing tools; it adds 4 tool schemas to every prompt (small cost) |
| 2 | After wiring, rerun the catalogue items for those intents (`--ids`, about 10 scripts, about $0.30) plus `pytest -m live`, as `CLAUDE.md` requires for prompt or tool changes | confirms fix 1 | 15 | none |
| 3 | `door_effect` helper: walk length from a room to its nearest entrance before and after a new door (reuse `impact.distances` and `edit_ops.add_door_safe` on a copy), so "how much shorter" is a number in metres. New file plus test, then wire like fix 1. | Level 4 "if I change this, what will be the distance", facility manager what-if in metres | 30 | low |
| 4 | "main entrance" rule in `CONVERSATION_RULES`: if the person says main or front entrance, take the entrance into a lobby or the step-free one that is nearest to the destination, say which, and offer the others. Only ask when no entrance qualifies. | newcomer persona friction | 10 | low, prompt only; run the live suite |
| 5 | Parser tolerance in `question_parser.py` (own file, review not needed): optional floor tag on the first room of `what_if_door`, "End with" and a missing tail, curly apostrophes folded to ASCII, "m2". Only matters for speed and cost, the model already answers the paraphrases. | README example sentence, copy-paste punctuation | 15 | low, `tests/test_question_parser.py` covers it |
| 6 | Tie rule: "which floor has the most X" with equal counts should say the tie, and "how many toilets" should say rooms and fixtures (the model chose the fixture count 3 vs 1 room). One prompt sentence. | analyst ambiguity | 5 | low |

Not recommended before the freeze: a general "count anything" or SQL-like tool, and any change to how `search_building` truncates (shared by every flow).

## 4. Mapping notes (catalogue item to tool)

- 35 tools (starter and ours). Every catalogue item lists `expected_tools`; the live runner records the real calls per item in `agent_output/catalogue_results.jsonl`.
- Covered by the model plus existing tools without a gap: count of rooms by type on a floor (`floor_area_total.count` and `space_ids`), average (total / count), same-floor check (`find_space` returns the floor), straight line on one floor (`straight_line_3d` works within a floor), which is closer (two `find_route` calls), elevation (the model derived 3.5 m from `room_stacked` and `straight_line_3d`; luck, `elevation_m` is not in `building_overview`), counts of lifts, stairs, entrances and floors (`building_overview`).
- `building_overview`, `search_building`, `find_asset` cover well enough: counting assets by type and floor (the `matches` field is exact even when only 15 rows come back), where is X, what is on a floor by type name. They do not cover: anything that needs per-room area, door data or dimensions, or lists longer than 15.
- Intents with no tool at all: smallest, second largest and any ranking, total area of a whole floor, room width or depth, number of doors, doors narrower than a limit, list of doors in a room, capacity (not in the data: the right answer is to say so, and the agent does), door widths along a route.

## How to rerun

```
uv run python -m tests.catalogue.generate data/dev/proc-factory-dev-003 --write
uv run --env-file .env python -m tests.catalogue.runner data/dev/osm-way22744230 --sample 30 --max-usd 0.8
uv run --env-file .env python -m tests.catalogue.runner data/dev/swiss-1689 --ids WHL-10,CNT-14 --max-usd 0.1
```
Add `--rescore <results.jsonl>` to score earlier runs again from the cache at no cost. Live runs are never part of `scripts/check.sh`.
