// The site view: covers the building scene while a campus is open and no building is entered.
// 2D = the site map, 3D = the buildings side by side; the toggle follows the twin's viewMode.

import { lazy, Suspense, useEffect } from "react";
import { useTwin } from "../store";
import "./Campus.css";
import { CampusMap2D } from "./CampusMap2D";
import { useCampus } from "./campusStore";

const CampusSite3D = lazy(() => import("./CampusSite3D").then((module) => ({ default: module.CampusSite3D })));

export function CampusSite() {
  const mode = useCampus((s) => s.mode);
  const view = useCampus((s) => s.view);
  const loadList = useCampus((s) => s.loadList);
  const viewMode = useTwin((s) => s.viewMode);
  const setViewMode = useTwin((s) => s.setViewMode);
  const site = mode === "site" && !!view?.loaded;

  useEffect(() => {
    void loadList();
  }, [loadList]);
  useEffect(() => {
    document.body.classList.toggle("campus-site-open", site);
    document.body.classList.toggle("campus-open", mode !== "off");
  }, [site, mode]);

  if (!site) return null;
  const flat = viewMode === "2d";
  return (
    <div className={`campus-site ${flat ? "flat" : "solid"}`}>
      {flat ? (
        <CampusMap2D />
      ) : (
        <Suspense fallback={null}>
          <CampusSite3D />
        </Suspense>
      )}
      <button className="campus-view-toggle" onClick={() => setViewMode(flat ? "3d" : "2d")} title={flat ? "Show the site in 3D" : "Show the site map"} aria-pressed={flat}>
        {flat ? "3D" : "2D"}
      </button>
    </div>
  );
}
