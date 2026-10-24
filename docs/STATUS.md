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
| shared_walls_count (26) | Leonie | gemergt | feat/q-shared_walls_count |
| largest_room (21) | Leonie | gemergt | feat/q-largest_room |
| wide_delivery_count (18) | Leonie | gemergt | feat/q-wide_delivery_count |
| room_stacked (9) | Leonie | gemergt | feat/q-room_stacked |
| what_if_door (3) | Leonie | gemergt | feat/q-what_if_door |
| step_free_reachable_count (0 im Test) | Jennifer | gemergt (2 Labels) | feat/hardening |

| Aufgabe | Wer | Status | Branch |
|---|---|---|---|
| Leitplanken: check.sh, ruff, Hooks | Jennifer | gemergt | chore/guardrails |
| tools.py (aus Registry), find_space, agent.py, Cache und Retry | Jennifer | gemergt | feat/agent-tools |
| Test "Text zu Parametern" (Haiku, alle gelabelten Fragen) | Jennifer | in Arbeit | feat/eval-params-full |
| Interaction: Landmarken, 3er-Schritte, Verständniskarte | Jennifer | gemergt | feat/guide-tools |
| Interaction: 6 Skripte als Tests (Live, mit LLM) | Jennifer | offen | |
| 2D-Web-Seite (Chat + Etagenplan mit Route) | Leonie | gemergt (Chat jetzt mit Session, siehe Blocker) | feat/web-2d |
| Abgabe-Tooling: make_submission, BENCHMARK.md, Format-Adapter | Leonie | offen | |
| Abgabeformat klären (PDF answers.json vs README-CSV) | | offen | |
| Demo-Video + Tech-Erklärung | beide | offen | |

## Blocker
- Jennifer an Leonie (`web/server.py`, `web/api.py`, deine Dateien): (1) Chat-Aufruf und Reset-Race: `session` und `chat` unter einem Lock zusammen holen, nach dem Aufruf prüfen, ob die Session noch dieselbe ist. (2) `adopt_agent_route` verliert `via`-Stopps und kann eine Seiten-Route überschreiben, wenn parallel geroutet wird. Ich habe in `web/chat.py` vier Zeilen geändert (Chat nutzt `building_agent.agent.Session`, Lock pro Gebäude, kein stilles Fallback mehr).
- Info Jennifer an Leonie: Der Sweep (`tests/test_sweep.py`, alle Typen auf allen 280 Gebäuden) fand einen Absturz in `kinds/what_if_door.py` (leere Wandlinie bei 0,35 bis 0,6 m Abstand, 33 Gebäude, 6 davon im Test). Ich habe eine Zeile ergänzt (`if not line.is_empty`) plus Regressionstest. Bitte kurz ansehen. Neue Kinds brauchen einen Generator in `tests/sweep_inputs.py`, sonst schlägt der Sweep an.
