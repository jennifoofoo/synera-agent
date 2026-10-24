import { useEffect } from "react";
import { CampusCard } from "./campus/CampusCard";
import { CampusSite } from "./campus/CampusSite";
import { Scene } from "./scene/Scene";
import { useTwin } from "./store";
import { Card } from "./ui/Card";
import { ChangesPill } from "./ui/ChangesPill";
import { FloorRail } from "./ui/FloorRail";
import { KeyHelp } from "./ui/KeyHelp";
import { NewBuilding } from "./ui/NewBuilding";
import { Omnibox } from "./ui/Omnibox";
import { Recenter } from "./ui/Recenter";
import { TopBar } from "./ui/TopBar";
import { Phone } from "./ui/Phone";
import { Planner } from "./ui/Planner";
import { Walk } from "./ui/Walk";

/** One screen: the building, one input, one card. Everything else only when needed. */
export function App() {
  const loadBuildings = useTwin((s) => s.loadBuildings);
  const profile = useTwin((s) => s.profile);
  const building = useTwin((s) => s.building);
  const loading = useTwin((s) => s.loading);
  const error = useTwin((s) => s.error);
  const flat = useTwin((s) => s.viewMode === "2d");
  const topInset = useTwin((s) => s.topInset);
  const bottomInset = useTwin((s) => s.bottomInset);
  const rightInset = useTwin((s) => s.rightInset);
  const directionsOpen = useTwin((s) => s.directions !== null);
  const walking = useTwin((s) => s.walkStep !== null);
  useEffect(() => {
    void loadBuildings();
  }, [loadBuildings]);
  return (
    <div
      className={`app ${profile} ${flat ? "flat" : "solid"} ${directionsOpen ? "directions-open" : ""} ${walking ? "walking" : ""}`}
      style={{ "--top-inset": `${topInset}px`, "--bottom-inset": `${bottomInset}px`, "--right-inset": `${rightInset}px` } as React.CSSProperties}
    >
      <Scene />
      <CampusSite />
      <TopBar />
      <FloorRail />
      <Recenter />
      <ChangesPill />
      <Planner />
      <Phone />
      <div className="dock">
        <CampusCard />
        {/* While walking: the step sheet and only the Talk button (say "next" while walking). */}
        {walking ? <Walk /> : <Card />}
        <Omnibox walking={walking} />
      </div>
      <NewBuilding />
      <KeyHelp />
      {loading && <div className="overlay">Loading {building?.name ?? "building"}…</div>}
      {error && <div className="overlay error">{error}</div>}
    </div>
  );
}
