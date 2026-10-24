# Spec: Level 3, mehrere Gebäude mit Wegen dazwischen (Campus)

Status: bestätigt (Jennifer, 2026-10-24, v2 mit Adapter-Schicht). Oberfläche (Schritt 4) wartet auf Leonies Zusage.
Grundlage: README "Scale: several floors, then several buildings, with stairs, lifts and walkways between them", Synera-Notiz zur Routenbewertung (Tür zu Tür, Treppe 2 m pro Meter, Aufzug 15 m plus 1 m pro Meter).

## Ziel
Zwei oder mehr Gebäude zu einem Campus verbinden und Fragen über Gebäudegrenzen hinweg beantworten: "Wie komme ich von Lab 0.12 im Forschungsbau zur Kantine im Hörsaalzentrum?", mit Weg durch Eingang, Verbindungsweg (Walkway, Brücke, Tunnel) und Zielgebäude, stufenfrei auf Wunsch, mit Sperrungen und Wegbeschreibung.

## Nicht-Ziele
Echte Geodaten oder Außenwegenetz, Wetter, Höhenunterschiede im Gelände, Fahrzeugverkehr. Es gibt dafür keine Daten, siehe unten.

## Was die Daten hergeben (geprüft über alle 280 Gebäude)
- **Nichts verbindet Gebäude.** `building.json` hat nur `id, name, source, source_ref, license, attribution, split, units`. Keine Koordinaten, keine Adresse, keine Campus-ID, kein Walkway. Jedes Gebäude hat ein eigenes lokales Koordinatensystem (Meter, x rechts, y oben).
- **Eingänge sind markiert:** Öffnungen, deren `space_ids` `"outside"` enthalten (`kind: entrance`, mit Position, Breite und `step_free`).
- Ein Campus muss also **erfunden** werden: welche Gebäude zusammengehören und wie sie verbunden sind. Das Format ist unsere Entscheidung und muss am Sonntag vorbereitet sein, falls Synera es prüft (offene Frage).

## Aufbau in drei Schichten
| Schicht | Inhalt |
|---|---|
| 1. Eingänge (Adapter) | Lesen von `campus.json`, einer Link-Tabelle (CSV), Geo-Koordinaten je Gebäude oder Angaben im Gespräch. Jeder Adapter liefert dieselbe interne Struktur. |
| 2. Intern (`Campus`) | Gebäude (ID, Pfad, optional Lage `origin` und Drehung), Links (Art, Eingang A, Eingang B, Länge, Breite, `step_free`, `closed`). |
| 3. Routing und Werkzeuge | Ein Campus-Graph auf `routing.py`, die Tools im Gespräch, die Anzeige. Sie kennen nur die interne Struktur. |

## Adapter (wie bei den Fragetypen: ein Modul pro Adapter)
- Ordner `building_agent/campus_adapters/`, je Datei ein `ADAPTER` mit `detect(path) -> bool` und `load(path) -> Campus`. Eine Registry findet sie automatisch, ein Test erzwingt Name und Signatur.
- `campus_json` (unser Format, Pflicht), `links_csv` (Spalten `building_a, entrance_a, building_b, entrance_b, kind, length_m`, tolerant bei Spaltennamen wie `from`, `to`, `distance`, Komma und Punkt, UTF-8 und Excel-Export), `geo` (Breite und Länge je Gebäude, Länge zwischen Eingängen aus Luftlinie mal 1,2, als Schätzung ausgewiesen), `conversation` (der Agent baut den Campus aus dem Gespräch, mit Karte und Ja).
- **Erkennung:** Der Loader probiert alle Adapter. Erkennt keiner die Datei, fragt der Agent, was sie enthält, zeigt eine Vorschau der Verbindungen und rät nicht.
- **Nach außen:** Antworten über Gebäudegrenzen nennen die Raumfolge (Raum-IDs sind pro Gebäude präfixiert und damit eindeutig). Ein Ausgabe-Adapter kann das Abgabeformat nachbilden, das Synera nennt.

## Format `campus.json` (neu, `building.json` bleibt unverändert)
```json
{
  "id": "campus-demo",
  "name": "Campus Garching",
  "buildings": [
    {"building_id": "proc-campus-dev-000", "path": "data/dev/proc-campus-dev-000", "origin": [0, 0], "rotation_deg": 0},
    {"building_id": "proc-factory-dev-003", "path": "data/dev/proc-factory-dev-003", "origin": [120, 40], "rotation_deg": 90}
  ],
  "links": [
    {"id": "L1", "kind": "walkway", "name": "Covered walkway",
     "from": {"building_id": "proc-campus-dev-000", "entrance": "<opening id>"},
     "to":   {"building_id": "proc-factory-dev-003", "entrance": "<opening id>"},
     "length_m": 85.0, "width_m": 2.5, "step_free": true, "closed": false}
  ]
}
```
- `kind`: `walkway` (Außenweg), `bridge`, `tunnel`. Brücken und Tunnel haben optional `level_delta` (Etagenunterschied, Aufzug oder Treppe zählen nach Synera-Regel).
- `origin` und `rotation_deg` sind nur für die Darstellung (3D, Karte). Das Routing braucht sie nicht.
- Länge: Wenn `length_m` fehlt, wird sie aus den `origin`-Positionen der Eingänge berechnet (Luftlinie mal 1,2 als Näherung, im Ergebnis ausgewiesen).
- Mehrere Links pro Gebäudepaar sind erlaubt, Eingänge ohne Link bleiben Ausgang ins Freie.

## Routing über Gebäudegrenzen
- Ein gemeinsamer Graph (`building_agent/campus.py`): jedes Gebäude behält seinen Graphen (Tür zu Tür, `routing.py`), `outside` wird je Gebäude zu einem eigenen Knoten `outside:<building_id>`, die Links verbinden die Eingangsknoten der zwei Gebäude mit Kosten `length_m`.
- Ohne Link zwischen zwei Gebäuden: Eingänge sind **nicht** frei verbunden. Die Antwort lautet "Es gibt keinen Weg zwischen A und B, sie sind nicht verbunden" und der Agent fragt, ob er sie verbinden soll (mit Karte und Ja).
- Eine Route ist die geordnete Liste von Räumen über beide Gebäude, mit den Eingängen und dem Link als Zwischenschritte (`element_path`). Länge nach Synera-Regel: Innenstrecken Tür zu Tür, Links mit `length_m`.
- `step_free` filtert Links (`step_free: false`), Eingänge und Connectors wie bisher. Sperrungen gelten für Links und Räume. Ein geschlossener Link trennt die Gebäude.
- Eindeutige Raum-IDs: sind bereits pro Gebäude präfixiert (`<building_id>-F0-S012`), also kollisionsfrei. Namen sind nur pro Gebäude eindeutig: Bei mehrdeutigen Namen fragt der Agent nach dem Gebäude.

## Werkzeuge im Agenten
| Tool | Zweck |
|---|---|
| `list_buildings()` | geladene Gebäude des Campus mit Etagen und Eingängen |
| `find_route` / `give_directions` | bekommen optional `building` für Start und Ziel (Namen werden über den Campus aufgelöst), Route über Gebäudegrenzen |
| `connect_buildings(first, second, kind, length_m?)` | schlägt einen Link vor (zwei Eingänge, Art, Länge), Karte und klares Ja wie bei Änderungen, speichert in `campus.json` |
| `what_changes` | gilt auch für Links ("Walkway gesperrt: welche Gebäude sind abgeschnitten?") |
Der Agent erwähnt Gebäudewechsel in der Wegbeschreibung ("Verlasse Gebäude A durch den Haupteingang, folge dem überdachten Weg, 85 m, betritt Gebäude B").

## Oberfläche (Leonie)
Gebäudewahl im Campus, Route über mehrere Gebäude mit Wechsel der Ansicht (später 3D: Gebäude nebeneinander nach `origin`). Optional: Karte mit Gebäuden als Kästen und den Links als Linien.

## Einbindung in Benchmark und Abgabe
Benchmark-Fragen betreffen ein Gebäude. `answer(building_dir, text)` bleibt unverändert. Ein Campus wird nur geladen, wenn eine `campus.json` neben den Gebäuden liegt oder der Agent einen Campus aufbaut. Kein Einfluss auf die 145 Testfragen.

## Akzeptanzkriterien
1. Jeder Adapter lädt eine passende Datei und `campus.py` prüft sie (unbekanntes Gebäude, Eingang nicht vorhanden, Link ohne Länge, doppelte IDs, Link innerhalb desselben Gebäudes, nicht verbundene Gebäude) und meldet Befunde in einfachen Sätzen, ohne Absturz.
2. Routen über zwei und drei Gebäude: gültig (jeder Schritt durch eine echte Tür, Treppe, Aufzug oder einen Link), Länge nach Synera-Regel, `step_free` und Sperrungen werden respektiert. Test mit einem künstlichen Campus aus zwei bis drei Dev-Gebäuden.
3. **Adapter-Test:** Dieselbe Campus-Beschreibung als `campus.json`, als CSV (mit drei Schreibweisen der Spalten) und als Geo-Datei ergibt dieselbe interne Struktur und dieselben Routen. Eine unbekannte Datei löst eine Rückfrage aus.
4. Innerhalb eines Gebäudes liefert der Campus-Router dieselbe Raumfolge wie `routing.route` (Regressionstest auf 300 Routen).
5. Der Agent fragt bei Mehrdeutigkeit nach dem Gebäude und schlägt fehlende Links vor, nie stillschweigend. Live-Skripte: "Von A nach B" über Gebäude, "stufenfrei", "Walkway gesperrt", "verbinde diese zwei Gebäude" mit Karte und Ja, Gegner-Varianten.
6. Sweep: Campus aus je zwei zufälligen Gebäuden über 40 Kombinationen, 5 Routen je Kombination, kein Absturz, alle Routen gültig.
7. `scripts/check.sh` bleibt ohne Key grün, bestehende Tests unverändert.

## Schritte (je ein Agent, eigenes Modul)
| Schritt | Inhalt | Besitzer |
|---|---|---|
| 1 Intern und Adapter | `campus.py` (Datenklassen, Prüfung, Befunde), Adapter-Registry, vier Adapter, Beispiel-Campus aus Dev-Gebäuden | Jennifer (Agent) |
| 2 Routing | Campus-Graph auf Basis von `routing.py`, Stufenfrei, Sperrungen, Touren über Gebäude, Wegbeschreibung | Jennifer (Agent) |
| 3 Werkzeuge und Gespräch | `list_buildings`, `connect_buildings` mit Karte und Ja, Prompt, Live-Skripte | Jennifer (Agent) |
| 4 Oberfläche | Gebäudewahl, Route über Gebäude, später 3D-Nachbarschaft | Leonie |

Aufwand: Schritte 1 bis 3 etwa 5 bis 6 Stunden, Oberfläche etwa 3 Stunden.

## Offene Fragen an Synera
Wie wird Level 3 geprüft: gibt die Jury mehrere Gebäude vor und welches Format haben die Verbindungen (Datei, Beschreibung, nichts)? Wie weit ist der Weg zwischen Eingängen zu rechnen? Gibt es Fragen mit "mehrere Gebäude" im Sonntagsbenchmark?

## Risiken
Das Format ist erfunden. Wenn Synera ein eigenes Format vorgibt, brauchen wir einen Adapter (ca. 1 Stunde, weil Gebäude und Links getrennt gehalten werden). Ohne Geo-Referenz sind Längen zwischen Gebäuden Annahmen und werden als solche genannt.

## Page API (Server, für Leonies Oberfläche)
Code: `web/campus_api.py`. Die Seite und der Chat-Agent teilen sich **einen** `CampusHolder`: schließt die Seite einen Link, sieht ihn `campus_route` im Chat sofort als gesperrt (und umgekehrt). Alle Antworten sind JSON, Fehler sind `400 {"error": "..."}` in einfachen Worten. Kein Pfad kommt je vom Browser: Campus-Schlüssel stammen aus einer Liste, die der Server baut, alle IDs werden gegen den geladenen Campus geprüft, falsche Typen (Zahl statt Text, `"true"` statt `true`) werden abgelehnt.

| Endpunkt | Zweck |
|---|---|
| `GET /api/campus[?key=dev/<id>]` | Zustand des Campus. `key` ist der Schlüssel des Gebäudes, das die Seite gerade zeigt (markiert `active`). |
| `POST /api/campus/load {key}` | Campus laden. `key` nur aus `available` (siehe unten). |
| `POST /api/campus/route {start, destination, start_building?, destination_building?, step_free?}` | Route über Gebäude. |
| `POST /api/campus/close {link_id, closed}` | Link sperren oder öffnen (direkte Seitenaktion wie `/api/close`). |

`connect_buildings` bleibt eine Chat-Aktion (Karte, klares Ja) und hat bewusst keinen Endpunkt.

**GET /api/campus**
- `loaded` (bool), `available: [{key, name}]` (ladbare Campusse: `example` = drei Dev-Gebäude im Speicher, dazu `campus*.json` und `*/campus.json` unter `--data` sowie Dateien im Ordner `campuses/`, Schlüssel `<ordner>:<datei>`).
- Wenn geladen: `key`, `name`, `findings: [{level, code, message, items}]`, `state` (wie `state_view.campus`).
- `buildings: [{id, name, map_loaded, page_key, active, floors: [{id, level, name, elevation_m, height_m}], floor_count, origin, rotation_deg, world_center, entrances: [{id, name, room, space_id, floor_id, position, world_position, step_free}]}]`. `page_key` ist der Schlüssel für `/api/building?key=` (null, wenn die Karte fehlt). `position` in Metern des Gebäudes, `world_position`, `origin` und `world_center` in Campus-Metern (null ohne Positionen, zum Beispiel bei einer reinen Link-Tabelle).
- `links: [{id, kind, name, from, to, level_delta, length_m, length_estimated, width_m, step_free, closed}]`, `from` und `to` sind `{building_id, entrance_id, point, world_point}`.

**POST /api/campus/load** liefert `{loaded, key, problems, findings, summary, campus}` (`campus` = die Antwort von GET). Fehlt ein Gebäudeordner, kommt kein Fehler, sondern ein Befund (`level: error`) und `map_loaded: false`; eine unlesbare Datei ist ein 400 mit Satz.

**POST /api/campus/route** liefert immer 200:
- Erfolg: `{ok: true, length_m, step_free, buildings: [ids], building_names, links_used: [ids], steps: [Sätze], legs, state}`.
- `legs` in Reihenfolge. Gebäude-Etappe: `{kind: "building", building_id, building_name, length_m, entry_entrance, exit_entrance, rooms: [{id, name, floor_id}], segments: [{floor_id, kind, points}], floor_changes, points, world_points}`. `points` sind alle Segmente hintereinander in Gebäude-Metern (Raummitte, Türen, Eingang), `world_points` dasselbe in Campus-Metern oder `null`. Link-Etappe: `{kind: "link", link_id, link_kind, name, length_m, step_free, level_delta, from, to}` mit Endpunkten wie oben.
- Kein Weg: `{ok: false, ambiguous: false, error: "<Satz>"}` (zum Beispiel "The bridge L2 is closed, so ... are cut off.").
- Mehrdeutiger Name: `{ok: false, ambiguous: true, error, candidates: [{building_id, building, space_id, name, floor}]}`; die Seite fragt nach dem Gebäude und ruft mit `start_building` oder `destination_building` erneut auf.
- Die Anfrage wird gemerkt und in `state_view.campus.route` bei jeder Änderung neu gerechnet.

**POST /api/campus/close** liefert `{link, effect: [Sätze], saved, state, route?}`. Nur die exakte Link-ID, `closed` muss ein echter Boolean sein. `route` ist die neu gerechnete gemerkte Route. Gespeichert wird nur in eine geladene `campus.json` (`saved: true`), nie in eine CSV- oder Geo-Datei.

**state_view.campus** (in jeder Antwort mit `state`, immer vorhanden): `{loaded, key, name, route, closed_links}`. `route` ist `null` oder `{request, ok, length_m, buildings, links_used}` beziehungsweise `{request, ok: false, error}`. Ohne geladenen Campus: `{loaded: false, key: null, name: null, route: null, closed_links: []}`.

Sperrungen: Für jedes Gebäude, das die Seite geöffnet hat, nutzt der Campus dieselbe Karte wie die Seitensitzung. Türen, Aufzüge und neue Türen aus `/api/close`, `/api/door` oder dem Chat zählen deshalb in `/api/campus/route` und im Chat-Werkzeug `campus_route` (ein Mechanismus: `CampusService.sync_maps`, vor jedem Campus-Zugriff). Ein Reset der Seite verwirft die Sperrungen auch im Campus. Gebäude, die die Seite noch nicht geöffnet hat, behalten ihre eigene Karte; dort kann es keine Sperrungen geben, weil sie nur über die Seite oder den Chat dieses Gebäudes entstehen. Links liegen im geteilten Campus und wirken überall.

`active` hängt am Aufruf: nur `GET /api/campus?key=<Gebäude>` markiert ein Gebäude, ohne `key` ist keines aktiv. Mehrere offene Seiten stören sich so nicht (der Server merkt sich kein "aktives Gebäude"). Die Seite schickt den Schlüssel bei jedem Aufruf mit.
