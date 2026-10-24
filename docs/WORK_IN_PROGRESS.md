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
