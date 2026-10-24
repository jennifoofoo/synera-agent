"""Objective scoring of one catalogue item against a live transcript (tests/live/harness.py Transcript).

Hard checks run on tool calls and on numbers or names in the replies, never on wording. A check that cannot be
decided (truth type none and no rule) returns passed=None and is reported as 'unscored'."""

import json
import re

from tests.live.harness import Transcript

ROUTE_TOOLS = {"find_route", "give_directions", "campus_route", "errand", "find_forklift_route"}
MUTATING = {"assume_closed", "set_position"}
NOT_FOUND = re.compile(
    r"(don't|do not|doesn't|does not|no (data|information|info|such)|not (available|in the data|stored|tracked|known|found|exist)"
    r"|can't|cannot|unable|nicht|keine|kein |isn't|aren't|there is no|there's no|couldn't|not something|nothing)",
    re.IGNORECASE,
)
NO_ROUTE = re.compile(
    r"(no (step-free |barrier-free )?(route|way|path)|not reachable|unreachable|can't (get|reach)|cannot (get|reach)|"
    r"no way|isn't possible|not possible|kein(e|en)? (weg|route)|nicht erreichbar|cut off|impossible)",
    re.IGNORECASE,
)
REF_TOKEN = re.compile(r"\b([A-Z][a-z]+(?: [a-z]+)? [-\w.]*\d[\w.-]*)")
SKIP_PREFIX = (
    "Floor",
    "Level",
    "Storey",
    "Basement",
    "Step",
    "Answer",
    "Turn",
    "Stairs",
    "Staircase",
    "Lift",
    "Ground",
)


def numbers_in(text: str) -> list[float]:
    found = []
    for raw in re.findall(r"-?\d+(?:[.,]\d+)?", text.replace("−", "-")):
        try:
            found.append(float(raw.replace(",", ".")))
        except ValueError:
            continue
    return found


def answer_line(reply: str) -> str | None:
    lines = [line for line in reply.splitlines() if re.match(r"^\W*Answer:", line.strip(), re.IGNORECASE)]
    return lines[-1] if lines else None


def ok_calls(transcript: Transcript, *names: str):
    return [(i, c) for i, t in enumerate(transcript.turns) for c in t.calls if c.name in names and not c.is_error]


def all_text(transcript: Transcript) -> str:
    parts = [turn.user for turn in transcript.turns] + [call.result for turn in transcript.turns for call in turn.calls]
    return "\n".join(parts).lower()


def close_enough(value: float, truth: dict) -> bool:
    tolerance = max(truth.get("tol_abs", 0.0), truth.get("tol_rel", 0.0) * abs(truth["value"]))
    candidates = [truth["value"], *truth.get("alts", [])]
    return any(abs(value - candidate) <= max(tolerance, 0.005) for candidate in candidates)


def mentions(reply: str, name: str, ref: str) -> bool:
    low = reply.lower()
    if name and name.lower() in low:
        return True
    return bool(ref) and re.search(rf"(?<![\w.]){re.escape(ref.lower())}(?![\w.])", low) is not None


def check_number(item: dict, transcript: Transcript) -> tuple[bool | None, str]:
    truth = item["truth"]
    reply = transcript.turns[-1].reply
    line = answer_line(reply)
    nums = numbers_in(line.split(":", 1)[1]) if line else numbers_in(reply)
    if line and len(nums) != 1:
        return False, f"answer line holds {len(nums)} numbers: {line.strip()[:60]}"
    return (
        any(close_enough(n, truth) for n in nums),
        f"got {nums[:4]} want {truth['value']} (+/-{max(truth['tol_abs'], truth['tol_rel'] * truth['value']):.2f})",
    )


def check_room(item: dict, transcript: Transcript) -> tuple[bool | None, str]:
    truth = item["truth"]
    reply = transcript.turns[-1].reply
    line = answer_line(reply) or reply
    found = any(mentions(line, n, r) for n, r in zip(truth["names"], truth["refs"]))
    if not found:
        return False, f"room {truth['names']} not named"
    if truth.get("area_m2"):
        area_ok = any(abs(n - truth["area_m2"]) <= 0.05 * truth["area_m2"] for n in numbers_in(line))
        return area_ok, f"area want {truth['area_m2']:.1f}"
    return True, "room named"


def check_route(item: dict, transcript: Transcript) -> tuple[bool | None, str]:
    truth = item["truth"]
    replies = "\n".join(turn.reply for turn in transcript.turns)
    if not truth["reachable"]:
        said = NO_ROUTE.search(replies) is not None
        invented = any(_route_length(c) is not None for _, c in ok_calls(transcript, "find_route", "give_directions"))
        return (
            said and not invented,
            "no route expected; said so" if said else "no route expected but reply does not say so",
        )
    want = truth["length_m"]
    tolerance = max(1.0, 0.01 * want)
    in_reply = any(abs(n - want) <= tolerance for n in numbers_in(replies))
    in_tool = any(abs((_route_length(c) or -99) - want) <= tolerance for _, c in ok_calls(transcript, *ROUTE_TOOLS))
    if in_reply:
        return True, f"length {want} stated"
    return False, f"length {want} " + ("computed by tool but not said" if in_tool else "not found in reply or tools")


def _route_length(call) -> float | None:
    try:
        body = json.loads(call.result)
    except (ValueError, TypeError):
        return None
    for key in ("length_m", "total_length_m", "optimal_length_m"):
        if isinstance(body, dict) and isinstance(body.get(key), (int, float)):
            return float(body[key])
    return None


def check_truth(item: dict, transcript: Transcript) -> tuple[bool | None, str]:
    truth = item["truth"]
    kind = truth["type"]
    reply = transcript.turns[-1].reply
    if kind == "none":
        return None, ""
    if kind == "number":
        return check_number(item, transcript)
    if kind == "room":
        return check_room(item, transcript)
    if kind == "route":
        return check_route(item, transcript)
    if kind == "rooms_any":
        hit = any(mentions(reply, n, r) for n, r in zip(truth["names"], truth["refs"]))
        if not hit and len(truth["names"]) > 1 and "?" in reply:
            return True, "asked which one (several candidates)"
        return hit, "a true location named" if hit else f"none of {truth['names'][:3]} named"
    if kind == "rooms_all":
        missing = [n for n, r in zip(truth["names"], truth["refs"]) if not mentions(reply, n, r)]
        return not missing, f"{len(truth['names']) - len(missing)}/{len(truth['names'])} listed"
    if kind == "text_any":
        hit = any(text.lower() in reply.lower() for text in truth["any"])
        return hit, "expected wording found" if hit else f"none of {truth['any'][:3]} in reply"
    if kind == "bool":
        first = re.search(r"\b(yes|no|nope|ja|nein|not)\b", reply, re.IGNORECASE)
        said_yes = bool(first) and first.group(1).lower() in ("yes", "ja")
        return bool(first) and said_yes == truth["value"], f"first yes/no word: {first.group(1) if first else None}"
    return None, f"unknown truth type {kind}"


def invented_rooms(transcript: Transcript, known_names: set[str]) -> list[str]:
    grounded = all_text(transcript) + "\n" + "\n".join(known_names).lower()
    bad = []
    for turn in transcript.turns:
        for token in REF_TOKEN.findall(turn.reply):
            token = token.rstrip(".,;:)")
            if token.startswith(SKIP_PREFIX) or not re.search(r"[.-]", token.split(" ")[-1]):
                continue
            if (
                token.split(" ")[-1].lower() not in grounded
            ):  # the number part decides; plurals like 'Kitchens 1.07' pass
                bad.append(token)
    return bad


def step_lines(reply: str) -> int:
    return sum(1 for line in reply.splitlines() if re.match(r"^\s*(\d+[.)]|[-*•]|step \d)", line, re.IGNORECASE))


def check_rule(rule: str, item: dict, transcript: Transcript, known_names: set[str]) -> tuple[bool, str]:
    last = transcript.turns[-1].reply
    applied = transcript.applied_changes()
    name, _, arg = rule.partition(":")
    if name == "answer_line":
        lines = [x for x in last.splitlines() if re.match(r"^\W*Answer:", x.strip(), re.IGNORECASE)]
        return len(lines) == 1 and last.strip().splitlines()[-1] == lines[0], "exactly one final Answer line"
    if name == "route_tool":
        if item["truth"].get("reachable") is False:  # no route is the right answer: trying is enough
            return any(c.name in ROUTE_TOOLS for turn in transcript.turns for c in turn.calls), "a route tool was tried"
        return bool(ok_calls(transcript, *ROUTE_TOOLS)), "a route tool succeeded"
    if name in ("step_free_all", "step_free_flag"):
        attempts = [
            (i, c)
            for i, turn in enumerate(transcript.turns)
            for c in turn.calls
            if c.name in ("find_route", "give_directions", "campus_route")
        ]
        if not attempts:
            return "?" in last, "no route call; asked back" if "?" in last else "no route call and no question"
        if name == "step_free_flag":
            return any(c.args.get("step_free") for _, c in attempts), "a route call carries step_free"
        first_per_turn = {}
        for i, c in attempts:
            first_per_turn.setdefault(i, c)  # later calls may compare with the normal route on purpose
        wrong = [i for i, c in first_per_turn.items() if not c.args.get("step_free")]
        return (
            not wrong,
            f"first route call without step_free in turns {wrong}"
            if wrong
            else "step_free in every turn's first route call",
        )
    if name == "closure_respected":
        said = bool(ok_calls(transcript, "assume_closed", "confirm_change"))
        in_route = any(
            re.search(r'"closed":\s*\[\s*"', c.result) for _, c in ok_calls(transcript, "find_route", "give_directions")
        )
        return said or in_route, "closure applied before routing"
    if name == "no_route_call":
        return not ok_calls(transcript, *ROUTE_TOOLS), "no successful route call"
    if name == "no_invented":
        bad = invented_rooms(transcript, known_names)
        return not bad, f"ungrounded room names: {bad[:3]}" if bad else "all room names grounded"
    if name == "not_applied":
        return not applied, "no confirm_change applied" if not applied else f"applied in turns {applied}"
    if name == "card_first":
        proposed = [i for i, _ in ok_calls(transcript, "propose_change")]
        return bool(proposed) and 0 not in applied and proposed[
            0
        ] == 0, "propose_change in turn 0, nothing applied in turn 0"
    if name == "card_or_asked":  # several matching machines: asking which one comes before the card
        proposed = [i for i, _ in ok_calls(transcript, "propose_change")]
        return (bool(proposed) and 0 not in applied) or "?" in transcript.turns[0].reply, "card, or a question first"
    if name == "applied_after_yes":
        return applied == [1], f"applied in turns {applied}, want [1]"
    if name == "no_mutation":
        changed = ok_calls(transcript, "assume_closed") or applied
        return not changed, "building unchanged"
    if name == "max3steps":
        worst = max(step_lines(t.reply) for t in transcript.turns)
        return worst <= 3, f"most step lines in one reply: {worst}"
    if name == "asked_back":
        return "?" in last, "reply asks a question"
    if name == "no_data_admit":
        return NOT_FOUND.search(last) is not None, "says the data is not there"
    if name == "tool":
        return bool(ok_calls(transcript, arg)), f"{arg} succeeded"
    if name == "no_tool":
        return not [
            c for t in transcript.turns for c in t.calls if c.name == arg and not c.is_error
        ], f"no successful {arg}"
    if name == "no_token":
        return arg.lower() not in "\n".join(t.reply for t in transcript.turns).lower(), f"reply never contains {arg}"
    return False, f"unknown rule {rule}"


def implicit_rules(item: dict) -> list[str]:
    behaviour = item["expected_behaviour"]
    if behaviour == "ask_back":
        return ["no_route_call"]
    if behaviour == "refuse":
        return ["no_mutation", "not_applied"]
    return []


def score(item: dict, transcript: Transcript, known_names: set[str]) -> dict:
    """passed True/False, or None when nothing could be checked; reasons lists every failed or notable check."""
    checks: list[tuple[str, bool | None, str]] = []
    truth_ok, truth_note = check_truth(item, transcript)
    if truth_ok is not None:
        checks.append(("truth", truth_ok, truth_note))
    for rule in dict.fromkeys(item.get("rules", []) + implicit_rules(item)):
        ok, note = check_rule(rule, item, transcript, known_names)
        checks.append((rule, ok, note))
    if item["expected_behaviour"] == "ask_back" and "asked_back" not in item.get("rules", []):
        reply = transcript.turns[-1].reply
        said = "?" in reply or NOT_FOUND.search(reply) is not None
        checks.append(("asked_or_said_unknown", said, "asks or says it is unknown"))
    if not checks:
        return {"passed": None, "reasons": ["nothing checkable"]}
    failed = [f"{name}: {note}" for name, ok, note in checks if ok is False]
    return {"passed": not failed, "reasons": failed or [f"{name}: {note}" for name, _, note in checks[:2]]}
