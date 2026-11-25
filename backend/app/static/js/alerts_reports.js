/**
 * alerts_reports.js - Phase 7 Unified Alerting, Threshold Rules, Incident Timeline & Exportable Reports UI.
 *
 * - Full CRUD for Threshold Alert Rules (`/api/v1/alerts/rules`)
 * - Live Threshold Rule Evaluation (`POST /api/v1/alerts/evaluate`)
 * - Full CRUD for Incident Timeline (`/api/v1/alerts/incidents`) + unified Security alerts
 * - Executive & SLA Reports with one-click CSV, JSON, and Printable HTML/PDF export
 * - 100% theme-variable styled (Dark Neon + Light), EN + ID, zero external assets, zero iframes.
 */
(function () {
  "use strict";

  const I18N = {
    en: {
      tab_rules: "Threshold Rules",
      tab_incidents: "Incident Timeline",
      tab_reports: "Executive Reports",
      kpi_env: "Environment",
      kpi_infra: "Infrastructure",
      kpi_sec: "Security",
      kpi_inc: "Active Incidents",
      sensors: "sensors",
      racks: "racks",
      devices: "devices",
      rules_enabled: "rules active",
      new_rule: "+ New Rule",
      evaluate_now: "Evaluate Rules Now",
      log_incident: "+ Log Incident",
      edit: "Edit",
      del: "Delete",
      save: "Save",
      cancel: "Cancel",
      enable: "Enable",
      disable: "Disable",
      enabled: "Enabled",
      disabled: "Disabled",
      ack: "Acknowledge",
      resolve: "Resolve",
      reopen: "Reopen",
      rule_name: "Rule Name",
      scope: "Target Scope",
      metric: "Metric",
      operator: "Operator",
      warn_th: "Warning Threshold",
      crit_th: "Critical Threshold",
      cooldown: "Cooldown (min)",
      webhook: "Webhook URL (Optional)",
      description: "Description",
      no_rules: "No threshold rules configured.",
      no_incidents: "No incidents matching the current filter.",
      filter_status: "Status",
      filter_severity: "Severity",
      all: "All",
      active: "Active",
      acknowledged: "Acknowledged",
      resolved: "Resolved",
      warning: "Warning",
      critical: "Critical",
      sensor: "Sensor",
      reading: "Reading",
      threshold: "Threshold",
      message: "Message",
      comment: "Notes / Resolution Comment",
      export_csv: "Export CSV",
      export_json: "Export JSON",
      export_html: "Printable HTML / PDF",
      env_summary: "Environment Sensors Snapshot",
      infra_summary: "Infrastructure & Capacity Summary",
      sec_summary: "Security & Access Posture",
      inc_summary: "Incident & SLA Breakdown",
      confirm_del_rule: "Delete this threshold rule?",
      confirm_del_inc: "Delete this incident permanently?",
      eval_done: "Evaluation complete",
      triggered: "new incident(s) triggered",
      saved_ok: "Saved successfully",
      deleted_ok: "Deleted successfully",
      security_source: "Security",
      env_source: "Environment",
      open_security: "Open Security",
    },
    id: {
      tab_rules: "Aturan Ambang Batas",
      tab_incidents: "Linimasa Insiden",
      tab_reports: "Laporan Eksekutif",
      kpi_env: "Lingkungan",
      kpi_infra: "Infrastruktur",
      kpi_sec: "Keamanan",
      kpi_inc: "Insiden Aktif",
      sensors: "sensor",
      racks: "rak",
      devices: "perangkat",
      rules_enabled: "aturan aktif",
      new_rule: "+ Aturan Baru",
      evaluate_now: "Evaluasi Aturan Sekarang",
      log_incident: "+ Catat Insiden",
      edit: "Ubah",
      del: "Hapus",
      save: "Simpan",
      cancel: "Batal",
      enable: "Aktifkan",
      disable: "Nonaktifkan",
      enabled: "Aktif",
      disabled: "Nonaktif",
      ack: "Akui",
      resolve: "Selesaikan",
      reopen: "Buka Lagi",
      rule_name: "Nama Aturan",
      scope: "Cakupan Target",
      metric: "Metrik",
      operator: "Operator",
      warn_th: "Ambang Peringatan",
      crit_th: "Ambang Kritis",
      cooldown: "Jeda (menit)",
      webhook: "URL Webhook (Opsional)",
      description: "Deskripsi",
      no_rules: "Belum ada aturan ambang batas.",
      no_incidents: "Tidak ada insiden sesuai filter.",
      filter_status: "Status",
      filter_severity: "Tingkat Keparahan",
      all: "Semua",
      active: "Aktif",
      acknowledged: "Diakui",
      resolved: "Selesai",
      warning: "Peringatan",
      critical: "Kritis",
      sensor: "Sensor",
      reading: "Pembacaan",
      threshold: "Ambang",
      message: "Pesan",
      comment: "Catatan / Resolusi",
      export_csv: "Ekspor CSV",
      export_json: "Ekspor JSON",
      export_html: "Laporan HTML / PDF",
      env_summary: "Ringkasan Sensor Lingkungan",
      infra_summary: "Ringkasan Infrastruktur & Kapasitas",
      sec_summary: "Postur Keamanan & Akses",
      inc_summary: "Rincian Insiden & SLA",
      confirm_del_rule: "Hapus aturan ambang batas ini?",
      confirm_del_inc: "Hapus insiden ini secara permanen?",
      eval_done: "Evaluasi selesai",
      triggered: "insiden baru terpicu",
      saved_ok: "Berhasil disimpan",
      deleted_ok: "Berhasil dihapus",
      security_source: "Keamanan",
      env_source: "Lingkungan",
      open_security: "Buka Keamanan",
    },
  };

  function esc(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function csrfHeaders(json = true) {
    const h = {};
    if (json) h["Content-Type"] = "application/json";
    if (typeof window.getCsrfToken === "function") {
      h["X-CSRF-Token"] = window.getCsrfToken();
    }
    return h;
  }

  function injectStyles() {
    if (document.getElementById("alerts-reports-styles")) return;
    const style = document.createElement("style");
    style.id = "alerts-reports-styles";
    style.textContent = `
      .ar-kpis {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
        gap: 12px;
        margin-bottom: 16px;
      }
      .ar-kpi {
        background: var(--bg-surface);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 14px 16px;
        box-shadow: var(--card-shadow);
      }
      .ar-kpi-label {
        font-size: 0.78rem;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 4px;
      }
      .ar-kpi-val {
        font-size: 1.45rem;
        font-weight: 700;
        color: var(--text-main);
        line-height: 1.2;
      }
      .ar-kpi-sub {
        font-size: 0.78rem;
        color: var(--text-muted);
        margin-top: 4px;
      }
      .ar-tabs {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 14px;
      }
      .ar-tab-group {
        display: inline-flex;
        padding: 4px;
        gap: 4px;
        border-radius: 999px;
        background: var(--bg-seg);
        border: 1px solid var(--border-color);
      }
      .ar-tab-btn {
        border: none;
        background: transparent;
        color: var(--text-muted);
        padding: 7px 14px;
        border-radius: 999px;
        font-size: 0.86rem;
        font-weight: 600;
        cursor: pointer;
        transition: background 0.15s, color 0.15s;
      }
      .ar-tab-btn.active {
        background: var(--accent-cyan-soft);
        color: var(--accent-cyan);
      }
      .ar-card {
        background: var(--bg-surface);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 16px;
        box-shadow: var(--card-shadow);
        margin-bottom: 14px;
      }
      .ar-table-wrap {
        overflow-x: auto;
      }
      .ar-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.86rem;
      }
      .ar-table th, .ar-table td {
        text-align: left;
        padding: 10px 12px;
        border-bottom: 1px solid var(--border-color);
        vertical-align: middle;
      }
      .ar-table th {
        color: var(--text-muted);
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }
      .ar-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 2px 9px;
        border-radius: 999px;
        font-size: 0.74rem;
        font-weight: 600;
        white-space: nowrap;
      }
      .ar-badge-ok { background: rgba(16,185,129,0.16); color: #10b981; }
      .ar-badge-warn { background: rgba(245,158,11,0.18); color: #f59e0b; }
      .ar-badge-crit { background: rgba(239,68,68,0.18); color: #ef4444; }
      .ar-badge-muted { background: rgba(148,163,184,0.16); color: var(--text-muted); }
      .ar-badge-info { background: var(--accent-cyan-soft); color: var(--accent-cyan); }
      .ar-form-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        gap: 10px;
        margin-bottom: 12px;
      }
      .ar-field label {
        display: block;
        font-size: 0.76rem;
        color: var(--text-muted);
        margin-bottom: 4px;
        font-weight: 600;
      }
      .ar-field input, .ar-field select, .ar-field textarea {
        width: 100%;
        box-sizing: border-box;
        padding: 8px 10px;
        border-radius: 8px;
        border: 1px solid var(--border-color);
        background: var(--bg-main);
        color: var(--text-main);
        font: inherit;
        font-size: 0.86rem;
      }
      .ar-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        align-items: center;
      }
      .ar-toast {
        position: fixed;
        bottom: 20px;
        right: 20px;
        z-index: 2000;
        padding: 10px 16px;
        border-radius: 10px;
        background: var(--bg-surface);
        border: 1px solid var(--accent-cyan);
        color: var(--text-main);
        box-shadow: 0 8px 24px rgba(0,0,0,0.35);
        font-size: 0.86rem;
        font-weight: 600;
      }
      .ar-grid-2 {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        gap: 14px;
      }
    `;
    document.head.appendChild(style);
  }

  function mount(root, opts = {}) {
    injectStyles();
    const lang = (opts.lang || "en").startsWith("id") ? "id" : "en";
    const canWrite = Boolean(opts.canWrite);
    const t = (k) => (I18N[lang] && I18N[lang][k]) || I18N.en[k] || k;

    const state = {
      tab: "rules",
      rules: [],
      incidents: [],
      sensors: [],
      summary: null,
      statusFilter: "",
      severityFilter: "",
      showRuleForm: false,
      editingRuleId: null,
      showIncidentForm: false,
      editingIncidentId: null,
      loading: false,
    };

    function toast(msg, isError = false) {
      const existing = document.getElementById("arToastEl");
      if (existing) existing.remove();
      const el = document.createElement("div");
      el.id = "arToastEl";
      el.className = "ar-toast";
      if (isError) el.style.borderColor = "#ef4444";
      el.textContent = msg;
      document.body.appendChild(el);
      setTimeout(() => el.remove(), 3500);
    }

    async function apiJson(url, options = {}) {
      const resp = await fetch(url, options);
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.detail || `HTTP ${resp.status}`);
      }
      return data;
    }

    async function loadAll() {
      state.loading = true;
      try {
        const incParams = new URLSearchParams();
        if (state.statusFilter) incParams.set("status", state.statusFilter);
        if (state.severityFilter) incParams.set("severity", state.severityFilter);
        const incQuery = incParams.toString() ? `?${incParams.toString()}` : "";

        const [rulesRes, incRes, sumRes, sensRes] = await Promise.all([
          apiJson("/api/v1/alerts/rules"),
          apiJson(`/api/v1/alerts/incidents${incQuery}`),
          apiJson("/api/v1/alerts/reports/summary"),
          apiJson("/api/v1/sensors").catch(() => ({ sensors: [] })),
        ]);
        state.rules = rulesRes.rules || [];
        state.incidents = incRes.incidents || [];
        state.summary = sumRes;
        state.sensors = Array.isArray(sensRes) ? sensRes : (sensRes.sensors || sensRes.items || []);
      } catch (err) {
        toast(err.message || "Failed to load alerts data", true);
      } finally {
        state.loading = false;
        render();
      }
    }

    function renderKpis() {
      const s = state.summary;
      if (!s) return "";
      const env = s.environment || {};
      const inf = s.infrastructure || {};
      const sec = s.security || {};
      const inc = s.incidents || {};
      const activeTotal = (inc.active || 0) + (sec.active_security_alerts || 0);
      return `
        <div class="ar-kpis">
          <div class="ar-kpi">
            <div class="ar-kpi-label">🌡️ ${t("kpi_env")}</div>
            <div class="ar-kpi-val">${env.avg_temp_c != null ? `${env.avg_temp_c} °C` : "—"}</div>
            <div class="ar-kpi-sub">${env.sensor_count || 0} ${t("sensors")} · RH ${env.avg_humidity_pct != null ? `${env.avg_humidity_pct}%` : "—"}</div>
          </div>
          <div class="ar-kpi">
            <div class="ar-kpi-label">🗄️ ${t("kpi_infra")}</div>
            <div class="ar-kpi-val">${inf.u_utilization_pct ?? 0}% U</div>
            <div class="ar-kpi-sub">${inf.rack_count || 0} ${t("racks")} · ${inf.total_power_w || 0} W · ${inf.structured_cables || 0} cables</div>
          </div>
          <div class="ar-kpi">
            <div class="ar-kpi-label">🛡️ ${t("kpi_sec")}</div>
            <div class="ar-kpi-val">${sec.device_count || 0} ${t("devices")}</div>
            <div class="ar-kpi-sub">CCTV: ${sec.cctv_count || 0} · Doors: ${sec.door_access_count || 0} · Alerts: ${sec.active_security_alerts || 0}</div>
          </div>
          <div class="ar-kpi">
            <div class="ar-kpi-label">🔔 ${t("kpi_inc")}</div>
            <div class="ar-kpi-val" style="color:${activeTotal > 0 ? '#ef4444' : '#10b981'}">${activeTotal}</div>
            <div class="ar-kpi-sub">${inc.enabled_rules || 0}/${inc.rule_count || 0} ${t("rules_enabled")} · ${inc.resolved || 0} ${t("resolved")}</div>
          </div>
        </div>
      `;
    }

    function renderRuleForm(rule = null) {
      const isEdit = Boolean(rule);
      const r = rule || {
        name: "",
        enabled: true,
        target_scope: "all_sensors",
        metric_type: "temperature",
        operator: "gt",
        warning_threshold: 27,
        critical_threshold: 30,
        cooldown_minutes: 15,
        notify_webhook_url: "",
        description: "",
      };
      return `
        <form id="arRuleForm" class="ar-card" data-rule-id="${isEdit ? esc(r.id) : ""}">
          <h3 style="margin:0 0 12px 0; font-size:1rem; color:var(--accent-cyan);">
            ${isEdit ? `✏️ ${t("edit")}: ${esc(r.name)}` : t("new_rule")}
          </h3>
          <div class="ar-form-grid">
            <div class="ar-field">
              <label>${t("rule_name")}</label>
              <input name="name" required value="${esc(r.name)}" placeholder="e.g. Hot Aisle Overheat">
            </div>
            <div class="ar-field">
              <label>${t("scope")}</label>
              <select name="target_scope">
                <option value="all_sensors" ${r.target_scope === "all_sensors" ? "selected" : ""}>All Sensors</option>
                <option value="sensor" ${r.target_scope === "sensor" ? "selected" : ""}>Specific Sensor</option>
                <option value="rack_power" ${r.target_scope === "rack_power" ? "selected" : ""}>Rack Power</option>
                <option value="security" ${r.target_scope === "security" ? "selected" : ""}>Security</option>
              </select>
            </div>
            <div class="ar-field">
              <label>${t("metric")}</label>
              <select name="metric_type">
                <option value="temperature" ${r.metric_type === "temperature" ? "selected" : ""}>Temperature (°C)</option>
                <option value="humidity" ${r.metric_type === "humidity" ? "selected" : ""}>Humidity (%RH)</option>
                <option value="power_kw" ${r.metric_type === "power_kw" ? "selected" : ""}>Power (kW)</option>
                <option value="rack_power_pct" ${r.metric_type === "rack_power_pct" ? "selected" : ""}>Rack Power (%)</option>
              </select>
            </div>
            <div class="ar-field">
              <label>${t("operator")}</label>
              <select name="operator">
                <option value="gt" ${r.operator === "gt" ? "selected" : ""}>&gt; (Greater than)</option>
                <option value="gte" ${r.operator === "gte" ? "selected" : ""}>&gt;= (Greater or equal)</option>
                <option value="lt" ${r.operator === "lt" ? "selected" : ""}>&lt; (Less than)</option>
                <option value="lte" ${r.operator === "lte" ? "selected" : ""}>&lt;= (Less or equal)</option>
              </select>
            </div>
            <div class="ar-field">
              <label>${t("warn_th")}</label>
              <input type="number" step="0.1" name="warning_threshold" value="${r.warning_threshold != null ? r.warning_threshold : ""}">
            </div>
            <div class="ar-field">
              <label>${t("crit_th")}</label>
              <input type="number" step="0.1" name="critical_threshold" required value="${r.critical_threshold}">
            </div>
            <div class="ar-field">
              <label>${t("cooldown")}</label>
              <input type="number" min="1" max="1440" name="cooldown_minutes" required value="${r.cooldown_minutes || 15}">
            </div>
            <div class="ar-field">
              <label>${t("webhook")}</label>
              <input type="url" name="notify_webhook_url" value="${esc(r.notify_webhook_url || "")}" placeholder="https://...">
            </div>
          </div>
          <div class="ar-field" style="margin-bottom:12px;">
            <label>${t("description")}</label>
            <input name="description" value="${esc(r.description || "")}" placeholder="Optional operational guidance">
          </div>
          <div class="ar-actions">
            <button type="submit" class="btn btn-primary btn-sm">💾 ${t("save")}</button>
            <button type="button" class="btn btn-secondary btn-sm" id="arCancelRuleBtn">${t("cancel")}</button>
          </div>
        </form>
      `;
    }

    function renderRulesTab() {
      const opLabel = { gt: ">", gte: "≥", lt: "<", lte: "≤" };
      const editingRule = state.editingRuleId
        ? state.rules.find((r) => r.id === state.editingRuleId)
        : null;

      const rows = state.rules.length
        ? state.rules
            .map(
              (r) => `
          <tr>
            <td>
              <strong>${esc(r.name)}</strong>
              ${r.description ? `<div style="font-size:0.76rem;color:var(--text-muted);">${esc(r.description)}</div>` : ""}
            </td>
            <td><span class="ar-badge ar-badge-info">${esc(r.metric_type)}</span> <span style="font-size:0.78rem;color:var(--text-muted);">${esc(r.target_scope)}</span></td>
            <td>
              ${r.warning_threshold != null ? `<span class="ar-badge ar-badge-warn">⚠ ${opLabel[r.operator] || r.operator} ${r.warning_threshold}</span> ` : ""}
              <span class="ar-badge ar-badge-crit">🚨 ${opLabel[r.operator] || r.operator} ${r.critical_threshold}</span>
            </td>
            <td>${r.cooldown_minutes}m</td>
            <td>
              <span class="ar-badge ${r.enabled ? "ar-badge-ok" : "ar-badge-muted"}">
                ${r.enabled ? t("enabled") : t("disabled")}
              </span>
            </td>
            <td>
              ${
                canWrite
                  ? `<div class="ar-actions">
                      <button class="btn btn-secondary btn-sm ar-toggle-rule" data-id="${esc(r.id)}" data-enabled="${r.enabled ? "1" : "0"}">${r.enabled ? t("disable") : t("enable")}</button>
                      <button class="btn btn-secondary btn-sm ar-edit-rule" data-id="${esc(r.id)}">✏️ ${t("edit")}</button>
                      <button class="btn btn-danger btn-sm ar-del-rule" data-id="${esc(r.id)}">🗑️</button>
                    </div>`
                  : "—"
              }
            </td>
          </tr>`
            )
            .join("")
        : `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:20px;">${t("no_rules")}</td></tr>`;

      return `
        ${canWrite ? `<div class="ar-actions" style="margin-bottom:12px;">
          <button class="btn btn-primary btn-sm" id="arNewRuleBtn">${t("new_rule")}</button>
          <button class="btn btn-secondary btn-sm" id="arEvalRulesBtn">⚡ ${t("evaluate_now")}</button>
        </div>` : ""}
        ${state.showRuleForm || editingRule ? renderRuleForm(editingRule) : ""}
        <div class="ar-card ar-table-wrap">
          <table class="ar-table">
            <thead>
              <tr>
                <th>${t("rule_name")}</th>
                <th>${t("metric")} / ${t("scope")}</th>
                <th>${t("warn_th")} / ${t("crit_th")}</th>
                <th>${t("cooldown")}</th>
                <th>${t("filter_status")}</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      `;
    }

    function renderIncidentForm() {
      const sensorOpts = state.sensors.length
        ? state.sensors.map((s) => `<option value="${esc(s.id)}">${esc(s.name)} (${esc(s.identifier)})</option>`).join("")
        : `<option value="">No sensors available</option>`;
      return `
        <form id="arIncidentForm" class="ar-card">
          <h3 style="margin:0 0 12px 0; font-size:1rem; color:var(--accent-cyan);">${t("log_incident")}</h3>
          <div class="ar-form-grid">
            <div class="ar-field">
              <label>${t("sensor")}</label>
              <select name="sensor_id" required>${sensorOpts}</select>
            </div>
            <div class="ar-field">
              <label>${t("metric")}</label>
              <select name="metric_type">
                <option value="temperature">Temperature</option>
                <option value="humidity">Humidity</option>
                <option value="power_kw">Power (kW)</option>
              </select>
            </div>
            <div class="ar-field">
              <label>${t("filter_severity")}</label>
              <select name="severity">
                <option value="warning">${t("warning")}</option>
                <option value="critical">${t("critical")}</option>
              </select>
            </div>
            <div class="ar-field">
              <label>${t("reading")}</label>
              <input type="number" step="0.1" name="reading_value" required value="32.5">
            </div>
            <div class="ar-field">
              <label>${t("threshold")}</label>
              <input type="number" step="0.1" name="threshold_value" required value="30.0">
            </div>
          </div>
          <div class="ar-form-grid">
            <div class="ar-field">
              <label>${t("message")}</label>
              <input name="message" required placeholder="Manual operator incident report">
            </div>
            <div class="ar-field">
              <label>${t("comment")}</label>
              <input name="comment" placeholder="Optional investigation notes">
            </div>
          </div>
          <div class="ar-actions">
            <button type="submit" class="btn btn-primary btn-sm">💾 ${t("save")}</button>
            <button type="button" class="btn btn-secondary btn-sm" id="arCancelIncBtn">${t("cancel")}</button>
          </div>
        </form>
      `;
    }

    function renderEditIncidentForm(inc) {
      return `
        <form id="arEditIncidentForm" class="ar-card" data-inc-id="${esc(inc.id)}">
          <h3 style="margin:0 0 12px 0; font-size:1rem; color:var(--accent-cyan);">✏️ ${t("edit")}: ${esc(inc.sensor_name)}</h3>
          <div class="ar-form-grid">
            <div class="ar-field">
              <label>${t("filter_status")}</label>
              <select name="status">
                <option value="active" ${inc.status === "active" ? "selected" : ""}>${t("active")}</option>
                <option value="acknowledged" ${inc.status === "acknowledged" ? "selected" : ""}>${t("acknowledged")}</option>
                <option value="resolved" ${inc.status === "resolved" ? "selected" : ""}>${t("resolved")}</option>
              </select>
            </div>
            <div class="ar-field">
              <label>${t("filter_severity")}</label>
              <select name="severity">
                <option value="warning" ${inc.severity === "warning" ? "selected" : ""}>${t("warning")}</option>
                <option value="critical" ${inc.severity === "critical" ? "selected" : ""}>${t("critical")}</option>
              </select>
            </div>
            <div class="ar-field">
              <label>${t("message")}</label>
              <input name="message" required value="${esc(inc.message)}">
            </div>
            <div class="ar-field">
              <label>${t("comment")}</label>
              <input name="comment" value="${esc(inc.comment || "")}">
            </div>
          </div>
          <div class="ar-actions">
            <button type="submit" class="btn btn-primary btn-sm">💾 ${t("save")}</button>
            <button type="button" class="btn btn-secondary btn-sm" id="arCancelEditIncBtn">${t("cancel")}</button>
          </div>
        </form>
      `;
    }

    function renderIncidentsTab() {
      const editingInc = state.editingIncidentId
        ? state.incidents.find((i) => i.id === state.editingIncidentId && i.source === "environment")
        : null;

      const rows = state.incidents.length
        ? state.incidents
            .map((inc) => {
              const sevCls = inc.severity === "critical" ? "ar-badge-crit" : "ar-badge-warn";
              const stCls =
                inc.status === "resolved"
                  ? "ar-badge-ok"
                  : inc.status === "acknowledged"
                  ? "ar-badge-info"
                  : "ar-badge-crit";
              const isEnv = inc.source === "environment";
              const ts = inc.created_at ? inc.created_at.replace("T", " ").slice(0, 19) : "—";
              return `
                <tr>
                  <td style="white-space:nowrap;font-size:0.78rem;color:var(--text-muted);">${esc(ts)}</td>
                  <td>
                    <span class="ar-badge ${isEnv ? "ar-badge-info" : "ar-badge-warn"}">${isEnv ? t("env_source") : t("security_source")}</span>
                    <strong style="margin-left:4px;">${esc(inc.sensor_name)}</strong>
                    <div style="font-size:0.76rem;color:var(--text-muted);">${esc(inc.metric_type)}${inc.reading_value != null ? ` · ${inc.reading_value} (th: ${inc.threshold_value})` : ""}</div>
                  </td>
                  <td><span class="ar-badge ${sevCls}">${esc(inc.severity.toUpperCase())}</span></td>
                  <td><span class="ar-badge ${stCls}">${esc(inc.status)}</span></td>
                  <td>
                    <div>${esc(inc.message)}</div>
                    ${inc.comment ? `<div style="font-size:0.76rem;color:var(--text-muted);margin-top:2px;">💬 ${esc(inc.comment)}</div>` : ""}
                  </td>
                  <td>
                    ${
                      isEnv && canWrite
                        ? `<div class="ar-actions">
                            ${inc.status === "active" ? `<button class="btn btn-secondary btn-sm ar-inc-status" data-id="${esc(inc.id)}" data-status="acknowledged">✓ ${t("ack")}</button>` : ""}
                            ${inc.status !== "resolved" ? `<button class="btn btn-primary btn-sm ar-inc-status" data-id="${esc(inc.id)}" data-status="resolved">✓ ${t("resolve")}</button>` : ""}
                            <button class="btn btn-secondary btn-sm ar-edit-inc" data-id="${esc(inc.id)}">✏️</button>
                            <button class="btn btn-danger btn-sm ar-del-inc" data-id="${esc(inc.id)}">🗑️</button>
                          </div>`
                        : !isEnv
                        ? `<a href="/security" class="btn btn-secondary btn-sm">${t("open_security")}</a>`
                        : "—"
                    }
                  </td>
                </tr>
              `;
            })
            .join("")
        : `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:20px;">${t("no_incidents")}</td></tr>`;

      return `
        <div class="ar-actions" style="justify-content:space-between; margin-bottom:12px;">
          <div class="ar-actions">
            <select id="arFilterStatus" style="padding:6px 10px;border-radius:8px;border:1px solid var(--border-color);background:var(--bg-surface);color:var(--text-main);">
              <option value="" ${!state.statusFilter ? "selected" : ""}>${t("filter_status")}: ${t("all")}</option>
              <option value="active" ${state.statusFilter === "active" ? "selected" : ""}>${t("active")}</option>
              <option value="acknowledged" ${state.statusFilter === "acknowledged" ? "selected" : ""}>${t("acknowledged")}</option>
              <option value="resolved" ${state.statusFilter === "resolved" ? "selected" : ""}>${t("resolved")}</option>
            </select>
            <select id="arFilterSeverity" style="padding:6px 10px;border-radius:8px;border:1px solid var(--border-color);background:var(--bg-surface);color:var(--text-main);">
              <option value="" ${!state.severityFilter ? "selected" : ""}>${t("filter_severity")}: ${t("all")}</option>
              <option value="critical" ${state.severityFilter === "critical" ? "selected" : ""}>${t("critical")}</option>
              <option value="warning" ${state.severityFilter === "warning" ? "selected" : ""}>${t("warning")}</option>
            </select>
          </div>
          ${canWrite ? `<div class="ar-actions">
            <button class="btn btn-primary btn-sm" id="arNewIncBtn">${t("log_incident")}</button>
            <button class="btn btn-secondary btn-sm" id="arEvalFromIncBtn">⚡ ${t("evaluate_now")}</button>
          </div>` : ""}
        </div>
        ${state.showIncidentForm ? renderIncidentForm() : ""}
        ${editingInc ? renderEditIncidentForm(editingInc) : ""}
        <div class="ar-card ar-table-wrap">
          <table class="ar-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Source / Metric</th>
                <th>${t("filter_severity")}</th>
                <th>${t("filter_status")}</th>
                <th>${t("message")}</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      `;
    }

    function renderReportsTab() {
      const s = state.summary;
      if (!s) return `<div class="ar-card">Loading report summary...</div>`;
      const env = s.environment || {};
      const inf = s.infrastructure || {};
      const sec = s.security || {};
      const inc = s.incidents || {};

      const sensorRows = (env.sensors || []).length
        ? env.sensors
            .map(
              (sn) => `
          <tr>
            <td><strong>${esc(sn.name)}</strong></td>
            <td style="color:var(--text-muted);">${esc(sn.identifier)}</td>
            <td>${sn.temp_c != null ? `${sn.temp_c} °C` : "—"}</td>
            <td>${sn.humidity_pct != null ? `${sn.humidity_pct}%` : "—"}</td>
            <td><span class="ar-badge ${sn.status === "online" ? "ar-badge-ok" : "ar-badge-muted"}">${esc(sn.status)}</span></td>
          </tr>`
            )
            .join("")
        : `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:14px;">No sensors registered.</td></tr>`;

      return `
        <div class="ar-card" style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:10px;">
          <div>
            <strong style="font-size:1rem;">📊 DCIM Executive &amp; SLA Report</strong>
            <div style="font-size:0.78rem;color:var(--text-muted);">Generated: ${esc((s.generated_at || "").replace("T", " ").slice(0, 19))} UTC</div>
          </div>
          <div class="ar-actions">
            <a id="arExportCsvBtn" class="btn btn-primary btn-sm" href="/api/v1/alerts/reports/export?format=csv">⬇ ${t("export_csv")}</a>
            <a id="arExportJsonBtn" class="btn btn-secondary btn-sm" href="/api/v1/alerts/reports/export?format=json">⬇ ${t("export_json")}</a>
            <a id="arExportHtmlBtn" class="btn btn-secondary btn-sm" href="/api/v1/alerts/reports/export?format=html" target="_blank" rel="noopener">🖨️ ${t("export_html")}</a>
          </div>
        </div>

        <div class="ar-grid-2">
          <div class="ar-card">
            <h3 style="margin:0 0 10px 0; font-size:0.95rem; color:var(--accent-cyan);">🗄️ ${t("infra_summary")}</h3>
            <table class="ar-table">
              <tbody>
                <tr><td>Total Racks</td><td><strong>${inf.rack_count || 0}</strong></td></tr>
                <tr><td>Mounted Hardware Devices</td><td><strong>${inf.mounted_devices || 0}</strong></td></tr>
                <tr><td>U-Space Utilization</td><td><strong>${inf.u_used || 0} / ${inf.u_total || 0} U (${inf.u_utilization_pct || 0}%)</strong></td></tr>
                <tr><td>Total Rack Power Budget</td><td><strong>${inf.total_power_w || 0} W</strong></td></tr>
                <tr><td>Structured Cables</td><td><strong>${inf.structured_cables || 0}</strong></td></tr>
              </tbody>
            </table>
          </div>
          <div class="ar-card">
            <h3 style="margin:0 0 10px 0; font-size:0.95rem; color:var(--accent-cyan);">🛡️ ${t("sec_summary")} &amp; ${t("inc_summary")}</h3>
            <table class="ar-table">
              <tbody>
                <tr><td>Security Devices (CCTV / Doors / Sensors)</td><td><strong>${sec.device_count || 0}</strong> (${sec.cctv_count || 0} / ${sec.door_access_count || 0} / ${sec.sensor_count || 0})</td></tr>
                <tr><td>Active Security Alerts</td><td><strong>${sec.active_security_alerts || 0}</strong></td></tr>
                <tr><td>Threshold Rules Enabled</td><td><strong>${inc.enabled_rules || 0} / ${inc.rule_count || 0}</strong></td></tr>
                <tr><td>Incidents (Active / Ack / Resolved)</td><td><strong>${inc.active || 0} / ${inc.acknowledged || 0} / ${inc.resolved || 0}</strong></td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="ar-card ar-table-wrap">
          <h3 style="margin:0 0 10px 0; font-size:0.95rem; color:var(--accent-cyan);">🌡️ ${t("env_summary")}</h3>
          <table class="ar-table">
            <thead>
              <tr><th>Name</th><th>Identifier</th><th>Temp</th><th>Humidity</th><th>Status</th></tr>
            </thead>
            <tbody>${sensorRows}</tbody>
          </table>
        </div>
      `;
    }

    function bindEvents() {
      root.querySelectorAll(".ar-tab-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          state.tab = btn.dataset.tab;
          state.showRuleForm = false;
          state.editingRuleId = null;
          state.showIncidentForm = false;
          state.editingIncidentId = null;
          render();
        });
      });

      const newRuleBtn = root.querySelector("#arNewRuleBtn");
      if (newRuleBtn) {
        newRuleBtn.addEventListener("click", () => {
          state.editingRuleId = null;
          state.showRuleForm = !state.showRuleForm;
          render();
        });
      }

      const cancelRuleBtn = root.querySelector("#arCancelRuleBtn");
      if (cancelRuleBtn) {
        cancelRuleBtn.addEventListener("click", () => {
          state.showRuleForm = false;
          state.editingRuleId = null;
          render();
        });
      }

      const ruleForm = root.querySelector("#arRuleForm");
      if (ruleForm) {
        ruleForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const fd = new FormData(ruleForm);
          const ruleId = ruleForm.dataset.ruleId;
          const warnRaw = fd.get("warning_threshold");
          const payload = {
            name: String(fd.get("name") || "").trim(),
            target_scope: String(fd.get("target_scope") || "all_sensors"),
            metric_type: String(fd.get("metric_type") || "temperature"),
            operator: String(fd.get("operator") || "gt"),
            warning_threshold: warnRaw !== "" && warnRaw != null ? parseFloat(warnRaw) : null,
            critical_threshold: parseFloat(fd.get("critical_threshold")),
            cooldown_minutes: parseInt(fd.get("cooldown_minutes"), 10) || 15,
            notify_webhook_url: String(fd.get("notify_webhook_url") || "").trim(),
            description: String(fd.get("description") || "").trim(),
          };
          try {
            await apiJson(ruleId ? `/api/v1/alerts/rules/${ruleId}` : "/api/v1/alerts/rules", {
              method: ruleId ? "PATCH" : "POST",
              headers: csrfHeaders(true),
              body: JSON.stringify(payload),
            });
            state.showRuleForm = false;
            state.editingRuleId = null;
            toast(t("saved_ok"));
            await loadAll();
          } catch (err) {
            toast(err.message, true);
          }
        });
      }

      root.querySelectorAll(".ar-toggle-rule").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const id = btn.dataset.id;
          const nextEnabled = btn.dataset.enabled !== "1";
          try {
            await apiJson(`/api/v1/alerts/rules/${id}`, {
              method: "PATCH",
              headers: csrfHeaders(true),
              body: JSON.stringify({ enabled: nextEnabled }),
            });
            toast(t("saved_ok"));
            await loadAll();
          } catch (err) {
            toast(err.message, true);
          }
        });
      });

      root.querySelectorAll(".ar-edit-rule").forEach((btn) => {
        btn.addEventListener("click", () => {
          state.showRuleForm = false;
          state.editingRuleId = btn.dataset.id;
          render();
        });
      });

      root.querySelectorAll(".ar-del-rule").forEach((btn) => {
        btn.addEventListener("click", async () => {
          if (!confirm(t("confirm_del_rule"))) return;
          try {
            await apiJson(`/api/v1/alerts/rules/${btn.dataset.id}`, {
              method: "DELETE",
              headers: csrfHeaders(false),
            });
            toast(t("deleted_ok"));
            await loadAll();
          } catch (err) {
            toast(err.message, true);
          }
        });
      });

      const runEvaluate = async () => {
        try {
          const res = await apiJson("/api/v1/alerts/evaluate", {
            method: "POST",
            headers: csrfHeaders(false),
          });
          toast(`${t("eval_done")}: ${res.triggered} ${t("triggered")}`);
          await loadAll();
        } catch (err) {
          toast(err.message, true);
        }
      };
      const evalBtn = root.querySelector("#arEvalRulesBtn");
      if (evalBtn) evalBtn.addEventListener("click", runEvaluate);
      const evalIncBtn = root.querySelector("#arEvalFromIncBtn");
      if (evalIncBtn) evalIncBtn.addEventListener("click", runEvaluate);

      const filterStatus = root.querySelector("#arFilterStatus");
      if (filterStatus) {
        filterStatus.addEventListener("change", () => {
          state.statusFilter = filterStatus.value;
          loadAll();
        });
      }
      const filterSeverity = root.querySelector("#arFilterSeverity");
      if (filterSeverity) {
        filterSeverity.addEventListener("change", () => {
          state.severityFilter = filterSeverity.value;
          loadAll();
        });
      }

      const newIncBtn = root.querySelector("#arNewIncBtn");
      if (newIncBtn) {
        newIncBtn.addEventListener("click", () => {
          state.editingIncidentId = null;
          state.showIncidentForm = !state.showIncidentForm;
          render();
        });
      }
      const cancelIncBtn = root.querySelector("#arCancelIncBtn");
      if (cancelIncBtn) {
        cancelIncBtn.addEventListener("click", () => {
          state.showIncidentForm = false;
          render();
        });
      }

      const incForm = root.querySelector("#arIncidentForm");
      if (incForm) {
        incForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const fd = new FormData(incForm);
          const payload = {
            sensor_id: String(fd.get("sensor_id") || ""),
            metric_type: String(fd.get("metric_type") || "temperature"),
            severity: String(fd.get("severity") || "warning"),
            reading_value: parseFloat(fd.get("reading_value")) || 0,
            threshold_value: parseFloat(fd.get("threshold_value")) || 0,
            message: String(fd.get("message") || "").trim(),
            comment: String(fd.get("comment") || "").trim(),
          };
          try {
            await apiJson("/api/v1/alerts/incidents", {
              method: "POST",
              headers: csrfHeaders(true),
              body: JSON.stringify(payload),
            });
            state.showIncidentForm = false;
            toast(t("saved_ok"));
            await loadAll();
          } catch (err) {
            toast(err.message, true);
          }
        });
      }

      const editIncForm = root.querySelector("#arEditIncidentForm");
      if (editIncForm) {
        editIncForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const fd = new FormData(editIncForm);
          const id = editIncForm.dataset.incId;
          try {
            await apiJson(`/api/v1/alerts/incidents/${id}`, {
              method: "PATCH",
              headers: csrfHeaders(true),
              body: JSON.stringify({
                status: String(fd.get("status") || "active"),
                severity: String(fd.get("severity") || "warning"),
                message: String(fd.get("message") || "").trim(),
                comment: String(fd.get("comment") || "").trim(),
              }),
            });
            state.editingIncidentId = null;
            toast(t("saved_ok"));
            await loadAll();
          } catch (err) {
            toast(err.message, true);
          }
        });
      }
      const cancelEditIncBtn = root.querySelector("#arCancelEditIncBtn");
      if (cancelEditIncBtn) {
        cancelEditIncBtn.addEventListener("click", () => {
          state.editingIncidentId = null;
          render();
        });
      }

      root.querySelectorAll(".ar-inc-status").forEach((btn) => {
        btn.addEventListener("click", async () => {
          try {
            await apiJson(`/api/v1/alerts/incidents/${btn.dataset.id}`, {
              method: "PATCH",
              headers: csrfHeaders(true),
              body: JSON.stringify({ status: btn.dataset.status }),
            });
            toast(t("saved_ok"));
            await loadAll();
          } catch (err) {
            toast(err.message, true);
          }
        });
      });

      root.querySelectorAll(".ar-edit-inc").forEach((btn) => {
        btn.addEventListener("click", () => {
          state.showIncidentForm = false;
          state.editingIncidentId = btn.dataset.id;
          render();
        });
      });

      root.querySelectorAll(".ar-del-inc").forEach((btn) => {
        btn.addEventListener("click", async () => {
          if (!confirm(t("confirm_del_inc"))) return;
          try {
            await apiJson(`/api/v1/alerts/incidents/${btn.dataset.id}`, {
              method: "DELETE",
              headers: csrfHeaders(false),
            });
            toast(t("deleted_ok"));
            await loadAll();
          } catch (err) {
            toast(err.message, true);
          }
        });
      });
    }

    function render() {
      const bodyHtml =
        state.tab === "rules"
          ? renderRulesTab()
          : state.tab === "incidents"
          ? renderIncidentsTab()
          : renderReportsTab();

      root.innerHTML = `
        ${renderKpis()}
        <div class="ar-tabs">
          <div class="ar-tab-group" role="tablist">
            <button class="ar-tab-btn ${state.tab === "rules" ? "active" : ""}" data-tab="rules">⚙️ ${t("tab_rules")} (${state.rules.length})</button>
            <button class="ar-tab-btn ${state.tab === "incidents" ? "active" : ""}" data-tab="incidents">🚨 ${t("tab_incidents")} (${state.incidents.length})</button>
            <button class="ar-tab-btn ${state.tab === "reports" ? "active" : ""}" data-tab="reports">📊 ${t("tab_reports")}</button>
          </div>
        </div>
        ${bodyHtml}
      `;
      bindEvents();
    }

    render();
    loadAll();

    return { reload: loadAll, setTab: (tb) => { state.tab = tb; render(); } };
  }

  window.AlertsReportsUI = { mount };
})();
