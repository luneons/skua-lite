"""Test integrasi: alur penuh Orchestrator dengan mock HTTP + mock SFS."""
import io
import time
from unittest.mock import patch

import pytest

from skua_lite import bot as bot_mod
from skua_lite import credentials, login, runner, servers
from tests.test_client import MockSFSServer


class _FakeHTTP(io.BytesIO):
    def __init__(self, body: str):
        super().__init__(body.encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


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


def test_orchestrator_full_flow(mock_server, tmp_path, monkeypatch):
    # Patch HTTP login & server-list fetch langsung di titik panggilannya,
    # supaya tidak mengotak-atik urllib.request global.
    monkeypatch.setattr(
        login, "aqw_login",
        lambda u, p, *, timeout=20: login.LoginToken(
            username=u, token="TOK", success=True,
        ),
    )
    monkeypatch.setattr(
        servers, "fetch_server_list",
        lambda *, timeout=20: {"Yorumi": servers.Server(
            name="Yorumi",
            ip=mock_server.host,
            port=mock_server.port,
            online=True,
            full=False,
            upgrade_only=False,
        )},
    )
    monkeypatch.setenv("SKUA_AI_BASE_URL", "https://ai.example/v1")
    monkeypatch.setenv("SKUA_AI_API_KEY", "test-key")
    monkeypatch.setenv("SKUA_AI_MODEL", "test-model")
    monkeypatch.setattr(
        runner, "openai_chat_generator",
        lambda _cfg: (lambda _message: "jawaban santai"),
    )

    store = credentials.CredentialStore(base_dir=tmp_path)
    store.save("alice", "pw")

    # auto-jawab prompt "gunakan kredensial tersimpan? [Y/n]"
    monkeypatch.setattr("builtins.input", lambda *a, **k: "y")

    orch = runner.Orchestrator(server_name="Yorumi", target_map="yulgar-14045", store=store)
    orch.auto_relogin = False
    u, p = orch.obtain_credentials()
    assert u == "alice" and p == "pw"

    orch.connect(u, p)
    assert orch.bot is not None
    assert orch.bot.ai_router is not None
    assert orch.bot.ai_router.enabled is False
    assert orch.bot.state == bot_mod.BotState.IN_MAP
    assert orch.bot.current_map == "yulgar-14045"
    assert orch.bot.room_id == 42

    time.sleep(0.3)
    assert any("afk" in pk for pk in mock_server.received)

    orch.shutdown()
    assert orch.bot.state == bot_mod.BotState.STOPPED


def test_presence_capture_records_only_structural_presence(tmp_path):
    capture = tmp_path / "presence.log"
    orch = runner.Orchestrator(presence_capture_path=capture)

    orch._on_packet("%xt%chatm%-1%zone~secret chat%Alice%2%273%0%", False)
    orch._on_packet(
        "<msg t='sys'><body action='uER' r='273'>"
        "<u i='21631' n='ME LE'/></body></msg>",
        False,
    )

    contents = capture.read_text(encoding="utf-8")
    assert "secret chat" not in contents
    assert "action='uER'" in contents
    assert "21631" in contents


def test_credentials_saved_only_when_user_agrees(tmp_path, monkeypatch):
    store = credentials.CredentialStore(base_dir=tmp_path)
    orch = runner.Orchestrator(store=store)

    inputs = iter(["bob", "n"])  # username, jangan simpan
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(inputs))
    monkeypatch.setattr("getpass.getpass", lambda *a, **k: "secretpw")

    u, p = orch.obtain_credentials()
    assert u == "bob" and p == "secretpw"
    assert store.exists() is False
