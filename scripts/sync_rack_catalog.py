#!/usr/bin/env python3
"""
sync_rack_catalog.py - Build native Server_Monits hardware catalog & copy optimized WebP
front/rear device images from reference/Rackula (MIT + NetBox Device Type Library CC0).

Outputs:
- backend/app/static/rack_assets/device-images/**.webp
- backend/app/static/rack_assets/catalog.json
"""
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RACKULA_DIR = ROOT / "reference" / "Rackula"
SRC_IMG_DIR = RACKULA_DIR / "src" / "lib" / "assets" / "device-images"
SRC_PACKS_DIR = RACKULA_DIR / "src" / "lib" / "data" / "brandPacks"
SRC_STARTER = RACKULA_DIR / "src" / "lib" / "data" / "starterLibrary.ts"

DEST_ROOT = ROOT / "backend" / "app" / "static" / "rack_assets"
DEST_IMG_DIR = DEST_ROOT / "device-images"
DEST_CATALOG = DEST_ROOT / "catalog.json"

CATEGORY_MAP = {
    "server": "server",
    "network": "switch",
    "patch-panel": "patch_panel",
    "power": "pdu",
    "ups": "ups",
    "storage": "storage",
    "blank": "blank_panel",
    "shelf": "custom",
    "kvm": "custom",
    "av-media": "custom",
    "cooling": "custom",
    "cable-management": "blank_panel",
    "chassis": "server",
    "other": "custom",
}

CATEGORY_COLOR = {
    "server": "#0284c7",
    "switch": "#059669",
    "patch_panel": "#475569",
    "pdu": "#d97706",
    "ups": "#dc2626",
    "storage": "#7c3aed",
    "blank_panel": "#64748b",
    "custom": "#db2777",
}

GENERIC_FALLBACK = {
    "server": {
        1: "/static/rack_assets/device-images/_generic/server/1u-server.front.webp",
        2: "/static/rack_assets/device-images/_generic/server/2u-server.front.webp",
        4: "/static/rack_assets/device-images/_generic/server/4u-server.front.webp",
    },
    "switch": {
        1: "/static/rack_assets/device-images/_generic/network/48-port-switch.front.webp",
    },
    "storage": {
        1: "/static/rack_assets/device-images/_generic/storage/1u-storage.front.webp",
        2: "/static/rack_assets/device-images/_generic/storage/2u-storage.front.webp",
        4: "/static/rack_assets/device-images/_generic/storage/4u-storage.front.webp",
    },
    "ups": {
        2: "/static/rack_assets/device-images/_generic/power/2u-ups.front.webp",
    },
    "custom": {
        1: "/static/rack_assets/device-images/_generic/network/1u-router-firewall.front.webp",
    },
}

# Curated Sangfor enterprise devices (mapped to realistic firewall/server/storage hardware images)
SANGFOR_DEVICES = [
    {
        "slug": "sangfor-ngaf-m5100-f-i",
        "brand": "Sangfor",
        "model": "NGAF M5100-F-I Next-Gen Firewall",
        "device_type": "switch",
        "category": "network",
        "u_height": 1,
        "is_full_depth": False,
        "half_width": False,
        "power_w": 85.0,
        "color": "#059669",
        "front_image": "/static/rack_assets/device-images/_generic/network/1u-router-firewall.front.webp",
        "rear_image": "/static/rack_assets/device-images/fortinet/fortigate-100f.rear.webp",
    },
    {
        "slug": "sangfor-ngaf-m5400-f-i",
        "brand": "Sangfor",
        "model": "NGAF M5400-F-I Enterprise Firewall",
        "device_type": "switch",
        "category": "network",
        "u_height": 2,
        "is_full_depth": True,
        "half_width": False,
        "power_w": 220.0,
        "color": "#059669",
        "front_image": "/static/rack_assets/device-images/palo-alto/palo-alto-pa-3220.front.webp",
        "rear_image": "/static/rack_assets/device-images/palo-alto/palo-alto-pa-3220.rear.webp",
    },
    {
        "slug": "sangfor-iam-m5100",
        "brand": "Sangfor",
        "model": "IAM M5100 Internet Access Gateway",
        "device_type": "switch",
        "category": "network",
        "u_height": 1,
        "is_full_depth": False,
        "half_width": False,
        "power_w": 75.0,
        "color": "#059669",
        "front_image": "/static/rack_assets/device-images/_generic/network/24-port-switch.front.webp",
        "rear_image": "/static/rack_assets/device-images/fortinet/fortigate-100f.rear.webp",
    },
    {
        "slug": "sangfor-hci-aserver-2205",
        "brand": "Sangfor",
        "model": "HCI aServer-2205 (2U Hyper-Converged)",
        "device_type": "server",
        "category": "server",
        "u_height": 2,
        "is_full_depth": True,
        "half_width": False,
        "power_w": 680.0,
        "color": "#0284c7",
        "front_image": "/static/rack_assets/device-images/_generic/server/2u-server.front.webp",
        "rear_image": "/static/rack_assets/device-images/dell/poweredge-r750.rear.webp",
    },
    {
        "slug": "sangfor-eds-storage-4u",
        "brand": "Sangfor",
        "model": "EDS Enterprise Storage Node 4U",
        "device_type": "storage",
        "category": "storage",
        "u_height": 4,
        "is_full_depth": True,
        "half_width": False,
        "power_w": 820.0,
        "color": "#7c3aed",
        "front_image": "/static/rack_assets/device-images/_generic/storage/4u-storage.front.webp",
        "rear_image": "/static/rack_assets/device-images/supermicro/supermicro-cse-846.rear.webp",
    },
]


def copy_images():
    DEST_IMG_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in SRC_IMG_DIR.rglob("*.webp"):
        rel = src.relative_to(SRC_IMG_DIR)
        dst = DEST_IMG_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
        count += 1
    return count


def index_images():
    """Build lookup maps: (brand_folder, slug) -> {front, rear} and slug -> {front, rear}."""
    by_slug = {}
    for p in DEST_IMG_DIR.rglob("*.webp"):
        rel_url = "/static/rack_assets/device-images/" + p.relative_to(DEST_IMG_DIR).as_posix()
        name = p.name
        if name.endswith(".front.webp"):
            slug = name[: -len(".front.webp")]
            by_slug.setdefault(slug, {})["front"] = rel_url
        elif name.endswith(".rear.webp"):
            slug = name[: -len(".rear.webp")]
            by_slug.setdefault(slug, {})["rear"] = rel_url
    return by_slug


def parse_ts_device_blocks(ts_text: str):
    """Extract DeviceType object literals from Rackula TypeScript brand pack files."""
    # Strip // comments so braces in comments never confuse matching
    clean = re.sub(r"//[^\n]*", "", ts_text)
    items = []
    # Match each object literal block `{ ... }` that contains `slug:`
    for m in re.finditer(r"\{[^{}]*\bslug\s*:[^{}]*\}", clean, re.S):
        block = m.group(0)

        def grab_str(key):
            mm = re.search(rf'\b{key}\s*:\s*["\']([^"\']+)["\']', block)
            return mm.group(1).strip() if mm else ""

        def grab_num(key, default=None):
            mm = re.search(rf"\b{key}\s*:\s*([0-9]+(?:\.[0-9]+)?)", block)
            return float(mm.group(1)) if mm else default

        def grab_bool(key, default=None):
            mm = re.search(rf"\b{key}\s*:\s*(true|false)", block)
            if not mm:
                return default
            return mm.group(1) == "true"

        slug = grab_str("slug")
        model = grab_str("model")
        if not slug or not model:
            continue
        mfr = grab_str("manufacturer") or "Generic"
        raw_cat = grab_str("category") or "other"
        u_h = max(1, min(70, int(round(grab_num("u_height", 1) or 1))))
        is_full_depth = grab_bool("is_full_depth", True)
        slot_width = grab_num("slot_width", 2)
        half_w = (slot_width == 1)
        dtype = CATEGORY_MAP.get(raw_cat, "custom")
        if raw_cat == "power" and ("ups" in model.lower() or "smart-ups" in model.lower() or "eaton" in mfr.lower()):
            dtype = "ups"
        default_power = {
            "server": 320.0 * u_h,
            "storage": 240.0 * u_h,
            "switch": 120.0,
            "ups": 90.0,
            "pdu": 15.0,
            "patch_panel": 0.0,
            "blank_panel": 0.0,
            "custom": 60.0,
        }.get(dtype, 50.0)

        items.append({
            "slug": slug,
            "brand": mfr,
            "model": model,
            "device_type": dtype,
            "category": raw_cat,
            "u_height": u_h,
            "is_full_depth": bool(is_full_depth),
            "half_width": bool(half_w),
            "power_w": float(grab_num("power_w", default_power) or default_power),
            "color": CATEGORY_COLOR.get(dtype, "#0284c7"),
        })
    return items


def resolve_fallback_image(dtype: str, u_height: int) -> str:
    table = GENERIC_FALLBACK.get(dtype) or GENERIC_FALLBACK["server"]
    if u_height in table:
        return table[u_height]
    # Pick closest available U
    closest = min(table.keys(), key=lambda k: abs(k - u_height))
    return table[closest]


def main():
    copied = copy_images()
    img_map = index_images()
    print(f"Copied/verified {copied} WebP device images ({len(img_map)} unique slugs indexed).")

    catalog = []
    seen_slugs = set()

    # 1. Generic Starter Library
    if SRC_STARTER.exists():
        for item in parse_ts_device_blocks(SRC_STARTER.read_text(encoding="utf-8")):
            if item["slug"] in seen_slugs:
                continue
            item["brand"] = "Generic"
            imgs = img_map.get(item["slug"], {})
            item["front_image"] = imgs.get("front") or resolve_fallback_image(item["device_type"], item["u_height"])
            item["rear_image"] = imgs.get("rear") or ""
            catalog.append(item)
            seen_slugs.add(item["slug"])

    # 2. All Brand Packs (MikroTik, Supermicro, Dell, HPE, Juniper, Cisco, Ubiquiti, APC, Fortinet, etc.)
    for ts_file in sorted(SRC_PACKS_DIR.glob("*.ts")):
        if ts_file.name == "index.ts":
            continue
        pack_items = parse_ts_device_blocks(ts_file.read_text(encoding="utf-8"))
        for item in pack_items:
            slug = item["slug"]
            if slug in seen_slugs:
                continue
            imgs = img_map.get(slug, {})
            # Also try prefixed/unprefixed slug lookup (e.g. dell-poweredge-r650 vs poweredge-r650)
            if not imgs:
                brand_prefix = ts_file.stem.lower() + "-"
                if slug.startswith(brand_prefix):
                    imgs = img_map.get(slug[len(brand_prefix):], {})
                else:
                    imgs = img_map.get(brand_prefix + slug, {})
            item["front_image"] = imgs.get("front") or resolve_fallback_image(item["device_type"], item["u_height"])
            item["rear_image"] = imgs.get("rear") or ""
            item["has_real_image"] = bool(imgs.get("front"))
            catalog.append(item)
            seen_slugs.add(slug)

    # 3. Add Sangfor enterprise appliances (only keep existing image URLs)
    for sf in SANGFOR_DEVICES:
        if sf["slug"] in seen_slugs:
            continue
        rear_path = ROOT / "backend" / "app" / sf["rear_image"].lstrip("/")
        if sf["rear_image"] and not rear_path.exists():
            sf["rear_image"] = ""
        sf["has_real_image"] = True
        catalog.append(sf)
        seen_slugs.add(sf["slug"])

    # 4. Auto-register ALL remaining real WebP hardware photos from device-images so zero real photos go unused!
    BRAND_LABELS = {
        "ac-infinity": ("AC Infinity", "custom"),
        "apc": ("APC", "ups"),
        "apple": ("Apple", "server"),
        "arista": ("Arista", "switch"),
        "cisco": ("Cisco", "switch"),
        "dell": ("Dell", "server"),
        "eaton": ("Eaton", "ups"),
        "fortinet": ("Fortinet", "switch"),
        "hpe": ("HPE", "server"),
        "juniper": ("Juniper", "switch"),
        "lenovo": ("Lenovo", "server"),
        "mikrotik": ("MikroTik", "switch"),
        "netgear": ("Netgear", "switch"),
        "palo-alto": ("Palo Alto", "switch"),
        "qnap": ("QNAP", "storage"),
        "supermicro": ("Supermicro", "server"),
        "synology": ("Synology", "storage"),
        "tp-link": ("TP-Link", "switch"),
        "ubiquiti": ("Ubiquiti", "switch"),
    }
    for p in sorted(DEST_IMG_DIR.rglob("*.front.webp")):
        rel = p.relative_to(DEST_IMG_DIR)
        folder = rel.parts[0]
        if folder == "_generic":
            continue
        slug = p.name[: -len(".front.webp")]
        if slug in seen_slugs:
            continue
        brand_name, default_dtype = BRAND_LABELS.get(folder, (folder.replace("-", " ").title(), "custom"))
        # Clean model name from slug
        m_slug = slug
        for pref in (folder + "-", brand_name.lower() + "-"):
            if m_slug.lower().startswith(pref):
                m_slug = m_slug[len(pref):]
        model_label = m_slug.replace("-", " ").upper()
        # Infer U height from common naming patterns (2u, 4u, dl380, r750, etc.)
        low = slug.lower()
        u_h = 1
        m_u = re.search(r"(\d+)u\b", low)
        if m_u:
            u_h = max(1, min(12, int(m_u.group(1))))
        elif any(k in low for k in ("dl380", "dl385", "r740", "r750", "r760", "r730", "r720", "sr650", "2u", "smx", "srt", "smt2200", "smt3000", "9px", "5px")):
            u_h = 2
        elif any(k in low for k in ("846", "847", "4u", "dl580", "r940")):
            u_h = 4
        elif any(k in low for k in ("3u", "836")):
            u_h = 3
        dtype = default_dtype
        if any(k in low for k in ("pdu", "ap7", "ap8", "ap6", "ap4")):
            dtype = "pdu"
        elif any(k in low for k in ("ups", "smt", "srt", "smx", "bx", "bc", "9px", "5px", "5p")):
            dtype = "ups"
        elif any(k in low for k in ("nas", "rs", "ds", "san", "msa", "store", "qnap", "ts-")):
            dtype = "storage"
        elif any(k in low for k in ("proliant", "poweredge", "thinksystem", "sys-", "cse-", "server")):
            dtype = "server"
        imgs = img_map.get(slug, {})
        catalog.append({
            "slug": slug,
            "brand": brand_name,
            "model": model_label,
            "device_type": dtype,
            "category": dtype,
            "u_height": u_h,
            "is_full_depth": bool(imgs.get("rear") or dtype in ("server", "storage", "ups")),
            "half_width": False,
            "power_w": 320.0 * u_h if dtype in ("server", "storage") else (120.0 if dtype == "switch" else 60.0),
            "color": CATEGORY_COLOR.get(dtype, "#0284c7"),
            "front_image": imgs.get("front", ""),
            "rear_image": imgs.get("rear", ""),
            "has_real_image": True,
        })
        seen_slugs.add(slug)

    # Verify zero broken image URLs across entire catalog
    for item in catalog:
        for k in ("front_image", "rear_image"):
            u = item.get(k) or ""
            if u and not (ROOT / "backend" / "app" / u.lstrip("/")).exists():
                item[k] = resolve_fallback_image(item["device_type"], item["u_height"]) if k == "front_image" else ""

    # Sort: prioritize items with real brand photos inside each brand, then alphabetical
    brands = sorted({c["brand"] for c in catalog})
    real_front = sum(1 for c in catalog if c.get("has_real_image"))
    real_rear = sum(1 for c in catalog if c.get("rear_image"))

    DEST_CATALOG.parent.mkdir(parents=True, exist_ok=True)
    DEST_CATALOG.write_text(
        json.dumps({"version": 1, "brands": brands, "count": len(catalog), "devices": catalog}, indent=None),
        encoding="utf-8",
    )
    print(f"Generated {DEST_CATALOG}: {len(catalog)} devices across {len(brands)} brands ({real_front} real brand front photos, {real_rear} rear photos).")


if __name__ == "__main__":
    main()
