// Server_Monits 3D Facility Adapter - DB-Backed Building Persistence, Direct DB Sensors, Gauges/24h Charts, Virtual Lights & 3D Cabling
import {
  getFacilityData,
  DEMO_PACK,
  DEMO_ENTITIES,
  DEMO_STATES,
  DEMO_PICTURES
} from "/static/neonplan3d/demo-data.js";

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
      fetch("/static/neonplan3d/lang/en.json"),
      fetch("/static/neonplan3d/lang/id.json")
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
  let sensorHistoryCache = {}; // identifier -> { readings: [...], tempSeries: [...], humSeries: [...] }
  let activeSensorIdentifier = "server_alpha_env";
  let expandedSensorIdentifier = null; // null = all cards show compact Gauges-only mode; identifier = that card shows full Gauges + Readings + 24h Chart below
  let wifiSurveyPointsCache = [];
  let wifiSsidsCache = [];
  let wifiApsCache = [];
  let wifiBandsCache = [];
  let wifiChannelsCache = [];
  let racksCache = [];
  let selectedWifiSsid = ""; // "" = All Wi-Fi APs
  let selectedWifiBand = ""; // "" | "2.4GHz" | "5GHz" | "6GHz"
  let selectedWifiChannel = null; // number | null
  let selectedObject = null; // { kind: "furniture"|"sensor"|"wifi_point"|"device", id, floorId }
  let activeTimeTravelState = null; // { t: ms, hass: hassObj } | null

  // Shared Object Registry (Task 6): single definition for all DCIM & monitoring extras
  const EXTRA_OBJECT_REGISTRY = {
    thermohygro_sensor: { category: "sensor", label: "Thermohygrometer", icon: "🌡", color: "#00f0ff", uHeight: null },
    rack_42u: { category: "rack", label: "42U Rack", icon: "🗄️", color: "#38bdf8", uHeight: 42 },
    rack_24u: { category: "rack", label: "24U Rack", icon: "🗄️", color: "#38bdf8", uHeight: 24 },
    wifi_ap: { category: "wifi", label: "Wi-Fi AP", icon: "📶", color: "#22c55e", uHeight: null },
    wifi_rssi_point: { category: "wifi", label: "RSSI Survey Point", icon: "📡", color: "#22c55e", uHeight: null },
    crac_unit: { category: "cooling", label: "CRAC Unit", icon: "❄️", color: "#38bdf8", uHeight: null },
    ups_cabinet: { category: "power", label: "UPS Cabinet", icon: "🔋", color: "#f59e0b", uHeight: null },
    fingerprint_reader: { category: "security", label: "Fingerprint Reader", icon: "🔐", color: "#22c55e", uHeight: null },
    pc_workstation: { category: "compute", label: "Workstation", icon: "🖥️", color: "#38bdf8", uHeight: null },
    ac_outdoor_unit: { category: "cooling", label: "AC Outdoor", icon: "🌀", color: "#38bdf8", uHeight: null },
    cable_power: { category: "cable", label: "Power Cable", icon: "⚡", color: "#ef4444", uHeight: null },
    cable_fiber: { category: "cable", label: "Fiber Optic", icon: "💎", color: "#00f0ff", uHeight: null },
    cable_ethernet: { category: "cable", label: "Ethernet LAN", icon: "🌐", color: "#3b82f6", uHeight: null },
    cable_tray: { category: "cable", label: "Cable Tray", icon: "🪜", color: "#94a3b8", uHeight: null }
  };

  function normalizeBandClient(band, channel = null) {
    const raw = String(band || "").trim().toLowerCase().replace(/\s+/g, "");
    if (["2.4", "2.4g", "2.4ghz", "2g"].includes(raw)) return "2.4GHz";
    if (["5", "5g", "5ghz"].includes(raw)) return "5GHz";
    if (["6", "6g", "6ghz"].includes(raw)) return "6GHz";
    if (["n/a", "na", "unknown"].includes(raw)) return "N/A";
    const ch = Number(channel);
    if (Number.isFinite(ch) && ch > 0) {
      if (ch <= 14) return "2.4GHz";
      if (ch <= 177) return "5GHz";
      return "6GHz";
    }
    return "5GHz";
  }

  async function loadWifiSurveyFromDb() {
    try {
      const res = await fetch("/api/v1/wifi-survey");
      if (res.ok) {
        const data = await res.json();
        wifiSurveyPointsCache = Array.isArray(data.points) ? data.points : [];
        wifiSsidsCache = Array.isArray(data.ssids) ? data.ssids : [];
        wifiApsCache = Array.isArray(data.aps) ? data.aps : [];
        wifiBandsCache = Array.isArray(data.bands) ? data.bands : [];
        wifiChannelsCache = Array.isArray(data.channels) ? data.channels : [];
      }
    } catch (e) {}
  }
  await loadWifiSurveyFromDb();

  function parseDbTimestampMs(ts) {
    if (ts === null || ts === undefined) return NaN;
    if (typeof ts === "number") return ts > 1e12 ? ts : ts * 1000;
    const raw = String(ts).trim();
    if (!raw) return NaN;
    if (/^\d+$/.test(raw)) {
      const n = Number(raw);
      return n > 1e12 ? n : n * 1000;
    }
    const iso = raw.replace(" ", "T");
    // MariaDB / SQLite datetime columns returned from UTC queries have no timezone suffix; treat as UTC ("Z")
    const withTz = /([zZ]|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
    return Date.parse(withTz);
  }

  function build24hSeriesForSensor(s, dbReadings = []) {
    const baseT = Number(s?.current_temperature ?? 21.5);
    const baseH = Number(s?.current_humidity ?? 45.0);
    const validT = dbReadings.map(r => r.temperature).filter(v => v !== null && v !== undefined && Number.isFinite(Number(v))).map(Number);
    const validH = dbReadings.map(r => r.humidity).filter(v => v !== null && v !== undefined && Number.isFinite(Number(v))).map(Number);

    // Build 24 points for the 24h chart from real DB readings when available
    const tempPts = [];
    const humPts = [];
    const chartPoints = [];
    const hasRealT = validT.length > 0;
    const hasRealH = validH.length > 0;
    const nowMs = Date.now();
    const fmtTime = (ms) => {
      const d = new Date(ms);
      return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    };
    const fmtFull = (ms) => {
      const d = new Date(ms);
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${fmtTime(ms)}:${String(d.getSeconds()).padStart(2, "0")}`;
    };

    for (let i = 0; i < 24; i++) {
      let tVal = baseT;
      let hVal = baseH;
      let tsMs = nowMs - (23 - i) * 3600000;
      if (dbReadings.length > 0) {
        const rIdx = dbReadings.length === 1 ? 0 : Math.min(dbReadings.length - 1, Math.round((i / 23) * (dbReadings.length - 1)));
        const rObj = dbReadings[rIdx];
        if (rObj?.timestamp) {
          const parsed = parseDbTimestampMs(rObj.timestamp);
          if (Number.isFinite(parsed)) tsMs = parsed;
        }
        if (hasRealT) tVal = rObj?.temperature !== null && rObj?.temperature !== undefined ? Number(rObj.temperature) : validT[Math.min(validT.length - 1, rIdx)] ?? baseT;
        if (hasRealH) hVal = rObj?.humidity !== null && rObj?.humidity !== undefined ? Number(rObj.humidity) : validH[Math.min(validH.length - 1, rIdx)] ?? baseH;
      }
      tempPts.push(tVal);
      humPts.push(hVal);
      chartPoints.push({
        timeLabel: fmtTime(tsMs),
        fullTime: fmtFull(tsMs),
        temp: Math.round(tVal * 100) / 100,
        hum: Math.round(hVal * 100) / 100
      });
    }

    const minTemp = Math.min(...tempPts);
    const maxTemp = Math.max(...tempPts);
    const avgTemp = tempPts.reduce((a, b) => a + b, 0) / tempPts.length;
    const minHum = Math.min(...humPts);
    const maxHum = Math.max(...humPts);
    const avgHum = humPts.reduce((a, b) => a + b, 0) / humPts.length;

    // Normalized visual curves (0..100 scale) anchored to real min/max
    const tSpan = Math.max(0.5, maxTemp - minTemp);
    const hSpan = Math.max(1.0, maxHum - minHum);
    const visualTemp = tempPts.map(v => Math.round((22 + ((v - minTemp) / tSpan) * 66) * 10) / 10);
    const visualHum = humPts.map(v => Math.round((18 + ((v - minHum) / hSpan) * 62) * 10) / 10);

    return {
      rawReadings: dbReadings,
      chartPoints,
      tempPts,
      humPts,
      minTemp,
      maxTemp,
      avgTemp,
      minHum,
      maxHum,
      avgHum,
      curves: {
        solar: visualTemp,
        use: visualHum
      }
    };
  }

  async function fetchSensorHistory(identifier, hours = 24) {
    try {
      const lim = hours > 24 ? 2200 : 300;
      const res = await fetch(`/api/v1/sensors/${encodeURIComponent(identifier)}/history?limit=${lim}&hours=${hours}`);
      if (res.ok) {
        const data = await res.json();
        const s = dbSensorsCache.find(item => item.identifier === identifier) || {
          identifier,
          name: data.name || identifier,
          current_temperature: data.readings?.at(-1)?.temperature ?? 21.5,
          current_humidity: data.readings?.at(-1)?.humidity ?? 45.0
        };
        const built = build24hSeriesForSensor(s, data.readings || []);
        built.hours = hours;
        sensorHistoryCache[identifier] = built;
        return sensorHistoryCache[identifier];
      }
    } catch (e) {}
    return sensorHistoryCache[identifier] || null;
  }

  // Sync live sensors directly from the SQLite/PostgreSQL database (/api/v1/sensors)
  function applyDbSensorToState(s) {
    const ident = s.identifier;
    const sType = s.sensor_type || "thermohygrometer";
    const areaId = s.area_id || "server_alpha";
    const tempId = `sensor.${ident}_temp`;
    const humId = `sensor.${ident}_humidity`;
    const pwrId = `sensor.${ident}_power`;
    const ampId = `sensor.${ident}_ampere`;
    const voltId = `sensor.${ident}_volt`;

    if ((sType === "thermohygrometer" || sType === "thermometer") && s.current_temperature !== null && s.current_temperature !== undefined) {
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

    if ((sType === "thermohygrometer" || sType === "hygrometer") && s.current_humidity !== null && s.current_humidity !== undefined) {
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

    if (sType === "power_meter" && s.power_kw !== null && s.power_kw !== undefined) {
      entitiesMap[pwrId] = { entity_id: pwrId, name: `${s.name} Power`, area_id: areaId };
      statesMap[pwrId] = {
        entity_id: pwrId,
        state: String(s.power_kw),
        attributes: {
          device_class: "power",
          unit_of_measurement: "kW",
          friendly_name: `${s.name} Power`,
          status: s.status || "online",
          db_identifier: ident
        }
      };
    }

    if (sType === "ammeter" && s.amperes !== null && s.amperes !== undefined) {
      entitiesMap[ampId] = { entity_id: ampId, name: `${s.name} Current`, area_id: areaId };
      statesMap[ampId] = {
        entity_id: ampId,
        state: String(s.amperes),
        attributes: {
          device_class: "current",
          unit_of_measurement: "A",
          friendly_name: `${s.name} Current`,
          status: s.status || "online",
          db_identifier: ident
        }
      };
    }

    if (sType === "voltmeter" && s.volts !== null && s.volts !== undefined) {
      entitiesMap[voltId] = { entity_id: voltId, name: `${s.name} Voltage`, area_id: areaId };
      statesMap[voltId] = {
        entity_id: voltId,
        state: String(s.volts),
        attributes: {
          device_class: "voltage",
          unit_of_measurement: "V",
          friendly_name: `${s.name} Voltage`,
          status: s.status || "online",
          db_identifier: ident
        }
      };
    }

    // Seed immediate 24h chart series and refresh from DB history endpoint
    const prevReadings = sensorHistoryCache[ident]?.rawReadings || [];
    sensorHistoryCache[ident] = build24hSeriesForSensor(s, prevReadings);

    // If the sensor has explicit 3D placement coordinates in DB, ensure its pins exist ONLY if not already present on any floor
    if (s.placement_x !== null && s.placement_x !== undefined && s.placement_z !== null && s.placement_z !== undefined) {
      const allFloors = building.floors || [];
      const unitId = `sensor_unit_${ident}`;
      const existingFurnFloor = allFloors.find(fl => (fl.furniture || []).some(f => f.id === unitId));
      const existingFurn = existingFurnFloor ? (existingFurnFloor.furniture || []).find(f => f.id === unitId) : null;
      const existingPinFloor = allFloors.find(fl => (fl.placements || []).some(p =>
        p.entity_id === tempId || p.entity_id === humId || p.entity_id === pwrId || p.entity_id === ampId || p.entity_id === voltId
      ));
      const targetFloor = existingFurnFloor || existingPinFloor || allFloors.find(f => f.id === (s.floor_id || "ground")) || allFloors[0];
      if (targetFloor) {
        targetFloor.placements = targetFloor.placements || [];
        const px = existingFurn ? Number(existingFurn.x) : Number(s.placement_x);
        const pz = existingFurn ? Number(existingFurn.z) : Number(s.placement_z);
        const py = existingFurn && existingFurn.mount_y != null
          ? Number(existingFurn.mount_y)
          : (s.placement_y !== null && s.placement_y !== undefined ? Number(s.placement_y) : 1.5);

        const hasPinAnywhere = (eid) => allFloors.some(fl => (fl.placements || []).some(p => p.entity_id === eid));
        if ((sType === "thermohygrometer" || sType === "thermometer") && !hasPinAnywhere(tempId)) {
          targetFloor.placements.push({ entity_id: tempId, x: px, z: pz, y: py });
        }
        if ((sType === "thermohygrometer" || sType === "hygrometer") && !hasPinAnywhere(humId)) {
          targetFloor.placements.push({ entity_id: humId, x: Math.round((px + (sType === "thermohygrometer" ? 0.35 : 0)) * 100) / 100, z: pz, y: py });
        }
        if (sType === "power_meter" && !hasPinAnywhere(pwrId)) {
          targetFloor.placements.push({ entity_id: pwrId, x: px, z: pz, y: py });
        }
        if (sType === "ammeter" && !hasPinAnywhere(ampId)) {
          targetFloor.placements.push({ entity_id: ampId, x: px, z: pz, y: py });
        }
        if (sType === "voltmeter" && !hasPinAnywhere(voltId)) {
          targetFloor.placements.push({ entity_id: voltId, x: px, z: pz, y: py });
        }
        targetFloor.furniture = targetFloor.furniture || [];
        if (!existingFurn) {
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
      if (dbSensorsCache.length > 0) {
        activeSensorIdentifier = dbSensorsCache[0].identifier;
      }
      for (const s of dbSensorsCache) {
        applyDbSensorToState(s);
        void fetchSensorHistory(s.identifier);
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
      const v3d = window.nfPanel.shadowRoot?.querySelector("fp3d-view3d, nf-view3d");
      if (v3d && typeof v3d.syncDevices === "function") {
        v3d.syncDevices(true);
        v3d.requestUpdate();
      }
    }
    window.dispatchEvent(new CustomEvent("monits-state-changed", { detail: { states: hass.states, sensors: dbSensorsCache, activeSensor: activeSensorIdentifier } }));
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

  function syncDevicePositionsFromBuilding(b) {
    if (!b || !Array.isArray(b.floors)) return;
    const sensorCoords = new Map();
    const rackCoords = new Map();
    for (const fl of b.floors) {
      const flId = fl.id || "ground";
      for (const f of (fl.furniture || [])) {
        if (f && typeof f.id === "string" && f.x != null && f.z != null) {
          if (f.id.startsWith("sensor_unit_")) {
            const ident = f.id.slice("sensor_unit_".length);
            sensorCoords.set(ident, { floor_id: flId, x: Number(f.x), z: Number(f.z), y: f.mount_y != null ? Number(f.mount_y) : null });
          }
          rackCoords.set(f.id, { floor_id: flId, x: Number(f.x), z: Number(f.z), rotation: Number(f.rotation || 0) });
        }
      }
      for (const p of (fl.placements || [])) {
        if (p && typeof p.entity_id === "string" && p.entity_id.startsWith("sensor.") && p.x != null && p.z != null) {
          const ident = p.entity_id.slice("sensor.".length).replace(/_(temp|humidity|power|ampere|volt)$/, "");
          if (ident && !sensorCoords.has(ident)) {
            sensorCoords.set(ident, { floor_id: flId, x: Number(p.x), z: Number(p.z), y: p.y != null ? Number(p.y) : null });
          }
        }
      }
    }
    for (const s of dbSensorsCache) {
      const c = sensorCoords.get(s.identifier);
      if (c) {
        s.floor_id = c.floor_id;
        s.placement_x = c.x;
        s.placement_z = c.z;
        if (c.y !== null) s.placement_y = c.y;
      }
    }
    for (const rk of racksCache) {
      const rc = rackCoords.get(rk.furniture_id) || rackCoords.get(rk.id);
      if (rc) {
        rk.floor_id = rc.floor_id;
        rk.pos_x = rc.x;
        rk.pos_z = rc.z;
        rk.rotation = rc.rotation;
      }
    }
  }

  async function persistBuildingToDatabase(bToSave) {
    if (!bToSave) return false;
    building = structuredClone(bToSave);
    syncRoomsToAreas(building);
    syncDevicePositionsFromBuilding(building);
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

  // Helper to resolve 3D coordinates (floorId, x, z, y) for any DB sensor
  function findSensor3DAnchor(s, b) {
    const targetB = b || building;
    const unitId = `sensor_unit_${s.identifier}`;
    const tempEntityId = `sensor.${s.identifier}_temp`;
    const humEntityId = `sensor.${s.identifier}_humidity`;

    // 1. Prefer sensor furniture item position (keeps 3D cards locked to where the sensor was placed/moved/imported)
    for (const fl of targetB?.floors || []) {
      const furn = (fl.furniture || []).find(f => f.id === unitId);
      if (furn && furn.x != null && furn.z != null) {
        return {
          floorId: fl.id,
          x: Number(furn.x),
          z: Number(furn.z),
          y: Number(furn.mount_y ?? s.placement_y ?? 1.5)
        };
      }
    }

    // 2. Fallback to placements pin
    for (const fl of targetB?.floors || []) {
      const pin = (fl.placements || []).find(p => p.entity_id === tempEntityId || p.entity_id === humEntityId);
      if (pin) {
        return {
          floorId: fl.id,
          x: Number(pin.x),
          z: Number(pin.z),
          y: Number(pin.y ?? s.placement_y ?? 1.35)
        };
      }
    }

    if (s.placement_x !== null && s.placement_x !== undefined && s.placement_z !== null && s.placement_z !== undefined) {
      return {
        floorId: s.floor_id || "ground",
        x: Number(s.placement_x),
        z: Number(s.placement_z),
        y: Number(s.placement_y ?? 1.35)
      };
    }

    // Fallback to center of linked room
    for (const fl of targetB?.floors || []) {
      const rm = (fl.rooms || []).find(r => (r.ha_area || r.id) === s.area_id || r.id === s.area_id);
      const pts = rm?.points || rm?.poly;
      if (rm && Array.isArray(pts) && pts.length > 0) {
        let sx = 0, sz = 0;
        for (const p of pts) {
          sx += Number(p[0] || 0);
          sz += Number(p[1] || 0);
        }
        return {
          floorId: fl.id,
          x: Math.round((sx / pts.length) * 100) / 100,
          z: Math.round((sz / pts.length) * 100) / 100,
          y: 2.1
        };
      }
    }

    return { floorId: "ground", x: 3.5, z: 2.5, y: 2.2 };
  }

  // Single Shared Time Travel / Live Selector (Task 5):
  // Pill, gauges, 24h charts, 3D labels, tooltips, and 2D badges ALL read from this selector.
  function resolveSensorStateAtTime(s, hassObj = null, replay = null) {
    const isTT = Boolean(replay && Number.isFinite(Number(replay.t)));
    const targetMs = isTT ? Number(replay.t) : Date.now();
    const cached = sensorHistoryCache[s.identifier] || build24hSeriesForSensor(s, []);
    const raw = Array.isArray(cached.rawReadings) ? cached.rawReadings : [];
    const tempId = `sensor.${s.identifier}_temp`;
    const humId = `sensor.${s.identifier}_humidity`;
    const fmtTime = (ms) => {
      const d = new Date(ms);
      return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    };
    const fmtFull = (ms) => {
      const d = new Date(ms);
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${fmtTime(ms)}:${String(d.getSeconds()).padStart(2, "0")}`;
    };

    if (!isTT) {
      const temp = s.current_temperature !== null && s.current_temperature !== undefined ? Number(s.current_temperature) : null;
      const humidity = s.current_humidity !== null && s.current_humidity !== undefined ? Number(s.current_humidity) : null;
      return {
        isTimeTravel: false,
        targetMs,
        cursorTimeLabel: fmtTime(targetMs),
        cursorFullTime: fmtFull(targetMs),
        cursorIndex: 23,
        temp,
        humidity,
        noData: temp === null && humidity === null,
        hist: cached
      };
    }

    // 1. Read exact value from Time Travel replayer hass.states (same source as 3D pills!)
    const hStates = hassObj?.states || {};
    const pillT = hStates[tempId]?.state;
    const pillH = hStates[humId]?.state;
    let temp = (pillT !== undefined && pillT !== "unavailable" && pillT !== "unknown" && Number.isFinite(Number(pillT))) ? Number(pillT) : null;
    let humidity = (pillH !== undefined && pillH !== "unavailable" && pillH !== "unknown" && Number.isFinite(Number(pillH))) ? Number(pillH) : null;

    // 2. Nearest historical reading at or before targetMs (for fallback & chart rescaling)
    const timed = raw
      .map(r => ({
        ms: parseDbTimestampMs(r.timestamp),
        t: r.temperature !== null && r.temperature !== undefined && Number.isFinite(Number(r.temperature)) ? Number(r.temperature) : null,
        h: r.humidity !== null && r.humidity !== undefined && Number.isFinite(Number(r.humidity)) ? Number(r.humidity) : null
      }))
      .filter(r => Number.isFinite(r.ms))
      .sort((a, b) => a.ms - b.ms);

    let nearest = null;
    for (let i = timed.length - 1; i >= 0; i--) {
      if (timed[i].ms <= targetMs) {
        nearest = timed[i];
        break;
      }
    }
    if (temp === null && nearest && nearest.t !== null) temp = nearest.t;
    if (humidity === null && nearest && nearest.h !== null) humidity = nearest.h;

    // 3. Re-slice the 24h chart window to the Time Travel range containing targetMs
    const winEnd = Math.max(targetMs, timed.length ? Math.min(timed[timed.length - 1].ms, targetMs + 6 * 3600000) : targetMs);
    const winStart = winEnd - 24 * 3600000;
    const inWin = timed.filter(r => r.ms >= winStart && r.ms <= winEnd);
    const tempPts = [];
    const humPts = [];
    const chartPoints = [];
    let cursorIndex = 23;
    let bestDist = Infinity;

    for (let i = 0; i < 24; i++) {
      const slotMs = winStart + (i / 23) * (winEnd - winStart);
      const dist = Math.abs(slotMs - targetMs);
      if (dist < bestDist) {
        bestDist = dist;
        cursorIndex = i;
      }
      // Find nearest sample at or before slotMs
      let sample = null;
      for (let j = inWin.length - 1; j >= 0; j--) {
        if (inWin[j].ms <= slotMs) { sample = inWin[j]; break; }
      }
      if (!sample && inWin.length) sample = inWin[0];
      const tv = sample?.t ?? temp ?? Number(s.current_temperature ?? 21.5);
      const hv = sample?.h ?? humidity ?? Number(s.current_humidity ?? 45.0);
      tempPts.push(tv);
      humPts.push(hv);
      chartPoints.push({
        timeLabel: fmtTime(slotMs),
        fullTime: fmtFull(slotMs),
        temp: Math.round(tv * 100) / 100,
        hum: Math.round(hv * 100) / 100
      });
    }
    // Pin cursor point to exact pill/gauge value so pill = gauge = chart cursor
    if (temp !== null) {
      tempPts[cursorIndex] = temp;
      chartPoints[cursorIndex].temp = Math.round(temp * 100) / 100;
    }
    if (humidity !== null) {
      humPts[cursorIndex] = humidity;
      chartPoints[cursorIndex].hum = Math.round(humidity * 100) / 100;
    }
    chartPoints[cursorIndex].fullTime = fmtFull(targetMs);
    chartPoints[cursorIndex].timeLabel = fmtTime(targetMs);

    const minTemp = Math.min(...tempPts);
    const maxTemp = Math.max(...tempPts);
    const avgTemp = tempPts.reduce((a, b) => a + b, 0) / tempPts.length;
    const minHum = Math.min(...humPts);
    const maxHum = Math.max(...humPts);
    const avgHum = humPts.reduce((a, b) => a + b, 0) / humPts.length;
    const tSpan = Math.max(0.5, maxTemp - minTemp);
    const hSpan = Math.max(1.0, maxHum - minHum);
    const visualTemp = tempPts.map(v => Math.round((22 + ((v - minTemp) / tSpan) * 66) * 10) / 10);
    const visualHum = humPts.map(v => Math.round((18 + ((v - minHum) / hSpan) * 62) * 10) / 10);

    return {
      isTimeTravel: true,
      targetMs,
      cursorTimeLabel: fmtTime(targetMs),
      cursorFullTime: fmtFull(targetMs),
      cursorIndex,
      temp,
      humidity,
      noData: temp === null && humidity === null,
      hist: {
        rawReadings: raw,
        tempPts,
        humPts,
        chartPoints,
        minTemp,
        maxTemp,
        avgTemp,
        minHum,
        maxHum,
        avgHum,
        curves: { solar: visualTemp, use: visualHum }
      }
    };
  }

  function buildCardDescriptorForSensor(s, b, index = 0, total = 1, hassObj = null, replay = null) {
    if (!s) return null;
    const resolved = resolveSensorStateAtTime(s, hassObj, replay);
    const hist = resolved.hist;
    const temp = resolved.temp;
    const humidity = resolved.humidity;
    const anchor = findSensor3DAnchor(s, b);
    const cleanTitle = (s.name || s.identifier)
      .replace("Thermohygrograph", "")
      .replace("Sensor", "")
      .trim() || s.name;

    return {
      kind: "env_sensor",
      identifier: s.identifier,
      name: cleanTitle,
      fullName: s.name || s.identifier,
      areaId: s.area_id || "server_alpha",
      at: anchor,
      temp: temp ?? 0,
      humidity: humidity ?? 0,
      hasTemp: temp !== null,
      hasHum: humidity !== null,
      noData: resolved.noData,
      isTimeTravel: resolved.isTimeTravel,
      cursorIndex: resolved.cursorIndex,
      cursorTimeLabel: resolved.cursorTimeLabel,
      cursorFullTime: resolved.cursorFullTime,
      powerKw: s.power_kw,
      battery: s.battery_level ?? 98,
      status: resolved.noData ? "offline" : (s.status || "online"),
      tempRatio: temp !== null ? Math.max(0.06, Math.min(1, temp / 45)) : 0,
      humRatio: humidity !== null ? Math.max(0.06, Math.min(1, humidity / 100)) : 0,
      minTemp: hist.minTemp,
      maxTemp: hist.maxTemp,
      avgTemp: hist.avgTemp,
      minHum: hist.minHum,
      maxHum: hist.maxHum,
      avgHum: hist.avgHum,
      tempPts: hist.tempPts,
      humPts: hist.humPts,
      chartPoints: hist.chartPoints,
      curves: hist.curves,
      grafanaLinkEnabled: Boolean(s.grafana_link_enabled),
      grafanaNewTab: s.grafana_new_tab !== false,
      grafanaUrl: s.grafana_url || "",
      expanded: s.identifier === expandedSensorIdentifier,
      selected: selectedObject?.kind === "sensor" && selectedObject?.id === s.identifier,
      indexLabel: `${index + 1}/${total}`
    };
  }

  function computeSunPosition(ms, lat, lon) {
    const rad = Math.PI / 180;
    const n = (ms / 864e5 + 2440587.5 - 2451545) / 36525;
    const L = ((280.46646 + n * (36000.76983 + n * 3.032e-4)) % 360 + 360) % 360;
    const M = 357.52911 + n * (35999.05029 - 1.537e-4 * n);
    const e = 0.016708634 - n * (4.2037e-8 + 1.267e-10 * n);
    const C = Math.sin(M * rad) * (1.914602 - n * (0.004817 + 1.4e-5 * n)) + Math.sin(2 * M * rad) * (0.019993 - 1.01e-4 * n) + Math.sin(3 * M * rad) * 2.89e-4;
    const omega = 125.04 - 1934.136 * n;
    const lambda = L + C - 0.00569 - 0.00478 * Math.sin(omega * rad);
    const eps = 23 + (26 + (21.448 - n * (46.815 + n * (5.9e-4 - n * 0.001813))) / 60) / 60 + 0.00256 * Math.cos(omega * rad);
    const dec = Math.asin(Math.sin(eps * rad) * Math.sin(lambda * rad));
    const y = Math.tan((eps / 2) * rad) ** 2;
    const eqTime = 4 * (y * Math.sin(2 * L * rad) - 2 * e * Math.sin(M * rad) + 4 * e * y * Math.sin(M * rad) * Math.cos(2 * L * rad) - 0.5 * y * y * Math.sin(4 * L * rad) - 1.25 * e * e * Math.sin(2 * M * rad)) / rad;
    const d = new Date(ms);
    const ha = (((d.getUTCHours() * 60 + d.getUTCMinutes() + d.getUTCSeconds() / 60 + eqTime + 4 * lon) % 1440 + 1440) % 1440 / 4 - 180) * rad;
    const latR = lat * rad;
    const cosZ = Math.sin(latR) * Math.sin(dec) + Math.cos(latR) * Math.cos(dec) * Math.cos(ha);
    const elevation = 90 - Math.acos(Math.min(1, Math.max(-1, cosZ))) / rad;
    const azimuth = (Math.atan2(Math.sin(ha), Math.cos(ha) * Math.sin(latR) - Math.tan(dec) * Math.cos(latR)) / rad + 180 + 360) % 360;
    return { azimuth: Math.round(azimuth * 100) / 100, elevation: Math.round(elevation * 100) / 100 };
  }

  let siteLat = -2.57555;
  let siteLon = 140.686402;
  try {
    const sRes = await fetch("/api/v1/settings");
    if (sRes.ok) {
      const sData = await sRes.json();
      const pLat = parseFloat(sData.site_latitude);
      const pLon = parseFloat(sData.site_longitude);
      if (Number.isFinite(pLat)) siteLat = pLat;
      if (Number.isFinite(pLon)) siteLon = pLon;
    }
  } catch (e) {}

  function updateLiveSunEntity() {
    const pos = computeSunPosition(Date.now(), siteLat, siteLon);
    statesMap["sun.sun"] = {
      entity_id: "sun.sun",
      state: pos.elevation > -0.833 ? "above_horizon" : "below_horizon",
      attributes: {
        azimuth: pos.azimuth,
        elevation: pos.elevation,
        friendly_name: "Sun"
      },
      last_changed: new Date().toISOString()
    };
  }
  updateLiveSunEntity();
  setInterval(() => {
    updateLiveSunEntity();
    pushHassToPanel();
  }, 60000);

  const initialIsDark = (document.documentElement.getAttribute("data-theme") || localStorage.getItem("monit_theme") || "neon") !== "light";
  const hass = {
    language: activeLang,
    selectedTheme: { dark: initialIsDark },
    themes: { darkMode: initialIsDark },
    config: {
      latitude: siteLat,
      longitude: siteLon,
      time_zone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Jayapura",
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
    // Virtual Device Engine
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

      // 1. Building & Plans Persistence (NeonPlan 3D v3.5.1 + NextFloor)
      if (type === "neonplan3d/plans/list" || type === "nextfloor/plans/list") {
        const flCount = building?.floors?.length ?? 0;
        const rmCount = building?.floors?.reduce((n, f) => n + (f.rooms?.length ?? 0), 0) ?? 0;
        const fnCount = building?.floors?.reduce((n, f) => n + (f.furniture?.length ?? 0), 0) ?? 0;
        return {
          plans: [{ ...mainEntry, revision, floors: flCount, rooms: rmCount, furniture: fnCount }],
          trash: [],
          locate_plan: "main"
        };
      }

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

      if (type === "nextfloor/history/get" || type === "neonplan3d/history/get") {
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

      if (type === "nextfloor/history/delete" || type === "neonplan3d/history/delete") {
        const idx = history.findIndex((h) => h.id === msg.snapshot_id);
        if (idx >= 0) history.splice(idx, 1);
        await persistBuildingToDatabase(building);
        return null;
      }

      // 2b. Full Backup Export & Restore (NeonPlan 3D + Server_Monits DB)
      if (type === "neonplan3d/backup/export" || type === "nextfloor/backup/export") {
        const curBuilding = structuredClone(window.nfPanel?.data?.building || building);
        return {
          format: "neonplan3d-backup",
          version: 1,
          building: curBuilding,
          plans: [
            {
              id: "main",
              name: mainEntry.name || "Main Server Facility",
              building: structuredClone(curBuilding)
            }
          ],
          main: "main",
          packs: [DEMO_PACK],
          server_monits: {
            sensors: structuredClone(dbSensorsCache),
            racks: structuredClone(racksCache),
            wifi_survey: structuredClone(wifiSurveyPointsCache)
          }
        };
      }

      if (type === "neonplan3d/backup/import" || type === "nextfloor/backup/import") {
        const incoming = msg.building;
        if (!incoming || !Array.isArray(incoming.floors)) {
          throw { code: "invalid_backup", message: "Backup is missing building floors" };
        }
        // Keep current state as a restore point before replacing
        history.push({
          id: `s${history.length + 1}`,
          revision,
          saved_at: Date.now() / 1000,
          name: activeLang === "id" ? "Sebelum Pulihkan Backup" : "Before Full Backup Restore",
          building: structuredClone(building)
        });
        revision += 1;
        await persistBuildingToDatabase(incoming);
        if (window.nfPanel?.data) {
          window.nfPanel.data.building = structuredClone(building);
        }
        pushHassToPanel();
        for (const cb of listeners) cb({ revision });
        return {
          building: structuredClone(building),
          packs: Array.isArray(msg.packs) ? msg.packs.length : 0,
          skipped: []
        };
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

      // 6. License checks (Unlocks all Pro capabilities, 100% offline, no external shop/API)
      if (type.includes("license")) {
        return {
          active: true,
          instance: "server_monits_enterprise",
          licensee: "Server_Monits Enterprise Pro",
          checked_at: Date.now() / 1000,
          error: null,
          packs: [],
          offers: [],
          updates: [],
          loyalty: null,
          newsletter: null,
          supporter: { code: "SM-PRO", until: "2099-12-31" }
        };
      }

      // 7. BLE Devices, TimeTravel & Diagnostics (100% local)
      if (type === "nextfloor/ble/devices" || type === "neonplan3d/ble/devices") {
        return { available: false, scanners: [], devices: [] };
      }

      if (type === "nextfloor/ble/scan" || type === "neonplan3d/ble/scan") {
        return { readings: {} };
      }

      if (type.startsWith("neonplan3d/locate/")) {
        return { available: false, scanners: [], tags: [] };
      }

      if (type.startsWith("neonplan3d/diagnostics/")) {
        return { enabled: false };
      }

      // 8b. NeonPlan 3D Time Travel History (real SQL/DB readings + sun.sun solar trajectory + 5-min stats)
      if (type === "neonplan3d/timetravel/history") {
        const startSec = Number(msg.start_time ?? (Date.now() / 1000 - 86400));
        const endSec = Number(msg.end_time ?? (Date.now() / 1000));
        const spanSec = Math.max(60, Math.round(endSec - startSec));
        const nowSec = Math.floor(Date.now() / 1000);
        const hoursReq = Math.max(24, Math.ceil((nowSec - startSec) / 3600) + 1);
        const reqIds = msg.entity_ids || [];
        const statIds = msg.statistic_ids || [];
        const entitiesOut = {};
        const statsOut = {};

        async function getSensorPairsForEntity(eid) {
          const st = statesMap[eid];
          const ident = st?.attributes?.db_identifier || eid.replace(/^sensor\./, "").replace(/_(temp|humidity|power|ampere|volt)$/, "");
          const s = dbSensorsCache.find(item => item.identifier === ident);
          const cached = sensorHistoryCache[ident];
          const series = (cached && (cached.hours || 24) >= hoursReq)
            ? cached
            : (await fetchSensorHistory(ident, hoursReq) || cached || (s ? build24hSeriesForSensor(s, []) : null));
          if (!series) return { pairs: [], attrs: st?.attributes || {}, fallback: st ? Number(st.state) : NaN };
          const isHum = eid.endsWith("_humidity");
          const isPower = eid.endsWith("_power");
          const isAmp = eid.endsWith("_ampere");
          const isVolt = eid.endsWith("_volt");
          const raw = Array.isArray(series.rawReadings) ? series.rawReadings : [];
          const pairs = [];
          const attrs = st?.attributes || {};

          if (raw.length > 0) {
            raw.forEach((r, idx) => {
              const val = isHum ? r.humidity : isPower ? r.raw_data?.power_kw : isAmp ? r.raw_data?.amperes : isVolt ? r.raw_data?.volts : r.temperature;
              if (val === null || val === undefined || !Number.isFinite(Number(val))) return;
              const parsedMs = parseDbTimestampMs(r.timestamp);
              const tsSec = Number.isFinite(parsedMs) ? (parsedMs / 1000) : (startSec + (spanSec * idx) / Math.max(1, raw.length - 1));
              const off = Math.max(0, Math.min(spanSec, Math.round(tsSec - startSec)));
              pairs.push([off, Number(val)]);
            });
          }
          if (pairs.length === 0) {
            const pts = isHum ? series.humPts : series.tempPts;
            pts.forEach((val, idx) => {
              if (!Number.isFinite(Number(val))) return;
              const off = Math.round((spanSec * idx) / Math.max(1, pts.length - 1));
              pairs.push([off, Number(val)]);
            });
          }
          pairs.sort((a, b) => a[0] - b[0]);
          const fallback = pairs.length > 0 ? pairs[0][1] : (st ? Number(st.state) : NaN);
          return { pairs, attrs, fallback };
        }

        for (const eid of reqIds) {
          if (eid === "sun.sun") {
            const tArr = [];
            const vArr = [];
            const tabArr = [];
            const step = 900; // 15-min steps
            for (let ts = startSec; ts <= endSec; ts += step) {
              const pos = computeSunPosition(ts * 1000, siteLat, siteLon);
              const stVal = pos.elevation > -0.833 ? "above_horizon" : "below_horizon";
              tArr.push(Math.round(ts - startSec));
              vArr.push(tabArr.length);
              tabArr.push([stVal, { azimuth: pos.azimuth, elevation: pos.elevation, friendly_name: "Sun" }]);
            }
            entitiesOut["sun.sun"] = { t: tArr, v: vArr, tab: tabArr };
            continue;
          }

          const st = statesMap[eid];
          if (!eid.startsWith("sensor.")) {
            if (st) {
              entitiesOut[eid] = { t: [0], v: [0], tab: [[String(st.state), st.attributes || {}]] };
            }
            continue;
          }

          const { pairs, attrs } = await getSensorPairsForEntity(eid);
          if (pairs.length > 0) {
            if (pairs[0][0] > 0) pairs.unshift([0, pairs[0][1]]);
            const tArr = [];
            const vArr = [];
            const tabArr = [];
            for (const [off, nval] of pairs) {
              tArr.push(off);
              vArr.push(tabArr.length);
              tabArr.push([String(nval), attrs]);
            }
            entitiesOut[eid] = { t: tArr, v: vArr, tab: tabArr };
          }
        }

        // Populate 5-minute bucketed stats for numeric sensors (statistic_ids)
        const statStep = 300;
        const numBuckets = Math.max(1, Math.ceil(spanSec / statStep) + 1);
        for (const eid of statIds) {
          const { pairs, fallback } = await getSensorPairsForEntity(eid);
          if (pairs.length === 0 && !Number.isFinite(fallback)) continue;
          const sums = new Array(numBuckets).fill(0);
          const counts = new Array(numBuckets).fill(0);
          for (const [off, nval] of pairs) {
            const b = Math.max(0, Math.min(numBuckets - 1, Math.floor(off / statStep)));
            sums[b] += nval;
            counts[b] += 1;
          }
          const mean = new Array(numBuckets).fill(null);
          let lastVal = Number.isFinite(fallback) ? fallback : null;
          for (let b = 0; b < numBuckets; b++) {
            if (counts[b] > 0) {
              lastVal = Math.round((sums[b] / counts[b]) * 100) / 100;
              mean[b] = lastVal;
            } else if (lastVal !== null) {
              mean[b] = lastVal;
            }
          }
          statsOut[eid] = { start: startSec, step: statStep, mean };
        }

        return {
          day_start: startSec,
          end: endSec,
          oldest: nowSec - 30 * 86400,
          keep_days: 30,
          entities: entitiesOut,
          stats: statsOut,
          missing: []
        };
      }

      if (type.startsWith("neonplan3d/timetravel/")) {
        return { available: false, rows: [], events: [] };
      }

      // 8. 24-Hour Sensor History & Statistics from Database (used by 24h Chart & Time Travel)
      if (type === "history/history_during_period") {
        const reqIds = msg.entity_ids || [];
        const startMs = msg.start_time ? Date.parse(msg.start_time) : Date.now() - 86400000;
        const endMs = msg.end_time ? Date.parse(msg.end_time) : Date.now();
        const out = {};

        for (const eid of reqIds) {
          const st = statesMap[eid];
          const ident = st?.attributes?.db_identifier || eid.replace(/^sensor\./, "").replace(/_(temp|humidity|power|ampere|volt)$/, "");
          const s = dbSensorsCache.find(item => item.identifier === ident);
          const series = sensorHistoryCache[ident] || await fetchSensorHistory(ident) || (s ? build24hSeriesForSensor(s, []) : null);
          if (series) {
            const isHum = eid.endsWith("_humidity");
            const isPower = eid.endsWith("_power");
            const isAmp = eid.endsWith("_ampere");
            const isVolt = eid.endsWith("_volt");
            const raw = Array.isArray(series.rawReadings) ? series.rawReadings : [];
            if (raw.length > 0) {
              const mapped = [];
              raw.forEach((r, idx) => {
                const val = isHum ? r.humidity : isPower ? r.raw_data?.power_kw : isAmp ? r.raw_data?.amperes : isVolt ? r.raw_data?.volts : r.temperature;
                if (val === null || val === undefined) return;
                const parsedTs = r.timestamp ? Date.parse(String(r.timestamp).replace(" ", "T")) : NaN;
                const lu = Number.isFinite(parsedTs)
                  ? parsedTs / 1000
                  : (startMs + ((endMs - startMs) * idx) / Math.max(1, raw.length - 1)) / 1000;
                mapped.push({ lu, s: String(val), a: st?.attributes || {} });
              });
              if (mapped.length > 0) {
                out[eid] = mapped;
                continue;
              }
            }
            const pts = isHum ? series.humPts : series.tempPts;
            out[eid] = pts.map((val, idx) => ({
              lu: (startMs + ((endMs - startMs) * idx) / Math.max(1, pts.length - 1)) / 1000,
              s: String(val),
              a: st?.attributes || {}
            }));
          }
        }
        return out;
      }

      if (type === "energy/get_prefs") {
        return { energy_sources: [] };
      }

      if (type === "recorder/statistics_during_period") {
        return {};
      }

      if (type.startsWith("nextfloor/") && type.endsWith("/subscribe")) {
        return { id: msg.id || 1, type: "result", success: true };
      }

      return {};
    }
  };

  // Ensure 3D floating hologram cards are enabled and unfolded by default
  try {
    localStorage.setItem("nextfloor.cards", "1");
    localStorage.setItem("nextfloor.house_card_folded", "0");
  } catch (e) {}

  // Listen for clicks on any 3D sensor pin (`hass-more-info`) to move the 3D Gauge + 24h Chart Card to that sensor in 3D space
  window.addEventListener("hass-more-info", (ev) => {
    const entityId = ev?.detail?.entityId;
    if (!entityId || typeof entityId !== "string") return;
    if (entityId.startsWith("sensor.")) {
      const st = statesMap[entityId];
      const ident = st?.attributes?.db_identifier || entityId.replace(/^sensor\./, "").replace(/_(temp|humidity|power)$/, "");
      const matched = dbSensorsCache.find(s => s.identifier === ident);
      if (matched) {
        activeSensorIdentifier = matched.identifier;
        expandedSensorIdentifier = matched.identifier;
        try {
          localStorage.setItem("nextfloor.cards", "1");
          localStorage.setItem("nextfloor.house_card_folded", "0");
          const v3d = window.nfPanel?.shadowRoot?.querySelector("fp3d-view3d, nf-view3d");
          if (v3d) {
            v3d._liveCardOn = true;
            v3d._houseFolded = false;
          }
        } catch (e) {}
        void fetchSensorHistory(matched.identifier).then(() => pushHassToPanel());
        pushHassToPanel();
      }
    }
  });

  // Expose programmatic API for Integrated Header, 3D Hologram Cards & Drawers
  window.monitsApi = {
    getStates: () => statesMap,
    getSensors: () => dbSensorsCache,
    getBuilding: () => (window.nfPanel?.data?.building || building),
    getAreas: () => areasMap,
    getActiveSensorIdentifier: () => activeSensorIdentifier,
    getExpandedSensorIdentifier: () => expandedSensorIdentifier,
    setExpandedSensor(identOrEntityId) {
      if (!identOrEntityId) {
        if (expandedSensorIdentifier !== null) {
          expandedSensorIdentifier = null;
          pushHassToPanel();
        }
        return null;
      }
      const clean = identOrEntityId.replace(/^sensor\./, "").replace(/_(temp|humidity|power)$/, "");
      const found = dbSensorsCache.find(s => s.identifier === clean || s.area_id === clean);
      if (found) {
        activeSensorIdentifier = found.identifier;
        expandedSensorIdentifier = found.identifier;
        void fetchSensorHistory(found.identifier).then(() => pushHassToPanel());
        pushHassToPanel();
        return this.getSensorCardData(found.identifier);
      }
      return null;
    },
    setActiveSensor(identOrEntityId) {
      if (!identOrEntityId) return null;
      const clean = identOrEntityId.replace(/^sensor\./, "").replace(/_(temp|humidity|power)$/, "");
      const found = dbSensorsCache.find(s => s.identifier === clean || s.area_id === clean);
      if (found) {
        activeSensorIdentifier = found.identifier;
        expandedSensorIdentifier = found.identifier;
        void fetchSensorHistory(found.identifier).then(() => pushHassToPanel());
        pushHassToPanel();
        return this.getSensorCardData(found.identifier);
      }
      return null;
    },
    cycleActiveSensor(delta = 1) {
      if (!dbSensorsCache.length) return null;
      const curIdx = Math.max(0, dbSensorsCache.findIndex(s => s.identifier === activeSensorIdentifier));
      const nextIdx = (curIdx + delta + dbSensorsCache.length) % dbSensorsCache.length;
      activeSensorIdentifier = dbSensorsCache[nextIdx].identifier;
      if (expandedSensorIdentifier !== null) {
        expandedSensorIdentifier = activeSensorIdentifier;
      }
      void fetchSensorHistory(activeSensorIdentifier).then(() => pushHassToPanel());
      pushHassToPanel();
      return this.getSensorCardData(activeSensorIdentifier);
    },
    getSensorCardData(identifier = null, customBuilding = null) {
      if (!dbSensorsCache.length) return null;
      const targetIdent = identifier || activeSensorIdentifier;
      let idx = dbSensorsCache.findIndex(s => s.identifier === targetIdent || s.area_id === targetIdent);
      if (idx < 0) idx = 0;
      const s = dbSensorsCache[idx];
      return buildCardDescriptorForSensor(s, customBuilding || window.nfPanel?.data?.building || building, idx, dbSensorsCache.length);
    },
    getLiveSensorCards(b, floorId = null, roomId = null, hassObj = null, replay = null) {
      if (!dbSensorsCache.length) return [];
      const targetB = b || window.nfPanel?.data?.building || building;
      activeTimeTravelState = replay && Number.isFinite(Number(replay.t)) ? { t: Number(replay.t), hass: hassObj } : null;

      // Return ALL thermohygrometer sensors on the active floor (or inside the selected room)
      let roomAreaFilter = null;
      if (roomId) {
        for (const fl of targetB?.floors || []) {
          const rm = (fl.rooms || []).find(r => r.id === roomId);
          if (rm) {
            roomAreaFilter = rm.ha_area || rm.id;
            break;
          }
        }
      }

      const cards = [];
      dbSensorsCache.forEach((s, idx) => {
        const anchor = findSensor3DAnchor(s, targetB);
        if (floorId && anchor.floorId !== floorId) return;
        if (roomAreaFilter && s.area_id !== roomAreaFilter) return;
        const card = buildCardDescriptorForSensor(s, targetB, idx, dbSensorsCache.length, hassObj, replay);
        if (card) cards.push(card);
      });
      return cards;
    },
    getSensorStateAtActiveTime(identifier) {
      const s = dbSensorsCache.find(x => x.identifier === identifier);
      if (!s) return null;
      const tt = activeTimeTravelState;
      return resolveSensorStateAtTime(s, tt?.hass || hass, tt ? { t: tt.t } : null);
    },
    buildFloorHeatmapCanvas(floor, heatMode, hassObj = null) {
      if (!floor || !Array.isArray(floor.rooms) || !floor.rooms.length) return null;
      const hStates = (hassObj && hassObj.states) || statesMap;

      // 1. Collect spatial sources on this floor
      const sources = [];
      if (heatMode === "temperature" || heatMode === "humidity") {
        const seen = new Set();
        for (const p of floor.placements || []) {
          const eid = p.entity_id || "";
          const st = hStates[eid];
          if (!st) continue;
          const dc = st.attributes?.device_class;
          const isTemp = heatMode === "temperature" && (dc === "temperature" || eid.endsWith("_temp"));
          const isHum = heatMode === "humidity" && (dc === "humidity" || eid.endsWith("_humidity"));
          if (!isTemp && !isHum) continue;
          const val = Number(st.state);
          if (Number.isFinite(val)) {
            sources.push({ x: Number(p.x), z: Number(p.z), value: val });
            seen.add(eid);
          }
        }
        // Fallback: include any DB sensors with coordinates on this floor not yet in placements
        for (const s of dbSensorsCache) {
          if (s.floor_id && s.floor_id !== floor.id) continue;
          if (s.placement_x == null || s.placement_z == null) continue;
          const eid = heatMode === "temperature" ? `sensor.${s.identifier}_temp` : `sensor.${s.identifier}_humidity`;
          if (seen.has(eid)) continue;
          const val = heatMode === "temperature" ? Number(s.current_temperature) : Number(s.current_humidity);
          if (Number.isFinite(val)) {
            sources.push({ x: Number(s.placement_x), z: Number(s.placement_z), value: val });
          }
        }
      } else if (heatMode === "wifi") {
        // 1a. Prefer measured Wi-Fi Survey RSSI points filtered by shared AP/SSID + Band + Channel state
        const floorSurvey = wifiSurveyPointsCache.filter(p => {
          if ((p.floor_id || "ground") !== floor.id) return false;
          if (selectedWifiSsid && p.ssid !== selectedWifiSsid) return false;
          if (selectedWifiBand && normalizeBandClient(p.band, p.channel) !== selectedWifiBand) return false;
          if (selectedWifiChannel !== null && Number(p.channel) !== Number(selectedWifiChannel)) return false;
          return true;
        });
        if (floorSurvey.length > 0) {
          for (const p of floorSurvey) {
            sources.push({
              x: Number(p.x),
              z: Number(p.z),
              value: Number(p.rssi_dbm),
              measured: true,
              ssid: p.ssid,
              band: normalizeBandClient(p.band, p.channel),
              channel: p.channel ?? null
            });
          }
        } else {
          // 1b. Fallback: placed WiFi APs in furniture (filtered by SSID/band if matching) using path-loss model
          for (const f of floor.furniture || []) {
            const t = String(f.type || "").toLowerCase();
            if (t.includes("wifi") || t.includes("router") || t.endsWith(":ap")) {
              if (selectedWifiSsid && (f.name || "").trim() !== selectedWifiSsid) continue;
              if (selectedWifiBand && f.band && normalizeBandClient(f.band, f.channel) !== selectedWifiBand) continue;
              sources.push({ x: Number(f.x), z: Number(f.z), txPower: -28 });
            }
          }
          if (!sources.length && !selectedWifiSsid && !selectedWifiBand && selectedWifiChannel === null && floor.rooms.length) {
            const apRoom = floor.rooms.find(r => (r.name || "").toLowerCase().includes("hardening") || (r.name || "").toLowerCase().includes("noc")) || floor.rooms[0];
            const pts = apRoom.points || apRoom.poly || [];
            if (pts.length) {
              let sx = 0, sz = 0;
              for (const pt of pts) { sx += Number(pt[0]); sz += Number(pt[1]); }
              sources.push({ x: sx / pts.length, z: sz / pts.length, txPower: -30 });
            }
          }
        }
      }

      if (!sources.length) return null;

      // 2. Compute floor bounding box
      let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
      const roomPolys = [];
      for (const rm of floor.rooms) {
        const pts = rm.points || rm.poly || [];
        if (pts.length < 3) continue;
        roomPolys.push(pts);
        for (const [px, pz] of pts) {
          if (px < x0) x0 = px;
          if (px > x1) x1 = px;
          if (pz < z0) z0 = pz;
          if (pz > z1) z1 = pz;
        }
      }
      if (!Number.isFinite(x0) || x1 <= x0 || z1 <= z0) return null;

      // 3. Extract wall segments & door openings (deduplicating shared walls)
      const wallSegs = [];
      const wallKeyMap = new Map();
      const roundKey = (ax, az, bx, bz) => {
        const a = `${ax.toFixed(2)},${az.toFixed(2)}`;
        const b = `${bx.toFixed(2)},${bz.toFixed(2)}`;
        return a < b ? `${a}|${b}` : `${b}|${a}`;
      };

      for (const rm of floor.rooms) {
        const pts = rm.points || rm.poly || [];
        for (let i = 0; i < pts.length; i++) {
          const [ax, az] = pts[i];
          const [bx, bz] = pts[(i + 1) % pts.length];
          const k = roundKey(ax, az, bx, bz);
          let seg = wallKeyMap.get(k);
          if (!seg) {
            seg = { ax, az, bx, bz, doors: [] };
            wallKeyMap.set(k, seg);
            wallSegs.push(seg);
          }
          // Attach any door/passage openings on this room edge
          for (const op of floor.openings || []) {
            if (op.room_id === rm.id && op.edge === i && (op.type === "door" || op.type === "passage")) {
              const len = Math.hypot(bx - ax, bz - az) || 1;
              const centerT = Number(op.offset ?? len / 2) / len;
              const halfT = (Number(op.width ?? 0.9) / 2) / len;
              seg.doors.push([Math.max(0, centerT - halfT), Math.min(1, centerT + halfT)]);
            }
          }
        }
      }
      for (const w of floor.walls || []) {
        if (w.a && w.b) {
          wallSegs.push({ ax: w.a[0], az: w.a[1], bx: w.b[0], bz: w.b[1], doors: [] });
        }
      }

      // Helper: point-in-polygon
      const inPoly = (px, pz, poly) => {
        let inside = false;
        for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
          const [xi, zi] = poly[i];
          const [xj, zj] = poly[j];
          if ((zi > pz) !== (zj > pz) && px < ((xj - xi) * (pz - zi)) / (zj - zi + 1e-9) + xi) {
            inside = !inside;
          }
        }
        return inside;
      };

      // Helper: count solid walls & doors crossed by segment (p1 -> p2)
      const countCrossings = (xA, zA, xB, zB) => {
        let walls = 0;
        let doors = 0;
        const dx = xB - xA;
        const dz = zB - zA;
        for (let i = 0; i < wallSegs.length; i++) {
          const s = wallSegs[i];
          const sx = s.bx - s.ax;
          const sz = s.bz - s.az;
          const denom = dx * sz - dz * sx;
          if (Math.abs(denom) < 1e-7) continue;
          const t = ((s.ax - xA) * sz - (s.az - zA) * sx) / denom;
          const u = ((s.ax - xA) * dz - (s.az - zA) * dx) / denom;
          if (t > 0.02 && t < 0.98 && u >= 0 && u <= 1) {
            const inDoor = s.doors.some(([d0, d1]) => u >= d0 && u <= d1);
            if (inDoor) doors++;
            else walls++;
          }
        }
        return { walls, doors };
      };

      // Helper: multi-stop RGB color ramp
      const sampleRamp = (val, stops) => {
        if (val <= stops[0][0]) return stops[0][1];
        for (let i = 1; i < stops.length; i++) {
          if (val <= stops[i][0]) {
            const t = (val - stops[i - 1][0]) / (stops[i][0] - stops[i - 1][0]);
            const c0 = stops[i - 1][1];
            const c1 = stops[i][1];
            return [
              Math.round(c0[0] + (c1[0] - c0[0]) * t),
              Math.round(c0[1] + (c1[1] - c0[1]) * t),
              Math.round(c0[2] + (c1[2] - c0[2]) * t)
            ];
          }
        }
        return stops[stops.length - 1][1];
      };

      const TEMP_STOPS = [
        [18, [30, 144, 255]],
        [21, [0, 235, 255]],
        [24, [34, 197, 94]],
        [27, [250, 204, 21]],
        [30, [249, 115, 22]],
        [34, [239, 68, 68]]
      ];
      const HUM_STOPS = [
        [25, [245, 158, 11]],
        [42, [34, 197, 94]],
        [52, [0, 235, 255]],
        [62, [59, 130, 246]],
        [75, [168, 85, 247]]
      ];
      const WIFI_STOPS = [
        [-88, [239, 68, 68]],
        [-75, [249, 115, 22]],
        [-65, [250, 204, 21]],
        [-50, [0, 230, 200]],
        [-32, [34, 197, 94]]
      ];

      // 4. Rasterize spatial field to offscreen canvas
      const W = 144;
      const H = 144;
      const canvas = document.createElement("canvas");
      canvas.width = W;
      canvas.height = H;
      const ctx = canvas.getContext("2d");
      const img = ctx.createImageData(W, H);
      const data = img.data;
      const spanX = x1 - x0;
      const spanZ = z1 - z0;

      for (let py = 0; py < H; py++) {
        const wz = z0 + ((py + 0.5) / H) * spanZ;
        for (let px = 0; px < W; px++) {
          const wx = x0 + ((px + 0.5) / W) * spanX;
          let inside = false;
          for (let r = 0; r < roomPolys.length; r++) {
            if (inPoly(wx, wz, roomPolys[r])) { inside = true; break; }
          }
          const idx = (py * W + px) * 4;
          if (!inside) {
            data[idx + 3] = 0;
            continue;
          }

          let rgb;
          if (heatMode === "wifi") {
            if (sources[0]?.measured) {
              // Wall-aware IDW interpolation of measured Wi-Fi Survey RSSI points
              let wSum = 0;
              let vSum = 0;
              for (let s = 0; s < sources.length; s++) {
                const src = sources[s];
                const d = Math.hypot(wx - src.x, wz - src.z);
                const { walls, doors } = countCrossings(wx, wz, src.x, src.z);
                const atten = walls > 0 ? Math.pow(0.08, walls) : (doors > 0 ? 0.55 : 1.0);
                const w = atten / (Math.pow(d, 2.0) + 0.08);
                // Account for wall attenuation & gentle distance falloff away from single points
                const localVal = sources.length === 1
                  ? src.value - 8.0 * Math.log10(Math.max(1.0, d)) - walls * 9.0 - doors * 2.0
                  : src.value - walls * 6.5 - doors * 1.5;
                wSum += w;
                vSum += w * localVal;
              }
              const rssiVal = wSum > 0 ? vSum / wSum : sources[0].value;
              rgb = sampleRamp(rssiVal, WIFI_STOPS);
            } else {
              let bestRssi = -95;
              for (let s = 0; s < sources.length; s++) {
                const src = sources[s];
                const d = Math.max(0.35, Math.hypot(wx - src.x, wz - src.z));
                const { walls, doors } = countCrossings(wx, wz, src.x, src.z);
                const rssi = (src.txPower ?? -30) - 20 * Math.log10(d) - walls * 10.5 - doors * 2.5;
                if (rssi > bestRssi) bestRssi = rssi;
              }
              rgb = sampleRamp(bestRssi, WIFI_STOPS);
            }
          } else {
            let wSum = 0;
            let vSum = 0;
            for (let s = 0; s < sources.length; s++) {
              const src = sources[s];
              const d = Math.hypot(wx - src.x, wz - src.z);
              const { walls, doors } = countCrossings(wx, wz, src.x, src.z);
              const atten = walls > 0 ? Math.pow(0.035, walls) : (doors > 0 ? 0.45 : 1.0);
              const w = atten / (Math.pow(d, 2.2) + 0.06);
              wSum += w;
              vSum += w * src.value;
            }
            const val = wSum > 0 ? vSum / wSum : sources[0].value;
            rgb = sampleRamp(val, heatMode === "humidity" ? HUM_STOPS : TEMP_STOPS);
          }

          data[idx] = rgb[0];
          data[idx + 1] = rgb[1];
          data[idx + 2] = rgb[2];
          data[idx + 3] = 195;
        }
      }

      ctx.putImageData(img, 0, 0);
      if (heatMode === "wifi" && sources[0]?.measured) {
        // Draw crisp RSSI survey spot pins + dBm labels on the heatmap texture
        for (const src of sources) {
          const px = ((src.x - x0) / Math.max(0.01, x1 - x0)) * W;
          const pz = ((src.z - z0) / Math.max(0.01, z1 - z0)) * H;
          ctx.beginPath();
          ctx.arc(px, pz, 4, 0, Math.PI * 2);
          ctx.fillStyle = "#ffffff";
          ctx.fill();
          ctx.lineWidth = 1.5;
          ctx.strokeStyle = "#070b14";
          ctx.stroke();
        }
      }
      return { canvas, x0, x1, z0, z1, count: sources.length };
    },
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
          void fetchSensorHistory(s.identifier);
        }
        pushHassToPanel();
      }
      return dbSensorsCache;
    },
    _lastSqlSync: null,
    getLastSqlSync() {
      return this._lastSqlSync;
    },
    async syncSqlSensors() {
      try {
        const res = await fetch("/api/v1/sensors/sync-sql", {
          method: "POST",
          headers: { "X-CSRF-Token": getCsrfToken() }
        });
        if (res.ok) {
          const data = await res.json().catch(() => null);
          await this.refreshSensorsFromDb();
          pushHassToPanel();
          return data;
        }
      } catch (e) {}
      return null;
    },
    async pushDbSensorReading({ identifier, name, sensor_type, area_id, floor_id, placement_x, placement_z, placement_y, temperature, humidity, power_kw, amperes, volts, data_source_id, sql_query, sql_query_humidity, grafana_link_enabled, grafana_new_tab, grafana_url }) {
      const res = await fetch("/api/v1/sensors/readings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": getCsrfToken()
        },
        body: JSON.stringify({
          identifier,
          ...(name ? { name } : {}),
          ...(sensor_type ? { sensor_type } : {}),
          ...(area_id ? { area_id } : {}),
          ...(floor_id ? { floor_id } : {}),
          ...(placement_x !== undefined && placement_x !== null && placement_x !== "" ? { placement_x: Number(placement_x) } : {}),
          ...(placement_z !== undefined && placement_z !== null && placement_z !== "" ? { placement_z: Number(placement_z) } : {}),
          ...(placement_y !== undefined && placement_y !== null && placement_y !== "" ? { placement_y: Number(placement_y) } : {}),
          ...(data_source_id !== undefined && data_source_id !== null ? { data_source_id: String(data_source_id) } : {}),
          ...(sql_query !== undefined && sql_query !== null ? { sql_query: String(sql_query) } : {}),
          ...(sql_query_humidity !== undefined && sql_query_humidity !== null ? { sql_query_humidity: String(sql_query_humidity) } : {}),
          ...(grafana_link_enabled !== undefined ? { grafana_link_enabled: Boolean(grafana_link_enabled) } : {}),
          ...(grafana_new_tab !== undefined ? { grafana_new_tab: Boolean(grafana_new_tab) } : {}),
          ...(grafana_url !== undefined && grafana_url !== null ? { grafana_url: String(grafana_url) } : {}),
          temperature: temperature !== "" && temperature !== null && temperature !== undefined ? Number(temperature) : null,
          humidity: humidity !== "" && humidity !== null && humidity !== undefined ? Number(humidity) : null,
          power_kw: power_kw !== "" && power_kw !== null && power_kw !== undefined ? Number(power_kw) : null,
          amperes: amperes !== "" && amperes !== null && amperes !== undefined ? Number(amperes) : null,
          volts: volts !== "" && volts !== null && volts !== undefined ? Number(volts) : null
        })
      });
      if (res.ok) {
        const json = await res.json().catch(() => null);
        this._lastSqlSync = json?.sql_sync || null;
        activeSensorIdentifier = identifier;
        if (name) {
          const prevSensor = dbSensorsCache.find(s => s.identifier === identifier);
          const prevName = prevSensor?.name;
          const panel = window.nfPanel;
          const curB = structuredClone(panel?.data?.building || building);
          const linkedEids = new Set([
            `sensor.${identifier}_temp`,
            `sensor.${identifier}_humidity`,
            `sensor.${identifier}_power`,
            `sensor.${identifier}_ampere`,
            `sensor.${identifier}_volt`
          ]);
          const linkedSuffixes = {
            [`sensor.${identifier}_temp`]: "Temp",
            [`sensor.${identifier}_humidity`]: "Humidity",
            [`sensor.${identifier}_power`]: "Power",
            [`sensor.${identifier}_ampere`]: "Current",
            [`sensor.${identifier}_volt`]: "Voltage"
          };
          let renamed3d = false;
          for (const fl of curB.floors || []) {
            for (const p of fl.placements || []) {
              if (p.entity_id && linkedSuffixes[p.entity_id]) {
                const nextLabel = `${name} ${linkedSuffixes[p.entity_id]}`;
                if (p.name !== nextLabel) {
                  p.name = nextLabel;
                  renamed3d = true;
                }
              }
            }
            for (const f of fl.furniture || []) {
              const isMatch =
                f.id === `sensor_unit_${identifier}` ||
                f.id === identifier ||
                (f.entity && linkedEids.has(f.entity)) ||
                (prevName && f.name === prevName && String(f.type || "").includes("thermohygro"));
              if (isMatch && f.name !== name) {
                f.name = name;
                renamed3d = true;
              }
            }
          }
          if (renamed3d) {
            building = curB;
            if (panel && panel.data) panel.data.edit(curB);
            await this.saveBuildingNow(curB);
          }
        }
        await this.refreshSensorsFromDb();
        void fetchSensorHistory(identifier).then(() => pushHassToPanel());
        pushHassToPanel();
        window.nfPanel?.shadowRoot?.querySelector("fp3d-view3d, nf-view3d")?.requestUpdate?.();
      } else {
        this._lastSqlSync = null;
      }
      return res.ok;
    },
    async addAndPlaceSensorIn3D({ name, identifier, sensorType, floorId, areaId, x, z, mountY, temperature, humidity, powerKw, amperes, volts, dataSourceId, sqlQuery, sqlQueryHumidity, grafanaLinkEnabled, grafanaNewTab, grafanaUrl }) {
      const cleanName = (name || "Rack Env Sensor").trim();
      const sType = (sensorType || "thermohygrometer").trim().toLowerCase();
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
        sensor_type: sType,
        area_id: arId,
        floor_id: flId,
        placement_x: px,
        placement_z: pz,
        placement_y: py,
        data_source_id: dataSourceId || null,
        sql_query: sqlQuery || null,
        sql_query_humidity: sqlQueryHumidity || null,
        grafana_link_enabled: Boolean(grafanaLinkEnabled),
        grafana_new_tab: grafanaNewTab !== false,
        grafana_url: grafanaUrl || "",
        temperature: (sType === "thermohygrometer" || sType === "thermometer") ? (temperature ?? 21.5) : null,
        humidity: (sType === "thermohygrometer" || sType === "hygrometer") ? (humidity ?? 45.0) : null,
        power_kw: sType === "power_meter" ? (powerKw !== "" && powerKw !== undefined ? powerKw : 1.5) : null,
        amperes: sType === "ammeter" ? (amperes !== "" && amperes !== undefined ? amperes : 12.0) : null,
        volts: sType === "voltmeter" ? (volts !== "" && volts !== undefined ? volts : 220.0) : null
      });
      if (!ok) return null;

      // 2. Place 3D hardware unit + floating pin(s) matching the selected sensor_type
      const panel = window.nfPanel;
      const curB = structuredClone(panel?.data?.building || building);
      const targetFloor = (curB.floors || []).find(f => f.id === flId) || (curB.floors || [])[0];
      if (targetFloor) {
        targetFloor.placements = targetFloor.placements || [];
        const tempEntityId = `sensor.${cleanIdent}_temp`;
        const humEntityId = `sensor.${cleanIdent}_humidity`;
        const pwrEntityId = `sensor.${cleanIdent}_power`;
        const ampEntityId = `sensor.${cleanIdent}_ampere`;
        const voltEntityId = `sensor.${cleanIdent}_volt`;

        targetFloor.placements = targetFloor.placements.filter(
          p => ![tempEntityId, humEntityId, pwrEntityId, ampEntityId, voltEntityId].includes(p.entity_id)
        );
        if (sType === "thermohygrometer") {
          targetFloor.placements.push({ entity_id: tempEntityId, x: px, z: pz });
          targetFloor.placements.push({ entity_id: humEntityId, x: Math.round((px + 0.35) * 100) / 100, z: pz });
        } else if (sType === "thermometer") {
          targetFloor.placements.push({ entity_id: tempEntityId, x: px, z: pz });
        } else if (sType === "hygrometer") {
          targetFloor.placements.push({ entity_id: humEntityId, x: px, z: pz });
        } else if (sType === "power_meter") {
          targetFloor.placements.push({ entity_id: pwrEntityId, x: px, z: pz });
        } else if (sType === "ammeter") {
          targetFloor.placements.push({ entity_id: ampEntityId, x: px, z: pz });
        } else if (sType === "voltmeter") {
          targetFloor.placements.push({ entity_id: voltEntityId, x: px, z: pz });
        }

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
        activeSensorIdentifier = cleanIdent;
        if (panel && panel.data) {
          panel.data.edit(curB);
        }
        await this.saveBuildingNow(curB);
        pushHassToPanel();
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
        const idsToRemove = [
          `sensor.${identifier}_temp`,
          `sensor.${identifier}_humidity`,
          `sensor.${identifier}_power`,
          `sensor.${identifier}_ampere`,
          `sensor.${identifier}_volt`
        ];
        for (const eid of idsToRemove) {
          delete entitiesMap[eid];
          delete statesMap[eid];
        }
        delete sensorHistoryCache[identifier];
        if (expandedSensorIdentifier === identifier) expandedSensorIdentifier = null;
        if (activeSensorIdentifier === identifier) activeSensorIdentifier = null;

        const panel = window.nfPanel;
        const curB = structuredClone(panel?.data?.building || building);
        for (const fl of curB.floors || []) {
          fl.placements = (fl.placements || []).filter(p => !idsToRemove.includes(p.entity_id));
          fl.furniture = (fl.furniture || []).filter(f => f.id !== `sensor_unit_${identifier}`);
        }
        building = curB;
        if (panel && panel.data) {
          panel.data.edit(curB);
        }
        await this.saveBuildingNow(curB);
        await this.refreshSensorsFromDb();
        pushHassToPanel();
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
    async addVirtualLight({ name, floorId, areaId, x, z, hexColor }) {
      const cleanName = (name || "Room Light").trim();
      const slug = cleanName.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || `light_${Date.now().toString(36)}`;
      const entityId = `light.${slug.slice(0, 48)}`;
      const rgb = hexColor
        ? [parseInt(hexColor.slice(1, 3), 16), parseInt(hexColor.slice(3, 5), 16), parseInt(hexColor.slice(5, 7), 16)]
        : [255, 244, 214];
      const px = Math.round(Number(x || 2.5) * 100) / 100;
      const pz = Math.round(Number(z || 1.5) * 100) / 100;

      entitiesMap[entityId] = { entity_id: entityId, area_id: areaId || "server_room", name: cleanName };
      statesMap[entityId] = {
        entity_id: entityId,
        state: "on",
        attributes: {
          friendly_name: cleanName,
          brightness: 220,
          rgb_color: rgb,
          supported_color_modes: ["rgb"]
        }
      };
      await persistVirtualState(entityId, statesMap[entityId]);

      const panel = window.nfPanel;
      const curB = structuredClone(panel?.data?.building || building);
      const targetFloor = (curB.floors || []).find(f => f.id === floorId) || (curB.floors || [])[0];
      if (targetFloor) {
        targetFloor.placements = (targetFloor.placements || []).filter(p => p.entity_id !== entityId);
        targetFloor.placements.push({ entity_id: entityId, x: px, z: pz });
        const lampId = `lamp_${slug}`;
        targetFloor.furniture = (targetFloor.furniture || []).filter(f => f.id !== lampId && f.entity !== entityId);
        targetFloor.furniture.push({
          id: lampId,
          type: "lamp_ceiling",
          name: cleanName,
          entity: entityId,
          x: px,
          z: pz,
          w: 0.4,
          d: 0.4,
          h: 0.08,
          mount_y: Math.max(2.2, (targetFloor.height || 3.0) - 0.12),
          rotation: 0
        });
        building = curB;
        if (panel && panel.data) panel.data.edit(curB);
        await this.saveBuildingNow(curB);
      }
      pushHassToPanel();
      return entityId;
    },
    async renameVirtualLight(entityId, newName) {
      const cleanName = (newName || "").trim();
      if (!cleanName || !statesMap[entityId]) return false;
      statesMap[entityId] = {
        ...statesMap[entityId],
        attributes: { ...(statesMap[entityId].attributes || {}), friendly_name: cleanName }
      };
      if (entitiesMap[entityId]) entitiesMap[entityId].name = cleanName;
      await persistVirtualState(entityId, statesMap[entityId]);

      const panel = window.nfPanel;
      const curB = structuredClone(panel?.data?.building || building);
      let changed = false;
      for (const fl of curB.floors || []) {
        for (const p of fl.placements || []) {
          if (p.entity_id === entityId && p.name !== cleanName) {
            p.name = cleanName;
            changed = true;
          }
        }
        for (const f of fl.furniture || []) {
          if (f.entity === entityId) {
            f.name = cleanName;
            changed = true;
          }
        }
      }
      if (changed) {
        building = curB;
        if (panel && panel.data) panel.data.edit(curB);
        await this.saveBuildingNow(curB);
      }
      pushHassToPanel();
      return true;
    },
    async deleteVirtualLight(entityId) {
      delete statesMap[entityId];
      delete entitiesMap[entityId];
      try {
        await fetch(`/api/v1/sensors/virtual/states/${encodeURIComponent(entityId)}`, {
          method: "DELETE",
          headers: { "X-CSRF-Token": getCsrfToken() }
        });
      } catch (e) {}
      const panel = window.nfPanel;
      const curB = structuredClone(panel?.data?.building || building);
      for (const fl of curB.floors || []) {
        fl.placements = (fl.placements || []).filter(p => p.entity_id !== entityId);
        fl.furniture = (fl.furniture || []).filter(f => f.entity !== entityId);
      }
      building = curB;
      if (panel && panel.data) panel.data.edit(curB);
      await this.saveBuildingNow(curB);
      pushHassToPanel();
      return true;
    },
    async toggleLayer(layerEntityId) {
      await hass.callService("input_boolean", "toggle", { entity_id: layerEntityId });
    },
    async addCableRunToPlan({ cableType, placementZone, customMountY, floorId, name, x1, z1, x2, z2, points, variant, color, snapToTray, fromEndpoint, toEndpoint }) {
      const panel = window.nfPanel;
      const curB = structuredClone(panel?.data?.building || building);
      const targetFloor = (curB.floors || []).find(f => f.id === floorId) || (curB.floors || [])[0];
      if (!targetFloor) return false;

      let pts = Array.isArray(points) && points.length >= 2
        ? points.map(pt => [Number(pt[0]), Number(pt[1])])
        : [[Number(x1), Number(z1)], [Number(x2), Number(z2)]];

      let mountY = -0.22;
      if (placementZone === "below_floor") mountY = -0.22;
      else if (placementZone === "wall") mountY = 1.25;
      else if (placementZone === "ceiling") mountY = 2.88;
      else if (placementZone === "custom" && Number.isFinite(Number(customMountY))) {
        mountY = Number(customMountY);
      }

      // Optional snapping to nearest placed cable_tray / ladder frame (within 0.65m) or room wall (within 0.35m)
      let snappedTray = false;
      if (snapToTray && cableType !== "tray") {
        const trays = (targetFloor.furniture || []).filter(f => String(f.type || "").includes("cable_tray"));
        const snapPt = (p) => {
          let best = p;
          let bestDist = 0.65;
          for (const tr of trays) {
            const rad = ((Number(tr.rotation || 0)) * Math.PI) / 180;
            const halfW = Number(tr.w || 1) / 2;
            const ax = Number(tr.x) - Math.cos(rad) * halfW;
            const az = Number(tr.z) - Math.sin(rad) * halfW;
            const bx = Number(tr.x) + Math.cos(rad) * halfW;
            const bz = Number(tr.z) + Math.sin(rad) * halfW;
            const vx = bx - ax, vz = bz - az;
            const len2 = vx * vx + vz * vz || 1;
            const t = Math.max(0, Math.min(1, ((p[0] - ax) * vx + (p[1] - az) * vz) / len2));
            const px = ax + t * vx, pz = az + t * vz;
            const d = Math.hypot(p[0] - px, p[1] - pz);
            if (d < bestDist) {
              bestDist = d;
              best = [Math.round(px * 100) / 100, Math.round(pz * 100) / 100];
              if (Number.isFinite(Number(tr.mount_y))) mountY = Number(tr.mount_y);
              snappedTray = true;
            }
          }
          return best;
        };
        pts = pts.map(snapPt);
      }

      const typeMap = {
        power: { type: "pack:dcim.facility:cable_power", layer: "input_boolean.layer_cable_power", d: 0.14, h: 0.06, defaultVariant: "red_hv", defaultColor: "#ef4444" },
        fiber: { type: "pack:dcim.facility:cable_fiber", layer: "input_boolean.layer_cable_fiber", d: 0.12, h: 0.05, defaultVariant: "aqua_om4", defaultColor: "#00e5ff" },
        ethernet: { type: "pack:dcim.facility:cable_ethernet", layer: "input_boolean.layer_cable_ethernet", d: 0.10, h: 0.05, defaultVariant: "blue_cat6a", defaultColor: "#3b82f6" },
        tray: { type: "pack:dcim.facility:cable_tray", layer: "input_boolean.layer_cable_tray", d: 0.45, h: 0.08, defaultVariant: "galvanized", defaultColor: "#94a3b8" }
      };

      const spec = typeMap[cableType] || typeMap.power;
      const chosenColor = (color && /^#[0-9a-fA-F]{3,8}$/.test(String(color).trim())) ? String(color).trim() : spec.defaultColor;
      const groupId = `cable_${cableType}_${Date.now().toString(36)}`;
      let totalLen = 0;
      const segments = [];
      for (let i = 0; i < pts.length - 1; i++) {
        const [ax, az] = pts[i];
        const [bx, bz] = pts[i + 1];
        const dx = bx - ax;
        const dz = bz - az;
        const segLen = Math.max(0.2, Math.round(Math.hypot(dx, dz) * 100) / 100);
        totalLen += segLen;
        const midX = Math.round(((ax + bx) / 2) * 100) / 100;
        const midZ = Math.round(((az + bz) / 2) * 100) / 100;
        const angleDeg = Math.round((Math.atan2(dz, dx) * 180) / Math.PI);
        segments.push({
          id: i === 0 ? groupId : `${groupId}_s${i}`,
          cable_group: groupId,
          cable_points: pts,
          type: spec.type,
          name: "",
          show_name: i === 0,
          x: midX,
          z: midZ,
          w: segLen,
          d: spec.d,
          h: spec.h,
          mount_y: mountY,
          rotation: angleDeg,
          color: chosenColor,
          variant: variant || spec.defaultVariant,
          from_endpoint: fromEndpoint || null,
          to_endpoint: toEndpoint || null,
          snapped_tray: snappedTray,
          show_when: { entity: spec.layer }
        });
      }
      // Include vertical riser drops when linked to rack devices (1U = 0.04445m)
      let verticalDrop = 0;
      if (fromEndpoint?.u_position) {
        const devY = 0.1 + Number(fromEndpoint.u_position) * 0.04445;
        verticalDrop += Math.abs(mountY - devY);
      }
      if (toEndpoint?.u_position) {
        const devY = 0.1 + Number(toEndpoint.u_position) * 0.04445;
        verticalDrop += Math.abs(mountY - devY);
      }
      totalLen = Math.round((totalLen + verticalDrop) * 100) / 100;
      const label = name || `${cableType.toUpperCase()} (${totalLen}m @ ${mountY}m)`;
      for (const seg of segments) {
        seg.name = label;
        seg.total_length_m = totalLen;
      }

      targetFloor.furniture = [...(targetFloor.furniture || []), ...segments];
      building = curB;
      if (panel && panel.data) {
        panel.data.edit(curB);
      }
      await this.saveBuildingNow(curB);
      panel?.shadowRoot?.querySelector("fp3d-editor")?.requestUpdate?.();
      return { id: groupId, name: label, mount_y: mountY, color: chosenColor, length: totalLen, segments: segments.length, snapped_tray: snappedTray };
    },
    getCableRuns() {
      const curB = window.nfPanel?.data?.building || building;
      const groups = new Map();
      for (const fl of curB?.floors || []) {
        for (const f of fl.furniture || []) {
          if (!String(f.type || "").includes("cable_")) continue;
          const gid = f.cable_group || f.id;
          if (!groups.has(gid)) {
            groups.set(gid, {
              id: gid,
              floorId: fl.id,
              name: f.name || gid,
              type: String(f.type).split(":").pop(),
              mount_y: f.mount_y ?? 0,
              color: f.color || (String(f.type).includes("fiber") ? "#00e5ff" : String(f.type).includes("ethernet") ? "#3b82f6" : String(f.type).includes("tray") ? "#94a3b8" : "#ef4444"),
              points: Array.isArray(f.cable_points) ? f.cable_points : null,
              from_endpoint: f.from_endpoint || null,
              to_endpoint: f.to_endpoint || null,
              layer: f.show_when?.entity || null,
              length: f.total_length_m ? Number(f.total_length_m) : 0,
              _computedLen: 0,
              segments: 0
            });
          }
          const g = groups.get(gid);
          g._computedLen = Math.round((g._computedLen + Number(f.w || 0)) * 100) / 100;
          if (!g.length) g.length = g._computedLen;
          g.segments += 1;
        }
      }
      return [...groups.values()];
    },
    async updateCableRun(groupId, { name, mountY, color }) {
      const panel = window.nfPanel;
      const curB = structuredClone(panel?.data?.building || building);
      let changed = false;
      for (const fl of curB.floors || []) {
        for (const f of fl.furniture || []) {
          if ((f.cable_group || f.id) === groupId) {
            if (name !== undefined && name.trim()) f.name = name.trim();
            if (mountY !== undefined && mountY !== "" && Number.isFinite(Number(mountY))) f.mount_y = Number(mountY);
            if (color && /^#[0-9a-fA-F]{3,8}$/.test(String(color).trim())) f.color = String(color).trim();
            changed = true;
          }
        }
      }
      if (changed) {
        building = curB;
        if (panel && panel.data) panel.data.edit(curB);
        await this.saveBuildingNow(curB);
        panel?.shadowRoot?.querySelector("fp3d-editor")?.requestUpdate?.();
      }
      return changed;
    },
    async deleteCableRun(groupId) {
      const panel = window.nfPanel;
      const curB = structuredClone(panel?.data?.building || building);
      for (const fl of curB.floors || []) {
        fl.furniture = (fl.furniture || []).filter(f => (f.cable_group || f.id) !== groupId);
      }
      building = curB;
      if (panel && panel.data) panel.data.edit(curB);
      await this.saveBuildingNow(curB);
      return true;
    },
    getObjectRegistry() {
      return EXTRA_OBJECT_REGISTRY;
    },
    getSelectedObject() {
      return selectedObject;
    },
    setSelectedObject(sel) {
      selectedObject = sel || null;
      if (sel?.kind === "sensor" && sel?.id) {
        activeSensorIdentifier = sel.id;
        expandedSensorIdentifier = sel.id;
      }
      const panel = window.nfPanel;
      const ed = panel?.shadowRoot?.querySelector("fp3d-editor");
      if (ed) {
        if (sel?.kind === "furniture" && sel.id) ed._furnitureId = sel.id;
        ed.requestUpdate?.();
      }
      const v3d = panel?.shadowRoot?.querySelector("fp3d-view3d, nf-view3d");
      if (v3d) {
        if (sel?.kind === "furniture") v3d.selectedFurniture = sel.id;
        v3d.requestUpdate?.();
      }
      window.dispatchEvent(new CustomEvent("monits-selection-changed", { detail: selectedObject }));
    },
    getWifiSurveyPoints() {
      return wifiSurveyPointsCache;
    },
    getFilteredWifiPoints(floorId = null) {
      return wifiSurveyPointsCache.filter(p => {
        if (floorId && (p.floor_id || "ground") !== floorId) return false;
        if (selectedWifiSsid && p.ssid !== selectedWifiSsid) return false;
        if (selectedWifiBand && normalizeBandClient(p.band, p.channel) !== selectedWifiBand) return false;
        if (selectedWifiChannel !== null && Number(p.channel) !== Number(selectedWifiChannel)) return false;
        return true;
      });
    },
    getWifiSsids() {
      return wifiSsidsCache;
    },
    getWifiApOptions() {
      // Combine surveyed APs (with observed bands/channels) + placed wifi_ap furniture in building
      const bySsid = new Map();
      for (const ap of wifiApsCache) {
        bySsid.set(ap.ssid, {
          ssid: ap.ssid,
          bands: new Set(ap.bands || []),
          channels: new Set(ap.channels || []),
          count: ap.count || 0
        });
      }
      const curB = window.nfPanel?.data?.building || building;
      for (const fl of curB?.floors || []) {
        for (const f of fl.furniture || []) {
          const t = String(f.type || "").toLowerCase();
          if (t.includes("wifi") || t.includes("router") || t.endsWith(":ap")) {
            const name = (f.name || f.id || "Wi-Fi AP").trim();
            const rec = bySsid.get(name) || { ssid: name, bands: new Set(), channels: new Set(), count: 0 };
            if (Array.isArray(f.bands)) f.bands.forEach(b => rec.bands.add(normalizeBandClient(b)));
            else if (f.band) rec.bands.add(normalizeBandClient(f.band, f.channel));
            else if (!rec.bands.size) { rec.bands.add("2.4GHz"); rec.bands.add("5GHz"); }
            if (f.channel) rec.channels.add(Number(f.channel));
            bySsid.set(name, rec);
          }
        }
      }
      const bandOrder = { "2.4GHz": 0, "5GHz": 1, "6GHz": 2, "N/A": 3 };
      return [...bySsid.values()]
        .sort((a, b) => a.ssid.localeCompare(b.ssid))
        .map(rec => {
          const bands = [...rec.bands].filter(b => b !== "N/A").sort((a, b) => (bandOrder[a] ?? 9) - (bandOrder[b] ?? 9));
          const channels = [...rec.channels].filter(c => Number.isFinite(c)).sort((a, b) => a - b);
          const bandStr = bands.length ? bands.map(b => b.replace("GHz", " GHz")).join(" / ") : "N/A";
          const chStr = channels.length ? ` ch${channels.join(",")}` : "";
          return {
            ssid: rec.ssid,
            bands,
            channels,
            count: rec.count,
            label: `${rec.ssid} — ${bandStr}${chStr}`
          };
        });
    },
    getWifiBandChannelOptions() {
      const bands = new Set(["2.4GHz", "5GHz", "6GHz", ...wifiBandsCache]);
      const channels = new Set(wifiChannelsCache);
      for (const p of wifiSurveyPointsCache) {
        if (p.band && p.band !== "N/A") bands.add(normalizeBandClient(p.band, p.channel));
        if (p.channel !== null && p.channel !== undefined) channels.add(Number(p.channel));
      }
      return {
        bands: ["2.4GHz", "5GHz", "6GHz"].filter(b => bands.has(b)),
        channels: [...channels].filter(c => Number.isFinite(c)).sort((a, b) => a - b)
      };
    },
    getSelectedWifiSsid() {
      return selectedWifiSsid;
    },
    getSelectedWifiBandChannel() {
      if (selectedWifiChannel !== null) return `ch:${selectedWifiChannel}`;
      if (selectedWifiBand) return `band:${selectedWifiBand}`;
      return "";
    },
    setSelectedWifiSsid(ssid) {
      selectedWifiSsid = ssid || "";
      const panel = window.nfPanel;
      const v3d = panel?.shadowRoot?.querySelector("fp3d-view3d, nf-view3d");
      if (v3d && v3d.heatMode === "wifi") v3d.applyTint?.();
      panel?.shadowRoot?.querySelector("fp3d-editor")?.requestUpdate?.();
      window.dispatchEvent(new CustomEvent("monits-wifi-survey-changed"));
    },
    setWifiBandChannelFilter(val) {
      const raw = String(val || "");
      selectedWifiBand = "";
      selectedWifiChannel = null;
      if (raw.startsWith("band:")) {
        selectedWifiBand = normalizeBandClient(raw.slice(5));
      } else if (raw.startsWith("ch:")) {
        const n = Number(raw.slice(3));
        if (Number.isFinite(n)) selectedWifiChannel = n;
      }
      const panel = window.nfPanel;
      const v3d = panel?.shadowRoot?.querySelector("fp3d-view3d, nf-view3d");
      if (v3d && v3d.heatMode === "wifi") v3d.applyTint?.();
      panel?.shadowRoot?.querySelector("fp3d-editor")?.requestUpdate?.();
      window.dispatchEvent(new CustomEvent("monits-wifi-survey-changed"));
    },
    async refreshWifiSurveyFromDb() {
      await loadWifiSurveyFromDb();
      const panel = window.nfPanel;
      const v3d = panel?.shadowRoot?.querySelector("fp3d-view3d, nf-view3d");
      if (v3d && v3d.heatMode === "wifi") v3d.applyTint?.();
      panel?.shadowRoot?.querySelector("fp3d-editor")?.requestUpdate?.();
      window.dispatchEvent(new CustomEvent("monits-wifi-survey-changed"));
      return { points: wifiSurveyPointsCache, ssids: wifiSsidsCache, aps: wifiApsCache };
    },
    async addWifiSurveyPoint({ ssid, bssid, band, channel, rssi_dbm, floor_id, x, z, y, notes }) {
      const res = await fetch("/api/v1/wifi-survey", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrfToken() },
        body: JSON.stringify({
          ssid,
          ...(bssid ? { bssid } : {}),
          band: normalizeBandClient(band, channel),
          ...(channel !== undefined && channel !== null && channel !== "" ? { channel: Number(channel) } : {}),
          rssi_dbm: Number(rssi_dbm),
          floor_id: floor_id || "ground",
          x: Number(x),
          z: Number(z),
          y: Number(y ?? 1.2),
          ...(notes ? { notes } : {})
        })
      });
      if (res.ok) {
        const created = await res.json();
        await this.refreshWifiSurveyFromDb();
        return created;
      }
      return null;
    },
    async updateWifiSurveyPoint(pointId, { ssid, band, channel, rssi_dbm, x, z }) {
      const res = await fetch(`/api/v1/wifi-survey/${encodeURIComponent(pointId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrfToken() },
        body: JSON.stringify({
          ...(ssid ? { ssid } : {}),
          ...(band ? { band: normalizeBandClient(band, channel) } : {}),
          ...(channel !== undefined && channel !== null && channel !== "" ? { channel: Number(channel) } : {}),
          ...(rssi_dbm !== undefined && rssi_dbm !== "" ? { rssi_dbm: Number(rssi_dbm) } : {}),
          ...(x !== undefined && x !== "" ? { x: Number(x) } : {}),
          ...(z !== undefined && z !== "" ? { z: Number(z) } : {})
        })
      });
      if (res.ok) {
        await this.refreshWifiSurveyFromDb();
        return true;
      }
      return false;
    },
    async deleteWifiSurveyPoint(pointId) {
      const res = await fetch(`/api/v1/wifi-survey/${encodeURIComponent(pointId)}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": getCsrfToken() }
      });
      if (res.ok) {
        await this.refreshWifiSurveyFromDb();
        return true;
      }
      return false;
    },
    async importWifiSurvey(format, data, replace = false) {
      const res = await fetch("/api/v1/wifi-survey/import", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrfToken() },
        body: JSON.stringify({ format, data, replace })
      });
      if (res.ok) {
        await this.refreshWifiSurveyFromDb();
        return await res.json();
      }
      return null;
    },
    getRacks() {
      return racksCache;
    },
    getRackByFurnitureId(fid) {
      if (!fid) return null;
      return racksCache.find(r => r.furniture_id === fid || r.id === fid) || null;
    },
    async refreshRacksFromDb() {
      try {
        const res = await fetch("/api/v1/racks");
        if (res.ok) {
          const data = await res.json();
          racksCache = Array.isArray(data.racks) ? data.racks : [];
        }
        // Reload synchronized building JSON so newly created/updated racks appear immediately in 2D & 3D
        const bRes = await fetch("/api/v1/sensors/building");
        if (bRes.ok) {
          const bData = await bRes.json();
          if (bData?.saved && bData.building?.floors?.length) {
            building = bData.building;
            syncRoomsToAreas(building);
            const panel = window.nfPanel;
            if (panel?.data?.edit) {
              panel.data.building = building;
              panel.requestUpdate?.();
            }
            panel?.shadowRoot?.querySelector("fp3d-view3d, nf-view3d")?.requestUpdate?.();
            panel?.shadowRoot?.querySelector("fp3d-editor")?.requestUpdate?.();
          }
        }
      } catch (e) {}
      window.dispatchEvent(new CustomEvent("monits-racks-changed", { detail: racksCache }));
      return racksCache;
    }
  };
  void window.monitsApi.refreshRacksFromDb();

  // Sync shared theme state into hass + Neon3D panel instantly on theme toggle
  window.addEventListener("monits-theme-changed", (ev) => {
    const isLight = ev?.detail?.theme === "light";
    hass.selectedTheme = { dark: !isLight };
    hass.themes = { darkMode: !isLight };
    const panel = window.nfPanel;
    if (panel) {
      const targetStyle = isLight ? "day" : "neon";
      if (panel._theme !== targetStyle) {
        panel._theme = targetStyle;
      }
      const v3d = panel.shadowRoot?.querySelector("fp3d-view3d, nf-view3d");
      if (v3d) {
        v3d.theme = targetStyle;
        v3d.requestUpdate?.();
      }
      panel.requestUpdate?.();
    }
    pushHassToPanel();
  });

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
          const idx = dbSensorsCache.findIndex(s => s.identifier === ident);
          const updatedSensor = {
            ...(idx >= 0 ? dbSensorsCache[idx] : {}),
            identifier: ident,
            name: data.sensor_name || (idx >= 0 ? dbSensorsCache[idx].name : ident),
            area_id: data.area_id || (idx >= 0 ? dbSensorsCache[idx].area_id : "server_alpha"),
            floor_id: data.floor_id || (idx >= 0 ? dbSensorsCache[idx].floor_id : "ground"),
            placement_x: data.placement_x ?? (idx >= 0 ? dbSensorsCache[idx].placement_x : null),
            placement_z: data.placement_z ?? (idx >= 0 ? dbSensorsCache[idx].placement_z : null),
            placement_y: data.placement_y ?? (idx >= 0 ? dbSensorsCache[idx].placement_y : null),
            current_temperature: data.temperature,
            current_humidity: data.humidity,
            power_kw: data.power_kw ?? (idx >= 0 ? dbSensorsCache[idx].power_kw : null),
            status: data.status || "online"
          };
          if (idx >= 0) dbSensorsCache[idx] = updatedSensor;
          else dbSensorsCache.push(updatedSensor);

          applyDbSensorToState(updatedSensor);
          void fetchSensorHistory(ident).then(() => pushHassToPanel());
          pushHassToPanel();
        } else if (data.type === "virtual_state" && data.entity_id) {
          const prev = statesMap[data.entity_id] || { entity_id: data.entity_id, state: "off", attributes: {} };
          statesMap[data.entity_id] = {
            ...prev,
            state: data.state,
            attributes: { ...prev.attributes, ...(data.attributes || {}) }
          };
          pushHassToPanel();
        } else if (data.type === "wifi_survey_updated") {
          void window.monitsApi?.refreshWifiSurveyFromDb?.();
        } else if (data.type === "rack_updated") {
          void window.monitsApi?.refreshRacksFromDb?.();
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
