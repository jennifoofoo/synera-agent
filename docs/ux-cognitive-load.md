# UX: kognitive Last senken (Synera-Hinweis 24.10. spät)

Synera (Bhushan Kotnis): UI/UX ist ein Bewertungskriterium, gutes UX senkt die kognitive Last. Quelle: https://lawsofux.com/articles/2015/design-principles-for-reducing-cognitive-load/

## Die 7 Regeln und was das für uns heißt

| Regel | Stand bei uns | Was wir ändern |
|---|---|---|
| 1. Unnötiges weglassen | Karte zeigt Koordinaten ("Point -15.7, 15.5 m"), Raster, viele graue Möbelkästen, doppelte Routenlänge (Pill "37 m route" und Sheet "37 m") | Koordinaten nur im Debug, Routenlänge nur einmal, Möbel nur ab Zoomstufe, Raster nur in 3D |
| 2. Bekannte Muster | Linksziehen drehte die Kamera statt zu verschieben | Halten und ziehen verschiebt (wie Google Maps, in Arbeit), Bottom Sheet wie Maps |
| 3. Aufgaben abnehmen | Start muss man oft selbst wählen | Start = "You are here" als Vorgabe, letzte Ziele merken, Vorschläge mit den üblichen Fragen ("nearest toilet", "way out", "coffee") als Chips, Antworten kurz, beim Begleiten ein Schritt auf einmal |
| 4. Wenige Wahlmöglichkeiten | Desktop: List, Änderungs-Pill, Etagenleiste, Step-free, Chat, Talk gleichzeitig | Pro Zustand höchstens 2 Hauptaktionen (Raumkarte: Route, I'm here). Selten Genutztes ins Menü |
| 5. Optionen als Gruppe zeigen | Etagen als eine Leiste, gut | so lassen |
| 6. Lesbarkeit | Raumnamen werden von Route und Markern verdeckt | Namen über allem mit Halo, Start- und Zielnamen nie verdeckt (in Arbeit) |
| 7. Icons nur mit Text | Chat, Mikrofon, Suche, Haus, Ausgang nur als Symbol | Hauptknöpfe mit Text ("Ask", "Talk"), Rest mit `aria-label` und Tooltip, Legende für Ausgang/Türsymbole |

## Für die Demo (Interaction 25 Punkte)
Ein Satz im Pitch: "Every screen has one job and at most two buttons; you can do everything by voice, so you never need to read the map while walking."
