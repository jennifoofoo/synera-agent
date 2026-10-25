# Wer arbeitet woran (Stand Sonntag 25.10.2026, ca. 01:00)

Für Leonie und ihren Agenten: damit niemand dieselbe Datei doppelt anfasst. Code-Freeze ist **Sonntag 13:00**. Jennifers Agenten laufen jeder auf einem **eigenen Branch** in einem eigenen Worktree. Gepusht wird nur auf `jennifoofoo/synera-agent`, **nie** auf das Synera-Kit-Repo. **Vor eigener Arbeit immer `git pull`.**

## Was ist in `main` (geprüft: Live-Suite 60 von 60, `check.sh` grün bis auf Zeittests unter Last, Antwortdatei 145 von 145 unverändert)
**Server und Agent**
- Level 4 (Plan zu Gebäude): SVG lesen, Maßstab aus `building.json`, Etagenhöhen und Ausrichtung, Raumtypen aus Möbel-Symbolen, Türbreiten. 83 % auf unserer Nachbildung der Level-4-Fragen.
- Fluchtplan `find_exit` (schnellster und zweiter Ausgang, nie Aufzug, fester Hinweis "folge den echten Schildern"), nächster Feuerlöscher, Defibrillator, Augendusche. Notfall-Regeln im Prompt **nur bei Notfall-Wörtern** (sonst störten sie normale Rückfragen).
- Route ab genauem Punkt (`state.position.point`, `/api/route` mit `start_point`/`destination_point`).
- Routenlinie nur gezeichnet: Enden nicht auf Möbeln, in großen Hallen an der Tür, Umwege um Maschinen. Länge und Antworten unverändert.
- Wegbeschreibung neutral ("go into X" statt "through the door", weil viele Öffnungen offene Passagen sind).
- Gesprochene Antworten enden immer auf ihrer einen Frage.

**Frontend `twin/`**
- Leonies `twin-fixes` (rote Ziel-Nadel, ein blauer Standortpunkt, kollisionsfreie 2D-Etiketten, POI-Symbole, Pinch und Doppeltippen am Handy).
- Kamera: halten und ziehen verschiebt, rechts ziehen dreht, Zoom zum Mauszeiger, Tastatur (`?` Hilfe), Zoom-Grenzen, kein Strecken bei offenen Sheets, ruhiges Raster statt Flackern.
- Wand-Lücken an Öffnungen, Türstriche, gestrichelte Zonengrenzen ab 4 m, roter Balken bei gesperrten Türen, Prüfskript `scripts/twin_audit.sh`.
- Design Blueprint minimal mit Synera-Blau `#004fab`, ruhige Routenlinie.
- Tipp-Pin, ziehbarer Standortpunkt, Marker verdecken keine Raumnamen.
- Handy: Raumname beim angetippten Raum, Plan nicht unter der Titelleiste, Etagenleiste im Querformat, Ton-Freischaltung und Wake Lock robuster, 44-px-Tippflächen, Handy-Tests auf `twin/` umgestellt (`scripts/mobile_smoke.sh`).

## Läuft gerade (noch NICHT in `main`, bitte diese Dateien nicht parallel ändern)
| Branch | Was | Dateien |
|---|---|---|
| `feat/twin-ux-calm` | UX gegen kognitive Last (`docs/ux-cognitive-load.md`): **zuerst** Möbel nach Pixelgröße (siehe unten), dann "End route" (ein Knopf), Mikrofon beim Begleiten sichtbar, Etagenleiste an einem festen Platz, ein Griff pro Sheet, kompakte Routenkarte, keine Koordinaten, POI-Symbole als kleine weiße Quadrate, klare Symbole statt "⇕"/"⌂", Eingabe am Handy angedockt, Knöpfe mit Text ("Ask", "Talk"), Legende, Vorschlags-Chips | `ui/` (Karte, Walk, Hilfe), `scene/Labels.tsx`, `scene/mapZoom.ts`, `scene/poiIcons.*`, `ui/FloorRail.tsx` |
| `feat/twin-room-colours` | Raumfarben nach Gruppen (`docs/specs/room-colours.md`): blass Sand (Küche), Aqua (Sanitär), Violett (Treppe, Aufzug), Salbei (Meeting), in Fabriken blass gelbe Gehwege, Sicherheit nur als Symbol in Normfarben, Rest neutral grau; Möbel und Wände heller | `model/palette.ts`, `styles/tokens.css`, `DESIGN.md` |
| `fix/twin-ghost` | **Geisterbild** (verschwommene große Kopie oben rechts, sobald die Raumkarte aufgeht) und neue **Etagen-Regel**: aktive Etage voll, darüber nichts, darunter nur dünner Umriss, Kamera gleitet beim Etagenwechsel, Route über Etagen gestapelt. Dazu Querformat mit rechter Seitenleiste | `scene/CameraRig.tsx`, `scene/Scene.tsx`, `scene/FloorMesh.tsx` (Sichtbarkeit) |

**Leonie selbst:** Wake Word "Hey Wanda" (Spec `docs/specs/voice-handsfree.md` Teil B). Bitte vorher pullen, `voice.ts` wurde unten (Ton-Freischaltung, Wake Lock) vom Handy-Fix geändert.

### Neu seit 01:00
| Branch | Was | Dateien |
|---|---|---|
| `feat/twin-semantic-zoom` | Informationsstufen beim Zoomen (`docs/specs/semantic-zoom.md`): Bereiche von weit, Gerätesymbole mittel, Typ und Fläche, Türbreiten nah | `scene/mapZoom.ts`, `scene/Labels.tsx`, Raumkarte |
| `feat/twin-walk-motion` | **fertig**: Modul "Walk with me" (Schritte zählen, Kompass, Punkt auf der Route), `twin/src/motion/`, 32 Tests | nur `twin/src/motion/` |
| `feat/twin-walk-wired` | Anbindung: Schalter "Walk with me" im Begleit-Sheet, Punkt "estimated", Ansage am Etappenende, Warten an Treppe/Aufzug | Begleit-Sheet (`Walk.tsx`), Marker |
In `main` seit 01:00: Raumfarben, Geisterbild-Fix (Puffer der Nachbearbeitung bei Auflösungswechsel), Leonies Wake Word und Ein-Etagen-Ansicht.

## Stand 01:50: was bei Jennifer liegt (nicht anfassen) und was frei ist
Belegt (fast fertig, kommen in Kürze nach `main`):
- Sprache: `twin/src/handsFree.ts`, `voice.ts`, `store.ts`, `ui/HandsFree.tsx`, `ui/Omnibox.tsx`, neu `wake.ts`
- Sperrungen sichtbar: `scene/Labels.tsx`, `scene/Markers.tsx`, `scene/poiIcons.*`, `ui/Card.tsx`, `ui/Card.css`, `ui/Directions.tsx`, `ui/KeyHelp.tsx`, `audit.ts`, `DESIGN.md`, neu `model/closures.ts`, `ui/AvoidsClosed.tsx`
- Route gerade durch Türen (Server): `web/api.py`, `web/route_draw.py`
Frei für Leonie: `ui/Walk.tsx` ("Walk with me" ist auf `main`) und alles in `scene/` außer Labels, Markers, poiIcons (3D-Look).
**Bis zum Freeze nur Fixes, mit einer Ausnahme als Wow-Effekt: Ortswissen mit Zeit** (Notizen, Probleme, Sperrungen "bis morgen" an Ort oder Gerät), Spec `docs/specs/place-knowledge.md`, wartet auf euer Okay. Leonie baut die Seite gegen den Vertrag dort.

## Sprache, Handtest Jennifer (25.10. nachts), Fix läuft auf `fix/twin-voice-wake-followup`
- "Hey Wanda" wird als "Evander" / "E Wander" erkannt, der Satz geht dann als Frage an den Agenten ("Hey Evander"). Fix: Wake Word per Ähnlichkeit am Satzanfang, auch bei "Talk" abschneiden, nur "Hey Wanda" ergibt "I'm here."
- Folge-Modus: nach jeder gesprochenen Antwort etwa 8 s zuhören, ohne Wake Word und ohne Knopf.
- Route in 3D, Fix läuft auf `fix/twin-route-start-depth`: Linie startet am blauen Punkt (`start_point` an `/api/route`) und wird in 3D von Wänden verdeckt (Tiefentest an, nur in 3D). Kleine Änderungen in `store.ts` und `scene/RouteLine.tsx`, Leonie bitte beim 3D-Look kurz abstimmen.
Dateien: `twin/src/handsFree.ts`, `twin/src/voice.ts` (Leonie: bitte dort gerade nichts parallel ändern).

## 3D-Look (Leonie, 25.10. nachts): Diagnose und Richtung von Jennifers Sitzung
Feedback von Aksha: die 3D-Ansicht wirkt billig. Ursache zum Teil unsere Vorgabe "Blueprint minimal, flach" (für 2D richtig, für 3D zu karg):
- alle Möbel und Maschinen gleiche graue Quader, Wände dunkel und voll hoch (verdecken die Räume), flaches Licht ohne echte Schatten, Boden nur Raster ohne Plattendicke.
Richtung wie bei Archilogic, Smplrspace, MapsIndoors 3D ("Architekturmodell" / Puppenhaus):
- helle Wände, auf etwa 1,2 bis 1,5 m gekappt, dünne dunkle Oberkante; weiches Sonnenlicht mit Schatten und Umgebungslicht (HDRI); Bodenplatten mit Dicke und den blassen Raumfarben.
- Möbel als einfache, erkennbare Formen nach Typ (Tisch, Stuhl, Regal, Schrank, Maschine, Drucker, Sofa, Bett), Rest als abgerundeter Block, als Instanzen gezeichnet (größtes Gebäude osm-way27917482 hat etwa 5000 Assets).
- Achtung: Das Geisterbild kam aus der Nachbearbeitung (N8AO-Puffer nach Auflösungswechsel, Fix in `scene/Effects.tsx`); `tests/e2e/test_twin_ghost.py` muss grün bleiben.

## Beschlossene Regeln (für alle Agenten)
1. **Was wann sichtbar ist:** "Alles zeigen, aber leise." Formen (Möbel, Maschinen) ab etwa 3 bis 4 px Bildschirmgröße auf jeder Zoomstufe. Text und Symbole nach Leonies Stufen in `mapZoom.ts` (weit: Zonen und POIs; mittel: alle Raumnamen; nah: Maschinennamen). Bei Route und Begleiten werden Formen blasser und die Landmarken der Wegbeschreibung kräftiger und beschriftet.
2. **Etagen in 3D:** keine halbdurchsichtigen Etagen. Aktive Etage voll, darüber nichts, darunter nur Umriss.
3. **Farben:** Synera-Blau nur für Route, Auswahl, Hauptknöpfe. Ziel-Nadel rot (Leonie, Karten-Konvention). Raumfarben sehr blass, nur für gesuchte Ziele, nie Farbe ohne Symbol.
4. **Fokus Industrie:** Synera-Kunden sind Automobil, Luftfahrt, Maschinenbau. Fabrik zuerst prüfen, dann Büro, dann Wohnen.

## Noch offen danach
- Leerer erster Schritt "Start in …" in der Wegbeschreibung (Jennifer, Server).
- Bewegung mitlaufen lassen (Schritte zählen plus Kompass, Schalter "Walk with me"): Idee, noch nicht entschieden.
- `feat/query-tools-wired` (vier Abfragewerkzeuge, 51 von 54 live): noch nicht gemergt.
- Echter Gerätetest auf dem iPhone über `scripts/tunnel.sh` (Anleitung `twin/IPHONE-CHECK.md`).
- Abgabe-Texte (`docs/submission-final`), Tag `known-good` kurz vor dem Freeze.

## Hinweise
- Seite bauen und starten: `scripts/build_twin.sh`, dann `uv run python -m web`. Handy über https: `scripts/tunnel.sh`.
- API-Schlüssel nur in `.env`.
- Regel aus `CLAUDE.md`: Alles, was Prompt, Werkzeuge, Position, Sprache oder Chat berührt, geht erst nach grüner Live-Suite und grünem `scripts/check.sh` in `main`.

## Leonie baut jetzt (Sonntag früh, mit Jennifer abgesprochen)
| Branch | Was | Dateien |
|---|---|---|
| `feat/twin-round` | Prüfrunde in der App: alle Geräte eines Typs in einem Bereich, kürzeste Reihenfolge im Code, Führung Station für Station mit "Done"; Was-wäre-wenn für die Runde ("Tür hier → Runde X m kürzer") | neue Dateien `twin/src/round/*`, `ui/Round.*`, kleiner Einhänger in `ui/Walk.tsx` |
| `feat/agent-plan-round` | **Agent-Werkzeug `plan_round`**: Gerätetyp und Bereich rein, kürzeste Reihenfolge mit Metern raus (Python, kein LLM), damit "Hey Wanda, inspection round" im Chat nicht mehr per Hand Reihenfolgen durchprobiert (heute 20 s und nicht garantiert optimal) | neue Datei unter `building_agent/`, Registrierung in den Werkzeugen (gemeinsamer Code: Review-Agent und Live-Suite vor dem Merge) |
| `feat/twin-notes` | Ortsnotizen mit Foto und Einsatzprotokoll, erst im Browser gespeichert | neue Dateien `twin/src/notes/*`, `ui/Notes.*`, `ui/Report.*`, `scene/NotePins.tsx` |
Nicht angefasst: Jennifers belegte Dateien (Sprache, Sperrungen, `web/api.py`, `web/route_draw.py`). Sprachbefehle ("done", "note …", "finished") hängt Leonie mit je einer Zeile an, sobald Jennifers Sprach-Fix in `main` ist.

## Frage an Jennifer (Leonie, Sonntag früh): zweiter Startknopf bei der Prüfrunde
`feat/twin-round` (Leonie) zeichnet die Prüfrunde als normale Route mit Zwischenstopps. Dadurch zeigt die Routenkarte in `ui/Card.tsx` (deine Datei) zusätzlich "Guide me". Der startet die normale Führung über die ganze Runde **ohne** Stationen ("Stop 2 of 5", "Done", Abhaken). Zwei Startknöpfe, einer davon falsch, verwirrt in der Demo.
Vorschlag, eine Zeile in `Card.tsx`, du entscheidest:
- A: Während eine Runde aktiv ist (`inRound()` aus `twin/src/round/round.ts`), die normale Routenkarte ausblenden.
- B: "Guide me" startet bei aktiver Runde die Runden-Führung (`startRound()`), sonst wie bisher.
Leonie empfiehlt A (weniger Knöpfe).
