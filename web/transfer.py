"""HTTP transfer helpers for web/server.py: gzip for text-like bodies and ETag revalidation. Pure functions, no I/O."""

import gzip
import hashlib

MIN_GZIP_BYTES = 1024
GZIP_LEVEL = 6
TEXT_TYPES = ("application/json", "application/javascript", "image/svg+xml", "application/xml")


def compressible(content_type: str) -> bool:
    """JSON, JS, CSS, HTML, SVG and other text. Never images, audio or other binary files."""
    kind = content_type.split(";")[0].strip().lower()
    return kind.startswith("text/") or kind in TEXT_TYPES


def accepts_gzip(header: str | None) -> bool:
    """True if Accept-Encoding lists gzip (or *) with a quality above 0."""
    for part in (header or "").split(","):
        name, _, params = part.strip().partition(";")
        if name.strip().lower() not in ("gzip", "x-gzip", "*"):
            continue
        quality = 1.0
        for param in params.split(";"):
            key, _, value = param.strip().partition("=")
            if key.strip().lower() == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        if quality > 0:
            return True
    return False


def maybe_gzip(body: bytes, content_type: str, accept_encoding: str | None) -> tuple[bytes, bool]:
    """(body to send, whether it is gzipped). Only text-like bodies over about 1 KB, only if the client asked."""
    if len(body) < MIN_GZIP_BYTES or not compressible(content_type) or not accepts_gzip(accept_encoding):
        return body, False
    packed = gzip.compress(body, compresslevel=GZIP_LEVEL, mtime=0)
    return (packed, True) if len(packed) < len(body) else (body, False)


def etag_for(body: bytes, gzipped: bool = False) -> str:
    """A strong ETag from the content; the gzip variant gets its own tag because its bytes differ."""
    digest = hashlib.sha256(body).hexdigest()[:20]
    return f'"{digest}-gzip"' if gzipped else f'"{digest}"'


def etag_matches(header: str | None, etag: str) -> bool:
    """If-None-Match: any listed tag equals ours (weak prefix ignored), or '*'."""
    if not header:
        return False
    wanted = [item.strip().removeprefix("W/") for item in header.split(",")]
    return "*" in wanted or etag in wanted
