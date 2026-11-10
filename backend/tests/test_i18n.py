import pytest
from backend.app.core.i18n import get_translations, translate


def test_i18n_translation_keys_completeness():
    en = get_translations("en")
    id_trans = get_translations("id")

    assert "app_name" in en
    assert "app_name" in id_trans
    assert "setup_wizard_title" in en
    assert "setup_wizard_title" in id_trans

    # Ensure Indonesian translation contains expected keys
    assert id_trans["login"] == "Masuk"
    assert id_trans["logout"] == "Keluar"
    assert en["login"] == "Login"


def test_i18n_fallback():
    # If key doesn't exist in ID, fall back to EN or default
    result = translate("non_existent_key_xyz", lang="id", default="Default Value")
    assert result == "Default Value"


@pytest.mark.asyncio
async def test_i18n_api_endpoint(client):
    res_en = await client.get("/api/v1/i18n/en")
    assert res_en.status_code == 200
    assert "app_name" in res_en.json()

    res_id = await client.get("/api/v1/i18n/id")
    assert res_id.status_code == 200
    assert res_id.json()["login"] == "Masuk"

