"""Tests for account management CLI commands (.tambahakun, .editakun, .hapusakun, .daftarakun)."""
from __future__ import annotations

import pytest
from skua_lite.cli import parse_farm_command, dispatch_farm, parse_account_credentials


def test_parse_account_credentials_with_comma_separator():
    user, pwd = parse_account_credentials("demo user,demo-credential")
    assert user == "demo user"
    assert pwd == "demo-credential"

    # With spaces around comma
    user, pwd = parse_account_credentials("demo user , another-demo-value ")
    assert user == "demo user"
    assert pwd == "another-demo-value"


def test_parse_account_credentials_fallback_space():
    user, pwd = parse_account_credentials("singleuser demo-value")
    assert user == "singleuser"
    assert pwd == "demo-value"


def test_parse_account_credentials_invalid():
    with pytest.raises(ValueError):
        parse_account_credentials("onlyusername")
    with pytest.raises(ValueError):
        parse_account_credentials("user,")
    with pytest.raises(ValueError):
        parse_account_credentials(",pass")


def test_cli_parse_farm_commands_account_verbs():
    assert parse_farm_command(".tambahakun demo user,sample-value") == ("tambahakun", "demo user,sample-value")
    assert parse_farm_command(".editakun demo user,updated-value") == ("editakun", "demo user,updated-value")
    assert parse_farm_command(".hapusakun demo user") == ("hapusakun", "demo user")
    assert parse_farm_command(".daftarakun") == ("daftarakun", "")
    assert parse_farm_command(".daftar") == ("daftarakun", "")


def test_cli_dispatch_tambah_and_edit_account_with_spaces_in_name(capsys):
    saved: dict[str, str] = {}

    class FakeAccounts:
        def list_usernames(self):
            return list(saved.keys())
        def add_account(self, u, p):
            saved[u] = p

    orch = type("FakeOrch", (), {"accounts": FakeAccounts(), "farming": object(), "bot": None})()

    res = dispatch_farm(orch, "tambahakun", "demo user,demo-credential")
    assert res == "farm"
    assert saved == {"demo user": "demo-credential"}
    out = capsys.readouterr().out
    assert "demo user" in out
    # Password must NEVER appear in stdout
    assert "demo-credential" not in out

    # Edit akun
    res2 = dispatch_farm(orch, "editakun", "demo user,updated-demo-value")
    assert res2 == "farm"
    assert saved == {"demo user": "updated-demo-value"}
    out2 = capsys.readouterr().out
    assert "demo user" in out2
    assert "updated-demo-value" not in out2


def test_cli_dispatch_hapusakun(capsys):
    accounts_db = {"demo user": "value2", "demo1": "value1"}

    class FakeAccounts:
        def remove_account(self, u):
            if u in accounts_db:
                del accounts_db[u]
                return True
            return False

    orch = type("FakeOrch", (), {"accounts": FakeAccounts(), "farming": object(), "bot": None})()

    # Hapus akun yang ada
    res = dispatch_farm(orch, "hapusakun", "demo user")
    assert res == "farm"
    assert "demo user" not in accounts_db
    out = capsys.readouterr().out
    assert "demo user" in out
    assert "dihapus" in out.lower()

    # Hapus akun yang tidak ada
    res2 = dispatch_farm(orch, "hapusakun", "notfound")
    assert res2 == "farm"
    out2 = capsys.readouterr().out
    assert "tidak ditemukan" in out2.lower()


def test_cli_dispatch_daftarakun(capsys):
    class FakeAccounts:
        def list_usernames(self):
            return ["demo user", "demo2"]
        def active_username(self):
            return "demo user"

    orch = type("FakeOrch", (), {"accounts": FakeAccounts(), "farming": object(), "bot": None})()

    res = dispatch_farm(orch, "daftarakun", "")
    assert res == "farm"
    out = capsys.readouterr().out
    assert "demo user" in out
    assert "demo2" in out
    assert "(aktif)" in out

def test_cli_dispatch_editakun_refuses_unknown_username(capsys):
    class FakeAccounts:
        def list_usernames(self):
            return ["demo1"]
        def add_account(self, u, p):
            raise AssertionError("should not be called")

    orch = type("FakeOrch", (), {"accounts": FakeAccounts(), "farming": object(), "bot": None})()
    res = dispatch_farm(orch, "editakun", "demo user,updated-value")
    assert res is None  # error path
    out = capsys.readouterr().out
    assert "tidak ada" in out.lower()
    # Confirm add_account was NOT called (FakeAccounts raises on call)

