"""CLI configuration tests for the opt-in MCP server."""
from __future__ import annotations

from skua_lite import __main__ as entry


def test_mcp_environment_does_not_change_default_startup(monkeypatch):
    monkeypatch.setenv("SKUA_MCP_TOKEN", "environment-secret")
    monkeypatch.setenv("SKUA_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("SKUA_MCP_PORT", "9999")
    monkeypatch.setattr(entry.runner, "run", lambda **kwargs: 23)
    monkeypatch.setattr("skua_lite.mcp_server.serve", lambda *args: (_ for _ in ()).throw(AssertionError("serve called")))

    assert entry.main([]) == 23


def test_mcp_cli_options_require_mcp_only(monkeypatch):
    monkeypatch.setenv("SKUA_MCP_TOKEN", "environment-secret")
    try:
        entry.main(["--mcp-token", "x"])
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("expected argparse error")


def test_mcp_only_resolves_environment_and_cli_overrides(monkeypatch):
    monkeypatch.setenv("SKUA_MCP_TOKEN", "environment-secret")
    monkeypatch.setenv("SKUA_MCP_HOST", "localhost")
    monkeypatch.setenv("SKUA_MCP_PORT", "9876")
    calls = []
    monkeypatch.setattr("skua_lite.mcp_server.serve", lambda *args: calls.append(args))

    assert entry.main(["--mcp-only"]) == 0
    assert calls == [("localhost", 9876, "environment-secret")]

    calls.clear()
    assert entry.main(["--mcp-only", "--mcp-host", "127.0.0.1", "--mcp-port", "8766", "--mcp-token", "cli-secret"]) == 0
    assert calls == [("127.0.0.1", 8766, "cli-secret")]


def test_mcp_only_requires_token_and_valid_port(monkeypatch):
    monkeypatch.delenv("SKUA_MCP_TOKEN", raising=False)
    for args, env in [(["--mcp-only"], {}), (["--mcp-only"], {"SKUA_MCP_TOKEN": "x", "SKUA_MCP_PORT": "bad"})]:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        try:
            entry.main(args)
        except SystemExit as error:
            assert error.code == 2
        else:
            raise AssertionError("expected argparse error")
        monkeypatch.delenv("SKUA_MCP_TOKEN", raising=False)
        monkeypatch.delenv("SKUA_MCP_PORT", raising=False)


def test_mcp_non_loopback_warns_without_token_leak(monkeypatch, capsys):
    monkeypatch.setenv("SKUA_MCP_TOKEN", "super-secret-token")
    monkeypatch.setattr("skua_lite.mcp_server.serve", lambda *args: None)
    entry.main(["--mcp-only", "--mcp-host", "0.0.0.0"])
    output = capsys.readouterr()
    assert "PERINGATAN" in output.err
    assert "super-secret-token" not in output.err + output.out


def test_mcp_loopback_hosts_do_not_warn(monkeypatch, capsys):
    monkeypatch.setenv("SKUA_MCP_TOKEN", "secret")
    monkeypatch.setattr("skua_lite.mcp_server.serve", lambda *args: None)
    for host in ("127.0.0.1", "localhost"):
        entry.main(["--mcp-only", "--mcp-host", host])
    assert "PERINGATAN" not in capsys.readouterr().err
