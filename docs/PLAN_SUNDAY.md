# Plan Sonntag bis Code-Freeze 13:00 (Leonie und Jennifer, Stand Sonntag früh)

Quelle: Gespräch Leonie und Jennifer (Granola) plus `docs/IDEAS.md` Abschnitt 11. Für beide Agenten: vor jeder Arbeit `git pull`, eigene Branches, nicht dieselben Dateien parallel (siehe Tabelle "Dateien").

## Story in einem Satz
Ein Agent, der auf echter Gebäudegeometrie rechnet statt zu raten, freihändig für den Servicetechniker in der Halle. Das Wissen bleibt im Gebäude.

## Personas
- **Hauptpersona: Servicetechniker / Instandhalter** (aus Syneras Präsentation: "Hands full, phone in pocket"). Hände voll, Handschuhe, Lärm, will Sprache.
- **Nebenrolle: Facility Manager / Ingenieur.** Ändert das Gebäude ("was wäre, wenn hier eine Tür wäre?"), die Brücke zu Syneras Welt (Engineering, Geometrie).
- Nicht im Fokus: Rollstuhl, Logistik/Roboter, Mehrnutzer (nur Roadmap).

## Positionierung (Satz für den Pitch)
Fast niemand verbindet **Gespräch, Gebäudegeometrie und Wegführung**. Die Wartungssoftware weiß *was*, die Ortung weiß *wo ungefähr*, aber keiner sagt dir freihändig: "Links an der Presse vorbei, das Ersatzteil liegt auf dem Weg im Lager H-C2."
Synera-Bezug: Agenten bedienen verlässliche Werkzeuge (jeder Fakt aus Python, das LLM wählt und formuliert), Geometrie ernst genommen (Flächen, Wände, Etagen, Türbreiten, Was-wäre-wenn), Level 4 erkennt Raumtypen aus den Möbelsymbolen.

## Schmerzpunkte, die wir lösen
1. Suchen kostet Zeit (Teile, Werkzeug, Maschine).
2. Wissen steckt in Köpfen (der Erfahrene geht in Rente).
3. Dokumentation passiert nachträglich und schlecht.

## Video-Ablauf (2 Minuten, Details folgen in `docs/submission/DEMO_SCRIPT.md`)
1. **Techniker, Morgen:** "Hey Wanda, Prüfrunde: alle Feuerlöscher in Halle A." Kürzeste Runde, Wanda lotst freihändig, an jeder Station "Hey Wanda, erledigt". An einer Station: "Hey Wanda, merk dir: Halterung locker" plus Foto. (Gefilmt: echt mit dem Handy durch den Raum laufen.)
2. **Facility Manager:** "Was wäre, wenn wir hier eine Tür einbauen?" Betroffene Räume leuchten auf, "die Prüfrunde wird 40 m kürzer". "Ja, bau sie ein."
3. **Nächste Schicht:** Neuer Techniker läuft dieselbe Runde, durch die neue Tür. An der Station: "Hinweis von heute Morgen: Halterung locker" (mit Foto). "Hey Wanda, fertig": Protokoll erscheint.
4. Technik in einem Satz ("Fakten aus Code, Sprache aus dem LLM"), Roadmap mit 6G ("heute sagst du Wanda, wo du bist, mit 6G weiß es das Gebäude").

## Was wir bauen (Reihenfolge = Priorität)
| # | Feature | Server/Agent (Jennifer) | Seite `twin/` (Leonie) |
|---|---|---|---|
| 1 | **Prüfrunde** | Deterministisches Werkzeug: alle Geräte eines Typs in einem Bereich/Etage finden und in kürzester Reihenfolge als Tour (`via`) zurückgeben, Satz "14 Feuerlöscher, 230 m". | Runde als Route mit Stationen, Schrittliste zeigt "Station 3 von 14", "Hey Wanda, erledigt" springt zur nächsten Station (lokal). |
| 2 | **Was-wäre-wenn auf der Karte** | Heute rechnet der Agent die Wirkung (Anzahl Räume, Meter), gibt aber **keine Raum-IDs** an die Seite. Neu: betroffene Räume und Längen vorher/nachher in der Antwort (z. B. `located`/`state`), dazu Wirkung auf eine laufende Runde ("Runde 40 m kürzer"). | Betroffene Räume einfärben, neue Tür markieren, Satz mit Meter-Differenz. |
| 3 | **Ortsnotizen per Sprache + Foto** | Kleiner Speicher pro Gebäude: `POST /api/notes` (Text, optional Foto, Raum, Punkt, Etage, Zeit), `GET /api/notes?key=`; Fotos verkleinert, Typ- und Größengrenze; im Chat "was gibt's hier?". | "Hey Wanda, merk dir hier: ..." (lokal erkannt, kein LLM) speichert am Standort; Kamera-Knopf im Sheet; Pins auf der Karte; beim Lotsen in den Raum wird die Notiz vorgelesen und das Foto gezeigt. |
| 4 | **Einsatzprotokoll** | – (optional: ein Satz Zusammenfassung über den Agenten) | "Hey Wanda, fertig": Karte mit Ziel/Runde, Zeit, Meter, Stationen erledigt, Sperrungen, Notizen und Fotos; Kopieren/Teilen. |
| 5 | **Kurze Schritte zusammenfassen** | Wegbeschreibung: Schritte unter etwa 3 m mit dem nächsten Schritt zusammenlegen ("Walk about 1 m" mehrfach hintereinander wirkt kaputt), in `building_agent/directions.py`. | – |

Nicht bauen: Mehrnutzer, Roboter, Kollegen orten, Fehlercode-Datenbank, Apple Watch.

## Dateien (gegen Konflikte)
- Jennifers laufende Branches: `feat/twin-semantic-zoom` (`scene/mapZoom.ts`, `scene/Labels.tsx`, Raumkarte), `feat/twin-walk-wired` (`ui/Walk.tsx`, Marker). **Walk.tsx wird von 1, 3 und 4 auch gebraucht:** erst `feat/twin-walk-wired` mergen, dann bauen Leonies Sessions darauf; neue UI möglichst in eigenen Dateien (`ui/Round.tsx`, `ui/Notes.tsx`, `ui/Report.tsx`) und in `Walk.tsx` nur einhängen.
- Server: neue Dateien `web/notes_api.py`, Werkzeug in eigener Datei unter `building_agent/`.

## Level 4 (Hinweis von Leonie für Jennifer, nur Vorschläge)
Ursache laut `docs/eval-log.md`: jede Etage ein eigenes zugeschnittenes Bild ohne gemeinsamen Rahmen, Ausrichtung nur über Treppen/Aufzüge (room_stacked 0 → 3 von 7, Swiss ohne Treppen im SVG); Türen im SVG nur als Punkt (Schätzung der Breiten gemergt, aber nicht neu gemessen).
1. Neu messen nach dem Türbreiten-Merge (`scripts/level4_questions_eval.py`, ohne API-Kosten).
2. Etagen am Außenumriss ausrichten (geht auch ohne Treppen).
3. Türbreite aus der Wandlücke im Bild, Rückfall nach Türart.
4. Bei Unsicherheit nachfragen statt raten (Karte und Ja).

## Zeitplan
- Jetzt bis ca. 10:30: 1 bis 4 parallel bauen (Server und Seite getrennt), 5 nebenher.
- 10:30 bis 11:30: zusammenführen, volle Testsuite und Live-Suite, Handtest am Laptop (Chrome, "Hey Wanda").
- 11:30 bis 13:00: nur Bugfixes, Video drehen (2 Minuten), Technik-Text, Formular.
- Abgabe: `SUBMISSION/` liegt in `main` (Jennifer). Vor 13:00 prüfen, dass `answers.json` dem Bild von Synera entspricht.
