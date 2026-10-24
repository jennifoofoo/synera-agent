"""Walk out of the building: route-model distance from every node to the nearest entrance.

The kit graph has no outside node (entrances do not link through a shared outside), so "the way out" is the
route distance to the nearest entrance door node. A space that reaches no entrance is absent from the result,
it is unreachable, not at distance zero."""

import networkx as nx

from starter_agent.building_map import DOOR_PREFIX, OUTSIDE, BuildingMap

EXIT = "exit:virtual-sink"


def entrance_nodes(bm: BuildingMap, graph: nx.MultiGraph) -> list[str]:
    """Door nodes of the open entrances (openings with 'outside' on one side) that are in `graph`."""
    nodes = (DOOR_PREFIX + opening["id"] for opening in bm.openings.values() if OUTSIDE in opening["space_ids"])
    return [node for node in nodes if node in graph]


def with_exit(bm: BuildingMap, graph: nx.MultiGraph) -> nx.MultiGraph:
    """A copy of `graph` with a virtual sink joined to every entrance at zero cost. The kit graph stays untouched."""
    copy = graph.copy()
    for node in entrance_nodes(bm, graph):
        copy.add_edge(node, EXIT, weight=0.0)
    return copy


def distances_to_exit(bm: BuildingMap, graph: nx.MultiGraph) -> dict[str, float]:
    """Walking distance to the nearest entrance for every node of `graph` that can reach one."""
    if not entrance_nodes(bm, graph):
        return {}
    lengths = nx.single_source_dijkstra_path_length(with_exit(bm, graph), EXIT, weight="weight")
    lengths.pop(EXIT, None)
    return lengths


def way_out(bm: BuildingMap, graph: nx.MultiGraph, node: str) -> list[str]:
    """Shortest node path from `node` to its nearest entrance door node (empty if there is none)."""
    try:
        path = nx.dijkstra_path(with_exit(bm, graph), node, EXIT, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []
    return path[:-1]
