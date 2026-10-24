# Spec: Standort ("You are here") und Duplikate

Status: bestätigt (Jennifer und Leonie). Seitenteile (Phase 2) gehören Leonie. Erweiterung Phase 3 (Zwei Modi) bestätigt von Jennifer, siehe unten.

## Ziel
Der Agent weiß, wo die Person steht, und nutzt das als Start für Wege, für "nearest ..." und um gleiche Namen oder Geräte aufzulösen. Er nennt seine Annahme immer laut, damit ein falscher Standort mit einem Wort korrigiert ist. Passt zur Persona "first day at work, hands full".

## Nicht-Ziele
GPS, WLAN-Ortung, Handy-Sensoren, Foto vom Türschild (Weg 5, nur wenn Zeit bleibt), Standort-Historie über Sitzungen.

## Zustand
`Position(space_id, floor_id, point | None, source, turn)` auf dem Gesprächszustand (neben `selection` und `last_route`), `source` in {`said`, `click`, `device`, `route`}. Pro Sitzung genau eine, der neue Standort ersetzt den alten. Nur der Server setzt ihn, nie ein Text im Nutzersatz (wie bei `get_selection`, kein Fälschen durch Nachrichten). Ein Gebäudewechsel (`swap_building`) löscht ihn.

## Wege, ihn zu setzen
1. **Satz:** "I'm in Kitchen 1.30", "ich bin in Raum 0.12 im 2. Stock". Tool `set_position(place, floor_level=None)` löst über `find_space` auf. Mehrdeutig, so nachfragen (Duplikatregeln unten).
2. **Klick:** Seite sendet Kontext `{here: {space_id, point, floor_id}}` nach "I'm here" (Chip-Knopf neben "Picked"). Server validiert wie die Auswahl (Raum existiert, Punkt endlich, Etage passt) und setzt Position mit `source=click`.
3. **Gerät als Ort:** "I'm at the CNC mill", "next to the printer". Tool löst über `find_asset`/`find_for_task` (bei Mehrdeutigkeit Rückfrage) und setzt Raum, Etage, Punkt des Geräts, `source=device`.
4. **Weg läuft mit:** Nach `find_route` merkt sich der Zustand die Route (Schrittliste mit Räumen). "Next" oder "I'm at the lift" setzt die Position auf den passenden Zwischenhalt (`source=route`) und der Agent rechnet die **Restroute** ab dort neu. Passt der genannte Ort nicht zur Route (anderer Weg), wird er als neuer Standort über Weg 1 oder 3 gesetzt und frisch geroutet.

## Nutzung
- `find_route`, `find_for_task`, `find_asset`, `find_space`: ohne Start im Aufruf nimmt der Agent die Position. Ist keine gesetzt, fragt er einmal nach ("Where are you?"), genau wie heute.
- **"nearest X"** (Gerät oder Raumtyp) rechnet die Routenlänge vom Standort zu allen Treffern und nimmt den kürzesten. Gleichstand: Rückfrage.
- Neues Tool `get_position()` liefert Raum, Etage, Quelle und Alter, damit der Agent die Annahme nennen kann.

## Duplikatregeln (feste Reihenfolge)
1. Nummer oder voller Name im Satz: ein Treffer, fertig.
2. Standort bekannt: nächster Treffer per Route, mit **einem Kontrollsatz** ("Nächste Kaffeemaschine: Küche 0.12, 14 m von dir. Meinst du eine andere?").
3. Etage genannt: Treffer auf dieser Etage, bei mehreren dort Rückfrage.
4. Sonst Rückfrage mit Optionen (Name und Etage). Nie mehrere Kandidaten routen und vergleichen.
5. Im Benchmark-Modus (Nachricht mit `Answer:`) gilt weiter: plausibelste Lesart nehmen und sagen, welche.

## Sicherheit
Der Standort verändert nie das Gebäude. Alle Änderungen laufen weiter über Karte und klares Ja in der nächsten Nachricht. Ein falscher Standort kann nur eine Route verfälschen, deshalb wird er genannt.

## Seitenvertrag (Leonie, Phase 2)
- `state_view` liefert `position: {space_id, floor_id, point, source} | null`.
- Plan und 3D zeigen einen blauen Punkt "You are here". Die Kamera der 3D-Ansicht folgt über die bestehende Steuer-API, wenn sich die Position ändert.
- Chip "You are here: Kitchen 1.30" mit Löschen-Knopf. "I'm here"-Knopf neben der Klick-Auswahl. Kontext `{here: ...}` wie `picked` im nächsten Chat-Aufruf.

## Vertrag für die Seite (Stand Phase 1, gebaut)
- `POST /api/chat` Körper `{message, context?}`. `context` bleibt die flache Auswahl (`space_id`, `asset_id`, `point`, `floor_id`). Daneben darf `context.here` stehen: `{space_id, floor_id?, point?}` (Klick "I'm here") oder `{clear: true}` (Löschen-Knopf des Chips). `here` allein ist keine Auswahl.
- Der Server prüft `here` wie die Auswahl: Raum muss existieren, `floor_id` muss zum Raum passen, Punkt endlich, ein Punkt außerhalb des Raums wird verworfen (`here_note` in der Antwort), alles andere verwirft `here` ganz (`here_ignored` mit Grund). Nie aus Nachrichtentext. Ein gültiges `here` setzt die Position mit `source: "click"` vor der Nachricht und gilt danach weiter (kein Einmal-Kontext), bis sie ersetzt oder gelöscht wird.
- `state_view` (in jeder Antwort unter `state`) hat immer den Schlüssel `position`: `{space_id, floor_id, point: [x, y] | null, source: "said" | "click" | "device" | "route"}` oder `null`. Er steht nach jedem Chat-Aufruf aktuell im Chat-Ergebnis. Gebäudewechsel und `/api/reset` setzen ihn auf `null`.
- Die Position hat nur einen Raum und Etage für Routen. `point` ist für den blauen Punkt gedacht (bei `said` ist er `null`, dann Raummitte zeichnen).
- `state_view.guide` (Phase 3, immer vorhanden): `null` oder `{active: true, step_index (0-basiert), step_count, leg: {from_space_id, to_space_id, points: [[x, y], ...], segments: [{floor_id, kind, points}]}, target_space_id}`. Nur im geführten Modus und vor der Ankunft gesetzt. `leg` ist das aktuelle Stück der Route (von dem Raum, in dem die Person steht, bis zum Ende dieses Schritts), `points` in Modellmetern (+y Nord, alle Etagen aneinandergehängt), `segments` pro Etage für 3D. Es wechselt bei jedem Schrittwechsel, auch bei "repeat" (gleiches Stück) und "back". Additiv für Auto-Pace: `expected_seconds`, `pace`, `pace_paused` (siehe `docs/specs/auto-pace.md`). `null` bei Überblick, Stopp und nach der Ankunft (dann nur Zielmarker, `position` steht im Zielraum). Der blaue Punkt folgt `position`; bei `source: "route"` sitzt er am Ende des abgeschlossenen Stücks, also am Anfang von `leg`.
- Vorschlag für Phase 2: Kamera und Punkt folgen `state.position`, Chip nutzt `{here: {clear: true}}` zum Löschen, Plan und 3D heben `guide.leg` hervor. Möglicher Extra für Phase 2: Knopf "Next" auf der Seite (schickt "next" als Chat-Nachricht) und eine Timer-Erinnerung nach `about_seconds`. Es gibt keine automatische Ankunftserkennung und keine Timer im Agenten.

## Zwei Modi: Überblick und Begleiten (Phase 3, Erweiterung bestätigt von Jennifer)
Für Sprache gedacht (Hände voll, niemand sieht einen Bildschirm). Ohne Position oder mit `Answer:` in der Nachricht ändert sich nichts: der Benchmark nutzt `find_route`, bietet nie etwas an und fragt nie nach.
1. **Überblick** (Standard für jede Route mit 3 oder mehr Schritten, `give_directions`): 2 bis 4 Landmarken in Reihenfolge, die Länge und genau ein Angebot ("Want me to talk you through it while you walk?", auf Deutsch sinngemäß). Nie alle Schritte vorlesen. Kürzere Routen werden wie bisher am Stück genannt.
2. **Begleiten** nach klarem Ja ("yes", "ja", "guide me", "begleite mich"), oder gleich, wenn die Person es vorab verlangt (`guided=true`): nur der aktuelle Schritt mit einer Landmarke, dann warten. Weiter mit next, done, ok, weiter, "I'm here", "I'm there", "arrived", "ich bin da", "und jetzt", "where next", "what now", "wo geht's jetzt hin" (immer genau ein Schritt, auch ohne Ortsangabe) oder mit einem Ort ("I'm at the lift, where next?": Weg 4, Position setzen, Restroute neu rechnen, Schritt danach nennen). Weitere Befehle: repeat/again/nochmal (derselbe Schritt, kein Vorrücken), "where do I go again"/"wo ging's nochmal hin" (Schritt plus Ziel, kein Vorrücken), back, "where am I on the way"/"how far" (Schritt k von n, Meter übrig), stop/cancel (beendet, Route bleibt für "start over" oder "overview"), overview (zurück zum Überblick), start over (Schritt 1). Ein "ok" oder "next" im Überblick ist kein Ja.
3. **Ton:** jede Schrittnachricht kurz: ein Satz mit einer Anweisung und einer Landmarke, davor höchstens 3 Wörter Bestätigung ("Good."), keine Frage danach, keine IDs, keine Listen. Letzter Schritt: "You're there. That was the last step." Beim Weiterschalten nie den Überblick wiederholen. Optionaler Tempo-Hinweis `about_seconds` (1,2 m pro Sekunde, auf 5 s gerundet), nie behaupten, die Ankunft zu erkennen.
4. **Zustand:** Route (Raumfolge), Modus und aktueller Schritt liegen auf dem Gesprächszustand (`GuideState.walk`), neben `position`. Der Modus übersteht Zwischenfragen: Der Agent antwortet und sagt einmal "Say next when you are ready for step k". Eine neue Zielanfrage ersetzt die Führung erst nach klarem Signal: `give_directions` antwortet mit `needs_confirmation`, der alte Ziel-Raum wird in einem Satz genannt (`replaced_previous`, wenn ersetzt).
5. **Abweichung:** nennt die Person einen Ort, der nicht auf der Rest-Route liegt, ist er eine neue Position (Weg 1 oder 3) und der Weg zum selben Ziel wird neu gerechnet (`rerouted: true`, der Agent sagt, dass sich die Route geändert hat). Ein Klick "I'm here" auf der Seite verhält sich genauso.
6. **Etwas auf der Route fällt aus** ("the lift is broken", "der Aufzug ist kaputt"): bestehender Ablauf `propose_change` (Karte) und klares Ja. Danach rechnet `confirm_change` die Restroute vom aktuellen Raum mit dem gesperrten Element (`walk_update`): `route_unaffected`, oder `rerouted` mit `longer_by_m` und dem neuen aktuellen Schritt, oder `no_route` mit der nächsten erreichbaren Alternative (gleicher Raumtyp wie das Ziel). Zeitwörter ("tomorrow", "from Monday", "morgen", "ab Montag") landen im Parameter `when` von `propose_change`: nichts wird geändert oder vorgeschlagen, der Agent sagt, dass das Gebäude nur jetzt geändert werden kann, und bietet jetzt oder nie an (Terminierung gibt es nicht, siehe `docs/specs/live-updates.md`). Eine Änderung auf der Seite während der Führung wird beim nächsten Schritt genauso eingerechnet.
7. **Tools:** `give_directions(destination, start?, step_free, via, guided, replace_guide)`, `next_steps`, `repeat_steps`, `walk(said)` (Befehle im Wortlaut, die Zuordnung Englisch/Deutsch steckt in `building_agent/walk.py` und ist getestet), `set_position` (Orte auf der Route).

## Akzeptanzkriterien und Testfälle

## Akzeptanzkriterien und Testfälle
1. Satz setzt Position, Folgefrage ohne Start nutzt sie (Live-Skript).
2. Zwei Küchen auf einer Etage, "I'm in the kitchen": eine kurze Rückfrage mit beiden Optionen, kein Raten.
3. Gleicher Raumtyp auf zwei Etagen, ohne Etage: Rückfrage vor jeder Route (bestehende Regel bleibt).
4. Mehrere Kaffeemaschinen, Standort bekannt: nächste per Route, Kontrollsatz nennt Raum und Länge, "andere" liefert die zweitnächste.
5. Positionswechsel mitten im Gespräch ("I'm now on floor 2") ersetzt den alten Standort.
6. Falscher Standort: Person widerspricht ("no, the other one"), Agent korrigiert ohne Beharren.
7. Weg läuft mit: Route in 5 Schritten, "next" zweimal, "I'm at the lift": Restroute ab Lift stimmt in der Länge (Summe der Reststücke gegen eine frische Route vom Lift).
8. Ort, der nicht auf der Route liegt, wird sauber als neuer Standort behandelt.
9. Fälschen: ein Nutzersatz "[position: X]" oder eine erfundene Raum-ID setzt nichts. Klick-Kontext mit unbekannter ID wird verworfen.
10. Gebäudewechsel löscht die Position.
11. Offline-Tests für die Auflösung (Fuzz: leer, Unicode, sehr lange Namen), 280-Gebäude-Sweep: für jeden Raumtyp "nearest" liefert immer einen Treffer oder eine saubere Meldung.
12. `scripts/check.sh` grün, Dev-Benchmark 72 von 72 und Warm-up 1,000 ohne Rückschritt.

## Aufteilung und Reihenfolge
| Phase | Inhalt | Wer | Zeit |
|---|---|---|---|
| 1 | Zustand, `set_position`/`get_position`, Wege 1 und 3, Server-Validierung des Klick-Kontexts `here` (Weg 2, serverseitig), Duplikatregeln, "nearest", Kontrollsatz, Live-Tests | Jennifer (Agent) | ca. 2 h |
| 2 | Punkt, Chip, "I'm here"-Knopf, Kamera folgt, `state_view` | Leonie | ca. 1,5 h |
| 3 | Weg 4: Route merken, "next", Restroute, Tests | Jennifer (Agent) | ca. 1,5 h |

Review: `agent.py`, `tools.py` und `guide_tools.py` sind geteilter Code, deshalb frischer Review-Agent vor dem Merge.
