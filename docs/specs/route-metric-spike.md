# Spike: Routenmetrik (grob, Tür-zu-Tür gerade, geodätisch)

Branch `spike/route-metric`, nur Messung und Prototyp, kein Produktivcode geändert.

## Fragestellung

Synera bewertet Routen auf unbekannten Gebäuden mit einer Tür-zu-Tür-Distanz im Raum (0,15 m Wandabstand, um Ecken), Treppen 2 m pro Höhenmeter, Lift 15 m + 1 m pro Höhenmeter. Unser Router (`BuildingMap.route`) nutzt das grobe Kit-Modell (Raum = ein Knoten am Anker, Kante = Anker zur Tür, Treppe 12 m pro Etage, Lift 15 + 6 m pro Etage). Frage: Wie oft ist unsere Raumfolge dadurch länger als das Optimum, und was ist der beste Kompromiss?

## Setup

- `spikes/route/geodesic.py`: Prototyp. `best_route(bm, start, end, step_free=False)` und `measure(bm, space_sequence)` (None bei ungültigem Schritt). Pro Raum: Polygon um 0,15 m geschrumpft (Fallback auf Rohpolygon bei leer oder zerfallen), Sichtbarkeitsgraph über Reflexecken (`covers(LineString)`), pro Raum gecacht. Graph über Türen und Treppen/Lift-Haltepunkte, `measure` wählt bei parallelen Türen per DP die beste.
- `spikes/route/evaluate.py`: Vergleich, `spikes/route/audit.py`: Laufzeit und Datenaudit.
- Annahmen: erster und letzter Raum kosten nichts (Tür zu Tür, Variante "Anker als Start" separat gemessen), "outside" kostet 0 wie im Kit, Höhenmeter aus `elevation_m`-Differenz, Haltepunkt von Treppe/Lift ist der Anker des Halteraums.
- Stichprobe: Warm-up-Fragen aus data/dev und data/train, `route` und `route_step_free` bis 150 pro Quelle, `route_with_closure` und Tour-Legs bis 60 pro Quelle, Seed 7. 705 Fälle, davon 672 erreichbar. Die 33 unerreichbaren sind in beiden Modellen unerreichbar (0 Abweichungen). `BuildingMap.route` liefert in allen 672 Fällen die gelabelte `space_path`.
- Score = bestes geodätisches Ergebnis / geodätische Länge unserer Folge. Ungültige Routen: 0 in allen Modellen.

## Ergebnisse: grobes Kit-Modell (heutiger Stand)

| Quelle | n | Anteil >= 0,99 | Median | 5. Perzentil | Minimum |
|---|---|---|---|---|---|
| osm | 83 | 71,1 % | 1,000 | 0,757 | 0,437 |
| proc | 200 | 92,0 % | 1,000 | 0,679 | 0,298 |
| resplan | 210 | 98,6 % | 1,000 | 1,000 | 0,443 |
| swiss | 179 | 95,5 % | 1,000 | 1,000 | 0,824 |
| alle | 672 | 92,4 % | 1,000 | 0,888 | 0,298 |

Schlechteste 5 pro Quelle (Kürzel: Raum-IDs ohne Gebäudepräfix):

| Quelle | Gebäude | Paar (Start, Ziel) | Score |
|---|---|---|---|
| osm | osm-way19183732 | F0-S038 nach F0-S008 (Tour-Leg) | 0,437 |
| osm | osm-way27917482 | F-1-S112 nach F-1-S041 | 0,516 |
| osm | osm-way27917482 | F0-S328 nach F3-S274 (Tour-Leg) | 0,691 |
| osm | osm-way27917482 | F2-S375 nach F1-S262 (step-free) | 0,749 |
| osm | osm-way360544293 | F0-S015 nach F1-S015 | 0,757 |
| proc | proc-campus-dev-001 | F0-S016 nach F1-S003 | 0,298 |
| proc | proc-campus-dev-002 | F2-S003 nach F1-S017 (Tour-Leg) | 0,351 |
| proc | proc-campus-train-000 | F0-S003 nach F2-S003 | 0,359 |
| proc | proc-campus-dev-000 | F3-S021 nach F0-S020 (Closure) | 0,382 |
| proc | proc-campus-dev-013 | F1-S002 nach F0-S016 (Tour-Leg) | 0,387 |
| resplan | resplan-7471 | F0-S002 nach F0-S006 (Tour-Leg) | 0,443 |
| resplan | resplan-14509 | F0-S002 nach F0-S005 | 0,508 |
| resplan | resplan-12985 | F0-S004 nach F0-S008 | 0,915 |
| swiss | swiss-3338 | F0-S004 nach F0-S031 (Tour-Leg) | 0,824 |
| swiss | swiss-3338 | F1-S037 nach F0-S027 | 0,888 |
| swiss | swiss-3418 | F3-S011 nach F0-S019 | 0,931 |

(resplan hat nur 3 Fälle unter 0,99, swiss 8.) Die Ausreißer sind kurze Wege oder große Räume, in denen der Anker-Umweg die Türwahl kippt, besonders bei großen Hallen und Fluren. Sensitivität: Wenn Synera Start und Ziel am Raumanker beginnen lässt statt Tür zu Tür, ändert sich das Bild kaum (alle 92,3 % >= 0,99, 5. Perzentil 0,887).

## Alternativen zum groben Modell

Alle Folgen werden mit dem geodätischen Maß bewertet.

| Modell | Anteil >= 0,99 | 5. Perz. | Minimum | osm | proc | resplan | swiss |
|---|---|---|---|---|---|---|---|
| grob (Kit) | 92,4 % | 0,888 | 0,298 | 71,1 % | 92,0 % | 98,6 % | 95,5 % |
| grob + Synera-Vertikalkosten | 92,6 % | 0,908 | 0,298 | 72,3 % | 92,0 % | 98,6 % | 95,5 % |
| Tür-zu-Tür gerade, Kit-Vertikalkosten | 99,4 % | 1,000 | 0,755 | 96,4 % | 100 % | 100 % | 99,4 % |
| Tür-zu-Tür gerade, Synera-Vertikalkosten | 99,6 % | 1,000 | 0,952 | 97,6 % | 100 % | 100 % | 99,4 % |
| geodätisch | 100 % (per Definition) | 1,000 | 1,000 | 100 % | 100 % | 100 % | 100 % |

Die Vertikalkosten sind nicht der Hebel (es gibt fast immer nur eine sinnvolle Treppe oder einen Lift pro Strecke). Der Hebel ist die Anker-Kante: Tür-zu-Tür gerade im Raum hebt den Anteil mit voller Punktzahl von 92 % auf 99,6 %. Geodätisch bringt nur noch die letzten 0,4 Punkte, vor allem in OSM mit verwinkelten Räumen.

## Laufzeit geodätischer Graph

Größtes Gebäude osm-way27917482: 1623 Räume, 1799 Türen, 7433 Polygonpunkte, 4110 Reflexecken. Aufbau des vollen Graphen 2,8 s (3729 Knoten, 19911 Kanten), danach 22 ms pro Anfrage. Swiss (362 Räume): 0,2 bis 0,3 s. Kein Raum brauchte den Schrumpf-Fallback. Der Aufbau ist einmal pro Gebäude und Variante (step-free, Sperrungen) nötig, die Sichtbarkeit pro Raum ist gecacht.

## Forklift- und Bay-Regeln gegen die Daten

Vorhanden:

- Bay-Typen nur in procedural (26 Gebäude): `production_zone` 78, `warehouse_zone` 78, `logistics_zone` 69, `assembly_zone` 48, `additive_zone` 18. Sie sind als `type: hall` modelliert. OSM, ResPlan und Swiss haben keine.
- Gänge: Räume `type: corridor` mit Namen "Main aisle ..." (112 Stück, Hallenraster H-B*). Büroflure heißen "Office corridor" und sind 2 m breit. Es gibt kein eigenes Feld "forklift_aisle".
- Öffnungsbreite `width_m`: in procedural bis 20 m (580 Öffnungen >= 3 m), Hallen untereinander und zu Gängen 14,6 oder 17,2 m als `kind: opening`, Eingänge zu Hallen 4 bis 5 m. In ResPlan und Swiss gibt es 74 bzw. 411 Öffnungen >= 3 m, aber nur Küche/Wohnraum und Balkon, also keine Gabelstaplerwege. OSM-Türen sind alle 0,9 m.
- Türposition ist ein Punkt, bei einer 17-m-Öffnung also die Mitte.

Fehlt:

- Kein Gabelstapler-Flag, keine Gangbreite pro Raum, kein Attribut "Bay ist Ziel". Gangbreite müsste aus dem Polygon (kleinere Seite des Minimum-Rotated-Rectangle) abgeleitet werden.

Ein Forklift-Modus bräuchte: (1) nur Öffnungen und Eingänge mit `width_m >= 3`, Türen und Treppen raus, Lifte nur wenn Maße bekannt (offen), (2) nur Räume als Zwischenknoten, die Gang oder Bay sind (Gang: Typ corridor und Breite >= 3 m, Büroflure raus), (3) Bay-Räume (`*_zone`) nur als Start oder Ziel, nie als Durchgangsknoten, also dort keine Kanten zwischen zwei Öffnungen, außer Start/Ziel. Aufwand im Graph: etwa 2 bis 3 Stunden inklusive Tests, aber die Regeln sind interpretierbar (siehe offene Fragen).

## Empfehlung

- Modell umstellen: ja, aber auf "Tür-zu-Tür gerade" mit Synera-Vertikalkosten, nicht auf volle Geodäsie. Das ist der beste Kompromiss: 92,4 % auf 99,6 % volle Punkte, der Bau ist eine kleine Änderung im Graph (Kanten zwischen den Türknoten desselben Raums statt Anker-Kante, Treppe 2 m pro Höhenmeter, Lift 15 m + 1 m pro Höhenmeter). Aufwand ca. 3 Stunden mit Tests.
- Geodätisch produktiv bauen lohnt sich nur, wenn die letzten 0,4 Punkte zählen (vor allem OSM-artige Gebäude). Aufwand ca. 6 bis 8 Stunden (Prototyp übernehmen, Tests, Cache pro Gebäude, Sonderfälle wie breite Öffnungen). Risiko: Der Prototyp ist unser eigenes Maß, kein Abgleich mit Syneras Checker.
- Wichtig: Das Kit-Modell bleibt für alles, was gegen die Kit-Labels bewertet wird (`errand`, `what_if_door`, Warm-up-`optimal_length_m`), weil diese Antworten aus dem groben Modell stammen. Zwei Modelle nebeneinander: grob für Zahlen, Tür-zu-Tür für die Raumfolge der Route. Sonst brechen die bestehenden Tests mit Längen.
- Risiko: Die Messung nimmt unser Prototyp als Wahrheit. Wenn Synera Start und Ziel anders behandelt (Anker statt Tür) oder "outside" nicht gratis ist, verschieben sich die Zahlen, die Reihenfolge der Modelle blieb im Test mit Anker-Start aber gleich. Breite Öffnungen (bis 20 m) sind als Mittelpunkt modelliert, das kann die Tür-zu-Tür-Länge in Fabrikhallen überschätzen.

## Offene Fragen an Synera

1. Wie viele Fragen auf unbekannten Gebäuden nutzen Forklift oder Bay-Regeln (nur procedural Fabriken)?
2. Wie wird in einen Bay eingefahren: über jede Öffnung, und zählt die Länge bis zur Öffnung oder bis in die Bay-Mitte?
3. Zählt ein Gang als Gang, wenn der Raum >= 3 m breit ist, oder wenn alle Öffnungen entlang der Strecke >= 3 m sind? Dürfen Gabelstapler Lifte nutzen?
4. Start und Ziel: zählt der Weg bis zur Tür des ersten und vom letzten Raum aus, oder vom Raummittelpunkt oder vom Gerät?
5. Wie lang ist der Weg draußen zwischen zwei Eingängen (im Kit 0 m)?
6. Bei breiten Öffnungen (14 bis 20 m): wird die Tür-zu-Tür-Distanz zu irgendeinem Punkt der Öffnung gemessen oder zur Mitte?

## Umsetzung

Branch `feat/route-model`, neues Modul `building_agent/routing.py`. `BuildingMap` und das Kit bleiben unverändert.

Was sich geändert hat:

- Neues Routenmodell "Tür-zu-Tür gerade" mit Synera-Vertikalkosten: pro Raum ein Knoten je Tür, Öffnung oder Treppen/Lift-Haltepunkt, Kanten zwischen den Knoten desselben Raums mit der geraden Distanz der Türpositionen (Haltepunkte am Raumanker). Eingänge und "outside" kosten 0. Start und Ziel zählen Tür zu Tür (Variante ohne Anker, weil im Spike kaum ein Unterschied). Treppe 2 m pro Höhenmeter (aus `elevation_m`), Lift 15 m plus 1 m pro Höhenmeter.
- Sperrungen (Räume, Öffnungen, Verbinder), `step_free` und `via` in Reihenfolge funktionieren wie im Kit. Unerreichbar oder gesperrtes Ziel wirft `MapError`. Rückgabe ist dieselbe `RouteResult`, die Schritte sind wie bei `BuildingMap.directions` formuliert, `bm.last_route` wird gesetzt.
- Der Graph wird pro Gebäude gecacht, Schlüssel sind Sperrungen, ein Hash über Öffnungen (id, step_free, Breite, Position, Räume) und `step_free`. Änderungen an Sperrungen oder Türen bauen ihn neu.

Wo das neue Modell läuft: `give_directions`, `route_effect` und `compare_normal_length` (`guide_tools.py`, Vorher und Nachher im selben Modell) und das Tool `find_route` in `building_agent/tools.py` (gleicher Name und Docstring, ersetzt das Starter-Tool).

Was beim Kit-Modell bleibt: alle Kinds (`errand`, `what_if_door`, `wide_delivery_count`, `step_free_reachable_count`), die Warm-up-`optimal_length_m` und `BuildingMap.route` selbst. Grund: Diese Zahlen sind mit dem groben Modell gelabelt und würden sonst von den Labels abweichen. Zwei Modelle nebeneinander: grob für Zahlen, Tür-zu-Tür für die Raumfolge, die Synera bewertet.

Messung (Test `tests/test_routing.py`, Maß ist der geodätische Prototyp): auf der gesamten dev- und train-Menge (1457 erreichbare Fälle) haben 99,4 % mindestens 0,99 (osm 97,6 %, swiss 98,8 %, proc und resplan 100 %), Median 1,000, schlechtester Wert 0,938. Der Test nutzt eine Stichprobe von rund 300 Fällen aus allen vier Quellen und prüft auf 98 %, weil die Stichprobe streut (hier 99,0 %). Laufzeit im größten Gebäude (1623 Räume): Graph plus 20 Routen unter 0,2 s.

Risiken: Das Maß ist unser eigener Prototyp, nicht Syneras Checker. Breite Öffnungen sind als Mittelpunkt modelliert.
