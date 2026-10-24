"""Rules for replies that are spoken aloud, switched on per turn by the page's request-level `voice` flag."""

VOICE_RULES = """

Spoken reply (heard, not read). These rules win over any earlier advice:
- One question at most: one short sentence, the very last, nothing after it. Never route while it is open.
- Never list places or steps: no numbering, bullets, tables, markdown or ids. Name at most two places \
('Kitchen zero point two eight, or the one upstairs?'). More hits: name the two nearest and say there are \
more. No known position: only ask where the person is.
- A sensible assumption: state it first and go on.
- Short sentences, speakable numbers.
- Walking: overview with an offer, then step by step."""


def is_voice(value) -> bool:
    """Only a real boolean true counts: the string 'true', 1 or anything else is false."""
    return value is True


def voice_kwargs(body: dict) -> dict:
    """The request body's flag as ask() keyword arguments; empty when off, so text chat calls stay unchanged."""
    return {"voice": True} if isinstance(body, dict) and is_voice(body.get("voice")) else {}


def voice_applies(voice, user_text: str) -> bool:
    """Benchmark questions (with an 'Answer:' instruction) never get spoken rules."""
    return is_voice(voice) and "Answer:" not in user_text


def with_voice_rules(prompt: str, voice, user_text: str) -> str:
    return prompt + VOICE_RULES if voice_applies(voice, user_text) else prompt


def without_voice_rules(prompt: str) -> str:
    return prompt.removesuffix(VOICE_RULES)
