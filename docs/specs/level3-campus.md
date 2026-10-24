# Spec: Level 3, mehrere Gebäude mit Wegen dazwischen (Campus)

Status: ENTWURF, wartet auf Bestätigung von Jennifer (und Leonie für die Oberfläche).
Grundlage: README "Scale: several floors, then several buildings, with stairs, lifts and walkways between them", Synera-Notiz zur Routenbewertung (Tür zu Tür, Treppe 2 m pro Meter, Aufzug 15 m plus 1 m pro Meter).

## Ziel
Zwei oder mehr Gebäude zu einem Campus verbinden und Fragen über Gebäudegrenzen hinweg beantworten: "Wie komme ich von Lab 0.12 im Forschungsbau zur Kantine im Hörsaalzentrum?", mit Weg durch Eingang, Verbindungsweg (Walkway, Brücke, Tunnel) und Zielgebäude, stufenfrei auf Wunsch, mit Sperrungen und Wegbeschreibung.

## Nicht-Ziele
Echte Geodaten oder Außenwegenetz, Wetter, Höhenunterschiede im Gelände, Fahrzeugverkehr. Es gibt dafür keine Daten, siehe unten.

## Was die Daten hergeben (geprüft über alle 280 Gebäude)
- **Nichts verbindet Gebäude.** `building.json` hat nur `id, name, source, source_ref, license, attribution, split, units`. Keine Koordinaten, keine Adresse, keine Campus-ID, kein Walkway. Jedes Gebäude hat ein eigenes lokales Koordinatensystem (Meter, x rechts, y oben).
- **Eingänge sind markiert:** Öffnungen, deren `space_ids` `"outside"` enthalten (`kind: entrance`, mit Position, Breite und `step_free`).
- Ein Campus muss also **erfunden** werden: welche Gebäude zusammengehören und wie sie verbunden sind. Das Format ist unsere Entscheidung und muss am Sonntag vorbereitet sein, falls Synera es prüft (offene Frage).

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
1. `campus.py` lädt `campus.json`, prüft sie (unbekanntes Gebäude, Eingang nicht vorhanden, Link ohne Länge, doppelte IDs, Link innerhalb desselben Gebäudes, nicht verbundene Gebäude) und meldet Befunde in einfachen Sätzen, ohne Absturz.
2. Routen über zwei und drei Gebäude: gültig (jeder Schritt durch eine echte Tür, Treppe, Aufzug oder einen Link), Länge nach Synera-Regel, `step_free` und Sperrungen werden respektiert. Test mit einem künstlichen Campus aus zwei bis drei Dev-Gebäuden.
3. Innerhalb eines Gebäudes liefert der Campus-Router dieselbe Raumfolge wie `routing.route` (Regressionstest auf 300 Routen).
4. Der Agent fragt bei Mehrdeutigkeit nach dem Gebäude und schlägt fehlende Links vor, nie stillschweigend. Live-Skripte: "Von A nach B" über Gebäude, "stufenfrei", "Walkway gesperrt", "verbinde diese zwei Gebäude" mit Karte und Ja, Gegner-Varianten.
5. Sweep: Campus aus je zwei zufälligen Gebäuden über 40 Kombinationen, 5 Routen je Kombination, kein Absturz, alle Routen gültig.
6. `scripts/check.sh` bleibt ohne Key grün, bestehende Tests unverändert.

## Schritte (je ein Agent, eigenes Modul)
| Schritt | Inhalt | Besitzer |
|---|---|---|
| 1 Format und Laden | `campus.py` (Datenklassen, Laden, Prüfung, Befunde), Beispiel-Campus aus Dev-Gebäuden | Jennifer (Agent) |
| 2 Routing | Campus-Graph auf Basis von `routing.py`, Stufenfrei, Sperrungen, Touren über Gebäude, Wegbeschreibung | Jennifer (Agent) |
| 3 Werkzeuge und Gespräch | `list_buildings`, `connect_buildings` mit Karte und Ja, Prompt, Live-Skripte | Jennifer (Agent) |
| 4 Oberfläche | Gebäudewahl, Route über Gebäude, später 3D-Nachbarschaft | Leonie |

Aufwand: Schritte 1 bis 3 etwa 5 bis 6 Stunden, Oberfläche etwa 3 Stunden.

## Offene Fragen an Synera
Wie wird Level 3 geprüft: gibt die Jury mehrere Gebäude vor und welches Format haben die Verbindungen (Datei, Beschreibung, nichts)? Wie weit ist der Weg zwischen Eingängen zu rechnen? Gibt es Fragen mit "mehrere Gebäude" im Sonntagsbenchmark?

## Risiken
Das Format ist erfunden. Wenn Synera ein eigenes Format vorgibt, brauchen wir einen Adapter (ca. 1 Stunde, weil Gebäude und Links getrennt gehalten werden). Ohne Geo-Referenz sind Längen zwischen Gebäuden Annahmen und werden als solche genannt.
