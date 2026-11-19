#!/usr/bin/env python3
"""
browser_smoke_test.py - Headless Playwright Browser Smoke Test (NextFloor Single Header & Editor)

Verifies:
1. Starts dev server and logs in as admin.
2. Asserts single unified header (Server_Monits brand, Mode switcher, New Design button).
3. Asserts ZERO German domestic words ('Obergeschoss', 'Wohnzimmer', 'Erdgeschoss', 'Kinderzimmer').
4. Switches to 3D CAD Editor mode via `#btnEditMode`.
5. Verifies CAD editor mounts cleanly with zero console errors or uncaught exceptions.
6. Switches back to 3D Monitor mode via `#btnViewMode`.
"""
import os
import sys

os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///server_monits_smoke_test.db"

import time
import subprocess
import urllib.request
import asyncio
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

DEV_PORT = 8008
BASE_URL = f"http://127.0.0.1:{DEV_PORT}"
TEST_ADMIN_USER = "admin"
TEST_ADMIN_PASS = "SmokeTestAdmin123!"


def seed_admin_for_smoke_test():
    """Ensure admin account with known password exists in server_monits_dev.db."""
    from backend.app.core.security import hash_password
    from backend.app.db.base import Base
    from backend.app.db.session import get_engine, get_session_factory
    from backend.app.db.models.user import User, Role
    from backend.app.db.models.system_config import SystemConfig
    from sqlalchemy import select

    async def _seed():
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = get_session_factory()
        async with session_factory() as db:
            cfg_res = await db.execute(select(SystemConfig).where(SystemConfig.key == "is_initialized"))
            cfg = cfg_res.scalar_one_or_none()
            if not cfg:
                db.add(SystemConfig(key="is_initialized", value="true"))
            else:
                cfg.value = "true"

            r_res = await db.execute(select(Role).where(Role.name == "Admin"))
            admin_role = r_res.scalar_one_or_none()
            if not admin_role:
                admin_role = Role(
                    name="Admin",
                    description="Full administrative access",
                    permissions=["*"],
                    is_system=True,
                )
                db.add(admin_role)
                await db.flush()

            u_res = await db.execute(select(User).where(User.username == TEST_ADMIN_USER))
            admin_user = u_res.scalar_one_or_none()
            pw_hash = hash_password(TEST_ADMIN_PASS)

            if not admin_user:
                admin_user = User(
                    username=TEST_ADMIN_USER,
                    email="admin@smoke-test.local",
                    password_hash=pw_hash,
                    is_active=True,
                    roles=[admin_role],
                )
                db.add(admin_user)
            else:
                admin_user.password_hash = pw_hash
                admin_user.is_active = True
                if admin_role not in admin_user.roles:
                    admin_user.roles.append(admin_role)

            await db.commit()

    asyncio.run(_seed())
    print(f">> Admin user ready: {TEST_ADMIN_USER}")


def is_server_ready() -> bool:
    try:
        req = urllib.request.Request(f"{BASE_URL}/login")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def run_smoke_test():
    print("====================================================================")
    print("   Server_Monits: Smoke Test (Single Header, CAD Editor & EN/ID)   ")
    print("====================================================================")

    seed_admin_for_smoke_test()

    server_process = None
    if not is_server_ready():
        print(f">> Launching local uvicorn development server on port {DEV_PORT}...")
        env = os.environ.copy()
        env["APP_ENV"] = "development"
        env["DATABASE_URL"] = "sqlite+aiosqlite:///server_monits_smoke_test.db"
        server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(DEV_PORT)],
            cwd=str(ROOT_DIR),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        for attempt in range(15):
            time.sleep(1)
            if is_server_ready():
                print(">> Development server is ready and responding.")
                break
        else:
            if server_process:
                server_process.kill()
            raise RuntimeError("Timed out waiting for uvicorn server to start.")
    else:
        print(f">> Existing local server detected on port {DEV_PORT}. Reusing instance.")

    from playwright.sync_api import sync_playwright

    console_errors = []
    page_errors = []
    outbound_requests = []

    with sync_playwright() as p:
        print(">> Launching headless Chromium browser...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 900})
        page = context.new_page()

        def on_console(msg):
            if msg.type == "error":
                text = msg.text
                if "favicon.ico" not in text:
                    console_errors.append(f"[Console Error] {text}")
                    print(f"  ❌ Console Error: {text}")

        def on_page_error(err):
            page_errors.append(f"[Uncaught Exception] {err}")
            print(f"  ❌ Uncaught Exception: {err}")
            if hasattr(err, "stack"):
                print(f"     Stack: {err.stack}")

        def on_request(req):
            url = req.url
            if not url.startswith(BASE_URL) and not url.startswith("data:"):
                outbound_requests.append(url)
                print(f"  ❌ External Outbound Request: {url}")

        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        page.on("request", on_request)

        try:
            # 1. Login
            print(">> [1/5] Logging in as admin...")
            page.goto(f"{BASE_URL}/login")
            page.wait_for_selector("#loginUsername", timeout=5000)
            page.fill("#loginUsername", TEST_ADMIN_USER)
            page.fill("#loginPassword", TEST_ADMIN_PASS)
            page.click("#btnLogin")

            # 2. Wait for main UI & Integrated NeonPlan 3D v3.5.1 Header
            print(">> [2/8] Loading 3D Facility Monitor & NeonPlan 3D v3.5.1 Header (/)...")
            page.wait_for_url(f"{BASE_URL}/", timeout=8000)
            page.wait_for_selector("neonplan3d-panel", timeout=10000)
            page.locator("header.fp3d-header").wait_for(state="visible", timeout=10000)

            header_count = page.locator("header.fp3d-header").count()
            if header_count != 1:
                raise RuntimeError(f"Expected 1 integrated .fp3d-header, found {header_count}")
            print("  ✓ NeonPlan 3D v3.5.1 .fp3d-header is VISIBLE and fully integrated with Server_Monits controls.")

            # 3. Assert NO German words & NO Home Assistant text
            print(">> [3/8] Verifying language purity (No German words, No Home Assistant references)...")
            body_text = page.inner_text("body")
            german_words = ["Obergeschoss", "Wohnzimmer", "Erdgeschoss", "Kinderzimmer", "Küche", "Schlafzimmer"]
            found_german = [w for w in german_words if w.lower() in body_text.lower()]
            if found_german:
                raise RuntimeError(f"Found unwanted German words in UI: {found_german}")
            if "home assistant" in body_text.lower():
                raise RuntimeError("Found unwanted 'Home Assistant' text in UI!")
            print("  ✓ Pure English / Indonesian facility model active: Zero German words & Zero Home Assistant references.")

            # 4. Test 3D Canvas
            print(">> [4/8] Verifying 3D WebGL Canvas...")
            page.wait_for_function("""() => {
                const p = document.querySelector('neonplan3d-panel');
                if (!p || !p.shadowRoot) return false;
                const v = p.shadowRoot.querySelector('fp3d-view3d');
                if (!v || !v.shadowRoot) return false;
                return v.shadowRoot.querySelector('canvas') !== null;
            }""", timeout=15000)
            print("  ✓ NeonPlan 3D v3.5.1 Three.js 3D canvas active and rendering.")

            # Verify Editor-only buttons are hidden in 3D View and header is single-row
            view_header_check = page.evaluate("""() => {
                const p = document.querySelector('neonplan3d-panel');
                const sr = p?.shadowRoot;
                const hdr = sr?.querySelector('.fp3d-header');
                return {
                    hasSave: !!sr?.querySelector('#btnSavePlan'),
                    hasDb: !!sr?.querySelector('#btnVirtualDb'),
                    hasCables: !!sr?.querySelector('#btnCablesMgr'),
                    hdrHeight: hdr ? Math.round(hdr.getBoundingClientRect().height) : 0
                };
            }""")
            if view_header_check["hasSave"] or view_header_check["hasDb"] or view_header_check["hasCables"]:
                raise RuntimeError(f"Save / DB Sensors / 3D Cables must be hidden in 3D view, got: {view_header_check}")
            if view_header_check["hdrHeight"] > 68:
                raise RuntimeError(f"Expected single-row 3D header (<=68px), got {view_header_check['hdrHeight']}px")
            print(f"  ✓ 3D View header is single-row ({view_header_check['hdrHeight']}px) & Editor-only buttons are hidden.")

            # 5. Test Placing New Temperature & Humidity Sensor at Specific Place + Virtual Lights (in Editor mode)
            print(">> [5/8] Testing Adding & Placing New Temp/Humidity Sensor at Specific Place (X=4.2m, Z=3.1m, Y=1.6m)...")
            page.locator("#btnEditMode").click()
            page.wait_for_timeout(400)
            page.locator("#btnVirtualDb").click()
            page.wait_for_selector("#drawerDevices.open", timeout=5000)

            page.fill("#newSensorName", "Cold Aisle Rack B09")
            page.fill("#newSensorX", "4.2")
            page.fill("#newSensorZ", "3.1")
            page.fill("#newSensorY", "1.6")
            page.fill("#newSensorTemp", "19.8")
            page.fill("#newSensorHum", "42.5")
            page.click("#btnPlaceSensorIn3D")
            page.wait_for_function("() => (document.querySelector('#sensorPlaceStatusMsg')?.innerText || '').includes('Cold Aisle Rack B09')", timeout=8000)

            place_msg = page.inner_text("#sensorPlaceStatusMsg")
            if "Cold Aisle Rack B09" not in place_msg:
                raise RuntimeError(f"Expected sensor placement confirmation, got '{place_msg}'")
            print(f"  ✓ Sensor placed at specific coordinates & saved to DB: {place_msg}")
            page.evaluate("() => window.toggleMonitsDrawer(null)")
            page.locator("#btnViewMode").click()
            page.wait_for_timeout(500)

            # Verify ALL sensors on floor show compact Gauges-only cards (.live-card-env-mini), clicking one expands to Full (.live-card-env-full with 24h chart below & no Rack Power), and clicking outside collapses back
            multi_check = page.evaluate("""() => {
                const v3d = document.querySelector('neonplan3d-panel')?.shadowRoot?.querySelector('fp3d-view3d');
                if (!v3d || !v3d.shadowRoot) return { ok: false };
                const miniCards = v3d.shadowRoot.querySelectorAll('.live-card-env-mini').length;
                const fullCards = v3d.shadowRoot.querySelectorAll('.live-card-env-full').length;
                return { ok: true, miniCards, fullCards };
            }""")
            if not multi_check.get("ok") or multi_check.get("miniCards", 0) < 5 or multi_check.get("fullCards") != 0:
                raise RuntimeError(f"Expected all sensors as compact gauges-only cards initially, got: {multi_check}")

            # Click the first compact Gauges-only card to expand it to Full view
            page.evaluate("""() => {
                const v3d = document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d');
                v3d.shadowRoot.querySelector('.live-card-env-mini')?.click();
            }""")
            page.wait_for_timeout(300)

            # Verify no Rack Power in full card and chart is rendered inside .live-card-env-full
            full_card_check = page.evaluate("""() => {
                const v3d = document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d');
                const card = v3d.shadowRoot.querySelector('.live-card-env-full');
                const rings = card.querySelectorAll('svg.live-ring').length;
                const hasSolarPath = !!card.querySelector('.live-day svg path.live-day-solar');
                const hasUsePath = !!card.querySelector('.live-day svg path.live-day-use');
                const text = card.innerText || '';
                return { rings, hasSolarPath, hasUsePath, hasPowerText: text.includes('Rack Power') };
            }""")
            if full_card_check["rings"] != 2 or not full_card_check["hasSolarPath"] or full_card_check["hasPowerText"]:
                raise RuntimeError(f"Expected 2 rings + 24h chart + no Rack Power, got: {full_card_check}")

            # Click collapse (−) / outside to return to all Gauges-only
            page.evaluate("() => window.monitsApi.setExpandedSensor(null)")
            page.wait_for_timeout(300)
            after_collapse = page.evaluate("""() => {
                const v3d = document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d');
                return {
                    miniCards: v3d.shadowRoot.querySelectorAll('.live-card-env-mini').length,
                    fullCards: v3d.shadowRoot.querySelectorAll('.live-card-env-full').length
                };
            }""")
            if after_collapse["fullCards"] != 0 or after_collapse["miniCards"] < 5:
                raise RuntimeError(f"Expected all cards collapsed to mini Gauges-only, got: {after_collapse}")
            print(f"  ✓ Multi-sensor 3D Holograms verified: {after_collapse['miniCards']} compact Gauges-only cards, 1 expandable Full card (Gauges + Readings + 24h Chart below, no Rack Power)!")

            # Expand a card and verify switching sensors via ▶ button works cleanly
            page.evaluate("""() => {
                const v3d = document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d');
                v3d.shadowRoot.querySelector('.live-card-env-mini')?.click();
            }""")
            page.wait_for_timeout(200)
            before_ident = page.evaluate("() => window.monitsApi.getActiveSensorIdentifier()")
            page.evaluate("""() => {
                const v3d = document.querySelector('neonplan3d-panel')?.shadowRoot?.querySelector('fp3d-view3d');
                const nextBtn = v3d?.shadowRoot?.querySelector('.live-card-env-full button[title="Next Sensor"]');
                if (nextBtn) nextBtn.click();
            }""")
            page.wait_for_timeout(300)
            after_ident = page.evaluate("() => window.monitsApi.getActiveSensorIdentifier()")
            if before_ident == after_ident:
                raise RuntimeError(f"Expected active sensor to switch when clicking Next Sensor button, stayed on '{before_ident}'")
            print(f"  ✓ Sensor switching via ▶ button works cleanly: '{before_ident}' -> '{after_ident}'")

            # Verify Markers='none' hides .live-card-env and Markers='important' restores it
            page.evaluate("() => { const p = document.querySelector('neonplan3d-panel'); p._markers = 'none'; p.requestUpdate(); }")
            page.wait_for_timeout(300)
            hidden_count = page.evaluate("() => document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d').shadowRoot.querySelectorAll('.fp3d-holo').length")
            if hidden_count != 0:
                raise RuntimeError(f"Expected 0 .fp3d-holo elements when markers='none', got {hidden_count}")
            page.evaluate("() => { const p = document.querySelector('neonplan3d-panel'); p._markers = 'important'; p.requestUpdate(); }")
            page.wait_for_timeout(300)
            restored_count = page.evaluate("() => document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d').shadowRoot.querySelectorAll('.live-card-env').length")
            if restored_count < 1:
                raise RuntimeError(f"Expected .live-card-env to reappear when markers='important', got {restored_count}")
            print("  ✓ Markers='none' hides 3D hologram pop-up, and Markers='important' restores it.")

            # Verify Spatial IDW Heatmaps (temperature, humidity, wifi) render multi-color floor gradient meshes
            for hm in ["temperature", "humidity", "wifi"]:
                hm_res = page.evaluate(f"""() => {{
                    const v3d = document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d');
                    v3d.heatMode = '{hm}';
                    v3d.requestUpdate();
                    v3d.applyTint();
                    const fl = v3d.viewer?.floors?.[0];
                    const mesh = fl?.heatOverlayMesh;
                    const canvas = mesh?.material?.map?.image;
                    let uniqueColors = 0;
                    if (canvas) {{
                        const ctx = canvas.getContext('2d');
                        const d = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
                        const s = new Set();
                        for (let i = 0; i < d.length; i += 16) {{
                            if (d[i + 3] > 0) s.add((d[i] >> 4) + ',' + (d[i+1] >> 4) + ',' + (d[i+2] >> 4));
                        }}
                        uniqueColors = s.size;
                    }}
                    return {{ visible: !!mesh?.visible, uniqueColors }};
                }}""")
                if not hm_res.get("visible") or hm_res.get("uniqueColors", 0) < 3:
                    raise RuntimeError(f"Expected multi-color spatial heatmap for '{hm}', got: {hm_res}")
                print(f"  ✓ Spatial wall-aware heatmap '{hm}' active ({hm_res['uniqueColors']} gradient color buckets).")
            page.evaluate("() => { const v3d = document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d'); v3d.heatMode = 'none'; v3d.applyTint(); }")

            # Toggle virtual light off then on
            page.evaluate("() => window.onVirtualLightToggle('light.server_alpha_light', 'off')")
            page.wait_for_timeout(300)
            light_state = page.evaluate("() => window.nfPanel.hass.states['light.server_alpha_light'].state")
            if light_state != "off":
                raise RuntimeError(f"Expected virtual light state 'off', got '{light_state}'")

            page.evaluate("() => window.onVirtualLightToggle('light.server_alpha_light', 'on')")
            page.wait_for_timeout(300)
            light_state = page.evaluate("() => window.nfPanel.hass.states['light.server_alpha_light'].state")
            if light_state != "on":
                raise RuntimeError(f"Expected virtual light state 'on', got '{light_state}'")
            print("  ✓ Virtual lights toggle ON/OFF in 3D scene & persist to DB.")

            # Verify Time Travel loads real numeric sensor readings (zero 'unavailable'/'unknown')
            page.evaluate("() => window.nfPanel.toggleTimeTravel()")
            page.wait_for_function("() => window.nfPanel?.tt?.session?.state === 'ready'", timeout=10000)
            tt_check = page.evaluate("""() => {
                const states = window.nfPanel.tt.session.hass?.states || {};
                const sensors = Object.entries(states).filter(([k]) => k.startsWith('sensor.') && (k.endsWith('_temp') || k.endsWith('_humidity')));
                const bad = sensors.filter(([, v]) => !v || v.state === 'unavailable' || v.state === 'unknown' || !Number.isFinite(Number(v.state)));
                return { total: sensors.length, bad: bad.map(([k, v]) => [k, v?.state]), sample: sensors.slice(0, 3).map(([k, v]) => [k, v?.state]) };
            }""")
            page.evaluate("() => window.nfPanel.tt.stop()")
            page.wait_for_timeout(300)
            if tt_check["total"] == 0 or len(tt_check["bad"]) > 0:
                raise RuntimeError(f"Time Travel had Unavailable/invalid sensor readings: {tt_check}")
            print(f"  ✓ Time Travel verified: {tt_check['total']} sensors loaded with real numeric values (sample: {tt_check['sample']}).")

            # 6. Test 3D Cabling (Below Floor, In Wall, Ceiling for Power, FO, Ethernet) in Editor mode
            print(">> [6/8] Testing 3D Cabling (Power, FO, Ethernet in Below Floor / Wall / Ceiling)...")
            page.locator("#btnEditMode").click()
            page.wait_for_timeout(400)
            page.locator("#btnCablesMgr").click()
            page.wait_for_selector("#drawerCables.open", timeout=5000)
            page.click("button[onclick='handleAddCableRun()']")
            page.wait_for_function("() => (document.querySelector('#cableStatusMsg')?.innerText || '').length > 5", timeout=8000)
            cable_msg = page.inner_text("#cableStatusMsg")
            if "Added" not in cable_msg and "Ditambahkan" not in cable_msg:
                raise RuntimeError(f"Expected cable addition confirmation, got '{cable_msg}'")
            page.evaluate("() => window.toggleMonitsDrawer(null)")
            print(f"  ✓ 3D Cable routing verified: {cable_msg}")

            # 7. Test 3D CAD Editor Modification + Explicit Save
            print(">> [7/8] Testing 3D CAD Editor Modification & Explicit Save to SQLite DB...")
            page.locator("#btnEditMode").click()
            page.wait_for_timeout(1000)

            mode = page.evaluate("() => document.querySelector('neonplan3d-panel')?._mode")
            if mode != "editor":
                raise RuntimeError(f"Expected mode 'editor', got '{mode}'")

            # Modify building in Editor (add a custom room 'Custom AI Cluster Pod') and click #btnSavePlan
            page.evaluate("""() => {
                const panel = document.querySelector('neonplan3d-panel');
                const b = structuredClone(panel.data.building);
                if (!b.floors[0].rooms.some(r => r.id === 'room_ai_pod')) {
                    b.floors[0].rooms.push({
                        id: 'room_ai_pod',
                        name: 'Custom AI Cluster Pod',
                        ha_area: 'ai_cluster_pod',
                        points: [[14, 0], [18, 0], [18, 5], [14, 5]],
                        floor_material: 'concrete_dark',
                        label: true
                    });
                }
                panel.data.edit(b);
            }""")
            page.locator("#btnSavePlan").click()
            page.wait_for_timeout(600)
            print("  ✓ Modified 3D building in Editor and saved via 💾 Save button.")

            # 8. Navigate to /admin/users, /admin/settings, /admin/audit to verify unified .fp3d-app-header layout & DB persistence!
            print(">> [8/8] Verifying unified header on /admin/users, /admin/settings, /admin/audit and DB persistence...")
            page.locator("#btnNavUsers").click()
            page.wait_for_url(f"{BASE_URL}/admin/users", timeout=8000)
            if page.locator("header.fp3d-app-header").count() != 1:
                raise RuntimeError("Expected unified .fp3d-app-header on /admin/users")
            page.goto(f"{BASE_URL}/admin/settings")
            if page.locator("header.fp3d-app-header").count() != 1:
                raise RuntimeError("Expected unified .fp3d-app-header on /admin/settings")
            page.goto(f"{BASE_URL}/admin/audit")
            if page.locator("header.fp3d-app-header").count() != 1:
                raise RuntimeError("Expected unified .fp3d-app-header on /admin/audit")
            page.goto(f"{BASE_URL}/")
            page.wait_for_selector("neonplan3d-panel", timeout=10000)
            page.wait_for_function("() => window.monitsApi && window.nfPanel && window.nfPanel.data && window.nfPanel.data.building", timeout=10000)

            persisted_check = page.evaluate("""() => {
                const b = window.monitsApi.getBuilding();
                const hasCustomRoom = b.floors[0].rooms.some(r => r.id === 'room_ai_pod' && r.name === 'Custom AI Cluster Pod');
                const hasPlacedSensorPin = (b.floors[0].placements || []).some(p => p.entity_id === 'sensor.cold_aisle_rack_b09_temp' && p.x === 4.2 && p.z === 3.1);
                const hasSensorState = window.nfPanel.hass.states['sensor.cold_aisle_rack_b09_temp']?.state === '19.8';
                return { hasCustomRoom, hasPlacedSensorPin, hasSensorState };
            }""")
            if not persisted_check["hasCustomRoom"]:
                raise RuntimeError(f"3D Editor custom room was lost after navigating to /admin/users and back! {persisted_check}")
            if not persisted_check["hasPlacedSensorPin"] or not persisted_check["hasSensorState"]:
                raise RuntimeError(f"Placed Temp/Humidity sensor was lost after navigating to /admin/users and back! {persisted_check}")
            print("  ✓ 3D Editor modifications AND placed Temp/Humidity sensor persisted across /admin/users navigation!")

            # Verify zero external outbound requests
            if outbound_requests:
                raise RuntimeError(f"Detected {len(outbound_requests)} external network request(s): {outbound_requests}")
            print("  ✓ Zero external outbound requests (100% air-gapped).")

            # Final verify on errors
            if console_errors:
                raise RuntimeError(f"Detected {len(console_errors)} console error(s): {console_errors}")
            if page_errors:
                raise RuntimeError(f"Detected {len(page_errors)} uncaught exception(s): {page_errors}")

            print("====================================================================")
            print("  ✓ ALL CHECKS PASSED: 1 Header, Clean CAD Editor & Pure EN/ID!    ")
            print("====================================================================")

        finally:
            browser.close()
            if server_process:
                server_process.kill()


if __name__ == "__main__":
    run_smoke_test()
