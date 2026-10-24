"""Auto-pace for guided walking: leg time estimates, spoken durations and the tick state machine.

Pure and dependency free: no building, no agent, no server imports. Spec: docs/specs/auto-pace.md.
The estimate is never a position fix, it only decides when the agent asks "ready for the next step?".

Integration (to apply after feat/position is merged; names of the guide state are placeholders):

    # tools.py or guide_tools.py, once per session next to the guide/position state
    from building_agent.pace import PaceState, Action, leg_seconds, spoken_duration, parse_pace_intent, validate_tick
    state.pace = PaceState()                       # mode "off" until the page switch sets it

    # when the guide speaks step i (route steps carry length_m and kind "walk" | "stairs" | "lift"):
    secs = leg_seconds(step.length_m, step.kind)
    state.pace.arm(i, secs)                        # then say spoken_duration(secs, lang) in the step text
    # the page starts its timer at secs + 5 after the speech ends and sends {guide_tick: true} on expiry

    # agent.py / web/chat.py, once per incoming chat call, BEFORE the model sees the message:
    ctx = request_context                          # the dict next to "picked"/"here", never parsed from text
    pace = state.pace
    if validate_tick(ctx, pace, lambda: state.guide_active()):
        action = pace.tick(state.guide_step_index())
        # Action.ASK_NEXT: model asks one sentence "Ready for step N?", then pace.arm(i + 1, secs) so a
        #   second unanswered ask is counted; Action.SAY_NEXT: give the next step plus
        #   "Say wait if you need a moment." and arm it as usual;
        # Action.PAUSED_NOTICE: say once "I'll wait here. Say go when you're ready.";
        # Action.NONE: drop the tick silently and do not call the model.
    else:
        pace.on_user_message()                     # every real user message resets the unanswered counter
        intent = parse_pace_intent(text)
        if intent == "wait":
            pace.pause()
        elif intent == "go":
            pace.resume()
    # at the last step: pace.arrived(); the page switch sets pace.mode = "off" | "ask" | "say"

The tick never edits the building and must never reach the model as message text.
"""

import math
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

WALK_M_PER_S = 1.2
STAIRS_M_PER_S = 0.8
LIFT_WAIT_S = 15.0
ROUND_S = 5
MAX_LEG_S = 3600
TIMER_GRACE_S = 5
MAX_UNANSWERED = 2
MODES = ("off", "ask", "say")


def leg_seconds(length_m: float, kind: str = "walk") -> int:
    """Expected seconds for one leg, rounded up to 5 s. Bad input (NaN, negative, None) counts as length 0."""
    try:
        length = float(length_m)
    except (TypeError, ValueError):
        length = 0.0
    if math.isnan(length) or length < 0:
        length = 0.0
    if kind == "lift":
        # The vertical part is the connector length at walking pace, as the lift cost in routing is wait plus metres.
        raw = LIFT_WAIT_S + length / WALK_M_PER_S
    elif kind == "stairs":
        raw = length / STAIRS_M_PER_S
    else:
        raw = length / WALK_M_PER_S
    if math.isinf(raw) or raw >= MAX_LEG_S:
        return MAX_LEG_S
    # Round off float noise first, otherwise 6 m / 1.2 becomes 5.000000000000001 and rounds up to 10 s.
    return min(math.ceil(round(raw, 6) / ROUND_S) * ROUND_S, MAX_LEG_S)


_EN_NUM = {5: "five", 10: "ten", 15: "fifteen", 20: "twenty", 25: "twenty-five", 30: "thirty", 35: "thirty-five"}
_EN_NUM[40] = "forty"
_DE_NUM = {5: "fünf", 10: "zehn", 15: "fünfzehn", 20: "zwanzig", 25: "fünfundzwanzig", 30: "dreißig"}
_DE_NUM.update({35: "fünfunddreißig", 40: "vierzig"})
_EN_MIN = ["", "a", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
_DE_MIN = ["", "eine", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn"]


def spoken_duration(seconds: float, lang: str = "en") -> str:
    """Rough spoken duration: 'about twenty seconds', 'about a minute', 'about two minutes' (German with lang 'de')."""
    de = str(lang).lower().startswith("de")
    try:
        secs = float(seconds)
    except (TypeError, ValueError):
        secs = 0.0
    if math.isnan(secs) or secs < 0:
        secs = 0.0
    secs = min(secs, MAX_LEG_S)
    if secs < 45:
        if secs <= 2.5:
            return "etwa ein paar Sekunden" if de else "about a few seconds"
        step = min(max(int(secs / 5 + 0.5) * 5, 5), 40)
        word = (_DE_NUM if de else _EN_NUM)[step]
        return f"etwa {word} Sekunden" if de else f"about {word} seconds"
    minutes = max(int(secs / 60 + 0.5), 1)
    if minutes == 1:
        return "etwa eine Minute" if de else "about a minute"
    word = (_DE_MIN if de else _EN_MIN)[minutes] if minutes <= 10 else str(minutes)
    return f"etwa {word} Minuten" if de else f"about {word} minutes"


class Action(Enum):
    NONE = "none"
    ASK_NEXT = "ask_next"
    SAY_NEXT = "say_next"
    PAUSED_NOTICE = "paused_notice"


@dataclass
class PaceState:
    """Tick state machine. At most one tick counts per step (until the person says something)."""

    mode: str = "off"
    step_index: int | None = None
    expected_seconds: int = 0
    unanswered: int = 0
    paused: bool = False
    done: bool = False
    _armed: bool = False
    _ticked: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            self.mode = "off"

    @property
    def active(self) -> bool:
        return self.mode != "off" and not self.paused and not self.done

    @property
    def timer_seconds(self) -> int:
        """What the page should wait before sending a tick: the estimate plus a grace period."""
        return self.expected_seconds + TIMER_GRACE_S

    def arm(self, step_index: int, expected_seconds: float = 0) -> None:
        """A step was spoken. Starts (or restarts) the timer for it, e.g. after a reroute."""
        if self.done or isinstance(step_index, bool) or not isinstance(step_index, int):
            return
        self.step_index = step_index
        self.expected_seconds = leg_seconds(expected_seconds)
        self._armed = True

    def tick(self, step_index: int) -> Action:
        """The timer expired for this step. Returns what the agent should do, NONE for a dropped tick."""
        if (
            not self.active
            or not self._armed
            or isinstance(step_index, bool)
            or step_index != self.step_index
            or step_index in self._ticked
        ):
            return Action.NONE
        self._armed = False
        self._ticked.add(step_index)
        if self.unanswered >= MAX_UNANSWERED:
            self.paused = True
            return Action.PAUSED_NOTICE
        self.unanswered += 1
        return Action.SAY_NEXT if self.mode == "say" else Action.ASK_NEXT

    def pause(self) -> None:
        """'wait', 'hold on': timer off, no ticks until resume()."""
        self.paused = True
        self._armed = False

    def resume(self) -> None:
        """'go', 'ready': ticks may count again once the next step is armed."""
        self.paused = False
        self.unanswered = 0
        self._ticked.clear()

    def on_user_message(self) -> None:
        """Any utterance of the person: they are there, so reset the counter and the per-step tick memory."""
        self.unanswered = 0
        self._ticked.clear()

    def arrived(self) -> None:
        """Last step spoken: the timer ends and no tick counts any more."""
        self.done = True
        self._armed = False


class GuideActive(Protocol):
    def __call__(self) -> bool: ...


def validate_tick(context: object, state: PaceState | None, guide_active: GuideActive | Callable[[], bool]) -> bool:
    """True only for a real boolean True under 'guide_tick' in the request context, while a guide is active.

    Message text is never looked at, and strings like "true" or the number 1 do not count.
    """
    if not isinstance(context, dict) or context.get("guide_tick") is not True:
        return False
    if state is None or not state.active:
        return False
    try:
        return guide_active() is True
    except Exception:  # noqa: BLE001 - a broken guard must fail closed, whatever it raised
        return False


_WAIT = {
    "wait", "hold on", "moment", "one moment", "a moment", "just a moment", "wait a moment", "wait a sec",
    "hold up", "one sec", "warte", "warte kurz", "warte mal", "moment mal", "einen moment", "kurz warten",
}  # fmt: skip
_GO = {
    "go", "ready", "im ready", "ready to go", "lets go", "go on", "okay go", "ok go", "weiter", "weiter gehts",
    "bereit", "ich bin bereit", "los", "los gehts",
}  # fmt: skip
MAX_INTENT_WORDS = 3


def parse_pace_intent(text: str) -> str | None:
    """Return 'wait', 'go' or None. Only short utterances (at most 3 words) that match a phrase exactly count.

    Longer sentences that merely contain the word, such as "wait, which floor is the lift on", are normal
    questions and return None, so a question never silently pauses the guide.
    """
    if not isinstance(text, str):
        return None
    folded = unicodedata.normalize("NFKC", text).lower().replace("’", "").replace("'", "")
    words = re.sub(r"[^\w\s]|_", " ", folded).split()
    if not words or len(words) > MAX_INTENT_WORDS:
        return None
    phrase = " ".join(words)
    if phrase in _WAIT:
        return "wait"
    if phrase in _GO:
        return "go"
    return None
