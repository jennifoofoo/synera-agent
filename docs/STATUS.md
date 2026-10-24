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

Phase 2 (siehe `docs/specs/phase-2.md`). Reihenfolge nach Punkten: A und B zuerst, C und D als Spikes parallel.

| Aufgabe | Wer | Status | Branch |
|---|---|---|---|
| Leitplanken, tools.py, find_space, agent.py, Cache, Session, Härtung, Sweep, Format | Jennifer | gemergt | |
| Interaction: Landmarken, 3er-Schritte, Verständniskarte, 6 Skripte plus Gegner-Varianten (live) | Jennifer | gemergt | |
| Test "Text zu Parametern" (Haiku, alle gelabelten und 145 Testfragen) | Jennifer | gemergt | |
| A. Warm-up: `structured.py`, `scripts/eval_warmup.py`, `assume_closed` (Live Dev: 18 von 18 gemischt, Sperrungen 26 von 29, Tools allein 369 von 369) | Jennifer | gemergt | feat/warmup |
| C. Voice-Spike (Ergebnis `docs/specs/voice-spike.md`: Browser-STT plus ElevenLabs-TTS, ca. 1,8 h) | Jennifer | gemergt | spike/voice |
| D. Level-4-Spike (Ergebnis `docs/specs/level4-spike.md`: geführter Ablauf, Maßstab vom Nutzer, ca. 8 bis 10 h für Einzeletage) | Jennifer | fertig, Branch spike/level4 | spike/level4 |
| Testlauf auf `data/test` (3 pro Typ), `docs/eval-log.md`, Tool-Schleife 20 auf 8 Runden | Jennifer | offen | |
| 2D-Web-Seite (Chat, Etagenplan, Route, Sperren, Türen) | Leonie | gemergt (Chat mit Session, siehe Blocker) | feat/web-2d |
| B. Abgabe: `run_benchmark <building_dir> <questions.json> <answers.json>`, `BENCHMARK.md`, `make_submission`, Format-Adapter (nutzt `structured.py`), Test-CSV, Tag `known-good` | Leonie | in Arbeit (`building_agent/submission.py`: alle Frageformate, CSV + answers.json, Prüfung wie Jury; structured.py fehlt noch) | main |
| B. `scripts/preflight.py <building_dir>`: neues Gebäude in Sekunden prüfen (Polygone, Schlüssel, alle Typen einmal) | Leonie | offen | |
| 2D-Seite: Route animieren, Blocker bei `web/server.py` und `web/api.py` beheben | Leonie | offen | |
| C. Voice-Oberfläche in der Seite (Mikrofon, Sprachausgabe), nach dem Spike | Leonie | offen (wartet auf Spike) | |
| D. Plan-Upload in der Seite, nach dem Level-4-Spike | Leonie | offen (wartet auf Spike) | |
| Fragen an Synera vor Ort: Format, Locate/Route, Level 3 mehrere Gebäude, Freeze, Zeitlimit | wer vor Ort ist | offen | |
| G. Routen-Modell: Raumfolge mit Tür-zu-Tür-Distanz und Synera-Kosten (Spike: 92,4 % auf 99,6 % volle Punkte), Kit-Modell für errand und what_if_door behalten, siehe `docs/specs/route-metric-spike.md` | Jennifer | gemergt-bereit | feat/route-model |
| E. Demo-Video, Technik-Text, Pitch (3 Minuten plus 1 Minute Fragen) | beide | offen | |
| F. Creativity (höchstens zwei Dinge, Entscheidung nach den Spikes) | beide | offen | |

## Blocker
- Jennifer an Leonie (`web/server.py`, `web/api.py`, deine Dateien): (1) Chat-Aufruf und Reset-Race: `session` und `chat` unter einem Lock zusammen holen, nach dem Aufruf prüfen, ob die Session noch dieselbe ist. (2) `adopt_agent_route` verliert `via`-Stopps und kann eine Seiten-Route überschreiben, wenn parallel geroutet wird. Ich habe in `web/chat.py` vier Zeilen geändert (Chat nutzt `building_agent.agent.Session`, Lock pro Gebäude, kein stilles Fallback mehr).
- Info Jennifer an Leonie: Der Sweep (`tests/test_sweep.py`, alle Typen auf allen 280 Gebäuden) fand einen Absturz in `kinds/what_if_door.py` (leere Wandlinie bei 0,35 bis 0,6 m Abstand, 33 Gebäude, 6 davon im Test). Ich habe eine Zeile ergänzt (`if not line.is_empty`) plus Regressionstest. Bitte kurz ansehen. Neue Kinds brauchen einen Generator in `tests/sweep_inputs.py`, sonst schlägt der Sweep an.
