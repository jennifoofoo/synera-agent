// New building from floor plans (Level 4): upload, read in the background, preview with red spots, fix,
// confirm card, save, switch to it. All checks and changes happen on the server (web/level4_api.py).
"use strict";

(() => {
  const MAX_BYTES = 10 * 1024 * 1024;
  const SECONDS_PER_FLOOR = 15;
  const ALONG = [["building_width", "building width"], ["room", "room width"], ["door", "door width"]];
  const ROOM_TYPES = ["generic_room", "office", "meeting_room", "corridor", "lobby", "stairwell", "lift", "toilet",
    "kitchen", "storage", "lab", "workshop", "classroom", "bedroom", "living_room", "bathroom", "technical_room"];

  const plan = {
    floors: [],          // [{file, url, level, length, along, bar, uploadId, error}]
    preview: null,       // last /api/level4/preview
    version: null,       // draft version the page knows
    saved: null,         // last saved key the page switched to
    pickFirst: null,     // first room of "add door"
    polling: false,
  };

  // ---------- server ----------

  async function post(path, body = {}) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }

  async function uploadFile(file) {
    const type = file.type || (/\.jpe?g$/i.test(file.name) ? "image/jpeg" : "image/png");
    const response = await fetch("/api/level4/upload", { method: "POST", headers: { "Content-Type": type }, body: file });
    const payload = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }

  // ---------- step 1: images, level, known length ----------

  function guessLevel(name, index) {
    const match = name.match(/(?:floor|level|etage|og|eg)[ _-]?(-?\d+)/i);
    return match ? Number(match[1]) : index;
  }

  function addFiles(files) {
    for (const file of files) {
      const entry = { file, url: URL.createObjectURL(file), level: guessLevel(file.name, plan.floors.length), length: "", along: "building_width", bar: false, error: "" };
      if (!/^image\/(png|jpeg)$/.test(file.type) && !/\.(png|jpe?g)$/i.test(file.name)) entry.error = "Only PNG and JPG images.";
      else if (file.size > MAX_BYTES) entry.error = "Larger than 10 MB.";
      plan.floors.push(entry);
    }
    renderFloors();
  }

  function renderFloors() {
    const box = $("#plan-floors");
    box.innerHTML = "";
    plan.floors.forEach((entry, index) => {
      const row = document.createElement("div");
      row.className = "plan-floor";
      row.innerHTML = `
        <img alt="">
        <div class="file"></div>
        <button type="button" class="remove" aria-label="Remove image">×</button>
        <div class="fields">
          <label>Floor <input type="number" class="level" step="1" min="-5" max="60"></label>
          <label>Known length <input type="number" class="length" step="any" min="0" placeholder="m"> m</label>
          <select class="along" aria-label="What that length is">${ALONG.map(([v, t]) => `<option value="${v}">${t}</option>`).join("")}</select>
          <label class="check"><input type="checkbox" class="bar"> scale bar printed</label>
        </div>`;
      row.querySelector("img").src = entry.url;
      row.querySelector(".file").textContent = entry.file.name;  // display only, never sent
      const level = row.querySelector(".level"), length = row.querySelector(".length");
      const along = row.querySelector(".along"), bar = row.querySelector(".bar");
      level.value = entry.level; length.value = entry.length; along.value = entry.along; bar.checked = entry.bar;
      length.disabled = along.disabled = entry.bar;
      level.oninput = () => { entry.level = level.value; updateReadButton(); };
      length.oninput = () => { entry.length = length.value; updateReadButton(); };
      along.onchange = () => (entry.along = along.value);
      bar.onchange = () => { entry.bar = bar.checked; length.disabled = along.disabled = bar.checked; updateReadButton(); };
      row.querySelector(".remove").onclick = () => { URL.revokeObjectURL(entry.url); plan.floors.splice(index, 1); renderFloors(); };
      if (entry.error) {
        const error = document.createElement("div");
        error.className = "error";
        error.textContent = entry.error;
        row.appendChild(error);
      }
      box.appendChild(row);
    });
    $("#plan-why").hidden = plan.floors.length === 0;
    updateReadButton();
  }

  function floorProblem(entry) {
    if (entry.error) return entry.error;
    if (entry.level === "" || !Number.isInteger(Number(entry.level))) return "Give the floor as a whole number (0 = ground floor).";
    if (!entry.bar && !(Number(entry.length) > 0)) return "Give one length you know in metres, or tick 'scale bar printed'.";
    return "";
  }

  function updateReadButton() {
    const levels = plan.floors.map((f) => String(f.level));
    const ok = plan.floors.length > 0 && plan.floors.every((f) => !floorProblem(f)) && new Set(levels).size === levels.length;
    $("#plan-read").disabled = !ok;
    $("#plan-read").title = ok ? "" : plan.floors.map(floorProblem).find(Boolean) || (plan.floors.length ? "Two images have the same floor." : "Add an image first.");
  }

  async function readPlans() {
    $("#plan-read").disabled = true;
    showStep("progress");
    setProgress("Uploading…", 0.02);
    try {
      for (const entry of plan.floors) {
        if (!entry.uploadId) entry.uploadId = (await uploadFile(entry.file)).upload_id;
      }
      const floors = plan.floors.map((f) => ({
        upload_id: f.uploadId,
        level: Number(f.level),
        known_length_m: f.bar ? null : Number(f.length),
        along: f.along,
        scale_bar: f.bar,
      }));
      await post("/api/level4/build", { floors, name: $("#plan-name").value.trim() });
      pollStatus();
    } catch (error) {
      showStep("upload");
      toast(error.message, true);
    }
  }

  // ---------- step 2: progress ----------

  function setProgress(text, fraction) {
    $("#plan-progress-text").textContent = text;
    $("#plan-progress-bar").style.width = `${Math.round(Math.min(1, fraction) * 100)}%`;
  }

  async function pollStatus() {
    if (plan.polling) return;
    plan.polling = true;
    try {
      for (;;) {
        const status = await fetch("/api/level4/status").then((r) => r.json());
        if (status.state === "running") {
          const fraction = Math.min(0.95, status.seconds / (SECONDS_PER_FLOOR * status.floors_total));
          setProgress(`${status.message} · ${Math.round(status.seconds)} s`, fraction);
          await new Promise((resolve) => setTimeout(resolve, 700));
          continue;
        }
        setProgress(status.message, 1);
        for (const error of status.errors || []) toast(`Floor ${error.level}: ${error.error}`, true);
        if (status.has_draft) await showDraft();
        else showStep("upload");
        break;
      }
    } catch (error) {
      toast(`Reading failed: ${error.message}`, true);
      showStep("upload");
    } finally {
      plan.polling = false;
    }
  }

  // ---------- step 3: preview, fix ----------

  async function showDraft(preview = null, refit = false) {
    preview = preview || await fetch("/api/level4/preview").then((r) => r.json());
    if (!preview.draft) { showStep("upload"); return; }
    const first = app.mode !== "draft";
    plan.preview = preview;
    plan.version = preview.version;
    plan.pickFirst = null;
    setBuildingData(preview.draft, { mode: "draft", suspect: { spaces: preview.suspect_spaces, openings: preview.suspect_openings } });
    $("#draft-banner").hidden = false;
    applyState(preview.draft.state, { silent: true, animate: false });
    showFloor(app.floorId, first || refit);
    $("#building-meta").textContent = `Draft · ${preview.draft.floors.length} floor${preview.draft.floors.length > 1 ? "s" : ""} · not saved`;
    $("#plan-show").hidden = true;
    renderReview(preview);
    showStep("review");
    switchTab("plan");
  }

  function renderReview(preview) {
    const summary = $("#plan-summary");
    summary.className = "summary" + (preview.can_save ? "" : " error");
    summary.textContent = preview.summary;
    const list = $("#plan-findings");
    list.innerHTML = "";
    for (const finding of preview.findings) {
      const li = document.createElement("li");
      li.className = finding.level;
      li.textContent = finding.items.length ? `${finding.message.replace(/\.$/, "")}: ${finding.items.slice(0, 8).join(", ")}${finding.items.length > 8 ? ", …" : ""}` : finding.message;
      list.appendChild(li);
    }
    const scales = $("#plan-scales");
    scales.innerHTML = "";
    for (const scale of preview.scales) {
      const row = document.createElement("div");
      row.className = "scale-row";
      row.innerHTML = `<span class="note"></span>
        <input type="number" step="any" min="0" placeholder="m" aria-label="Known length in metres">
        <select aria-label="What that length is">${ALONG.filter(([v]) => v !== "room").map(([v, t]) => `<option value="${v}">${t}</option>`).join("")}</select>
        <button type="button" class="small secondary">Set scale</button>`;
      row.querySelector(".note").textContent = `Floor ${scale.level}: ${scale.note}.`;
      const input = row.querySelector("input"), select = row.querySelector("select");
      row.querySelector("button").onclick = () => fix({ action: "set_scale", known_length_m: Number(input.value), along: select.value, level: scale.level });
      scales.appendChild(row);
    }
    $("#plan-card").hidden = true;
    $("#plan-save").hidden = false;
  }

  async function fix(body) {
    try {
      const result = await post("/api/level4/fix", body);
      toast(result.done || "Changed.");
      await showDraft(result, body.action === "set_scale");  // a new scale moves everything
    } catch (error) {
      toast(error.message, true);
      render();
    }
  }

  const label = (s) => s.ref || s.name;
  // What a finding means for the one room the person tapped.
  const ROOM_PROBLEM = {
    room_unreachable: "No way out: a door is probably missing.",
    area_implausible: "Unlikely size (not 2 to 300 m²).",
    polygon_tiny: "Smaller than 1 m².",
    room_overlap: "Overlaps another room strongly.",
    door_not_on_wall: "A door is not on a wall it shares.",
    connector_single_floor: "Stair or lift not matched to another floor.",
    connector_missing_stop: "Stair or lift misses a floor.",
  };

  function onSpaceClick(event, spaceId) {
    const s = app.spaces.get(spaceId);
    if (plan.pickFirst) {
      const first = plan.pickFirst;
      plan.pickFirst = null;
      app.pendingDoorFrom = null;
      setBanner(null);
      if (first !== spaceId) fix({ action: "add_door", ref: first, other_ref: spaceId });
      else render();
      return;
    }
    app.pickedSpaceId = spaceId;
    render();
    const problems = plan.preview.findings.filter((f) => f.items.some((item) => item.split("/").includes(label(s))));
    const problemText = problems.map((f) => `<br><b style="color:var(--closed)">${esc(ROOM_PROBLEM[f.code] || f.message)}</b>`).join("");
    const types = [...new Set([s.room_type, ...ROOM_TYPES])];
    const options = types.map((t) => `<option value="${esc(t)}"${t === s.room_type ? " selected" : ""}>${esc(t.replaceAll("_", " "))}</option>`).join("");
    showPopover(event, `<h4>${esc(s.name)}</h4><div class="sub">${esc(floorName(s.floor_id))} · ${s.area_m2} m²${problemText}</div><select aria-label="Room type">${options}</select>`, [
      ["Add door to…", "", () => {
        plan.pickFirst = spaceId;
        app.pendingDoorFrom = spaceId;
        render();
        setBanner(`New door from ${s.name}: tap the neighbouring room.`);
      }],
      ["Set type", "secondary", () => {
        const value = $("#popover select").value;
        if (value && value !== s.room_type) fix({ action: "set_room_type", ref: spaceId, room_type: value });
      }],
    ]);
  }

  function onOpeningClick(event, openingId) {
    const o = app.openings.get(openingId);
    const sides = o.space_ids.map((id) => (id === "outside" ? "outside" : esc(spaceName(id)))).join(" ↔ ");
    const actions = o.space_ids.includes("outside") ? [] : [["Remove door", "danger", () => fix({ action: "remove_door", ref: o.space_ids[0], other_ref: o.space_ids[1] })]];
    showPopover(event, `<h4>${esc(o.kind[0].toUpperCase() + o.kind.slice(1))}</h4><div class="sub">${sides}${o.width_m ? `<br>${o.width_m} m wide` : ""}</div>`, actions);
  }

  function cancelPick() {
    plan.pickFirst = null;
  }

  // ---------- step 4: card, yes, save ----------

  async function askToSave() {
    try {
      const { card } = await post("/api/level4/card");
      const box = $("#plan-card");
      const floors = card["I understood"].map((f) => `<li>${esc(f.floor)}: ${f.rooms} rooms, ${f.doors} doors, ${f.entrances} entrance${f.entrances === 1 ? "" : "s"}; scale: ${esc(f.scale)}</li>`).join("");
      const blocked = card["can be saved"] ? "" : `<p class="blocked">${esc(card["problems found"])}</p>
        <label class="check"><input type="checkbox" id="plan-accept"> Save anyway, I accept these problems.</label>`;
      box.innerHTML = `<h4>Save this building?</h4><ul>${floors}</ul>${card["can be saved"] ? `<p>${esc(card["problems found"])}</p>` : blocked}
        <div class="row"><button type="button" class="yes">Yes, save</button><button type="button" class="no secondary">Not yet</button></div>`;
      box.hidden = false;
      $("#plan-save").hidden = true;
      box.querySelector(".yes").onclick = () => answer("yes");
      box.querySelector(".no").onclick = () => answer("no");
      box.scrollIntoView({ block: "nearest" });
    } catch (error) {
      toast(error.message, true);
    }
  }

  async function answer(reply) {
    const accept = Boolean(document.querySelector("#plan-card input[type=checkbox]")?.checked);
    $("#plan-card").hidden = true;
    $("#plan-save").hidden = false;
    try {
      const result = await post("/api/level4/save", { answer: reply, accept_problems: accept });
      if (!result.saved) { toast("Not saved. The draft is kept, you can still fix it."); return; }
      await openSaved(result.key, `Saved: ${result.rooms} rooms, ${result.doors} doors, ${result.entrances} entrances.`);
    } catch (error) {
      toast(error.message, true);
    }
  }

  async function openSaved(key, text) {
    plan.saved = key;
    for (const entry of plan.floors) URL.revokeObjectURL(entry.url);
    plan.floors = [];
    plan.preview = null;
    renderFloors();
    showStep("upload");
    await fillBuildingSelect();
    $("#building-select").value = key;
    await loadBuilding(key);
    addMessage("system", `${text} The new building is loaded: ask anything about it.`);
    toast(text);
    switchTab("chat");
  }

  async function startOver() {
    await post("/api/level4/reset").catch(() => null);
    for (const entry of plan.floors) URL.revokeObjectURL(entry.url);
    plan.floors = [];
    plan.preview = null;
    renderFloors();
    $("#plan-name").value = "";
    showStep("upload");
    if (app.mode === "draft") await backToBuilding();
  }

  async function backToBuilding() {
    await loadBuilding(app.key, false, { keepChat: true });
  }

  // ---------- hooks from app.js ----------

  function onBuildingShown() {
    $("#draft-banner").hidden = true;
    plan.pickFirst = null;
    $("#plan-show").hidden = !plan.preview;
  }

  async function onChat(info) {
    if (!info) return;
    if (info.saved && info.saved !== plan.saved) {
      await openSaved(info.saved, "The agent saved the building.");
      return;
    }
    if (info.has_draft && info.version !== plan.version) {
      addMessage("system", "The agent built or changed a floor plan draft. It is shown on the plan now.");
      await showDraft();
    }
  }

  function showStep(name) {
    $("#plan-step-upload").hidden = name !== "upload" && name !== "review";
    $("#plan-progress").hidden = name !== "progress";
    $("#plan-review").hidden = name !== "review";
    if (name === "review") $("#plan-step-upload").hidden = true;
  }

  function wire() {
    const drop = $("#plan-drop");
    $("#plan-files").onchange = (e) => { addFiles(e.target.files); e.target.value = ""; };
    drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("over"));
    drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); addFiles(e.dataTransfer.files); });
    $("#plan-read").onclick = readPlans;
    $("#plan-save").onclick = askToSave;
    $("#plan-discard").onclick = startOver;
    $("#plan-show").onclick = () => showDraft();
    $("#draft-back").onclick = backToBuilding;
    $("#new-building").onclick = () => switchTab("plan");
    fetch("/api/level4/status").then((r) => r.json()).then((status) => {
      plan.version = status.version;
      plan.saved = status.saved;
      if (status.state === "running") { showStep("progress"); pollStatus(); }
      else if (status.has_draft && !status.saved) return fetch("/api/level4/preview").then((r) => r.json()).then((preview) => {
        if (!preview.draft) return;
        plan.preview = preview;
        renderReview(preview);
        showStep("review");
        $("#plan-show").hidden = false;
      });
    }).catch(() => null);
  }

  window.plan = { onSpaceClick, onOpeningClick, onBuildingShown, onChat, cancelPick };
  wire();
})();
