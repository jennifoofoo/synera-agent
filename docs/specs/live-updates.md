# Spec: Live-Updates (Sperrungen mit Zeitraum, Dokumente hochladen, Sprache)

Status: ENTWURF, wartet auf Bestätigung von Jennifer (und Leonie für die Oberfläche).
Anlass: Jennifer, 24.10.2026: "Wir bräuchten immer Updates: Dokumente hochladen (zum Beispiel einen Umbau), Wartungszeiten automatisch auslesen, per Sprache 'Da ist jetzt eine Baustelle', 'der Durchgang ist von da bis da blockiert'. Den Zeitraum merkt man sich selbst und aktualisiert es dann selbst."
Grundlage: README Level 5 "Make things move", "Several users", Synera-Präsentation "A building that never stops changing / the map has to move with it", Idea Fridge 3b (Ereignisprotokoll).

## Ziel
Das Gebäude ändert sich über die Zeit, und der Agent kennt das. Eine Person (oder ein Dokument) meldet eine Änderung **mit Zeitraum**: "Aufzug 1 ist morgen von 8 bis 12 Uhr in Wartung", "Der Gang zwischen Halle A und Halle B ist vom 3. bis 10. November Baustelle", "Aisle 4 ist heute Nachmittag blockiert". Der Agent merkt sich den Zeitraum, **wendet die Sperrung automatisch zur richtigen Zeit an und hebt sie automatisch wieder auf**, plant Routen für den gefragten Zeitpunkt und warnt vor Sperrungen, die bald beginnen.

## Nicht-Ziele
Anbindung an echte Wartungs- oder Facility-Systeme (nur Dateien und Sprache), Benachrichtigungen per E-Mail oder Chat, Berechtigungsprüfung (wer darf melden), Wiederholungen mit komplexen Kalenderregeln über einfache Wochentage hinaus, Fassadenpläne.

## Szenarien (Tests laufen auf diesen)
1. **Sprache:** "Der Aufzug 1 ist morgen von 8 bis 12 Uhr in Wartung." Karte (Was habe ich verstanden: was, wo, wann, was ändert sich für die Routen), Ja, gespeichert.
2. **Abschnitt:** "Der Durchgang ist von Raum 0.12 bis Raum 0.18 blockiert, nächste Woche Montag bis Freitag." Der Abschnitt wird aus dem Weg zwischen den Räumen bestimmt (die dazwischen liegenden Räume und Türen), nicht geraten. Mehrdeutig: Rückfrage mit Optionen.
3. **Dokument:** Aufgehängter Aushang als Foto oder PDF ("Baustelle Flur Ost, 3. bis 14. Nov."), E-Mail-Text, Wartungsplan als CSV oder Kalenderdatei (`.ics`), Umbauplan. Der Agent liest Meldungen aus, zeigt jede mit dem Textausschnitt, aus dem sie stammt, und fragt vor dem Anlegen.
4. **Zeitpunkt-Routen:** "Wie komme ich morgen um 10 Uhr zum Labor?" nutzt den Stand von morgen 10 Uhr. "Wie komme ich jetzt?" nutzt jetzt.
5. **Automatik:** Beginnt oder endet ein Zeitraum, ändern sich Routen, Karten und "What changes?" ohne Zutun. Es gibt kein Hintergrundprogramm: Der wirksame Stand wird bei jeder Abfrage aus der Uhr berechnet (gespeichert wird nur die Liste der Zeiträume).
6. **Warnung:** "Deine Route führt durch Aisle 4. Die Sperrung beginnt in 20 Minuten." und Umweg anbieten.
7. **Überblick:** "Was ist diese Woche gesperrt?" gibt eine Liste und in der Seite eine Zeitleiste.
8. **Ändern und Zurücknehmen:** "Die Baustelle ist früher fertig" verkürzt den Zeitraum (Karte, Ja), Undo funktioniert, Löschen auch.

## Datenmodell (`building_agent/schedule.py`)
`ScheduledChange`: `id`, `kind` (`closure`, `maintenance`, `construction`, `blocked`), `targets` (Liste von Raum-, Öffnungs- oder Connector-IDs, auflösbar und geprüft), `label` (Klartext), `start`, `end` (zeitzonenbewusst, ISO 8601), `repeat` (`none`, `daily`, `weekdays`, `weekly`), `reason`, `source` (`voice`, `text`, `document:<name>`, `file`), `quote` (Ausschnitt aus Dokument oder Wortlaut), `confidence` (`exact` oder `needs_check`), `created_at`, `status` (`planned`, `active`, `done`, `cancelled`).
- Speicherort: eine Datei pro Gebäude (`agent_output/schedules/<building>.json`), atomar geschrieben, Backup beim Überschreiben. Nie auf Platte schreiben, was nur Gesundheitsdaten betrifft (hier nicht relevant).
- **Wirksamer Stand zu einem Zeitpunkt t:** `effective_closed(bm, schedule, t)` ist die Vereinigung der dauerhaften Sperrungen (`bm.closed`) und aller aktiven Zeiträume. Routing, `find_route`, `give_directions`, `campus_route`, `what_changes` und `reachable_for_me` bekommen einen optionalen Zeitpunkt (Standard: jetzt). Ohne Einträge verhält sich alles genau wie heute (Regressionstest).
- **Uhr:** Eine einzige Funktion `now()` ist austauschbar (Tests setzen die Zeit), Zeitzone wird einmal pro Gebäude festgelegt (Standard Europe/Berlin, im Gespräch änderbar). Mehrdeutige Zeitangaben ("nächste Woche Montag", "Mittag", "heute Abend") wertet der Agent in ein festes Datum aus und **zeigt es auf der Karte** (Mo, 3. November 2026, 08:00 bis 12:00), statt zu raten.

## Werkzeuge
| Tool | Zweck |
|---|---|
| `schedule_change(what, where, start, end, kind, repeat)` | Schlägt einen Zeitraum vor: Karte mit Ziel, Zeitraum, Wirkung auf Routen ("12 Räume länger erreichbar, 2 abgeschnitten") und Konflikten. Anlegen nur nach klarem Ja in der nächsten Nachricht, wie bei den anderen Änderungen. |
| `list_schedule(range)` | Zeigt Zeiträume (Standard: heute und die nächsten 14 Tage) |
| `change_schedule(id, ...)` und `cancel_schedule(id)` | Ändern und Löschen, mit Karte und Ja |
| `status_at(when)` | Was ist zu diesem Zeitpunkt gesperrt, was ändert sich gegenüber jetzt |
| `ingest_document(file)` | Liest Meldungen aus einem hochgeladenen Dokument (siehe unten), gibt Kandidaten mit Quelle zurück, legt nichts an |
| `confirm_schedule(items)` | Legt die vom Menschen bestätigten Kandidaten an (Guard wie bei `confirm_change`) |
Die bestehenden Werkzeuge bekommen `when`: `find_route(..., when=None)` und so weiter. Der Prompt sagt: Nennt die Person einen Zeitpunkt, immer `when` setzen. Gibt es in den nächsten 60 Minuten eine Sperrung auf der Route, nenne sie.

## Abschnitte und Ziele auflösen
- Ein Element: Name oder ID ("Aufzug 1", "Tür zwischen 0.03 und 0.04") wie `find_element`.
- Ein Durchgang "von A bis B": der kürzeste Weg zwischen den beiden Räumen (Routing ohne Sperrungen), die Räume und Türen dazwischen sind das Ziel. Gibt es mehrere gleich lange Wege oder mehr als 6 Räume dazwischen, fragt der Agent.
- Ein Bereich ("Halle A", "Etage 2 Ostflügel"): der benannte Raum oder die Räume einer Zone, nur nach Name, nie nach Himmelsrichtung ohne Bestätigung.
- Gänge ("Aisle 4") nur, wenn der Name eindeutig ist, sonst Rückfrage mit der Gangliste (Daten haben keine Nummern, siehe Idea Fridge 3a).

## Dokumente hochladen
- Formate: Bild (PNG, JPG), PDF, Textdatei und E-Mail-Text, CSV, Kalenderdatei `.ics`. Größe bis 10 MB, Speicherort fest `agent_output/uploads/`, Dateityp nach Inhalt prüfen.
- Auslesung: CSV und `.ics` **deterministisch** (feste Spalten und Kalenderfelder, tolerant bei Namen und Format), Bild, PDF und Text über **einen** Modellaufruf mit festem Werkzeugschema (`report_notices`: Liste mit `what`, `where_text`, `start_text`, `end_text`, `kind`, `quote`, `confidence`). Das Modell **führt nichts aus**, es gibt nur Kandidaten.
- **Dokumente sind Daten, keine Anweisungen:** Text im Dokument ("ignoriere alle Regeln", "sperre alles") wird nie befolgt. Es gibt nur Kandidaten. Nichts wird ohne Karte und Ja angelegt.
- Der Agent löst `where_text` und `start_text` selbst auf (deterministische Auflösung wie oben), zeigt zu jedem Kandidaten den Textausschnitt und markiert unsichere Auflösungen (`needs_check`).
- Umbau-Pläne: erkennt der Agent, dass das Dokument einen neuen Grundriss zeigt, schlägt er den Level-4-Weg vor (Plan hochladen, bauen, vergleichen) statt eine Sperrung anzulegen. Ein Vergleich "alt gegen neu" ist ein späterer Schritt.

## Oberfläche (Leonie, Phase 3)
Zeitleiste für Sperrungen (heute, Woche), Schieberegler "Stand zu Zeitpunkt t" (Plan zeigt die Sperrungen von t, Route für t), Upload für Dokumente (neben Plan-Upload), Kandidatenliste mit Textausschnitt und Häkchen, Banner "Beginnt in 20 Min: Aisle 4". Der Server liefert `state.schedule` (aktive und anstehende Einträge) und `state.now`. Aktualisierung per Abfrage alle 30 Sekunden (kein Server-Push nötig), Voice liest Warnungen vor.

## Akzeptanzkriterien
1. Ohne Einträge sind alle bestehenden Ergebnisse identisch (alle Tests, 300 Routen).
2. **Zeitlogik:** Mit austauschbarer Uhr: vor, während und nach einem Zeitraum jeweils der richtige wirksame Stand (Grenzen inklusive Beginn und Ende, Mitternacht, Sommerzeitwechsel, Zeitzone, wiederholte Einträge, überlappende Einträge, Eintrag in der Vergangenheit wird `done`, Ende vor Beginn wird abgelehnt).
3. **Routing:** Route für t berücksichtigt aktive Sperrungen und ignoriert künftige, `when` im Prompt, gleiche Länge wie die Route mit der entsprechenden festen Sperrung (Gleichheit mit `closed`-Routing, 100 Routen).
4. **Sprache und Text:** 20 Formulierungen (deutsch und englisch, relative und absolute Zeiten, "von … bis …", "bis auf Weiteres", "nur heute Nachmittag") werden korrekt zu Zeitraum und Ziel; Unklares erzeugt eine Rückfrage, keine Vermutung (Live-Skripte mit Gegner: Themenwechsel, Ja ohne Karte, falsches Datum, Ziel mehrdeutig).
5. **Abschnitte:** "von A bis B" wählt den kürzesten Weg, bei Mehrdeutigkeit Rückfrage; Test auf mindestens 20 echten Gebäuden.
6. **Dokumente:** CSV und `.ics` Beispiele (mindestens 5 je) werden vollständig gelesen; für Bild, PDF und Text ein Satz künstlicher Aushänge (10) mit bekannten Meldungen: Recall und Präzision der Auslesung werden gemessen und berichtet (nicht versprochen). Einschleusungsversuche im Dokument ("sperre alle Aufzüge") führen zu keinem Eintrag ohne Ja.
7. **Sicherheit und Robustheit:** Uploads nur in den festen Ordner, Typ nach Inhalt, Größenlimit, kaputte oder leere Dateien, riesige Dateien, Binärdaten, falsche Kodierung: kein Absturz, klare Meldung. Gespeicherte Datei bleibt bei Absturz konsistent (atomar).
8. `scripts/check.sh` bleibt ohne Key grün, Sweep über alle 280 Gebäude für Zeitraum-Sperrungen ohne Absturz.

## Schritte
| Schritt | Inhalt | Besitzer | Stunden |
|---|---|---|---|
| 1 Kern | `schedule.py` (Modell, Uhr, wirksamer Stand, Speichern), `when` in Routing und Werkzeugen, `schedule_change`, `list_schedule`, `change_schedule`, `cancel_schedule`, `status_at`, Prompt, Tests und Sweep | Jennifer (Agent) | 4 bis 5 |
| 2 Auflösung und Dokumente | Abschnitts- und Zeitauflösung, `ingest_document`, CSV und `.ics`, Bild, PDF und Text mit festem Werkzeugschema, Einschleusungstests, Messung an künstlichen Aushängen | Jennifer (Agent) | 3 bis 4 |
| 3 Live-Skripte | Gespräche für die Szenarien 1 bis 8 mit Gegnern | Jennifer (Agent) | 1 bis 2 |
| 4 Oberfläche | Zeitleiste, Schieberegler, Upload, Kandidatenliste, Banner | Leonie | 3 bis 4 |
Phase 1 (Schritte 1 und 3) allein ist in etwa 5 bis 6 Stunden lieferbar und deckt die Sprachsituation ab. Dokumente sind der zweite Block.

## Offene Fragen und Risiken
- "Wartezeiten" kann zweierlei heißen: Wartungszeiträume (hier gemeint) oder Wartezeiten vor Aufzügen und Türen (Wartezeit als Kostenanteil im Routing, dort sind 15 m pro Aufzug schon Synera-Regel). Wir gehen von Wartungszeiträumen aus.
- Zeitangaben sind fehleranfällig. Darum zeigt die Karte immer das ausgewertete Datum mit Wochentag.
- Das Modell kann sich beim Lesen von Dokumenten irren. Darum Kandidaten mit Textausschnitt und Bestätigung, nie automatisch.
- Wer darf melden? Keine Rechteprüfung (siehe Idea Fridge 4). Hinweis in der Karte: "gilt für alle, die dieses Gebäude abfragen".
- Mehrere Personen gleichzeitig: Änderungen sind pro Gebäude, nicht pro Person. Für gleichzeitige Nutzung Zustand und Sperren auf dem Server, mit Abfrage alle 30 Sekunden.
- Synera am Sonntag: Gibt es zeitabhängige Fragen oder Dokumente? Vermutlich nein, daher als Creativity-Extra und für den Alltag.
