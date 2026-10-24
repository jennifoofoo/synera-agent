"""Offline tests for web/speech.py and POST /api/speak. No real ElevenLabs call, no key needed."""

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from web.server import App, make_handler
from web.speech import SpeechError, spoken_version, synthesize

SECRET = "sk_test_secret_value_123"
ID = "proc-campus-dev-000-F0-S012"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", SECRET)
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice123")


# ---------- spoken_version ----------


def test_markdown_and_answer_line_are_removed():
    reply = "## Result\n**The lift** is `closed`.\n- Use the stairs.\nAnswer: 42"
    assert spoken_version(reply) == "Result The lift is closed. Use the stairs."


def test_only_three_steps_then_german_tail():
    reply = "Route found:\n1. Go left.\n2. Take the lift.\n3. Turn right.\n4. Walk on.\n5. Arrive."
    spoken = spoken_version(reply)
    assert "Go left." in spoken and "Turn right." in spoken
    assert "Walk on" not in spoken
    assert spoken.endswith("und 2 weitere Schritte, siehe Bildschirm.")


def test_single_extra_step_is_singular():
    spoken = spoken_version("1. A.\n2. B.\n3. C.\n4. D.")
    assert spoken.endswith("und ein weiterer Schritt, siehe Bildschirm.")


def test_three_steps_have_no_tail():
    assert "weitere" not in spoken_version("1. A.\n2. B.\n3. C.")


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
    assert spoken == "I understood: close the east lift on floor 1. Should I do that?"


def test_german_card():
    spoken = spoken_version("Ich habe verstanden: Aufzug 2 sperren. Auswirkung: Umweg. Soll ich das so machen?")
    assert spoken == "Ich habe verstanden: Aufzug 2 sperren. Soll ich das so machen?"


def test_pronunciation_table_and_room_numbers():
    spoken = spoken_version("Room 0.12 has 24 m2 and 30 m² next to the WC, 5 m away.")
    assert "0.12" in spoken
    assert "24 Quadratmeter" in spoken and "30 Quadratmeter" in spoken
    assert "W C" in spoken and "5 Meter" in spoken


def test_cap_at_sentence_boundary():
    reply = " ".join(f"Sentence number {i} is here." for i in range(40))
    spoken = spoken_version(reply, max_chars=100)
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
    assert synthesize("Hallo", "voice123", http=fake_http(seen=seen)) == b"MP3DATA"
    assert seen["url"].endswith("/v1/text-to-speech/voice123?output_format=mp3_44100_128")
    assert seen["headers"]["xi-api-key"] == SECRET
    assert seen["data"] == {"text": "Hallo", "model_id": "eleven_flash_v2_5"}
    assert seen["timeout"] == 5


@pytest.mark.parametrize("status", [401, 402, 429, 500, 503, 422])
def test_synthesize_http_errors_hide_key(env, status):
    with pytest.raises(SpeechError) as error:
        synthesize("Hallo", "voice123", http=fake_http(status=status))
    assert SECRET not in str(error.value) and str(status) in str(error.value)


def test_synthesize_timeouts_hide_key(env):
    def timeout(url, headers, data, timeout):
        raise TimeoutError(f"timed out {headers['xi-api-key']}")

    def url_timeout(url, headers, data, timeout):
        raise urllib.error.URLError(TimeoutError("x"))

    for http in (timeout, url_timeout):
        with pytest.raises(SpeechError) as error:
            synthesize("Hallo", "voice123", http=http)
        assert "5 seconds" in str(error.value) and SECRET not in str(error.value)


def test_synthesize_missing_key_or_voice(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(SpeechError):
        synthesize("Hallo", "voice123", http=fake_http())
    monkeypatch.setenv("ELEVENLABS_API_KEY", SECRET)
    with pytest.raises(SpeechError):
        synthesize("Hallo", "", http=fake_http())


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
