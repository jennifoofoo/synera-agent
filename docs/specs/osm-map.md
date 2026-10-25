# Spec: Straßenkarte unter dem Gebäude (OpenStreetMap)

Stand: 25.10.2026, analysiert auf main bcf5152. Noch nicht bestätigt, nicht gebaut.

## Ziel
Hat ein Gebäude einen echten Ort, liegt unter dem 3D-Modell und dem 2D-Plan eine blasse Straßenkarte: Straßen, Grün, Nachbargebäude. Dazu kommt ein Knopf "Open in Google Maps" für den Weg dorthin. Gebäude ohne Ort sehen genau aus wie heute. Kein Ort wird geraten.

## Ausgangslage (Analyse)
1. **Welche Gebäude einen Ort haben:**

   | Herkunft | Anzahl | Ort |
   |---|---|---|
   | `osm_indoor` | 17 | ja, `building.source_ref.osm` = OSM-Way-ID |
   | Urban Colab (`user/plan-89323a15`) | 1 | ja, Koordinaten 48.1566, 11.5515 (Google-Maps-Link der offiziellen Seite) |
   | `swiss_dwellings`, `resplan`, `procedural` | 263 | nein |

2. **OSM-Gebäude passen ohne Drehung.** Geprüft an `test/osm-way43035346` ("N8", Theresienstraße 90): Ausdehnung im Kit 39,1 × 45,7 m, echter OSM-Umriss 39,1 × 45,9 m. Die Kit-Koordinaten sind nordausgerichtete Meter, es fehlt nur der Versatz. Kit-`attribution` nennt schon "© OpenStreetMap contributors (ODbL)".
3. **Urban Colab:** Es ist nur ein Ausschnitt jeder Etage, und der Nordpfeil der Fluchtpläne steht schräg. Drehung und Versatz müssen einmal von Hand eingestellt werden, am Übersichtsplan (Tonnenhalle im Norden, Freddie-Mercury-Straße im Osten, Dachauer Straße im Süden).
4. **Kit-Daten nicht ändern:** `data/` ist Kit-Code. Ortsangaben gehören in eine eigene Datei.
5. **Kein Hard-Coding:** Der Weg über die OSM-Way-ID funktioniert für jedes `osm_indoor`-Gebäude, auch für ein neues am Sonntag.

## Design
**Ort bestimmen (Python, deterministisch, neu `building_agent/geo.py`):**
- `osm_indoor`: Way über die OSM-API holen (`/api/0.6/way/<id>/full.json`). Daraus Mittelpunkt, Adresse (`addr:street`, `addr:housenumber`) und Umriss. Den Versatz berechnet man aus dem Abgleich Kit-Mittelpunkt gegen OSM-Mittelpunkt, Drehung 0.
- Gebäude aus dem Plan-Upload: optionale Datei `geo.json` im Gebäudeordner (`lat`, `lon`, `rotation_deg`, `address`). Fürs Urban Colab legen wir sie in `demo/buildings/plan-89323a15/geo.json` an.
- Alles andere: kein Ort, `geo = null`.
- Ergebnis wird zwischengespeichert in `agent_output/geo/<key>.json`. Ein Netzaufruf pro Gebäude, danach offline.

**Karte als Bild, einmal vorbereitet (kein Live-Kartendienst in der Demo):**
- Skript `scripts/bake_map.py <key>`: lädt die Kacheln rund um das Gebäude (etwa 300 × 300 m, Zoom 18), setzt sie zu einem PNG zusammen und speichert Bild plus Grenzen in Metern nach `agent_output/geo/<key>.png` und `.json`.
- Kartenstil hell und ruhig: CARTO Positron (`light_all`) oder OSM Standard. Beides frei mit Namensnennung. Bei wenigen Abrufen passt das zu den Nutzungsregeln, und wir laden ja nur einmal pro Gebäude.
- Google-Maps-Kacheln nicht verwenden: Sie brauchen einen API-Schlüssel mit Abrechnung, und die Bedingungen verbieten fremde 3D-Inhalte darüber.
- Vorteil: Die Demo funktioniert auch ohne WLAN, und die Seite lädt nichts von außen.

**Server (`web/api.py`):**
- `GET /api/building` liefert zusätzlich `geo: {lat, lon, address, map: {url, bounds_m}} | null`.
- `GET /api/geo/map?key=` liefert das gebackene PNG.

**Seite (`twin/`, Design-Sitzung):**
- 3D: eine Bodenfläche mit dem Kartenbild als Textur, knapp unter dem Erdgeschoss, blass (Deckkraft etwa 0,5, entsättigt). Ersetzt die heutige leere Bodenfläche nur, wenn `geo` da ist.
- 2D: dasselbe Bild hinter dem Plan.
- Namensnennung klein unten links: "© OpenStreetMap contributors" (bei CARTO zusätzlich "© CARTO").
- Knopf "Open in Google Maps" in der Gebäudeleiste oben (nur mit `geo`): öffnet `https://www.google.com/maps/search/?api=1&query=<lat>,<lon>`.
- Keine Läden, keine Haltestellen, keine weiteren Ebenen.

**Wanda (optional, später):** `where_is_building` antwortet mit der Adresse und dem Google-Maps-Link, wenn `geo` da ist. Nur mit Live-Suite.

## Akzeptanzkriterien
1. `test/osm-way43035346` ("N8"): `geo.address` ist "Theresienstraße 90". Der OSM-Umriss deckt sich mit dem Kit-Grundriss, Abweichung höchstens 1 m an den Ecken.
2. Ein `swiss`-, ein `resplan`- und ein `proc`-Gebäude: `geo` ist `null`, die Seite sieht pixelgleich aus wie vorher.
3. Urban Colab: Die Karte liegt so darunter, dass Tonnenhalle im Norden und Freddie-Mercury-Straße im Osten liegen. Das prüft Jennifer einmal per Screenshot.
4. Ohne Netz: Ist die Karte einmal gebacken, startet die Seite mit Karte, ohne Aufruf nach außen.
5. Namensnennung ist sichtbar, wenn die Karte da ist.
6. "Open in Google Maps" öffnet die richtigen Koordinaten.
7. Bestehende Tests grün: `test_mobile`, `test_no_overlap`, `test_twin_controls`, `test_semantic_zoom`, dazu `scripts/check.sh`, Typecheck, Build.

## Testfälle
- **Unit `tests/test_geo.py`** (ohne Netz, OSM-Antwort als Fixture): Versatz und Adresse für N8, `null` für Nicht-OSM-Gebäude, `geo.json` wird gelesen.
- **Unit:** Umriss-Abgleich, Kit-Ecken gegen OSM-Ecken nach Versatz unter 1 m.
- **E2E `tests/e2e/test_osm_map.py`:** N8 hat die Bodenfläche mit Karte und die Namensnennung. Ein `swiss`-Gebäude hat beides nicht. Der Google-Maps-Link hat die richtige Adresse.

## Dateien
- `building_agent/geo.py` (neu), `tests/test_geo.py` (neu)
- `scripts/bake_map.py` (neu)
- `web/api.py`: `geo` in `/api/building`, Route für das Kartenbild
- `twin/src/scene/GroundMap.tsx` (neu), eine Zeile in `Scene.tsx`, Knopf in `TopBar.tsx`, Typ in `api/types.ts`
- `demo/buildings/plan-89323a15/geo.json` (neu)
- `tests/e2e/test_osm_map.py` (neu)

## Aufwand
- Python `geo.py` mit Tests: 40 min
- Karte backen: 30 min
- Server: 15 min
- Seite (Bodenfläche, 2D-Hintergrund, Namensnennung, Knopf): 45 min
- Urban Colab ausrichten: 15 min
- E2E und volle Suite: 30 min

Gesamt etwa 3 Stunden. Kleinste sinnvolle Version: nur der Knopf "Open in Google Maps" mit Adresse, etwa 30 min, ohne Karte.

## Reihenfolge und Zuständigkeit
- Python und Server (`geo.py`, `bake_map.py`, `web/api.py`): Funktions-Agent in eigenem Worktree, Branch `feat/osm-map` von main.
- Seite (`GroundMap.tsx`, TopBar-Knopf): Design-Sitzung, weil es den Look betrifft.
- `web/api.py` ist geteilter Code: vor dem Merge ein Review-Agent ohne Vorwissen.

## Risiken
- **Zeit bis zum Freeze:** 3 Stunden plus Merge sind knapp. Die Knopf-Variante ist sicher.
- **Kachel-Nutzungsregeln:** einmal backen, nicht live laden, Namensnennung immer zeigen.
- **Urban Colab ungenau:** Nur Ausschnitte der Etagen, Ausrichtung per Hand. Als Hintergrund reicht das, für Wege draußen nicht.
- **Optik:** Eine volle Karte lenkt vom Gebäude ab. Deshalb blass, entsättigt und ohne Läden.
- **Sonntags-Gebäude:** Hat es keinen Ort, passiert nichts. Ist es ein OSM-Gebäude, funktioniert es automatisch.
