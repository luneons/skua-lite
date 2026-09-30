"""RED tests – multi-session CLI loop: broadcast, quit, dan stop semua."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch


def _make_orch(username: str) -> SimpleNamespace:
    bot = Mock()
    bot.username = username
    bot.current_map = "sevencircleswar-1"
    bot.state = "IN_MAP"
    farming = Mock()
    farming.status.return_value = f"[{username}] farming ON"
    farming.start_leveling.return_value = f"leveling dimulai untuk {username}"
    farming.stop_leveling.return_value = f"leveling berhenti untuk {username}"
    return SimpleNamespace(bot=bot, farming=farming, server_name="Yorumi")


def test_multi_farm_menu_loop_quit_stops_all_slots():
    from skua_lite.cli import multi_farm_menu_loop
    from skua_lite.multi_session import MultiOrchestrator
    from unittest.mock import Mock, patch

    orch1 = _make_orch("Hero1")
    orch2 = _make_orch("Hero2")
    mo = MultiOrchestrator()
    mo.add_slot("Hero1", orch1)
    mo.add_slot("Hero2", orch2)

    with patch("builtins.input", side_effect=["quit"]):
        multi_farm_menu_loop(mo)

    orch1.bot.stop.assert_called_once()
    orch2.bot.stop.assert_called_once()


def test_multi_cli_broadcasts_farm_commands():
    from skua_lite.cli import multi_farm_menu_loop
    from skua_lite.multi_session import MultiOrchestrator
    from unittest.mock import patch

    orch1 = _make_orch("Hero1")
    orch2 = _make_orch("Hero2")
    mo = MultiOrchestrator()
    mo.add_slot("Hero1", orch1)
    mo.add_slot("Hero2", orch2)

    # Kirim .level 100 lalu quit
    with patch("builtins.input", side_effect=[".level 100", "quit"]):
        multi_farm_menu_loop(mo)

    orch1.farming.start_leveling.assert_called_once_with(100, private=False)
    orch2.farming.start_leveling.assert_called_once_with(100, private=False)
