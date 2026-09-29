"""Live wiring: runner.connect brings up Admin Mode on the real bot path."""
from __future__ import annotations

import time
from unittest.mock import Mock

from skua_lite import bot as bot_mod
from skua_lite import credentials, login, runner, servers
from tests.test_client import MockSFSServer

import pytest


@pytest.fixture
def mock_server():
    srv = MockSFSServer()
    srv.scripted.extend([
        "<msg t='sys'><body action='apiOK' r='0'></body></msg>",
        "%xt%loginResponse%-1%true%1%alice%Welcome!%",
        "<msg t='sys'><body action='joinOK' r='3'><pid id='1'/></body></msg>",
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":3,'
        '"areaName":"battleon-1","strMapName":"battleon"}}}',
        '{"t":"xt","b":{"r":3,"o":{"cmd":"loadInventoryBig","items":[]}}}',
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":42,'
        '"areaName":"yulgar-14045","strMapName":"yulgar"}}}',
    ])
    srv.start()
    yield srv
    srv.stop()


def test_runner_wires_admin_mode_and_owner_bang_command(mock_server, tmp_path, monkeypatch):
    monkeypatch.setattr(
        login, "aqw_login",
        lambda u, p, *, timeout=20: login.LoginToken(username=u, token="TOK", success=True),
    )
    monkeypatch.setattr(
        servers, "fetch_server_list",
        lambda *, timeout=20: {"Yorumi": servers.Server(
            name="Yorumi", ip=mock_server.host, port=mock_server.port,
            online=True, full=False, upgrade_only=False,
        )},
    )
    monkeypatch.setenv("SKUA_AI_BASE_URL", "https://ai.example/v1")
    monkeypatch.setenv("SKUA_AI_API_KEY", "test-key")
    monkeypatch.setenv("SKUA_AI_MODEL", "test-model")
    monkeypatch.setenv("SKUA_ADMIN_SHELL", "0")
    monkeypatch.setattr(
        runner, "openai_chat_generator",
        lambda _cfg: (lambda _message: "jawaban santai"),
    )
    monkeypatch.setattr("builtins.input", lambda *a, **k: "y")
    monkeypatch.chdir(tmp_path)

    store = credentials.CredentialStore(base_dir=tmp_path)
    store.save("alice", "pw")
    orch = runner.Orchestrator(server_name="Yorumi", target_map="yulgar-14045", store=store)
    orch.auto_relogin = False
    orch.connect("alice", "pw")

    try:
        bot = orch.bot
        assert bot is not None
        router = bot.ai_router
        assert router is not None
        assert router.admin_inbox is not None
        assert router.admin_mode is False

        # Owner walks in while the bot is live.
        bot._handle_server_packet(
            "<msg t='sys'><body action='uER' r='42'>"
            "<u i='21623' n='MELE'/></body></msg>"
        )
        assert router.admin_mode is True
        time.sleep(0.3)

        # Fake the web search so this stays offline, then prove the whole
        # chat -> admin dispatch -> zone chat reply path works live.
        seen = {}

        def fake_search(query: str):
            seen["query"] = query
            from skua_lite.agent_tools import ToolResult
            return ToolResult(True, f"hasil untuk {query}")

        router._admin_handler.tools.web_search = fake_search
        sent = []
        router._send_chat = lambda text: (sent.append(text), bot.send_plain_chat(text, channel="zone"))
        bot._handle_server_packet("%xt%chatm%-1%zone~!cari info event%MELE%21623%42%0%")

        deadline = time.time() + 5
        while not sent and time.time() < deadline:
            time.sleep(0.05)
        assert seen.get("query") == "info event"
        assert sent and "hasil untuk info event" in sent[0]
        deadline = time.time() + 2
        while not any("hasil untuk info event" in pk for pk in mock_server.received) and time.time() < deadline:
            time.sleep(0.02)
        assert any("hasil untuk info event" in pk for pk in mock_server.received)

        # Non-owner `!` lines are ignored even though the text parses as admin.
        tools = Mock()
        router._admin_handler.tools = tools
        handled = router.handle_message("!cari rahasia", "Alice", sender_id=44)
        assert handled is False
        time.sleep(0.3)
        tools.web_search.assert_not_called()
    finally:
        orch.shutdown()
