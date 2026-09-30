"""Plaintext account file (akun.txt) support.

Rules:
  * akun.txt lives next to accounts.enc in base_dir.
  * One account per line: ``username,password`` (username may contain spaces).
  * Blank lines and ``#`` comments are ignored.
  * An optional leading ``N.`` / ``N)`` index is stripped (handy pasted lists).
  * Merged with the encrypted store by username; when the same username exists
    in both, the ENCRYPTED entry wins and the list shows it once.
  * Passwords are never returned by list/report helpers.
"""
from __future__ import annotations

import os
import stat
import sys

import pytest

from skua_lite import credentials


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def test_parse_plaintext_lines_basic():
    text = "mele,password321\nsorani,password123\n"
    parsed = credentials.parse_plaintext_accounts(text)
    assert parsed == {"mele": "password321", "sorani": "password123"}


def test_parse_plaintext_lines_skips_blank_and_comments():
    text = "# daftar akun\n\nmele,pw1\n   \n# sorani,pw2\nsorani,pw3\n"
    parsed = credentials.parse_plaintext_accounts(text)
    assert parsed == {"mele": "pw1", "sorani": "pw3"}


def test_parse_plaintext_lines_allows_spaces_in_username():
    parsed = credentials.parse_plaintext_accounts("sorani ex,password2\n")
    assert parsed == {"sorani ex": "password2"}


def test_parse_plaintext_lines_strips_numbered_prefix():
    text = "1. mele,password321\n2.sorani,password123\n3) alt,password9\n"
    parsed = credentials.parse_plaintext_accounts(text)
    assert parsed == {
        "mele": "password321",
        "sorani": "password123",
        "alt": "password9",
    }


def test_parse_plaintext_lines_password_may_contain_comma():
    parsed = credentials.parse_plaintext_accounts("mele,pass,with,commas\n")
    assert parsed == {"mele": "pass,with,commas"}


def test_parse_plaintext_lines_ignores_malformed_and_empty_values():
    text = "noCommaHere\nuser,\n,pass\n  ,  \nvalid,pw\n"
    parsed = credentials.parse_plaintext_accounts(text)
    assert parsed == {"valid": "pw"}


# --------------------------------------------------------------------------
# Merge with encrypted store
# --------------------------------------------------------------------------

def _store(tmp_path):
    return credentials.MultiAccountStore(base_dir=tmp_path)


def test_encrypted_only_unchanged(tmp_path):
    store = _store(tmp_path)
    store.add_account("demo-one", "encpass")
    assert store.list_usernames() == ["demo-one"]
    assert store.load("demo-one") == ("demo-one", "encpass")
    assert store.has_accounts() is True


def test_plaintext_only_is_usable(tmp_path):
    store = _store(tmp_path)
    store.plaintext_file.write_text("mele,password321\nsorani,password123\n", encoding="utf-8")

    assert store.has_accounts() is True
    assert store.list_usernames() == ["mele", "sorani"]
    assert store.load("mele") == ("mele", "password321")
    assert store.load("sorani") == ("sorani", "password123")


def test_duplicate_username_shown_once_and_encrypted_wins(tmp_path):
    store = _store(tmp_path)
    store.add_account("mele", "encrypted-pass")
    store.plaintext_file.write_text("mele,plain-pass\nsorani,plain-pass2\n", encoding="utf-8")

    names = store.list_usernames()
    assert names.count("mele") == 1
    assert sorted(names) == ["mele", "sorani"]
    assert store.load("mele") == ("mele", "encrypted-pass")
    assert store.load("sorani") == ("sorani", "plain-pass2")


def test_duplicate_username_dedup_is_case_insensitive(tmp_path):
    store = _store(tmp_path)
    store.add_account("Mele", "encrypted-pass")
    store.plaintext_file.write_text("mele,plain-pass\n", encoding="utf-8")

    names = store.list_usernames()
    assert len(names) == 1
    assert names[0] == "Mele"
    assert store.load("Mele") == ("Mele", "encrypted-pass")


def test_missing_or_unreadable_plaintext_is_not_fatal(tmp_path):
    store = _store(tmp_path)
    assert store.list_usernames() == []
    assert store.has_accounts() is False
    # a directory in place of the file must not raise
    store.plaintext_file.mkdir()
    assert store.list_usernames() == []


def test_account_source_reports_which_store_holds_it(tmp_path):
    store = _store(tmp_path)
    store.add_account("enc-user", "pw")
    store.plaintext_file.write_text("plain-user,pw\n", encoding="utf-8")

    assert store.account_source("enc-user") == "encrypted"
    assert store.account_source("plain-user") == "plaintext"
    assert store.account_source("ghost-user") is None


# --------------------------------------------------------------------------
# Removal works on both sources
# --------------------------------------------------------------------------

def test_remove_account_deletes_plaintext_entry(tmp_path):
    store = _store(tmp_path)
    store.plaintext_file.write_text("mele,pw1\nsorani,pw2\n", encoding="utf-8")

    assert store.remove_account("mele") is True
    assert store.list_usernames() == ["sorani"]
    assert "mele" not in store.plaintext_file.read_text(encoding="utf-8")

    assert store.remove_account("ghost") is False


def test_remove_account_removes_from_both_sources(tmp_path):
    store = _store(tmp_path)
    store.add_account("mele", "encpw")
    store.plaintext_file.write_text("mele,plainpw\n", encoding="utf-8")

    assert store.remove_account("mele") is True
    assert store.list_usernames() == []
    assert store.has_accounts() is False


def test_add_account_does_not_touch_plaintext_file(tmp_path):
    store = _store(tmp_path)
    store.plaintext_file.write_text("mele,pw1\n", encoding="utf-8")

    store.add_account("enc-user", "encpw")

    text = store.plaintext_file.read_text(encoding="utf-8")
    assert "enc-user" not in text
    assert "encpw" not in text
    assert sorted(store.list_usernames()) == ["enc-user", "mele"]


# --------------------------------------------------------------------------
# Permissions: only the current user may read the plaintext file
# --------------------------------------------------------------------------

def test_harden_plaintext_file_restricts_posix_permissions(tmp_path):
    if sys.platform == "win32":
        pytest.skip("POSIX-only assertion")

    store = _store(tmp_path)
    store.plaintext_file.write_text("mele,pw1\n", encoding="utf-8")

    assert credentials.harden_plaintext_file(store.plaintext_file) is True

    mode = stat.S_IMODE(os.stat(store.plaintext_file).st_mode)
    assert mode == 0o600


def test_harden_plaintext_file_is_safe_when_file_absent(tmp_path):
    target = tmp_path / "akun.txt"
    assert credentials.harden_plaintext_file(target) is False


def test_list_usernames_never_returns_passwords(tmp_path):
    store = _store(tmp_path)
    store.plaintext_file.write_text("mele,password321\n", encoding="utf-8")

    assert "password321" not in " ".join(store.list_usernames())
