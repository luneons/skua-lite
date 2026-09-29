"""Lokasi penyimpanan kredensial harus stabil lintas interpreter Python."""
from pathlib import Path

from skua_lite import credentials


def test_uses_localappdata_when_normal(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    store = credentials.CredentialStore()
    assert store.base_dir == tmp_path / "AppData" / "Local" / "skua-lite"


def test_ignores_ms_store_sandbox_and_uses_userprofile(monkeypatch, tmp_path):
    user_home = tmp_path / "home"
    user_home.mkdir()
    sandbox = user_home / "AppData" / "Local" / "Packages" / "MS_Store" / "LocalCache" / "Local"
    sandbox.mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(user_home))
    monkeypatch.setenv("LOCALAPPDATA", str(sandbox))

    store = credentials.CredentialStore()
    assert "Packages" not in store.base_dir.parts
    assert store.base_dir == user_home / "AppData" / "Local" / "skua-lite"


def test_explicit_base_dir_is_respected(tmp_path):
    store = credentials.CredentialStore(base_dir=tmp_path / "custom")
    assert store.base_dir == tmp_path / "custom"
    assert store.cred_file == tmp_path / "custom" / "credentials.enc"


def test_default_storage_dirname_is_skua_lite(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "L"))
    store = credentials.CredentialStore()
    assert store.base_dir.name == "skua-lite"
