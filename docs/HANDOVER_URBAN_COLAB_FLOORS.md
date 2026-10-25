# Übergabe an Leonies Agent: alle Etagen des Urban Colab bauen

Stand: Sonntag 25.10.2026, 09:35. Von Jennifers Sitzung `synera-agent-bd`. Freeze 13:00.
Auftrag von Jennifer: **alle fotografierten Fluchtpläne müssen ins Gebäude**, nicht nur EG und 1. OG.

Lies vorher: `CLAUDE.md`, `docs/HANDOVER_JENNIFER_TO_LEONIE.md` (was am Urban Colab schon passiert ist).

## 1. Ausgangslage
Gebäude: `demo/buildings/plan-89323a15/building.json` (Key `user/plan-89323a15`), installiert wird es mit `scripts/install_demo_buildings.sh` nach `agent_output/buildings/` (überschreibt nie: vorher `rm -rf agent_output/buildings/plan-89323a15`).
Heute drin: **EG (aus E.05) und 1. OG (aus OG1.06)**, aufgeräumt, englische Raumnamen, 8 Ausgänge, 24 Geräte. Tests grün: `tests/test_demo_buildings.py`, `tests/test_demo_urban_colab.py`.

Alle Fotos liegen jetzt im Repo: `demo/plans/urban-colab/photos/` (Originale), `demo/plans/urban-colab/crops/` (nur der Grundriss, vergrößert, so wie sie in den Plan-Leser gehen).

| Foto | Plan | Inhalt | Status |
|---|---|---|---|
| `E05_ground_floor` | E.05 | EG Mitte und Ost: Foyer, Arena, Café, WCs, Project Rooms | **gebaut** |
| `E05_ground_floor_dark_duplicate` | E.05 | dasselbe, dunkles Foto | nicht nötig (Duplikat) |
| `E06_ground_floor_west` | E.06 | EG West: zusätzlich Gefahrstofflager, WC, Handwaschraum, WC, NW-Treppe, Kühlung-Gang | **offen**: an F0 anfügen |
| `OG1-06_floor1` | OG1.06 | 1. OG | **gebaut** |
| `OG3-08_floor3_west` | OG3.08 | 3. OG West: 5 Büros, NW-Treppe, 4 Think Tanks, Terrasse, Luftraum, offener Bürobereich, Küche, Putzraum, EDV | **offen** |
| `OG3-04_floor3_east` | OG3.04 | 3. OG Ost: Küche, 5 Besprechungsräume, Putzraum, EDV, ELT, 3 WC, Aufzug, Haupttreppe, offener Bürobereich, Terrasse, Luftraum, 2 Think Tanks | **offen** |
| `OG4-04_floor4` | OG4.04 | 4. OG: Küche, Aktivraum/Bib, 4 Besprechungsräume, EDV, ELT, 2 WC, Aufzug, Haupttreppe, Terrasse, Luftraum, Think Tank, offener Bürobereich | **offen** |
| `U02_basement` | U.02 | Untergeschoss: Tiefgarage, Treppenkern, Aufzug, Serverräume, BMA, BOS Funk, 3 Lager, NSHV | **offen** |
| `wayfinding_sign_not_a_plan` | - | Wegweiser-Schild, kein Grundriss | nicht nötig |

**Kein Foto vom 2. OG.** Nicht erfinden; Etage 2 fehlt einfach (Aufzug und Treppe verbinden 1 mit 3, die Höhe kommt aus `elevation_m`).

## 2. Ziel
In `building.json` zusätzlich: Etage `B1` (level -1, "Basement"), F0 um den Westteil aus E.06 ergänzt, `F3` (level 3, "Floor 3", aus beiden OG3-Hälften), `F4` (level 4, "Floor 4"). Jede neue Etage mit Räumen, Türen, Aufzug und Haupttreppe in den bestehenden `vertical_connectors` (V01 Lift, V02 Treppe), Feuerlöschern und Druckknopfmeldern als Assets. Alles auf Englisch benannt. Danach Tests und Preflight grün, Merge nach `main`.

## 3. Arbeitsweise, die heute funktioniert hat
1. **Eigener Worktree und Branch** (`feat/mucl-all-floors` von `main`). `building.json` vorher sichern (Kopie im Scratchpad).
2. **Plan lesen mit dem Plan-Leser** (Level 4, kostet ca. 0,03 $ pro Etage, nutzt den API-Key aus `.env`). Eigener Server, nicht die Vorschau auf 8815:
   ```
   uv run --env-file .env python -m web --host 127.0.0.1 --port 8821 --data data
   U=http://127.0.0.1:8821; O="Origin: $U"
   curl -s -X POST -H "$O" -H "Content-Type: image/jpeg" --data-binary @demo/plans/urban-colab/crops/OG4-04_floor4.jpg $U/api/level4/upload
   curl -s -X POST -H "$O" -H "Content-Type: application/json" -d '{"name":"x","floors":[{"upload_id":"plan-…","level":4,"known_length_m":47,"along":"building_width"}]}' $U/api/level4/build
   curl -s $U/api/level4/status      # bis state != running
   curl -s $U/api/level4/preview     # draft.spaces, draft.openings in Metern
   ```
   - **Maßstab:** "door" als Lineal geht nicht (Fluchtpläne haben keine Türmaße). `building_width` mit Schätzung, dann über bekannte Größen korrigieren (siehe 4.).
   - Der Leser findet Räume gut, **Türen schlecht** (bei E.05 hatten 34 von 41 Räumen keinen Ausgang). Türen nach dem Foto selbst setzen.
   - `POST /api/level4/fix` kann nur `add_door`, `remove_door`, `set_room_type`, `set_scale` (kein `outside`, kein Umbenennen). Für Ausgänge, Namen und Geometrie direkt `building.json` bearbeiten (Python-Skript, reproduzierbar).
   - Den Entwurf **nicht** über `/api/level4/save` als neues Gebäude speichern, sondern die Räume aus `preview.draft` in das bestehende `plan-89323a15` übernehmen (Etagen-ID und Raum-IDs umschreiben, z. B. `plan-89323a15-F4-S001`).
3. **In den Rahmen des Gebäudes bringen** (wichtigster Schritt): Ähnlichkeitstransformation (Maßstab plus Verschiebung, keine Drehung, alle Pläne haben dieselbe Nordrichtung) aus zwei Ankern, die auf jeder Etage an derselben Stelle stehen:
   - **Aufzug** Mitte: F0 (11.24, 19.25), F1 (11.55, 19.06). Im Plan das Kästchen mit dem X.
   - **Haupttreppe** (zweiläufig, neben dem Aufzug, unter dem grünen Flur): F0 x 0.52..9.02, y 11.88..14.88; F1 x 0.19..9.34, y 11.88..14.88.
   - OG3.04 und OG4.04 haben beide Anker. **OG3.08 hat keinen Aufzug**: mit OG3.04 über die gemeinsame **Terrasse** und den **Luftraum** zusammensetzen (beide Pläne zeigen sie), danach mit den Ankern von OG3.04 ausrichten. Doppelte Räume aus der Überlappung nur einmal übernehmen.
   - E.06 hat Aufzug, Lager neben dem Aufzug und die Haupttreppe wie E.05: ausrichten und **nur die Räume westlich vom bestehenden F0** übernehmen (Gefahrstofflager, WC, Handwaschraum, WC, NW-Treppe, Teile von Projektraum West). Bestehende Räume und IDs von F0 nicht ersetzen.
   - UG: Aufzug und Treppenkern (grün, mit Notausgang-Pfeil) als Anker; vorher am Übersichtsplan unten rechts prüfen, ob es derselbe Kern ist.
4. **Maßstab prüfen** mit bekannten Größen: offizielle Flächen (munich-urban-colab.de/en/event-spaces): Project Room 141 m², Foyer 281 m² (mit Auditorium 330), Seminarräume 144 + 88 + 91 m², Innovation Lab 124 m². Aufzug ca. 2,5 × 3,5 m. Eine Etage ist ca. 47 m breit (Mittelteil) plus Westflügel.
5. **Geometrie säubern** (das hat die Zickzack-Routen beseitigt), Vorlage: `demo/plans/urban-colab/tools/fix_geometry_EG_OG1_reference.py` (schon angewendet, **nicht** auf die aktuelle Datei laufen lassen, nur als Muster):
   - Flure und Hallen als Rechtecke (Vereinigung von Boxen) neu definieren, dann alle Räume herausschneiden (`difference`), Rest-Überlappungen gehen an den kleineren Raum.
   - **Keine Löcher**: liegt ein Raum mitten im Flur, muss er einen anderen Raum oder den Rand berühren (sonst entsteht ein Loch, das Format kennt keine Löcher). Kanten exakt aufeinander setzen, nicht nur fast.
   - Jede Tür auf die gemeinsame Wand der zwei Räume schieben (`nearest_points` auf `boundary ∩ buffer`), Ausgänge auf die Außenwand.
   - Fluchtweg (grün) ist zu Foyers und offenen Bereichen oft offen: dann eine breite `opening` statt Tür.
6. **Prüfen nach jeder Etage**:
   ```
   uv run python demo/plans/urban-colab/tools/draw_floors.py demo/buildings/plan-89323a15/building.json <scratchdir>   # PNG pro Etage, listet Überlappungen
   uv run python scripts/preflight.py demo/buildings/plan-89323a15 --data data
   uv run pytest -q tests/test_demo_buildings.py tests/test_demo_urban_colab.py
   ```
   Dazu ein paar Routen über `/api/route` (Feld `space_path` zeigt die Raumfolge): z. B. Café → ein Besprechungsraum im 3. OG, Basement Lager → Foyer. Keine Route darf durch Technikräume (EDV, ELT, Putzraum) laufen.

## 4. Regeln, die nicht brechen dürfen
- **Bestehende IDs bleiben** (Räume, Türen, Geräte von F0 und F1). `scripts/demo_seed.py` und `tests/test_demo_urban_colab.py` hängen daran. **Der erste Ausgang in `openings` bleibt der in South Corridor** (`…-F0-O0021`): der Demo-Start. Neue Einträge hinten anhängen.
- IDs eindeutig, keine verlorenen IDs (vorher/nachher vergleichen).
- Neue Räume englisch benennen (Liste der bisherigen Übersetzungen: `demo/plans/urban-colab/tools/english_names_reference.py`). Besprechung → Meeting Room 3.01 … (fortlaufend pro Etage), Büro → Office, Küche → Kitchen, Think Thank → Think Tank, offener Bürobereich → Open Office, Aktivraum/Bib → Activity Room / Library, Tiefgarage → Car Park, Serverraum → Server Room, NSHV → Main Switchboard, BMA → Fire Alarm Panel, BOS Funk → Emergency Radio.
- Raumtypen wie bisher (`room`, `corridor`, `hall`, `stair`, `lift`, `outdoor`); Luftraum = `outdoor`, ohne Tür (Preflight-Warnung ist dann normal).
- Geräte: Feuerlöscher `fire_extinguisher`, Druckknopfmelder `manual_call_point`, Erste Hilfe `first_aid_kit`, Defibrillator nur EG Empfang. Position dort, wo das Symbol im Plan an der Wand hängt; `space_id` = Raum, in dem der Punkt liegt (Test prüft das).
- `vertical_connectors`: V01 (Lift) und V02 (Treppe) um die neuen Etagen erweitern (`floor_ids` und `space_ids` in Etagenreihenfolge). Weitere Treppen (NW-Treppe) als eigener Connector nur, wenn sie auf mehreren Etagen nachweislich übereinander liegen.
- `building.source_ref.floors_aligned` bleibt `true` (sonst verweigert `room_stacked`).
- Merge nach `main` nur mit grünem `scripts/check.sh`. Achtung: unter hoher Last fallen Laufzeit-Tests aus (`test_impact.py::test_sweep_over_all_buildings`, `test_routing.py::test_runtime_on_largest_building`, `test_routing_tours.py::…largest_building`); einzeln bei ruhigem Rechner nachprüfen.
- Danach die 8815-Vorschau neu installieren (siehe oben) und Zahlen im Drehbuch prüfen.

## 5. Reihenfolge und Zeit (Vorschlag)
1. OG4 (ein Plan, beide Anker) ca. 30 bis 40 Min, gut zum Einspielen des Ablaufs.
2. OG3 aus zwei Hälften ca. 60 Min.
3. EG West aus E.06 ca. 40 Min (behebt auch die graue Bodenfläche in 3D unter dem Westflügel).
4. Untergeschoss ca. 40 Min.
Nach jeder Etage committen und pushen, damit nichts verloren geht. Wenn die Zeit knapp wird: lieber eine Etage sauber als vier halb.

## 6. Ansprechpartner
Fragen zu dieser Datei oder zum Ausrichten: Notiz in `docs/WORK_IN_PROGRESS.md` (Jennifers Sitzungen lesen dort mit).
