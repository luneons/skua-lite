"""Tests for the owner-only `!` admin command layer (offline, no subprocess)."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import Mock

from skua_lite.admin_commands import (
    AdminActions,
    AdminCommandHandler,
    AdminInbox,
    AdminOutcome,
    parse_admin_command,
    resolve_room_target,
    split_private_flag,
)
from skua_lite.agent_tools import AgentTools, ToolResult


def _handler(tmp_path: Path, **kwargs) -> AdminCommandHandler:
    tools = kwargs.pop("tools", None) or AgentTools(tmp_path)
    return AdminCommandHandler(tools=tools, **kwargs)


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------
def test_parse_recognises_known_admin_commands():
    assert parse_admin_command("!cari harga emas") == ("cari", "harga emas")
    assert parse_admin_command("  !STATUS ") == ("status", "")
    assert parse_admin_command("!join yulgar-14045") == ("join", "yulgar-14045")


def test_private_flag_is_only_a_separated_trailing_marker():
    assert split_private_flag("yulgar") == ("yulgar", False)
    assert split_private_flag("yulgar-14045") == ("yulgar-14045", False)
    assert split_private_flag("yulgar -private") == ("yulgar", True)
    assert split_private_flag("sevencircleswar PRIVATE") == ("sevencircleswar", True)
    assert split_private_flag("-private") == ("", True)


def test_private_room_resolution_preserves_explicit_numeric_rooms():
    assert resolve_room_target("yulgar", private=False) == "yulgar"
    assert resolve_room_target("yulgar", private=True) == "yulgar-100000"
    assert resolve_room_target("yulgar-14045", private=True) == "yulgar-14045"


def test_admin_join_uses_public_by_default_and_private_only_on_request(tmp_path):
    joined: list[str] = []
    actions = AdminActions(join_map=lambda target: joined.append(target) or True)
    handler = _handler(tmp_path, actions=actions)

    outcome = handler.handle("MELE", "!join yulgar")
    assert outcome.consumed is True
    assert joined == ["yulgar"]

    outcome = handler.handle("MELE", "!join yulgar -private")
    assert outcome.consumed is True
    assert joined[-1] == "yulgar-100000"
    assert "private" in outcome.reply.lower()


def test_parse_ignores_plain_chat_and_unknown_bang_words():
    assert parse_admin_command("halo semua") is None
    assert parse_admin_command("!halo") is None
    assert parse_admin_command("") is None


# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------
def test_cari_calls_web_search_and_returns_clamped_reply(tmp_path):
    tools = Mock(spec=AgentTools)
    tools.web_search.return_value = ToolResult(True, "Gold naik 2% (sumber: x.com)")
    handler = _handler(tmp_path, tools=tools)

    outcome = handler.handle("MELE", "!cari harga emas hari ini")

    tools.web_search.assert_called_once_with("harga emas hari ini")
    assert outcome.consumed is True
    assert "Gold naik" in outcome.reply
    assert len(outcome.reply) <= 150


def test_tool_exception_becomes_a_reply_instead_of_crashing(tmp_path):
    tools = Mock(spec=AgentTools)
    tools.web_search.side_effect = RuntimeError("network down")
    handler = _handler(tmp_path, tools=tools)

    outcome = handler.handle("MELE", "!cari apa saja")

    assert outcome.consumed is True
    assert outcome.reply
    assert "network down" not in outcome.reply  # internal detail stays in logs


def test_status_uses_injected_status_provider(tmp_path):
    actions = AdminActions(describe_status=lambda: "map yulgar, afk aktif")
    handler = _handler(tmp_path, actions=actions)

    outcome = handler.handle("MELE", "!status")

    assert "yulgar" in outcome.reply


# --------------------------------------------------------------------------
# self-upgrade is two-step: propose, then execute on confirmation
# --------------------------------------------------------------------------
def test_upgrade_asks_before_executing(tmp_path):
    tools = Mock(spec=AgentTools)
    handler = _handler(tmp_path, tools=tools)

    outcome = handler.handle("MELE", "!upgrade tambah fitur rekap harian")

    assert outcome.consumed is True
    assert "tambah fitur rekap harian" in outcome.reply
    tools.project_upgrade.assert_not_called()
    assert handler.pending_upgrade == "tambah fitur rekap harian"


def test_upgrade_runs_after_ok_confirmation(tmp_path):
    tools = Mock(spec=AgentTools)
    tools.project_upgrade.return_value = ToolResult(
        True,
        "Upgrade selesai. Ubah: src/mod.py. 12 test lulus",
        evidence={"changed": ["src/mod.py"], "tests": {"passed": True}},
    )
    handler = _handler(tmp_path, tools=tools)
    handler.handle("MELE", "!upgrade tambah fitur")

    outcome = handler.handle("MELE", "!upgrade ok")

    tools.project_upgrade.assert_called_once_with("tambah fitur")
    assert "12 test lulus" in outcome.reply
    assert handler.pending_upgrade is None


def test_upgrade_ok_without_a_plan_does_nothing(tmp_path):
    tools = Mock(spec=AgentTools)
    handler = _handler(tmp_path, tools=tools)

    outcome = handler.handle("MELE", "!upgrade ok")

    tools.project_upgrade.assert_not_called()
    assert "menunggu" in outcome.reply.lower()


# --------------------------------------------------------------------------
# movement
# --------------------------------------------------------------------------
def test_join_and_move_use_injected_game_actions(tmp_path):
    joined: list[str] = []
    moved: list[tuple[int, int]] = []
    actions = AdminActions(
        join_map=lambda target: joined.append(target) or True,
        move=lambda x, y: moved.append((x, y)) or True,
    )
    handler = _handler(tmp_path, actions=actions)

    assert handler.handle("MELE", "!join yulgar-14045").consumed is True
    assert handler.handle("MELE", "!move 850 302").consumed is True

    assert joined == ["yulgar-14045"]
    assert moved == [(850, 302)]


def test_move_rejects_non_numeric_coordinates(tmp_path):
    actions = AdminActions(move=lambda x, y: True)
    handler = _handler(tmp_path, actions=actions)

    outcome = handler.handle("MELE", "!move jauh sekali")

    assert outcome.consumed is True
    assert "format" in outcome.reply.lower()


def test_failed_join_is_reported_as_failure(tmp_path):
    handler = _handler(tmp_path, actions=AdminActions(join_map=lambda _t: False))

    outcome = handler.handle("MELE", "!join nowhere")

    assert "gagal" in outcome.reply.lower()


# --------------------------------------------------------------------------
# admin off signals the router
# --------------------------------------------------------------------------
def test_admin_off_raises_the_signal_instead_of_a_plain_reply(tmp_path):
    handler = _handler(tmp_path)

    outcome = handler.handle("MELE", "!admin off")

    assert outcome.consumed is True
    assert outcome.admin_off is True


def test_help_lists_the_command_surface(tmp_path):
    handler = _handler(tmp_path)

    outcome = handler.handle("MELE", "!bantuan")

    assert "!cari" in outcome.reply
    assert "!upgrade" in outcome.reply


def test_non_admin_chat_is_not_consumed(tmp_path):
    handler = _handler(tmp_path)

    outcome = handler.handle("MELE", "halo mele")

    assert outcome.consumed is False
    assert isinstance(outcome, AdminOutcome)


# --------------------------------------------------------------------------
# inbox: async handoff, off-signal propagation
# --------------------------------------------------------------------------
def test_inbox_returns_false_for_non_admin_lines(tmp_path):
    inbox = AdminInbox(_handler(tmp_path))

    assert inbox.submit("MELE", "halo", lambda _t: None) is False


def test_inbox_sends_reply_and_signals_admin_off(tmp_path):
    sent: list[str] = []
    done = threading.Event()
    off_calls: list[bool] = []
    handler = _handler(tmp_path)

    def send(text: str) -> None:
        sent.append(text)
        done.set()

    inbox = AdminInbox(handler)
    assert inbox.submit("MELE", "!admin off", send, on_off=lambda: off_calls.append(True)) is True

    assert done.wait(2)
    assert off_calls == [True]
    assert sent and "off" in sent[0].lower()


def test_inbox_swallows_send_errors(tmp_path):
    logs: list[str] = []
    handler = _handler(tmp_path, on_log=logs.append)

    def boom(_text: str) -> None:
        raise OSError("socket closed")

    inbox = AdminInbox(handler)
    assert inbox.submit("MELE", "!status", boom) is True
    time.sleep(0.3)
    assert any("gagal mengirim" in line for line in logs)
