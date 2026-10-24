"""get_selection: what the person clicked on the plan, as names the model can read out.

The server validates the click and stores it on the conversation state for one turn only. It never goes into
the user message text, so a message cannot fake a selection."""

from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from starter_agent.building_map import BuildingMap
from starter_agent.tools import as_json

NOTHING_SELECTED = "Nothing is selected. Ask the person to click the room or machine on the plan first."


def make_selection_tools(bm: BuildingMap, state) -> list:
    @beta_tool
    def get_selection() -> str:
        """The room, machine or spot the person clicked on the plan. Call it first when they say 'here', 'this',
        'it' or 'that' and a selection may exist. For placement use hint {'point': point} from the result."""
        selection = getattr(state, "selection", None)
        if selection is None:
            raise ToolError(NOTHING_SELECTED)
        space = bm.spaces.get(selection.space_id) if selection.space_id else None
        asset = bm.assets.get(selection.asset_id) if selection.asset_id else None
        floor = bm.floors.get(selection.floor_id) if selection.floor_id else None
        return as_json(
            {
                "space_id": selection.space_id,
                "space_name": space["name"] if space else None,
                "floor": floor["name"] if floor else None,
                "asset_id": selection.asset_id,
                "asset_name": asset["name"] if asset else None,
                "point": list(selection.point) if selection.point else None,
                "note": selection.note,
            }
        )

    return [get_selection]
