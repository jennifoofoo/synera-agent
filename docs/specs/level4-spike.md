# Level 4 Spike: Gebäude aus Grundriss per Claude-Vision

Ergebnis vorweg: **bauen, aber als geführter Flow mit Vorschau und Prüfung, nicht als "Bild rein, fertig".** Bei sauberen Plänen (procedural, ResPlan) kommt in 6 bis 13 s für ca. 1 bis 3 Cent ein Gebäude heraus, das fast exakt zum Original passt (alle Räume, alle Türen, Flächen 0,5 bis 1,8 % daneben, Routen 0,1 bis 0,4 % daneben, sobald der Maßstab stimmt). Bei dichten Plänen (Swiss Dwellings) fehlen kleine Räume und viele Türen, und der Graph hängt auseinander. Das fangen Validierung und eine Rückfrage ab, ohne Mensch geht es nicht.

## Aufbau (Code unter `spikes/level4/`)

| Datei | Was |
|---|---|
| `schema.py` | Extraktions-Schema und Prompt. Räume (id, ref, name, type, room_type, Polygon in Pixeln), Türen (zwei Raum-IDs oder `outside`, Position, Breite in px, kind), Maßstabsleiste (meist null). Treppen und Aufzüge sind Räume mit `type: stair/lift`. |
| `extract.py` | Ein Vision-Call (`claude-sonnet-5-5`, effort medium, max. 1 Retry) pro `floor_<n>_plain.png`. Speichert Antwort, Tokens und Sekunden unter `outputs/`. |
| `convert.py` | Deterministisch: Pixel zu Metern, y gedreht, Raum-IDs zu Space-IDs, Türen zu Openings (unbekannte oder identische Räume werden verworfen und als Warnung gemeldet). Maßstab: `true_width` (bekannte Gebäudebreite), `door` (Tür = 0,9 m), `bar` (Maßstabsleiste). |
| `measure.py` | Vergleich gegen das Original der gleichen Etage, schreibt `results.json`. |

Bilder liegen nicht im Repo, Referenz: `data/dev/<id>/floor_0_plain.png`.

Was im Bild steht: Raumnummern (Refs) sind gedruckt, Räume farbig nach Typ, Türen sind braune Punkte, Öffnungen graue Punkte, Eingänge rote Dreiecke. **Kein Maßstab, keine Maßstabsleiste, keine Türbreiten** (Türen sind Punkte, keine Öffnungsbögen). Die Bilder sind klein (270 bis 570 px breit), daher ca. 1000 Input-Tokens pro Bild.

## Messaufbau

- 6 Etagen (je Etage 0): proc-campus-dev-000 und -001, resplan-439 und -1465, swiss-31 und -203. Dazu eine Wiederholung von swiss-31 mit verbessertem Prompt (v2) und ein ungültiger v2-Lauf. Insgesamt **9 API-Calls** (Limit 12).
- Maßstab für die Hauptzahlen: wahre Breite der Etage aus `building.json`. Gemessen wird die Qualität des Extrahierens, nicht die des Maßstabs.
- Räume: Zentroid-Matching 1:1 (greedy), Toleranz 2,0 m. Recall = gematcht / wahr, Precision = gematcht / erzeugt. Fläche: relativer Fehler der gematchten Räume.
- Türen: nur interne Türen, Treffer = gleiches Raumpaar wie im Original (nach Raum-Matching). Eingänge extra gezählt.
- Routen: 5 zufällige (Seed 0) gematchte Raumpaare, `BuildingMap.route` auf der Original-Etage (nur diese Etage) gegen die erzeugte. "ohne Route" = der erzeugte Graph hat keinen Weg.

## Ergebnisse (Maßstab = wahre Breite)

| Etage | Räume wahr / gefunden | Recall | Precision | Fläche median / worst | Türen wahr / gefunden / korrekt | Tür-Recall | Eingänge | Route median / worst | ohne Route | Sek. | Tokens in / out |
|---|---|---|---|---|---|---|---|---|---|---|---|
| proc-campus-dev-000 | 28 / 28 | 1,00 | 1,00 | 0,6 % / 1,5 % | 27 / 27 / 27 | 1,00 | 2 / 2 | 0,3 % / 0,4 % | 0 von 5 | 13,2 | 1017 / 2885 |
| proc-campus-dev-001 | 22 / 22 | 1,00 | 1,00 | 0,8 % / 1,9 % | 21 / 21 / 21 | 1,00 | 2 / 2 | 0,1 % / 0,2 % | 0 von 5 | 11,3 | 955 / 2281 |
| resplan-439 | 8 / 8 | 1,00 | 1,00 | 0,5 % / 1,9 % | 7 / 7 / 7 | 1,00 | 1 / 1 | 0,2 % / 0,4 % | 0 von 5 | 5,7 | 942 / 967 |
| resplan-1465 | 10 / 10 | 1,00 | 1,00 | 1,8 % / 4,3 % | 9 / 9 / 9 | 1,00 | 1 / 1 | **17,8 % / 21,2 %** | 0 von 5 | 6,3 | 942 / 1142 |
| swiss-203 | 36 / 24 | **0,67** | 1,00 | 8,2 % / 17,7 % | 34 / 8 / 7 | **0,21** | 4 / 4 | 11,9 % / 13,0 % | 2 von 5 | 13,4 | 996 / 2130 |
| swiss-31 | 30 / 25 | **0,83** | 1,00 | 12,0 % / 42,3 % | 27 / 12 / 10 | **0,37** | 4 / 4 | nicht messbar | 5 von 5 | 13,5 | 972 / 2258 |
| swiss-31, Prompt v2 | 30 / 26 | 0,87 | 1,00 | 7,0 % / 126,8 % | 27 / 21 / 15 | 0,56 | 4 / 4 | 7,0 % / 7,9 % | 3 von 5 | 17,2 | 1135 / 2871 |

Median über die 6 Etagen (Prompt v1): Raum-Recall 1,00 (min 0,67), Precision 1,00, Flächenfehler median 1,3 %, Tür-Recall 1,00 (min 0,21). Die beiden Swiss-Etagen ziehen die Zahlen nach unten, die vier anderen sind praktisch perfekt.

Validierung aus dem erzeugten Graph: Swiss-31 hat 10 Zusammenhangskomponenten und 16 Räume ohne Weg nach draußen, Swiss-203 hat 13 Komponenten und 15 solche Räume, die vier anderen Etagen 1 Komponente und 0. **Die Prüfung "jeder Raum erreichbar" erkennt genau die Pläne, bei denen die Extraktion schlecht war.**

### Maßstab

| Quelle | Ergebnis |
|---|---|
| Maßstabsleiste | In allen 6 Plänen keine vorhanden, Claude gibt korrekt `null` zurück. |
| Tür = 0,9 m | Auf diesen Bildern unbrauchbar: Maßstabsfehler zwischen -45 % und +191 % (Faktor 0,55 bis 1,9 gegenüber dem wahren), weil Türen nur als 8 bis 12 px große Punkte gezeichnet sind. Auf Plänen mit echten Türflügeln vermutlich besser, hier nicht belegt. |
| Bekannte Gebäudebreite | Fehlerfrei (ist die Referenz). Im Produkt: Nutzer nach einer bekannten Länge fragen (Gebäudebreite, Raumbreite, Türbreite). |

Ein falscher Maßstab macht alle Längen und Flächen falsch, aber der Graph (Räume, Türen) bleibt richtig. Routen skalieren linear mit.

### Fehlerarten (beobachtet)

- **Kleine Räume fehlen**: Swiss-31 ohne die Flure 0.06, 0.09, 0.14, 0.21, und die vier grauen Treppenhäuser wurden zu zwei Treppenformen zusammengefasst. Die Treppenhäuser sind im Original teils synthetisch ergänzt und im Bild kaum sichtbar.
- **Türen fehlen**: Swiss 8 von 34 und 12 von 27 gefunden. Viele Punkte an dichten Wänden werden übersehen. Prompt v2 (erst Inventar zählen, dann zeichnen) hob den Tür-Recall von 0,37 auf 0,56, die Precision fiel von 0,83 auf 0,71. Ein v2-Lauf lieferte kaputtes JSON (zwei Objekte, eine Klammer zu viel), gespeichert unter `outputs/failed/`. Danach stand im Prompt "ein einziges Objekt", der zweite Lauf war gültig. Heißt: Structured Output (`output_config.format`) oder JSON-Reparatur einplanen.
- **Eckpunkte ungenau bei gedrehten Plänen**: Swiss-31 Fläche worst +42 %, v2 sogar +127 % (ein Raum mit falschem Polygon).
- **Raumtypen sind geraten** (viele "living room" statt bedroom oder kitchen in Swiss). Fürs Routen egal, für "wo ist die Küche" nicht.
- **Türposition ein paar Pixel daneben** (resplan-1465: Routen 18 % zu lang, obwohl Räume und Türpaare stimmen). Gegenmittel: Tür deterministisch auf die gemeinsame Wand der zwei Polygone projizieren (wie `add_door` es schon macht). Nicht getestet.
- **Verschmolzene Räume**: nicht beobachtet (Precision 1,00 überall). Das Hauptproblem ist Fehlen, nicht Verschmelzen.

## Zeit und Kosten pro Etage

Sonnet 5.5 kostet 2 USD pro 1 Mio. Input-Tokens und 10 USD pro 1 Mio. Output-Tokens (Preistabelle im claude-api-Skill, Stand 2026-10-06, nicht gegen die Rechnung geprüft). Pro Etage 0,012 bis 0,031 USD (Median der 6 Etagen ca. 0,020 USD) und 5,7 bis 17,2 s. Der ganze Spike mit 9 Calls: ca. 0,19 USD (8,1k Input, 17,4k Output Tokens). Ein 5-Etagen-Haus: ca. 0,10 bis 0,15 USD, etwa eine Minute, wenn die Etagen parallel laufen.

## Empfehlung

**Level 4 bauen, Ziel "Entwurf in Minuten, Mensch bestätigt".** Versprechen, die wir halten können: saubere Pläne mit gedruckten Raumnummern, Räume und Türen praktisch vollständig, Maße nur so gut wie der angegebene Maßstab. Nicht versprechen: Treppenhäuser und kleine Nebenräume auf dichten Plänen, Türbreiten, Raumtypen.

### Minimaler Gesprächsfluss

1. Nutzer lädt den Grundriss hoch (pro Etage ein Bild) und sagt "baue das".
2. Agent fragt kurz: "Welche Etage ist das? Und eine bekannte Länge, z. B. die Gebäudebreite oder eine Raumbreite in Metern." Bei gedruckter Maßstabsleiste entfällt die zweite Frage.
3. Extraktion (ein Call), Konvertierung, Validierung.
4. Agent zeigt, was er verstanden hat: Vorschau (Polygone mit Raumnummer, Türpunkte) und eine Befundzeile, z. B. "24 Räume, 8 Türen, 2 Eingänge. 15 Räume ohne Weg nach draußen, vermutlich fehlen Türen."
5. Nutzer korrigiert im Gespräch ("Tür zwischen 0.13 und 0.07 fehlt", "0.27 ist das Treppenhaus", "der Flur ist 1,6 m breit"), der Agent ändert deterministisch (`add_door` gibt es schon).
6. Erst nach "ok" wird `building.json` gespeichert und geladen.

### Validierungen vor dem Speichern

- Polygon gültig (kein Selbstschnitt), Fläche über 1 m², keine große Überlappung zwischen Räumen.
- Jede Tür verbindet zwei verschiedene bekannte Räume (oder `outside`) und liegt an deren gemeinsamer Wand (max. 0,6 m Abstand).
- Jeder Raum erreichbar (eine Zusammenhangskomponente inklusive `outside`), mindestens ein Eingang. Das war hier der beste Indikator für schlechte Extraktion.
- Plausible Maße: Raumflächen 2 bis 300 m², Türbreite 0,7 bis 2,5 m.
- Mehrere Etagen: Treppen und Aufzüge brauchen auf jeder Etage einen Stop-Raum, sonst fragt der Agent nach.
- `scripts/preflight.py` (Phase 2, Block B) als letzte Hürde wiederverwenden.

### Was die Webseite braucht

- Bild-Upload (PNG oder JPG, Etagenzuordnung, Größenlimit), mehrere Etagen per Drag and Drop.
- Vorschau-Ansicht (SVG aus den Polygonen, Raumnummern, Türen, auffällige Stellen rot).
- Eingabe oder Chat-Frage für den Maßstab, Button "speichern".
- Backend: Upload-Endpunkt, asynchroner Aufruf der Extraktion (10 bis 20 s), Ablage des Entwurfs, Übergabe an `BuildingMap`.

### Aufwand (Schätzung)

| Block | Stunden |
|---|---|
| Extraktion robust (Structured Output, JSON-Fehler, Retry, Mehr-Etagen-Prompt, ggf. Kacheln bei großen Bildern) | 4 bis 6 |
| Converter produktiv (Tür auf Wand projizieren, kleine Lücken schließen, Treppen und Lifte als Connectors, Mehr-Etagen) | 4 bis 5 |
| Validierung und Befundtext | 3 bis 4 |
| Gesprächsfluss (Rückfragen, Korrekturen, Speichern) | 4 bis 5 |
| Web: Upload und Vorschau | 5 bis 6 |
| Tests und Eval auf den Dev-Gebäuden (Zahlen aus diesem Spike als Baseline) | 3 bis 4 |
| **Summe** | **ca. 23 bis 30 h** |

Für einen Demo-Schnitt (eine Etage, Maßstabsfrage, Vorschau, kein Mehr-Etagen-Support) reichen ca. 8 bis 10 h.

### Grenzen dieses Spikes

Nur Etage 0, 6 Etagen, ein Lauf je Bild (Streuung zwischen Läufen nicht gemessen), nur das Zeichenformat der Datensätze. Echte Architektenpläne (Schraffuren, Möblierung, Maßketten, Scans) sind schwerer und nicht getestet. Gemessen wurde die Extraktionsqualität bei bekanntem Maßstab, den wir im Produkt vom Nutzer erfragen müssten.
