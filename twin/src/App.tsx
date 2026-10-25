import { useEffect } from "react";
import { CampusCard } from "./campus/CampusCard";
import { CampusSite } from "./campus/CampusSite";
import { Scene } from "./scene/Scene";
import { installHandsFree } from "./handsFree";
import { useTwin } from "./store";
import { Card } from "./ui/Card";
import { TiltHint } from "./ui/Compass";
import { ChangesPill } from "./ui/ChangesPill";
import { FloorRail } from "./ui/FloorRail";
import { KeyHelp } from "./ui/KeyHelp";
import { KnowledgeGraph } from "./ui/KnowledgeGraph";
import { NewBuilding } from "./ui/NewBuilding";
import { NotesButton, NotesDock } from "./ui/Facts";
import { Omnibox } from "./ui/Omnibox";
import { Recenter } from "./ui/Recenter";
import { TopBar } from "./ui/TopBar";
import { Phone } from "./ui/Phone";
import { Planner } from "./ui/Planner";
import { Round } from "./ui/Round";
import { Walk } from "./ui/Walk";
import { Welcome } from "./ui/Welcome";

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
  useEffect(installHandsFree, []);
  return (
    <div
      className={`app ${profile} ${flat ? "flat" : "solid"} ${directionsOpen ? "directions-open" : ""} ${walking ? "walking" : ""}`}
      style={{ "--top-inset": `${topInset}px`, "--bottom-inset": `${bottomInset}px`, "--right-inset": `${rightInset}px` } as React.CSSProperties}
    >
      <Scene />
      <Welcome />
      <CampusSite />
      <TopBar />
      <FloorRail />
      <Recenter />
      <ChangesPill />
      <Planner />
      <Round />
      <Phone />
      <div className="dock">
        <CampusCard />
        <NotesDock />
        {/* While walking: the step sheet and only the Talk button (say "next" while walking). */}
        {walking ? <Walk /> : <Card />}
        <Omnibox walking={walking} />
      </div>
      <NotesButton />
      <KnowledgeGraph />
      <NewBuilding />
      <KeyHelp />
      <TiltHint />
      {loading && <div className="overlay">Loading {building?.name ?? "building"}…</div>}
      {error && <div className="overlay error">{error}</div>}
    </div>
  );
}
