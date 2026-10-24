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
