/**
 * rack_elevation.js - Native, Theme-Aware Interactive Rack Elevation View & Device Library (Phase 5a)
 *
 * Shared by both `/racks` page and the slide-over Rack Elevation Drawer inside `/` (2D Editor & 3D View).
 * Uses ONLY app CSS theme variables (--bg-*, --text-*, --accent-*, --border-*). Zero iframes, zero external CSS.
 */
(function () {
  const RACK_TEMPLATES_U = [4, 6, 9, 12, 18, 24, 36, 42, 48, 52, 60, 70];
  const DEVICE_TYPES = [
    { value: "server", en: "Server", id: "Server", icon: "🖥️", color: "#0284c7" },
    { value: "switch", en: "Switch", id: "Switch", icon: "🔀", color: "#059669" },
    { value: "patch_panel", en: "Patch Panel", id: "Patch Panel", icon: "🔌", color: "#475569" },
    { value: "pdu", en: "PDU", id: "PDU", icon: "⚡", color: "#d97706" },
    { value: "ups", en: "UPS", id: "UPS", icon: "🔋", color: "#dc2626" },
    { value: "storage", en: "Storage", id: "Penyimpanan", icon: "💾", color: "#7c3aed" },
    { value: "blank_panel", en: "Blank Panel", id: "Panel Kosong", icon: "▬", color: "#64748b" },
    { value: "custom", en: "Custom", id: "Kustom", icon: "📦", color: "#db2777" },
  ];

  function getCsrf() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function typeMeta(t) {
    return DEVICE_TYPES.find((x) => x.value === t) || DEVICE_TYPES[DEVICE_TYPES.length - 1];
  }

  function statusColor(st) {
    if (st === "active") return "var(--accent-green)";
    if (st === "planned") return "var(--accent-cyan)";
    if (st === "maintenance") return "var(--accent-amber)";
    return "var(--accent-red)";
  }

  function facesConflict(a, b) {
    if (a === "both" || b === "both") return true;
    return a === b;
  }

  function slotsConflict(hA, sA, hB, sB) {
    if (!hA || !hB) return true;
    if (sA === "full" || sB === "full") return true;
    return sA === sB;
  }

  function checkLocalOverlap(rack, cand, ignoreId = null) {
    const topU = cand.u_position + cand.u_height - 1;
    if (cand.u_position < 1 || topU > rack.u_height) {
      return `Out of range: U${cand.u_position}–U${topU} exceeds 1–${rack.u_height}U`;
    }
    for (const d of rack.devices || []) {
      if (ignoreId && d.id === ignoreId) continue;
      const dTop = d.u_position + d.u_height - 1;
      if (cand.u_position <= dTop && d.u_position <= topU) {
        if (facesConflict(cand.face, d.face)) {
          if (slotsConflict(cand.half_width, cand.half_slot, d.half_width, d.half_slot)) {
            return `Overlap with ${d.name} (U${d.u_position}–U${dTop})`;
          }
        }
      }
    }
    return null;
  }

  function injectStyles() {
    if (document.getElementById("monits-rack-elevation-css")) return;
    const style = document.createElement("style");
    style.id = "monits-rack-elevation-css";
    style.textContent = `
      .rk-shell {
        display: grid;
        grid-template-columns: 270px 1fr 290px;
        gap: 14px;
        align-items: start;
        color: var(--text-main);
        font-family: var(--font-sans);
      }
      .rk-shell.rk-compact {
        grid-template-columns: 1fr;
      }
      @media (max-width: 1120px) {
        .rk-shell { grid-template-columns: 240px 1fr; }
        .rk-col-lib { grid-column: 1 / -1; }
      }
      @media (max-width: 780px) {
        .rk-shell { grid-template-columns: 1fr; }
      }
      .rk-panel {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 12px 14px;
        box-shadow: var(--card-shadow);
      }
      .rk-title {
        font-size: 0.78rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--accent-cyan);
        margin: 0 0 10px 0;
        padding-bottom: 5px;
        border-bottom: 1px solid var(--border-color);
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
      }
      .rk-rack-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        padding: 8px 10px;
        border-radius: 8px;
        border: 1px solid var(--border-subtle);
        background: var(--bg-card-inner);
        margin-bottom: 6px;
        cursor: pointer;
        transition: border-color 0.15s, background 0.15s;
      }
      .rk-rack-item:hover, .rk-rack-item.active {
        border-color: var(--accent-cyan);
        background: var(--accent-cyan-soft);
      }
      .rk-input, .rk-select, .rk-textarea {
        width: 100%;
        box-sizing: border-box;
        background: var(--bg-app);
        color: var(--text-main);
        border: 1px solid var(--border-subtle);
        border-radius: 6px;
        padding: 5px 8px;
        font-size: 0.78rem;
        font-family: inherit;
      }
      .rk-input:focus, .rk-select:focus, .rk-textarea:focus {
        outline: none;
        border-color: var(--accent-cyan);
      }
      .rk-btn {
        border: 1px solid var(--border-color);
        background: var(--accent-cyan-soft);
        color: var(--accent-cyan);
        padding: 5px 10px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
        cursor: pointer;
        white-space: nowrap;
        transition: all 0.15s;
      }
      .rk-btn:hover { filter: brightness(1.1); }
      .rk-btn.primary {
        background: var(--accent-cyan);
        color: var(--text-on-accent);
      }
      .rk-btn.danger {
        color: var(--accent-red);
        border-color: rgba(239, 68, 68, 0.4);
        background: rgba(239, 68, 68, 0.1);
      }
      .rk-stats {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 10px;
        margin-bottom: 12px;
      }
      .rk-stat-box {
        background: var(--bg-card-inner);
        border: 1px solid var(--border-subtle);
        border-radius: 8px;
        padding: 8px 10px;
      }
      .rk-bar {
        height: 7px;
        border-radius: 999px;
        background: var(--bg-surface-elevated);
        overflow: hidden;
        margin-top: 5px;
      }
      .rk-bar > span {
        display: block;
        height: 100%;
        border-radius: 999px;
        background: var(--accent-cyan);
        transition: width 0.25s ease;
      }
      .rk-elev-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 14px;
      }
      @media (max-width: 680px) {
        .rk-elev-grid { grid-template-columns: 1fr; }
      }
      .rk-cabinet {
        background: var(--bg-app);
        border: 2px solid var(--border-color);
        border-radius: 10px;
        overflow: hidden;
      }
      .rk-cabinet-head {
        background: var(--bg-header);
        color: var(--accent-cyan);
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        padding: 6px 10px;
        border-bottom: 1px solid var(--border-color);
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .rk-u-grid {
        display: grid;
        grid-template-columns: 36px 1fr 1fr;
        grid-auto-rows: 26px;
        position: relative;
      }
      .rk-u-num {
        grid-column: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.68rem;
        font-family: var(--font-mono);
        color: var(--text-muted);
        border-right: 1px solid var(--border-subtle);
        border-bottom: 1px solid var(--border-subtle);
        background: var(--bg-card-inner);
        user-select: none;
      }
      .rk-u-slot {
        border-bottom: 1px dashed var(--border-subtle);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.64rem;
        color: transparent;
        transition: background 0.12s;
        cursor: pointer;
      }
      .rk-u-slot:hover {
        background: var(--accent-cyan-soft);
        color: var(--accent-cyan);
      }
      .rk-u-slot.drop-ok {
        background: rgba(34, 197, 94, 0.24) !important;
        outline: 1px solid var(--accent-green);
      }
      .rk-u-slot.drop-bad {
        background: rgba(239, 68, 68, 0.26) !important;
        outline: 1px solid var(--accent-red);
      }
      .rk-dev-block {
        z-index: 3;
        margin: 1px 2px;
        border-radius: 5px;
        padding: 2px 7px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 6px;
        font-size: 0.72rem;
        font-weight: 600;
        color: #ffffff;
        cursor: grab;
        overflow: hidden;
        box-shadow: inset 0 0 0 1px rgba(255,255,255,0.22);
        user-select: none;
      }
      .rk-dev-block:active { cursor: grabbing; }
      .rk-dev-block.selected {
        outline: 2px solid var(--accent-cyan);
        outline-offset: 1px;
      }
      .rk-dev-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        flex-shrink: 0;
        box-shadow: 0 0 6px currentColor;
      }
      .rk-tpl-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 6px;
        padding: 6px 8px;
        border-radius: 7px;
        background: var(--bg-card-inner);
        border: 1px solid var(--border-subtle);
        margin-bottom: 5px;
        font-size: 0.74rem;
        cursor: grab;
      }
      .rk-tpl-item:hover {
        border-color: var(--accent-cyan);
      }
      .rk-alert {
        padding: 7px 10px;
        border-radius: 8px;
        font-size: 0.76rem;
        margin-bottom: 10px;
        border: 1px solid var(--border-color);
      }
      .rk-alert.err {
        background: rgba(239, 68, 68, 0.14);
        border-color: rgba(239, 68, 68, 0.45);
        color: var(--accent-red);
      }
      .rk-alert.ok {
        background: rgba(34, 197, 94, 0.14);
        border-color: rgba(34, 197, 94, 0.45);
        color: var(--accent-green);
      }
      .rk-form-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 7px;
        font-size: 0.74rem;
      }
      .rk-form-grid label {
        display: flex;
        flex-direction: column;
        gap: 3px;
        color: var(--text-muted);
      }
    `;
    document.head.appendChild(style);
  }

  class RackElevationController {
    constructor(container, opts = {}) {
      this.container = container;
      this.lang = opts.lang || document.documentElement.lang || "en";
      this.isId = this.lang === "id";
      this.compact = Boolean(opts.compact);
      this.canWrite = opts.canWrite !== false;
      this.racks = [];
      this.templates = [];
      this.selectedRackId = opts.rackId || null;
      this.selectedDeviceId = null;
      this.dragPayload = null;
      this.banner = null; // { kind: 'ok'|'err', text: '' }
      this.libFilter = "";
      this.showNewRack = false;
      this.showNewTpl = false;
      this.showNetbox = false;
      this.undoStack = [];
      this.redoStack = [];
      injectStyles();
    }

    t(en, id) {
      return this.isId ? id : en;
    }

    setBanner(kind, text) {
      this.banner = text ? { kind, text } : null;
      this.render();
    }

    async loadAll(selectRackId = null) {
      try {
        const [rRes, tRes] = await Promise.all([
          fetch("/api/v1/racks"),
          fetch("/api/v1/racks/library/templates"),
        ]);
        if (rRes.ok) {
          const data = await rRes.json();
          this.racks = data.racks || [];
        }
        if (tRes.ok) {
          const tData = await tRes.json();
          this.templates = tData.templates || [];
        }
        if (selectRackId) {
          const found = this.racks.find((r) => r.id === selectRackId || r.furniture_id === selectRackId);
          if (found) this.selectedRackId = found.id;
        }
        if (!this.selectedRackId || !this.racks.some((r) => r.id === this.selectedRackId)) {
          this.selectedRackId = this.racks[0]?.id || null;
        }
        this.render();
      } catch (err) {
        this.setBanner("err", `Failed to load racks: ${err.message}`);
      }
    }

    get activeRack() {
      return this.racks.find((r) => r.id === this.selectedRackId) || null;
    }

    get activeDevice() {
      const r = this.activeRack;
      if (!r || !this.selectedDeviceId) return null;
      return (r.devices || []).find((d) => d.id === this.selectedDeviceId) || null;
    }

    async notifyPlanSync() {
      try {
        await window.monitsApi?.refreshRacksFromDb?.();
      } catch (e) {}
    }

    async createRack(payload) {
      const res = await fetch("/api/v1/racks", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrf() },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        this.setBanner("err", data.detail || "Failed to create rack");
        return;
      }
      this.showNewRack = false;
      await this.loadAll(data.id);
      this.setBanner("ok", this.t(`Created rack "${data.name}" (${data.u_height}U).`, `Rak "${data.name}" (${data.u_height}U) berhasil dibuat.`));
      await this.notifyPlanSync();
    }

    async deleteRack(rackId) {
      const r = this.racks.find((x) => x.id === rackId);
      if (!r) return;
      if (!confirm(this.t(`Delete rack "${r.name}" and all mounted devices?`, `Hapus rak "${r.name}" beserta semua perangkatnya?`))) return;
      const res = await fetch(`/api/v1/racks/${encodeURIComponent(rackId)}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": getCsrf() },
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        this.setBanner("err", d.detail || "Delete failed");
        return;
      }
      this.selectedDeviceId = null;
      await this.loadAll();
      this.setBanner("ok", this.t(`Deleted rack "${r.name}".`, `Rak "${r.name}" dihapus.`));
      await this.notifyPlanSync();
    }

    async mountDevice(rackId, payload, pushUndo = true) {
      const res = await fetch(`/api/v1/racks/${encodeURIComponent(rackId)}/devices`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrf() },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        this.setBanner("err", data.detail || "Placement rejected (overlap or out of range)");
        return null;
      }
      if (pushUndo) {
        this.undoStack.push({ type: "add", rackId, device: data });
        this.redoStack = [];
      }
      this.selectedDeviceId = data.id;
      await this.loadAll(rackId);
      this.setBanner("ok", this.t(`Mounted "${data.name}" at U${data.u_position} (${data.face}).`, `"${data.name}" dipasang di U${data.u_position} (${data.face}).`));
      await this.notifyPlanSync();
      return data;
    }

    async updateDevice(rackId, deviceId, patch, pushUndo = true) {
      const prev = this.activeRack?.devices?.find((d) => d.id === deviceId);
      const res = await fetch(`/api/v1/racks/${encodeURIComponent(rackId)}/devices/${encodeURIComponent(deviceId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrf() },
        body: JSON.stringify(patch),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        this.setBanner("err", data.detail || "Update rejected (overlap or out of range)");
        return null;
      }
      if (pushUndo && prev) {
        this.undoStack.push({ type: "update", rackId, deviceId, before: { ...prev }, after: { ...data } });
        this.redoStack = [];
      }
      this.selectedDeviceId = data.id;
      await this.loadAll(rackId);
      this.setBanner("ok", this.t(`Updated "${data.name}" @ U${data.u_position}.`, `"${data.name}" diperbarui di U${data.u_position}.`));
      await this.notifyPlanSync();
      return data;
    }

    async deleteDevice(rackId, deviceId, pushUndo = true) {
      const prev = this.activeRack?.devices?.find((d) => d.id === deviceId);
      const res = await fetch(`/api/v1/racks/${encodeURIComponent(rackId)}/devices/${encodeURIComponent(deviceId)}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": getCsrf() },
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        this.setBanner("err", d.detail || "Failed to delete device");
        return;
      }
      if (pushUndo && prev) {
        this.undoStack.push({ type: "delete", rackId, device: { ...prev } });
        this.redoStack = [];
      }
      if (this.selectedDeviceId === deviceId) this.selectedDeviceId = null;
      await this.loadAll(rackId);
      this.setBanner("ok", this.t("Device removed from rack.", "Perangkat dihapus dari rak."));
      await this.notifyPlanSync();
    }

    async undo() {
      const act = this.undoStack.pop();
      if (!act) return;
      if (act.type === "add") {
        await this.deleteDevice(act.rackId, act.device.id, false);
        this.redoStack.push(act);
      } else if (act.type === "update") {
        await this.updateDevice(act.rackId, act.deviceId, act.before, false);
        this.redoStack.push(act);
      } else if (act.type === "delete") {
        const created = await this.mountDevice(act.rackId, act.device, false);
        if (created) this.redoStack.push({ ...act, device: created });
      }
    }

    async redo() {
      const act = this.redoStack.pop();
      if (!act) return;
      if (act.type === "add") {
        const created = await this.mountDevice(act.rackId, act.device, false);
        if (created) this.undoStack.push({ ...act, device: created });
      } else if (act.type === "update") {
        await this.updateDevice(act.rackId, act.deviceId, act.after, false);
        this.undoStack.push(act);
      } else if (act.type === "delete") {
        await this.deleteDevice(act.rackId, act.device.id, false);
        this.undoStack.push(act);
      }
    }

    async createTemplate(payload) {
      const res = await fetch("/api/v1/racks/library/templates", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrf() },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        this.setBanner("err", data.detail || "Failed to save template");
        return;
      }
      this.showNewTpl = false;
      await this.loadAll(this.selectedRackId);
      this.setBanner("ok", this.t(`Saved template "${data.name}".`, `Templat "${data.name}" tersimpan.`));
    }

    async importNetbox(rawText) {
      const res = await fetch("/api/v1/racks/library/import-netbox", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrf() },
        body: JSON.stringify({ data: rawText }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        this.setBanner("err", data.detail || "NetBox import failed");
        return;
      }
      this.showNetbox = false;
      await this.loadAll(this.selectedRackId);
      this.setBanner("ok", this.t(`Imported ${data.imported} device type(s) into library.`, `Berhasil mengimpor ${data.imported} tipe perangkat ke pustaka.`));
    }

    renderElevationFace(rack, face) {
      const uMax = rack.u_height;
      const faceTitle = face === "front" ? this.t("Front Elevation", "Tampak Depan") : this.t("Rear Elevation", "Tampak Belakang");
      const devs = (rack.devices || []).filter((d) => d.face === face || d.face === "both");

      let cells = "";
      for (let u = uMax; u >= 1; u--) {
        const row = uMax - u + 1;
        cells += `<div class="rk-u-num" style="grid-row:${row};">U${u}</div>`;
        cells += `<div class="rk-u-slot" data-face="${face}" data-u="${u}" data-slot="left" style="grid-row:${row}; grid-column:2;">+ U${u}</div>`;
        cells += `<div class="rk-u-slot" data-face="${face}" data-u="${u}" data-slot="right" style="grid-row:${row}; grid-column:3;">+ U${u}</div>`;
      }

      for (const d of devs) {
        const topU = Math.min(uMax, d.u_position + d.u_height - 1);
        const startRow = uMax - topU + 1;
        const endRow = startRow + d.u_height;
        let colSpec = "2 / 4";
        if (d.half_width) {
          colSpec = d.half_slot === "right" ? "3 / 4" : "2 / 3";
        }
        const meta = typeMeta(d.device_type);
        const isSel = this.selectedDeviceId === d.id;
        cells += `
          <div class="rk-dev-block ${isSel ? "selected" : ""}"
               draggable="${this.canWrite ? "true" : "false"}"
               data-dev-id="${esc(d.id)}"
               style="grid-row:${startRow} / ${endRow}; grid-column:${colSpec}; background:${esc(d.color || meta.color)};"
               title="${esc(d.name)} · ${d.u_height}U (U${d.u_position}-U${topU}) · ${d.power_w}W · ${d.status}">
            <span style="display:flex; align-items:center; gap:5px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
              <span class="rk-dev-dot" style="background:${statusColor(d.status)}; color:${statusColor(d.status)};"></span>
              <span>${meta.icon}</span>
              <span style="overflow:hidden; text-overflow:ellipsis;">${esc(d.name)}</span>
            </span>
            <span style="font-size:0.65rem; opacity:0.9; white-space:nowrap; flex-shrink:0;">
              ${d.u_height}U${d.power_w > 0 ? ` · ${Math.round(d.power_w)}W` : ""}
            </span>
          </div>
        `;
      }

      return `
        <div class="rk-cabinet">
          <div class="rk-cabinet-head">
            <span>${faceTitle}</span>
            <span>${uMax}U · ${rack.width_in}"</span>
          </div>
          <div class="rk-u-grid">${cells}</div>
        </div>
      `;
    }

    render() {
      const rack = this.activeRack;
      const dev = this.activeDevice;
      const filteredTpls = this.templates.filter((tpl) => {
        if (!this.libFilter) return true;
        const q = this.libFilter.toLowerCase();
        return (
          tpl.name.toLowerCase().includes(q) ||
          tpl.device_type.toLowerCase().includes(q) ||
          (tpl.manufacturer || "").toLowerCase().includes(q) ||
          (tpl.model || "").toLowerCase().includes(q)
        );
      });

      const bannerHtml = this.banner
        ? `<div class="rk-alert ${this.banner.kind === "err" ? "err" : "ok"}">${esc(this.banner.text)}</div>`
        : "";

      const racksListHtml = this.racks.length
        ? this.racks
            .map((r) => {
              const u = r.utilization || {};
              return `
                <div class="rk-rack-item ${r.id === this.selectedRackId ? "active" : ""}" data-select-rack="${esc(r.id)}">
                  <div style="overflow:hidden;">
                    <div style="font-weight:700; font-size:0.82rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">🗄️ ${esc(r.name)}</div>
                    <div style="font-size:0.69rem; color:var(--text-muted);">${r.u_height}U · ${u.u_used || 0}/${r.u_height}U · ${Math.round(u.total_power_w || 0)}W</div>
                  </div>
                  ${this.canWrite ? `<button type="button" class="rk-btn danger" style="padding:2px 7px;" data-del-rack="${esc(r.id)}" title="${this.t("Delete Rack", "Hapus Rak")}">🗑️</button>` : ""}
                </div>
              `;
            })
            .join("")
        : `<div style="font-size:0.78rem; color:var(--text-muted);">${this.t("No racks yet. Create a 4U–70U rack above.", "Belum ada rak. Buat rak 4U–70U di atas.")}</div>`;

      const newRackFormHtml = this.showNewRack
        ? `
          <div style="background:var(--bg-card-inner); border:1px solid var(--border-color); border-radius:8px; padding:9px; margin-bottom:10px;">
            <div class="rk-form-grid">
              <label style="grid-column:span 2;">
                <span>${this.t("Rack Name", "Nama Rak")}</span>
                <input id="rkNewName" class="rk-input" value="Rack-${String(this.racks.length + 1).padStart(2, "0")}" />
              </label>
              <label>
                <span>${this.t("Template (4U–70U)", "Templat (4U–70U)")}</span>
                <select id="rkNewPreset" class="rk-select">
                  ${RACK_TEMPLATES_U.map((u) => `<option value="${u}" ${u === 42 ? "selected" : ""}>${u}U</option>`).join("")}
                </select>
              </label>
              <label>
                <span>${this.t("Custom U (4–70)", "Kustom U (4–70)")}</span>
                <input id="rkNewU" type="number" min="4" max="70" value="42" class="rk-input" />
              </label>
              <label>
                <span>${this.t("Width (in)", "Lebar (inci)")}</span>
                <input id="rkNewWidth" type="number" step="0.5" min="10" max="30" value="19" class="rk-input" />
              </label>
              <label>
                <span>${this.t("Depth (mm)", "Kedalaman (mm)")}</span>
                <input id="rkNewDepth" type="number" step="50" min="300" max="1600" value="1000" class="rk-input" />
              </label>
              <label>
                <span>${this.t("Max Power (W)", "Daya Maks (W)")}</span>
                <input id="rkNewPower" type="number" step="100" value="5000" class="rk-input" />
              </label>
              <label>
                <span>${this.t("Color", "Warna")}</span>
                <input id="rkNewColor" type="color" value="#1e293b" class="rk-input" style="height:30px; padding:2px;" />
              </label>
              <label>
                <span>X (m)</span>
                <input id="rkNewX" type="number" step="0.2" value="2.5" class="rk-input" />
              </label>
              <label>
                <span>Z (m)</span>
                <input id="rkNewZ" type="number" step="0.2" value="2.0" class="rk-input" />
              </label>
            </div>
            <div style="display:flex; gap:6px; justify-content:flex-end; margin-top:8px;">
              <button type="button" class="rk-btn" id="rkCancelNew">${this.t("Cancel", "Batal")}</button>
              <button type="button" class="rk-btn primary" id="rkSubmitNew">${this.t("Create & Place", "Buat & Tempatkan")}</button>
            </div>
          </div>
        `
        : "";

      let centerHtml = `<div class="rk-panel" style="text-align:center; padding:32px; color:var(--text-muted);">${this.t("Select or create a rack to view its elevation.", "Pilih atau buat rak untuk melihat tampilan elevasinya.")}</div>`;
      if (rack) {
        const u = rack.utilization || {};
        const devEditorHtml = dev
          ? `
            <div style="margin-top:12px; background:var(--bg-card-inner); border:1px solid var(--border-color); border-radius:10px; padding:10px 12px;">
              <div class="rk-title" style="margin-bottom:8px;">
                <span>✏️ ${this.t("Edit Mounted Device", "Ubah Perangkat Terpasang")}</span>
                <div style="display:flex; gap:5px;">
                  ${this.canWrite ? `<button type="button" class="rk-btn danger" id="rkBtnDelDev">🗑️ ${this.t("Remove", "Hapus")}</button>` : ""}
                  <button type="button" class="rk-btn" id="rkBtnCloseDev">✕</button>
                </div>
              </div>
              <div class="rk-form-grid">
                <label style="grid-column:span 2;"><span>${this.t("Device Name", "Nama Perangkat")}</span><input id="edDevName" class="rk-input" value="${esc(dev.name)}" /></label>
                <label><span>${this.t("Type", "Tipe")}</span>
                  <select id="edDevType" class="rk-select">
                    ${DEVICE_TYPES.map((dt) => `<option value="${dt.value}" ${dt.value === dev.device_type ? "selected" : ""}>${dt.icon} ${this.t(dt.en, dt.id)}</option>`).join("")}
                  </select>
                </label>
                <label><span>${this.t("Status", "Status")}</span>
                  <select id="edDevStatus" class="rk-select">
                    ${["active", "planned", "maintenance", "offline", "decommissioned"].map((st) => `<option value="${st}" ${st === dev.status ? "selected" : ""}>${st}</option>`).join("")}
                  </select>
                </label>
                <label><span>${this.t("Manufacturer", "Pabrikan")}</span><input id="edDevMfr" class="rk-input" value="${esc(dev.manufacturer)}" /></label>
                <label><span>${this.t("Model", "Model")}</span><input id="edDevModel" class="rk-input" value="${esc(dev.model)}" /></label>
                <label><span>${this.t("Position (Bottom U)", "Posisi (U Bawah)")}</span><input id="edDevPos" type="number" min="1" max="${rack.u_height}" class="rk-input" value="${dev.u_position}" /></label>
                <label><span>${this.t("Height (U)", "Tinggi (U)")}</span><input id="edDevH" type="number" min="1" max="${rack.u_height}" class="rk-input" value="${dev.u_height}" /></label>
                <label><span>${this.t("Face", "Sisi")}</span>
                  <select id="edDevFace" class="rk-select">
                    <option value="front" ${dev.face === "front" ? "selected" : ""}>${this.t("Front", "Depan")}</option>
                    <option value="rear" ${dev.face === "rear" ? "selected" : ""}>${this.t("Rear", "Belakang")}</option>
                    <option value="both" ${dev.face === "both" ? "selected" : ""}>${this.t("Full Depth (Both)", "Penuh (Depan & Belakang)")}</option>
                  </select>
                </label>
                <label><span>${this.t("Width Slot", "Slot Lebar")}</span>
                  <select id="edDevSlot" class="rk-select">
                    <option value="full" ${!dev.half_width ? "selected" : ""}>${this.t("Full Width (19\")", "Lebar Penuh (19\")")}</option>
                    <option value="left" ${dev.half_width && dev.half_slot === "left" ? "selected" : ""}>${this.t("Half-Width (Left)", "Setengah (Kiri)")}</option>
                    <option value="right" ${dev.half_width && dev.half_slot === "right" ? "selected" : ""}>${this.t("Half-Width (Right)", "Setengah (Kanan)")}</option>
                  </select>
                </label>
                <label><span>${this.t("Power Draw (W)", "Daya (W)")}</span><input id="edDevPower" type="number" step="5" min="0" class="rk-input" value="${dev.power_w}" /></label>
                <label><span>${this.t("Color", "Warna")}</span><input id="edDevColor" type="color" class="rk-input" style="height:30px; padding:2px;" value="${esc(dev.color || "#0284c7")}" /></label>
                <label style="grid-column:span 2;"><span>${this.t("Serial Number", "Nomor Seri")}</span><input id="edDevSerial" class="rk-input" value="${esc(dev.serial)}" /></label>
                <label style="grid-column:span 2;"><span>${this.t("Notes", "Catatan")}</span><textarea id="edDevNotes" rows="2" class="rk-textarea">${esc(dev.notes)}</textarea></label>
              </div>
              ${this.canWrite ? `<div style="display:flex; justify-content:flex-end; margin-top:8px;"><button type="button" class="rk-btn primary" id="rkBtnSaveDev">💾 ${this.t("Save Device", "Simpan Perangkat")}</button></div>` : ""}
            </div>
          `
          : "";

        centerHtml = `
          <div class="rk-panel">
            <div class="rk-title">
              <span>🗄️ ${esc(rack.name)} (${rack.u_height}U · ${rack.width_in}" · ${rack.depth_mm}mm)</span>
              <div style="display:flex; gap:5px; align-items:center; flex-wrap:wrap;">
                <button type="button" class="rk-btn" id="rkUndoBtn" ${this.undoStack.length ? "" : "disabled"}>↶ ${this.t("Undo", "Batal")}</button>
                <button type="button" class="rk-btn" id="rkRedoBtn" ${this.redoStack.length ? "" : "disabled"}>↷ ${this.t("Redo", "Ulangi")}</button>
                <a href="/api/v1/racks/export" download="racks_export.json" class="rk-btn" style="text-decoration:none;">⬇ JSON</a>
              </div>
            </div>
            ${bannerHtml}
            <div class="rk-stats">
              <div class="rk-stat-box">
                <div style="display:flex; justify-content:space-between; font-size:0.74rem;">
                  <span style="color:var(--text-muted);">${this.t("U-Space Utilization", "Penggunaan Ruang U")}</span>
                  <strong>${u.u_used || 0} / ${u.u_total || rack.u_height}U (${u.u_percent || 0}%)</strong>
                </div>
                <div class="rk-bar"><span style="width:${Math.min(100, u.u_percent || 0)}%;"></span></div>
                <div style="font-size:0.68rem; color:var(--text-muted); margin-top:3px;">${u.u_free ?? rack.u_height}U ${this.t("free", "tersedia")} · ${u.device_count || 0} ${this.t("devices", "perangkat")}</div>
              </div>
              <div class="rk-stat-box">
                <div style="display:flex; justify-content:space-between; font-size:0.74rem;">
                  <span style="color:var(--text-muted);">${this.t("Total Power Draw", "Total Konsumsi Daya")}</span>
                  <strong>${Math.round(u.total_power_w || 0)}W / ${Math.round(u.max_power_w || rack.max_power_w)}W</strong>
                </div>
                <div class="rk-bar"><span style="width:${Math.min(100, u.power_percent || 0)}%; background:${(u.power_percent || 0) > 85 ? "var(--accent-red)" : "var(--accent-amber)"};"></span></div>
                <div style="font-size:0.68rem; color:var(--text-muted); margin-top:3px;">${u.power_percent || 0}% ${this.t("of rack budget", "dari kapasitas rak")}</div>
              </div>
            </div>
            <div style="font-size:0.72rem; color:var(--text-muted); margin-bottom:8px;">
              ${this.t("Drag devices from the Library or within the rack onto any U slot. Click a device to edit.", "Seret perangkat dari Pustaka atau di dalam rak ke slot U mana saja. Klik perangkat untuk mengedit.")}
            </div>
            <div class="rk-elev-grid">
              ${this.renderElevationFace(rack, "front")}
              ${this.renderElevationFace(rack, "rear")}
            </div>
            ${devEditorHtml}
          </div>
        `;
      }

      const newTplHtml = this.showNewTpl
        ? `
          <div style="background:var(--bg-card-inner); border:1px solid var(--border-color); border-radius:8px; padding:8px; margin-bottom:8px;">
            <div class="rk-form-grid">
              <label style="grid-column:span 2;"><span>${this.t("Template Name", "Nama Templat")}</span><input id="tplName" class="rk-input" placeholder="Dell PowerEdge R750" /></label>
              <label><span>${this.t("Type", "Tipe")}</span>
                <select id="tplType" class="rk-select">${DEVICE_TYPES.map((dt) => `<option value="${dt.value}">${dt.icon} ${this.t(dt.en, dt.id)}</option>`).join("")}</select>
              </label>
              <label><span>${this.t("Height (U)", "Tinggi (U)")}</span><input id="tplU" type="number" min="1" max="70" value="2" class="rk-input" /></label>
              <label><span>${this.t("Manufacturer", "Pabrikan")}</span><input id="tplMfr" class="rk-input" placeholder="Dell" /></label>
              <label><span>${this.t("Power (W)", "Daya (W)")}</span><input id="tplPower" type="number" min="0" value="450" class="rk-input" /></label>
            </div>
            <div style="display:flex; gap:5px; justify-content:flex-end; margin-top:7px;">
              <button type="button" class="rk-btn" id="tplCancel">${this.t("Cancel", "Batal")}</button>
              <button type="button" class="rk-btn primary" id="tplSave">${this.t("Save", "Simpan")}</button>
            </div>
          </div>
        `
        : "";

      const netboxHtml = this.showNetbox
        ? `
          <div style="background:var(--bg-card-inner); border:1px solid var(--border-color); border-radius:8px; padding:8px; margin-bottom:8px;">
            <div style="font-size:0.72rem; color:var(--text-muted); margin-bottom:5px;">
              ${this.t("Paste NetBox Device-Type YAML or JSON (imported as native templates in our DB):", "Tempel YAML atau JSON Tipe Perangkat NetBox (diimpor sebagai templat asli di DB kita):")}
            </div>
            <textarea id="nbRawData" rows="5" class="rk-textarea" style="font-family:var(--font-mono); font-size:0.7rem;" placeholder="manufacturer: Cisco&#10;model: Catalyst 9300-48P&#10;u_height: 1&#10;is_full_depth: false"></textarea>
            <div style="display:flex; gap:5px; justify-content:flex-end; margin-top:6px;">
              <button type="button" class="rk-btn" id="nbCancel">${this.t("Cancel", "Batal")}</button>
              <button type="button" class="rk-btn primary" id="nbSubmit">⬆ ${this.t("Import", "Impor")}</button>
            </div>
          </div>
        `
        : "";

      this.container.innerHTML = `
        <div class="rk-shell ${this.compact ? "rk-compact" : ""}">
          <!-- Left: Rack List & 4U-70U Creator -->
          <div class="rk-panel">
            <div class="rk-title">
              <span>🗄️ ${this.t("Racks", "Daftar Rak")} (${this.racks.length})</span>
              ${this.canWrite ? `<button type="button" class="rk-btn primary" id="rkToggleNew">+ ${this.t("New Rack", "Rak Baru")}</button>` : ""}
            </div>
            ${newRackFormHtml}
            ${racksListHtml}
          </div>

          <!-- Center: Interactive Front/Rear Elevation -->
          <div>${centerHtml}</div>

          <!-- Right: Device Library & NetBox Importer -->
          <div class="rk-panel rk-col-lib">
            <div class="rk-title">
              <span>📚 ${this.t("Device Library", "Pustaka Perangkat")}</span>
              ${this.canWrite ? `
                <div style="display:flex; gap:4px;">
                  <button type="button" class="rk-btn" id="rkToggleNewTpl">+ ${this.t("Custom", "Kustom")}</button>
                  <button type="button" class="rk-btn" id="rkToggleNetbox">⬆ NetBox</button>
                </div>
              ` : ""}
            </div>
            ${newTplHtml}
            ${netboxHtml}
            <input id="rkLibSearch" class="rk-input" style="margin-bottom:8px;" placeholder="${this.t("Search device templates...", "Cari templat perangkat...")}" value="${esc(this.libFilter)}" />
            <div style="max-height:520px; overflow-y:auto;">
              ${filteredTpls
                .map((tpl) => {
                  const m = typeMeta(tpl.device_type);
                  return `
                    <div class="rk-tpl-item" draggable="${this.canWrite ? "true" : "false"}" data-tpl-id="${esc(tpl.id)}">
                      <div style="overflow:hidden;">
                        <div style="font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                          <span style="display:inline-block; width:8px; height:8px; border-radius:2px; background:${esc(tpl.color || m.color)}; margin-right:4px;"></span>
                          ${m.icon} ${esc(tpl.name)}
                        </div>
                        <div style="font-size:0.66rem; color:var(--text-muted);">
                          ${tpl.u_height}U${tpl.half_width ? " · ½W" : ""} · ${Math.round(tpl.power_w || 0)}W${tpl.manufacturer ? ` · ${esc(tpl.manufacturer)}` : ""}
                        </div>
                      </div>
                      ${this.canWrite && rack ? `<button type="button" class="rk-btn" style="padding:2px 7px;" data-quick-mount="${esc(tpl.id)}" title="${this.t("Mount at first free U", "Pasang di U kosong pertama")}">+</button>` : ""}
                    </div>
                  `;
                })
                .join("")}
            </div>
          </div>
        </div>
      `;

      this.bindEvents();
    }

    findFirstFreeSlot(rack, uHeight, face = "front", halfWidth = false) {
      for (let u = 1; u <= rack.u_height - uHeight + 1; u++) {
        const err = checkLocalOverlap(rack, {
          u_position: u,
          u_height: uHeight,
          face,
          half_width: halfWidth,
          half_slot: halfWidth ? "left" : "full",
        });
        if (!err) return { u, half_slot: halfWidth ? "left" : "full" };
        if (halfWidth) {
          const errR = checkLocalOverlap(rack, {
            u_position: u,
            u_height: uHeight,
            face,
            half_width: true,
            half_slot: "right",
          });
          if (!errR) return { u, half_slot: "right" };
        }
      }
      return null;
    }

    bindEvents() {
      const root = this.container;
      const rack = this.activeRack;

      root.querySelectorAll("[data-select-rack]").forEach((el) => {
        el.addEventListener("click", (ev) => {
          if (ev.target.closest("[data-del-rack]")) return;
          this.selectedRackId = el.dataset.selectRack;
          this.selectedDeviceId = null;
          this.banner = null;
          this.render();
        });
      });

      root.querySelectorAll("[data-del-rack]").forEach((btn) => {
        btn.addEventListener("click", (ev) => {
          ev.stopPropagation();
          this.deleteRack(btn.dataset.delRack);
        });
      });

      root.querySelector("#rkToggleNew")?.addEventListener("click", () => {
        this.showNewRack = !this.showNewRack;
        this.render();
      });
      root.querySelector("#rkCancelNew")?.addEventListener("click", () => {
        this.showNewRack = false;
        this.render();
      });
      root.querySelector("#rkNewPreset")?.addEventListener("change", (ev) => {
        const uIn = root.querySelector("#rkNewU");
        if (uIn) uIn.value = ev.target.value;
      });
      root.querySelector("#rkSubmitNew")?.addEventListener("click", () => {
        const name = root.querySelector("#rkNewName")?.value?.trim() || "Server Rack";
        const u_height = Number(root.querySelector("#rkNewU")?.value || 42);
        const width_in = Number(root.querySelector("#rkNewWidth")?.value || 19);
        const depth_mm = Number(root.querySelector("#rkNewDepth")?.value || 1000);
        const max_power_w = Number(root.querySelector("#rkNewPower")?.value || 5000);
        const color = root.querySelector("#rkNewColor")?.value || "#1e293b";
        const pos_x = Number(root.querySelector("#rkNewX")?.value || 2.5);
        const pos_z = Number(root.querySelector("#rkNewZ")?.value || 2.0);
        this.createRack({ name, u_height, width_in, depth_mm, max_power_w, color, pos_x, pos_z });
      });

      root.querySelector("#rkUndoBtn")?.addEventListener("click", () => this.undo());
      root.querySelector("#rkRedoBtn")?.addEventListener("click", () => this.redo());

      // Library search & toggles
      root.querySelector("#rkLibSearch")?.addEventListener("input", (ev) => {
        this.libFilter = ev.target.value;
        this.render();
        const inp = root.querySelector("#rkLibSearch");
        if (inp) { inp.focus(); inp.selectionStart = inp.selectionEnd = inp.value.length; }
      });
      root.querySelector("#rkToggleNewTpl")?.addEventListener("click", () => {
        this.showNewTpl = !this.showNewTpl;
        this.showNetbox = false;
        this.render();
      });
      root.querySelector("#tplCancel")?.addEventListener("click", () => {
        this.showNewTpl = false;
        this.render();
      });
      root.querySelector("#tplSave")?.addEventListener("click", () => {
        const name = root.querySelector("#tplName")?.value?.trim();
        if (!name) return;
        const device_type = root.querySelector("#tplType")?.value || "custom";
        const u_height = Number(root.querySelector("#tplU")?.value || 1);
        const manufacturer = root.querySelector("#tplMfr")?.value?.trim() || "";
        const power_w = Number(root.querySelector("#tplPower")?.value || 0);
        this.createTemplate({ name, device_type, u_height, manufacturer, model: name, power_w, color: typeMeta(device_type).color });
      });
      root.querySelector("#rkToggleNetbox")?.addEventListener("click", () => {
        this.showNetbox = !this.showNetbox;
        this.showNewTpl = false;
        this.render();
      });
      root.querySelector("#nbCancel")?.addEventListener("click", () => {
        this.showNetbox = false;
        this.render();
      });
      root.querySelector("#nbSubmit")?.addEventListener("click", () => {
        const txt = root.querySelector("#nbRawData")?.value?.trim();
        if (txt) this.importNetbox(txt);
      });

      // Quick mount from template
      root.querySelectorAll("[data-quick-mount]").forEach((btn) => {
        btn.addEventListener("click", (ev) => {
          ev.stopPropagation();
          if (!rack) return;
          const tpl = this.templates.find((x) => x.id === btn.dataset.quickMount);
          if (!tpl) return;
          const face = tpl.is_full_depth ? "both" : "front";
          const slot = this.findFirstFreeSlot(rack, tpl.u_height, face, tpl.half_width);
          if (!slot) {
            this.setBanner("err", this.t(`No free ${tpl.u_height}U space available in "${rack.name}".`, `Tidak ada ruang kosong ${tpl.u_height}U di "${rack.name}".`));
            return;
          }
          this.mountDevice(rack.id, {
            name: tpl.name,
            device_type: tpl.device_type,
            manufacturer: tpl.manufacturer,
            model: tpl.model,
            u_height: tpl.u_height,
            u_position: slot.u,
            face,
            half_width: tpl.half_width,
            half_slot: slot.half_slot,
            power_w: tpl.power_w,
            status: "active",
            color: tpl.color,
          });
        });
      });

      // Drag from template library
      root.querySelectorAll("[data-tpl-id]").forEach((el) => {
        el.addEventListener("dragstart", (ev) => {
          const tpl = this.templates.find((x) => x.id === el.dataset.tplId);
          if (!tpl) return;
          this.dragPayload = { kind: "template", tpl };
          ev.dataTransfer?.setData("text/plain", tpl.id);
        });
      });

      // Click & Drag mounted devices
      root.querySelectorAll("[data-dev-id]").forEach((el) => {
        el.addEventListener("click", (ev) => {
          ev.stopPropagation();
          this.selectedDeviceId = el.dataset.devId;
          this.render();
        });
        el.addEventListener("dragstart", (ev) => {
          if (!rack) return;
          const d = (rack.devices || []).find((x) => x.id === el.dataset.devId);
          if (!d) return;
          this.dragPayload = { kind: "device", dev: d };
          ev.dataTransfer?.setData("text/plain", d.id);
        });
      });

      // Drop onto U slots (with live green/red overlap preview!)
      root.querySelectorAll(".rk-u-slot").forEach((slotEl) => {
        slotEl.addEventListener("dragover", (ev) => {
          if (!this.canWrite || !rack || !this.dragPayload) return;
          ev.preventDefault();
          const targetU = Number(slotEl.dataset.u);
          const targetFace = slotEl.dataset.face;
          const targetHalfSlot = slotEl.dataset.slot;
          const cand =
            this.dragPayload.kind === "template"
              ? {
                  u_position: targetU,
                  u_height: this.dragPayload.tpl.u_height,
                  face: this.dragPayload.tpl.is_full_depth ? "both" : targetFace,
                  half_width: this.dragPayload.tpl.half_width,
                  half_slot: this.dragPayload.tpl.half_width ? targetHalfSlot : "full",
                }
              : {
                  u_position: targetU,
                  u_height: this.dragPayload.dev.u_height,
                  face: this.dragPayload.dev.face === "both" ? "both" : targetFace,
                  half_width: this.dragPayload.dev.half_width,
                  half_slot: this.dragPayload.dev.half_width ? targetHalfSlot : "full",
                };
          const err = checkLocalOverlap(rack, cand, this.dragPayload.kind === "device" ? this.dragPayload.dev.id : null);
          slotEl.classList.toggle("drop-ok", !err);
          slotEl.classList.toggle("drop-bad", !!err);
        });

        slotEl.addEventListener("dragleave", () => {
          slotEl.classList.remove("drop-ok", "drop-bad");
        });

        slotEl.addEventListener("drop", (ev) => {
          ev.preventDefault();
          slotEl.classList.remove("drop-ok", "drop-bad");
          if (!this.canWrite || !rack || !this.dragPayload) return;
          const targetU = Number(slotEl.dataset.u);
          const targetFace = slotEl.dataset.face;
          const targetHalfSlot = slotEl.dataset.slot;
          const payload = this.dragPayload;
          this.dragPayload = null;

          if (payload.kind === "template") {
            const tpl = payload.tpl;
            this.mountDevice(rack.id, {
              name: tpl.name,
              device_type: tpl.device_type,
              manufacturer: tpl.manufacturer,
              model: tpl.model,
              u_height: tpl.u_height,
              u_position: targetU,
              face: tpl.is_full_depth ? "both" : targetFace,
              half_width: tpl.half_width,
              half_slot: tpl.half_width ? targetHalfSlot : "full",
              power_w: tpl.power_w,
              status: "active",
              color: tpl.color,
            });
          } else if (payload.kind === "device") {
            const d = payload.dev;
            this.updateDevice(rack.id, d.id, {
              u_position: targetU,
              face: d.face === "both" ? "both" : targetFace,
              half_slot: d.half_width ? targetHalfSlot : "full",
            });
          }
        });
      });

      // Device editor actions
      root.querySelector("#rkBtnCloseDev")?.addEventListener("click", () => {
        this.selectedDeviceId = null;
        this.render();
      });
      root.querySelector("#rkBtnDelDev")?.addEventListener("click", () => {
        if (rack && this.selectedDeviceId) this.deleteDevice(rack.id, this.selectedDeviceId);
      });
      root.querySelector("#rkBtnSaveDev")?.addEventListener("click", () => {
        if (!rack || !this.selectedDeviceId) return;
        const slotSel = root.querySelector("#edDevSlot")?.value || "full";
        this.updateDevice(rack.id, this.selectedDeviceId, {
          name: root.querySelector("#edDevName")?.value?.trim(),
          device_type: root.querySelector("#edDevType")?.value,
          status: root.querySelector("#edDevStatus")?.value,
          manufacturer: root.querySelector("#edDevMfr")?.value?.trim() || "",
          model: root.querySelector("#edDevModel")?.value?.trim() || "",
          u_position: Number(root.querySelector("#edDevPos")?.value || 1),
          u_height: Number(root.querySelector("#edDevH")?.value || 1),
          face: root.querySelector("#edDevFace")?.value || "front",
          half_width: slotSel !== "full",
          half_slot: slotSel,
          power_w: Number(root.querySelector("#edDevPower")?.value || 0),
          color: root.querySelector("#edDevColor")?.value || "#0284c7",
          serial: root.querySelector("#edDevSerial")?.value?.trim() || "",
          notes: root.querySelector("#edDevNotes")?.value || "",
        });
      });
    }
  }

  window.RackElevationUI = {
    mount(container, opts) {
      const ctrl = new RackElevationController(container, opts);
      ctrl.loadAll(opts?.rackId || null);
      return ctrl;
    },
  };
})();
