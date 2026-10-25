# Spec: Prüfrunde (Entscheidung Sonntag früh, Jennifer und Leonie)

Status: Entwurf zur Entscheidung. Es gibt kein "nach dem Freeze": entweder bis 13:00 gemergt oder gestrichen (dann Video-Ersatzszene in `docs/submission/VIDEO_2MIN.md`).

## Ziel
"Hey Wanda, inspection round: all fire extinguishers on the ground floor, I start at the entrance in Main aisle H-B3" ergibt die kürzeste Runde über alle passenden Geräte, Station für Station geführt ("Stop 2 of 5"), mit "done" weiter. Facility Manager: "What if we add a door here?" zeigt, um wie viel die Runde kürzer wird. Zahlen im Video: 5 Stopps, 100 m; mit Tür zwischen Production zone H-A2 und Server room 0.16: 62 m (`train/proc-factory-train-015`).

## Was es schon gibt
| Teil | Wo | Stand |
|---|---|---|
| Seite: Runde planen, zeichnen, Station für Station, "Try a door" | Leonies `feat/twin-round` (`twin/src/round/*`, `ui/Round.*`, Einhänger in `ui/Walk.tsx`) | **nur auf Leonies Laptop**, nicht gepusht |
| Agent-Werkzeug `plan_round` | Leonies `feat/agent-plan-round` (neue Datei unter `building_agent/`) | **nur auf Leonies Laptop** |
| Touren in fester Reihenfolge (Benchmark-Art `tour`, `via`) | `building_agent/routing.py`, `guide_tools.py` | auf `main` |
| Wirkung einer neuen Tür auf Wege | `building_agent/impact.py`, Karte und Ja | auf `main` |
| Ortswissen mit Zeit (Notizen an Geräten) | `building_agent/knowledge.py` (K1) auf `main`, Werkzeuge (K2) kommen | passt zur Runde: an jeder Station Hinweise vorlesen |
| Begleiten, Punkt folgt "Next", Walk with me, Hey Wanda "done" lokal | `twin/` auf `main` | passt |

## Weg A (bevorzugt): Leonies Stand übernehmen
1. Leonie pusht `feat/twin-round`, `feat/agent-plan-round` gleich nach dem Aufwachen (spätestens 9:00).
2. Jennifers Sitzung führt beide auf `main` zusammen: Konflikte mit `Walk.tsx` (Punkt folgt Next, Walk with me), `tools.py`/`agent.py` (K2 Ortswissen) lösen, Leonies Code gewinnt bei ihrer Logik.
3. Prüfen: `plan_round` deterministisch (Reihenfolge nearest neighbour + 2-opt auf Tür-zu-Tür-Längen aus unserem Routing, gleiche Längen wie `/api/route`), Live-Suite grün (Werkzeug neu), Browser-Tests für die Runde, Testantworten byte-gleich.
4. Entscheidung zu Leonies Frage (zwei Startknöpfe): **A**, die normale Routenkarte während einer aktiven Runde ausblenden (`roundStatus().active` in `ui/Card.tsx`).
5. Verbinden mit Ortswissen: an jeder Station die jetzt gültigen Fakten des Geräts/Raums vorlesen (K2-Werkzeug bzw. `state.facts`), "Hey Wanda, note …" an der Station hängt den Fakt an das Gerät.

## Weg B (Fallback, wenn Leonie bis 9:00 nicht gepusht hat): Server-Teil selbst bauen, Seite minimal
- `building_agent/inspection_round.py`: `plan_round(bm, asset_type|category, scope (Gebäude/Etage/Bereich), start)` → Stationen (Geräte-ID, Raum, Etage), Reihenfolge (nearest neighbour + 2-opt, höchstens 30 Stationen), Gesamtlänge, Satz "5 fire extinguishers on the ground floor, about 100 m"; setzt die Route mit `via` wie bestehende Touren, damit Seite und Begleiten sie zeigen (Schritte = Stationen).
- Werkzeug in `tools.py` + eine Prompt-Zeile; "done" beim Begleiten springt zur nächsten Station (vorhandene Begleit-Logik).
- Was-wäre-wenn: `impact.py` liefert für eine vorgeschlagene Tür zusätzlich "Runde vorher/nachher" (Länge der aktiven Runde neu gerechnet), Karte und Ja wie heute.
- Seite: keine neue Oberfläche; die Runde erscheint als normale Route mit Stopps, das Begleit-Sheet zeigt "Stop n of m" aus den Schritten.
- Aufwand etwa 2 Stunden (Server + Live-Suite).

## Akzeptanz (beide Wege)
- Demo-Gebäude `train/proc-factory-train-015`, Start "entrance in Main aisle H-B3": 5 Stopps, Länge gleich `/api/route` für dieselbe Reihenfolge (±1 m), Reihenfolge nicht schlechter als jede andere bei ≤ 8 Stopps (Brute-Force-Test).
- Mit Tür zwischen Production zone H-A2 und Server room 0.16: Runde kürzer (Video: 62 m), Karte nennt beide Zahlen.
- "done" geht weiter, "how far" sagt Restmeter, End route beendet die Runde.
- Keine Änderung an Benchmark-Antworten (`SUBMISSION/answers.json` neu erzeugen und vergleichen), Live-Suite grün.

## Zeitplan
- bis 9:00 Leonie pusht (Weg A) oder Jennifer startet Weg B.
- bis 10:30 gemergt und geprüft.
- danach Video; ohne Runde Ersatzszene aus `VIDEO_2MIN.md`.
