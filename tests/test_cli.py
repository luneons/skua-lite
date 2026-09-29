"""Test menu CLI: parsing perintah dan dispatch aksi (tanpa I/O nyata)."""
import io
from unittest.mock import MagicMock, patch

import pytest

from skua_lite import cli


@pytest.fixture
def fake_bot():
    b = MagicMock()
    b.state = MagicMock()
    b.state.value = "IN_MAP"
    return b


def test_parse_chat_command():
    action, arg = cli.parse_command("chat halo dunia")
    assert action == "chat"
    assert arg == "halo dunia"


def test_parse_action_reload():
    action, arg = cli.parse_command("action reload")
    assert action == "action"
    assert arg == "reload"


def test_parse_action_debug_presence():
    assert cli.parse_command("debug") == ("debug", "")
    assert cli.parse_command("diag") == ("debug", "")


def test_parse_action_logout():
    action, arg = cli.parse_command("action logout")
    assert action == "action"
    assert arg == "logout"


def test_parse_action_minimize():
    action, arg = cli.parse_command("action minimize")
    assert action == "action"
    assert arg == "minimize"


def test_parse_menu_numbers():
    assert cli.parse_command("1") == ("menu", "chat")
    assert cli.parse_command("2") == ("menu", "action")
    assert cli.parse_command("3") == ("menu", "status")
    assert cli.parse_command("0") == ("menu", "quit")


def test_dispatch_chat_calls_bot(fake_bot):
    cli.dispatch(fake_bot, "chat", "halo")
    fake_bot.chat.assert_called_once_with("halo")


def test_dispatch_reload_calls_bot(fake_bot):
    cli.dispatch(fake_bot, "action", "reload")
    fake_bot.reload.assert_called_once()


def test_dispatch_logout_calls_bot(fake_bot):
    cli.dispatch(fake_bot, "action", "logout")
    fake_bot.logout.assert_called_once()


def test_dispatch_unknown_action_is_noop(fake_bot):
    # tidak boleh crash untuk aksi tak dikenal
    cli.dispatch(fake_bot, "action", "terbang")
    fake_bot.reload.assert_not_called()
    fake_bot.logout.assert_not_called()


def test_minimize_returns_flag_without_calling_bot(fake_bot):
    result = cli.dispatch(fake_bot, "action", "minimize")
    assert result == "minimize"
    fake_bot.reload.assert_not_called()
    fake_bot.logout.assert_not_called()
