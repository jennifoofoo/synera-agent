import json

from building_agent.registry import load_kinds
from building_agent.tools import make_tools
from tests.conftest import labelled_questions, load_map


def tool_by_name(tools, name):
    return next(tool for tool in tools if tool.name == name)


def test_every_kind_becomes_a_tool_without_bm_in_its_schema():
    building_dir, _ = labelled_questions("errand")[0]
    tools = make_tools(load_map(building_dir), None)
    for name in load_kinds():
        schema = tool_by_name(tools, name).to_dict()["input_schema"]
        assert "bm" not in schema["properties"], name
        assert tool_by_name(tools, name).to_dict()["description"].strip()
    assert tool_by_name(tools, "find_space")


def test_kind_tool_returns_the_same_answer_as_the_kind():
    building_dir, question = labelled_questions("errand")[0]
    bm = load_map(building_dir)
    tool = tool_by_name(make_tools(bm, None), "errand")
    result = json.loads(tool(**question["inputs"]))
    assert result == load_kinds()["errand"].fn(bm, **question["inputs"])
