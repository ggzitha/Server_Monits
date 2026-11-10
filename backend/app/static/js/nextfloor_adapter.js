// Server_Monits NextFloor Adapter - 100% Offline, Zero External Calls, Strict EN/ID
import {
  getFacilityData,
  DEMO_PACK,
  DEMO_ENTITIES,
  DEMO_STATES,
  DEMO_PICTURES
} from "/static/nextfloor/demo-data.js";

// =========================================================================
// 1. OUTBOUND NETWORK FIREWALL: ZERO EXTERNAL CALLS / 100% AIR-GAPPED
// =========================================================================
if (typeof window !== "undefined" && !window.__monits_firewall_installed) {
  window.__monits_firewall_installed = true;
  const originalFetch = window.fetch;
  window.fetch = function(input, init) {
    const url = typeof input === "string" ? input : (input && input.url ? input.url : "");
    if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("//")) {
      const isLocal = url.startsWith(window.location.origin) ||
                      url.startsWith("http://127.0.0.1") ||
                      url.startsWith("http://localhost");
      if (!isLocal) {
        // Block external calls (OpenStreetMap, GitHub plugin index, analytics, tracking)
        // Return harmless empty responses
        if (url.includes(".png") || url.includes(".jpg") || url.includes(".webp")) {
          // Transparent 1x1 image blob for blocked map tiles
          const transparentPng = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAA=";
          return originalFetch(transparentPng);
        }
        return Promise.resolve(new Response(JSON.stringify({ plugins: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }));
      }
    }
    return originalFetch.apply(this, arguments);
  };
  // Silently neutralize any telemetry beacon calls
  if (typeof navigator !== "undefined" && navigator.sendBeacon) {
    const origBeacon = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = function(url, data) {
      if (typeof url === "string" && !url.startsWith(window.location.origin) && !url.startsWith("/") && !url.startsWith("http://127.0.0.1") && !url.startsWith("http://localhost")) {
        return true;
      }
      return origBeacon(url, data);
    };
  }
}

function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta && meta.content) return meta.content;
  const match = document.cookie.match(/csrf_token=([^;]+)/);
  return match ? match[1] : '';
}

// =========================================================================
// 2. ADAPTER INITIALIZER
// =========================================================================
export async function createNextFloorHass(options = {}) {
  const listeners = new Set();
  
  // Strict language enforcement: Only English and Indonesian
  let activeLang = (options.lang || document.documentElement.lang || "en").toLowerCase();
  if (activeLang !== "id" && activeLang !== "en") {
    activeLang = activeLang.startsWith("id") ? "id" : "en";
  }

  // Preload translation tables directly into NextFloor runtime to eliminate any German fallback
  try {
    const [enRes, idRes] = await Promise.all([
      fetch("/static/nextfloor/lang/en.json"),
      fetch("/static/nextfloor/lang/id.json")
    ]);
    const enTexts = enRes.ok ? await enRes.json() : {};
    const idTexts = idRes.ok ? await idRes.json() : {};

    window.__nextfloorTexts = window.__nextfloorTexts || new Map();
    window.__nextfloorTexts.set("en", enTexts);
    window.__nextfloorTexts.set("id", idTexts);

    // Replace internal German builtin with English so German never leaks
    window.__nextfloorBuiltin = {
      de: enTexts,
      en: enTexts
    };
  } catch (e) {
    console.warn("Language pre-seed deferred:", e);
  }

  const facility = getFacilityData(activeLang);
  let building = structuredClone(facility.building);
  let revision = 1;
  const images = { ...DEMO_PICTURES };
  let mainEntry = {
    id: "main",
    name: activeLang === "id" ? "Fasilitas Server Utama" : "Main Server Facility",
    icon: "server",
    site: activeLang === "id" ? "Pusat Data Alpha" : "Datacenter Alpha",
    created: Date.now() / 1000
  };

  // Try to load initial plan from Server_Monits API
  try {
    const res = await fetch("/api/v1/plans");
    if (res.ok) {
      const dbPlans = await res.json();
      if (dbPlans && dbPlans.length > 0) {
        const first = dbPlans[0];
        const detailRes = await fetch(`/api/v1/plans/${first.id}`);
        if (detailRes.ok) {
          const detail = await detailRes.json();
          if (detail.metadata_json && detail.metadata_json.floors) {
            building = detail.metadata_json;
            mainEntry.id = detail.id;
            mainEntry.name = detail.name;
          }
        }
      }
    }
  } catch (err) {
    console.warn("Could not fetch floor plans from API, using default model:", err);
  }

  const history = [{ id: "s0", revision: 0, saved_at: Date.now() / 1000 - 3600, building: structuredClone(building) }];

  const hass = {
    language: activeLang,
    user: {
      is_admin: true, // Always allow authenticated operators to access CAD editor & tools
      name: options.username || "Admin"
    },
    themes: { darkMode: true },
    config: { latitude: 0, longitude: 0 },
    areas: facility.areas,
    floors: facility.floors,
    entities: DEMO_ENTITIES,
    devices: {},
    states: structuredClone(DEMO_STATES),
    connection: {
      async subscribeMessage(cb) {
        listeners.add(cb);
        return async () => listeners.delete(cb);
      }
    },
    async callApi(method, path) {
      return [];
    },
    async fetchWithAuth(path, init = {}) {
      return new Response(null, { status: 404 });
    },
    async callService(domain, service, data) {
      for (const id of [].concat(data?.entity_id ?? [])) {
        const st = hass.states[id];
        if (!st) continue;
        const next = { ...st, attributes: { ...st.attributes } };
        if (service === "toggle") next.state = st.state === "on" ? "off" : "on";
        else if (service === "turn_on") next.state = "on";
        else if (service === "turn_off") next.state = "off";
        hass.states[id] = next;
      }
      if (window.nfPanel) window.nfPanel.requestUpdate();
    },
    async callWS(msg) {
      const type = msg.type || "";

      // 1. Building Persistence
      if (type === "nextfloor/building/get" || type === "neonplan3d/building/get") {
        return { building: structuredClone(building), revision };
      }

      if (type === "nextfloor/building/save" || type === "neonplan3d/building/save") {
        building = structuredClone(msg.building);
        revision += 1;
        for (const cb of listeners) cb({ revision });

        // Asynchronously persist to backend database
        try {
          await fetch("/api/v1/plans", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({
              name: mainEntry.name || "Main Server Facility",
              site_name: mainEntry.site || "Datacenter Alpha",
              metadata_json: building
            })
          });
        } catch (e) {
          console.warn("Async save to API skipped/failed:", e);
        }

        return { revision };
      }

      // 2. History & Snapshots
      if (type === "nextfloor/history/list" || type === "neonplan3d/history/list") {
        return {
          snapshots: history
            .map(({ building: b, ...rest }) => ({
              ...rest,
              floors: b?.floors?.length ?? 0,
              rooms: b?.floors?.reduce((n, f) => n + (f.rooms?.length ?? 0), 0) ?? 0,
              furniture: b?.floors?.reduce((n, f) => n + (f.furniture?.length ?? 0), 0) ?? 0
            }))
            .reverse()
        };
      }

      if (type === "nextfloor/history/snapshot" || type === "neonplan3d/history/snapshot") {
        const id = `s${history.length + 1}`;
        history.push({ id, revision, saved_at: Date.now() / 1000, building: structuredClone(building), ...(msg.name ? { name: msg.name } : {}) });
        return { id };
      }

      if (type === "nextfloor/history/get") {
        const snap = history.find((h) => h.id === msg.snapshot_id);
        if (!snap) throw { code: "not_found", message: "Restore point not found" };
        return { building: structuredClone(snap.building) };
      }

      if (type === "nextfloor/history/restore" || type === "neonplan3d/history/restore") {
        const snap = history.find((h) => h.id === msg.snapshot_id);
        if (snap) {
          building = structuredClone(snap.building);
          revision += 1;
          for (const cb of listeners) cb({ revision });
        }
        return { revision };
      }

      if (type === "nextfloor/history/delete") {
        const idx = history.findIndex((h) => h.id === msg.snapshot_id);
        if (idx >= 0) history.splice(idx, 1);
        return null;
      }

      // 3. Pro Equipment Packs
      if (type === "nextfloor/packs/list" || type === "neonplan3d/packs/list") {
        return {
          packs: [
            DEMO_PACK,
            {
              format: "fp3dpack",
              version: 1,
              id: "pro.dcim",
              name: activeLang === "id" ? "Infrastruktur Pusat Data (Pro)" : "Data Center Infrastructure (Pro)",
              publisher: "Server_Monits",
              licensee: "Enterprise",
              features: [
                "camera_cockpit",
                "weather",
                "screens",
                "energy_pro",
                "sound",
                "auto_pro",
                "time_travel",
                "floor_stack",
                "heatmaps"
              ],
              items: []
            }
          ]
        };
      }

      // 4. Image Store
      if (type === "nextfloor/image/get" || type === "neonplan3d/image/get") {
        if (!images[msg.image_id]) throw { code: "not_found", message: "Image not found" };
        return { data: images[msg.image_id] };
      }

      if (type === "nextfloor/image/set" || type === "neonplan3d/image/set") {
        images[msg.image_id] = msg.data;
        return null;
      }

      // 5. Weather Forecasts (offline local simulation)
      if (type === "call_service" && msg.domain === "weather" && msg.service === "get_forecasts") {
        const id = msg.target?.entity_id || "weather.datacenter";
        const kinds = ["sunny", "partlycloudy", "rainy", "cloudy"];
        const forecast = kinds.map((condition, i) => ({
          datetime: new Date(Date.now() + i * 86400000).toISOString(),
          condition,
          temperature: 22 - i,
          templow: 18 - i,
          precipitation: condition === "rainy" ? 5.0 : 0
        }));
        return { response: { [id]: { forecast } } };
      }

      // 6. License checks (Unlocks all Pro capabilities)
      if (type.includes("license")) {
        return {
          active: true,
          instance: "server_monits_enterprise",
          licensee: "Server_Monits Enterprise Pro",
          checked_at: Date.now() / 1000,
          error: null,
          supporter: { code: "SM-PRO", until: "2099-12-31" }
        };
      }

      // 7. BLE Devices & Scanners (safe defaults to prevent length error)
      if (type === "nextfloor/ble/devices") {
        return { available: false, scanners: [], devices: [] };
      }

      if (type === "nextfloor/ble/scan") {
        return { readings: {} };
      }

      // 8. Energy & Statistics
      if (type === "energy/get_prefs") {
        return { energy_sources: [] };
      }

      if (type === "recorder/statistics_during_period" || type === "history/history_during_period") {
        return {};
      }

      if (type.startsWith("nextfloor/") && type.endsWith("/subscribe")) {
        return { id: msg.id || 1, type: "result", success: true };
      }

      return {};
    }
  };

  // Connect WebSocket to /ws/live for realtime push telemetry
  try {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/live`;
    const ws = new WebSocket(wsUrl);

    ws.onerror = () => {
      // Graceful offline fallback
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "telemetry" && data.sensor_id) {
          const entityId = `sensor.${data.sensor_id}`;
          hass.states[entityId] = {
            entity_id: entityId,
            state: String(data.value),
            attributes: {
              unit_of_measurement: data.unit || "",
              friendly_name: data.sensor_name || data.sensor_id,
              status: data.status || "online"
            }
          };
          if (window.nfPanel) window.nfPanel.requestUpdate();
        }
      } catch (e) {
        // Ignore non-json frames
      }
    };
  } catch (err) {
    console.warn("WebSocket live link optional/deferred:", err);
  }

  return hass;
}
