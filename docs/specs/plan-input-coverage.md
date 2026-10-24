# Spec: Plan-Eingaben für Level 4: alle Fälle erkennen, prüfen, abdecken

Status: ENTWURF, wartet auf Bestätigung von Jennifer.
Anlass: Jennifer, 24.10.2026: "Es soll die Daten prüfen, und alle Fälle sollen abgedeckt werden." Unklar ist, **was Synera am Sonntag für Level 4 liefert** (nur PNG, auch SVG, Kit-Stil oder echte Pläne, eine oder mehrere Etagen, mit oder ohne Maßstab). Wir bauen deshalb nicht auf eine Annahme, sondern eine Eingangsprüfung, die jeden Fall erkennt und den besten Weg wählt, mit ehrlicher Meldung statt stillem Raten.

## Grundregeln
1. **Erst prüfen, dann wählen:** Eine Funktion `analyze_plan_input(path) -> InputReport` bestimmt Format, Stil und Qualität nur aus dem Inhalt (nicht aus Dateiendung oder Name).
2. **Beste verfügbare Quelle gewinnt:** `building.json` (fertig) vor SVG (Vektor) vor PNG im Kit-Stil (Farbe plus Marker) vor beliebigem Bild (nur Modell).
3. **Nie still schlechter:** Jeder Rückfall steht in der Karte ("Ich lese diesen Plan nur mit dem Modell, das ist ungenauer: ...") mit Gründen und Kennzahlen.
4. **Nie ein Absturz:** Ein kaputtes, ungewöhnliches oder zu großes Bild ergibt eine Meldung und einen Vorschlag, was die Person tun kann.
5. **Jede Pipeline mit Messung:** Für jeden Fall der Matrix gibt es einen Test oder eine dokumentierte Messung.

## Matrix der Fälle
| Achse | Werte |
|---|---|
| Format | `building.json` (Kit-Format), SVG vom Kit (Matplotlib-Export), SVG sonst (Pfade, Polygone, Gruppen), PNG, JPG, PDF (Vektor, Raster, mehrere Seiten), mehrere Bilder (eine je Etage) |
| Stil | Kit-Farbflächen mit Markern, Kit mit Möbeln, Linienplan (schwarze Wände, Türbögen), schraffiert, mit Maßketten und Maßstabsleiste, gescannt oder fotografiert (Rauschen, Drehung, Schatten), niedrige Auflösung |
| Quelle | procedural, ResPlan, Swiss Dwellings, OSM (dicht, viele Räume), unbekannt |
| Etagen | eine, mehrere (mit Treppen und Aufzügen), unterschiedliche Bildgrößen je Etage, Keller |
| Maßstab | gedruckte Leiste, Maßkette, bekannte Länge aus Gespräch, Türbreite als Anker, gar nichts |
| Größe und Qualität | klein, sehr groß (über 6 Mpx), beschädigt, leer, falscher Typ |
| Gebäude | normal, mit mehreren Eingängen, ohne Eingang im Bild, gedreht |

## Erkennung (`InputReport`)
Format (aus Magic Bytes und Struktur), Seitenzahl, Pixelgröße und Größe in Megapixel, **Kit-Stil-Wert** (Anteil flacher Füllfarben, Treffer der Kit-Palette, Marker-Farben vorhanden), **Linienplan-Wert** (viel Weiß, dünne dunkle Linien, wenig Füllfläche), **Scan-Wert** (Rauschen, JPEG-Artefakte, Schräglage), gedruckte Maßstabsleiste oder Maßketten (Hinweis, nicht gelesen), SVG-Art (Kit-Export an `figure_1`, `patch_`, `use`-Symbolen erkannt oder generisch), geschätzte Etagen (bei mehreren Dateien aus Namen wie `floor_0`), Warnungen. Alles deterministisch, ohne Modellaufruf, in unter einer Sekunde.

## Wegwahl (`choose_pipeline(report) -> Pipeline`)
| Erkannt | Weg | Erwartete Qualität (belegt oder offen) |
|---|---|---|
| `building.json` im Kit-Format | direkt laden und mit `preflight` prüfen | exakt |
| SVG vom Kit | **Vektor-Leser** (Räume als Flächen, Türen und Öffnungen aus den Symbolen, Eingänge, Maßstab aus bekannter Länge), danach Modell nur für Namen, Typen, Nummern | offen, wird von `feat/swiss-stairwell` gemessen (vermutlich bester Weg) |
| PNG im Kit-Stil | Modell, dann Farb-Segmentierung, dann Marker, dann Prüfung, optional Türvorschläge | belegt: sehr gut auf sauberen Plänen und OSM, auf Swiss schwach |
| Linienplan, schraffiert, Scan | nur Modell, bei dichten Plänen in Kacheln, mit Qualitätsprüfung und deutlicher Warnung | offen, wird von `test/level4-styles` gemessen |
| Mehrere Dateien | je Datei der passende Weg, dann Etagen verbinden (Treppen und Aufzüge, siehe `fix/level4-connectors`) | siehe dort |
| Unbrauchbar (leer, beschädigt, zu groß) | klare Meldung, was zu tun ist | getestet |

## Prüfungen nach dem Bau (immer, unabhängig vom Weg)
Reiner Zustandscheck am Ergebnis: Polygone gültig, Räume nicht überlappend, jede Tür verbindet zwei Räume, Eingang vorhanden und an der Außenwand, jeder Raum erreichbar, Etagen verbunden, Maße plausibel, **Gesamtprüfung wie `scripts/preflight.py`** auf das gebaute Gebäude (alle Fragetypen laufen ohne Absturz). Das Ergebnis erscheint als Kennzahlenzeile in der Karte ("24 Räume, 27 Türen, 2 Eingänge, 2 Etagen, 6 Verbindungen, Qualität: gut / mittel / schwach, weil ...").

## Maßstab (alle Wege)
Reihenfolge: bekannte Länge der Person, gedruckte Maßstabsleiste (Modell liest sie, mit Plausibilitätsprüfung), Türbreite als Anker (0,9 m, mit Warnung "ungenau"), sonst Rückfrage. Nie eine stille Annahme. Bei SVG und Kit-PNG kommt der Maßstab aus der bekannten Gebäudebreite.

## Testmatrix (Akzeptanz)
1. Für **jede Zeile der Fall-Matrix** gibt es ein Beispiel (echt aus den Daten, oder künstlich gerendert in `scripts/render_plan_styles.py`) und einen Test, dass `analyze_plan_input` es richtig erkennt (Format, Stil, Etagen).
2. `choose_pipeline` ist für jeden erkannten Fall festgelegt (Tabelle als Test), und der Rückfall ist in jedem Fall in der Karte sichtbar.
3. Messung pro Weg auf mindestens 6 Gebäuden (alle vier Quellen) mit Recall, Präzision, Türen, Routenqualität (Judge-Metrik) und Kosten, dokumentiert in `docs/eval-log.md`, mit den Zielen: Kit-PNG wie heute, SVG besser als PNG, Linienplan **mindestens Räume und Türen zu 0,8**, sonst klare Warnung und Hinweis, dass die Qualität begrenzt ist.
4. Fuzz: 30 kaputte oder unpassende Dateien (leer, abgeschnitten, falsche Endung, Textdatei als PNG, riesiges SVG, SVG-Bombe mit tiefer Verschachtelung, PDF mit 100 Seiten, Bild 20000 Pixel breit, Skripte in SVG) ergeben eine Meldung, **kein Absturz, kein Auslesen von Skripten, kein Nachladen externer Adressen** (SVG darf keine Skripte oder externe Verweise ausführen).
5. Sicherheit: Dateien nur in `agent_output/uploads/`, Dateityp nach Inhalt, Größenlimit, keine Pfade vom Browser, keine Auswertung von XML-Entitäten (kein XXE).
6. `scripts/check.sh` bleibt ohne Key grün.

## Schritte
| Schritt | Inhalt | Besitzer | Stunden |
|---|---|---|---|
| 1 Eingangsprüfung | `plan_input.py` (`analyze_plan_input`, `choose_pipeline`), Fall-Matrix als Tests, Fuzz und Sicherheit | Jennifer (Agent) | 3 |
| 2 SVG-Leser | `svg_read.py` (nur wenn `feat/swiss-stairwell` einen Gewinn zeigt), sicherer XML-Parser, Zuordnung der Symbole | Jennifer (Agent) | 3 bis 4 |
| 3 Fremde Stile verbessern | Kacheln, Linienplan-Prompt, Maßketten und Maßstabsleiste lesen, Qualitätsprüfung, nach `test/level4-styles` | Jennifer (Agent) | 4 bis 6 |
| 4 Einbau und Karte | `build_from_plan` nutzt `choose_pipeline`, Kennzahlenzeile und Warnungen in der Karte, Live-Skripte | Jennifer (Agent) | 2 |
| 5 Oberfläche | mehrere Dateien hochladen, Etagenzuordnung, Qualitätsanzeige | Leonie | 2 |

## Abhängigkeiten
Wartet auf: Messung SVG und Swiss-Regel (`feat/swiss-stairwell`), Messung fremder Stile (`test/level4-styles`), Treppen und Aufzüge (`fix/level4-connectors`). Danach Schritt 1 starten.

## Risiken
- Wir kennen die Sonntagsdaten nicht. Die Matrix deckt die möglichen Fälle ab, aber nicht echte Architektenpläne mit unvorhersehbaren Eigenheiten. Darum die klare Warnung statt scheinbarer Sicherheit.
- Ein SVG-Leser ist nur sinnvoll, wenn die Sonntagsdaten SVG enthalten. Frage 14 steht auf der Synera-Liste.
- Mehr Wege bedeuten mehr Wartung. Jeder Weg bekommt Tests, und der Rückfall (Modell allein) bleibt immer erhalten.
