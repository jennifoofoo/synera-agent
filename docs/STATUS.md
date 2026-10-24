# Status: who works on what

Claim before you start: edit the row, commit, push, then work. Set `gemergt` in the same commit as the merge.
Status: `offen`, `in Arbeit`, `Test grün`, `gemergt`. Branch pattern: `feat/q-<kind>`.
One file per kind: `building_agent/kinds/<kind>.py` (exports `KIND`) plus `tests/test_<kind>.py`. Only the owner touches a kind's file.
Blocked by someone else's file? Do not edit it. Add a line under "Blocker" below and work on something else.

Split by test weight (145 test questions): Jennifer 68, Leonie 77.

| Kind (Testfragen) | Wer | Status | Branch |
|---|---|---|---|
| errand (20) | Jennifer | gemergt | feat/q-errand |
| floor_area_total (33) | Jennifer | gemergt | feat/q-floor_area_total |
| straight_line_3d (15) | Jennifer | gemergt | feat/q-straight_line_3d |
| shared_walls_count (26) | Leonie | in Arbeit | feat/q-shared_walls_count |
| largest_room (21) | Leonie | in Arbeit | feat/q-largest_room |
| wide_delivery_count (18) | Leonie | in Arbeit | feat/q-wide_delivery_count |
| room_stacked (9) | Leonie | in Arbeit | feat/q-room_stacked |
| what_if_door (3) | Leonie | in Arbeit | feat/q-what_if_door |
| step_free_reachable_count (0 im Test) | | offen | |

| Aufgabe | Wer | Status | Branch |
|---|---|---|---|
| Leitplanken: check.sh, ruff, Hooks | Jennifer | gemergt | chore/guardrails |
| tools.py (aus Registry), find_space, agent.py, Baseline-Lauf | Jennifer | in Arbeit | feat/agent-tools |
| Test "Text zu Parametern" | Jennifer | offen | |
| Interaction: 6 Skripte, Verständniskarte, Landmarken (directions.py) | Jennifer | offen | |
| 2D-Web-Seite (Chat + Etagenplan mit Route) | Leonie | in Arbeit | feat/web-2d |
| Abgabe-Tooling: make_submission, BENCHMARK.md, Format-Adapter | Leonie | offen | |
| Abgabeformat klären (PDF answers.json vs README-CSV) | | offen | |
| Demo-Video + Tech-Erklärung | beide | offen | |

## Blocker
(none)
