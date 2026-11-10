# Open Source References & Prior Art Review

**Document Version:** 1.1.0  
**Date:** 2026-11-10  
**Scope:** Architecture, UI/UX aesthetics, DCIM schemas, Wi-Fi survey mechanics, exact files inspected, and licensing compliance review across open-source repositories and industry benchmarks.

---

## 1. Compliance Policy & Code Reuse Rules

1. **Permissive Licenses (MIT / Apache-2.0 / BSD)**:
   - Concepts, data structures, and styling tokens may be referenced and adapted.
   - Reused tokens, structures, and styling patterns retain attribution and copyright notices in `THIRD_PARTY_NOTICES.md`.
2. **Copyleft Licenses (GPL-2.0 / AGPL-3.0)**:
   - Implemented from general algorithms, no code copied.
   - Studied strictly for mathematical concepts (e.g. Inverse Distance Weighting interpolation), survey workflows, and data structures. Clean-room implemented in custom Python / TypeScript.
3. **Proprietary Commercial Benchmarks (Ekahau)**:
   - Conceptual reference only (wall attenuation modeling, heat map color gradients, AP coverage planning).

---

## 2. Reference Project Matrix & Files Read

| Project | Repository / URL | Exact License | Role in Platform | Files Actually Read | Code Copied? |
|---|---|---|---|---|---|
| **NeonPlan 3D** | [`Mastershort/neonplan3d`](https://github.com/Mastershort/neonplan3d) | **MIT License** | Primary 3D UI reference: neon aesthetic, floating glassmorphism toolbars, glowing edge shaders, pop-up live KPI cards (modeled after solar/energy cards), on-demand render-on-change loop for low-power wall tablets. | `LICENSE`, `README.md`, `frontend/src/styles.ts`, `frontend/src/card.ts`, `frontend/src/solar.ts`, `frontend/src/energy.ts`, `frontend/src/components/room-panel.ts`. | Reused styling tokens & pop-up card structure; attributed in `THIRD_PARTY_NOTICES.md`. |
| **NextFloor** | [`therealMRBK/NextFloor`](https://github.com/therealMRBK/NextFloor) | **MIT License** | Complete 3D CAD visualization & editor engine: multi-floor stacked views, wall/room polygon drawing, corner vertex snapping, door/window cuts, energy flow pathways, climate heatmaps, weather simulation, and 3D print export. 100% local operation without cloud dependence. | `LICENSE`, `README.md`, `CLAUDE.md`, `frontend/build.mjs`, `frontend/src/i18n.ts`, `frontend/src/panel.ts`, `frontend/src/features.ts`, `preview/index.html`. | Integrated frontend engine with `Server_Monits` adapter; MIT license & attribution in `THIRD_PARTY_NOTICES.md`. |
| **NetBox** | [`netbox-community/netbox`](https://github.com/netbox-community/netbox) | **Apache-2.0** | Phase 5 reference: DCIM data schema standard for rack elevation (42U/48U), front vs rear rack faces, device U-heights, structured cabling paths, and patch panels. | `LICENSE.txt`, `NOTICE`, `README.md`, `netbox/dcim/models/racks.py`, `devices.py`. | Implemented from general algorithms, no code copied. |
| **Rackula** | [`RackulaLives/Rackula`](https://github.com/RackulaLives/Rackula) | **MIT License** | Phase 5 reference: 2D interactive rack layout designer, drag-and-drop unit slot snapping (1U/2U/4U), capacity visualization (occupied vs free rack units). | `LICENSE`, `README.md`, `package.json`, `svelte.config.js`. | Implemented from general algorithms, no code copied. |
| **Python WiFi Survey Heatmap** | [`jantman/python-wifi-survey-heatmap`](https://github.com/jantman/python-wifi-survey-heatmap) | **AGPL-3.0** | Phase 4 reference: Linux wireless survey workflow (BSSID, RSSI, channel, frequency, band recording) and 2D Inverse Distance Weighting (IDW) interpolation over floor plans. | `LICENSE`, `README.rst`, `setup.cfg`, `wifi_survey_heatmap/` (survey structures). | Implemented from general algorithms, no code copied. |
| **WifiHeatmap** | [`weimens/wifiheatmap`](https://github.com/weimens/wifiheatmap) | **GPL-2.0** | Phase 4 reference: Survey point sampling patterns and signal strength dBm color grading (Green > -65 dBm, Yellow -65 to -75 dBm, Red < -80 dBm). | `LICENSE`, `README.md`, `heatmap.cpp`, `heatmap.h`. | Implemented from general algorithms, no code copied. |
| **Ekahau AI Pro** | [Ekahau Product Overview](https://www.ekahau.com/products/ekahau-connect/ai-pro/) | **Proprietary** | Phase 4 concept: Predictive attenuation dB loss per material (drywall 3dB, concrete 12dB, metal rack 18dB), signal propagation contours. | Product specification and documentation. | Conceptual reference only; no code copied. |

---

## 3. Key Findings & Design Adaptations

### 3.1 NeonPlan 3D (`Mastershort/neonplan3d`)
- **Visual Aesthetic & Styling Tokens**:
  - Deep space background (`--fp3d-bg: #070b14`, `--fp3d-bg2: #0d1424`), glassmorphic chrome (`--fp3d-chrome: rgba(14, 21, 38, 0.86)`), cyan accent (`--fp3d-accent: #37e0ff`), border lines (`--fp3d-line: rgba(120, 170, 255, 0.16)`).
  - Segmented pill controls (`.fp3d-seg`) and action buttons with focus visibility outlines.
- **Pop-Up Equipment Cards (Solar / Energy Card Pattern)**:
  - Header with glowing icon badge, device name, and live status pill.
  - KPI tiles with glowing readout numbers.
  - Inline SVG mini sparklines showing trends.
  - Action shortcuts (Focus 3D, Elevation view).
  - **Prerequisite Flag**: All unlinked equipment displays an explicit `[ DEMO DATA ]` badge so placeholder numbers are never mistaken for live telemetry.
- **On-Demand Rendering for Low-Power Devices**:
  - Render loop executes strictly on interaction / dirty flag (`camera moved`, `object dragged`, `telemetry update arrived`) to support wall tablets and low-power hardware.
- **Data Center Specialization**:
  - Strictly technical data center hardware (Server Racks, CRAC units, UPS, Generator, Sensors, Cameras) with **strictly zero domestic decorative objects** (no dogs, cats, or trees).

### 3.2 NetBox & Rackula (`netbox-community/netbox`, `RackulaLives/Rackula`)
- **Rack Units (RU) Precision**:
  - 1U standard = 1.75 inches = 0.04445 meters.
  - Standard rack height = 42U (~2.0m) or 48U (~2.25m); depth = 1.0m to 1.2m; width = 0.6m or 0.8m.
  - Front and rear equipment faces modeled independently.

### 3.3 Wi-Fi Survey Prior Art (`jantman/python-wifi-survey-heatmap`, `weimens/wifiheatmap`, Ekahau)
- **Linux Survey Tools**:
  - Standalone Python survey agent CLI capturing BSSID beacons without requiring root permissions.
- **Obstacle & Wall Attenuation**:
  - Inverse Distance Weighting (IDW) spatial interpolation calculated per room polygon with raycast boundary obstruction checks.
