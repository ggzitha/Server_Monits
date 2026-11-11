// Server_Monits NextFloor Adapter - 100% Detached from Home Assistant, DB-Backed Sensors, Virtual Lights & 3D Cabling
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
        if (url.includes(".png") || url.includes(".jpg") || url.includes(".webp")) {
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

export function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta && meta.content) return meta.content;
  const match = document.cookie.match(/csrf_token=([^;]+)/);
  return match ? match[1] : "";
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
  let currentPlanId = null;
  const images = { ...DEMO_PICTURES };
  let mainEntry = {
    id: "main",
    name: activeLang === "id" ? "Fasilitas Server Utama" : "Main Server Facility",
    icon: "server",
    site: activeLang === "id" ? "Pusat Data Alpha" : "Datacenter Alpha",
    created: Date.now() / 1000
  };

  // Load saved floor plan from Server_Monits DB if available (and if it has rooms & furniture)
  try {
    const res = await fetch("/api/v1/plans");
    if (res.ok) {
      const dbPlans = await res.json();
      if (dbPlans && dbPlans.length > 0) {
        const first = dbPlans[0];
        currentPlanId = first.id;
        const detailRes = await fetch(`/api/v1/plans/${first.id}`);
        if (detailRes.ok) {
          const detail = await detailRes.json();
          if (detail.metadata_json && detail.metadata_json.floors && detail.metadata_json.floors.some(f => f.rooms && f.rooms.length > 0)) {
            building = detail.metadata_json;
            mainEntry.name = detail.name || mainEntry.name;
          }
        }
      }
    }
  } catch (e) {
    console.warn("Using default Data Center 3D model:", e);
  }

  const history = [
    {
      id: "s1",
      revision: 1,
      saved_at: Date.now() / 1000 - 3600,
      name: activeLang === "id" ? "Konfigurasi Awal Fasilitas" : "Initial Facility Baseline",
      building: structuredClone(building)
    }
  ];

  let entitiesMap = { ...DEMO_ENTITIES };
  let statesMap = structuredClone(DEMO_STATES);

  // Sync live sensors directly from the SQLite/PostgreSQL database (/api/v1/sensors)
  function applyDbSensorToState(s) {
    const ident = s.identifier;
    const areaId = s.area_id || "server_alpha";
    const tempId = `sensor.${ident}_temp`;
    const humId = `sensor.${ident}_humidity`;
    const pwrId = `sensor.${ident}_power`;

    if (s.current_temperature !== null && s.current_temperature !== undefined) {
      entitiesMap[tempId] = { entity_id: tempId, name: `${s.name} Temp`, area_id: areaId };
      statesMap[tempId] = {
        entity_id: tempId,
        state: String(s.current_temperature),
        attributes: {
          device_class: "temperature",
          unit_of_measurement: "°C",
          friendly_name: `${s.name} Temp`,
          status: s.status || "online",
          db_identifier: ident
        }
      };
    }

    if (s.current_humidity !== null && s.current_humidity !== undefined) {
      entitiesMap[humId] = { entity_id: humId, name: `${s.name} Humidity`, area_id: areaId };
      statesMap[humId] = {
        entity_id: humId,
        state: String(s.current_humidity),
        attributes: {
          device_class: "humidity",
          unit_of_measurement: "%",
          friendly_name: `${s.name} Humidity`,
          status: s.status || "online",
          db_identifier: ident
        }
      };
    }

    if (s.power_kw !== null && s.power_kw !== undefined) {
      entitiesMap[pwrId] = { entity_id: pwrId, name: `${s.name} Power`, area_id: areaId };
      statesMap[pwrId] = {
        entity_id: pwrId,
        state: String(s.power_kw),
        attributes: {
          device_class: "power",
          unit_of_measurement: "kW",
          friendly_name: `${s.name} Load`,
          status: s.status || "online",
          db_identifier: ident
        }
      };
    }
  }

  let dbSensorsCache = [];
  try {
    const sRes = await fetch("/api/v1/sensors");
    if (sRes.ok) {
      dbSensorsCache = await sRes.json();
      for (const s of dbSensorsCache) {
        applyDbSensorToState(s);
      }
    }
  } catch (e) {
    console.warn("Initial DB sensor fetch deferred:", e);
  }

  // Load persisted virtual device states (lights, switches, locks, cable layers) from DB
  try {
    const vRes = await fetch("/api/v1/sensors/virtual/states");
    if (vRes.ok) {
      const vData = await vRes.json();
      const savedStates = vData.states || {};
      for (const [entityId, entry] of Object.entries(savedStates)) {
        const prev = statesMap[entityId] || { entity_id: entityId, state: "off", attributes: {} };
        statesMap[entityId] = {
          ...prev,
          state: entry.state,
          attributes: { ...prev.attributes, ...(entry.attributes || {}) }
        };
      }
    }
  } catch (e) {
    console.warn("Virtual states fetch deferred:", e);
  }

  // Push fresh hass reference into <nextfloor-panel> so LitElement detects `changed.has("hass")`
  function pushHassToPanel() {
    hass.states = { ...statesMap };
    hass.entities = { ...entitiesMap };
    if (window.nfPanel) {
      window.nfPanel.hass = { ...hass, states: hass.states, entities: hass.entities };
      window.nfPanel.requestUpdate();
    }
    window.dispatchEvent(new CustomEvent("monits-state-changed", { detail: { states: hass.states, sensors: dbSensorsCache } }));
  }

  async function persistVirtualState(entityId, stateObj) {
    try {
      await fetch("/api/v1/sensors/virtual/states", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": getCsrfToken()
        },
        body: JSON.stringify({
          entity_id: entityId,
          state: stateObj.state,
          attributes: stateObj.attributes || {}
        })
      });
    } catch (e) {
      // non-blocking
    }
  }

  const hass = {
    language: activeLang,
    selectedTheme: { dark: true },
    themes: { darkMode: true },
    config: {
      latitude: -6.2,
      longitude: 106.8,
      time_zone: "Asia/Jakarta",
      unit_system: { temperature: "°C" }
    },
    user: {
      is_admin: true,
      name: options.username || "Admin"
    },
    floors: facility.floors,
    areas: facility.areas,
    devices: {},
    entities: entitiesMap,
    states: statesMap,
    connection: {
      async subscribeMessage(cb, msg) {
        if (msg && (msg.type === "nextfloor/building/subscribe" || msg.type === "neonplan3d/building/subscribe")) {
          listeners.add(cb);
          return async () => {
            listeners.delete(cb);
          };
        }
        return async () => {};
      }
    },
    // Virtual Device Engine (100% Detached from Home Assistant)
    async callService(domain, service, data = {}, target = {}) {
      const rawIds = data.entity_id ?? target.entity_id ?? [];
      const ids = Array.isArray(rawIds) ? rawIds : [rawIds];

      for (const id of ids) {
        const cur = statesMap[id] || { entity_id: id, state: "off", attributes: { friendly_name: id } };
        const next = { ...cur, attributes: { ...cur.attributes } };

        if (service === "toggle") {
          if (domain === "lock") {
            next.state = cur.state === "locked" ? "unlocked" : "locked";
          } else {
            next.state = cur.state === "on" ? "off" : "on";
          }
        } else if (service === "turn_on") {
          next.state = "on";
          if (typeof data.brightness === "number") next.attributes.brightness = data.brightness;
          if (typeof data.brightness_pct === "number") next.attributes.brightness = Math.round((data.brightness_pct / 100) * 255);
          if (Array.isArray(data.rgb_color)) next.attributes.rgb_color = data.rgb_color;
          if (typeof data.color_temp_kelvin === "number") {
            next.attributes.color_temp_kelvin = data.color_temp_kelvin;
          }
        } else if (service === "turn_off") {
          next.state = "off";
        } else if (service === "lock") {
          next.state = "locked";
        } else if (service === "unlock") {
          next.state = "unlocked";
        } else if (service === "open_cover") {
          next.state = "open";
          next.attributes.current_position = 100;
        } else if (service === "close_cover") {
          next.state = "closed";
          next.attributes.current_position = 0;
        } else if (service === "set_temperature" && typeof data.temperature === "number") {
          next.attributes.temperature = data.temperature;
        }

        statesMap[id] = next;
        void persistVirtualState(id, next);
      }

      pushHassToPanel();
    },
    async callWS(msg) {
      const type = msg.type || "";

      // 1. Building Persistence
      if (type === "nextfloor/building/get" || type === "neonplan3d/building/get") {
        return {
          building: structuredClone(building),
          revision,
          buildings: [mainEntry],
          current: "main"
        };
      }

      if (type === "nextfloor/building/save" || type === "neonplan3d/building/save") {
        building = structuredClone(msg.building);
        revision += 1;
        for (const cb of listeners) cb({ revision });

        try {
          if (currentPlanId) {
            await fetch(`/api/v1/plans/${currentPlanId}`, {
              method: "PUT",
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
          } else {
            const createRes = await fetch("/api/v1/plans", {
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
            if (createRes.ok) {
              const created = await createRes.json();
              currentPlanId = created.id;
            }
          }
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

      // 3. Pro Equipment & Cabling Packs
      if (type === "nextfloor/packs/list" || type === "neonplan3d/packs/list") {
        return {
          packs: [DEMO_PACK]
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

      // 7. BLE Devices & Scanners
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

  // Expose programmatic API for our Integrated Header Drawers (Virtual Lights, DB Sensors, 3D Cable Routing)
  window.monitsApi = {
    getStates: () => statesMap,
    getSensors: () => dbSensorsCache,
    getBuilding: () => building,
    async refreshSensorsFromDb() {
      const res = await fetch("/api/v1/sensors");
      if (res.ok) {
        dbSensorsCache = await res.json();
        for (const s of dbSensorsCache) {
          applyDbSensorToState(s);
        }
        pushHassToPanel();
      }
      return dbSensorsCache;
    },
    async pushDbSensorReading({ identifier, area_id, temperature, humidity, power_kw }) {
      const res = await fetch("/api/v1/sensors/readings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": getCsrfToken()
        },
        body: JSON.stringify({
          identifier,
          area_id,
          temperature: temperature !== "" && temperature !== null ? Number(temperature) : null,
          humidity: humidity !== "" && humidity !== null ? Number(humidity) : null,
          power_kw: power_kw !== "" && power_kw !== null ? Number(power_kw) : null
        })
      });
      if (res.ok) {
        await this.refreshSensorsFromDb();
      }
      return res.ok;
    },
    async setVirtualLight(entityId, { state, brightness, hexColor }) {
      const rgb = hexColor
        ? [
            parseInt(hexColor.slice(1, 3), 16),
            parseInt(hexColor.slice(3, 5), 16),
            parseInt(hexColor.slice(5, 7), 16)
          ]
        : undefined;
      if (state === "off") {
        await hass.callService("light", "turn_off", { entity_id: entityId });
      } else {
        await hass.callService("light", "turn_on", {
          entity_id: entityId,
          ...(typeof brightness === "number" ? { brightness } : {}),
          ...(rgb ? { rgb_color: rgb } : {})
        });
      }
    },
    async toggleLayer(layerEntityId) {
      await hass.callService("input_boolean", "toggle", { entity_id: layerEntityId });
    },
    addCableRunToPlan({ cableType, placementZone, customMountY, floorId, name, x1, z1, x2, z2, variant }) {
      const panel = window.nfPanel;
      if (!panel || !panel.data || !panel.data.building) return false;
      const b = structuredClone(panel.data.building);
      const targetFloor = b.floors.find(f => f.id === floorId) || b.floors[0];
      if (!targetFloor) return false;

      const dx = Number(x2) - Number(x1);
      const dz = Number(z2) - Number(z1);
      const length = Math.max(0.4, Math.round(Math.hypot(dx, dz) * 100) / 100);
      const midX = Math.round(((Number(x1) + Number(x2)) / 2) * 100) / 100;
      const midZ = Math.round(((Number(z1) + Number(z2)) / 2) * 100) / 100;
      const angleDeg = Math.round((Math.atan2(dz, dx) * 180) / Math.PI);

      // Determine mount_y in meters based on placement zone (Below Floor, In Wall, Ceiling)
      let mountY = -0.22;
      if (placementZone === "below_floor") mountY = -0.22;
      else if (placementZone === "wall") mountY = 1.25;
      else if (placementZone === "ceiling") mountY = 2.88;
      else if (placementZone === "custom" && Number.isFinite(Number(customMountY))) {
        mountY = Number(customMountY);
      }

      const typeMap = {
        power: {
          type: "pack:dcim.facility:cable_power",
          layer: "input_boolean.layer_cable_power",
          d: 0.14,
          h: 0.06,
          defaultVariant: "red_hv"
        },
        fiber: {
          type: "pack:dcim.facility:cable_fiber",
          layer: "input_boolean.layer_cable_fiber",
          d: 0.12,
          h: 0.05,
          defaultVariant: "aqua_om4"
        },
        ethernet: {
          type: "pack:dcim.facility:cable_ethernet",
          layer: "input_boolean.layer_cable_ethernet",
          d: 0.10,
          h: 0.05,
          defaultVariant: "blue_cat6a"
        },
        tray: {
          type: "pack:dcim.facility:cable_tray",
          layer: "input_boolean.layer_cable_tray",
          d: 0.45,
          h: 0.08,
          defaultVariant: "galvanized"
        }
      };

      const spec = typeMap[cableType] || typeMap.power;
      const newCable = {
        id: `cable_${cableType}_${Date.now().toString(36)}`,
        type: spec.type,
        name: name || `${cableType.toUpperCase()} (${length}m @ ${mountY}m)`,
        show_name: true,
        x: midX,
        z: midZ,
        w: length,
        d: spec.d,
        h: spec.h,
        mount_y: mountY,
        rotation: angleDeg,
        variant: variant || spec.defaultVariant,
        show_when: { entity: spec.layer }
      };

      targetFloor.furniture = [...(targetFloor.furniture || []), newCable];
      building = b;
      panel.data.edit(b);
      return newCable;
    }
  };

  // Connect WebSocket to /ws/live for realtime push telemetry & virtual states
  try {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/live`;
    const ws = new WebSocket(wsUrl);

    ws.onerror = () => {};

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "telemetry") {
          const ident = data.identifier || data.sensor_id;
          applyDbSensorToState({
            identifier: ident,
            name: data.sensor_name || ident,
            area_id: data.area_id || "server_alpha",
            current_temperature: data.temperature,
            current_humidity: data.humidity,
            power_kw: data.power_kw,
            status: data.status || "online"
          });
          pushHassToPanel();
        } else if (data.type === "virtual_state" && data.entity_id) {
          const prev = statesMap[data.entity_id] || { entity_id: data.entity_id, state: "off", attributes: {} };
          statesMap[data.entity_id] = {
            ...prev,
            state: data.state,
            attributes: { ...prev.attributes, ...(data.attributes || {}) }
          };
          pushHassToPanel();
        }
      } catch (e) {
        // ignore malformed packets
      }
    };
  } catch (e) {
    // WebSocket optional fallback
  }

  return hass;
}
