// Server_Monits - Enterprise Data Center Facility Model (English & Indonesian)

const rect = (id, name, area_id, x0, z0, x1, z1, floor_material = "concrete") => ({
  id,
  name,
  area_id,
  points: [
    [x0, z0],
    [x1, z0],
    [x1, z1],
    [x0, z1],
  ],
  floor_material,
});

const floor = (id, name, elevation, rooms) => ({
  id,
  name,
  elevation,
  height: 3.5,
  cut_height: 1.2,
  rooms,
  openings: [],
  furniture: [],
  placements: [],
  background: null,
});

export function getFacilityData(lang = "en") {
  const isId = lang.toLowerCase().startsWith("id");

  const floors_def = isId ? {
    ground: { floor_id: "ground", name: "Lantai Dasar", level: 0 },
    first: { floor_id: "first", name: "Lantai 1", level: 1 },
  } : {
    ground: { floor_id: "ground", name: "Ground Floor", level: 0 },
    first: { floor_id: "first", name: "First Floor", level: 1 },
  };

  const areas_def = isId ? {
    server_alpha: { area_id: "server_alpha", name: "Ruang Server Alpha", floor_id: "ground" },
    noc: { area_id: "noc", name: "Pusat Operasi NOC", floor_id: "ground" },
    ups: { area_id: "ups", name: "Ruang Daya & UPS", floor_id: "ground" },
    battery: { area_id: "battery", name: "Ruang Baterai", floor_id: "ground" },
    meet_me: { area_id: "meet_me", name: "Ruang Meet-Me", floor_id: "ground" },
    server_beta: { area_id: "server_beta", name: "Ruang Server Beta", floor_id: "first" },
    network_core: { area_id: "network_core", name: "Ruang Inti Jaringan", floor_id: "first" },
    security: { area_id: "security", name: "Pusat Keamanan & Akses", floor_id: "first" },
  } : {
    server_alpha: { area_id: "server_alpha", name: "Server Room Alpha", floor_id: "ground" },
    noc: { area_id: "noc", name: "NOC Operations Center", floor_id: "ground" },
    ups: { area_id: "ups", name: "UPS & Power Room", floor_id: "ground" },
    battery: { area_id: "battery", name: "Battery Storage Room", floor_id: "ground" },
    meet_me: { area_id: "meet_me", name: "Telecom Meet-Me Room", floor_id: "ground" },
    server_beta: { area_id: "server_beta", name: "Server Room Beta", floor_id: "first" },
    network_core: { area_id: "network_core", name: "Network Core Room", floor_id: "first" },
    security: { area_id: "security", name: "Security & Access Center", floor_id: "first" },
  };

  const building_def = {
    version: 1,
    settings: { wall_exterior: 0.25, wall_interior: 0.15, grid: 0.1 },
    floors: [
      floor("ground", floors_def.ground.name, 0, [
        rect("room_server_a", areas_def.server_alpha.name, "server_alpha", 0, 0, 10, 8, "tiles"),
        rect("room_noc", areas_def.noc.name, "noc", 10, 0, 16, 5, "oak"),
        rect("room_ups", areas_def.ups.name, "ups", 10, 5, 16, 8, "concrete"),
        rect("room_battery", areas_def.battery.name, "battery", 0, 8, 6, 12, "concrete"),
        rect("room_meet_me", areas_def.meet_me.name, "meet_me", 6, 8, 16, 12, "tiles"),
      ]),
      floor("first", floors_def.first.name, 3.5, [
        rect("room_server_b", areas_def.server_beta.name, "server_beta", 0, 0, 10, 8, "tiles"),
        rect("room_network_core", areas_def.network_core.name, "network_core", 10, 0, 16, 6, "tiles"),
        rect("room_security", areas_def.security.name, "security", 0, 8, 16, 12, "oak"),
      ]),
    ],
  };

  return { floors: floors_def, areas: areas_def, building: building_def };
}

const defaultData = getFacilityData("en");
export const DEMO_FLOORS = defaultData.floors;
export const DEMO_AREAS = defaultData.areas;
export const DEMO_BUILDING = defaultData.building;

export const DEMO_PACK = {
  format: "fp3dpack",
  version: 1,
  id: "dcim.facility",
  name: "Data Center Infrastructure",
  publisher: "Server_Monits",
  licensee: null,
  features: ["camera_cockpit", "weather", "energy_pro", "floor_stack", "heatmaps"],
  items: [],
};

export const DEMO_ENTITIES = {
  "sensor.rack_temp_alpha": { entity_id: "sensor.rack_temp_alpha", name: "Rack Alpha Temp", device_class: "temperature" },
  "sensor.rack_humidity_alpha": { entity_id: "sensor.rack_humidity_alpha", name: "Rack Alpha Humidity", device_class: "humidity" },
  "sensor.ups_load": { entity_id: "sensor.ups_load", name: "UPS Primary Load", device_class: "power" },
  "sensor.crac_temperature": { entity_id: "sensor.crac_temperature", name: "CRAC Cold Aisle Temp", device_class: "temperature" },
};

export const DEMO_STATES = {
  "sensor.rack_temp_alpha": {
    entity_id: "sensor.rack_temp_alpha",
    state: "22.5",
    attributes: { unit_of_measurement: "°C", friendly_name: "Rack Alpha Temperature", status: "online" }
  },
  "sensor.rack_humidity_alpha": {
    entity_id: "sensor.rack_humidity_alpha",
    state: "45.0",
    attributes: { unit_of_measurement: "%", friendly_name: "Rack Alpha Humidity", status: "online" }
  },
  "sensor.ups_load": {
    entity_id: "sensor.ups_load",
    state: "68.4",
    attributes: { unit_of_measurement: "kW", friendly_name: "UPS Load Capacity", status: "online" }
  },
  "sensor.crac_temperature": {
    entity_id: "sensor.crac_temperature",
    state: "19.8",
    attributes: { unit_of_measurement: "°C", friendly_name: "CRAC Supply Air", status: "online" }
  },
};

export const DEMO_PICTURES = {};
