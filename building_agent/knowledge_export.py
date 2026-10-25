"""Export of the building plus place knowledge as a temporal knowledge graph (docs/specs/place-knowledge.md).

- `graph_jsonld`: JSON-LD with Brick Schema and RealEstateCore (REC) types. Nodes: building, floors, spaces,
  doors/openings, lifts/stairs, assets, persons, facts. Edges: connects, isLocatedIn / hasPart, anchoredAt,
  resolves, reportedBy, related; facts carry validFrom / validTo.
- `aas_export`: Asset Administration Shell (simplified AAS v3 JSON): per machine/equipment a shell with the
  submodels "Nameplate" (name, type, category, location) and "OpenIssues" (issues and notes open now).
Only data we have; unknown room types become rec:Room, unknown asset types brick:Equipment (furniture:
rec:Furniture)."""

from building_agent.knowledge import KnowledgeStore, building_of, parse_time
from building_agent.time_words import berlin_now
from starter_agent.building_map import BuildingMap

BRICK = "https://brickschema.org/schema/Brick#"
REC = "https://w3id.org/rec#"
WANDA = "https://synera-agent.example/wanda#"

# room_type -> (REC class, Brick class). Every room type in the kit data has a row (tests check this).
ROOM_TYPES = {
    "additive_zone": ("rec:ProductionRoom", "brick:Space"),
    "assembly_zone": ("rec:ProductionRoom", "brick:Space"),
    "balcony": ("rec:Balcony", "brick:Outdoor_Area"),
    "bathroom": ("rec:Bathroom", "brick:Restroom"),
    "bedroom": ("rec:Bedroom", "brick:Room"),
    "canteen": ("rec:Cafeteria", "brick:Break_Room"),
    "corridor": ("rec:Hallway", "brick:Hallway"),
    "generic_room": ("rec:Room", "brick:Room"),
    "kitchen": ("rec:Kitchen", "brick:Kitchen"),
    "lab": ("rec:Laboratory", "brick:Laboratory"),
    "lecture_hall": ("rec:Auditorium", "brick:Room"),
    "library": ("rec:Library", "brick:Room"),
    "lift": ("rec:ElevatorShaft", "brick:Elevator_Shaft"),
    "living_room": ("rec:LivingRoom", "brick:Room"),
    "lobby": ("rec:Lobby", "brick:Lobby"),
    "locker_room": ("rec:LockerRoom", "brick:Room"),
    "logistics_zone": ("rec:LoadingReceivingRoom", "brick:Space"),
    "makerspace": ("rec:Workshop", "brick:Room"),
    "meeting_room": ("rec:ConferenceRoom", "brick:Conference_Room"),
    "office": ("rec:Office", "brick:Office"),
    "print_room": ("rec:CopyingRoom", "brick:Room"),
    "production_zone": ("rec:ProductionRoom", "brick:Space"),
    "quality_lab": ("rec:Laboratory", "brick:Laboratory"),
    "seminar_room": ("rec:Classroom", "brick:Room"),
    "server_room": ("rec:DataServerRoom", "brick:Server_Room"),
    "stairwell": ("rec:Stairwell", "brick:Vertical_Space"),
    "storage": ("rec:StorageRoom", "brick:Storage_Room"),
    "technical_room": ("rec:UtilitiesRoom", "brick:Mechanical_Room"),
    "toilet": ("rec:Toilet", "brick:Restroom"),
    "warehouse_zone": ("rec:Warehouse", "brick:Storage_Room"),
}
DEFAULT_ROOM = ("rec:Room", "brick:Room")

# asset type -> Brick (or REC) class, for the types where a standard class exists; the rest by category.
ASSET_TYPES = {
    "fire_extinguisher": "brick:Fire_Extinguisher",
    "defibrillator": "brick:Equipment",
    "eyewash_station": "brick:Safety_Equipment",
    "hvac_unit": "brick:HVAC_Equipment",
    "boiler": "brick:Boiler",
    "compressor": "brick:Compressor",
    "electrical_panel": "brick:Panelboard",
    "ups_unit": "brick:Uninterruptible_Power_Supply",
    "server_rack": "brick:Equipment",
    "fume_hood": "brick:Fume_Hood",
    "conveyor": "brick:Conveyor",
    "water_dispenser": "brick:Water_Distribution",
    "dishwasher": "brick:Equipment",
    "fridge": "brick:Refrigerator",
    "coffee_machine": "brick:Equipment",
    "display_screen": "brick:Display",
    "projector": "brick:Equipment",
    "internal_stairs": "rec:Stairs",
}
CATEGORY_TYPES = {
    "machine": "brick:Equipment",
    "equipment": "brick:Equipment",
    "fixture": "rec:Fixture",
    "furniture": "rec:Furniture",
}
AAS_CATEGORIES = ("machine", "equipment")
CONNECTOR_TYPES = {"lift": ("rec:Elevator", "brick:Elevator"), "stairs": ("rec:Stairs", "brick:Stairs")}

CONTEXT = {
    "brick": BRICK,
    "rec": REC,
    "wanda": WANDA,
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "name": "rec:name",
    "level": "wanda:level",
    "roomType": "wanda:roomType",
    "assetType": "wanda:assetType",
    "category": "wanda:category",
    "kind": "wanda:kind",
    "text": "wanda:text",
    "status": "wanda:status",
    "source": "wanda:source",
    "stepFree": "wanda:stepFree",
    "closed": "wanda:closed",
    "closedUntil": {"@id": "wanda:closedUntil", "@type": "xsd:dateTime"},
    "position": "wanda:position",
    "validFrom": {"@id": "wanda:validFrom", "@type": "xsd:dateTime"},
    "validTo": {"@id": "wanda:validTo", "@type": "xsd:dateTime"},
    "createdAt": {"@id": "wanda:createdAt", "@type": "xsd:dateTime"},
    "isLocatedIn": {"@id": "rec:locatedIn", "@type": "@id"},
    "hasPart": {"@id": "rec:hasPart", "@type": "@id"},
    "isPartOf": {"@id": "rec:isPartOf", "@type": "@id"},
    "connects": {"@id": "wanda:connects", "@type": "@id"},
    "anchoredAt": {"@id": "wanda:anchoredAt", "@type": "@id"},
    "related": {"@id": "wanda:related", "@type": "@id"},
    "resolves": {"@id": "wanda:resolves", "@type": "@id"},
    "resolvedBy": {"@id": "wanda:resolvedBy", "@type": "@id"},
    "reportedBy": {"@id": "wanda:reportedBy", "@type": "@id"},
}


def room_types(room_type: str) -> list[str]:
    return list(ROOM_TYPES.get(room_type, DEFAULT_ROOM))


def asset_types(asset: dict) -> list[str]:
    main = ASSET_TYPES.get(asset["type"]) or CATEGORY_TYPES.get(asset.get("category"), "brick:Equipment")
    return [main] if main.startswith("rec:") or main == "brick:Equipment" else [main, "brick:Equipment"]


def node_id(building: str, kind: str, item_id: str) -> str:
    return f"urn:synera:{building}:{kind}:{item_id}"


def graph_jsonld(bm: BuildingMap, store: KnowledgeStore, at=None) -> dict:
    """The whole graph as one JSON-LD document ({@context, @graph})."""
    building = building_of(bm)
    moment = berlin_now(parse_time(at)) if at is not None else berlin_now()
    info = bm.data.get("building", {})
    ref = {}

    def iri(item_id: str) -> str:
        if item_id in ref:
            return ref[item_id]
        if item_id in bm.floors:
            kind = "floor"
        elif item_id in bm.spaces:
            kind = "space"
        elif item_id in bm.openings:
            kind = "opening"
        elif item_id in bm.connectors:
            kind = "connector"
        elif item_id in bm.assets:
            kind = "asset"
        else:
            kind = "node"
        ref[item_id] = node_id(building, kind, item_id)
        return ref[item_id]

    building_iri = node_id(building, "building", building)
    closures = store.active_closures(bm, moment)
    graph: list[dict] = [
        {
            "@id": building_iri,
            "@type": ["rec:Building", "brick:Building"],
            "name": info.get("name", building),
            "hasPart": [iri(floor_id) for floor_id in bm.floors],
        }
    ]
    for floor_id, floor in bm.floors.items():
        graph.append(
            {
                "@id": iri(floor_id),
                "@type": ["rec:Level", "brick:Floor"],
                "name": floor["name"],
                "level": floor["level"],
                "isPartOf": building_iri,
            }
        )
    for space_id, space in bm.spaces.items():
        graph.append(
            {
                "@id": iri(space_id),
                "@type": room_types(space.get("room_type", "")),
                "name": space["name"],
                "roomType": space.get("room_type"),
                "isPartOf": iri(space["floor_id"]),
                "closed": space_id in bm.closed,
            }
        )
    for opening_id, opening in bm.openings.items():
        graph.append(
            {
                "@id": iri(opening_id),
                "@type": ["rec:Door", "brick:Door"] if opening.get("kind") == "door" else ["rec:Door", "brick:Space"],
                "kind": opening.get("kind"),
                "connects": [iri(space_id) for space_id in opening["space_ids"]],
                "isPartOf": iri(opening["floor_id"]),
                "stepFree": bool(opening.get("step_free")),
                "closed": opening_id in bm.closed,
                **({"closedUntil": closures[opening_id]} if closures.get(opening_id) else {}),
            }
        )
    for connector_id, connector in bm.connectors.items():
        graph.append(
            {
                "@id": iri(connector_id),
                "@type": list(CONNECTOR_TYPES.get(connector["kind"], ("rec:Space", "brick:Space"))),
                "name": connector.get("name"),
                "connects": [iri(space_id) for space_id in connector["space_ids"]],
                "stepFree": bool(connector.get("step_free")),
                "closed": connector_id in bm.closed,
                **({"closedUntil": closures[connector_id]} if closures.get(connector_id) else {}),
            }
        )
    for asset_id, asset in bm.assets.items():
        graph.append(
            {
                "@id": iri(asset_id),
                "@type": asset_types(asset),
                "name": asset["name"],
                "assetType": asset["type"],
                "category": asset.get("category"),
                "isLocatedIn": iri(asset["space_id"]),
            }
        )
    for person in store.persons(bm):
        graph.append(
            {
                "@id": node_id(building, "person", person["person_id"]),
                "@type": ["rec:Person", "wanda:Person"],
                "name": person["name"],
            }
        )
    for fact in store.query(bm, history=True, at=moment):
        anchor = fact.anchor
        anchors = [anchor.get("asset_id") or anchor.get("element_id") or anchor.get("space_id")]
        if anchor.get("asset_id") and anchor.get("element_id"):
            anchors.append(anchor["element_id"])
        entry = {
            "@id": node_id(building, "fact", fact.id),
            "@type": ["wanda:Fact", f"wanda:{fact.kind.capitalize()}"],
            "kind": fact.kind,
            "text": fact.text,
            "status": fact.status,
            "source": fact.source,
            "validFrom": fact.valid_from,
            "createdAt": fact.created_at,
            "anchoredAt": [iri(item) for item in anchors if item],
            "isLocatedIn": iri(anchor["space_id"]) if anchor.get("space_id") else None,
        }
        if fact.valid_to:
            entry["validTo"] = fact.valid_to
        if fact.related:
            entry["related"] = [iri(item) for item in fact.related]
        if fact.resolves:
            entry["resolves"] = node_id(building, "fact", fact.resolves)
        if fact.resolved_by:
            entry["resolvedBy"] = node_id(building, "fact", fact.resolved_by)
        if fact.person_id:
            entry["reportedBy"] = node_id(building, "person", fact.person_id)
        if anchor.get("point"):
            entry["position"] = anchor["point"]
        graph.append({key: value for key, value in entry.items() if value is not None})
    return {
        "@context": CONTEXT,
        "@id": building_iri + ":graph",
        "generatedAt": moment.isoformat(timespec="seconds"),
        "@graph": graph,
    }


def property_element(id_short: str, value) -> dict:
    return {
        "modelType": "Property",
        "idShort": id_short,
        "valueType": "xs:string",
        "value": "" if value is None else str(value),
    }


def aas_export(bm: BuildingMap, store: KnowledgeStore, at=None) -> dict:
    """{assetAdministrationShells, submodels} in the AAS v3 JSON shape, one shell per machine/equipment asset."""
    building = building_of(bm)
    moment = berlin_now(parse_time(at)) if at is not None else berlin_now()
    info = bm.data.get("building", {})
    open_facts = [fact for fact in store.active(bm, moment) if fact.kind in ("issue", "note")]
    by_asset: dict[str, list] = {}
    for fact in open_facts:
        for item in [fact.anchor.get("asset_id"), *fact.related]:
            if item in bm.assets:
                by_asset.setdefault(item, []).append(fact)
    shells, submodels = [], []
    for asset_id, asset in bm.assets.items():
        if asset.get("category") not in AAS_CATEGORIES:
            continue
        base = f"urn:synera:{building}:aas:{asset_id}"
        space = bm.spaces.get(asset["space_id"], {})
        floor = bm.floors.get(asset.get("floor_id") or space.get("floor_id"), {})
        nameplate = {
            "modelType": "Submodel",
            "id": f"{base}:sm:nameplate",
            "idShort": "Nameplate",
            "semanticId": {
                "type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": "https://admin-shell.io/zvei/nameplate/2/0/Nameplate"}],
            },
            "submodelElements": [
                property_element("Name", asset["name"]),
                property_element("Type", asset["type"]),
                property_element("Category", asset.get("category")),
                {
                    "modelType": "SubmodelElementCollection",
                    "idShort": "Location",
                    "value": [
                        property_element("Room", space.get("name")),
                        property_element("RoomId", asset["space_id"]),
                        property_element("Floor", floor.get("name")),
                        property_element("Building", info.get("name", building)),
                    ],
                },
            ],
        }
        issues = {
            "modelType": "Submodel",
            "id": f"{base}:sm:openissues",
            "idShort": "OpenIssues",
            "submodelElements": [
                {
                    "modelType": "SubmodelElementCollection",
                    "idShort": fact.id.replace("-", "_"),
                    "value": [
                        property_element("Kind", fact.kind),
                        property_element("Text", fact.text),
                        property_element("ValidFrom", fact.valid_from),
                        property_element("ValidTo", fact.valid_to),
                        property_element("Author", fact.author),
                    ],
                }
                for fact in by_asset.get(asset_id, [])
            ],
        }
        submodels += [nameplate, issues]
        shells.append(
            {
                "modelType": "AssetAdministrationShell",
                "id": base,
                "idShort": asset_id.replace("-", "_"),
                "assetInformation": {
                    "assetKind": "Instance",
                    "globalAssetId": f"urn:synera:{building}:asset:{asset_id}",
                },
                "submodels": [
                    {"type": "ModelReference", "keys": [{"type": "Submodel", "value": submodel["id"]}]}
                    for submodel in (nameplate, issues)
                ],
            }
        )
    return {
        "generatedAt": moment.isoformat(timespec="seconds"),
        "assetAdministrationShells": shells,
        "submodels": submodels,
    }
