# Plan: 3D-Look "Architekturmodell" (Leonies Teil, gebaut während sie schläft)

## Ziel
Die 3D-Ansicht soll wie ein ruhiges Architekturmodell wirken (Referenzen: Archilogic, Smplrspace, MapsIndoors 3D), nicht wie graue Klötze. Feedback Aksha: "sieht schlecht aus". Jennifers Test: Punkteboden unruhig, flacher Blick unübersichtlich.

## Bauen (in dieser Reihenfolge, jeweils mit Vorher-Nachher-Screenshots, nach jedem Schritt committen)
1. **Wände:** hell (Papier/Warmweiß), auf etwa 1,2 bis 1,5 m gekappt (Puppenhaus-Schnitt), dünne dunkle Oberkante. Türlücken und Zonengrenzen wie heute.
2. **Licht:** weiches Sonnenlicht mit Schatten (eine gerichtete Lichtquelle, Schattenkarte nur in 3D, Qualität nach `PerformanceMonitor`), Umgebungslicht über eine HDRI (drei `Environment`, leichtes Preset), Tonemapping sauber, keine dunklen Ecken.
3. **Boden:** Bodenplatten mit Dicke (Kante sichtbar), Raumfarben wie in `palette.ts`; um das Gebäude eine ruhige Fläche: sehr blasses Raster, das mit der Entfernung ausblendet, **kein Punkteraster bis zum Horizont**.
4. **Möbel nach Typ** (instanziert, ein Mesh pro Typ): Tisch (Platte + Beine), Stuhl, Regal, Schrank, Maschine (Block mit Fase und dunklerer Oberseite), Drucker, Sofa, Bett, Küchenzeile; alles andere als abgerundeter Block. Höhe nach Typ. Farbe neutral, leicht nach Kategorie.
   Stand: Die Daten haben keine Höhen. Jedes Ding ist ein niedriger Körper mit Standardhöhe nach Typ (`twin/src/model/assetHeights.ts`: Palette 0,15 m, Tisch 0,75 m, Regale höchstens 1,2 m, sonst 0,3 m), Maschinen 1,9 m. Bodenmarkierungen bleiben flach und haben den Walkway-Farbton.
5. **Aufräumen:** keine doppelten Schatten, Geisterbild-Test (`tests/e2e/test_twin_ghost.py`) bleibt grün (die Ursache war die Nachbearbeitung).

## Grenzen
- Nur 3D; 2D-Plan unverändert. Farben aus `palette.ts`/Tokens, keine neue Palette.
- Leistung: größtes Gebäude (`osm-way27917482`, ~5000 Assets) bleibt flüssig (Bildzeit messen); am Handy Schatten aus.
- Nicht anfassen: Kamera/Steuerung (Trackpad-Fix läuft: `CameraRig.tsx`, `cameraMouse.ts`, Kipp-Grenze), `Labels.tsx` (Etiketten), Seite fürs Ortswissen (eigener Agent), Sprache.

## Tests
Bestehende e2e grün (`test_twin_ghost`, `test_twin_controls`, `test_here_ui`, `test_semantic_zoom`, `test_closed_marking`), Screenshots Fabrikhalle, Büroetage, Wohnung, Desktop und Handy, vorher und nachher.
