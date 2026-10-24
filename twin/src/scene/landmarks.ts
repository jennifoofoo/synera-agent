// Landmarks of the current directions: the things the spoken or written directions name ("past the CNC lathe").
// The server phrases them from the asset type (building_agent/directions.py: "cnc lathe"), so a thing counts as a
// landmark when it stands in a room on the route and its type words (or its name) appear in the directions text:
// the route's own steps plus the agent's last reply while a route is drawn. The 2D map always draws and labels
// them (scene/Things.tsx, scene/Labels.tsx), whatever the zoom.

import { useMemo } from "react";
import type { Asset } from "../api/types";
import { useTwin } from "../store";

const EMPTY: ReadonlySet<string> = new Set();

export function landmarkIds(assets: Iterable<Asset>, roomsOnRoute: ReadonlySet<string>, text: string): Set<string> {
  const lower = ` ${text.toLowerCase().replace(/[^a-z0-9äöüß]+/g, " ")} `;
  const out = new Set<string>();
  for (const asset of assets) {
    if (!roomsOnRoute.has(asset.space_id)) continue;
    const type = asset.type.toLowerCase().replace(/_/g, " ");
    const name = asset.name.toLowerCase().replace(/[^a-z0-9äöüß]+/g, " ").trim();
    if ((type.length > 2 && lower.includes(` ${type} `)) || (name.length > 2 && lower.includes(` ${name} `))) out.add(asset.id);
  }
  return out;
}

/** Ids of the things the current directions name; empty without a route. */
export function useLandmarks(): ReadonlySet<string> {
  const model = useTwin((s) => s.model);
  const route = useTwin((s) => s.state?.route ?? null);
  const chat = useTwin((s) => s.chat);
  return useMemo(() => {
    if (!model || !route?.ok) return EMPTY;
    const rooms = new Set(route.space_path ?? []);
    if (!rooms.size) return EMPTY;
    const reply = [...chat].reverse().find((message) => message.role === "agent");
    const text = [...(route.steps ?? []), reply?.text ?? ""].join(" ");
    const ids = landmarkIds(model.assetById.values(), rooms, text);
    return ids.size ? ids : EMPTY;
  }, [model, route, chat]);
}
