# Spec: Level 4, Gebäude aus Grundrissen bauen

Status: ENTWURF, wartet auf Bestätigung von Jennifer (und Leonie für die Web-Teile).
Grundlage: `docs/specs/level4-spike.md` (Messungen), `docs/specs/phase-2.md` Block D.

## Ziel
Aus einem oder mehreren Grundriss-Bildern ein `building.json` im Kit-Format erzeugen, im Gespräch prüfen und korrigieren, speichern und sofort befragen. "Ein neues Gebäude in Minuten, nicht Tagen." Laut PDF prüfen die automatischen Checks "buildings built correctly from plans" (Level 4). Wie genau, ist offen (siehe Fragen).

## Nicht-Ziele
Scans oder Fotos von echten Architektenplänen, Handaufmaß, Capture per Handy, automatische Maßstabserkennung ohne Hilfe, 3D.

## Ablauf im Gespräch (geführt, nie "Bild rein, fertig")
1. Person lädt pro Etage ein Bild hoch und sagt "build this".
2. Agent fragt nur, was er braucht: Etage (Level) pro Bild, und eine bekannte Länge in Metern (Gebäudebreite, Raumbreite oder Türbreite), außer eine Maßstabsleiste ist gedruckt.
3. Extraktion (ein Vision-Aufruf pro Etage), Konvertierung, Validierung.
4. Agent zeigt, was er verstanden hat: Vorschau (Räume mit Nummer, Türen) und eine Befundzeile ("24 Räume, 8 Türen, 2 Eingänge. 15 Räume ohne Weg nach draußen, vermutlich fehlen Türen.").
5. Korrekturen im Gespräch ("Tür zwischen 0.13 und 0.07 fehlt", "0.27 ist das Treppenhaus", "Maßstab: Gebäude ist 40 m breit"). Der Agent ändert deterministisch, nie per Raten.
6. Speichern erst nach klarem Ja (derselbe Bestätigungsschutz wie bei `propose_change`: Karte, nächste Nachricht, klares Ja). Danach lädt das Gebäude und alle Tools funktionieren darauf.

## Bausteine und Besitz
| Baustein | Inhalt | Wer |
|---|---|---|
| `building_agent/level4/extract.py` | Vision-Aufruf mit Structured Output (Tool-Schema statt Freitext-JSON), Retry bei ungültigem JSON, Bildgrößen-Limit | Jennifer |
| `building_agent/level4/convert.py` | Pixel zu Metern aus der bekannten Länge, y-Achse drehen, Türen auf die gemeinsame Wand projizieren (`add_door`-Logik), Treppen und Aufzüge als `vertical_connectors` mit Stop-Räumen je Etage, kleine Lücken schließen | Jennifer |
| `building_agent/level4/validate.py` | Prüfungen und Befundtext (siehe unten) | Jennifer |
| `building_agent/level4/tools.py` und Einbindung in `tools.py` | `build_from_plan(image, level, known_length_m)`, `fix_building(...)` (Tür, Raumtyp, Maßstab), `save_building(confirm)` mit Bestätigungsschutz | Jennifer |
| `scripts/eval_level4.py` | Läuft die Pipeline auf Dev-Etagen und misst gegen das Original (Raum- und Tür-Recall, Fläche, Routenfehler), mit Kosten | Jennifer |
| Web: Upload-Endpunkt, Vorschau als SVG, Maßstab-Eingabe, Speichern-Knopf | Datei-Upload (PNG, JPG, Limit), Aufruf der Extraktion im Hintergrund (10 bis 20 s mit Fortschritt), Vorschau mit auffälligen Stellen rot | Leonie |

## Validierung (vor dem Speichern, Befunde in einfachen Worten)
- Polygon gültig, Fläche über 1 m², keine große Überlappung.
- Jede Tür verbindet zwei verschiedene bekannte Räume oder `outside` und liegt an deren gemeinsamer Wand (höchstens 0,6 m).
- Jeder Raum erreichbar (eine Zusammenhangskomponente inklusive `outside`), mindestens ein Eingang. Das war im Spike der beste Indikator für schlechte Extraktion.
- Plausible Maße: Flächen 2 bis 300 m², Türbreite 0,7 bis 2,5 m.
- Mehrere Etagen: Treppen und Aufzüge haben auf jeder Etage einen Stop-Raum, sonst fragt der Agent nach.
- `scripts/preflight.py` (Leonie) als letzte Hürde.

## Akzeptanzkriterien
1. **Pipeline-Qualität auf sauberen Plänen** (procedural und ResPlan, mindestens 8 Dev-Etagen): Raum-Recall und Precision mindestens 0,95, Tür-Recall mindestens 0,90, Flächenfehler Median höchstens 3 %, Routenfehler Median höchstens 3 % (bei richtigem Maßstab), jeder Befund "Raum ohne Weg" bei sauberen Plänen höchstens 1 von 10 Etagen.
2. **Swiss-Pläne**: keine Zusage. Gemessen und im Bericht ausgewiesen. Der Befund muss schlechte Etagen erkennen (Anteil der Etagen mit unerreichbaren Räumen, bei denen der Agent warnt: 100 %).
3. **Gespräch**: Test (live, wie `tests/live/`) mit Skript: Bild, Etagenfrage, Maßstabsfrage, Vorschau-Karte, Korrektur "Tür fehlt", Ja, danach Routenfrage auf dem neuen Gebäude beantwortet richtig. Auch Gegner-Varianten: "ja" ohne Karte, Maßstab fehlt, kaputtes Bild.
4. **Sicherheit**: Speichern nur nach Karte und klarem Ja. Hochgeladene Dateien nur PNG und JPG bis 10 MB, Pfad nur im festen Ordner `agent_output/uploads/`, keine Pfadübergabe vom Browser, Key bleibt auf dem Server.
5. **Kosten und Zeit**: Pro Etage höchstens 60 Sekunden und 10 Cent, Kosten werden im Eval ausgegeben.
6. **Der Rest bleibt grün**: `scripts/check.sh` ohne Key, bestehende Tests unverändert.

## Phasen (jede für sich lieferbar)
- **Phase 1 (Demo-Schnitt, ca. 8 bis 10 h):** Eine Etage, Maßstab per Frage, Extraktion mit Structured Output, Konvertierung, Validierung, Eval-Skript, Gespräch ohne Web (per Pfad im Chat).
- **Phase 2 (ca. 5 bis 6 h, Leonie):** Upload und Vorschau in der Seite.
- **Phase 3 (Reserve, ca. 6 h):** Mehrere Etagen mit Treppen und Aufzügen, Prompt v2 (erst zählen, dann zeichnen) gegen fehlende Türen, Kacheln bei großen Bildern.

## Offene Fragen an die Organisatoren
Wie prüfen die automatischen Checks Level 4: gibt die Jury Pläne vor (Format: PNG, PDF, JSON-Strukturdatei?) und prüft dann Fragen auf dem gebauten Gebäude, oder vergleicht sie das erzeugte `building.json` mit einem Original? Welche Pläne und wie viele? Wie viel Zeit pro Gebäude ist erlaubt? Gibt es einen Maßstab im Plan oder müssen wir fragen?

## Risiken
Falscher Maßstab macht alle Längen falsch, der Graph bleibt richtig. Echte Architektenpläne sind schwerer als die Kit-Bilder. Swiss-Pläne verlieren kleine Räume und viele Türen. Ein Plan-Upload ist ein neuer Eingabeweg: Dateityp, Größe, Pfad strikt prüfen.
