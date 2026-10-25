"""Live: an inspection round is planned by plan_round in one call, not by trying orders with find_route.
Asserts on tool calls and on the numbers in the reply, not on wording."""

import json
import re
from pathlib import Path

import pytest

from tests.live.harness import run_script

pytestmark = pytest.mark.live

FACTORY = Path("data/dev/proc-factory-dev-003")
ROUND = "Hey Wanda, inspection round: all fire extinguishers on the ground floor, I start at Main aisle H-B5."


def test_inspection_round_uses_plan_round_once():
    transcript = run_script(FACTORY, [ROUND])
    turn = transcript.turns[0]
    calls = turn.called("plan_round")
    assert len(calls) == 1 and not calls[0].is_error, [call.name for call in turn.calls]
    assert not turn.called("find_route"), "the model ordered stops by hand"
    result = json.loads(calls[0].result)
    assert len(result["stops"]) == 6
    numbers = {round(float(n)) for n in re.findall(r"\d+(?:\.\d+)?", turn.reply.replace(",", "."))}
    assert any(abs(n - result["total_m"]) <= 1 for n in numbers), turn.reply[:400]
    second = result["stops"][1]["room"]
    assert second.lower() in turn.reply.lower() or second.split()[-1] in turn.reply, turn.reply[:400]
