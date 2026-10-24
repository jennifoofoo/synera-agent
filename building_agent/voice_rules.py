"""Rules for replies that are spoken aloud, switched on per turn by the page's request-level `voice` flag."""

VOICE_RULES = """

Spoken reply (heard, not read):
- At most one question per reply: one short sentence, at the very end. Ask for one thing only, \
never a second request.
- Offer at most two named options ('Kitchen zero point two eight, or the one upstairs?'). With more \
hits, never list them: name the two nearest and say there are more.
- If a sensible assumption exists, start with it ('I'll start from your last spot, Kitchen zero point two eight.') \
and do not ask.
- No tables, lists, markdown or ids. Short sentences. Write numbers and rooms the way you say them.
- Guided walking: overview with an offer first, then step by step."""


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
