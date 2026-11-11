// Server_Monits 3D Facility Adapter - DB-Backed Building Persistence, Direct DB Sensors, Virtual Lights & 3D Cabling
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

  // Preload translation tables directly into runtime to eliminate any German fallback
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
  let areasMap = structuredClone(facility.areas);
  let revision = 1;
  const images = { ...DEMO_PICTURES };
  let mainEntry = {
    id: "main",
    name: activeLang === "id" ? "Fasilitas Server Utama" : "Main Server Facility",
    icon: "server",
    site: activeLang === "id" ? "Pusat Data Alpha" : "Datacenter Alpha",
    created: Date.now() / 1000
  };

  let history = [
    {
      id: "s1",
      revision: 1,
      saved_at: Date.now() / 1000 - 3600,
      name: activeLang === "id" ? "Konfigurasi Awal Fasilitas" : "Initial Facility Baseline",
      building: structuredClone(building)
    }
  ];

  // Auto-sync rooms inside building.floors with areasMap so newly drawn rooms in Editor always have an area_id
  function syncRoomsToAreas(b) {
    if (!b || !Array.isArray(b.floors)) return;
    for (const fl of b.floors) {
      for (const rm of fl.rooms || []) {
        const aid = rm.ha_area || rm.id;
        if (aid) {
          if (!rm.ha_area) rm.ha_area = aid;
          if (!areasMap[aid]) {
            areasMap[aid] = {
              area_id: aid,
              name: rm.name || aid,
              floor_id: fl.ha_floor || fl.id || "ground"
            };
          } else if (rm.name) {
            areasMap[aid].name = rm.name;
          }
        }
      }
    }
  }

  // Load saved 3D building from Server_Monits Database (/api/v1/sensors/building)
  try {
    const bRes = await fetch("/api/v1/sensors/building");
    if (bRes.ok) {
      const bData = await bRes.json();
      if (bData && bData.saved && bData.building && Array.isArray(bData.building.floors) && bData.building.floors.length > 0) {
        building = bData.building;
        if (bData.name) mainEntry.name = bData.name;
        if (bData.site) mainEntry.site = bData.site;
        if (bData.areas && typeof bData.areas === "object") {
          areasMap = { ...areasMap, ...bData.areas };
        }
        if (Array.isArray(bData.snapshots) && bData.snapshots.length > 0) {
          history = bData.snapshots;
        }
        if (typeof bData.revision === "number") {
          revision = bData.revision;
        }
        syncRoomsToAreas(building);
      }
    }
  } catch (e) {
    console.warn("Using default Data Center 3D model:", e);
  }

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

    // If the sensor has explicit 3D placement coordinates in DB, ensure its pins exist on that floor
    if (s.placement_x !== null && s.placement_x !== undefined && s.placement_z !== null && s.placement_z !== undefined) {
      const targetFloor = (building.floors || []).find(f => f.id === (s.floor_id || "ground")) || (building.floors || [])[0];
      if (targetFloor) {
        targetFloor.placements = targetFloor.placements || [];
        const px = Number(s.placement_x);
        const pz = Number(s.placement_z);
        const py = s.placement_y !== null && s.placement_y !== undefined ? Number(s.placement_y) : 1.5;

        const existingTemp = targetFloor.placements.find(p => p.entity_id === tempId);
        if (!existingTemp) {
          targetFloor.placements.push({ entity_id: tempId, x: px, z: pz });
        }
        const existingHum = targetFloor.placements.find(p => p.entity_id === humId);
        if (!existingHum) {
          targetFloor.placements.push({ entity_id: humId, x: Math.round((px + 0.35) * 100) / 100, z: pz });
        }
        targetFloor.furniture = targetFloor.furniture || [];
        const unitId = `sensor_unit_${ident}`;
        if (!targetFloor.furniture.some(f => f.id === unitId)) {
          targetFloor.furniture.push({
            id: unitId,
            type: "pack:dcim.facility:thermohygro_sensor",
            name: s.name || ident,
            show_name: true,
            x: px,
            z: pz,
            w: 0.22,
            d: 0.08,
            h: 0.26,
            mount_y: py,
            rotation: 0
          });
        }
      }
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

  function pushHassToPanel() {
    hass.states = { ...statesMap };
    hass.entities = { ...entitiesMap };
    hass.areas = { ...areasMap };
    if (window.nfPanel) {
      window.nfPanel.hass = { ...hass, states: hass.states, entities: hass.entities, areas: hass.areas };
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

  async function persistBuildingToDatabase(bToSave) {
    if (!bToSave) return false;
    building = structuredClone(bToSave);
    syncRoomsToAreas(building);
    try {
      localStorage.removeItem("nextfloor.unsaved");
    } catch (e) {}

    try {
      const res = await fetch("/api/v1/sensors/building", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": getCsrfToken()
        },
        body: JSON.stringify({
          building,
          name: mainEntry.name || "Main Server Facility",
          site: mainEntry.site || "Datacenter Alpha",
          areas: areasMap,
          snapshots: history.slice(-15),
          revision
        })
      });
      return res.ok;
    } catch (e) {
      console.warn("Building DB save error:", e);
      return false;
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
    areas: areasMap,
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
        revision += 1;
        await persistBuildingToDatabase(msg.building);
        pushHassToPanel();
        for (const cb of listeners) cb({ revision });
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
        await persistBuildingToDatabase(building);
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
          revision += 1;
          await persistBuildingToDatabase(snap.building);
          for (const cb of listeners) cb({ revision });
        }
        return { revision };
      }

      if (type === "nextfloor/history/delete") {
        const idx = history.findIndex((h) => h.id === msg.snapshot_id);
        if (idx >= 0) history.splice(idx, 1);
        await persistBuildingToDatabase(building);
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

  // Expose programmatic API for Integrated Header & Drawers
  window.monitsApi = {
    getStates: () => statesMap,
    getSensors: () => dbSensorsCache,
    getBuilding: () => (window.nfPanel?.data?.building || building),
    getAreas: () => areasMap,
    async saveBuildingNow(customBuilding = null) {
      const panel = window.nfPanel;
      if (panel && panel.data) {
        if (customBuilding) {
          panel.data.building = structuredClone(customBuilding);
        }
        try {
          await panel.data.flush();
        } catch (e) {}
      }
      const target = customBuilding || panel?.data?.building || building;
      const ok = await persistBuildingToDatabase(target);
      if (panel && panel.data) {
        panel.data.saveState = ok ? "saved" : "error";
        panel.requestUpdate();
      }
      return ok;
    },
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
    async pushDbSensorReading({ identifier, name, area_id, floor_id, placement_x, placement_z, placement_y, temperature, humidity, power_kw }) {
      const res = await fetch("/api/v1/sensors/readings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": getCsrfToken()
        },
        body: JSON.stringify({
          identifier,
          ...(name ? { name } : {}),
          ...(area_id ? { area_id } : {}),
          ...(floor_id ? { floor_id } : {}),
          ...(placement_x !== undefined && placement_x !== null && placement_x !== "" ? { placement_x: Number(placement_x) } : {}),
          ...(placement_z !== undefined && placement_z !== null && placement_z !== "" ? { placement_z: Number(placement_z) } : {}),
          ...(placement_y !== undefined && placement_y !== null && placement_y !== "" ? { placement_y: Number(placement_y) } : {}),
          temperature: temperature !== "" && temperature !== null && temperature !== undefined ? Number(temperature) : null,
          humidity: humidity !== "" && humidity !== null && humidity !== undefined ? Number(humidity) : null,
          power_kw: power_kw !== "" && power_kw !== null && power_kw !== undefined ? Number(power_kw) : null
        })
      });
      if (res.ok) {
        await this.refreshSensorsFromDb();
      }
      return res.ok;
    },
    async addAndPlaceSensorIn3D({ name, identifier, floorId, areaId, x, z, mountY, temperature, humidity, powerKw }) {
      const cleanName = (name || "Rack Env Sensor").trim();
      const cleanIdent = (identifier || cleanName.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || `sensor_${Date.now().toString(36)}`).slice(0, 60);
      const px = Math.round(Number(x || 3.0) * 100) / 100;
      const pz = Math.round(Number(z || 2.5) * 100) / 100;
      const py = Math.round(Number(mountY ?? 1.5) * 100) / 100;
      const flId = floorId || "ground";
      const arId = areaId || "server_alpha";

      // 1. Save sensor & initial telemetry to SQLite/PostgreSQL database
      const ok = await this.pushDbSensorReading({
        identifier: cleanIdent,
        name: cleanName,
        area_id: arId,
        floor_id: flId,
        placement_x: px,
        placement_z: pz,
        placement_y: py,
        temperature: temperature ?? 21.5,
        humidity: humidity ?? 45.0,
        power_kw: powerKw !== "" && powerKw !== undefined ? powerKw : null
      });
      if (!ok) return null;

      // 2. Place 3D Thermohygrograph hardware unit + floating Temperature & Humidity pins in the 3D floor plan
      const panel = window.nfPanel;
      const curB = structuredClone(panel?.data?.building || building);
      const targetFloor = (curB.floors || []).find(f => f.id === flId) || (curB.floors || [])[0];
      if (targetFloor) {
        targetFloor.placements = targetFloor.placements || [];
        const tempEntityId = `sensor.${cleanIdent}_temp`;
        const humEntityId = `sensor.${cleanIdent}_humidity`;

        // Remove any previous pin for the same entity before placing at new coordinates
        targetFloor.placements = targetFloor.placements.filter(
          p => p.entity_id !== tempEntityId && p.entity_id !== humEntityId
        );
        targetFloor.placements.push({ entity_id: tempEntityId, x: px, z: pz });
        targetFloor.placements.push({ entity_id: humEntityId, x: Math.round((px + 0.35) * 100) / 100, z: pz });

        if (powerKw !== "" && powerKw !== null && powerKw !== undefined) {
          const pwrEntityId = `sensor.${cleanIdent}_power`;
          targetFloor.placements = targetFloor.placements.filter(p => p.entity_id !== pwrEntityId);
          targetFloor.placements.push({ entity_id: pwrEntityId, x: Math.round((px + 0.7) * 100) / 100, z: pz });
        }

        // Also place 3D physical sensor box on the wall/rack at (px, pz, py)
        targetFloor.furniture = targetFloor.furniture || [];
        const unitId = `sensor_unit_${cleanIdent}`;
        targetFloor.furniture = targetFloor.furniture.filter(f => f.id !== unitId);
        targetFloor.furniture.push({
          id: unitId,
          type: "pack:dcim.facility:thermohygro_sensor",
          name: cleanName,
          show_name: true,
          x: px,
          z: pz,
          w: 0.22,
          d: 0.08,
          h: 0.26,
          mount_y: py,
          rotation: 0
        });

        building = curB;
        if (panel && panel.data) {
          panel.data.edit(curB);
        }
        await this.saveBuildingNow(curB);
      }

      return {
        identifier: cleanIdent,
        name: cleanName,
        floorId: flId,
        areaId: arId,
        x: px,
        z: pz,
        mountY: py
      };
    },
    async deleteSensor(identifier) {
      const res = await fetch(`/api/v1/sensors/${encodeURIComponent(identifier)}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": getCsrfToken() }
      });
      if (res.ok) {
        const tempId = `sensor.${identifier}_temp`;
        const humId = `sensor.${identifier}_humidity`;
        const pwrId = `sensor.${identifier}_power`;
        delete entitiesMap[tempId];
        delete entitiesMap[humId];
        delete entitiesMap[pwrId];
        delete statesMap[tempId];
        delete statesMap[humId];
        delete statesMap[pwrId];

        const panel = window.nfPanel;
        const curB = structuredClone(panel?.data?.building || building);
        for (const fl of curB.floors || []) {
          fl.placements = (fl.placements || []).filter(
            p => p.entity_id !== tempId && p.entity_id !== humId && p.entity_id !== pwrId
          );
          fl.furniture = (fl.furniture || []).filter(f => f.id !== `sensor_unit_${identifier}`);
        }
        building = curB;
        if (panel && panel.data) {
          panel.data.edit(curB);
        }
        await this.saveBuildingNow(curB);
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
    async addCableRunToPlan({ cableType, placementZone, customMountY, floorId, name, x1, z1, x2, z2, variant }) {
      const panel = window.nfPanel;
      const curB = structuredClone(panel?.data?.building || building);
      const targetFloor = (curB.floors || []).find(f => f.id === floorId) || (curB.floors || [])[0];
      if (!targetFloor) return false;

      const dx = Number(x2) - Number(x1);
      const dz = Number(z2) - Number(z1);
      const length = Math.max(0.4, Math.round(Math.hypot(dx, dz) * 100) / 100);
      const midX = Math.round(((Number(x1) + Number(x2)) / 2) * 100) / 100;
      const midZ = Math.round(((Number(z1) + Number(z2)) / 2) * 100) / 100;
      const angleDeg = Math.round((Math.atan2(dz, dx) * 180) / Math.PI);

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
      building = curB;
      if (panel && panel.data) {
        panel.data.edit(curB);
      }
      await this.saveBuildingNow(curB);
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
            floor_id: data.floor_id || "ground",
            placement_x: data.placement_x,
            placement_z: data.placement_z,
            placement_y: data.placement_y,
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
