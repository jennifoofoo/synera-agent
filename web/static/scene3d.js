// 3D renderer for the building page: rooms as low extruded walls on floor slabs, doors as gaps, stairs and lifts
// as shafts, things as true-size boxes, the route as a glowing tube. It only draws what it is given; the state
// (which floor, which mode, what is highlighted) lives in view3d.js, so the agent can steer it without touching this.
// Plan coordinates (x, y) in metres map to three.js as (x, height, -y).
import * as THREE from "three";
import { OrbitControls } from "three/addons/OrbitControls.js";

const TYPE_COLOURS = {
  room: 0xf4f1ea,
  corridor: 0xdcd7cc,
  hall: 0xe9dfc8,
  stair: 0xb3bee6,
  lift: 0x9ed5dd,
  outdoor: 0xcfe2bd,
};
const PRODUCTION_TYPES = new Set(["production_zone", "assembly_zone", "additive_zone"]);
const LOGISTICS_TYPES = new Set(["warehouse_zone", "logistics_zone"]);
const ROOM_TYPE_COLOURS = { quality_lab: 0xe3ecf6, lab: 0xe3ecf6, toilet: 0xe6f0f1, bathroom: 0xe6f0f1, server_room: 0xe4e2ef, technical_room: 0xe4e2ef };
const ASSET_COLOURS = { machine: 0xe07b24, equipment: 0x4f6b8a, fixture: 0x9a968c, furniture: 0xb8a68a };
const ASSET_HEIGHTS = { machine: 2.0, equipment: 1.3, fixture: 1.0, furniture: 0.75 };
const COLOURS = {
  wall: 0xe9e5dc, wallTop: 0x6f6a60, floorLine: 0x8b877e, background: 0xecebe6,
  route: 0x2563eb, routeGlow: 0x60a5fa, closed: 0xdc2626, added: 0x059669, entrance: 0x0e7490, step: 0xea8a00,
  lift: 0x0e7490, stairs: 0x4f5fa3, start: 0x16a34a, end: 0xdc2626, suspect: 0xdc2626,
};
const ROUTE_LIFT_M = 0.45; // route line height above the floor slab
const DOOR_SNAP_M = 0.45; // an opening this close to a wall edge cuts a gap into it
const ANIM_MIN_MS = 3000;
const ANIM_MAX_MS = 11000;

export function spaceColour(space) {
  if (PRODUCTION_TYPES.has(space.room_type)) return 0xf1cd8c;
  if (LOGISTICS_TYPES.has(space.room_type)) return 0xd6dcc4;
  if (space.type === "room" && ROOM_TYPE_COLOURS[space.room_type]) return ROOM_TYPE_COLOURS[space.room_type];
  return TYPE_COLOURS[space.type] ?? TYPE_COLOURS.room;
}

const easeInOut = (t) => 0.5 - Math.cos(Math.PI * Math.min(1, Math.max(0, t))) / 2;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

function ringOf(polygon) {
  const pts = polygon.map(([x, y]) => [x, y]);
  if (pts.length > 1) {
    const [a, b] = [pts[0], pts[pts.length - 1]];
    if (a[0] === b[0] && a[1] === b[1]) pts.pop();
  }
  return pts;
}

function bboxOf(points, box = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity }) {
  for (const [x, y] of points) {
    box.minX = Math.min(box.minX, x); box.maxX = Math.max(box.maxX, x);
    box.minY = Math.min(box.minY, y); box.maxY = Math.max(box.maxY, y);
  }
  return box;
}

// Triangles of a plan polygon (indices into the ring), robust to either winding.
function triangulate(ring) {
  const contour = ring.map(([x, y]) => new THREE.Vector2(x, y));
  try {
    return THREE.ShapeUtils.triangulateShape(contour, []);
  } catch {
    return [];
  }
}

// Closest point of segment a-b to p: {t in metres along the edge, distance}.
function projectOnEdge(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1e-9;
  const t = clamp(((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len, 0, len);
  const qx = a[0] + (dx * t) / len, qy = a[1] + (dy * t) / len;
  return { t, len, distance: Math.hypot(p[0] - qx, p[1] - qy), dir: [dx / len, dy / len] };
}

class GeometryBuilder {
  constructor(withColour = true) {
    this.positions = []; this.normals = []; this.colours = withColour ? [] : null; this.indices = [];
  }
  get vertexCount() { return this.positions.length / 3; }
  vertex(x, y, z, nx, ny, nz, colour) {
    this.positions.push(x, y, z);
    this.normals.push(nx, ny, nz);
    if (this.colours) this.colours.push(colour.r, colour.g, colour.b);
  }
  quad(a, b, y0, y1, colour) {
    // vertical wall quad over plan edge a-b
    const nx = b[1] - a[1], nz = b[0] - a[0];
    const n = Math.hypot(nx, nz) || 1;
    const base = this.vertexCount;
    for (const [p, y] of [[a, y0], [b, y0], [b, y1], [a, y1]]) this.vertex(p[0], y, -p[1], nx / n, 0, nz / n, colour);
    this.indices.push(base, base + 1, base + 2, base, base + 2, base + 3);
  }
  build() {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(this.positions, 3));
    g.setAttribute("normal", new THREE.Float32BufferAttribute(this.normals, 3));
    if (this.colours) g.setAttribute("color", new THREE.Float32BufferAttribute(this.colours, 3));
    g.setIndex(this.indices);
    g.computeBoundingSphere();
    return g;
  }
}

function lineGeometry(points) {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
  g.computeBoundingSphere();
  return g;
}

// Translucent coloured prisms over spaces (closures, highlights, suspect rooms) plus a solid outline on top.
function prismObject(rings, height, colour, opacity) {
  const body = new GeometryBuilder(false);
  const lines = [];
  for (const ring of rings) {
    const base = body.vertexCount;
    for (const [x, y] of ring) body.vertex(x, height, -y, 0, 1, 0);
    for (const [a, b, c] of triangulate(ring)) body.indices.push(base + a, base + b, base + c);
    ring.forEach((a, i) => {
      const b = ring[(i + 1) % ring.length];
      body.quad(a, b, 0.03, height);
      lines.push(a[0], height, -a[1], b[0], height, -b[1]);
    });
  }
  const group = new THREE.Group();
  const material = new THREE.MeshBasicMaterial({ color: colour, transparent: true, opacity, side: THREE.DoubleSide, depthWrite: false });
  const mesh = new THREE.Mesh(body.build(), material);
  mesh.renderOrder = 3;
  group.add(mesh);
  const outline = new THREE.LineSegments(lineGeometry(lines), new THREE.LineBasicMaterial({ color: colour }));
  outline.renderOrder = 4;
  group.add(outline);
  group.userData.baseOpacity = opacity;
  group.userData.material = material;
  return group;
}

export class Scene3D {
  constructor(container, handlers = {}) {
    this.container = container;
    this.handlers = handlers; // {onSpaceClick(event, id), onOpeningClick(event, id), onEmptyClick(), onCaption(text)}
    this.reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setClearColor(COLOURS.background);
    this.renderer.domElement.className = "view3d-canvas";
    container.appendChild(this.renderer.domElement);
    this.tooltip = document.createElement("div");
    this.tooltip.className = "view3d-tooltip";
    this.tooltip.hidden = true;
    container.appendChild(this.tooltip);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.1, 5000);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = !this.reducedMotion.matches;
    this.controls.dampingFactor = 0.12;
    this.controls.screenSpacePanning = false; // pan along the floor, like a map
    this.controls.maxPolarAngle = Math.PI * 0.49;
    this.controls.addEventListener("change", () => this.requestRender());
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0xb8b2a6, 2.0));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(0.4, 1, 0.25);
    this.scene.add(sun);

    this.root = new THREE.Group();
    this.scene.add(this.root);
    this.shaftGroup = new THREE.Group();
    this.routeGroup = new THREE.Group();
    this.scene.add(this.shaftGroup, this.routeGroup);

    this.building = null;
    this.floors = new Map(); // floorId -> {floor, group, built, parts..., box, spaces: []}
    this.layout = { mode: "stacked", focus: null, things: "auto" };
    this.stateData = { closed: new Set(), added: [], suspectSpaces: new Set(), suspectOpenings: new Set() };
    this.highlights = new Map();
    this.route = null;
    this.routeAnim = null;
    this.flight = null;
    this.floorTween = null;
    this.dirty = true;
    this.labelsDirty = true;
    this.stats = { build_ms: 0, floors_built: 0, frames: 0, fps: 0, last_fps_at: performance.now(), frames_since: 0 };
    this.running = false;
    this.raycaster = new THREE.Raycaster();
    this.pointer = { down: null, hoverAt: 0 };
    this.wireInput();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.resize();
  }

  // ---------- lifecycle ----------

  start() {
    if (this.running) return;
    this.running = true;
    this.resize();
    const loop = (now) => {
      if (!this.running) return;
      this.frame = requestAnimationFrame(loop);
      this.beforeFrame?.(now);
      this.tick(now);
    };
    this.frame = requestAnimationFrame(loop);
  }

  stop() {
    this.running = false;
    cancelAnimationFrame(this.frame);
  }

  resize() {
    const w = Math.max(1, this.container.clientWidth), h = Math.max(1, this.container.clientHeight);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.requestRender();
  }

  requestRender() {
    this.dirty = true;
    this.labelsDirty = true;
  }

  // ---------- building ----------

  setBuilding(building, focus = null) {
    if (focus) this.layout.focus = focus;
    this.cancelBuild();
    this.clearGroup(this.root);
    this.floors.clear();
    this.building = building;
    this.connectorBySpace = null;
    this.spaces = new Map(building.spaces.map((s) => [s.id, s]));
    this.assets = new Map(building.assets.map((a) => [a.id, a]));
    this.openings = new Map(building.openings.map((o) => [o.id, o]));
    this.connectors = new Map(building.connectors.map((c) => [c.id, c]));
    const ordered = [...building.floors].sort((a, b) => a.level - b.level);
    const all = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
    ordered.forEach((floor, index) => {
      const height = floor.height_m || 3;
      const record = {
        floor, index, built: false, group: new THREE.Group(), spaces: [], openings: [], assets: [],
        elevation: floor.elevation_m ?? floor.level * height, height, wallHeight: clamp(height * 0.42, 1.1, 3.2),
        box: { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity }, y: 0, targetY: 0,
      };
      record.group.userData.floorId = floor.id;
      this.floors.set(floor.id, record);
      this.root.add(record.group);
    });
    for (const s of building.spaces) {
      const record = this.floors.get(s.floor_id);
      if (!record) continue;
      record.spaces.push(s);
      bboxOf(s.polygon, record.box);
      bboxOf(s.polygon, all);
    }
    for (const o of building.openings) this.floors.get(o.floor_id)?.openings.push(o);
    for (const a of building.assets) this.floors.get(a.floor_id)?.assets.push(a);
    if (!this.floors.has(this.layout.focus)) this.layout.focus = (ordered.find((f) => f.level === 0) || ordered[0])?.id ?? null;
    this.box = all;
    this.size = Math.max(10, Math.hypot(all.maxX - all.minX, all.maxY - all.minY));
    this.camera.near = clamp(this.size / 2000, 0.05, 1);
    this.camera.far = this.size * 30;
    this.camera.updateProjectionMatrix();
    this.controls.maxDistance = this.size * 6;
    this.controls.minDistance = 2;
    this.stats.build_ms = 0;
    this.stats.floors_built = 0;
    this.applyLayout(true);
    this.scheduleBuild();
    this.route = null;
    this.rebuildRoute();
    this.requestRender();
  }

  // Focused floor first, the rest one per idle slice, so the first picture comes fast on big buildings.
  scheduleBuild() {
    const order = [...this.floors.values()].sort((a, b) => {
      const fa = a.floor.id === this.layout.focus ? -1 : 0, fb = b.floor.id === this.layout.focus ? -1 : 0;
      return fa - fb || Math.abs(a.index) - Math.abs(b.index);
    });
    const step = () => {
      const next = order.find((record) => !record.built && this.floorVisible(record));
      if (!next) { this.buildTimer = null; return; }
      this.buildFloor(next);
      this.buildTimer = setTimeout(step, 0);
    };
    const focus = this.floors.get(this.layout.focus);
    if (focus && !focus.built) this.buildFloor(focus);
    this.buildTimer = setTimeout(step, 0);
  }

  cancelBuild() {
    clearTimeout(this.buildTimer);
    this.buildTimer = null;
  }

  ensureBuilt(record) {
    if (record && !record.built) this.buildFloor(record);
  }

  buildFloor(record) {
    const t0 = performance.now();
    const { group, wallHeight } = record;
    const doorsBySpace = new Map();
    for (const o of record.openings) {
      for (const sid of o.space_ids) {
        if (!doorsBySpace.has(sid)) doorsBySpace.set(sid, []);
        doorsBySpace.get(sid).push(o);
      }
    }
    const slab = new GeometryBuilder();
    const walls = new GeometryBuilder(false);
    const topLines = [], floorLines = [];
    const triStarts = [], triSpaces = [];
    const colour = new THREE.Color();
    for (const s of record.spaces) {
      const ring = ringOf(s.polygon);
      if (ring.length < 3) continue;
      colour.setHex(spaceColour(s));
      const base = slab.vertexCount;
      for (const [x, y] of ring) slab.vertex(x, 0, -y, 0, 1, 0, colour);
      triStarts.push(slab.indices.length / 3);
      triSpaces.push(s.id);
      for (const [a, b, c] of triangulate(ring)) slab.indices.push(base + a, base + b, base + c);
      if (s.type === "outdoor") {
        ring.forEach((a, i) => { const b = ring[(i + 1) % ring.length]; floorLines.push(a[0], 0.02, -a[1], b[0], 0.02, -b[1]); });
        continue; // outdoor areas get no walls
      }
      const doors = doorsBySpace.get(s.id) || [];
      ring.forEach((a, i) => {
        const b = ring[(i + 1) % ring.length];
        floorLines.push(a[0], 0.02, -a[1], b[0], 0.02, -b[1]);
        const gaps = [];
        let len = Math.hypot(b[0] - a[0], b[1] - a[1]);
        for (const o of doors) {
          const hit = projectOnEdge(o.position, a, b);
          len = hit.len;
          if (hit.distance <= DOOR_SNAP_M) {
            const half = (o.width_m || 0.9) / 2;
            gaps.push([hit.t - half, hit.t + half]);
          }
        }
        gaps.sort((p, q) => p[0] - q[0]);
        let from = 0;
        const pieces = [];
        for (const [g0, g1] of gaps) {
          if (g0 > from + 0.02) pieces.push([from, Math.min(g0, len)]);
          from = Math.max(from, g1);
        }
        if (from < len - 0.02) pieces.push([from, len]);
        const dx = (b[0] - a[0]) / (len || 1), dy = (b[1] - a[1]) / (len || 1);
        for (const [t0, t1] of pieces) {
          if (t1 - t0 < 0.02) continue;
          const p = [a[0] + dx * t0, a[1] + dy * t0], q = [a[0] + dx * t1, a[1] + dy * t1];
          walls.quad(p, q, 0, wallHeight);
          topLines.push(p[0], wallHeight, -p[1], q[0], wallHeight, -q[1]);
        }
      });
    }
    record.triStarts = triStarts;
    record.triSpaces = triSpaces;

    record.slabMaterial = new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
    record.slab = new THREE.Mesh(slab.build(), record.slabMaterial);
    record.slab.userData = { kind: "slab", record };
    record.wallMaterial = new THREE.MeshLambertMaterial({ color: COLOURS.wall, side: THREE.DoubleSide });
    record.walls = new THREE.Mesh(walls.build(), record.wallMaterial);
    record.topLineMaterial = new THREE.LineBasicMaterial({ color: COLOURS.wallTop });
    record.topLines = new THREE.LineSegments(lineGeometry(topLines), record.topLineMaterial);
    record.floorLineMaterial = new THREE.LineBasicMaterial({ color: COLOURS.floorLine, transparent: true, opacity: 0.9 });
    record.floorLines = new THREE.LineSegments(lineGeometry(floorLines), record.floorLineMaterial);
    group.add(record.slab, record.walls, record.topLines, record.floorLines);

    record.doorMarkers = this.buildDoorMarkers(record, record.openings.filter((o) => o.kind === "entrance" || !o.step_free), false);
    if (record.doorMarkers) group.add(record.doorMarkers);
    record.stateGroup = new THREE.Group();
    group.add(record.stateGroup);
    record.built = true;
    this.stats.floors_built += 1;
    this.stats.build_ms += performance.now() - t0;
    this.refreshFloorState(record);
    this.applyFloorLook(record);
    this.requestRender();
  }

  // Assets are built only when needed (focused floor, or zoomed in), one InstancedMesh per floor.
  buildAssets(record) {
    const t0 = performance.now();
    const items = record.assets;
    const geometry = new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0);
    const material = new THREE.MeshLambertMaterial();
    const mesh = new THREE.InstancedMesh(geometry, material, Math.max(1, items.length));
    mesh.count = items.length;
    const matrix = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0), colour = new THREE.Color();
    const maxHeight = record.wallHeight * 1.15;
    items.forEach((a, i) => {
      const fp = a.footprint || { width_m: 0.5, depth_m: 0.5, rotation_deg: 0 };
      const height = Math.min(ASSET_HEIGHTS[a.category] ?? 0.8, maxHeight);
      q.setFromAxisAngle(up, ((fp.rotation_deg || 0) * Math.PI) / 180);
      matrix.compose(new THREE.Vector3(a.position[0], 0.01, -a.position[1]), q, new THREE.Vector3(Math.max(0.15, fp.width_m), height, Math.max(0.15, fp.depth_m)));
      mesh.setMatrixAt(i, matrix);
      mesh.setColorAt(i, colour.setHex(ASSET_COLOURS[a.category] ?? ASSET_COLOURS.furniture));
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingSphere();
    mesh.userData = { kind: "assets", record, ids: items.map((a) => a.id) };
    record.assetMesh = mesh;
    record.group.add(mesh);
    this.stats.build_ms += performance.now() - t0;
  }

  // Short coloured posts in door gaps: entrances, doors with a step, new doors, closed doors.
  buildDoorMarkers(record, openings, stateful) {
    if (!openings.length) return null;
    const geometry = new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0);
    const material = new THREE.MeshLambertMaterial({ transparent: stateful, opacity: stateful ? 0.85 : 1 });
    const mesh = new THREE.InstancedMesh(geometry, material, openings.length);
    const matrix = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0), colour = new THREE.Color();
    openings.forEach((o, i) => {
      const angle = this.doorAngle(o);
      q.setFromAxisAngle(up, angle);
      const closed = this.stateData.closed.has(o.id);
      const width = o.width_m || 0.9;
      let height = 0.12, thickness = 0.5, hex = o.kind === "entrance" ? COLOURS.entrance : COLOURS.step;
      if (stateful) {
        hex = closed ? COLOURS.closed : this.stateData.suspectOpenings.has(o.id) ? COLOURS.suspect : COLOURS.added;
        height = record.wallHeight;
        thickness = closed ? 0.25 : 0.35;
      } else if (o.kind === "entrance") {
        height = 0.35;
      }
      matrix.compose(new THREE.Vector3(o.position[0], 0, -o.position[1]), q, new THREE.Vector3(width, height, thickness));
      mesh.setMatrixAt(i, matrix);
      mesh.setColorAt(i, colour.setHex(hex));
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingSphere();
    mesh.userData = { kind: "doors", record, ids: openings.map((o) => o.id) };
    return mesh;
  }

  // Orientation of a door in its wall: the nearest polygon edge of the spaces it joins.
  doorAngle(o) {
    let best = null;
    for (const sid of o.space_ids) {
      const s = this.spaces.get(sid);
      if (!s) continue;
      const ring = ringOf(s.polygon);
      ring.forEach((a, i) => {
        const hit = projectOnEdge(o.position, a, ring[(i + 1) % ring.length]);
        if (!best || hit.distance < best.distance) best = hit;
      });
    }
    return best ? Math.atan2(best.dir[1], best.dir[0]) : 0;
  }

  // ---------- state: closures, new doors, draft findings, highlights ----------

  setState({ closed = [], added = [], suspectSpaces = [], suspectOpenings = [] } = {}) {
    this.stateData = { closed: new Set(closed), added, suspectSpaces: new Set(suspectSpaces), suspectOpenings: new Set(suspectOpenings) };
    for (const door of added) {
      if (!this.openings.has(door.id)) {
        const opening = { kind: "door", width_m: 0.9, ...door, added: true };
        this.openings.set(door.id, opening);
        this.floors.get(door.floor_id)?.openings.push(opening);
      }
    }
    for (const record of this.floors.values()) if (record.built) this.refreshFloorState(record);
    this.rebuildShafts();
    this.requestRender();
  }

  refreshFloorState(record) {
    this.clearGroup(record.stateGroup);
    const { closed, suspectSpaces, suspectOpenings } = this.stateData;
    const h = record.wallHeight + 0.04;
    const closedRings = [], suspectRings = [];
    for (const s of record.spaces) {
      const connector = this.connectorOfSpace(s.id);
      if (closed.has(s.id) || (connector && closed.has(connector.id))) closedRings.push(ringOf(s.polygon));
      else if (suspectSpaces.has(s.id)) suspectRings.push(ringOf(s.polygon));
    }
    if (closedRings.length) record.stateGroup.add(prismObject(closedRings, h, COLOURS.closed, 0.32));
    if (suspectRings.length) record.stateGroup.add(prismObject(suspectRings, h, COLOURS.suspect, 0.22));
    const marked = record.openings.filter((o) => closed.has(o.id) || o.added || suspectOpenings.has(o.id));
    const doors = this.buildDoorMarkers(record, marked, true);
    if (doors) record.stateGroup.add(doors);
    for (const [name, item] of this.highlights) {
      const rings = item.spaceIds.filter((id) => this.spaces.get(id)?.floor_id === record.floor.id).map((id) => ringOf(this.spaces.get(id).polygon));
      if (rings.length) {
        const prism = prismObject(rings, h + 0.06, item.colour, 0.38);
        prism.userData.pulse = true;
        prism.name = `highlight:${name}`;
        record.stateGroup.add(prism);
      }
      const boxes = item.assetIds.map((id) => this.assets.get(id)).filter((a) => a && a.floor_id === record.floor.id);
      for (const a of boxes) record.stateGroup.add(this.assetHalo(a, item.colour, record));
      const points = item.points.filter((p) => p.floor_id === record.floor.id);
      for (const p of points) record.stateGroup.add(this.pointHalo(p.point, item.colour, record));
    }
  }

  connectorOfSpace(spaceId) {
    if (!this.connectorBySpace) {
      this.connectorBySpace = new Map();
      for (const c of this.connectors.values()) for (const sid of c.space_ids) this.connectorBySpace.set(sid, c);
    }
    return this.connectorBySpace.get(spaceId);
  }

  assetHalo(a, colour, record) {
    const fp = a.footprint || { width_m: 0.5, depth_m: 0.5, rotation_deg: 0 };
    const height = Math.min(ASSET_HEIGHTS[a.category] ?? 0.8, record.wallHeight * 1.15) + 0.3;
    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(fp.width_m + 0.5, height, fp.depth_m + 0.5).translate(0, height / 2, 0),
      new THREE.MeshBasicMaterial({ color: colour, transparent: true, opacity: 0.45, depthWrite: false }),
    );
    mesh.position.set(a.position[0], 0, -a.position[1]);
    mesh.rotation.y = ((fp.rotation_deg || 0) * Math.PI) / 180;
    mesh.userData.pulse = true;
    mesh.userData.baseOpacity = 0.45;
    mesh.userData.material = mesh.material;
    mesh.renderOrder = 5;
    return mesh;
  }

  pointHalo(point, colour, record) {
    const mesh = new THREE.Mesh(
      new THREE.CylinderGeometry(0.9, 0.9, record.wallHeight + 0.6, 24, 1, true).translate(0, (record.wallHeight + 0.6) / 2, 0),
      new THREE.MeshBasicMaterial({ color: colour, transparent: true, opacity: 0.4, depthWrite: false, side: THREE.DoubleSide }),
    );
    mesh.position.set(point[0], 0, -point[1]);
    mesh.userData.pulse = true;
    mesh.userData.baseOpacity = 0.4;
    mesh.userData.material = mesh.material;
    mesh.renderOrder = 5;
    return mesh;
  }

  // highlights: Map name -> {spaceIds, assetIds, connectorIds, openingIds, points: [{floor_id, point}], colour}
  setHighlights(highlights) {
    this.highlights = highlights;
    for (const record of this.floors.values()) if (record.built) this.refreshFloorState(record);
    this.rebuildShafts();
    this.requestRender();
  }

  // ---------- floors: stacked, exploded, single ----------

  setLayout({ mode, focus, things }) {
    const changedFocus = focus !== undefined && focus !== this.layout.focus;
    if (mode) this.layout.mode = mode;
    if (focus !== undefined && this.floors.has(focus)) this.layout.focus = focus;
    if (things) this.layout.things = things;
    this.applyLayout(false);
    if (changedFocus) this.ensureBuilt(this.floors.get(this.layout.focus));
    if (this.buildTimer === null && [...this.floors.values()].some((r) => !r.built && this.floorVisible(r))) this.scheduleBuild();
    this.requestRender();
  }

  explodeGap() {
    return clamp(this.size * 0.14, 6, 40);
  }

  floorY(record, mode = this.layout.mode) {
    return mode === "exploded" ? record.elevation + record.index * this.explodeGap() : record.elevation;
  }

  floorVisible(record) {
    return this.layout.mode !== "single" || record.floor.id === this.layout.focus;
  }

  // Upper floors are x-ray ghosts in stacked mode, so the focused floor and the route below stay readable.
  isGhost(record) {
    if (this.layout.mode !== "stacked") return false;
    const focus = this.floors.get(this.layout.focus);
    return focus ? record.floor.level > focus.floor.level : false;
  }

  applyLayout(instant) {
    const animate = !instant && !this.reducedMotion.matches;
    for (const record of this.floors.values()) {
      record.targetY = this.floorY(record);
      if (!animate) { record.y = record.targetY; record.group.position.y = record.y; }
      this.applyFloorLook(record);
    }
    if (animate) {
      this.floorTween = { t0: performance.now(), duration: 550, from: new Map([...this.floors.values()].map((r) => [r.floor.id, r.group.position.y])) };
      this.shaftGroup.visible = false;
      this.routeGroup.visible = false;
    } else {
      this.floorTween = null;
      this.rebuildShafts();
      this.rebuildRoute();
    }
  }

  applyFloorLook(record) {
    const visible = this.floorVisible(record);
    record.group.visible = visible;
    if (!record.built) return;
    const ghost = this.isGhost(record);
    const focused = record.floor.id === this.layout.focus;
    const dim = this.layout.mode === "exploded" && !focused;
    record.slabMaterial.transparent = ghost;
    record.slabMaterial.opacity = ghost ? 0.07 : 1;
    record.slabMaterial.depthWrite = !ghost;
    record.wallMaterial.transparent = ghost || dim;
    record.wallMaterial.opacity = ghost ? 0.05 : dim ? 0.75 : 1;
    record.wallMaterial.depthWrite = !ghost;
    record.walls.visible = !ghost;
    record.topLines.visible = !ghost;
    record.floorLineMaterial.opacity = ghost ? 0.35 : 0.9;
    if (record.doorMarkers) record.doorMarkers.visible = !ghost;
    record.slab.renderOrder = ghost ? 2 : 0;
    record.floorLines.renderOrder = ghost ? 2 : 0;
    record.ghost = ghost;
    this.updateAssetVisibility(record);
  }

  wantsAssets(record) {
    if (!this.floorVisible(record) || record.ghost || !record.assets.length || this.layout.things === "off") return false;
    if (this.layout.things === "on") return true;
    if (record.floor.id === this.layout.focus && record.assets.length <= 2500) return true;
    // Zoomed in on this floor: the camera target is over it and close.
    const distance = this.camera.position.distanceTo(this.controls.target);
    const box = record.box;
    const t = this.controls.target;
    const over = t.x >= box.minX - 5 && t.x <= box.maxX + 5 && -t.z >= box.minY - 5 && -t.z <= box.maxY + 5;
    const near = Math.abs(t.y - record.y) < record.height * 2;
    return over && near && distance < Math.max(40, this.size * 0.35);
  }

  updateAssetVisibility(record) {
    if (!record.built) return;
    const want = this.wantsAssets(record);
    if (want && !record.assetMesh) this.buildAssets(record);
    if (record.assetMesh) record.assetMesh.visible = want;
  }

  // ---------- stairs and lifts ----------

  rebuildShafts() {
    this.clearGroup(this.shaftGroup);
    if (!this.building) return;
    const geometry = new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0);
    const byColour = new Map();
    const highlighted = new Map();
    for (const [, item] of this.highlights) for (const id of item.connectorIds) highlighted.set(id, item.colour);
    for (const c of this.connectors.values()) {
      const stops = c.floor_ids.map((fid, i) => ({ record: this.floors.get(fid), space: this.spaces.get(c.space_ids[i]) })).filter((s) => s.record && s.space);
      stops.sort((a, b) => a.record.floor.level - b.record.floor.level);
      const colour = this.stateData.closed.has(c.id) ? COLOURS.closed : highlighted.get(c.id) ?? (c.kind === "lift" ? COLOURS.lift : COLOURS.stairs);
      for (let i = 0; i + 1 < stops.length; i++) {
        const [a, b] = [stops[i], stops[i + 1]];
        if (!this.floorVisible(a.record) || !this.floorVisible(b.record)) continue;
        const box = bboxOf(a.space.polygon);
        const w = clamp(box.maxX - box.minX, 0.8, 5) * 0.8, d = clamp(box.maxY - box.minY, 0.8, 5) * 0.8;
        const [cx, cy] = a.space.anchor;
        const y0 = a.record.targetY + 0.05, y1 = b.record.targetY;
        if (!byColour.has(colour)) byColour.set(colour, []);
        byColour.get(colour).push({ cx, cy, w, d, y0, y1 });
      }
    }
    const matrix = new THREE.Matrix4(), q = new THREE.Quaternion();
    for (const [colour, items] of byColour) {
      const mesh = new THREE.InstancedMesh(geometry, new THREE.MeshLambertMaterial({ color: colour, transparent: true, opacity: 0.4, depthWrite: false }), items.length);
      items.forEach((it, i) => {
        matrix.compose(new THREE.Vector3(it.cx, it.y0, -it.cy), q, new THREE.Vector3(it.w, Math.max(0.1, it.y1 - it.y0), it.d));
        mesh.setMatrixAt(i, matrix);
      });
      mesh.renderOrder = 1;
      this.shaftGroup.add(mesh);
    }
    this.shaftGroup.visible = true;
  }

  // ---------- route ----------

  setRoute(route) {
    this.route = route?.ok ? route : null;
    this.stopRouteAnimation();
    this.rebuildRoute();
    this.requestRender();
  }

  // The route as one 3D path: walking segments on their floor, vertical runs where it takes stairs or a lift.
  routePath() {
    const route = this.route;
    if (!route) return null;
    const pts = [];
    const marks = []; // {at: index of first point of a floor, floor_id, caption}
    let lastFloor = null;
    const yOf = (fid) => (this.floors.get(fid)?.targetY ?? 0) + ROUTE_LIFT_M;
    for (const segment of route.segments) {
      if (!segment.points.length) continue;
      const fid = segment.floor_id;
      if (lastFloor && lastFloor !== fid) {
        const change = route.floor_changes.find((c) => c.from_floor === lastFloor && c.to_floor === fid);
        const from = change ? change.from_point : pts[pts.length - 1].plan;
        const toY = yOf(fid);
        pts.push({ v: new THREE.Vector3(from[0], toY, -from[1]), plan: from, floor: fid });
        marks.push({ at: pts.length - 1, floor_id: fid, caption: change ? `${change.name}: ${change.kind === "lift" ? "ride" : "walk"} ${change.direction} to ${this.floors.get(fid)?.floor.name ?? fid}` : "" });
      } else if (!lastFloor) {
        marks.push({ at: 0, floor_id: fid, caption: "" });
      }
      for (const p of segment.points) {
        const prev = pts[pts.length - 1];
        if (prev && prev.floor === fid && prev.plan[0] === p[0] && prev.plan[1] === p[1]) continue;
        pts.push({ v: new THREE.Vector3(p[0], yOf(fid), -p[1]), plan: p, floor: fid });
      }
      lastFloor = fid;
    }
    if (pts.length < 2) return null;
    const path = new THREE.CurvePath();
    const lengths = [0];
    for (let i = 1; i < pts.length; i++) {
      path.add(new THREE.LineCurve3(pts[i - 1].v, pts[i].v));
      lengths.push(lengths[i - 1] + pts[i - 1].v.distanceTo(pts[i].v));
    }
    const total = lengths[lengths.length - 1] || 1;
    for (const m of marks) m.t = lengths[m.at] / total;
    return { path, points: pts, total, marks };
  }

  rebuildRoute() {
    this.clearGroup(this.routeGroup);
    this.routeShape = this.routePath();
    this.routeGroup.visible = true;
    if (!this.routeShape) return;
    const { path, total } = this.routeShape;
    const radius = clamp(this.size / 450, 0.16, 0.55);
    const segments = clamp(Math.round(total / 0.3), 16, 5000);
    const tube = new THREE.TubeGeometry(path, segments, radius, 8, false);
    const core = new THREE.Mesh(tube, new THREE.MeshBasicMaterial({ color: COLOURS.route }));
    const glow = new THREE.Mesh(new THREE.TubeGeometry(path, segments, radius * 2.6, 8, false), new THREE.MeshBasicMaterial({ color: COLOURS.routeGlow, transparent: true, opacity: 0.28, depthWrite: false }));
    core.renderOrder = 6;
    glow.renderOrder = 7;
    this.routeGroup.add(glow, core);
    this.routeCore = core;
    this.routeGlow = glow;
    this.routeSegments = segments;
    const head = new THREE.Mesh(new THREE.SphereGeometry(radius * 3, 20, 14), new THREE.MeshBasicMaterial({ color: 0xffffff }));
    const halo = new THREE.Mesh(new THREE.SphereGeometry(radius * 6, 20, 14), new THREE.MeshBasicMaterial({ color: COLOURS.route, transparent: true, opacity: 0.25, depthWrite: false }));
    head.add(halo);
    head.visible = false;
    head.renderOrder = 8;
    this.routeHead = head;
    this.routeGroup.add(head);
    // Flowing pulses along the finished route (like the dashes in 2D); none with reduced motion.
    const count = this.reducedMotion.matches ? 0 : clamp(Math.round(total / 18), 2, 40);
    if (count) {
      const pulses = new THREE.InstancedMesh(new THREE.SphereGeometry(radius * 1.5, 12, 8), new THREE.MeshBasicMaterial({ color: 0xffffff }), count);
      pulses.renderOrder = 8;
      this.routePulses = pulses;
      this.routeGroup.add(pulses);
    } else {
      this.routePulses = null;
    }
    if (this.routeAnim) this.updateRouteAnimation(performance.now());
  }

  playRoute() {
    if (!this.routeShape) return false;
    this.stopRouteAnimation();
    if (this.reducedMotion.matches) return false;
    const duration = clamp(2500 + this.routeShape.total * 40, ANIM_MIN_MS, ANIM_MAX_MS);
    this.routeAnim = { t0: performance.now(), duration, mark: -1 };
    this.requestRender();
    return true;
  }

  stopRouteAnimation() {
    if (!this.routeAnim) return;
    this.routeAnim = null;
    this.handlers.onCaption?.("");
    if (this.routeCore) {
      this.routeCore.geometry.setDrawRange(0, Infinity);
      this.routeGlow.geometry.setDrawRange(0, Infinity);
      this.routeHead.visible = false;
    }
  }

  updateRouteAnimation(now) {
    const anim = this.routeAnim;
    if (!anim || !this.routeShape) return;
    const t = easeInOut((now - anim.t0) / anim.duration);
    const per = 8 * 6; // indices per tubular segment
    const n = Math.floor(t * this.routeSegments) * per;
    this.routeCore.geometry.setDrawRange(0, n);
    this.routeGlow.geometry.setDrawRange(0, n);
    this.routeHead.visible = true;
    this.routeHead.position.copy(this.routeShape.path.getPointAt(Math.min(t, 0.9999)));
    const marks = this.routeShape.marks;
    let current = -1;
    marks.forEach((m, i) => { if (t >= m.t) current = i; });
    if (current !== anim.mark) {
      anim.mark = current;
      const mark = marks[current];
      if (mark) {
        this.handlers.onCaption?.(mark.caption || this.floors.get(mark.floor_id)?.floor.name || "");
      }
    }
    if (now - anim.t0 >= anim.duration) this.stopRouteAnimation();
  }

  updatePulses(now) {
    const pulses = this.routePulses;
    if (!pulses || !this.routeShape || this.routeAnim) { if (pulses) pulses.visible = false; return false; }
    pulses.visible = true;
    const matrix = new THREE.Matrix4();
    const speed = 6; // metres per second
    const offset = ((now / 1000) * speed) / this.routeShape.total;
    for (let i = 0; i < pulses.count; i++) {
      const t = (i / pulses.count + offset) % 1;
      matrix.makeTranslation(this.routeShape.path.getPointAt(t));
      pulses.setMatrixAt(i, matrix);
    }
    pulses.instanceMatrix.needsUpdate = true;
    return true;
  }

  // ---------- camera ----------

  // Fit the visible floors with a three-quarter view from the south-west.
  fit(instant = false) {
    const box = new THREE.Box3();
    for (const record of this.floors.values()) {
      if (!this.floorVisible(record) || !Number.isFinite(record.box.minX)) continue;
      box.expandByPoint(new THREE.Vector3(record.box.minX, record.targetY, -record.box.maxY));
      box.expandByPoint(new THREE.Vector3(record.box.maxX, record.targetY + record.wallHeight, -record.box.minY));
    }
    if (box.isEmpty()) return;
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const focus = this.floors.get(this.layout.focus);
    const target = sphere.center.clone();
    if (focus && this.layout.mode !== "exploded") target.y = focus.targetY;
    this.flyToSphere(target, sphere.radius, { instant, direction: new THREE.Vector3(-0.55, 0.95, 0.75).normalize() });
  }

  flyToSphere(center, radius, { instant = false, direction = null } = {}) {
    const dir = direction || this.camera.position.clone().sub(this.controls.target).normalize();
    if (dir.y < 0.35) { dir.y = 0.35; dir.normalize(); }
    const vfov = (this.camera.fov * Math.PI) / 180;
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * this.camera.aspect);
    const distance = clamp((Math.max(radius, 3) / Math.sin(Math.min(vfov, hfov) / 2)) * 0.92, 6, this.size * 5);
    const position = center.clone().add(dir.multiplyScalar(distance));
    if (instant || this.reducedMotion.matches) {
      this.flight = null;
      this.controls.target.copy(center);
      this.camera.position.copy(position);
      this.controls.update();
    } else {
      this.flight = { t0: performance.now(), duration: 750, fromTarget: this.controls.target.clone(), fromPos: this.camera.position.clone(), toTarget: center, toPos: position };
    }
    this.requestRender();
  }

  // Where something is in 3D: {center, radius, floor_id}. Accepts space, asset, opening, connector and floor ids.
  locate(id) {
    const at = (fid, x, y, radius) => {
      const record = this.floors.get(fid);
      return record ? { center: new THREE.Vector3(x, record.targetY + 1, -y), radius, floor_id: fid } : null;
    };
    if (this.spaces.has(id)) {
      const s = this.spaces.get(id);
      const b = bboxOf(s.polygon);
      return at(s.floor_id, s.anchor[0], s.anchor[1], Math.max(10, Math.hypot(b.maxX - b.minX, b.maxY - b.minY) * 0.9));
    }
    if (this.assets.has(id)) { const a = this.assets.get(id); return at(a.floor_id, a.position[0], a.position[1], 6); }
    if (this.openings.has(id)) { const o = this.openings.get(id); return at(o.floor_id, o.position[0], o.position[1], 6); }
    if (this.connectors.has(id)) {
      const c = this.connectors.get(id);
      const stops = c.space_ids.map((sid) => this.spaces.get(sid)).filter(Boolean);
      if (!stops.length) return null;
      const ys = c.floor_ids.map((fid) => this.floors.get(fid)?.targetY ?? 0);
      const lo = Math.min(...ys), hi = Math.max(...ys);
      return { center: new THREE.Vector3(stops[0].anchor[0], (lo + hi) / 2, -stops[0].anchor[1]), radius: Math.max(18, (hi - lo) * 0.8), floor_id: null };
    }
    if (this.floors.has(id)) {
      const r = this.floors.get(id);
      const b = r.box;
      return { center: new THREE.Vector3((b.minX + b.maxX) / 2, r.targetY, -(b.minY + b.maxY) / 2), radius: Math.hypot(b.maxX - b.minX, b.maxY - b.minY) / 2, floor_id: id };
    }
    return null;
  }

  // Frame the whole route, including its vertical runs.
  fitRoute() {
    if (!this.routeShape) return;
    const box = new THREE.Box3();
    for (const p of this.routeShape.points) box.expandByPoint(p.v);
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    this.flyToSphere(sphere.center, Math.max(8, sphere.radius * 1.1));
  }

  flyToIds(ids, { instant = false } = {}) {
    const found = ids.map((id) => this.locate(id)).filter(Boolean);
    if (!found.length) return null;
    const box = new THREE.Box3();
    for (const f of found) box.union(new THREE.Sphere(f.center, f.radius).getBoundingBox(new THREE.Box3()));
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    this.flyToSphere(sphere.center, found.length === 1 ? found[0].radius : sphere.radius, { instant });
    return found.find((f) => f.floor_id)?.floor_id ?? null;
  }

  flyToPoint(floorId, point, radius = 12) {
    const record = this.floors.get(floorId);
    if (!record) return;
    this.flyToSphere(new THREE.Vector3(point[0], record.targetY, -point[1]), radius);
  }

  zoom(factor) {
    const offset = this.camera.position.clone().sub(this.controls.target).multiplyScalar(factor);
    if (offset.length() < this.controls.minDistance || offset.length() > this.controls.maxDistance) return;
    this.camera.position.copy(this.controls.target).add(offset);
    this.controls.update();
    this.requestRender();
  }

  // Camera target on the focused floor in plan coordinates, for the minimap.
  cameraOnPlan() {
    const t = this.controls.target, p = this.camera.position;
    return { target: [t.x, -t.z], heading: Math.atan2(-(t.z - p.z), t.x - p.x), distance: p.distanceTo(t), fov: this.camera.fov, aspect: this.camera.aspect };
  }

  panTo(planPoint) {
    const record = this.floors.get(this.layout.focus);
    const target = new THREE.Vector3(planPoint[0], record ? record.targetY : this.controls.target.y, -planPoint[1]);
    const delta = target.clone().sub(this.controls.target);
    this.controls.target.add(delta);
    this.camera.position.add(delta);
    this.controls.update();
    this.requestRender();
  }

  // ---------- frame ----------

  tick(now) {
    let busy = false;
    if (this.flight) {
      const f = this.flight;
      const t = easeInOut((now - f.t0) / f.duration);
      this.controls.target.lerpVectors(f.fromTarget, f.toTarget, t);
      this.camera.position.lerpVectors(f.fromPos, f.toPos, t);
      if (now - f.t0 >= f.duration) this.flight = null;
      busy = true;
      this.labelsDirty = true;
    }
    if (this.floorTween) {
      const tw = this.floorTween;
      const t = easeInOut((now - tw.t0) / tw.duration);
      for (const record of this.floors.values()) {
        const from = tw.from.get(record.floor.id) ?? record.targetY;
        record.y = from + (record.targetY - from) * t;
        record.group.position.y = record.y;
      }
      if (now - tw.t0 >= tw.duration) {
        this.floorTween = null;
        this.rebuildShafts();
        this.rebuildRoute();
      }
      busy = true;
      this.labelsDirty = true;
    }
    if (this.controls.update()) busy = true;
    if (this.routeAnim) { this.updateRouteAnimation(now); busy = true; }
    if (this.updatePulses(now)) busy = true;
    if (!this.reducedMotion.matches && this.pulseHighlights(now)) busy = true;
    if (this.spin) {
      const angle = ((now - this.spin.last) / 1000) * this.spin.speed;
      this.spin.last = now;
      const offset = this.camera.position.clone().sub(this.controls.target).applyAxisAngle(new THREE.Vector3(0, 1, 0), angle);
      this.camera.position.copy(this.controls.target).add(offset);
      busy = true;
      this.labelsDirty = true;
    }
    if (!this.dirty && !busy) return;
    this.dirty = false;
    if (!this.assetCheckAt || now - this.assetCheckAt > 250) {
      this.assetCheckAt = now;
      for (const record of this.floors.values()) this.updateAssetVisibility(record);
    }
    this.renderer.render(this.scene, this.camera);
    this.afterRender?.(now);
    this.countFrame(now);
  }

  pulseHighlights(now) {
    let any = false;
    const k = 0.65 + 0.35 * Math.sin(now / 260);
    for (const record of this.floors.values()) {
      if (!record.stateGroup) continue;
      for (const child of record.stateGroup.children) {
        if (!child.userData.pulse) continue;
        child.userData.material.opacity = child.userData.baseOpacity * k;
        any = true;
      }
    }
    return any;
  }

  countFrame(now) {
    const s = this.stats;
    s.frames += 1;
    s.frames_since += 1;
    if (now - s.last_fps_at >= 1000) {
      s.fps = Math.round((s.frames_since * 1000) / (now - s.last_fps_at));
      s.frames_since = 0;
      s.last_fps_at = now;
    }
  }

  // Spin the camera for a while and measure frames per second (for the performance check, view3d.benchmark()).
  benchmark(ms = 3000) {
    return new Promise((resolve) => {
      const t0 = performance.now();
      const start = this.stats.frames;
      this.spin = { last: t0, speed: 0.6 };
      setTimeout(() => {
        this.spin = null;
        const elapsed = performance.now() - t0;
        resolve({ fps: Math.round(((this.stats.frames - start) * 1000) / elapsed), ...this.info() });
      }, ms);
    });
  }

  info() {
    const r = this.renderer.info.render;
    return { build_ms: Math.round(this.stats.build_ms), floors_built: this.stats.floors_built, floors: this.floors.size, draw_calls: r.calls, triangles: r.triangles, fps: this.stats.fps };
  }

  // ---------- labels and pins (HTML overlay) ----------

  // Room names near the camera: only rooms big enough on screen, nearest first, no overlaps, at most 60.
  layoutLabels(focusOnly = true) {
    if (!this.labelsDirty) return;
    this.labelsDirty = false;
    const w = this.renderer.domElement.clientWidth, h = this.renderer.domElement.clientHeight;
    const focal = h / 2 / Math.tan((this.camera.fov * Math.PI) / 360);
    const candidates = [];
    const v = new THREE.Vector3();
    for (const record of this.floors.values()) {
      if (!this.floorVisible(record) || record.ghost || (focusOnly && this.layout.mode !== "exploded" && record.floor.id !== this.layout.focus)) continue;
      for (const s of record.spaces) {
        if (s.type === "corridor" && !s.ref) continue;
        if (s.type === "outdoor") continue;
        const text = this.labelText(s);
        if (!text) continue;
        v.set(s.anchor[0], record.y + record.wallHeight + 0.2, -s.anchor[1]);
        const distance = v.distanceTo(this.camera.position);
        const size = (Math.sqrt(s.area_m2 || 4) / distance) * focal;
        if (size < text.length * 5.5) continue; // too small on screen to name
        v.project(this.camera);
        if (v.z > 1 || v.x < -1.05 || v.x > 1.05 || v.y < -1.05 || v.y > 1.05) continue;
        candidates.push({ s, text, x: ((v.x + 1) / 2) * w, y: ((1 - v.y) / 2) * h, distance });
      }
    }
    candidates.sort((a, b) => a.distance - b.distance);
    const placed = [];
    const out = [];
    for (const c of candidates) {
      const half = (c.text.length * 6.6) / 2 + 4;
      const box = [c.x - half, c.y - 9, c.x + half, c.y + 9];
      if (placed.some((p) => box[0] < p[2] && box[2] > p[0] && box[1] < p[3] && box[3] > p[1])) continue;
      placed.push(box);
      out.push(c);
      if (out.length >= 60) break;
    }
    return out;
  }

  labelText(s) {
    const generic = /^(Corridor|Generic room|Room)\b/.test(s.name);
    if (generic) return s.ref || "";
    return s.name.length > 26 ? s.ref || s.name.slice(0, 24) + "…" : s.name;
  }

  // Screen position of a plan point on a floor (for pins), or null when behind the camera.
  project(floorId, point, lift = 1.2) {
    const record = this.floors.get(floorId);
    if (!record || !this.floorVisible(record)) return null;
    const v = new THREE.Vector3(point[0], record.y + lift, -point[1]).project(this.camera);
    if (v.z > 1) return null;
    const w = this.renderer.domElement.clientWidth, h = this.renderer.domElement.clientHeight;
    return [((v.x + 1) / 2) * w, ((1 - v.y) / 2) * h];
  }

  // ---------- picking ----------

  pick(clientX, clientY) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const targets = [];
    for (const record of this.floors.values()) {
      if (!record.built || !record.group.visible || record.ghost) continue;
      targets.push(record.slab);
      if (record.assetMesh?.visible) targets.push(record.assetMesh);
      for (const child of record.stateGroup.children) if (child.userData.kind === "doors") targets.push(child);
      if (record.doorMarkers) targets.push(record.doorMarkers);
    }
    const hits = this.raycaster.intersectObjects(targets, false);
    for (const hit of hits) {
      const data = hit.object.userData;
      if (data.kind === "slab") {
        const record = data.record;
        const tri = hit.faceIndex;
        let lo = 0, hi = record.triStarts.length - 1;
        while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (record.triStarts[mid] <= tri) lo = mid; else hi = mid - 1; }
        return { kind: "space", id: record.triSpaces[lo], point: hit.point };
      }
      if (data.kind === "assets") return { kind: "asset", id: data.ids[hit.instanceId], point: hit.point };
      if (data.kind === "doors") return { kind: "opening", id: data.ids[hit.instanceId], point: hit.point };
    }
    return null;
  }

  wireInput() {
    const canvas = this.renderer.domElement;
    canvas.addEventListener("pointerdown", (e) => { this.pointer.down = { x: e.clientX, y: e.clientY }; this.flight = null; });
    canvas.addEventListener("pointerup", (e) => {
      const down = this.pointer.down;
      this.pointer.down = null;
      if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return;
      const hit = this.pick(e.clientX, e.clientY);
      if (!hit) return this.handlers.onEmptyClick?.(e);
      if (hit.kind === "opening") return this.handlers.onOpeningClick?.(e, hit.id);
      const spaceId = hit.kind === "asset" ? this.assets.get(hit.id)?.space_id : hit.id;
      if (spaceId) this.handlers.onSpaceClick?.(e, spaceId, hit);
    });
    canvas.addEventListener("pointermove", (e) => {
      if (e.pointerType !== "mouse" || e.buttons) { this.tooltip.hidden = true; return; }
      const now = performance.now();
      if (now - this.pointer.hoverAt < 60) return;
      this.pointer.hoverAt = now;
      const hit = this.pick(e.clientX, e.clientY);
      this.showTooltip(hit, e);
    });
    canvas.addEventListener("pointerleave", () => (this.tooltip.hidden = true));
  }

  showTooltip(hit, e) {
    if (!hit) { this.tooltip.hidden = true; return; }
    let text = "";
    if (hit.kind === "space") {
      const s = this.spaces.get(hit.id);
      text = `${s.name} · ${String(s.room_type).replaceAll("_", " ")}`;
    } else if (hit.kind === "asset") {
      const a = this.assets.get(hit.id);
      const fp = a.footprint;
      text = `${a.name}${fp ? ` · ${fp.width_m} × ${fp.depth_m} m` : ""}`;
    } else {
      const o = this.openings.get(hit.id);
      text = `${o.added ? "New door" : o.kind}${o.width_m ? ` · ${o.width_m} m wide` : ""}${o.step_free ? "" : " · step"}${this.stateData.closed.has(o.id) ? " · closed" : ""}`;
    }
    const rect = this.container.getBoundingClientRect();
    this.tooltip.textContent = text;
    this.tooltip.style.left = `${e.clientX - rect.left + 14}px`;
    this.tooltip.style.top = `${e.clientY - rect.top + 14}px`;
    this.tooltip.hidden = false;
  }

  // ---------- helpers ----------

  clearGroup(group) {
    for (const child of [...group.children]) {
      group.remove(child);
      child.traverse((node) => {
        node.geometry?.dispose();
        if (node.material) (Array.isArray(node.material) ? node.material : [node.material]).forEach((m) => m.dispose());
      });
    }
  }
}
