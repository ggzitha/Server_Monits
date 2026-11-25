/**
 * cable_trace.js - Native NetBox-Style End-to-End SVG Cable Trace Viewer (Phase 5).
 *
 * Shared across BOTH `/racks` (Rack Elevation View) and `/` (3D Rack `.fp3d-wall` Popup).
 * - Renders top-to-bottom vector SVG cable trace (origin device, port boxes, colored cables,
 *   patch-panel front<->rear pass-throughs, fan-out branches, destination devices).
 * - Right-side "Related Paths" summary table + "Download SVG" export.
 * - 100% theme-variable styled (Dark + Light), EN + ID i18n, zero iframes, zero external deps.
 */
(function () {
  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function injectTraceStyles() {
    if (document.getElementById("monits-cable-trace-css")) return;
    const style = document.createElement("style");
    style.id = "monits-cable-trace-css";
    style.textContent = `
      .ct-overlay {
        position: fixed;
        inset: 48px 16px 16px 16px;
        z-index: 3500;
        display: flex;
        flex-direction: column;
        gap: 10px;
        padding: 14px 18px;
        border-radius: 16px;
        background: var(--bg-drawer);
        backdrop-filter: blur(18px);
        -webkit-backdrop-filter: blur(18px);
        border: 1px solid var(--border-color);
        box-shadow: var(--card-shadow);
        color: var(--text-main);
        overflow: hidden;
        animation: ctFadeIn 0.14s ease-out;
      }
      @keyframes ctFadeIn {
        from { opacity: 0; transform: scale(0.985); }
        to { opacity: 1; transform: scale(1); }
      }
      .ct-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        flex-wrap: wrap;
        padding-bottom: 10px;
        border-bottom: 1px solid var(--border-color);
        flex-shrink: 0;
      }
      .ct-title {
        font-size: 15px;
        font-weight: 700;
        color: var(--text-main);
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
      }
      .ct-sub {
        font-size: 12px;
        font-weight: 500;
        color: var(--text-muted);
      }
      .ct-tools {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        flex-wrap: wrap;
      }
      .ct-chip {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 5px 11px;
        border-radius: 999px;
        border: 1px solid var(--border-color);
        background: var(--bg-card-inner);
        color: var(--text-main);
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
        transition: border-color 0.15s, background 0.15s;
      }
      .ct-chip:hover, .ct-chip.active {
        border-color: var(--accent-cyan);
        background: var(--accent-cyan-soft);
        color: var(--accent-cyan);
      }
      .ct-ports-bar {
        display: flex;
        align-items: center;
        gap: 6px;
        flex-wrap: wrap;
        font-size: 12px;
        flex-shrink: 0;
      }
      .ct-body {
        flex: 1;
        min-height: 0;
        display: grid;
        grid-template-columns: minmax(340px, 1.35fr) minmax(280px, 1fr);
        gap: 16px;
        overflow: hidden;
      }
      @media (max-width: 960px) {
        .ct-body { grid-template-columns: 1fr; overflow: auto; }
      }
      .ct-svg-pane {
        background: var(--bg-app);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        overflow: auto;
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 16px;
        gap: 12px;
      }
      .ct-svg-wrap {
        width: 100%;
        display: flex;
        justify-content: center;
      }
      .ct-svg-wrap svg {
        max-width: 100%;
        height: auto;
      }
      .ct-side-pane {
        background: var(--bg-card-inner);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 12px 14px;
        overflow: auto;
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .ct-side-title {
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--accent-cyan);
        margin: 0;
      }
      .ct-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
      }
      .ct-table th {
        text-align: left;
        padding: 6px 8px;
        color: var(--text-muted);
        border-bottom: 1px solid var(--border-color);
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }
      .ct-table td {
        padding: 7px 8px;
        border-bottom: 1px solid var(--border-subtle);
        color: var(--text-main);
        vertical-align: top;
      }
      .ct-table tr.ct-row-click { cursor: pointer; }
      .ct-table tr.ct-row-click:hover { background: var(--accent-cyan-soft); }
      .ct-empty {
        text-align: center;
        color: var(--text-muted);
        padding: 36px 20px;
        font-size: 13px;
      }
    `;
    document.head.appendChild(style);
  }

  function isLightTheme() {
    return (document.documentElement.dataset.theme || "neon") === "light";
  }

  /**
   * Build a clean, standalone NetBox-style top-to-bottom SVG diagram for one or more traced paths.
   */
  function buildTraceSvg(traceData) {
    const paths = Array.isArray(traceData?.paths) ? traceData.paths : [];
    const light = isLightTheme();
    const bgColor = light ? "#f8fafc" : "#0b1220";
    const portBg = light ? "#f1f5f9" : "#1e293b";
    const portStroke = light ? "#94a3b8" : "#475569";
    const portText = light ? "#0f172a" : "#e2e8f0";
    const metaText = light ? "#334155" : "#cbd5e1";
    const mutedText = light ? "#64748b" : "#94a3b8";

    if (!paths.length) {
      return `<svg xmlns="http://www.w3.org/2000/svg" width="520" height="140" viewBox="0 0 520 140">
        <rect width="520" height="140" rx="10" fill="${bgColor}"/>
        <text x="260" y="74" text-anchor="middle" fill="${mutedText}" font-family="system-ui, sans-serif" font-size="14">No cable connections found for this device / port.</text>
      </svg>`;
    }

    // Group paths into columns (each branch side-by-side if fan-out, or single centered column)
    const colW = 310;
    const colGap = 28;
    const padX = 28;
    const padY = 22;
    const devH = 62;
    const portH = 26;
    const cableGap = 86;

    const maxNodes = Math.max(...paths.map((p) => (p.nodes || []).length), 2);
    const totalW = Math.max(460, padX * 2 + paths.length * colW + (paths.length - 1) * colGap);

    // Compute Y positions for each hop level
    let yCursor = padY;
    const levelY = [];
    for (let lvl = 0; lvl < maxNodes; lvl++) {
      levelY.push(yCursor);
      // Device box + incoming/outgoing port bars + cable run below
      const hasIn = lvl > 0;
      const hasOut = lvl < maxNodes - 1;
      yCursor += (hasIn ? portH + 2 : 0) + devH + (hasOut ? portH + 2 : 0) + (lvl < maxNodes - 1 ? cableGap : 0);
    }
    const totalH = yCursor + padY;

    const parts = [];
    parts.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${totalW}" height="${totalH}" viewBox="0 0 ${totalW} ${totalH}" style="font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;">`);
    parts.push(`<rect width="${totalW}" height="${totalH}" rx="10" fill="${bgColor}"/>`);

    paths.forEach((p, colIdx) => {
      const cx = paths.length === 1 ? totalW / 2 : padX + colIdx * (colW + colGap) + colW / 2;
      const boxW = Math.min(290, colW - 10);
      const boxX = cx - boxW / 2;
      const nodes = p.nodes || [];
      const segs = p.segments || [];

      nodes.forEach((node, idx) => {
        let ny = levelY[idx];
        const hasIn = idx > 0 && node.in_port;
        const hasOut = idx < nodes.length - 1 && node.out_port;

        // Incoming port pill (top of device)
        if (hasIn) {
          parts.push(`<rect x="${boxX}" y="${ny}" width="${boxW}" height="${portH}" rx="5" fill="${portBg}" stroke="${portStroke}" stroke-width="1.2"/>`);
          const sideTag = node.in_side === "rear" ? " [rear]" : "";
          parts.push(`<text x="${cx}" y="${ny + 17}" text-anchor="middle" fill="${portText}" font-size="11.5" font-weight="600">${esc(node.in_port + sideTag)}</text>`);
          ny += portH + 2;
        }

        // Device box (NetBox style: solid header color, device name, model, rack & U-slot)
        const fillCol = node.device_type === "patch_panel" ? "#546e7a" : (node.color || "#0284c7");
        parts.push(`<rect x="${boxX}" y="${ny}" width="${boxW}" height="${devH}" rx="8" fill="${esc(fillCol)}" stroke="rgba(255,255,255,0.2)" stroke-width="1"/>`);
        parts.push(`<text x="${cx}" y="${ny + 20}" text-anchor="middle" fill="#ffffff" font-size="13" font-weight="700">${esc(node.name)}</text>`);
        const modelStr = [node.manufacturer, node.model].filter(Boolean).join(" ") || node.device_type;
        parts.push(`<text x="${cx}" y="${ny + 37}" text-anchor="middle" fill="rgba(255,255,255,0.9)" font-size="11">${esc(modelStr)}</text>`);
        const locStr = node.rack_name ? `${node.rack_name} · U${node.u_position || 1}` : `U${node.u_position || 1}`;
        parts.push(`<text x="${cx}" y="${ny + 53}" text-anchor="middle" fill="rgba(255,255,255,0.78)" font-size="10.5">${esc(locStr)}</text>`);
        ny += devH;

        // Outgoing port pill (bottom of device)
        if (hasOut) {
          ny += 2;
          parts.push(`<rect x="${boxX}" y="${ny}" width="${boxW}" height="${portH}" rx="5" fill="${portBg}" stroke="${portStroke}" stroke-width="1.2"/>`);
          const sideTag = node.out_side === "rear" ? " [rear]" : "";
          parts.push(`<text x="${cx}" y="${ny + 17}" text-anchor="middle" fill="${portText}" font-size="11.5" font-weight="600">${esc(node.out_port + sideTag)}</text>`);
          ny += portH;
        }

        // Cable segment connecting to next node
        if (idx < segs.length) {
          const seg = segs[idx];
          const nextY = levelY[idx + 1];
          const midY = (ny + nextY) / 2;
          const cColor = seg.color || "#22c55e";
          const dash = seg.status === "planned" ? ' stroke-dasharray="6,4"' : "";

          // Outer dark casing + inner colored cable core (NetBox visual style)
          parts.push(`<line x1="${cx}" y1="${ny}" x2="${cx}" y2="${nextY}" stroke="${light ? '#334155' : '#020617'}" stroke-width="8" stroke-linecap="round"${dash}/>`);
          parts.push(`<line x1="${cx}" y1="${ny}" x2="${cx}" y2="${nextY}" stroke="${esc(cColor)}" stroke-width="5" stroke-linecap="round"${dash}/>`);

          // Cable label + status + type/length to the right of the line
          const lenTxt = seg.length_m != null ? ` · ${seg.length_m}m` : "";
          const statusLbl = (seg.status || "connected").charAt(0).toUpperCase() + (seg.status || "connected").slice(1);
          parts.push(`<text x="${cx + 12}" y="${midY - 4}" fill="${metaText}" font-size="12" font-weight="700">${esc(seg.label)}</text>`);
          parts.push(`<text x="${cx + 12}" y="${midY + 12}" fill="${mutedText}" font-size="11">${esc(statusLbl)} · ${esc(seg.cable_type || "fiber")}${esc(lenTxt)}</text>`);
        }
      });
    });

    parts.push(`</svg>`);
    return parts.join("");
  }

  function close() {
    const el = document.getElementById("monitsCableTraceOverlay");
    if (el) el.remove();
  }

  async function open(deviceId, port = null, opts = {}) {
    if (!deviceId) return;
    injectTraceStyles();
    const isId = (opts.lang || document.documentElement.lang || "en").startsWith("id");
    const t = (en, id) => (isId ? id : en);

    let root = document.getElementById("monitsCableTraceOverlay");
    if (!root) {
      root = document.createElement("div");
      root.id = "monitsCableTraceOverlay";
      root.className = "ct-overlay";
      root.setAttribute("role", "dialog");
      root.setAttribute("aria-modal", "true");
      document.body.appendChild(root);
    }

    root.innerHTML = `<div class="ct-head"><span class="ct-title">🔗 ${t("Loading Cable Trace...", "Memuat Jejak Kabel...")}</span><button type="button" class="ct-chip" aria-label="✕" id="ctBtnClose">✕</button></div>`;
    root.querySelector("#ctBtnClose")?.addEventListener("click", close);

    const qs = port ? `?port=${encodeURIComponent(port)}` : "";
    let data = null;
    try {
      const res = await fetch(`/api/v1/racks/devices/${encodeURIComponent(deviceId)}/trace${qs}`);
      if (res.ok) data = await res.json();
    } catch (e) {}

    if (!data || !data.origin) {
      root.innerHTML = `
        <div class="ct-head">
          <span class="ct-title">🔗 ${t("Cable Trace", "Jejak Kabel")}</span>
          <button type="button" class="ct-chip" aria-label="✕" id="ctBtnClose">✕</button>
        </div>
        <div class="ct-empty">${t("Could not load cable trace for this device.", "Gagal memuat jejak kabel untuk perangkat ini.")}</div>
      `;
      root.querySelector("#ctBtnClose")?.addEventListener("click", close);
      return;
    }

    const svgStr = buildTraceSvg(data);
    const ports = data.connected_ports || [];
    const rel = data.related_paths || [];
    const activePort = port || "";
    const titlePort = activePort ? ` · ${activePort}` : "";

    const portChipsHtml = ports.length
      ? `
        <div class="ct-ports-bar">
          <span class="ct-sub">${t("Interface / Port:", "Antarmuka / Port:")}</span>
          <button type="button" class="ct-chip ${!activePort ? "active" : ""}" data-ct-port="">${t("All Ports", "Semua Port")} (${ports.length})</button>
          ${ports.map((pName) => `<button type="button" class="ct-chip ${activePort.toLowerCase() === pName.toLowerCase() ? "active" : ""}" data-ct-port="${esc(pName)}">${esc(pName)}</button>`).join("")}
        </div>
      `
      : "";

    const relatedRows = rel.length
      ? rel
          .map(
            (r) => `
          <tr class="ct-row-click" data-ct-row-port="${esc(r.origin_port || "")}">
            <td>
              <strong>${esc(r.origin_device)}</strong><br/>
              <span class="ct-sub">${esc(r.origin_port || "")}${r.origin_rack ? " · " + esc(r.origin_rack) : ""}</span>
            </td>
            <td>
              <strong>${esc(r.destination_device)}</strong><br/>
              <span class="ct-sub">${esc(r.destination_port || "")}${r.destination_rack ? " · " + esc(r.destination_rack) : ""}</span>
            </td>
            <td>${r.segments} ${t("hop(s)", "hop")}${r.total_length_m ? `<br/><span class="ct-sub">${r.total_length_m} m</span>` : ""}</td>
          </tr>`
          )
          .join("")
      : `<tr><td colspan="3" class="ct-sub" style="text-align:center; padding:16px;">${t("None found", "Tidak ada jalur terkait")}</td></tr>`;

    root.innerHTML = `
      <div class="ct-head">
        <div class="ct-title">
          <span>🔗 ${t("Cable Trace", "Jejak Kabel")}: ${esc(data.origin.name)}${esc(titlePort)}</span>
          <span class="ct-sub">${esc(data.origin.rack_name || "")} · U${data.origin.u_position || 1} · ${data.total_paths} ${t("path(s)", "jalur")}</span>
        </div>
        <div class="ct-tools">
          <button type="button" class="ct-chip" id="ctBtnDownloadSvg">⬇ ${t("Download SVG", "Unduh SVG")}</button>
          <button type="button" class="ct-chip" aria-label="✕" id="ctBtnClose">✕</button>
        </div>
      </div>
      ${portChipsHtml}
      <div class="ct-body">
        <div class="ct-svg-pane">
          <div class="ct-svg-wrap" id="ctSvgMount">${svgStr}</div>
        </div>
        <div class="ct-side-pane">
          <h4 class="ct-side-title">${t("Related Paths", "Jalur Terkait")}</h4>
          <table class="ct-table">
            <thead>
              <tr>
                <th>${t("Origin", "Asal")}</th>
                <th>${t("Destination", "Tujuan")}</th>
                <th>${t("Segments", "Segmen")}</th>
              </tr>
            </thead>
            <tbody>${relatedRows}</tbody>
          </table>
        </div>
      </div>
    `;

    root.querySelector("#ctBtnClose")?.addEventListener("click", close);
    root.querySelector("#ctBtnDownloadSvg")?.addEventListener("click", () => {
      const blob = new Blob([svgStr], { type: "image/svg+xml;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const safeName = (data.origin.name || "device").replace(/[^a-zA-Z0-9_-]+/g, "_");
      a.href = url;
      a.download = `cable-trace-${safeName}${activePort ? "-" + activePort.replace(/[^a-zA-Z0-9_-]+/g, "_") : ""}.svg`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    root.querySelectorAll("[data-ct-port]").forEach((btn) => {
      btn.addEventListener("click", () => open(deviceId, btn.dataset.ctPort || null, opts));
    });
    root.querySelectorAll("[data-ct-row-port]").forEach((tr) => {
      tr.addEventListener("click", () => open(deviceId, tr.dataset.ctRowPort || null, opts));
    });
  }

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && document.getElementById("monitsCableTraceOverlay")) {
      close();
    }
  });

  window.RackCableTraceUI = { open, close, buildTraceSvg };
})();
