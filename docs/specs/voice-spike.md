# Voice-Spike: Sprache rein und raus in der 2D-Seite

Status: Ergebnis des Spikes (Block C in `docs/specs/phase-2.md`). Kein Produktionscode. Prototyp: `spikes/voice/index.html`.

## Frage
Wie bekommt der Gebäude-Agent (`Session(building_map).ask(text) -> str`, Claude-Tool-Loop, Deutsch oder Englisch) Sprache rein und raus, in der Stdlib-Seite (`web/`), für die Demo, mit ElevenLabs-Credits der Organisatoren? Ohne ElevenLabs-Key in dieser Umgebung, daher stammt alles aus der aktuellen Doku, nichts wurde gegen die API getestet.

## 1. ElevenLabs Agents Platform mit unserem LLM

Ja, unsere `Session` kann das Gehirn bleiben, aber mit Aufwand.

| Punkt | Befund (Quelle) |
|---|---|
| Vertrag | Eigener Server muss OpenAI-kompatibel sein: Chat Completions (`/v1/chat/completions`) oder Responses (`/v1/responses`) (docs: agents-platform/customization/llm/custom-llm) |
| Streaming | Pflicht: "Both endpoints must return responses in SSE" mit `text/event-stream`, Chunks `data: {json}`, Ende mit `data: [DONE]` |
| Erreichbarkeit | Doku-Beispiel nutzt ngrok, Server muss aus dem Internet erreichbar sein. Localhost braucht also einen Tunnel (ngrok, cloudflared) |
| Auth zu unserem Server | Auf der Seite nicht dokumentiert, im Dashboard prüfen (Header/Secret) |
| Model-ID | Wird im Dashboard eingetragen und kommt im Feld `model` an |
| Füller | Bei langsamem LLM kann man eine Füllphrase mit Endung "... " vorab streamen, damit die Sprache fließt |
| Server-Tools | Webhook-Tools rufen externe URLs mit Parametern, die der Agent erzeugt. Ob localhost geht, steht nicht in der Doku, also Tunnel annehmen |
| Sprachen | TTS-Modelle decken Deutsch ab (Flash v2.5: 32 Sprachen). Die Übersichtsseite nennt Deutsch nicht explizit, im Dashboard testen |
| Latenz | Auf der Plattform-Seite keine Zahl. Unsere Latenz ist die Tool-Loop-Zeit (mehrere Sekunden) |

Was unser Server bräuchte: `POST /v1/chat/completions`, nimmt `messages`, nimmt nur die letzte User-Nachricht, ruft `Session.ask()` (blockierend, kein Streaming), schickt die Antwort als SSE-Chunks plus `[DONE]`. Die Tool-Calls macht `Session` intern, ElevenLabs sieht nur Text. Die System-Tools von ElevenLabs (Sprache erkennen, Gespräch beenden) kommen als OpenAI-`tools` an, wir müssten sie ignorieren oder durchreichen.

Probleme:
- Zwei Gesprächsverläufe (ElevenLabs hält Historie, `Session` hält ihre eigene). Wir ignorieren deren Historie, Unterbrechungen (Barge-in) verfälschen aber, was die `Session` für gesagt hält.
- Die Seite muss mitbekommen, dass die Karte sich geändert hat (Schließungen, Routen). Dafür bräuchte sie Polling oder einen Event-Kanal, den `web/` heute nicht hat.
- Tunnel, Agent im Dashboard anlegen, Abhängigkeit vom WLAN im Saal, mehr Teile, die ausfallen.

## 2. Einfach: Browser-STT plus ElevenLabs-TTS vom Server

| Punkt | Befund |
|---|---|
| STT | Web Speech API (`webkitSpeechRecognition`), `lang = "de-DE"` oder `"en-US"`, `interimResults` für Live-Text. Funktioniert in Chrome und Edge, in Firefox nicht. Im Prototyp erkannt (siehe unten) |
| TTS-Endpunkt | `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}` und Stream-Variante `.../{voice_id}/stream` ("Streaming audio data") |
| Auth | Header `xi-api-key`, Key nur serverseitig in `.env` (z. B. `ELEVENLABS_API_KEY`), nie im Browser |
| Modelle | `eleven_flash_v2_5`: Deutsch, ca. 75 ms Modelllatenz (ohne Netz), 40.000 Zeichen Limit, halber Preis. `eleven_multilingual_v2` (Default): Deutsch, ruhiger und natürlicher, langsamer, 10.000 Zeichen. `eleven_v3`: dramatisch, 5.000 Zeichen, nicht für schnelle Dialoge. Turbo v2.5 ist deprecated (docs: overview/models) |
| Sprache erzwingen | `language_code` (ISO 639-1) geht bei Flash v2.5, nicht bei Multilingual v2 |
| Format | `output_format` Query, Default `mp3_44100_128`. Für den Browser: `mp3_22050_32` (klein, schnell) oder `mp3_44100_128`. `<audio>` spielt MP3 direkt |
| Preis | API: Flash/Turbo 0,04 USD pro 1.000 Zeichen, Multilingual v2 und v3 0,08 USD (elevenlabs.io/pricing/api). Mit Organisator-Credits egal, kurze Antworten halten es trotzdem klein |
| Stimme | Eine Stimme mit gutem Deutsch aus der Voice Library wählen, `voice_id` in `.env`. Mehrsprachige Stimmen sprechen auch Englisch. Im Dashboard 2 bis 3 Kandidaten anhören |
| Latenz | Eine Anfrage pro Antwort. Mit Flash und kurzem Text typisch unter einer Sekunde bis zum ersten Byte (Annahme, nicht gemessen) |

Als Fallback ohne Key: `speechSynthesis` (Browser-Stimme) ist im Prototyp enthalten und gibt dieselbe Schnittstelle.

## 3. Empfehlung

**Option 2** (Browser-STT plus serverseitiges ElevenLabs-TTS). Gründe:
- 1 bis 2 Stunden reichen, kein Tunnel, kein Dashboard-Setup, `Session` bleibt unangetastet.
- Ein Verlauf, eine Wahrheit. Die Verständniskarte und das Ja laufen über denselben `/api/chat`, den die Seite schon nutzt.
- Fällt etwas aus, bleibt der Text. Die Plattform-Variante hat mehr Ausfallpunkte (Tunnel, WLAN).
- Die Tool-Loop braucht Sekunden, ein Echtzeit-Voice-Agent bringt dafür keinen Vorteil, weil das Gehirn der Engpass ist.

Option 1 nur, wenn Zeit übrig ist und das Echtzeit-Gefühl (Unterbrechen mitten im Satz) gewünscht wird.

### Minimales Design

Dateien (alle neu, bis auf kleine Ergänzungen in `web/server.py` und `web/static/app.js`):

| Datei | Inhalt |
|---|---|
| `web/speech.py` | `speak_text(text, lang) -> bytes` (ruft ElevenLabs per `urllib`, kein neues Paket), `spoken_version(reply, lang) -> str` (kürzt, siehe unten) |
| `web/server.py` | `POST /api/speak` mit `{text, lang}`, Antwort `audio/mpeg`; `/api/status` meldet `voice_available` |
| `web/static/voice.js` | Mikro-Knopf, Erkennung, Wiedergabe, Stopp-Knopf |
| `tests/test_speech.py` | `spoken_version` und Fehlerpfade mit gefaktem HTTP, keine echten Aufrufe |
| `.env.example` | `ELEVENLABS_API_KEY=`, `ELEVENLABS_VOICE_ID=` |

Ablauf in der Seite:
1. Knopf "Sprechen" (Push-to-talk, ein Klick startet, Ende bei Pause). Start erst nach Klick, das erfüllt auch die Autoplay-Regel.
2. Erkennung liefert Text, der Text geht in das bestehende Chat-Feld und über `/api/chat`, der Nutzer sieht ihn und die Antwort als Text.
3. Antwort: `POST /api/speak` mit `spoken_version(reply)`, Browser spielt per `new Audio(URL.createObjectURL(blob))`.
4. Nach `ended` startet die Erkennung nur dann wieder, wenn die Antwort eine Rückfrage oder Verständniskarte war (endet auf "?" oder enthält die Bestätigungsaufforderung). Sonst bleibt das Mikro aus.
5. Stopp-Knopf und Klick auf Sprechen während der Wiedergabe: `audio.pause()`, `recognition.abort()`. Das ist unser Barge-in, ohne Echtzeit-Erkennung.
6. Sprache: Umschalter DE/EN, Standard aus der Seite. Auto-Erkennung wäre unzuverlässig.

Kein Always-on: im lauten Saal und bei Eigenecho (Lautsprecher in das Mikro) ist Push-to-talk deutlich robuster. Während der Wiedergabe ist das Mikro aus.

Kürzen für die Sprache (`spoken_version`):
- Verständniskarte: nur die Kernaussage vorlesen ("Ich verstehe: ... Soll ich das so machen?"), Details bleiben im Text. Dafür erkennt die Funktion die Kartenüberschrift und nimmt den ersten Satz plus die Rückfrage.
- Schrittlisten: nur die ersten 3 Schritte, dann "und noch N weitere Schritte, siehe Bildschirm". Nummerierung, Markdown, Klammern und die `Answer:`-Zeile entfernen.
- Maximal ca. 400 Zeichen, hält die Latenz klein.
- Raumnamen: kleine Aussprache-Tabelle (z. B. "UG" zu "Untergeschoss", "R. 1.02" zu "Raum 1.02", Abkürzungen ausschreiben), Zahlen mit Punkten ausschreiben. Datei `web/speech.py`, Tabelle erweitern nach dem ersten Hörtest.

Fehlerfall: `/api/speak` liefert bei jedem Fehler (kein Key, HTTP-Fehler, Timeout nach 5 s) Status 502, die Seite fällt auf `speechSynthesis` zurück oder bleibt stumm. Der Text steht immer da.

## 4. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Autoplay-Regel: Audio ohne Nutzergeste wird geblockt | Wiedergabe nur nach Klick auf Sprechen/Senden starten, beim ersten Klick ein stilles `audio.play()` zum Freischalten. Bei `NotAllowedError` Knopf "Vorlesen" zeigen |
| Mikro auf `http://127.0.0.1` | `127.0.0.1` und `localhost` gelten als sicherer Kontext (im Prototyp `isSecureContext = true`). Auf einer anderen IP (Laptop-Netz) kein Mikro. Chrome fragt einmal, vorher im Saal erlauben |
| Web Speech braucht Internet | Chrome schickt Audio an Googles Dienst. Ohne WLAN Fehler `network`. Text-Eingabe bleibt Fallback, Hotspot als Plan B |
| Lauter Saal | Push-to-talk, Headset-Mikro oder Laptop nah am Mund, Transkript sichtbar machen, Nutzer kann korrigieren und Enter drücken |
| Erkennung ändert Namen und Zahlen | Transkript vor dem Senden kurz zeigen. Ja/Nein-Antworten funktionieren robust, Eigennamen nicht |
| Raumnamen falsch gesprochen | Aussprache-Tabelle, Test mit echten Raumnamen aus den Dev-Gebäuden |
| ElevenLabs-API-Ausfall oder Rate-Limit | 5-s-Timeout, Fallback Browser-Stimme, danach Text |
| Latenz Tool-Loop plus TTS | Sofort "Moment ..." anzeigen, Antwort kurz halten, Flash-Modell |
| Eigenecho | Mikro erst nach `ended` der Wiedergabe starten |
| Key-Leck | Nur serverseitig, `.env` ist ignoriert, Key nie loggen |

## Prototyp (ohne Key)

`spikes/voice/index.html`: Web-Speech-Erkennung mit de-DE/en-US-Umschalter, Live-Transkript, Fehlerstatus und ein Test der Browser-Stimme. Start: `cd spikes/voice && python3 -m http.server 8799 --bind 127.0.0.1`, dann http://127.0.0.1:8799/index.html in Chrome.

Getestet in Chrome (Claude-in-Chrome): Seite lädt, `SpeechRecognition` vorhanden, `speechSynthesis` vorhanden, `isSecureContext` true. **Nicht getestet:** echte Spracherkennung (Mikro-Erlaubnis und Sprechen nicht automatisierbar), Erkennungsqualität Deutsch, ElevenLabs (kein Key).

## Bauplan (eine Person)

| Schritt | Stunden |
|---|---|
| `web/speech.py`: `spoken_version` plus Aussprache-Tabelle plus Tests | 0,5 |
| `/api/speak` und Status-Flag in `web/server.py`, Fallback bei Fehler | 0,3 |
| `web/static/voice.js`: Sprechen, Wiedergabe, Stopp, Auto-Zuhören nach Rückfrage | 0,7 |
| Hörtest mit echten Raumnamen, Stimme wählen (Key nötig) | 0,3 |
| Summe | ca. 1,8 |

Dateiliste: `web/speech.py`, `web/static/voice.js`, `tests/test_speech.py`, Änderungen in `web/server.py`, `web/static/index.html`, `.env.example`, `web/README.md`.

## Was braucht den Key, was nicht

| Ohne Key baubar und testbar | Mit Key der Organisatoren |
|---|---|
| Mikro-Knopf, Erkennung, Transkript, Sprachumschalter | Echte Anfrage an `/v1/text-to-speech/...` |
| `spoken_version` (Kürzen, Schritte, Aussprache) mit Unit-Tests | Stimme und Modell wählen, Deutsch-Qualität hören |
| `/api/speak` mit gefaktem HTTP, Fehlerpfad, Fallback Browser-Stimme | Latenz bis zum ersten Byte messen |
| Autoplay-Verhalten, Stopp, Wiederhören nach Rückfrage (mit `speechSynthesis`) | Aussprache der Raumnamen prüfen |

## Offene Fragen an die Organisatoren
- ElevenLabs-Key, Region (EU oder US) und Kontingent in Zeichen oder Credits? Dürfen wir `eleven_flash_v2_5` und eine Voice-Library-Stimme nutzen?
- Wie ist der Aufbau bei der Bewertung: eigener Laptop mit Mikro und Lautsprecher, oder ein Raumsystem? Gibt es stabiles WLAN (Web Speech braucht Internet)?
- Zählt Voice, wenn die Eingabe über Browser-Erkennung läuft, oder wird ElevenLabs für beide Richtungen erwartet?
- Wird der Browser vorgegeben (Chrome)?

## Quellen
- https://elevenlabs.io/docs/agents-platform/customization/llm/custom-llm
- https://elevenlabs.io/docs/agents-platform/customization/tools/server-tools
- https://elevenlabs.io/docs/api-reference/text-to-speech/convert
- https://elevenlabs.io/docs/api-reference/text-to-speech/stream
- https://elevenlabs.io/docs/overview/models
- https://elevenlabs.io/pricing/api

## API (Vertrag für `web/static/voice.js`)

Backend steht (`web/speech.py`, `web/server.py`). Modell `eleven_flash_v2_5`, `language_code` wird nicht gesendet (Sprache wird aus dem Text erkannt).

`GET /api/status` enthält `speech_available` (true, wenn Key und Voice-ID in der Umgebung stehen; die Werte werden nie ausgegeben).

`POST /api/speak`, JSON `{ "text": "<voller Agent-Text>", "lang": "en" | "de", "voice_id": "<optional>" }`. `lang` ist optional, Standard `en` (die Demo ist englisch); `de` liefert die deutschen Sprechtexte ("und N weitere Schritte, siehe Bildschirm", Quadratmeter). Der Server kürzt selbst (`spoken_version`), die Seite schickt den ungekürzten Text. Der Request braucht `Content-Type: application/json`, Origin und Host müssen `127.0.0.1:<port>` oder `localhost:<port>` sein (sonst 403), höchstens 1 Request pro Sekunde und 30 pro Minute (sonst 429). `voice_id` aus dem Body zählt nur, wenn `ELEVENLABS_VOICE_ID` nicht gesetzt ist, und muss `[A-Za-z0-9]{10,40}` sein (sonst 400).

| Status | Inhalt | Was die Seite tut |
|---|---|---|
| 200 | `audio/mpeg` (Bytes) | `new Audio(URL.createObjectURL(blob)).play()` |
| 400 | JSON `{error}` (nichts zu sagen) | nichts abspielen |
| 502 | JSON `{error, fallback}` (Quota, 401, Timeout nach 5 s, ElevenLabs-Fehler) | `speechSynthesis` mit dem Text, sonst stumm; Text steht immer da |
| 503 | JSON `{error}` (kein Key oder keine Voice-ID) | wie 502; besser: `speech_available` aus `/api/status` beim Laden lesen und gleich die Browser-Stimme nutzen |

Push-to-talk:
1. Klick auf Sprechen: `SpeechRecognition` starten, Standard `lang = "en-US"` (`de-DE` als Option im Umschalter), Transkript anzeigen.
2. Ende der Erkennung: Text per `/api/chat` senden, Antwort als Text anzeigen.
3. Danach `POST /api/speak` mit der Antwort und dem gewählten `lang` (`en` oder `de`), Audio abspielen. Mikro ist während der Wiedergabe aus.
4. Nach `ended` die Erkennung nur neu starten, wenn die Antwort eine Rückfrage oder Verständniskarte war.
5. Stopp oder erneuter Klick auf Sprechen: `audio.pause()` und `recognition.abort()`.
