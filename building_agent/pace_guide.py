"""Auto-pace wiring for guided walking: the page's `pace` switch and `guide_tick` context, one turn at a time.

pace.py holds the pure state machine; this module connects it to the guide state (GuideState.pace), the walk
(building_agent/walk.py) and the agent. Spec: docs/specs/auto-pace.md. It lives in its own file so the walk and
tool modules stay untouched.

With pace 'off' (the default) run_turn() is exactly `agent.ask(text)`: same call, same state. With 'ask' or 'say':
- A tick (context.guide_tick is True, empty message) is answered WITHOUT the model: 'Ready for step N?', the next
  step plus 'Say wait if you need a moment.' (German conversations use the model for the step, the suffix is ours),
  the 'I'll wait here' notice, or nothing at all. A tick never changes the building.
- 'wait' / 'go' and a yes after the question are short utterances read by parse_pace_intent, not by the model.
- Benchmark messages (with 'Answer:') ignore pace and ticks."""

import re
from dataclasses import dataclass

from building_agent import walk as walking
from building_agent.guide_tools import building_signature
from building_agent.pace import MODES, Action, PaceState, leg_seconds, parse_pace_intent, spoken_duration, validate_tick

LIFT_FIXED_M = 15.0  # the routing cost of a lift ride includes this many metres; leg_seconds adds the wait itself

PACE_RULES = """

Auto-pace is on: after a guided step the system itself adds how long the leg takes. Never say a duration or time \
estimate for a step yourself (ignore about_seconds), and never ask 'ready for the next step' yourself."""

ASK = {"en": "Ready for step {n}?", "de": "Bereit für Schritt {n}?"}
PAUSED = {"en": "I'll wait here. Say go when you're ready.", "de": "Ich warte hier. Sag los, wenn du bereit bist."}
WAITING = {
    "en": "Okay, take your time. Say go when you're ready.",
    "de": "Okay, lass dir Zeit. Sag los, wenn du bereit bist.",
}
SAY_WAIT = {"en": "Say wait if you need a moment.", "de": "Sag warte, wenn du einen Moment brauchst."}
THERE = {"en": "You're there. That was the last step.", "de": "Du bist da. Das war der letzte Schritt."}
TAKES = {"en": "That's {duration}.", "de": "Das sind {duration}."}
GERMAN = re.compile(  # umlauts and words that do not exist in English; never "bin", "die", "wo", "moment", "nach"
    r"[äöüß]|\b(ja|nein|bitte|danke|ich|nicht|weiter|warte|bereit|nochmal|zurück|zurueck|schritt|jetzt|gerne|"
    r"klar|kurz|mal|los|wo ist|wo geht|wie weit|und|oder|aber)\b",
    re.IGNORECASE,
)
YES_WORDS = {
    "yes",
    "yeah",
    "yep",
    "yup",
    "sure",
    "ja",
    "jep",
    "klar",
    "gerne",
    "gern",
    "ok ja",
    "ja bitte",
    "yes please",
}


@dataclass
class GuidePace(PaceState):
    """PaceState plus what the wiring needs: the walk the timer belongs to and an open 'Ready for step N?'."""

    walk_ref: object = None
    awaiting: bool = False
    lang: str = "en"  # language of the last real message


def normalize_mode(value) -> str:
    """Only the exact strings 'off', 'ask', 'say' count; anything else (None, 'ASK', true, 1) is 'off'."""
    return value if isinstance(value, str) and value in MODES else "off"


def pace_kwargs(body: dict, context) -> dict:
    """Request-level pace switch and tick as chat.ask() keywords; empty when both are off, so old calls stay as is.

    The tick is context.guide_tick, a real boolean true only, never read from the message text. The optional
    context.guide_step (int, the step the timer was started for) lets the server drop a tick that crossed a
    step change."""
    found: dict = {}
    mode = normalize_mode(body.get("pace") if isinstance(body, dict) else None)
    if mode != "off":
        found["pace"] = mode
    if isinstance(context, dict) and context.get("guide_tick") is True:
        found["tick"] = True
        step = context.get("guide_step")
        if isinstance(step, int) and not isinstance(step, bool):
            found["tick_step"] = step
    return found


def without_tick_keys(context):
    """The context minus the pace keys, so they are not mistaken for a click selection."""
    if not isinstance(context, dict):
        return context
    return {key: value for key, value in context.items() if key not in ("guide_tick", "guide_step")} or None


def is_german(text: str) -> bool:
    return bool(GERMAN.search(text or ""))


def language_of(text: str, previous: str = "en") -> str:
    """'de' only for clear German; a very short ambiguous phrase ('wait') keeps the language of the last message."""
    if is_german(text):
        return "de"
    return previous if len(str(text).split()) <= 1 else "en"


def pace_of(guide) -> GuidePace | None:
    return getattr(guide, "pace", None)


def state_of(guide, mode: str) -> GuidePace:
    pace = pace_of(guide)
    if pace is None:
        pace = guide.pace = GuidePace()
    pace.mode = mode
    return pace


def guided(guide) -> bool:
    """A guide is running and the person has not arrived yet."""
    walk = getattr(guide, "walk", None)
    return walk is not None and walk.mode == "guided" and walk.index < len(walk.steps) - 1


def leg_for(bm, walk, index: int) -> int:
    """Expected seconds for the leg of step `index`: route metres between the two stops and the kind of leg."""
    here = walking.metres_left(bm, walk, index)
    after = walking.metres_left(bm, walk, index + 1) if index + 1 < len(walk.steps) else None
    length = here - after if here is not None and after is not None else 0.0
    step = walk.steps[index].lower()
    if "(lift)" in step:
        return leg_seconds(max(length - LIFT_FIXED_M, 0.0), "lift")
    return leg_seconds(max(length, 0.0), "stairs" if "(stair" in step else "walk")


def safe_leg(bm, walk, index: int) -> int:
    try:
        return leg_for(bm, walk, index)
    except Exception:  # noqa: BLE001 - a missing estimate must never break the conversation
        return 0


def view(bm, guide) -> dict:
    """The additive state_view.guide fields: expected_seconds (timer start for the page), pace, pace_paused."""
    pace, walk = pace_of(guide), guide.walk
    expected = safe_leg(bm, walk, walk.index) if walk is not None and walk.mode == "guided" else 0
    return {
        "expected_seconds": expected,
        "pace": pace.mode if pace is not None else "off",
        "pace_paused": bool(pace is not None and pace.paused),
    }


def settle(bm, guide, pace: GuidePace) -> None:
    """After a turn: arrive, or (re)arm the timer for the step that is current now."""
    walk = guide.walk
    if walk is None or walk.mode != "guided":
        return
    if pace.done and walk is not pace.walk_ref:  # a new route: the old arrival does not count any more
        pace.done = False
    if walk.index >= len(walk.steps) - 1:
        pace.arrived()
    elif not pace.paused:
        pace.arm(walk.index, safe_leg(bm, walk, walk.index))
    pace.walk_ref = walk


def ask_model(agent, text: str, voice: bool, pace_on: bool) -> str:
    """The plain agent call, with the pace rules for this turn only when pace is on."""
    kwargs = {"voice": True} if voice else {}
    if not pace_on:
        return agent.ask(text, **kwargs)
    agent.system[0]["text"] += PACE_RULES
    try:
        return agent.ask(text, **kwargs)
    finally:
        agent.system[0]["text"] = agent.system[0]["text"].removesuffix(PACE_RULES)


def duration_sentence(seconds: int, lang: str) -> str:
    return TAKES[lang].format(duration=spoken_duration(seconds, lang))


def tick_turn(agent, pace: GuidePace, step: int | None, lang: str, voice: bool) -> str:
    """One validated-or-not tick. Returns the reply, '' when it is dropped."""
    guide, bm = agent.guide, agent.map
    if not validate_tick({"guide_tick": True}, pace, lambda: guided(guide)):
        return ""
    walk = guide.walk
    if (
        (step is not None and step != walk.index)
        or guide.pending is not None  # the person is answering a card
        or guide.signature != building_signature(bm)  # the building changed: the walk is stale
    ):
        return ""
    action = pace.tick(walk.index)
    if action is Action.NONE:
        return ""
    if action is Action.PAUSED_NOTICE:
        return PAUSED[lang]
    if action is Action.ASK_NEXT:
        pace.awaiting = True
        return ASK[lang].format(n=walk.index + 2)
    # SAY_NEXT: advance with the state machine, speak the step ourselves in English, ask the model in German
    if lang == "de":
        before = walk.index
        reply = ask_model(agent, "weiter", voice, True)
        advanced = guide.walk is walk and walk.index > before
        suffix = [SAY_WAIT[lang]] if advanced and guided(guide) else []
    else:
        walking.apply(bm, guide, "next")
        if walk.index >= len(walk.steps) - 1:
            reply, suffix = THERE[lang], []
        else:
            reply = f"{walk.steps[walk.index]} {duration_sentence(safe_leg(bm, walk, walk.index), lang)}"
            suffix = [SAY_WAIT[lang]]
    settle(bm, guide, pace)
    if lang == "de" and guided(guide):
        reply = f"{reply} {duration_sentence(safe_leg(bm, guide.walk, guide.walk.index), lang)}"
    return " ".join([reply, *suffix])


def user_turn(agent, text: str, pace: GuidePace, voice: bool) -> str:
    """A real message of the person while pace is on."""
    guide, bm = agent.guide, agent.map
    lang = pace.lang = language_of(text, pace.lang)
    was_paused, was_awaiting = pace.paused, pace.awaiting
    pace.on_user_message()
    pace.awaiting = False
    card_open = guide.pending is not None  # the next message may answer the card: pass everything through
    intent = parse_pace_intent(text) if guided(guide) and not card_open else None
    send = text
    if intent == "wait":
        pace.pause()
        guide.begin_turn()
        guide.last_user_text = text
        return WAITING[lang]
    if intent == "go":
        pace.resume()
        if was_paused or was_awaiting:
            send = "next"
    elif was_awaiting and guided(guide) and not card_open and parse_yes(text):
        send = "next"
    before = (guide.walk, guide.walk.index if guide.walk is not None else None, guided(guide))
    reply = ask_model(agent, send, voice, True)
    # A new step was spoken: another walk, another step, or guiding just started (a yes to the overview's offer
    # keeps the same walk at step 0 and only switches it to guided).
    spoke_new_step = guided(guide) and (guide.walk is not before[0] or guide.walk.index != before[1] or not before[2])
    settle(bm, guide, pace)
    if spoke_new_step and not pace.paused:
        reply = f"{reply} {duration_sentence(safe_leg(bm, guide.walk, guide.walk.index), lang)}"
    return reply


def parse_yes(text: str) -> bool:
    words = re.sub(r"[^\w\s]|_", " ", str(text).lower()).split()
    return 0 < len(words) <= 3 and " ".join(words) in YES_WORDS


def run_turn(
    agent, text: str, mode="off", tick: bool = False, tick_step: int | None = None, voice: bool = False
) -> str:
    """Everything the page can send about pace for one chat call; returns the reply text ('' for a dropped tick)."""
    mode = normalize_mode(mode)
    is_tick = tick is True and not str(text).strip()
    if "Answer:" in str(text):  # benchmark: no pace, no tick, nothing touched
        return ask_model(agent, text, voice, False)
    if mode == "off" and not is_tick:
        if pace_of(agent.guide) is not None:
            pace_of(agent.guide).mode = "off"
        return ask_model(agent, text, voice, False)
    pace = state_of(agent.guide, mode)
    if is_tick:
        return tick_turn(agent, pace, tick_step, pace.lang, voice)
    return user_turn(agent, text, pace, voice)
