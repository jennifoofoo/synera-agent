# Spec: Phase 2 (Warm-up, Abgabe, Voice, Level 4)

Status: ENTWURF. Wird "bestätigt", wenn Jennifer und Leonie zugestimmt haben.

## Warum
Das PDF und die README sagen: die 55 Punkte "Does it work" bestehen nicht nur aus den 145 Benchmark-Fragen. Dazu kommen automatische Checks auf unbekannten Gebäuden und Fragen für Level 1 bis 4 (richtige Antworten, gültige Routen, Routenlänge gegen die beste Route, aus Plänen gebaute Gebäude). 25 Punkte Interaction (Voice zählt). Stand heute:
- 8 Benchmark-Typen: Dev 72 von 72 (Stichprobe), Live-Skripte 18 von 18.
- Warm-up-Typen (`locate`, `count`, `route`, `route_step_free`, `route_with_closure`, `tour`): die **Tools allein** schaffen 369 von 369 in Dev (`uv run python -m starter_agent.evaluate data/dev --oracle`). Der **LLM-Agent** wurde dort nie getestet.
- Level 4 (Gebäude aus Plan bauen), Voice, Abgabe-Befehl: nicht vorhanden.

## Blöcke und Akzeptanzkriterien

### A. Warm-up und strukturierte Ausgabe (Jennifer)
- `building_agent/structured.py`: aus den aufgezeichneten Tool-Aufrufen eines Gesprächs `locate` (Raum- oder Item-ID), `route` (Knotenliste `space_path` und `length_m`), `tour`, `count` ziehen. Liefert dieselbe Struktur für CSV (mit `Answer:`-Zeile) und `answers.json`.
- Live-Auswertung des Agenten auf Warm-up-Fragen (Dev, `--limit` klein, Kosten pro Frage ausgeben), gegen `questions_basic.jsonl`. Ziel: mindestens so gut wie der Starter-Agent, Schwächen in `docs/eval-log.md`.
- Fertig: Offline-Tests der Extraktion auf allen 369 Dev-Antworten (aus Aufruf-Aufzeichnungen oder Orakel-Läufen), Live-Stichprobe dokumentiert.

### B. Abgabe (Leonie)
- Ein Befehl `run_benchmark <building_dir> <questions.json> <answers.json>` ohne manuelle Schritte, dokumentiert in `BENCHMARK.md`. Nimmt beide Formate (README-CSV und PDF-`answers.json`), sobald die Organisatoren das gültige nennen.
- `scripts/make_submission` für die Test-CSV (145 Fragen), `scripts/preflight.py <building_dir>`: prüft ein neues Gebäude in Sekunden (Polygone gültig, Schlüssel, alle Typen einmal ohne Absturz) und zeigt Auffälligkeiten.
- Fertig: Befehl läuft frisch aus einem leeren Klon, Test-CSV gültig, Tag `known-good`.

### C. Voice (Spike Jennifer, Oberfläche Leonie)
- Spike (30 Minuten): geht ElevenLabs mit eigenem LLM, oder Sprache rein im Browser und Sprache raus über ElevenLabs? Ergebnis in `docs/specs/voice-spike.md` mit Empfehlung. Kein Produktionscode im Spike.
- Danach: Mikrofon-Knopf und Sprachausgabe in der 2D-Seite (Leonie), Backend-Anbindung an `Session` (Jennifer).
- Fertig: gesprochene Frage bekommt gesprochene Antwort, Verständniskarte wird vorgelesen, Ja per Sprache bestätigt.

### D. Level 4: Gebäude aus Plan bauen (Spike Jennifer)
- Spike: Aus `floor_<n>_plain.png` per Claude-Vision ein `building.json` erzeugen und gegen das Original messen (Räume gefunden, Flächen, Türen, Treppen und Aufzüge). Ergebnis in `docs/specs/level4-spike.md`: Qualität, Dauer, Kosten, Empfehlung bauen oder lassen.
- Wenn bauen: Mutations-API mit Validierung, "neues Gebäude" im Chat, Plan-Upload in der 2D-Seite (Leonie).

### E. Demo und Technik (beide)
- Drehbuch "neue Technikerin, Tag 1" (90 Sekunden), Video, kurzer Technik-Text, Pitch (3 Minuten plus 1 Minute Fragen).

### F. Creativity (beide, erst nach A bis D)
- Höchstens zwei Dinge aus: Hausmeister-Stimme, Chaos-Button (Aufzug sperren, live umrouten), Landmarken-Politur. Entscheidung nach den Spikes, 30 Minuten gemeinsam.

## Fragen an die Organisatoren (eine Person fragt vor Ort)
Welches Ausgabeformat gilt am Sonntag (PDF-`answers.json` oder README-CSV)? Gibt es Locate und Route als Fragetypen und Level 3 mit mehreren Gebäuden? Code-Freeze-Zeit und Zeitlimit pro Frage? Wird Level 4 automatisch geprüft, und wie?

## Qualitätsregeln (unverändert)
Kein Merge ohne Test, `scripts/check.sh` grün (inklusive `ruff format --check`), geteilter Code mit frischem Review-Agenten, nichts auf Testgebäude hartcodiert, Kosten pro Lauf festhalten.
