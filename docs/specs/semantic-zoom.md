# Spec: Informationsstufen beim Zoomen (2D, mit Jennifer abgestimmt, 25.10. nachts)

## Ziel
Zoomen soll sich nach "mehr Information" anfühlen, nicht nur nach "größer". Grundlage ist Shneidermans Visual Information-Seeking Mantra: **Overview first, zoom and filter, then details-on-demand**. Bei Karten heißt das semantic zoom: jede Stufe zeigt andere Arten von Information.

## Heute
- Leonies Textstufen in `twin/src/scene/mapZoom.ts`: weit (Zonen, POIs), mittel (alle Raumnamen), nah (Maschinennamen).
- UX-Branch: Formen (Möbel, Maschinen) ab etwa 3 bis 4 px Bildschirmgröße auf jeder Stufe, Landmarken an der Route hervorgehoben.
- Raumfarben nach Gruppen (`docs/specs/room-colours.md`).

## Vier Stufen (2D, auf Leonies Mechanismus aufbauen, Maßstab in Metern pro Pixel)
| Stufe | Wann | Was dazukommt |
|---|---|---|
| **1. Gebäude** | ganzes Gebäude passt auf den Schirm (weit) | **Bereiche statt Einzelnamen**: angrenzende Räume derselben Gruppe auf einer Etage werden zu einem Bereich zusammengefasst, ein großer, ruhiger Name in der Mitte ("Production", "Logistics", "Offices", "Social"). Eingänge, WC, Treppe, Aufzug als Symbol. Maschinen als leises Muster. |
| **2. Halle oder Etage** | mittel | einzelne Raum- und Zonennamen (wie heute bei mittel), große Maschinen deutlicher, Gerätesymbole für Kaffee, Drucker, Feuerlöscher (Normfarbe), Erste Hilfe (Normfarbe) |
| **3. Raum** | nah | Maschinennamen, unter dem Raumnamen eine zweite Zeile mit Typ und Fläche ("Kitchen · 24 m²"), Türen mit Breite als kleine Zahl ab 1,2 m und Stufen-Markierung bei `step_free: false`, gesperrte Türen mit rotem Balken |
| **4. Antippen** | Details auf Wunsch | Raumkarte wie heute (Fläche, Typ, Route, I'm here), zusätzlich Geräte im Raum als kurze Liste |

## Regeln
1. **Ein Mechanismus:** alles hängt an `useMapZoom` / `tierOf` in `mapZoom.ts`, eine vierte Stufe "area" ganz außen, keine zweite Logik.
2. **Weiche Übergänge:** neue Elemente blenden in 150 bis 200 ms ein (Opacity), nie hartes Aufpoppen; mit `prefers-reduced-motion` ohne Animation.
3. **Hysterese:** Stufenwechsel erst etwas nach der Grenze, damit beim leichten Zoomen nichts flackert (die halben Oktaven aus `mapZoom.ts` nutzen).
4. **Keine Überlappung:** neue Texte gehen durch Leonies kollisionsfreies Layout; bei Platzmangel gewinnt Route > Auswahl > POI > Raumname > Zweitzeile.
5. **Gleich auf Handy und Desktop**, nur der Maßstab entscheidet.
6. **Fabrik zuerst** prüfen (Synera-Kunden sind Industrie), dann Büro, dann Wohnen.
7. **3D** bleibt wie es ist; nur die Bereichsnamen der Stufe 1 auch in 3D, wenn es ruhig bleibt.

## Akzeptanz
- Screenshots je Stufe für proc-factory-dev-012 Etage 0 (Halle), Etage 2 (Büro), resplan-1465 (Wohnung), Desktop und Handy.
- Langsam von außen nach innen zoomen: auf jeder Stufe kommt sichtbar etwas Neues, nichts flackert, nichts überlappt.
- Leistung: größtes Gebäude (osm-way27917482) bleibt flüssig, Bereichsberechnung einmal pro Etage im Cache.

## Umsetzung (25.10., Branch `feat/twin-semantic-zoom`)
- `twin/src/scene/mapZoom.ts`: Stufen `area | far | mid | near`. `area` gilt, solange die längere Seite der Etage höchstens 480 px auf dem Schirm einnimmt (Pixel, nicht Bildschirmanteil, also gleich auf Handy und Desktop). Kleine Etagen (Wohnung, 22 m) erreichen `area` nur auf dem Handy, auf dem Desktop begrenzt der Zoom vorher. Hysterese: eine Stufe wird erst 0,2 Halboktaven hinter der Grenze verlassen, das Layout rechnet mit dem gröbsten gehaltenen Maßstab.
- `twin/src/scene/areas.ts`: Bereiche = Räume derselben Gruppe mit gemeinsamer Wand (Kanten auf einer Linie, 0,35 m Toleranz, mindestens 0,5 m Überlappung). Kleine Sozialräume (höchstens 2 Räume) gehen im Nachbarbereich auf, damit ein Büroflur "Offices" bleibt und nicht in Einzelteile zerfällt. Generische Räume ("Rooms") bekommen keinen Namen. Einmal pro Etage im Cache, größte Etage (osm-way27917482) etwa 10 ms.
- Stufe 2: Kaffee, Drucker, Erste Hilfe/Defibrillator/Augendusche (grün) vor den Raumnamen, Feuerlöscher (rot) nach den Raumnamen, sonst verdrängen sie in großen Gebäuden die Namen.
- Stufe 3: Zweitzeile, Türbreiten ab 1,2 m (Türen und Eingänge), Stufen-Symbol und rote Balken wie bisher.
- Stufe 4: Raumkarte listet Maschinen, Geräte, Einbauten (keine Möbel) nach Typ mit Anzahl, höchstens 6 und "+n more".
- 3D unverändert (dort gilt `area` wie `far`).
- Test: `tests/e2e/test_semantic_zoom.py`. Screenshots: `docs/twin-audit/semantic-zoom/`.
