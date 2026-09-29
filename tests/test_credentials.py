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


def test_load_raises_when_missing(store):
    with pytest.raises(credentials.NoStoredCredentials):
        store.load()


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
