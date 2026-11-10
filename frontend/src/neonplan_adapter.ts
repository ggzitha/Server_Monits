// Server_Monits Adapter for NeonPlan 3D Engine
import {
  DEMO_AREAS,
  DEMO_BUILDING,
  DEMO_FLOORS,
  DEMO_PACK,
  DEMO_ENTITIES,
  DEMO_STATES,
  DEMO_PICTURES,
  DEMO_PLANS
} from "/static/neonplan3d/demo-data.js";
import { demoHistory } from "/static/neonplan3d/demo-history.js";

function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta && meta.content) return meta.content;
  const match = document.cookie.match(/csrf_token=([^;]+)/);
  return match ? match[1] : '';
}

export async function createMonitsHass(options = {}) {
  const listeners = new Map();
  let building = structuredClone(DEMO_BUILDING);
  let revision = 1;
  const plans = structuredClone(DEMO_PLANS);
  const planTrash = [];
  let mainEntry = { id: "main", name: "Main Facility", icon: "server", site: "Datacenter A", created: Date.now() / 1000 };
  let locatePlan = "main";

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

  const sizeOf = (b) => ({
    floors: b?.floors?.length ?? 0,
    rooms: b?.floors?.reduce((n, f) => n + (f.rooms?.length ?? 0), 0) ?? 0,
    furniture: b?.floors?.reduce((n, f) => n + (f.furniture?.length ?? 0), 0) ?? 0
  });

  const planList = () => ({
    plans: [
      { ...mainEntry, revision, ...sizeOf(building) },
      ...plans.map(({ building: b, ...e }) => ({ ...e, ...sizeOf(b) }))
    ],
    trash: planTrash.map(({ building: b, ...e }) => ({ ...e, ...sizeOf(b) })),
    locate_plan: locatePlan
  });

  const notifyPlans = () => {
    for (const [cb, m] of listeners) {
      if (m?.type === "neonplan3d/plans/subscribe") cb(planList());
    }
  };

  const notifyBuilding = (plan, rev) => {
    for (const [cb, m] of listeners) {
      if (m?.type !== "neonplan3d/plans/subscribe" && ((m?.plan ?? "main") === plan || m?.plan === "*")) {
        cb({ revision: rev, plan });
      }
    }
  };

  const history = [{ id: "s0", revision: 0, saved_at: Date.now() / 1000 - 3600, building: structuredClone(building) }];
  let license = {
    instance: "server_monits_dcim",
    active: true,
    key_hint: "…DCIM",
    licensee: "Server_Monits Enterprise",
    checked_at: Date.now() / 1000,
    error: null,
    shop_url: null,
    packs: [
      { id: "dcim.core", name: "Data Center Infrastructure", release: 1, url: null, installed: 1 },
      { id: "mastershort.living", name: "Living", release: 2, url: null, installed: 1 },
      { id: "mastershort.kitchen", name: "Kitchen", release: 1, url: null, installed: 1 }
    ],
    offers: [],
    loyalty: null,
    supporter: { code: "SM-PRO", until: "2099-12-31" },
    newsletter: null,
    updates: []
  };

  const hass = {
    language: options.lang || document.documentElement.lang || "en",
    user: {
      is_admin: options.isAdmin !== undefined ? options.isAdmin : true,
      name: options.username || "Admin"
    },
    areas: DEMO_AREAS,
    floors: DEMO_FLOORS,
    entities: DEMO_ENTITIES,
    devices: {},
    config: { latitude: 0, longitude: 0 },
    states: structuredClone(DEMO_STATES),
    connection: {
      async subscribeMessage(cb, msg) {
        listeners.set(cb, msg);
        return async () => listeners.delete(cb);
      }
    },
    async callApi(method, path) {
      return [];
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
      if (window.fp3dPanel) window.fp3dPanel.requestUpdate();
    },
    async callWS(msg) {
      switch (msg.type) {
        case "neonplan3d/screens/list":
          return { screens: [] };
        case "neonplan3d/screens/reload":
          return { sent: true };
        case "neonplan3d/building/get":
          return { building: structuredClone(building), revision };
        case "neonplan3d/building/save": {
          building = structuredClone(msg.building);
          revision += 1;
          notifyBuilding("main", revision);

          // Persist to Server_Monits API asynchronously
          try {
            await fetch("/api/v1/plans", {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
              },
              body: JSON.stringify({
                name: mainEntry.name || "Main Facility",
                site_name: mainEntry.site || "Datacenter",
                metadata_json: building
              })
            });
          } catch (e) {
            console.warn("Async save to API skipped/failed:", e);
          }

          return { revision };
        }
        case "neonplan3d/plans/list":
          return planList();
        case "neonplan3d/plans/create": {
          const id = `p_${Math.random().toString(36).slice(2, 10)}`;
          plans.push({
            id,
            name: msg.name,
            icon: msg.icon ?? null,
            site: null,
            created: Date.now() / 1000,
            revision: 1,
            building: structuredClone(msg.building ?? { version: 1, floors: [], settings: { wall_exterior: 0.24, wall_interior: 0.12, grid: 0.05 } })
          });
          notifyPlans();
          return { plan: id };
        }
        case "neonplan3d/plans/update": {
          const entry = msg.plan === "main" ? mainEntry : plans.find((pl) => pl.id === msg.plan);
          if (entry) {
            for (const k of ["name", "icon", "site"]) if (k in msg) entry[k] = msg[k];
          }
          notifyPlans();
          return null;
        }
        case "neonplan3d/plans/delete": {
          const i = plans.findIndex((pl) => pl.id === msg.plan);
          if (i >= 0) {
            planTrash.push({ ...plans[i], deleted_at: Date.now() / 1000 });
            plans.splice(i, 1);
            notifyPlans();
          }
          return null;
        }
        case "neonplan3d/plans/locate":
          locatePlan = msg.plan;
          notifyPlans();
          return null;
        case "neonplan3d/diagnostics/client":
          return { enabled: false };
        case "neonplan3d/history/list":
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
        case "neonplan3d/history/snapshot":
          history.push({ id: `s${history.length + 1}`, revision, saved_at: Date.now() / 1000, building: structuredClone(building) });
          return null;
        case "neonplan3d/history/restore": {
          const snap = history.find((h) => h.id === msg.snapshot_id);
          if (snap) {
            building = structuredClone(snap.building);
            revision += 1;
            notifyBuilding("main", revision);
          }
          return { revision };
        }
        case "neonplan3d/packs/list":
          return { packs: [DEMO_PACK] };
        case "neonplan3d/license/get":
          return license;
        case "recorder/statistics_during_period":
          return {};
        case "neonplan3d/timetravel/history":
          return demoHistory(msg, hass.states);
        case "history/history_during_period":
          return {};
        default:
          return {};
      }
    }
  };

  // Setup WebSocket connection to /ws/live for live telemetry
  try {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/live`;
    const ws = new WebSocket(wsUrl);

    ws.onerror = () => {
      // Quiet fallback when WebSocket server is offline or proxy is closing
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
          if (window.fp3dPanel) window.fp3dPanel.requestUpdate();
        }
      } catch (e) {
        // Ignore non-json ws frames
      }
    };
  } catch (err) {
    console.warn("WebSocket live link optional/deferred:", err);
  }

  return hass;
}
