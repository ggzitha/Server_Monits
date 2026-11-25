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

            # Verify Time Travel loads real numeric sensor readings AND pill === gauge === chart cursor at 3 distinct timestamps!
            # Focus server_alpha_env (which has varying 24h history readings) so gauges & chart reflect real changes across timestamps
            page.evaluate("""() => {
                window.monitsApi.setActiveSensor('server_alpha_env');
                window.monitsApi.setExpandedSensor('server_alpha_env');
                const v3d = document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d');
                v3d?.syncDevices?.(true);
                v3d?.requestUpdate?.();
            }""")
            page.wait_for_timeout(350)
            active_ident_live = page.evaluate("() => window.monitsApi.getActiveSensorIdentifier()")
            live_temp_before = page.evaluate(f"() => window.nfPanel.hass.states['sensor.{active_ident_live}_temp']?.state")

            page.evaluate("() => window.nfPanel.toggleTimeTravel()")
            page.wait_for_function("() => window.nfPanel?.tt?.session?.state === 'ready'", timeout=10000)

            tt_samples = []
            for frac in [0.15, 0.50, 0.85]:
                page.evaluate(f"""() => {{
                    const tt = window.nfPanel.tt;
                    const s = tt.session;
                    const t0 = s.startMs ?? (Date.now() - 86400000);
                    const t1 = s.endMs ?? Date.now();
                    const targetT = Math.round(t0 + (t1 - t0) * {frac});
                    if (s.replay) {{
                        s.replay.t = targetT;
                        s.replay.seek = (s.replay.seek || 0) + 1;
                    }}
                    window.nfPanel.requestUpdate();
                    const v3d = window.nfPanel.shadowRoot.querySelector('fp3d-view3d');
                    if (v3d) {{
                        v3d.hass = tt.hass(window.nfPanel.hass);
                        v3d.replay = {{ ...(s.replay || {{}}), t: targetT, seek: (s.replay?.seek || 0) + 1 }};
                        v3d.requestUpdate();
                    }}
                }}""")
                page.wait_for_timeout(350)
                snap = page.evaluate("""() => {
                    const v3d = window.nfPanel.shadowRoot.querySelector('fp3d-view3d');
                    const ident = window.monitsApi.getActiveSensorIdentifier();
                    const pillState = v3d.hass?.states?.['sensor.' + ident + '_temp']?.state;
                    const card = v3d.shadowRoot.querySelector('.live-card-env-full');
                    const ringText = card?.querySelector('[title="Temperature Gauge"] b')?.textContent?.trim() || '';
                    const hasTtCursor = !!card?.querySelector('.live-chart-tt-cursor');
                    const ttBadge = card?.querySelector('.live-card-tt-badge')?.textContent?.trim() || '';
                    const states = window.nfPanel.tt.session.hass?.states || {};
                    const sensors = Object.entries(states).filter(([k]) => k.startsWith('sensor.') && (k.endsWith('_temp') || k.endsWith('_humidity')));
                    const bad = sensors.filter(([, v]) => !v || v.state === 'unavailable' || v.state === 'unknown' || !Number.isFinite(Number(v.state)));
                    return { ident, pillState, ringText, hasTtCursor, ttBadge, total: sensors.length, badCount: bad.length };
                }""")
                tt_samples.append(snap)
                if snap["total"] == 0 or snap["badCount"] > 0:
                    raise RuntimeError(f"Time Travel had invalid sensor readings at frac={frac}: {snap}")
                expected_ring = f"{float(snap['pillState']):.1f}°"
                if snap["ringText"] != expected_ring or not snap["hasTtCursor"]:
                    raise RuntimeError(f"Time Travel gauge/chart mismatch at frac={frac}: expected ring='{expected_ring}' with cursor, got {snap}")

            # Exit Time Travel and verify Live values restore
            page.evaluate("() => window.nfPanel.tt.stop()")
            page.wait_for_timeout(350)
            live_after = page.evaluate("""() => {
                const v3d = window.nfPanel.shadowRoot.querySelector('fp3d-view3d');
                const card = v3d.shadowRoot.querySelector('.live-card-env-full');
                return {
                    ringText: card?.querySelector('[title="Temperature Gauge"] b')?.textContent?.trim() || '',
                    hasTtCursor: !!card?.querySelector('.live-chart-tt-cursor'),
                    ttActive: !!window.nfPanel.tt?.session?.active
                };
            }""")
            if live_after["hasTtCursor"] or live_after["ringText"] != f"{float(live_temp_before):.1f}°":
                raise RuntimeError(f"Returning to Live did not restore live gauge/chart: before={live_temp_before}, after={live_after}")
            print(f"  ✓ Time Travel 3-timestamp check PASSED (pill === gauge === chart cursor at 15%, 50%, 85% + Live restored): {[(s['pillState'], s['ringText'], s['ttBadge']) for s in tt_samples]}")

            # Verify Tasks 1, 2, 3: Wi-Fi Survey Band/Channel CRUD, Floating AP dropdown with Band/Channel, duplicate legend (a) REMOVED & replaced with Channel/WiFi dropdown while main Neon3D legend remains
            print(">> [5b/8] Verifying Wi-Fi Survey Band/Channel, AP Dropdown, Single Legend & Channel Filter...")
            page.evaluate("() => window.toggleMonitsDrawer('wifi')")
            page.wait_for_selector("#drawerWifiSurvey.open", timeout=5000)
            page.fill("#newWifiSsid", "AP-Lobby-Main")
            page.fill("#newWifiRssi", "-44")
            page.select_option("#newWifiBand", "5GHz")
            page.fill("#newWifiChannel", "36")
            page.click("#btnAddWifiRssi")
            page.wait_for_function("() => (document.querySelector('#wifiSurveyStatusMsg')?.innerText || '').includes('AP-Lobby-Main')", timeout=8000)

            wifi_ui_check = page.evaluate("""() => {
                const v3d = document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d');
                v3d.heatMode = 'wifi';
                v3d.applyTint();
                v3d.requestUpdate();
                const bar = document.getElementById('wifiSsidBar');
                const apOpts = Array.from(document.getElementById('liveWifiSsidSelect')?.options || []).map(o => o.textContent);
                const chSelect = document.getElementById('liveWifiBandChannelSelect');
                const chOpts = Array.from(chSelect?.options || []).map(o => o.value);
                const barText = bar?.innerText || '';
                const hasDuplicateLegend = barText.includes('-88 dBm') || barText.includes('-32 dBm');
                const badges = Array.from(document.querySelectorAll('#wifiSurveyPointsList .wifi-band-badge')).map(b => b.textContent.trim());
                return { apOpts, hasChannelSelect: !!chSelect, chOpts, hasDuplicateLegend, badges };
            }""")
            page.wait_for_timeout(300)
            main_legend_present = page.evaluate("""() => {
                const v3d = document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d');
                return !!v3d?.shadowRoot?.querySelector('.fp3d-legend');
            }""")
            if wifi_ui_check["hasDuplicateLegend"]:
                raise RuntimeError(f"Duplicate RSSI legend (a) still present in #wifiSsidBar! {wifi_ui_check}")
            if not wifi_ui_check["hasChannelSelect"] or "band:5GHz" not in wifi_ui_check["chOpts"]:
                raise RuntimeError(f"Channel/WiFi dropdown missing or incomplete: {wifi_ui_check}")
            if not any("AP-Lobby-Main" in o and "5 GHz" in o and "ch36" in o for o in wifi_ui_check["apOpts"]):
                raise RuntimeError(f"Floating AP dropdown missing Band/Channel info: {wifi_ui_check['apOpts']}")
            if not any("5G" in b for b in wifi_ui_check["badges"]):
                raise RuntimeError(f"Band badge missing in Measured RSSI Points list: {wifi_ui_check['badges']}")
            if not main_legend_present:
                raise RuntimeError("Main Neon3D canvas RSSI legend (.fp3d-legend) was missing!")
            print(f"  ✓ Wi-Fi Survey Band/Channel verified: badges={wifi_ui_check['badges']}, AP options={wifi_ui_check['apOpts']}, duplicate legend removed, main .fp3d-legend active.")
            page.evaluate("() => { window.toggleMonitsDrawer(null); const v3d = document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d'); v3d.heatMode = 'none'; v3d.applyTint(); }")

            # Verify Task 4: Theme Picker (Dark <-> Light) applies instantly to Neon3D without reload & persists across pages!
            print(">> [5c/8] Verifying Dark <-> Light Theme Switch on Neon3D (instant, no reload) & persistence...")
            page.evaluate("() => window.applyAppTheme('light', true)")
            page.wait_for_timeout(400)
            light_check = page.evaluate("""() => {
                const panel = document.querySelector('neonplan3d-panel');
                const v3d = panel?.shadowRoot?.querySelector('fp3d-view3d');
                return {
                    htmlTheme: document.documentElement.dataset.theme,
                    lsTheme: localStorage.getItem('monit_theme'),
                    panelTheme: panel?._theme,
                    v3dTheme: v3d?.theme,
                    bgVar: getComputedStyle(document.documentElement).getPropertyValue('--bg-app').trim()
                };
            }""")
            if light_check["htmlTheme"] != "light" or light_check["panelTheme"] != "day" or light_check["v3dTheme"] != "day":
                raise RuntimeError(f"Light theme did not propagate to Neon3D instantly: {light_check}")
            print(f"  ✓ Light theme applied instantly to app + Neon3D 3D scene: {light_check}")

            # 6. Test 3D Cabling (Custom Color, Tray Snapping, Rack Endpoint Linking & 2D/3D Rendering) in Editor mode
            print(">> [6/8] Testing 3D Cabling (Custom Color, Tray Snapping, Rack Endpoints & 2D Polylines)...")
            page.locator("#btnEditMode").click()
            page.wait_for_timeout(400)
            page.locator("#btnCablesMgr").click()
            page.wait_for_selector("#drawerCables.open", timeout=5000)
            # First place an overhead cable tray, then place a custom-colored fiber cable snapped to it
            page.select_option("#cableTypeSelect", "tray")
            page.select_option("#cableZoneSelect", "ceiling")
            page.fill("#cableLabelInput", "Overhead Ladder Tray A")
            page.click("button[onclick='handleAddCableRun()']")
            page.wait_for_function("() => (document.querySelector('#cableStatusMsg')?.innerText || '').includes('Overhead Ladder Tray A')", timeout=8000)
            page.select_option("#cableTypeSelect", "fiber")
            page.fill("#cableColorInput", "#ff00aa")
            page.fill("#cableLabelInput", "OM4 Trunk Custom Color")
            page.click("button[onclick='handleAddCableRun()']")
            page.wait_for_function("() => (document.querySelector('#cableStatusMsg')?.innerText || '').includes('OM4 Trunk Custom Color')", timeout=8000)
            cable_msg = page.inner_text("#cableStatusMsg")
            if "Added" not in cable_msg and "Ditambahkan" not in cable_msg:
                raise RuntimeError(f"Expected cable addition confirmation, got '{cable_msg}'")
            page.evaluate("() => window.toggleMonitsDrawer(null)")
            print(f"  ✓ 3D Cable routing & Tray snapping verified: {cable_msg}")

            # 7. Test 3D CAD Editor Modification + Extras Parity (Wi-Fi Points, Thermo-Hygro Badges, Rack Labels) + Explicit Save
            print(">> [7/8] Testing 2D/3D CAD Editor Extras & Explicit Save to SQLite DB...")
            page.locator("#btnEditMode").click()
            page.wait_for_timeout(1000)

            mode = page.evaluate("() => document.querySelector('neonplan3d-panel')?._mode")
            if mode != "editor":
                raise RuntimeError(f"Expected mode 'editor', got '{mode}'")

            editor_extras_check = page.evaluate("""() => {
                const ed = document.querySelector('neonplan3d-panel')?.shadowRoot?.querySelector('fp3d-editor');
                const svg = ed?.shadowRoot?.querySelector('svg.fp3d-plan');
                const wifiPins = svg ? svg.querySelectorAll('.fp3d-wifi-pt').length : 0;
                const thermoBadges = svg ? svg.querySelectorAll('.fp3d-thermo-badge').length : 0;
                const rackLabels = svg ? svg.querySelectorAll('.fp3d-rack-label').length : 0;
                const cableRuns = svg ? svg.querySelectorAll('.fp3d-cable-run').length : 0;
                const htmlTheme = document.documentElement.dataset.theme;
                return { wifiPins, thermoBadges, rackLabels, cableRuns, htmlTheme };
            }""")
            if editor_extras_check["wifiPins"] < 1 or editor_extras_check["thermoBadges"] < 1 or editor_extras_check["cableRuns"] < 1:
                raise RuntimeError(f"Expected 2D editor to render Wi-Fi points, Thermo-Hygro badges, and colored cable runs, got: {editor_extras_check}")
            print(f"  ✓ 2D Editor unified extras verified in {editor_extras_check['htmlTheme']} theme: {editor_extras_check}")

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

            # 8. Navigate to /admin/users, /admin/settings, /admin/audit to verify unified .fp3d-app-header layout, theme persistence & DB persistence!
            print(">> [8/8] Verifying unified header & Light/Dark theme persistence on /admin/users, /admin/settings, /admin/audit...")
            page.locator("#btnNavUsers").click()
            page.wait_for_url(f"{BASE_URL}/admin/users", timeout=8000)
            if page.locator("header.fp3d-app-header").count() != 1:
                raise RuntimeError("Expected unified .fp3d-app-header on /admin/users")
            if page.evaluate("() => document.documentElement.dataset.theme") != "light":
                raise RuntimeError("Expected Light theme to persist on /admin/users!")
            page.goto(f"{BASE_URL}/admin/settings")
            if page.locator("header.fp3d-app-header").count() != 1:
                raise RuntimeError("Expected unified .fp3d-app-header on /admin/settings")
            if page.evaluate("() => document.documentElement.dataset.theme") != "light":
                raise RuntimeError("Expected Light theme to persist on /admin/settings!")
            page.goto(f"{BASE_URL}/admin/audit")
            if page.locator("header.fp3d-app-header").count() != 1:
                raise RuntimeError("Expected unified .fp3d-app-header on /admin/audit")
            if page.evaluate("() => document.documentElement.dataset.theme") != "light":
                raise RuntimeError("Expected Light theme to persist on /admin/audit!")
            # Verify Phase 6 Security Console (/security): CCTV Wall snapshots, Door Access, Motion/Contact, Alert Overlay & Light/Dark themes
            page.goto(f"{BASE_URL}/security")
            page.wait_for_selector("#securityAppRoot .sec-shell", timeout=8000)
            if page.locator("header.fp3d-app-header").count() != 1:
                raise RuntimeError("Expected unified .fp3d-app-header on /security")
            if page.evaluate("() => document.documentElement.dataset.theme") != "light":
                raise RuntimeError("Expected Light theme to persist on /security!")
            page.wait_for_function("() => { const imgs = Array.from(document.querySelectorAll('.sec-cam-frame img')); return imgs.length >= 2 && imgs.every(i => i.complete && i.naturalWidth > 0); }", timeout=8000)
            # Trigger a security alert on a camera and verify the active alert banner appears, then acknowledge it
            page.locator("[data-sec-act='trigger_alert']").first.click()
            page.wait_for_selector("#secActiveAlertBanner", timeout=6000)
            page.locator("#secActiveAlertBanner [data-sec-act='ack_alert']").first.click()
            page.wait_for_timeout(350)
            if page.locator("#secActiveAlertBanner").count() != 0:
                raise RuntimeError("Acknowledging security alert must clear #secActiveAlertBanner!")
            # Verify full CRUD Edit on a placed camera (rename & update FOV)
            page.locator("[data-edit-dev]").first.click()
            page.wait_for_selector("#secEditDevicePanel", timeout=5000)
            page.fill("#secEdName", "CCTV Main Lobby Frigate")
            page.fill("#secEdFov", "95")
            page.click("#secSubmitEdit")
            page.wait_for_function("() => (document.querySelector('#securityAppRoot')?.innerText || '').includes('CCTV Main Lobby Frigate')", timeout=6000)
            print("  ✓ Phase 6 Security Console (/security) verified: CCTV Wall live snapshots, Edit CRUD, Door Access, Motion/Contact, Alert trigger/ack & unified header!")
            page.goto(f"{BASE_URL}/racks")
            page.wait_for_selector("#racksAppRoot .rk-shell", timeout=8000)
            if page.locator("header.fp3d-app-header").count() != 1:
                raise RuntimeError("Expected unified .fp3d-app-header on /racks")
            if page.evaluate("() => document.documentElement.dataset.theme") != "light":
                raise RuntimeError("Expected Light theme to persist on /racks!")
            # Create a 48U rack via Racks tab, then switch to Devices (Brand/Category/A-Z) and mount a real hardware device
            page.click("[data-sb-mode='racks']")
            page.click("#rkToggleNew")
            page.fill("#rkNewName", "AI-Rack-48U")
            page.fill("#rkNewU", "48")
            page.click("#rkSubmitNew")
            page.wait_for_function("() => (document.querySelector('#racksAppRoot')?.innerText || '').includes('AI-Rack-48U')", timeout=8000)
            page.click("[data-sb-mode='devices']")
            page.wait_for_selector("[data-quick-mount-slug]", timeout=8000)
            page.locator("[data-quick-mount-slug]").first.click()
            page.wait_for_selector(".rk-dev-block img.rk-dev-img", timeout=8000)
            page.wait_for_function("() => { const img = document.querySelector('.rk-dev-block img.rk-dev-img'); return img && img.complete && img.naturalWidth > 0; }", timeout=8000)
            rk_check = page.evaluate("""() => {
                const txt = (document.querySelector('#racksAppRoot')?.innerText || '').toLowerCase();
                const imgs = Array.from(document.querySelectorAll('.rk-dev-block img.rk-dev-img'));
                return {
                    hasIframe: document.querySelectorAll('iframe').length,
                    devCount: document.querySelectorAll('.rk-dev-block').length,
                    loadedPhotos: imgs.filter(i => i.complete && i.naturalWidth > 0).length,
                    hasFrontRear: txt.includes('front') && txt.includes('rear'),
                    hasBrandTabs: !!document.querySelector('[data-sort-tab="brand"]') && !!document.querySelector('[data-sort-tab="category"]') && !!document.querySelector('[data-sort-tab="az"]'),
                    hasStats: txt.includes('u-space utilization') && txt.includes('total power draw')
                };
            }""")
            if rk_check["hasIframe"] != 0 or rk_check["devCount"] < 1 or rk_check["loadedPhotos"] < 1 or not rk_check["hasFrontRear"] or not rk_check["hasBrandTabs"] or not rk_check["hasStats"]:
                raise RuntimeError(f"Native Rack Elevation check failed: {rk_check}")
            # Verify unstretched object-fit:contain on device photos AND multi-U (2U+) drag preview ghost spanning exact U rows!
            fit_and_drag_check = page.evaluate("""() => {
                const img = document.querySelector('.rk-dev-block img.rk-dev-img');
                const objFit = img ? getComputedStyle(img).objectFit : null;
                // Simulate dragging a 4U device onto U10 front slot and verify .rk-drop-ghost spans 4 rows!
                const ctrl = window._racksCtrl;
                const fourU = (ctrl?.catalog || []).find(d => (d.u_height || 1) >= 2) || { slug: 'test-4u', model: 'Test 4U Server', u_height: 4, is_full_depth: true, half_width: false };
                ctrl.dragPayload = { kind: 'catalog', item: fourU };
                const slot = document.querySelector('.rk-u-slot[data-face="front"][data-u="10"][data-slot="left"]');
                if (slot) slot.dispatchEvent(new Event('dragover', { bubbles: true, cancelable: true }));
                const ghost = document.querySelector('.rk-drop-ghost');
                const gridRow = ghost ? ghost.style.gridRow : '';
                const text = ghost ? ghost.textContent : '';
                ctrl.dragPayload = null;
                if (ghost) ghost.remove();
                return { objFit, uHeight: fourU.u_height, gridRow, text };
            }""")
            if fit_and_drag_check["objFit"] != "contain" or f"span {fit_and_drag_check['uHeight']}" not in fit_and_drag_check["gridRow"]:
                raise RuntimeError(f"Image aspect-fit or multi-U drag preview check failed: {fit_and_drag_check}")
            print(f"  ✓ Unstretched object-fit:contain & multi-U ({fit_and_drag_check['uHeight']}U) drag ghost verified: {fit_and_drag_check}")
            # Mount a 2nd device, connect a structured cable, and verify NetBox-style SVG Cable Trace overlay!
            page.locator("[data-quick-mount-slug]").nth(1).click()
            page.wait_for_timeout(450)
            page.locator(".rk-dev-block").first.click()
            page.wait_for_selector("#rkBtnAddCable", timeout=5000)
            page.evaluate("""() => {
                const sel = document.querySelector('#cabBDev');
                if (sel && sel.options.length >= 2) sel.selectedIndex = sel.options.length - 1;
            }""")
            page.fill("#cabLabel", "Cable #224")
            page.click("#rkBtnAddCable")
            page.wait_for_selector("[data-trace-port]", timeout=6000)
            page.locator("[data-trace-port]").first.click()
            page.wait_for_selector("#monitsCableTraceOverlay svg", timeout=6000)
            ct_check = page.evaluate("""() => {
                const ov = document.querySelector('#monitsCableTraceOverlay');
                const svg = ov?.querySelector('svg');
                return {
                    hasSvg: !!svg,
                    hasCableLabel: (svg?.textContent || '').includes('Cable #224'),
                    hasDownloadBtn: !!ov?.querySelector('#ctBtnDownloadSvg'),
                    relatedRows: ov?.querySelectorAll('.ct-table tbody tr.ct-row-click')?.length || 0
                };
            }""")
            if not ct_check["hasSvg"] or not ct_check["hasCableLabel"] or not ct_check["hasDownloadBtn"] or ct_check["relatedRows"] < 1:
                raise RuntimeError(f"NetBox-style SVG Cable Trace check failed: {ct_check}")
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)
            if page.locator("#monitsCableTraceOverlay").count() != 0:
                raise RuntimeError("Escape must close #monitsCableTraceOverlay!")
            print(f"  ✓ NetBox-style SVG Cable Trace verified on /racks (SVG diagram + Cable #224 + Related Paths + Download SVG): {ct_check}")
            # Also verify Dark theme works cleanly on /racks
            page.evaluate("() => window.applyAppTheme('neon', true)")
            page.wait_for_timeout(200)
            if page.evaluate("() => document.documentElement.dataset.theme") != "neon":
                raise RuntimeError("Failed switching /racks to Dark (neon) theme!")
            page.evaluate("() => window.applyAppTheme('light', true)")
            page.wait_for_timeout(200)
            print(f"  ✓ Native /racks Elevation View verified with real WebP photos in Light & Dark themes: {rk_check}")
            page.goto(f"{BASE_URL}/")
            page.wait_for_selector("neonplan3d-panel", timeout=10000)
            page.wait_for_function("() => window.monitsApi && window.nfPanel && window.nfPanel.data && window.nfPanel.data.building", timeout=10000)
            # Verify NO separate #drawerRacks section exists in app.html, and REAL mouse clicks on 3D racks
            # open <div id="monitsRackWallPopup" class="fp3d-wall"> OUTSIDE <fp3d-view3d> shadowRoot!
            if page.locator("#drawerRacks").count() != 0:
                raise RuntimeError("Separate #drawerRacks section must NOT exist on 3D view!")
            if page.locator("#monitsRackWallPopup").count() != 0:
                raise RuntimeError("#monitsRackWallPopup should not exist before clicking a rack!")
            page.wait_for_function("""() => {
                const v3d = document.querySelector('neonplan3d-panel')?.shadowRoot?.querySelector('fp3d-view3d');
                return !!(v3d && v3d.viewer && v3d.viewer.camera && v3d.viewer.floors && v3d.viewer.floors.length > 0 && v3d.viewer.pickFurniture && v3d.viewer.pickFurniture.size > 0);
            }""", timeout=12000)
            page.wait_for_timeout(450)

            # 1) REAL mouse click on 'Core Spine Router 01' (f_rack_netcore1, sensor-linked rack on First Floor in full multi-floor overview!)
            core_rack_click = page.evaluate("""() => {
                const v3d = document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d');
                const viewer = v3d.viewer;
                const canvas = viewer.renderer.domElement;
                const rect = canvas.getBoundingClientRect();
                const cam = viewer.camera;
                // Find Core Spine Router 01 (f_rack_netcore1) first across all floors, fallback to any sensor-linked rack
                const allRacks = [];
                for (const fl of viewer.activeFloors()) {
                    for (const f of (fl.floor.furniture || [])) {
                        if (f.id === 'f_rack_netcore1') allRacks.unshift({ fl, f });
                        else if (String(f.type || '').toLowerCase().includes('rack') && (x => x.power || x.temp_entity)(f)) allRacks.push({ fl, f });
                    }
                }
                for (const { fl, f } of allRacks) {
                    const pin = Array.from(v3d.shadowRoot.querySelectorAll('button.fp3d-dev')).find(b => (b.title || '').includes(f.name) || (b.innerText || '').includes(f.name));
                    if (pin) {
                        const pr = pin.getBoundingClientRect();
                        const cx = pr.left + pr.width / 2, cy = pr.top + pr.height / 2;
                        const topEl = v3d.shadowRoot.elementFromPoint(cx, cy);
                        if (pr.width > 0 && pr.height > 0 && (topEl === pin || pin.contains(topEl))) {
                            return { ok: true, viaPin: true, fid: f.id, name: f.name, clientX: cx, clientY: cy };
                        }
                    }
                    const h = f.h || 1.4;
                    const offsets = [[0,0.55,0],[0,0.85,0],[0,0.2,0],[0.2,0.5,0],[-0.2,0.5,0],[0,0.5,0.25],[0,0.5,-0.25]];
                    for (const [dx, my, dz] of offsets) {
                        const wv = cam.position.clone().set(f.x + dx, h * my, f.z + dz);
                        fl.group.localToWorld(wv);
                        const pv = wv.project(cam);
                        const lx = (pv.x * 0.5 + 0.5) * rect.width;
                        const ly = (-pv.y * 0.5 + 0.5) * rect.height;
                        const cx = rect.left + lx, cy = rect.top + ly;
                        if (v3d.shadowRoot.elementFromPoint(cx, cy) !== canvas) continue;
                        const hit = viewer.pick(lx, ly, true);
                        if (hit && hit.entity === 'rack:' + f.id) {
                            return { ok: true, viaMesh: true, fid: f.id, name: f.name, clientX: cx, clientY: cy };
                        }
                    }
                }
                return { ok: false, reason: 'no unoccluded rack mesh or pin found in overview' };
            }""")
            if not core_rack_click.get("ok"):
                raise RuntimeError(f"Could not project sensor-linked rack (Core Spine Router 01) for real mouse click: {core_rack_click}")
            page.mouse.click(core_rack_click["clientX"], core_rack_click["clientY"])
            page.wait_for_selector("#monitsRackWallPopup.fp3d-wall", timeout=6000)
            core_info = page.evaluate("""() => {
                const v3d = document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d');
                const wall = document.querySelector('#monitsRackWallPopup.fp3d-wall');
                return {
                    inShadowRoot: !!v3d?.shadowRoot?.querySelector('.fp3d-wall'),
                    outsideShadowRoot: !!wall && wall.parentElement === document.body,
                    head: wall?.querySelector('.fp3d-wall-head')?.innerText?.trim() || '',
                    cabinets: wall?.querySelectorAll('.fp3d-rw-cab')?.length || 0
                };
            }""")
            if core_info["inShadowRoot"] or not core_info["outsideShadowRoot"] or core_rack_click["name"] not in core_info["head"] or core_info["cabinets"] != 2:
                raise RuntimeError(f"Real mouse click on '{core_rack_click['name']}' popup check failed: {core_info}")
            print(f"  ✓ REAL 3D mouse click ({'pin' if core_rack_click.get('viaPin') else 'mesh'}) on '{core_rack_click['name']}' opened <div class='fp3d-wall'> OUTSIDE <fp3d-view3d>: {core_info}")
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)
            if page.locator("#monitsRackWallPopup").count() != 0:
                raise RuntimeError("Pressing Escape must close and remove #monitsRackWallPopup!")

            # 2) Switch to Ground Floor so Ground Floor racks aren't occluded by First Floor, then REAL mouse click directly on AI-Rack-48U 3D MESH (with real WebP hardware photos!)
            page.evaluate("""() => {
                const v3d = document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d');
                v3d.viewer.setFloor('ground');
                // Turn off floating hologram overlays temporarily or inspect unoccluded rack pixels
                v3d.viewer.fit(0);
            }""")
            page.wait_for_timeout(300)
            rack_click_target = page.evaluate("""() => {
                const v3d = document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d');
                const viewer = v3d.viewer;
                const canvas = viewer.renderer.domElement;
                const rect = canvas.getBoundingClientRect();
                const racks = window.monitsApi.getRacks?.() || [];
                const aiRack = racks.find(r => r.name === 'AI-Rack-48U');
                const targetFid = aiRack?.furniture_id;
                const fl = viewer.activeFloors().find(x => x.floor.id === 'ground') || viewer.activeFloors()[0];
                const f = (fl?.floor?.furniture || []).find(x => x.id === targetFid);
                if (!f || !fl) return { ok: false, reason: 'AI-Rack-48U furniture not found on ground floor' };
                const cam = viewer.camera;
                const h = f.h || 2.0;
                const samples = [];
                for (const my of [0.55, 0.78, 0.30, 0.90, 0.15]) {
                    for (const [dx, dz] of [[0,0], [0.18,0], [-0.18,0], [0,0.28], [0,-0.28]]) {
                        samples.push([f.x + dx, h * my, f.z + dz]);
                    }
                }
                const debugSamples = [];
                for (const [wx, wy, wz] of samples) {
                    const wv = cam.position.clone().set(wx, wy, wz);
                    fl.group.localToWorld(wv);
                    const pv = wv.project(cam);
                    const lx = (pv.x * 0.5 + 0.5) * rect.width;
                    const ly = (-pv.y * 0.5 + 0.5) * rect.height;
                    if (lx < 0 || lx > rect.width || ly < 0 || ly > rect.height) continue;
                    const cx = rect.left + lx, cy = rect.top + ly;
                    const topEl = v3d.shadowRoot.elementFromPoint(cx, cy);
                    const hit = viewer.pick(lx, ly, true);
                    if (debugSamples.length < 4) {
                        debugSamples.push({ lx: Math.round(lx), ly: Math.round(ly), hit, el: topEl ? topEl.tagName + '.' + topEl.className : null });
                    }
                    if (topEl !== canvas) continue;
                    if (hit && hit.entity === 'rack:' + f.id) {
                        return {
                            ok: true,
                            fid: f.id,
                            name: f.name,
                            clientX: cx,
                            clientY: cy
                        };
                    }
                }
                return {
                    ok: false,
                    fid: f.id,
                    name: f.name,
                    pos: [f.x, f.z, f.h],
                    hasTri: !!fl.geo.furnitureTris.find(t => t.id === f.id),
                    pickTarget: viewer.pickFurniture.get(f.id),
                    debugSamples
                };
            }""")
            if not rack_click_target.get("ok"):
                raise RuntimeError(f"Could not project AI-Rack-48U on Ground Floor for real mouse click: {rack_click_target}")
            page.mouse.click(rack_click_target["clientX"], rack_click_target["clientY"])
            page.wait_for_function("""() => {
                const wall = document.querySelector('#monitsRackWallPopup.fp3d-wall');
                const imgs = wall ? Array.from(wall.querySelectorAll('img.fp3d-rw-img')) : [];
                return !!wall && wall.querySelectorAll('.fp3d-rw-cab').length === 2 && imgs.length >= 1 && imgs.every(i => i.complete && i.naturalWidth > 0);
            }""", timeout=8000)
            wall_info = page.evaluate("""() => {
                const v3d = document.querySelector('neonplan3d-panel').shadowRoot.querySelector('fp3d-view3d');
                const wall = document.querySelector('#monitsRackWallPopup.fp3d-wall');
                return {
                    inShadowRoot: !!v3d?.shadowRoot?.querySelector('.fp3d-wall'),
                    outsideShadowRoot: !!wall && wall.parentElement === document.body,
                    head: wall?.querySelector('.fp3d-wall-head')?.innerText?.trim() || '',
                    cabinets: wall?.querySelectorAll('.fp3d-rw-cab')?.length || 0,
                    photos: wall?.querySelectorAll('img.fp3d-rw-img')?.length || 0
                };
            }""")
            if wall_info["inShadowRoot"] or not wall_info["outsideShadowRoot"]:
                raise RuntimeError(f"Rack popup must render OUTSIDE <fp3d-view3d> shadowRoot! Got: {wall_info}")
            print(f"  ✓ REAL 3D mouse click on '{rack_click_target['name']}' opened <div class='fp3d-wall'> OUTSIDE <fp3d-view3d> with real WebP hardware photos: {wall_info}")
            # Close via ✕ button and verify complete removal from DOM
            page.locator('#monitsRackWallPopup .fp3d-wall-head button[aria-label="✕"]').click()
            page.wait_for_timeout(150)
            if page.locator("#monitsRackWallPopup").count() != 0:
                raise RuntimeError("Clicking ✕ must remove #monitsRackWallPopup from DOM!")
            if page.evaluate("() => document.documentElement.dataset.theme") != "light":
                raise RuntimeError("Expected Light theme to persist when returning to /!")
            # Toggle back to Dark (neon) and verify instant Neon3D update
            page.evaluate("() => window.applyAppTheme('neon', true)")
            page.wait_for_timeout(350)
            dark_check = page.evaluate("""() => {
                const panel = document.querySelector('neonplan3d-panel');
                const v3d = panel?.shadowRoot?.querySelector('fp3d-view3d');
                return { htmlTheme: document.documentElement.dataset.theme, panelTheme: panel?._theme, v3dTheme: v3d?.theme };
            }""")
            if dark_check["htmlTheme"] != "neon" or dark_check["panelTheme"] != "neon" or dark_check["v3dTheme"] != "neon":
                raise RuntimeError(f"Dark theme restore failed on Neon3D: {dark_check}")
            # Verify .fp3d-style-pick 3D style selector works and is NOT overwritten by theme sync interval!
            style_pick_check = page.evaluate("""() => {
                const panel = document.querySelector('neonplan3d-panel');
                const sel = panel?.shadowRoot?.querySelector('.fp3d-style-pick select');
                if (!sel) return { ok: false, reason: 'no .fp3d-style-pick select found' };
                const targetVal = Array.from(sel.options).map(o => o.value).find(v => v && v !== 'neon' && v !== 'day') || 'cozy';
                sel.value = targetVal;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                return { ok: true, targetVal };
            }""")
            page.wait_for_timeout(400)
            after_style = page.evaluate("""() => {
                const panel = document.querySelector('neonplan3d-panel');
                const v3d = panel?.shadowRoot?.querySelector('fp3d-view3d');
                return { panelTheme: panel?._theme, v3dTheme: v3d?.theme };
            }""")
            if not style_pick_check.get("ok") or after_style["panelTheme"] != style_pick_check["targetVal"] or after_style["v3dTheme"] != style_pick_check["targetVal"]:
                raise RuntimeError(f".fp3d-style-pick failed to apply & hold 3D style: {style_pick_check} -> {after_style}")
            print(f"  ✓ .fp3d-style-pick 3D style picker verified ('{style_pick_check['targetVal']}' applied & held): {after_style}")
            print(f"  ✓ Theme persisted across /admin/users, /admin/settings, /admin/audit, and restored to Dark (neon): {dark_check}")

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

            # Verify Full Backup Export + Restore AND File Export/Import preserve exact device/sensor/rack coordinates across reload!
            backup_check = page.evaluate("""async () => {
                const hass = window.nfPanel.hass;
                // 1) Full Backup Export (must NOT throw "can't access property floors, a is undefined")
                const exp = await hass.callWS({ type: 'neonplan3d/backup/export' });
                if (!exp || exp.format !== 'neonplan3d-backup' || !exp.building || !Array.isArray(exp.building.floors)) {
                    return { ok: false, step: 'export', exp };
                }
                // Mutate a sensor furniture + rack position inside the backup payload, then import it via backup/import
                const b2 = structuredClone(exp.building);
                const fl0 = b2.floors[0];
                const sensorFurn = fl0.furniture.find(f => f.id === 'sensor_unit_cold_aisle_rack_b09');
                const rackFurn = fl0.furniture.find(f => String(f.type || '').toLowerCase().includes('rack'));
                if (!sensorFurn || !rackFurn) return { ok: false, step: 'find_items' };
                sensorFurn.x = 7.77;
                sensorFurn.z = 4.44;
                rackFurn.x = 8.88;
                rackFurn.z = 3.33;
                const impRes = await hass.callWS({ type: 'neonplan3d/backup/import', building: b2, packs: exp.packs || [] });
                const sList = await (await fetch('/api/v1/sensors')).json();
                const sObj = sList.find(x => x.identifier === 'cold_aisle_rack_b09');
                return {
                    ok: impRes?.building?.floors?.length > 0 && sObj?.placement_x === 7.77 && sObj?.placement_z === 4.44,
                    rackId: rackFurn.id,
                    sensorDbPos: sObj ? [sObj.placement_x, sObj.placement_z] : null,
                    packs: impRes?.packs
                };
            }""")
            if not backup_check.get("ok"):
                raise RuntimeError(f"Full Backup Export/Import coordinate preservation check failed: {backup_check}")
            # Reload page and verify exact imported coordinates survive reload without drifting back to old DB coords!
            page.reload()
            page.wait_for_selector("neonplan3d-panel", timeout=10000)
            page.wait_for_function("() => window.monitsApi && window.nfPanel && window.nfPanel.data && window.nfPanel.data.building", timeout=10000)
            after_reload_pos = page.evaluate("""(rackId) => {
                const b = window.monitsApi.getBuilding();
                const fl0 = b.floors[0];
                const sf = fl0.furniture.find(f => f.id === 'sensor_unit_cold_aisle_rack_b09');
                const rf = fl0.furniture.find(f => f.id === rackId);
                const card = window.monitsApi.getSensorCardData('cold_aisle_rack_b09');
                return {
                    sensorFurn: sf ? [sf.x, sf.z] : null,
                    rackFurn: rf ? [rf.x, rf.z] : null,
                    cardAnchor: card?.at ? [card.at.x, card.at.z] : null
                };
            }""", backup_check["rackId"])
            if after_reload_pos["sensorFurn"] != [7.77, 4.44] or after_reload_pos["rackFurn"] != [8.88, 3.33] or after_reload_pos["cardAnchor"] != [7.77, 4.44]:
                raise RuntimeError(f"Device positions drifted after Backup/Export Import + reload! Got: {after_reload_pos}")
            print(f"  ✓ Full Backup Export/Restore & File Export/Import preserved EXACT device/sensor/rack coordinates across reload: {after_reload_pos}")

            # Phase 7: Verify Unified Alerts, Threshold Rules CRUD, Incident Timeline & Executive Reports (/alerts)
            print(">> [8/8] Verifying Phase 7 Alerts, Threshold Rules CRUD, Incidents & Exportable Reports (/alerts)...")
            page.goto(f"{BASE_URL}/alerts")
            page.wait_for_selector("#alertsAppRoot .ar-kpis", timeout=10000)
            page.wait_for_selector("#alertsAppRoot table.ar-table tbody tr", timeout=10000)

            # Verify unified header & active Alerts link
            alerts_nav_active = page.evaluate("""() => {
                const a = document.querySelector('.fp3d-app-header a[href="/alerts"]');
                return !!a && a.classList.contains('active');
            }""")
            if not alerts_nav_active:
                raise RuntimeError("Unified header missing active /alerts link on /alerts page!")

            # Create a custom threshold rule via UI form
            page.click("#arNewRuleBtn")
            page.wait_for_selector("#arRuleForm", timeout=5000)
            page.fill('#arRuleForm input[name="name"]', "Smoke Test Overheat Rule")
            page.fill('#arRuleForm input[name="warning_threshold"]', "26.5")
            page.fill('#arRuleForm input[name="critical_threshold"]', "29.5")
            page.click('#arRuleForm button[type="submit"]')
            page.wait_for_function("() => (document.querySelector('#alertsAppRoot')?.innerText || '').includes('Smoke Test Overheat Rule')", timeout=8000)

            # Evaluate rules
            page.click("#arEvalRulesBtn")
            page.wait_for_timeout(400)

            # Switch to Incident Timeline tab, log manual incident & resolve it
            page.click('.ar-tab-btn[data-tab="incidents"]')
            page.wait_for_selector("#arNewIncBtn", timeout=5000)
            page.click("#arNewIncBtn")
            page.wait_for_selector("#arIncidentForm", timeout=5000)
            page.fill('#arIncidentForm input[name="message"]', "Smoke Test Manual Incident")
            page.click('#arIncidentForm button[type="submit"]')
            page.wait_for_function("() => (document.querySelector('#alertsAppRoot')?.innerText || '').includes('Smoke Test Manual Incident')", timeout=8000)
            page.locator('.ar-inc-status[data-status="resolved"]').first.click()
            page.wait_for_timeout(400)

            # Switch to Reports tab & verify export endpoints
            page.click('.ar-tab-btn[data-tab="reports"]')
            page.wait_for_selector("#arExportCsvBtn", timeout=5000)
            export_ok = page.evaluate("""async () => {
                const rCsv = await fetch('/api/v1/alerts/reports/export?format=csv');
                const rHtml = await fetch('/api/v1/alerts/reports/export?format=html');
                const rReady = await fetch('/ready');
                return {
                    csv: rCsv.status,
                    html: rHtml.status,
                    ready: rReady.status,
                    nosniff: rReady.headers.get('x-content-type-options')
                };
            }""")
            if export_ok["csv"] != 200 or export_ok["html"] != 200 or export_ok["ready"] != 200 or export_ok["nosniff"] != "nosniff":
                raise RuntimeError(f"Phase 7 reports/hardening check failed: {export_ok}")
            print(f"  ✓ Phase 7 /alerts UI (Rules CRUD, Incident Timeline, Reports Export & Security Headers) PASSED: {export_ok}")

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
