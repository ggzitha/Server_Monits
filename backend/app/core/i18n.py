import json
from pathlib import Path
from typing import Dict, Any, Optional

I18N_DIR = Path(__file__).resolve().parent.parent / "i18n"
_TRANSLATIONS: Dict[str, Dict[str, str]] = {}


def load_translations() -> None:
    """Load JSON translation dictionaries into memory."""
    global _TRANSLATIONS
    _TRANSLATIONS = {}
    if not I18N_DIR.exists():
        return
        
    for file_path in I18N_DIR.glob("*.json"):
        lang_code = file_path.stem.lower()
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                _TRANSLATIONS[lang_code] = json.load(f)
        except Exception:
            _TRANSLATIONS[lang_code] = {}


# Initial load
load_translations()


def get_translations(lang: str = "en") -> Dict[str, str]:
    """Get the full translation dictionary for a language code."""
    lang = lang.lower()
    return _TRANSLATIONS.get(lang, _TRANSLATIONS.get("en", {}))


def translate(key: str, lang: str = "en", default: Optional[str] = None) -> str:
    """Translate a message key for a specific language code with fallback to English."""
    lang = lang.lower()
    trans = _TRANSLATIONS.get(lang)
    if trans and key in trans:
        return trans[key]
    
    # Fallback to English
    en_trans = _TRANSLATIONS.get("en", {})
    if key in en_trans:
        return en_trans[key]
        
    return default if default is not None else key


def create_i18n_helper(lang: str = "en"):
    """Helper callable for Jinja2 template rendering context."""
    def _(key: str, default: Optional[str] = None) -> str:
        return translate(key, lang=lang, default=default)
    return _

