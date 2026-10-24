"""Offline tests for web/speech.py and POST /api/speak. No real ElevenLabs call, no key needed."""

import json
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from web import speech
from web.server import App, make_handler
from web.speech import SpeechError, synthesize
from web.speech import spoken_version as tagged_version

SECRET = "sk_test_secret_value_123"
ID = "proc-campus-dev-000-F0-S012"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", SECRET)
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice1234567890")


# ---------- spoken_version ----------

TAG = re.compile(r' ?<break time="[0-9.]+s" /> ?')


def spoken_version(reply, **kwargs):
    """The spoken text without pause tags (the old tests check wording, pauses have their own tests)."""
    return TAG.sub(" ", tagged_version(reply, **kwargs))


def test_markdown_and_answer_line_are_removed():
    reply = "## Result\n**The lift** is `closed`.\n- Use the stairs.\nAnswer: 42"
    assert spoken_version(reply) == "Result The lift is closed. Use the stairs."


def test_only_three_steps_then_german_tail():
    reply = "Route found:\n1. Go left.\n2. Take the lift.\n3. Turn right.\n4. Walk on.\n5. Arrive."
    spoken = spoken_version(reply)
    assert "go left." in spoken and "turn right." in spoken
    assert "Walk on" not in spoken
    assert spoken.endswith("and 2 more steps, see the screen.")
    assert spoken_version(reply, lang="de").endswith("und 2 weitere Schritte, siehe Bildschirm.")


def test_single_extra_step_is_singular():
    spoken = spoken_version("1. A.\n2. B.\n3. C.\n4. D.")
    assert spoken.endswith("and one more step, see the screen.")
    assert spoken_version("1. A.\n2. B.\n3. C.\n4. D.", lang="de").endswith(
        "und ein weiterer Schritt, siehe Bildschirm."
    )


def test_three_steps_have_no_tail():
    assert "weitere" not in spoken_version("1. A.\n2. B.\n3. C.")


def test_dates_and_refs_are_kept_but_dataset_ids_go():
    spoken = spoken_version(f"On 2026-10-24 see ref 0-12-B, osm-way22744230-F0 and {ID} and swiss-abc1-F2-S004.")
    assert "2026-10-24" in spoken and "0-12-B" in spoken
    assert "osm-" not in spoken and "proc-" not in spoken and "swiss-" not in spoken and "S004" not in spoken


def test_markdown_links_tables_rules_and_bold_steps():
    reply = "See [the plan](http://x.y/z).\n---\n| a | b |\n|---|---|\n**1.** Go left.\n**2.** Go on."
    assert spoken_version(reply) == "See the plan. Step one, go left. Step two, go on."


def test_abbreviations_do_not_end_sentences():
    reply = "Das Büro ist z. B. Raum A, d. h. im Erdgeschoss, ca. 20 m2 groß. Noch ein Satz."
    spoken = spoken_version(reply, max_chars=80)
    assert spoken.endswith("groß.") and "Noch" not in spoken and "z. B. Raum A" in spoken


def test_tail_only_if_steps_survived_the_cap():
    steps = "\n".join(f"{i}. Step {i} " + "word " * 10 for i in range(1, 6))
    assert "more steps" in spoken_version(steps, max_chars=400)
    short = spoken_version(steps, max_chars=60)
    assert "more steps" not in short and "Step 3" not in short


def test_raw_ids_and_bracketed_fragments_are_removed():
    spoken = spoken_version(f"Go to the room {ID} now [{ID}]. Then step-free via lift (proc-x-1-2).")
    assert "proc-" not in spoken and "[" not in spoken and "()" not in spoken
    assert "step-free" in spoken


def test_confirmation_card_keeps_core_and_question():
    reply = (
        "I understood: close the east lift on floor 1. It is currently open. "
        "Your last route would change by 40 metres. Nothing changed yet. Should I do that?"
    )
    spoken = spoken_version(reply)
    assert spoken == "I understood: close the east lift on floor one. Should I do that?"


def test_german_card():
    spoken = spoken_version(
        "Ich habe verstanden: Aufzug 2 sperren. Auswirkung: Umweg. Soll ich das so machen?", lang="de"
    )
    assert spoken == "Ich habe verstanden: Aufzug 2 sperren. Soll ich das so machen?"


def test_pronunciation_table_and_room_numbers():
    reply = "Room 0.12 has 24 m2 and 30 m² next to the WC, 5 m away."
    spoken = spoken_version(reply)
    assert "zero point one two" in spoken
    assert "24 square metres" in spoken and "30 square metres" in spoken
    assert "toilet" in spoken and "5 metres" in spoken
    german = spoken_version(reply, lang="de")
    assert "24 Quadratmeter" in german and "W C" in german and "5 Meter" in german and "null Punkt eins zwei" in german


def test_english_card_markers_and_abbreviations():
    reply = (
        "Effect on your last route: 40 metres longer. I understood: close lift B (e.g. the east one). "
        "Status: waiting for the person's yes. Shall I do that?"
    )
    assert spoken_version(reply) == "I understood: close lift B (e.g. the east one). Shall I do that?"
    text = "It is approx. 20 m2, i.e. small, etc. and quiet. Next sentence here."
    assert spoken_version(text, max_chars=60) == "It is approx. 20 square metres, i.e. small, etc. and quiet."


def test_room_refs_are_spelled_and_measurements_are_not():
    assert spoken_version("Lab 0.12 is 63.4 m away") == "Lab zero point one two is sixty three point four metres away"
    assert spoken_version("Lab 0.12 is 63.4 m away", lang="de") == (
        "Lab null Punkt eins zwei is dreiundsechzig Komma vier Meter away"
    )
    assert spoken_version("Office 2.30 and Office 2.31.") == (
        "Office two point three zero and Office two point three one."
    )
    assert spoken_version("Rooms 1.02, 1.03 and 1.04 are free.") == (
        "Rooms one point zero two, one point zero three and one point zero four are free."
    )
    assert spoken_version("Raum 0.12 und 0.13", lang="de") == "Raum null Punkt eins zwei und null Punkt eins drei"
    assert spoken_version("The corridor is 12.5 metres long on floor 2.") == (
        "The corridor is twelve point five metres long on floor two."
    )
    assert spoken_version("Meeting room 0.12 has 24.5 m2.") == (
        "Meeting room zero point one two has twenty four point five square metres."
    )


# ---------- pacing: pauses, numbers, lists ----------

BREAK = re.compile(r'<break time="([0-9.]+)s" />')
ROUTE = "Route to Kitchen 0.28, about 36 m.\n1. Leave the office.\n2. Turn left.\n3. Go on."


def test_pauses_after_headline_and_between_steps():
    spoken = tagged_version(ROUTE)
    assert spoken == (
        "Route to Kitchen zero point two eight, about 36 metres. "
        '<break time="0.8s" /> Step one, leave the office. <break time="0.8s" /> Step two, turn left. <break time="0.8s" /> Step three, go on.'
    )
    assert [float(x) for x in BREAK.findall(spoken)] == [speech.PAUSE_HEADLINE, speech.PAUSE_ITEM, speech.PAUSE_ITEM]


def test_longer_pause_before_closing_question():
    spoken = tagged_version("I understood: close lift B. Nothing changed yet. Should I do that?")
    assert spoken == 'I understood: close lift B. <break time="1.2s" /> Should I do that?'
    assert speech.PAUSE_QUESTION > speech.PAUSE_ITEM


def test_no_pause_inside_a_short_sentence_or_at_the_edges():
    assert tagged_version("The lift is closed.") == "The lift is closed."
    for reply in (ROUTE, "Go left, then right, then straight on. Done?", "A. B. C. D?"):
        spoken = tagged_version(reply)
        assert not spoken.startswith("<") and not spoken.endswith(">")
        assert "<break" not in spoken.split("<break")[0]
        assert not re.search(r"/>\s*<break", spoken)


def test_forged_tags_in_the_reply_are_stripped():
    reply = 'Go left <break time="9s" /> now. <speak>Hi</speak> <phoneme alias="x">y</phoneme> done'
    spoken = tagged_version(reply)
    assert "9s" not in spoken and "<speak" not in spoken and "phoneme" not in spoken
    assert all(float(x) in (0.8, 1.2) for x in BREAK.findall(spoken))
    assert "<" not in BREAK.sub("", spoken) and ">" not in BREAK.sub("", spoken)
    assert tagged_version('<break time="2s" />') == ""


def test_tags_do_not_count_towards_max_chars():
    reply = "Route to the lab.\n" + "\n".join(f"{i}. Walk {i}." for i in range(1, 4))
    full = "Route to the lab. Step one, walk 1. Step two, walk 2. Step three, walk 3."
    two = "Route to the lab. Step one, walk 1. Step two, walk 2."
    spoken = tagged_version(reply, max_chars=len(full))
    assert BREAK.sub(" ", spoken).count("walk") == 3 and len(spoken) > len(full) + 10
    assert "walk 3" not in tagged_version(reply, max_chars=len(two))
    assert "walk 2" in tagged_version(reply, max_chars=len(two))


def test_more_steps_remark_follows_the_last_shown_step():
    steps = "\n".join(f"{i}. Step {i}." for i in range(1, 6))
    spoken = tagged_version(f"Route found.\n{steps}")
    assert spoken.endswith("Step three, step 3. and 2 more steps, see the screen.")
    assert "Step 4" not in spoken


def test_route_steps_are_steps_and_lists_are_ordinals():
    steps = "Route to the lab.\n1. Go left.\n2. Take the lift."
    assert spoken_version(steps) == "Route to the lab. Step one, go left. Step two, take the lift."
    assert spoken_version("Route zum Labor.\n1. Links.\n2. Zum Aufzug.", lang="de") == (
        "Route zum Labor. Schritt eins, links. Schritt zwei, zum Aufzug."
    )
    # "Step N:" lines are steps too, and the written number is replaced by our own counting.
    assert spoken_version("Route:\nStep 1: Go left.\nStep 2: Go on.") == "Route: Step one, go left. Step two, go on."
    assert spoken_version("Weg:\nSchritt 1: Links.\nSchritt 2: Weiter.", lang="de") == (
        "Weg: Schritt eins, links. Schritt zwei, weiter."
    )
    assert spoken_version("Route:\n1. Go on.") == "Route: Go on."  # one step needs no numbering
    welding = "Welding station H-A1 in zone H-A1 Welding station H-A4 in zone H-A4"
    assert spoken_version(welding).startswith("First, welding") and "Step" not in spoken_version(welding)
    assert spoken_version("Two:\n- Press 1\n- Press 2", lang="de").count("Erstens") == 1
    assert "Schritt" not in spoken_version("Two:\n- Press 1\n- Press 2", lang="de")


def test_room_numbers_and_codes_english():
    assert spoken_version("Office corridor 0.16 is next to Kitchen 0.28.") == (
        "Office corridor zero point one six is next to Kitchen zero point two eight."
    )
    assert spoken_version("Room 1.30 is free.") == "Room one point three zero is free."
    assert spoken_version("Zone H-A1 is on F1.") == "Zone H A one is on floor one."
    assert spoken_version("Ref N3806 on floor 2.") == "Ref N three eight zero six on floor two."
    assert spoken_version("It is 36.48 metres, about 36 m.") == (
        "It is thirty six point four eight metres, about 36 metres."
    )
    assert spoken_version("That is 1.5 m wide.") == "That is one point five metres wide."


def test_room_numbers_and_codes_german():
    assert spoken_version("Flur 0.16 neben Küche 0.28.", lang="de") == (
        "Flur null Punkt eins sechs neben Küche null Punkt zwei acht."
    )
    assert spoken_version("Zone H-A1 auf Etage F-1, 36.48 m.", lang="de") == (
        "Zone H A eins auf Etage minus eins, sechsunddreißig Komma vier acht Meter."
    )
    assert spoken_version("Das sind 21.5 m und 101.2 m.", lang="de") == (
        "Das sind einundzwanzig Komma fünf Meter und einhunderteins Komma zwei Meter."
    )


def test_run_on_list_becomes_separate_items():
    reply = "Welding station H-A1 in Production zone H-A1 Welding station H-A4 in Production zone H-A4"
    assert tagged_version(reply) == (
        "First, welding station H A one in Production zone H A one. "
        '<break time="0.8s" /> Second, welding station H A four in Production zone H A four.'
    )
    german = tagged_version("Schweißstation H-A1 in Zone H-A1 Schweißstation H-A4 in Zone H-A4", lang="de")
    assert german.startswith("Erstens, schweißstation H A eins in Zone H A eins.") and "Zweitens," in german


def test_lead_in_and_bullet_lists():
    spoken = tagged_version("Found two: Welding station H-A1 in Production zone H-A1 Welding station H-A4 in zone H-A4")
    assert spoken.startswith('Found two: <break time="0.8s" /> First, welding station H A one')
    bullets = tagged_version("Two matches:\n- Press 1 in hall A\n- Press 2 in hall B")
    assert bullets == (
        'Two matches: <break time="0.8s" /> First, press 1 in hall A. <break time="0.8s" /> Second, press 2 in hall B.'
    )
    assert tagged_version("Note:\n- Only one bullet here") == "Note: Only one bullet here"


def test_second_pass_keeps_text_and_never_doubles_tags():
    for reply in (
        ROUTE,
        "I understood: close lift B. Should I do that?",
        "Welding station H-A1 in zone H-A1 Welding station H-A4 in zone H-A4",
    ):
        once = tagged_version(reply)
        twice = tagged_version(once)
        assert BREAK.sub(" ", twice).split() == BREAK.sub(" ", once).split()
        assert not re.search(r"/>\s*<break", twice)
        assert not twice.startswith("<") and not twice.endswith(">")
    assert tagged_version(ROUTE) == tagged_version(ROUTE)


def test_cap_at_sentence_boundary():
    reply = " ".join(f"Sentence number {i} is here." for i in range(40))
    spoken = spoken_version(reply, max_chars=80)
    assert len(spoken) <= 100 and spoken.endswith(".")
    assert spoken.count("Sentence") == spoken.count("here.")


def test_cap_with_one_endless_sentence():
    spoken = spoken_version("word " * 200, max_chars=50)
    assert len(spoken) <= 52


def test_deterministic_and_empty():
    reply = "**Hallo** Welt. 1. Eins\n2. Zwei"
    assert spoken_version(reply) == spoken_version(reply)
    assert spoken_version("") == ""
    assert spoken_version("Answer: 5") == ""


# ---------- synthesize ----------


def fake_http(status=200, body=b"MP3DATA", seen=None):
    def http(url, headers, data, timeout):
        if seen is not None:
            seen.update(url=url, headers=headers, data=json.loads(data), timeout=timeout)
        return status, body

    return http


def test_synthesize_success(env):
    seen: dict = {}
    assert synthesize("Hallo", "voice1234567890", http=fake_http(seen=seen)) == b"MP3DATA"
    assert seen["url"].endswith("/v1/text-to-speech/voice1234567890?output_format=mp3_44100_128")
    assert seen["headers"]["xi-api-key"] == SECRET
    assert seen["data"] == {
        "text": "Hallo",
        "model_id": "eleven_flash_v2_5",
        "voice_settings": {"speed": 0.85, "stability": 0.5, "similarity_boost": 0.75},
    }
    assert seen["timeout"] == 5


@pytest.mark.parametrize("status", [401, 402, 429, 500, 503, 422])
def test_synthesize_http_errors_hide_key(env, status):
    with pytest.raises(SpeechError) as error:
        synthesize("Hallo", "voice1234567890", http=fake_http(status=status))
    assert SECRET not in str(error.value) and str(status) in str(error.value)


def test_synthesize_timeouts_hide_key(env):
    def timeout(url, headers, data, timeout):
        raise TimeoutError(f"timed out {headers['xi-api-key']}")

    def url_timeout(url, headers, data, timeout):
        raise urllib.error.URLError(TimeoutError("x"))

    for http in (timeout, url_timeout):
        with pytest.raises(SpeechError) as error:
            synthesize("Hallo", "voice1234567890", http=http)
        assert "in time" in str(error.value) and SECRET not in str(error.value)


def test_synthesize_catches_every_exception_without_leaking(env):
    from http.client import BadStatusLine, InvalidURL

    for exc in (ValueError(SECRET), InvalidURL(SECRET), BadStatusLine(SECRET), RuntimeError(SECRET)):

        def boom(url, headers, data, timeout, exc=exc):
            raise exc

        with pytest.raises(SpeechError) as error:
            synthesize("Hallo", "voice1234567890", http=boom)
        assert SECRET not in str(error.value)


def test_synthesize_missing_key_or_voice(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(SpeechError):
        synthesize("Hallo", "voice1234567890", http=fake_http())
    monkeypatch.setenv("ELEVENLABS_API_KEY", SECRET)
    with pytest.raises(SpeechError):
        synthesize("Hallo", "", http=fake_http())


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 0.85), ("0.9", 0.9), ("0.2", 0.7), ("5", 1.2), ("abc", 0.85), ("", 0.85), ("nan", 0.85), ("inf", 0.85)],
)
def test_speed_from_env_is_clamped(env, monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("ELEVENLABS_SPEED", raising=False)
    else:
        monkeypatch.setenv("ELEVENLABS_SPEED", value)
    seen: dict = {}
    synthesize("Hallo", "voice1234567890", http=fake_http(seen=seen))
    assert seen["data"]["voice_settings"]["speed"] == expected
    assert 0 <= seen["data"]["voice_settings"]["stability"] <= 1


def test_pause_tags_reach_the_request_body(env):
    seen: dict = {}
    text = tagged_version(ROUTE)
    synthesize(text, "voice1234567890", http=fake_http(seen=seen))
    assert seen["data"]["text"] == text and "<break" in seen["data"]["text"]


# ---------- endpoint ----------


@pytest.fixture
def server():
    app = App(Path("data"))
    httpd = __import__("http.server", fromlist=["x"]).ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield app, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post_speak(base, payload):
    request = urllib.request.Request(
        f"{base}/api/speak", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.headers["Content-Type"], response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers["Content-Type"], error.read()


def test_speak_returns_audio_with_shortened_text(env, server):
    app, base = server
    said: list[str] = []

    def fake(text, voice_id):
        said.append(text)
        return b"MP3DATA"

    app.synthesize = fake
    status, content_type, body = post_speak(base, {"text": "**Hi** there.\nAnswer: 1"})
    assert (status, content_type, body) == (200, "audio/mpeg", b"MP3DATA")
    assert said == ["Hi there."]


def raw_post(base, payload, headers=None):
    request = urllib.request.Request(f"{base}/api/speak", data=json.dumps(payload).encode(), headers=headers or {})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


JSON = {"Content-Type": "application/json"}


def test_newline_in_key_never_reaches_the_response(monkeypatch, server):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_line1\nsecretpart2")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice1234567890")
    _, base = server
    status, _, body = post_speak(base, {"text": "Hi"})
    assert status == 502
    assert b"secretpart2" not in body and b"line1" not in body


def test_unexpected_exception_gives_fixed_message(env, server):
    app, base = server

    def boom(text, voice_id):
        raise RuntimeError(SECRET)

    app.synthesize = boom
    status, _, body = post_speak(base, {"text": "Hi"})
    assert status == 500 and SECRET.encode() not in body


def test_voice_id_with_control_characters_is_rejected(monkeypatch, server):
    monkeypatch.setenv("ELEVENLABS_API_KEY", SECRET)
    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
    _, base = server
    for bad in ("abc\r\nX-Evil: 1234", "short", "a" * 41, "../../etc/passwd1"):
        status, _, body = post_speak(base, {"text": "Hi", "voice_id": bad})
        assert status == 400 and SECRET.encode() not in body


def test_env_voice_wins_over_body(env, server):
    app, base = server
    used = []
    app.synthesize = lambda text, voice_id: used.append(voice_id) or b"X"
    post_speak(base, {"text": "Hi", "voice_id": "attackervoice99"})
    assert used == ["voice1234567890"]


def test_foreign_origin_and_host_are_403(env, server):
    app, base = server
    app.synthesize = lambda text, voice_id: b"X"
    port = base.rsplit(":", 1)[1]
    assert raw_post(base, {"text": "Hi"}, {**JSON, "Origin": "http://evil.example"})[0] == 403
    assert raw_post(base, {"text": "Hi"}, {**JSON, "Origin": f"http://127.0.0.1:{int(port) + 1}"})[0] == 403
    assert raw_post(base, {"text": "Hi"}, {**JSON, "Host": "evil.example"})[0] == 403
    assert (
        raw_post(base, {"text": "Hi"}, {**JSON, "Origin": f"http://localhost:{port}", "Host": f"localhost:{port}"})[0]
        == 200
    )


def test_speak_requires_json_content_type(env, server):
    app, base = server
    app.synthesize = lambda text, voice_id: b"X"
    assert raw_post(base, {"text": "Hi"}, {"Content-Type": "text/plain"})[0] == 415
    assert raw_post(base, {"text": "Hi"})[0] == 415


def test_rate_limit(env):
    app = App(Path("data"))
    now = [100.0]
    app.clock = lambda: now[0]
    app.synthesize = lambda text, voice_id: b"X"
    assert app.speak({"text": "Hi"})[0] == 200
    assert app.speak({"text": "Hi"})[0] == 429  # same second
    for _ in range(29):
        now[0] += 1.5
        assert app.speak({"text": "Hi"})[0] == 200
    now[0] += 1.5
    assert app.speak({"text": "Hi"})[0] == 429  # 31st within a minute
    now[0] += 61
    assert app.speak({"text": "Hi"})[0] == 200


def test_speak_lang_defaults_to_english(env, server):
    app, base = server
    said: list[str] = []
    app.synthesize = lambda text, voice_id: said.append(text) or b"X"
    steps = "1. A.\n2. B.\n3. C.\n4. D."
    post_speak(base, {"text": steps})
    app.speak_times.clear()  # skip the 1 per second limit
    post_speak(base, {"text": steps, "lang": "de"})
    assert said[0].endswith("and one more step, see the screen.")
    assert said[1].endswith("und ein weiterer Schritt, siehe Bildschirm.")


def test_speak_without_key_is_503(monkeypatch, server):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
    _, base = server
    status, content_type, body = post_speak(base, {"text": "Hi"})
    assert status == 503 and content_type.startswith("application/json")
    assert "error" in json.loads(body)


def test_speak_error_is_502_with_fallback(env, server):
    app, base = server

    def failing(text, voice_id):
        raise SpeechError("ElevenLabs quota or rate limit reached (429).")

    app.synthesize = failing
    status, _, body = post_speak(base, {"text": "Hi"})
    assert status == 502 and json.loads(body)["fallback"]


def test_status_reports_speech_available(monkeypatch):
    app = App(Path("data"))
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert app.get("/api/status", {})[1]["speech_available"] is False
    monkeypatch.setenv("ELEVENLABS_API_KEY", SECRET)
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "v")
    payload = app.get("/api/status", {})[1]
    assert payload["speech_available"] is True and SECRET not in json.dumps(payload)
