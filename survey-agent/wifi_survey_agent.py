#!/usr/bin/env python3
"""
wifi_survey_agent.py - Server_Monits Wi-Fi RSSI Survey CLI Agent (Phase 4)
Scans nearby Wi-Fi networks (Windows netsh / Linux nmcli) at a given (x, z) floor coordinate
and uploads RSSI measurements to Server_Monits (/api/v1/wifi-survey/batch).

Usage:
    python survey-agent/wifi_survey_agent.py --server http://127.0.0.1:8000 --token <API_TOKEN> --x 2.5 --z 1.5 --floor ground
"""
import argparse
import json
import platform
import re
import subprocess
import sys
import urllib.request


def scan_wifi_windows():
    out = subprocess.check_output(
        ["netsh", "wlan", "show", "networks", "mode=bssid"],
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    results = []
    cur_ssid = None
    cur_bssid = None
    for line in out.splitlines():
        m_ssid = re.match(r"^\s*SSID\s+\d+\s*:\s*(.*)$", line)
        if m_ssid:
            cur_ssid = m_ssid.group(1).strip()
            cur_bssid = None
            continue
        m_bssid = re.match(r"^\s*BSSID\s+\d+\s*:\s*([0-9a-fA-F:]+)", line)
        if m_bssid:
            cur_bssid = m_bssid.group(1).strip()
            continue
        m_sig = re.match(r"^\s*Signal\s*:\s*(\d+)%", line)
        if m_sig and cur_ssid:
            pct = int(m_sig.group(1))
            # Standard Windows % to dBm approximation: -100 + pct/2
            rssi_dbm = round(-100.0 + (pct / 2.0), 1)
            results.append({"ssid": cur_ssid, "bssid": cur_bssid, "rssi_dbm": rssi_dbm, "band": "5GHz"})
    return results


def scan_wifi_linux():
    out = subprocess.check_output(
        ["nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,FREQ", "dev", "wifi", "list"],
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    results = []
    for line in out.splitlines():
        parts = re.split(r"(?<!\\):", line)
        if len(parts) >= 3 and parts[0].strip():
            ssid = parts[0].strip()
            bssid = parts[1].replace("\\:", ":").strip()
            pct = int(parts[2].strip() or 0)
            freq = parts[3] if len(parts) > 3 else ""
            band = "5GHz" if "5" in freq else "2.4GHz"
            rssi_dbm = round(-100.0 + (pct / 2.0), 1)
            results.append({"ssid": ssid, "bssid": bssid, "rssi_dbm": rssi_dbm, "band": band})
    return results


def main():
    parser = argparse.ArgumentParser(description="Server_Monits Wi-Fi RSSI Survey Agent")
    parser.add_argument("--server", required=True, help="Server_Monits base URL (e.g. http://127.0.0.1:8000)")
    parser.add_argument("--token", required=True, help="Bearer API token from Server_Monits")
    parser.add_argument("--x", type=float, required=True, help="X coordinate on floor plan (meters)")
    parser.add_argument("--z", type=float, required=True, help="Z coordinate on floor plan (meters)")
    parser.add_argument("--y", type=float, default=1.2, help="Measurement height Y (meters)")
    parser.add_argument("--floor", default="ground", help="Floor ID (default: ground)")
    parser.add_argument("--ssid-filter", default="", help="Optional SSID substring filter")
    args = parser.parse_args()

    system = platform.system().lower()
    scans = scan_wifi_windows() if "windows" in system else scan_wifi_linux()
    if args.ssid_filter:
        scans = [s for s in scans if args.ssid_filter.lower() in s["ssid"].lower()]

    if not scans:
        print("No Wi-Fi networks detected.")
        sys.exit(1)

    payload = {
        "points": [
            {
                "ssid": s["ssid"],
                "bssid": s.get("bssid"),
                "band": s.get("band", "5GHz"),
                "rssi_dbm": s["rssi_dbm"],
                "floor_id": args.floor,
                "x": args.x,
                "z": args.z,
                "y": args.y,
            }
            for s in scans
        ]
    }
    url = f"{args.server.rstrip('/')}/api/v1/wifi-survey/batch"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {args.token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f"Uploaded {len(scans)} RSSI readings to {url}: HTTP {resp.status}")
        print(resp.read().decode("utf-8"))


if __name__ == "__main__":
    main()
