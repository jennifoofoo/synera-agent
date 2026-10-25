// How high a thing stands in 3D. The kit data has no heights at all (a footprint is width, depth and rotation), so
// every thing gets a default height by its type: low bodies that give the room scale (a desk at table height, a
// pallet a hand high), capped at about 1.2 m so tall storage never hides the room behind it (office walls are about
// 1.5 m in 3D). Machines keep their category height. Floor markings stay flat and are drawn apart from objects.

import type { Asset } from "../api/types";

/** Machines: the bodies people steer by. */
export const MACHINE_HEIGHT = 1.9;
/** Anything without its own entry. */
export const DEFAULT_HEIGHT = 0.3;
/** Floor markings: flat on the floor. */
export const MARKING_HEIGHT = 0.02;

/** Types that are markings on the floor, not objects (none in the kit data yet; a pallet place or a rug would be). */
export const FLOOR_MARKINGS = new Set(["floor_marking", "marking", "pallet_place", "parking_space", "rug", "carpet", "doormat"]);

const HEIGHTS: Record<string, number> = {
  // tables and work surfaces
  desk: 0.75,
  seminar_table: 0.75,
  meeting_table: 0.75,
  dining_table: 0.75,
  canteen_table: 0.75,
  reading_table: 0.75,
  outdoor_table: 0.75,
  lab_bench: 0.9,
  workbench: 0.9,
  assembly_station: 0.9,
  packing_station: 0.9,
  inspection_bench: 0.9,
  reception_desk: 1.0,
  kitchen_counter: 0.9,
  serving_counter: 0.9,
  coffee_table: 0.4,
  lectern: 1.1,
  // seats and beds
  chair: 0.45,
  office_chair: 0.45,
  dining_chair: 0.45,
  outdoor_chair: 0.45,
  armchair: 0.45,
  sofa: 0.45,
  bench: 0.45,
  lecture_seating_row: 0.8,
  bed: 0.5,
  single_bed: 0.5,
  nightstand: 0.5,
  tv_stand: 0.5,
  // storage (really taller; capped so the room stays readable)
  wardrobe: 1.2,
  built_in_wardrobe: 1.2,
  bookshelf: 1.2,
  shelf: 1.2,
  paper_shelf: 1.2,
  pallet_rack: 1.2,
  server_rack: 1.2,
  locker: 1.2,
  tool_cabinet: 1.0,
  chemical_cabinet: 1.0,
  filing_cabinet: 1.0,
  shoe_cabinet: 0.9,
  coat_rack: 1.2,
  // sanitary
  toilet: 0.4,
  sink: 0.85,
  bathtub: 0.55,
  shower: 0.1,
  // appliances and equipment
  fridge: 1.2,
  stove: 0.9,
  dishwasher: 0.85,
  washing_machine: 0.85,
  vending_machine: 1.2,
  water_dispenser: 1.0,
  atm: 1.2,
  fume_hood: 1.2,
  electrical_panel: 1.2,
  ups_unit: 1.0,
  whiteboard: 1.2,
  projector_screen: 1.2,
  display_screen: 1.2,
  multifunction_printer: 1.0,
  printer: 0.5,
  fire_extinguisher: 0.6,
  eyewash_station: 1.0,
  forklift_charging_station: 1.0,
  welding_station: 0.9,
  soldering_station: 0.9,
  oscilloscope_station: 0.9,
  powder_station: 1.0,
  internal_stairs: 0.6,
  plant: 0.6,
  waste_basket: 0.4,
  pallet: 0.15,
  pallet_jack: 0.15,
};

export function isFloorMarking(asset: Pick<Asset, "type">): boolean {
  return FLOOR_MARKINGS.has(asset.type);
}

/** Height in metres of a thing's body in 3D. */
export function assetHeight(asset: Pick<Asset, "type" | "category">): number {
  if (FLOOR_MARKINGS.has(asset.type)) return MARKING_HEIGHT;
  if (asset.category === "machine") return MACHINE_HEIGHT;
  return HEIGHTS[asset.type] ?? DEFAULT_HEIGHT;
}
