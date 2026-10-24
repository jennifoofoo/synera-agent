# Spec: Raumfarben nach Gruppen (Entwurf, wartet auf Okay von Jennifer und Leonie)

## Ziel
Man soll auf einen Blick sehen, wo Küche, WC, Treppe oder Besprechung sind, ohne Etiketten zu lesen (Synera bewertet UX über kognitive Last). Heute unterscheiden sich Raumgruppen nur in der Helligkeit (`twin/src/model/palette.ts`, "never by hue"), und Küche, Büro, Besprechung und WC liegen alle in der Gruppe `office`.

## Recherche, kurz
- Innenkarten (Apple IMDF, MapsIndoors, Azure Maps, Mapbox-Beispiele) färben **Räume nach Kategorie**, nicht Möbel. Die Farben legt jede App selbst fest, es gibt keine Norm. MapsIndoors hat ein eigenes "color system for location types".
- Wayfinding-Leitfäden: Farbe nie allein, immer zusammen mit Symbol und Text (Farbfehlsichtigkeit, Barrierefreiheit). Zu viele kräftige Farben überfordern, besonders neurodivergente Menschen. Ruhige Farben, die Räume abgrenzen, helfen.
- Fitwel (Gebäudezertifizierung) nennt unterscheidbare Farbschemata als eins von drei Mitteln für Orientierung in Gebäuden, neben Landmarken und durchgehenden Fluren.

## Regel
1. **Farbe nur für Ziele, die Menschen suchen.** Alles andere bleibt neutral (Grau nach Helligkeit wie heute). So bleiben es 4 Farbtöne, nicht 10.
2. **Sehr blass** (wenig Sättigung, hell). Synera-Blau bleibt allein für Route, Auswahl und Hauptknöpfe.
3. **Nie Farbe allein:** jede farbige Gruppe hat auch ein Symbol (WC, Kaffee, Treppe, Aufzug, Besprechung) und steht in der Legende.
4. **Möbel neutral und leiser** (heller als heute), wichtige Geräte als Symbol, nicht als Farbe.
5. **Wände** ein Ton dunkler als der Boden der Gruppe, nicht fast schwarz.
6. **Gleich in 2D und 3D**, auf Handy und Desktop.

## Gruppen (alle 30 Raumtypen der Daten zugeordnet)
| Gruppe | Raumtypen | Farbe Boden (Vorschlag) | Symbol |
|---|---|---|---|
| Essen und Pause | kitchen, canteen | Sand `#eadfc6` | Tasse |
| Sanitär | toilet, bathroom, locker_room | Helles Aqua `#d3e4e4` | WC |
| Treppe und Aufzug | stairwell, lift | Gedämpftes Violett `#cfc8de` (passt zu den Schächten) | Treppe, Aufzug |
| Besprechen und Lernen | meeting_room, seminar_room, lecture_hall, library | Helles Salbei `#d9e3d3` | Besprechung |
| Wege | corridor, lobby | fast weiß `#efede8` | keins |
| Arbeiten und Wohnen | office, generic_room, bedroom, living_room | neutral `#dcdad4` (wie heute) | keins |
| Produktion | production_zone, assembly_zone, additive_zone, makerspace, lab, quality_lab | neutral mittel `#c4c7cb` | keins |
| Lager und Logistik | warehouse_zone, logistics_zone, storage | neutral warm `#cbc9c3` | keins |
| Technik | technical_room, server_room, print_room | neutral dunkler `#b4b8bd` | Drucker bei print_room |
| Außen | balcony | neutral hell `#e2e3dc` | keins |

Die vier Farbtöne liegen auch in der Helligkeit auseinander, damit sie bei Rot-Grün-Schwäche unterscheidbar bleiben. Beim Bauen mit einem Farbfehlsichtigkeits-Filter (Chrome DevTools, "Emulate vision deficiencies") prüfen.

## Fabriken (Ergänzung, mit Jennifer abgestimmt)
In Hallen gelten feste Konventionen: Bodenmarkierung nach Lean/5S (Gelb = Geh- und Fahrwege) und Sicherheitsfarben nach ISO 7010 / ISO 3864 (Rot = Brandschutz, Grün = Rettung und Erste Hilfe).
- Zonen (production, assembly, additive, warehouse, logistics) bleiben neutral, nur Helligkeit.
- Hauptgänge und Fahrwege (Flure in Industriegebäuden, Räume mit "aisle" im Namen, Gabelstapler-Gänge) blass gelb `#eee7b8` (kühler, zitroniger Ton, klar getrennt vom warmen Sand der Küchen `#eadfc6`).
- Maschinen neutrale Formen (Pixelgrößen-Regel aus `docs/ux-cognitive-load.md`), Landmarken an der Route hervorgehoben.
- Sicherheit nur als Symbol in Normfarben: Feuerlöscher rot, Erste Hilfe, Augendusche, Defibrillator und Notausgang grün. Keine Raumflächen in Rot oder Grün.
- Sozialräume in Fabriken (Küche, WC, Umkleide, Besprechung) wie im Büro gefärbt.

## Was sich ändert
- `twin/src/model/palette.ts`: `SpaceGroup` und `GROUP_COLOURS` nach der Tabelle, Regel "never by hue" ersetzt durch "hue only for sought-after groups".
- `twin/DESIGN.md` und `twin/src/styles/tokens.css`: die vier Gruppenfarben als Tokens.
- Legende in der Hilfe ("?", Abschnitt "Map symbols").
- Möbel heller, Wände heller.

## Akzeptanz
- Screenshot Büroetage (proc-factory-dev-012, Etage 2) und Fabrikhalle, 2D und 3D, Desktop und Handy: Küche, WC, Treppe, Besprechung ohne Lesen erkennbar.
- Route und Auswahl bleiben die kräftigste Farbe im Bild.
- Etiketten auf allen Gruppenfarben lesbar (Kontrast mindestens 4,5:1).
- Prüfung mit Deuteranopie-Filter: die vier Gruppen bleiben unterscheidbar.
