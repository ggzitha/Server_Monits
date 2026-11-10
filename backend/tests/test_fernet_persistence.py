import os
from pathlib import Path
from backend.app.core.config import get_or_generate_fernet_key, FERNET_KEY_FILE


def test_fernet_key_persistence_and_no_regeneration(tmp_path, monkeypatch):
    test_key_file = tmp_path / "data" / "fernet.key"
    monkeypatch.setattr("backend.app.core.config.FERNET_KEY_FILE", test_key_file)
    monkeypatch.setattr("backend.app.core.config.DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("backend.app.core.config.ENV_FILE", tmp_path / ".env")

    # 1. Initial generation
    key1 = get_or_generate_fernet_key()
    assert key1 is not None
    assert len(key1) >= 32
    assert test_key_file.exists()
    assert test_key_file.read_text(encoding="utf-8").strip() == key1

    # 2. Simulate container restart (loading without existing key argument)
    key2 = get_or_generate_fernet_key()
    assert key2 == key1  # Key must be preserved, never regenerated!

    # 3. Simulate another restart with existing key file
    key3 = get_or_generate_fernet_key(None)
    assert key3 == key1

