# Spec: Core 2D (benchmark, agent, interaction basics, 2D view)

Status: bestätigt von Jennifer. Leonie liest sie beim ersten Start und meldet Einwände im Chat.

## Ziel
Ein Agent beantwortet Fragen zu beliebigen Gebäuden im Kit-Format korrekt und prüfbar. Jede Zahl und jede Route kommt aus deterministischem Python, das LLM wählt nur Tools und formuliert die Antwort. Darauf aufbauend ein Gespräch, das nachfragt und zeigt, was es verstanden hat, plus eine 2D-Ansicht der Route.

## Nicht-Ziele (kommen erst nach dem Ideation-Gate)
3D-Ansicht, Voice, Hausmeister-Charakter, Live-Mehrnutzer-Sync, Rush-Hour, Level-4-Builder aus Bildern.

## Akzeptanzkriterien (Core-Gate)
1. Alle Fragetypen aus der Tabelle unten sind gegen alle train/dev-Antworten grün (`step_free_reachable_count` optional).
2. Dev-Lauf des Agents (`--per-kind 3`) erreicht das Ziel von ca. 80 % (nach der Baseline nachschärfen).
3. Test-CSV für `data/test` ist gültig (UTF-8, Header, unter 5 MB), Tag `known-good`, `BENCHMARK.md`-Befehl läuft frisch.
4. Sechs Interaction-Skripte sind als Tests hinterlegt und bestehen (siehe unten).
5. Route ist auf dem Etagenplan in 2D sichtbar, Mutationen (Tür, Sperrung) wirken in 2D.
6. Abgabeformat geklärt (PDF `answers.json` oder README-CSV), Adapter eingeplant.

## Fragetypen, Signaturen, Rückgabe (der Vertrag)
Alle Funktionen sind reine Funktionen auf einer `BuildingMap` (`starter_agent/building_map.py`). Parameter heißen wie die `inputs` in train/dev. Rückgabe ist ein Dict mit genau diesen Schlüsseln.

| Typ (Test) | Owner | Signatur | Rückgabe |
|---|---|---|---|
| floor_area_total (33) | Leonie | `(bm, floor_id, room_type)` | `area_m2`, `count` |
| shared_walls_count (26) | Leonie | `(bm, start)` | `count`, `space_ids` |
| largest_room (21) | Leonie | `(bm, floor_id, room_type)` | `space_id`, `name`, `area_m2` |
| errand (20), fertig | Jennifer | `(bm, start, asset_type, floor_id, room_type)` | `length_m`, `via`, `target` |
| wide_delivery_count (18) | Leonie | `(bm, start, floor_id, min_width)` | `count`, `space_ids` |
| straight_line_3d (15) | Leonie | `(bm, first, second)` | `distance_m` |
| room_stacked (9) | Leonie | `(bm, start, direction)` | `space_id`, `name` |
| what_if_door (3) | Jennifer | `(bm, first, second, door_floor_id, floor_id)` | `count`, `space_ids` |
| step_free_reachable_count (0) | offen | `(bm, start, floor_id, closed)` | `count` |

Registrierung: Jede Query-Datei exportiert `KINDS = {"<kind>": Kind(fn=..., description="...")}` (`Kind` liegt in `building_agent/registry.py`). `tools.py` baut daraus automatisch die Claude-Tools. Wer einen Typ hinzufügt, ändert nur seine eigene Query-Datei und legt `tests/test_<kind>.py` an.

## Verifizierte Regeln
- **shared_walls_count:** Raum o auf derselben Etage zählt, wenn `len(start.exterior ∩ o.exterior.buffer(0.35)) >= 1.0` und weder `type` in {corridor, stair, lift, outdoor} noch `room_type` in {corridor, stairwell, lift}. Beide Filter nötig. (143/143 train/dev bestätigt.)
- **errand:** nächster Raum mit dem Asset nach Routenlänge (Treppen erlaubt, alle Fragen sagen das), dann zum größten Raum des Typs auf der Zieletage. Summe beider Wege. (93/93 train/dev bestätigt.)
- **wide_delivery_count:** Start ist der Raum, in den der Eingang führt. Keine Treppen und Stufen, Lifte erlaubt, jede Tür mindestens `min_width` (1,0 oder 1,1). Gezählt werden erreichbare Räume auf der Zieletage.
- **what_if_door:** Tür in der Mitte des gemeinsamen Wandsegments (nicht `nearest_points` wie im Starter), 0,9 m, stufenfrei, zwischen beliebigen Raumtypen. Vorher und nachher Weg zum nächsten Eingang für alle Räume der Zieletage, gezählt wird Verkürzung um mehr als 1 m.
- **room_stacked:** Raum auf der Etage darüber oder darunter mit der größten Überlappung. Nur für OSM und procedural, bei Swiss/ResPlan warnen statt raten.
- **Etagen im Text:** "ground floor" = 0, "Floor N" = N, "Basement N" = -N. Räume ohne Ref über den vollen Namen auflösen.

## Agent-Verhalten
- Testfragen enthalten nur Text. Der Agent liest Namen, Etagen und Mengen aus dem Satz und löst sie mit `find_space(name, floor)` auf. Mehrdeutig? Kandidaten mit Etage zurückgeben, nicht raten.
- Antwort endet mit **genau einer** `Answer:`-Zeile, bei Zählfragen genau eine Zahl, kein Bereich.
- Fakten nur aus Tool-Ergebnissen. Keine eigenen Berechnungen im Text.
- Tool-Schleife auf ca. 6 Runden begrenzt, Antworten pro Frage cachen, Retry mit Backoff.

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

## Dateibesitz
Leonie: `geometry.py`, `queries.py`. Jennifer: `queries_routing.py`, `tools.py`, `agent.py`, `directions.py`, `registry.py`. Geteilt und nur nach `git pull`: `CLAUDE.md`, `docs/STATUS.md`, `pyproject.toml`. Nie ändern: `starter_agent/`, `benchmark/`, `data/`.

## Qualitätsregeln
Kein Merge ohne Test. Keine Tests oder Logik auf Testgebäude hartcodiert (das Sonntagsgebäude ist neu). `scripts/check.sh` muss grün sein. Eine Verschlechterung des Dev-Scores wird nicht gemergt.

## Offene Punkte
Code-Freeze-Zeit, Abgabeformat (PDF vs. README), Zielwert fürs Dev-Gate nach der Baseline, API-Keys je Person.
