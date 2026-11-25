/**
 * security_console.js - Native Phase 6 Security Devices Console:
 * - CCTV Camera Wall (live auto-refreshing snapshot/stream tiles, click to expand, 3D FOV cone toggle)
 * - Door Access & Biometric Fingerprint Readers (Lock/Unlock, Grant/Deny badge simulation)
 * - Motion & Contact Sensors (Arm/Disarm, live Trigger/Clear alert testing)
 * - Active Security Alerts Banner & Real-Time Event Log with Acknowledge
 * - 100% theme-variable styled (Dark + Light), EN + ID, zero iframes, single DB source of truth.
 */
(function () {
  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function getCsrf() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function injectSecurityStyles() {
    if (document.getElementById("monits-security-css")) return;
    const st = document.createElement("style");
    st.id = "monits-security-css";
    st.textContent = `
      .sec-shell { display: flex; flex-direction: column; gap: 14px; }
      .sec-alert-bar {
        display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;
        padding: 10px 14px; border-radius: 12px;
        background: rgba(239, 68, 68, 0.14); border: 1px solid rgba(239, 68, 68, 0.55);
        color: var(--text-main);
      }
      .sec-tabs {
        display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;
      }
      .sec-tab-group { display: inline-flex; gap: 6px; flex-wrap: wrap; }
      .sec-btn {
        display: inline-flex; align-items: center; gap: 5px;
        padding: 6px 12px; border-radius: 8px; font-size: 0.8rem; font-weight: 600;
        border: 1px solid var(--border-color); background: var(--bg-card-inner);
        color: var(--text-main); cursor: pointer; transition: all 0.15s;
      }
      .sec-btn:hover, .sec-btn.active {
        border-color: var(--accent-cyan); background: var(--accent-cyan-soft); color: var(--accent-cyan);
      }
      .sec-btn.primary {
        background: var(--accent-cyan); color: var(--text-on-accent); border-color: var(--accent-cyan);
      }
      .sec-btn.danger {
        color: var(--accent-red); border-color: rgba(239, 68, 68, 0.45); background: rgba(239, 68, 68, 0.1);
      }
      .sec-btn.warn {
        color: var(--accent-amber); border-color: rgba(245, 158, 11, 0.45); background: rgba(245, 158, 11, 0.1);
      }
      .sec-btn.ok {
        color: var(--accent-green); border-color: rgba(34, 197, 94, 0.45); background: rgba(34, 197, 94, 0.1);
      }
      .sec-wall-grid {
        display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px;
      }
      .sec-card {
        background: var(--bg-card); border: 1px solid var(--border-color);
        border-radius: 12px; overflow: hidden; box-shadow: var(--card-shadow);
        display: flex; flex-direction: column;
      }
      .sec-card.alerting {
        border-color: rgba(239, 68, 68, 0.85);
        box-shadow: 0 0 18px rgba(239, 68, 68, 0.25);
      }
      .sec-cam-frame {
        position: relative; aspect-ratio: 16 / 9; background: #050b16; cursor: pointer; overflow: hidden;
      }
      .sec-cam-frame img, .sec-cam-frame video {
        width: 100%; height: 100%; object-fit: cover; display: block;
      }
      .sec-card-body { padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }
      .sec-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
      .sec-pill {
        display: inline-flex; align-items: center; gap: 4px;
        padding: 2px 8px; border-radius: 999px; font-size: 0.7rem; font-weight: 700;
        border: 1px solid currentColor;
      }
      .sec-pill.ok { color: var(--accent-green); background: rgba(34, 197, 94, 0.12); }
      .sec-pill.warn { color: var(--accent-amber); background: rgba(245, 158, 11, 0.12); }
      .sec-pill.crit { color: var(--accent-red); background: rgba(239, 68, 68, 0.14); }
      .sec-pill.info { color: var(--accent-cyan); background: var(--accent-cyan-soft); }
      .sec-panel {
        background: var(--bg-card); border: 1px solid var(--border-color);
        border-radius: 12px; padding: 12px 14px;
      }
      .sec-form-grid {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 8px; font-size: 0.78rem;
      }
      .sec-form-grid label { display: flex; flex-direction: column; gap: 4px; color: var(--text-muted); }
      .sec-input {
        background: var(--bg-app); border: 1px solid var(--border-subtle); color: var(--text-main);
        border-radius: 7px; padding: 6px 8px; font-size: 0.8rem; width: 100%; box-sizing: border-box;
      }
      .sec-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
      .sec-table th {
        text-align: left; padding: 7px 8px; color: var(--text-muted);
        border-bottom: 1px solid var(--border-color); font-size: 0.72rem; text-transform: uppercase;
      }
      .sec-table td { padding: 8px; border-bottom: 1px solid var(--border-subtle); color: var(--text-main); }
      .sec-modal {
        position: fixed; inset: 56px 20px 20px 20px; z-index: 3400;
        background: var(--bg-drawer); backdrop-filter: blur(18px);
        border: 1px solid var(--border-color); border-radius: 16px;
        padding: 14px 18px; display: flex; flex-direction: column; gap: 10px;
        box-shadow: var(--card-shadow);
      }
    `;
    document.head.appendChild(st);
  }

  class SecurityConsoleController {
    constructor(container, opts = {}) {
      this.container = container;
      this.lang = opts.lang || document.documentElement.lang || "en";
      this.isId = this.lang === "id";
      this.canWrite = opts.canWrite !== false;
      this.devices = [];
      this.events = [];
      this.activeTab = "all"; // all | cctv | access | sensors | events
      this.showAddForm = false;
      this.editingDeviceId = null;
      this.expandedCamId = null;
      this.expandedUseStream = true;
      this.tick = Date.now();
      injectSecurityStyles();
    }

    t(en, id) {
      return this.isId ? id : en;
    }

    async loadAll() {
      const [dRes, eRes] = await Promise.all([
        fetch("/api/v1/security/devices"),
        fetch("/api/v1/security/events?limit=40"),
      ]);
      if (dRes.ok) {
        const d = await dRes.json();
        this.devices = d.devices || [];
      }
      if (eRes.ok) {
        const e = await eRes.json();
        this.events = e.events || [];
      }
      this.tick = Date.now();
      this.render();
    }

    async runAction(deviceId, action, extra = {}) {
      const res = await fetch(`/api/v1/security/devices/${encodeURIComponent(deviceId)}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrf() },
        body: JSON.stringify({ action, ...extra }),
      });
      if (res.ok) await this.loadAll();
    }

    async createDevice(payload) {
      const res = await fetch("/api/v1/security/devices", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrf() },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        this.showAddForm = false;
        await this.loadAll();
      }
    }

    async updateDevice(deviceId, payload) {
      const res = await fetch(`/api/v1/security/devices/${encodeURIComponent(deviceId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrf() },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        this.editingDeviceId = null;
        await this.loadAll();
      }
    }

    async deleteDevice(deviceId) {
      const res = await fetch(`/api/v1/security/devices/${encodeURIComponent(deviceId)}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": getCsrf() },
      });
      if (res.ok) await this.loadAll();
    }

    async ackEvent(eventId) {
      const res = await fetch(`/api/v1/security/events/${encodeURIComponent(eventId)}/ack`, {
        method: "POST",
        headers: { "X-CSRF-Token": getCsrf() },
      });
      if (res.ok) await this.loadAll();
    }

    render() {
      const cams = this.devices.filter((d) => d.device_kind === "cctv");
      const access = this.devices.filter((d) => d.device_kind === "door_access" || d.device_kind === "fingerprint");
      const sensors = this.devices.filter((d) => d.device_kind === "motion" || d.device_kind === "contact");
      const alerts = this.devices.filter((d) => d.alert_active);

      const alertBannerHtml = alerts.length
        ? `
          <div class="sec-alert-bar" id="secActiveAlertBanner">
            <div>
              <strong>🚨 ${alerts.length} ${this.t("Active Security Alert(s)", "Peringatan Keamanan Aktif")}:</strong>
              ${alerts.map((a) => `<span style="margin-left:8px;">${esc(a.name)} — ${esc(a.alert_message || a.state)}</span>`).join(" · ")}
            </div>
            ${this.canWrite ? `<div style="display:flex; gap:6px;">${alerts.map((a) => `<button type="button" class="sec-btn" data-sec-act="ack_alert" data-dev-id="${esc(a.id)}">✓ ${this.t("Acknowledge", "Konfirmasi")} ${esc(a.name)}</button>`).join("")}</div>` : ""}
          </div>
        `
        : "";

      const addFormHtml = this.showAddForm
        ? `
          <div class="sec-panel">
            <div class="sec-row" style="margin-bottom:8px;">
              <strong>+ ${this.t("Add Security Device (Synced to 2D & 3D)", "Tambah Perangkat Keamanan (Sinkron 2D & 3D)")}</strong>
              <button type="button" class="sec-btn" id="secCancelAdd">✕</button>
            </div>
            <div class="sec-form-grid">
              <label><span>${this.t("Name", "Nama")}</span><input id="secNewName" class="sec-input" placeholder="CCTV Corridors B" /></label>
              <label><span>${this.t("Device Type", "Tipe Perangkat")}</span>
                <select id="secNewKind" class="sec-input">
                  <option value="cctv">📹 CCTV Camera (3D FOV Cone)</option>
                  <option value="fingerprint">🔐 Biometric Fingerprint Reader</option>
                  <option value="door_access">🚪 Door Access Lock</option>
                  <option value="motion">📡 Motion Sensor (3D Cone)</option>
                  <option value="contact">🧲 Door / Rack Contact Sensor</option>
                </select>
              </label>
              <label><span>${this.t("Floor", "Lantai")}</span><input id="secNewFloor" class="sec-input" value="ground" /></label>
              <label><span>X (m)</span><input id="secNewX" type="number" step="0.2" class="sec-input" value="5.0" /></label>
              <label><span>Z (m)</span><input id="secNewZ" type="number" step="0.2" class="sec-input" value="3.0" /></label>
              <label><span>Y (m)</span><input id="secNewY" type="number" step="0.1" class="sec-input" value="2.8" /></label>
              <label><span>${this.t("Rotation (°)", "Rotasi (°)")}</span><input id="secNewRot" type="number" step="15" class="sec-input" value="180" /></label>
              <label><span>${this.t("FOV (°) / Reach (m)", "FOV (°) / Jangkauan (m)")}</span>
                <div style="display:flex; gap:4px;">
                  <input id="secNewFov" type="number" class="sec-input" value="75" title="FOV deg" />
                  <input id="secNewReach" type="number" step="0.5" class="sec-input" value="7" title="Reach m" />
                </div>
              </label>
              <label style="grid-column:span 2;"><span>${this.t("Stream / Snapshot URL (Optional LAN)", "URL Stream / Snapshot (Opsional LAN)")}</span><input id="secNewStream" class="sec-input" placeholder="http://192.168.1.50/mjpeg or leave blank for offline HUD" /></label>
            </div>
            <div style="display:flex; justify-content:flex-end; margin-top:10px;">
              <button type="button" class="sec-btn primary" id="secSubmitAdd">💾 ${this.t("Save & Place in 3D", "Simpan & Tempatkan di 3D")}</button>
            </div>
          </div>
        `
        : "";

      const editDev = this.editingDeviceId ? this.devices.find((d) => d.id === this.editingDeviceId) : null;
      const editFormHtml = editDev
        ? `
          <div class="sec-panel" id="secEditDevicePanel" style="border-color:var(--accent-cyan);">
            <div class="sec-row" style="margin-bottom:8px;">
              <strong style="color:var(--accent-cyan);">✏️ ${this.t("Edit Security Device", "Ubah Perangkat Keamanan")} — ${esc(editDev.name)} (${esc(editDev.entity_id)})</strong>
              <button type="button" class="sec-btn" id="secCancelEdit">✕</button>
            </div>
            <div class="sec-form-grid">
              <label><span>${this.t("Name", "Nama")}</span><input id="secEdName" class="sec-input" value="${esc(editDev.name)}" /></label>
              <label><span>${this.t("Floor", "Lantai")}</span><input id="secEdFloor" class="sec-input" value="${esc(editDev.floor_id || "ground")}" /></label>
              <label><span>X (m)</span><input id="secEdX" type="number" step="0.1" class="sec-input" value="${editDev.pos_x}" /></label>
              <label><span>Z (m)</span><input id="secEdZ" type="number" step="0.1" class="sec-input" value="${editDev.pos_z}" /></label>
              <label><span>Y (m)</span><input id="secEdY" type="number" step="0.1" class="sec-input" value="${editDev.pos_y}" /></label>
              <label><span>${this.t("Rotation (°)", "Rotasi (°)")}</span><input id="secEdRot" type="number" step="5" class="sec-input" value="${editDev.rotation}" /></label>
              ${editDev.device_kind === "cctv" || editDev.device_kind === "motion" ? `
                <label><span>${this.t("FOV (°)", "FOV (°)")}</span><input id="secEdFov" type="number" step="5" class="sec-input" value="${editDev.fov_deg}" /></label>
                <label><span>${this.t("Reach (m)", "Jangkauan (m)")}</span><input id="secEdReach" type="number" step="0.5" class="sec-input" value="${editDev.reach_m}" /></label>
              ` : ""}
              ${editDev.device_kind === "cctv" ? `
                <label style="grid-column:span 2;">
                  <span>${this.t("Frigate / go2rtc / MJPEG / RTSP Stream URL", "URL Stream Frigate / go2rtc / MJPEG / RTSP")}</span>
                  <input id="secEdStream" class="sec-input" value="${esc(editDev.stream_url || "")}" placeholder="https://inskal-cctv.balai5.my.id/api/go2rtc/streams/inskal_main_lobby" />
                </label>
                <label style="grid-column:span 2;">
                  <span>${this.t("Snapshot URL (Optional — auto-derived from Frigate/go2rtc)", "URL Snapshot (Opsional — otomatis dari Frigate/go2rtc)")}</span>
                  <input id="secEdSnap" class="sec-input" value="${esc(editDev.snapshot_url || "")}" placeholder="https://inskal-cctv.balai5.my.id/api/inskal_main_lobby/latest.jpg" />
                </label>
              ` : ""}
              <label style="grid-column:span 2;"><span>${this.t("Notes", "Catatan")}</span><input id="secEdNotes" class="sec-input" value="${esc(editDev.notes || "")}" /></label>
            </div>
            <div style="display:flex; justify-content:flex-end; gap:6px; margin-top:10px;">
              <button type="button" class="sec-btn" id="secCancelEdit2">${this.t("Cancel", "Batal")}</button>
              <button type="button" class="sec-btn primary" id="secSubmitEdit">💾 ${this.t("Save Changes", "Simpan Perubahan")}</button>
            </div>
          </div>
        `
        : "";

      const renderCams = () => `
        <div class="sec-panel">
          <div class="sec-row" style="margin-bottom:10px;">
            <strong style="color:var(--accent-cyan);">📹 ${this.t("CCTV Camera Wall", "Dinding Kamera CCTV")} (${cams.length})</strong>
            <button type="button" class="sec-btn" id="secRefreshWall">🔄 ${this.t("Refresh Snapshots", "Segarkan Cuplikan")}</button>
          </div>
          <div class="sec-wall-grid">
            ${cams.map((c) => {
              const src = `${c.snapshot_endpoint}?t=${this.tick}`;
              const pillCls = c.alert_active ? "crit" : (c.state === "recording" ? "ok" : "info");
              return `
                <div class="sec-card ${c.alert_active ? "alerting" : ""}">
                  <div class="sec-cam-frame" data-expand-cam="${esc(c.id)}" title="${this.t("Click to open live stream", "Klik untuk buka siaran langsung")}">
                    <img src="${esc(src)}" alt="${esc(c.name)}" />
                  </div>
                  <div class="sec-card-body">
                    <div class="sec-row">
                      <strong>${esc(c.name)}</strong>
                      <span class="sec-pill ${pillCls}">${c.alert_active ? "ALERT" : esc(c.state.toUpperCase())}</span>
                    </div>
                    <div style="font-size:0.73rem; color:var(--text-muted);">
                      ${esc(c.entity_id)} · FOV ${c.fov_deg}° · ${c.reach_m}m · (${c.pos_x}m, ${c.pos_z}m)
                      ${c.stream_url ? `<div style="color:var(--accent-cyan); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${esc(c.stream_url)}">🔗 ${esc(c.stream_url)}</div>` : ""}
                    </div>
                    ${this.canWrite ? `
                      <div class="sec-row">
                        <div style="display:flex; gap:5px; flex-wrap:wrap;">
                          <button type="button" class="sec-btn ${c.cone_enabled ? "active" : ""}" data-sec-act="toggle_cone" data-dev-id="${esc(c.id)}">🔦 ${c.cone_enabled ? "3D Cone ON" : "3D Cone OFF"}</button>
                          <button type="button" class="sec-btn" data-sec-act="toggle_recording" data-dev-id="${esc(c.id)}">${c.state === "recording" ? "⏹ Idle" : "● REC"}</button>
                          <button type="button" class="sec-btn ${c.alert_active ? "ok" : "warn"}" data-sec-act="${c.alert_active ? "ack_alert" : "trigger_alert"}" data-dev-id="${esc(c.id)}">${c.alert_active ? "✓ Clear" : "⚠ Alert"}</button>
                        </div>
                        <div style="display:flex; gap:4px;">
                          <button type="button" class="sec-btn" data-edit-dev="${esc(c.id)}" title="Edit">✏️</button>
                          <button type="button" class="sec-btn danger" data-del-dev="${esc(c.id)}" title="Delete">🗑️</button>
                        </div>
                      </div>
                    ` : ""}
                  </div>
                </div>
              `;
            }).join("")}
          </div>
        </div>
      `;

      const renderAccess = () => `
        <div class="sec-panel">
          <strong style="color:var(--accent-cyan); display:block; margin-bottom:10px;">🔐 ${this.t("Door Access & Biometric Fingerprint Readers", "Akses Pintu & Pembaca Sidik Jari Biometrik")} (${access.length})</strong>
          <div class="sec-wall-grid">
            ${access.map((d) => {
              const isLocked = d.state === "locked";
              const pillCls = d.alert_active ? "crit" : (isLocked ? "ok" : "warn");
              return `
                <div class="sec-card ${d.alert_active ? "alerting" : ""}">
                  <div class="sec-card-body">
                    <div class="sec-row">
                      <strong>${d.device_kind === "fingerprint" ? "🧬" : "🚪"} ${esc(d.name)}</strong>
                      <span class="sec-pill ${pillCls}">${d.alert_active ? "DENIED / ALERT" : esc(d.state.toUpperCase())}</span>
                    </div>
                    <div style="font-size:0.74rem; color:var(--text-muted);">${esc(d.entity_id)} · Floor ${esc(d.floor_id)} · (${d.pos_x}m, ${d.pos_z}m)</div>
                    ${this.canWrite ? `
                      <div class="sec-row" style="margin-top:4px;">
                        <div style="display:flex; gap:5px; flex-wrap:wrap;">
                          <button type="button" class="sec-btn ${isLocked ? "warn" : "ok"}" data-sec-act="${isLocked ? "unlock" : "lock"}" data-dev-id="${esc(d.id)}">${isLocked ? "🔓 Unlock" : "🔒 Lock"}</button>
                          <button type="button" class="sec-btn ok" data-sec-act="grant_access" data-dev-id="${esc(d.id)}">👆 Grant</button>
                          <button type="button" class="sec-btn danger" data-sec-act="deny_access" data-dev-id="${esc(d.id)}">⛔ Deny</button>
                        </div>
                        <div style="display:flex; gap:4px;">
                          <button type="button" class="sec-btn" data-edit-dev="${esc(d.id)}" title="Edit">✏️</button>
                          <button type="button" class="sec-btn danger" data-del-dev="${esc(d.id)}" title="Delete">🗑️</button>
                        </div>
                      </div>
                    ` : ""}
                  </div>
                </div>
              `;
            }).join("")}
          </div>
        </div>
      `;

      const renderSensors = () => `
        <div class="sec-panel">
          <strong style="color:var(--accent-cyan); display:block; margin-bottom:10px;">📡 ${this.t("Motion & Door/Rack Contact Sensors", "Sensor Gerak & Kontak Pintu/Rak")} (${sensors.length})</strong>
          <div class="sec-wall-grid">
            ${sensors.map((d) => {
              const isMotion = d.device_kind === "motion";
              const triggered = d.state === "detected" || d.state === "open";
              const pillCls = d.alert_active ? "crit" : (triggered ? "warn" : "ok");
              return `
                <div class="sec-card ${d.alert_active ? "alerting" : ""}">
                  <div class="sec-card-body">
                    <div class="sec-row">
                      <strong>${isMotion ? "📡" : "🧲"} ${esc(d.name)}</strong>
                      <span class="sec-pill ${pillCls}">${esc(d.state.toUpperCase())}</span>
                    </div>
                    <div style="font-size:0.74rem; color:var(--text-muted);">
                      ${esc(d.entity_id)} · ${d.armed ? "🛡️ Armed" : "Disarmed"}${isMotion ? ` · Cone ${d.fov_deg}° / ${d.reach_m}m` : ""}
                    </div>
                    ${this.canWrite ? `
                      <div class="sec-row" style="margin-top:4px;">
                        <div style="display:flex; gap:5px; flex-wrap:wrap;">
                          <button type="button" class="sec-btn ${d.armed ? "active" : ""}" data-sec-act="toggle_arm" data-dev-id="${esc(d.id)}">${d.armed ? "🛡️ Armed" : "Disarmed"}</button>
                          <button type="button" class="sec-btn ${triggered ? "ok" : "warn"}" data-sec-act="${isMotion ? (triggered ? "clear_motion" : "trigger_motion") : (triggered ? "close_door" : "open_door")}" data-dev-id="${esc(d.id)}">${triggered ? "✓ Clear" : (isMotion ? "⚡ Trigger Motion" : "🚪 Open Door")}</button>
                          ${isMotion ? `<button type="button" class="sec-btn ${d.cone_enabled ? "active" : ""}" data-sec-act="toggle_cone" data-dev-id="${esc(d.id)}">🔦 Cone</button>` : ""}
                        </div>
                        <div style="display:flex; gap:4px;">
                          <button type="button" class="sec-btn" data-edit-dev="${esc(d.id)}" title="Edit">✏️</button>
                          <button type="button" class="sec-btn danger" data-del-dev="${esc(d.id)}" title="Delete">🗑️</button>
                        </div>
                      </div>
                    ` : ""}
                  </div>
                </div>
              `;
            }).join("")}
          </div>
        </div>
      `;

      const renderEvents = () => `
        <div class="sec-panel">
          <strong style="color:var(--accent-cyan); display:block; margin-bottom:8px;">📋 ${this.t("Security Access & Alert Timeline", "Riwayat Akses & Peringatan Keamanan")} (${this.events.length})</strong>
          <table class="sec-table">
            <thead>
              <tr>
                <th>${this.t("Time", "Waktu")}</th>
                <th>${this.t("Device", "Perangkat")}</th>
                <th>${this.t("Event", "Kejadian")}</th>
                <th>${this.t("Actor", "Pelaku")}</th>
                <th>${this.t("Message", "Pesan")}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${this.events.length ? this.events.map((ev) => {
                const sevCls = ev.severity === "critical" ? "crit" : (ev.severity === "warning" ? "warn" : "info");
                const ts = ev.created_at ? new Date(ev.created_at).toLocaleString() : "";
                return `
                  <tr>
                    <td style="white-space:nowrap; font-size:0.74rem; color:var(--text-muted);">${esc(ts)}</td>
                    <td><strong>${esc(ev.device_name)}</strong></td>
                    <td><span class="sec-pill ${sevCls}">${esc(ev.event_type)}</span></td>
                    <td>${esc(ev.actor)}</td>
                    <td>${esc(ev.message)}</td>
                    <td>${!ev.acknowledged && this.canWrite ? `<button type="button" class="sec-btn ok" data-ack-ev="${esc(ev.id)}">✓ Ack</button>` : (ev.acknowledged ? '<span style="color:var(--accent-green); font-size:0.72rem;">✓</span>' : "")}</td>
                  </tr>
                `;
              }).join("") : `<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:16px;">${this.t("No security events recorded yet.", "Belum ada kejadian keamanan.")}</td></tr>`}
            </tbody>
          </table>
        </div>
      `;

      const expandedCam = this.expandedCamId ? cams.find((c) => c.id === this.expandedCamId) : null;
      const modalSrc = expandedCam
        ? (this.expandedUseStream && expandedCam.stream_url
            ? `${expandedCam.stream_endpoint}?t=${this.tick}`
            : `${expandedCam.snapshot_endpoint}?t=${this.tick}`)
        : "";
      const modalHtml = expandedCam
        ? `
          <div class="sec-modal" id="secCamModal" role="dialog" aria-modal="true">
            <div class="sec-row">
              <strong>📹 ${esc(expandedCam.name)} · ${esc(expandedCam.entity_id)} (FOV ${expandedCam.fov_deg}° · ${expandedCam.reach_m}m)</strong>
              <div style="display:flex; gap:6px; align-items:center;">
                ${expandedCam.stream_url ? `<button type="button" class="sec-btn ${this.expandedUseStream ? "active" : ""}" id="secToggleStreamMode">${this.expandedUseStream ? "● Live MJPEG" : "🖼️ Snapshot"}</button>` : ""}
                <button type="button" class="sec-btn" id="secCloseModal" aria-label="✕">✕</button>
              </div>
            </div>
            <div style="flex:1; min-height:0; display:flex; align-items:center; justify-content:center; background:#050b16; border-radius:10px; overflow:hidden;">
              <img src="${esc(modalSrc)}" alt="${esc(expandedCam.name)}" style="max-width:100%; max-height:100%; object-fit:contain;" />
            </div>
          </div>
        `
        : "";

      this.container.innerHTML = `
        <div class="sec-shell">
          ${alertBannerHtml}
          <div class="sec-tabs">
            <div class="sec-tab-group">
              <button type="button" class="sec-btn ${this.activeTab === "all" ? "active" : ""}" data-sec-tab="all">🛡️ ${this.t("All", "Semua")} (${this.devices.length})</button>
              <button type="button" class="sec-btn ${this.activeTab === "cctv" ? "active" : ""}" data-sec-tab="cctv">📹 CCTV (${cams.length})</button>
              <button type="button" class="sec-btn ${this.activeTab === "access" ? "active" : ""}" data-sec-tab="access">🔐 ${this.t("Door Access", "Akses Pintu")} (${access.length})</button>
              <button type="button" class="sec-btn ${this.activeTab === "sensors" ? "active" : ""}" data-sec-tab="sensors">📡 ${this.t("Motion / Contact", "Gerak / Kontak")} (${sensors.length})</button>
              <button type="button" class="sec-btn ${this.activeTab === "events" ? "active" : ""}" data-sec-tab="events">📋 ${this.t("Events", "Riwayat")} (${this.events.length})</button>
            </div>
            ${this.canWrite ? `<button type="button" class="sec-btn primary" id="secBtnToggleAdd">+ ${this.t("Add Security Device", "Tambah Perangkat")}</button>` : ""}
          </div>
          ${addFormHtml}
          ${editFormHtml}
          ${this.activeTab === "all" || this.activeTab === "cctv" ? renderCams() : ""}
          ${this.activeTab === "all" || this.activeTab === "access" ? renderAccess() : ""}
          ${this.activeTab === "all" || this.activeTab === "sensors" ? renderSensors() : ""}
          ${this.activeTab === "all" || this.activeTab === "events" ? renderEvents() : ""}
        </div>
        ${modalHtml}
      `;

      this.bindEvents();
    }

    bindEvents() {
      const root = this.container;
      root.querySelectorAll("[data-sec-tab]").forEach((b) => {
        b.addEventListener("click", () => {
          this.activeTab = b.dataset.secTab;
          this.render();
        });
      });
      root.querySelector("#secBtnToggleAdd")?.addEventListener("click", () => {
        this.showAddForm = !this.showAddForm;
        this.render();
      });
      root.querySelector("#secCancelAdd")?.addEventListener("click", () => {
        this.showAddForm = false;
        this.render();
      });
      root.querySelector("#secRefreshWall")?.addEventListener("click", () => {
        this.tick = Date.now();
        this.render();
      });
      root.querySelector("#secSubmitAdd")?.addEventListener("click", () => {
        const name = root.querySelector("#secNewName")?.value?.trim();
        if (!name) return;
        this.createDevice({
          name,
          device_kind: root.querySelector("#secNewKind")?.value || "cctv",
          floor_id: root.querySelector("#secNewFloor")?.value?.trim() || "ground",
          pos_x: Number(root.querySelector("#secNewX")?.value || 5.0),
          pos_z: Number(root.querySelector("#secNewZ")?.value || 3.0),
          pos_y: Number(root.querySelector("#secNewY")?.value || 2.8),
          rotation: Number(root.querySelector("#secNewRot")?.value || 180),
          fov_deg: Number(root.querySelector("#secNewFov")?.value || 75),
          reach_m: Number(root.querySelector("#secNewReach")?.value || 7.0),
          stream_url: root.querySelector("#secNewStream")?.value?.trim() || "",
          snapshot_url: root.querySelector("#secNewStream")?.value?.trim() || "",
          cone_enabled: true,
        });
      });
      root.querySelectorAll("[data-sec-act]").forEach((b) => {
        b.addEventListener("click", () => this.runAction(b.dataset.devId, b.dataset.secAct));
      });
      root.querySelectorAll("[data-edit-dev]").forEach((b) => {
        b.addEventListener("click", () => {
          this.editingDeviceId = b.dataset.editDev;
          this.showAddForm = false;
          this.render();
          root.querySelector("#secEditDevicePanel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        });
      });
      const closeEdit = () => {
        this.editingDeviceId = null;
        this.render();
      };
      root.querySelector("#secCancelEdit")?.addEventListener("click", closeEdit);
      root.querySelector("#secCancelEdit2")?.addEventListener("click", closeEdit);
      root.querySelector("#secSubmitEdit")?.addEventListener("click", () => {
        if (!this.editingDeviceId) return;
        const payload = {
          name: root.querySelector("#secEdName")?.value?.trim(),
          floor_id: root.querySelector("#secEdFloor")?.value?.trim() || "ground",
          pos_x: Number(root.querySelector("#secEdX")?.value || 0),
          pos_z: Number(root.querySelector("#secEdZ")?.value || 0),
          pos_y: Number(root.querySelector("#secEdY")?.value || 0),
          rotation: Number(root.querySelector("#secEdRot")?.value || 0),
          notes: root.querySelector("#secEdNotes")?.value || "",
        };
        const fovEl = root.querySelector("#secEdFov");
        const reachEl = root.querySelector("#secEdReach");
        const streamEl = root.querySelector("#secEdStream");
        const snapEl = root.querySelector("#secEdSnap");
        if (fovEl) payload.fov_deg = Number(fovEl.value || 75);
        if (reachEl) payload.reach_m = Number(reachEl.value || 7);
        if (streamEl) payload.stream_url = streamEl.value.trim();
        if (snapEl) payload.snapshot_url = snapEl.value.trim();
        this.updateDevice(this.editingDeviceId, payload);
      });
      root.querySelector("#secToggleStreamMode")?.addEventListener("click", () => {
        this.expandedUseStream = !this.expandedUseStream;
        this.tick = Date.now();
        this.render();
      });
      root.querySelectorAll("[data-del-dev]").forEach((b) => {
        b.addEventListener("click", () => this.deleteDevice(b.dataset.delDev));
      });
      root.querySelectorAll("[data-ack-ev]").forEach((b) => {
        b.addEventListener("click", () => this.ackEvent(b.dataset.ackEv));
      });
      root.querySelectorAll("[data-expand-cam]").forEach((el) => {
        el.addEventListener("click", () => {
          this.expandedCamId = el.dataset.expandCam;
          this.render();
        });
      });
      root.querySelector("#secCloseModal")?.addEventListener("click", () => {
        this.expandedCamId = null;
        this.render();
      });
    }
  }

  window.SecurityConsoleUI = {
    mount(container, opts) {
      const ctrl = new SecurityConsoleController(container, opts);
      ctrl.loadAll();
      return ctrl;
    },
  };
})();
