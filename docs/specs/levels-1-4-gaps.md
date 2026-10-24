# Plan: was für Level 1 bis 4 noch fehlt, und wie wir es schließen

Status: bestätigt (Jennifer, 2026-10-24). Stand `main` bei Erstellung: `16d7218` plus offene Agenten (`feat/placement`, `feat/level4-segment`).
Regeln wie überall: Spec zuerst, Tests als Vertrag, ein Modul pro Agent, Review vor Merge, `scripts/check.sh` grün, Langläufer im Hintergrund.

## Überblick: Lücken je Level
| Level | Lücke | Paket | Besitzer |
|---|---|---|---|
| 1 Locate | Funde aus dem Chat leuchten auf dem Plan nicht auf | W-L1a | Leonie |
| 1 | Suche und Mehrdeutigkeit mit echter Seite und Voice nie am Gerät getestet | W-L1b | Jennifer oder Leonie, Handtest mit Skript |
| 2 Route | Seite zeichnet Route mit altem Kit-Modell, verliert Zwischenstopps | W-L2a | Leonie (Vertrag von mir, siehe unten) |
| 2 | Gabelstapler und Bereichsregeln nur grob getestet, Frage an Synera offen | W-L2b | Jennifer (bedingt) |
| 2 | Bewertung "nur Synera-Modell" ungeklärt | Frage an Synera | wer vor Ort ist |
| 3 Scale | Mehrere Gebäude komplett fehlen | W-L3a bis W-L3d, Spec `level3-campus.md` | Jennifer (Agenten) und Leonie (Oberfläche) |
| 4 Build | Raumerkennung auf dichten Plänen (Swiss, OSM) | W-L4a Segmentierung (läuft) | Jennifer (Agent) |
| 4 | Gespräch kennt nach dem Speichern in der Seite das neue Gebäude nicht (`web/chat.py` hält die alte Karte) | W-L4b | Leonie (Vertrag von mir) |
| 4 | Upload, Vorschau, Maßstab-Eingabe in der Seite | W-L4c | Leonie |
| 4 | Mehrere Etagen nur offline getestet, echte Architektenpläne ungetestet | W-L4d | Jennifer (Agent, Live-Test) |
| 1 bis 4 | Edits per Sprache (Platzieren, Hinzufügen, Undo, "hier") | `feat/placement` (läuft) und Seite (Leonie) | beide |
| Abgabe | Format ungeklärt, voller Testlauf, `known-good` neu | W-A1 bis W-A3 | beide |

## Pakete im Einzelnen

### W-L1a Funde auf dem Plan (Leonie, klein)
- Das Feld `located` kommt schon in der Chat-Antwort (`structured.located_entries`). `sendChat` ruft danach `focusPoint(floor_id, position, assetIds)` auf, setzt `app.highlight`, schaltet die Etage um und hebt Assets hervor. Bei reinen Raumantworten `app.pickedSpaceId`.
- Akzeptanz: Test in `tests/test_web_static.py` (Funktion existiert und wird mit Funden aufgerufen), Browser-Handtest "Where is the 3D printer?".

### W-L1b Handtest Voice und Suche (Skript, 30 Minuten)
- Skript für Chrome mit Mikrofon: 10 Sätze (Fund, Mehrdeutigkeit "toilet", "second press", "east lift", Tippfehler). Ergebnis in `docs/eval-log.md`. Findet Fehler, die kein Offline-Test findet.

### W-L2a Seite zeigt die Route des Agenten (Leonie)
- `web/api.py` `route_view` und `current_route` rufen das Kit-Modell (`bm.route`) auf. Sie sollen `building_agent.routing.route` nutzen (gleiche `RouteResult`-Form), `via`-Stopps im `adopt_agent_route` behalten (`GuideState` oder `RouteResult` bekommt `via`) und die Route des Agenten nicht beim nächsten Zustandsabruf überschreiben.
- Akzeptanz: Test, dass Route der Seite und `give_directions` dieselbe Raumfolge haben (auch bei Touren), und dass `last_route` nicht zurückspringt.

### W-L2b Gabelstapler und Bereiche (Jennifer, bedingt)
- Nur wenn Synera bestätigt, dass es Fragen gibt: Tests auf allen proc-Fabriken (26), Vergleich `judge_route` gegen `routing`, Regeln für Bereiche (nur Start oder Ziel) mit 3 m Öffnungen prüfen, Ergebnis dokumentieren.

### W-L3a bis W-L3d Campus (Spec `docs/specs/level3-campus.md`)
- W-L3a Intern und Adapter, W-L3b Routing, W-L3c Werkzeuge und Gespräch (Jennifer, je ein Agent), W-L3d Oberfläche (Leonie).
- W-L3a startet jetzt (neues Modul, keine Konflikte).

### W-L4a Segmentierung (Agent läuft)
- Ziel: Swiss und OSM Raum-Recall ab 0,95 und, **im Zusammenspiel mit Markern und Türvorschlägen**, Anteil routbarer Paare klar über heute (Swiss 3 bis 6 %, OSM 34 %). Einbindung in `build_from_plan` nur bei messbarem Gewinn.

### W-L4b Gebäudewechsel in der Seite (Leonie)
- `ChatAdapter.ask` kennt `on_saved`: Der Agent ruft `on_saved(path)` nach dem Speichern. Die Seite ersetzt `session.map` und `ChatAdapter.map`, lädt das Gebäude neu und zeigt es an. Test: Speichern im Chat, danach liefert `/api/building` das neue Gebäude.

### W-L4c Upload und Vorschau (Leonie)
- Upload nach `agent_output/uploads/` (Servername, nur PNG und JPG, höchstens 10 MB), Maßstab-Eingabe, Vorschau (Polygone, Türen, rote Räume ohne Weg, Vorschläge), Knopf "Speichern" nur nach der Karte im Chat. Test mit den bestehenden Upload-Grenzen.

### W-L4d Level 4 auf Realität prüfen (Jennifer)
- Zwei bis drei Etagen eines Gebäudes live (Kosten unter $1), Prüfung der Verbindung der Treppen und Aufzüge, ein Plan im Kit-Stil ohne Möbel und einer mit Möbeln, ein "fremder" Stil (zum Beispiel Screenshot mit anderer Farbpalette) als Negativtest: erwartetes Ergebnis ist Rückfall auf die Modellauslesung mit Warnung.

### W-A1 bis W-A3 Abgabe
- W-A1: Voller Testlauf mit allen 145 Fragen und Prüfung der CSV (`building_agent.submission --check`), Anzahl der vom Parser beantworteten Fragen und der Modellfälle dokumentieren.
- W-A2: `docs/SYNERA_QUESTIONS.md` abarbeiten (Format, Level 3 und 4, Freeze, Gabelstapler, Himmelsrichtungen), danach einen Adapter-Punkt nachziehen.
- W-A3: Tag `known-good` neu setzen, wenn Level 3 und 4 Schritte gemerged und gemessen sind.

## Reihenfolge und Parallelisierung
1. Jetzt parallel: `feat/placement` (läuft), `feat/level4-segment` (läuft), W-L3a (neu), Dokumente für die Abgabe (Demo-Drehbuch, Technik-Text, englische Dateien), voller Testlauf, Fragenliste an Synera. Leonie: W-L1a, W-L2a, W-L4b, 3D-Prototyp und Voice-Test.
2. Danach: W-L3b, W-L3c, Einbindung Segmentierung, W-L4d, Review, Merge.
3. Zum Schluss: W-L3d und W-L4c (Oberfläche), Demo, Pitch, `known-good`, Freeze.

## Messbare Ziele
- Level 1: Funde im Browser sichtbar, Handtest 10 von 10.
- Level 2: Route in Seite und Agent identisch, Touren-Score ab 0,99 in 97 %, Warm-up 1,000 mittlerer Score.
- Level 3: Routen über 2 und 3 Gebäude gültig, Adapter-Äquivalenztest grün, Sweep ohne Absturz.
- Level 4: Sauberes Kit-Format unverändert (Recall 1,00), Swiss und OSM Raum-Recall ab 0,95, routbare Paare deutlich besser als heute, keine ungültigen Routen durch erfundene Eingänge.

## Risiken
- Das Campus-Format ist unsere Annahme. Der Adapter-Aufwand ist gering, solange die interne Struktur stimmt.
- Segmentierung und Marker funktionieren nur für Pläne im Kit-Stil. Rückfall auf das Modell bleibt.
- Die Seite ist der Engpass (viele Pakete bei Leonie). Mein Vorschlag: Ihre Reihenfolge W-L2a, W-L1a, W-L4b, dann Upload und 3D.

### Page contract (Auswahl und Zustand)
- `POST /api/chat` nimmt optional `context: {space_id, asset_id, point: [x, y], floor_id}` (Modellmeter, +y Norden). Alles optional, unbekannte Felder werden ignoriert. Der Server prüft gegen das Gebäude: unbekannte Ids, falsches Stockwerk, NaN/inf/riesige Zahlen, falsche Typen verwerfen die ganze Auswahl (Antwort bleibt 200, mit `selection_ignored: "<Grund>"`). Ein Punkt außerhalb des Raums wird allein verworfen. Die Auswahl gilt nur für diese eine Nachricht.
- Der Agent liest sie mit `get_selection`, es stehen keine Ids im Nachrichtentext.
- `state` (in jeder Antwort mit `state`) enthält zusätzlich, nur wenn nicht leer: `added_assets {id: {space_id, floor_id, position, name, rotation_deg, type, category}}`, `moved_assets {id: {space_id, floor_id, position, name, rotation_deg}}`, `removed_assets [ids]`, `removed_openings [ids]`, `widened_openings {id: width_m}`. Das ist der Stand seit dem Laden, nicht nur die Änderung seit der letzten Antwort: die Seite ersetzt ihr Asset- und Türbild damit. Nach Undo eines hinzugefügten Assets steht seine Id in `removed_assets`.
