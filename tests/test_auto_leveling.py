"""Character level tracking and auto-leveling runtime logic."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from skua_lite import bot as bot_module, cli
from skua_lite.farming import FarmingRuntime
from skua_lite.servers import Server


def _bot():
    return bot_module.AQWBot(
        username="user",
        token="FAKE-TOKEN",
        server=Server("Test", "127.0.0.1", 5588, True, False, False),
    )


def test_bot_extracts_level_from_login_packet():
    bot = _bot()
    packet = json.dumps({"t": "xt", "b": {"r": -1, "o": {
        "cmd": "loginResponse", "login": {
            "bSuccess": 1, "userid": 12345678, "iLevel": 35
        }
    }}})

    bot._track_character_level(packet)

    assert bot.level == 35


def test_bot_updates_level_from_server_level_packet():
    bot = _bot()
    bot.level = 35

    bot._handle_server_packet("%xt%server%-1%level%36%1000%5000%")

    assert bot.level == 36


def test_farming_runtime_evaluates_leveling_progression_from_skua_rules():
    runtime = FarmingRuntime(bot=Mock(level=22))

    spot = runtime.auto_level_spot()
    assert (spot.map_name, spot.cell, spot.pad, spot.quests) == (
        "icestormarena", "r7", "Left", (6628,)
    )

    runtime.bot.level = 27
    spot = runtime.auto_level_spot()
    assert (spot.map_name, spot.cell, spot.quests) == (
        "icestormarena", "r10", (6628,)
    )

    runtime.bot.level = 32
    spot = runtime.auto_level_spot()
    assert (spot.map_name, spot.cell, spot.quests) == (
        "icestormarena", "r11", (6629,)
    )

    runtime.bot.level = 40
    spot = runtime.auto_level_spot()
    assert (spot.map_name, spot.cell, spot.quests) == (
        "icestormarena", "r14", (6629,)
    )

    runtime.bot.level = 55
    spot = runtime.auto_level_spot()
    assert (spot.map_name, spot.cell, spot.quests) == (
        "icestormarena", "r16", (6629,)
    )

    runtime.bot.level = 65
    spot = runtime.auto_level_spot()
    assert (spot.map_name, spot.cell, spot.pad, spot.quests) == (
        "battlegrounde", "r2", "center", (3991, 3992)
    )

    runtime.bot.level = 80
    spot = runtime.auto_level_spot()
    assert (spot.map_name, spot.cell, spot.pad, spot.quests) == (
        "icestormunder", "r2", "Top", ()
    )

    runtime.bot.level = 100
    assert runtime.auto_level_spot() is None


def test_auto_level_low_level_uses_oaklore_before_icestorm():
    runtime = FarmingRuntime(bot=Mock(level=7))
    spot = runtime.auto_level_spot()
    assert (spot.map_name, spot.cell, spot.pad, spot.target, spot.quests) == (
        "oaklore", "r3", "Left", "Bone Berserker", (4007, 6257)
    )


def test_auto_level_10_to_19_uses_undead_giant():
    runtime = FarmingRuntime(bot=Mock(level=12))
    spot = runtime.auto_level_spot()
    assert (spot.map_name, spot.cell, spot.pad, spot.target, spot.quests) == (
        "swordhavenundead", "Gates", "Left", "Undead Giant", (178,)
    )


def test_auto_level_command_wires_to_farming_runtime(capsys):
    runtime = Mock()
    runtime.start_leveling.return_value = "auto leveling level 65 → 100"
    orch = SimpleNamespace(farming=runtime, bot=Mock(level=65))

    result = cli.dispatch_farm(orch, "level", "auto")

    assert result == "farm"
    runtime.start_leveling.assert_called_once_with(100)
    assert "level 65" in capsys.readouterr().out


def test_level_command_defaults_to_auto_and_accepts_target(capsys):
    runtime = Mock()
    runtime.start_leveling.return_value = "auto leveling level 35 → 100"
    orch = SimpleNamespace(farming=runtime, bot=Mock(level=35))

    assert cli.dispatch_farm(orch, "level", "") == "farm"
    runtime.start_leveling.assert_called_once_with(100)

    runtime.reset_mock()
    runtime.start_leveling.return_value = "auto leveling level 35 → 80"
    assert cli.dispatch_farm(orch, "level", "80") == "farm"
    runtime.start_leveling.assert_called_once_with(80)


def test_level_stop_stops_leveling_only(capsys):
    runtime = Mock()
    runtime.stop_leveling.return_value = "auto leveling dihentikan"
    orch = SimpleNamespace(farming=runtime, bot=Mock(level=35))

    assert cli.dispatch_farm(orch, "level", "stop") == "farm"
    runtime.stop_leveling.assert_called_once()


def test_start_and_stop_leveling_toggle_state_without_joining():
    import time

    bot = _bot()
    bot.level = 12
    bot.current_map = "swordhavenundead-100000"
    runtime = FarmingRuntime(bot=bot)
    runtime.join = Mock()
    runtime.combat = Mock()
    runtime.combat.running = True
    runtime.combat.state = Mock(cell="Gates", map_file_name="swordhavenundead.swf")
    runtime._send = Mock()

    runtime.start_leveling(100)
    runtime.join.assert_not_called()

    runtime.stop_leveling()
    deadline = time.monotonic() + 5
    while runtime.is_leveling() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not runtime.is_leveling()


def test_leveling_loop_retargets_named_monster(monkeypatch):
    import threading

    bot = _bot()
    bot.level = 12  # swordhavenundead / Undead Giant
    bot.current_map = "swordhavenundead-100000"
    bot.room_id = 42
    runtime = FarmingRuntime(bot=bot)

    state = Mock()
    state.cell = "Gates"
    state.map_file_name = "swordhavenundead.swf"
    runtime.combat = Mock()
    runtime.combat.state = state
    runtime.combat.running = True
    runtime.join = Mock()
    runtime.move_to_cell = Mock()
    runtime._send = Mock()

    runtime._leveling_target = 100
    runtime._leveling_stop.clear()

    import time
    old_sleep = time.sleep
    monkeypatch.setattr(time, "sleep", lambda s: old_sleep(0.01))

    t = threading.Thread(target=runtime._leveling_loop)
    t.start()
    deadline = time.monotonic() + 3
    while runtime.combat.set_target.call_count == 0 and time.monotonic() < deadline:
        old_sleep(0.05)
    runtime._leveling_stop.set()
    t.join(timeout=2.0)

    runtime.combat.set_target.assert_called_with("Undead Giant")


def test_start_leveling_does_not_join_before_background_loop():
    runtime = FarmingRuntime(bot=Mock(level=22))
    runtime.join = Mock(side_effect=AssertionError("join called synchronously"))
    runtime._leveling_loop = Mock()

    message = runtime.start_leveling(100)

    assert message == "auto leveling level 22 → 100"
    runtime.join.assert_not_called()


def test_leveling_loop_survives_join_bot_error(monkeypatch):
    import threading
    from skua_lite.bot import BotError
    
    bot = _bot()
    bot.level = 22
    bot.current_map = "battleon-1"
    runtime = FarmingRuntime(bot=bot)
    
    # Track calls and force exception on first join
    joins = []
    def fake_join(target):
        joins.append(target)
        if len(joins) == 1:
            raise BotError("cannot join map right now")
        bot.current_map = target
    
    runtime.join = fake_join
    runtime.combat.start = Mock()
    runtime.combat.stop = Mock()
    runtime._leveling_target = 100
    runtime._leveling_stop.clear()
    
    t = threading.Thread(target=runtime._leveling_loop)
    t.start()
    
    # Let it tick twice so it survives the BotError and succeeds next time
    import time
    deadline = time.monotonic() + 3
    while len(joins) < 2 and time.monotonic() < deadline:
        time.sleep(0.05)
        
    runtime._leveling_stop.set()
    t.join(timeout=1.0)
    
    assert len(joins) >= 2
    assert joins[0] == "icestormarena-100000"


def test_leveling_loop_rate_limits_quest_accepts(monkeypatch):
    import threading
    
    bot = _bot()
    bot.level = 22
    bot.current_map = "icestormarena-100000"
    bot.room_id = 42
    runtime = FarmingRuntime(bot=bot)
    
    # Give fake state to bypass move/combat start wait
    state = Mock()
    state.cell = "r7"
    state.map_file_name = "icestormarena.swf"
    runtime.combat.state = state
    # fake running by overriding the whole object since it's a property
    runtime.combat = Mock()
    runtime.combat.state = state
    runtime.combat.running = True
    runtime.join = Mock()
    runtime.move_to_cell = Mock()
    
    sent = []
    runtime._send = lambda pkt, ctx: sent.append(pkt)

    def _blob(p):
        return p if isinstance(p, bytes) else str(p).encode("utf-8")

    runtime._leveling_target = 100
    runtime._leveling_stop.clear()

    # We stub sleep to simulate multiple fast iterations
    import time
    old_sleep = time.sleep
    def fast_sleep(s):
        old_sleep(0.01)
    monkeypatch.setattr(time, "sleep", fast_sleep)

    t = threading.Thread(target=runtime._leveling_loop)
    t.start()

    # wait for at least 4 loop iterations (each sends tryQuestComplete)
    deadline = time.monotonic() + 3
    while sum(1 for p in sent if b"tryQuestComplete" in _blob(p)) < 4 and time.monotonic() < deadline:
        old_sleep(0.05)

    runtime._leveling_stop.set()
    t.join(timeout=2.0)

    # Quest 6628 should be accepted ONLY ONCE despite 4+ iterations
    accepts = [p for p in sent if b"acceptQuest" in _blob(p) and b"6628" in _blob(p)]
    assert len(accepts) == 1
