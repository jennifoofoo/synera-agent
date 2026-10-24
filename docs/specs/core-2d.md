# Spec: Core 2D (benchmark, agent, interaction basics, 2D view)

Status: ENTWURF. Verteilung von Jennifer bestätigt (68 zu 77 Testfragen). Leonie liest die Spec beim ersten Start und meldet Einwände im Chat. Danach auf "bestätigt" setzen.

## Ziel
Ein Agent beantwortet Fragen zu beliebigen Gebäuden im Kit-Format korrekt und prüfbar. Jede Zahl und jede Route kommt aus deterministischem Python, das LLM wählt nur Tools und formuliert die Antwort. Darauf aufbauend ein Gespräch, das nachfragt und zeigt, was es verstanden hat, plus eine 2D-Ansicht der Route.

## Nicht-Ziele (kommen erst nach dem Ideation-Gate)
3D-Ansicht, Voice, Hausmeister-Charakter, Live-Mehrnutzer-Sync, Rush-Hour, Level-4-Builder aus Bildern. (Level 4 bleibt Pflichtkandidat fürs Gate, weil Level 1 bis 4 in die 55 Punkte zählen.)

## Akzeptanzkriterien (Core-Gate)
1. Alle Typen aus der Tabelle sind gegen alle train/dev-Antworten grün (`step_free_reachable_count` optional).
2. Dev-Lauf des Agents (`--per-kind 3`) erreicht ca. 80 % (Platzhalter, nach der Baseline nachschärfen).
3. Test-CSV für `data/test` gültig (UTF-8, Header, unter 5 MB), Tag `known-good`, `BENCHMARK.md`-Befehl läuft frisch.
4. Sechs Interaction-Skripte als Tests, bestanden.
5. Route in 2D sichtbar, Mutationen (Tür, Sperrung) wirken in 2D.
6. Abgabeformat geklärt (PDF `answers.json` oder README-CSV), Adapter eingeplant.

## Struktur: eine Datei pro Fragetyp
- `building_agent/kinds/<kind>.py` enthält die Funktion und `KIND = Kind(name, fn, description)` (siehe `building_agent/registry.py`). Dateiname und `KIND.name` sind gleich.
- `building_agent/registry.py` sammelt alle Dateien in `kinds/` automatisch. `tools.py` baut daraus die Claude-Tools. Einen Typ hinzufügen heißt: eine neue Datei plus `tests/test_<kind>.py` plus Zeile in `docs/STATUS.md`. Sonst nichts ändern.
- Gemeinsame Hilfen liegen in `building_agent/geometry.py` (`space_polygon`, `space_area`, `largest_space_id`). Neue Hilfen nur ergänzen, wenn zwei Typen sie brauchen.
- **Durchgesetzt durch `tests/test_registry.py`:** Jede Datei in `kinds/` exportiert `KIND` mit passendem Namen, erster Parameter heißt `bm`, Beschreibung nicht leer, Testdatei vorhanden, Typ steht in `docs/STATUS.md`.

## Fragetypen und Verteilung (145 Testfragen)
Parameter heißen wie die `inputs` in train/dev. Rückgabe ist ein Dict mit genau diesen Schlüsseln.

| Typ (Testfragen) | Wer | Signatur | Rückgabe |
|---|---|---|---|
| errand (20), fertig | Jennifer | `(bm, start, asset_type, floor_id, room_type)` | `length_m`, `via`, `target` |
| floor_area_total (33) | Jennifer | `(bm, floor_id, room_type)` | `area_m2`, `count` |
| straight_line_3d (15) | Jennifer | `(bm, first, second)` | `distance_m` |
| shared_walls_count (26) | Leonie | `(bm, start)` | `count`, `space_ids` |
| largest_room (21) | Leonie | `(bm, floor_id, room_type)` | `space_id`, `name`, `area_m2` |
| wide_delivery_count (18) | Leonie | `(bm, start, floor_id, min_width)` | `count`, `space_ids` |
| room_stacked (9) | Leonie | `(bm, start, direction)` | `space_id`, `name` |
| what_if_door (3) | Leonie | `(bm, first, second, door_floor_id, floor_id)` | `count`, `space_ids` |
| step_free_reachable_count (0) | offen | `(bm, start, floor_id, closed)` | `count` |

Summe: Jennifer 68, Leonie 77 (Spillover: Jennifer kann `room_stacked` übernehmen, wenn Leonie hängt).

## Verifizierte Regeln
- **shared_walls_count:** Raum o auf derselben Etage zählt, wenn `len(start.exterior ∩ o.exterior.buffer(0.35)) >= 1.0` und weder `type` in {corridor, stair, lift, outdoor} noch `room_type` in {corridor, stairwell, lift}. Beide Filter nötig. (143/143 train/dev bestätigt.)
- **errand:** nächster Raum mit dem Asset nach Routenlänge (Treppen erlaubt), dann zum größten Raum des Typs auf der Zieletage. Summe beider Wege. (93/93 bestätigt.)
- **Noch nicht gegen die Daten getestet (Annahmen, vor dem Bauen prüfen):**
  - wide_delivery_count: Start ist der Raum, in den der Eingang führt. Keine Treppen und Stufen, Lifte erlaubt, jede Tür mindestens `min_width` (1,0 oder 1,1). Gezählt werden erreichbare Räume auf der Zieletage.
  - what_if_door: Tür in der Mitte des gemeinsamen Wandsegments (nicht `nearest_points` wie im Starter), 0,9 m, stufenfrei. Vorher und nachher Weg zum nächsten Eingang für alle Räume der Zieletage, gezählt wird Verkürzung um mehr als 1 m.
  - room_stacked: Raum auf der Etage darüber oder darunter mit der größten Überlappung. Nur OSM und procedural, bei Swiss/ResPlan warnen statt raten.
- **Etagen im Text:** "ground floor" = 0, "Floor N" = N, "Basement N" = -N. Räume ohne Ref über den vollen Namen auflösen.

## Aufgaben pro Person (in dieser Reihenfolge)
**Leonie:** (1) Setup und `pytest` grün, Zeilen claimen. (2) `largest_room`, (3) `shared_walls_count`, (4) `wide_delivery_count` (Regel zuerst gegen Daten prüfen), (5) `room_stacked`, (6) `what_if_door`. Danach (7) 2D-Web-Seite, (8) Abgabe-Tooling (`make_submission`, `BENCHMARK.md`, Format-Adapter).
Je Aufgabe geliefert: `kinds/<kind>.py` mit `KIND`, `tests/test_<kind>.py` (alle train/dev-Fragen grün), `STATUS.md` aktualisiert, nach `main` gemergt.
Nicht anfassen: `tools.py`, `agent.py`, `directions.py`, `registry.py`, Dateien von Jennifers Typen.

**Jennifer:** (1) Leitplanken (`scripts/check.sh`, ruff, Hooks). (2) `floor_area_total`, (3) `straight_line_3d`. (4) `tools.py` (automatisch aus der Registry), `find_space`, `agent.py`, Baseline-Lauf. (5) Test "Text zu Parametern" (Parameter aus jedem train/dev-Fragetext lesen und mit `inputs` vergleichen). (6) Interaction: `directions.py`, sechs Skripte, Verständniskarte.
Nicht anfassen: Dateien von Leonies Typen, ihre 2D-Seite, ihr Abgabe-Tooling.

**Übergaben:** Leonies Typen erscheinen automatisch im Agent, sobald `kinds/<kind>.py` auf `main` liegt. Zeigt der Dev-Lauf einen schwachen Typ, steht das Ergebnis in `docs/eval-log.md`. Falsche Zahl heißt: Query reparieren (Besitzer des Typs). Falscher Parameter aus dem Text heißt: Agent reparieren (Jennifer).
**Blocker:** Wer an eine fremde Datei muss, ändert sie nicht, sondern schreibt unter "Blocker" in `docs/STATUS.md` eine Zeile und arbeitet an etwas anderem weiter.

## Agent-Verhalten
- Testfragen enthalten nur Text. Der Agent liest Namen, Etagen und Mengen aus dem Satz und löst sie mit `find_space(name, floor)` auf. Mehrdeutig: Kandidaten mit Etage zurückgeben, nicht raten.
- Antwort endet mit **genau einer** `Answer:`-Zeile, bei Zählfragen genau eine Zahl, kein Bereich, Einheiten ohne Ziffern.
- Fakten nur aus Tool-Ergebnissen. Tool-Schleife ca. 6 Runden, Antworten pro Frage cachen, Retry mit Backoff.
- Rückfragen bei Mehrdeutigkeit: im Benchmark-Modus aus (es gibt keinen Menschen), im Gespräch an.

## Interaction-Skripte (je ein Test)
1. Vage: "Wo gibt's Kaffee?" Auflösen auf canteen oder kitchen, nur bei mehreren Treffern fragen.
2. Falscher Raum: "Raum 2.30" existiert nicht. Ähnliche Treffer anbieten, nicht raten.
3. Meinungsänderung: erst Labor, dann "doch Toilette". Start behalten, neu routen.
4. Barrierefrei: step-free sofort setzen, Umweg nennen.
5. Hände voll: höchstens 3 Schritte, Landmarken, "nochmal" und "weiter".
6. Facility Manager: "Tür zwischen 2.03 und 2.04". Verständniskarte, auf Ja warten, ausführen, Folge nennen.
Mehrdeutige Namen wie "WC" immer mit Etage nachfragen.

## 2D-Ansicht
Zuerst `starter_agent/viewer.py` (Route je Etage als Bild), dann eine schlanke Web-Seite mit Chat und Etagenplan. Keine neuen Frameworks im Core.

## Qualitätsregeln
Kein Merge ohne Test. Nichts auf Testgebäude hartcodiert (das Sonntagsgebäude ist neu). `scripts/check.sh` grün (sobald vorhanden, bis dahin `uv run pytest`). Eine Verschlechterung des Dev-Scores wird nicht gemergt. Nie ändern: `starter_agent/`, `benchmark/`, `data/`.

## Offen
Code-Freeze-Zeit, Abgabeformat (PDF vs. README), Dev-Zielwert nach der Baseline, API-Keys je Person.
