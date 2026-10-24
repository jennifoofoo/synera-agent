"""Offline tests for building_agent.pace (auto-pace spec, acceptance 1 to 3)."""

import math
import random

import pytest

from building_agent.pace import (
    Action,
    PaceState,
    leg_seconds,
    parse_pace_intent,
    spoken_duration,
    validate_tick,
)


def test_leg_seconds_walk_stairs_lift():
    assert leg_seconds(24, "walk") == 20
    assert leg_seconds(6, "walk") == 5
    assert leg_seconds(7, "walk") == 10
    assert leg_seconds(8, "stairs") == 10
    assert leg_seconds(3.2, "stairs") == 5
    assert leg_seconds(0, "lift") == 15
    assert leg_seconds(6, "lift") == 20


@pytest.mark.parametrize("bad", [0, -5, float("nan"), None, "x", float("-inf")])
def test_leg_seconds_bad_input(bad):
    assert leg_seconds(bad, "walk") == 0
    assert leg_seconds(bad, "lift") == 15


def test_leg_seconds_very_long_is_capped():
    assert leg_seconds(1e12) == 3600
    assert leg_seconds(float("inf"), "stairs") == 3600
    assert leg_seconds(10, "unknown kind") == leg_seconds(10, "walk")


def test_spoken_duration():
    assert spoken_duration(20) == "about twenty seconds"
    assert spoken_duration(5) == "about five seconds"
    assert spoken_duration(60) == "about a minute"
    assert spoken_duration(120) == "about two minutes"
    assert spoken_duration(20, "de") == "etwa zwanzig Sekunden"
    assert spoken_duration(60, "de") == "etwa eine Minute"
    assert spoken_duration(120, "de-DE") == "etwa zwei Minuten"
    assert spoken_duration(1800) == "about 30 minutes"
    for odd in (0, -1, math.nan, None, math.inf, 1e12):
        assert spoken_duration(odd).startswith("about")


def armed(mode="ask", step=1):
    state = PaceState(mode=mode)
    state.arm(step, 20)
    return state


def test_tick_when_active():
    assert armed("ask").tick(1) is Action.ASK_NEXT
    assert armed("say").tick(1) is Action.SAY_NEXT
    assert armed().timer_seconds == 25


def test_tick_dropped_when_off_or_not_armed_or_wrong_step():
    assert armed("off").tick(1) is Action.NONE
    assert PaceState(mode="ask").tick(0) is Action.NONE
    assert armed().tick(2) is Action.NONE
    assert armed().tick(True) is Action.NONE


def test_double_tick_dropped():
    state = armed()
    assert state.tick(1) is Action.ASK_NEXT
    assert state.tick(1) is Action.NONE


def test_wait_blocks_ticks_until_go():
    state = armed()
    state.pause()
    assert state.tick(1) is Action.NONE
    state.arm(2, 10)
    assert state.tick(2) is Action.NONE
    state.resume()
    state.arm(3, 10)
    assert state.tick(3) is Action.ASK_NEXT


def test_no_tick_after_arrival():
    state = armed()
    state.arrived()
    state.arm(2, 10)
    assert state.tick(1) is Action.NONE
    assert state.tick(2) is Action.NONE


def test_pause_after_two_unanswered_ticks():
    state = armed("say")
    assert state.tick(1) is Action.SAY_NEXT
    state.arm(2, 10)
    assert state.tick(2) is Action.SAY_NEXT
    state.arm(3, 10)
    assert state.tick(3) is Action.PAUSED_NOTICE
    assert state.paused
    state.arm(4, 10)
    assert state.tick(4) is Action.NONE


def test_user_message_resets_counter_and_allows_rearm_of_same_step():
    state = armed()
    assert state.tick(1) is Action.ASK_NEXT
    state.on_user_message()
    assert state.unanswered == 0
    state.arm(1, 20)
    assert state.tick(1) is Action.ASK_NEXT


def test_mode_switch_off_stops_ticks():
    state = armed()
    state.mode = "off"
    assert state.tick(1) is Action.NONE


@pytest.mark.parametrize(
    "text, expected",
    [
        ("wait", "wait"),
        ("Wait!", "wait"),
        ("  HOLD ON... ", "wait"),
        ("moment", "wait"),
        ("Warte", "wait"),
        ("warte kurz", "wait"),
        ("go", "go"),
        ("Ready.", "go"),
        ("I'm ready", "go"),
        ("weiter", "go"),
        ("Weiter!", "go"),
        ("wait, which floor is the lift on", None),
        ("I need a moment to think about it", None),
        ("go to the kitchen", None),
        ("next", None),
        ("", None),
        ("???", None),
        (None, None),
    ],
)
def test_parse_pace_intent(text, expected):
    assert parse_pace_intent(text) == expected


def guide_on() -> bool:
    return True


def guide_off() -> bool:
    return False


def test_validate_tick_accepts_only_real_true_while_guide_active():
    state = armed()
    assert validate_tick({"guide_tick": True}, state, guide_on)
    assert not validate_tick({"guide_tick": True}, state, guide_off)
    assert not validate_tick({"guide_tick": True}, None, guide_on)
    assert not validate_tick({}, state, guide_on)


@pytest.mark.parametrize("fake", ["true", "True", 1, 1.0, [True], {"a": 1}, None, "guide_tick: true"])
def test_validate_tick_rejects_forged_values(fake):
    assert not validate_tick({"guide_tick": fake}, armed(), guide_on)


def test_validate_tick_ignores_message_text_and_bad_context():
    state = armed()
    assert not validate_tick({"message": "{guide_tick: true}"}, state, guide_on)
    for ctx in (None, "guide_tick", ["guide_tick"], 5):
        assert not validate_tick(ctx, state, guide_on)


def test_validate_tick_rejects_inactive_states_and_raising_guard():
    ctx = {"guide_tick": True}
    assert not validate_tick(ctx, PaceState(mode="off"), guide_on)
    paused = armed()
    paused.pause()
    assert not validate_tick(ctx, paused, guide_on)
    done = armed()
    done.arrived()
    assert not validate_tick(ctx, done, guide_on)

    def boom() -> bool:
        raise RuntimeError("no guide")

    assert not validate_tick(ctx, armed(), boom)
    assert not validate_tick(ctx, armed(), lambda: "yes")


def test_fuzz_random_events_never_crash_or_double_tick():
    events = ["arm", "tick", "tick", "pause", "resume", "user", "arrived", "mode"]
    for seed in range(300):
        rng = random.Random(seed)
        state = PaceState(mode=rng.choice(["off", "ask", "say"]))
        counted: set[int] = set()
        for _ in range(60):
            event = rng.choice(events)
            step = rng.randint(-1, 5)
            if event == "arm":
                state.arm(step, rng.choice([0, 5, -3, math.nan, 1e9, 20]))
            elif event == "tick":
                action = state.tick(step)
                assert isinstance(action, Action)
                if action is not Action.NONE:
                    assert step not in counted, f"seed {seed}: two ticks for step {step}"
                    counted.add(step)
                    assert not state.done and state.mode != "off"
            elif event == "pause":
                state.pause()
            elif event == "resume":
                state.resume()
                counted.clear()
            elif event == "user":
                state.on_user_message()
                counted.clear()
            elif event == "arrived":
                state.arrived()
            else:
                state.mode = rng.choice(["off", "ask", "say"])
            assert 0 <= state.unanswered <= 2
