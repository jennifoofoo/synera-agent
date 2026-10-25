"""POST /api/transcribe (iPhone wake word): ElevenLabs speech-to-text with the HTTP call mocked."""

import json
import socket
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from web import speech
from web.server import App, make_handler
from web.speech import SpeechError, transcribe

SECRET = "sk_test_secret_value_123"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", SECRET)


def test_transcribe_sends_multipart_and_returns_text(env):
    seen: dict = {}

    def http(url, headers, data, timeout):
        seen.update(url=url, headers=headers, data=data)
        return 200, json.dumps({"text": " Hey Wanda, next. ", "language_code": "eng"}).encode()

    assert transcribe(b"AUDIOBYTES", "audio/mp4", http=http) == "Hey Wanda, next."
    assert seen["url"] == "https://api.elevenlabs.io/v1/speech-to-text"
    assert seen["headers"]["xi-api-key"] == SECRET
    assert seen["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    body = seen["data"]
    assert b'name="model_id"\r\n\r\nscribe_v1\r\n' in body
    assert b'name="file"; filename="utterance.m4a"\r\nContent-Type: audio/mp4\r\n\r\nAUDIOBYTES\r\n' in body


@pytest.mark.parametrize("status", [401, 429, 500, 422])
def test_transcribe_errors_hide_key(env, status):
    with pytest.raises(SpeechError) as error:
        transcribe(b"A", "audio/mp4", http=lambda *a: (status, b""))
    assert SECRET not in str(error.value) and str(status) in str(error.value)


def test_transcribe_exception_hides_key(env):
    def boom(*args):
        raise ValueError(SECRET)

    with pytest.raises(SpeechError) as error:
        transcribe(b"A", "audio/mp4", http=boom)
    assert SECRET not in str(error.value)


def test_transcribe_without_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(SpeechError):
        transcribe(b"A", "audio/mp4", http=lambda *a: (200, b"{}"))


@pytest.fixture
def server():
    app = App(Path("data"))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield app, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post(base, data: bytes, content_type="audio/mp4", headers=None):
    request = urllib.request.Request(
        f"{base}/api/transcribe", data=data, headers={"Content-Type": content_type, **(headers or {})}, method="POST"
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def test_endpoint_returns_text(env, server):
    app, base = server
    got: list = []

    def fake(audio, content_type):
        got.append((audio, content_type))
        return "hey wanda how far"

    app.transcribe = fake
    assert post(base, b"M4A", "audio/mp4; codecs=mp4a.40.2") == (200, {"text": "hey wanda how far"})
    assert got == [(b"M4A", "audio/mp4")]


def test_endpoint_503_without_key(monkeypatch, server):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    _, base = server
    status, body = post(base, b"M4A")
    assert status == 503 and "ELEVENLABS_API_KEY" in body["error"]


def test_endpoint_rejects_wrong_type_origin_and_size(env, server):
    app, base = server
    app.transcribe = lambda audio, content_type: "x"
    assert post(base, b"{}", "application/json")[0] == 415
    assert post(base, b"M4A", headers={"Origin": "http://evil.example"})[0] == 403
    # Too large: answered from the headers alone, the body is never read (so none is sent here).
    host, port = base.removeprefix("http://").split(":")
    with socket.create_connection((host, int(port))) as sock:
        sock.sendall(
            f"POST /api/transcribe HTTP/1.1\r\nHost: {host}:{port}\r\nContent-Type: audio/mp4\r\n"
            f"Content-Length: {speech.STT_MAX_BYTES + 1}\r\n\r\n".encode()
        )
        assert sock.recv(64).startswith(b"HTTP/1.0 413")


def test_endpoint_rate_limit_and_error_hides_key(env, server):
    app, base = server
    now = [100.0]
    app.clock = lambda: now[0]

    def failing(audio, content_type):
        raise SpeechError("ElevenLabs returned an error (422).")

    app.transcribe = failing
    status, body = post(base, b"M4A")
    assert status == 502 and SECRET not in json.dumps(body)
    assert post(base, b"M4A")[0] == 429  # same instant: too soon
    now[0] += 1

    def boom(audio, content_type):
        raise RuntimeError(SECRET)

    app.transcribe = boom
    status, body = post(base, b"M4A")
    assert status == 500 and SECRET not in json.dumps(body)
