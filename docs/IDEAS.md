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
