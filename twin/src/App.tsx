import { useEffect } from "react";
import { Scene } from "./scene/Scene";
import { useTwin } from "./store";
import { Card } from "./ui/Card";
import { ChangesPill } from "./ui/ChangesPill";
import { FloorRail } from "./ui/FloorRail";
import { NewBuilding } from "./ui/NewBuilding";
import { Omnibox } from "./ui/Omnibox";
import { Position } from "./ui/Position";
import { Recenter } from "./ui/Recenter";
import { TopBar } from "./ui/TopBar";
import { Phone } from "./ui/Phone";

/** One screen: the building, one input, one card. Everything else only when needed. */
export function App() {
  const loadBuildings = useTwin((s) => s.loadBuildings);
  const profile = useTwin((s) => s.profile);
  const building = useTwin((s) => s.building);
  const loading = useTwin((s) => s.loading);
  const error = useTwin((s) => s.error);
  const flat = useTwin((s) => s.viewMode === "2d");
  useEffect(() => {
    void loadBuildings();
  }, [loadBuildings]);
  return (
    <div className={`app ${profile} ${flat ? "flat" : "solid"}`}>
      <Scene />
      <TopBar />
      <FloorRail />
      <Recenter />
      <ChangesPill />
      <Phone />
      <Position />
      <div className="dock">
        <Card />
        <Omnibox />
      </div>
      <NewBuilding />
      {loading && <div className="overlay">Loading {building?.name ?? "building"}…</div>}
      {error && <div className="overlay error">{error}</div>}
    </div>
  );
}
