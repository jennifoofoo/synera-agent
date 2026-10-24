# Wer arbeitet woran (Stand Samstag 24.10.2026, ca. 22:50)

Für Leonie und ihren Agenten: damit niemand dieselbe Datei doppelt anfasst. Code-Freeze ist **Sonntag 13:00**. Alle Agenten hier laufen in Jennifers Sitzung, jeder auf einem **eigenen Branch** in einem eigenen Worktree. Gepusht wird nur auf `jennifoofoo/synera-agent`, **nie** auf das Synera-Kit-Repo.

## Was ist in `main` (alles grün: 3394 Tests, Live-Suite 54 von 54)
Kit 1.1.0 (neue Wegregeln und Labels von Synera), Position und Begleiten (`state.position`, `state.guide`), Auto-Pace (`pace`, `guide_tick`), Sprachregeln (`voice: true`), Campus-Endpunkte (`/api/campus/*`), gzip und Cache, **Leonies `twin/` als einziges Frontend** (alte Seite gelöscht), `scripts/build_twin.sh`, Antwortdatei `answers/team_synera.csv` (145 von 145, im Repo).
Seite bauen und starten: `scripts/build_twin.sh`, dann `uv run python -m web`. Handy über https: `scripts/tunnel.sh`.

## Offene Arbeiten (alle noch nicht in `main`)

### Frontend `twin/` (bitte hier nicht parallel an denselben Dateien arbeiten)
| Branch | Inhalt | Dateien, die er anfasst |
|---|---|---|
| `fix/twin-controls` | **Fehler 1: Seitenverhältnis.** Bei offenem Sheet oder Panel ist die ganze Karte vertikal gedehnt (runde Marken werden Ovale). Ursache: `setViewOffset` in `CameraRig.tsx` ohne passendes `camera.aspect`. **Fehler 2: Flackern.** Der unendliche Boden-Raster wird bei flachem Winkel zu Moiré (Striche und Punkte), das flackert beim Drehen. Fix in `Scene.tsx` (`<Grid>`, `<fog>`). **Steuerung:** Tastatur (WASD, Pfeile, Q/E, R/F, Shift, Home, 1 bis 9 für Etagen, `?` Hilfe), Maus und Trackpad (Zoom zum Mauszeiger, Mittelklick und Shift-Ziehen verschieben, Doppelklick fliegt zum Raum), weniger Dämpfung, Zoom-Grenzen (kein graues Nichts), Campus-Kamera angleichen | `scene/CameraRig.tsx`, `scene/Scene.tsx` (Grid, Fog), `campus/CampusSite3D.tsx` (Kamera), Eingabe |
| `fix/twin-openings` | **Offene Passagen** (`opening`, keine Tür, zum Beispiel 14,6 m zwischen den Hallenzonen H-A4 und H-A3) als **Lücke in der Wand** zeichnen, 2D und 3D. Dazu der **blasse Geisterblock** (Safari, nah an den Büros), und ein wiederholbares Prüfskript "gezeichnet gegen Daten" (`scripts/twin_audit.sh`, Bericht in `docs/twin-audit/REPORT.md`) | Wand- und Bodengeometrie unter `scene/` (nicht Kamera) |
| `design/blueprint-minimal` | **Stil**: nüchtern, Blueprint/Industrie, nicht zu krass: Radien 4 bis 6 px statt Pillen, Haarlinien statt Schatten, Papierweiß, Graphit, **eine** Signalfarbe (Orange), flache Raumetiketten, ein Token-Block (`tokens.css`), `twin/DESIGN.md`. **Nur Stil, keine Logik** | CSS-Dateien, Farb-Konstanten der Szene |
| `feat/twin-here-ui` | **Tipp-Pin** (Marker am genau angetippten Punkt, Punkt in der Karte), **blauen "You are here"-Punkt ziehen** (Standort korrigieren, Maus und Touch), veralteten Stub `ui/Position.tsx` bereinigen. Der Chip "You are here", die Etappenkarte (Back, Next, Stop) und die Marker **gibt es schon** | `scene/FloorMesh.tsx`, `scene/Markers.tsx`, `ui/Card.tsx`, `ui/HereChip.tsx`, `store.ts` (nur ein kleines Flag `dragLock`) |

Zuständigkeit gegen Konflikte: Kamera und Raster = `fix/twin-controls`. Wände, Öffnungen, Geisterblock = `fix/twin-openings`. Farben, Radien, Schatten = `design/blueprint-minimal`. Antippen, Pin, Standortpunkt = `feat/twin-here-ui`. Leonies eigene Arbeit am Rest (Handy-Layout, Wake-Wort "Hey Wanda", Auto-Pace-Timer) bleibt bei ihr, siehe `docs/LEONIE_TODO.md`. **Wer `feat/twin` weiterentwickelt, bitte vorher `origin/main` holen.**

### Server und Agent
| Branch | Inhalt |
|---|---|
| `feat/route-from-point` | Route **ab genauem Punkt** im Raum (nicht ab Raumanker): `/api/route` mit `start_point` und `destination_point`, Agent nutzt den Punkt aus `state.position.point` automatisch. Ohne Punkt byte-gleich wie heute |
| `feat/query-tools-wired` | vier Abfragewerkzeuge (`list_rooms`, `floor_summary`, `list_doors`, `room_size`), `door_effect` (Länge vor und nach einer neuen Tür), Hauptausgang-Regel. Live-Suite 51 von 54 (Streuung der Modellformulierung), wird vor dem Merge geklärt |
| `feat/exit-tools` | `find_exit` (schnellster und zweiter Ausgang vom Standort, Aufzüge nie, stets der Satz "Kürzester Weg im Plan. Kein Fluchtwegplan: folge den echten Schildern"), nächster Feuerlöscher, Defibrillator, Augendusche, Alter des Standorts |

### Level 4 (Plan zu Gebäude)
Aufeinander aufbauend: `feat/level4-svg-first` (SVG neben dem Plan lesen, Maßstab aus `building.json`, `find_space`-Regel) → `feat/level4-align-types` (Stockwerkshöhen, Etagen ausrichten über Aufzüge) → `feat/level4-furniture` (Raumtypen und Geräte aus den Möbel-Symbolen, 69 % statt 33 % auf unserer Nachbildung) → `feat/level4-door-widths` (Schätzung der Türbreiten). Dazu Abgabe-Texte auf `docs/submission-final`.

## Reihenfolge der Merges nach `main` (macht Jennifers Sitzung, jeweils mit Prüfung)
1. Kamera und Flackern (`fix/twin-controls`), 2. Wand-Lücken und Audit (`fix/twin-openings`), 3. Design, 4. Tipp-Pin und Ziehen, 5. Route ab Punkt, 6. Level 4 (in der Kette), 7. Werkzeuge und Fluchtplan (nach Live-Prüfung), 8. Abgabe-Texte zuletzt.
Regel aus `CLAUDE.md`: Alles, was Prompt, Werkzeuge, Position, Sprache oder Chat berührt, geht erst nach grüner **Live-Suite** (`uv run --env-file .env pytest -m live -q`) und grünem `scripts/check.sh` in `main`.

## Was an der Oberfläche gerade bekannt falsch ist (Belege: Screenshots von Jennifer, Messungen)
- Marken und Karte **vertikal gestreckt** bei offenem Sheet (Seitenverhältnis), siehe `fix/twin-controls`.
- **Flackern** beim Drehen: Boden-Raster bei flachem Winkel, siehe `fix/twin-controls`.
- **Route läuft scheinbar durch eine Wand** an offenen Passagen (die Daten haben dort wirklich eine Öffnung), siehe `fix/twin-openings`.
- **Geisterblock** (blasse große Kopie rechts oben) in Safari bei Nahansicht, wird nachgestellt.
- Mausrad-Zoom kann in eine **graue leere Fläche** laufen, siehe `fix/twin-controls`.
- Optik wirkt **generisch** (Pillen, große Radien), siehe `design/blueprint-minimal`.

## Hinweise
- API-Schlüssel stehen nur in `.env`, nie im Repo oder Chat. Die Anthropic-Grenze war heute Abend einmal erreicht und ist wieder angehoben.
- Die Handy-Prüftests unter `tests/e2e/` prüfen noch die **alte** Seite und werden auf `twin/` umgestellt, sobald Leonies Stand stabil ist.
- Wenn ihr etwas an einer der oben genannten Dateien ändern wollt: kurz in den Chat schreiben, dann stimmen wir den Branch ab.
