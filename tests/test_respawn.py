"""Test auto-respawn saat karakter mati saat leveling."""
import time
import threading
from unittest.mock import Mock, call, patch

from skua_lite import combat, sfs
from skua_lite.combat import AutoAttackEngine, CombatState, generic_profile


def _death_pkt(username: str, hp: int = 0, state: int = 0) -> str:
    return f"%xt%zm%uotls%-1%{username}%intHP={hp}%intState={state}%"


def _res_timed_pkt(room: int, cell: str = "Enter", pad: str = "Spawn") -> str:
    return f"%xt%zm%resTimed%-1%{cell}%{pad}%"


def test_engine_sends_respawn_after_delay_when_dead():
    """Setelah mati & delay respawn, engine kirim resPlayerTimed."""
    bot = Mock(room_id=42, session_user_id=999)
    engine = AutoAttackEngine(
        bot, target_name="Wrath Guard", class_profile=generic_profile("Mage"),
        respawn_delay=0.0,
    )
    engine.state.seen_self = True
    engine.state.player_state = 0
    engine.state.hp = 0
    engine.state.self_user_id = 999

    engine.tick()

    calls = bot._send_raw.call_args_list
    respawn_sent = any(
        b"%resPlayerTimed%" in call.args[0]
        for call in calls
    )
    assert respawn_sent, f"resPlayerTimed tidak dikirim; calls: {calls}"


def test_engine_does_not_respawn_before_delay():
    bot = Mock(room_id=42, session_user_id=999)
    engine = AutoAttackEngine(
        bot, target_name="Wrath Guard", class_profile=generic_profile("Mage"),
        respawn_delay=100.0,
    )
    engine.state.seen_self = True
    engine.state.player_state = 0
    engine.state.hp = 0
    engine.state.self_user_id = 999

    engine.tick()

    calls = bot._send_raw.call_args_list
    assert not any(b"%resPlayerTimed%" in c.args[0] for c in calls)


def test_engine_returns_to_spot_cell_after_respawn():
    """Setelah respawn ke Enter, engine harus kembali ke spot leveling cell."""
    bot = Mock(room_id=42, session_user_id=999)
    engine = AutoAttackEngine(
        bot, target_name="Wrath Guard", class_profile=generic_profile("Mage"),
        respawn_delay=0.0,
    )
    engine.state.seen_self = True
    engine.state.player_state = 1
    engine.state.hp = 100

    # Simulate resTimed inbound
    pkt = _res_timed_pkt(42, "r9", "Left")
    engine.feed(pkt)

    # Verify moveToCell sent with correct target
    calls = bot._send_raw.call_args_list
    move_sent = any(
        b"%moveToCell%" in c.args[0] and b"%r9%" in c.args[0]
        for c in calls
    )
    assert move_sent, f"moveToCell r9 tidak dikirim setelah resTimed; calls: {calls}"


def test_leveling_loop_auto_respawns_on_death(monkeypatch):
    """Loop leveling tidak freeze saat karakter mati; bot auto respawn."""
    import skua_lite.farming as farming

    bot = Mock(level=8, current_map="sevencircleswar-1", room_id=42, session_user_id=999)
    runtime = farming.FarmingRuntime(bot=bot)

    state = Mock(cell="r9", map_file_name="sevencircleswar.swf", player_state=0, hp=0, seen_self=True)
    engine = Mock()
    engine.state = state
    engine.running = True
    runtime.combat = engine

    gate_pkt = '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":1,"QuestID":7977,"msg":"success"}}}'
    runtime.feed_packet(gate_pkt)

    logs = []
    runtime._on_log = logs.append
    runtime._send = Mock()
    runtime._leveling_target = 100
    runtime._leveling_stop.clear()

    old_sleep = time.sleep
    monkeypatch.setattr(time, "sleep", lambda _s: old_sleep(0.01))

    thread = threading.Thread(target=runtime._leveling_loop)
    thread.start()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if any("respawn" in l.lower() or "mati" in l.lower() for l in logs):
            break
        old_sleep(0.05)
    runtime._leveling_stop.set()
    thread.join(timeout=1)

    assert any("respawn" in l.lower() or "mati" in l.lower() for l in logs), (
        f"Tidak ada log respawn/mati: {logs}"
    )
