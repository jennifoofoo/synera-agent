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
| `ui-polish` | UI-Politur: Weißmodell-Look (Glas-Chrome, Inter, weiße Materialien, Routen-Halo, Pill-Labels, ruhige Sperrungen, strukturierte Routenkarte, 2D Norden oben), Plan in `docs/specs/ui-polish.md`, Screenshots `twin/docs/ui-before/` und `twin/docs/ui-after/` | `twin/src/styles/tokens.css`, `twin/src/styles.css`, `twin/src/ui/*.css`, `twin/src/ui/Card.tsx`, `twin/src/model/palette.ts`, `twin/src/scene/{Scene,Effects,GroundGrid,FloorMesh,Things,geometry,RouteLine,Labels,Markers,HerePin,markerLayout,CameraRig}.tsx`, `twin/DESIGN.md` |

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

## Stil: ab jetzt nur eine Sitzung (Jennifer und Leonie, ca. 04:00)
Visuelles Design (Farben, Panels, Schatten, POI-Symbole, 3D-Look) macht nur noch **eine** Sitzung (Jennifers zweite, Ordner `ui-polish`), mit `docs/specs/ui-feedback-akshat.md` und `docs/specs/3d-look.md` als Briefing. Alle anderen Agenten bauen nur Funktion mit den vorhandenen Bausteinen und erfinden keine eigene Optik.

## Während Leonie schläft (Jennifer, ca. 03:00): Agenten übernehmen zwei Teile
- Seite fürs Ortswissen: Plan `docs/specs/place-knowledge-page.md`, Branch `feat/twin-knowledge-page`. Ersetzt Leonies lokale Browser-Notizen (`feat/twin-notes`): Notizen liegen auf dem Server, mit Zeit. Foto-Knopf, Protokoll und Prüfrunde kann Leonie darauf aufsetzen.
- 3D-Look: Plan `docs/specs/3d-look.md`. Wird von Jennifers zweiter Sitzung gebaut (Ordner `ui-polish`, Licht, Boden, Wände, Möbel), nicht von einem weiteren Agenten.
- **Prüfrunde: Spec `docs/specs/inspection-round.md`.** Leonie, bitte `feat/twin-round` und `feat/agent-plan-round` gleich nach dem Aufwachen pushen (spätestens 9:00, Weg A). Sonst baut Jennifers Sitzung den Server-Teil selbst (Weg B). Zwei Startknöpfe: Vorschlag A (Routenkarte während der Runde ausblenden).
- Leonies lokale Branches (`feat/twin-round`, `feat/agent-plan-round`, `feat/twin-notes`) sind nicht gepusht; bitte pushen, bevor du weiterbaust.

## Für Leonies 3D-Look (Jennifers Test 02:50)
- Boden in 3D: das Punkteraster füllt bei flachem Blick die halbe Fläche bis zum Horizont und wirkt unruhig. Besser: sehr blasses Raster, das mit der Entfernung ausblendet, oder einfarbiger Boden.
- Kippen begrenzt auf etwa 55 bis 60 Grad und weit entfernte Etiketten ausblenden: macht `fix/twin-trackpad` (Kamera, kleine Änderung in Labels.tsx).
- Fadenkreuz des Tipp-Pins kürzer: macht `fix/twin-pin-label`.

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

## Leonie: Prüfrunde ist gepusht (Weg A aus `docs/specs/inspection-round.md`)
Branch **`feat/inspection-round-and-notes`** (auf aktuellem `main`, 822dc44) enthält alles in einem:
- `feat/twin-round`: Seite, Runde planen/zeichnen, Station für Station, "Try a door" (Demo-Link: `#round=fire%20extinguisher&area=Ground%20floor&building=train/proc-factory-train-015&door=proc-factory-train-015-F0-S002,proc-factory-train-015-F0-S016`, 5 Stopps, 100 m → 62 m).
- `feat/agent-plan-round`: Werkzeug `plan_round` (`building_agent/round_tools.py`, eine Zeile in `tools.py`, eine Prompt-Regel in `agent.py`), 15 Unit-Tests, `tests/live/test_round.py`, Review-Agent ohne Blocker. Live: "Inspection round: all fire extinguishers on the ground floor. I start at the entrance in Main aisle H-B3." → ein Aufruf, 6,5 s, 99,1 m (Seite sagt 100 m, Start Raummitte statt Eingangspunkt).
- `feat/twin-notes`: Notizen/Probleme mit Foto als Fakten nach `docs/specs/place-knowledge.md`, nutzt automatisch `/api/facts` (sonst IndexedDB), Pins, Verlauf, Vorlesen beim Begleiten, Einsatzprotokoll.
- Hey Wanda in `handsFree.ts`: "done/erledigt" hakt die Station ab, "how many left", "note:/merk dir:", "problem:", "what's here", "finished/fertig" (Protokoll).
Noch offen vor `main`: `scripts/check.sh` auf ruhigem Rechner (einziger roter Test war `test_impact.py::test_sweep_over_all_buildings` mit 117 s statt 90 s unter Last), volle Live-Suite, Testantworten byte-gleich, Entscheidung A zu zwei Startknöpfen (`inRound()` aus `twin/src/round/round.ts` in `ui/Card.tsx`). Sprach-Notizen speichern heute direkt (ohne Karte und Ja); sobald `remember_here` (K2) da ist, kann der Notiz-Teil des Einhängers raus.

## Jennifer, Sonntag 03:45: `feat/twin-desktop-flow` (belegt)
1. **Laptop: Chat als Seitenleiste links** (nur Profil `planner`, Handy unverändert): Eingabe oben, Verlauf immer sichtbar, Antwort/Route/Begleiten in derselben Spalte, Kamera rahmt mit `--left-inset` im freien Bereich.
2. **Weicher Wechsel 2D ↔ 3D:** Kamera fliegt senkrecht auf den Plan-Maßstab, Wände senken/heben sich, erst dann Kameratausch (unsichtbar). Fast senkrecht kippen rastet 2D ein, Zwei-Finger-Wischen nach oben im Plan geht in 3D.
Dateien: `twin/src/App.tsx`, `twin/src/styles.css`, `twin/src/ui/Omnibox.*`, `twin/src/store.ts` (nur Inset/Übergang), `twin/src/scene/CameraRig.tsx`, `twin/src/scene/Scene.tsx`, `twin/src/scene/FloorMesh.tsx`. `Card.tsx` und `Walk.tsx` nur CSS-seitig, damit Leonies Runde sauber drauf passt.

## Leonie, Sonntag ~03:40: neu auf `feat/inspection-round-and-notes` (gepusht)
- Notizen über den echten Server: Speichern wendet `{fact, state}` an, Undo über `/api/facts/undo` (nur neueste Notiz), Fotos als Server-URL, "Fixed/Done" auf dem Server-Weg ausgeblendet (kein Endpunkt für Statuswechsel).
- Runde per Sprache führt Station für Station: `plan_round` merkt sich die Stopps, der Server hängt sie als `state.route.round` an die Route (**kleine Ergänzung in `web/api.py`, bitte kurz ansehen**), die Seite übernimmt sie (`adoptRound()`); "Guide me" und "Hey Wanda, done" gehen Stopp für Stopp. Test: `tests/test_web.py::test_agent_round_carries_its_stops_for_the_page`.
- Notizen ohne Noise: während einer Runde nur Notizen an den Geräten der Runde (an diesem Stopp), bei normalen Routen nur am Ziel; alles andere auf dem Weg bleibt still.
- Für dich gefunden (nicht von uns): `tests/test_selection.py::test_state_view_has_no_edit_keys_without_edits` ist rot, weil `state` jetzt `facts`/`closed_until` enthält; und wieder der 400er "invalid signature in thinking block" bei getippter, dann gesprochener Frage im selben Chat.
- Bekannte Lücken: Rückweg zum Start bei Runden mit Rückkehr wird nicht gelotst; das Einsatzprotokoll zählt während einer Runde nur die erste Etappe.
- Live-Suite für den Branch noch nicht gelaufen (Pflicht vor `main`, weil `round_tools.py` sich geändert hat).

## Leonie an Jennifer (Sonntag ~04:00): zwei Server-Wünsche aus dem Code-Review
1. **Undo per ID:** `POST /api/facts/undo` löscht heute immer die neueste Notiz des Gebäudes. Speichert jemand zwischen "neueste prüfen" und "undo", trifft es dessen Notiz. Bitte `{building, id}` annehmen und nur diese ID zurücknehmen. Unsere Seite prüft bis dahin vorher und nachher.
2. **Eine Rundenplanung statt zwei:** Die Seite (`twin/src/round/order.ts`, nächster Nachbar + 2-opt, bis zu 231 `/api/route`-Aufrufe nacheinander) und der Agent (`plan_round`, exakt bis 8 Stopps) rechnen beide. Vorschlag: kleiner Endpunkt `GET /api/round?key=&type=&area=&start=` ruft dieselbe Funktion wie `plan_round` (Python, deterministisch), die Seite nutzt nur noch den. Dann gleiche Reihenfolge und Zahlen in Chat und Panel, und Planen in Millisekunden statt Sekunden. Wir bauen die Seite darauf um, sobald der Endpunkt da ist (oder wir schreiben ihn, wenn du okay sagst, da `web/` deins ist).
Außerdem: Stil von `ui/Round.css` und `ui/Facts.css` gehört in deine Design-Sitzung (eigene Schriftgrößen und `#004fab` doppelt, gegen `DESIGN.md`).

## ⚠️ Leonie an Jennifer (Sonntag ~04:15): zwei Notizen-Oberflächen, bitte entscheiden
Dein `feat/twin-knowledge-page` und unser `feat/inspection-round-and-notes` (bzw. dein `integrate/round`) bauen beide eine Notizen-Oberfläche, **mit denselben Dateinamen**: `twin/src/ui/Facts.tsx` und `ui/Facts.css` gibt es in beiden (unsere Session hat ihre Dateien nach deiner Spec so benannt). Beim Merge kracht das, und zwei UIs für eine Funktion wollen wir nicht.
Was jede Seite hat:
- **Deine** (`ui/Facts.tsx`, `factsStore.ts`, `NoteHere.tsx`): eigene Wissensseite, Notiz hier, Foto aus der Chat-Antwort öffnen (`open_photo`), Schalter nur wenn es etwas gibt, e2e-Test.
- **Unsere** (`twin/src/notes/notes.ts` + `notesStore.ts`, `ui/Facts.tsx`, `ui/Report.tsx`, `scene/FactPins.tsx`): Speicher-Schnittstelle (`/api/facts`, sonst IndexedDB), Pins an Raum/Gerät, **Vorlesen beim Lotsen** ("Night shift left a note here"), **Filter ohne Noise** (in einer Runde nur Notizen an den Geräten bzw. im Raum der aktuellen Station, sonst nur am Ziel), **Einsatzprotokoll** ("finished"), Sprachbefehle in `handsFree.ts` ("note:", "problem:", "what's here", "finished").
**Vorschlag:** deine Oberfläche (Seite, Notiz hier, Fotos) bleibt; unsere Logik-Teile bleiben (Vorlesen beim Lotsen, Filter, Protokoll, Sprachbefehle) und nutzen deinen `factsStore` statt unseres `notesStore` für die Daten. Unsere `ui/Facts.tsx` fällt weg. Wer führt zusammen? Leonies Session kann das machen, wenn du sagst, welcher Stand die Basis ist.
Außerdem: dein `integrate/round` endet bei unserem `a33fefa`. Danach kamen noch `ceada75` (Filter ohne Noise) und gleich die Runden-Fixes (Protokoll über die ganze Runde, Raum-Notizen an der Station, Ja vor "Try a door", Sperre bei doppeltem "Done", "how far" für Station und Runde, Rückweg zum Start). Die bringen wir auf `feat/inspection-round-and-notes`, bitte von dort nachziehen.

## Jennifer an Leonie (Sonntag ~04:35): erledigt, auf `main`
- **Notizen: Basis ist eure Version** (schon in `main` über die Runde, getestet). `feat/twin-knowledge-page` wird nicht gemergt. Wenn eure Session Zeit hat: "Notiz hier" und Foto aus der Chat-Antwort (`open_photo`) aus meinem Branch auf euren `notesStore` übertragen, sonst bleibt es weg.
- **Undo per ID:** `POST /api/facts/undo {key, id}` nimmt genau diese Notiz zurück (unter 2 Minuten). `ServerFacts.undo` schickt die ID schon, der Vorab-Check ist raus.
- **Rundenplanung auf dem Server:** `POST /api/round {building, type, area?, start?, return_to_start?, step_free?}` ruft dieselbe `plan_round` wie der Agent und zeichnet die Runde mit `state.route.round`. Antwort `{round: {ok, stops, total_m, info, route, ...} | {ok: false, error}, state}`. `area` versteht "Ground floor", "Level 1", Etagennamen, "all" und Raumbereiche wie `plan_round`. Test: `tests/test_web.py::test_round_endpoint_plans_like_the_agent_and_draws_the_round`. Die Seite (`round.ts`) könnt ihr jetzt darauf umstellen.
- `ceada75` (Notizen ohne Noise) ist in `main`. `test_selection` ist wieder grün.
- Euer Stil in `ui/Round.css` und `ui/Facts.css` geht an die Design-Sitzung.

## Leonie an Jennifer (Sonntag ~04:45): bitte prüfen, leere Karte beim Laden
Im Browser-Fenster von Leonies Sitzung bleibt die 3D-Karte nach dem Laden leer (Chrome/Leiste, Knöpfe, Routenkarte sind da), das Gebäude erscheint erst nach einem Klick oder Scroll in die Karte. Gesehen auf `main`-Stand mit `?building=train/proc-factory-train-015` bei 1440×900, zweimal. **Vorbehalt:** das Fenster war dabei im Hintergrund, dort drosselt der Browser das Zeichnen; es kann also ein Artefakt sein. Bitte einmal in einem normalen Chrome-Tab und am iPhone ohne Antippen prüfen (frameloop "demand": nach dem Laden bzw. nach "Etage steigt aus dem Boden" ein `invalidate()`?). Fürs Video kritisch, weil die Karte beim Öffnen sofort da sein muss.
**Rundenplanung:** Leonies Sitzung stellt `twin/src/round/round.ts` jetzt auf `POST /api/round` um (Danke!) und entfernt die Rechnung in `order.ts`.
