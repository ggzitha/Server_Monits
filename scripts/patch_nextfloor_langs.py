from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
static_nf = ROOT / "backend" / "app" / "static" / "nextfloor"

for fname in ["nextfloor.js", "nextfloor-editor.js", "nextfloor-card-editor.js"]:
    fpath = static_nf / fname
    if not fpath.exists():
        continue
    s = fpath.read_text(encoding="utf-8")
    
    # 1. Ensure id is in M
    if 'id:"' not in s:
        s = s.replace('var M={', 'var M={id:"1.0",en:"1.0",')
    
    # 2. Never fall back to German (de)
    # Replace german?de:en with en
    s = s.replace('(german?de:en)', 'en')
    s = s.replace('german?de:en', 'en')
    s = s.replace('??de[key]', '??en[key]')
    
    fpath.write_text(s, encoding="utf-8")
    print(f"Patched {fname} for strict EN/ID enforcement")

