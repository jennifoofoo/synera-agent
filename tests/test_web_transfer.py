"""gzip, ETag and cache headers of the page server, over a real local socket (no API calls)."""

import gzip
import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from web import server as web_server
from web import transfer
from web.server import App, make_handler

DATA = Path("data")
KEY = "dev/proc-campus-dev-000"
BIG_TEXT = ("the quick brown fox jumps over the lazy dog\n" * 200).encode()  # ~8.6 KB, compresses well
NOISE = bytes((index * 7919 + 13) % 251 for index in range(4000))


@pytest.fixture
def static_dir(tmp_path, monkeypatch) -> Path:
    folder = tmp_path / "static"
    folder.mkdir()
    (folder / "index.html").write_bytes(b"<!doctype html><title>x</title>" + BIG_TEXT)
    (folder / "app.js").write_bytes(BIG_TEXT)
    (folder / "style.css").write_bytes(BIG_TEXT)
    (folder / "tiny.js").write_bytes(b"var a = 1;\n")
    (folder / "icon.svg").write_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'>" + BIG_TEXT + b"</svg>")
    (folder / "notes.txt").write_bytes(BIG_TEXT)
    (folder / "data.json").write_bytes(json.dumps({"rows": ["abc"] * 1000}).encode())
    for name in ("picture.png", "voice.mp3", "beep.wav"):
        (folder / name).write_bytes(NOISE)
    monkeypatch.setattr(web_server, "STATIC", folder)
    return folder


@pytest.fixture
def base(static_dir):
    app = App(DATA)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    except PermissionError:
        pytest.skip("local port binding is not allowed here")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def fetch(port: int, path: str, headers: dict | None = None, method: str = "GET", body: bytes | None = None):
    connection = http.client.HTTPConnection("127.0.0.1", port)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, {key.lower(): value for key, value in response.getheaders()}, data


GZIP = {"Accept-Encoding": "gzip"}


# ---------- helpers ----------


def test_accept_encoding_parsing():
    assert transfer.accepts_gzip("gzip, deflate, br")
    assert transfer.accepts_gzip("deflate, GZIP;q=0.5")
    assert transfer.accepts_gzip("*")
    assert not transfer.accepts_gzip(None) and not transfer.accepts_gzip("") and not transfer.accepts_gzip("br")
    assert not transfer.accepts_gzip("gzip;q=0") and not transfer.accepts_gzip("gzip;q=banana")


def test_only_text_like_types_are_compressible():
    for kind in ("text/html", "text/css", "text/javascript", "application/json; charset=utf-8", "image/svg+xml"):
        assert transfer.compressible(kind), kind
    for kind in ("image/png", "audio/mpeg", "audio/wav", "audio/x-wav", "application/octet-stream", "image/jpeg"):
        assert not transfer.compressible(kind), kind


def test_etag_matching():
    tag = transfer.etag_for(b"abc")
    assert transfer.etag_matches(tag, tag) and transfer.etag_matches(f'"zzz", {tag}', tag)
    assert transfer.etag_matches(f"W/{tag}", tag) and transfer.etag_matches("*", tag)
    assert not transfer.etag_matches(None, tag) and not transfer.etag_matches('"other"', tag)
    assert transfer.etag_for(b"abc", gzipped=True) != tag


# ---------- static files ----------


@pytest.mark.parametrize("path", ["/", "/app.js", "/style.css", "/icon.svg", "/notes.txt", "/data.json"])
def test_gzip_body_decompresses_to_the_original(base, static_dir, path):
    _, _, plain = fetch(base, path)
    status, headers, packed = fetch(base, path, GZIP)
    assert status == 200 and headers["content-encoding"] == "gzip"
    assert gzip.decompress(packed) == plain
    assert int(headers["content-length"]) == len(packed) < len(plain)
    assert "Accept-Encoding" in headers["vary"]


def test_no_accept_encoding_means_no_gzip(base):
    status, headers, body = fetch(base, "/app.js")
    assert status == 200 and "content-encoding" not in headers
    assert body == BIG_TEXT and int(headers["content-length"]) == len(BIG_TEXT)
    assert "Accept-Encoding" in headers["vary"]  # caches must still key on it
    assert "content-encoding" not in fetch(base, "/app.js", {"Accept-Encoding": "br, deflate"})[1]
    assert "content-encoding" not in fetch(base, "/app.js", {"Accept-Encoding": "gzip;q=0"})[1]


def test_small_bodies_are_not_compressed(base):
    status, headers, body = fetch(base, "/tiny.js", GZIP)
    assert status == 200 and body == b"var a = 1;\n" and "content-encoding" not in headers
    assert int(headers["content-length"]) == len(body)


@pytest.mark.parametrize("path", ["/picture.png", "/voice.mp3", "/beep.wav"])
def test_binary_files_are_not_compressed(base, path):
    status, headers, body = fetch(base, path, GZIP)
    assert status == 200 and body == NOISE and "content-encoding" not in headers and "vary" not in headers
    assert int(headers["content-length"]) == len(NOISE)


def test_static_files_use_no_cache_with_an_etag_and_304(base, static_dir):
    status, headers, _ = fetch(base, "/app.js", GZIP)
    assert status == 200 and headers["cache-control"] == "no-cache" and headers["etag"]
    status, again, body = fetch(base, "/app.js", {**GZIP, "If-None-Match": headers["etag"]})
    assert status == 304 and body == b"" and again["etag"] == headers["etag"]
    assert again["cache-control"] == "no-cache" and "Accept-Encoding" in again["vary"]
    assert "content-length" not in again or again["content-length"] == "0"
    assert fetch(base, "/app.js", {**GZIP, "If-None-Match": '"stale"'})[0] == 200
    _, plain_headers, _ = fetch(base, "/app.js")
    assert plain_headers["etag"] != headers["etag"]  # the gzip variant has its own tag
    assert fetch(base, "/app.js", {"If-None-Match": plain_headers["etag"]})[0] == 304
    (static_dir / "app.js").write_bytes(BIG_TEXT + b"// changed\n")
    changed = fetch(base, "/app.js", {**GZIP, "If-None-Match": headers["etag"]})
    assert changed[0] == 200 and gzip.decompress(changed[2]).endswith(b"// changed\n")


def test_head_matches_get_without_a_body(base):
    status, headers, body = fetch(base, "/app.js", GZIP, method="HEAD")
    _, get_headers, packed = fetch(base, "/app.js", GZIP)
    assert status == 200 and body == b""
    assert headers["content-length"] == get_headers["content-length"] == str(len(packed))
    assert headers["etag"] == get_headers["etag"] and headers["content-encoding"] == "gzip"


def test_missing_files_and_directory_traversal_stay_refused(base, static_dir):
    (static_dir.parent / "secret.txt").write_text("secret", encoding="utf-8")
    for path in ("/nope.js", "/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt", "/vendor/../../secret.txt"):
        status, _, body = fetch(base, path, GZIP)
        assert status == 404 and b"secret" not in body, path
    assert fetch(base, "/", GZIP)[0] == 200  # index.html still answers for the folder


# ---------- API ----------


def test_building_json_is_gzipped_and_revalidated(base):
    path = f"/api/building?key={KEY}"
    _, _, plain = fetch(base, path)
    status, headers, packed = fetch(base, path, GZIP)
    assert status == 200 and headers["content-encoding"] == "gzip" and "Accept-Encoding" in headers["vary"]
    assert gzip.decompress(packed) == plain and len(packed) < len(plain) // 3
    assert headers["cache-control"] == "no-cache" and headers["etag"]
    again = fetch(base, path, {**GZIP, "If-None-Match": headers["etag"]})
    assert again[0] == 304 and again[2] == b""
    view = json.loads(plain)
    lift = next(item["id"] for item in view["connectors"])
    close = json.dumps({"building": KEY, "element": lift, "closed": True}).encode()
    assert fetch(base, "/api/close", method="POST", headers={"Content-Type": "application/json"}, body=close)[0] == 200
    changed = fetch(base, path, {**GZIP, "If-None-Match": headers["etag"]})
    assert changed[0] == 200 and json.loads(gzip.decompress(changed[2]))["state"]["closed"] == [lift]


def test_other_api_answers_are_never_cached_and_small_ones_stay_plain(base, monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"):
        monkeypatch.delenv(name, raising=False)  # nothing here may reach a paid API
    status, headers, body = fetch(base, "/api/status", GZIP)
    assert status == 200 and headers["cache-control"] == "no-store" and "etag" not in headers
    assert "content-encoding" not in headers and json.loads(body)
    status, headers, _ = fetch(base, "/api/buildings", GZIP)  # large list: compressed, still never cached
    assert status == 200 and headers["cache-control"] == "no-store" and "etag" not in headers
    post = fetch(
        base,
        "/api/chat",
        method="POST",
        headers={"Content-Type": "application/json", **GZIP},
        body=json.dumps({"building": KEY, "message": "hi"}).encode(),
    )
    assert post[0] == 200 and post[1]["cache-control"] == "no-store" and "etag" not in post[1]
    speak = fetch(
        base, "/api/speak", method="POST", headers={"Content-Type": "application/json"}, body=b'{"text": "hi"}'
    )
    assert speak[1]["cache-control"] == "no-store" and "etag" not in speak[1]
    errors = fetch(base, "/api/nothing", GZIP)
    assert errors[0] == 404 and errors[1]["cache-control"] == "no-store" and "etag" not in errors[1]


def test_error_of_the_building_endpoint_is_not_given_an_etag(base):
    status, headers, _ = fetch(base, "/api/building?key=dev/does-not-exist", GZIP)
    assert status >= 400 and "etag" not in headers and headers["cache-control"] == "no-store"
