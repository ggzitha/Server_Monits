# Plan: Transitioning 3D Editor to NeonPlan 3D Architecture

**Document Version:** 1.0.0  
**Date:** 2026-11-10  
**Target:** Replace hand-written editor with battle-tested CAD & 3D visualization engine from `Mastershort/neonplan3d` (MIT License).

---

## 1. Objectives & Compliance

1. **Robust CAD & 3D Core**:
   - Utilize NeonPlan 3D's sophisticated wall drawing, corner vertex snapping, automatic wall-thickness offsetting, door/window cutouts, split 2D/3D views, wall elevation mode, and first-person walkthrough.
2. **Licensing & Attribution**:
   - Cleanly vendor only required components from `reference/neonplan3d/frontend/`.
   - Maintain the MIT License and copyright notice (`Copyright (c) 2026 Mastershort`) in `THIRD_PARTY_NOTICES.md` and module headers.
   - Maintain git history/records of vendored source files.
3. **Own Branding & Clean Data Center Scope**:
   - Branded as **Server_Monits 3D Facility Monitor**. Zero references to "NeonPlan 3D" in user-facing UI.
   - Strictly enterprise infrastructure: Server Racks (4U–60U), CRAC cooling, UPS/PDU, Thermohygro sensors, Access Points, CCTV cameras, biometric readers, cable trays.
   - **Strictly zero domestic/decorative objects**: No pets (dogs/cats), no trees, no home furniture (sofas, beds, sinks), no Halloween/Christmas fun packs.
   - Completely offline & secure: **Zero calls to external servers** (`mastershort.de` shop, license keys, or analytics).
4. **Localization & Themes**:
   - Full English (`en`) and Indonesian (`id`) translations.
   - Themes: Neon (dark cyberpunk), Blueprint (technical wireframe), and Normal Light (crisp daylight blueprint).
   - Tablet-optimized quality settings (Low / Medium / High / Auto) with on-demand dirty rendering.

---

## 2. Architecture & The FastAPI / WebSocket Adapter

NeonPlan 3D was originally designed as a Home Assistant custom component communicating via `hass.callWS(...)`. Rather than rewriting all component internals, we employ the **Adapter Pattern**:

```mermaid
flowchart TD
    subgraph NeonPlan 3D Engine
        VIEW[fp3d-view3d (Three.js)]
        EDIT[fp3d-editor (CAD Tools)]
        CARD[fp3d-room-panel (Equipment HUD)]
    end

    subgraph Backend Adapter Layer
        ADAPT[ServerMonitsAdapter]
    end

    subgraph FastAPI Backend & Storage
        REST[/api/v1/plans (CRUD + CSRF)]
        AUTH[/api/v1/auth (Session + RBAC)]
        WS[/ws/live (Realtime Telemetry & Alerts)]
        DB[(PostgreSQL / SQLite)]
    end

    VIEW <--> ADAPT
    EDIT <--> ADAPT
    CARD <--> ADAPT

    ADAPT -->|GET / PUT Plan JSON| REST
    ADAPT -->|Telemetry / Alerts| WS
    REST --> DB
```

### Adapter API Mapping:
- `callWS("neonplan3d/building/get", { plan })` $\rightarrow$ `GET /api/v1/plans/{id}`
- `callWS("neonplan3d/building/save", { building })` $\rightarrow$ `PUT /api/v1/plans/{id}` (with CSRF header and `plans:write` permission guard)
- `callWS("neonplan3d/plans/list")` $\rightarrow$ `GET /api/v1/plans`
- WebSocket listener $\rightarrow$ Connects to `/ws/live`, ingests incoming sensor telemetry, updates `adapter.states[sensor_id]`, and triggers reactive visual pulse / card refresh.

---

## 3. Scope of Vendoring & Component Cleanup

### 3.1 Files to Vendor into `frontend/src/`:
- `geometry/`: `walls.ts`, `cut.ts`, `polygon.ts` (wall thickness offsetting, polygon math, openings).
- `viewer/`: `viewer3d.ts`, `camera.ts`, `shaders.ts`, `walk.ts` (Three.js rendering, orbit/top-down/walkthrough).
- `components/`: `editor.ts`, `room-bar.ts`, `room-panel.ts`, `view3d.ts`.
- `styles.ts` & `themes.ts`: Neon, Blueprint, and Light design tokens.
- `model.ts`: Data schema for floors, rooms, walls, doors, windows, and technical equipment.

### 3.2 Files & Features to Remove:
- `license.ts`, `shop.ts`, `updater.ts`: External licensing, purchase flows, and shop endpoints.
- `fun/`, `fun-packs.ts`, `christmas.ts`, `halloween.ts`, `pets.ts`, `pool.ts`: Non-facility decorative items.
- `voice/`, `timetravel/`: Home Assistant voice pipeline and domestic history replay.
- `domestic furniture`: Sofas, beds, wardrobes, kitchen counters, bathtubs.

### 3.3 Data Center Catalog Additions (`dcim_catalog.ts`):
1. **Server Racks**:
   - 42U Server Enclosure ($600 \times 1000 \times 2000\,\text{mm}$)
   - 48U High-Density Rack ($600 \times 1200 \times 2250\,\text{mm}$)
   - Network / Patch Rack ($800 \times 1000 \times 2000\,\text{mm}$)
2. **Cooling & Environmental**:
   - CRAC Downflow Unit ($1200 \times 900 \times 1950\,\text{mm}$)
   - In-Row Cooling Unit ($300 \times 1000 \times 2000\,\text{mm}$)
   - Thermohygrometer Sensor Node ($120 \times 120 \times 50\,\text{mm}$)
3. **Power Infrastructure**:
   - Modular UPS Cabinet ($800 \times 1000 \times 2000\,\text{mm}$)
   - Floor PDU ($800 \times 800 \times 1800\,\text{mm}$)
   - Backup Diesel Generator ($2500 \times 1400 \times 2200\,\text{mm}$)
4. **Security & Physical Access**:
   - Security IP Dome Camera (go2rtc stream link)
   - Biometric Fingerprint / Access Card Reader
   - Smart Electromagnetic Door Lock
5. **Structured Cabling**:
   - Overhead Cable Tray / Ladder Frame ($400\,\text{mm}$ width, ceiling snap)
   - Raised Floor Cable Pathway

---

## 4. Hard-to-Port Areas & Proposed Solutions

| Challenge | Why it's Hard | Proposed Solution |
|---|---|---|
| **Lit Web Components Build** | NeonPlan 3D uses Lit (`LitElement`). Running raw Lit `.ts` in browser without bundling fails. | **Vite Production & Dev Pipeline**: Use `frontend/package.json` with `vite build` to compile the single clean bundle `editor.bundle.js` into `backend/app/static/dist/`. For development without Node, keep the bundled release checked in and provide `python scripts/build_frontend.py` utilizing the local Node v22 engine. |
| **Home Assistant State Object** | NeonPlan 3D components access `hass.states["sensor.xyz"].state`. | **`ServerMonitsAdapter`**: Implements a standard reactive dictionary. Incoming `/ws/live` messages directly mutate `adapter.states[sensor_id]`, which Lit components observe natively via `requestUpdate()`. |
| **German Hardcoded Strings** | NeonPlan 3D has German fallbacks in several component templates. | **Unified i18n Translation Layer**: Extract strings into clean English (`en.json`) and Indonesian (`id.json`) translation tables loaded by our existing `/api/v1/i18n/{lang}` backend endpoint. |
| **Multi-Floor vs Single Plan Schema** | NeonPlan 3D supports multiple floors in a single building JSON. | **Schema Harmonization**: Store the building JSON (floors, rooms, objects) directly in the `floor_plans.metadata_json` column while maintaining relational rows in `floor_plan_rooms` and `placed_objects` for SQL querying and permission checks. |

---

## 5. Verification & Testing Guard

1. **Browser Smoke Test (`scripts/browser_smoke_test.py`)**:
   - Executed after every change using headless Playwright Chromium.
   - Logs in as admin, loads 3D view, asserts zero console errors / uncaught exceptions, and verifies all toolbar button handlers.
2. **Backend Dialect Suite (`python -m pytest backend/tests/ -v`)**:
   - Ensures no regressions across authentication, RBAC, floor plan persistence, and math utilities.
3. **Manual Click-Through Checklist**:
   - Drawing walls, placing server racks, testing themes, camera modes, and pop-up cards.

