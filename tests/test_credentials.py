"""Test penyimpanan kredensial terenkripsi (DPAPI via ctypes, fallback)."""
import os
from pathlib import Path

import pytest

from skua_lite import credentials


@pytest.fixture
def store(tmp_path: Path) -> credentials.CredentialStore:
    return credentials.CredentialStore(base_dir=tmp_path)


def test_save_and_load_roundtrip(store):
    store.save("alice", "s3cretpw")
    u, p = store.load()
    assert u == "alice"
    assert p == "s3cretpw"


def test_file_is_encrypted_not_plaintext(store):
    store.save("alice", "s3cretpw")
    raw = store.cred_file.read_bytes()
    assert b"alice" not in raw
    assert b"s3cretpw" not in raw


def test_multi_account_store_crud_and_switch(tmp_path):
    store = credentials.MultiAccountStore(base_dir=tmp_path)
    assert store.has_accounts() is False
    assert store.list_usernames() == []
    assert store.active_username() is None

    # Tambah akun pertama -> otomatis jadi aktif
    store.add_account("user1", "pass1")
    assert store.has_accounts() is True
    assert store.list_usernames() == ["user1"]
    assert store.active_username() == "user1"
    assert store.load_active() == ("user1", "pass1")

    # Tambah akun kedua -> aktif tetap user1
    store.add_account("user2", "pass2")
    assert store.list_usernames() == ["user1", "user2"]
    assert store.active_username() == "user1"
    assert store.load("user2") == ("user2", "pass2")

    # Ganti akun aktif
    store.set_active("user2")
    assert store.active_username() == "user2"
    assert store.load_active() == ("user2", "pass2")

    # Hapus akun
    assert store.remove_account("user2") is True
    assert store.active_username() == "user1"
    assert store.list_usernames() == ["user1"]
    assert store.remove_account("unknown") is False


def test_overwrite_existing(store):
    store.save("alice", "pw1")
    store.save("bob", "pw2")
    u, p = store.load()
    assert u == "bob"
    assert p == "pw2"


def test_machine_entropy_is_persistent(store):
    e1 = store._machine_entropy()
    e2 = store._machine_entropy()
    assert e1 == e2
    assert (store.base_dir / store.MACHINE_KEY).exists()
