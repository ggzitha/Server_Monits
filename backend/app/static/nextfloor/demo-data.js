// Enterprise Data Center 3D Model, Virtual Devices, DB Sensors & Multi-Elevation Cabling
// Strictly English (EN) and Indonesian (ID) — Zero German, 100% Detached from Home Assistant.

export const DEMO_PACK = {
  format: "fp3dpack",
  version: 1,
  id: "dcim.facility",
  name: "Data Center Infrastructure & Cabling",
  publisher: "Server_Monits",
  builtin: true,
  licensee: "Enterprise Pro",
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
  items: [
    {
      id: "rack_42u",
      name: { en: "42U Server Rack Cabinet", id: "Kabinet Rak Server 42U" },
      size: [0.6, 1.0, 2.0],
      mount: "floor",
      electric: true,
      colors: [
        { id: "obsidian", name: { en: "Obsidian Black", id: "Hitam Obsidian" }, hex: "#161d2a" },
        { id: "slate", name: { en: " Enterprise Slate", id: "Abu-abu Slate" }, hex: "#263248" }
      ],
      parts: [
        { shape: "box", x: 0, z: 0, w: 1, d: 1, y: 0, h: 1, color: "#161d2a", paint: true, edges: "glow" },
        { shape: "box", x: 0, z: 0.49, w: 0.86, d: 0.03, y: 0.12, h: 0.08, color: "#00f0ff", glow: true },
        { shape: "box", x: 0, z: 0.49, w: 0.86, d: 0.03, y: 0.28, h: 0.08, color: "#00f0ff", glow: true },
        { shape: "box", x: 0, z: 0.49, w: 0.86, d: 0.03, y: 0.44, h: 0.08, color: "#22c55e", glow: true },
        { shape: "box", x: 0, z: 0.49, w: 0.86, d: 0.03, y: 0.60, h: 0.08, color: "#00f0ff", glow: true },
        { shape: "box", x: 0, z: 0.49, w: 0.86, d: 0.03, y: 0.76, h: 0.08, color: "#38bdf8", glow: true }
      ],
      symbol: [
        { shape: "rect", x: 0, z: 0, w: 1, d: 1, fill: true },
        { shape: "line", x1: -0.4, z1: 0.35, x2: 0.4, z2: 0.35 }
      ]
    },
    {
      id: "rack_24u",
      name: { en: "24U Network & Patch Rack", id: "Rak Jaringan & Patch 24U" },
      size: [0.6, 0.8, 1.25],
      mount: "floor",
      electric: true,
      parts: [
        { shape: "box", x: 0, z: 0, w: 1, d: 1, y: 0, h: 1, color: "#1e293b", edges: "glow" },
        { shape: "box", x: 0, z: 0.49, w: 0.84, d: 0.03, y: 0.25, h: 0.12, color: "#38bdf8", glow: true },
        { shape: "box", x: 0, z: 0.49, w: 0.84, d: 0.03, y: 0.55, h: 0.12, color: "#22c55e", glow: true }
      ],
      symbol: [{ shape: "rect", x: 0, z: 0, w: 1, d: 1, fill: true }]
    },
    {
      id: "crac_unit",
      name: { en: "CRAC Precision Cooling Unit", id: "Unit Pendingin Presisi CRAC" },
      size: [0.9, 0.9, 1.95],
      mount: "floor",
      electric: true,
      climate: true,
      parts: [
        { shape: "box", x: 0, z: 0, w: 1, d: 1, y: 0, h: 1, color: "#1e3a5f", edges: "glow" },
        { shape: "box", x: 0, z: 0.49, w: 0.75, d: 0.03, y: 0.65, h: 0.22, color: "#00f0ff", glow: true }
      ],
      symbol: [
        { shape: "rect", x: 0, z: 0, w: 1, d: 1, fill: true },
        { shape: "circle", x: 0, z: 0, r: 0.32 }
      ]
    },
    {
      id: "ups_cabinet",
      name: { en: "Modular UPS & Battery Bank", id: "Kabinet UPS Modular & Baterai" },
      size: [0.8, 0.9, 1.9],
      mount: "floor",
      electric: true,
      parts: [
        { shape: "box", x: 0, z: 0, w: 1, d: 1, y: 0, h: 1, color: "#27272a", edges: "glow" },
        { shape: "box", x: 0, z: 0.49, w: 0.7, d: 0.03, y: 0.7, h: 0.12, color: "#f59e0b", glow: true }
      ],
      symbol: [{ shape: "rect", x: 0, z: 0, w: 1, d: 1, fill: true }]
    },
    {
      id: "cable_tray",
      name: { en: "Cable Tray / Ladder Frame", id: "Tray Kabel / Ladder Frame" },
      size: [2.0, 0.45, 0.08],
      mount: "ceiling",
      stretch: true,
      colors: [
        { id: "galvanized", name: { en: "Steel Tray", id: "Tray Baja" }, hex: "#475569" },
        { id: "yellow", name: { en: "Fiber Runner Yellow", id: "Kuning Jalur FO" }, hex: "#eab308" }
      ],
      parts: [
        { shape: "box", x: 0, z: -0.44, w: 1, d: 0.12, y: 0, h: 1, color: "#475569", paint: true, edges: "glow" },
        { shape: "box", x: 0, z: 0.44, w: 1, d: 0.12, y: 0, h: 1, color: "#475569", paint: true, edges: "glow" },
        { shape: "box", x: 0, z: 0, w: 1, d: 0.88, y: 0, h: 0.25, color: "#334155", paint: true, edges: true }
      ],
      symbol: [
        { shape: "rect", x: 0, z: 0, w: 1, d: 1 },
        { shape: "line", x1: -0.5, z1: 0, x2: 0.5, z2: 0 }
      ]
    },
    {
      id: "cable_power",
      name: { en: "Electric / Power Cable Run", id: "Jalur Kabel Listrik / Power" },
      size: [2.0, 0.12, 0.06],
      mount: "floor",
      stretch: true,
      electric: true,
      colors: [
        { id: "red_hv", name: { en: "Red Primary Power", id: "Merah Listrik Utama" }, hex: "#ef4444" },
        { id: "amber_ups", name: { en: "Amber UPS Feed", id: "Kuning Daya UPS" }, hex: "#f59e0b" },
        { id: "orange_pdu", name: { en: "Orange PDU Branch", id: "Oranye Cabang PDU" }, hex: "#f97316" }
      ],
      parts: [
        { shape: "box", x: 0, z: 0, w: 1, d: 1, y: 0, h: 1, color: "#ef4444", paint: true, glow: true, edges: "glow" }
      ],
      symbol: [
        { shape: "rect", x: 0, z: 0, w: 1, d: 1, fill: true }
      ]
    },
    {
      id: "cable_fiber",
      name: { en: "Fiber Optic (FO) Cable Run", id: "Jalur Kabel Fiber Optik (FO)" },
      size: [2.0, 0.10, 0.05],
      mount: "ceiling",
      stretch: true,
      colors: [
        { id: "aqua_om4", name: { en: "Aqua OM4 Multimode FO", id: "Biru Muda FO OM4" }, hex: "#00f0ff" },
        { id: "yellow_os2", name: { en: "Yellow OS2 Singlemode FO", id: "Kuning FO OS2" }, hex: "#facc15" },
        { id: "violet_om5", name: { en: "Violet OM5 Backbone FO", id: "Ungu FO OM5" }, hex: "#a855f7" }
      ],
      parts: [
        { shape: "box", x: 0, z: 0, w: 1, d: 1, y: 0, h: 1, color: "#00f0ff", paint: true, glow: true, edges: "glow" }
      ],
      symbol: [
        { shape: "rect", x: 0, z: 0, w: 1, d: 1, fill: true }
      ]
    },
    {
      id: "cable_ethernet",
      name: { en: "Ethernet (LAN Cat6A) Cable Run", id: "Jalur Kabel Ethernet (LAN Cat6A)" },
      size: [2.0, 0.10, 0.05],
      mount: "wall",
      wall_y: 1.25,
      stretch: true,
      colors: [
        { id: "blue_cat6a", name: { en: "Blue Cat6A Data LAN", id: "Biru LAN Data Cat6A" }, hex: "#3b82f6" },
        { id: "green_mgmt", name: { en: "Green Out-of-Band Mgmt", id: "Hijau LAN Manajemen" }, hex: "#22c55e" },
        { id: "cyan_uplink", name: { en: "Cyan Switch Trunk", id: "Sian Trunk Switch" }, hex: "#06b6d4" }
      ],
      parts: [
        { shape: "box", x: 0, z: 0, w: 1, d: 1, y: 0, h: 1, color: "#3b82f6", paint: true, glow: true, edges: "glow" }
      ],
      symbol: [
        { shape: "rect", x: 0, z: 0, w: 1, d: 1, fill: true }
      ]
    },
    {
      id: "wifi_ap",
      name: { en: "Enterprise Wi-Fi Access Point", id: "Access Point Wi-Fi Enterprise" },
      size: [0.24, 0.24, 0.05],
      mount: "ceiling",
      electric: true,
      parts: [
        { shape: "cyl", x: 0, z: 0, w: 1, d: 1, y: 0, h: 1, color: "#e2e8f0", edges: "glow" },
        { shape: "cyl", x: 0, z: 0, w: 0.45, d: 0.45, y: 0, h: 0.2, color: "#00f0ff", glow: true }
      ],
      symbol: [{ shape: "circle", x: 0, z: 0, r: 0.45 }]
    },
    {
      id: "thermohygro_sensor",
      name: { en: "Thermohygrograph Sensor (Temp/RH)", id: "Sensor Termohigrograf (Suhu/RH)" },
      size: [0.14, 0.05, 0.16],
      mount: "wall",
      wall_y: 1.5,
      electric: true,
      parts: [
        { shape: "box", x: 0, z: 0, w: 1, d: 1, y: 0, h: 1, color: "#1e293b", edges: "glow" },
        { shape: "box", x: 0, z: 0.48, w: 0.75, d: 0.1, y: 0.35, h: 0.45, color: "#00f0ff", glow: true }
      ],
      symbol: [{ shape: "rect", x: 0, z: 0, w: 1, d: 1, fill: true }]
    },
    {
      id: "fingerprint_reader",
      name: { en: "Biometric Fingerprint Reader", id: "Pembaca Sidik Jari Biometrik" },
      size: [0.14, 0.05, 0.20],
      mount: "wall",
      wall_y: 1.35,
      electric: true,
      parts: [
        { shape: "box", x: 0, z: 0, w: 1, d: 1, y: 0, h: 1, color: "#0f172a", edges: "glow" },
        { shape: "box", x: 0, z: 0.48, w: 0.65, d: 0.1, y: 0.25, h: 0.5, color: "#22c55e", glow: true }
      ],
      symbol: [{ shape: "rect", x: 0, z: 0, w: 1, d: 1, fill: true }]
    }
  ]
};

const rect = (id, name, area_id, x0, z0, x1, z1, floor_material = "tiles", extra = {}) => ({
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
  ...extra,
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
    settings: {
      wall_exterior: 0.25,
      wall_interior: 0.15,
      grid: 0.1,
      roof: { type: "none" }
    },
    floors: [
      {
        id: "ground",
        name: floors_def.ground.name,
        elevation: 0,
        height: 3.5,
        cut_height: 1.4,
        ha_floor: "ground",
        background: null,
        outdoor: [],
        rooms: [
          rect("room_server_a", areas_def.server_alpha.name, "server_alpha", 0, 0, 10, 8, "tiles", {
            climate: { temperature: "sensor.server_alpha_env_temp", humidity: "sensor.server_alpha_env_humidity" }
          }),
          rect("room_noc", areas_def.noc.name, "noc", 10, 0, 16, 5, "oak", {
            climate: { temperature: "sensor.noc_env_temp", humidity: "sensor.noc_env_humidity" }
          }),
          rect("room_ups", areas_def.ups.name, "ups", 10, 5, 16, 8, "concrete", {
            climate: { temperature: "sensor.ups_env_temp", humidity: "sensor.ups_env_humidity" }
          }),
          rect("room_battery", areas_def.battery.name, "battery", 0, 8, 6, 12, "concrete", {
            climate: { temperature: "sensor.battery_env_temp", humidity: "sensor.battery_env_humidity" }
          }),
          rect("room_meet_me", areas_def.meet_me.name, "meet_me", 6, 8, 16, 12, "tiles", {
            climate: { temperature: "sensor.meet_me_env_temp", humidity: "sensor.meet_me_env_humidity" }
          }),
        ],
        openings: [
          {
            id: "door_server_alpha",
            room_id: "room_server_a",
            edge: 1,
            offset: 2.5,
            width: 1.1,
            height: 2.1,
            sill: 0,
            type: "door",
            hinge: "left",
            leaves: 1,
            swing: "in",
            lock: "lock.server_alpha_door",
            contact: "binary_sensor.server_alpha_door",
            contact2: null,
            cover: null,
            tilt: null
          },
          {
            id: "door_meet_me",
            room_id: "room_server_a",
            edge: 2,
            offset: 2.0,
            width: 1.2,
            height: 2.1,
            sill: 0,
            type: "door",
            hinge: "right",
            leaves: 2,
            swing: "in",
            lock: "lock.meet_me_door",
            contact: null,
            contact2: null,
            cover: null,
            tilt: null
          }
        ],
        furniture: [
          // Server Racks Row A & B in Server Room Alpha
          {
            id: "f_rack_a1",
            type: "pack:dcim.facility:rack_42u",
            name: "Rack A01 (Compute)",
            show_name: true,
            x: 2.2,
            z: 2.2,
            w: 0.6,
            d: 1.0,
            h: 2.0,
            rotation: 0,
            variant: "obsidian",
            power: "sensor.server_alpha_env_power",
            temp_entity: "sensor.server_alpha_env_temp",
            marker: "always"
          },
          {
            id: "f_rack_a2",
            type: "pack:dcim.facility:rack_42u",
            name: "Rack A02 (Storage)",
            show_name: true,
            x: 3.0,
            z: 2.2,
            w: 0.6,
            d: 1.0,
            h: 2.0,
            rotation: 0,
            variant: "obsidian",
            temp_entity: "sensor.server_alpha_env_temp",
            marker: "always"
          },
          {
            id: "f_rack_a3",
            type: "pack:dcim.facility:rack_42u",
            name: "Rack A03 (AI GPU Cluster)",
            show_name: true,
            x: 3.8,
            z: 2.2,
            w: 0.6,
            d: 1.0,
            h: 2.0,
            rotation: 0,
            variant: "obsidian",
            marker: "always"
          },
          {
            id: "f_rack_b1",
            type: "pack:dcim.facility:rack_42u",
            name: "Rack B01 (Database)",
            show_name: true,
            x: 2.2,
            z: 5.2,
            w: 0.6,
            d: 1.0,
            h: 2.0,
            rotation: 180,
            variant: "slate",
            marker: "always"
          },
          {
            id: "f_rack_b2",
            type: "pack:dcim.facility:rack_42u",
            name: "Rack B02 (Core Switch)",
            show_name: true,
            x: 3.0,
            z: 5.2,
            w: 0.6,
            d: 1.0,
            h: 2.0,
            rotation: 180,
            variant: "slate",
            marker: "always"
          },
          // CRAC Cooling Unit
          {
            id: "f_crac_1",
            type: "pack:dcim.facility:crac_unit",
            name: "CRAC Unit Alpha-1",
            show_name: true,
            x: 0.8,
            z: 3.8,
            w: 0.9,
            d: 1.2,
            h: 1.95,
            rotation: 90,
            variant: null,
            entity: "switch.crac_alpha_1",
            temp_entity: "sensor.server_alpha_env_temp",
            marker: "always"
          },
          // UPS Cabinet in UPS Room
          {
            id: "f_ups_1",
            type: "pack:dcim.facility:ups_cabinet",
            name: "UPS Bank Primary 100kVA",
            show_name: true,
            x: 13.0,
            z: 6.5,
            w: 1.6,
            d: 0.9,
            h: 1.9,
            rotation: 0,
            variant: null,
            power: "sensor.ups_env_power",
            temp_entity: "sensor.ups_env_temp",
            marker: "always"
          },
          // Meet-Me Patch Racks
          {
            id: "f_mmr_rack1",
            type: "pack:dcim.facility:rack_24u",
            name: "MMR Fiber Distribution",
            show_name: true,
            x: 9.0,
            z: 10.0,
            w: 0.6,
            d: 0.8,
            h: 1.4,
            rotation: 0,
            variant: null,
            marker: "always"
          },
          // Virtual Ceiling Luminaires (linked to virtual lights!)
          {
            id: "f_lamp_alpha",
            type: "lamp_ceiling",
            name: "Server Alpha Cold-Aisle LED",
            x: 5.0,
            z: 3.7,
            w: 1.2,
            d: 0.3,
            h: 0.08,
            rotation: 0,
            variant: null,
            entity: "light.server_alpha_light",
            glow_scale: 1.3
          },
          {
            id: "f_lamp_noc",
            type: "lamp_ceiling",
            name: "NOC Ceiling Light",
            x: 13.0,
            z: 2.5,
            w: 0.8,
            d: 0.8,
            h: 0.08,
            rotation: 0,
            variant: null,
            entity: "light.noc_light",
            glow_scale: 1.2
          },
          {
            id: "f_lamp_ups",
            type: "lamp_ceiling",
            name: "UPS Room Utility Light",
            x: 13.0,
            z: 6.5,
            w: 0.8,
            d: 0.4,
            h: 0.08,
            rotation: 0,
            variant: null,
            entity: "light.ups_light",
            glow_scale: 1.2
          },
          // ===================================================================
          // 3D CABLING INFRASTRUCTURE: BELOW FLOOR, IN WALL, AND CEILING TRAYS
          // ===================================================================
          // 1. CEILING CABLE TRAY (mount_y = 2.80m)
          {
            id: "f_tray_main",
            type: "pack:dcim.facility:cable_tray",
            name: "Overhead Ladder Tray Alpha",
            show_name: true,
            x: 5.0,
            z: 2.2,
            w: 7.5,
            d: 0.45,
            h: 0.08,
            mount_y: 2.80,
            rotation: 0,
            variant: "galvanized",
            show_when: { entity: "input_boolean.layer_cable_tray" }
          },
          // 2. CEILING FIBER OPTIC (FO) TRUNK CABLE (mount_y = 2.88m)
          {
            id: "f_cable_fo_ceiling",
            type: "pack:dcim.facility:cable_fiber",
            name: "FO Trunk OM4 (Ceiling 2.88m)",
            show_name: true,
            x: 5.5,
            z: 2.2,
            w: 8.0,
            d: 0.12,
            h: 0.05,
            mount_y: 2.88,
            rotation: 0,
            variant: "aqua_om4",
            show_when: { entity: "input_boolean.layer_cable_fiber" }
          },
          {
            id: "f_cable_fo_mmr",
            type: "pack:dcim.facility:cable_fiber",
            name: "FO Cross-Connect MMR (Ceiling 2.88m)",
            show_name: true,
            x: 8.5,
            z: 6.0,
            w: 7.5,
            d: 0.12,
            h: 0.05,
            mount_y: 2.88,
            rotation: 90,
            variant: "yellow_os2",
            show_when: { entity: "input_boolean.layer_cable_fiber" }
          },
          // 3. BELOW-FLOOR ELECTRIC POWER CABLES (mount_y = -0.22m Under Raised Floor)
          {
            id: "f_cable_pwr_subfloor_1",
            type: "pack:dcim.facility:cable_power",
            name: "HV Power Feed A (Below Floor -0.22m)",
            show_name: true,
            x: 7.5,
            z: 5.8,
            w: 10.5,
            d: 0.15,
            h: 0.06,
            mount_y: -0.22,
            rotation: 0,
            variant: "red_hv",
            show_when: { entity: "input_boolean.layer_cable_power" }
          },
          {
            id: "f_cable_pwr_subfloor_2",
            type: "pack:dcim.facility:cable_power",
            name: "UPS Redundant Bus B (Below Floor -0.22m)",
            show_name: true,
            x: 3.0,
            z: 4.0,
            w: 3.8,
            d: 0.14,
            h: 0.06,
            mount_y: -0.22,
            rotation: 90,
            variant: "amber_ups",
            show_when: { entity: "input_boolean.layer_cable_power" }
          },
          // 4. IN-WALL ETHERNET (LAN Cat6A) CABLES (mount_y = 1.25m Along Wall)
          {
            id: "f_cable_lan_wall_1",
            type: "pack:dcim.facility:cable_ethernet",
            name: "Cat6A NOC Wall Conduit (Wall 1.25m)",
            show_name: true,
            x: 10.0,
            z: 4.0,
            w: 7.2,
            d: 0.10,
            h: 0.05,
            mount_y: 1.25,
            rotation: 90,
            variant: "blue_cat6a",
            show_when: { entity: "input_boolean.layer_cable_ethernet" }
          },
          {
            id: "f_cable_lan_wall_2",
            type: "pack:dcim.facility:cable_ethernet",
            name: "Mgmt LAN Wall Run (Wall 1.25m)",
            show_name: true,
            x: 11.0,
            z: 8.0,
            w: 8.5,
            d: 0.10,
            h: 0.05,
            mount_y: 1.25,
            rotation: 0,
            variant: "green_mgmt",
            show_when: { entity: "input_boolean.layer_cable_ethernet" }
          }
        ],
        placements: [
          // Virtual Lights
          { entity_id: "light.server_alpha_light", x: 5.0, z: 3.7, y: 3.3, mount: "ceiling", name: "Server Alpha Light", show_name: true, marker: "always" },
          { entity_id: "light.noc_light", x: 13.0, z: 2.5, y: 3.3, mount: "ceiling", name: "NOC Ceiling Light", show_name: true, marker: "always" },
          { entity_id: "light.ups_light", x: 13.0, z: 6.5, y: 3.3, mount: "ceiling", name: "UPS Room Light", show_name: true, marker: "always" },
          { entity_id: "light.battery_light", x: 3.0, z: 10.0, y: 3.3, mount: "ceiling", name: "Battery Room Light", show_name: true, marker: "always" },
          { entity_id: "light.meet_me_light", x: 11.0, z: 10.0, y: 3.3, mount: "ceiling", name: "Meet-Me Room Light", show_name: true, marker: "always" },
          // DB-Backed Room Sensors
          { entity_id: "sensor.server_alpha_env_temp", x: 3.4, z: 3.7, y: 1.6, name: "Alpha Temp", show_name: true, marker: "always" },
          { entity_id: "sensor.server_alpha_env_humidity", x: 6.5, z: 3.7, y: 1.6, name: "Alpha Humidity", show_name: true, marker: "always" },
          { entity_id: "sensor.noc_env_temp", x: 13.5, z: 1.5, y: 1.5, name: "NOC Temp", show_name: true, marker: "always" },
          { entity_id: "sensor.ups_env_temp", x: 14.5, z: 6.5, y: 1.5, name: "UPS Temp", show_name: true, marker: "always" },
          { entity_id: "sensor.battery_env_temp", x: 3.0, z: 9.2, y: 1.5, name: "Battery Temp", show_name: true, marker: "always" },
          { entity_id: "sensor.meet_me_env_temp", x: 12.5, z: 10.0, y: 1.5, name: "Meet-Me Temp", show_name: true, marker: "always" },
          // Security Cameras
          { entity_id: "camera.server_alpha_cam", x: 9.2, z: 0.8, y: 3.1, rotation: 225, fov: 75, reach: 7, cone: true, name: "CCTV Alpha Aisle", show_name: true, marker: "always" }
        ]
      },
      {
        id: "first",
        name: floors_def.first.name,
        elevation: 3.5,
        height: 3.5,
        cut_height: 1.4,
        ha_floor: "first",
        background: null,
        outdoor: [],
        rooms: [
          rect("room_server_b", areas_def.server_beta.name, "server_beta", 0, 0, 10, 8, "tiles", {
            climate: { temperature: "sensor.server_beta_env_temp", humidity: "sensor.server_beta_env_humidity" }
          }),
          rect("room_network_core", areas_def.network_core.name, "network_core", 10, 0, 16, 8, "tiles", {
            climate: { temperature: "sensor.network_core_env_temp", humidity: "sensor.network_core_env_humidity" }
          }),
          rect("room_security", areas_def.security.name, "security", 0, 8, 16, 12, "oak", {
            climate: { temperature: "sensor.security_env_temp", humidity: "sensor.security_env_humidity" }
          }),
        ],
        openings: [],
        furniture: [
          {
            id: "f_rack_beta1",
            type: "pack:dcim.facility:rack_42u",
            name: "Rack C01 (Cloud Node)",
            show_name: true,
            x: 3.0,
            z: 3.0,
            w: 0.6,
            d: 1.0,
            h: 2.0,
            rotation: 0,
            variant: "obsidian",
            power: "sensor.server_beta_env_power",
            temp_entity: "sensor.server_beta_env_temp",
            marker: "always"
          },
          {
            id: "f_rack_netcore1",
            type: "pack:dcim.facility:rack_24u",
            name: "Core Spine Router 01",
            show_name: true,
            x: 13.0,
            z: 3.5,
            w: 0.6,
            d: 0.8,
            h: 1.4,
            rotation: 0,
            variant: null,
            power: "sensor.network_core_env_power",
            temp_entity: "sensor.network_core_env_temp",
            marker: "always"
          },
          {
            id: "f_cable_fo_first",
            type: "pack:dcim.facility:cable_fiber",
            name: "FO Core Backbone (Ceiling 2.88m)",
            show_name: true,
            x: 8.0,
            z: 3.2,
            w: 10.5,
            d: 0.12,
            h: 0.05,
            mount_y: 2.88,
            rotation: 0,
            variant: "aqua_om4",
            show_when: { entity: "input_boolean.layer_cable_fiber" }
          }
        ],
        placements: [
          { entity_id: "light.server_beta_light", x: 5.0, z: 4.0, y: 3.3, mount: "ceiling", name: "Server Beta Light", show_name: true, marker: "always" },
          { entity_id: "light.network_core_light", x: 13.0, z: 4.0, y: 3.3, mount: "ceiling", name: "Network Core Light", show_name: true, marker: "always" },
          { entity_id: "light.security_light", x: 8.0, z: 10.0, y: 3.3, mount: "ceiling", name: "Security Center Light", show_name: true, marker: "always" },
          { entity_id: "sensor.server_beta_env_temp", x: 4.5, z: 3.0, y: 1.6, name: "Beta Temp", show_name: true, marker: "always" },
          { entity_id: "sensor.network_core_env_temp", x: 13.0, z: 2.0, y: 1.6, name: "Core Temp", show_name: true, marker: "always" },
          { entity_id: "sensor.security_env_temp", x: 8.0, z: 9.5, y: 1.6, name: "Security Temp", show_name: true, marker: "always" }
        ]
      }
    ],
  };

  return { floors: floors_def, areas: areas_def, building: building_def };
}

const defaultData = getFacilityData("en");
export const DEMO_FLOORS = defaultData.floors;
export const DEMO_AREAS = defaultData.areas;
export const DEMO_BUILDING = defaultData.building;

export const DEMO_ENTITIES = {
  // Virtual Room Lights (100% detached from Home Assistant)
  "light.server_alpha_light": { entity_id: "light.server_alpha_light", name: "Server Alpha Ceiling LED", area_id: "server_alpha" },
  "light.noc_light": { entity_id: "light.noc_light", name: "NOC Operations Ceiling Light", area_id: "noc" },
  "light.ups_light": { entity_id: "light.ups_light", name: "UPS & Power Room Light", area_id: "ups" },
  "light.battery_light": { entity_id: "light.battery_light", name: "Battery Storage Light", area_id: "battery" },
  "light.meet_me_light": { entity_id: "light.meet_me_light", name: "Meet-Me Room Light", area_id: "meet_me" },
  "light.server_beta_light": { entity_id: "light.server_beta_light", name: "Server Beta Ceiling Light", area_id: "server_beta" },
  "light.network_core_light": { entity_id: "light.network_core_light", name: "Network Core Light", area_id: "network_core" },
  "light.security_light": { entity_id: "light.security_light", name: "Security Center Light", area_id: "security" },

  // Virtual Equipment Switches & Smart Locks
  "switch.crac_alpha_1": { entity_id: "switch.crac_alpha_1", name: "CRAC Cooling Unit Alpha-1", area_id: "server_alpha" },
  "lock.server_alpha_door": { entity_id: "lock.server_alpha_door", name: "Server Alpha Biometric Lock", area_id: "server_alpha" },
  "lock.meet_me_door": { entity_id: "lock.meet_me_door", name: "Meet-Me Dual Door Lock", area_id: "meet_me" },
  "binary_sensor.server_alpha_door": { entity_id: "binary_sensor.server_alpha_door", name: "Server Alpha Door Contact", area_id: "server_alpha" },
  "camera.server_alpha_cam": { entity_id: "camera.server_alpha_cam", name: "CCTV Server Alpha Aisle", area_id: "server_alpha" },

  // Cable Layer Visibility Toggles
  "input_boolean.layer_cable_power": { entity_id: "input_boolean.layer_cable_power", name: "Electric Power Cables Layer", area_id: null },
  "input_boolean.layer_cable_fiber": { entity_id: "input_boolean.layer_cable_fiber", name: "Fiber Optic (FO) Cables Layer", area_id: null },
  "input_boolean.layer_cable_ethernet": { entity_id: "input_boolean.layer_cable_ethernet", name: "Ethernet (LAN) Cables Layer", area_id: null },
  "input_boolean.layer_cable_tray": { entity_id: "input_boolean.layer_cable_tray", name: "Cable Trays & Ladder Layer", area_id: null },

  // DB-Backed Room Sensors (Temperature, Humidity, Power Load)
  "sensor.server_alpha_env_temp": { entity_id: "sensor.server_alpha_env_temp", name: "Server Alpha Temperature", area_id: "server_alpha" },
  "sensor.server_alpha_env_humidity": { entity_id: "sensor.server_alpha_env_humidity", name: "Server Alpha Humidity", area_id: "server_alpha" },
  "sensor.server_alpha_env_power": { entity_id: "sensor.server_alpha_env_power", name: "Server Alpha Rack Load", area_id: "server_alpha" },
  "sensor.noc_env_temp": { entity_id: "sensor.noc_env_temp", name: "NOC Temperature", area_id: "noc" },
  "sensor.noc_env_humidity": { entity_id: "sensor.noc_env_humidity", name: "NOC Humidity", area_id: "noc" },
  "sensor.noc_env_power": { entity_id: "sensor.noc_env_power", name: "NOC Power Load", area_id: "noc" },
  "sensor.ups_env_temp": { entity_id: "sensor.ups_env_temp", name: "UPS Room Temperature", area_id: "ups" },
  "sensor.ups_env_humidity": { entity_id: "sensor.ups_env_humidity", name: "UPS Room Humidity", area_id: "ups" },
  "sensor.ups_env_power": { entity_id: "sensor.ups_env_power", name: "UPS Primary Output Load", area_id: "ups" },
  "sensor.battery_env_temp": { entity_id: "sensor.battery_env_temp", name: "Battery Room Temperature", area_id: "battery" },
  "sensor.battery_env_humidity": { entity_id: "sensor.battery_env_humidity", name: "Battery Room Humidity", area_id: "battery" },
  "sensor.meet_me_env_temp": { entity_id: "sensor.meet_me_env_temp", name: "Meet-Me Room Temperature", area_id: "meet_me" },
  "sensor.meet_me_env_humidity": { entity_id: "sensor.meet_me_env_humidity", name: "Meet-Me Room Humidity", area_id: "meet_me" },
  "sensor.server_beta_env_temp": { entity_id: "sensor.server_beta_env_temp", name: "Server Beta Temperature", area_id: "server_beta" },
  "sensor.server_beta_env_humidity": { entity_id: "sensor.server_beta_env_humidity", name: "Server Beta Humidity", area_id: "server_beta" },
  "sensor.server_beta_env_power": { entity_id: "sensor.server_beta_env_power", name: "Server Beta Load", area_id: "server_beta" },
  "sensor.network_core_env_temp": { entity_id: "sensor.network_core_env_temp", name: "Network Core Temperature", area_id: "network_core" },
  "sensor.network_core_env_humidity": { entity_id: "sensor.network_core_env_humidity", name: "Network Core Humidity", area_id: "network_core" },
  "sensor.network_core_env_power": { entity_id: "sensor.network_core_env_power", name: "Network Core Load", area_id: "network_core" },
  "sensor.security_env_temp": { entity_id: "sensor.security_env_temp", name: "Security Center Temperature", area_id: "security" },
  "sensor.security_env_humidity": { entity_id: "sensor.security_env_humidity", name: "Security Center Humidity", area_id: "security" },
};

export const DEMO_STATES = {
  // Virtual Lights (ON by default with cool cyan/daylight server room illumination)
  "light.server_alpha_light": {
    entity_id: "light.server_alpha_light",
    state: "on",
    attributes: { friendly_name: "Server Alpha Ceiling LED", brightness: 230, rgb_color: [56, 189, 248], supported_color_modes: ["rgb", "brightness"] }
  },
  "light.noc_light": {
    entity_id: "light.noc_light",
    state: "on",
    attributes: { friendly_name: "NOC Operations Ceiling Light", brightness: 245, rgb_color: [224, 242, 254], supported_color_modes: ["rgb", "brightness"] }
  },
  "light.ups_light": {
    entity_id: "light.ups_light",
    state: "on",
    attributes: { friendly_name: "UPS & Power Room Light", brightness: 210, rgb_color: [254, 243, 199], supported_color_modes: ["rgb", "brightness"] }
  },
  "light.battery_light": {
    entity_id: "light.battery_light",
    state: "off",
    attributes: { friendly_name: "Battery Storage Light", brightness: 180, rgb_color: [254, 215, 170], supported_color_modes: ["rgb", "brightness"] }
  },
  "light.meet_me_light": {
    entity_id: "light.meet_me_light",
    state: "on",
    attributes: { friendly_name: "Meet-Me Room Light", brightness: 220, rgb_color: [165, 243, 252], supported_color_modes: ["rgb", "brightness"] }
  },
  "light.server_beta_light": {
    entity_id: "light.server_beta_light",
    state: "on",
    attributes: { friendly_name: "Server Beta Ceiling Light", brightness: 230, rgb_color: [56, 189, 248], supported_color_modes: ["rgb", "brightness"] }
  },
  "light.network_core_light": {
    entity_id: "light.network_core_light",
    state: "on",
    attributes: { friendly_name: "Network Core Light", brightness: 235, rgb_color: [125, 211, 252], supported_color_modes: ["rgb", "brightness"] }
  },
  "light.security_light": {
    entity_id: "light.security_light",
    state: "on",
    attributes: { friendly_name: "Security Center Light", brightness: 225, rgb_color: [241, 245, 249], supported_color_modes: ["rgb", "brightness"] }
  },

  // Equipment Switches & Locks
  "switch.crac_alpha_1": {
    entity_id: "switch.crac_alpha_1",
    state: "on",
    attributes: { friendly_name: "CRAC Cooling Unit Alpha-1" }
  },
  "lock.server_alpha_door": {
    entity_id: "lock.server_alpha_door",
    state: "locked",
    attributes: { friendly_name: "Server Alpha Biometric Lock" }
  },
  "lock.meet_me_door": {
    entity_id: "lock.meet_me_door",
    state: "locked",
    attributes: { friendly_name: "Meet-Me Dual Door Lock" }
  },
  "binary_sensor.server_alpha_door": {
    entity_id: "binary_sensor.server_alpha_door",
    state: "off",
    attributes: { device_class: "door", friendly_name: "Server Alpha Door Contact" }
  },
  "camera.server_alpha_cam": {
    entity_id: "camera.server_alpha_cam",
    state: "streaming",
    attributes: { friendly_name: "CCTV Server Alpha Aisle" }
  },

  // Cable Layer Visibility States
  "input_boolean.layer_cable_power": {
    entity_id: "input_boolean.layer_cable_power",
    state: "on",
    attributes: { friendly_name: "Electric Power Cables Layer" }
  },
  "input_boolean.layer_cable_fiber": {
    entity_id: "input_boolean.layer_cable_fiber",
    state: "on",
    attributes: { friendly_name: "Fiber Optic (FO) Cables Layer" }
  },
  "input_boolean.layer_cable_ethernet": {
    entity_id: "input_boolean.layer_cable_ethernet",
    state: "on",
    attributes: { friendly_name: "Ethernet (LAN) Cables Layer" }
  },
  "input_boolean.layer_cable_tray": {
    entity_id: "input_boolean.layer_cable_tray",
    state: "on",
    attributes: { friendly_name: "Cable Trays & Ladder Layer" }
  },

  // Initial DB Sensor Readings (Synced live from /api/v1/sensors)
  "sensor.server_alpha_env_temp": {
    entity_id: "sensor.server_alpha_env_temp",
    state: "21.4",
    attributes: { device_class: "temperature", unit_of_measurement: "°C", friendly_name: "Server Alpha Temperature", status: "online" }
  },
  "sensor.server_alpha_env_humidity": {
    entity_id: "sensor.server_alpha_env_humidity",
    state: "44.5",
    attributes: { device_class: "humidity", unit_of_measurement: "%", friendly_name: "Server Alpha Humidity", status: "online" }
  },
  "sensor.server_alpha_env_power": {
    entity_id: "sensor.server_alpha_env_power",
    state: "42.8",
    attributes: { device_class: "power", unit_of_measurement: "kW", friendly_name: "Server Alpha Rack Load", status: "online" }
  },
  "sensor.noc_env_temp": {
    entity_id: "sensor.noc_env_temp",
    state: "22.8",
    attributes: { device_class: "temperature", unit_of_measurement: "°C", friendly_name: "NOC Temperature", status: "online" }
  },
  "sensor.noc_env_humidity": {
    entity_id: "sensor.noc_env_humidity",
    state: "46.0",
    attributes: { device_class: "humidity", unit_of_measurement: "%", friendly_name: "NOC Humidity", status: "online" }
  },
  "sensor.noc_env_power": {
    entity_id: "sensor.noc_env_power",
    state: "8.4",
    attributes: { device_class: "power", unit_of_measurement: "kW", friendly_name: "NOC Power Load", status: "online" }
  },
  "sensor.ups_env_temp": {
    entity_id: "sensor.ups_env_temp",
    state: "24.6",
    attributes: { device_class: "temperature", unit_of_measurement: "°C", friendly_name: "UPS Room Temperature", status: "online" }
  },
  "sensor.ups_env_humidity": {
    entity_id: "sensor.ups_env_humidity",
    state: "41.2",
    attributes: { device_class: "humidity", unit_of_measurement: "%", friendly_name: "UPS Room Humidity", status: "online" }
  },
  "sensor.ups_env_power": {
    entity_id: "sensor.ups_env_power",
    state: "68.4",
    attributes: { device_class: "power", unit_of_measurement: "kW", friendly_name: "UPS Primary Output Load", status: "online" }
  },
  "sensor.battery_env_temp": {
    entity_id: "sensor.battery_env_temp",
    state: "23.1",
    attributes: { device_class: "temperature", unit_of_measurement: "°C", friendly_name: "Battery Room Temperature", status: "online" }
  },
  "sensor.battery_env_humidity": {
    entity_id: "sensor.battery_env_humidity",
    state: "39.8",
    attributes: { device_class: "humidity", unit_of_measurement: "%", friendly_name: "Battery Room Humidity", status: "online" }
  },
  "sensor.meet_me_env_temp": {
    entity_id: "sensor.meet_me_env_temp",
    state: "20.9",
    attributes: { device_class: "temperature", unit_of_measurement: "°C", friendly_name: "Meet-Me Room Temperature", status: "online" }
  },
  "sensor.meet_me_env_humidity": {
    entity_id: "sensor.meet_me_env_humidity",
    state: "43.0",
    attributes: { device_class: "humidity", unit_of_measurement: "%", friendly_name: "Meet-Me Room Humidity", status: "online" }
  },
  "sensor.server_beta_env_temp": {
    entity_id: "sensor.server_beta_env_temp",
    state: "21.8",
    attributes: { device_class: "temperature", unit_of_measurement: "°C", friendly_name: "Server Beta Temperature", status: "online" }
  },
  "sensor.server_beta_env_humidity": {
    entity_id: "sensor.server_beta_env_humidity",
    state: "45.1",
    attributes: { device_class: "humidity", unit_of_measurement: "%", friendly_name: "Server Beta Humidity", status: "online" }
  },
  "sensor.server_beta_env_power": {
    entity_id: "sensor.server_beta_env_power",
    state: "36.5",
    attributes: { device_class: "power", unit_of_measurement: "kW", friendly_name: "Server Beta Load", status: "online" }
  },
  "sensor.network_core_env_temp": {
    entity_id: "sensor.network_core_env_temp",
    state: "20.5",
    attributes: { device_class: "temperature", unit_of_measurement: "°C", friendly_name: "Network Core Temperature", status: "online" }
  },
  "sensor.network_core_env_humidity": {
    entity_id: "sensor.network_core_env_humidity",
    state: "42.3",
    attributes: { device_class: "humidity", unit_of_measurement: "%", friendly_name: "Network Core Humidity", status: "online" }
  },
  "sensor.network_core_env_power": {
    entity_id: "sensor.network_core_env_power",
    state: "24.1",
    attributes: { device_class: "power", unit_of_measurement: "kW", friendly_name: "Network Core Load", status: "online" }
  },
  "sensor.security_env_temp": {
    entity_id: "sensor.security_env_temp",
    state: "22.4",
    attributes: { device_class: "temperature", unit_of_measurement: "°C", friendly_name: "Security Center Temperature", status: "online" }
  },
  "sensor.security_env_humidity": {
    entity_id: "sensor.security_env_humidity",
    state: "47.0",
    attributes: { device_class: "humidity", unit_of_measurement: "%", friendly_name: "Security Center Humidity", status: "online" }
  },
  "sun.sun": {
    entity_id: "sun.sun",
    state: "above_horizon",
    attributes: { elevation: 38, azimuth: 175 }
  }
};

export const DEMO_PICTURES = {};
