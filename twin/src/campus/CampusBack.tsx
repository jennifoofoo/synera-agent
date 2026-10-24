// Next to the building name while a campus building is open: back to the site.

import { useCampus } from "./campusStore";

export function CampusBack() {
  const mode = useCampus((s) => s.mode);
  const name = useCampus((s) => s.view?.name);
  const backToSite = useCampus((s) => s.backToSite);
  if (mode !== "building") return null;
  return (
    <button className="campus-back" onClick={backToSite} title={`Back to ${name ?? "the site"}`} aria-label={`Back to ${name ?? "the site"}`}>
      <span aria-hidden>←</span> <span className="campus-back-name">{name ?? "Site"}</span>
    </button>
  );
}
