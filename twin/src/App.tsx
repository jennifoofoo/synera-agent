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
import { Round, RoundCard } from "./ui/Round";
import { SIDEBAR_MIN_WIDTH, Sidebar, SidebarExpand, useMinWidth, useSidebar } from "./ui/Sidebar";
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
  // Laptop: the chat is a column on the left (ui/Sidebar.tsx); phones and narrow windows keep the floating dock.
  const wide = useMinWidth(SIDEBAR_MIN_WIDTH);
  const collapsed = useSidebar((s) => s.collapsed);
  const sidebar = profile === "planner" && wide;
  const docked = sidebar && !collapsed;
  useEffect(() => {
    void loadBuildings();
  }, [loadBuildings]);
  useEffect(installHandsFree, []);
  return (
    <div
      className={`app ${profile} ${flat ? "flat" : "solid"} ${directionsOpen ? "directions-open" : ""} ${walking ? "walking" : ""}${docked ? " with-sidebar" : sidebar ? " sb-collapsed" : ""}`}
      style={{ "--top-inset": `${topInset}px`, "--bottom-inset": `${bottomInset}px`, "--right-inset": `${rightInset}px` } as React.CSSProperties}
    >
      {docked && (
        <Sidebar
          walking={walking}
          dock={
            <>
              <CampusCard />
              <NotesDock />
              <RoundCard />
              {walking ? <Walk /> : <Card />}
            </>
          }
        />
      )}
      <Scene />
      <Welcome />
      <CampusSite />
      {!docked && <TopBar />}
      <FloorRail />
      <Recenter />
      <ChangesPill />
      <Planner />
      <Round />
      <Phone />
      {!docked && (
        <div className="dock">
          <CampusCard />
          <NotesDock />
          <RoundCard />
          {/* While walking: the step sheet and only the Talk button (say "next" while walking). */}
          {walking ? <Walk /> : <Card />}
          <Omnibox walking={walking} />
        </div>
      )}
      {sidebar && collapsed && <SidebarExpand />}
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
