// Dev demo for "Walk with me" (twin/motion-demo.html, served by `npm run dev` only, not part of the build).
// Loads a route from /api/route, draws the current leg's floor and the estimated dot; window.__walkSim(2) walks it.
import { api } from "../api/client";
import type { Route } from "../api/types";
import { createWalkWithMe, legsFromRoute, requestMotionPermission, type MotionLeg, type Point, type WalkPosition } from "./index";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const canvas = $<HTMLCanvasElement>("plan");
const ctx = canvas.getContext("2d");
const info = $<HTMLDivElement>("info");
const walk = createWalkWithMe();
let legs: MotionLeg[] = [];
let route: Route | null = null;
const log: string[] = [];

function say(line: string): void {
  log.unshift(line);
  log.length = Math.min(log.length, 8);
}

walk.on("legEnded", (e) => say(`legEnded ${e.legIndex}: ${e.connector ? `${e.connector.name} (${e.connector.kind}), press Next` : e.end}`));
walk.on("arrived", () => say("arrived (estimated)"));
walk.on("status", (s) => say(`status: ${s}`));
walk.on("position", draw);

$<HTMLButtonElement>("load").onclick = async () => {
  const building = $<HTMLInputElement>("building").value.trim();
  const reply = await api.route(building, $<HTMLInputElement>("start").value.trim(), $<HTMLInputElement>("destination").value.trim());
  route = reply.route;
  if (!route.ok) {
    say(`no route: ${route.error ?? "?"}`);
    return draw(null);
  }
  legs = legsFromRoute(route);
  say(`route ${route.length_m} m, ${legs.length} legs`);
  walk.start(route);
  draw(walk.position());
};

$<HTMLButtonElement>("sensors").onclick = async () => {
  const status = await requestMotionPermission(); // inside the tap, as the UI must do on iOS
  say(`permission: ${status}`);
  if (route?.ok && (status === "ready" || status === "active")) walk.start(route);
};
$<HTMLButtonElement>("next").onclick = () => walk.next();
$<HTMLButtonElement>("confirm").onclick = () => walk.confirmLegEnd();
for (const button of document.querySelectorAll<HTMLButtonElement>("[data-sim]")) {
  button.onclick = () => window.__walkSim?.(Number(button.dataset.sim));
}

let view = { scale: 1, minX: 0, maxY: 0 };
canvas.onclick = (event) => {
  const p = walk.position();
  if (!p) return;
  const rect = canvas.getBoundingClientRect();
  const x = ((event.clientX - rect.left) * canvas.width) / rect.width;
  const y = ((event.clientY - rect.top) * canvas.height) / rect.height;
  const point: Point = [view.minX + (x - 20) / view.scale, view.maxY - (y - 20) / view.scale];
  walk.resetTo({ point, floorId: p.floorId }, { calibrate: true });
  say(`I'm here -> calibration ${walk.calibrationFactor().toFixed(2)}`);
};

function draw(p: WalkPosition | null): void {
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!p || !legs.length) {
    info.textContent = log.join("\n");
    return;
  }
  const floorLegs = legs.filter((leg) => leg.floorId === p.floorId);
  const all = floorLegs.flatMap((leg) => leg.points);
  const xs = all.map((q) => q[0]);
  const ys = all.map((q) => q[1]);
  const minX = Math.min(...xs);
  const maxY = Math.max(...ys);
  const span = Math.max(Math.max(...xs) - minX, maxY - Math.min(...ys), 1);
  view = { scale: Math.min(canvas.width - 40, canvas.height - 40) / span, minX, maxY };
  const toPx = (q: Point): [number, number] => [20 + (q[0] - minX) * view.scale, 20 + (maxY - q[1]) * view.scale];
  floorLegs.forEach((leg) => {
    ctx.strokeStyle = legs.indexOf(leg) === p.legIndex ? "#1f6feb" : "#aab";
    ctx.lineWidth = 4;
    ctx.beginPath();
    leg.points.forEach((q, i) => (i ? ctx.lineTo(...toPx(q)) : ctx.moveTo(...toPx(q))));
    ctx.stroke();
  });
  const [dx, dy] = toPx(p.point);
  ctx.fillStyle = p.offRoute ? "#d29922" : "#0969da";
  ctx.globalAlpha = 0.25;
  ctx.beginPath();
  ctx.arc(dx, dy, 18, 0, Math.PI * 2); // a halo: the dot is an estimate, not a fix
  ctx.fill();
  ctx.globalAlpha = 1;
  ctx.beginPath();
  ctx.arc(dx, dy, 6, 0, Math.PI * 2);
  ctx.fill();
  info.textContent = [
    `status ${walk.status()}  steps ${p.steps}  calibration ${walk.calibrationFactor().toFixed(2)}`,
    `leg ${p.legIndex + 1}/${p.legCount} on ${p.floorId}  about ${Math.round(p.distanceLeftM)} m left (estimated)`,
    `${p.atConnector ? "waiting at stairs/lift, press Next" : ""}${p.arrived ? "arrived (estimated)" : ""}${p.offRoute ? "  heading points away from the route" : ""}`,
    "",
    ...log,
  ].join("\n");
}
