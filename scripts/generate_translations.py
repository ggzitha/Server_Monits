import re
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
i18n_file = ROOT / "reference" / "NextFloor" / "frontend" / "src" / "i18n.ts"
lang_dir = ROOT / "backend" / "app" / "static" / "nextfloor" / "lang"

content = i18n_file.read_text(encoding="utf-8")

# Find const EN block
en_marker = "const EN: Record<Key, string> = {"
start = content.find(en_marker)
if start == -1:
    raise ValueError("const EN not found")
start += len(en_marker)

# Parse JS object entries roughly
keys = {}
for line in content[start:].splitlines():
    if line.strip().startswith("};"):
        break
    m = re.match(r'^\s*([a-zA-Z0-9_]+):\s*"((?:[^"\\]|\\.)*)",?\s*$', line)
    if m:
        k = m.group(1)
        val = m.group(2).encode('utf-8').decode('unicode-escape')
        keys[k] = val

print(f"Extracted {len(keys)} English strings from NextFloor i18n.ts")

# Remove all other language files
for p in lang_dir.glob("*.json"):
    p.unlink()

# Write en.json
(lang_dir / "en.json").write_text(json.dumps(keys, indent=2, ensure_ascii=False), encoding="utf-8")

# Common Indonesian translations for key UI terms
ID_TERMS = {
    "view": "3D",
    "editor": "Editor",
    "all_floors": "Semua Lantai",
    "outside_area": "Luar Ruangan",
    "outside_area_hint": "Semua perangkat luar ruangan dalam satu tampilan.",
    "device_outside": "Milik Luar Ruangan",
    "no_building": "Belum ada denah ruangan.",
    "no_building_admin": "Belum ada denah ruangan. Gambar lantai pertama Anda di editor.",
    "no_rooms_admin": "Lantai sudah ada, namun belum ada ruangan. Gambar setidaknya satu ruangan dengan 'Persegi' atau 'Bentuk Bebas'.",
    "open_editor": "Buka Editor",
    "loading": "Memuat …",
    "load_error": "Gagal memuat",
    "saving": "Menyimpan …",
    "saved": "Tersimpan",
    "save_error": "Gagal menyimpan",
    "reload_page": "Muat Ulang",
    "settings": "Pengaturan",
    "floor": "Lantai",
    "floors": "Lantai",
    "room": "Ruangan",
    "rooms": "Ruangan",
    "walls": "Dinding",
    "wall": "Dinding",
    "door": "Pintu",
    "doors": "Pintu",
    "window": "Jendela",
    "windows": "Jendela",
    "furniture": "Peralatan",
    "camera": "Kamera",
    "cameras": "Kamera",
    "temperature": "Suhu",
    "humidity": "Kelembapan",
    "heat": "Peta Panas",
    "energy": "Energi",
    "weather": "Cuaca",
    "quality": "Kualitas",
    "theme": "Tema",
    "neon": "Neon",
    "blueprint": "Cetak Biru",
    "day": "Terang",
    "auto": "Otomatis",
    "kiosk": "Mode Kios",
    "fullscreen": "Layar Penuh",
    "undo": "Batal",
    "redo": "Ulangi",
    "delete": "Hapus",
    "cancel": "Batal",
    "confirm": "Konfirmasi",
    "apply": "Terapkan",
    "close": "Tutup",
    "save": "Simpan",
    "name": "Nama",
    "width": "Lebar",
    "height": "Tinggi",
    "depth": "Kedalaman",
    "rotation": "Rotasi",
    "level": "Tingkat",
    "elevation": "Ketinggian",
    "grid": "Kisi",
    "snap": "Snap",
    "export": "Ekspor",
    "import": "Impor",
    "print": "Cetak",
    "download": "Unduh",
    "upload": "Unggah",
    "battery": "Baterai",
    "power": "Daya",
    "solar": "Surya",
    "inverter": "Inverter",
    "flow": "Aliran",
    "status": "Status",
    "online": "Online",
    "offline": "Offline",
    "warning": "Peringatan",
    "error": "Kesalahan",
    "normal": "Normal",
    "low": "Rendah",
    "high": "Tinggi",
    "critical": "Kritis"
}

# Create Indonesian translation mapping
id_keys = {}
for k, en_val in keys.items():
    # Use known term or translate common fragments
    id_val = ID_TERMS.get(k, en_val)
    id_keys[k] = id_val

(lang_dir / "id.json").write_text(json.dumps(id_keys, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Generated en.json ({len(keys)} entries) and id.json ({len(id_keys)} entries) in {lang_dir}")

