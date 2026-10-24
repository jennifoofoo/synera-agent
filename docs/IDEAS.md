# Idea fridge

Ideen, die wir geparkt haben. Nichts hier ist beschlossen oder gebaut. Neue Ideen unten anhängen, Status pflegen (`geparkt`, `in Prüfung`, `gebaut`, `verworfen`).

## 1. Accessibility-Modus ("Profil wählen und alles passt sich an")
Status: geparkt (Idee von Jennifer, 24.10.2026). Passt zu Level 5 im README ("Accessibility: wider doors, step-free and quiet routes") und zur Rubrik "Wheelchair user: step-free and wide doors, every time, without asking twice".

### Idee
Eine Person wählt zu Beginn ein Profil (oder beschreibt es im Gespräch). Danach gelten die Regeln für Routen, Wegbeschreibung, Antworten und die Oberfläche automatisch, ohne dass sie jedes Mal danach fragen muss.

### Profile und was sie ändern
| Profil | Routing | Wegbeschreibung und Antworten | Oberfläche |
|---|---|---|---|
| Rollstuhl | nur stufenfreie Wege, Türen mindestens 0,9 m (wählbar 1,0 oder 1,1 m für breite Rollstühle), Aufzüge ja, Treppen nie, Eingänge nur stufenfrei | nennt Umwege ehrlich, sagt "kein Weg" statt zu raten | Zielliste zeigt nur erreichbare Räume |
| Eingeschränkt gehfähig (Krücken, Rollator, Erschöpfung) | wenige Treppen, kürzeste Gesamtstrecke zählt mehr als Treppe gegen Aufzug, Aufzug bevorzugt | Pausenpunkte ("hier ist eine Bank") alle X Meter, kurze Schritte | |
| Sensorisch empfindlich (Autismus, Reizüberflutung) | leise und ruhige Wege: Hallen, Produktionszonen, Kantinen, Räume mit lauten Maschinen meiden oder nur durchqueren, wenn es keinen anderen Weg gibt | sagt vorher, was kommt ("Du kommst an der Kantine vorbei, es kann laut sein"), wenige Wendungen | ruhige Farben, keine Bewegungseffekte |
| Epilepsie, Photosensitivität | gleich wie Standard (Licht ist nicht in den Daten) | keine Hinweise auf blinkende Dinge als Orientierung | **keine blinkenden oder pulsierenden Animationen**, Route statisch statt animiert, `prefers-reduced-motion` respektieren, nichts über 3 Mal pro Sekunde |
| Sehbehinderung, blind | wie Standard, Wege mit klaren Führungslinien (Flure) bevorzugt | Sprache zuerst, Tastorientierung ("Wand links"), Abstände in Schritten und Metern, keine Farbwörter | hoher Kontrast, große Schrift, Screenreader-Beschriftungen |
| Hörbehinderung | wie Standard | nur Text und Bild, keine Sprachausgabe als einziger Weg | Untertitel für Sprache |
| Kognitiv (Demenz, Lernschwierigkeit) | wenige Abbiegungen, bekannte Orientierungspunkte, einfache Wege | sehr kurze Sätze, immer nur ein Schritt, wiederholen auf Wunsch, bestätigen ("Bist du angekommen?") | |

### Was die Daten hergeben (geprüft im README und in den Datenfeldern)
- **Ja:** Stufen (`step_free`), Türbreiten (`width_m`), Aufzüge und Treppen, Raumtypen (Produktionszone, Kantine, Serverraum, Lager), Maschinen als Lärmquellen (Kategorie `machine`), Bänke und Sitzgelegenheiten (Asset-Typ `bench`, `sofa`, `chair`) als Pausenpunkte.
- **Nein:** Lautstärke, Beleuchtung, Menschenmenge, Bodenbelag, Rampen als eigener Typ. "Leise" ist also ein **Näherungswert** aus Raumtyp und Maschinen, kein Messwert. Das sagen wir ehrlich.
- **Wichtig:** Türbreiten von Aufzügen und Treppenhäusern sind in den Daten Modellwerte (Procedural: 0,9 bis 1,6 m). Echte Wendekreise für Rollstühle sind nicht modelliert.

### Technische Skizze
- Ein `AccessProfile` (Datenklasse) mit Feldern: `step_free`, `min_door_width_m`, `avoid_room_types`, `avoid_machines`, `max_stairs`, `rest_stop_every_m`, `reduce_motion`, `voice_first`, `short_steps`.
- Das Routenmodell (`building_agent/routing.py`) bekommt Filter und Zuschläge: Kanten sperren (Breite, Stufen), Strafaufschläge für laute Räume. Das geht im bestehenden Dijkstra, weil dort schon `step_free` und Sperrungen laufen.
- Der Agent speichert das Profil im Gespräch (`GuideState`), setzt es beim ersten Hinweis ("ich sitze im Rollstuhl") und fragt nur einmal nach Details (Breite des Rollstuhls). Es gilt für `give_directions`, `find_route`, `find_asset` (zeigt nur erreichbare Ziele) und `what_changes`.
- Wegbeschreibung (`directions.py`): Pausenpunkte, kürzere Schritte, Vorwarnungen für laute Bereiche.
- Oberfläche (Leonie): Profilwähler, `prefers-reduced-motion`, Kontrast, Schriftgröße, Stopp-Knopf für Animation, statischer Routenmodus.
- Zusatzfrage-Stil: "Ich bin leicht überreizt" oder "ich kann nicht lange stehen" soll ohne Menü zum passenden Profil führen (Modell wählt, zeigt Karte, Ja-Schutz wie bei Änderungen).

### Aufwand (grobe Schätzung)
| Teil | Stunden |
|---|---|
| Profile und Routing-Filter (Rollstuhl, gehbehindert, leise) | 3 bis 4 |
| Wegbeschreibung und Antworten anpassen, Pausenpunkte | 2 |
| Gesprächsfluss und Prompt, Live-Tests mit Profilen | 2 |
| Oberfläche (Profil, reduzierte Bewegung, Kontrast) | 3 |
| Zusammen | etwa 10 bis 11 |
Ein **Demo-Schnitt** ist in 3 bis 4 Stunden möglich: Rollstuhl-Profil mit Türbreite, gehbehindert mit Aufzug-Vorrang, leises Profil mit Raumtyp-Zuschlägen, plus reduzierte Bewegung in der Seite.

### Risiken und Haken
- Wir dürfen **nichts versprechen, was wir nicht messen** (zum Beispiel "reizarm" oder "sicher bei Epilepsie"). Formulierung immer: "ruhigere Route nach Raumtyp, keine Messung".
- Profile sind Annahmen. Die Person kann sie jederzeit ändern, und der Agent fragt, statt zu raten.
- Gesundheitsdaten sind sensibel: das Profil nur im Gespräch halten, nicht speichern oder loggen.
- Überschneidung mit Creativity: Es ist eine der Level-5-Optionen ("Accessibility: wider doors, step-free and quiet routes"). Wir sollten höchstens zwei Level-5-Ideen bauen. Konkurriert mit Hausmeister-Stimme und Chaos-Button.

### Entscheidung offen
Beim Ideation-Gate (höchstens zwei Extras): Accessibility-Modus gegen Hausmeister-Stimme gegen Chaos-Button. Meine Einschätzung: Accessibility hat den stärksten Bezug zur Rubrik und zu den Personas des README, ist mit unserem Routing am billigsten umzusetzen und hat die beste Demo-Geschichte (dieselbe Frage, drei Profile, drei Routen).

## 2. Das "Krasse": 3D-Gebäude und Walkthrough (Antwort auf die Konkurrenz)
Status: geparkt (Idee von Jennifer, 24.10.2026). Andere Teams zeigen 3D-Gebäude, oft mit 2D-Minimap in der Ecke und einem Gefühl, als liefe man durch das Haus. Wir sollten uns davon absetzen, nicht nur nachziehen.

### Was die Daten für 3D hergeben (geprüft im README)
- Polygone pro Raum (Grundriss), Etagenhöhe (`height_m`) und Höhe über Null (`elevation_m`): daraus lassen sich Räume als Quader (extrudierte Polygone) bauen.
- Türen mit Position und Breite, Treppen und Aufzüge mit Stop-Räumen, Assets mit Position und Maßen (`footprint` Breite, Tiefe, Drehung): Möbel und Maschinen als Kisten, Maschinen farbig.
- Nicht vorhanden: Fassade, Fenster, Texturen, Dachformen, echte Raumhöhe pro Raum. Alles Fehlende wäre erfunden, also stilisiert (reduzierte Optik), nicht "realistisch". Realismus wie bei einem Spiel erreichen wir damit nicht, und wir sollten es nicht versprechen.

### Optionen (nach Wirkung pro Aufwand)
| Idee | Was die Jury sieht | Aufwand | Risiko |
|---|---|---|---|
| A. 3D-Ansicht mit three.js: Räume als Quader, Etagen gestapelt oder aufgeklappt, Route als leuchtende Linie, Assets als Kisten, 2D-Plan als Minimap in der Ecke | "Haben wir auch", saubere Basis | 6 bis 8 h | gering, Standard |
| B. **Begehbare Ego-Perspektive:** Kamera läuft die Route ab (Türen, Treppen, Aufzugsfahrt), dazu sprechen Voice und Wegbeschreibung synchron ("Jetzt links am CNC-Fräser vorbei") | "Man geht durch das Haus", direkter Bezug zu "directions a person can follow" | 4 bis 6 h zusätzlich zu A | mittel, Kameraführung durch Türen und Treppen |
| C. **Der Agent steuert die Ansicht:** "Zeig mir den Aufzug" fliegt die Kamera hin, "zeig die Etage ohne Decke", Funde leuchten auf, Sperrungen färben rot, "What changes?" markiert betroffene Räume farbig im 3D-Modell | Das unterscheidet uns: Konkurrenten zeigen, wir **sprechen und erklären** in der Ansicht | 3 bis 4 h zusätzlich | gering, nutzt vorhandene Tools |
| D. **Gebäude entsteht beim Hochladen:** Level 4 Plan hochgeladen, Räume wachsen live in 3D aus dem Grundriss, Türen erscheinen, Prüfung zeigt rote Räume ohne Weg direkt im Modell | Level 4 wird sichtbar und eindrucksvoll, sonst ist es nur ein JSON | 3 bis 4 h zusätzlich | gering |
| E. Auswirkungs-Ansicht: "Aufzug 1 gesperrt" zeigt im 3D-Modell, welche Räume jetzt abgeschnitten oder länger entfernt sind (Heatmap der Wegdifferenz) | Starke Demo für "React: What changes?" | 2 bis 3 h zusätzlich zu A und C | gering, Zahlen aus `impact.py` |
| F. Rush-Hour oder Crowd-Simulation (viele Punkte laufen, Engstellen werden rot) | Wow, aber ohne Bezug zur Aufgabe | 6 h | hoch, kein Nutzen für die Punkte |
| G. AR-Overlay mit Handy | Aufgabe nennt es, braucht Standortbestimmung (QR-Codes) | 10 h und mehr | hoch |

### Meine Einschätzung (Ideation-Gate)
- A allein ist Pflichtprogramm, wenn die anderen es auch haben, bringt aber kaum Differenzierung.
- Der Unterschied entsteht aus **A + B + C + E zusammen**: Eine 3D-Ansicht, durch die der Agent spricht und führt. Das ist unser Kern ("talk to your building") sichtbar gemacht und mit unseren echten Stärken verbunden (Verständniskarte, "What changes?", Barrierefreiheit).
- Mit **D** wird Level 4 in der Demo greifbar. Das ist vermutlich der beste Schnitt für Creativity und Demo-Punkte.
- **Zusammen mit dem Accessibility-Modus** (Idee 1) gibt es eine starke Geschichte: dieselbe Frage, Rollstuhl-Profil gegen Standard, zwei Routen im 3D-Modell, eine stufenfrei, eine über die Treppe.
- Höchstens zwei Level-5-Extras: Vorschlag **3D mit Agentensteuerung** (A, B, C, E) und **Accessibility-Modus**. Hausmeister-Stimme und Chaos-Button nur, wenn Zeit bleibt. Den Chaos-Button kann man ohne Aufwand in C einbauen ("Aufzug sperren" per Klick im 3D-Modell, Route berechnet sich live neu).

### Technische Skizze
- `web/static/` bekommt eine neue Datei `view3d.js` (three.js; **die Bibliothek lokal ins Repo legen**, nicht vom Netz laden, sonst scheitert die Demo ohne WLAN).
- Ein Endpunkt `GET /api/building3d?key=...` liefert Räume mit Polygon und Höhe, Türen, Connectors und Assets (vorhandene `building_view`-Daten reichen fast).
- Der Chat-Antwort wird ein optionales Feld `view` mitgegeben: `{"focus": [...ids], "camera": "..."}`. Der Agent hat dafür ein Tool `show_in_view(...)` (nur Anzeige, kein Rechnen).
- Für B: Kamera folgt der Knotenliste der Route (`space_path` plus Türpositionen), Auf- und Abfahrt bei Treppen und Aufzügen, Tempo einstellbar, Pause und Wiederholen per Stimme.
- Barrierefreiheit der Ansicht: reduzierte Bewegung respektieren, Kameraflug abschaltbar, Hochkontrast.

### Risiken
- Zeit: A bis E sind zusammen etwa 18 bis 24 Stunden. Wir müssen vorher festlegen, was **in der Demo wirklich vorkommt** (Drehbuch zuerst, dann bauen).
- Leistung bei großen Gebäuden (OSM mit 1600 Räumen und 5000 Assets): Assets nur bei Zoom, Etagen einzeln laden.
- Nicht kopieren: Wir bauen eigene Ansicht, ohne Code anderer Teams.
- Realismus nicht versprechen. Besser "klare, lesbare 3D-Darstellung, die der Agent erklärt".

### Entscheidung offen
Gemeinsam mit Leonie beim Gate: Wer baut die Oberfläche (Leonie), wer die Agentensteuerung (Jennifer)? Zuerst ein 90-Sekunden-Drehbuch schreiben, dann nur bauen, was darin vorkommt.

## 3. Fabrik-Werkzeuge in 3D (Manufacturing statt "schönes Modell")
Status: 3a und 3b **gesetzt** (Leonie, 24.10.2026), 3c geparkt. Gedanke: 3D nicht als Deko, sondern als Werkzeug für eine Entscheidung in der Fabrik. Passt zu Synera (Geometrie, "was passiert, wenn") und zu Level 5 "Make things move" und "Industrial logistics". Baut auf der 3D-Ansicht aus Idee 2 (A) auf.

### 3a. "Passt die neue Maschine rein?" (Einbring-Check), gesetzt
- Eingabe im Gespräch: "Wir bekommen eine CNC-Fräse, 2,5 × 1,5 × 2,8 m, für Halle 3."
- Der Block fährt in echter Größe vom Tor zur Zielhalle. Jede Tür, Öffnung und jeder Aufzug auf dem Weg wird grün oder rot (zu schmal, zu niedrig, nur gedreht). Ergebnis: Weg passt / passt nicht, mit dem Engpass.
- Abstellen in der Halle: Kollision mit vorhandenen Maschinen (`footprint`, Drehung) und Restbreite der Staplergassen (mindestens 3 m) werden geprüft und rot markiert.
- Daten: `width_m` der Öffnungen, Etagenhöhe `height_m`, Assets mit `footprint`, Stapler-Router (`judge_route.py`, `find_forklift_route`). Fehlt: Türhöhen, Aufzug-Innenmaße (Annahmen klar benennen).

### 3b. Sicherheits-Hotspots: Stapler und Menschen, gesetzt
- Fußwege und Staplerwege werden gleichzeitig berechnet (typische Wege: Eingang zu Arbeitsplätzen, Lager zu Produktion). Räume und Öffnungen, die beide oft nutzen, werden rot.
- Vorschlag des Agenten: "Fußweg über Gang H1B3 trennt die Ströme, kostet 12 m Umweg."
- Zusammen mit 3a: "Neue Maschine steht hier. Was ändert sich an den Staplerwegen und an den Kreuzungen?"
- Daten: beide Router vorhanden. Fehlt: echte Verkehrsmengen, also "oft" als Anzahl Routen zwischen typischen Paaren, kein Messwert.

### 3c. Spaghetti-Diagramm (Lean: Laufwege sichtbar machen), geparkt
- Ein Schichtablauf ("Teil holen, Prüflabor, Montage, Lager") wird als Linien gezeichnet, mit Metern pro Schicht.
- Der Agent probiert Varianten ("Werkzeugregal nach Halle 2") und zeigt die bessere: "minus 340 m pro Schicht".
- Daten: `errand`-Logik, nächster Raum mit Asset, Was-wäre-wenn. Fehlt: echte Abläufe und Häufigkeiten (Annahmen vom Nutzer erfragen).

### 3d. Störungs-Modus für den Instandhalter, geparkt
- Persona aus dem README: Servicetechniker, Hände voll, Handy in der Tasche, will Sprache.
- Per Sprache: "Presse 2 steht still." Der Agent findet die Maschine, die 3D-Ansicht fliegt hin, die Maschine blinkt rot.
- Eine Rückfrage: "Brauchst du Werkzeug?" Wenn ja, nächstes passendes Werkzeug oder Ersatzteil suchen und die Route darüber legen (erst holen, dann zur Maschine, wie `errand`).
- An der Maschine die Zugangsseite markieren (die Seite, die nicht an Wand oder Nachbarmaschine steht, aus `footprint` und Nachbarn).
- Wegbeschreibung per Sprache in kurzen Schritten mit Landmarken.
- Unterschied zur normalen Route: Der Agent denkt den Auftrag mit (holen, wo anpacken), nicht nur den Weg. Näher an "üblich" als 3a und 3b.

## 4. Funde aus der Synera-Präsentation ("Industrial Agents Hackathon.pdf")
Status: geparkt (24.10.2026). Abgleich der Präsentation mit unserem Stand. Alles hier ist nicht beschlossen. Details zum Stand der Level stehen in `docs/LEVELS_STATUS.md`.

### 3a. Gänge und Docks auflösen ("Aisle 4 is blocked. Fastest route to dock B?")
- Befund: Gänge heißen in den Daten nur "Main aisle H-C1" (112 Räume, keine Nummer 4). Räume mit "Dock" im Namen gibt es nicht. "Aisle 4" und "dock B" lassen sich nicht eindeutig auflösen.
- Idee: Der Agent listet die Gänge der Halle auf und fragt, welchen die Person meint. "Dock B" wird auf Eingänge der Halle (Öffnungen mit 3 m oder mehr zum Außenbereich) oder auf Bereiche abgebildet, die der Person angeboten werden. Eine Zuordnung per Zähler ("aisle 4" gleich vierter Gang nach Name sortiert) nur als Vorschlag mit Bestätigung, wie bei "line 4".
- Frage an Synera: Wie heißen Gänge und Docks am Sonntag? Zählen Gabelstapler-Regeln wirklich?
- Aufwand: klein (1 bis 2 Stunden), Tests mit Fabrik-Gebäuden. Teil des Gabelstapler-Pakets W-L2b.

### 3b. Ereignisprotokoll und Zeit ("Where is the steel drum delivered yesterday?")
- Befund: Wir haben keinen Zeitverlauf. Es gibt `move_asset`, `add_asset` und Undo, aber keine Zeitstempel, keine Lieferungen und keine Abfrage "wo war X gestern". In den Daten gibt es kein Fass (nur Palettenregale und Hubwagen).
- Idee ("Make things move"): Ein Ereignisprotokoll `events.jsonl` pro Gebäude (Zeit, Art, Asset, von, nach, wer). Werkzeuge: `where_was(asset, when)`, `what_changed_since(when)`, `record_delivery(type, room)` (neues Asset mit Eingangszeit, Karte und Ja). Eine Zeitleiste in der Seite (Schieberegler "Stand von gestern").
- Auch gut für die Demo: "Der Hubwagen stand heute früh in Halle A, jetzt in Halle B".
- Aufwand: etwa 2 bis 3 Stunden ohne Seite, 2 Stunden Seite (Leonie). Kann auf dem Undo-Stapel und `moved_assets` aufbauen.

### 3c. Rollstuhl-Persona vollständig ("step-free and wide doors, every time, without asking twice")
- Befund: Stufenfrei ja. Türbreite und das Merken des Profils im Gespräch fehlen. Das ist ein direkter Punkt in ihrer Rubrik.
- Idee: Accessibility-Modus (siehe Idee 1 oben). Mindestumfang für den Score: Profil Rollstuhl mit wählbarer Türbreite (0,9, 1,0, 1,1 m), merkt sich das Profil für das ganze Gespräch, alle Routen, Wegbeschreibungen und Zielvorschläge halten es ein, Hinweis, wenn kein Weg existiert, Umweg ehrlich nennen. Die Bausteine existieren: `step_free`, `min_width` in `wide_delivery_count`, Filter im Routing.
- Empfehlung: Als erstes Extra bauen (billig, direkter Bezug zur Jury).

### 3d. Live-Update per Scan, AR auf dem Handy
- Befund: Die Präsentation nennt "Live updates from a scan" und "AR on the phone" unter "possible today". Wir haben nichts dafür geplant.
- Einschätzung: Hoher Aufwand, geringer Gewinn. Ein Scan-Update ließe sich als "Plan nachladen und Unterschiede zeigen" (Level-4-Pipeline plus Vergleich zweier Gebäude) vereinfachen. AR braucht Standortbestimmung (QR-Codes an Türen). Nur wenn Zeit bleibt.

### 3e. Darstellung und Mehrnutzer (Schlussfolie)
- Befund: Die Schlussfolie zeigt eine isometrische 3D-Etage über dem 2D-Plan, eine Spielkarte (Mario), eine Among-Us-Karte mit mehreren Figuren und eine Kartenroute (Tacto als Ziel). Das deutet auf Erwartungen an Darstellung (stilisierte, spielerische Karte) und mehrere Personen hin.
- Idee Mehrnutzer: Mehrere Personen sehen dasselbe Gebäude, jede Person hat eine Figur und eine Farbe, Änderungen eines Facility Managers erscheinen live bei allen (Server-Ereignisse per Polling oder Server-Sent Events). Passt zu "Several users" im README (Level 5) und zu 3b.
- Idee Spielkarte: eine optionale, stilisierte Ansicht (Pixel-Optik) als Gag für die Demo, nur wenn die 3D-Ansicht steht.
- Aufwand Mehrnutzer: 3 bis 4 Stunden (Server-Ereignisse, Figuren auf dem Plan). Risiko: Zeitaufwand ohne Punkte aus der Rubrik, außer unter Creativity.

### Reihenfolge-Empfehlung für das Ideation-Gate
1. Accessibility-Modus mit Türbreite (3c) und die Gabelstapler-Auflösung (3a).
2. 3D mit Agentensteuerung (Idee 2).
3. Ereignisprotokoll (3b), falls Make-things-move als Extra gewählt wird.
4. Mehrnutzer und Spielkarte (3e) nur, wenn noch Zeit bleibt. Scan und AR (3d) nicht.

## 5. Zutrittsrechte: "Wo darf ich überhaupt hin?" (Idee von Jennifer, 24.10.2026)
Status: geparkt. Passt zu den Personas (Facility Manager, Servicetechniker, neue Mitarbeitende) und ist im Alltag sehr realistisch: Nicht jeder darf überall hin.

### Idee
Die Person hat eine Rolle oder Berechtigungen (Besucher, Mitarbeitende, Servicetechniker, Facility Manager, Admin). Der Agent kennt, welche Räume und Türen eine Berechtigung brauchen, und sagt klar:
- "Du kommst da nicht hin. Der Serverraum 0.42 braucht Zutritt Stufe 3 (IT). Du hast Stufe 1. Frag bei der IT oder beim Empfang."
- "Dahin geht es nur mit Sicherheitsausrüstung (Helm, Schutzbrille). In der Produktionszone sind Besucher nicht erlaubt, nur mit Begleitung."
- "Es gibt einen anderen Weg zu deinem Ziel, der nur über Bereiche führt, die du betreten darfst."
- Routen führen **nie durch gesperrte Bereiche als Abkürzung**, auch wenn der Weg dann länger ist. Wenn es gar keinen erlaubten Weg gibt, sagt der Agent das und nennt, was fehlt.

### Wichtig: Die Daten enthalten keine Zutrittsrechte
Weder Türen noch Räume tragen Berechtigungen oder Schlösser (geprüft im README und in den Feldern der Öffnungen und Räume). Wir müssten die Regeln **selbst festlegen**:
- Ableiten aus Raumart als Standard (zum Beispiel `server_room`, `technical_room`, `warehouse_zone`, `production_zone`, `lab` brauchen mehr als `office` oder `corridor`).
- Oder eine Richtliniendatei `access_policy.json` pro Gebäude (Rollen, Zonen, Türen mit Kartenleser), wie beim Campus mit Adaptern (JSON, CSV, im Gespräch).
Wir sagen immer ehrlich: "Das ist eine Beispielregel, kein echtes Berechtigungssystem."

### Aufbau
- Datenmodell: `Role` (Name, Stufe, Zonen), `AccessPolicy` (Räume und Türen mit `requires` (Stufe, Rolle, Begleitung, Ausrüstung), Standardregeln nach Raumart).
- Person: Rolle wird im Gespräch genannt ("ich bin Servicetechniker") oder in der Seite gewählt. **Es ist keine Authentifizierung**: Der Agent kann nicht prüfen, wer jemand ist, und darf sich nicht als Sicherheitsfunktion ausgeben. Es ist eine Orientierungshilfe.
- Routing: Zugangsregeln als Kanten- und Raumfilter im bestehenden Dijkstra (wie `step_free`), mit Grund pro Ausschluss ("Tür 0.12 braucht Karte Stufe 2").
- Werkzeuge: `set_role(role)`, `can_i_go(destination)`, `why_not(destination)` (listet Hürden und Abhilfe), `route` berücksichtigt die Rolle automatisch. `what_changes`: "Wenn deine Stufe erhöht wird, welche Räume kommen dazu?"
- Zusammen mit Accessibility: ein gemeinsames Personenprofil (Mobilität plus Rolle), damit der Agent beides nie wieder erfragen muss.
- Oberfläche: Rollenwähler, gesperrte Räume schraffiert, Hinweis am Ziel ("Zutritt Stufe 3 nötig").
- Edits: Facility Manager können Rechte ändern ("Serverraum nur noch für IT"), mit Karte und Ja und Undo.

### Aufwand und Risiken
- Phase 1 (Rollen, Standardregeln nach Raumart, Routing, `can_i_go`, Tests, Live-Skripte): etwa 3 bis 4 Stunden. Phase 2 (Richtliniendatei mit Adaptern, Türen mit Kartenleser, Oberfläche): etwa 3 Stunden.
- Risiko: Es wirkt wie Sicherheit. Texte müssen klar sagen, dass es Planungshilfe ist. Keine Behauptung wie "du darfst" für sicherheitskritische Räume, nur "nach der hinterlegten Regel".
- Risiko: Eine Rolle ist nur eine Angabe der Person. Sensible Regeln gehören nicht in Prompts, sondern in die Richtlinie auf dem Server. Berechtigungen nicht in Logs schreiben.
- Frage an Synera: Gibt es Berechtigungen in den Sonntagsdaten oder Fragen dazu? (vermutlich nein)
- Einordnung für das Ideation-Gate: Starke Alltagsgeschichte und billig auf unserem Routing, aber **keine Rubrik der Jury nennt sie**. Als Creativity-Extra neben Accessibility und 3D denkbar, nicht als Ersatz.

## 6. "Wir haben weitergedacht": Roadmap-Geschichte für Pitch und Technik-Text
Status: geparkt, Nutzung beim Schreiben von Pitch, Video und Technik-Text (`docs/submission/`). Gedanke von Jennifer: Nicht alles muss gebaut sein. Die Jury bewertet auch, was wir **nicht gefragt wurden** ("what did you add that we did not ask for"). Eine ehrlich beschriebene Roadmap zeigt Tiefe, solange wir klar trennen zwischen **gebaut und gemessen**, **als Spec oder Prototyp vorbereitet** und **nur Idee**.

### Aussage in einem Satz
"Aus einem Gebäude, das man fragen kann, machen wir ein Gebäude, das **jede Person versteht und für jede Person passt**: wer sie ist, was sie braucht, wohin sie darf, was gerade passiert."

### Die Roadmap-Folie (eine Folie, drei Spalten)
| Heute gebaut (belegt) | Als Nächstes vorbereitet | Weitergedacht |
|---|---|---|
| Fragen beantworten (alle 9 Typen, Parser plus Agent), Routen nach Synera-Regel, Touren, stufenfrei, Sperrungen, Gabelstapler grob, "What changes?" fürs ganze Gebäude, Edits mit Karte und Ja (Tür, Gerät platzieren, Undo), Voice in und out, Gebäude aus Plänen bauen (Level 4), Campus über mehrere Gebäude (Level 3) | Accessibility-Profil (Rollstuhl mit Türbreite, Mobilität, ruhige Wege), 3D-Ansicht mit sprechendem Agenten, Aufgabe zu Gerät ("ich will schweißen"), Ereignisprotokoll ("wo war die Presse gestern") | Zutrittsrechte und Rollen ("du brauchst Stufe 3"), Live-Updates per Scan, AR auf dem Handy, mehrere Personen gleichzeitig im Gebäude, Verbindung zu echten Systemen (Zugangskontrolle, Inventar, Wartung) |

### Wie wir es erzählen (Skript für 20 Sekunden im Pitch)
"Wir haben nicht nur die Fragen beantwortet, sondern weitergedacht: Wer fragt, hat Bedürfnisse (Rollstuhl, Reizempfindlichkeit), Rechte (nicht jeder darf in den Serverraum) und eine Aufgabe (ich will schweißen, nicht 'Station H-A4'). Das Gebäude ändert sich ständig, deshalb haben wir Edits, Undo und einen Verlauf vorgesehen. Die Teile, die schon laufen, sind gemessen, die anderen sind als Spezifikation vorbereitet."

### Regeln, damit es glaubwürdig bleibt
- Jede Zeile der Folie gehört in genau eine Spalte. Nichts aus der Spalte "weitergedacht" wird als gebaut gezeigt oder gesprochen.
- Zahlen nur aus `docs/eval-log.md` und den Berichten, mit Quelle. Keine Schätzungen als Messwerte.
- Die Idee mit Rechten ist keine Sicherheitsfunktion und wird nicht so verkauft. Gesundheitsangaben (Accessibility) werden nicht gespeichert.
- Wenn etwas aus dem Fridge vor dem Freeze gebaut wird, rückt es in die erste Spalte und bekommt eine Messung.

### Wohin damit
- `docs/submission/TECHNICAL_EXPLANATION.md`: Abschnitt "Where this goes next" (englisch, 6 bis 8 Zeilen, dieselben drei Spalten, nur Belegtes in der ersten Spalte).
- `docs/submission/DEMO_SCRIPT.md`: Schlussbild des Videos (5 Sekunden Roadmap-Folie) und eine Antwort in den Q&A ("What would you build next?").
- Optional als Mini-Demo, wenn Zeit bleibt: eine Rollen-Auswahl in der Seite, die nur zeigt, welche Räume mit der Regel "Beispielregel" gesperrt wären (kein Routing). Nur wenn Idee 4 Phase 1 nicht gebaut wird und klar als Beispiel gekennzeichnet.

## 7. Wo bin ich, und was bewegt sich? Heute schon, ohne 6G
Status: geparkt (Leonie, 24.10.2026). Gedanke für die Story: 6G soll Gebäude selbst "sehen" lassen (Sensing, cm-genaue Ortung, Echtzeit-Zwilling). Vieles davon lässt sich heute mit Handy und Laptop nachbauen. Unser Agent ist die Schnittstelle, egal woher die Daten kommen: "heute Gespräch, QR und Foto, morgen 6G".

| Idee | Heute echt oder simuliert | Aufwand | Einschätzung |
|---|---|---|---|
| 7a QR-Code an jeder Tür (aus den Daten generiert): Scan = "du stehst an Tür 0.12" | echt | klein | verlässlich, Rückfallebene |
| 7b **Foto-Ortung**: Foto von Türschild oder Maschine, Claude-Vision liest Raumnummer oder Maschinentyp, Abgleich mit unseren Daten | echt | mittel | Wow-Moment ohne Infrastruktur |
| 7c Blauer Punkt zwischen QR-Codes (Schritte und Kompass im Browser, rastet an der Route ein) | echt, ungenau | mittel | parken (Risiko) |
| 7d "Das ist jetzt hier": Maschine per Code umziehen, Karte und Einbring-Check rechnen neu | echt | klein bis mittel | Level 5 "Make things move" |
| 7e Positions-Schnittstelle `/api/position` plus simulierter Stapler-Feed (heute UWB-Tags, morgen 6G), Live-Hotspots Mensch und Stapler | Schnittstelle echt, Daten simuliert | mittel | Brücke zu 6G und zu Idee 3b |
| 7f Mehrere Menschen: Einchecken per QR, "wer ist am nächsten an Presse 2?" | echt | mittel | nur mit klarem Zweck (siehe unten) |
| 7g Ereignis-Eingang aus Systemen ("Aufzug 1: Störung"), sperrt und routet automatisch | Eingang echt, Meldung simuliert | klein | nutzt vorhandene Sperren |

### 7b Foto-Ortung: reichen die Daten? (gezählt über alle 280 Gebäude)
- Türschilder: jeder Raum hat eine Nummer (`ref`), eindeutig pro Gebäude bei procedural, Swiss und ResPlan zu 100 %, bei OSM zu 95 % (Rückfrage bei Doppelten).
- Maschinen: 853, nur in Fabriken, nur 100 davon sind die einzige ihres Typs im Gebäude. Ortung über die Maschine also nur mit Rückfrage über Nachbarn ("was steht links neben dir?"), Positionen und Nachbarn haben wir.
- Möbel taugen nicht (zu viele gleiche).
- Es gibt keine echten Fotos der Gebäude. Demo: Türschild aus den Daten ausdrucken und fotografieren.

### 7f Mehrere Menschen: für wen?
- Evakuierung und Sammelplatz-Kontrolle ("wer ist noch drin, wo?", Rettungsweg für Rollstuhl): stärkster Fall, echter Pflichtprozess.
- Instandhaltungs-Disponent ("wer ist am nächsten an Presse 2?"): spart Stillstandszeit, passt zu 3d.
- Empfang und Besucher: mittel. Kollegen finden: schwach.
- Datenschutz: freiwillig, nur Raumebene, nur für die Schicht.

### 7h. Evakuierung und Sammelplatz-Kontrolle (aus 7f), spannend (Leonie)
- Wer: Sicherheitsbeauftragter, Brandschutzhelfer. Echter Pflichtprozess in jeder Fabrik, heute oft Listen auf Papier.
- Ablauf: Alarm. Alle Eingecheckten (QR, Foto-Ortung, später 6G) erscheinen auf der Karte. Jeder bekommt seinen Fluchtweg zum nächsten Ausgang, Aufzüge gesperrt, Rollstuhlnutzer bekommen einen stufenfreien Weg oder einen sicheren Wartebereich. Am Sammelplatz abhaken. Der Beauftragte fragt: "Wer ist noch drin, und wo?" und bekommt Räume und Namen.
- Daten: Eingänge (`outside`), Sperren, stufenfreies Routing vorhanden. Fehlt: Fluchtwege und Sammelplätze als eigene Angabe (Annahme: Eingänge = Ausgänge, Sammelplatz im Gespräch festlegen).
- Ehrlich: kein Ersatz für die Brandschutzordnung, nur Hilfe. Datenschutz: nur für die Dauer des Alarms.

### 7i. Nächster Techniker bei einer Störung (aus 7f), spannend (Leonie)
- Wer: Schichtleiter oder Instandhaltungs-Disponent. Spart Stillstandszeit.
- Ablauf: "Presse 2 steht." Der Agent kennt die Positionen der eingecheckten Techniker, rechnet echte Laufwege (nicht Luftlinie, über Treppen und Aufzüge) und schlägt den nächsten vor: "Max ist 40 m entfernt, Lena 120 m über die Treppe." Auf Ja bekommt Max die Route, optional mit Werkzeug-Abholung (3d Störungs-Modus).
- Daten: Routing, `errand`-Logik, Maschinenpositionen vorhanden. Fehlt: Qualifikation der Techniker (im Gespräch angeben oder simulieren).
- Passt zu Syneras Präsentation (Mehrnutzer-Karte auf der Schlussfolie).

## 6. Geplante Wartungen anmelden (Idee von Jennifer, 24.10.2026)
Status: geparkt. Baut auf der Spec `docs/specs/live-updates.md` auf (Sperrungen mit Zeitraum, Dokumente, Sprache) und auf Idee 3b (Ereignisprotokoll).

### Idee
Wartungen sind keine Überraschung, sondern vorab bekannt. Man **meldet sie an** (per Sprache, Text, Formular in der Seite oder Dokument) und das Gebäude "weiß" es: Wann wird was gewartet, wer macht es, was ist dadurch gesperrt, wie komme ich trotzdem hin?
- "Die Abkantpresse H-A3-B wird am 4. November von 8 bis 12 Uhr gewartet, Techniker Müller." Der Agent legt einen Wartungstermin an: Gerät, Zeitraum, Person, Dauer, Wirkung (die Maschine ist gesperrt, der Gang davor ist bis 10 Uhr blockiert, ein Umweg wird nötig).
- Wiederkehrende Wartungen: "Alle Aufzüge jeden ersten Montag im Monat, 7 bis 9 Uhr." Der Eintrag wiederholt sich selbst.
- Erinnerung und Warnung: "Morgen ab 8 Uhr ist Aufzug 1 in Wartung. Deine Route für morgen führt über ihn, hier ist der Umweg." Der Techniker bekommt seinen Weg zum Gerät (mit Landmarken und Abbiegehinweisen) und sagt "angekommen" (Beginn), "fertig" (Ende, hebt die Sperrung auf).
- Konflikte erkennen: "Am 4. November sind schon der Aufzug 2 und der Hauptgang gesperrt. Mit dieser Wartung ist Halle B nicht mehr erreichbar." Der Agent zeigt es als Warnung, bevor der Termin bestätigt wird.
- Überblick: Wartungskalender pro Gebäude, "Was ist diese Woche in Wartung?", "Was steht beim Gerät X an?", "Wann war die letzte Wartung der Presse?" (Verlauf aus dem Ereignisprotokoll).

### Was daraus ohne Neubau folgt
- Alles aus `live-updates.md` (Zeitraum, automatisches Anwenden und Aufheben, Routen für einen Zeitpunkt, Warnung vor kommenden Sperrungen, Dokumente und Kalenderdateien einlesen) deckt die Sperrungsseite ab. Dazu kommt nur noch die **Wartungsseite**: Gerät, verantwortliche Person, Art (Inspektion, Reparatur, Reinigung), Wiederholung, Status (geplant, läuft, erledigt) und Notizen.
- Wartungstypen als `kind: maintenance` im Datenmodell `ScheduledChange` (schon vorgesehen), erweitert um `asset_id`, `assignee`, `task`, `repeat`.
- Techniker-Weg: `give_directions` zum Gerät mit Rolle "Techniker" (Hände voll, Landmarken, Dreierschritte, Sprache), das gibt es.
- Verlauf: die Ereignisse "Wartung begonnen" und "fertig" mit Zeit gehören ins Ereignisprotokoll (Idee 3b).

### Was die Daten nicht hergeben
Es gibt keine Wartungsdaten, Intervalle, Techniker oder Termine (geprüft). Alles wird von Menschen oder Dokumenten gemeldet. Wir erfinden nichts: kein "die Presse ist wartungsfällig" ohne gemeldete Wartung. Ein Standard-Intervall nach Geräteart (zum Beispiel "Aufzug monatlich") wäre nur ein Vorschlag mit Quelle "Beispielregel".

### Aufbau und Aufwand
- Abhängig von Schritt 1 der Live-Updates-Spec (4 bis 5 Stunden). Dazu für Wartungen: Felder, Wiederholung, Konflikterkennung ("Was ist dann nicht mehr erreichbar?", Wiederverwendung von `impact.analyse` mit Zeitpunkt), Techniker-Weg, Status "läuft" und "erledigt" per Sprache: etwa 3 bis 4 Stunden.
- Oberfläche (Leonie): Wartungskalender (Wochenansicht), Formular "Wartung anmelden", Gerät auf dem Plan markiert, Banner "Wartung beginnt in 20 Min".
- Mit Dokumenten (Wartungsplan als CSV, Kalenderdatei oder Aushang): gehört zu Schritt 2 der Live-Updates-Spec.

### Risiken und Haken
- Zeitangaben und Zeitzonen (siehe Live-Updates-Spec): Karte zeigt immer das ausgewertete Datum mit Wochentag.
- Wer darf Wartungen anmelden und aufheben? Ohne Rechteprüfung (Idee 4) darf es jeder, der den Agenten fragt. Hinweis in der Karte.
- Sicherheit: Wartungsmeldungen nicht als Freigabe für gefährliche Arbeiten darstellen ("Sperrung für Planung", kein Sicherheitsfreigabe-System).
- Einordnung: Gehört zu "Make things move" und zu "A building that never stops changing" in der Synera-Präsentation. Für die Jury eine glaubwürdige Alltagsgeschichte, aber keine Rubrik der Kernwertung. Beim Gate zusammen mit Live-Updates entscheiden, nicht einzeln.
