/**
 * rack_elevation.js - Native Rack Elevation View, Photorealistic Front/Rear Hardware Images,
 * Brand/Category/A-Z Device Library & .fp3d-wall 3D Popup (Phase 5).
 *
 * - 100% native UI using app CSS theme variables (--bg-*, --text-*, --accent-*, --border-*).
 * - Zero iframes, zero external runtime requests.
 * - Real front & rear hardware WebP photos (MikroTik, Sangfor, Supermicro, Dell, HPE, Juniper,
 *   Cisco, Ubiquiti, APC, Fortinet, Arista, Palo Alto, Synology, QNAP, Eaton, etc.) + custom image upload.
 * - Diagonal hatched half-depth opposite-face indicator + Image / Image+Label / Label toggle + Zoom.
 */
(function () {
  const RACK_TEMPLATES_U = [4, 6, 9, 12, 18, 24, 36, 42, 48, 52, 60, 70];
  const DEVICE_TYPES = [
    { value: "server", en: "Server", id: "Server", icon: "🖥️", color: "#0284c7" },
    { value: "switch", en: "Network / Switch", id: "Jaringan / Switch", icon: "🔀", color: "#059669" },
    { value: "storage", en: "Storage", id: "Penyimpanan", icon: "💾", color: "#7c3aed" },
    { value: "ups", en: "UPS", id: "UPS", icon: "🔋", color: "#dc2626" },
    { value: "pdu", en: "PDU / Power", id: "PDU / Daya", icon: "⚡", color: "#d97706" },
    { value: "patch_panel", en: "Patch Panel", id: "Patch Panel", icon: "🔌", color: "#475569" },
    { value: "blank_panel", en: "Blank Panel", id: "Panel Kosong", icon: "▬", color: "#64748b" },
    { value: "custom", en: "Custom / Appliance", id: "Kustom / Perangkat", icon: "📦", color: "#db2777" },
  ];

  let _sharedCatalogPromise = null;
  async function fetchSharedCatalog(force = false) {
    if (!force && _sharedCatalogPromise) return _sharedCatalogPromise;
    _sharedCatalogPromise = fetch("/api/v1/racks/library/catalog")
      .then((r) => (r.ok ? r.json() : { brands: [], devices: [] }))
      .catch(() => ({ brands: [], devices: [] }));
    return _sharedCatalogPromise;
  }

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
      /* Native .fp3d-wall Glass Rack Popup Overlay (matches Neon3D camera wall style) */
      .fp3d-rack-wall {
        position: fixed;
        inset: 56px 14px 14px 14px;
        z-index: 2600;
        display: none;
        flex-direction: column;
        gap: 10px;
        padding: 12px 16px;
        border-radius: 16px;
        background: var(--bg-drawer);
        backdrop-filter: blur(18px);
        border: 1px solid var(--border-color);
        box-shadow: var(--card-shadow), 0 0 28px var(--accent-cyan-soft);
        color: var(--text-main);
        overflow: hidden;
      }
      .fp3d-rack-wall.open { display: flex; }
      .fp3d-rack-wall-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        flex-wrap: wrap;
        padding-bottom: 8px;
        border-bottom: 1px solid var(--border-color);
      }
      .fp3d-rack-wall-body {
        flex: 1;
        min-height: 0;
        overflow-y: auto;
        padding-right: 2px;
      }

      /* Shared Rack Elevation Layout */
      .rk-shell {
        display: grid;
        grid-template-columns: 310px 1fr;
        gap: 14px;
        align-items: start;
        color: var(--text-main);
        font-family: var(--font-sans);
      }
      .rk-shell.rk-view-only {
        grid-template-columns: 1fr;
      }
      @media (max-width: 960px) {
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
        flex-wrap: wrap;
      }
      .rk-tabs {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 4px;
        background: var(--bg-app);
        padding: 3px;
        border-radius: 8px;
        border: 1px solid var(--border-subtle);
        margin-bottom: 8px;
      }
      .rk-tab {
        border: none;
        background: transparent;
        color: var(--text-muted);
        padding: 5px 6px;
        border-radius: 6px;
        font-size: 0.73rem;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.15s;
      }
      .rk-tab.active {
        background: var(--accent-cyan-soft);
        color: var(--accent-cyan);
        box-shadow: inset 0 0 0 1px var(--border-color);
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
        font-size: 0.74rem;
        font-weight: 600;
        cursor: pointer;
        white-space: nowrap;
        transition: all 0.15s;
      }
      .rk-btn:hover { filter: brightness(1.1); }
      .rk-btn:disabled { opacity: 0.45; cursor: not-allowed; }
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
        grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
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
      .rk-stage {
        display: flex;
        flex-direction: column;
        align-items: center;
        overflow-x: auto;
        padding: 6px 0 12px 0;
      }
      .rk-elev-grid {
        display: grid;
        grid-template-columns: minmax(280px, 370px) minmax(280px, 370px);
        gap: 22px;
        transform-origin: top center;
        transition: transform 0.15s ease;
      }
      @media (max-width: 720px) {
        .rk-elev-grid { grid-template-columns: minmax(260px, 1fr); }
      }
      .rk-cabinet {
        background: var(--bg-surface-elevated);
        border: 8px solid var(--bg-header);
        outline: 1px solid var(--border-color);
        border-radius: 6px;
        overflow: hidden;
        box-shadow: var(--card-shadow);
      }
      .rk-cabinet-head {
        background: var(--bg-header);
        color: var(--text-muted);
        font-size: 0.74rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        padding: 6px 10px;
        text-align: center;
        border-bottom: 1px solid var(--border-subtle);
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .rk-u-grid {
        display: grid;
        grid-template-columns: 30px 1fr 1fr;
        grid-auto-rows: var(--rk-u-px, 31px);
        position: relative;
        background: var(--bg-app);
      }
      .rk-u-num {
        grid-column: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.67rem;
        font-family: var(--font-mono);
        color: var(--text-muted);
        border-right: 2px dotted var(--border-subtle);
        border-bottom: 1px solid var(--border-subtle);
        background: var(--bg-card-inner);
        user-select: none;
      }
      .rk-u-num.major {
        color: var(--text-main);
        font-weight: 700;
      }
      .rk-u-slot {
        border-bottom: 1px solid rgba(148, 163, 184, 0.12);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.62rem;
        color: transparent;
        transition: background 0.12s;
        cursor: pointer;
      }
      .rk-u-slot:hover {
        background: var(--accent-cyan-soft);
        color: var(--accent-cyan);
      }
      .rk-u-slot.drop-ok {
        background: rgba(34, 197, 94, 0.22) !important;
      }
      .rk-u-slot.drop-bad {
        background: rgba(239, 68, 68, 0.25) !important;
      }
      .rk-drop-ghost {
        z-index: 6;
        pointer-events: none;
        margin: 1px;
        border-radius: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        padding: 2px 8px;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.02em;
        backdrop-filter: blur(2px);
      }
      .rk-drop-ghost.ok {
        background: rgba(34, 197, 94, 0.34);
        border: 2px dashed var(--accent-green);
        color: #fff;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.85);
      }
      .rk-drop-ghost.bad {
        background: rgba(239, 68, 68, 0.36);
        border: 2px dashed var(--accent-red);
        color: #fff;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.85);
      }
      /* Photorealistic Hardware Block */
      .rk-dev-block {
        z-index: 3;
        position: relative;
        margin: 0.5px 1px;
        border-radius: 3px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        overflow: hidden;
        cursor: grab;
        user-select: none;
        box-shadow: inset 0 0 0 1px rgba(255,255,255,0.16);
      }
      .rk-dev-block:active { cursor: grabbing; }
      .rk-dev-block.selected {
        outline: 2px solid var(--accent-cyan);
        outline-offset: 0px;
        z-index: 5;
      }
      .rk-dev-img {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        object-fit: contain;
        object-position: center;
        background: #0b1120;
        display: block;
        pointer-events: none;
      }
      .rk-dev-overlay {
        position: relative;
        z-index: 2;
        width: 100%;
        height: 100%;
        padding: 2px 7px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 6px;
        font-size: 0.72rem;
        font-weight: 600;
        color: #ffffff;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.92), 0 0 6px rgba(0, 0, 0, 0.8);
      }
      .rk-dev-overlay.img-only {
        background: transparent;
        opacity: 0;
        transition: opacity 0.15s;
      }
      .rk-dev-block:hover .rk-dev-overlay.img-only {
        opacity: 1;
        background: rgba(5, 10, 22, 0.62);
      }
      .rk-dev-overlay.img-label {
        background: linear-gradient(90deg, rgba(5,10,22,0.72) 0%, rgba(5,10,22,0.22) 60%, rgba(5,10,22,0.68) 100%);
      }
      .rk-dev-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        flex-shrink: 0;
        box-shadow: 0 0 6px currentColor;
      }
      /* Half-depth opposite-face hatched occlusion (exact Rackula style!) */
      .rk-dev-halfdepth {
        z-index: 2;
        margin: 0.5px 1px;
        border-radius: 2px;
        background: repeating-linear-gradient(
          -45deg,
          rgba(148, 163, 184, 0.14),
          rgba(148, 163, 184, 0.14) 6px,
          rgba(15, 23, 42, 0.18) 6px,
          rgba(15, 23, 42, 0.18) 12px
        );
        border: 1px dashed var(--border-subtle);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.7rem;
        font-weight: 600;
        color: var(--text-muted);
        pointer-events: none;
        padding: 0 6px;
        text-align: center;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      /* Brand Accordion & Device Palette */
      .rk-brand-group {
        border: 1px solid var(--border-subtle);
        border-radius: 8px;
        margin-bottom: 6px;
        overflow: hidden;
        background: var(--bg-card-inner);
      }
      .rk-brand-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 7px 10px;
        font-size: 0.78rem;
        font-weight: 700;
        color: var(--text-main);
        cursor: pointer;
        user-select: none;
        background: var(--bg-surface-elevated);
      }
      .rk-brand-head:hover { color: var(--accent-cyan); }
      .rk-tpl-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 7px;
        padding: 6px 8px;
        border-top: 1px solid var(--border-subtle);
        font-size: 0.73rem;
        cursor: grab;
        background: var(--bg-card-inner);
      }
      .rk-tpl-item:hover {
        background: var(--accent-cyan-soft);
      }
      .rk-tpl-thumb {
        width: 52px;
        height: 18px;
        border-radius: 3px;
        object-fit: cover;
        background: var(--bg-app);
        border: 1px solid var(--border-subtle);
        flex-shrink: 0;
      }
      .rk-u-pill {
        font-size: 0.65rem;
        font-weight: 700;
        padding: 1px 6px;
        border-radius: 999px;
        background: var(--bg-surface-elevated);
        color: var(--text-main);
        border: 1px solid var(--border-subtle);
        white-space: nowrap;
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
      .rk-toolbar {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        flex-wrap: wrap;
        margin-top: 10px;
        padding: 5px 10px;
        background: var(--bg-card-inner);
        border: 1px solid var(--border-subtle);
        border-radius: 999px;
      }
    `;
    document.head.appendChild(style);
  }

  class RackElevationController {
    constructor(container, opts = {}) {
      this.container = container;
      this.lang = opts.lang || document.documentElement.lang || "en";
      this.isId = this.lang === "id";
      this.canWrite = opts.canWrite !== false;
      this.popupMode = Boolean(opts.popupMode); // true = opened from clicking a rack in 3D view (.fp3d-wall)
      this.editSidebarOpen = !this.popupMode;
      this.racks = [];
      this.cables = [];
      this.catalog = [];
      this.selectedRackId = opts.rackId || null;
      this.selectedDeviceId = null;
      this.dragPayload = null;
      this.banner = null;

      // Rackula-inspired sidebar state
      this.sidebarMode = "devices"; // "racks" | "devices"
      this.deviceSortTab = "brand"; // "brand" | "category" | "az"
      this.libFilter = "";
      this.expandedGroups = new Set(["MikroTik", "Sangfor", "Dell", "HPE", "Supermicro", "Ubiquiti", "Generic"]);
      this.displayMode = "image"; // "image" | "image-label" | "label"
      this.zoomPct = 100;

      this.showNewRack = false;
      this.showNewTpl = false;
      this.showNetbox = false;
      this.pendingFrontImgUrl = "";
      this.pendingRearImgUrl = "";
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

    async loadAll(selectRackId = null, forceCatalog = false) {
      try {
        const [rRes, cRes, catData] = await Promise.all([
          fetch("/api/v1/racks"),
          fetch("/api/v1/racks/cables"),
          fetchSharedCatalog(forceCatalog),
        ]);
        if (rRes.ok) {
          const data = await rRes.json();
          this.racks = data.racks || [];
        }
        if (cRes.ok) {
          const cData = await cRes.json();
          this.cables = cData.cables || [];
        }
        this.catalog = catData.devices || [];

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

    async createCable(payload) {
      const res = await fetch("/api/v1/racks/cables", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrf() },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        this.setBanner("err", data.detail || "Failed to connect cable");
        return null;
      }
      this.banner = { kind: "ok", text: this.t(`Connected ${data.label} (${data.length_m ?? "auto"}m)`, `Terhubung ${data.label} (${data.length_m ?? "auto"}m)`) };
      await this.loadAll(this.selectedRackId);
      return data;
    }

    async deleteCable(cableId) {
      const res = await fetch(`/api/v1/racks/cables/${encodeURIComponent(cableId)}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": getCsrf() },
      });
      if (!res.ok) {
        this.setBanner("err", "Failed to delete cable");
        return;
      }
      this.banner = { kind: "ok", text: this.t("Cable disconnected.", "Kabel diputuskan.") };
      await this.loadAll(this.selectedRackId);
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

    async uploadCustomImage(file, side) {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("side", side);
      const res = await fetch("/api/v1/racks/library/upload-image", {
        method: "POST",
        headers: { "X-CSRF-Token": getCsrf() },
        body: fd,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        this.setBanner("err", data.detail || "Image upload failed");
        return "";
      }
      return data.url || "";
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
      this.setBanner("ok", this.t(`Mounted "${data.name}" at U${data.u_position}.`, `"${data.name}" dipasang di U${data.u_position}.`));
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
        this.setBanner("err", data.detail || "Failed to save custom device");
        return;
      }
      this.showNewTpl = false;
      this.pendingFrontImgUrl = "";
      this.pendingRearImgUrl = "";
      this.expandedGroups.add(data.manufacturer || "Custom");
      await this.loadAll(this.selectedRackId, true);
      this.setBanner("ok", this.t(`Added custom device "${data.name}" to library.`, `Perangkat kustom "${data.name}" ditambahkan ke pustaka.`));
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
      await this.loadAll(this.selectedRackId, true);
      this.setBanner("ok", this.t(`Imported ${data.imported} device type(s) into library.`, `Berhasil mengimpor ${data.imported} tipe perangkat ke pustaka.`));
    }

    renderElevationFace(rack, face) {
      const uMax = rack.u_height;
      const faceTitle = face === "front" ? this.t("FRONT", "DEPAN") : this.t("REAR", "BELAKANG");
      const allDevs = rack.devices || [];

      let cells = "";
      for (let u = uMax; u >= 1; u--) {
        const row = uMax - u + 1;
        const isMajor = u % 5 === 0 || u === 1 || u === uMax;
        cells += `<div class="rk-u-num ${isMajor ? "major" : ""}" style="grid-row:${row};">${u}</div>`;
        cells += `<div class="rk-u-slot" data-face="${face}" data-u="${u}" data-slot="left" style="grid-row:${row}; grid-column:2;">+ U${u}</div>`;
        cells += `<div class="rk-u-slot" data-face="${face}" data-u="${u}" data-slot="right" style="grid-row:${row}; grid-column:3;">+ U${u}</div>`;
      }

      for (const d of allDevs) {
        const topU = Math.min(uMax, d.u_position + d.u_height - 1);
        const startRow = uMax - topU + 1;
        const endRow = startRow + d.u_height;
        let colSpec = "2 / 4";
        if (d.half_width) {
          colSpec = d.half_slot === "right" ? "3 / 4" : "2 / 3";
        }

        const isShownHere = d.face === face || d.face === "both";
        const isOppositeHalfDepth = !isShownHere && d.face !== "both" && !d.is_full_depth;

        if (isOppositeHalfDepth) {
          // Exact Rackula diagonal hatched block on the opposite face for half-depth devices!
          const sideLbl = d.face === "front" ? this.t("front, half depth", "depan, setengah") : this.t("rear, half depth", "belakang, setengah");
          cells += `
            <div class="rk-dev-halfdepth" style="grid-row:${startRow} / ${endRow}; grid-column:${colSpec};"
                 title="${esc(d.name)} (${sideLbl})">
              ${esc(d.name)} (${sideLbl})
            </div>
          `;
          continue;
        }
        if (!isShownHere) continue;

        const meta = typeMeta(d.device_type);
        const isSel = this.selectedDeviceId === d.id;
        const imgUrl = face === "rear"
          ? (d.rear_image || (d.face === "rear" ? d.front_image : ""))
          : (d.front_image || "");
        const showImg = this.displayMode !== "label" && Boolean(imgUrl);
        const overlayClass = showImg
          ? (this.displayMode === "image" ? "img-only" : "img-label")
          : "";

        cells += `
          <div class="rk-dev-block ${isSel ? "selected" : ""}"
               draggable="${this.canWrite ? "true" : "false"}"
               data-dev-id="${esc(d.id)}"
               style="grid-row:${startRow} / ${endRow}; grid-column:${colSpec}; background:${esc(d.color || meta.color)};"
               title="${esc(d.name)} · ${esc(d.manufacturer)} ${esc(d.model)} · ${d.u_height}U (U${d.u_position}–U${topU}) · ${d.power_w}W · ${d.status}">
            ${showImg ? `<img class="rk-dev-img" src="${esc(imgUrl)}" alt="${esc(d.name)}" loading="lazy" />` : ""}
            <div class="rk-dev-overlay ${overlayClass}">
              <span style="display:flex; align-items:center; gap:5px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                <span class="rk-dev-dot" style="background:${statusColor(d.status)}; color:${statusColor(d.status)};"></span>
                <span style="overflow:hidden; text-overflow:ellipsis;">${esc(d.name)}</span>
              </span>
              <span style="font-size:0.64rem; opacity:0.92; white-space:nowrap; flex-shrink:0;">
                ${d.u_height}U${d.power_w > 0 ? ` · ${Math.round(d.power_w)}W` : ""}
              </span>
            </div>
          </div>
        `;
      }

      const emptyHint = allDevs.length === 0 && face === "front"
        ? `<div style="position:absolute; inset:0; display:grid; place-items:center; pointer-events:none; color:var(--text-muted); font-size:0.78rem; text-align:center; padding:12px;">${this.t("Empty rack.<br/>Drag a device in from the library.", "Rak kosong.<br/>Seret perangkat dari pustaka.")}</div>`
        : "";

      return `
        <div class="rk-cabinet">
          <div class="rk-cabinet-head">
            <span>${faceTitle}</span>
            <span style="font-size:0.66rem; opacity:0.8;">${uMax}U · ${rack.width_in}"</span>
          </div>
          <div class="rk-u-grid" style="--rk-u-px:${uMax > 48 ? 22 : 28}px;">
            ${cells}
            ${emptyHint}
          </div>
        </div>
      `;
    }

    renderDeviceCatalogList(rack) {
      const q = this.libFilter.trim().toLowerCase();
      let items = this.catalog;
      if (q) {
        items = items.filter(
          (d) =>
            (d.brand || "").toLowerCase().includes(q) ||
            (d.model || "").toLowerCase().includes(q) ||
            (d.name || "").toLowerCase().includes(q) ||
            (d.device_type || "").toLowerCase().includes(q) ||
            (d.slug || "").toLowerCase().includes(q)
        );
      }

      const renderRow = (d) => {
        const displayName = d.name || d.model || d.slug;
        const depthTag = d.is_full_depth ? "" : " ½D";
        const widthTag = d.half_width ? " ½W" : "";
        return `
          <div class="rk-tpl-item" draggable="${this.canWrite ? "true" : "false"}" data-cat-slug="${esc(d.slug)}">
            ${d.front_image ? `<img class="rk-tpl-thumb" src="${esc(d.front_image)}" alt="" loading="lazy" />` : `<span class="rk-tpl-thumb" style="background:${esc(d.color)};"></span>`}
            <div style="flex:1; min-width:0;">
              <div style="font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${esc(d.brand)} ${esc(displayName)}">${esc(displayName)}</div>
              <div style="font-size:0.64rem; color:var(--text-muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                ${esc(d.brand)}${d.rear_image ? " · 📷 Front+Rear" : ""}${depthTag}${widthTag}
              </div>
            </div>
            <span class="rk-u-pill">${d.u_height}U</span>
            ${this.canWrite && rack ? `<button type="button" class="rk-btn" style="padding:2px 7px;" data-quick-mount-slug="${esc(d.slug)}" title="${this.t("Mount at first free U", "Pasang di U kosong pertama")}">+</button>` : ""}
          </div>
        `;
      };

      if (this.deviceSortTab === "az") {
        const sorted = [...items].sort((a, b) => (a.model || a.name || "").localeCompare(b.model || b.name || "")).slice(0, 120);
        return sorted.length
          ? `<div class="rk-brand-group">${sorted.map(renderRow).join("")}</div>`
          : `<div style="font-size:0.76rem; color:var(--text-muted); padding:10px;">${this.t("No matching devices.", "Tidak ada perangkat yang cocok.")}</div>`;
      }

      const groups = new Map();
      for (const d of items) {
        const key = this.deviceSortTab === "category"
          ? this.t(typeMeta(d.device_type).en, typeMeta(d.device_type).id)
          : (d.brand || "Generic");
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(d);
      }

      // Put priority enterprise brands near the top when searching isn't active
      const priority = ["MikroTik", "Sangfor", "Supermicro", "Dell", "HPE", "Juniper", "Ubiquiti", "Cisco", "Fortinet", "Palo Alto", "Arista", "APC", "Eaton", "Synology", "QNAP", "Generic"];
      const keys = [...groups.keys()].sort((a, b) => {
        if (this.deviceSortTab === "brand") {
          const ia = priority.indexOf(a), ib = priority.indexOf(b);
          if (ia !== -1 || ib !== -1) return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
        }
        return a.localeCompare(b);
      });

      if (!keys.length) {
        return `<div style="font-size:0.76rem; color:var(--text-muted); padding:10px;">${this.t("No matching devices.", "Tidak ada perangkat yang cocok.")}</div>`;
      }

      return keys
        .map((k) => {
          const arr = groups.get(k);
          const isOpen = Boolean(q) || this.expandedGroups.has(k);
          // Show devices with real photos first inside each brand
          const ordered = [...arr].sort((a, b) => Number(!!b.rear_image) - Number(!!a.rear_image) || Number(!!b.has_real_image) - Number(!!a.has_real_image) || (a.model || "").localeCompare(b.model || ""));
          return `
            <div class="rk-brand-group">
              <div class="rk-brand-head" data-toggle-group="${esc(k)}">
                <span>${isOpen ? "▾" : "▸"} ${esc(k)}</span>
                <span style="font-size:0.68rem; color:var(--text-muted);">(${arr.length})</span>
              </div>
              ${isOpen ? `<div>${ordered.slice(0, 60).map(renderRow).join("")}</div>` : ""}
            </div>
          `;
        })
        .join("");
    }

    render() {
      const rack = this.activeRack;
      const dev = this.activeDevice;
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
              <label><span>${this.t("Width (in)", "Lebar (inci)")}</span><input id="rkNewWidth" type="number" step="0.5" min="10" max="30" value="19" class="rk-input" /></label>
              <label><span>${this.t("Depth (mm)", "Kedalaman (mm)")}</span><input id="rkNewDepth" type="number" step="50" min="300" max="1600" value="1000" class="rk-input" /></label>
              <label><span>${this.t("Max Power (W)", "Daya Maks (W)")}</span><input id="rkNewPower" type="number" step="100" value="5000" class="rk-input" /></label>
              <label><span>${this.t("Color", "Warna")}</span><input id="rkNewColor" type="color" value="#1e293b" class="rk-input" style="height:30px; padding:2px;" /></label>
              <label><span>X (m)</span><input id="rkNewX" type="number" step="0.2" value="2.5" class="rk-input" /></label>
              <label><span>Z (m)</span><input id="rkNewZ" type="number" step="0.2" value="2.0" class="rk-input" /></label>
            </div>
            <div style="display:flex; gap:6px; justify-content:flex-end; margin-top:8px;">
              <button type="button" class="rk-btn" id="rkCancelNew">${this.t("Cancel", "Batal")}</button>
              <button type="button" class="rk-btn primary" id="rkSubmitNew">${this.t("Create & Place", "Buat & Tempatkan")}</button>
            </div>
          </div>
        `
        : "";

      const newTplHtml = this.showNewTpl
        ? `
          <div style="background:var(--bg-card-inner); border:1px solid var(--border-color); border-radius:8px; padding:9px; margin-bottom:8px;">
            <div class="rk-form-grid">
              <label style="grid-column:span 2;"><span>${this.t("Device Model / Name", "Nama / Model Perangkat")}</span><input id="tplName" class="rk-input" placeholder="e.g. Sangfor NGAF M5600 / Custom Server" /></label>
              <label><span>${this.t("Brand / Manufacturer", "Merek / Pabrikan")}</span><input id="tplMfr" class="rk-input" placeholder="e.g. Sangfor, MikroTik" /></label>
              <label><span>${this.t("Category", "Kategori")}</span>
                <select id="tplType" class="rk-select">${DEVICE_TYPES.map((dt) => `<option value="${dt.value}">${dt.icon} ${this.t(dt.en, dt.id)}</option>`).join("")}</select>
              </label>
              <label><span>${this.t("Height (U)", "Tinggi (U)")}</span><input id="tplU" type="number" min="1" max="70" value="1" class="rk-input" /></label>
              <label><span>${this.t("Power (W)", "Daya (W)")}</span><input id="tplPower" type="number" min="0" value="150" class="rk-input" /></label>
              <label><span>${this.t("Front Photo (PNG/JPG/WebP)", "Foto Depan")}</span><input id="tplFrontFile" type="file" accept=".png,.jpg,.jpeg,.webp" class="rk-input" style="font-size:0.68rem;" /></label>
              <label><span>${this.t("Rear Photo (Optional)", "Foto Belakang (Opsional)")}</span><input id="tplRearFile" type="file" accept=".png,.jpg,.jpeg,.webp" class="rk-input" style="font-size:0.68rem;" /></label>
            </div>
            <div style="display:flex; gap:5px; justify-content:flex-end; margin-top:7px;">
              <button type="button" class="rk-btn" id="tplCancel">${this.t("Cancel", "Batal")}</button>
              <button type="button" class="rk-btn primary" id="tplSave">${this.t("Save Custom Device", "Simpan Perangkat")}</button>
            </div>
          </div>
        `
        : "";

      const netboxHtml = this.showNetbox
        ? `
          <div style="background:var(--bg-card-inner); border:1px solid var(--border-color); border-radius:8px; padding:8px; margin-bottom:8px;">
            <div style="font-size:0.71rem; color:var(--text-muted); margin-bottom:5px;">
              ${this.t("Paste NetBox Device-Type YAML/JSON (imported natively into our DB):", "Tempel YAML/JSON Tipe Perangkat NetBox (diimpor ke DB kita):")}
            </div>
            <textarea id="nbRawData" rows="4" class="rk-textarea" style="font-family:var(--font-mono); font-size:0.7rem;" placeholder="manufacturer: Cisco&#10;model: Catalyst 9300-48P&#10;u_height: 1&#10;is_full_depth: false"></textarea>
            <div style="display:flex; gap:5px; justify-content:flex-end; margin-top:6px;">
              <button type="button" class="rk-btn" id="nbCancel">${this.t("Cancel", "Batal")}</button>
              <button type="button" class="rk-btn primary" id="nbSubmit">⬆ ${this.t("Import", "Impor")}</button>
            </div>
          </div>
        `
        : "";

      const sidebarHtml = this.editSidebarOpen
        ? `
          <div class="rk-panel" style="display:flex; flex-direction:column; max-height:calc(100vh - 120px);">
            <div class="rk-tabs" style="grid-template-columns:1fr 1fr;">
              <button type="button" class="rk-tab ${this.sidebarMode === "racks" ? "active" : ""}" data-sb-mode="racks">🗄️ ${this.t("Racks", "Rak")} (${this.racks.length})</button>
              <button type="button" class="rk-tab ${this.sidebarMode === "devices" ? "active" : ""}" data-sb-mode="devices">📦 ${this.t("Devices", "Perangkat")} (${this.catalog.length})</button>
            </div>
            ${this.sidebarMode === "racks" ? `
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size:0.74rem; color:var(--text-muted);">${this.t("4U–70U Rack Templates", "Templat Rak 4U–70U")}</span>
                ${this.canWrite ? `<button type="button" class="rk-btn primary" id="rkToggleNew">+ ${this.t("New Rack", "Rak Baru")}</button>` : ""}
              </div>
              ${newRackFormHtml}
              <div style="overflow-y:auto; flex:1;">${racksListHtml}</div>
            ` : `
              <div class="rk-tabs">
                <button type="button" class="rk-tab ${this.deviceSortTab === "brand" ? "active" : ""}" data-sort-tab="brand">${this.t("Brand", "Merek")}</button>
                <button type="button" class="rk-tab ${this.deviceSortTab === "category" ? "active" : ""}" data-sort-tab="category">${this.t("Category", "Kategori")}</button>
                <button type="button" class="rk-tab ${this.deviceSortTab === "az" ? "active" : ""}" data-sort-tab="az">A–Z</button>
              </div>
              <input id="rkLibSearch" class="rk-input" style="margin-bottom:8px;" placeholder="${this.t("Search MikroTik, Sangfor, Dell, HPE, Juniper...", "Cari MikroTik, Sangfor, Dell, HPE, Juniper...")}" value="${esc(this.libFilter)}" />
              ${newTplHtml}
              ${netboxHtml}
              <div style="overflow-y:auto; flex:1; padding-right:2px;">
                ${this.renderDeviceCatalogList(rack)}
              </div>
              ${this.canWrite ? `
                <div style="display:flex; gap:6px; margin-top:8px; padding-top:8px; border-top:1px solid var(--border-subtle);">
                  <button type="button" class="rk-btn primary" style="flex:1;" id="rkToggleNewTpl">+ ${this.t("Add custom device", "Tambah kustom")}</button>
                  <button type="button" class="rk-btn" id="rkToggleNetbox">⬆ NetBox</button>
                </div>
              ` : ""}
            `}
          </div>
        `
        : "";

      let centerHtml = `<div class="rk-panel" style="text-align:center; padding:32px; color:var(--text-muted);">${this.t("Select or create a rack to view its front & rear hardware elevation.", "Pilih atau buat rak untuk melihat elevasi perangkat depan & belakang.")}</div>`;
      if (rack) {
        const u = rack.utilization || {};
        const devCables = dev
          ? (this.cables || []).filter((c) => c.a_device_id === dev.id || c.b_device_id === dev.id)
          : [];
        const allDevicesFlat = [];
        for (const rk of this.racks) {
          for (const d of rk.devices || []) {
            allDevicesFlat.push({ rackId: rk.id, rackName: rk.name, dev: d });
          }
        }
        const devCablesRowsHtml = devCables.length
          ? devCables
              .map((c) => {
                const isA = c.a_device_id === dev.id;
                const localPort = isA ? c.a_port : c.b_port;
                const localSide = isA ? c.a_port_side : c.b_port_side;
                const remRack = isA ? c.b_rack_name : c.a_rack_name;
                const remDev = isA ? c.b_device_name : c.a_device_name;
                const remPort = isA ? c.b_port : c.a_port;
                const remSide = isA ? c.b_port_side : c.a_port_side;
                return `
                  <div style="display:flex; align-items:center; justify-content:space-between; gap:6px; padding:6px 8px; border:1px solid var(--border-subtle); border-radius:7px; background:var(--bg-app); font-size:0.74rem; margin-bottom:5px; flex-wrap:wrap;">
                    <div style="display:flex; align-items:center; gap:6px; flex:1; min-width:180px;">
                      <span style="width:10px; height:10px; border-radius:999px; background:${esc(c.color || "#22c55e")}; flex-shrink:0;"></span>
                      <div>
                        <strong>${esc(localPort)}</strong>${localSide === "rear" ? ' <span style="font-size:0.65rem; color:var(--text-muted);">[rear]</span>' : ""}
                        <span style="color:var(--text-muted);">→ ${esc(c.label)} (${esc(c.cable_type)}${c.length_m != null ? " · " + c.length_m + "m" : ""}) →</span>
                        <strong>${esc(remDev || "Device")}</strong> <span style="color:var(--accent-cyan);">${esc(remPort)}${remSide === "rear" ? " [rear]" : ""}</span>
                        ${remRack ? `<span style="font-size:0.68rem; color:var(--text-muted);">(${esc(remRack)})</span>` : ""}
                      </div>
                    </div>
                    <div style="display:flex; gap:4px; flex-shrink:0;">
                      <button type="button" class="rk-btn primary" data-trace-port="${esc(localPort)}" title="${this.t("Trace end-to-end cable path", "Lacak jalur kabel ujung-ke-ujung")}">🔍 ${this.t("Trace", "Lacak")}</button>
                      ${this.canWrite && !c.from_3d_plan ? `<button type="button" class="rk-btn danger" data-del-cable="${esc(c.id)}" title="${this.t("Disconnect cable", "Putuskan kabel")}">🗑️</button>` : ""}
                    </div>
                  </div>
                `;
              })
              .join("")
          : `<div style="font-size:0.73rem; color:var(--text-muted); padding:4px 0;">${this.t("No cables connected to this device yet.", "Belum ada kabel terhubung ke perangkat ini.")}</div>`;

        const devEditorHtml = dev
          ? `
            <div style="margin-top:12px; background:var(--bg-card-inner); border:1px solid var(--border-color); border-radius:10px; padding:10px 12px;">
              <div class="rk-title" style="margin-bottom:8px;">
                <span>✏️ ${this.t("Edit Mounted Device", "Ubah Perangkat Terpasang")} — ${esc(dev.name)}</span>
                <div style="display:flex; gap:5px; flex-wrap:wrap;">
                  <button type="button" class="rk-btn primary" id="rkBtnTraceDev">🔗 ${this.t("Cable Trace", "Jejak Kabel")}</button>
                  ${this.canWrite ? `<button type="button" class="rk-btn danger" id="rkBtnDelDev">🗑️ ${this.t("Remove", "Hapus")}</button>` : ""}
                  <button type="button" class="rk-btn" id="rkBtnCloseDev">✕</button>
                </div>
              </div>
              <div class="rk-form-grid">
                <label style="grid-column:span 2;"><span>${this.t("Device Name", "Nama Perangkat")}</span><input id="edDevName" class="rk-input" value="${esc(dev.name)}" /></label>
                <label><span>${this.t("Category", "Kategori")}</span>
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
                <label><span>${this.t("Face / Depth", "Sisi / Kedalaman")}</span>
                  <select id="edDevFace" class="rk-select">
                    <option value="both" ${dev.face === "both" ? "selected" : ""}>${this.t("Full Depth (Front + Rear)", "Penuh (Depan + Belakang)")}</option>
                    <option value="front" ${dev.face === "front" ? "selected" : ""}>${this.t("Front (Half Depth)", "Depan (Setengah)")}</option>
                    <option value="rear" ${dev.face === "rear" ? "selected" : ""}>${this.t("Rear (Half Depth)", "Belakang (Setengah)")}</option>
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
                <label><span>${this.t("Fallback Color", "Warna Cadangan")}</span><input id="edDevColor" type="color" class="rk-input" style="height:30px; padding:2px;" value="${esc(dev.color || "#0284c7")}" /></label>
                <label><span>${this.t("Front Image URL", "URL Foto Depan")}</span><input id="edDevFrontImg" class="rk-input" value="${esc(dev.front_image)}" placeholder="/static/rack_assets/..." /></label>
                <label><span>${this.t("Rear Image URL", "URL Foto Belakang")}</span><input id="edDevRearImg" class="rk-input" value="${esc(dev.rear_image)}" placeholder="/static/rack_assets/..." /></label>
                <label style="grid-column:span 2;"><span>${this.t("Serial Number", "Nomor Seri")}</span><input id="edDevSerial" class="rk-input" value="${esc(dev.serial)}" /></label>
                <label style="grid-column:span 2;"><span>${this.t("Notes", "Catatan")}</span><textarea id="edDevNotes" rows="2" class="rk-textarea">${esc(dev.notes)}</textarea></label>
              </div>
              ${this.canWrite ? `<div style="display:flex; justify-content:flex-end; margin-top:8px;"><button type="button" class="rk-btn primary" id="rkBtnSaveDev">💾 ${this.t("Save Device", "Simpan Perangkat")}</button></div>` : ""}

              <!-- Port-to-Port Cable Connections & NetBox-Style Trace -->
              <div style="margin-top:12px; padding-top:10px; border-top:1px solid var(--border-color);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; gap:6px; flex-wrap:wrap;">
                  <strong style="font-size:0.78rem; color:var(--accent-cyan);">🔗 ${this.t("Cable Connections & Trace", "Koneksi Kabel & Pelacakan")} (${devCables.length})</strong>
                  ${devCables.length ? `<button type="button" class="rk-btn" id="rkBtnTraceAll">🔍 ${this.t("View Full SVG Trace", "Lihat Jejak SVG")}</button>` : ""}
                </div>
                <div>${devCablesRowsHtml}</div>
                ${this.canWrite ? `
                  <div style="margin-top:8px; padding:8px; border:1px dashed var(--border-color); border-radius:8px; background:var(--bg-app);">
                    <div style="font-size:0.72rem; font-weight:700; color:var(--text-muted); margin-bottom:6px;">+ ${this.t("Connect Port to Another Device / Patch Panel", "Hubungkan Port ke Perangkat / Patch Panel Lain")}</div>
                    <div class="rk-form-grid">
                      <label><span>${this.t("Local Port (A)", "Port Lokal (A)")}</span><input id="cabAPort" class="rk-input" placeholder="ge-0/0/0 / Port 1 / Rear Splice" value="ge-0/0/0" /></label>
                      <label><span>${this.t("Local Side", "Sisi Lokal")}</span>
                        <select id="cabASide" class="rk-select">
                          <option value="front">${this.t("Front", "Depan")}</option>
                          <option value="rear">${this.t("Rear", "Belakang")}</option>
                        </select>
                      </label>
                      <label style="grid-column:span 2;"><span>${this.t("Target Device (B)", "Perangkat Tujuan (B)")}</span>
                        <select id="cabBDev" class="rk-select">
                          ${allDevicesFlat.map((x) => `<option value="${esc(x.dev.id)}">${esc(x.rackName)} · U${x.dev.u_position} — ${esc(x.dev.name)} (${esc(x.dev.device_type)})</option>`).join("")}
                        </select>
                      </label>
                      <label><span>${this.t("Target Port (B)", "Port Tujuan (B)")}</span><input id="cabBPort" class="rk-input" placeholder="Port 1 / ge-0/0/1 / Rear Splice" value="Port 1" /></label>
                      <label><span>${this.t("Target Side", "Sisi Tujuan")}</span>
                        <select id="cabBSide" class="rk-select">
                          <option value="front">${this.t("Front", "Depan")}</option>
                          <option value="rear">${this.t("Rear", "Belakang")}</option>
                        </select>
                      </label>
                      <label><span>${this.t("Cable Label", "Label Kabel")}</span><input id="cabLabel" class="rk-input" placeholder="Cable #101" /></label>
                      <label><span>${this.t("Type & Color", "Tipe & Warna")}</span>
                        <div style="display:flex; gap:5px;">
                          <select id="cabType" class="rk-select" style="flex:1;">
                            <option value="fiber">💎 Fiber</option>
                            <option value="ethernet">🌐 Ethernet</option>
                            <option value="dac">⚡ DAC</option>
                            <option value="power">🔌 Power</option>
                            <option value="console">🖥️ Console</option>
                          </select>
                          <input id="cabColor" type="color" value="#22c55e" class="rk-input" style="width:36px; height:30px; padding:2px;" />
                        </div>
                      </label>
                    </div>
                    <div style="display:flex; justify-content:flex-end; margin-top:7px;">
                      <button type="button" class="rk-btn primary" id="rkBtnAddCable">🔗 ${this.t("Connect Cable", "Hubungkan Kabel")}</button>
                    </div>
                  </div>
                ` : ""}
              </div>
            </div>
          `
          : "";

        centerHtml = `
          <div class="rk-panel">
            <div class="rk-title">
              <span>🗄️ ${esc(rack.name)} (${rack.u_height}U · ${rack.width_in}" · ${rack.depth_mm}mm)</span>
              <div style="display:flex; gap:5px; align-items:center; flex-wrap:wrap;">
                ${this.popupMode ? `<button type="button" class="rk-btn ${this.editSidebarOpen ? "primary" : ""}" id="rkToggleEditSidebar">${this.editSidebarOpen ? "✕ " + this.t("Hide Library", "Tutup Pustaka") : "✏️ " + this.t("Edit / Add Devices", "Edit / Tambah Perangkat")}</button>` : ""}
                <button type="button" class="rk-btn" id="rkUndoBtn" ${this.undoStack.length ? "" : "disabled"} title="Undo">↶</button>
                <button type="button" class="rk-btn" id="rkRedoBtn" ${this.redoStack.length ? "" : "disabled"} title="Redo">↷</button>
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

            <div class="rk-stage">
              <div class="rk-elev-grid" style="transform:scale(${this.zoomPct / 100});">
                ${this.renderElevationFace(rack, "front")}
                ${this.renderElevationFace(rack, "rear")}
              </div>
              <div class="rk-toolbar">
                <button type="button" class="rk-btn" id="rkZoomOut" title="Zoom Out">−</button>
                <span style="font-size:0.72rem; font-weight:700; min-width:42px; text-align:center;">${this.zoomPct}%</span>
                <button type="button" class="rk-btn" id="rkZoomIn" title="Zoom In">+</button>
                <span style="width:1px; height:16px; background:var(--border-subtle); margin:0 2px;"></span>
                <button type="button" class="rk-btn ${this.displayMode === "image" ? "primary" : ""}" data-disp-mode="image" title="Photorealistic Hardware Images">🖼️ ${this.t("Image", "Gambar")}</button>
                <button type="button" class="rk-btn ${this.displayMode === "image-label" ? "primary" : ""}" data-disp-mode="image-label" title="Image + Labels">🖼️+T</button>
                <button type="button" class="rk-btn ${this.displayMode === "label" ? "primary" : ""}" data-disp-mode="label" title="Color-Coded Labels Only">T</button>
              </div>
            </div>
            ${devEditorHtml}
          </div>
        `;
      }

      this.container.innerHTML = `
        <div class="rk-shell ${this.editSidebarOpen ? "" : "rk-view-only"}">
          ${sidebarHtml}
          <div>${centerHtml}</div>
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

    buildMountPayloadFromCatalog(item, uPos, face, halfSlot) {
      const displayName = item.name || `${item.brand && item.brand !== "Generic" ? item.brand + " " : ""}${item.model}`;
      const isFull = item.is_full_depth !== false;
      return {
        name: displayName.slice(0, 120),
        device_type: item.device_type || "server",
        manufacturer: item.brand || item.manufacturer || "",
        model: item.model || displayName,
        slug: item.slug || "",
        u_height: item.u_height || 1,
        u_position: uPos,
        face: isFull ? "both" : face,
        is_full_depth: isFull,
        half_width: Boolean(item.half_width),
        half_slot: item.half_width ? (halfSlot || "left") : "full",
        power_w: Number(item.power_w || 0),
        status: "active",
        color: item.color || typeMeta(item.device_type).color,
        front_image: item.front_image || "",
        rear_image: item.rear_image || "",
      };
    }

    bindEvents() {
      const root = this.container;
      const rack = this.activeRack;

      // Sidebar mode tabs (Racks / Devices)
      root.querySelectorAll("[data-sb-mode]").forEach((btn) => {
        btn.addEventListener("click", () => {
          this.sidebarMode = btn.dataset.sbMode;
          this.render();
        });
      });

      // Device sort tabs (Brand / Category / A-Z)
      root.querySelectorAll("[data-sort-tab]").forEach((btn) => {
        btn.addEventListener("click", () => {
          this.deviceSortTab = btn.dataset.sortTab;
          this.render();
        });
      });

      // Brand / Category group accordions
      root.querySelectorAll("[data-toggle-group]").forEach((hdr) => {
        hdr.addEventListener("click", () => {
          const g = hdr.dataset.toggleGroup;
          if (this.expandedGroups.has(g)) this.expandedGroups.delete(g);
          else this.expandedGroups.add(g);
          this.render();
        });
      });

      // Popup edit sidebar toggle
      root.querySelector("#rkToggleEditSidebar")?.addEventListener("click", () => {
        this.editSidebarOpen = !this.editSidebarOpen;
        this.render();
      });

      // Zoom & display mode toolbar
      root.querySelector("#rkZoomOut")?.addEventListener("click", () => {
        this.zoomPct = Math.max(70, this.zoomPct - 10);
        this.render();
      });
      root.querySelector("#rkZoomIn")?.addEventListener("click", () => {
        this.zoomPct = Math.min(140, this.zoomPct + 10);
        this.render();
      });
      root.querySelectorAll("[data-disp-mode]").forEach((btn) => {
        btn.addEventListener("click", () => {
          this.displayMode = btn.dataset.dispMode;
          this.render();
        });
      });

      // Rack list selection & deletion
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

      // New Rack form
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

      // Library search & custom device form
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
      root.querySelector("#tplSave")?.addEventListener("click", async () => {
        const name = root.querySelector("#tplName")?.value?.trim();
        if (!name) return;
        const device_type = root.querySelector("#tplType")?.value || "custom";
        const u_height = Number(root.querySelector("#tplU")?.value || 1);
        const manufacturer = root.querySelector("#tplMfr")?.value?.trim() || "Custom";
        const power_w = Number(root.querySelector("#tplPower")?.value || 0);
        const fFile = root.querySelector("#tplFrontFile")?.files?.[0];
        const rFile = root.querySelector("#tplRearFile")?.files?.[0];
        let front_image = "";
        let rear_image = "";
        if (fFile) front_image = await this.uploadCustomImage(fFile, "front");
        if (rFile) rear_image = await this.uploadCustomImage(rFile, "rear");
        await this.createTemplate({
          name,
          device_type,
          u_height,
          manufacturer,
          model: name,
          power_w,
          color: typeMeta(device_type).color,
          front_image,
          rear_image,
        });
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

      // Quick mount from catalog
      root.querySelectorAll("[data-quick-mount-slug]").forEach((btn) => {
        btn.addEventListener("click", (ev) => {
          ev.stopPropagation();
          if (!rack) return;
          const item = this.catalog.find((x) => x.slug === btn.dataset.quickMountSlug);
          if (!item) return;
          const face = item.is_full_depth !== false ? "both" : "front";
          const slot = this.findFirstFreeSlot(rack, item.u_height, face, item.half_width);
          if (!slot) {
            this.setBanner("err", this.t(`No free ${item.u_height}U space available in "${rack.name}".`, `Tidak ada ruang kosong ${item.u_height}U di "${rack.name}".`));
            return;
          }
          this.mountDevice(rack.id, this.buildMountPayloadFromCatalog(item, slot.u, face, slot.half_slot));
        });
      });

      // Drag from catalog
      root.querySelectorAll("[data-cat-slug]").forEach((el) => {
        el.addEventListener("dragstart", (ev) => {
          const item = this.catalog.find((x) => x.slug === el.dataset.catSlug);
          if (!item) return;
          this.dragPayload = { kind: "catalog", item };
          ev.dataTransfer?.setData("text/plain", item.slug);
        });
      });

      // Click & drag mounted devices
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

      // Multi-U drag-and-drop preview helper (highlights ALL U slots of 2U/3U/4U+ devices + live ghost block)
      const clearDropPreview = () => {
        root.querySelectorAll(".rk-u-slot.drop-ok, .rk-u-slot.drop-bad").forEach((el) => {
          el.classList.remove("drop-ok", "drop-bad");
        });
        root.querySelectorAll(".rk-drop-ghost").forEach((el) => el.remove());
      };

      root.querySelectorAll("[data-cat-slug], [data-dev-id]").forEach((el) => {
        el.addEventListener("dragend", clearDropPreview);
      });
      root.querySelectorAll(".rk-u-grid").forEach((gridEl) => {
        gridEl.addEventListener("dragleave", (ev) => {
          if (!gridEl.contains(ev.relatedTarget)) clearDropPreview();
        });
      });

      // Drop onto U slots with exact multi-U height preview & green/red overlap validation
      root.querySelectorAll(".rk-u-slot").forEach((slotEl) => {
        slotEl.addEventListener("dragover", (ev) => {
          if (!this.canWrite || !rack || !this.dragPayload) return;
          ev.preventDefault();
          const targetU = Number(slotEl.dataset.u);
          const targetFace = slotEl.dataset.face;
          const targetHalfSlot = slotEl.dataset.slot;
          const isCat = this.dragPayload.kind === "catalog";
          const uH = Math.max(1, Number((isCat ? this.dragPayload.item.u_height : this.dragPayload.dev.u_height) || 1));
          const devName = isCat ? (this.dragPayload.item.model || this.dragPayload.item.name) : this.dragPayload.dev.name;
          const cand = isCat
            ? {
                u_position: targetU,
                u_height: uH,
                face: this.dragPayload.item.is_full_depth !== false ? "both" : targetFace,
                half_width: Boolean(this.dragPayload.item.half_width),
                half_slot: this.dragPayload.item.half_width ? targetHalfSlot : "full",
              }
            : {
                u_position: targetU,
                u_height: uH,
                face: this.dragPayload.dev.face === "both" ? "both" : targetFace,
                half_width: this.dragPayload.dev.half_width,
                half_slot: this.dragPayload.dev.half_width ? targetHalfSlot : "full",
              };
          const err = checkLocalOverlap(rack, cand, isCat ? null : this.dragPayload.dev.id);
          const ok = !err;

          clearDropPreview();
          const uMax = rack.u_height;
          const topU = targetU + uH - 1;
          const clampedTop = Math.min(uMax, topU);
          const spanRows = Math.max(1, clampedTop - targetU + 1);
          const startRow = uMax - clampedTop + 1;
          const gridEl = slotEl.closest(".rk-u-grid");

          if (gridEl) {
            for (let u = targetU; u <= clampedTop; u++) {
              const slotsToMark = cand.half_width ? [cand.half_slot] : ["left", "right"];
              for (const sl of slotsToMark) {
                const cell = gridEl.querySelector(`.rk-u-slot[data-face="${targetFace}"][data-u="${u}"][data-slot="${sl}"]`);
                if (cell) cell.classList.add(ok ? "drop-ok" : "drop-bad");
              }
            }
            const ghost = document.createElement("div");
            ghost.className = `rk-drop-ghost ${ok ? "ok" : "bad"}`;
            const colSpec = cand.half_width ? (cand.half_slot === "right" ? "3 / 4" : "2 / 3") : "2 / 4";
            ghost.style.gridRow = `${startRow} / span ${spanRows}`;
            ghost.style.gridColumn = colSpec;
            const rangeLbl = uH > 1 ? `U${targetU}–U${topU}` : `U${targetU}`;
            ghost.textContent = ok
              ? `${devName} · ${uH}U (${rangeLbl})`
              : `⚠ ${uH}U (${rangeLbl}) — ${err}`;
            gridEl.appendChild(ghost);
          }
        });

        slotEl.addEventListener("drop", (ev) => {
          ev.preventDefault();
          clearDropPreview();
          if (!this.canWrite || !rack || !this.dragPayload) return;
          const targetU = Number(slotEl.dataset.u);
          const targetFace = slotEl.dataset.face;
          const targetHalfSlot = slotEl.dataset.slot;
          const payload = this.dragPayload;
          this.dragPayload = null;

          if (payload.kind === "catalog") {
            this.mountDevice(rack.id, this.buildMountPayloadFromCatalog(payload.item, targetU, targetFace, targetHalfSlot));
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

      // Mounted device editor + Cable Connections & Trace
      root.querySelector("#rkBtnTraceDev")?.addEventListener("click", () => {
        if (this.selectedDeviceId) window.RackCableTraceUI?.open(this.selectedDeviceId, null, { lang: this.lang });
      });
      root.querySelector("#rkBtnTraceAll")?.addEventListener("click", () => {
        if (this.selectedDeviceId) window.RackCableTraceUI?.open(this.selectedDeviceId, null, { lang: this.lang });
      });
      root.querySelectorAll("[data-trace-port]").forEach((btn) => {
        btn.addEventListener("click", () => {
          if (this.selectedDeviceId) {
            window.RackCableTraceUI?.open(this.selectedDeviceId, btn.dataset.tracePort || null, { lang: this.lang });
          }
        });
      });
      root.querySelectorAll("[data-del-cable]").forEach((btn) => {
        btn.addEventListener("click", () => {
          if (btn.dataset.delCable) this.deleteCable(btn.dataset.delCable);
        });
      });
      root.querySelector("#rkBtnAddCable")?.addEventListener("click", () => {
        if (!this.selectedDeviceId) return;
        const aPort = root.querySelector("#cabAPort")?.value?.trim() || "eth0";
        const aSide = root.querySelector("#cabASide")?.value || "front";
        const bDevId = root.querySelector("#cabBDev")?.value;
        const bPort = root.querySelector("#cabBPort")?.value?.trim() || "Port 1";
        const bSide = root.querySelector("#cabBSide")?.value || "front";
        const label = root.querySelector("#cabLabel")?.value?.trim() || "";
        const cableType = root.querySelector("#cabType")?.value || "fiber";
        const color = root.querySelector("#cabColor")?.value || "#22c55e";
        if (!bDevId) return;
        this.createCable({
          label,
          cable_type: cableType,
          color,
          status: "connected",
          a_device_id: this.selectedDeviceId,
          a_port: aPort,
          a_port_side: aSide,
          b_device_id: bDevId,
          b_port: bPort,
          b_port_side: bSide,
        });
      });
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
        const faceVal = root.querySelector("#edDevFace")?.value || "both";
        this.updateDevice(rack.id, this.selectedDeviceId, {
          name: root.querySelector("#edDevName")?.value?.trim(),
          device_type: root.querySelector("#edDevType")?.value,
          status: root.querySelector("#edDevStatus")?.value,
          manufacturer: root.querySelector("#edDevMfr")?.value?.trim() || "",
          model: root.querySelector("#edDevModel")?.value?.trim() || "",
          u_position: Number(root.querySelector("#edDevPos")?.value || 1),
          u_height: Number(root.querySelector("#edDevH")?.value || 1),
          face: faceVal,
          is_full_depth: faceVal === "both",
          half_width: slotSel !== "full",
          half_slot: slotSel,
          power_w: Number(root.querySelector("#edDevPower")?.value || 0),
          color: root.querySelector("#edDevColor")?.value || "#0284c7",
          front_image: root.querySelector("#edDevFrontImg")?.value?.trim() || "",
          rear_image: root.querySelector("#edDevRearImg")?.value?.trim() || "",
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
