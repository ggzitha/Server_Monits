# Task: Data Center Monitoring Platform with 3D Floor Plan (Web, Docker-ready)

## 0. How to Use This Document (instructions for the AI agent)

You are building a complete, production-oriented web application. Read this whole document before writing code.

- Work in **phases** (Section 14). Finish and verify each phase before starting the next.
- Before coding, produce an **implementation plan** (architecture, folder structure, DB schema, API list) and save it to `docs/PLAN.md`.
- Where a requirement is marked **MUST**, it is mandatory. **SHOULD** = strongly preferred. **MAY** = optional.
- If a requirement is ambiguous or technically impossible as written, follow the **Resolved Decisions** in Section 2. Do not silently skip requirements; record deviations in `docs/DECISIONS.md`.
- Use the referenced GitHub repos **only as UX/feature inspiration**. Do **not** copy their code. Check each license before reusing anything.
- The app will be deployed on a remote server with Docker. Local development here is only for running and debugging Python. Everything MUST run via `docker compose up`.

---

## 1. Product Summary

A web-based **server room / data center monitoring system** built around an editable **3D floor plan**. Users draw rooms in meters, place racks, access points, sensors and security devices on the plan, and see live data (temperature, humidity, Wi-Fi strength, camera feeds, door/fingerprint events) directly in the 3D scene, including **heat maps** per room.

Primary things monitored:
1. Room temperature and humidity (thermohygrograph sensors)
2. Wi-Fi signal strength (access points + survey data)
3. Racks (U-space layout, devices) and cabling (fiber, LAN, power)
4. Security devices (CCTV, fingerprint readers, smart door locks)

---

## 2. Resolved Decisions (important technical clarifications)

The original idea said "UI layer: use Python". A browser cannot run Python to render 3D, so interpret the architecture like this:

| Layer | Technology | Notes |
|---|---|---|
| **Backend / API** | **Python 3.12 + FastAPI** | REST + WebSocket. Async. Pydantic v2. |
| **UI layer** | **Python-served web app**: server-rendered pages (Jinja2 templates) + a small **TypeScript/JavaScript front-end bundle** for the interactive parts | Python owns routing, templates, auth, i18n and config pages. The browser runs the 3D viewer. |
| **3D engine** | **Three.js** with **WebGL2**, and **WebGPU when available** (automatic fallback) | This is how GPU acceleration is achieved. Safari on iOS/macOS uses Metal under the hood; Chrome on Android uses the GPU via ANGLE/Vulkan. No extra work beyond efficient rendering. |
| **Database** | **PostgreSQL (default)**, with **MySQL and MariaDB** supported | SQLAlchemy 2.x + Alembic. Chosen at first run (see Section 5). |
| **Cache / realtime fan-out** | Redis (MAY, optional) | Only if needed for WebSocket scaling. App MUST also work without it. |
| **Video** | **Existing Frigate (go2rtc)** | Server already runs Frigate with embedded go2rtc (:1984). The app connects to Frigate rather than shipping a separate gateway container. |
| **MQTT Broker** | **Existing Mosquitto** | Server already runs Mosquitto. The app connects to the existing broker with encrypted credentials and auto-reconnect backoff. |
| **Reverse Proxy** | **Existing Nginx Proxy Manager (NPM)** | Reverse proxy and SSL are handled by the host's existing NPM (with WebSockets Support enabled). |
| **Wi-Fi survey** | Small **Python survey agent** (CLI) that runs on a laptop/Raspberry Pi | A browser cannot scan Wi-Fi. The agent measures signal at spots on the plan and uploads results to the API. |

If you believe a different front-end approach is better (for example a full SPA), you MAY propose it in `docs/DECISIONS.md`, but the backend MUST stay Python + FastAPI.

---

## 3. Tech Stack and Conventions

- Python 3.12, FastAPI, Uvicorn/Gunicorn, SQLAlchemy 2.x (async), Alembic, Pydantic v2.
- Front-end: Three.js, TypeScript (built with Vite), no heavy UI framework required. Keep the bundle small.
- Auth: password hashing with Argon2 or bcrypt, JWT (short-lived access + refresh) or secure session cookies, CSRF protection for cookie sessions.
- Tests: pytest (backend), Playwright (basic UI smoke tests).
- Lint/format: ruff + black, mypy for backend where practical.
- Config: environment variables (12-factor) plus the in-app setup wizard for DB and data sources.
- All code, comments and docs in English. UI strings go through i18n (Section 8).

---

## 4. Security, Users and Access Control (MUST)

- Secure login page, logout, password change, optional TOTP 2FA (SHOULD).
- First run creates the initial admin through the setup wizard (no hard-coded default password).
- Multi-user management: create, edit, disable, delete users.
- **Role-based access control (RBAC)** with at least these roles:
  - **Admin**: everything, including users, DB, data sources, system settings.
  - **Operator**: edit floor plans, racks, devices; view all live data; acknowledge alerts.
  - **Viewer**: read-only access to the 3D view and dashboards.
  - **Security Officer**: Viewer + camera live view + access logs.
  - Custom roles with per-permission checkboxes (MAY).
- Permissions can also be scoped per floor plan / site (SHOULD).
- Rate-limit login, lock out after repeated failures, write an **audit log** (who changed what, when).
- Secrets (camera passwords, DB credentials, API tokens) stored encrypted at rest (for example Fernet with a key from env).
- HTTPS is expected to be handled by a reverse proxy (Traefik/Nginx/Caddy). Provide an example config. Set secure headers and cookie flags.

---

## 5. Setup Wizard and Configuration ("like Grafana")

On first launch, the app shows a **Setup Wizard** in the browser:

1. Choose database type (PostgreSQL / MySQL / MariaDB), host, port, name, user, password. **Test connection** button.
2. Run migrations automatically.
3. Create the admin account.
4. Pick default language and theme.

Afterwards, an **Admin > Settings** area lets admins change configuration without editing files:

- Database connection (with a safe migration/restart flow).
- **Data Sources** (Section 9.1): add, edit, test and delete sources for sensor data.
- Themes, languages, notification and sound settings.
- Camera/stream gateway settings.

The Docker image MUST also support fully env-driven config (for example `DATABASE_URL`) so the wizard can be skipped in automated deployments.

---

## 6. 3D Floor Plan Builder (core feature)

Inspiration for look and workflow: https://github.com/Mastershort/neonplan3d and https://github.com/therealMRBK/NextFloor (concepts only, no code copying).

### 6.1 Editing
- All dimensions in **meters with decimal precision** (for example 3.25 m). Snap-to-grid with configurable grid step (for example 0.05 / 0.1 / 0.5 m).
- Draw walls, rooms (closed polygons), doors, windows; set wall height and thickness.
- Multiple floors/levels and multiple sites/buildings (SHOULD).
- Tools: select, move, rotate, resize, duplicate, delete, undo/redo, multi-select.
- Camera modes: orbit 3D, top-down 2D, first-person walkthrough (SHOULD).
- Edit mode vs. view mode (view mode hides editing handles).
- Save/load floor plans in the database; export/import as JSON (SHOULD: also export a PNG snapshot).

### 6.2 Visual design
- UI is **mostly based on the neonplan3d look and feel**: dark futuristic "neon" style with glowing edges, clean panels and pop-up cards.
- **Remove all decorative demo objects** from that design: no dogs, cats, trees or similar. The scene shows only what the user places (walls, racks, devices, sensors).
- Two theme families: **Neon (dark)** and **Normal (light)**. Theme switch at runtime, remembered per user.
- Theme colors, glow strength and object colors MUST be customizable in the web UI (theme editor, saved per user or globally by admin).

### 6.3 Performance (MUST)
- Target 60 FPS on a mid-range phone and desktop. Use: instancing for repeated objects (racks, cable segments), merged geometries, frustum culling, level of detail, texture compression, `devicePixelRatio` capping on mobile, render-on-demand when the scene is static.
- Prefer WebGPU, fall back to WebGL2, and show a clear message if neither is available.
- Provide a **Quality setting** (Low / Medium / High / Auto) and show an optional FPS/GPU stats overlay.

---

## 7. Objects You Can Place on the Floor Plan

Every placed object supports: **add, delete, move, rotate, resize** (where it makes sense), name, color, notes, and a **pop-up info card** when clicked or hovered.

### 7.1 Sensors (Thermohygrograph: temperature + humidity)
- Placed at any x/y/z position in a room.
- Linked to a **data source** configured later (Section 9.1), not hard-coded.
- **Pop-up card per sensor**, styled like the solar-panel pop-up in neonplan3d: name, current value, min/max, small history sparkline, status (online/offline/alert), last update time.
- Threshold alerts (warning/critical) per sensor.

### 7.2 Wireless Access Points
- Add, delete, move and resize (coverage radius/size) on the plan.
- Fields: name, model, SSID(s), band, channel, TX power, IP/MAC (optional).
- Pop-up card: status, connected clients (if a data source provides it), signal info.

### 7.3 Security Devices
- Types: **CCTV camera, fingerprint reader, smart door lock** (extensible).
- **CCTV pop-up window with live view.** Supported inputs: URL video (MJPEG/HLS/WebRTC), **RTSP**, **ONVIF** (discovery and profile/stream URL lookup). RTSP/ONVIF go through the stream gateway (Section 2). Support multiple cameras open at once (grid view SHOULD).
- Fingerprint / smart lock: show **time of access**, user/identity, success or failure, and door state.
- **Notifications in the 3D view** on events (door opened, access denied, camera offline, temperature alarm):
  - A visual pop-up/toast and a highlight/pulse on the device in 3D.
  - A **soft, non-intrusive notification sound** (short chime). Sound is **off by default or low volume**, with a mute toggle and per-event-type sound settings. Browsers block autoplay, so enable audio after the first user interaction.
- Device integration is done through adapters (webhook, MQTT, HTTP polling, vendor SDK later). Provide at least **webhook + MQTT** adapters in the first version.

### 7.4 Racks
- Place **multiple racks** from templates: **4U up to 60U** (also custom U height, width 19", depth, color).
- Rack pop-up / detail page: see Section 10.

### 7.5 Cables and Power
- Cable types: **Fiber optic**, **LAN (copper)**, **Electrical/power**.
- Each cable type has a **user-selectable color** (and optional label).
- Routing paths: along the **floor**, along **ceiling ladder frames/cable trays**, and along **walls**. Users draw routes as polylines with snapping to trays/walls, with configurable height.
- Cable trays / ladder frames are placeable objects (add, move, resize).
- Cables can be linked to rack ports/devices (SHOULD): start/end endpoints, length auto-calculated in meters.
- Layer toggles: show/hide each cable type independently.

---

## 8. Languages and Responsive Design

### 8.1 Languages (MUST)
- **English** and **Indonesian (Bahasa Indonesia)**. All UI text goes through an i18n layer (JSON/gettext translation files), with a language switcher and per-user preference. Structure the code so more languages can be added without code changes. Numbers and dates are formatted per locale.

### 8.2 Responsive / device support (MUST)
Must work and be usable on: phones (16:9, 21:9, 3:4), iPad portrait and landscape, laptops, desktop 1080p / 2K (1440p), widescreen, ultrawide, and 4K.
- Touch controls: pinch-zoom, two-finger pan, one-finger orbit, long-press for context menu.
- Mouse/keyboard shortcuts on desktop.
- Panels collapse into drawers/bottom sheets on small screens. Pop-ups are never larger than the viewport.
- Test with Playwright viewport presets for the sizes above.

---

## 9. Data, Heat Maps and Wi-Fi Survey

### 9.1 Data sources (configurable, "like Grafana")
- Admin UI to add sources and map them to sensors/devices. Supported types in v1 (extensible plugin interface):
  - **MQTT** (topic + JSON path)
  - **HTTP/REST polling** (URL, headers, JSON path, interval)
  - **Webhook** (push endpoint with token)
  - **SNMP** (SHOULD)
  - **Modbus TCP** (MAY)
  - Manual/CSV import (for testing)
- Each source has a **Test** button that shows a sample reading.
- Store time-series readings in the DB (partitioned or indexed by time); provide retention settings and downsampling (SHOULD).
- Push live updates to the browser via **WebSocket**.

### 9.2 Heat maps (MUST)
Per room, toggled by **radio buttons**: *Off / Temperature / Humidity / Wi-Fi*. Only one heat map layer is active at a time.
- Computed automatically from sensor readings placed in the room using interpolation (for example IDW or Kriging-lite), rendered on the floor as a GPU shader/texture overlay.
- **User-selectable colors**: pick the **lowest value color** and the **highest value color** (cool to hot for temperature, plus the same for humidity and Wi-Fi). Optional middle color stops and min/max value range.
- Legend with units, and tooltip showing the interpolated value under the cursor.
- Updates live as new readings arrive. Handle rooms with few sensors gracefully (show a low-confidence hint).

### 9.3 Wi-Fi signal heat map and survey
Inspiration: https://github.com/jantman/python-wifi-survey-heatmap, https://github.com/weimens/wifiheatmap, and the Ekahau AI Pro workflow (concepts only).
- **Survey Agent** (separate Python package, runs on a Linux/Windows/macOS laptop or Raspberry Pi with a Wi-Fi adapter):
  1. Fetches the floor plan from the API.
  2. User walks to a spot, clicks that spot on the plan (or enters coordinates), agent records RSSI/SNR per BSSID/SSID (and optionally iperf throughput).
  3. Uploads measurements to the API with an API token.
- Backend stores survey points and builds the Wi-Fi heat map (per SSID/band/AP selectable).
- Also support **predicted coverage** from AP position, TX power and wall attenuation as a simple model (SHOULD, v2).
- Display survey points as markers in 3D with their dBm values.

---

## 10. Rack View (inspiration: NetBox and Rackula)

References: https://github.com/netbox-community/netbox and https://github.com/RackulaLives/Rackula (concepts only).
- Clicking a rack in the 3D scene opens a **rack elevation view**: a front (and optional rear) view from **top U to bottom U**.
- Users can **add, move, remove and edit devices** in specific U positions: servers, switches, patch panels, PDUs, UPS, storage, blank panels, and custom items.
- Fields: name, model/manufacturer, height in U, position, face (front/rear), half-width, power draw, status, serial, notes, color.
- Validate overlaps and out-of-range placement; support drag-and-drop.
- Device library with reusable templates (user can create their own).
- Show rack utilization (U used/free, power total).
- (SHOULD) Optional import of device types from NetBox-style YAML/JSON.

---

## 11. Architecture and Deliverables

### 11.1 Suggested repository layout
```
/
├── Task.md
├── docker-compose.yml
├── docker-compose.dev.yml
├── .env.example
├── README.md
├── docs/            # PLAN.md, DECISIONS.md, API.md, DEPLOYMENT.md
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/         # FastAPI routers (auth, users, plans, devices, racks, cables, sensors, sources, ws)
│   │   ├── core/        # config, security, rbac, i18n
│   │   ├── db/          # models, session, migrations (alembic)
│   │   ├── services/    # heatmap, ingestion, adapters (mqtt, http, webhook, snmp), notifications
│   │   ├── templates/   # Jinja2 pages
│   │   └── static/
│   ├── tests/
│   └── Dockerfile
├── frontend/        # TypeScript + Three.js viewer/editor (Vite)
├── survey-agent/    # Python Wi-Fi survey CLI
├── gateway/         # go2rtc / MediaMTX config
└── deploy/          # example reverse proxy configs
```

### 11.2 Docker (MUST)
- Dockerfile, healthchecks, graceful shutdown.
- `docker-compose.yml` with: app, database (PostgreSQL default; document MySQL/MariaDB variants), and optional Redis. Integrates with existing NPM, Frigate go2rtc, and Mosquitto on the host.
- Persistent volumes for DB, uploads and config. No secrets in the image.
- Works on linux/amd64 and linux/arm64.
- Provide `docs/DEPLOYMENT.md` with steps for pushing to the remote server, env variables, Nginx Proxy Manager setup, and backup/restore.

### 11.3 API
- Versioned REST API (`/api/v1`), auto-generated OpenAPI docs, WebSocket channel for live readings and notifications.
- Consistent error format, pagination, input validation, and permission checks on every endpoint.

---

## 12. Non-Functional Requirements

- Security: OWASP basics, dependency pinning, no secrets in logs, SSRF-safe handling of user-supplied camera/data-source URLs (allow-list option for private networks).
- Reliability: reconnect logic for MQTT/streams, backoff, offline status in UI.
- Observability: structured logs, `/healthz` and `/metrics` (Prometheus format, SHOULD).
- Accessibility: keyboard navigation for non-3D UI, sufficient contrast in both themes.
- Documentation: README with quick start, screenshots (later), and architecture diagram.

---

## 13. Out of Scope for v1

- Native mobile apps (the web app must work on mobile browsers).
- Cloud-hosted multi-tenant SaaS billing.
- Automatic wall detection from images/CAD (manual drawing only; DXF/image-underlay import is a MAY).

---

## 14. Delivery Phases (do in this order)

1. **Foundation**: repo layout, Docker Compose, FastAPI skeleton, DB layer for Postgres/MySQL/MariaDB, migrations, setup wizard, auth, users, RBAC, i18n (EN/ID), light/neon themes, health checks.
2. **3D floor plan editor**: walls/rooms in meters, save/load, camera modes, responsive layout, performance baseline.
3. **Devices and sensors**: sensor placement, data sources (webhook, MQTT, HTTP), live WebSocket updates, sensor pop-up cards, alerts.
4. **Heat maps**: temperature and humidity with custom colors, then Wi-Fi heat map and the survey agent.
5. **Racks and cables**: rack templates 4U to 60U, rack elevation view, device library, cable trays and colored cable routing.
6. **Security devices**: CCTV live view through the stream gateway (RTSP/ONVIF/URL), fingerprint and smart lock events, access logs, in-3D notifications with soft sound.
7. **Hardening and polish**: tests, performance tuning on mobile, accessibility, docs, final Docker/deployment verification.

---

## 15. Acceptance Criteria (definition of done)

- [ ] `docker compose up` starts the whole stack; setup wizard completes with PostgreSQL, and also with MySQL and MariaDB.
- [ ] Login, multi-user management and all roles enforce correct permissions (automated tests).
- [ ] A floor plan can be drawn in meters with decimals, saved, reloaded and edited.
- [ ] Sensors, access points, racks, cables, CCTV, fingerprint and door lock can be added, moved, resized (where applicable) and deleted.
- [ ] Sensor pop-up shows live data from a configured data source.
- [ ] Temperature, humidity and Wi-Fi heat maps work per room via radio buttons, with user-chosen lowest/highest colors.
- [ ] Wi-Fi survey agent uploads measurements and the heat map updates.
- [ ] Rack elevation view works with U-based device placement and overlap validation.
- [ ] CCTV live view works from at least one RTSP source via the gateway and one URL source.
- [ ] Access events trigger a visual notification and a soft, mutable sound.
- [ ] No decorative demo objects (dogs, cats, trees) anywhere.
- [ ] English and Indonesian fully translated; neon and light themes both complete.
- [ ] Usable on phone, tablet, desktop, 2K, 4K, widescreen and ultrawide viewports (Playwright checks).
- [ ] Runs at a smooth frame rate on mid-range mobile hardware with GPU acceleration.

---

<!-- Admin account created through Setup Wizard with operator-chosen password -->

## 16. Reference Links (inspiration and source)

- UI/3D look: https://github.com/Mastershort/neonplan3d
- Floor plan editor: https://github.com/therealMRBK/NextFloor
- Rack/DCIM concepts: https://github.com/netbox-community/netbox
- Rack elevation UI: https://github.com/RackulaLives/Rackula
- Wi-Fi heat map: https://github.com/jantman/python-wifi-survey-heatmap
- Wi-Fi heat map: https://github.com/weimens/wifiheatmap
- Wi-Fi survey product concept: https://www.ekahau.com