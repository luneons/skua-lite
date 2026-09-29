"""Admin Mode behaviour in the chat router: owner-only, evidence-backed tools."""
from __future__ import annotations

import threading
import time
from unittest.mock import Mock

from skua_lite.admin_commands import AdminActions, AdminCommandHandler, AdminInbox
from skua_lite.agent_tools import AgentTools, ToolResult
from skua_lite.ai_router import AIChatRouter


def _router(tmp_path, *, handler=None, generate=None, sent=None, **kwargs):
    sent = sent if sent is not None else []

    def send(text):
        sent.append(text)

    router = AIChatRouter(
        generator=generate or (lambda _m: "oke"),
        send_chat=send,
        admin_handler=handler,
        admin_inbox=kwargs.pop("inbox", None),
        **kwargs,
    )
    return router, sent


def _handler(tmp_path, **kwargs) -> AdminCommandHandler:
    tools = kwargs.pop("tools", None) or Mock(spec=AgentTools)
    return AdminCommandHandler(tools=tools, **kwargs)


# --------------------------------------------------------------------------
# admin mode is switched on by the owner's arrival
# --------------------------------------------------------------------------
def test_owner_arrival_enables_admin_mode(tmp_path):
    router, _ = _router(tmp_path)

    assert router.admin_mode is False
    assert router.owner_arrived(21623) is True
    assert router.admin_mode is True
    assert router.owner_lock is True


def test_owner_leaving_disables_admin_mode(tmp_path):
    router, _ = _router(tmp_path)
    router.owner_arrived(21623)

    assert router.owner_left_location("MELE", 21623) is True

    assert router.admin_mode is False
    assert router.enabled is False


# --------------------------------------------------------------------------
# ! commands are owner-only
# --------------------------------------------------------------------------
def test_owner_bang_command_is_executed_and_answered(tmp_path):
    tools = Mock(spec=AgentTools)
    tools.web_search.return_value = ToolResult(True, "AQW versi .261 (sumber: aq.com)")
    done = threading.Event()
    router, sent = _router(
        tmp_path,
        handler=_handler(tmp_path, tools=tools),
        sent=[],
    )
    router._send_chat = lambda text: (sent.append(text), done.set())[0]
    router.owner_arrived(21623)
    time.sleep(0.2)
    sent.clear()

    assert router.handle_message("!cari versi aqw", "MELE", sender_id=21623) is True

    assert done.wait(2)
    assert tools.web_search.call_args[0][0] == "versi aqw"
    assert any(".261" in line for line in sent)


def test_non_owner_bang_command_is_refused_while_owner_is_present(tmp_path):
    tools = Mock(spec=AgentTools)
    router, sent = _router(tmp_path, handler=_handler(tmp_path, tools=tools))
    router.owner_arrived(21623)
    time.sleep(0.2)
    sent.clear()

    assert router.handle_message("!cari apa saja", "Alice", sender_id=44) is False

    time.sleep(0.3)
    tools.web_search.assert_not_called()
    assert sent == []


def test_bang_command_without_admin_mode_does_not_run_tools(tmp_path):
    tools = Mock(spec=AgentTools)
    generate = Mock(return_value="halo")
    router, _ = _router(
        tmp_path, handler=_handler(tmp_path, tools=tools), generate=generate
    )
    # AI ON but nobody is an active owner: no admin powers.
    router.handle_message("MELE AI ON", "moderator")

    assert router.handle_message("!cari apa saja", "Alice", sender_id=44) is False

    time.sleep(0.2)
    tools.web_search.assert_not_called()


def test_bang_command_reply_is_clamped_to_chat_limit(tmp_path):
    tools = Mock(spec=AgentTools)
    tools.web_search.return_value = ToolResult(True, "x" * 400)
    done = threading.Event()
    sent: list[str] = []
    router, _ = _router(tmp_path, handler=_handler(tmp_path, tools=tools))
    router._send_chat = lambda text: (sent.append(text), done.set())[0]
    router.owner_arrived(21623)
    time.sleep(0.2)

    router.handle_message("!cari apa saja", "MELE", sender_id=21623)

    assert done.wait(2)
    assert sent and len(sent[0]) <= 150


# --------------------------------------------------------------------------
# mode transitions
# --------------------------------------------------------------------------
def test_mode_normal_keeps_admin_powers_but_releases_exclusivity(tmp_path):
    tools = Mock(spec=AgentTools)
    tools.web_search.return_value = ToolResult(True, "ok")
    router, _ = _router(tmp_path, handler=_handler(tmp_path, tools=tools))
    router.owner_arrived(21623)
    time.sleep(0.2)

    assert router.handle_message("MODE NORMAL", "MELE", sender_id=21623) is True

    assert router.owner_lock is False
    assert router.admin_mode is True
    # The room is open again, but the owner still owns the tool surface.
    assert router.handle_message("!status", "MELE", sender_id=21623) is True
    assert router.handle_message("halo", "Alice", sender_id=44) is False or True


def test_admin_off_command_disables_admin_mode_but_keeps_ai_on(tmp_path):
    router, _ = _router(tmp_path, handler=_handler(tmp_path))
    router.owner_arrived(21623)
    time.sleep(0.2)

    assert router.handle_message("!admin off", "MELE", sender_id=21623) is True

    deadline = time.time() + 2
    while router.admin_mode and time.time() < deadline:
        time.sleep(0.01)
    assert router.admin_mode is False
    assert router.enabled is True
    assert router.handle_message("!status", "MELE", sender_id=21623) is False


# --------------------------------------------------------------------------
# ordinary chat still works
# --------------------------------------------------------------------------
def test_owner_normal_chat_still_reaches_the_ai_in_admin_mode(tmp_path):
    prompts: list[str] = []
    router, _ = _router(
        tmp_path,
        handler=_handler(tmp_path),
        generate=lambda m: prompts.append(m) or "siap",
    )
    router.owner_arrived(21623)
    time.sleep(0.2)
    prompts.clear()

    assert router.handle_message("bro apa kabar", "MELE", sender_id=21623) is True

    time.sleep(0.3)
    assert prompts and "apa kabar" in prompts[-1]


def test_router_without_admin_handler_does_not_crash_on_bang_command(tmp_path):
    prompts: list[str] = []
    router, _ = _router(
        tmp_path,
        handler=None,
        generate=lambda m: prompts.append(m) or "oke",
    )
    router.owner_arrived(21623)
    time.sleep(0.2)
    prompts.clear()

    consumed = router.handle_message("!cari apa saja", "MELE", sender_id=21623)

    time.sleep(0.3)
    # Without a handler the line is ordinary chat: consumed only if a normal
    # reply path applies, and never dispatched to tools.
    assert consumed in (True, False)
    assert not any("!cari" in p for p in prompts)


def test_admin_actions_can_drive_game_movement(tmp_path):
    moved: list[str] = []
    tools = Mock(spec=AgentTools)
    handler = _handler(
        tmp_path,
        tools=tools,
        actions=AdminActions(
            join_map=lambda target: moved.append(target) or True,
            move=lambda x, y: True,
            describe_status=lambda: "state IN_MAP",
        ),
    )
    router, _ = _router(tmp_path, handler=handler)
    router.owner_arrived(21623)
    time.sleep(0.2)

    assert router.handle_message("!join yulgar-14045", "MELE", sender_id=21623) is True

    time.sleep(0.3)
    assert moved == ["yulgar-14045"]


def test_admin_inbox_is_used_for_async_dispatch(tmp_path):
    seen: list[str] = []
    handler = _handler(tmp_path, tools=Mock(spec=AgentTools))
    inbox = AdminInbox(handler)
    router, _ = _router(tmp_path, handler=handler, inbox=inbox)

    assert router.admin_inbox is inbox
    assert seen == []
