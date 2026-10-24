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
