# Übergabe an Leonies Agenten (Sonntag 25.10.2026, 08:25)

Von Jennifers zweiter Sitzung (`synera-agent-bd`). Lies zuerst `CLAUDE.md`, dann diese Datei, dann den letzten Abschnitt von `docs/WORK_IN_PROGRESS.md`. Freeze 13:00.

## 1. Urban Colab (`user/plan-89323a15`): Geometrie aufgeräumt
Branch **`fix/mucl-geometry`** (gepusht). Ändert nur `demo/buildings/plan-89323a15/building.json`, neu ist `tests/test_demo_buildings.py`. **Gemergt auf `main`** (Geometrie und englische Raumnamen, 25.10. ~09:10).

Was sich geändert hat:
- Überlappungen weg (vorher EG 9 Raumpaare, 1. OG 8). Flure und Hallen sind gerade Rechtecke, Räume sind aus ihnen herausgeschnitten, keine Löcher.
- Schräge Kanten und das Fünfeck an Flur Nord gerade gezogen.
- Ausgänge wie auf dem Fluchtplan E.05: jetzt 8 (5 Süd, 2 Nord, 1 Nordost), vorher 2. Die ersten zwei Einträge sind unverändert, **der erste Ausgang liegt weiter in South Corridor (vorher Flur Süd)** (`demo_seed.py` startet dort).
- Türen wie auf dem Plan: Project Room hat die Doppeltür in der Westwand und eine Tür zum Bereich vor dem Foyer; die Treppe öffnet nach Norden zum Flur (nicht zur Außenwand); der grüne Fluchtweg ist zum Foyer offen (zwei breite Öffnungen). Jede Tür liegt auf der Wand, die ihre zwei Räume teilen.
- **Alle Raum-, Tür- und Geräte-IDs bleiben gleich.** Neue Ausgänge und Türen haben neue IDs (`…-F0-O0100` ff.), hinten angehängt. Ein Feuerlöscher (`A00010`) lag außerhalb jedes Raums und ist um wenige Zentimeter in Flur Nord gerückt.

Zahlen danach (für Drehbuch und Pitch neu nehmen):
| Route | vorher | jetzt |
|---|---|---|
| Project Room → Foyer | 55,8 m | 17,5 m |
| Flur West → Treppe Mitte | 26,1 m (durch ELT, EDV, Umkleide) | 14,3 m (Flur West, Flur Süd, Treppe) |
| Café → Seminar Rooms 1-3 | 77,4 m | 65,5 m |
| Feuerlöscher-Runde EG ab South Corridor | 7 Stopps, 106 m | 8 Geräte, 7 Stopps, 81,6 m |

Geprüft: `scripts/preflight.py demo/buildings/plan-89323a15` 25 OK, 5 WARN, 0 FAIL (WARN: zwei Lufträume ohne Tür, absichtlich; neue Typen `hall`, `outdoor`, `first_aid_kit`, `manual_call_point`). Dein `tests/test_demo_urban_colab.py` (aus `feat/demo-urban-colab-prep`) 2 von 2 grün gegen die neue Datei. Neuer Test `tests/test_demo_buildings.py` (keine Überlappung, keine Löcher, Türen auf gemeinsamen Wänden, Ausgänge an Außenwänden, Geräte in ihrem Raum) 4 von 4 grün, schlägt auf dem alten Stand an.

Nach dem Merge auf einem Rechner mit schon installiertem Gebäude: das Install-Skript überschreibt nie. Einmal die alte Kopie entfernen und neu installieren:
```
rm -rf agent_output/buildings/plan-89323a15 && scripts/install_demo_buildings.sh
```
Danach `POST /api/reset` für das Gebäude oder den Server neu starten.

Bekannte Grenzen: Der Westflügel (Arbeitsbereich, CAD-Center) steht nur im 1. OG, weil der EG-Plan ihn nicht zeigt; 2. bis 4. OG und Untergeschoss fehlen (Fotos liegen bei Jennifer).

### Englische Raumnamen (IDs gleich)
Wanda spricht Englisch, die Schilder im Haus sind englisch. Umbenannt: Flur Süd/West/Nord/Ost → South/West/North/East Corridor, Treppe Mitte → Main Stairs, Treppe West → West Stairs, Lager → Storage by the Lift / Storage Foyer / Storage North / Storage (1. OG), Umkleide → Changing Room West/East, WC → Toilets, EDV → IT Room, ELT-Verteiler → Electrical Room, Putzraum → Cleaning Room, Müll → Waste Room, Büro → Office, Café (Gastraum) → Café, Teeküche → Kitchenette, Terrasse → Terrace, Luftraum → Void, Projektraum West → Project Room West, Arbeitsbereich → Work Area, Living Lab Einzelhandel → Retail Living Lab, Flur 1. OG → First Floor Corridor. **Drehbuch und Demo-Sätze bitte auf die neuen Namen umstellen** (Start der Runde heißt jetzt "South Corridor").

## 2. Heute schon auf `main` (von dieser Sitzung)
- `feat/twin-walk-hint`: Beim ersten Schritt der Führung einmal "Walk with me?" mit "Turn on" und ×, nur auf Handys mit Bewegungssensoren; ersetzt den Schalter, bis die Frage beantwortet ist (`twin/src/walkWithMe.ts`, `ui/Walk.tsx`).
- `feat/twin-guide-calm`: Guide-Sheet ohne eigene Sprachknöpfe (die Wanda-Leiste ist der eine Ort für Stimme), Kopfzeile einzeilig "Step 1/7 · 56 m left". `test_voice_followup.py` prüft jetzt: keine Sprachknöpfe in `.card-walk`.
- `feat/demo-urban-colab`: Urban Colab als Demo-Gebäude in `demo/buildings/`, `scripts/install_demo_buildings.sh`.
- Pläne in `docs/specs/`: `swipe-tilt.md` (gebaut von Jennifers Hauptsitzung), `wanda-fairy.md`, `chat-sidebar.md`, `osm-map.md`. Die letzten drei sind **nicht** für vor dem Freeze gedacht, eher "next steps" im Pitch.

## 3. Offen und wer es hat
| Punkt | Wer |
|---|---|
| Graue Bodenfläche in 3D (Boden spannt über beide Etagen, Westflügel nur im 1. OG): Boden auf die gezeigte Etage begrenzen (`Scene.tsx`) | Jennifers Hauptsitzung |
| Bereichsnamen in der weitesten Zoomstufe am Handy falsch ("Logistics" am Project Room, "Social" an WCs) | Jennifers Hauptsitzung |
| `POST /api/round` ohne `start` gibt 500 (`'NoneType' object has no attribute 'strip'`); Seite und Test übergeben immer einen Start | Jennifers Hauptsitzung |
| Wanda-Leiste: roter Auflegen-Knopf und separater Hands-free-Knopf weg, Stummschalten beim Gehen im Orb | Jennifers Hauptsitzung (`fix/twin-start-and-bugs`) |
| Desktop: in 3D Ziehen = drehen und kippen, fast senkrecht loslassen = 2D (heute nur Strg plus Ziehen, ohne Wechsel nach 2D) | vorgeschlagen, noch nicht beauftragt |
| Drehbuch und Pitch-Zahlen auf die neue Urban-Colab-Geometrie umstellen | Leonie |
| Volle Prüfung vor dem Freeze (check.sh, Live-Suite, Browser-Tests, Antworten byte-gleich, Tag `known-good`) | Jennifers Hauptsitzung |

## 4. Regeln, die heute Nacht wichtig waren
- Nie zwei Agenten im selben Ordner; jede Aufgabe in einem eigenen Worktree und Branch.
- Merges nach `main` nur mit grünem `scripts/check.sh`; bei Änderungen an Prompt, Tools, Stimme oder Chat auch die Live-Suite.
- Unter hoher Rechnerlast fallen die drei Geschwindigkeits-Tests (Sweep über alle Gebäude, `test_huge_building_is_fast`) aus; einzeln bei ruhigem Rechner nachprüfen, bevor man sie für echt hält.
- Abstimmung zwischen Jennifers und Leonies Sitzungen läuft über `docs/WORK_IN_PROGRESS.md` (kurzer Abschnitt mit Uhrzeit, wer an wen).

## 5. Synera zur Sonntags-Aufgabe (Discord, Bhushan Kotnis, 07:11 bis 09:04)
- Die "Build"-Aufgabe ist **dieselbe Aufgabe mit denselben Eingaben** wie die Beispiele (Bilder plus `building.json` im Kit-Format), nur auf einem **neuen Gebäude**. Gemessen wird über die Antworten auf ähnliche Fragen, getrennt gewertet.
- Zweck laut Synera: **Overfitting prüfen**. Folge für uns: nichts auf Test-Gebäude abstimmen (tun wir nicht, siehe `CLAUDE.md` "No hard-coding"), und unser Plan-Upload (Level 4) wird für die Wertung nicht gebraucht, er bleibt Demo.
- Vor dem Freeze sinnvoll: `scripts/preflight.py <neues_gebäude>` und die Abgabe-Pipeline (`building_agent.submission`) einmal auf einem Dev-Gebäude als "fremdes Gebäude" durchspielen.
