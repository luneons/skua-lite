"""RED tests – multi-session farming: beberapa akun login dan broadcast perintah."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from skua_lite import runner
from skua_lite.credentials import MultiAccountStore
from skua_lite.mode import RunMode


# ---------------------------------------------------------------- MultiOrchestrator unit


def _make_orch(username: str, connected: bool = True) -> SimpleNamespace:
    bot = Mock()
    bot.username = username
    bot.current_map = "sevencircleswar-1"
    bot.state = "IN_MAP"
    farming = Mock()
    farming.status.return_value = f"[{username}] farming ON"
    farming.start_leveling.return_value = f"leveling dimulai untuk {username}"
    farming.stop_leveling.return_value = f"leveling berhenti untuk {username}"
    orch = SimpleNamespace(
        bot=bot if connected else None,
        farming=farming if connected else None,
        server_name="Yorumi",
        accounts=None,
        store=None,
    )
    return orch


def test_multi_orchestrator_holds_multiple_slots():
    from skua_lite.multi_session import MultiOrchestrator

    mo = MultiOrchestrator()
    orch1 = _make_orch("Hero1")
    orch2 = _make_orch("Hero2")

    mo.add_slot("Hero1", orch1)
    mo.add_slot("Hero2", orch2)

    assert mo.slot_count() == 2
    assert mo.get_slot("Hero1") is orch1
    assert mo.get_slot("Hero2") is orch2


def test_multi_orchestrator_list_usernames():
    from skua_lite.multi_session import MultiOrchestrator

    mo = MultiOrchestrator()
    mo.add_slot("Alice", _make_orch("Alice"))
    mo.add_slot("Bob", _make_orch("Bob"))

    names = mo.list_usernames()
    assert set(names) == {"Alice", "Bob"}


def test_multi_orchestrator_remove_slot():
    from skua_lite.multi_session import MultiOrchestrator

    mo = MultiOrchestrator()
    mo.add_slot("Hero1", _make_orch("Hero1"))
    mo.add_slot("Hero2", _make_orch("Hero2"))

    removed = mo.remove_slot("Hero1")
    assert removed is True
    assert mo.slot_count() == 1
    assert mo.list_usernames() == ["Hero2"]

    assert mo.remove_slot("Nonexistent") is False


# ---------------------------------------------------------------- broadcast


def test_broadcast_dispatch_hits_all_active_slots():
    from skua_lite.multi_session import MultiOrchestrator

    calls: dict[str, list] = {}

    def fake_dispatch(orch, action, arg):
        name = orch.bot.username
        calls.setdefault(name, []).append((action, arg))
        return "farm"

    mo = MultiOrchestrator(run_command=fake_dispatch)
    mo.add_slot("Alice", _make_orch("Alice"))
    mo.add_slot("Bob", _make_orch("Bob"))

    results = mo.broadcast("level", "100")

    assert set(results.keys()) == {"Alice", "Bob"}
    assert ("level", "100") in calls["Alice"]
    assert ("level", "100") in calls["Bob"]


def test_broadcast_skips_disconnected_slots():
    from skua_lite.multi_session import MultiOrchestrator

    calls: dict[str, list] = {}

    def fake_dispatch(orch, action, arg):
        name = orch.bot.username
        calls.setdefault(name, []).append((action, arg))
        return "farm"

    mo = MultiOrchestrator(run_command=fake_dispatch)
    mo.add_slot("Online", _make_orch("Online", connected=True))
    mo.add_slot("Offline", _make_orch("Offline", connected=False))

    mo.broadcast("level", "100")

    assert "Online" in calls
    assert "Offline" not in calls


def test_broadcast_returns_per_slot_output():
    from skua_lite.multi_session import MultiOrchestrator
    import io
    from contextlib import redirect_stdout

    def fake_dispatch(orch, action, arg):
        print(f"[{orch.bot.username}] {action} dimulai")
        return "farm"

    mo = MultiOrchestrator(run_command=fake_dispatch)
    mo.add_slot("Alice", _make_orch("Alice"))
    mo.add_slot("Bob", _make_orch("Bob"))

    results = mo.broadcast("level", "100")

    assert "Alice" in results["Alice"] or "Alice" in results
    assert "Bob" in results["Bob"] or "Bob" in results


# ---------------------------------------------------------------- status


def test_multi_status_aggregates_all_slots():
    from skua_lite.multi_session import MultiOrchestrator

    mo = MultiOrchestrator()
    mo.add_slot("Alice", _make_orch("Alice"))
    mo.add_slot("Bob", _make_orch("Bob"))

    status = mo.status_all()

    assert "Alice" in status
    assert "Bob" in status
    assert len(status) == 2


# ---------------------------------------------------------------- Telegram broadcast integration


def test_telegram_broadcast_level_to_all_slots():
    """Telegram /level 100 harus dikirim ke semua slot aktif."""
    from skua_lite.multi_session import MultiOrchestrator
    from skua_lite.telegram_control import TelegramControl

    class FakeTransport:
        def __init__(self):
            self.sent: list[tuple] = []
            self.answered: list = []
            self.edits: list = []

        def get_me(self):
            return {"id": 1, "username": "bot"}

        def get_updates(self, offset=None, timeout=25):
            raise Exception("stop")

        def send_message(self, chat_id, text, *, buttons=None):
            self.sent.append((chat_id, text))
            return {"message_id": len(self.sent)}

        def answer_callback_query(self, cid, text=""):
            self.answered.append((cid, text))

        def edit_message_text(self, chat_id, msg_id, text, *, buttons=None):
            self.edits.append((chat_id, msg_id, text))

    broadcast_calls: list[tuple] = []

    mo = MultiOrchestrator()
    mo.add_slot("Alice", _make_orch("Alice"))
    mo.add_slot("Bob", _make_orch("Bob"))

    # Intercept broadcast
    original_broadcast = mo.broadcast
    def capturing_broadcast(action, arg):
        broadcast_calls.append((action, arg))
        return original_broadcast(action, arg)
    mo.broadcast = capturing_broadcast

    transport = FakeTransport()
    control = TelegramControl(mo, transport, owner_id=555)

    msg = {
        "message_id": 1,
        "from": {"id": 555, "first_name": "Boss"},
        "chat": {"id": 99, "type": "private"},
        "text": "/level 100",
    }
    control.handle_message(msg)

    # Broadcast harus dipanggil
    assert any(a == "level" and arg == "100" for a, arg in broadcast_calls)
    # Balas harus dikirim ke owner
    assert len(transport.sent) == 1
