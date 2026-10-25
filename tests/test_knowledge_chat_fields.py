"""The chat reply carries what facts_here found: facts with photo URLs and the photo to open."""

from types import SimpleNamespace

from web.knowledge_api import chat_fields


def test_nothing_found_gives_empty_fields():
    assert chat_fields(SimpleNamespace(), "b1") == {"facts": [], "open_photo": None}


def test_photo_paths_become_urls_and_open_photo_is_named():
    bm = SimpleNamespace(
        found_facts=[
            {"id": "f1", "text": "valve drips", "photo": "photos/f1.jpg"},
            {"id": "f2", "text": "lift out", "photo": None},
        ],
        open_photo={"fact_id": "f1", "photo": "photos/f1.jpg"},
    )
    out = chat_fields(bm, "train/x y")
    assert out["facts"][0]["photo"] == "/api/facts/photo?key=train%2Fx%20y&id=f1"
    assert out["facts"][1]["photo"] is None
    assert out["open_photo"] == {"fact_id": "f1", "photo_url": "/api/facts/photo?key=train%2Fx%20y&id=f1"}
    assert bm.found_facts[0]["photo"] == "photos/f1.jpg"  # the agent's own copy stays untouched
