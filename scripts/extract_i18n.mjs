import fs from 'node:fs';
import path from 'node:path';
import { stripTypeScriptTypes } from 'node:module';

const i18nPath = path.resolve('reference/NextFloor/frontend/src/i18n.ts');
let code = fs.readFileSync(i18nPath, 'utf8');

const jsCode = stripTypeScriptTypes(code);

const enMatch = /const\s+EN\s*=\s*\{/.exec(jsCode);
if (!enMatch) {
  throw new Error("Could not find const EN");
}
const startIdx = enMatch.index + enMatch[0].length - 1; // points to '{'
const endIdx = jsCode.indexOf('};\n', startIdx);
const enObjStr = jsCode.substring(startIdx, endIdx + 1);

const fn = new Function('return ' + enObjStr);
const enDict = fn();

console.log('Successfully extracted', Object.keys(enDict).length, 'English keys.');

const ID_TERMS = {
  view: "3D Monitor",
  editor: "Editor CAD 3D",
  all_floors: "Semua Lantai",
  outside_area: "Luar Ruangan",
  outside_area_hint: "Semua sensor & perangkat luar ruangan dalam satu tampilan.",
  device_outside: "Milik Luar Ruangan",
  no_building: "Belum ada denah ruangan.",
  no_building_admin: "Belum ada denah fasilitas server. Buat lantai pertama Anda di editor.",
  no_rooms_admin: "Lantai sudah ada, namun belum ada ruangan server. Gambar setidaknya satu ruangan dengan 'Persegi' atau 'Bentuk Bebas'.",
  open_editor: "Buka Editor CAD",
  loading: "Memuat …",
  load_error: "Gagal memuat",
  saving: "Menyimpan …",
  saved: "Tersimpan",
  save_error: "Gagal menyimpan",
  reload_page: "Muat Ulang",
  settings: "Pengaturan",
  floor: "Lantai",
  floors: "Lantai",
  room: "Ruangan",
  rooms: "Ruangan",
  walls: "Dinding",
  wall: "Dinding",
  door: "Pintu",
  doors: "Pintu",
  window: "Jendela",
  windows: "Jendela",
  furniture: "Peralatan & Rak",
  camera: "Kamera",
  cameras: "Kamera",
  temperature: "Suhu",
  humidity: "Kelembapan",
  heat: "Peta Panas",
  energy: "Aliran Energi",
  weather: "Simulasi Cuaca",
  quality: "Kualitas Grafis",
  theme: "Tema",
  neon: "Neon",
  blueprint: "Cetak Biru",
  day: "Terang",
  auto: "Otomatis",
  kiosk: "Mode Kios",
  fullscreen: "Layar Penuh",
  undo: "Batal",
  redo: "Ulangi",
  delete: "Hapus",
  cancel: "Batal",
  confirm: "Konfirmasi",
  apply: "Terapkan",
  close: "Tutup",
  save: "Simpan",
  name: "Nama",
  width: "Lebar",
  height: "Tinggi",
  depth: "Kedalaman",
  rotation: "Rotasi",
  level: "Tingkat",
  elevation: "Ketinggian",
  grid: "Kisi Snap",
  snap: "Snap",
  export: "Ekspor",
  import: "Impor",
  print: "Cetak 3D",
  download: "Unduh",
  upload: "Unggah",
  battery: "Baterai",
  power: "Daya",
  solar: "Surya",
  inverter: "Inverter",
  flow: "Aliran Kabel",
  status: "Status",
  online: "Online",
  offline: "Offline",
  warning: "Peringatan",
  error: "Kesalahan",
  normal: "Normal",
  low: "Rendah",
  high: "Tinggi",
  critical: "Kritis",
  tool_select: "Pilih",
  tool_rect: "Persegi",
  tool_polygon: "Bentuk Bebas",
  tool_wall: "Dinding",
  tool_doors: "Pintu & Jendela",
  tool_furniture: "Peralatan & Rak",
  tool_stairs: "Tangga",
  tool_outdoor: "Area Luar",
  tool_roof: "Atap",
  tool_energy: "Kabel & Energi",
  btn_measure: "Pengukuran",
  btn_3d_beside: "3D Bersebelahan",
  btn_show_all: "Tampilkan Semua",
  floor_plan: "Denah Lantai"
};

const idDict = {};
for (const [k, v] of Object.entries(enDict)) {
  idDict[k] = ID_TERMS[k] || v;
}

const outDir = path.resolve('backend/app/static/nextfloor/lang');
fs.mkdirSync(outDir, { recursive: true });

fs.writeFileSync(path.join(outDir, 'en.json'), JSON.stringify(enDict, null, 2), 'utf8');
fs.writeFileSync(path.join(outDir, 'id.json'), JSON.stringify(idDict, null, 2), 'utf8');

console.log('Saved pristine UTF-8 en.json and id.json to', outDir);
