# Stand Level 1 bis 4 (Übersicht für Jennifer und Leonie)

Stand: 24.10.2026, spät. Quelle der Wahrheit für Details: `docs/specs/levels-1-4-gaps.md`, `docs/STATUS.md`, `docs/eval-log.md`.
Legende: **fertig** = in `main` und getestet. **läuft** = ein Agent baut es gerade. **fehlt** = noch niemand dran, Besitzer genannt. **offen** = Frage oder Test.

## Level 1: Locate
| Teil | Stand |
|---|---|
| Suche, Gruppen ("second press"), "east lift", Mehrdeutigkeit | fertig im Agenten, offline und live getestet |
| Funde auf dem Plan | **fehlt**, Leonie (W-L1a, geclaimt). Das Feld `located` kommt schon im Chat. |
| Auswahl per Klick ("this one", "move it here") | Server und Agent fertig (`web/selection.py`, `get_selection`, Vertrag in `docs/specs/levels-1-4-gaps.md` "Page contract"). **Seite fehlt**, Leonie: Klick, Chip, Kontext senden. |
| Voice-Handtest | **offen**, nie am Gerät getestet |

## Level 2: Route
| Teil | Stand |
|---|---|
| Tür-zu-Tür-Modell, stufenfrei, Sperrungen, Touren (99,2 % volle Punkte), Abbiegehinweise | fertig |
| Seite zeichnet die Route des Agenten | **fehlt**, Leonie (W-L2a, geclaimt). Die Seite nutzt noch das alte Modell und verliert Zwischenstopps. |
| Gabelstapler und Bereiche | grob (`find_forklift_route`), Synera-Frage offen |
| "Nur Synera-Modell zählt?" | **offen**, Frage an Synera |

## Level 3: Scale
| Teil | Stand |
|---|---|
| Mehrere Etagen | fertig |
| Campus: Format, Adapter, Prüfung | fertig (`campus.py`, vier Adapter, Spec `docs/specs/level3-campus.md`) |
| Campus-Routing und Werkzeuge | **läuft**, `feat/campus-routing` (Routen über Gebäude, `connect_buildings` mit Karte und Ja, Live-Gespräche) |
| Oberfläche (Gebäudewahl, Route über Gebäude) | **fehlt**, Leonie (W-L3d), nach dem Routing |
| Prüfung durch Synera | **unbekannt**, Frage auf der Liste (`docs/SYNERA_QUESTIONS.md`) |

## Level 4: Build
| Teil | Stand |
|---|---|
| Pipeline: Modell, Segmentierung, Marker, Prüfung, Karte, Speichern | fertig, End-zu-End mit echtem Aufruf getestet (ResPlan: 5,7 s, Route im neuen Gebäude) |
| Qualität sauber und OSM | sehr gut (OSM Raum-Recall 1,00, Tür-Recall 0,96) |
| Swiss | **schwach**: Türen zwischen Wohnung und Treppenhaus sind im Bild nicht gezeichnet, nichts findet sie. Vorschlag "nur Treppenhaus-Türen mit Bestätigung" noch nicht gebaut. |
| Mehrere Etagen live, Plan mit Möbeln | **offen**, Test steht an (unter $1) |
| Weboberfläche (Upload, Vorschau, Speichern) | von Leonie gemergt, **von mir nicht im Browser geprüft** |
| Seite kennt das neue Gebäude nach dem Speichern | **fehlt**, Leonie (W-L4b, geclaimt) |
| Fremder Stil (andere Farben, Scans, echte Pläne) | ungetestet, Rückfall auf Modell mit Warnung |

## Quer zu allen
| Teil | Stand |
|---|---|
| Edits per Sprache: Platzieren (Ecke, Wand, neben X, Punkt, Drehung), `add_asset`, Undo | fertig im Agenten. **Seite zeigt Änderungen noch nicht** (Leonie, Vertrag: `state_view` Felder `added_assets`, `moved_assets`, `removed_assets`, `removed_openings`, `widened_openings`). |
| Abgabe: Test-CSV (145 Zeilen, alle vom Parser beantwortet) | formal abgabefertig. Format am Sonntag ungeklärt. Stichprobe von Hand und neuer `known-good`-Tag stehen aus. |
| Fragen an Synera | `docs/SYNERA_QUESTIONS.md` |
| Demo, Technik-Text, Pitch | Entwürfe in `docs/submission/`, Video fehlt |

## Neu aus der Synera-Präsentation ("Industrial Agents Hackathon.pdf")
Abgleich mit dem, was wir können (ehrlich):
| Punkt in der Präsentation | Stand |
|---|---|
| "Which of the three presses is line 4, and how do I get there?" | "Presse in Zone" und "zweite Presse" ja, "line 4" **gibt es in den Daten nicht**. Der Agent fragt nach der Zone und nennt "line 4" nur als Hinweis. |
| "Aisle 4 is blocked. Fastest route to dock B?" | Sperren und neu routen ja (Gabelstapler grob). **Lücke:** In den Daten heißen Gänge nur "Main aisle H-C1" (112 Räume, keine Nummer 4) und es gibt **keine Räume mit "Dock"** im Namen. "Aisle 4" und "dock B" lassen sich also nicht eindeutig auflösen. Der Agent muss nachfragen und die Gänge nennen. |
| "Where is the steel drum delivered yesterday?" (Dinge bewegen sich, die Karte muss mit) | **Lücke:** Wir haben keinen Zeitverlauf (wer hat was wann bewegt) und keinen Lieferfluss. Es gibt `move_asset` und Undo, aber keine Zeitstempel und keine Abfrage "wo war X gestern". Es gibt auch kein Fass in den Daten (nur Palettenregale, 969, und Hubwagen, 79). Optionales Add-on "Make things move": Ereignisprotokoll mit Zeit. |
| Persona Servicetechniker: "Hands full, phone in pocket. Wants voice and 'turn left at the press'" | fertig: Dreierschritte, Landmarken, Abbiegewörter, Voice (UI-Test offen) |
| Persona Rollstuhl: "step-free routes and wide doors, every time, without asking twice" | Stufenfrei ja. **Türbreite und "ohne nochmal zu fragen" (Profil merken) ist noch nicht gebaut**, siehe Idea Fridge Accessibility-Modus (`docs/IDEAS.md`). |
| Persona Facility Manager: "Moves a machine, closes a lift, adds a door. The map must keep up." | fertig im Agenten, Seite zieht noch nach (siehe oben) |
| "Use what is possible today": Voice in/out, Rückfragen, zeigt, was es verstanden hat, Directions people can follow | fertig, außer "Live updates from a scan" und "AR on the phone" (optional, nicht geplant) |
| Schlussfolie: isometrische 3D-Etagen über dem 2D-Plan, Spielkarte (Mario), Among-Us-Karte (mehrere Spieler), Kartenroute | Hinweis auf Darstellung: 3D und Mehrnutzer wirken wichtig. 3D steht im Idea Fridge, Mehrnutzer nicht geplant. |
| Baseline-Folie: "Scale: several floors and buildings, linked by stairs and lifts" | Campus-Links haben `level_delta`, Treppen und Aufzüge zwischen Gebäuden sind damit abbildbar. |

## Weitere Spezifikationen und Ideen (nicht gebaut)
- Live-Updates mit Zeiträumen, Dokumenten und Sprache: `docs/specs/live-updates.md` (Entwurf).
- Eingangsprüfung für alle Plan-Fälle in Level 4: `docs/specs/plan-input-coverage.md` (Entwurf).
- Accessibility-Modus: `docs/specs/accessibility-mode.md` (Entwurf).
- Idea Fridge: Accessibility, 3D mit Walkthrough, Funde aus der Synera-Präsentation, Zutrittsrechte, Roadmap-Geschichte, geplante Wartungen (`docs/IDEAS.md`).
