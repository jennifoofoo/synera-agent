"""Asset types a person can add with `add_asset`: category, display label and footprint per type.

Generated, not hand-written: a read-only pass over every data/*/*/building.json (280 buildings, 85 703 assets).
Per `type`: category = most common category, label = most common name with the room reference stripped,
width_m and depth_m = median over all assets of that type (rounded to 2 decimals). All 96 types that occur are kept
(the cap of about 100 is not reached). Regenerate only when the data changes; never guess a size for an unknown type.
"""

import difflib

from starter_agent.building_map import MapError

ASSET_CATALOG: dict[str, dict] = {
    "chair": {"category": "furniture", "label": "Chair", "width_m": 0.5, "depth_m": 0.5},
    "desk": {"category": "furniture", "label": "Desk", "width_m": 1.4, "depth_m": 0.7},
    "wardrobe": {"category": "furniture", "label": "Wardrobe", "width_m": 1.2, "depth_m": 0.6},
    "nightstand": {"category": "furniture", "label": "Nightstand", "width_m": 0.45, "depth_m": 0.4},
    "plant": {"category": "furniture", "label": "Plant", "width_m": 0.4, "depth_m": 0.4},
    "toilet": {"category": "fixture", "label": "Toilet", "width_m": 0.45, "depth_m": 0.66},
    "office_chair": {"category": "furniture", "label": "Office chair", "width_m": 0.6, "depth_m": 0.6},
    "sink": {"category": "fixture", "label": "Sink", "width_m": 0.6, "depth_m": 0.45},
    "kitchen_counter": {"category": "fixture", "label": "Kitchen counter", "width_m": 2.34, "depth_m": 0.6},
    "shelf": {"category": "furniture", "label": "Shelf", "width_m": 1.0, "depth_m": 0.4},
    "bookshelf": {"category": "furniture", "label": "Bookshelf", "width_m": 0.9, "depth_m": 0.35},
    "dining_chair": {"category": "furniture", "label": "Dining chair", "width_m": 0.45, "depth_m": 0.45},
    "single_bed": {"category": "furniture", "label": "Single bed", "width_m": 0.9, "depth_m": 2.0},
    "bed": {"category": "furniture", "label": "Bed", "width_m": 1.6, "depth_m": 2.0},
    "fire_extinguisher": {"category": "equipment", "label": "Fire extinguisher", "width_m": 0.3, "depth_m": 0.3},
    "fridge": {"category": "equipment", "label": "Fridge", "width_m": 0.6, "depth_m": 0.65},
    "outdoor_chair": {"category": "furniture", "label": "Outdoor chair", "width_m": 0.5, "depth_m": 0.5},
    "stove": {"category": "equipment", "label": "Stove", "width_m": 0.6, "depth_m": 0.6},
    "filing_cabinet": {"category": "furniture", "label": "Filing cabinet", "width_m": 0.5, "depth_m": 0.6},
    "coffee_machine": {"category": "equipment", "label": "Coffee machine", "width_m": 0.4, "depth_m": 0.4},
    "bathtub": {"category": "fixture", "label": "Bathtub", "width_m": 1.64, "depth_m": 0.71},
    "seminar_table": {"category": "furniture", "label": "Seminar table", "width_m": 1.4, "depth_m": 0.6},
    "coffee_table": {"category": "furniture", "label": "Coffee table", "width_m": 1.0, "depth_m": 0.6},
    "sofa": {"category": "furniture", "label": "Sofa", "width_m": 2.0, "depth_m": 0.9},
    "tv_stand": {"category": "furniture", "label": "TV stand", "width_m": 1.5, "depth_m": 0.4},
    "server_rack": {"category": "equipment", "label": "Server rack", "width_m": 0.6, "depth_m": 1.2},
    "pallet_rack": {"category": "furniture", "label": "Pallet rack", "width_m": 2.7, "depth_m": 1.1},
    "microwave": {"category": "equipment", "label": "Microwave", "width_m": 0.5, "depth_m": 0.4},
    "dishwasher": {"category": "equipment", "label": "Dishwasher", "width_m": 0.6, "depth_m": 0.6},
    "outdoor_table": {"category": "furniture", "label": "Outdoor table", "width_m": 0.8, "depth_m": 0.8},
    "armchair": {"category": "furniture", "label": "Armchair", "width_m": 0.8, "depth_m": 0.8},
    "whiteboard": {"category": "equipment", "label": "Whiteboard", "width_m": 1.8, "depth_m": 0.1},
    "lab_bench": {"category": "furniture", "label": "Lab bench", "width_m": 3.0, "depth_m": 0.8},
    "dining_table": {"category": "furniture", "label": "Dining table", "width_m": 1.6, "depth_m": 0.9},
    "microscope": {"category": "equipment", "label": "Microscope", "width_m": 0.5, "depth_m": 0.5},
    "shower": {"category": "fixture", "label": "Shower", "width_m": 0.9, "depth_m": 0.83},
    "meeting_table": {"category": "furniture", "label": "Meeting table", "width_m": 2.4, "depth_m": 1.1},
    "display_screen": {"category": "equipment", "label": "Display screen", "width_m": 1.6, "depth_m": 0.3},
    "locker": {"category": "furniture", "label": "Locker", "width_m": 0.9, "depth_m": 0.5},
    "projector": {"category": "equipment", "label": "Projector", "width_m": 0.4, "depth_m": 0.3},
    "projector_screen": {"category": "equipment", "label": "Projector screen", "width_m": 2.4, "depth_m": 0.15},
    "coat_rack": {"category": "furniture", "label": "Coat rack", "width_m": 0.6, "depth_m": 0.3},
    "fume_hood": {"category": "equipment", "label": "Fume hood", "width_m": 1.5, "depth_m": 0.8},
    "oscilloscope_station": {"category": "equipment", "label": "Oscilloscope station", "width_m": 1.2, "depth_m": 0.7},
    "shoe_cabinet": {"category": "furniture", "label": "Shoe cabinet", "width_m": 0.8, "depth_m": 0.35},
    "lecture_seating_row": {"category": "furniture", "label": "Seating row", "width_m": 5.0, "depth_m": 0.8},
    "assembly_station": {"category": "furniture", "label": "Assembly station", "width_m": 2.4, "depth_m": 1.2},
    "bench": {"category": "furniture", "label": "Bench", "width_m": 1.5, "depth_m": 0.4},
    "tool_cabinet": {"category": "furniture", "label": "Tool cabinet", "width_m": 1.0, "depth_m": 0.6},
    "washing_machine": {"category": "equipment", "label": "Washing machine", "width_m": 0.6, "depth_m": 0.6},
    "3d_printer": {"category": "machine", "label": "3D printer", "width_m": 0.6, "depth_m": 0.6},
    "hand_dryer": {"category": "equipment", "label": "Hand dryer", "width_m": 0.3, "depth_m": 0.2},
    "canteen_table": {"category": "furniture", "label": "Canteen table", "width_m": 1.8, "depth_m": 0.8},
    "workbench": {"category": "furniture", "label": "Workbench", "width_m": 2.0, "depth_m": 0.8},
    "chemical_cabinet": {"category": "furniture", "label": "Chemical cabinet", "width_m": 1.0, "depth_m": 0.5},
    "eyewash_station": {"category": "equipment", "label": "Eyewash station", "width_m": 0.5, "depth_m": 0.4},
    "multifunction_printer": {
        "category": "equipment",
        "label": "Multifunction printer",
        "width_m": 0.8,
        "depth_m": 0.7,
    },
    "ups_unit": {"category": "equipment", "label": "UPS unit", "width_m": 0.6, "depth_m": 0.8},
    "packing_station": {"category": "furniture", "label": "Packing station", "width_m": 2.0, "depth_m": 1.0},
    "reading_table": {"category": "furniture", "label": "Reading table", "width_m": 1.6, "depth_m": 0.8},
    "forklift": {"category": "machine", "label": "Forklift", "width_m": 2.5, "depth_m": 1.2},
    "vending_machine": {"category": "equipment", "label": "Vending machine", "width_m": 0.9, "depth_m": 0.8},
    "paper_shelf": {"category": "furniture", "label": "Paper shelf", "width_m": 1.0, "depth_m": 0.4},
    "welding_station": {"category": "equipment", "label": "Welding station", "width_m": 2.0, "depth_m": 2.0},
    "pallet_jack": {"category": "equipment", "label": "Pallet jack", "width_m": 1.6, "depth_m": 0.7},
    "drill_press": {"category": "machine", "label": "Drill press", "width_m": 0.8, "depth_m": 0.8},
    "electrical_panel": {"category": "equipment", "label": "Electrical panel", "width_m": 1.0, "depth_m": 0.3},
    "industrial_3d_printer": {"category": "machine", "label": "Industrial 3D printer", "width_m": 1.5, "depth_m": 1.2},
    "forklift_charging_station": {
        "category": "equipment",
        "label": "Forklift charging station",
        "width_m": 1.5,
        "depth_m": 1.0,
    },
    "printer": {"category": "equipment", "label": "Printer", "width_m": 0.6, "depth_m": 0.5},
    "cnc_mill": {"category": "machine", "label": "CNC mill", "width_m": 3.0, "depth_m": 2.5},
    "internal_stairs": {"category": "fixture", "label": "Internal stairs", "width_m": 1.35, "depth_m": 0.96},
    "built_in_wardrobe": {"category": "furniture", "label": "Built in wardrobe", "width_m": 1.2, "depth_m": 0.6},
    "injection_moulding_machine": {
        "category": "machine",
        "label": "Injection moulding machine",
        "width_m": 5.0,
        "depth_m": 2.0,
    },
    "cnc_lathe": {"category": "machine", "label": "CNC lathe", "width_m": 3.5, "depth_m": 2.0},
    "soldering_station": {"category": "equipment", "label": "Soldering station", "width_m": 1.2, "depth_m": 0.6},
    "milling_machine": {"category": "machine", "label": "Milling machine", "width_m": 2.0, "depth_m": 1.8},
    "press_brake": {"category": "machine", "label": "Press brake", "width_m": 4.0, "depth_m": 1.8},
    "defibrillator": {"category": "equipment", "label": "Defibrillator", "width_m": 0.4, "depth_m": 0.2},
    "inspection_bench": {"category": "furniture", "label": "Inspection bench", "width_m": 2.0, "depth_m": 0.8},
    "reception_desk": {"category": "furniture", "label": "Reception desk", "width_m": 2.5, "depth_m": 0.8},
    "lectern": {"category": "furniture", "label": "Lectern", "width_m": 0.6, "depth_m": 0.5},
    "serving_counter": {"category": "fixture", "label": "Serving counter", "width_m": 4.0, "depth_m": 0.8},
    "hvac_unit": {"category": "machine", "label": "HVAC unit", "width_m": 2.0, "depth_m": 1.2},
    "coordinate_measuring_machine": {
        "category": "machine",
        "label": "Coordinate measuring machine",
        "width_m": 2.0,
        "depth_m": 1.5,
    },
    "boiler": {"category": "machine", "label": "Boiler", "width_m": 1.0, "depth_m": 1.0},
    "laser_cutter": {"category": "machine", "label": "Laser cutter", "width_m": 1.4, "depth_m": 0.9},
    "water_dispenser": {"category": "equipment", "label": "Water dispenser", "width_m": 0.4, "depth_m": 0.4},
    "compressor": {"category": "machine", "label": "Air compressor", "width_m": 1.5, "depth_m": 1.0},
    "robot_cell": {"category": "machine", "label": "Robot cell", "width_m": 4.0, "depth_m": 4.0},
    "waterjet_cutter": {"category": "machine", "label": "Waterjet cutter", "width_m": 4.0, "depth_m": 3.0},
    "waste_basket": {"category": "furniture", "label": "Waste basket", "width_m": 0.6, "depth_m": 0.6},
    "conveyor": {"category": "machine", "label": "Conveyor", "width_m": 6.0, "depth_m": 1.0},
    "curing_oven": {"category": "machine", "label": "Curing oven", "width_m": 1.2, "depth_m": 1.0},
    "powder_station": {"category": "equipment", "label": "Powder handling station", "width_m": 1.5, "depth_m": 1.0},
    "atm": {"category": "equipment", "label": "Atm", "width_m": 0.6, "depth_m": 0.6},
}


def normalise_type(text: str) -> str:
    return "_".join(text.strip().lower().replace("-", " ").split())


def catalog_entry(asset_type: str) -> tuple[str, dict]:
    """(canonical type, entry). A label such as 'CNC mill' works too. Unknown types list close names."""
    key = normalise_type(asset_type or "")
    if key in ASSET_CATALOG:
        return key, ASSET_CATALOG[key]
    for name, entry in ASSET_CATALOG.items():
        if normalise_type(entry["label"]) == key:
            return name, entry
    close = difflib.get_close_matches(key, list(ASSET_CATALOG), n=5, cutoff=0.5)
    hint = (
        "Close types: " + ", ".join(close) + "."
        if close
        else "Known types include: " + ", ".join(list(ASSET_CATALOG)[:12]) + "."
    )
    raise MapError(f"Unknown asset type '{asset_type}'. {hint} Ask the person which one they mean.")
