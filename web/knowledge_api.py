"""Place knowledge for the page (docs/specs/place-knowledge.md, "Vertrag für die Seite").

  GET  /api/facts?key=&space_id=&asset_id=&element_id=&floor_id=&area=&asset_type=&category=&person=&since=&until=
                 &at=&status=open|resolved|expired|all&history=1      -> {facts: [...], persons: [...]}
  POST /api/facts {building|key, kind: note|issue, anchor, text, valid_to?, author?, related?, photo_base64?}
                 -> {fact, state}   (closures only through the chat card, they change routes)
  GET  /api/facts/photo?key=&id=   image/jpeg
  POST /api/facts/undo {building|key} -> {undone: fact|null, state}   (only facts younger than 2 minutes)
  GET  /api/graph?key=[&format=aas][&at=]   JSON-LD (Brick/REC) or Asset Administration Shell export

The store keeps photos as "photos/<id>.jpg"; here they become /api/facts/photo URLs for the building key."""

import base64
import binascii
from urllib.parse import quote

from building_agent.knowledge import (
    MAX_PHOTO_BYTES,
    Fact,
    KnowledgeError,
    KnowledgeStore,
    aas_export,
    apply_timed_closures,
    closed_until,
    graph_jsonld,
)

MAX_POST_BYTES = 12 * 1024 * 1024  # JSON with an 8 MB photo as base64 (4/3) plus the fields
PAGE_KINDS = ("note", "issue")
FILTERS = ("space_id", "asset_id", "element_id", "floor_id", "area", "asset_type", "category", "person")
TIMES = ("since", "until", "at")


def photo_url(key: str, fact_id: str) -> str:
    return f"/api/facts/photo?key={quote(key, safe='')}&id={fact_id}"


def public(fact: Fact, key: str) -> dict:
    """A fact as the page sees it: photo as URL."""
    data = fact.to_dict()
    data["photo"] = photo_url(key, fact.id) if fact.photo else None
    return data


def chat_fields(bm, key: str) -> dict:
    """What facts_here found this turn, for the page: facts with photo URLs, and the photo to open."""
    facts = []
    for found in getattr(bm, "found_facts", None) or []:
        data = dict(found)
        data["photo"] = photo_url(key, data["id"]) if data.get("photo") and data.get("id") else None
        facts.append(data)
    shown = getattr(bm, "open_photo", None)
    fact_id = shown.get("fact_id") if isinstance(shown, dict) else None
    return {
        "facts": facts,
        "open_photo": {"fact_id": fact_id, "photo_url": photo_url(key, fact_id)} if fact_id else None,
    }


def first(query: dict, name: str) -> str | None:
    value = (query.get(name) or [None])[0]
    return value if value not in (None, "") else None


def tick(store: KnowledgeStore | None, bm) -> None:
    """Timed closures on/off for this moment (no background job)."""
    if store is not None:
        apply_timed_closures(bm, store)


def state_part(store: KnowledgeStore | None, bm, key: str) -> dict:
    """state.facts (open now, all floors) and state.closed_until {element_id: ISO}."""
    if store is None:
        return {"facts": [], "closed_until": {}}
    try:
        facts = [public(fact, key) for fact in store.active(bm)]
        return {"facts": facts, "closed_until": closed_until(store, bm)}
    except KnowledgeError:
        return {"facts": [], "closed_until": {}}


def list_facts(store: KnowledgeStore, bm, key: str, query: dict) -> dict:
    filters = {name: first(query, name) for name in (*FILTERS, *TIMES)}
    status = first(query, "status") or "open"
    history = first(query, "history") in ("1", "true", "yes")
    facts = store.query(bm, status=status, history=history, **{k: v for k, v in filters.items() if v is not None})
    return {"facts": [public(fact, key) for fact in facts], "persons": store.persons(bm)}


def decode_photo(raw) -> bytes:
    """Base64 (optionally a data: URL) -> bytes, at most 8 MB."""
    if not isinstance(raw, str) or not raw:
        raise KnowledgeError("photo_base64 must be a base64 string.")
    if raw.startswith("data:"):
        raw = raw.split(",", 1)[1] if "," in raw else ""
    if len(raw) > MAX_PHOTO_BYTES * 4 // 3 + 8:
        raise KnowledgeError("The photo is larger than 8 MB.", 413)
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as error:
        raise KnowledgeError("photo_base64 is not valid base64.") from error
    if len(data) > MAX_PHOTO_BYTES:
        raise KnowledgeError("The photo is larger than 8 MB.", 413)
    return data


def create(store: KnowledgeStore, bm, key: str, body: dict) -> dict:
    """The page's "Notiz hier" button: submitting counts as confirmation. Notes and issues only."""
    if not isinstance(body, dict):
        raise KnowledgeError("Body must be an object.")
    kind = body.get("kind", "note")
    if kind not in PAGE_KINDS:
        raise KnowledgeError("The page can add notes and issues; closures go through the chat (card and yes).")
    photo = decode_photo(body["photo_base64"]) if body.get("photo_base64") else None
    source = body.get("source") if body.get("source") in ("tap", "text", "voice") else "tap"
    fact = store.add(
        bm,
        kind=kind,
        anchor=body.get("anchor"),
        text=body.get("text"),
        valid_to=body.get("valid_to"),
        author=body.get("author"),
        source=source,
        utterance=body.get("utterance") or "",
        related=body.get("related") or (),
        photo_bytes=photo,
    )
    return {"fact": public(fact, key)}


def undo(store: KnowledgeStore, bm, key: str) -> dict:
    removed = store.undo_last(bm)
    tick(store, bm)
    return {"undone": public(removed, key) if removed else None}


def photo(store: KnowledgeStore, bm, fact_id: str) -> bytes:
    path = store.photo_path(bm, fact_id)
    if path is None:
        raise KnowledgeError("Unknown fact or no photo.", 404)
    try:
        return path.read_bytes()
    except OSError as error:
        raise KnowledgeError("Unknown fact or no photo.", 404) from error


def graph(store: KnowledgeStore, bm, query: dict) -> dict:
    at = first(query, "at")
    if first(query, "format") == "aas":
        return aas_export(bm, store, at)
    return graph_jsonld(bm, store, at)


def reopen(store: KnowledgeStore | None, bm, element: str, author: str | None = None) -> list[str]:
    """Opening an element on the page ends its open closure facts (otherwise the next tick closes it again)."""
    if store is None:
        return []
    ended = []
    for fact in store.query(bm, element_id=element):
        if fact.kind == "closure" and fact.anchor.get("element_id") == element:
            store.resolve(bm, fact.id, text="opened on the page", author=author)
            ended.append(fact.id)
    tick(store, bm)
    return ended
