from fastapi import APIRouter
from backend.app.core.i18n import get_translations

router = APIRouter(prefix="/i18n", tags=["i18n"])


@router.get("/{lang}")
async def get_locale_translations(lang: str):
    """Retrieve full translation JSON dictionary for frontend usage."""
    return get_translations(lang)

