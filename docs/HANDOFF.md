# Handoff: aktueller Stand (24.10.2026, abends)

Für jede neue Session (auch nach Account-Wechsel): zuerst `CLAUDE.md`, dann diese Datei, dann `docs/STATUS.md`. Der Plan liegt lokal bei Jennifer unter `~/.claude/plans/pasted-content-id-03a7-synera-mittel-delightful-teapot.md` und ist hier zusammengefasst.

## Wo wir stehen
- `main` (origin) enthält: alle 9 Fragetypen, Warm-up (`structured.py`, `scripts/eval_warmup.py`, `assume_closed`), Session-Chat, Landmarken-Wegbeschreibung, Verständniskarte mit Ja-Schutz, Voice-Backend (`web/speech.py`, `/api/speak`, Englisch als Standard), Sweep über alle 280 Gebäude, Live-Tests (22 von 22), Spikes für Level 4, Voice und Routenmodell, Spec `docs/specs/level4.md` (bestätigt), Verträge `building_agent/level4/schema.py`. `scripts/check.sh` ist grün (ruff format, Lint, Tests).
- Messwerte: Dev-Stichprobe 72 von 72 (Agent), Warm-up Tools 369 von 369, Agent 18 von 18 gemischt, Sperrungen 26 von 29, Testlauf `data/test` 24 von 24 formal in Ordnung (noch altes Routenmodell). Routen mit Kit-Modell 92,4 % volle Punkte nach Synera-Regel, neues Modell 99,4 %.
- Demo und Voice sind auf **Englisch**. Stimme ElevenLabs `eleven_flash_v2_5`, Voice-ID in `.env`, klingt gut.

## Läuft gerade (Welle 1, Agenten in Worktrees unter `.claude/worktrees/`)
| Branch | Inhalt | Status bei Übergabe |
|---|---|---|
| `feat/route-model` | Tür-zu-Tür-Routenmodell `building_agent/routing.py` | größtenteils gebaut, Agent schließt Schwelle 98 %, Cache, Doku, Push ab, noch nicht gemergt |
| `feat/level4-extract` | Level 4 Schritt 1a, Vision-Extraktion | läuft |
| `feat/level4-convert` | Level 4 Schritt 1b, Konvertierung und Prüfung (Round-Trip-Tests) | läuft |
| `feat/impact` | "What changes?" für das ganze Gebäude (`impact.py`) | läuft |
| `feat/find-tools` | `find_asset` (zweite Presse, Zonen) und `find_connector` (east lift) | läuft |
| `feat/question-parser` | deterministischer Fragen-Parser als schneller Weg, LLM als Reserve | läuft |
Jeder Agent pusht seinen Branch und meldet sich. Danach: frischer Review-Agent, `scripts/check.sh`, Merge nach `main`, Einbindung in `tools.py` und `agent.py` (je eine Zeile, die macht die Hauptsession).

## Nächste Schritte (Reihenfolge)
1. Welle 1 mergen (nach Review). Einbindungen setzen: `find_route` neu (Routenmodell), `what_changes` und Karten-Effekt, `find_asset`, `find_connector`, Parser in `answer()`.
2. Welle 2: Edit-Operationen (`remove_door`, `widen_door`, `move_asset`), Level 4 Gespräch und Eval (`level4/tools.py`, `scripts/eval_level4.py`).
3. Welle 3: Campus (Level 3, erst Spec `docs/specs/level3-campus.md`), Level-4-Weboberfläche.
4. Danach: Testlauf auf `data/test` mit neuem Routenmodell, Tag `known-good`, `docs/eval-log.md`, Schleife von 20 auf 8 Runden.
5. Leonie: Voice-Oberfläche (Vertrag in `docs/specs/voice-spike.md`), Web-Anschluss (Funde aufleuchten, Türen und Geräte), Abgabe (`run_benchmark`, `preflight.py`), Demo.

## Offene Entscheidungen und Fragen an Synera
Ausgabeformat Sonntag (PDF `answers.json` oder README-CSV), Locate und Route als Fragetypen, Level 3 (mehrere Gebäude) und Level 4 Prüfung, Gabelstapler- und Bereichsregeln, Code-Freeze, Zeitlimit, Himmelsrichtungen ("east lift"). Annahmen: Kompass +x Osten, +y Norden; Campus-Format `campus.json` wird erfunden.

## Secrets und Konto
Keys nur in `.env` (git-ignoriert): `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY` (nur Text-to-Speech-Recht), `ELEVENLABS_VOICE_ID`. Beide Keys standen im Chat und werden nach dem Hackathon widerrufen. **Bei Wechsel des Anthropic-Accounts** muss in `.env` ein neuer `ANTHROPIC_API_KEY` stehen, sonst scheitern Live-Läufe und Evals. Das Ausgabenlimit lag im alten Konto auf $50 pro Monat, im neuen prüfen.

## Arbeitsregeln (Kurzfassung)
Antworten Deutsch, kurz, ohne Gedankenstriche. Commits nur auf Feature-Branches, normaler Push, nie Force. Langläufer (Live-Tests, Evals) im Hintergrund. Geteilte Dateien (`tools.py`, `agent.py`, `guide_tools.py`, `web/`) nur mit Review. Kein Merge ohne `scripts/check.sh` grün.
