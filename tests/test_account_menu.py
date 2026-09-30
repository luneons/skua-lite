"""Tests for the interactive farming account selection menu.

Flow:
  1. (no stored accounts) → tampilkan menu tambah akun / masuk langsung
  2. (ada akun) → tanya Single atau Multi
  3. Single → pilih akun dari list (nomor) atau 'baru'
  4. Multi  → pilih subset (1,3 / semua / all) → return list nama
  5. '+' / 'tambah' → simpan akun baru, loop kembali ke menu
"""
from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import patch, call
import getpass


# ---------------------------------------------------------------------------
# Helper: buat fake MultiAccountStore
# ---------------------------------------------------------------------------

def _store(accounts: dict[str, str]):
    """Fake MultiAccountStore sesuai interface yang dipakai prompt."""

    class Fake:
        def __init__(self):
            self._db = dict(accounts)

        def list_usernames(self):
            return list(self._db.keys())

        def has_accounts(self):
            return bool(self._db)

        def load(self, username: str = None):
            if username is None:
                # Single-account load — first entry
                u = next(iter(self._db))
                return u, self._db[u]
            return username, self._db[username]

        def add_account(self, username: str, password: str):
            self._db[username] = password

    return Fake()


# ---------------------------------------------------------------------------
# Import target (will fail before implementation → RED)
# ---------------------------------------------------------------------------

def _import():
    from skua_lite.runner import prompt_farming_account_flow
    return prompt_farming_account_flow


# =============================================================================
# 1. Tidak ada akun tersimpan → langsung ke alur tambah akun
# =============================================================================

def test_no_accounts_offers_add_then_single(monkeypatch):
    """Jika belum ada akun, menu minta tambah dulu lalu pilih single."""
    fn = _import()
    store = _store({})

    inputs = iter([
        "+",                          # pilih tambah akun
        "demo-user",                  # username akun baru
        "1",                          # kembali di menu: pilih single
        "1",                          # pilih akun ke-1
    ])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    monkeypatch.setattr("getpass.getpass", lambda _p="": "demo-credential")

    mode, selected = fn(store)
    assert mode == "single"
    assert selected == ["demo-user"]
    assert "demo-user" in store.list_usernames()


# =============================================================================
# 2. Ada akun → pilih single → pilih berdasar nomor
# =============================================================================

def test_single_select_by_number(monkeypatch):
    fn = _import()
    store = _store({"hero1": "p1", "hero2": "p2"})

    inputs = iter(["1", "2"])  # mode single, lalu pilih akun ke-2
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    mode, selected = fn(store)
    assert mode == "single"
    assert selected == ["hero2"]


def test_single_select_first_by_default(monkeypatch):
    fn = _import()
    store = _store({"hero1": "p1"})

    inputs = iter(["1", "1"])  # single, akun ke-1
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    mode, selected = fn(store)
    assert mode == "single"
    assert selected == ["hero1"]


# =============================================================================
# 3. Ada akun → pilih multi → subset
# =============================================================================

def test_multi_select_subset(monkeypatch):
    fn = _import()
    store = _store({"hero1": "p1", "hero2": "p2", "hero3": "p3"})

    inputs = iter(["2", "1,3"])  # mode multi, pilih akun 1 dan 3
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    mode, selected = fn(store)
    assert mode == "multi"
    assert selected == ["hero1", "hero3"]


def test_multi_select_all_default(monkeypatch):
    fn = _import()
    store = _store({"hero1": "p1", "hero2": "p2"})

    inputs = iter(["2", "semua"])  # multi, semua
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    mode, selected = fn(store)
    assert mode == "multi"
    assert selected == ["hero1", "hero2"]


def test_multi_select_all_english_keyword(monkeypatch):
    fn = _import()
    store = _store({"a1": "x", "a2": "y"})

    inputs = iter(["2", "all"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    mode, selected = fn(store)
    assert mode == "multi"
    assert selected == ["a1", "a2"]


def test_multi_empty_input_defaults_to_all(monkeypatch):
    fn = _import()
    store = _store({"a1": "x", "a2": "y"})

    inputs = iter(["2", ""])  # kosong → semua
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    mode, selected = fn(store)
    assert mode == "multi"
    assert selected == ["a1", "a2"]


def test_multi_invalid_number_reprompts(monkeypatch, capsys):
    fn = _import()
    store = _store({"hero1": "p1", "hero2": "p2"})

    # "2" → pilih multi; "1,99" → 99 tidak ada, re-prompt DALAM loop multi; "1,2" → OK
    inputs = iter(["2", "1,99", "1,2"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    mode, selected = fn(store)
    assert mode == "multi"
    assert selected == ["hero1", "hero2"]
    out = capsys.readouterr().out
    assert "tidak valid" in out.lower()


# =============================================================================
# 4. Tambah akun dari menu → loop kembali
# =============================================================================

def test_add_account_from_menu_then_single(monkeypatch):
    fn = _import()
    store = _store({"hero1": "p1"})

    inputs = iter([
        "+",                          # tambah akun
        "newuser",                    # username akun baru
        "1",                          # kembali: pilih single
        "2",                          # pilih akun ke-2 (newuser)
    ])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    monkeypatch.setattr("getpass.getpass", lambda _p="": "demo-pass")

    mode, selected = fn(store)
    assert mode == "single"
    assert selected == ["newuser"]
    assert "newuser" in store.list_usernames()


def test_add_account_from_menu_then_multi(monkeypatch):
    fn = _import()
    store = _store({})

    inputs = iter([
        "+",            # pilih tambah akun
        "demo-user",    # username akun baru
        "2",            # pilih multi
        "semua",        # semua
    ])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    monkeypatch.setattr("getpass.getpass", lambda _p="": "demo-cred")

    mode, selected = fn(store)
    assert mode == "multi"
    assert selected == ["demo-user"]


# =============================================================================
# 5. Single → 'baru' → masukkan kredensial segar (tidak disimpan otomatis)
# =============================================================================

def test_single_new_credentials(monkeypatch):
    """Memilih 'baru' mengembalikan mode single dengan None sebagai selected
    agar caller bisa memanggil obtain_credentials() seperti biasa.
    """
    fn = _import()
    store = _store({"hero1": "p1"})

    inputs = iter(["1", "baru"])  # single, lalu pilih 'baru'
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    mode, selected = fn(store)
    assert mode == "single"
    assert selected is None  # caller will invoke obtain_credentials()


# =============================================================================
# 6. Mode teks tidak valid → re-prompt
# =============================================================================

def test_invalid_mode_input_reprompts(monkeypatch, capsys):
    fn = _import()
    store = _store({"hero1": "p1"})

    inputs = iter(["ngaco", "1", "1"])  # invalid, lalu single, akun 1
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    mode, selected = fn(store)
    assert mode == "single"
    out = capsys.readouterr().out
    assert "tidak dikenal" in out.lower() or "pilih" in out.lower()
